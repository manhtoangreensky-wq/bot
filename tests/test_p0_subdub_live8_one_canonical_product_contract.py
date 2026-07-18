import asyncio
import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace

import bot
from services import subdub_canonical_cues as canonical


REPO = Path(__file__).resolve().parents[1]


class _CaptureBot:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(dict(kwargs))
        return SimpleNamespace(
            message_id=kwargs["message_id"],
            chat_id=kwargs["chat_id"],
        )


class _CaptureMessage:
    def __init__(self):
        self.chat_id = 7008
        self.message_id = 8008
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((str(text), dict(kwargs)))
        return SimpleNamespace(
            message_id=9008 + len(self.replies),
            chat_id=self.chat_id,
        )


class _CaptureQuery:
    def __init__(self, message, bot_client):
        self.message = message
        self._bot_client = bot_client

    def get_bot(self):
        return self._bot_client


def _source_cues():
    return canonical.canonicalize_segments(
        [
            {"index": 1, "start": 0.25, "end": 1.75, "text": "Xin chao"},
            {"index": 2, "start": 2.00, "end": 4.50, "text": "Hen gap lai"},
        ],
        extraction_source="subtitle_stream",
        source_language="vi",
    )


def test_live8_canonical_cue_schema_and_translation_are_timeline_locked():
    required = {
        "cue_id",
        "start_ms",
        "end_ms",
        "source_text",
        "translated_text",
        "cue_source",
        "source_language",
        "confidence",
    }
    assert required <= set(canonical.CanonicalCue.__annotations__)

    source = _source_cues()
    translated = canonical.apply_translations(
        source,
        [
            {"cue_id": source[0]["cue_id"], "translated_text": "Hello"},
            {"cue_id": source[1]["cue_id"], "translated_text": "See you again"},
            {"cue_id": "extra-cue", "translated_text": "must be ignored"},
        ],
        target_language="en",
    )

    assert canonical.same_timeline(source, translated)
    assert len(translated) == len(source)
    assert [cue["translated_text"] for cue in translated] == ["Hello", "See you again"]
    assert canonical.timeline_signature(translated) == canonical.timeline_signature(source)


def test_live8_missing_or_long_translation_never_shifts_following_cues():
    source = _source_cues()
    translated = canonical.apply_translations(
        source,
        [{"cue_id": source[0]["cue_id"], "translated_text": "A very long translated sentence that must wrap only inside this cue window"}],
        target_language="en",
        max_chars=24,
        max_lines=2,
    )

    assert canonical.same_timeline(source, translated)
    assert translated[0]["translated_text"].count("\n") <= 1
    assert translated[1]["translate_missing"] is True
    assert translated[1]["translated_text"] == source[1]["source_text"]


def test_live8_all_four_lanes_use_the_shared_canonical_core():
    modes = (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    )
    assert all(bot.subdub_mode_uses_canonical_cues(mode) for mode in modes)

    pipeline_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "video_dubbing_prepare_subtitles" in pipeline_source
    assert "canonical_cue_mode" in pipeline_source
    assert "await _progress(\"delivered\")" not in pipeline_source


def test_live8_wrong_script_ocr_is_rejected_before_asr_fallback():
    wrong = canonical.evaluate_ocr_quality(
        [{"index": 1, "start": 0.0, "end": 1.0, "text": "This is English text", "confidence": 0.95}],
        source_language="zh",
        language_spec="chi_sim+eng",
    )
    right = canonical.evaluate_ocr_quality(
        [{"index": 1, "start": 0.0, "end": 1.0, "text": "这是中文字幕", "confidence": 0.95}],
        source_language="zh",
        language_spec="chi_sim+eng",
    )

    assert wrong["accepted"] is False
    assert wrong["reason"] == "ocr_wrong_script_for_source_language"
    assert right["accepted"] is True


def test_live8_duration_truth_is_strict_and_parses_renderer_evidence():
    assert canonical.duration_matches_source(30.0, 30.35)["ok"] is True
    assert canonical.duration_matches_source(30.0, 30.351)["ok"] is False
    evidence = canonical.parse_render_duration_evidence(
        "source_duration_preserved=30.000;output_duration=29.800"
    )
    assert evidence["duration_evidence_present"] is True
    assert evidence["duration_preserved"] is True
    assert evidence["duration_delta_seconds"] == 0.2


def test_live8_subdub_renderer_never_uses_shortest():
    source = inspect.getsource(bot.video_dubbing_render_video)
    assert "-shortest" not in source
    assert 'command.extend(["-t", f"{source_duration:.3f}"])' in source


def test_live8_subtitle_style_is_current_plus_two_and_raised_eight_px_at_1080p():
    state = {
        "output_type": "burn",
        "video_width": 1920,
        "video_height": 1080,
        "m4live1_style_renderer_only": True,
    }
    baseline = bot.subdub_normalize_style(state)
    live8 = bot.subdub_normalize_style({**state, "subdub_canonical_product_contract": True})

    assert live8["render_size"] == baseline["render_size"] + 2
    assert live8["subtitle_alignment"] == "bottom_center"
    assert live8["subtitle_margin_v_after"] == baseline["subtitle_margin_v_after"] + 8
    assert live8["subtitle_max_lines"] == 2
    assert live8["background"] == "box"
    assert live8["boxed_background"] is True
    assert live8["uppercase_text"] is True
    assert live8["bold_text"] is True
    assert live8["cover_original"] is False


def test_live8_all_four_lanes_terminalize_only_after_real_artifact_message_id():
    modes = (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    )
    for index, mode in enumerate(modes, start=1):
        key = f"live8-terminal-{index}"
        bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
        acquired, job = bot.acquire_subtitle_dub_pipeline_job(
            key,
            user_id=7008,
            chat_id=7008,
            mode=mode,
            status_panel_message_id="8008",
            status_panel_chat_id="7008",
        )
        assert acquired is True

        # Generic Telegram ids from unrelated messages are never proof.
        assert bot.subdub_terminal_delivery_evidence({
            "mode": mode,
            "has_video": True,
            "telegram_message_id": f"generic-{index}",
        }) == {}

        delivery_id = str(9100 + index)
        assert bot.mark_subtitle_dub_pipeline_output_sent(
            key,
            terminal_state="delivered",
            terminal_artifact_type="video",
            delivery_message_id=delivery_id,
            video_delivery_message_id=delivery_id,
            defer_until_panel=True,
        )
        pending = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
        assert pending["terminal_state"] != "delivered"
        assert pending["progress_percent"] <= 99
        assert pending["panel_finalized"] is False
        capture_bot = _CaptureBot()
        message = _CaptureMessage()
        query = _CaptureQuery(message, capture_bot)
        result = {
            "mode": mode,
            "has_video": True,
            "final_mp4_delivered": True,
            "video_delivery_message_id": delivery_id,
        }

        finalized = asyncio.run(bot.subdub_finalize_delivered_panel(
            query,
            SimpleNamespace(bot=capture_bot),
            key,
            job["job_id"],
            "vi",
            result,
        ))
        first = asyncio.run(bot.subdub_send_success_receipt_once(message, key, "receipt"))
        retry = asyncio.run(bot.subdub_send_success_receipt_once(message, key, "receipt"))

        stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
        assert finalized is not None
        assert first is not None
        assert retry is None
        assert stored["progress_percent"] == 100
        assert stored["telegram_artifact_message_id"] == delivery_id
        assert stored["terminal_receipt_count"] == 1
        assert len(capture_bot.edits) == 1
        assert len(message.replies) == 1


def test_live8_receipt_exposes_source_and_output_duration():
    delivery_id = "video-9208"
    text = bot.video_dubbing_receipt_text(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "terminal_state": "delivered",
            "source_duration": 30.0,
            "output_duration": 29.9,
        },
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "terminal_state": "delivered",
            "final_mp4_delivered": True,
            "video_delivery_message_id": delivery_id,
            "source_duration": 30.0,
            "output_duration": 29.9,
        },
        "vi",
    )

    assert "Thời lượng nguồn:" in text and "30" in text
    assert "Thời lượng kết quả:" in text and "29.9" in text


def test_live8_scope_is_subdub_only():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.splitlines()
    allowed = {
        "bot.py",
        "services/subdub_canonical_cues.py",
        "services/subtitle_dub_product_pipeline.py",
        "tests/test_p0_subdub_live5_subtitle_combo_canonical_cue_restore.py",
        "tests/test_p0_subdub_live6_mp4_audio_cue_long_auto_subtitle.py",
            "tests/test_p0_subdub_live8_one_canonical_product_contract.py",
            "tests/test_p0_subdub_live9_persistent_execution_recovery.py",
            "tests/test_p0_subdub_live10_menu_route_isolation.py",
            "tests/test_p0_subdub_live10_tts_checkpoint_resume.py",
        }
    assert set(changed) <= allowed
