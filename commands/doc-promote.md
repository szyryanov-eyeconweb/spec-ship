---
description: Delivery — промоутнуть знание о поведении из survey/bd в канон .ship/docs/workflows/ + INDEX
---

Используй скилл `doc-promote` для промоушена знания о поведении системы в долгоживущие workflow-доки.

Скилл находится в `.claude/skills/spec-ship/doc-promote/SKILL.md` — прочитай его и следуй инструкциям точно. Источники: `survey-*.json` + `bd-*.json` (+ `shape` из task) из `.ship/pipeline/{slug}/`. Результат: `.ship/docs/workflows/<area>-*.md` + строка в `.ship/docs/workflows/INDEX.md`. Предусловия: ReviewReport APPROVED, MR смёржен. Задетые чужие документы пометить partially-outdated/superseded — ничто не лжёт молча.

$ARGUMENTS
