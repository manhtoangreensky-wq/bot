import ast
from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def test_autopost_embedded_engine_compiles_as_runtime_source() -> None:
    source = BOT_PATH.read_text(encoding="utf-8")
    marker = "autopost_engine_code = "
    start = source.index(marker) + len(marker)
    end = source.index("\nexec(compile(autopost_engine_code", start)
    runtime_source = ast.literal_eval(source[start:end].strip())

    assert isinstance(runtime_source, str) and runtime_source.strip()
    compile(runtime_source, f"{BOT_PATH}:autopost_engine", "exec")
