import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    next_sync = BOT_SOURCE.find("\ndef ", start + 1)
    next_async = BOT_SOURCE.find("\nasync def ", start + 1)
    candidates = [offset for offset in (next_sync, next_async) if offset >= 0]
    return BOT_SOURCE[start : min(candidates) if candidates else len(BOT_SOURCE)]


def test_audio_mix_has_only_two_compact_layer_buttons_and_back():
    keyboard = _function_source("subdub_audio_mix_keyboard")
    same_row = re.search(
        r"\[\s*InlineKeyboardButton\([^\]]+videodub\|audio_original[^\]]+"
        r"InlineKeyboardButton\([^\]]+videodub\|audio_dub[^\]]+\]",
        keyboard,
        flags=re.DOTALL,
    )

    assert same_row is not None
    assert "videodub|back_audio_mix" in keyboard
    assert "audio_original_volume" not in keyboard
    assert "audio_dub_volume" not in keyboard
    assert not any(
        label in keyboard
        for label in (
            "Gốc 20%", "Gốc 40%", "Gốc 60%", "Gốc 80%", "Gốc 100%",
            "Lồng 80%", "Lồng 100%", "Lồng 120%", "Lồng 150%", "Lồng 200%",
        )
    )


def test_audio_layers_keep_only_existing_numeric_input_callbacks():
    layer_keyboard = _function_source("subdub_audio_layer_keyboard")
    callback = _function_source("handle_video_dubbing_callback")

    assert "videodub|audio_original_input" in layer_keyboard
    assert "videodub|audio_dub_input" in layer_keyboard
    assert '"audio_original_input", "audio_dub_input"' in callback
    assert '"audio_original_volume"' not in callback
    assert '"audio_dub_volume"' not in callback


def test_dynamic_audio_ui_contract_disables_fixed_percentage_grid():
    contract = _function_source("subdub_dynamic_volume_ui_future_spec")

    assert '"public_fixed_percentage_grid": False' in contract
    assert '"numeric_input_min": 0' in contract
    assert '"numeric_input_max": 100' in contract
    assert '"numeric_input_max": 200' in contract
