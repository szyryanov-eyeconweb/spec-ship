#!/usr/bin/env python3
"""Кейсы для ship-guard.sh: барьер прав сабагентов, включая запись через Bash.

Запуск: python3 hooks/test_ship_guard.py
"""
import json
import subprocess
import sys
from pathlib import Path

GUARD = Path(__file__).with_name("ship-guard.sh")
ROOT = "/proj"


def run(agent: str, tool: str, tool_input: dict) -> bool:
    """True — хук отклонил вызов."""
    payload = {"agent_type": agent, "tool_name": tool, "tool_input": tool_input}
    out = subprocess.run(["bash", str(GUARD)], input=json.dumps(payload),
                         capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": ROOT}).stdout
    return '"deny"' in out


def check(agent: str, tool: str, tool_input: dict, deny: bool, label: str) -> None:
    got = run(agent, tool, tool_input)
    assert got == deny, f"{label}: ожидалось {'deny' if deny else 'allow'}, получено {'deny' if got else 'allow'}"
    print(f"  ok  {label}")


def bash(cmd: str) -> dict:
    return {"command": cmd}


print("Write/Edit (было до Bash)")
check("ship-green", "Write", {"file_path": f"{ROOT}/tests/ATest.php"}, True, "green пишет тест")
check("ship-green", "Edit", {"file_path": f"{ROOT}/src/A.php"}, False, "green пишет src")
check("ship-red", "Write", {"file_path": f"{ROOT}/src/A.php"}, True, "red пишет src")
check("main", "Write", {"file_path": f"{ROOT}/tests/ATest.php"}, False, "основная сессия не ограничена")

print("Bash: обход через запись в shell")
check("ship-green", "Bash", bash("sed -i 's/assertSame/assertNotNull/' tests/Unit/ATest.php"), True, "green: sed -i по тесту")
check("ship-green", "Bash", bash("cat > tests/Unit/ATest.php <<'EOF'\n<?php\nEOF"), True, "green: heredoc в тест")
check("ship-green", "Bash", bash("echo x >> ./tests/ATest.php"), True, "green: >> в тест")
check("ship-green", "Bash", bash("git checkout -- tests/Unit/ATest.php"), True, "green: откат теста через git")
check("ship-green", "Bash", bash("rm tests/Unit/ATest.php"), True, "green: удаление теста")
check("ship-green", "Bash", bash(f"cp /tmp/x.php {ROOT}/tests/ATest.php"), True, "green: cp в тест, абсолютный путь")
check("ship-red", "Bash", bash("echo '<?php' > src/Foo.php"), True, "red: запись в src")
check("ship-red", "Bash", bash("sed -i '' config/services.yaml"), True, "red: sed -i по config")
check("ship-review", "Bash", bash("tee src/A.php < /tmp/x"), True, "review: tee в src")
check("ship-decompose", "Bash", bash("mv /tmp/a.php tests/A.php"), True, "decompose: mv в tests")

print("Bash: легитимная работа не ломается")
check("ship-green", "Bash", bash("vendor/bin/phpunit tests/Unit/ATest.php > /tmp/out.txt 2>&1"), False, "green: прогон теста с выводом в /tmp")
check("ship-green", "Bash", bash("vendor/bin/phpunit tests/Unit 2>/dev/null | tail -5"), False, "green: прогон, stderr в /dev/null")
check("ship-green", "Bash", bash("grep -rn 'Payout' tests/ src/"), False, "green: чтение тестов")
check("ship-green", "Bash", bash("sed -i 's/a/b/' src/A.php"), False, "green: sed -i по src")
check("ship-red", "Bash", bash("sed -n 1,20p src/A.php"), False, "red: sed без -i читает src")
check("ship-red", "Bash", bash("echo '<?php' > tests/ATest.php"), False, "red: запись в tests")
check("ship-review", "Bash", bash("git diff src/ tests/ | head"), False, "review: дифф")
check("ship-review", "Bash", bash("php -r 'echo 1;' > .ship/pipeline/x/out.txt"), False, "review: запись в pipeline")

print("\n✓ все кейсы прошли")
