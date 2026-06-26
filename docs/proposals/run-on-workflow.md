# Гибрид `run`: spec-ship-политика на Workflow-механизме

> Статус: **прототип / proposal**. Дизайн того, как `run`-оркестратор лёг бы на
> нативный Claude Code `Workflow` вместо проза-оркестрации через модель.
> Цель — токены+скорость Workflow при точности spec-ship (гейты, trust_zone,
> TDD-изоляция, канон).

## Принцип разделения

| Слой | Кто | Где живёт |
|---|---|---|
| **Механизм** оркестрации (fan-out, pipeline, resume, конкуренция) | Workflow JS-скрипт | этот файл |
| **Политика** (trust_zone-роутинг, гейты человека, TDD-изоляция, канон) | spec-ship | skills + промпты агентов |

Workflow гонит ТОЛЬКО автономную часть: ROUTINE-задачи и LOGIC c уже
`approved`-шейпом. На каждом гейте человека (LOGIC без шейпа, CRITICAL, blocked,
escalate, ADR-конфликт) скрипт НЕ решает сам — он `return`-ит дескриптор гейта.
Главная сессия дёргает человека (`AskUserQuestion`/шейп-сессия), пишет результат
в артефакт, и резюмит скрипт (`resumeFromRunId`) — уже-сделанное из кэша,
дошейпленная задача гонится живьём.

## Почему гейт = выход из скрипта, а не внутри

Workflow — fire-and-forget в фоне, человека в середине дёргать не может. Гейты
spec-ship — это и есть «решения человека», единственное место, где экономить
нельзя. Поэтому: автономный сегмент → Workflow; гейт → возврат в сессию; следующий
автономный сегмент → resume. Граница сегмента = граница гейта.

## Карта на примитивы

| spec-ship проза | Workflow примитив |
|---|---|
| Phase B fan-out по слоям | `parallel(layers.map(...))` + `isolation:'worktree'` |
| ROUTINE RED→GREEN | `pipeline([task], redStage, greenStage)` |
| независимые задачи катятся, пока LOGIC ждёт | топосорт → `parallel` по готовому фронту |
| `run --resume` из `.ship/pipeline/{slug}/` | `resumeFromRunId` (журнал agent()-ов) |
| ship-red / ship-green изоляция правами | `agentType:'ship-red'/'ship-green'` |
| NEEDS_WORK→build→review ≤2 | цикл `while` в стадии review |

## Прототип скрипта

```javascript
export const meta = {
  name: 'spec-ship-run',
  description: 'Гибрид-оркестратор spec-ship на Workflow: автономный сегмент (ROUTINE + approved-LOGIC) гонится параллельно по depends_on-фронтам и fan-out-слоям; гейты человека возвращаются в сессию для resume',
  phases: [
    { title: 'Plan',    detail: 'топосорт задач, разнести на автономные / гейт' },
    { title: 'Build',   detail: 'pipeline RED→GREEN; fan-out слои в parallel+worktree' },
    { title: 'Review',  detail: 'review каждого build; NEEDS_WORK чинится ≤2' },
  ],
}

// args = { slug, tasks: TaskSpec[] }  — читает decompose-артефакты заранее, в скрипт уже как JSON
const { slug, tasks } = args
const byId = new Map(tasks.map(t => [t.id, t]))

// --- гейт: задача требует человека ДО автономной работы ---
const needsHumanGate = (t) =>
  (t.trust_zone === 'LOGIC' && t.shape?.status !== 'approved') ||  // шейп-сессия
  (t.trust_zone === 'CRITICAL')                                     // Dev пишет сам

const gated = tasks.filter(needsHumanGate)
const autonomous = tasks.filter(t => !needsHumanGate(t))

// Если автономного фронта нет вовсе — сразу вернуть гейты, гонять нечего
if (!autonomous.length) {
  return { kind: 'GATE', reason: 'no-autonomous-front', gates: gated.map(gateOf) }
}

phase('Plan')
log(`${autonomous.length} автономных, ${gated.length} на гейте человека`)

// --- топосорт: автономную задачу нельзя строить раньше её depends_on ---
// depends_on на gated-задачу = тоже барьер (её сначала разберёт человек)
const ready = (t, done) =>
  (t.dependencies?.depends_on ?? []).every(d => done.has(d))

phase('Build')
const done = new Set()        // id успешно собранных
const builtReports = []
let remaining = [...autonomous]
let stuck = []

while (remaining.length) {
  const front = remaining.filter(t => ready(t, done))
  if (!front.length) { stuck = remaining; break }  // упёрлись в gated-зависимость

  // весь готовый фронт — параллельно
  const reports = await parallel(front.map(t => () => buildTask(t)))

  front.forEach((t, i) => {
    const r = reports[i]
    if (r && r.outcome === 'done') { done.add(t.id); builtReports.push(r) }
    else stuck.push({ task: t, report: r })   // blocked/escalated/conflict → гейт
  })
  remaining = remaining.filter(t => !done.has(t.id) && !stuck.find(s => s.task?.id === t.id))
}

// --- build одной задачи: fan-out или прямой RED→GREEN ---
async function buildTask(t) {
  if (t.fan_out?.enabled) return buildFanOut(t)
  return buildLinear(t)
}

// прямой трек: RED все тесты → GREEN
async function buildLinear(t) {
  const red = await agent(redPrompt(t), {
    agentType: 'ship-red', phase: 'Build', label: `red:${t.id}`, schema: RED_SCHEMA,
  })
  if (red?.status !== 'done') return { task: t.id, outcome: 'blocked', detail: red }
  const green = await agent(greenPrompt(t, red), {
    agentType: 'ship-green', phase: 'Build', label: `green:${t.id}`, schema: GREEN_SCHEMA,
  })
  return { task: t.id, outcome: green?.status === 'done' ? 'done' : green?.status, report: green }
}

// fan-out: Phase A контракт (1 агент, контракт-only) → A.5 RED все тесты →
//          B слои в parallel+worktree → C интеграция
async function buildFanOut(t) {
  // Phase A — контракт (порты+DTO), пишет только contract_paths
  const contract = await agent(contractPrompt(t), {
    agentType: 'ship-green', phase: 'Build', label: `contract:${t.id}`, schema: CONTRACT_SCHEMA,
  })
  if (contract?.status !== 'done') return { task: t.id, outcome: 'blocked', detail: contract }

  // Phase A.5 — RED все тесты задачи (сквозное поведение)
  const red = await agent(redPrompt(t), {
    agentType: 'ship-red', phase: 'Build', label: `red:${t.id}`, schema: RED_SCHEMA,
  })
  if (red?.status !== 'done') return { task: t.id, outcome: 'blocked', detail: red }

  // Phase B — слои параллельно, каждый в своём worktree (непересекающиеся пути)
  const layers = await parallel(t.fan_out.layers.map(layer => () =>
    agent(layerPrompt(t, layer, contract), {
      agentType: 'ship-green', phase: 'Build', label: `green:${t.id}:${layer.role}`,
      isolation: 'worktree', schema: GREEN_SCHEMA,
    }).then(r => ({ role: layer.role, ...r }))
  ))

  // незрелый контракт: слой сообщил «порту/DTO не хватает X» → стоп фан-аута, гейт в Phase A
  const immature = layers.find(l => l?.status === 'immature-contract')
  if (immature) return { task: t.id, outcome: 'immature-contract', detail: immature }

  // Phase C — интеграция (полный suite по объединению слоёв)
  const integ = await agent(integrationPrompt(t, layers), {
    agentType: 'ship-green', phase: 'Build', label: `integ:${t.id}`, schema: GREEN_SCHEMA,
  })
  return { task: t.id, outcome: integ?.status === 'done' ? 'done' : integ?.status, report: integ, layers }
}

// --- Review с авто-починкой ≤2 ---
phase('Review')
const reviewed = await pipeline(
  builtReports,
  r => reviewWithFixLoop(byId.get(r.task), r),
)

async function reviewWithFixLoop(t, buildReport) {
  let attempt = 0, report = buildReport
  while (attempt < 3) {                       // 1 review + ≤2 починки
    const rev = await agent(reviewPrompt(t, report), {
      agentType: 'code-reviewer', phase: 'Review', label: `review:${t.id}`, schema: REVIEW_SCHEMA,
    })
    if (rev?.verdict === 'APPROVED') return { task: t.id, verdict: 'APPROVED' }
    if (rev?.verdict === 'ESCALATE')  return { task: t.id, verdict: 'ESCALATE', detail: rev }
    // NEEDS_WORK → агент чинит, повторное review
    report = await agent(fixPrompt(t, rev), {
      agentType: 'ship-green', phase: 'Review', label: `fix:${t.id}`, schema: GREEN_SCHEMA,
    })
    attempt++
  }
  return { task: t.id, verdict: 'ESCALATE', detail: 'fix-loop-exhausted' }
}

// --- Итог: что готово, что на гейте человека ---
return {
  kind: 'SEGMENT_DONE',
  slug,
  approved: reviewed.filter(r => r?.verdict === 'APPROVED').map(r => r.task),
  escalated: reviewed.filter(r => r?.verdict === 'ESCALATE'),
  gates: [
    ...gated.map(gateOf),                                  // LOGIC-шейп / CRITICAL
    ...stuck.map(s => ({ task: s.task?.id, ...gateOf2(s) })), // blocked/escalated/conflict/immature
  ],
}

function gateOf(t) {
  if (t.trust_zone === 'LOGIC')    return { task: t.id, gate: 'shape-session', need: 'зашейпить алгоритм, shape.status→approved' }
  if (t.trust_zone === 'CRITICAL') return { task: t.id, gate: 'critical-dev', need: 'Dev пишет код сам, консультация' }
  return { task: t.id, gate: 'unknown' }
}
function gateOf2(s) {
  const o = s.report?.outcome ?? s.report?.status
  if (o === 'blocked')           return { gate: 'red-blocked',  need: 'RED не смог честный тест → переклассифицировать в LOGIC, дошейп интерфейса' }
  if (o === 'escalated')         return { gate: 'green-escalated', need: 'GREEN не сошёлся за N → переклассифицировать в LOGIC' }
  if (o === 'conflict')          return { gate: 'test-conflict', need: 'GREEN хочет править тест → TestUpdateTicket, решение человека' }
  if (o === 'immature-contract') return { gate: 'phase-a-reshape', need: 'контракт неполон → дополнить contract_paths в Phase A, рестарт fan-out' }
  return { gate: 'review-escalate', need: 'разобрать ReviewReport' }
}
```

## Жизненный цикл с гейтами (главная сессия)

```
1. главная сессия: decompose уже дал tasks[] → Workflow({script, args:{slug, tasks}})
2. скрипт катит автономный фронт, возвращает { kind:'SEGMENT_DONE', approved, gates }
3. сессия: для каждого gate — AskUserQuestion / шейп-сессия с человеком
4. сессия: пишет shape.status='approved' (или переклассификацию) в task-*.json
5. сессия: Workflow({scriptPath, args:{slug, tasks: <обновлённые>}, resumeFromRunId})
   → сделанное из кэша, дошейпленная задача теперь автономна → катится
6. повтор 2-5 пока gates пуст
7. сессия: финальная сводка (как run шаг 7)
```

Резюме идемпотентно: тот же (prompt, opts) у agent() → кэш-хит. Меняется только
дошейпленная задача (её prompt теперь несёт approved-shape) → она и всё после неё
гонится живьём.

## Что выигрывает vs проза-`run`

- **Токены**: оркестрация в JS = ~0 токенов на поток; главная сессия плоская,
  тяжесть в эфемерных субагентах (вывод не оседает в сессии).
- **Скорость**: `parallel` по фронту depends_on + по fan-out-слоям = реальная
  конкуренция (cap ~min(16,cores-2)), не сериализованная через модель проза.
- **Точность сохранена**: гейты не растворились — стали границами сегментов,
  человек на них так же дёргается. TDD-изоляция — через `agentType`. Канон —
  внутри промптов агентов (contractPrompt берёт паттерн-док).

## Что НЕ переносится в скрипт (остаётся политикой spec-ship)

- Тексты промптов (redPrompt/greenPrompt/...) — несут trust_zone-контекст, канон,
  test_scenarios. Скрипт их только собирает из TaskSpec, не сочиняет.
- Решение decompose про `trust_zone` и `fan_out` — до Workflow.
- Гейтовые диалоги — `AskUserQuestion` в главной сессии, не в скрипте.

## Открытые вопросы

1. **Схемы** (RED_SCHEMA/GREEN_SCHEMA/...) — вывести из BuildReport v1, чтобы
   `agent({schema})` валидировал исход на tool-слое (модель ретраит при mismatch).
2. **worktree-мёрж**: Phase B-слои в отдельных worktree → Phase C нужен их свод
   в одно дерево. Кто мёржит — интеграционный агент или скрипт-хук? (worktree
   авто-удаляется если не тронут; тронутый — надо собрать.)
3. **Стоимость рестарта fan-out** при immature-contract: resume гонит Phase A
   заново + все слои. Принять как цену, или кэшировать «здоровые» слои?
4. Гейт-диалог можно ли частично автоматизировать флагами `--auto-shape` /
   `--auto-decompose` как в прозе-`run` — да, но решает их главная сессия ДО
   запуска скрипта (фильтр needsHumanGate учитывает флаги).
```
```

## Вердикт

Прототип закрывает все три оси: механизм от Workflow (токены+скорость), политику
от spec-ship (точность). Не «или-или» — слои. Перед реализацией решить открытые
вопросы 1-3 (схемы, worktree-мёрж, цена рестарта).
