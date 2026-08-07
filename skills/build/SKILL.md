---
name: build
description: Оркеструет билд TaskSpec по trust_zone (Two-Agent TDD для ROUTINE, шейп-в-сессии для LOGIC, консультация для CRITICAL), производит BuildReport + ADREntry JSON (Phase 2). Использовать когда есть TaskSpec, или когда пользователь говорит "build task", "implement task", "phase 2", "run TDD", "собери задачу".
---

# Ship Build

Оркеструет билд `TaskSpec` по `trust_zone`, производит `BuildReport` + опционально `ADREntry` в `.ship/pipeline/{slug}/`. Код не пишет — делегирует сабагентам (ROUTINE/LOGIC) или консультирует (CRITICAL).

## Pre-flight

- Загрузить `TaskSpec` из `.ship/pipeline/{slug}/task-*.json` (спросить id если неоднозначно; slug — по правилу из [CANON.md](../CANON.md)).
- Проверить `shape`: LOGIC без `shape` или `status: "proposal"` → шейп-сессия обязательна до сабагентов. `status: "approved"` → шейп готов, сессия сокращается до подтверждения актуальности.
- Загрузить `Survey` из `.ship/pipeline/{slug}/survey-*.json`, если есть: `observed_workflows` + `validation_boundaries` — стартовый контекст шейп-сессии LOGIC (не пере-трассировать код), `connected_groups.risk_if_skipped` — чеклист рисков для self-review.
- Прочитать `CONTEXT.md` и `spec.files_read_only`.
- Резолвить `adr_refs` через `.ship/docs/adr/INDEX.md` — тела только этих ADR (отфильтрованы на decompose). `adr_ref` со `Status: Expired` → ADR-CONFLICT (ссылка на устаревший ADR).

## Маршрутизация по trust_zone

Скилл — ОРКЕСТРАТОР: читает `trust_zone`, выбирает трек. Рассуждающая модель (сессия) — где мышление; исполнительная (сабагенты) — где исполнение по спеке. Модели заданы в `model:` сабагентов и настройке сессии — НЕ хардкодить имена здесь.

| trust_zone | Кто строит | Где рассуждение | Механизм |
|---|---|---|---|
| `ROUTINE` | автономно | — | сабагенты `ship-red` + `ship-green` (исполнительная модель) |
| `LOGIC` | Dev шейпит → агент реализует | шейп в сессии | сессия (рассуждение) + сабагенты (код) |
| `CRITICAL` | Dev only | вся задача в сессии | сессия (консультант), БЕЗ сабагентов, ноль автозаписи |

---

## Трек ROUTINE — Two-Agent TDD через сабагентов

Оркестратор код не пишет. Делегирует двум сабагентам с изолированными правами. Контракт между ними — тестовый набор.

### 1. RED — сабагент `ship-red` (права только `tests/`)

`test_scenarios: []` (`test_seam: null`) → у слайса нет своих тестов, он покрыт функциональным набором фичи на слайсе-носителе. RED/GREEN этого слайса не через тесты: пропустить RED, GREEN реализует напрямую по `spec.interface`; в self-review отметить «покрытие — функц. набор слайса-носителя <task-id>». Дальше только для слайсов со сценариями.

Вызвать `ship-red` через Agent tool. Передать: TaskSpec (`spec.interface`, `test_scenarios[]`, `data[]`, `files_*`) + путь результата. Запись `data[]` с `value_ref` передаётся дескриптором — RED читает файл по `path` сам (файл в `files_read_only`), корпус в промпт не инлайнится.

`ship-red` пишет по одному падающему тесту на сценарий, подтверждает ALL RED, возвращает `agent_red`. Физически не пишет в `src/` → тесты честные.

Обработка исхода RED:

| Исход от ship-red | Действие оркестратора |
|---|---|
| `status: done` | перейти к GREEN |
| `status: blocked` | RED не смог написать честный тест (интерфейс неоднозначен / нетестируемо / нет seam). Переклассифицировать в LOGIC: скелет `shape` (`status: "proposal"`, `blocker` RED → `open_for_developer`) → дошейп интерфейса с Dev. STOP, GREEN не вызывать. |

### 2. GREEN — сабагент `ship-green` (права только `src/`)

После подтверждения RED вызвать `ship-green`. Передать: TaskSpec, тела ADR (резолвлены через INDEX), список RED тест-классов.

`ship-green` итерирует (N итераций, лимит в ship-green) пока тесты зелёные. Тесты не трогает. Возвращает `agent_green`.

### Обработка исходов GREEN (оркестратор)

| Исход от ship-green | Действие оркестратора |
|---|---|
| `status: done` | собрать BuildReport, перейти к ADR Writer |
| `status: escalated` (N) | переклассифицировать в LOGIC: скелет `shape` (`status: "proposal"`, причина провала итераций → `open_for_developer`) → трек LOGIC (рассуждение в сессии) |
| `status: conflict` | создать `TestUpdateTicket` → `.ship/pipeline/{slug}/tu-*.json`. STOP. |
| сигнал ADR-конфликта | запустить [ADR-CONFLICT flow](../ADR-CONFLICT.md) |

### 3. Refactor

После GREEN — опциональный рефактор через `ship-green` (дедуп, deep modules), прогон после каждого шага, никогда на RED.

---

## Трек LOGIC — шейп в сессии + реализация сабагентами

1. **Шейп (сессия).** Dev + оркестратор шейпят решение ~15 мин: подход, ключевые модули, интерфейсы, риски. Старт — `shape` из TaskSpec (`status: "proposal"` от decompose, `open_for_developer` = повестка сессии).
2. **Зафиксировать шейп.** Результат записать в `shape` TaskSpec: `approach`, `intermediate_structures`, `ordering_rules`; `open_for_developer` опустошить или оставить осознанно developer-owned пункты. После апрува Dev → `status: "approved"`, `approved_by`, `approved_at`. Шейп — в `.ship/pipeline/{slug}/task-*.json`, не в памяти сессии.
3. **RED.** Вызвать `ship-red` — тесты по сценариям.
4. **GREEN.** Вызвать `ship-green` с TaskSpec где `shape.status: "approved"`. Реализует по плану из артефакта, не по пересказу.
5. **Эскалация из ROUTINE** приходит сюда — продолжить рассуждение в сессии (скелет `shape` уже создан оркестратором, см. трек ROUTINE).

Сессия делает дорогое (решение), сабагент — дешёвое (код). GREEN для LOGIC не вызывается, пока `shape.status != "approved"`.

---

## Трек CRITICAL — только консультация

- Весь код пишет Dev сам, без сабагентов `ship-red`/`ship-green`.
- Оркестратор (сессия) = консультант: анализ, риски, предложения. Ноль записи в файлы.
- BuildReport фиксирует консультацию (`tdd` блоки = null, отметка "CRITICAL: Dev-implemented").

---

## Под-трек FAN-OUT (когда `fan_out.enabled: true`)

При `fan_out.enabled: true` слои реализуются ПАРАЛЛЕЛЬНО (Phase A контракт → A.5 RED все тесты → B по `ship-green` на слой в worktree → C интеграция). Ортогонален trust_zone, при `CRITICAL` не ставится. Оркестратор фиксирует контракт, делегирует слои.

**Канон механики (фазы, инварианты, worktree-детектор, риски) — [FAN-OUT.md](../FAN-OUT.md).** `fan_out: null` — под-трек пропустить, FAN-OUT.md не грузить.

---

## ADR Writer

После реализации проверить, было ли решение:
1. Трудно обратимым
2. Удивительным без контекста
3. Результатом реального trade-off

Если да → произвести `ADREntry` в `.ship/pipeline/{slug}/adr-entry-<task-id>-<letter>.json`.

`ADREntry` — КАНДИДАТ (`status: proposed`), не канон. Промоушен в `.ship/docs/adr/ADR-NNN.md` делает maintainer на Delivery, не агент.

---

## ADR conflict

Реализация противоречит `Status: Accepted` ADR — не продавливать. Запустить [ADR-CONFLICT flow](../ADR-CONFLICT.md) (канон протокола), `detected_by: build`. Специфика этапа: исход "ADR верен" → GREEN переписывает реализацию под ADR (не лезет в N → escalate LOGIC).

---

## Self-review

**ROUTINE / LOGIC** (сабагенты писали код) — проверить:
- [ ] `spec.interface` полностью реализован
- [ ] Все `test_scenarios` покрыты тестами (`test_scenarios: []` → слайс покрыт функц. набором фичи, свои тесты не нужны)
- [ ] Ни один `adr_refs` не нарушен
- [ ] Изменены только `spec.files_to_change` — ничего сверх
- [ ] Все `spec.files_read_only` не тронуты
- [ ] Значения из `data[]` (если есть) в коде/тестах совпадают с артефактом точно — без округлений и «нормализаций»
- [ ] Записи с `value_ref`: файл по `path` прочитан целиком, checksum сходится; `sample` из дескриптора нигде не использован как данные (это выдержка для человека, не источник)

**CRITICAL** (Dev писал сам, сабагенты не вызывались) — проверить:
- [ ] Консультация задокументирована (анализ, риски, предложения)
- [ ] `tdd` блоки в BuildReport = null
- [ ] `self_review.notes` отмечает "CRITICAL: Dev-implemented", автозаписи агента не было
- [ ] Ненарушение `adr_refs` оценивается по Dev-коду (review подтвердит на Phase 3)

Чеклист `files_to_change` / `test_scenarios` к CRITICAL НЕ применяется — код не агента.

---

## Схема выхода

Перед сборкой BuildReport (и ADREntry, если решение того требует) открыть полные схемы + правила их полей (GREEN не трогает тесты, RED не трогает src, LOGIC GREEN только при `approved`, эскалация после N) — [SCHEMA.md](SCHEMA.md).

Сквозные законы (сохранить ВСЕ артефакты до отчёта, `[]` не опускать, выборка ADR через INDEX) — [CANON.md](../CANON.md).