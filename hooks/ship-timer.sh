#!/usr/bin/env bash
# spec-ship timer — измеряет активное время агента и его сабагентов, без
# простоя в ожидании юзера.
#
# Главная сессия:
#   UserPromptSubmit → active_since = now (юзер написал промпт, таймер стартует)
#   Stop             → total_active += now - active_since, active_since = null
#
# Сабагенты (Task-вызовы): не ждут юзера, работают от старта до стопа сплошным
# куском — время = SubagentStop.now - SubagentStart.now, простой вычитать не с чего.
#   SubagentStart → subagents[agent_id] = {agent_type, started: now}
#   SubagentStop  → subagents[agent_id].total += now - started
#
# ВАЖНО: total_active главной сессии и total сабагента ПЕРЕСЕКАЮТСЯ по времени —
# пока сабагент работает, главная сессия сидит внутри вызова Task и тоже
# считается "активной" (Stop до возврата из Task не наступает). total_active
# главной сессии уже покрывает весь wall-clock интервал сама по себе, включая
# время сабагентов внутри неё — НЕ складывать total_active + сумму subagents.*
# как "общее время работы", будет задвоение. Складывать сабагентов между собой
# можно, если нужна метрика "суммарное CPU-время всех агентов" (параллельные
# сабагенты складываются, а не берут max).
#
# Простой в PreToolUse permission-prompt (approval-диалог инструмента) отдельно
# не вычитается — Claude Code не даёt хук на сам диалог approval, только
# PreToolUse/PostToolUse вокруг вызова. Мера грубая, шум для секундной метрики.
#
# Состояние — per-session, ключ session_id. Всегда exit 0: хук не должен
# ломать работу агента.
#
# Параллельные сабагенты триггерят SubagentStop одновременно → без блокировки
# два jq-процесса читают state.json на старте друг друга и пишут поверх один
# другого (classic read-modify-write race), последний mv побеждает, первый
# потерян. Весь read-modify-write под flock -x на отдельный lock-файл —
# сериализует конкурентные вызовы хука, ни один результат не теряется.
#
# Переменные для тестов:
#   SHIP_TIMER_STATE — путь к state-файлу (по умолчанию .claude/state/ship-timer.json)

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
STATE_FILE="${SHIP_TIMER_STATE:-$ROOT/.claude/state/ship-timer.json}"
LOCK_FILE="$STATE_FILE.lock"

command -v jq >/dev/null 2>&1 || exit 0
command -v flock >/dev/null 2>&1 || exit 0

INPUT="$(cat)"
SESSION_ID="$(jq -r '.session_id // "default"' <<<"$INPUT" 2>/dev/null)"
HOOK_EVENT="$(jq -r '.hook_event_name // empty' <<<"$INPUT" 2>/dev/null)"
AGENT_ID="$(jq -r '.agent_id // empty' <<<"$INPUT" 2>/dev/null)"
AGENT_TYPE="$(jq -r '.agent_type // "unknown" | if . == "" then "unknown" else . end' <<<"$INPUT" 2>/dev/null)"
NOW="$(date +%s)"

mkdir -p "$(dirname "$STATE_FILE")"

update_state() {
    local filter="$1"
    shift
    [ -f "$STATE_FILE" ] || echo '{}' > "$STATE_FILE"
    local tmp="$STATE_FILE.tmp.$$"
    jq "$@" "$filter" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"
}

{
    flock -x 200

    case "$HOOK_EVENT" in
        UserPromptSubmit)
            # Не перезаписывать active_since, если уже тикает (защита от двойного старта).
            update_state '
                .[$s] //= {"active_since": null, "total_active": 0, "subagents": {}} |
                if .[$s].active_since == null then .[$s].active_since = $now else . end
            ' --arg s "$SESSION_ID" --argjson now "$NOW"
            ;;
        Stop)
            update_state '
                .[$s] //= {"active_since": null, "total_active": 0, "subagents": {}} |
                if .[$s].active_since != null then
                    .[$s].total_active += ($now - .[$s].active_since) | .[$s].active_since = null
                else . end
            ' --arg s "$SESSION_ID" --argjson now "$NOW"
            ;;
        SubagentStart)
            [ -n "$AGENT_ID" ] || exit 0
            update_state '
                .[$s] //= {"active_since": null, "total_active": 0, "subagents": {}} |
                .[$s].subagents[$a] = {"agent_type": $t, "started": $now, "total": 0}
            ' --arg s "$SESSION_ID" --arg a "$AGENT_ID" --arg t "$AGENT_TYPE" --argjson now "$NOW"
            ;;
        SubagentStop)
            [ -n "$AGENT_ID" ] || exit 0
            update_state '
                .[$s] //= {"active_since": null, "total_active": 0, "subagents": {}} |
                if .[$s].subagents[$a].started then
                    .[$s].subagents[$a].total += ($now - .[$s].subagents[$a].started) |
                    .[$s].subagents[$a].started = null
                else . end
            ' --arg s "$SESSION_ID" --arg a "$AGENT_ID" --argjson now "$NOW"
            ;;
    esac
} 200>"$LOCK_FILE"

exit 0
