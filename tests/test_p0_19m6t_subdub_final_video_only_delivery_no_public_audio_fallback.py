import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

import bot


MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-p019m6t" + b"x" * 4096
GENERIC_ERROR = "Có lỗi khi xử lý lệnh. Bot chưa trừ Xu"


class CaptureMessage:
    def __init__(self, chat_id=19660):
        self.chat_id = chat_id
        self.texts = []
        self.audios = []
        self.documents = []
        self.videos = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(str(text))
        return SimpleNamespace(message_id=100 + len(self.texts), chat_id=self.chat_id)

    async def reply_audio(self, **kwargs):
        self.audios.append(kwargs)
        return SimpleNamespace(message_id=200 + len(self.audios), chat_id=self.chat_id)

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)
        return SimpleNamespace(message_id=300 + len(self.documents), chat_id=self.chat_id)

    async def reply_video(self, **kwargs):
        self.videos.append(kwargs)
        return SimpleNamespace(message_id=400 + len(self.videos), chat_id=self.chat_id)


class CaptureUpdate:
    def __init__(self, user_id=19660):
        self.effective_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)


def _branch_name():
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()
    except Exception:
        return ""


def _is_m6t_scope():
    branch = _branch_name().lower()
    return "p0-19m6t" in branch or "final-video-only" in branch or "no-public-audio-fallback" in branch


def _fresh_job(key="p019m6t-job", *, mode=bot.VIDEO_SUBTITLE_MODE_DUB):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    acquired, job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=19660,
        chat_id=19660,
        mode=mode,
        status_panel_message_id="panel-1",
    )
    assert acquired is True
    return key, job


def test_video_dub_mp4_failure_does_not_send_public_audio_fallback_by_default(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", False)
    message = CaptureMessage()

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"internal-audio",
            video_bytes=b"",
            include_subtitle_outputs=False,
        )
    )

    assert message.audios == []
    assert message.videos == []
    assert sent["audio"] == 0
    assert sent["partial_audio_delivered"] is False
    assert sent["audio_fallback_suppressed"] is True
    assert sent["audio_artifact_internal_only"] is True
    assert sent["terminal_public_outcome_type"] == "failure"


def test_video_dub_mp4_failure_does_not_send_video_success_copy(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", False)
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB},
        {"has_audio": True, "has_video": False, "terminal_public_outcome_type": "failure"},
    )

    assert "Đã tạo video" not in text
    assert "audio tạm" not in text
    assert "chưa tạo được video hoàn chỉnh" in text


def test_audio_artifact_kept_internal_only_when_public_fallback_disabled(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", False)
    message = CaptureMessage()

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            audio_bytes=b"internal-audio",
            video_bytes=b"",
            include_subtitle_outputs=True,
        )
    )

    assert sent["partial_audio_available"] is True
    assert sent["partial_audio_delivered"] is False
    assert sent["audio_artifact_internal_only"] is True
    assert message.audios == []
    assert message.documents == []


def test_success_requires_validated_delivered_final_mp4(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", False)
    key, _job = _fresh_job("p019m6t-success-gate")

    ok = bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered")
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert ok is False
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["terminal_public_outcome_type"] == "failure"
    assert stored["success_blocked_reason"] == "missing_valid_delivered_mp4"
    assert stored["charge_status"] == "not_charged"


def test_success_blocked_when_only_audio_exists(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", False)
    key, _job = _fresh_job("p019m6t-audio-only-gate")

    ok = bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="needs_admin_review",
        terminal_artifact_type="audio_fallback",
        audio_delivery_message_id="222",
        delivery_message_id="222",
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert ok is False
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["partial_audio_delivered"] is False
    assert stored["audio_fallback_suppressed"] is True


def test_clean_failed_no_charge_sent_once_for_missing_mp4(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", False)
    key, _job = _fresh_job("p019m6t-fail-once")
    message = CaptureMessage()

    first = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="missing_valid_delivered_mp4"))
    second = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="late_error"))
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert first["sent"] is True
    assert second["suppressed"] is True
    assert len(message.texts) == 1
    assert "chưa tạo được video hoàn chỉnh" in message.texts[0]
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["public_error_sent_count"] == 1
    assert stored["success_sent_count"] == 0


def test_terminal_state_persisted_not_running_after_failed_no_charge(monkeypatch):
    captured = {}
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: captured.setdefault("payload", dict(payload)) or payload)
    job = {
        "internal_job_id": "DUB-M6T-PERSIST",
        "job_id": "M6TPERSIST1234567890",
        "public_code": "M6TPERSIST",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "product_type": bot.SUBDUB_PRODUCT_TYPE_DUB_ONLY,
        "status": "running",
        "terminal_state": "failed_no_charge",
        "progress_percent": 90,
    }

    assert bot.persist_subtitle_dub_pipeline_job_snapshot("p019m6t-persist", job, reason="test") is True

    assert captured["payload"]["status"] == "failed_no_charge"
    assert captured["payload"]["terminal_state"] == "failed_no_charge"


def test_progress_debug_reads_terminal_persisted_state_not_running_90(monkeypatch):
    persisted = {
        "feature": "subtitle_dub",
        "internal_job_id": "DUB-M6T-PROGRESS",
        "job_id": "2F5F0958FA1234567890",
        "public_code": "2F5F0958FA",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "product_type": bot.SUBDUB_PRODUCT_TYPE_DUB_ONLY,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "progress_percent": 95,
        "terminal_public_outcome_type": "failure",
    }
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "subdub_engine_async_persisted_scan", lambda limit=240: [persisted])

    text = bot.product_progress_debug_text("2f5f0958fa")

    assert "Terminal: <code>failed_no_charge</code>" in text
    assert "persisted_job_status: <code>failed_no_charge</code>" in text
    assert "persisted_job_progress: <code>95%</code>" in text
    assert "persisted_job_status: <code>running</code>" not in text


def test_subdub_delivery_debug_never_badrequest_without_arg(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    update = CaptureUpdate()
    context = SimpleNamespace(args=[])

    asyncio.run(bot.cmd_subdub_delivery_debug(update, context))

    assert update.message.texts
    assert "Cách dùng" in update.message.texts[0]
    assert GENERIC_ERROR not in update.message.texts[0]


def test_subdub_delivery_debug_never_badrequest_for_partial_audio_shape():
    payload = {
        "feature": "subtitle_dub",
        "internal_job_id": "DUB-3574A74F",
        "job_id": "2F5F0958FA1234567890",
        "public_code": "2F5F0958FA",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "product_type": bot.SUBDUB_PRODUCT_TYPE_DUB_ONLY,
        "terminal_state": "failed_no_charge",
        "status": "failed_no_charge",
        "audio_bytes": 12345,
        "partial_audio_available": True,
        "partial_audio_delivered": False,
        "audio_fallback_suppressed": True,
        "audio_artifact_internal_only": True,
        "pipeline_blocker": "BadRequest: failed to send audio",
    }

    text = bot.subdub_delivery_debug_text(payload, "2F5F0958FA")

    assert "SUBDUB DELIVERY DEBUG" in text
    assert "audio_delivery_bad_request" in text
    assert "2F5F0958FA" in text
    assert GENERIC_ERROR not in text


def test_subdub_delivery_debug_shows_audio_fallback_suppressed():
    text = bot.subdub_delivery_debug_text(
        {
            "public_code": "2F5F0958FA",
            "internal_job_id": "DUB-3574A74F",
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "product_type": bot.SUBDUB_PRODUCT_TYPE_DUB_ONLY,
            "audio_fallback_public_enabled": False,
            "audio_fallback_suppressed": True,
            "audio_artifact_internal_only": True,
            "success_blocked_reason": "missing_valid_delivered_mp4",
        },
        "2F5F0958FA",
    )

    assert "audio_fallback_public_enabled: <code>no</code>" in text
    assert "audio_fallback_suppressed: <code>yes</code>" in text
    assert "audio_artifact_internal_only: <code>yes</code>" in text
    assert "missing_valid_delivered_mp4" in text


def test_badrequest_classified_safely():
    assert bot.subdub_classify_bad_request("BadRequest: message is not modified", stage="panel_edit") == "panel_edit_bad_request"
    assert bot.subdub_classify_bad_request("BadRequest: failed to send audio", stage="delivery") == "audio_delivery_bad_request"
    assert bot.subdub_classify_bad_request("BadRequest: failed to send video", stage="delivery") == "video_delivery_bad_request"
    assert bot.subdub_classify_bad_request("BadRequest", stage="subdub_delivery_debug") == "debug_render_bad_request"
    assert bot.subdub_classify_bad_request("BadRequest: telegram send failed", stage="delivery") == "telegram_send_bad_request"


def test_subdub_voice_debug_reads_runtime_voice_config(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")

    found = bot.subdub_merge_debug_job({
        "internal_job_id": "DUB-VOICE-M6T",
        "public_code": "VOICE6T",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "product_type": bot.SUBDUB_PRODUCT_TYPE_DUB_ONLY,
    })
    text = bot.subdub_voice_debug_text(found)

    assert found["default_female_configured"] is True
    assert found["default_male_configured"] is True
    assert found["default_voices_distinct"] is True
    assert found["voice_config_source"] == "subdub_runtime_default_voice_config"
    assert "voice_config_blocker: <code>-</code>" in text


def test_subdub_female_voice_prefers_voice_engine_default_over_stale_male(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "voice_kind": "default_female",
        "voice_style": "Giọng nữ mặc định",
        "voice_id": "male-real-voice",
    }

    voice_id = bot.resolve_video_dub_tts_voice_id(19660, state)

    assert voice_id == "female-real-voice"
    assert state["selected_voice_gender"] == "female"
    assert state["tts_payload_voice_id"] == "female-real-voice"
    assert state["voice_fallback_used"] is False


def test_no_product_video_music_payos_pricing_db_changes():
    if not _is_m6t_scope():
        pytest.skip("SubDub M6T scope guard is not active for this branch")

    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "tests/test_p0_17b_subtitle_translation_dubbing.py",
        "tests/test_p0_17b12_2_live_hotfix_contract.py",
        "tests/test_p0_17b6_2_final_product_pipeline.py",
        "tests/test_p0_18q_video_ui_polish_back_routing_5_option_buttons.py",
        "tests/test_p0_19b3_subtitle_dub_clean_product_ux_two_path_flow.py",
        "tests/test_p0_19b7_restore_pr38_subtitle_dub_engine_no_subtitle_branch.py",
        "tests/test_p0_19d_live_subtitle_dub_blackbox_engine_fix_only.py",
        "tests/test_p0_19g_professional_subtitle_dub_overlay_voice_delivery.py",
        "tests/test_p0_19h_restore_subdub_engine_professional_status.py",
        "tests/test_p0_19j_restore_subdub_real_video_engine_delivery.py",
        "tests/test_p0_19m5_complete_subdub_status_style_dub_voice_audio_delivery_sync.py",
        "tests/test_p0_19m6a_subdub_one_terminal_public_outcome_late_error_duplicate_fix.py",
        "tests/test_p0_19m6r_subdub_live_runtime_terminal_outcome_path_fix.py",
        "tests/test_p0_19m6s_subdub_live_job_registry_partial_audio_debug_fix.py",
        "tests/test_p0_19m6t_subdub_final_video_only_delivery_no_public_audio_fallback.py",
    }
    assert changed <= allowed
