from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import bot


OWNER_ID = 7_126_457_028
JOB_ID = "211844aa34788db33757"
SOURCE_SHA256 = "83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e"


def _seed_job(tmp_path, monkeypatch):
    workspace = tmp_path / JOB_ID
    workspace.mkdir()
    source = workspace / "test_nhi_u_gi_ng.mp4"
    source_bytes = b"authorized-multi-source"
    source.write_bytes(source_bytes)
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    job_key = (
        f"{OWNER_ID}|{OWNER_ID}|AgAD9CsAAkGRoVQ|"
        "subtitle_plus_dub|auto_multi_speaker"
    )
    job = {
        "feature": "subtitle_dub",
        "internal_job_id": JOB_ID,
        "job_id": JOB_ID,
        "job_key": job_key,
        "user_id": OWNER_ID,
        "chat_id": OWNER_ID,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "charge_status": "not_charged",
        "charged_xu": 0,
        "output_sent": False,
        "delivery_attempted": False,
        "final_mp4_exists": False,
        "workspace": str(workspace),
        "input_save": {
            "path": str(source),
            "size": len(source_bytes),
            "content_type": "video/mp4",
        },
        "auto_exact_session_nonce": "recovery-session-1",
        "multi_diarization_attempted": True,
        "multi_diarization_provider": "gemini_transcribe_multi_diarization",
        "multi_diarization_status": "AUTO_CAST_UNAVAILABLE",
        "multi_diarization_detail": "gemini_multi_diarization_invalid:http=200",
        "multi_diarization_http_status": 200,
        "multi_diarization_provider_word_count": 0,
        "multi_diarization_provider_speaker_count": 0,
        "multi_diarization_mapped_speaker_count": 0,
        "provider_task_id": f"subdub:{JOB_ID}",
    }
    db_path = tmp_path / "recovery.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            note TEXT,
            updated_at TEXT,
            updated_by TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO system_settings(key,value,note,updated_at,updated_by) VALUES(?,?,?,?,?)",
        (
            f"engine_async_job:{JOB_ID}",
            json.dumps(job, ensure_ascii=False),
            "fixture",
            "2026-08-31 00:00:00",
            str(OWNER_ID),
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(
        bot,
        "subtitle_dub_workspace_path_safety",
        lambda _workspace: {"allowed": True},
    )
    monkeypatch.setattr(bot, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(bot, "SUBTITLE_DUB_PIPELINE_JOBS", {})
    return db_path, job, source, source_sha256


def test_failed_auto_multi_recovery_cas_keeps_same_job_and_wins_once(
    tmp_path,
    monkeypatch,
):
    db_path, job, _source, source_sha256 = _seed_job(tmp_path, monkeypatch)

    wrong = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256="0" * 64,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    assert wrong["ok"] is False
    assert wrong["reason"] == "source_sha256_mismatch"
    conn = sqlite3.connect(db_path)
    try:
        unchanged = json.loads(
            conn.execute(
                "SELECT value FROM system_settings WHERE key=?",
                (f"engine_async_job:{JOB_ID}",),
            ).fetchone()[0]
        )
    finally:
        conn.close()
    assert unchanged == job

    claimed = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    assert claimed["ok"] is True
    assert claimed["claimed"] is True
    recovered = claimed["job"]
    assert recovered["internal_job_id"] == JOB_ID
    assert recovered["job_id"] == JOB_ID
    assert recovered["status"] == "recovering_auto_multi"
    assert recovered["terminal_state"] == ""
    assert recovered["auto_multi_recovery_attempt_count"] == 1
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[recovered["job_key"]]["job_id"] == JOB_ID

    duplicate = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    assert duplicate["ok"] is False
    assert duplicate["reason"] == "job_not_terminal_failed_no_charge"


def test_failed_auto_multi_recovery_state_is_exact_and_not_receipt_resume(
    tmp_path,
    monkeypatch,
):
    _db_path, job, source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    job["auto_multi_recovery"] = {
        "source_sha256": source_sha256,
        "source_path": str(source),
        "target_language": "English",
        "original_volume_percent": 40,
        "dub_volume_percent": 150,
        "owner_confirmed_paid": True,
    }

    state = bot.subdub_failed_auto_multi_recovery_state(job)

    assert state["mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert state["active_flow"] == bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB
    assert state["target_language"] == "English"
    assert state["translate_requested"] == "1"
    assert state["voice_kind"] == "auto_speaker_gender"
    assert state["voice_selection_mode"] == "auto_speaker"
    assert state["auto_speaker_lane"] == "multi"
    assert state["keep_original_audio"] == "1"
    assert state["original_audio_volume_percent"] == 40
    assert state["dubbed_voice_volume_percent"] == 150
    assert state["subdub_final_confirmed"] is True
    assert state["_pipeline_source_path_override"] == str(source)
    assert state["_pipeline_workspace"] == job["workspace"]
    assert state["auto_exact_resume"] is False
    assert "auto_exact_receipt" not in state


def test_failed_auto_multi_executor_passes_same_recovery_job_to_wrapper(
    tmp_path,
    monkeypatch,
):
    _db_path, job, source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    job.update(
        {
            "status": "recovering_auto_multi",
            "terminal_state": "",
            "auto_multi_recovery": {
                "source_sha256": source_sha256,
                "source_path": str(source),
                "target_language": "English",
                "original_volume_percent": 40,
                "dub_volume_percent": 150,
                "owner_confirmed_paid": True,
            },
        }
    )
    captured = {}

    async def capture_pipeline(
        query,
        context,
        state,
        lang,
        *,
        admin_interactive_confirm=False,
        resume_job=None,
        recovery_job=None,
    ):
        captured.update(
            {
                "query": query,
                "context": context,
                "state": dict(state),
                "lang": lang,
                "admin_interactive_confirm": admin_interactive_confirm,
                "resume_job": resume_job,
                "recovery_job": dict(recovery_job or {}),
            }
        )
        return {"ok": False, "status": "fixture_stop"}

    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", capture_pipeline)
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=OWNER_ID),
        message=SimpleNamespace(chat_id=OWNER_ID),
    )

    result = asyncio.run(
        bot.execute_subdub_failed_auto_multi_recovery(
            query,
            SimpleNamespace(),
            job,
            "vi",
        )
    )

    assert result == {"ok": False, "status": "fixture_stop"}
    assert captured["recovery_job"]["internal_job_id"] == JOB_ID
    assert captured["recovery_job"]["job_id"] == JOB_ID
    assert captured["resume_job"] is None
    assert captured["admin_interactive_confirm"] is True
    assert captured["state"]["_pipeline_source_path_override"] == str(source)
    assert captured["state"]["subdub_final_confirmed"] is True


def test_failed_auto_multi_recovery_command_requires_exact_literal_and_args(
    monkeypatch,
):
    replies = []
    claims = []
    executions = []

    async def reply_text(text, **_kwargs):
        replies.append(str(text))
        return SimpleNamespace(message_id=len(replies))

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=OWNER_ID),
        message=SimpleNamespace(chat_id=OWNER_ID, reply_text=reply_text),
    )
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")

    def claim(job_id, **kwargs):
        claims.append((job_id, dict(kwargs)))
        return {
            "ok": True,
            "claimed": True,
            "job": {
                "internal_job_id": JOB_ID,
                "job_id": JOB_ID,
                "job_key": "fixture-key",
                "status": "recovering_auto_multi",
            },
        }

    async def execute(_query, _context, job, _lang):
        executions.append(dict(job))
        return {"ok": False, "status": "fixture_stop"}

    monkeypatch.setattr(bot, "claim_subdub_failed_auto_multi_recovery", claim)
    monkeypatch.setattr(bot, "execute_subdub_failed_auto_multi_recovery", execute)
    monkeypatch.setattr(
        bot,
        "update_subtitle_dub_pipeline_job",
        lambda _job_key, **fields: dict(fields),
    )

    missing_literal = SimpleNamespace(
        args=[JOB_ID, SOURCE_SHA256, "English", "40", "150"]
    )
    asyncio.run(bot.cmd_subdub_recover_failed_auto_multi(update, missing_literal))
    assert claims == []
    assert executions == []
    assert replies

    exact = SimpleNamespace(
        args=[
            JOB_ID,
            SOURCE_SHA256,
            "English",
            "40",
            "150",
            "--confirm-paid",
        ]
    )
    asyncio.run(bot.cmd_subdub_recover_failed_auto_multi(update, exact))

    assert len(claims) == 1
    assert claims[0][0] == JOB_ID
    assert claims[0][1] == {
        "owner_user_id": OWNER_ID,
        "chat_id": OWNER_ID,
        "source_sha256": SOURCE_SHA256,
        "target_language": "English",
        "original_volume_percent": 40,
        "dub_volume_percent": 150,
        "confirm_paid": True,
    }
    assert executions[0]["job_id"] == JOB_ID
