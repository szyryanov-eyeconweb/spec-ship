# Метрики: время и токены на прогон

Два независимых хука измеряют, во что обходится прогон пайплайна: `hooks/ship-timer.sh` — активное время (без простоя в ожидании вас), `hooks/ship-tokens.sh` — расход токенов. Оба пишут per-session state на диск, ничего никуда не отправляют.

Хуки не завязаны на spec-ship — не читают `.ship/pipeline/`, не знают про артефакты пайплайна. Годятся в любом проекте на Claude Code, где нужно мерить время/токены сессии и её сабагентов, не только в паре со spec-ship.

## Как это устроено

```
UserPromptSubmit → ship-timer:  active_since = now
Stop             → ship-timer:  total_active += now - active_since
                    ship-tokens: прочитать transcript_path целиком,
                                 сумма usage → перезаписать итог сессии

SubagentStart    → ship-timer:  subagents[agent_id].started = now
SubagentStop     → ship-timer:  subagents[agent_id].total += now - started
                    ship-tokens: прочитать transcript_path сабагента,
                                 сумма usage → subagents[agent_id]
```

Источник токенов — `transcript_path` из hook payload: у сессии и у каждого сабагента свой JSONL-файл, каждое assistant-сообщение несёт `message.usage`. Пересчёт с нуля на каждый `Stop`, не накопление по дельте — так число всегда точное, `/compact` не портит подсчёт (старые usage-записи остаются в файле, суммируются как есть).

## Что можно и нельзя складывать

**Время**: `total_active` главной сессии уже покрывает время сабагентов внутри неё — пока сабагент работает, сессия сидит внутри вызова `Task`, её таймер не стоит. `total_active + sum(subagents.*.total)` — задвоение, не общее время. Складывать можно только сабагентов между собой (параллельные — CPU-время, не wall-clock).

**Токены**: наоборот — main и сабагент это разные API-запросы, разные файлы, не пересекаются. `main.tokens + sum(subagents.*.tokens)` — корректный общий расход за прогон.

## Известные ограничения

- Считает usage по **всей** сессии с начала, не по последнему ходу — если сессия живёт долго, число на каждом `Stop` растёт кумулятивно, это не «стоимость последнего ответа».
- Параллельные `SubagentStop` — под `flock -x` на `<state>.json.lock`, гонка исключена; при зависшем держателе лока остальные ждут без таймаута.
- `agent_type` иногда приходит пустой строкой (не `null`) — хук нормализует в `"unknown"`, но что именно вызвало пустой agent_type, не выяснено.
- Требует `jq` и `flock`; без них хук молча выходит (`exit 0`), метрика просто не пишется.

## Установка

Три файла — `ship-timer.sh`, `ship-tokens.sh`, `ship-report.py` (из `hooks/` этого репозитория, или откуда угодно ещё) — положить в `.claude/hooks/` вашего проекта:

```bash
PROJECT=/path/to/your-project

mkdir -p "$PROJECT/.claude/hooks"
cp ship-timer.sh ship-tokens.sh ship-report.py "$PROJECT/.claude/hooks/"
chmod +x "$PROJECT/.claude/hooks/ship-timer.sh" "$PROJECT/.claude/hooks/ship-tokens.sh" "$PROJECT/.claude/hooks/ship-report.py"
```

Путь `.claude/hooks/` — не обязательный, а просто конвенция; хуки не ссылаются друг на друга по пути, только по имени в `settings.json` ниже. Можно положить в любое место, тогда поправьте `command` в JSON соответственно.

Зарегистрировать в `$PROJECT/.claude/settings.json` (можно слить с уже существующими хуками этого же проекта, если такие есть — на одно событие допустимо несколько хуков в массиве):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/ship-timer.sh" }] }
    ],
    "SubagentStart": [
      { "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/ship-timer.sh" }] }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/ship-timer.sh" },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/ship-tokens.sh" }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/ship-timer.sh" },
          { "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/ship-tokens.sh" }
        ]
      }
    ]
  }
}
```

Регистрация применяется только на старте сессии — после правки `settings.json` перезапустите `claude`.

## Куда пишут

```
.claude/state/ship-timer.json
.claude/state/ship-tokens.json
```

Добавьте в `.gitignore` — это локальное состояние сессий, не артефакт проекта:

```gitignore
/.claude/state/
```

## Отчёт по прогону

```bash
.claude/hooks/ship-report.py                  # последняя сессия, таблица
.claude/hooks/ship-report.py <session_id>     # конкретная сессия
.claude/hooks/ship-report.py --json           # сырой JSON вместо таблицы
```

Джойнит оба state-файла по `session_id`/`agent_id`, ничего заново не парсит. Пример вывода:

```
session c48fa94f-002c-45fb-9f4d-ca5ae4b7aadb
  wall-clock: 1m05s
  main tokens: in=32 out=2015 cache_read=756393 cache_creation=63699
  subagents:
    Explore                   0m13s   in=0 out=0 cache_read=0 cache_creation=0
    general-purpose           0m06s   in=0 out=0 cache_read=0 cache_creation=0
    unknown                   0m00s   in=26 out=1598 cache_read=654568 cache_creation=31724
  TOTAL tokens (main+subagents): in=58 out=3613 cache_read=1410961 cache_creation=95423
```

`unknown` с `0m00s` в этом примере — сабагент, зафиксированный `ship-tokens` (у него usage есть), но не `ship-timer` (нет пары по `agent_id` — этот конкретный вызов не прошёл обычным `SubagentStart`/`SubagentStop`, разбор в разделе «Известные ограничения»). Джойн в `ship-report.py` берёт объединение ключей из обоих файлов, а не пересечение — такой сабагент не теряется молча, просто одна из двух метрик у него нулевая.

## Ротация

Оба state-файла растут: одна запись на `session_id` навсегда. Ротация/prune не реализованы — при большом числе сессий почистите руками:

```bash
jq 'to_entries | sort_by(.key) | reverse | .[0:50] | from_entries' .claude/state/ship-timer.json > /tmp/t.json && mv /tmp/t.json .claude/state/ship-timer.json
```

(оставляет 50 последних по алфавиту ключей session_id — грубо, но рабочий вариант, если размер файла начал мешать).
