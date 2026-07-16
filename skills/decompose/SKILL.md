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

### 2.5. Выбрать test seam каждого слайса

Каждому слайсу назначить `spec.test_seam` — уровень, на котором RED будет его тестировать. Не оставлять RED угадывать: неявный seam всплывает как `blocked: no_seam` в середине build. Три правила (в порядке приоритета):

1. **Существующий seam предпочтительнее нового.** Смотреть prior art: `files_evidence` survey и существующие `tests/` той области — как уже тестируется соседний код. Тестировать через ту же границу.
2. **Высший возможный уровень.** Не тестировать глубоко внутри, если поведение слайса наблюдаемо с края (use-case harness / API / публичный сервис). Глубокий unit-тест внутренностей переживает рефактор хуже.
3. **Минимум seam'ов.** Идеально один на слайс — совпадает с `spec.interface`. Несколько seam на слайс — сигнал, что слайс режется неправильно.

`test_seam` = где act теста входит в систему: конкретный тип теста (`unit`/`functional`/`use-case-harness`) + точка входа (класс/метод/эндпоинт из `spec.interface`). Формальный маппинг `tests/unit` (логика) / `tests/functional` (I/O) — минимум; seam уточняет ГДЕ именно, а не только тип. Если существующего seam нет и высший разумный уровень неочевиден — это сигнал LOGIC (дошейп seam с Dev), не догадка RED.

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

Скан тестов в `tests/` на сценарии, конфликтующие с новым spec. Каждый такой конфликт выносится из TaskSpec в отдельный `TestUpdateTicket` JSON — `.ship/pipeline/{slug}/tu-*.json`.

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

## Схема выхода

Перед шагом 6 (сохранением артефактов) открыть полные схемы TaskSpec и TestUpdateTicket + правила их полей — [SCHEMA.md](SCHEMA.md).

## Правила

- Decompose только режет и классифицирует — исходные файлы не меняет. Единственная запись — артефакты в `.ship/pipeline/{slug}/`.
- Правила полей артефактов (`trust_zone`, `test_seam`, `shape`, `fan_out`, `data`) — в [SCHEMA.md](SCHEMA.md), не дублируются здесь.
- Сквозные законы (сохранить ВСЕ файлы до отчёта, `[]` не опускать, состояния из `CONTEXT.md`, выборка ADR через INDEX) — [CANON.md](../CANON.md).