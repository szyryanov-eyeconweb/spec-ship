#!/usr/bin/env bash
# spec-ship guard — PreToolUse-хук. Физический барьер прав Two-Agent TDD:
# ship-red НЕ может писать вне tests/, ship-green НЕ может писать в tests/.
# Это enforcement (deny на уровне харнесса), а не просьба в промпте сабагента —
# RED не подгонит реализацию, GREEN не перепишет тест, даже если попытается.
#
# Регистрация (PreToolUse, matcher Write|Edit|MultiEdit) — docs/installation.md.
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

# Барьер только для наших сабагентов. Всё прочее (основная сессия, другие
# сабагенты) — обычный flow.
case "$agent_type" in
    ship-red|ship-green|ship-review|ship-decompose) ;;
    *) exit 0 ;;
esac

tool_name=$(jq -r '.tool_name // empty' <<<"$input" 2>/dev/null)
case "$tool_name" in
    Write|Edit|MultiEdit) ;;
    *) exit 0 ;;
esac

file_path=$(jq -r '.tool_input.file_path // empty' <<<"$input" 2>/dev/null)
[ -n "$file_path" ] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
TESTS_DIR="${SHIP_GUARD_TESTS_DIR:-tests/}"

# Привести к пути относительно корня проекта (deny-решение по слою tests/).
rel="${file_path#"$ROOT"/}"

# В каком слое тестов лежит путь? Срабатывает и на абсолютном, и на
# относительном пути: ищем компонент пути, начинающийся с TESTS_DIR.
case "$rel" in
    "$TESTS_DIR"*|*/"$TESTS_DIR"*) in_tests=1 ;;
    *) in_tests=0 ;;
esac

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

if [ "$agent_type" = "ship-red" ] && [ "$in_tests" -eq 0 ]; then
    deny "spec-ship: ship-red пишет ТОЛЬКО в ${TESTS_DIR} — реализацию пишет ship-green. Запись в '$rel' отклонена (барьер Two-Agent TDD)."
fi

if [ "$agent_type" = "ship-green" ] && [ "$in_tests" -eq 1 ]; then
    deny "spec-ship: ship-green НЕ трогает тесты — они контракт RED. Запись в '$rel' отклонена (барьер Two-Agent TDD). Конфликт теста со spec → сообщи оркестратору (TestUpdateTicket), не правь тест."
fi

# ship-review / ship-decompose — пишут ТОЛЬКО артефакты в .ship/pipeline/,
# код не трогают. Любая запись вне .ship/pipeline/ отклоняется.
PIPELINE_DIR="${SHIP_GUARD_PIPELINE_DIR:-.ship/pipeline/}"
case "$rel" in
    "$PIPELINE_DIR"*|*/"$PIPELINE_DIR"*) in_pipeline=1 ;;
    *) in_pipeline=0 ;;
esac
if [ "$agent_type" = "ship-review" ] && [ "$in_pipeline" -eq 0 ]; then
    deny "spec-ship: ship-review пишет ТОЛЬКО ReviewReport в ${PIPELINE_DIR} — код не чинит. Запись в '$rel' отклонена. Дефект → NEEDS_WORK/ESCALATE в отчёте, чинит build."
fi
if [ "$agent_type" = "ship-decompose" ] && [ "$in_pipeline" -eq 0 ]; then
    deny "spec-ship: ship-decompose пишет ТОЛЬКО task-*/tu-* в ${PIPELINE_DIR} — код не реализует, bd не морозит. Запись в '$rel' отклонена."
fi

exit 0