import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

import bot


GENERIC_ERROR = "Có lỗi khi xử lý lệnh. Bot chưa trừ Xu"


class CaptureMessage:
    def __init__(self, chat_id=19660):
        self.chat_id = chat_id
        self.texts = []
        self.audios = []
        self.documents = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(str(text))
        return SimpleNamespace(message_id=100 + len(self.texts), chat_id=self.chat_id)

    async def reply_audio(self, **kwargs):
        self.audios.append(kwargs)
        return SimpleNamespace(message_id=200 + len(self.audios), chat_id=self.chat_id)

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)
        return SimpleNamespace(message_id=300 + len(self.documents), chat_id=self.chat_id)


class CaptureQuery:
    def __init__(self, data="videodub|confirm_dub", user_id=19660):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)
        self.edits = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        self.edits.append(str(text))
        return SimpleNamespace(message_id=900 + len(self.edits), chat_id=self.message.chat_id)


def _branch_name():
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()
    except Exception:
        return ""


def _is_m6s_scope():
    branch = _branch_name().lower()
    return "p0-19m6s" in branch or "partial-audio-debug" in branch


def _fresh_job(key="p019m6s-job", *, mode=bot.VIDEO_SUBTITLE_MODE_DUB):
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


def test_subdub_public_code_maps_to_internal_job_for_debug_and_progress():
    key, job = _fresh_job("p019m6s-public-code", mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    public_code = job["public_code"]

    found = bot.subtitle_dub_debug_lookup_job(public_code)
    progress = bot.product_progress_debug_text(public_code)

    assert found["job_key"] == key
    assert found["internal_job_id"] == job["internal_job_id"]
    assert found["mapped_product_type"] == bot.SUBDUB_PRODUCT_TYPE_SUBTITLE_ONLY
    assert "Product: <code>subdub</code>" in progress
    assert "multiscene_video" not in progress


def test_progress_status_debug_subdub_not_misclassified_as_multiscene_video():
    _key, job = _fresh_job("p019m6s-progress-debug", mode=bot.VIDEO_SUBTITLE_MODE_DUB)

    text = bot.product_progress_debug_text("#" + job["public_code"].lower())

    assert "Product: <code>subdub</code>" in text
    assert "mapped_product_type" in text
    assert "dub_only" in text
    assert "Product: <code>multiscene_video</code>" not in text


def test_progress_status_debug_recovers_subdub_terminal_state_from_persisted_store(monkeypatch):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    persisted = {
        "feature": "subtitle_dub",
        "internal_job_id": "DUB-3A1E32AF",
        "job_id": "69754A80581234567890",
        "public_code": "69754A8058",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "product_type": bot.SUBDUB_PRODUCT_TYPE_DUB_ONLY,
        "terminal_state": "needs_admin_review",
        "status": "partial",
        "progress_percent": 95,
        "terminal_public_outcome_type": "partial_audio_delivered",
        "partial_audio_delivered": True,
    }
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "subdub_engine_async_persisted_scan", lambda limit=240: [persisted])

    text = bot.product_progress_debug_text("69754A8058")

    assert "Product: <code>subdub</code>" in text
    assert "Terminal: <code>needs_admin_review</code>" in text
    assert "recovered_from_persisted_subdub_job: <code>yes</code>" in text


def test_large_telegram_unsupported_terminalizes_panel_failed_no_charge(monkeypatch):
    key, job = _fresh_job("p019m6s-large-panel", mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    user_id = 19660
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "process_type": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "source_file_id": "large-file",
        "video_file_id": "large-file",
        "target_language": "Tiếng Việt",
    }
    bot.set_video_dubbing_pending(user_id, "confirm", **state)

    async def fake_execute_engine(*_args, **_kwargs):
        return {
            "ok": True,
            "runner_result": {
                "ok": False,
                "status": "INPUT_SAVE_FAILED",
                "text": bot.subdub_large_telegram_media_public_text("vi"),
                "detail": "large_telegram_download_unsupported",
                "debug_job": {
                    "pipeline_blocker": "large_telegram_download_unsupported",
                    "input_save_blocker": "large_telegram_download_unsupported",
                    "job_id": job["job_id"],
                    "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                },
                "input_save": {"input_save_blocker": "large_telegram_download_unsupported"},
            },
        }

    monkeypatch.setattr(bot, "execute_engine", fake_execute_engine)
    monkeypatch.setattr(bot, "subtitle_dub_pipeline_job_key", lambda *_args, **_kwargs: key)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)

    query = CaptureQuery("videodub|final", user_id=user_id)
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace()
    asyncio.run(bot.handle_video_dubbing_callback(update, context))
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert query.edits
    assert "file quá lớn" in query.edits[-1]
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["terminal_public_outcome_type"] == "failure"
    assert stored["status_panel_terminalized"] is True
    assert stored["refresh_stopped_after_terminal"] is True
    assert stored["charge_status"] == "not_charged"


def test_large_telegram_unsupported_refresh_stops_and_no_pipeline_started():
    key, _job = _fresh_job("p019m6s-large-refresh", mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    bot.update_subtitle_dub_pipeline_job(
        key,
        status="failed",
        terminal_state="failed_no_charge",
        pipeline_attempted=False,
        pipeline_blocker="large_telegram_download_unsupported",
        input_save_blocker="large_telegram_download_unsupported",
        status_panel_terminalized=True,
        refresh_stopped_after_terminal=True,
        charge_status="not_charged",
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    panel = bot.subdub_job_public_status_text(stored, "vi")

    assert stored["pipeline_attempted"] is False
    assert stored["status_panel_terminalized"] is True
    assert stored["refresh_stopped_after_terminal"] is True
    assert "file quá lớn" in panel


def test_partial_audio_fallback_not_sent_after_public_failure(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", True)
    key, _job = _fresh_job("p019m6s-partial-after-failure")
    message = CaptureMessage()
    asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="known_failure"))

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"audio-bytes",
            lang="vi",
            job_key=key,
        )
    )

    assert sent["partial_audio_after_failure_prevented"] is True
    assert message.audios == []
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["terminal_public_outcome_type"] == "failure"


def test_partial_audio_delivered_is_single_terminal_outcome(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", True)
    key, _job = _fresh_job("p019m6s-partial-terminal")

    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="needs_admin_review",
        terminal_artifact_type="audio_fallback",
        audio_delivery_message_id="222",
        delivery_message_id="222",
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    second = bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        video_delivery_message_id="333",
    )

    assert second is False
    assert stored["terminal_public_outcome_type"] == "partial_audio_delivered"
    assert stored["terminal_state"] == "needs_admin_review"
    assert stored["success_sent_count"] == 0
    assert stored["partial_audio_delivered"] is True
    assert stored["charge_status"] == "not_charged_partial_audio"


def test_partial_audio_copy_does_not_claim_video_completed():
    text = bot.subdub_audio_fallback_text(bot.VIDEO_SUBTITLE_MODE_DUB, "vi")
    receipt = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB},
        {"terminal_public_outcome_type": "partial_audio_delivered", "partial_audio_delivered": True},
    )

    assert "Đã tạo video" not in text
    assert "✅" not in text
    assert "Đã tạo video" not in receipt
    assert "chưa tạo được video hoàn chỉnh" in receipt


def test_full_video_success_still_uses_success_copy():
    text = bot.subdub_mode_success_text(bot.VIDEO_SUBTITLE_MODE_DUB, "vi")

    assert "Đã tạo video lồng tiếng" in text


def test_subdub_job_debug_never_silent_or_generic():
    text = bot.subtitle_dub_debug_text(bot.subdub_debug_missing_payload("missing", "subdub_job_debug"))

    assert text
    assert "job_lookup_missing" in text
    assert GENERIC_ERROR not in text


def test_subdub_delivery_debug_never_silent_or_generic():
    text = bot.subtitle_dub_debug_text(bot.subdub_debug_missing_payload("missing", "subdub_delivery_debug"))

    assert text
    assert "job_lookup_missing" in text
    assert GENERIC_ERROR not in text


def test_subdub_voice_debug_maps_public_code_to_internal_dub_job():
    key = "p019m6s-voice-map"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "feature": "subtitle_dub",
        "internal_job_id": "DUB-3A1E32AF",
        "job_id": "69754A80581234567890",
        "public_code": "69754A8058",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "product_type": bot.SUBDUB_PRODUCT_TYPE_DUB_ONLY,
        "pipeline_blocker": "BadRequest",
    }

    found = bot.subtitle_dub_debug_lookup_job("#69754a8058")
    text = bot.subdub_voice_debug_text(found)

    assert found["internal_job_id"] == "DUB-3A1E32AF"
    assert "public code" in text
    assert "69754A8058" in text
    assert "bad_request_classification" in text


def test_badrequest_classified_safely():
    assert bot.subdub_classify_bad_request("BadRequest: message is not modified", stage="panel_edit") == "panel_edit_bad_request"
    assert bot.subdub_classify_bad_request("BadRequest: failed to send audio", stage="delivery") == "audio_delivery_bad_request"
    assert bot.subdub_classify_bad_request("BadRequest", stage="tts") == "unknown_bad_request"


def test_no_product_video_music_payos_pricing_db_changes():
    if not _is_m6s_scope():
        pytest.skip("SubDub M6S scope guard is not active for this branch")

    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "tests/test_p0_19m5_complete_subdub_status_style_dub_voice_audio_delivery_sync.py",
        "tests/test_p0_19m6a_subdub_one_terminal_public_outcome_late_error_duplicate_fix.py",
        "tests/test_p0_19m6s_subdub_live_job_registry_partial_audio_debug_fix.py",
    }
    assert changed <= allowed
    disallowed = ("payos", "wallet", "pricing", "finance", "music", "suno", "video_provider", "remote_worker.py", "local_worker.py")
    assert not any(any(token in path.lower() for token in disallowed) for path in changed)
