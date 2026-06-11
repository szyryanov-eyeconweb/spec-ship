---
name: decompose
description: Разбить замороженный BusinessDoc на артефакты TaskSpec v1 JSON для пайплайна spec-ship. Использовать когда BusinessDoc существует и approved, или когда пользователь говорит "decompose feature", "create task specs", "phase 1", "разбей фичу".
---

# Decompose

Читает approved `BusinessDoc v1` и производит по одному `TaskSpec v1` JSON на подзадачу, сохраняя в `.ship/pipeline/`.

## Процесс

### 1. Прочитать входы

- Загрузить целевой `BusinessDoc` из `.ship/pipeline/{slug}/bd-*.json` (спросить id если неоднозначно; вывести slug из id + feature.title как в шаге 6).
- Загрузить `Survey` из `.ship/pipeline/{slug}/survey-*.json`, если есть. Тогда `spec.files_to_change`/`spec.files_read_only` каждого TaskSpec выводятся из `files_evidence` survey (доказательно, с причинами), а не из головы. Файл сверх survey — допустимо, но требует явной причины в `spec.description`.
- Прочитать `CONTEXT.md` и файлы из `spec.files_read_only` для понимания существующих интерфейсов.
- Прочитать `.ship/docs/adr/INDEX.md` (НЕ все ADR). Отфильтровать `Status: Accepted` где `Area` пересекает фичу, загрузить тела ТОЛЬКО matched. Expired игнорировать.

### 2. Выделить подзадачи

Перед разбивкой: если в BusinessDoc (v2) есть `open_questions` с `severity: "blocking"` без `resolution` — СТОП, вернуть пользователю на дорешение, не декомпозировать.

Разбить фичу на вертикальные слайсы — каждый независимо собираем и тестируем:
- Каждый слайс задевает ВСЕ нужные слои (schema → logic → API → test).
- Предпочитать тонкие слайсы толстым.
- Каждый слайс маппится на ≥1 `acceptance_criteria` из BusinessDoc.
- Если у `acceptance_criteria` заполнен `workflow` (v2) — выводить `test_scenarios[].workflow` из него: ветки `[...]` дают отдельные сценарии (happy/edge/sad), конечные состояния — `expected_outcome`.
- Если в BusinessDoc есть `data[]` — в каждый TaskSpec пробросить subset записей, нужных его сценариям, КОПИЕЙ значений с теми же `d-N` id. Не ссылкой: сабагенты работают в изолированном контексте и bd не видят — TaskSpec самодостаточен. `test_scenarios[].input` ссылается на `d-N` вместо дублирования значения в прозе.

### 3. Классифицировать trust zone

Для каждой подзадачи назначить `trust_zone`. Формальный признак — нужен ли задаче `shape` (алгоритмический план, см. схему):

- `ROUTINE` — чистая реализация, нет архитектурной неоднозначности, Two-Agent TDD безопасен. Признак: декларативного описания + `spec.interface` достаточно для кода без угадывания → `shape: null`.
- `LOGIC` — нетривиальная логика или интеграция, Dev должен сначала зашейпить решение. Признак: нужны промежуточные структуры (индексы, графы, staged-преобразования), правила упорядочивания/reconciliation, или алгоритм должен остаться developer-owned → создать скелет `shape` со `status: "proposal"`: зафиксировать что уже известно (подход, кандидаты структур) и перечислить открытое в `open_for_developer`.
- `CRITICAL` — целостность данных, безопасность, миграции — только Dev, агент = консультант. `shape: null` (решение целиком в сессии с Dev, не в артефакте). Сигнал из survey: слайс задевает группу `persistence` с миграциями или одновременно `persistence` + `response_propagation`.

Если при наполнении `shape` выяснилось, что шейпить нечего — это сигнал переклассифицировать в ROUTINE, не наоборот.

### 4. Проверить TEST-UPDATE конфликты

Скан существующих тестов в `tests/` на сценарии конфликтующие с новым spec. Для каждого найденного:
- НЕ включать в TaskSpec.
- Произвести отдельный `TestUpdateTicket v1` JSON в `.ship/pipeline/{slug}/tu-*.json`.

### 5. Валидировать покрытие

- [ ] Каждый `acceptance_criteria` из BusinessDoc покрыт хотя бы одним TaskSpec.
- [ ] Нет циклических цепочек `depends_on`.
- [ ] `spec.files_to_change` содержит только реально меняемые файлы.

Показать разбивку пользователю (title, trust_zone, depends_on). Получить апрув до сохранения.

### 6. Сохранить артефакты

Определить директорию фичи: прочитать `id` из BusinessDoc, вывести slug `{bd-id}-{kebab}` (то же правило что shape-doc: 4–6 значимых слов из `feature.title`, kebab-case). Пример: `bd-2026-0002-db-connection-reconnect`.

Сохранить каждый TaskSpec в `.ship/pipeline/{slug}/task-<NNNN>-<NN>.json`.
Обновить `status` BusinessDoc на `"frozen"` в его `.ship/pipeline/{slug}/bd-*.json`.

---

## Схема выхода TaskSpec

```jsonc
{
  "$schema": "pipeline/task-spec/v2",
  "id": "task-0042-03",
  "business_doc_id": "bd-2024-0042",
  "created_at": "<ISO8601>",

  "title": "<краткий заголовок в повелительном>",
  "trust_zone": "ROUTINE",        // ROUTINE | LOGIC | CRITICAL

  "spec": {
    "description": "<что строить, поведение end-to-end>",
    "interface": {
      "input":  { "<поле>": "<тип>" },
      "output": { "<поле>": "<тип>" }
    },
    "files_to_change": ["<путь>"],
    "files_read_only": ["<путь>"]
  },

  "shape": null,
  // null для ROUTINE и CRITICAL. Для LOGIC — алгоритмический план:
  // {
  //   "status": "proposal",       // proposal | approved — GREEN запускается только при approved
  //   "approach": "<алгоритмический путь решения>",
  //   "intermediate_structures": [
  //     {
  //       "name": "<имя по содержимому, напр. tx_index_by_label>",
  //       "derived_from": "<исходные данные>",
  //       "consumed_by": "<шаг/модуль-потребитель>",
  //       "invariants": ["<инвариант, снимающий ревалидацию ниже по потоку>"]
  //     }
  //   ],
  //   "ordering_rules": ["<правила порядка/батчинга/агрегации>"],
  //   "open_for_developer": ["<что осталось решить Dev на шейп-сессии>"],
  //   "approved_by": null,        // "dev:<username>" после апрува
  //   "approved_at": null
  // }

  "data": [
    // subset data[] из BusinessDoc, нужный сценариям этого слайса.
    // КОПИЯ значений с сохранением d-N id (сабагенты bd не видят).
    // [] если слайсу конкретные данные не нужны.
    {
      "id": "d-1",
      "name": "rakeback_rate_matrix",
      "purpose": "<что управляет>",
      "value": null               // точное значение из bd, без изменений
    }
  ],

  "test_scenarios": [
    {
      "id": "ts-1",
      "scenario": "happy",        // happy | edge | sad
      "description": "<что проверить>",
      "workflow": "<состояние с данным входом --шаг(и)--> конечное состояние>",
                                  // опционально; стрелочный синтаксис (канон — README);
                                  // для edge/sad — ветка отказа явно;
                                  // типизированная форма "состояние: Тип" — когда тип
                                  // задан spec.interface или shape.intermediate_structures
      "input": "<вход: значения/фикстура>",            // опционально; обязателен при workflow
      "expected_outcome": "<результат или исключение>" // опционально; обязателен при workflow
    }
  ],

  "dependencies": {
    "depends_on": ["task-0042-01"],
    "blocks":     ["task-0042-05"]
  },

  "adr_refs": ["adr-007"],

  "validation": {
    "business_doc_coverage": ["ac-1", "ac-2"],
    "risk": "low",                // low | medium | high
    "risk_reason": null
  }
}
```

## Схема TestUpdateTicket (при найденном конфликте)

```jsonc
{
  "$schema": "pipeline/test-update-ticket/v1",
  "id": "tu-0042-03",
  "detected_by": "decomposer",    // agent_green | decomposer | ci
  "detected_at": "<ISO8601>",
  "task_spec_id": "task-0042-03",
  "conflict": {
    "test_file": "<путь>",
    "test_id": "<ts-id>",
    "current_expectation": "<что тест сейчас утверждает>",
    "spec_expectation": "<что требует spec>",
    "adr_ref": null,
    "spec_ref": "ac-2"
  },
  "resolution": {
    "status": "pending",          // pending | approved | rejected
    "agent_red_action": "<что должен сделать Agent RED>",
    "approved_by": null,
    "approved_at": null
  }
}
```

## Правила

- `trust_zone` ставится ОДИН раз здесь и пробрасывается неизменным в BuildReport и ReviewReport.
- `shape` обязан быть `null` для ROUTINE/CRITICAL и непустым скелетом `status: "proposal"` для LOGIC. Decompose никогда не ставит `status: "approved"` — апрув шейпа происходит на шейп-сессии build с Dev.
- `test_scenarios`: поля `workflow`/`input`/`expected_outcome` опциональны, но для ROUTINE-задач предпочтительны — однозначный сценарий снижает исход `blocked` у RED. Если есть `workflow`, обязаны быть `input` и `expected_outcome`. Состояния в `workflow` — из доменного глоссария `CONTEXT.md`; синтаксис (включая типизированную форму `состояние: Тип`) — по канону нотации в README. Типы в состояниях брать из `spec.interface` / `shape.intermediate_structures`, не выдумывать ради синтаксиса.
- Артефакты `pipeline/task-spec/v1` (без поля `shape`) остаются валидными — читать как `shape: null`. Артефакты без `data` — читать как `[]`.
- `data` в TaskSpec — всегда копия значений из bd с теми же `d-N`, никогда не изменённая и не «улучшенная». Расхождение значения с bd — ошибка decompose.
- Никогда не делать TaskSpec со смешанными `files_to_change` из несвязанных доменных областей.
- Сохранить ВСЕ файлы до отчёта.
- НЕ менять исходные файлы.