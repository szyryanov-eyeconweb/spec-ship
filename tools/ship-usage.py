#!/usr/bin/env python3
"""spec-ship usage meter — агрегирует токены Claude Code по стадиям пайплайна.

Читает JSONL-транскрипты (~/.claude/projects/<proj>/**), считает usage
раздельно (input / output / cache_write / cache_read), режет по стадии,
модели, trust_zone. Отдельно — основная сессия vs сабагенты (Г1 брифа).
Печатает базу сравнения для оптимизации пайплайна (задача 1 брифа).

Запуск:
    tools/ship-usage.py                      # проект = cwd, все сессии
    tools/ship-usage.py --project /path
    tools/ship-usage.py --since 2026-07-20   # ISO-дата
    tools/ship-usage.py --json
    tools/ship-usage.py --sessions           # разбивка по сессиям

Только stdlib. Данные транскриптов машину не покидают.

СТРУКТУРА ФАЙЛОВ (проверено на живых транскриптах):
    ~/.claude/projects/<proj-slug>/
      <session>.jsonl                             ← родитель (основная сессия)
      <session>/subagents/agent-<id>.jsonl        ← сабагент, isSidechain=true
      <session>/subagents/workflows/wf_*/agent-*.jsonl
  Тип сабагента — в поле верхнего уровня `attributionAgent`
  ("ship-red" / "ship-green" / "ship-review" / прочие). Атрибуция сабагентов
  по нему ТОЧНАЯ, не эвристика.

ГРАНИЦЫ АТРИБУЦИИ:
  * Сабагенты → стадия по `attributionAgent` (ship-red→build:red,
    ship-green→build:green, ship-review→review). Надёжно.
  * Стадии основной сессии (survey/shape-doc/decompose/build-оркестрация/
    run) → по Skill-вызову или по имени артефакта в .ship/pipeline/.
    Приблизительно: turn'ы между двумя маркерами относятся к первому.
    Границы стадий в общей сессии размыты by design (Г1) — потому и дробим.
  * trust_zone → из TaskSpec/артефакта, попавшего в контекст turn'а;
    иначе "unknown".
  Неатрибутированное основной сессии → "main/other": сам её объём есть
  метрика веса нешардированного дирижёра (Г1).
"""
from __future__ import annotations
import argparse, json, os, re, sys
from collections import defaultdict
from pathlib import Path

# поля usage — проверены на живых записях
USAGE_FIELDS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_write": "cache_creation_input_tokens",
    "cache_read": "cache_read_input_tokens",
}

# attributionAgent сабагента -> стадия
AGENT_STAGE = {"ship-red": "build:red", "ship-green": "build:green",
               "ship-review": "review", "ship-decompose": "decompose"}

# skill -> стадия основной сессии
SKILL_STAGE = {
    "spec-ship:survey": "survey", "survey": "survey",
    "spec-ship:shape-doc": "shape-doc", "shape-doc": "shape-doc",
    "spec-ship:decompose": "decompose", "decompose": "decompose",
    "spec-ship:build": "build:orchestrate", "build": "build:orchestrate",
    "spec-ship:review": "review", "review": "review",
    "spec-ship:run": "run", "run": "run",
    "spec-ship:roadmap": "roadmap", "roadmap": "roadmap",
}

# артефакт в pipeline -> стадия (fallback-маркер, если Skill не назван)
ARTIFACT_STAGE = [
    (re.compile(r"survey-.*\.json"), "survey"),
    (re.compile(r"bd-.*\.json"), "shape-doc"),
    (re.compile(r"task-.*\.json"), "decompose"),
    (re.compile(r"build-.*\.json"), "build:orchestrate"),
    (re.compile(r"review-.*\.json"), "review"),
]

TRUST_RE = re.compile(r'"trust_zone"\s*:\s*"(ROUTINE|LOGIC|CRITICAL)"')

SIDECHAIN_STAGES = set(AGENT_STAGE.values()) | {"subagent/other"}


def zero():
    return {k: 0 for k in USAGE_FIELDS} | {"turns": 0}


def add_usage(acc, usage):
    for out, src in USAGE_FIELDS.items():
        acc[out] += usage.get(src, 0) or 0
    acc["turns"] += 1


def iter_records(path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # битая строка — пропустить, не падать


def tool_uses(rec):
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                yield b


def new_agg():
    return defaultdict(lambda: defaultdict(lambda: defaultdict(zero)))


def analyze_parent(path, agg, since=None):
    """Родительский транскрипт: стадии основной сессии по маркерам."""
    cur_stage = "main/other"
    cur_trust = "unknown"
    for rec in iter_records(path):
        ts = rec.get("timestamp", "")
        if since and ts and ts < since:
            continue
        if rec.get("type") in ("assistant", "user"):
            m = TRUST_RE.search(json.dumps(rec.get("message", {}),
                                           ensure_ascii=False))
            if m:
                cur_trust = m.group(1)
        if rec.get("type") == "assistant":
            for tu in tool_uses(rec):
                name, inp = tu.get("name", ""), (tu.get("input") or {})
                if name == "Skill":
                    sk = (inp.get("skill") or inp.get("command") or "")
                    sk = sk.split()[0] if sk else ""
                    if sk in SKILL_STAGE:
                        cur_stage = SKILL_STAGE[sk]
                elif name in ("Write", "Edit", "MultiEdit"):
                    fp = str(inp.get("file_path", ""))
                    if ".ship/pipeline/" in fp:
                        for rx, stg in ARTIFACT_STAGE:
                            if rx.search(fp):
                                cur_stage = stg
                                break
            usage = (rec.get("message") or {}).get("usage")
            if usage:
                model = (rec.get("message") or {}).get("model", "unknown")
                add_usage(agg[cur_stage][model][cur_trust], usage)


def analyze_subagent(path, agg, since=None):
    """Файл сабагента: стадия по attributionAgent, весь usage файла — ей."""
    stage = None
    trust = "unknown"
    for rec in iter_records(path):
        if stage is None:
            aa = rec.get("attributionAgent")
            if isinstance(aa, str):
                stage = AGENT_STAGE.get(aa, "subagent/other")
        ts = rec.get("timestamp", "")
        if since and ts and ts < since:
            continue
        if rec.get("type") in ("assistant", "user"):
            m = TRUST_RE.search(json.dumps(rec.get("message", {}),
                                           ensure_ascii=False))
            if m:
                trust = m.group(1)
        if rec.get("type") == "assistant":
            usage = (rec.get("message") or {}).get("usage")
            if usage:
                model = (rec.get("message") or {}).get("model", "unknown")
                add_usage(agg[stage or "subagent/other"][model][trust], usage)


def merge(dst, src):
    for stage, models in src.items():
        for model, trusts in models.items():
            for trust, u in trusts.items():
                d = dst[stage][model][trust]
                for k in u:
                    d[k] += u[k]


def flatten(agg):
    return [{"stage": s, "model": m, "trust_zone": t, **u}
            for s, models in agg.items()
            for m, trusts in models.items()
            for t, u in trusts.items()]


def total(u):
    return u["input"] + u["output"] + u["cache_write"] + u["cache_read"]


def cache_hit_ratio(u):
    denom = u["cache_read"] + u["input"] + u["cache_write"]
    return u["cache_read"] / denom if denom else 0.0


def print_table(rows):
    if not rows:
        print("Нет данных spec-ship в транскриптах "
              "(или --since отсёк всё).", file=sys.stderr)
        return
    by_stage = defaultdict(zero)
    for r in rows:
        for k in list(USAGE_FIELDS) + ["turns"]:
            by_stage[r["stage"]][k] += r[k]
    grand = sum(total(u) for u in by_stage.values()) or 1

    hdr = (f'{"стадия":<20}{"всего":>13}{"%":>5}{"in":>11}{"out":>10}'
           f'{"c_write":>11}{"c_read":>12}{"cache%":>8}{"turns":>7}')
    print(hdr); print("-" * len(hdr))
    for stage in sorted(by_stage, key=lambda s: -total(by_stage[s])):
        u = by_stage[stage]; t = total(u)
        print(f'{stage:<20}{t:>13,}{100*t/grand:>4.0f}%{u["input"]:>11,}'
              f'{u["output"]:>10,}{u["cache_write"]:>11,}{u["cache_read"]:>12,}'
              f'{cache_hit_ratio(u):>7.0%}{u["turns"]:>7,}')
    print("-" * len(hdr))
    print(f'{"ИТОГО":<20}{grand:>13,}')

    side = sum(total(by_stage[s]) for s in by_stage if s in SIDECHAIN_STAGES)
    main = grand - side
    print(f'\nОсновная сессия/оркестрация vs сабагенты (Г1):')
    print(f'  основная сессия: {main:>13,} ({100*main/grand:.0f}%)')
    print(f'  сабагенты:       {side:>13,} ({100*side/grand:.0f}%)')

    # разбивка по trust_zone — где живёт расход (для решения «что дробить»)
    by_trust = defaultdict(zero)
    for r in rows:
        for k in list(USAGE_FIELDS) + ["turns"]:
            by_trust[r["trust_zone"]][k] += r[k]
    print("\nПо trust_zone:")
    for tz in sorted(by_trust, key=lambda z: -total(by_trust[z])):
        u = by_trust[tz]
        print(f'  {tz:<10}{total(u):>13,} ({100*total(u)/grand:.0f}%)')

    print('\n[!] Стадии основной сессии — эвристика по маркерам; сабагенты — '
          'точно по attributionAgent. См. docstring.')


def collect(proj_dir, since):
    agg = new_agg()
    parents = sorted(proj_dir.glob("*.jsonl"))
    subs = sorted(proj_dir.glob("*/subagents/**/agent-*.jsonl"))
    for f in parents:
        analyze_parent(f, agg, since)
    for f in subs:
        analyze_subagent(f, agg, since)
    return agg, len(parents), len(subs)


def main():
    ap = argparse.ArgumentParser(description="spec-ship usage meter")
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--projects-dir",
                    default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument("--since")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sessions", action="store_true")
    args = ap.parse_args()

    slug = str(Path(args.project).resolve()).replace("/", "-")
    proj_dir = Path(args.projects_dir) / slug
    if not proj_dir.is_dir():
        print(f"Папка транскриптов не найдена: {proj_dir}", file=sys.stderr)
        sys.exit(1)

    agg, n_par, n_sub = collect(proj_dir, args.since)
    rows = flatten(agg)

    if args.json:
        out = {"project": args.project, "parents": n_par,
               "subagents": n_sub, "rows": rows}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print(f"Проект: {args.project}   родит.сессий: {n_par}   "
          f"сабагент-файлов: {n_sub}"
          + (f"   since: {args.since}" if args.since else "") + "\n")
    print_table(rows)

    if args.sessions:
        print("\n=== по сессиям (родитель + его сабагенты) ===")
        for pf in sorted(proj_dir.glob("*.jsonl")):
            sess = new_agg()
            analyze_parent(pf, sess, args.since)
            for sf in sorted((proj_dir / pf.stem).glob(
                    "subagents/**/agent-*.jsonl")):
                analyze_subagent(sf, sess, args.since)
            tot = sum(total(r) for r in flatten(sess))
            if tot:
                print(f"  {pf.stem}: {tot:,}")


if __name__ == "__main__":
    main()
