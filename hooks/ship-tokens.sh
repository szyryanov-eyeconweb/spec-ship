#!/usr/bin/env bash
# spec-ship tokens — измеряет расход токенов агента и его сабагентов.
#
# Источник: hook payload несёт transcript_path — JSONL-транскрипт (у сессии
# и у каждого сабагента свой отдельный файл). Каждое assistant-сообщение
# несёт message.usage {input_tokens, output_tokens,
# cache_creation_input_tokens, cache_read_input_tokens}.
#
# Stop/SubagentStop → прочитать transcript_path целиком, просуммировать usage
# по всем assistant-сообщениям, ЗАПИСАТЬ (не прибавить) как текущий итог.
# Транскрипт монотонно растёт и уже полностью на диске к моменту события —
# пересчёт с нуля на каждый Stop не даёт двойного счёта между последовательными
# Stop одной сессии (в отличие от накопления по дельте).
#
# В отличие от ship-timer: токены сабагента и родителя НЕ пересекаются (разные
# файлы, разные API-запросы) — sum(main + все subagents) корректно даёт "всего
# потрачено за сессию", задвоения нет.
#
# Состояние — per-session, ключ session_id. Всегда exit 0: хук не должен
# ломать работу агента.
#
# Параллельные сабагенты триггерят SubagentStop одновременно → без блокировки
# два jq-процесса читают state.json на старте друг друга и пишут поверх один
# другого (classic read-modify-write race), последний mv побеждает, первый
# потерян. Read-modify-write под flock -x на отдельный lock-файл — сериализует
# конкурентные вызовы хука, ни один результат не теряется.
#
# Переменные для тестов:
#   SHIP_TOKENS_STATE — путь к state-файлу (по умолчанию .claude/state/ship-tokens.json)

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
STATE_FILE="${SHIP_TOKENS_STATE:-$ROOT/.claude/state/ship-tokens.json}"
LOCK_FILE="$STATE_FILE.lock"

command -v jq >/dev/null 2>&1 || exit 0
command -v flock >/dev/null 2>&1 || exit 0

INPUT="$(cat)"
SESSION_ID="$(jq -r '.session_id // "default"' <<<"$INPUT" 2>/dev/null)"
HOOK_EVENT="$(jq -r '.hook_event_name // empty' <<<"$INPUT" 2>/dev/null)"
AGENT_ID="$(jq -r '.agent_id // empty' <<<"$INPUT" 2>/dev/null)"
AGENT_TYPE="$(jq -r '.agent_type // "unknown" | if . == "" then "unknown" else . end' <<<"$INPUT" 2>/dev/null)"
TRANSCRIPT="$(jq -r '.transcript_path // empty' <<<"$INPUT" 2>/dev/null)"

[ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ] || exit 0

mkdir -p "$(dirname "$STATE_FILE")"

# Сумма usage по всем assistant-сообщениям транскрипта — читается вне lock'а,
# это read-only на чужом файле (транскрипт), под гонку с параллельными
# сабагентами не попадает: у каждого свой transcript_path.
TOKENS_JSON="$(jq -s '[.[] | select(.message.usage) | .message.usage] |
    {
        "input": (map(.input_tokens // 0) | add // 0),
        "output": (map(.output_tokens // 0) | add // 0),
        "cache_read": (map(.cache_read_input_tokens // 0) | add // 0),
        "cache_creation": (map(.cache_creation_input_tokens // 0) | add // 0)
    }' "$TRANSCRIPT" 2>/dev/null)"
[ -n "$TOKENS_JSON" ] || exit 0

{
    flock -x 200

    [ -f "$STATE_FILE" ] || echo '{}' > "$STATE_FILE"
    tmp="$STATE_FILE.tmp.$$"

    case "$HOOK_EVENT" in
        Stop)
            jq --arg s "$SESSION_ID" --argjson t "$TOKENS_JSON" '
                .[$s] //= {"tokens": {}, "subagents": {}} |
                .[$s].tokens = $t
            ' "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"
            ;;
        SubagentStop)
            [ -n "$AGENT_ID" ] || exit 0
            jq --arg s "$SESSION_ID" --arg a "$AGENT_ID" --arg ty "$AGENT_TYPE" --argjson t "$TOKENS_JSON" '
                .[$s] //= {"tokens": {}, "subagents": {}} |
                .[$s].subagents[$a] = {"agent_type": $ty, "tokens": $t}
            ' "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"
            ;;
    esac
} 200>"$LOCK_FILE"

exit 0
