# Уведомления: Telegram, когда нужно ваше участие

Пайплайн часто работает автономно: build гоняет агентов, review проверяет. Но в некоторых точках он останавливается и ждёт человека. Чтобы не проверять терминал вручную, есть хук `hooks/ship-notify.sh`: как только сессия останавливается с «висящим» сигналом — вам прилетает сообщение в Telegram.

## Как это устроено

Доставка **детерминированная**: хук исполняет Claude Code (событие Stop), а не сам агент — «агент забыл уведомить» исключено. Скиллы про уведомления вообще не знают: хук читает статусы прямо из сохранённых артефактов `.ship/pipeline/`.

```
Stop-хук
  → скан .ship/pipeline/**: есть ли сигналы «нужен человек»
  → дедупликация: одно уведомление на сигнал, пока тот не снят
  → отправка в Telegram
```

## Какие события отслеживаются

| Событие | Сигнал в артефактах | Сообщение |
|---|---|---|
| `bd_approval` | BusinessDoc в статусе draft | спека ждёт апрува |
| `blocking_questions` | blocking-вопросы без ответа | вопросы ждут решения |
| `shape_proposal` | план LOGIC-задачи в статусе proposal | ждёт шейп-сессии |
| `test_update_pending` | TestUpdateTicket pending | конфликт теста ждёт maintainer |
| `adr_conflict_pending` | тикет ADR-конфликта pending | ждёт вердикта: ADR верен или устарел |
| `build_escalation` | эскалация в BuildReport | агенты не справились, нужен Dev |
| `review_escalate` | вердикт ESCALATE | ревью подняло проблему |

Не покрыто (и не нужно): интерактивные фазы, где вы и так в сессии — апрув разбивки decompose, вопросы интервью shape-doc в моменте.

## Настройка

### 1. Бот и токен

Создайте бота у [@BotFather](https://t.me/BotFather) (`/newbot`) и получите токен. Токен — секрет, в репозиторий не попадает. Два способа передать его хуку:

```bash
# способ 1: файл (надёжнее — работает при любом способе запуска Claude Code)
mkdir -p ~/.config/ship-notify
echo '123456789:AAEhB0...' > ~/.config/ship-notify/telegram-token
chmod 600 ~/.config/ship-notify/telegram-token

# способ 2: переменная окружения
export SHIP_TELEGRAM_BOT_TOKEN='123456789:AAEhB0...'
```

В файле — сам токен одной строкой, без имени переменной и кавычек.

### 2. Ваш chat_id

Это **ваш** Telegram user id, не id бота. Откройте своего бота и нажмите **Start** (боты не могут писать первыми!), затем узнайте свой id — например, у [@userinfobot](https://t.me/userinfobot).

Частые грабли:
- «chat not found» → вы не нажали Start у своего бота
- «bot can't send messages to the bot» → вы указали id бота вместо своего
- для канала/группы id имеет вид `-100XXXXXXXXXX`, и бот должен быть добавлен туда с правом писать

### 3. Конфиг

```bash
cp .ship/notify.yaml.dist .ship/notify.yaml   # gitignored
```

```yaml
enabled: true
transport: telegram
telegram_chat_id: "417039654"
telegram_token_env: SHIP_TELEGRAM_BOT_TOKEN
telegram_token_file: ~/.config/ship-notify/telegram-token
# пусто = все события; иначе список через запятую
events: blocking_questions, bd_approval, shape_proposal, test_update_pending, adr_conflict_pending, build_escalation, review_escalate
```

Без этого файла (или с `enabled: false`) хук молчит — безопасно для коллег, у которых уведомления не настроены.

### 4. Проверка

```bash
# фейковый сигнал
mkdir -p .ship/pipeline/bd-9999-test
echo '{"id":"bd-9999","status":"draft","open_questions":[]}' > .ship/pipeline/bd-9999-test/bd-9999.json

.claude/hooks/ship-notify.sh        # должно прийти сообщение

rm -rf .ship/pipeline/bd-9999-test
.claude/hooks/ship-notify.sh        # снимет сигнал из state
```

Режим без отправки: `SHIP_NOTIFY_DRY_RUN=1 .claude/hooks/ship-notify.sh` — напечатает сообщение вместо отправки.

## Поведение

- **Одно уведомление на сигнал.** Состояние «уже отправлено» хранится в `.claude/state/ship-notify-sent.json`; пока сигнал висит, повторные остановки сессии не спамят. Сигнал снят → забыт; если появится снова — придёт новое уведомление.
- **Провал доставки = ретрай.** Если Telegram недоступен или ответил ошибкой, сигнал не помечается отправленным — попытка повторится на следующей остановке.
- **Хук никогда не ломает сессию** — при любой проблеме тихо выходит с кодом 0.
