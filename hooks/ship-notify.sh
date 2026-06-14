#!/usr/bin/env bash
# spec-ship notify — Stop-хук. Сканирует .ship/pipeline/ на статусы, требующие
# участия человека, и шлёт уведомление (Telegram). Дедупликация через
# state-файл: одно уведомление на сигнал, пока сигнал не снят.
#
# Без конфига (.ship/notify.yaml) или с enabled != true — молчит.
# Всегда exit 0: хук не должен ломать сессию.
#
# Документация: docs/notifications.md репозитория spec-ship;
# канон протоколов: .claude/skills/spec-ship/README.md, секция «Уведомления».
#
# Переменные для тестов:
#   SHIP_NOTIFY_CONFIG  — путь к конфигу (по умолчанию .ship/notify.yaml)
#   SHIP_NOTIFY_STATE   — путь к state-файлу
#   SHIP_NOTIFY_DRY_RUN — 1 = печатать вместо отправки

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
CFG="${SHIP_NOTIFY_CONFIG:-$ROOT/.ship/notify.yaml}"
PIPE="$ROOT/.ship/pipeline"
STATE_FILE="${SHIP_NOTIFY_STATE:-$ROOT/.claude/state/ship-notify-sent.json}"

[ -f "$CFG" ] || exit 0
[ -d "$PIPE" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

cfg() {
    grep -E "^$1:" "$CFG" 2>/dev/null | head -1 \
        | sed 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*$//' | tr -d '"'
}

[ "$(cfg enabled)" = "true" ] || exit 0

EVENTS_RAW="$(cfg events | tr -d ' ')"
want() {
    [ -z "$EVENTS_RAW" ] && return 0    # пустой список = все события
    case ",$EVENTS_RAW," in *",$1,"*) return 0 ;; *) return 1 ;; esac
}

# --- Скан сигналов ----------------------------------------------------------
# Каждый сигнал: key (file:type) + человекочитаемое сообщение.

KEYS=()
MSGS=()
add() { KEYS+=("$1"); MSGS+=("$2"); }

for f in "$PIPE"/*/bd-*.json; do
    [ -f "$f" ] || continue
    slug=$(basename "$(dirname "$f")")
    status=$(jq -r '.status // empty' "$f" 2>/dev/null)
    blocking=$(jq '[.open_questions[]? | select(.severity == "blocking" and .resolution == null)] | length' "$f" 2>/dev/null)
    if [ "${blocking:-0}" -gt 0 ] && want blocking_questions; then
        add "$f:blocking" "[?] $slug: blocking-вопросов без resolution: $blocking"
    elif [ "$status" = "draft" ] && want bd_approval; then
        add "$f:approval" "[bd] $slug: BusinessDoc ждёт апрува"
    fi
done

for f in "$PIPE"/*/task-*.json; do
    [ -f "$f" ] || continue
    if [ "$(jq -r '.shape.status // empty' "$f" 2>/dev/null)" = "proposal" ] && want shape_proposal; then
        add "$f:shape" "[shape] $(jq -r '.id' "$f"): shape proposal ждёт шейп-сессии Dev"
    fi
done

for f in "$PIPE"/*/tu-*.json; do
    [ -f "$f" ] || continue
    if [ "$(jq -r '.resolution.status // empty' "$f" 2>/dev/null)" = "pending" ] && want test_update_pending; then
        add "$f:tu" "[test] $(jq -r '.id' "$f"): TestUpdateTicket ждёт решения maintainer"
    fi
done

for f in "$PIPE"/*/adr-change-*.json; do
    [ -f "$f" ] || continue
    if [ "$(jq -r '.human_verdict.status // empty' "$f" 2>/dev/null)" = "pending" ] && want adr_conflict_pending; then
        add "$f:adr" "[adr] $(jq -r '.id' "$f"): ADR-конфликт ждёт вердикта человека"
    fi
done

for f in "$PIPE"/*/build-*.json; do
    [ -f "$f" ] || continue
    reason=$(jq -r '.escalation.reason // empty' "$f" 2>/dev/null)
    if [ -n "$reason" ] && want build_escalation; then
        add "$f:esc" "[build] $(jq -r '.id' "$f"): эскалация ($reason)"
    fi
done

for f in "$PIPE"/*/review-*.json; do
    [ -f "$f" ] || continue
    if [ "$(jq -r '.verdict // empty' "$f" 2>/dev/null)" = "ESCALATE" ] && want review_escalate; then
        add "$f:rev" "[review] $(jq -r '.id' "$f"): вердикт ESCALATE, нужен Dev"
    fi
done

# --- Дедупликация ------------------------------------------------------------

mkdir -p "$(dirname "$STATE_FILE")"
[ -f "$STATE_FILE" ] || echo '{}' > "$STATE_FILE"

NEW_MSGS=""
CURRENT_KEYS_JSON='{}'
for i in "${!KEYS[@]}"; do
    k="${KEYS[$i]}"
    CURRENT_KEYS_JSON=$(jq --arg k "$k" '. + {($k): true}' <<<"$CURRENT_KEYS_JSON")
    if ! jq -e --arg k "$k" 'has($k)' "$STATE_FILE" >/dev/null 2>&1; then
        NEW_MSGS="${NEW_MSGS}${MSGS[$i]}"$'\n'
    fi
done

prune_state() {
    # Оставить в state только сигналы, всё ещё активные (снятые — забыть).
    jq --argjson cur "$CURRENT_KEYS_JSON" 'with_entries(select(.key | in($cur)))' \
        "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

if [ -z "$NEW_MSGS" ]; then
    prune_state
    exit 0
fi

# --- Отправка ----------------------------------------------------------------

TEXT="spec-ship: требуется участие
${NEW_MSGS}"

send_ok=1
if [ "${SHIP_NOTIFY_DRY_RUN:-0}" = "1" ]; then
    printf 'DRY-RUN notify:\n%s' "$TEXT"
    send_ok=0
elif [ "$(cfg transport)" = "telegram" ]; then
    token_env="$(cfg telegram_token_env)"
    TOKEN="${!token_env:-}"
    if [ -z "$TOKEN" ]; then
        token_file="$(cfg telegram_token_file)"
        token_file="${token_file/#\~/$HOME}"
        [ -f "$token_file" ] && TOKEN=$(<"$token_file")
    fi
    CHAT="$(cfg telegram_chat_id)"
    if [ -n "$TOKEN" ] && [ -n "$CHAT" ]; then
        curl -sS --fail -m 10 -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
            -d "chat_id=${CHAT}" --data-urlencode "text=${TEXT}" >/dev/null 2>&1
        send_ok=$?
    fi
fi

if [ "$send_ok" -eq 0 ]; then
    # Успех: все текущие сигналы отмечены отправленными.
    echo "$CURRENT_KEYS_JSON" > "$STATE_FILE"
else
    # Провал отправки: state не помечаем — повтор на следующем Stop.
    prune_state
fi

exit 0