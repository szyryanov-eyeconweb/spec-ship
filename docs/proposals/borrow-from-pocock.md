# План: что изъять у Matt Pocock для spec-ship

Источник: https://github.com/mattpocock/skills (`skills/engineering/`)

Разобраны 5 скиллов: wayfinder, to-spec, to-tickets, implement, code-review.
Дата анализа: 2026-07-10.

## Контекст

Набор Pocock и spec-ship — один жанр: spec-as-contract, стадийный конвейер,
изоляция агентов. Соответствия:

| Pocock | spec-ship |
|---|---|
| to-spec + grilling | shape-doc |
| to-tickets | decompose |
| implement + tdd | build (Two-Agent RED/GREEN) |
| code-review | review |
| — (нет) | adr-promote / doc-promote (канон) |
| wayfinder | — (нет) |

Ключевая разница: у Pocock изоляция RED/GREEN — только промпт; у spec-ship —
барьер на уровне прав (`hooks/ship-guard.sh`, PreToolUse по `agent_type`).
spec-ship жёстче и файло-центричен (артефакты = файлы + хуки), Pocock
трекер-центричен (GitHub/Linear native blocking).

## Кандидаты на изъятие (по приоритету)

### 1. wayfinder → мульти-сессионный слой НАД `run` (самый большой пробел) — ✅ СДЕЛАНО (2026-07-10)

Реализовано как скилл `roadmap`:
- `skills/roadmap/SKILL.md` — карта `.ship/roadmap/{epic}/MAP.json` + `ticket-NN.json`;
  режимы chart/work; типы survey/prototype/grilling/task; туман/out-of-scope; blocking через `depends_on`.
- `commands/roadmap.md`, `docs/00-roadmap.md`; вписано в README, process, 08-run, skills/README.
- Стык: `run_handoff` (B — обогащённый: feature_description+anchor+decisions+scope+survey_ref+adr_refs);
  `shape-doc` и `run` читают handoff, не переоткрывают скоуп. Граница «roadmap не пишет спеку» держится.

- spec-ship = конвейер одной фичи (идея→MR). Работы длиннее одного прогона нет.
- Взять: «карта = индекс, не хранилище» (gist решений + ссылки на тикеты);
  секции карты — Destination / Notes / Decisions-so-far / Fog / Out-of-scope;
  правило «туман→тикет когда можешь чётко сформулировать вопрос, НЕ когда можешь
  ответить»; «out-of-scope не graduates»; «один тикет за сессию».

**РЕШЕНО (2026-07-10) — дизайн стыка:**

- **Стык: созревший тикет → вход в `run`.** wayfinder — слой планирования НАД
  `run`, не пересекается с shape-doc. Карта решает ЧТО и в каком порядке;
  каждый созревший тикет = описание одной фичи → `/spec-ship:run <фича>`;
  `run` уже сам гонит shape→decompose→build→review.
  ```
  roadmap MAP.md
   ├─ [closed] фича A → /run
   ├─ [closed] фича B → /run (blocked by A)
   └─ fog: фича C (ещё не ясна)
  ```

- **Файлы, не трекер.** Pocock весь на native blocking трекера (GitHub/Linear);
  spec-ship осознанно файло-центричен. Карта = markdown `.ship/roadmap/{epic}/MAP.md`,
  тикеты = файлы, blocking = ссылки + порядок (как `depends_on` в decompose).
  Pocock сам разрешает: "default to the local-markdown tracker".

- **Интервью — свой движок.** wayfinder charting = grilling+domain-modeling;
  spec-ship переиспользует интервью shape-doc в breadth-first режиме (широко по
  скоупу эпика, не глубоко по одной фиче). grilling НЕ тащим.

- **Типы тикетов → язык spec-ship:** Research→`survey`, Prototype→набросок
  shape-doc, Grilling→shape-интервью, Task/decision→готов к `run`.

- Связь: перекликается с batch-conveyor / SprintManifest (см. память
  concepts/batch-conveyor-sprint-pipeline). Возможно, объединить.

### 2. code-review → двухосевое ревью с anti-merge (дёшево, ложится на review)
- Сейчас review = «по чеклисту → вердикт».
- Взять: две независимые оси разными суб-агентами —
  - **Standards**: конвенции репо + фиксированный baseline 9 запахов Фаулера
    (Mysterious Name, Duplicated Code, Feature Envy, Data Clumps, Primitive
    Obsession, Repeated Switches, Shotgun Surgery, Divergent Change, Speculative
    Generality, Message Chains, Middle Man, Refused Bequest).
  - **Spec**: реализовано ли то, что просил spec/тикет (missing/extra/wrong).
  - Правило: находки репортятся бок-о-бок, НЕ мёржатся и НЕ реранжируются —
    иначе одна ось маскирует другую (правильный код ≠ та фича, и наоборот).
- Прибито к fixed point: `git diff <ref>...HEAD`.

### 3. to-tickets → expand–contract для широких рефакторингов (в decompose)
- decompose режет на вертикальные задачи + зоны доверия; механический рефактор
  через весь код на вертикальный срез не ложится.
- Взять: отдельная ветка **expand → migrate-by-blast-radius → contract**:
  - expand: новое рядом со старым, ничего не ломается;
  - migrate: call-sites батчами по blast radius, каждый батч = свой тикет;
  - contract: удалить старое после полной миграции.
  - Инвариант: CI зелёный всё время.

### 4. to-spec → test seams как явный артефакт спеки — ✅ СДЕЛАНО (2026-07-10)

Вариант A: seam per-slice в TaskSpec (не на уровне фичи — spec-ship
вертикально-слайсовый, seam живёт на слайсе рядом со `spec.interface`).
Feature-level функциональный тест обсуждён и ОТЛОЖЕН (не сейчас).

- `decompose/SKILL.md` — шаг 2.5 «выбрать test seam» (3 правила Pocock:
  существующий > новый, высший уровень, один на слайс); поле `spec.test_seam`
  в схеме (`level`/`entry`/`existing`/`prior_art`); правило обязательности.
- `agents/ship-red.md` — читает `spec.test_seam` как контракт уровня, не
  выбирает сам; `no_seam` теперь = «заданный seam неверен», не «RED не нашёл».
- `review/SKILL.md` check #2 — seam-adherence: тест на заявленном seam, уход
  глубже / обход мокингом = провал.
- `docs/03-decompose.md` — шаг 3 «test seam» + в списке артефактов.

## НЕ брать
- `implement` — spec-ship build уже жёстче (права, не промпт).
- Трекер-центризм — у spec-ship файлы+хуки, осознанный выбор.
- Внутренние зависимости Pocock (grilling, domain glossary, tdd) — свои есть.

## Дальше
Углубиться в каждый пункт → конкретные диффы в соответствующие скиллы
(skills/run, skills/review, skills/decompose, skills/shape-doc).
