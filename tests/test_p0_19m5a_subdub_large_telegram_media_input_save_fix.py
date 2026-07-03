import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

import bot


VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42-p019m5a-video" + b"x" * 1024


def _current_branch_name():
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return subprocess.check_output(
        ["git", "branch", "--show-current"],
        text=True,
        encoding="utf-8",
    ).strip()


def _is_subdub_m5a_scope():
    branch = _current_branch_name().lower()
    branch_tokens = (
        "p0-19m5a",
        "large-telegram-media",
        "telegram-media-input-save",
    )
    return any(token in branch for token in branch_tokens)


class CaptureMessage:
    def __init__(self, chat_id=919950):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})
        return SimpleNamespace(message_id=len(self.outputs), chat_id=self.chat_id)


class CaptureQuery:
    def __init__(self, user_id=919950):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)


class TooBigTelegramFile:
    async def download_as_bytearray(self):
        raise RuntimeError("File is too big")


class TooBigTelegramBot:
    async def get_file(self, file_id):
        assert file_id
        return TooBigTelegramFile()


def _context(fake_bot=None):
    return SimpleNamespace(bot=fake_bot or TooBigTelegramBot())


def _state(**extra):
    mode = extra.pop("mode", bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    return {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        "source_file_id": "tg-large-p019m5a",
        "video_file_id": "tg-large-p019m5a",
        "source_file_unique_id": "unique-large-p019m5a",
        "source_file_name": "large_clip.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
        "video_duration": "60",
        "source_duration": "60",
        "video_file_size": 32 * 1024 * 1024,
        "source_file_size": 32 * 1024 * 1024,
        "target_language": "Tiếng Việt",
        **extra,
    }


def _create_job(key="p019m5a-live", user_id=919950, mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    _, job = bot.acquire_subtitle_dub_pipeline_job(key, user_id=user_id, chat_id=user_id, mode=mode)
    return key, job


def _run_too_big_pipeline(tmp_path, monkeypatch, *, key="p019m5a-live", user_id=919950):
    key, job = _create_job(key=key, user_id=user_id)
    async def _noop_progress(*_args, **_kwargs):
        return None
    monkeypatch.setattr(bot, "subdub_send_progress_update", _noop_progress)
    state = _state(_pipeline_job_key=key, _pipeline_job_id=job["job_id"], _pipeline_workspace=str(tmp_path))
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(user_id),
            _context(),
            state,
            "vi",
            admin_interactive_confirm=True,
        )
    )
    return key, job, result


def test_60s_video_passes_duration_gate_but_large_download_failure_fails_clean_no_charge(tmp_path, monkeypatch):
    key, job, result = _run_too_big_pipeline(tmp_path, monkeypatch)
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert result["ok"] is False
    assert result["terminal_state"] == "failed_no_charge"
    assert result["debug_job"]["duration_gate_result"] == "pass_long"
    assert result["debug_job"]["long_media_allowed"] is True
    assert result["debug_job"]["pipeline_blocker"] == "large_telegram_download_unsupported"
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["charge_status"] == "not_charged"
    assert stored["no_charge_reason"] == "large_telegram_download_unsupported"
    assert job["job_id"]


def test_file_too_big_never_starts_asr_translation_tts_mux(tmp_path, monkeypatch):
    _, _, result = _run_too_big_pipeline(tmp_path, monkeypatch, key="p019m5a-no-engine")
    debug = result["debug_job"]

    assert debug["pipeline_attempted"] is False
    assert debug["asr_started"] is False
    assert debug["translation_started"] is False
    assert debug["tts_started"] is False
    assert debug["mux_started"] is False
    assert debug["delivery_attempted"] is False


def test_file_too_big_terminalizes_status_panel_and_stops_refresh(tmp_path, monkeypatch):
    key, job, result = _run_too_big_pipeline(tmp_path, monkeypatch, key="p019m5a-terminal")
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    snapshot = bot.progress_auto_refresh_snapshot("subdub", job["job_id"], stored, "vi")

    assert result["debug_job"]["status_panel_terminalized"] is True
    assert result["debug_job"]["refresh_stopped_after_terminal"] is True
    assert stored["status_panel_terminalized"] is True
    assert stored["refresh_stopped_after_terminal"] is True
    assert snapshot["terminal_state"] == "failed_no_charge"
    assert snapshot["percent"] >= 90


def test_file_too_big_public_message_no_debug_terms(tmp_path, monkeypatch):
    _, _, result = _run_too_big_pipeline(tmp_path, monkeypatch, key="p019m5a-public")
    text = result["text"]
    panel = bot.product_progress_status_from_job_text("subdub", result["debug_job"], result["debug_job"]["job_id"], "vi")

    assert "file quá lớn" in text
    assert "Hệ thống chưa trừ Xu" in text
    public = (text + "\n" + panel).lower()
    for forbidden in ("api", "provider", "traceback", "ffmpeg", "mux", "asr", "tts", "file is too big"):
        assert forbidden not in public


def test_input_save_failure_does_not_create_new_job_on_refresh(tmp_path, monkeypatch):
    key, job, _ = _run_too_big_pipeline(tmp_path, monkeypatch, key="p019m5a-refresh")
    before = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)
    found = bot.subdub_progress_job_for_user("#" + job["job_id"].lower(), 919950)
    after = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)

    assert after == before
    assert found["job_key"] == key
    assert found["terminal_state"] == "failed_no_charge"


def test_supported_large_media_intake_path_saves_file_and_allows_pipeline(tmp_path):
    source = tmp_path / "large_media_intake.mp4"
    source.write_bytes(VIDEO_BYTES)
    state = _state(
        _pipeline_large_media_local_path=str(source),
        _pipeline_workspace=str(tmp_path / "workspace"),
    )
    (tmp_path / "workspace").mkdir()
    result = asyncio.run(bot.video_dubbing_save_input_for_pipeline(_context(), state, str(tmp_path / "workspace")))
    gate = bot.video_dubbing_product_gate_matrix(
        919950,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        state,
        access={"allowed": True, "readiness": {"configured": True, "public_ready": True, "technical_missing": [], "public_blockers": []}},
        input_save=result,
    )

    assert result["ok"] is True
    assert result["file_saved"] is True
    assert result["telegram_download_method"] == "local_path_override"
    assert result["large_media_intake_supported"] is True
    assert gate["input_file_saved"] is True
    assert gate["input_file_exists"] is True


def test_missing_large_media_intake_config_reports_actionable_blocker(tmp_path):
    result = asyncio.run(bot.video_dubbing_save_input_for_pipeline(_context(), _state(), str(tmp_path)))
    debug = bot.subdub_input_save_debug_fields(result, _state())

    assert result["ok"] is False
    assert result["input_save_blocker"] == "large_telegram_download_unsupported"
    assert result["input_save_public_action"] == "send_smaller_or_supported_upload"
    assert debug["telegram_download_limit_hit"] is True
    assert debug["large_media_intake_supported"] is False


def test_duration_300_gate_unchanged():
    gate = bot.subdub_duration_gate_payload({"duration": 300}, {}, is_admin=False)
    assert gate["duration_gate_result"] in {"pass", "pass_long"}
    assert gate["duration_limit"] >= 300


def test_over_300_still_fails_clean_no_charge():
    gate = bot.subdub_duration_gate_payload({"duration": 301}, {}, is_admin=False)
    text = bot.subdub_duration_over_limit_text("vi")

    assert gate["duration_gate_result"] == "fail_over_limit"
    assert "TOAN AAS chưa trừ Xu" in text
    assert "provider" not in text.lower()


def test_no_payos_wallet_music_product_video_pricing_db_changes():
    if not _is_subdub_m5a_scope():
        pytest.skip("SubDub M5A scope guard is not active for this branch")

    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "tests/test_p0_18s2j_product_video_remote_worker_provider_env_namespace_hydration_fix.py",
        "tests/test_p0_19m4b_subdub_long_video_over_30s_progress_duration_gate_fix.py",
        "tests/test_p0_19m5a_subdub_large_telegram_media_input_save_fix.py",
        "tests/test_p0_19m8r_selective_rollback_subdub_m8_keep_international_subtitle_only.py",
    }
    assert changed <= allowed
    disallowed_tokens = ("payos", "wallet", "pricing", "finance", "music", "suno", "video_provider", "remote_worker.py", "local_worker.py")
    assert not any(any(token in path.lower() for token in disallowed_tokens) for path in changed)
