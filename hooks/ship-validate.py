#!/usr/bin/env python3
"""spec-ship schema validator — энфорсмент правил артефактов.

Правила схем (обязательные поля, `[]` вместо опущенного списка, «ровно одно
из value/value_ref», `mr_ready` только при APPROVED) до этого держались
добровольно: скилл просил, агент мог тихо нарушить. Хук делает их барьером —
как ship-guard.sh делает барьером изоляцию прав.

Два режима:

    ship-validate.py --hook          PostToolUse: читает JSON харнесса со stdin,
                                     валидирует записанный артефакт, при провале
                                     возвращает ошибку агенту (он правит сам)

    ship-validate.py [путь ...]      CLI: проверить артефакты руками.
                                     Без аргументов — все .ship/pipeline/**/*.json.
                                     Выход 0 = чисто, 1 = есть провалы.

Только stdlib. Схема определяется по полю `$schema` артефакта; неизвестная
схема — не ошибка (пайплайн растёт, валидатор не должен блокировать новое).

ГРАНИЦЫ: проверяются структурные инварианты, не смысл. «Каждый файл в
files_evidence имеет причину» проверяемо (поле непусто), «причина осмысленна» —
нет, это работа review. Валидатор ловит тихое нарушение формы, не халтуру.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# ── Схемы ────────────────────────────────────────────────────────────────────
# required: поля, без которых артефакт неполон.
# lists:    поля-списки, которые обязаны присутствовать (пустой = [], не опущен).
# Вложенность через точку: "spec.files_to_change".

SCHEMAS: dict[str, dict] = {
    "pipeline/survey": {
        "required": ["id", "anchor"],
        "lists": ["observed_workflows", "connected_groups", "validation_boundaries",
                  "adr_refs", "empty_groups_checked"],
    },
    "pipeline/business-doc": {
        "required": ["id", "status", "feature"],
        "lists": ["acceptance_criteria", "data", "open_questions"],
    },
    "pipeline/task-spec": {
        "required": ["id", "title", "trust_zone", "spec"],
        "lists": ["data", "test_scenarios", "adr_refs"],
    },
    "pipeline/test-update-ticket": {
        "required": ["id", "detected_by", "conflict", "resolution"],
        "lists": [],
    },
    "pipeline/build-report": {
        "required": ["id", "task_spec_id", "trust_zone"],
        "lists": ["files_changed", "adr_entries"],
    },
    "pipeline/review-report": {
        "required": ["id", "build_report_id", "task_spec_id", "verdict", "checklist"],
        "lists": ["issues"],
    },
    "pipeline/adr-entry": {
        "required": ["id", "status", "decision"],
        "lists": ["alternatives"],
    },
    "pipeline/diagnosis": {
        "required": ["id", "survey_id", "defect", "repro_test", "approval"],
        "lists": ["hypotheses", "tasks_produced", "adr_refs"],
    },
}

TRUST_ZONES = {"ROUTINE", "LOGIC", "CRITICAL"}
VERDICTS = {"APPROVED", "NEEDS_WORK", "ESCALATE"}
REVIEW_CHECKS = ["spec_coverage", "test_scenarios_covered", "adr_violations",
                 "regressions", "performance", "regression_guard"]


def _get(obj: dict, dotted: str):
    """Достать вложенное поле по "a.b.c". Отсутствие → KeyError-сентинел None."""
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _present(obj: dict, dotted: str) -> bool:
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


# ── Проверки ─────────────────────────────────────────────────────────────────

def check_common(art: dict, schema_id: str, errors: list[str]) -> None:
    spec = SCHEMAS[schema_id]

    for field in spec["required"]:
        val = _get(art, field)
        if not _present(art, field) or val is None or val == "":
            errors.append(f"нет обязательного поля `{field}`")

    for field in spec["lists"]:
        if not _present(art, field):
            errors.append(
                f"поле-список `{field}` отсутствует — пустой список пишется как "
                f"[], это значит «проверено, пусто» (CANON.md)"
            )
        elif not isinstance(_get(art, field), list):
            errors.append(f"поле `{field}` должно быть списком")


def check_data_layer(art: dict, errors: list[str], base: Path) -> None:
    """data[]: ровно одно из value/value_ref; при value_ref — дескриптор полон."""
    data = art.get("data")
    if not isinstance(data, list):
        return

    for i, rec in enumerate(data):
        if not isinstance(rec, dict):
            errors.append(f"data[{i}] не объект")
            continue

        where = f"data[{i}] ({rec.get('id', '?')})"
        has_value = rec.get("value") is not None
        ref = rec.get("value_ref")
        has_ref = isinstance(ref, dict) and ref

        if has_value and has_ref:
            errors.append(f"{where}: заполнены и `value`, и `value_ref` — "
                          f"ровно одно из двух")
        if not has_value and not has_ref:
            errors.append(f"{where}: не заполнено ни `value`, ни `value_ref` — "
                          f"«около 5%» это open_question, не data-запись")

        if not has_ref:
            continue

        for f in ("path", "shape", "checksum"):
            if not ref.get(f):
                errors.append(f"{where}.value_ref: нет `{f}` — дескриптор без "
                              f"него не контракт (checksum делает точность "
                              f"проверяемой, а не доверенной)")

        path, checksum = ref.get("path"), ref.get("checksum")
        if not (path and checksum):
            continue

        f = base / path if not Path(path).is_absolute() else Path(path)
        if not f.exists():
            errors.append(f"{where}.value_ref: файл `{path}` не найден")
            continue
        if not checksum.startswith("sha256:"):
            errors.append(f"{where}.value_ref.checksum: ожидается "
                          f"`sha256:<хеш>`, получено `{checksum}`")
            continue
        actual = hashlib.sha256(f.read_bytes()).hexdigest()
        if actual != checksum.split(":", 1)[1].strip():
            errors.append(
                f"{where}.value_ref: checksum НЕ совпадает с файлом `{path}` — "
                f"данные изменены после заморозки (ожидалось {checksum[7:19]}…, "
                f"фактически sha256:{actual[:12]}…)"
            )


def check_task_spec(art: dict, errors: list[str]) -> None:
    tz = art.get("trust_zone")
    if tz and tz not in TRUST_ZONES:
        errors.append(f"trust_zone `{tz}` — допустимы {sorted(TRUST_ZONES)}")

    # Источник: фича из bd, баг из Diagnosis. Ровно один.
    bd, diag = art.get("business_doc_id"), art.get("diagnosis_id")
    if not bd and not diag:
        errors.append("нет ни `business_doc_id`, ни `diagnosis_id` — TaskSpec "
                      "приходит либо из BusinessDoc, либо из Diagnosis")
    if bd and diag:
        errors.append("заполнены и `business_doc_id`, и `diagnosis_id` — "
                      "ровно одно из двух")

    # test_seam непустой ⟺ test_scenarios непустой.
    scen = art.get("test_scenarios")
    seam = _get(art, "spec.test_seam")
    if isinstance(scen, list):
        if scen and not seam:
            errors.append("есть test_scenarios, но `spec.test_seam` пуст — "
                          "seam контракт для RED, не догадка (decompose 2.5)")
        if not scen and seam:
            errors.append("test_scenarios: [], но `spec.test_seam` заполнен — "
                          "тестировать нечего, seam должен быть null")
        if diag and not scen:
            errors.append("задача из bug_fix с пустым test_scenarios — "
                          "репро-сценарий обязателен (regression guard)")

    if seam and isinstance(seam, dict):
        if seam.get("existing") and not seam.get("prior_art"):
            errors.append("test_seam.existing: true без `prior_art` — "
                          "существующий seam называется путём к тесту")

    # LOGIC ⟺ непустой shape (proposal); ROUTINE/CRITICAL → null.
    shape = art.get("shape")
    if tz == "LOGIC" and not shape:
        errors.append("trust_zone LOGIC без `shape` — нужен скелет со "
                      "status: proposal (decompose 3)")
    if tz in ("ROUTINE", "CRITICAL") and shape:
        errors.append(f"trust_zone {tz} с непустым `shape` — должен быть null")
    if isinstance(shape, dict):
        st = shape.get("status")
        if st not in ("proposal", "approved"):
            errors.append(f"shape.status `{st}` — допустимы proposal/approved")
        if st == "approved" and not shape.get("approved_by"):
            errors.append("shape.status approved без `approved_by` — "
                          "апрув шейпа делает человек")

    fan = art.get("fan_out")
    if isinstance(fan, dict) and fan.get("enabled"):
        if tz == "CRITICAL":
            errors.append("fan_out при trust_zone CRITICAL запрещён "
                          "(decompose 3.5)")
        layers = fan.get("layers") or []
        seen: dict[str, int] = {}
        for li, layer in enumerate(layers):
            for p in layer.get("files_to_change", []):
                if p in seen:
                    errors.append(
                        f"fan_out: путь `{p}` в двух слоях "
                        f"({seen[p]} и {li}) — files_to_change слоёв не "
                        f"пересекаются (инвариант 1)"
                    )
                seen[p] = li
        for group in ("contract_paths", "shared_paths"):
            for p in fan.get(group) or []:
                if p in seen:
                    errors.append(f"fan_out: `{p}` и в `{group}`, и в "
                                  f"layer.files_to_change (инвариант 2/3)")


def check_review_report(art: dict, errors: list[str]) -> None:
    verdict = art.get("verdict")
    if verdict and verdict not in VERDICTS:
        errors.append(f"verdict `{verdict}` — допустимы {sorted(VERDICTS)}")

    checklist = art.get("checklist")
    if isinstance(checklist, dict):
        for key in REVIEW_CHECKS:
            if key not in checklist:
                errors.append(f"checklist: нет ключа `{key}` — все проверки "
                              f"присутствуют всегда (n/a пишется pass: true)")
        failed = [k for k, v in checklist.items()
                  if isinstance(v, dict) and v.get("pass") is False]
        if verdict == "APPROVED" and failed:
            errors.append(f"verdict APPROVED, но провалены проверки: "
                          f"{', '.join(sorted(failed))}")
        for k in failed:
            if not checklist[k].get("notes"):
                errors.append(f"checklist.{k}: pass false без `notes` — "
                              f"провал называет file:line")

    issues = art.get("issues")
    if isinstance(issues, list):
        if verdict == "APPROVED" and issues:
            errors.append("verdict APPROVED с непустым `issues[]`")
        if verdict in ("NEEDS_WORK", "ESCALATE") and not issues:
            errors.append(f"verdict {verdict} с пустым `issues[]`")

    if art.get("mr_ready") and verdict != "APPROVED":
        errors.append(f"mr_ready: true при verdict {verdict} — гейт MR "
                      f"открывается только на APPROVED")

    esc = art.get("escalation")
    if verdict == "ESCALATE" and not esc:
        errors.append("verdict ESCALATE без `escalation`")
    if verdict != "ESCALATE" and esc:
        errors.append(f"`escalation` заполнено при verdict {verdict} — "
                      f"должно быть null")


def check_diagnosis(art: dict, errors: list[str]) -> None:
    if not _get(art, "repro_test.was_red"):
        errors.append("repro_test.was_red не true — репро-тест пишется ДО "
                      "анализа корня; диагноз без красного теста это гипотеза")

    if _get(art, "defect.expected_source") in (None, "", "none"):
        errors.append("defect.expected_source пуст или `none` — гейт «баг или "
                      "намеренное поведение?» разрешается до артефакта")

    hyps = art.get("hypotheses")
    if isinstance(hyps, list):
        if not hyps:
            errors.append("hypotheses: [] — корень находится опровержением, "
                          "гипотезы это аудит-след")
        confirmed = [h for h in hyps if isinstance(h, dict)
                     and h.get("verdict") == "confirmed"]
        if len(confirmed) > 1:
            errors.append(f"подтверждённых гипотез {len(confirmed)} — корень "
                          f"один: ровно одна confirmed, объясняющая весь симптом")
        for i, h in enumerate(hyps):
            if not isinstance(h, dict):
                continue
            if not (h.get("evidence_for") or h.get("evidence_against")):
                errors.append(f"hypotheses[{i}]: нет ни `evidence_for`, ни "
                              f"`evidence_against` — «похоже, дело в кеше» "
                              f"не гипотеза")

    root, tasks = art.get("root_cause"), art.get("tasks_produced")
    if isinstance(tasks, list) and tasks:
        if not root:
            errors.append("есть `tasks_produced`, но `root_cause` пуст — "
                          "корень не найден → эскалация, не задача")
        elif root.get("explains_full_symptom") is not True:
            errors.append("root_cause.explains_full_symptom не true при "
                          "непустом tasks_produced — чинить неполностью "
                          "объяснённый симптом = чинить симптом")

    br = art.get("blast_radius")
    if isinstance(br, dict):
        for i, c in enumerate(br.get("callers") or []):
            if not isinstance(c, dict):
                continue
            if not c.get("reason"):
                errors.append(f"blast_radius.callers[{i}]: нет `reason` — "
                              f"broken:false тоже обосновывается")
            if c.get("broken") and not c.get("covered_by_task"):
                errors.append(
                    f"blast_radius.callers[{i}] ({c.get('symbol', '?')}): "
                    f"broken:true без `covered_by_task` — сломанный сосед "
                    f"либо покрыт задачей, либо имеет свою; молчаливый "
                    f"пропуск запрещён"
                )

    if art.get("approval", {}).get("status") != "approved":
        errors.append("approval.status не `approved` — диагноз без апрува "
                      "человека не сохраняется (неверный корень дороже всего "
                      "дальше по цепочке)")


def check_survey(art: dict, errors: list[str]) -> None:
    for group in ("to_change", "read_only"):
        files = _get(art, f"files_evidence.{group}")
        if files is None:
            errors.append(f"нет `files_evidence.{group}`")
            continue
        for i, rec in enumerate(files if isinstance(files, list) else []):
            if isinstance(rec, dict) and not rec.get("reason"):
                errors.append(
                    f"files_evidence.{group}[{i}] ({rec.get('path', '?')}): "
                    f"нет `reason` — «найден грепом» не причина, причина это "
                    f"роль файла в связанной группе"
                )
    for i, g in enumerate(art.get("connected_groups") or []):
        if not isinstance(g, dict):
            continue
        for f in ("why_connected", "risk_if_skipped"):
            if not g.get(f):
                errors.append(f"connected_groups[{i}] ({g.get('group', '?')}): "
                              f"нет `{f}`")


def check_business_doc(art: dict, errors: list[str]) -> None:
    st = art.get("status")
    if st not in ("draft", "approved", "frozen"):
        errors.append(f"status `{st}` — допустимы draft/approved/frozen")
    if st == "frozen":
        blocking = [q for q in art.get("open_questions") or []
                    if isinstance(q, dict) and q.get("severity") == "blocking"
                    and not q.get("resolution")]
        if blocking:
            errors.append(f"status frozen при {len(blocking)} нерешённых "
                          f"blocking-вопросах")


VALIDATORS = {
    "pipeline/survey": check_survey,
    "pipeline/business-doc": check_business_doc,
    "pipeline/task-spec": check_task_spec,
    "pipeline/review-report": check_review_report,
    "pipeline/diagnosis": check_diagnosis,
}


def validate(path: Path, base: Path) -> list[str]:
    """Вернуть список ошибок. Пустой список = артефакт валиден."""
    try:
        art = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"невалидный JSON: {e}"]
    except OSError as e:
        return [f"не прочитать файл: {e}"]

    if not isinstance(art, dict):
        return ["артефакт должен быть объектом"]

    schema_id = art.get("$schema")
    if not schema_id:
        return ["нет поля `$schema` — метка схемы обязательна (skills/README.md)"]
    if schema_id not in SCHEMAS:
        return []  # неизвестная схема — пайплайн растёт, не блокировать

    errors: list[str] = []
    check_common(art, schema_id, errors)
    check_data_layer(art, errors, base)
    if fn := VALIDATORS.get(schema_id):
        fn(art, errors)
    return errors


# ── Режим хука ───────────────────────────────────────────────────────────────

def run_hook() -> int:
    """PostToolUse: провал → additionalContext агенту, он правит сам.

    При любой неоднозначности (не наш путь, нет stdin, не распарсилось) —
    молчать: хук не мешает легитимной работе.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0

    raw = (payload.get("tool_input") or {}).get("file_path")
    if not raw:
        return 0

    path = Path(raw)
    parts = path.parts
    if ".ship" not in parts or "pipeline" not in parts or path.suffix != ".json":
        return 0
    if not path.exists():
        return 0

    root = Path(payload.get("cwd") or ".")
    errors = validate(path, root)
    if not errors:
        return 0

    listing = "\n".join(f"  - {e}" for e in errors)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"spec-ship: артефакт {path.name} нарушает схему "
                f"({len(errors)}):\n{listing}\n\n"
                f"Исправь файл — правила схемы это контракт этапа, а не "
                f"пожелание. Схема поля — в SCHEMA.md рядом со SKILL.md "
                f"этапа, сквозные законы — в skills/CANON.md."
            ),
        }
    }))
    return 0


def run_cli(args: list[str]) -> int:
    root = Path.cwd()
    if args:
        targets = [Path(a) for a in args]
    else:
        targets = sorted((root / ".ship" / "pipeline").rglob("*.json"))
        if not targets:
            print("нет артефактов в .ship/pipeline/")
            return 0

    failed = 0
    for path in targets:
        errors = validate(path, root)
        if errors:
            failed += 1
            print(f"\n✗ {path}")
            for e in errors:
                print(f"    {e}")

    total = len(targets)
    if failed:
        print(f"\n{failed} из {total} артефактов нарушают схему")
        return 1
    print(f"✓ {total} артефакт(ов), схемы соблюдены")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    sys.exit(run_hook() if "--hook" in argv else run_cli(argv))
