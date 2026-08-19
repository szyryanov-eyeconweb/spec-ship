#!/usr/bin/env python3
"""Самопроверка ship-validate.py. Запуск: tools/test_ship_validate.py

Каждый кейс: артефакт → ожидаем, что нарушение поймано (или что чистый прошёл).
Без фреймворков — assert и один прогон.
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from importlib import import_module

v = import_module("ship-validate")


def check(art: dict, expect: str | None, label: str, files: dict | None = None):
    """expect=подстрока ожидаемой ошибки; None = ожидаем чистый артефакт."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        for rel, content in (files or {}).items():
            f = base / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content)
        p = base / "artifact.json"
        p.write_text(json.dumps(art))
        errors = v.validate(p, base)

    if expect is None:
        assert not errors, f"{label}: ожидался чистый, получено {errors}"
    else:
        assert any(expect in e for e in errors), \
            f"{label}: ожидалась ошибка ~{expect!r}, получено {errors}"
    print(f"  ok  {label}")


def task(**over) -> dict:
    art = {
        "$schema": "pipeline/task-spec",
        "id": "task-0001-01", "business_doc_id": "bd-2026-0001",
        "diagnosis_id": None, "title": "T", "trust_zone": "ROUTINE",
        "spec": {"description": "d", "test_seam": {"level": "unit", "entry": "E",
                                                   "existing": False},
                 "files_to_change": ["src/A.php"], "files_read_only": []},
        "shape": None, "fan_out": None, "data": [],
        "test_scenarios": [{"id": "ts-1", "scenario": "happy"}],
        "adr_refs": [], "dependencies": {"depends_on": [], "blocks": []},
        "validation": {"business_doc_coverage": ["ac-1"], "risk": "low"},
    }
    art.update(over)
    return art


def review(**over) -> dict:
    art = {
        "$schema": "pipeline/review-report", "id": "review-0001-01",
        "build_report_id": "build-0001-01", "task_spec_id": "task-0001-01",
        "verdict": "APPROVED",
        "checklist": {k: {"pass": True, "notes": None} for k in v.REVIEW_CHECKS},
        "issues": [], "escalation": None, "mr_ready": True,
    }
    art.update(over)
    return art


def diag(**over) -> dict:
    art = {
        "$schema": "pipeline/diagnosis", "id": "diag-2026-0001",
        "survey_id": "survey-2026-0001",
        "defect": {"symptom": "s", "repro": "r", "expected": "e",
                   "expected_source": "adr-007"},
        "repro_test": {"path": "tests/T.php", "was_red": True},
        "hypotheses": [{"id": "h-1", "verdict": "confirmed",
                        "evidence_for": ["src/A.php:1"]}],
        "root_cause": {"hypothesis_id": "h-1", "explains_full_symptom": True},
        "blast_radius": {"callers": [], "fix_point": "src/A.php#m"},
        "data_corruption": None, "tasks_produced": ["task-0001-01"],
        "adr_refs": [], "approval": {"status": "approved", "approved_by": "dev:x"},
    }
    art.update(over)
    return art


print("common")
check({"id": "x"}, "$schema", "нет $schema")
check({"$schema": "pipeline/unknown-thing", "junk": 1}, None,
      "неизвестная схема не блокирует")
omitted = task()
del omitted["test_scenarios"]
check(omitted, "отсутствует", "опущенный список ловится")
check(task(test_scenarios=None), "должно быть списком", "null вместо списка")
check(task(), None, "валидный TaskSpec")

print("data-слой")
big = "1,USD,0.05\n2,EUR,0.04\n"
h = hashlib.sha256(big.encode()).hexdigest()
ok_ref = {"path": "data/m.csv", "shape": "2×3", "sample": ["1,USD,0.05"],
          "checksum": f"sha256:{h}"}
check(task(data=[{"id": "d-1", "value": None, "value_ref": ok_ref}]), None,
      "value_ref с верным checksum", {"data/m.csv": big})
check(task(data=[{"id": "d-1", "value": 5, "value_ref": ok_ref}]),
      "ровно одно из двух", "value и value_ref вместе", {"data/m.csv": big})
check(task(data=[{"id": "d-1", "value": None, "value_ref": None}]),
      "не заполнено ни", "пустая data-запись")
check(task(data=[{"id": "d-1", "value_ref": ok_ref}]),
      "НЕ совпадает", "изменённый файл ловится checksum",
      {"data/m.csv": big + "3,KRW,0.03\n"})
check(task(data=[{"id": "d-1", "value_ref": {**ok_ref, "checksum": None}}]),
      "нет `checksum`", "дескриптор без checksum", {"data/m.csv": big})
check(task(data=[{"id": "d-1", "value_ref": ok_ref}]),
      "не найден", "пропавший файл")

print("TaskSpec")
check(task(trust_zone="MAGIC"), "trust_zone", "неизвестная зона")
check(task(business_doc_id=None), "ни `business_doc_id`", "нет источника")
check(task(diagnosis_id="diag-1"), "ровно одно из двух", "bd и diag вместе")
check(task(trust_zone="LOGIC"), "LOGIC без `shape`", "LOGIC без шейпа")
check(task(shape={"status": "proposal"}), "с непустым `shape`",
      "ROUTINE с шейпом")
check(task(trust_zone="LOGIC", shape={"status": "approved"}),
      "без `approved_by`", "approved без апрувера")
check(task(test_scenarios=[], spec={**task()["spec"], "test_seam": None}), None,
      "пустые сценарии + null seam")
check(task(test_scenarios=[]), "seam должен быть null", "нет сценариев, есть seam")
check(task(business_doc_id=None, diagnosis_id="diag-1", test_scenarios=[],
           spec={**task()["spec"], "test_seam": None}),
      "репро-сценарий обязателен", "баг без репро-сценария")
check(task(trust_zone="CRITICAL", fan_out={"enabled": True, "layers": []}),
      "CRITICAL запрещён", "fan_out на CRITICAL")
check(task(fan_out={"enabled": True, "contract_paths": [], "shared_paths": [],
                    "layers": [{"role": "entry", "files_to_change": ["a.php"]},
                               {"role": "application",
                                "files_to_change": ["a.php"]}]}),
      "в двух слоях", "пересечение слоёв fan_out")

print("ReviewReport")
check(review(), None, "валидный APPROVED")
check(review(mr_ready=True, verdict="NEEDS_WORK",
             issues=[{"severity": "blocking"}]),
      "mr_ready", "mr_ready при NEEDS_WORK")
bad = {k: {"pass": True, "notes": None} for k in v.REVIEW_CHECKS}
bad["regressions"] = {"pass": False, "notes": "src/A.php:10"}
check(review(checklist=bad), "провалены проверки", "APPROVED с провалом")
check(review(checklist={k: {"pass": True} for k in v.REVIEW_CHECKS[:5]}),
      "regression_guard", "нет ключа шестой проверки")
check(review(verdict="ESCALATE", mr_ready=False, issues=[{"severity": "blocking"}]),
      "без `escalation`", "ESCALATE без блока эскалации")

print("Diagnosis")
check(diag(), None, "валидный Diagnosis")
check(diag(repro_test={"path": "t", "was_red": False}), "was_red",
      "диагноз без красного теста")
check(diag(defect={"symptom": "s", "repro": "r", "expected": "e",
                   "expected_source": "none"}),
      "expected_source", "нет источника ожидания")
check(diag(root_cause=None), "root_cause` пуст", "задачи без корня")
check(diag(root_cause={"hypothesis_id": "h-1", "explains_full_symptom": False}),
      "explains_full_symptom", "частично объяснённый симптом")
check(diag(hypotheses=[{"id": "h-1", "verdict": "confirmed"},
                       {"id": "h-2", "verdict": "confirmed"}]),
      "Подтверждённых гипотез".lower()[:12], "два корня")
check(diag(hypotheses=[{"id": "h-1", "verdict": "unresolved"}], root_cause=None,
           tasks_produced=[]),
      "не гипотеза", "гипотеза без доказательств")
check(diag(blast_radius={"callers": [{"symbol": "src/B.php#m", "broken": True,
                                      "reason": "тот же корень"}]}),
      "covered_by_task", "сломанный сосед без задачи")
check(diag(approval={"status": "pending"}), "approval", "диагноз без апрува")

print("BusinessDoc")
check({"$schema": "pipeline/business-doc", "id": "bd-1", "status": "frozen",
       "feature": {"title": "T"}, "acceptance_criteria": [], "data": [],
       "open_questions": [{"severity": "blocking", "resolution": None}]},
      "frozen при", "заморозка с blocking-вопросом")

print("Survey")
check({"$schema": "pipeline/survey", "id": "s-1", "anchor": {"entrypoint": "E"},
       "observed_workflows": [], "connected_groups": [],
       "validation_boundaries": [], "adr_refs": [], "empty_groups_checked": [],
       "files_evidence": {"to_change": [{"path": "a.php"}], "read_only": []}},
      "нет `reason`", "файл без причины")

print("\n✓ все кейсы прошли")
