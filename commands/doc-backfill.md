---
description: Наполнить канон .ship/docs/workflows/ поведением существующего кода (без фичи и MR-гейта)
---

Используй скилл `doc-backfill` для наполнения workflow-канона поведением уже написанного кода — заранее, для типовых паттернов.

Скилл находится в `.claude/skills/spec-ship/doc-backfill/SKILL.md` — прочитай его и следуй инструкциям точно. Выбери эталонный символ паттерна, получи по нему `survey-*.json` (при необходимости запусти `survey`), реши уровень документа (паттерн или экземпляр) и передай survey внутреннему конвертеру `doc-promote-internal` с пометой `backfill (<survey-id>)`. Гейт APPROVED/MR НЕ применяется. Результат: `.ship/docs/workflows/<area>-*.md` + строка в INDEX.

$ARGUMENTS