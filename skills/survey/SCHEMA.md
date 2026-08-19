# Схема выхода Survey

```jsonc
{
  "$schema": "pipeline/survey",
  "id": "survey-2026-0007",
  "created_at": "<ISO8601>",
  "created_by": "dev:<username>",
  "business_doc_id": null,          // bd-id если survey делается для существующего BusinessDoc

  "anchor": {
    "entrypoint": "<точный символ/роут/тест>",
    "changed_assumption": "<что устаревает>",   // на баг-входе: null (ничего не меняем осознанно)
    "why_non_local": "<почему не локальная правка>",

    "defect": null
    // Опционально, только на баг-входе (survey вызван из bug-fix). Якорь бага двухчастный:
    // entrypoint = где симптом НАБЛЮДАЕТСЯ, корень может быть в другом месте — survey его
    // не объявляет (это забота bug-fix).
    // {
    //   "symptom": "<что наблюдаемо>",
    //   "repro": "<шаги | падающий тест>",
    //   "expected": "<каким поведение задумано>",
    //   "expected_source": "workflow-doc:<путь> | adr-NNN | bd-NNNN | dev"
    // }
  },

  "observed_workflows": [
    {
      "name": "<имя код-пути>",
      "workflow": "trigger --шаг--> состояние --шаг--> [ветка 1, ветка 2]",
      "entry_symbol": "<путь>#<метод>"
    }
  ],

  "connected_groups": [
    {
      "group": "persistence",       // entry_orchestration | loaders_resolvers | persistence |
                                    // response_propagation | consumers | validation
      "symbols": ["src/<путь>.php#<метод>"],
      "why_connected": "<связь с якорем>",
      "risk_if_skipped": "<что сломается при пропуске>"
    }
  ],

  "validation_boundaries": [
    {
      "where": "<символ/слой входа слабого инпута>",
      "validates": "<что проверяется/нормализуется>",
      "post_validation_contract": "<на что могут полагаться внутренние шаги>",
      "revalidation_required_at": null   // или "<граница доверия>"
    }
  ],

  "files_evidence": {
    "to_change": [
      { "path": "<путь>", "reason": "<роль в изменении>" }
    ],
    "read_only": [
      { "path": "<путь>", "reason": "<зачем учитывать>" }
    ]
  },

  "adr_refs": ["adr-007"],          // Accepted ADR, пересекающие область якоря

  "empty_groups_checked": ["consumers"]  // проверенные и пустые группы
}
```
