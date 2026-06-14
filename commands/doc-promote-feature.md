---
description: Delivery — промоутнуть поведение смёрженной фичи в канон .ship/docs/workflows/ (гейт APPROVED + MR)
---

Используй скилл `doc-promote-feature` для промоушена поведения смёрженной фичи в долгоживущие workflow-доки.

Скилл находится в `.claude/skills/spec-ship/doc-promote-feature/SKILL.md` — прочитай его и следуй инструкциям точно. Проверь гейт (ReviewReport APPROVED + MR смёржен), собери `survey-*.json` + `bd-*.json` (+ `shape` из task) из `.ship/pipeline/{slug}/` и передай внутреннему конвертеру `doc-promote-internal`. Результат: `.ship/docs/workflows/<area>-*.md` + строка в INDEX. Задетые чужие документы пометить partially-outdated/superseded — ничто не лжёт молча.

$ARGUMENTS