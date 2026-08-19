#!/usr/bin/env python3
"""spec-ship report — сводка времени и токенов по одному прогону (session_id).

Джойнит ship-timer.json (время) + ship-tokens.json (токены) по session_id и
agent_id — обе метрики уже агрегированы хуками по этим ключам на диске, здесь
только чтение и форматирование, ни один транскрипт заново не парсится.

    ship-report.py                  последняя сессия (по mtime state-файла)
    ship-report.py <session_id>     конкретная сессия
    ship-report.py --json [id]      сырой JSON вместо таблицы

Ищет state-файлы в .claude/state/ относительно CLAUDE_PROJECT_DIR (или cwd).
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def pick_session(timer: dict, tokens: dict, session_id: str | None) -> str | None:
    if session_id:
        return session_id
    ids = set(timer) | set(tokens)
    if not ids:
        return None
    # последняя по вставке в любой из файлов — jq/bash пишут в конец объекта,
    # порядок ключей python сохраняет как есть при чтении JSON.
    return list(ids)[-1]


def fmt_secs(s: int) -> str:
    m, s = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def fmt_tokens(t: dict) -> str:
    inp = t.get("input", 0)
    out = t.get("output", 0)
    cr = t.get("cache_read", 0)
    cc = t.get("cache_creation", 0)
    return f"in={inp} out={out} cache_read={cr} cache_creation={cc}"


def build_report(timer: dict, tokens: dict, session_id: str) -> dict:
    t_sess = timer.get(session_id, {})
    k_sess = tokens.get(session_id, {})

    agent_ids = set(t_sess.get("subagents", {})) | set(k_sess.get("subagents", {}))
    subagents = []
    for aid in agent_ids:
        t_sub = t_sess.get("subagents", {}).get(aid, {})
        k_sub = k_sess.get("subagents", {}).get(aid, {})
        subagents.append({
            "agent_id": aid,
            "agent_type": t_sub.get("agent_type") or k_sub.get("agent_type") or "unknown",
            "seconds": t_sub.get("total", 0),
            "running": t_sub.get("started") is not None,
            "tokens": k_sub.get("tokens", {}),
        })
    subagents.sort(key=lambda a: -a["seconds"])

    main_tokens = k_sess.get("tokens", {})
    sub_tokens_sum = {
        k: sum(a["tokens"].get(k, 0) for a in subagents)
        for k in ("input", "output", "cache_read", "cache_creation")
    }
    total_tokens = {
        k: main_tokens.get(k, 0) + sub_tokens_sum[k]
        for k in ("input", "output", "cache_read", "cache_creation")
    }

    return {
        "session_id": session_id,
        "main": {
            "seconds": t_sess.get("total_active", 0),
            "running": t_sess.get("active_since") is not None,
            "tokens": main_tokens,
        },
        "subagents": subagents,
        # main.seconds УЖЕ покрывает время сабагентов (см. ship-timer.sh) —
        # не складывать с суммой subagents.*.seconds, будет задвоение.
        "wall_clock_seconds": t_sess.get("total_active", 0),
        # токены сабагента и родителя — разные API-запросы, не пересекаются.
        "total_tokens": total_tokens,
    }


def print_table(report: dict) -> None:
    print(f"session {report['session_id']}")
    print(f"  wall-clock: {fmt_secs(report['wall_clock_seconds'])}"
          f"{' (в процессе)' if report['main']['running'] else ''}")
    print(f"  main tokens: {fmt_tokens(report['main']['tokens'])}")
    if report["subagents"]:
        print("  subagents:")
        for a in report["subagents"]:
            flag = " (в процессе)" if a["running"] else ""
            print(f"    {a['agent_type']:<20} {fmt_secs(a['seconds']):>10}{flag}"
                  f"   {fmt_tokens(a['tokens'])}")
    print(f"  TOTAL tokens (main+subagents): {fmt_tokens(report['total_tokens'])}")


def main() -> int:
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    session_id = args[0] if args else None

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
    timer = load(root / ".claude/state/ship-timer.json")
    tokens = load(root / ".claude/state/ship-tokens.json")

    sid = pick_session(timer, tokens, session_id)
    if sid is None:
        print("нет данных: .claude/state/ship-timer.json и ship-tokens.json пусты", file=sys.stderr)
        return 1

    report = build_report(timer, tokens, sid)
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_table(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
