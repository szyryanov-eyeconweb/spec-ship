---
name: review
description: Ревью готового билда против его TaskSpec и ADR, затем выдать ReviewReport JSON для пайплайна spec-ship. Использовать когда есть BuildReport готовый к ревью, или когда пользователь говорит "review build", "review task", "phase 3", "pre-MR review", "отревьюй билд".
---

# Review Report

Читает `BuildReport` + его `TaskSpec` и производит артефакт `ReviewReport`, сохраняя в `.ship/pipeline/`.

## Pre-flight

Определить slug фичи по правилу slug из [CANON.md](../CANON.md). Пример: `bd-2026-0002-db-connection-reconnect`.

Загрузить из `.ship/pipeline/{slug}/`:
- `BuildReport`: `build-<id>.json` (спросить если неоднозначно)
- `TaskSpec`: `task-<id>.json` (из `build.task_spec_id`)
- `BusinessDoc`: `bd-<id>.json` (из `business_doc_id` таскспека). `business_doc_id: null` → задача из `bug-fix`: вместо bd загрузить `Diagnosis` `diag-<id>.json` (из `diagnosis_id`); ожидания берутся из `defect.expected`, не из `acceptance_criteria`
- ADR из `adr_refs` — резолвить через `.ship/docs/adr/INDEX.md`, загрузить тела только этих (НЕ все ADR)
- Все `ADREntry` из `build.adr_entries`

Если `build.escalation` не null → пропустить авто-ревью, surface эскалацию Dev сразу.

---

## Review checklist

Прогнать каждую проверку. При провале: `pass: false` + конкретные `notes` с `file:line`.

### 1. spec_coverage
- Весь `spec.interface` реализован.
- Нет недокументированных endpoint/param.
- Значения из `data[]` TaskSpec присутствуют в реализации точно: те же числа, порядок, размерность, шаблоны. Тихо изменённая константа (округление, «нормализация», другой дефолт в конфиге) = провал проверки.
- Запись с `value_ref` проверяется **по checksum**, не глазами: пересчитать хеш файла по `path` и сверить с `value_ref.checksum`. Расхождение = провал (данные изменены после заморозки спеки). Если реализация скопировала данные в свой формат (сид, конфиг, миграция) — сверить, что копия полна и упорядочена как источник: `shape` из дескриптора говорит, сколько строк и колонок должно быть.

### 2. test_scenarios_covered
- `tests_written` в BuildReport ≥ числа `test_scenarios` в TaskSpec.
- `test_scenarios: []` (слайс без своих тестов) — валидно: покрытие даёт функциональный набор фичи на слайсе-носителе. Проверить, что этот носитель существует и его функц. сценарии покрывают `acceptance_criteria`, к которым слайс маппится. Баг-фикс: `test_scenarios: []` **не** валидно — репро-сценарий обязателен (см. check #6).
- Каждый `ts-*` сценарий имеет соответствующий тест.
- Тесты через публичный интерфейс (без моков доменных внутренностей).
- **Тест ассертит результат, не взаимодействие.** Провал: тест, чей единственный assert — «метод вызван N раз» / `expects()->method()` / verify мока внутреннего коллаборатора / порядок вызовов. Такой тест не проверяет поведение. Исключение — внешний эффект (платёж, внешний API/шина, email/webhook): там verify вызова внешней границы легитимен. Внутренний сервис/репозиторий/маппер под исключение не подпадает.
- Тесты написаны на заявленном `spec.test_seam`: `level` и `entry` совпадают. Тест, ушедший глубже (unit внутренностей вместо заявленного use-case-harness) или обошедший seam мокингом — провал: seam выбран decompose как контракт, RED его не переопределяет.
- Если у сценария заполнены `workflow`/`input`/`expected_outcome` — тест ассертит именно `expected_outcome` (включая тип исключения для sad), не ослабленную версию.
- Если `input` сценария ссылается на `d-N` — фикстура теста построена из точного значения `data[]`, не из аппроксимации или усечённой версии. При `value_ref` фикстура читает файл по `path` целиком; тест, построенный на `sample` из дескриптора (3 строки вместо 200) — провал: `sample` существует для чтения человеком, не как данные.

### 3. adr_violations
- Ни один `adr_refs` из TaskSpec не нарушен реализацией.
- Новые `ADREntry` не противоречат существующим ADR.
- Ни один `adr_refs` не указывает на ADR со `Status: Expired` — устаревший ADR не должен быть в ссылках.
- При нарушении различить тип (см. ADR conflict ниже): код виноват → NEEDS_WORK; ADR устарел → ESCALATE.

### 4. regressions
- Скан `files_changed` — вызывающие изменённый код не сломаны.
- Нет новых падений тестов.

### 5. performance
- Если `definition_of_done` BusinessDoc содержит latency/throughput target: проверить что адресован.
- Если `ADREntry` отмечает performance-следствие: валидировать что claim правдоподобен.

### 6. regression_guard (только баг-фикс)

Применяется, когда `TaskSpec.diagnosis_id` не null (задача пришла из `bug-fix`). Иначе `{ "pass": true, "notes": "n/a — не баг-фикс" }`.

- Репро-тест из `Diagnosis.repro_test` существует и остался в наборе постоянно (не удалён, не помечен skip).
- Тест был RED до фикса (`Diagnosis.repro_test.was_red: true`) и GREEN после.
- Фикс лежит в `Diagnosis.blast_radius.fix_point`, а не только в пути из тикета. Guard в одном вызывающем при `fix_point_is_shared: true` = провал: сиблинги остались сломанными.
- Каждый `blast_radius.callers` с `broken: true` либо покрыт этим билдом, либо имеет свой TaskSpec. Непокрытый сиблинг — blocking issue.
- `data_corruption` не null → проверить, что cleanup идёт **отдельным** TaskSpec, а не смешан с фиксом кода.

---

## Verdict

| Результат | Условие |
|-----------|---------|
| `APPROVED` | все 6 проверок pass |
| `NEEDS_WORK` | ≥1 провал, чинимо агентом без Dev |
| `ESCALATE` | фундаментальный конфликт spec, проблема безопасности или архитектурное нарушение |

- `APPROVED` → `mr_ready: true`, сохранить ReviewReport.
- `NEEDS_WORK` → список issues с `severity: "blocking" | "warning"`, `mr_ready: false`.
- `ESCALATE` → `mr_ready: false`, заполнить `escalation`, уведомить Dev с полным контекстом.

---

## Проверка TEST-UPDATE

Если `BuildReport.tdd.agent_green.status == "conflict"`:
- Проверить наличие `TestUpdateTicket` в `.ship/pipeline/{slug}/tu-*.json`.
- Если `resolution.status == "pending"` → блок MR, добавить в `issues[]` с `severity: "blocking"`.

---

## ADR conflict check

Если check #3 (`adr_violations`) упал — противоречие с ADR. Запустить [ADR-CONFLICT flow](../ADR-CONFLICT.md) (канон протокола). Детектор `detected_by: review`. Специфика этапа по исходу: "ADR верен" → `NEEDS_WORK`; "ADR устарел" → `ESCALATE`. Оба → `mr_ready: false`.

Если есть `adr-change-*.json` с `human_verdict.status == pending` → блок MR, issue severity blocking.

---

## Save artifact

Сохранить `ReviewReport` в `.ship/pipeline/{slug}/review-<task-id>.json`.

---

## Схема выхода ReviewReport

```jsonc
{
  "$schema": "pipeline/review-report",
  "id": "review-0042-03",
  "build_report_id": "build-0042-03",
  "task_spec_id": "task-0042-03",
  "created_at": "<ISO8601>",

  "verdict": "APPROVED",          // APPROVED | NEEDS_WORK | ESCALATE

  "checklist": {
    "spec_coverage":          { "pass": true, "notes": null },
    "test_scenarios_covered": { "pass": true, "notes": "5/5 сценариев покрыты" },
    "adr_violations":         { "pass": true, "notes": null },
    "regressions":            { "pass": true, "notes": null },
    "performance":            { "pass": true, "notes": "p95 45ms, DoD < 200ms" },
    "regression_guard":       { "pass": true, "notes": "n/a — не баг-фикс" }
  },

  "issues": [],
  // при NEEDS_WORK или ESCALATE:
  // [{ "severity": "blocking | warning", "location": "file:line", "description": "..." }]

  "escalation": null,
  // при ESCALATE:
  // { "reason": "...", "recommended_action": "..." }

  "mr_ready": true
}
```

## Правила

- `mr_ready: true` ТОЛЬКО когда `verdict == "APPROVED"` И нет pending TestUpdateTicket.
- Все 6 ключей checklist всегда присутствуют. `regression_guard` на не-баг-задаче — `pass: true` с пометкой `n/a`, не отсутствующий ключ.
- `issues[]` пуст для APPROVED, непуст для NEEDS_WORK/ESCALATE.
- `escalation` = null для не-ESCALATE вердиктов.
- Сохранить файл до отчёта о завершении.