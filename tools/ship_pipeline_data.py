"""spec-ship pipeline data — читает .ship/pipeline/{slug}/*.json, собирает
задачи/статусы/покрытие в plain dict. Общая логика для ship-dashboard.py
(статичный HTML на одну фичу) и ship-server.py (live-сервер по всему проекту).

Артефакты различаются по полю "$schema" (pipeline/<type>[/vN]), а не по
имени файла — имена файлов не стандартизованы между слайсами.
"""
from __future__ import annotations
import json
from pathlib import Path


def schema_type(doc: dict) -> str | None:
    s = doc.get("$schema")
    if not s or not isinstance(s, str) or not s.startswith("pipeline/"):
        return None
    parts = s.split("/")
    return parts[1] if len(parts) > 1 else None


def load_pipeline(dir_path: Path) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {}
    for f in sorted(dir_path.glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(doc, dict):
            continue
        t = schema_type(doc)
        if t is None:
            continue
        doc["_file"] = f.name
        buckets.setdefault(t, []).append(doc)
    return buckets


def pick_root_doc(buckets: dict[str, list[dict]]) -> tuple[str, dict] | tuple[None, None]:
    """business-doc для фичи, diagnosis для бага. Ровно один ожидается."""
    if buckets.get("business-doc"):
        return "business-doc", buckets["business-doc"][0]
    if buckets.get("diagnosis"):
        return "diagnosis", buckets["diagnosis"][0]
    return None, None


def green_note(build: dict | None, task: dict) -> str:
    if build is None:
        return task.get("risk_reason") or ""
    tdd = build.get("tdd") or {}
    green = tdd.get("agent_green") or {}
    red = tdd.get("agent_red") or {}
    bits = []
    if green.get("status"):
        bits.append(f"green: {green['status']}, {green.get('iterations', '?')} итерация(й)")
    if red.get("status"):
        bits.append(f"red: {red['status']}, {red.get('iterations', '?')} итерация(й)")
    if build.get("escalation"):
        bits.append("⚠ escalation")
    adrs = build.get("adr_entries") or []
    if adrs:
        bits.append("adr: " + ", ".join(adrs))
    return " · ".join(bits) if bits else (task.get("risk_reason") or "")


def collect(buckets: dict[str, list[dict]]) -> dict:
    root_type, root = pick_root_doc(buckets)

    build_by_task = {b["task_spec_id"]: b for b in buckets.get("build-report", []) if b.get("task_spec_id")}
    review_by_task: dict[str, list[dict]] = {}
    for r in buckets.get("review-report", []):
        tid = r.get("task_spec_id")
        if tid:
            review_by_task.setdefault(tid, []).append(r)

    task_specs = sorted(buckets.get("task-spec", []), key=lambda t: t.get("id", ""))

    tasks = []
    for t in task_specs:
        build = build_by_task.get(t["id"])
        reviews = review_by_task.get(t["id"], [])
        validation = t.get("validation") or {}
        deps = (t.get("dependencies") or {})
        tasks.append({
            "id": t["id"],
            "title": t.get("title", ""),
            "tz": t.get("trust_zone", "ROUTINE"),
            "risk": validation.get("risk", "low"),
            "risk_reason": validation.get("risk_reason") or "",
            "depends_on": deps.get("depends_on") or [],
            "covers": validation.get("business_doc_coverage") or [],
            "built": build is not None,
            "reviewed": len(reviews) > 0,
            "review_verdicts": [r.get("verdict") or r.get("status") for r in reviews],
            "note": green_note(build, t),
        })

    task_by_id = {t["id"]: t for t in tasks}
    for t in tasks:
        t["status"] = "built" if t["built"] else (
            "blocked" if any(not task_by_id.get(d, {}).get("built") for d in t["depends_on"]) else "pending"
        )

    acceptance = []
    if root_type == "business-doc":
        for ac in (root.get("acceptance_criteria") or []):
            acceptance.append({
                "id": ac.get("id", ""),
                "scenario": ac.get("scenario", ""),
                "then": ac.get("then", "") or ac.get("expected", ""),
            })
    elif root_type == "diagnosis":
        defect = root.get("defect") or {}
        if defect:
            acceptance.append({
                "id": "defect",
                "scenario": "bug",
                "then": defect.get("expected", ""),
            })

    meta = {}
    if root:
        meta["id"] = root.get("id", "")
        meta["status"] = root.get("status", "")
        meta["created_at"] = root.get("created_at", "")
        feature = root.get("feature") or {}
        meta["title"] = feature.get("title") or root.get("id", "")
        meta["subtitle"] = feature.get("goal") or root.get("summary", "") or ""
        meta["open_questions"] = len(root.get("open_questions", []) or [])
        meta["root_type"] = root_type

    return {
        "meta": meta,
        "tasks": tasks,
        "acceptance": acceptance,
        "counts": {
            "adr_entries": len(buckets.get("adr-entry", [])),
            "test_update_tickets": len(buckets.get("test-update-ticket", [])),
            "surveys": len(buckets.get("survey", [])),
        },
    }


def list_pipelines(project: Path) -> list[dict]:
    """Лёгкий summary по каждой pipeline-папке — для списка на главной."""
    root = project / ".ship" / "pipeline"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name.startswith("."):
            continue
        buckets = load_pipeline(d)
        if not buckets:
            continue
        data = collect(buckets)
        meta = data["meta"]
        tasks = data["tasks"]
        if not meta and not tasks:
            continue
        out.append({
            "slug": d.name,
            "id": meta.get("id", d.name),
            "title": meta.get("title", d.name),
            "status": meta.get("status", "—"),
            "root_type": meta.get("root_type"),
            "created_at": meta.get("created_at", ""),
            "task_count": len(tasks),
            "built_count": sum(1 for t in tasks if t["built"]),
            "critical_count": sum(1 for t in tasks if t["tz"] == "CRITICAL"),
            "blocked_count": sum(1 for t in tasks if t["status"] == "blocked"),
        })
    out.sort(key=lambda p: p["created_at"], reverse=True)
    return out


def load_epic(dir_path: Path) -> dict | None:
    """MAP.json + все ticket-*.json одного эпика в .ship/roadmap/{epic}/."""
    map_path = dir_path / "MAP.json"
    if not map_path.is_file():
        return None
    try:
        map_doc = json.loads(map_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    tickets = []
    for f in sorted(dir_path.glob("ticket-*.json")):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        tickets.append(t)
    tickets.sort(key=lambda t: t.get("id", ""))

    by_id = {t["id"]: t for t in tickets if t.get("id")}
    out_tickets = []
    for t in tickets:
        deps = t.get("dependencies") or {}
        depends_on = deps.get("depends_on") or []
        status = t.get("status", "open")
        blocked = status == "open" and any(
            by_id.get(d, {}).get("status") != "closed" for d in depends_on
        )
        out_tickets.append({
            "id": t.get("id", ""),
            "title": t.get("title", ""),
            "type": t.get("type", ""),
            "hitl": t.get("hitl", False),
            "question": t.get("question", ""),
            "depends_on": depends_on,
            "blocks": deps.get("blocks") or [],
            "claimed_by": t.get("claimed_by"),
            "status": status,
            "resolution": t.get("resolution") or "",
            "outcome": t.get("outcome"),
            "resolved_at": t.get("resolved_at"),
            "blocked": blocked,
        })

    return {
        "epic": map_doc.get("epic", dir_path.name),
        "created_at": map_doc.get("created_at", ""),
        "created_by": map_doc.get("created_by", ""),
        "destination": map_doc.get("destination", ""),
        "notes": map_doc.get("notes") or {},
        "decisions_so_far": map_doc.get("decisions_so_far") or [],
        "not_yet_specified": map_doc.get("not_yet_specified") or [],
        "out_of_scope": map_doc.get("out_of_scope") or [],
        "tickets": out_tickets,
    }


def list_epics(project: Path) -> list[dict]:
    """Лёгкий summary по каждому эпику roadmap — для списка на главной."""
    root = project / ".ship" / "roadmap"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name.startswith("."):
            continue
        epic = load_epic(d)
        if not epic:
            continue
        tickets = epic["tickets"]
        out.append({
            "slug": d.name,
            "epic": epic["epic"],
            "destination": epic["destination"],
            "created_at": epic["created_at"],
            "ticket_count": len(tickets),
            "closed_count": sum(1 for t in tickets if t["status"] == "closed"),
            "hitl_open_count": sum(1 for t in tickets if t["status"] == "open" and t["hitl"]),
            "ready_for_run_count": sum(1 for t in tickets if t["outcome"] == "ready_for_run"),
            "not_yet_specified_count": len(epic["not_yet_specified"]),
        })
    out.sort(key=lambda e: e["created_at"], reverse=True)
    return out
