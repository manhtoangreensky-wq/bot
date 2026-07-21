from __future__ import annotations

import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BOT_PATH = ROOT / "bot.py"


def main() -> int:
    source = BOT_PATH.read_text(encoding="utf-8")
    try:
        compiled = compile(source, str(BOT_PATH), "exec")
        del compiled
        ast.parse(source, filename=str(BOT_PATH))
    except SyntaxError as exc:
        location = f"{exc.lineno or '-'}:{exc.offset or '-'}"
        print(
            f"bot.py syntax error at {location}: {exc.msg}",
            file=sys.stderr,
        )
        return 1
    print("bot.py compile(source) PASS")
    print("bot.py ast.parse PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
