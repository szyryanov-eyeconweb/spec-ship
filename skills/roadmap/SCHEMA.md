# Схемы roadmap

## Схема MAP.json

```jsonc
{
  "$schema": "roadmap/map",
  "epic": "checkout-v2",              // kebab-slug цели
  "created_at": "<ISO8601>",
  "created_by": "<username>",

  "destination": "<чего достигает эпик; какое состояние продукта = готово. 1–2 строки; каждая сессия сверяется с ним перед выбором тикета>",

  "notes": {
    "domain": "<область эпика>",
    "consult_skills": ["survey", "shape-doc"],   // что каждая сессия должна учитывать
    "preferences": ["<стоячие предпочтения этого эпика>"]
  },

  // индекс: одна строка на закрытый тикет — достаточно чтобы судить релевантность,
  // деталь — по ссылке в тикете. Граница скоупа сюда НЕ попадает (см. out_of_scope).
  "decisions_so_far": [
    { "ticket": "ticket-01", "title": "<заголовок>", "gist": "<однострочный итог ответа>" }
  ],

  // туман: в-скоупе, но ещё не резкое для тикета. Коарсер тикета.
  "not_yet_specified": [
    "<предполагаемый вопрос / область на потом>"
  ],

  // граница эпика: сознательно исключённое. Не graduates.
  "out_of_scope": [
    { "gist": "<что>", "why": "<почему за целью>", "ticket": "ticket-NN" }  // ticket — если был закрыт out_of_scope
  ]
}
```

## Схема ticket-NN.json

```jsonc
{
  "$schema": "roadmap/ticket",
  "id": "ticket-03",
  "epic": "checkout-v2",
  "created_at": "<ISO8601>",

  "title": "<заголовок — по нему ссылаются, не по id>",
  "type": "grilling",                 // survey | prototype | grilling | task
  "hitl": true,                       // true = человек в цикле; false = AFK. task бывает любым

  "question": "<решение или исследование, которое тикет резолвит; размер — одна сессия>",

  "dependencies": {
    "depends_on": ["ticket-02"],      // blocking: тикет разблокирован когда все закрыты
    "blocks": ["ticket-05"]
  },

  "claimed_by": null,                 // "<username>" — заявка; ставится ДО работы
  "status": "open",                   // open | closed

  // заполняется при резолве:
  "resolution": null,                 // <ответ: что решено/исследовано/сделано>
  "outcome": null,                    // decision | ready_for_run | out_of_scope | done(task)
  "assets": [],                       // ссылки на созданные артефакты (survey-*.json, прототип), не вклеивать тела
  "resolved_at": null,

  // только при outcome == "ready_for_run" — обогащённый вход для /spec-ship:run.
  // НЕ BusinessDoc: run сам проведёт shape-doc. Но несёт контекст, накопленный
  // картой — чтобы shape не переспрашивал уже решённое эпиком.
  "run_handoff": null
  // {
  //   "feature_description": "<свободное описание фичи для run>",
  //   "anchor": "<якорь в коде, если меняется существующее; null если greenfield>",
  //   "decisions": ["ticket-01", "ticket-04"],   // релевантные фиче closed-тикеты
  //                                              // (shape читает их resolution как контекст)
  //   "in_scope": ["<что входит в эту фичу>"],   // границы фичи из карты
  //   "out_of_scope": ["<что явно НЕ эта фича>"], // чтобы shape не растащил скоуп
  //   "survey_ref": null,   // путь к survey-*.json, если тикет типа survey его создал —
  //                         // run пропускает свой survey, shape стартует с этой карты кода
  //   "adr_refs": []        // ADR, задетые решениями фичи (уже выявлены картой)
  // }
}
```

## Правила схемы

- `run_handoff` заполняется из карты, не выдумывается: `decisions`/`adr_refs` — из реальных closed-тикетов, `out_of_scope` — из секции карты.
- Все поля-списки (`decisions_so_far`, `not_yet_specified`, `out_of_scope`, `assets`) — `[]` если пусто.
