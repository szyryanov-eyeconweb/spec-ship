# Схема выхода BuildReport

```jsonc
{
  "$schema": "pipeline/build-report",
  "id": "build-0042-03",
  "task_spec_id": "task-0042-03",
  "trust_zone": "ROUTINE",
  "fan_out": null,                // или { "layers": [{ "role": "application", "status": "done", "worktree": "<path>" }, ...], "shared_written": true, "merged": true }
                                  // статусы слоя: done | escalated | conflict | immature-contract | out-of-bounds (вылазка за границы)
  "created_at": "<ISO8601>",

  "tdd": {
    "agent_red": {
      "status": "done",
      "tests_written": 5,
      "test_files": ["tests/<path>.php"],
      "all_red_confirmed": true
    },
    "agent_green": {
      "status": "done",           // done | escalated | conflict
      "iterations": 2,
      "files_changed": ["src/<path>.php"],
      "all_green_confirmed": true,
      "conflict": null            // или { "test_id": "ts-3", "reason": "..." }
    }
  },

  "escalation": null,
  // если escalated:
  // {
  //   "reason": "green_iterations_exceeded | test_spec_conflict",
  //   "escalated_to": "LOGIC",
  //   "details": "...",
  //   "test_update_ticket": null
  // }

  "adr_entries": [],              // список id adr-entry, или []

  "self_review": {
    "spec_coverage": true,
    "adr_violations": [],
    "notes": "<неочевидные заметки по реализации>"
  }
}
```

## Схема выхода ADREntry

```jsonc
{
  "$schema": "pipeline/adr-entry",
  "id": "adr-entry-0042-a",
  "task_spec_id": "task-0042-03",
  "created_at": "<ISO8601>",
  "status": "proposed",           // proposed | promoted (промоушен делает adr-promote)
  "promoted_to": null,            // "adr-015" после промоушена в канон

  "decision": "<что решено>",
  "context": "<зачем нужно это решение>",
  "consequences": ["<следствие 1>"],
  "alternatives_considered": ["<альт 1>", "<альт 2>"],
  "files_ref": ["<путь>:<строка>"],
  "adr_refs_used": ["adr-007"]
}
```

## Правила схемы

- GREEN никогда не трогает тесты. RED никогда не трогает src.
- LOGIC: GREEN только при `shape.status: "approved"`. Запись `shape` — единственная разрешённая правка сохранённого TaskSpec (ничего сверх).
- Эскалация после N — не зацикливаться.
- `self_review.adr_violations` обязан быть `[]`, иначе downstream `mr_ready` = false.
