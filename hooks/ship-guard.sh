#!/usr/bin/env bash
# spec-ship guard — PreToolUse-хук. Физический барьер прав Two-Agent TDD:
# ship-red НЕ может писать вне tests/, ship-green НЕ может писать в tests/.
# Это enforcement (deny на уровне харнесса), а не просьба в промпте сабагента —
# RED не подгонит реализацию, GREEN не перепишет тест, даже если попытается.
#
# Регистрация (PreToolUse, matcher Write|Edit|MultiEdit|Bash) — docs/installation.md.
# Барьер грубый по слою (tests/ vs src/), не по TaskSpec.files_to_change:
# закрывает главный инвариант изоляции, точную границу даёт self-review build.
#
# Решение блокировки — через permissionDecision: "deny" (харнесс отклоняет вызов).
# При любой неоднозначности (нет jq, не распарсилось, не сабагент) — НЕ мешать:
# выход без вердикта = обычный permission-flow. Хук не ломает легитимную работу.
#
# Переменные для тестов:
#   SHIP_GUARD_TESTS_DIR  — префикс тестов (по умолчанию tests/)

input=$(cat)

command -v jq >/dev/null 2>&1 || exit 0

agent_type=$(jq -r '.agent_type // "main"' <<<"$input" 2>/dev/null)
# Плагин-агенты приходят как "spec-ship:ship-red" — отбросить префикс плагина.
agent_type="${agent_type##*:}"

# Барьер только для наших сабагентов. Всё прочее (основная сессия, другие
# сабагенты) — обычный flow.
case "$agent_type" in
    ship-red|ship-green|ship-review|ship-decompose) ;;
    *) exit 0 ;;
esac

# Цели записи из Bash-команды, по одной на строку. Эвристика, не парсер shell:
# перенаправления (> >>, цель — только файл после них) и команды записи
# (cp/mv/rm/tee/touch/…, sed -i, perl -i, git checkout|restore|rm|mv) — все
# аргументы-пути сегмента. /tmp и /dev — не код проекта, пропускаются.
# ponytail: эвристика, python -c "open(…)"/eval/переменные-пути не ловит;
# упирается в это — запрещать Bash сабагентам целиком или песочница ФС.
BASH_WRITE_TARGETS='
import re, shlex, sys
WRITE_CMDS = {"cp", "mv", "rm", "tee", "touch", "truncate", "install", "ln",
              "dd", "mkdir", "rmdir", "unlink"}
GIT_WRITE = {"checkout", "restore", "rm", "mv", "apply"}
out = []
for seg in re.split(r"\|\||&&|;|\||\n", sys.argv[1]):
    for m in re.finditer(r"\d*>>?\|?(?!&)\s*([^\s;|&<>()]+)", seg):
        out.append(m.group(1))
    try:
        words = shlex.split(seg)
    except ValueError:
        words = seg.split()
    while words and (re.match(r"^\w+=", words[0]) or words[0] in ("sudo", "command", "env")):
        words = words[1:]
    if not words:
        continue
    cmd, args = words[0].rsplit("/", 1)[-1], words[1:]
    writes = (cmd in WRITE_CMDS
              or (cmd == "sed" and any(a.startswith("-i") or a == "--in-place" for a in args))
              or (cmd == "perl" and any(re.match(r"^-\w*i", a) for a in args))
              or (cmd == "git" and args[:1] and args[0] in GIT_WRITE))
    if writes:
        out += [a.split("=", 1)[-1] for a in args if not a.startswith("-")]
for p in out:
    p = p.strip("\"\x27")
    if p and not p.startswith(("/tmp/", "/dev/")):
        print(p)
'

tool_name=$(jq -r '.tool_name // empty' <<<"$input" 2>/dev/null)
case "$tool_name" in
    Write|Edit|MultiEdit)
        file_path=$(jq -r '.tool_input.file_path // empty' <<<"$input" 2>/dev/null)
        [ -n "$file_path" ] || exit 0
        paths="$file_path" ;;
    Bash)
        # Запись через shell (sed -i, cat >, cp, git checkout -- …) обходила барьер:
        # matcher был только Write|Edit. Достаём цели записи из команды.
        command -v python3 >/dev/null 2>&1 || exit 0
        cmd=$(jq -r '.tool_input.command // empty' <<<"$input" 2>/dev/null)
        [ -n "$cmd" ] || exit 0
        paths=$(python3 -I -c "$BASH_WRITE_TARGETS" "$cmd" 2>/dev/null) || exit 0
        [ -n "$paths" ] || exit 0 ;;
    *) exit 0 ;;
esac

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
TESTS_DIR="${SHIP_GUARD_TESTS_DIR:-tests/}"
PIPELINE_DIR="${SHIP_GUARD_PIPELINE_DIR:-.ship/pipeline/}"

deny() {
    jq -n --arg reason "$1" '{
        hookSpecificOutput: {
            hookEventName: "PreToolUse",
            permissionDecision: "deny",
            permissionDecisionReason: $reason
        }
    }'
    exit 0
}

check_path() {
    # Привести к пути относительно корня проекта (deny-решение по слою tests/).
    local rel="${1#"$ROOT"/}"
    rel="${rel#./}"
    local in_tests in_pipeline
    # Срабатывает и на абсолютном, и на относительном пути: ищем компонент
    # пути, начинающийся с TESTS_DIR / PIPELINE_DIR.
    case "$rel" in
        "$TESTS_DIR"*|*/"$TESTS_DIR"*) in_tests=1 ;;
        *) in_tests=0 ;;
    esac
    case "$rel" in
        "$PIPELINE_DIR"*|*/"$PIPELINE_DIR"*) in_pipeline=1 ;;
        *) in_pipeline=0 ;;
    esac

    if [ "$agent_type" = "ship-red" ] && [ "$in_tests" -eq 0 ]; then
        deny "spec-ship: ship-red пишет ТОЛЬКО в ${TESTS_DIR} — реализацию пишет ship-green. Запись в '$rel' отклонена (барьер Two-Agent TDD)."
    fi

    if [ "$agent_type" = "ship-green" ] && [ "$in_tests" -eq 1 ]; then
        deny "spec-ship: ship-green НЕ трогает тесты — они контракт RED. Запись в '$rel' отклонена (барьер Two-Agent TDD). Конфликт теста со spec → сообщи оркестратору (TestUpdateTicket), не правь тест."
    fi

    # ship-review / ship-decompose — пишут ТОЛЬКО артефакты в .ship/pipeline/,
    # код не трогают. Любая запись вне .ship/pipeline/ отклоняется.
    if [ "$agent_type" = "ship-review" ] && [ "$in_pipeline" -eq 0 ]; then
        deny "spec-ship: ship-review пишет ТОЛЬКО ReviewReport в ${PIPELINE_DIR} — код не чинит. Запись в '$rel' отклонена. Дефект → NEEDS_WORK/ESCALATE в отчёте, чинит build."
    fi
    if [ "$agent_type" = "ship-decompose" ] && [ "$in_pipeline" -eq 0 ]; then
        deny "spec-ship: ship-decompose пишет ТОЛЬКО task-*/tu-* в ${PIPELINE_DIR} — код не реализует, bd не морозит. Запись в '$rel' отклонена."
    fi
}

while IFS= read -r path; do
    [ -n "$path" ] && check_path "$path"
done <<<"$paths"

exit 0
