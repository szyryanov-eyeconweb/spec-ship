# spec-ship — Spec-to-Ship Pipeline

**S**hape → **H**and-off (decompose) → **I**mplement (build) → **P**rove (review).

пБиблиотека из 7 скиллов + 2 сабагента. Каждый этап читает артефакт предыдущего из `.ship/pipeline/{slug}/` и производит свой JSON по схеме своего этапа. Схема каждого артефакта — JSONC-блок в соответствующем `SKILL.md` (раздел «Схема выхода»); поле `$schema` несёт метку схемы из колонки `Schema ID` карты ниже. Артефакты версионируются в репо.

Этот README — карта и сквозные протоколы. Детали каждого этапа (процесс, схема, кейсы, грабли) — в соответствующем `SKILL.md`, не здесь.

## Карта

| Команда | Скилл | Вход | Выход | Schema ID |
|---|---|---|---|---|
| `/spec-ship:run` | run | описание фичи (+ якорь) | оркеструет всю цепочку | — (дирижёр) |
м| `/spec-ship:survey` | survey | якорь в существующем коде | `survey-*.json` | `pipeline/survey` |
| `/spec-ship:shape-doc` | shape-doc | требование/идея (+ survey) | `bd-*.json` | `pipeline/business-doc` |
| `/spec-ship:decompose` | decompose | `bd-*.json` | `task-*.json` (×N), `tu-*.json` | `pipeline/task-spec`, `pipeline/test-update-ticket` |
| `/spec-ship:build` | build | `task-*.json` | `build-*.json`, `adr-entry-*.json` | `pipeline/build-report`, `pipeline/adr-entry` |
| `/spec-ship:review` | review | `build-*.json` | `review-*.json` | `pipeline/review-report` |
| `/spec-ship:adr-promote` | adr-promote | `adr-entry-*.json` (Proposed) | `.ship/docs/adr/ADR-NNN-*.md` + INDEX | — (markdown канон) |
| `/spec-ship:doc-promote-feature` | doc-promote-feature | `survey-*.json` + `bd-*.json` (после мёржа MR) | `.ship/docs/workflows/*.md` + INDEX | — (markdown канон) |
| `/spec-ship:doc-backfill` | doc-backfill | только `survey-*.json` (без MR-гейта, из существующего кода) | `.ship/docs/workflows/*.md` + INDEX | — (markdown канон) |
| — (внутренний) | doc-promote-internal | source-артефакты от обёртки | `.ship/docs/workflows/*.md` + INDEX | — (конвертер, не вызывается напрямую) |

Сабагенты (`.claude/agents/`), вызываются только из build:

| Сабагент | Права | Роль |
|---|---|---|
| `ship-red` | только `tests/`, читает src | падающие тесты по `test_scenarios`, физически не может подогнать под реализацию |
| `ship-green` | только `files_to_change`, не трогает tests | минимальный код пока тесты зелёные |

Изоляция прав — физический барьер, не инструкция: PreToolUse-хук `ship-guard.sh` отклоняет запись вне разрешённого слоя по `agent_type` (ship-red ≠ src, ship-green ≠ tests). GREEN не может схитрить с тестом, RED не видит реализацию. Контракт между ними — тестовый набор. Барьер активен при зарегистрированном хуке (установка); иначе деградирует до промпт-инструкции в теле сабагента.

## Структура артефактов

```
.ship/pipeline/
├── _intake/                                 ← survey до создания BusinessDoc
│   └── survey-2026-0007.json                  Phase 0a (переносится в slug при shape)
└── {slug}/                                  ← feature slug = {bd-id}-{kebab feature.title}
    ├── survey-bd-2026-0002.json               Phase 0a Survey (опционально)
    ├── bd-2026-0002.json                      Phase 0  BusinessDoc
    ├── task-0002-01.json … task-0002-NN.json  Phase 1  TaskSpec ×N
    ├── tu-0002-01.json                         Phase 1/2  TestUpdateTicket (конфликт теста)
    ├── adr-change-0002-01.json                 Phase 0/2/3  AdrChangeTicket (конфликт ADR)
    ├── build-0002-01.json                      Phase 2  BuildReport
    ├── adr-entry-0002-01-a.json                Phase 2  ADREntry (кандидат, опционально)
    └── review-0002-01.json                     Phase 3  ReviewReport
```

Slug-правило (едино во всех скиллах): `{bd-id}-{kebab}`, `kebab` = 4–6 значимых слов из `feature.title`, lowercase, дефисы. Канон для скиллов — [CANON.md](CANON.md) (грузится точечно, без всего README).

## Два режима запуска

**Точечный** — вызывать этапы по очереди руками (ниже «Сценарий успеха»). Полный контроль на каждом шаге; дешевле для одиночной задачи.

**Оркестрованный** — `/spec-ship:run «описание фичи»` прогоняет всю цепочку одним вызовом, останавливаясь ТОЛЬКО на гейтах участия человека (апрув спеки, апрув разбивки, шейп LOGIC, CRITICAL, эскалации, review ESCALATE). Между автономными этапами и ROUTINE-задачами не дёргает. Флаги `--auto-shape` / `--auto-decompose` / `--auto` снимают низкорисковые гейты (детали — `run/SKILL.md`). Выигрыш — не токены (этапы всё равно выполняются), а число ручных вызовов и переключений контекста: один запуск вместо пяти, Telegram-хук дёргает на гейтах. Окупается на фичах в 3–15 слайсов; для одиночной задачи дешевле прямой `/spec-ship:build`.

## Сценарий успеха

```
/spec-ship:survey TransactionRepository#findByPartner — добавляется фильтр по меткам
   → трассировка → survey-2026-0002.json          (только если меняем существующее поведение)
/spec-ship:shape-doc Фильтрация транзакций по меткам
   → интервью (контекст из survey) → BusinessDoc approved → bd-2026-0002.json
/spec-ship:decompose
   → 3 TaskSpec: -01 (ROUTINE), -02 (LOGIC), -03 (ROUTINE) → bd: frozen
/spec-ship:build task-0002-01
   → ship-red (RED) → ship-green (GREEN) → build-0002-01.json
/spec-ship:review build-0002-01
   → 5/5 checklist → APPROVED → mr_ready: true → review-0002-01.json
```

## Этапы (детали — в SKILL.md)

| Phase | Скилл | Суть | Участие человека |
|---|---|---|---|
| 0a | survey | якорь → трассировка связанного кода, доказательная карта (только для изменений существующего поведения) | подтверждает якорь |
| 0 | shape-doc | требование → BusinessDoc, Requirements Review, заморозка | BA апрувит |
| 1 | decompose | BusinessDoc → vertical slices TaskSpec, классификация trust_zone | апрув разбивки |
| 2 | build | оркестрация билда по trust_zone (см. ниже) | только LOGIC/CRITICAL |
| 3 | review | 5-проверочный чеклист → APPROVED/NEEDS_WORK/ESCALATE, гейт MR | только ESCALATE |

`trust_zone` ставится ОДИН раз на decompose и пробрасывается неизменным в build → review.

## build: маршрутизация по trust_zone

Оркестратор. Выбирает трек по `trust_zone`. Рассуждающая модель (основная сессия) — где мышление; исполнительная (сабагенты) — где исполнение по спеке. Конкретные модели в `model:` сабагентов и настройке сессии, не в тексте скиллов.

| trust_zone | Трек | Поле `shape` в TaskSpec |
|---|---|---|
| `ROUTINE` | сабагенты `ship-red` → `ship-green` автономно | `null` |
| `LOGIC` | Dev шейпит решение в сессии → сабагенты реализуют по шейпу | `proposal` (decompose) → `approved` (шейп-сессия) → контракт для GREEN |
| `CRITICAL` | консультант в сессии, БЕЗ сабагентов, Dev пишет код сам | `null` |

Шейп LOGIC-задачи персистится в поле `shape` TaskSpec, не живёт в памяти сессии: decompose кладёт скелет `proposal` с повесткой `open_for_developer`, шейп-сессия build заполняет план и Dev апрувит (`approved`), GREEN реализует по артефакту. Эскалации из ROUTINE (RED `blocked`, GREEN `escalated`) создают такой же скелет `proposal` с причиной эскалации.

### Fan-out: параллель по слоям (ортогонально trust_zone)

Если задача делится на слои-роли с непересекающимися путями и контракт между ними фиксируем заранее — decompose ставит `fan_out` (см. decompose «3.5»), build реализует слои ПАРАЛЛЕЛЬНО: Phase A (контракт: порты+DTO, сессия) → A.5 (RED все тесты) → B (по `ship-green` на слой, параллельно, изоляция `files_to_change`) → C (интеграция). Слои зависят от контракта, не от кода друг друга — заморозили контракт, реализации независимы. Незрелый контракт → стоп фан-аута → дошейп в Phase A → рестарт B. Ускоряет ROUTINE и LOGIC; не применяется к CRITICAL. Канон механики — [FAN-OUT.md](FAN-OUT.md) (грузить только для fan_out-задач).

## Сквозные протоколы

### Workflow-нотация

DSL описания поведения во всех артефактах. **Канон — [CANON.md](CANON.md)** (горячий файл, его грузят сами скиллы вместо всего README). Скиллы синтаксис не переопределяют, только ссылаются.

### Data-слой: точные значения сквозь пайплайн

Конкретные значения, управляющие поведением (ставки, пороги, матрицы, шаблоны, справочные списки), живут в `data[]` с id `d-N` — не в прозе критериев. Точность, порядок, размерность — часть контракта.

```
bd.data[] (интервью: точное значение или open_question)
   → decompose: subset КОПИЕЙ в task.data[] (те же d-N; сабагенты bd не видят)
      → RED: input "d-N" → фикстура из точного значения
      → GREEN: значение в код/конфиг без изменений (где живёт — решает shape/spec)
         → review check #1/#2: точное совпадение, тихо изменённая константа = провал
            → doc-promote: управляющие значения → Definitions канона
```

«Около 5%» — это `open_question`, не data-запись.

### TEST-UPDATE flow

Устаревший тест = отдельный тикет, никогда не inline-правка.

```
Обнаружен (decomposer | agent_green | ci)
   → TestUpdateTicket {slug}/tu-*.json  status: pending
   → Agent RED обновляет тест (НЕ GREEN)
   → review проверяет что правка обоснована, не обход
   → maintainer апрувит → status: approved → тест снова заморожен
```

GREEN никогда не инициирует изменение теста — только останавливается и создаёт тикет.

### ADR-CONFLICT flow

**Канон протокола: [ADR-CONFLICT.md](ADR-CONFLICT.md)** — все детали разрешения там. Здесь — карта.

Зеркало TEST-UPDATE: агент никогда не решает сам. Детект на 3 этапах: shape-doc (Requirements Review), build (self-review), review (check #3).

```
Противоречие с Accepted ADR
   → СТОП → вопрос человеку: ADR верен или устарел?
   ├─ ВЕРЕН   → переписать решение/spec под ADR (детали по этапу — в скилле)
   └─ УСТАРЕЛ → ESCALATE → AdrChangeTicket → maintainer апрувит → канон-протокол
```

### ADR: кандидат vs канон

| | `.ship/pipeline/{slug}/adr-entry-*.json` | `.ship/docs/adr/ADR-NNN-*.md` |
|---|---|---|
| Кто пишет | build (ADR Writer) | maintainer на Delivery |
| Статус | Proposed (кандидат) | Accepted / Expired |
| Формат | JSON | Markdown |
| Один файл = | одно решение, привязка к task | одно решение, сквозная нумерация |
| Промоушен | — | adr-entry → ADR-NNN.md на мёрже MR |

build только предлагает (`Proposed`). review валидирует. Промоушен в канон — `/spec-ship:adr-promote` (maintainer на Delivery).

Процедура промоушена (детали — в `adr-promote/SKILL.md`):
```
adr-entry-*.json (Proposed)
   │ ReviewReport APPROVED + adr_violations pass + MR апрувнут
   ▼ /spec-ship:adr-promote
   1. NNN = max в .ship/docs/adr/ + 1 (сквозной, Expired-номера не реюзаются)
   2. Area из files_ref (projection/importer/api/reports/shared)
   3. JSON → .ship/docs/adr/ADR-NNN-{kebab}.md (Accepted): decision→Decision,
      context→Context, consequences→Consequences, alternatives→Considered Options
   4. строка в .ship/docs/adr/INDEX.md (Accepted, Area)
   5. adr-entry → status: promoted, promoted_to: adr-NNN (остаётся в .ship/pipeline/)
```
Конфликт промоутимого решения с существующим Accepted ADR → не промоушен, а [ADR-CONFLICT flow](ADR-CONFLICT.md).

### Выборка ADR через INDEX

`.ship/docs/adr/INDEX.md` — таблица (ADR, Status, Area, decision, supersede). Скиллы читают только индекс → фильтр `Accepted` + пересечение `Area` с фичей → грузят тела ТОЛЬКО matched. Не читать все ADR подряд.

Рост корпуса сдержан: ADR редки by design + Expired выпадают из выборки + выборка по Area. 100 ADR → в контекст 1 индекс + 2-3 тела (~константа).

### Workflow-доки: второй канон (поведение)

Два вида долгоживущего знания, симметричные механики:

| | `.ship/docs/adr/` | `.ship/docs/workflows/` |
|---|---|---|
| Хранит | «почему решили так» | «как система себя ведёт» |
| Источник | adr-entry (build) | feature: survey + bd (после мёржа MR); backfill: только survey (заранее, из существующего кода) |
| Промоушен | `/spec-ship:adr-promote` | `/spec-ship:doc-promote-feature` (фича) · `/spec-ship:doc-backfill` (существующий код); оба → конвертер `doc-promote-internal` |
| Статусы | Accepted / Expired | current / partially-outdated / superseded |
| Потребитель | shape-doc, decompose, build, review | survey (вместо повторной трассировки) |
| Выборка | только через INDEX, по Area | только через INDEX, по Area |

**Разделение ответственности doc-promote** (механика vs политика запуска):

- `doc-promote-internal` — чистый конвертер: source-артефакты + Source-помета + create/amend → workflow-док + INDEX. Не знает «когда» и «откуда», не проверяет гейты. `user-invocable: false` + `disable-model-invocation: true` — напрямую не вызывается, только из обёрток. Стабильная механика в одном месте, без дублирования.
- `doc-promote-feature` — обёртка: гейт (ReviewReport APPROVED + MR смёржен), сбор survey+bd, вызов конвертера. «Когда» = после мёржа фичи.
- `doc-backfill` — обёртка: без гейта, выбор эталона + survey существующего кода, вызов конвертера с пометой `backfill`. «Когда» = заранее, для типовых паттернов.

Новый сценарий запуска (напр. промоушен по CI/расписанию) = новая обёртка; конвертер не трогается.

Пайплайн-артефакты в `.ship/pipeline/` остаются одноразовым аудит-следом; канон поведения накапливается в `.ship/docs/workflows/` — каждый следующий survey по той же области дешевле.

### Уведомления о точках участия человека

Доставка детерминированная — Stop-хук, не дисциплина LLM. Скиллы про уведомления не знают: сигналы читаются из статусов уже сохранённых артефактов.

```
Stop-хук (.claude/hooks/ship-notify.sh, регистрация в .claude/settings.json)
   → скан .ship/pipeline/**: draft bd / blocking без resolution / shape proposal /
     tu pending / adr-change pending / build escalation / review ESCALATE
   → дедуп через .claude/state/ship-notify-sent.json (1 уведомление на сигнал,
     снятый сигнал забывается)
   → транспорт из .ship/notify.yaml (gitignored; шаблон notify.yaml.dist)
```

Настройка: `cp .ship/notify.yaml.dist .ship/notify.yaml`, заполнить `telegram_chat_id`, токен — в env `SHIP_TELEGRAM_BOT_TOKEN` или `~/.config/ship-notify/telegram-token`, `enabled: true`. Фильтр событий — поле `events`. Без конфига хук молчит.

Не покрыто (интерактивные фазы, человек в сессии): апрув разбивки decompose до сохранения файлов, вопросы интервью shape-doc в моменте.

## Эскалации (сквозные)

| Триггер | Куда |
|---|---|
| RED не смог написать честный тест (`blocked`) | переклассификация в LOGIC: скелет `shape` (proposal, blocker → `open_for_developer`), дошейп интерфейса с Dev |
| GREEN не прошёл за N итераций | переклассификация в LOGIC: скелет `shape` (proposal, причина → `open_for_developer`), Dev |
| GREEN конфликт spec/тест | TestUpdateTicket, стоп |
| ADR-конфликт, человек сказал "устарел" | ESCALATE, AdrChangeTicket, стоп |
| review вернул ESCALATE | Dev с полным контекстом |

Лимит итераций GREEN `N` задаётся в одном месте — `ship-green` (frontmatter-логика). Остальные файлы ссылаются на `N` без числа.
