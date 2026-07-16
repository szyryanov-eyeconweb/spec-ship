# Схема выхода BusinessDoc

```jsonc
{
  "$schema": "pipeline/business-doc",
  "id": "bd-2024-0042",
  "created_at": "<ISO8601>",
  "created_by": "ba:<username>",
  "status": "approved",           // draft | approved | frozen

  "feature": {
    "title": "<краткий заголовок>",
    "goal": "<цель глазами пользователя>",
    "actors": ["<актор1>", "<актор2>"],
    "priority": "high",           // low | medium | high | critical
    "workflow": null
    // опционально: сквозной workflow фичи в стрелочном синтаксисе,
    // "trigger --шаг--> состояние --шаг--> [ветка 1, ветка 2]"
    // полезен при ветвистых сценариях; null если GWT-критериев достаточно.
    // при изменении существующего поведения (есть survey) — рефакторинг-форма:
    // "{workflow из survey} --шаг--> {новый workflow}"
  },

  "acceptance_criteria": [
    {
      "id": "ac-1",
      "scenario": "happy",        // happy | edge | sad
      "given": "<предусловие>",
      "when": "<действие>",
      "then": "<ожидаемый результат>",
      "workflow": null
      // опционально: тот же критерий компактно,
      // "given-состояние --when-шаг--> then-состояние"
      // НЕ замена given/when/then — дубль для ветвистых случаев
    }
  ],

  "data": [
    // конкретные значения, управляющие поведением: ставки, пороги,
    // матрицы, шаблоны строк, справочные списки. [] если нет.
    {
      "id": "d-1",
      "name": "rakeback_rate_matrix",   // имя по содержимому, не по архитектурной роли
      "purpose": "<что это значение управляет/ограничивает>",
      "value": null
      // точное значение любой JSON-формы: скаляр, список, объект, матрица
      // (массив массивов), шаблон-строка. Сохранять точность, порядок,
      // размерность — они часть контракта.
    }
  ],

  "open_questions": [
    {
      "id": "q-1",
      "severity": "non_blocking", // blocking | non_blocking
      "question": "<вопрос>",
      "assumption": "<допущение, под которым едем, пока нет ответа>",  // обязателен для non_blocking без resolution
      "resolution": null,         // ответ пользователя; для blocking обязателен до заморозки
      "resolved_at": null
    }
  ],

  "definition_of_done": [
    "<измеримый критерий 1>",
    "<измеримый критерий 2>"
  ],

  "constraints": [
    "<техническое или бизнес-ограничение>"
  ],

  "adr_refs": ["adr-007"],

  "conflicts": [],                // заполняет Requirements Review — список id конфликтующих ADR

  "approved_by": "ba:<username>",
  "approved_at": "<ISO8601>"
}
```

## Правила схемы

- Каждый `acceptance_criteria` требует `given/when/then` — никаких расплывчатых критериев. `workflow` — опциональный дубль для ветвистых случаев, не замена.
- `definition_of_done` измерим: числа latency, % покрытия, явные проверки.
- `data` — точные значения; «около 5%» — это `open_question`, не data-запись. Критерии и `workflow`-поля ссылаются на записи как `d-N`, не дублируют значение в прозе.
- `open_questions`: заморозка/апрув при `blocking` без `resolution` запрещены. Ответы писать в `resolution`, не перетирать `question`.
- Состояния в `workflow`-полях — по канону нотации [CANON.md](../CANON.md).
- НЕ ставить `status: "frozen"` — это делает decompose после производства TaskSpec.
