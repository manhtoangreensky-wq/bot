import asyncio
import hashlib
from pathlib import Path
import re
import time
from types import SimpleNamespace

import pytest

import bot
from services import subdub_speaker_cast


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
AUTO_SPEAKER_PATH = ROOT / "services" / "subdub_blackboxes" / "auto_speaker.py"
AUTO_SPEAKER_SOURCE = AUTO_SPEAKER_PATH.read_text(encoding="utf-8")

POST_ONNX_AUTO_SPEAKER_GIT_BLOB = (
    "1d1326bcdc2c3d9fb4adb892475999599308ec5a"
)


def _git_blob_sha1(path: Path) -> str:
    payload = path.read_bytes().replace(b"\r\n", b"\n")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _function_source(source: str, name: str) -> str:
    start = source.index(f"def {name}(")
    next_sync = source.find("\ndef ", start + 1)
    next_async = source.find("\nasync def ", start + 1)
    candidates = [offset for offset in (next_sync, next_async) if offset >= 0]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_two_speaker_engine_is_locked_after_exact_onnx_authority():
    assert (
        _git_blob_sha1(AUTO_SPEAKER_PATH)
        == POST_ONNX_AUTO_SPEAKER_GIT_BLOB
    )


def test_two_speaker_wrapper_has_only_the_scoped_onnx_authority():
    core = _function_source(BOT_SOURCE, "_execute_video_dubbing_pipeline_core")

    assert "auto_speaker.guard_subtitle_font(" not in core
    assert "def guard_subtitle_font(" not in AUTO_SPEAKER_SOURCE
    assert "subdub_two_speaker_gender_onnx.classify_two_speaker_genders" in AUTO_SPEAKER_SOURCE
    assert "def _independent_two_speaker_classifications(" not in AUTO_SPEAKER_SOURCE
    assert "def _collect_two_speaker_pitch_evidence(" not in AUTO_SPEAKER_SOURCE
    assert "def _classify_two_speaker_registers(" not in AUTO_SPEAKER_SOURCE
    assert "MULTI_PCM_AUDIO_FILTER" not in AUTO_SPEAKER_SOURCE


def test_audio_mix_main_screen_keeps_both_layers_in_one_row():
    keyboard = _function_source(BOT_SOURCE, "subdub_audio_mix_keyboard")
    same_row = re.search(
        r"\[\s*InlineKeyboardButton\([^\]]+videodub\|audio_original[^\]]+"
        r"InlineKeyboardButton\([^\]]+videodub\|audio_dub[^\]]+\]",
        keyboard,
        flags=re.DOTALL,
    )

    assert same_row is not None


def test_audio_layers_keep_compact_numeric_controls_without_presets():
    mix_keyboard = _function_source(BOT_SOURCE, "subdub_audio_mix_keyboard")
    layer_keyboard = _function_source(BOT_SOURCE, "subdub_audio_layer_keyboard")
    callback = _function_source(BOT_SOURCE, "handle_video_dubbing_callback")

    assert "videodub|audio_original" in mix_keyboard
    assert "videodub|audio_dub" in mix_keyboard
    assert "audio_original_volume" not in mix_keyboard
    assert "audio_dub_volume" not in mix_keyboard
    assert "videodub|audio_original_input" in layer_keyboard
    assert "videodub|audio_dub_input" in layer_keyboard
    assert '"audio_original_input", "audio_dub_input"' in callback
    assert '"audio_original_volume"' not in callback
    assert '"audio_dub_volume"' not in callback


def test_multi_lane_file_is_not_part_of_two_speaker_rollback():
    multi_path = ROOT / "services" / "subdub_blackboxes" / "auto_multi_speaker.py"

    assert multi_path.is_file()
    assert hashlib.sha256(multi_path.read_bytes()).hexdigest().upper() == (
        "55AAB8949EFAECAD8DD987AC6DFE056AB0E4BC4EF81A23977EA5EDD1CDF64911"
    )


@pytest.mark.parametrize(
    ("frequencies", "expected"),
    (
        ((110.0, 130.0), ("low", "low")),
        ((110.0, 220.0), ("low", "high")),
        ((180.0, 220.0), ("high", "high")),
    ),
    ids=("male-male", "male-female", "female-female"),
)
def test_pr842_classifier_classifies_each_speaker_independently(
    monkeypatch,
    tmp_path,
    frequencies,
    expected,
):
    pcm_path = tmp_path / "two-speaker.pcm"
    pcm_path.write_bytes(
        b"\0" * (subdub_speaker_cast.PCM_SAMPLE_RATE * 2 * 6)
    )
    estimates = iter(
        [(frequencies[0], 0.95)] * 6
        + [(frequencies[1], 0.95)] * 6
    )
    monkeypatch.setattr(
        subdub_speaker_cast,
        "_estimate_window_pitch",
        lambda *_args, **_kwargs: next(estimates),
    )

    result = subdub_speaker_cast.classify_speaker_registers(
        str(pcm_path),
        {
            "chunk_00:speaker_0": [(0.0, 3.0)],
            "chunk_00:speaker_1": [(3.0, 6.0)],
        },
        deadline_monotonic=time.monotonic() + 30.0,
        stop_requested=lambda: False,
    )

    assert (
        result["chunk_00:speaker_0"]["voice_register"],
        result["chunk_00:speaker_1"]["voice_register"],
    ) == expected


@pytest.mark.parametrize(
    ("mode", "active_flow"),
    (
        ("dub", "dub_audio"),
        ("subtitle_plus_dub", "subtitle_plus_dub"),
    ),
)
def test_numeric_audio_inputs_persist_in_both_dub_lanes(
    monkeypatch,
    mode,
    active_flow,
):
    user_id = 98_842
    state = {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "active_flow": active_flow,
        "step": "audio_mix",
        "source_file_id": "fixture",
    }
    rendered = []

    def get_pending(_uid):
        return dict(state)

    def set_pending(_uid, step, **fields):
        state.update(fields)
        state["step"] = step
        return dict(state)

    async def safe_edit(_query, text, **kwargs):
        rendered.append({"text": text, **kwargs})
        return rendered[-1]

    monkeypatch.setattr(bot, "get_video_dubbing_pending", get_pending)
    monkeypatch.setattr(bot, "set_video_dubbing_pending", set_pending)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "enter_product_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "safe_edit_or_send", safe_edit)

    class Query:
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)

        async def answer(self):
            return None

    class InputMessage:
        def __init__(self, text):
            self.text = text
            self.replies = []

        async def reply_text(self, text, **kwargs):
            self.replies.append({"text": text, **kwargs})
            return self.replies[-1]

    update = SimpleNamespace(callback_query=Query())
    for callback, expected_step, numeric_value in (
        ("videodub|audio_original_input", "subdub_original_volume_input", "40"),
        ("videodub|audio_dub_input", "subdub_dub_volume_input", "150"),
    ):
        update.callback_query.data = callback
        asyncio.run(bot.handle_video_dubbing_callback(update, SimpleNamespace()))
        assert state["step"] == expected_step
        message = InputMessage(numeric_value)
        numeric_update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=user_id),
        )
        assert asyncio.run(
            bot.handle_video_dubbing_pending_text(numeric_update, SimpleNamespace())
        ) is True
        assert len(message.replies) == 1

    assert state["step"] == "audio_dub"
    assert state["keep_original_audio"] == "1"
    assert state["original_audio_volume_percent"] == 40
    assert state["dubbed_voice_volume_percent"] == 150
    assert state["audio_mix_mode"] == "keep_original"
    assert state["volume_config_source"] == "user_numeric_audio_mix"
    assert len(rendered) == 2
