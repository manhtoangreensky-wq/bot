import ast
from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
ENGINE_PATH = Path(__file__).resolve().parents[1] / "services" / "autopost_engine.py"


def test_autopost_engine_module_compiles_as_runtime_source() -> None:
    # M3 (2026-11-24): the autopost engine used to live as an exec'd string
    # literal inside bot.py (``autopost_engine_code``). It is now a real
    # module; this test pins the new shape: the module source compiles and
    # exposes the same three public names bot.py imports.
    source = ENGINE_PATH.read_text(encoding="utf-8")
    assert source.strip()
    compile(source, str(ENGINE_PATH), "exec")
    tree = ast.parse(source)
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {"autopost_hub_text", "autopost_hub_keyboard", "handle_autopost_callback"} <= defined

    from services.autopost_engine import (
        autopost_hub_keyboard,
        autopost_hub_text,
        handle_autopost_callback,
    )

    assert callable(autopost_hub_text)
    assert callable(autopost_hub_keyboard)
    assert callable(handle_autopost_callback)

    bot_source = BOT_PATH.read_text(encoding="utf-8")
    assert "autopost_engine_code" not in bot_source
    assert "exec(compile(autopost_engine_code" not in bot_source
    assert "from services.autopost_engine import" in bot_source
