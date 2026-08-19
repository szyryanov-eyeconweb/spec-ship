---
description: Баг-ветка — от симптома до корня, выдать Diagnosis + TaskSpec (заменяет shape-doc + decompose)
---

Используй скилл `bug-fix` для диагностики бага: от симптома до корня, с оценкой радиуса поражения.

Скилл находится в `.claude/skills/spec-ship/bug-fix/SKILL.md` — прочитай его и следуй инструкциям точно. Вызови `survey` сам (на баге он обязателен), затем репро-тест через `ship-red` ДО анализа корня. Сохрани Diagnosis и TaskSpec в `.ship/pipeline/{slug}/` строго по схемам. Код не пишешь: фикс собирает `build` по TaskSpec.

$ARGUMENTS
