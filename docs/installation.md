# Установка spec-ship в проект

spec-ship — это набор скиллов, команд, сабагентов и хука для Claude Code. Установка — копирование файлов в `.claude/` вашего проекта.

## Требования

- [Claude Code](https://claude.com/claude-code)
- `jq` — для хука уведомлений (опционально, см. [notifications.md](notifications.md))

## Шаг 1. Скопировать файлы

Из корня этого репозитория в корень вашего проекта:

```bash
SPEC_SHIP=/path/to/spec-ship
PROJECT=/path/to/your-project

# скиллы (вместе с README-каноном и протоколом ADR-CONFLICT)
cp -r "$SPEC_SHIP/skills"   "$PROJECT/.claude/skills/spec-ship"

# слэш-команды /spec-ship:*
cp -r "$SPEC_SHIP/commands" "$PROJECT/.claude/commands/spec-ship"

# сабагенты Two-Agent TDD
mkdir -p "$PROJECT/.claude/agents"
cp "$SPEC_SHIP"/agents/*.md "$PROJECT/.claude/agents/"

# хук-барьер изоляции прав (ship-red ≠ src, ship-green ≠ tests)
mkdir -p "$PROJECT/.claude/hooks"
cp "$SPEC_SHIP/hooks/ship-guard.sh" "$PROJECT/.claude/hooks/"
chmod +x "$PROJECT/.claude/hooks/ship-guard.sh"
```

После перезапуска сессии Claude Code команды `/spec-ship:*` появятся в списке.

## Шаг 1.5. Зарегистрировать хук-барьер (важно)

Изоляция прав Two-Agent TDD — физический барьер, а не просьба в промпте: `ship-red` не может писать в `src/`, `ship-green` не может писать в `tests/`. Барьер держит PreToolUse-хук `ship-guard.sh` (см. предыдущий шаг). **Без регистрации хука изоляция деградирует до текстовой инструкции в промпте сабагента** — RED технически сможет подогнать реализацию. Зарегистрировать в `$PROJECT/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/ship-guard.sh"
          }
        ]
      }
    ]
  }
}
```

Хук видит `agent_type` вызывающего сабагента и `file_path`; запись вне разрешённого слоя отклоняется (`permissionDecision: deny`). Основной сессии и прочим агентам не мешает. Требует `jq`; без `jq` хук пропускает вызов (барьер деградирует — установите `jq`). Барьер грубый по слою (`tests/` vs остальное), точную границу `files_to_change` проверяет self-review build.

## Шаг 2. Создать CONTEXT.md (рекомендуется)

Скиллы читают `CONTEXT.md` в корне проекта — доменный глоссарий: термины, акторы, имена состояний. Имена в спеках и тестах будут сверяться с ним, чтобы вся команда (и все агенты) называли вещи одинаково.

Минимальный вариант:

```markdown
# CONTEXT.md — доменный глоссарий

## Термины
- **Партнёр** — ...
- **Транзакция** — ...

## Акторы
- **BA** — ставит требования, апрувит спеки
- **Dev** — шейпит LOGIC, пишет CRITICAL, принимает эскалации
```

## Шаг 3. Уведомления в Telegram (опционально)

Чтобы получать сообщение, когда пайплайну нужно ваше участие (апрув, эскалация, тикет):

```bash
mkdir -p "$PROJECT/.claude/hooks"
cp "$SPEC_SHIP/hooks/ship-notify.sh" "$PROJECT/.claude/hooks/"
chmod +x "$PROJECT/.claude/hooks/ship-notify.sh"
```

Зарегистрировать Stop-хук в `$PROJECT/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/ship-notify.sh"
          }
        ]
      }
    ]
  }
}
```

Настройка транспорта — на странице [notifications.md](notifications.md). Без конфига хук молчит и ничему не мешает.

## Шаг 4. Первая фича

```
/spec-ship:shape-doc Краткое описание фичи
```

Если фича меняет существующее поведение — начните с разведки:

```
/spec-ship:survey ClassName#method — что меняется
```

## Что появится в проекте по ходу работы

Каталог `.ship/` создаётся пайплайном автоматически:

```
.ship/
├── pipeline/   артефакты фич (JSON) — коммитьте вместе с кодом
└── docs/       канон: adr/ и workflows/ — накапливается после мёржей
```

Рекомендация: добавьте `.ship/notify.yaml` в `.gitignore` (личная настройка уведомлений, содержит chat_id):

```gitignore
/.ship/notify.yaml
```

## Обновление

Повторите шаг 1 поверх. Артефакты в `.ship/` совместимы между версиями: новые поля схем опциональны, старые артефакты читаются как есть.
