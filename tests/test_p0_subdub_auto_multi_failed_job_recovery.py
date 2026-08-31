from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import bot
import pytest


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


def test_failed_auto_multi_recovery_allows_one_empty_http_200_correction_only(
    tmp_path,
    monkeypatch,
):
    db_path, _job, _source, source_sha256 = _seed_job(tmp_path, monkeypatch)

    first = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    assert first["claimed"] is True

    failed = dict(first["job"])
    failed.update(
        {
            "status": "failed_no_charge",
            "terminal_state": "failed_no_charge",
            "charge_status": "not_charged",
            "charged_xu": 0,
            "output_sent": False,
            "delivery_attempted": False,
            "final_mp4_exists": False,
            "multi_diarization_status": "AUTO_CAST_UNAVAILABLE",
            "multi_diarization_detail": (
                "gemini_multi_diarization_invalid:http=200;status=completed"
            ),
            "multi_diarization_http_status": 200,
            "multi_diarization_provider_word_count": 0,
            "multi_diarization_provider_speaker_count": 0,
            "multi_diarization_mapped_speaker_count": 0,
            "multi_diarization_raw_annotation_count": 0,
            "multi_diarization_terminal_empty": True,
            "artifact_started": False,
            "output_validated": False,
            "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        }
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE system_settings SET value=? WHERE key=?",
            (
                json.dumps(failed, ensure_ascii=False),
                f"engine_async_job:{JOB_ID}",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    correction = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )

    assert correction["ok"] is True
    assert correction["claimed"] is True
    assert correction["job"]["internal_job_id"] == JOB_ID
    assert correction["job"]["auto_multi_recovery_attempt_count"] == 2
    assert correction["job"]["auto_multi_recovery_correction_attempt_count"] == 1

    failed_again = dict(correction["job"])
    failed_again.update(failed)
    failed_again["auto_multi_recovery_attempt_count"] = 2
    failed_again["auto_multi_recovery_correction_attempt_count"] = 1
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE system_settings SET value=? WHERE key=?",
            (
                json.dumps(failed_again, ensure_ascii=False),
                f"engine_async_job:{JOB_ID}",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    blocked = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )

    assert blocked["ok"] is False
    assert blocked["reason"] == "recovery_already_used"


def _persist_recovery_job(db_path, job):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE system_settings SET value=? WHERE key=?",
            (
                json.dumps(job, ensure_ascii=False),
                f"engine_async_job:{JOB_ID}",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _terminal_empty_recovery_failure(job):
    failed = dict(job)
    failed.update(
        {
            "status": "failed_no_charge",
            "terminal_state": "failed_no_charge",
            "charge_status": "not_charged",
            "charged_xu": 0,
            "output_sent": False,
            "delivery_attempted": False,
            "artifact_started": False,
            "final_mp4_exists": False,
            "output_validated": False,
            "multi_diarization_attempted": True,
            "multi_diarization_provider": "gemini_transcribe_multi_diarization",
            "multi_diarization_status": "AUTO_CAST_UNAVAILABLE",
            "multi_diarization_detail": (
                "gemini_multi_diarization_invalid:http=200;status=completed"
            ),
            "multi_diarization_http_status": 200,
            "multi_diarization_provider_word_count": 0,
            "multi_diarization_provider_speaker_count": 0,
            "multi_diarization_mapped_speaker_count": 0,
            "multi_diarization_raw_annotation_count": 0,
            "multi_diarization_terminal_empty": True,
            "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        }
    )
    return failed


@pytest.mark.parametrize(
    ("field", "replacement", "delete"),
    (
        ("charged_xu", None, True),
        ("charged_xu", 1, False),
        ("charge_status", None, True),
        ("charge_status", "charged", False),
        ("output_sent", None, True),
        ("output_sent", True, False),
        ("delivery_attempted", None, True),
        ("delivery_attempted", True, False),
        ("artifact_started", None, True),
        ("artifact_started", True, False),
        ("final_mp4_exists", None, True),
        ("final_mp4_exists", True, False),
        ("output_validated", None, True),
        ("output_validated", True, False),
    ),
)
def test_failed_auto_multi_correction_requires_explicit_no_output_evidence(
    tmp_path,
    monkeypatch,
    field,
    replacement,
    delete,
):
    db_path, _job, _source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    first = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    failed = _terminal_empty_recovery_failure(first["job"])
    if delete:
        failed.pop(field)
    else:
        failed[field] = replacement
    _persist_recovery_job(db_path, failed)

    correction = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )

    assert correction["ok"] is False
    assert correction["reason"] == "job_not_safe_to_recover"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("final_mp4_path", "/tmp/final.mp4"),
        ("video_delivery_message_id", "991"),
        ("final_video_message_id", "992"),
        ("delivery_message_id", "993"),
    ),
)
def test_failed_auto_multi_correction_rejects_artifact_or_delivery_evidence(
    tmp_path,
    monkeypatch,
    field,
    value,
):
    db_path, _job, _source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    first = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    failed = _terminal_empty_recovery_failure(first["job"])
    failed[field] = value
    _persist_recovery_job(db_path, failed)

    correction = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )

    assert correction["ok"] is False
    assert correction["reason"] == "job_not_safe_to_recover"


def test_failed_auto_multi_correction_rejects_nonempty_rejected_annotations(
    tmp_path,
    monkeypatch,
):
    db_path, _job, _source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    first = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    failed = _terminal_empty_recovery_failure(first["job"])
    failed["multi_diarization_raw_annotation_count"] = 2
    failed["multi_diarization_terminal_empty"] = False
    _persist_recovery_job(db_path, failed)

    correction = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )

    assert correction["ok"] is False
    assert correction["reason"] == "recovery_already_used"


def test_failed_auto_multi_legacy_observability_gap_needs_literal_and_wins_once(
    tmp_path,
    monkeypatch,
):
    db_path, _job, _source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    first = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    failed = _terminal_empty_recovery_failure(first["job"])
    failed.pop("multi_diarization_raw_annotation_count")
    failed.pop("multi_diarization_terminal_empty")
    _persist_recovery_job(db_path, failed)

    ordinary = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    assert ordinary["ok"] is False
    assert ordinary["reason"] == "recovery_already_used"

    override = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_legacy_observability_gap=True,
    )
    assert override["ok"] is True
    assert override["claimed"] is True
    assert override["job"]["internal_job_id"] == JOB_ID
    assert override["job"]["auto_multi_recovery_attempt_count"] == 2
    assert override["job"]["auto_multi_recovery_correction_attempt_count"] == 1
    assert override["job"]["auto_multi_recovery_observability_override_used"] is True
    assert (
        override["job"]["auto_multi_recovery_observability_authority"]
        == "owner_literal_legacy_gap"
    )

    failed_again = _terminal_empty_recovery_failure(override["job"])
    failed_again.pop("multi_diarization_raw_annotation_count")
    failed_again.pop("multi_diarization_terminal_empty")
    _persist_recovery_job(db_path, failed_again)
    duplicate = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_legacy_observability_gap=True,
    )
    assert duplicate["ok"] is False
    assert duplicate["reason"] == "legacy_observability_override_not_allowed"


def test_failed_auto_multi_legacy_gap_override_rejects_partial_raw_evidence(
    tmp_path,
    monkeypatch,
):
    db_path, _job, _source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    first = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
    )
    failed = _terminal_empty_recovery_failure(first["job"])
    failed.pop("multi_diarization_terminal_empty")
    _persist_recovery_job(db_path, failed)

    result = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_legacy_observability_gap=True,
    )

    assert result["ok"] is False
    assert result["reason"] == "legacy_observability_override_not_allowed"


@pytest.mark.parametrize("raw_state", ("complete", "partial"))
def test_failed_auto_multi_legacy_gap_literal_rejects_first_recovery(
    tmp_path,
    monkeypatch,
    raw_state,
):
    db_path, job, _source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    if raw_state == "complete":
        job["multi_diarization_raw_annotation_count"] = 0
        job["multi_diarization_terminal_empty"] = True
    else:
        job["multi_diarization_raw_annotation_count"] = 0
    _persist_recovery_job(db_path, job)

    result = bot.claim_subdub_failed_auto_multi_recovery(
        JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=source_sha256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_legacy_observability_gap=True,
    )

    assert result["ok"] is False
    assert result["reason"] == "legacy_observability_override_not_allowed"


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
        "allow_legacy_observability_gap": False,
    }
    assert executions[0]["job_id"] == JOB_ID

    legacy = SimpleNamespace(
        args=[
            JOB_ID,
            SOURCE_SHA256,
            "English",
            "40",
            "150",
            "--confirm-paid",
            "--confirm-observability-gap",
        ]
    )
    asyncio.run(bot.cmd_subdub_recover_failed_auto_multi(update, legacy))
    assert len(claims) == 2
    assert claims[1][1]["allow_legacy_observability_gap"] is True
    assert executions[1]["job_id"] == JOB_ID


def test_failed_auto_multi_recovery_command_edits_one_progress_panel(
    monkeypatch,
):
    sent_texts = []
    edited_texts = []

    class SentMessage:
        message_id = 901
        chat_id = OWNER_ID

        async def edit_text(self, text, **_kwargs):
            edited_texts.append(str(text))
            return self

    async def reply_text(text, **_kwargs):
        sent_texts.append(str(text))
        return SentMessage()

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=OWNER_ID),
        message=SimpleNamespace(chat_id=OWNER_ID, reply_text=reply_text),
    )
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(
        bot,
        "claim_subdub_failed_auto_multi_recovery",
        lambda *_args, **_kwargs: {
            "ok": True,
            "claimed": True,
            "job": {
                "internal_job_id": JOB_ID,
                "job_id": JOB_ID,
                "job_key": "fixture-key",
                "status": "recovering_auto_multi",
            },
        },
    )

    async def execute(query, _context, _job, _lang):
        await query.edit_message_text("progress 5")
        await query.edit_message_text("progress 20")
        await query.edit_message_text("progress 50")
        return {"ok": False, "status": "fixture_stop"}

    monkeypatch.setattr(bot, "execute_subdub_failed_auto_multi_recovery", execute)
    monkeypatch.setattr(
        bot,
        "update_subtitle_dub_pipeline_job",
        lambda _job_key, **fields: dict(fields),
    )
    context = SimpleNamespace(
        args=[
            JOB_ID,
            SOURCE_SHA256,
            "English",
            "40",
            "150",
            "--confirm-paid",
        ],
        bot=None,
    )

    asyncio.run(bot.cmd_subdub_recover_failed_auto_multi(update, context))

    assert sent_texts == ["progress 5"]
    assert edited_texts == [
        "progress 20",
        "progress 50",
        "SubDub recovery chưa tạo được MP4: <code>fixture_stop</code>",
    ]


def test_failed_auto_multi_recovery_real_progress_edit_failure_sends_no_new_panel(
    monkeypatch,
):
    sent_texts = []
    edit_attempts = []
    persisted_panel_ids = []

    class SentMessage:
        message_id = 902
        chat_id = OWNER_ID

        async def edit_text(self, text, **_kwargs):
            edit_attempts.append(str(text))
            if len(edit_attempts) == 1:
                raise RuntimeError("Timed out")
            return self

    async def reply_text(text, **_kwargs):
        sent_texts.append(str(text))
        return SentMessage()

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=OWNER_ID),
        message=SimpleNamespace(chat_id=OWNER_ID, reply_text=reply_text),
    )
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "SUBTITLE_DUB_PIPELINE_JOBS", {})
    monkeypatch.setattr(bot, "SUBDUB_PROGRESS_EDIT_LOCKS", {})
    monkeypatch.setattr(
        bot,
        "claim_subdub_failed_auto_multi_recovery",
        lambda *_args, **_kwargs: {
            "ok": True,
            "claimed": True,
            "job": {
                "internal_job_id": JOB_ID,
                "job_id": JOB_ID,
                "job_key": "fixture-key",
                "status": "recovering_auto_multi",
            },
        },
    )

    def update_job(job_key, **fields):
        current = dict(bot.SUBTITLE_DUB_PIPELINE_JOBS.get(job_key) or {})
        current.update(fields)
        bot.SUBTITLE_DUB_PIPELINE_JOBS[job_key] = current
        if fields.get("status_panel_message_id"):
            persisted_panel_ids.append(str(fields["status_panel_message_id"]))
        return current

    monkeypatch.setattr(bot, "update_subtitle_dub_pipeline_job", update_job)

    async def execute(query, _context, _job, _lang):
        bot.SUBTITLE_DUB_PIPELINE_JOBS["fixture-key"] = {
            "terminal_state": "",
        }
        await bot.subdub_send_progress_update(
            query,
            "fixture-key",
            JOB_ID,
            "saved_input",
        )
        await bot.subdub_send_progress_update(
            query,
            "fixture-key",
            JOB_ID,
            "extracting_audio",
        )
        await bot.subdub_send_progress_update(
            query,
            "fixture-key",
            JOB_ID,
            "transcribing",
        )
        return {"ok": False, "status": "fixture_stop"}

    monkeypatch.setattr(bot, "execute_subdub_failed_auto_multi_recovery", execute)
    context = SimpleNamespace(
        args=[
            JOB_ID,
            SOURCE_SHA256,
            "English",
            "40",
            "150",
            "--confirm-paid",
        ],
        bot=None,
    )

    asyncio.run(bot.cmd_subdub_recover_failed_auto_multi(update, context))

    assert len(sent_texts) == 1
    assert len(edit_attempts) == 3
    assert persisted_panel_ids == ["902", "902", "902"]
    assert "SubDub recovery chưa tạo được MP4" in edit_attempts[-1]
