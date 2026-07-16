# ADR-CONFLICT Flow

Сквозной протокол. Применяется в `shape-doc`, `build`, `review` — везде, где обнаружено противоречие между новым решением/spec и существующим ADR в `.ship/docs/adr/`.

Зеркало TEST-UPDATE flow: агент НИКОГДА не решает сам, верен ADR или устарел. Останавливается → спрашивает человека → действует по ответу.

---

## Триггер

Реализация, spec или BusinessDoc противоречит уже принятому (`Status: Accepted`) ADR.

## Шаг 1 — СТОП и вопрос человеку

Не продолжать. Сформулировать конкретно:

```
Противоречие с {ADR-NNN}: "{краткая суть ADR}".
Новое решение/требование: "{что хочет фича}".
Вопрос: ADR-NNN всё ещё ВЕРЕН или УСТАРЕЛ?
```

Ждать явного ответа. Два исхода.

---

## Исход A — ADR ВЕРЕН (код/решение виноваты)

Существующее решение в силе. Виновато новое.

1. Переписать решение/spec в соответствии с ADR.
2. ADR не трогать.
3. Контекст этапа:
   - **shape-doc** → переформулировать AC/constraints под ADR, очистить `conflicts[]` после правки.
   - **build** → GREEN переписывает реализацию под ADR. Если требует пересмотра подхода и не лезет в N → escalate LOGIC.
   - **review** → `NEEDS_WORK`, issue severity blocking "противоречит ADR-NNN, переписать под него".
4. Продолжить пайплайн нормально.

---

## Исход B — ADR УСТАРЕЛ (решение виновато)

ADR обоснованно требует пересмотра.

1. **ESCALATE.** Этап останавливается (как GREEN при конфликте теста).
2. Создать `AdrChangeTicket` → `.ship/pipeline/{slug}/adr-change-*.json`, `resolution.status: pending`.
3. После апрува maintainer'а выполнить ДВЕ операции:

   **a) Пометить старый ADR Expired.**
   В `.ship/docs/adr/ADR-NNN-*.md`:
   ```
   **Status:** Expired
   **Superseded by:** ADR-MMM
   **Expired:** <date>
   ```
   Файл НЕ удалять — иммутабельная история.

   **b) Написать новый ADR.**
   `.ship/docs/adr/ADR-MMM-{kebab}.md` (MMM = max номер + 1), `Status: Accepted`, с секцией `Supersedes: ADR-NNN`.

   **c) Обновить `.ship/docs/adr/INDEX.md`.**
   Старый ADR-NNN: `Status: Accepted` → `Expired`, в колонке supersede проставить `→ superseded by ADR-MMM`.
   Добавить строку ADR-MMM: `Status: Accepted`, область, `Supersedes ADR-NNN`.

4. **Перестать ссылаться на старый ADR.** Убрать `adr-NNN` из всех `adr_refs[]` в текущих и будущих артефактах. Заменить на `adr-MMM`. Expired ADR не появляется в новых `adr_refs`.

5. Возобновить пайплайн с новым ADR в силе.

---

## Правила

- Агент НИКОГДА не помечает ADR Expired сам — только после явного ответа человека "устарел" + апрува тикета.
- Expired ADR — иммутабелен, файл остаётся для истории, только статус меняется.
- Новый ADR обязан иметь `Supersedes: ADR-NNN`, старый — `Superseded by: ADR-MMM`. Двусторонняя ссылка.
- После Expired — ноль ссылок в новых `adr_refs`. Grep `adr-NNN` не должен возвращать живых ссылок.
- Сквозная нумерация ADR не переиспользуется (номер Expired не освобождается).

---

## AdrChangeTicket Schema

```jsonc
{
  "$schema": "pipeline/adr-change-ticket",
  "id": "adr-change-0042-01",
  "detected_by": "review",        // shape-doc | build | review
  "detected_at": "<ISO8601>",
  "task_spec_id": "task-0042-03",       // или null если detected на shape-doc
  "business_doc_id": "bd-2026-0042",

  "conflict": {
    "adr_ref": "adr-007",
    "adr_statement": "<что утверждает старый ADR>",
    "new_requirement": "<что требует новое решение>",
    "where": "<file:line | bd-id | task-id>"
  },

  "human_verdict": {
    "status": "pending",                // pending | adr_valid | adr_expired
    "answered_by": null,
    "answered_at": null,
    "reasoning": null
  },

  "resolution": {
    // если adr_valid:
    "rewrite_action": null,             // "<как переписать решение под ADR>"
    // если adr_expired:
    "expired_adr": null,                // "adr-007"
    "new_adr_id": null,                 // "adr-015"
    "new_adr_decision": null,           // "<кратко новое решение>"
    "approved_by": null,
    "approved_at": null
  }
}
```