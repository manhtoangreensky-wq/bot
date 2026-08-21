from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def test_registered_autopost_callback_is_a_real_top_level_handler() -> None:
    source = BOT_PATH.read_text(encoding="utf-8")
    assert 'CallbackQueryHandler(handle_autopost_callback, pattern=r"^autopost\\|")' in source

    engine_start = source.index("autopost_engine_code = '''")
    engine_body_start = engine_start + len("autopost_engine_code = '''")
    engine_body_end = source.index("\n'''", engine_body_start)
    engine_source = source[engine_body_start:engine_body_end]
    compile(engine_source, "<autopost_engine>", "exec")

    context_types = type("ContextTypes", (), {"DEFAULT_TYPE": object})
    engine_namespace = {
        "ContextTypes": context_types,
        "InlineKeyboardMarkup": object,
        "Update": object,
    }
    exec(compile(engine_source, "<autopost_engine>", "exec"), engine_namespace)

    assert "\ndef autopost_hub_text(" in engine_source
    assert "\ndef autopost_hub_keyboard(" in engine_source
    assert "\nasync def handle_autopost_callback(" in engine_source
    assert callable(engine_namespace["handle_autopost_callback"])

    activation = (
        'exec(compile(autopost_engine_code, f"{__file__}:autopost_engine", "exec"), globals())'
    )
    activation_index = source.index(activation)
    menu_handler_index = source.index("\nasync def handle_menu_callback(")
    registration_index = source.index(
        'CallbackQueryHandler(handle_autopost_callback, pattern=r"^autopost\\|")'
    )
    assert engine_body_end < activation_index < menu_handler_index
    assert activation_index < registration_index
