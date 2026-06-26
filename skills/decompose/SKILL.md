---
name: decompose
description: Разбить замороженный BusinessDoc на артефакты TaskSpec JSON для пайплайна spec-ship. Использовать когда BusinessDoc существует и approved, или когда пользователь говорит "decompose feature", "create task specs", "phase 1", "разбей фичу".
---

# Decompose

Читает approved `BusinessDoc`, производит по одному `TaskSpec` JSON на подзадачу в `.ship/pipeline/`.

## Процесс

### 1. Прочитать входы

- Загрузить `BusinessDoc` из `.ship/pipeline/{slug}/bd-*.json` (спросить id если неоднозначно; slug — из id + feature.title, см. шаг 6).
- Загрузить `Survey` из `.ship/pipeline/{slug}/survey-*.json`, если есть. Тогда `spec.files_to_change`/`spec.files_read_only` каждого TaskSpec выводятся из `files_evidence` survey (с причинами), не из головы. Файл сверх survey допустим, но требует причины в `spec.description`.
- Прочитать `CONTEXT.md` и файлы `spec.files_read_only` — понять существующие интерфейсы.
- Прочитать `.ship/docs/adr/INDEX.md` (НЕ все ADR). Отфильтровать `Status: Accepted` где `Area` пересекает фичу, загрузить тела ТОЛЬКО matched. Expired игнорировать.

### 2. Выделить подзадачи

Перед разбивкой: `open_questions` с `severity: "blocking"` без `resolution` → СТОП, вернуть пользователю на дорешение, не декомпозировать.

Разбить фичу на вертикальные слайсы — каждый независимо собираем и тестируем:
- Каждый слайс задевает ВСЕ нужные слои (schema → logic → API → test).
- Тонкие слайсы предпочтительнее толстых.
- Каждый слайс маппится на ≥1 `acceptance_criteria` из BusinessDoc.
- Если у `acceptance_criteria` заполнен `workflow` — вывести `test_scenarios[].workflow` из него: ветки `[...]` дают отдельные сценарии (happy/edge/sad), конечные состояния — `expected_outcome`.
- Если в BusinessDoc есть `data[]` — пробросить в каждый TaskSpec subset записей под его сценарии, КОПИЕЙ значений с теми же `d-N` id. Не ссылкой: сабагенты в изолированном контексте, bd не видят — TaskSpec самодостаточен. `test_scenarios[].input` ссылается на `d-N`, не дублирует значение в прозе.

### 3. Классифицировать trust zone

Каждой подзадаче назначить `trust_zone`. Формальный признак — нужен ли задаче `shape` (алгоритмический план, см. схему):

- `ROUTINE` — чистая реализация, нет архитектурной неоднозначности, Two-Agent TDD безопасен. Признак: декларативного описания + `spec.interface` достаточно для кода без угадывания → `shape: null`.
- `LOGIC` — нетривиальная логика/интеграция, Dev сначала шейпит решение. Признак: нужны промежуточные структуры (индексы, графы, staged-преобразования), правила упорядочивания/reconciliation, или алгоритм остаётся developer-owned → скелет `shape` со `status: "proposal"`: зафиксировать известное (подход, кандидаты структур), перечислить открытое в `open_for_developer`.
- `CRITICAL` — целостность данных, безопасность, миграции — только Dev, агент = консультант. `shape: null` (решение в сессии с Dev, не в артефакте). Сигнал из survey: слайс задевает `persistence` с миграциями или `persistence` + `response_propagation` вместе.

Если при наполнении `shape` шейпить нечего — сигнал переклассифицировать в ROUTINE, не наоборот.

### 3.5. Fan-out (опционально, ортогонально trust_zone)

Задача может реализовываться слоями-ролями ПАРАЛЛЕЛЬНО, если контракт между слоями фиксируем заранее. Ускорение build, не отдельная trust_zone. **Механика, фазы, worktree, риски — [FAN-OUT.md](../FAN-OUT.md); decompose только классифицирует и валидирует.**

Пометить `fan_out.enabled: true` ТОЛЬКО когда ВСЕ:
1. задача делится на ≥2 слоя-роли (`entry` / `application` / `contract-impl` — см. FAN-OUT.md) с непересекающимися путями;
2. контракт (порты + DTO) фиксируем ДО реализации — известен из `spec.interface`, `shape` или паттерн-дока `.ship/docs/workflows/`;
3. `trust_zone != CRITICAL`.

Заполнить `contract_paths` (порты+DTO), `shared_paths` (общая земля: DI/реестр/схема; `[]` если нет), `layers[]`. Назначение полей — FAN-OUT.md.

Инварианты (проверить перед `enabled: true`):
1. `files_to_change` слоёв попарно НЕ пересекаются;
2. `contract_paths` ∩ любой `layer.files_to_change` = пусто;
3. `shared_paths` ∩ любой `layer.files_to_change` = пусто.
Нарушение любого → не fan_out, обычный build.

Fan-out — оптимизация, не дефолт. Окупается при ≥3 нетривиальных слоях + известном заранее контракте. Сомнение в зрелости контракта → последовательный build.

### 4. Проверить TEST-UPDATE конфликты

Скан тестов в `tests/` на сценарии, конфликтующие с новым spec. Для каждого:
- НЕ включать в TaskSpec.
- Произвести отдельный `TestUpdateTicket` JSON в `.ship/pipeline/{slug}/tu-*.json`.

### 5. Валидировать покрытие

- [ ] Каждый `acceptance_criteria` из BusinessDoc покрыт хотя бы одним TaskSpec.
- [ ] Нет циклических цепочек `depends_on`.
- [ ] `spec.files_to_change` содержит только реально меняемые файлы.

Показать разбивку пользователю (title, trust_zone, depends_on). Получить апрув до сохранения.

### 6. Сохранить артефакты

Определить директорию фичи: прочитать `id` из BusinessDoc, вывести slug по правилу slug из [CANON.md](../CANON.md). Пример: `bd-2026-0002-db-connection-reconnect`.

Сохранить каждый TaskSpec в `.ship/pipeline/{slug}/task-<NNNN>-<NN>.json`.
Обновить `status` BusinessDoc на `"frozen"` в его `.ship/pipeline/{slug}/bd-*.json`.

---

## Схема выхода TaskSpec

```jsonc
{
  "$schema": "pipeline/task-spec",
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

  "fan_out": null,
  // null = обычный последовательный build. Иначе параллель по слоям-ролям:
  // {
  //   "enabled": true,
  //   "contract_paths": ["<пути портов+DTO; Phase A пишет, слои read-only>"],
  //   "shared_paths":   ["<общая земля: DI/реестр/схема; Phase A пишет за все слои, слои read-only>"],
  //   "layers": [
  //     { "role": "application",   "files_to_change": ["<пути>"] },
  //     { "role": "contract-impl", "files_to_change": ["<пути>"] },
  //     { "role": "entry",         "files_to_change": ["<пути>"] }
  //   ]
  //   // role ∈ {entry, application, contract-impl}; files_to_change слоёв попарно НЕ
  //   // пересекаются и не пересекают ни contract_paths, ни shared_paths.
  //   // shared_paths — опционально ([] если общей земли нет).
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
                                  // опционально; стрелочный синтаксис (канон — CANON.md);
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
  "$schema": "pipeline/test-update-ticket",
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

- `trust_zone` ставится ОДИН раз здесь, пробрасывается неизменным в BuildReport и ReviewReport.
- `shape` — `null` для ROUTINE/CRITICAL, непустой скелет `status: "proposal"` для LOGIC. Decompose никогда не ставит `status: "approved"` — апрув на шейп-сессии build с Dev.
- `fan_out` — `null` по умолчанию. Непустой только при всех трёх условиях (см. 3.5), запрещён при `trust_zone: CRITICAL`. При непустом: `layers[].files_to_change` ∪ `contract_paths` ∪ `shared_paths` покрывает весь `spec.files_to_change`, а `contract_paths` и `shared_paths` ⊆ `spec.files_to_change` (контракт + общая земля — часть задачи, пишутся в Phase A). Проверить инварианты 1-3 из 3.5. `shared_paths` — `[]` если общей земли нет.
- `test_scenarios`: `workflow`/`input`/`expected_outcome` опциональны, но для ROUTINE предпочтительны — однозначный сценарий снижает исход `blocked` у RED. Есть `workflow` → обязаны быть `input` и `expected_outcome`. Состояния — из `CONTEXT.md`; синтаксис (включая `состояние: Тип`) — по [CANON.md](../CANON.md). Типы брать из `spec.interface` / `shape.intermediate_structures`, не выдумывать ради синтаксиса.
- `data` в TaskSpec — копия значений из bd с теми же `d-N`, не изменённая и не «улучшенная». Расхождение с bd — ошибка decompose.
- Не делать TaskSpec со смешанными `files_to_change` из несвязанных доменных областей.
- Сохранить ВСЕ файлы до отчёта.
- НЕ менять исходные файлы.