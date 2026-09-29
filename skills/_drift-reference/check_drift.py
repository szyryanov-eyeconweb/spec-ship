#!/usr/bin/env python3
# owner: szyryanov
# tier: stable
#
# Drift-чекер канона spec-ship. Сверяет .ship/docs/ (workflow-доки + ADR) с кодом
# по claims.yaml. Контракт — в claims.yaml (схема + семантика exit/skip).
# Реализация ниже на stdlib Python; агент на другом языке регенерирует из контракта.
#
# Usage:
#   python3 .ship/docs/check_drift.py [--source-root DIR]
#   DRIFT_SOURCE_ROOT=DIR python3 .ship/docs/check_drift.py
# Exit 1 при любом FAIL. Отсутствующий source-файл -> SKIP (не fail) — канон не
# блокирует ветки, где соответствующего кода ещё нет.

import os
import re
import sys

DOCS_ROOT = os.path.dirname(os.path.abspath(__file__))           # .ship/docs
REPO_ROOT = os.path.normpath(os.path.join(DOCS_ROOT, "..", ".."))  # корень analytics


def parse_claims(path):
    """Мини-парсер плоского claims.yaml (stdlib-only, без зависимостей)."""
    claims = []
    cur = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.strip().startswith("#") or not line.strip():
                continue
            if line.startswith("- "):
                if cur:
                    claims.append(cur)
                cur = {}
                line = "  " + line[2:]
            if cur is None:
                continue
            m = re.match(r"\s+(\w+):\s*(.*)$", line)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            if key == "source" and val.startswith("{"):
                src = {}
                for kv in re.findall(r"(\w+):\s*([^,}]+)", val):
                    src[kv[0].strip()] = kv[1].strip()
                cur["source"] = src
            else:
                cur[key] = val
    if cur:
        claims.append(cur)
    return claims


def code_root(override):
    base = override or os.environ.get("DRIFT_SOURCE_ROOT")
    return os.path.normpath(base) if base else REPO_ROOT


def enum_values_from_php(text):
    """Значения PHP backed-enum (case X = 'v';); иначе имена case."""
    backed = re.findall(r"case\s+\w+\s*=\s*'([^']*)'", text)
    if backed:
        return set(backed)
    return set(re.findall(r"case\s+(\w+)\s*[=;]", text))


def doc_section(doc_text, symbol):
    """Текст секции дока (## ...), упоминающей symbol, до следующего '## '/'### '."""
    lines = doc_text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("#") and re.search(r"`?" + re.escape(symbol) + r"`?", ln):
            start = i
            break
    if start is None:
        for i, ln in enumerate(lines):
            if ln.startswith("#") and symbol in "".join(lines[i:i + 8]):
                start = i
                break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("#") and lines[j][:start_level(lines[start])] == lines[start][:start_level(lines[start])]:
            end = j
            break
    return "\n".join(lines[start:end])


def start_level(heading):
    return len(heading) - len(heading.lstrip("#"))


def find_symbol(root, symbol):
    """grep объявления (class/enum/interface/trait) под root/src."""
    src = os.path.join(root, "src")
    if not os.path.isdir(src):
        src = root
    pat = re.compile(r"\b(class|enum|interface|trait)\s+" + re.escape(symbol) + r"\b")
    for dp, _dn, fns in os.walk(src):
        for fn in fns:
            if not fn.endswith(".php"):
                continue
            try:
                with open(os.path.join(dp, fn), encoding="utf-8") as fh:
                    if pat.search(fh.read()):
                        return os.path.join(dp, fn)
            except (OSError, UnicodeDecodeError):
                continue
    return None


def check(claim, root):
    """Вернуть (status, detail): status in PASS|FAIL|SKIP."""
    src = claim.get("source", {})
    sym = src.get("symbol", "")
    path = src.get("path", "")
    ctype = claim.get("type", "")
    abspath = os.path.join(root, path) if path else None

    # SKIP: объявленный файл-источник отсутствует (другая ветка, код не влит)
    if abspath and not os.path.isfile(abspath):
        return "SKIP", f"источник не выкачан: {path}"

    if ctype == "symbol-exists":
        found = abspath if abspath else find_symbol(root, sym)
        if abspath:
            txt = open(abspath, encoding="utf-8").read()
            ok = re.search(r"\b(class|enum|interface|trait)\s+" + re.escape(sym) + r"\b", txt)
            return ("PASS", f"{sym} в {path}") if ok else ("FAIL", f"{sym} не объявлен в {path}")
        return ("PASS", f"{sym} найден: {found}") if found else ("FAIL", f"{sym} не найден в коде")

    if ctype == "pointer-only":
        # symbol существует в указанном файле + канон ссылается на путь
        txt = open(abspath, encoding="utf-8").read()
        ok = re.search(r"\b(class|enum|interface|trait)\s+" + re.escape(sym) + r"\b", txt)
        return ("PASS", f"{sym} жив в {path}") if ok else ("FAIL", f"{sym} исчез из {path}")

    if ctype == "enum-values":
        code_vals = enum_values_from_php(open(abspath, encoding="utf-8").read())
        doc_path = os.path.join(DOCS_ROOT, claim["doc"])
        if not os.path.isfile(doc_path):
            return "FAIL", f"канон-док не найден: {claim['doc']}"
        section = doc_section(open(doc_path, encoding="utf-8").read(), sym)
        if section is None:
            return "FAIL", f"в {claim['doc']} нет секции про {sym}"
        missing = {v for v in code_vals if v not in section}
        if missing:
            return "FAIL", f"{sym}: значения в коде, но не в каноне: {sorted(missing)}"
        return "PASS", f"{sym}: все {len(code_vals)} значений в каноне"

    return "FAIL", f"неизвестный тип claim: {ctype}"


def main():
    override = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--source-root" and i + 1 < len(args):
            override = args[i + 1]
    root = code_root(override)

    claims_path = os.path.join(DOCS_ROOT, "claims.yaml")
    if not os.path.isfile(claims_path):
        print("[drift] нет claims.yaml — нечего проверять")
        return 0

    claims = parse_claims(claims_path)
    failed = passed = skipped = 0
    for c in claims:
        try:
            status, detail = check(c, root)
        except Exception as e:  # noqa: BLE001 — чекер не должен падать стектрейсом
            status, detail = "FAIL", f"ошибка проверки: {e}"
        mark = {"PASS": "ok", "FAIL": "FAIL", "SKIP": "skip"}[status]
        print(f"[drift] {mark}: {c.get('id', '?')} — {detail}")
        failed += status == "FAIL"
        passed += status == "PASS"
        skipped += status == "SKIP"

    verb = "verified" if not skipped else "verified (часть skipped)"
    print(f"[drift] итог: {passed} {verb}, {skipped} skipped, {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
