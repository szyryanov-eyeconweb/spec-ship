# Схема выхода Diagnosis

```jsonc
{
  "$schema": "pipeline/diagnosis",
  "id": "diag-2026-0011",
  "created_at": "<ISO8601>",
  "created_by": "dev:<username>",
  "survey_id": "survey-2026-0011",     // survey шага 2, обязателен

  "defect": {
    "symptom": "<что наблюдаемо: значение/исключение/отсутствующий эффект, с числами и именами>",
    "repro": "<шаги | команда | падающий тест | входные данные>",
    "repro_frequency": null,           // null = детерминированно; иначе "K из N прогонов" (флик)
    "expected": "<каким поведение задумано>",
    "expected_source": "workflow-doc:.ship/docs/workflows/payout.md",
                                       // workflow-doc:<путь> | adr-NNN | bd-NNNN | dev | none
                                       // none → гейт «баг или намеренное поведение?», диагноз не сохраняется
    "source_was_wrong": false          // true если expected_source — workflow-doc, и док разошёлся
                                       // с реальностью → doc-promote-feature после мёржа обязателен
  },

  "repro_test": {
    "path": "<путь к тесту, написанному ship-red на шаге 3>",
    "test_id": "<метод/имя сценария>",
    "was_red": true,                   // подтверждено красным до анализа корня; false недопустим
    "seam_level": "use-case-harness"   // unit | functional | use-case-harness
  },

  "hypotheses": [
    {
      "id": "h-1",
      "statement": "<что именно неверно и где>",
      "location": "src/<путь>.php#<метод>",
      "evidence_for":     ["src/<путь>.php:142 — <что подтверждает>"],
      "evidence_against": ["tests/<путь>.php:88 — <что опровергает>"],
      "verdict": "refuted"             // confirmed | refuted | unresolved
    }
  ],
  // Ровно одна confirmed — и она объясняет ВЕСЬ симптом. Частичное объяснение = корень не найден.
  // Все refuted/unresolved при исчерпанных N=5 → эскалация человеку, TaskSpec не производится.

  "root_cause": {
    "hypothesis_id": "h-3",
    "broken_assumption": "<какое допущение сломано — не «где симптом»>",
    "location": "src/<путь>.php#<метод>",
    "explains_full_symptom": true      // false → корень не найден, к шагу 4
  },
  // null, когда корень не найден (эскалация)

  "blast_radius": {
    "root_symbol": "src/<путь>.php#<метод>",
    "callers": [
      {
        "symbol": "src/<путь>.php#<метод>",
        "broken": true,                 // ломается тем же корнем
        "reason": "<обоснование: почему ломается / почему нет>",
        "covered_by_task": "task-0011-01"   // null если требует отдельного TaskSpec
      }
    ],
    "fix_point": "src/<путь>.php#<метод>",
    // общая точка, где сходятся все вызывающие. Фикс идёт СЮДА, не в путь из тикета.
    "fix_point_is_shared": true
    // false → общей точки нет: все места перечислены в spec.files_to_change TaskSpec явно,
    // ни одно не «на потом»
  },

  "data_corruption": null,
  // Накопленная порча данных, если есть. ВСЕГДА отдельный TaskSpec от фикса кода:
  // {
  //   "scope": "<что испорчено: таблица/поле/диапазон записей>",
  //   "volume": "<оценка объёма>",
  //   "cleanup_task_id": "task-0011-02",
  //   "trust_zone": "CRITICAL"        // миграция данных — почти всегда CRITICAL
  // }

  "tasks_produced": ["task-0011-01"],  // все TaskSpec, произведённые из этого диагноза

  "adr_refs": ["adr-007"],             // Accepted ADR, пересекающие область корня

  "approval": {
    "status": "approved",              // pending | approved
    "approved_by": "dev:<username>",   // апрув диагноза обязателен (шаг 8)
    "approved_at": "<ISO8601>"
  }
}
```

## Правила схемы

- `survey_id` обязателен: у бага якорь всегда в существующем коде, survey не опционален.
- `repro_test.was_red: true` — предусловие сохранения диагноза. Репро-тест пишется ДО анализа корня; диагноз без красного теста — гипотеза.
- `defect.expected_source: "none"` не сохраняется: гейт «баг или намеренное поведение?» разрешается до артефакта.
- `hypotheses[]` непуст всегда. Каждая запись несёт `evidence_for` или `evidence_against` с `файл:строка` — «похоже, дело в кеше» не гипотеза.
- `root_cause: null` ⟺ корень не найден ⟺ `tasks_produced: []` (эскалация, TaskSpec не производится).
- `root_cause.explains_full_symptom: false` недопустимо при непустом `tasks_produced`: чинить неполностью объяснённый симптом = чинить симптом.
- `blast_radius.callers` перечисляет ВСЕХ вызывающих корневой символ, включая `broken: false` с обоснованием. Пропущенный сиблинг — главный класс дефекта баг-фикса.
- Каждый `broken: true` вызывающий либо покрыт `covered_by_task`, либо породил свой TaskSpec. Молчаливый пропуск запрещён.
- `data_corruption.cleanup_task_id` ≠ TaskSpec фикса кода: фикс останавливает порчу, миграция чинит накопленное. Разный trust_zone, разный откат.
- `defect.source_was_wrong: true` → после мёржа обязателен `doc-promote-feature`: `Status: current` док, разошедшийся с кодом, — источник следующего бага.
- `approval.status` при сохранении = `approved`. Диагноз без апрува человека не сохраняется.

## Производимый TaskSpec

Схема — [decompose/SCHEMA.md](../decompose/SCHEMA.md) без изменений, чтобы `build` не отличал баг от фичи. Поля, заполняемые иначе:

| Поле | На баге |
|---|---|
| `business_doc_id` | `null` — BusinessDoc не существует |
| `diagnosis_id` | id диагноза (источник вместо bd) |
| `validation.business_doc_coverage` | `[]` — покрытие против `defect.expected` |
| `test_scenarios[]` | содержит репро-сценарий (`scenario: "sad"`/`edge`) как постоянный regression guard |
