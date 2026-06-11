---
name: adr-promote
description: Промоутит кандидата ADREntry (.ship/pipeline/{slug}/adr-entry-*.json, Proposed) в канон .ship/docs/adr/ADR-NNN-*.md (Accepted) и обновляет INDEX. Выполняется maintainer'ом на Delivery после апрува MR. Использовать когда BuildReport содержит adr_entries и ReviewReport дал APPROVED, или когда пользователь говорит "promote adr", "промоутни adr", "merge adr в канон".
---

# Ship ADR Promote

Конвертит кандидата `ADREntry v1` (JSON, `Proposed`) в канонический ADR markdown (`Accepted`) и регистрирует в `.ship/docs/adr/INDEX.md`.

Это ручной шаг maintainer'а на Delivery — НЕ автономный. Агент исполняет конвертацию, человек инициирует и апрувит.

## Предусловия

Промоушен допустим ТОЛЬКО когда всё верно:
- [ ] `ReviewReport.verdict == "APPROVED"` для задачи (adr-entry прошёл валидацию)
- [ ] `ReviewReport.checklist.adr_violations.pass == true`
- [ ] MR апрувнут maintainer'ом (Delivery)

Если любое не выполнено — НЕ промоутить, surface причину.

## Процесс

### 1. Найти кандидатов

Прочитать `BuildReport.adr_entries[]` — список id кандидатов. Для каждого загрузить `.ship/pipeline/{slug}/adr-entry-<id>.json`.

Если `adr_entries: []` — нечего промоутить, сообщить и выйти.

### 2. Определить номер NNN

`NNN = max номер в .ship/docs/adr/ + 1`. Сканировать `.ship/docs/adr/ADR-*.md` и `.ship/docs/adr/INDEX.md`. Сквозная нумерация, номера Expired не переиспользуются.

### 3. Вывести Area

Определить `Area` из `adr-entry.files_ref[]` по feature-based структуре (ADR-001):
- путь `src/Projection/...` → `projection` (+ подобласть, напр. `projection/wallet`)
- `src/Importer/...` → `importer`
- `src/Api/...` → `api`
- `src/Reports/...` → `reports`
- `src/Shared/...` → `shared`
- затрагивает структуру/несколько фич → `architecture` или `all`

Если неоднозначно — спросить maintainer.

### 4. Конвертировать JSON → markdown

Создать `.ship/docs/adr/ADR-<NNN>-<kebab>.md`, где `kebab` = краткое kebab-резюме `decision`.

Маппинг полей:

| adr-entry JSON | ADR markdown |
|---|---|
| `decision` | `# ADR-NNN: <title>` (заголовок) + раздел `## Decision` |
| `context` | `## Context` |
| `consequences[]` | `## Consequences` (список) |
| `alternatives_considered[]` | `## Considered Options` (список) |
| `files_ref[]` | inline-ссылки в Decision/Consequences |
| `task_spec_id` | поле `**Task:**` |
| (из business_doc) | поле `**BD:**` |

Шаблон (формат как ADR-001):
```markdown
# ADR-<NNN>: <Заголовок решения>

**Status:** Accepted
**Date:** <ISO-date>
**Author:** <maintainer>
**BD:** <business_doc_id>
**Task:** <task_spec_id>

---

## Context

<context>

## Decision

<decision>

## Consequences

- <consequence 1>
- <consequence 2>

## Considered Options

- <alternative 1>
- <alternative 2>
```

Опциональные разделы (Status frontmatter, Considered Options, Consequences) включать только если в adr-entry есть данные — пустые не плодить.

### 5. Зарегистрировать в INDEX

Добавить строку в таблицу `.ship/docs/adr/INDEX.md`:
```
| <NNN> | Accepted | <area> | <decision кратко> | — |
```

Убрать соответствующую строку из секции "Кандидаты" в INDEX (кандидат стал каноном).

### 6. Пометить кандидата promoted

В `.ship/pipeline/{slug}/adr-entry-*.json` выставить `status: "promoted"` + `promoted_to: "adr-<NNN>"`. Файл не удалять — след трассируемости.

### 7. Подтвердить

Показать: путь нового `ADR-NNN-*.md`, обновлённую строку INDEX, какой adr-entry промоутнут.

## Правила

- НЕ промоутить без APPROVED + апрува MR. Это гейт maintainer'а.
- NNN сквозной, Expired-номера не переиспользуются.
- Один adr-entry → один ADR-NNN. Несколько кандидатов в BuildReport → несколько ADR с инкрементом NNN.
- При конфликте промоутимого решения с существующим Accepted ADR → это не промоушен, а [ADR-CONFLICT flow](../ADR-CONFLICT.md).
- adr-entry после промоушена остаётся в `.ship/pipeline/` со `status: promoted` — для истории.