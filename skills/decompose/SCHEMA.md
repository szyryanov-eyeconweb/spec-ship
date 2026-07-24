# Схема выхода TaskSpec

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
    "test_seam": {
      // уровень, на котором RED тестирует (см. шаг 2.5). Контракт для RED, не догадка.
      // null, если test_scenarios: [] — слайс покрыт функциональным набором фичи, тестировать нечего.
      "level": "use-case-harness",  // unit | functional | use-case-harness
      "entry": "<точка входа: класс/метод/эндпоинт из spec.interface>",
      "existing": true,             // seam уже есть в tests/ этой области (prior art) | новый
      "prior_art": "<путь к похожему тесту, если existing>"  // null если новый seam
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

## Правила схемы

- `trust_zone` ставится ОДИН раз здесь, пробрасывается неизменным в BuildReport и ReviewReport.
- `spec.test_seam`: непустой ⟺ `test_scenarios` непустой. Слайс со сценариями → seam по трём правилам шага 2.5 (`existing: true` требует `prior_art`; нет разумного seam → LOGIC, не догадка RED). Слайс с `test_scenarios: []` → `test_seam: null`.
- Тесты — на фичу, не на слайс (шаг 2): один функциональный набор на фичу (`level: functional`/`use-case-harness`) на слайсе внешнего входа; unit только на слайсах с реальной бизнес-логикой (`trust_zone: LOGIC`). Slice без своей логики — `test_scenarios: []`, `test_seam: null`.
- `shape` — `null` для ROUTINE/CRITICAL, непустой скелет `status: "proposal"` для LOGIC. Decompose никогда не ставит `status: "approved"` — апрув на шейп-сессии build с Dev.
- `fan_out` — `null` по умолчанию. Непустой только при всех трёх условиях шага 3.5 SKILL.md, запрещён при `trust_zone: CRITICAL`. При непустом: `layers[].files_to_change` ∪ `contract_paths` ∪ `shared_paths` покрывает весь `spec.files_to_change`, а `contract_paths` и `shared_paths` ⊆ `spec.files_to_change`. Проверить инварианты 1-3 из 3.5. `shared_paths` — `[]` если общей земли нет.
- `test_scenarios`: `workflow`/`input`/`expected_outcome` опциональны, но для ROUTINE предпочтительны. Есть `workflow` → обязаны быть `input` и `expected_outcome`. Типы брать из `spec.interface` / `shape.intermediate_structures`.
- `data` в TaskSpec — копия значений из bd с теми же `d-N`, не изменённая. Расхождение с bd — ошибка decompose.
- Не смешивать в одном TaskSpec `files_to_change` из несвязанных доменных областей.
