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
- `BusinessDoc`: `bd-<id>.json` (из `business_doc_id` таскспека)
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

### 2. test_scenarios_covered
- `tests_written` в BuildReport ≥ числа `test_scenarios` в TaskSpec.
- Каждый `ts-*` сценарий имеет соответствующий тест.
- Тесты через публичный интерфейс (без моков доменных внутренностей).
- Если у сценария заполнены `workflow`/`input`/`expected_outcome` — тест ассертит именно `expected_outcome` (включая тип исключения для sad), не ослабленную версию.
- Если `input` сценария ссылается на `d-N` — фикстура теста построена из точного значения `data[]`, не из аппроксимации или усечённой версии.

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

---

## Verdict

| Результат | Условие |
|-----------|---------|
| `APPROVED` | все 5 проверок pass |
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
    "performance":            { "pass": true, "notes": "p95 45ms, DoD < 200ms" }
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
- Все 5 ключей checklist всегда присутствуют.
- `issues[]` пуст для APPROVED, непуст для NEEDS_WORK/ESCALATE.
- `escalation` = null для не-ESCALATE вердиктов.
- Сохранить файл до отчёта о завершении.