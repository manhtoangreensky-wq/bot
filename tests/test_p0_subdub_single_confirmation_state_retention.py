import ast
import html
from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _load_function(name: str, namespace: dict):
    tree = ast.parse(BOT_SOURCE)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, str(BOT_PATH), "exec"), namespace)
    return namespace[name]


def test_voice_reset_keeps_combo_media_translation_and_audio_state():
    key = "video_dubbing:7"
    pending = {
        key: {
            "pending_action": "video_dubbing",
            "mode": "subtitle_plus_dub",
            "process_type": "subtitle_plus_dub",
            "video_processing_mode": "subtitle_plus_dub",
            "active_flow": "subtitle_plus_dub",
            "source_file_id": "telegram-video",
            "subtitle_ref": "original-srt",
            "translated_subtitle_ref": "ja-srt",
            "target_language": "日本語",
            "segment_count": "25",
            "keep_original_audio": "1",
            "original_audio_volume_percent": "20",
            "dubbed_voice_volume_percent": "100",
            "voice_style": "default_female",
            "selected_voice_id": "manual-voice",
            "subdub_final_confirmed": True,
        }
    }
    namespace = {
        "USER_PENDING": pending,
        "video_dubbing_pending_key": lambda user_id: f"video_dubbing:{user_id}",
        "SUBDUB_MANUAL_VOICE_FIELDS": frozenset({"voice_style", "selected_voice_id"}),
        "SUBDUB_AUTO_VOICE_FIELDS": frozenset({"voice_kind", "voice_selection_mode"}),
        "SUBDUB_VOICE_CONFIRMATION_FIELDS": frozenset({"subdub_final_confirmed"}),
    }
    persist = _load_function("_persist_subdub_voice_reset", namespace)

    restored = persist(
        7,
        {
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
        },
    )

    assert restored["pending_action"] == "video_dubbing"
    assert restored["mode"] == "subtitle_plus_dub"
    assert restored["source_file_id"] == "telegram-video"
    assert restored["translated_subtitle_ref"] == "ja-srt"
    assert restored["target_language"] == "日本語"
    assert restored["segment_count"] == "25"
    assert restored["original_audio_volume_percent"] == "20"
    assert restored["dubbed_voice_volume_percent"] == "100"
    assert restored["voice_kind"] == "auto_speaker_gender"
    assert "voice_style" not in restored
    assert "selected_voice_id" not in restored
    assert "subdub_final_confirmed" not in restored


def _confirmation_namespace() -> dict:
    copy = {
        "voice_auto_speaker": "👥 Tự nhận giọng (tối đa 16)",
        "confirm": "✅ Xác nhận",
        "continue": "✅ Tiếp tục",
        "back": "⬅️ Quay lại",
        "current": "🎬 Video đang làm",
        "language": "🌐 Ngôn ngữ",
        "voice": "🎙 Giọng",
        "output": "📤 Kết quả xuất",
        "auto": "Tạo phụ đề",
        "translate": "🌐 Dịch phụ đề video",
        "dub": "🎙 Lồng tiếng video",
        "combo": "🎞 Phụ đề + Lồng tiếng",
        "locked": "Đã khóa cấu hình",
    }
    return {
        "html": html,
        "normalize_user_language": lambda value: value or "vi",
        "normalize_video_translate_mode": lambda value: str(value or ""),
        "public_subdub_deep_copy": lambda _lang: copy,
        "subtitle_plus_dub_is_active": lambda _state: False,
        "video_dubbing_is_video_only_mode": lambda _mode: False,
        "_short_pending_text": lambda value, _limit=0: str(value or ""),
        "subdub_auto_speaker_route_enabled": lambda _state: False,
        "video_dubbing_estimated_price_xu": lambda _state: 0,
        "video_dubbing_invoice_breakdown": lambda _state: {},
        "canonical_price_xu": lambda _key: 0,
        "subdub_audio_mix_confirm_lines": lambda _state, _lang: "",
        "video_only_price_line": lambda _value: "0%",
        "VIDEO_DUBBING_FLOW_TRANSCRIPT": "transcript",
        "VIDEO_DUBBING_FLOW_SUBTITLE_FILE_TRANSLATE": "subtitle_file_translate",
        "VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
        "VIDEO_SUBTITLE_MODE_CREATE": "create",
        "VIDEO_SUBTITLE_MODE_TRANSLATE": "translate",
        "VIDEO_SUBTITLE_MODE_DUB": "dub",
        "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
        "VIDEO_ONLY_SUBTITLE_TRANSLATE_RATE_XU": 0.2,
        "VIDEO_ONLY_DUB_DEFAULT_RATE_XU": 0.3,
    }


def test_fallback_confirmation_copy_is_not_repeated():
    render = _load_function("video_dubbing_confirm_text", _confirmation_namespace())

    text = render({}, "vi")

    assert text.count("✅ Xác nhận") == 1


def test_fallback_confirmation_keyboard_has_one_submit_action():
    class Button:
        def __init__(self, text, callback_data=""):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        **_confirmation_namespace(),
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "video_dubbing_subtitle_position_button": lambda *_args: Button("position"),
        "subdub_audio_mix_available": lambda _state: False,
        "video_dubbing_subtitle_position_available": lambda _state: False,
        "ui_text": lambda _lang, _key: "🏠 Menu chính",
    }
    keyboard = _load_function("video_dubbing_confirm_keyboard", namespace)

    labels = [button.text for row in keyboard("vi", {}).inline_keyboard for button in row]

    assert labels.count("✅ Xác nhận") == 1
    assert "✅ Tiếp tục" not in labels
