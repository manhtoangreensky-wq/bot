from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
ENGINE_PATH = Path(__file__).resolve().parents[1] / "services" / "autopost_engine.py"


def test_registered_autopost_callback_is_a_real_top_level_handler() -> None:
    source = BOT_PATH.read_text(encoding="utf-8")
    assert 'CallbackQueryHandler(handle_autopost_callback, pattern=r"^autopost\\|")' in source

    # M3 (2026-11-24): the autopost engine used to be an exec'd string inside
    # bot.py. It is now a real module; the handler must be importable from
    # it and bot.py must import (not exec) it.
    engine_source = ENGINE_PATH.read_text(encoding="utf-8")
    compile(engine_source, str(ENGINE_PATH), "exec")

    assert "\ndef autopost_hub_text(" in engine_source
    assert "\ndef autopost_hub_keyboard(" in engine_source
    assert "\nasync def handle_autopost_callback(" in engine_source

    from services.autopost_engine import handle_autopost_callback

    assert callable(handle_autopost_callback)

    assert "autopost_engine_code" not in source
    assert "exec(compile(autopost_engine_code" not in source
    assert "from services.autopost_engine import" in source
    assert "handle_autopost_callback" in source

    import_index = source.index("from services.autopost_engine import")
    menu_handler_index = source.index("\nasync def handle_menu_callback(")
    registration_index = source.index(
        'CallbackQueryHandler(handle_autopost_callback, pattern=r"^autopost\\|")'
    )
    assert import_index < menu_handler_index
    assert import_index < registration_index
