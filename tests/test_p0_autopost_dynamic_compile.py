from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def test_autopost_embedded_engine_compiles_as_runtime_source() -> None:
    source = BOT_PATH.read_text(encoding="utf-8")
    marker = "autopost_engine_code = r'''"
    start = source.index(marker) + len(marker)
    end = source.index("\n'''\nexec(compile(autopost_engine_code", start)

    compile(source[start:end], f"{BOT_PATH}:autopost_engine", "exec")
