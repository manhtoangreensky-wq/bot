import ast
import asyncio
import html
from pathlib import Path
from types import SimpleNamespace
import time
import uuid


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


def test_auto_combo_translation_choice_marks_translated_subtitle_as_dub_source():
    start = BOT_SOURCE.index("def subdub_apply_voice_choice(")
    end = BOT_SOURCE.index("\ndef subdub_auto_manual_required_recovery(", start)
    namespace = {
        "subdub_auto_provider_capacity_ready": lambda: True,
        "reset_subdub_voice_selection": lambda state, *, selecting_auto: dict(state),
        "subtitle_plus_dub_is_active": lambda state: state.get("mode") == "subtitle_plus_dub",
        "video_dubbing_voice_payload": lambda *_args, **_kwargs: {},
    }
    exec(compile(BOT_SOURCE[start:end], str(BOT_PATH), "exec"), namespace)
    choose = namespace["subdub_apply_voice_choice"]
    selected = choose(
        {
            "mode": "subtitle_plus_dub",
            "active_flow": "subtitle_plus_dub",
            "target_language": "日本語",
            "translate_requested": "1",
        },
        "auto_speaker_gender",
    )

    assert selected is not None
    assert selected["target_language"] == "日本語"
    assert selected["dub_source"] == "translated_subtitle"
    assert selected["voice_kind"] == "auto_speaker_gender"


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


def test_owner_initial_confirmation_claims_exact_auto_receipt_without_second_prompt():
    persisted = []
    state = {
        "_pipeline_is_admin": True,
        "_pipeline_job_key": "owner-auto-job-key",
        "_pipeline_job_id": "owner-auto-job",
        "_pipeline_owner_user_id": "7",
        "_pipeline_chat_id": "7",
        "subdub_final_confirmed": True,
        "auto_quote_exact_known": False,
        "auto_quote_billable_words": None,
        "auto_quote_total_xu": None,
    }
    initial_state = dict(state)
    receipt = {
        "session_nonce": "nonce12345678",
        "consumed": False,
        "claim_state": "unconsumed",
    }

    def update_job(job_key, **fields):
        return {"job_key": job_key, **fields}

    def persist_job(job_key, snapshot=None, *, reason=""):
        persisted.append((job_key, dict(snapshot or {}), reason))
        return True

    namespace = {
        "subdub_auto_speaker_route_enabled": lambda _state: True,
        "subtitle_dub_product_pipeline": SimpleNamespace(
            resolve_subdub_dub_audio_policy=lambda _state, _prepared: {
                "tts_segments": [{"text": "xin chào"}],
            }
        ),
        "_subdub_auto_selected_text": lambda _segments: "xin chào",
        "_subdub_auto_actual_components": lambda *_args: (2, 1, 0),
        "_subdub_auto_read_balance_xu": lambda _user_id: 100,
        "_workspace_truthy": bool,
        "subdub_auto_word_pricing": SimpleNamespace(
            auto_exact_confirmation_state=lambda **_kwargs: {
                "exact_confirmation_required": True,
            }
        ),
        "SUBDUB_AUTO_EXACT_RECEIPT_VERSION": "exact-v1",
        "_subdub_auto_build_exact_receipt": lambda *_args, **_kwargs: {
            "ok": True,
            "receipt": receipt,
            "cache": {},
            "resume_state": {
                "keep_original_audio": "1",
                "original_audio_volume_percent": 20,
                "dubbed_voice_volume_percent": 100,
            },
        },
        "subdub_final_confirmed_state": lambda current: bool(
            current.get("subdub_final_confirmed")
        ),
        "uuid": uuid,
        "time": time,
        "update_subtitle_dub_pipeline_job": update_job,
        "persist_subtitle_dub_pipeline_job_snapshot": persist_job,
    }
    gate = _load_function("_subdub_auto_post_prepare_gate", namespace)

    result = asyncio.run(gate({"state": dict(state)}, state))

    assert result == {"continue": True}
    assert state["auto_exact_receipt"]["consumed"] is True
    assert state["auto_exact_receipt"]["claim_state"] == "resuming"
    assert state["auto_exact_receipt_confirmed"] is True
    assert persisted[-1][2] == "auto_exact_initial_confirmation_claimed"
    assert persisted[-1][1]["auto_exact_resume_state"] == {
        "keep_original_audio": "1",
        "original_audio_volume_percent": 20,
        "dubbed_voice_volume_percent": 100,
    }

    public_state = {**initial_state, "_pipeline_is_admin": False}
    public_result = asyncio.run(
        gate({"state": dict(public_state)}, public_state)
    )

    assert public_result["status"] == "AUTO_EXACT_CONFIRMATION_REQUIRED"
    assert public_result["resume_required"] is True
    assert public_state["auto_exact_receipt"]["consumed"] is False
    assert public_state["auto_exact_receipt"]["claim_state"] == "unconsumed"


def test_auto_pause_resume_snapshot_keeps_user_audio_mix_percentages():
    namespace = {
        "video_dubbing_sync_state_fields": lambda state, exclude=None: {
            key: value
            for key, value in state.items()
            if key not in set(exclude or ())
        }
    }
    snapshot = _load_function("_subdub_auto_resume_state", namespace)

    result = snapshot(
        {
            "keep_original_audio": "1",
            "original_audio_volume_percent": 20,
            "dubbed_voice_volume_percent": 100,
            "provider_route": "internal-only",
        }
    )

    assert result["keep_original_audio"] == "1"
    assert result["original_audio_volume_percent"] == 20
    assert result["dubbed_voice_volume_percent"] == 100
    assert "provider_route" not in result
