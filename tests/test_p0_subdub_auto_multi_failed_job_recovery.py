from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace

import bot
import pytest
from scripts import recover_subdub_final_acoustic_stability as stability_repair


OWNER_ID = 7_126_457_028
JOB_ID = "211844aa34788db33757"
SOURCE_SHA256 = "83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e"
ACOUSTIC_JOB_ID = "b4cb6d5fe8a7bdfce507"
ACOUSTIC_PUBLIC_CODE = "B4CB6D5FE8"
ACOUSTIC_MODEL_SHA256 = (
    "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
)
ACOUSTIC_ALGORITHM_VERSION = "wespeaker-resnet34-fixed-vocal-v2"
DOWNLOADABLE_FILE_ID = (
    "BAACAgQAAxkBAAIBQWf-subdub-auto-multi-downloadable-file-id"
)


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
    source_file_unique_id = job_key.split("|")[2]
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
            "file_id": DOWNLOADABLE_FILE_ID,
            "file_unique_id": source_file_unique_id,
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


def _seed_exact_acoustic_job(tmp_path, monkeypatch):
    workspace = tmp_path / ACOUSTIC_JOB_ID
    workspace.mkdir()
    source = workspace / "test_nhieu_giong.mp4"
    source.write_bytes(b"hash-is-injected-exact-authorized-fixture")
    job_key = (
        f"{OWNER_ID}|{OWNER_ID}|AgADeSIAAh1tkVQ|"
        "subtitle_plus_dub|auto_multi_speaker"
    )
    source_file_unique_id = job_key.split("|")[2]
    job = {
        "feature": "subtitle_dub",
        "internal_job_id": ACOUSTIC_JOB_ID,
        "job_id": ACOUSTIC_JOB_ID,
        "public_code": ACOUSTIC_PUBLIC_CODE,
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
        "artifact_started": False,
        "final_mp4_exists": False,
        "output_validated": False,
        "workspace": str(workspace),
        "input_save": {
            "path": str(source),
            "size": source.stat().st_size,
            "content_type": "video/mp4",
            "file_id": DOWNLOADABLE_FILE_ID,
            "file_unique_id": source_file_unique_id,
        },
        "source_sha256": SOURCE_SHA256,
        "target_language": "English",
        "original_audio_volume_percent": 40,
        "dubbed_voice_volume_percent": 150,
        "auto_exact_session_nonce": "acoustic-recovery-session",
        "multi_diarization_attempted": True,
        "multi_diarization_provider": "gemini_transcribe_multi_diarization",
        "multi_diarization_status": "PASS",
        "multi_diarization_parse_rejection": "",
        "multi_diarization_http_status": 200,
        "multi_diarization_raw_annotation_count": 149,
        "multi_diarization_provider_word_count": 147,
        "multi_diarization_provider_speaker_count": 5,
        "multi_diarization_mapped_speaker_count": 0,
        "auto_multi_recovery_attempt_count": 3,
        "auto_multi_recovery_correction_attempt_count": 2,
        "auto_multi_recovery_crosswalk_correction_used": True,
        "auto_multi_recovery": {
            "source_sha256": SOURCE_SHA256,
            "source_path": str(source),
            "source_file_id": DOWNLOADABLE_FILE_ID,
            "source_file_unique_id": source_file_unique_id,
            "target_language": "English",
            "original_volume_percent": 40,
            "dub_volume_percent": 150,
            "owner_confirmed_paid": True,
        },
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "provider_task_id": f"subdub:{ACOUSTIC_JOB_ID}",
    }
    db_path = tmp_path / "acoustic-recovery.db"
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
            f"engine_async_job:{ACOUSTIC_JOB_ID}",
            json.dumps(job, ensure_ascii=False),
            "fixture",
            "2026-09-01 00:00:00",
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
    monkeypatch.setattr(bot, "_subdub_sha256_file", lambda _path: SOURCE_SHA256)
    monkeypatch.setattr(bot, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(bot, "SUBTITLE_DUB_PIPELINE_JOBS", {})
    return db_path, job, source


def exact_acoustic_preflight():
    return {
        "ok": True,
        "status": "PASS",
        "model_sha256": ACOUSTIC_MODEL_SHA256,
        "algorithm_version": ACOUSTIC_ALGORITHM_VERSION,
    }


def test_exact_acoustic_recovery_claims_same_job_once_and_blocks_attempt_five(
    tmp_path,
    monkeypatch,
):
    db_path, job, source = _seed_exact_acoustic_job(tmp_path, monkeypatch)
    before_count = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM system_settings"
    ).fetchone()[0]

    claimed = bot.claim_subdub_failed_auto_multi_recovery(
        ACOUSTIC_JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=SOURCE_SHA256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_acoustic_recovery=True,
        acoustic_preflight=exact_acoustic_preflight,
    )

    assert claimed["ok"] is True
    assert claimed["claimed"] is True
    recovered = claimed["job"]
    assert recovered["internal_job_id"] == ACOUSTIC_JOB_ID
    assert recovered["public_code"] == ACOUSTIC_PUBLIC_CODE
    assert recovered["job_key"] == job["job_key"]
    assert recovered["workspace"] == str(source.parent)
    assert recovered["auto_multi_recovery_attempt_count"] == 4
    assert recovered["auto_multi_recovery_correction_attempt_count"] == 3
    assert recovered["auto_multi_acoustic_recovery_used"] is True
    assert recovered["auto_multi_acoustic_backend"] == (
        "local_wespeaker_resnet34_fixed_vocal"
    )
    assert recovered["auto_multi_acoustic_model_sha256"] == ACOUSTIC_MODEL_SHA256
    assert recovered["auto_multi_acoustic_algorithm_version"] == (
        ACOUSTIC_ALGORITHM_VERSION
    )
    assert recovered["auto_multi_recovery"]["source_file_id"] == (
        DOWNLOADABLE_FILE_ID
    )
    assert recovered["auto_multi_recovery"]["source_file_unique_id"] == (
        job["job_key"].split("|")[2]
    )
    after_count = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM system_settings"
    ).fetchone()[0]
    assert after_count == before_count == 1

    terminal = dict(recovered)
    terminal.update(
        {
            "status": "failed_no_charge",
            "terminal_state": "failed_no_charge",
            "lifecycle_state": "failed_no_charge",
            "current_stage": "failed_no_charge",
            "progress_stage": "failed_no_charge",
            "charge_status": "not_charged",
            "charged_xu": 0,
            "output_sent": False,
            "delivery_attempted": False,
            "artifact_started": False,
            "final_mp4_exists": False,
            "output_validated": False,
        }
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (
            json.dumps(terminal, ensure_ascii=False),
            f"engine_async_job:{ACOUSTIC_JOB_ID}",
        ),
    )
    conn.commit()
    conn.close()

    duplicate = bot.claim_subdub_failed_auto_multi_recovery(
        ACOUSTIC_JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=SOURCE_SHA256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_acoustic_recovery=True,
        acoustic_preflight=exact_acoustic_preflight,
    )

    assert duplicate["ok"] is False
    assert duplicate["reason"] == "recovery_already_used"
    stored = json.loads(
        sqlite3.connect(db_path).execute(
            "SELECT value FROM system_settings WHERE key=?",
            (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
        ).fetchone()[0]
    )
    assert stored == terminal


def test_exact_acoustic_recovery_accepts_nested_durable_selection_authority(
    tmp_path,
    monkeypatch,
):
    db_path, job, _source = _seed_exact_acoustic_job(tmp_path, monkeypatch)
    for field in (
        "source_sha256",
        "target_language",
        "original_audio_volume_percent",
        "dubbed_voice_volume_percent",
    ):
        job.pop(field)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (
            json.dumps(job, ensure_ascii=False),
            f"engine_async_job:{ACOUSTIC_JOB_ID}",
        ),
    )
    conn.commit()
    conn.close()

    claimed = bot.claim_subdub_failed_auto_multi_recovery(
        ACOUSTIC_JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=SOURCE_SHA256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_acoustic_recovery=True,
        acoustic_preflight=exact_acoustic_preflight,
    )

    assert claimed["ok"] is True
    assert claimed["claimed"] is True
    assert claimed["job"]["auto_multi_recovery_attempt_count"] == 4
    assert claimed["job"]["auto_multi_acoustic_recovery_used"] is True


def test_exact_acoustic_recovery_requires_nested_durable_selection_authority(
    tmp_path,
    monkeypatch,
):
    db_path, job, _source = _seed_exact_acoustic_job(tmp_path, monkeypatch)
    job.pop("auto_multi_recovery")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (
            json.dumps(job, ensure_ascii=False),
            f"engine_async_job:{ACOUSTIC_JOB_ID}",
        ),
    )
    conn.commit()
    old_value = conn.execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    conn.close()

    claimed = bot.claim_subdub_failed_auto_multi_recovery(
        ACOUSTIC_JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=SOURCE_SHA256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_acoustic_recovery=True,
        acoustic_preflight=exact_acoustic_preflight,
    )

    assert claimed["ok"] is False
    assert claimed["reason"] == "acoustic_recovery_not_allowed"
    stored = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert stored == old_value


def test_exact_acoustic_preflight_fails_before_database_transaction(
    monkeypatch,
):
    calls = []

    def forbidden_db():
        calls.append("db")
        raise AssertionError("preflight must precede BEGIN IMMEDIATE")

    monkeypatch.setattr(bot, "db_connect", forbidden_db)

    result = bot.claim_subdub_failed_auto_multi_recovery(
        ACOUSTIC_JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=SOURCE_SHA256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_acoustic_recovery=True,
        acoustic_preflight=lambda: {"ok": False, "status": "FAIL"},
    )

    assert result["ok"] is False
    assert result["reason"] == "acoustic_preflight_failed"
    assert calls == []


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("public_code", "WRONGCODE", "acoustic_recovery_not_allowed"),
        ("user_id", OWNER_ID + 1, "acoustic_recovery_not_allowed"),
        ("chat_id", OWNER_ID + 1, "acoustic_recovery_not_allowed"),
        ("job_key", "wrong|route", "acoustic_recovery_not_allowed"),
        ("source_sha256", "0" * 64, "acoustic_recovery_not_allowed"),
        ("target_language", "Vietnamese", "acoustic_recovery_not_allowed"),
        ("original_audio_volume_percent", 39, "acoustic_recovery_not_allowed"),
        ("dubbed_voice_volume_percent", 149, "acoustic_recovery_not_allowed"),
        ("auto_multi_recovery_attempt_count", 2, "acoustic_recovery_not_allowed"),
        ("auto_multi_recovery_correction_attempt_count", 1, "acoustic_recovery_not_allowed"),
        ("auto_multi_recovery_crosswalk_correction_used", False, "acoustic_recovery_not_allowed"),
        ("auto_multi_acoustic_recovery_used", True, "recovery_already_used"),
        ("status", "delivered", "job_not_safe_to_recover"),
        ("terminal_state", "delivered", "job_not_safe_to_recover"),
        ("charged_xu", 1, "job_not_safe_to_recover"),
        ("charge_status", "charged", "job_not_safe_to_recover"),
        ("output_sent", True, "job_not_safe_to_recover"),
        ("artifact_started", True, "job_not_safe_to_recover"),
        ("final_mp4_path", "/tmp/existing.mp4", "job_not_safe_to_recover"),
    ),
)
def test_exact_acoustic_recovery_rejects_every_mutated_authority_without_write(
    tmp_path,
    monkeypatch,
    field,
    value,
    reason,
):
    db_path, job, _source = _seed_exact_acoustic_job(tmp_path, monkeypatch)
    job[field] = value
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (
            json.dumps(job, ensure_ascii=False),
            f"engine_async_job:{ACOUSTIC_JOB_ID}",
        ),
    )
    conn.commit()
    old_value = conn.execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    conn.close()

    result = bot.claim_subdub_failed_auto_multi_recovery(
        ACOUSTIC_JOB_ID,
        owner_user_id=OWNER_ID,
        chat_id=OWNER_ID,
        source_sha256=SOURCE_SHA256,
        target_language="English",
        original_volume_percent=40,
        dub_volume_percent=150,
        confirm_paid=True,
        allow_acoustic_recovery=True,
        acoustic_preflight=exact_acoustic_preflight,
    )

    assert result["ok"] is False
    assert result["reason"] == reason
    stored = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert stored == old_value


def test_exact_acoustic_recovery_concurrent_claim_has_one_cas_winner(
    tmp_path,
    monkeypatch,
):
    db_path, _job, _source = _seed_exact_acoustic_job(tmp_path, monkeypatch)
    barrier = threading.Barrier(2)

    def claim():
        barrier.wait(timeout=5.0)
        return bot.claim_subdub_failed_auto_multi_recovery(
            ACOUSTIC_JOB_ID,
            owner_user_id=OWNER_ID,
            chat_id=OWNER_ID,
            source_sha256=SOURCE_SHA256,
            target_language="English",
            original_volume_percent=40,
            dub_volume_percent=150,
            confirm_paid=True,
            allow_acoustic_recovery=True,
            acoustic_preflight=exact_acoustic_preflight,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: claim(), range(2)))

    winners = [result for result in results if result.get("claimed") is True]
    losers = [result for result in results if result.get("claimed") is not True]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0]["reason"] in {
        "recovery_already_used",
        "recovery_cas_lost",
    }
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM system_settings").fetchone()[0] == 1
        stored = json.loads(
            conn.execute(
                "SELECT value FROM system_settings WHERE key=?",
                (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
            ).fetchone()[0]
        )
    finally:
        conn.close()
    assert stored["auto_multi_recovery_attempt_count"] == 4
    assert stored["auto_multi_recovery_correction_attempt_count"] == 3
    assert stored["auto_multi_acoustic_recovery_used"] is True


def test_stability_repair_rearms_same_fourth_attempt_once(tmp_path, monkeypatch):
    db_path, job, _source = _seed_exact_acoustic_job(tmp_path, monkeypatch)
    job.update({
        "auto_multi_recovery_attempt_count": 4,
        "auto_multi_recovery_correction_attempt_count": 3,
        "auto_multi_acoustic_recovery_used": True,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
    })
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (json.dumps(job, ensure_ascii=False), f"engine_async_job:{ACOUSTIC_JOB_ID}"),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(stability_repair.app, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(stability_repair.app, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(stability_repair.app, "SUBTITLE_DUB_PIPELINE_JOBS", {})

    first = stability_repair.claim_same_attempt()
    second = stability_repair.claim_same_attempt()

    assert first["claimed"] is True
    assert first["job"]["auto_multi_recovery_attempt_count"] == 4
    assert first["job"]["auto_multi_recovery_correction_attempt_count"] == 3
    assert first["job"]["auto_multi_acoustic_stability_repair_used"] is True
    assert second == {
        "ok": False,
        "claimed": False,
        "reason": "stability_repair_not_allowed",
    }


def _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch):
    db_path, job, _source = _seed_exact_acoustic_job(tmp_path, monkeypatch)
    job.update(
        {
            "auto_multi_recovery_attempt_count": 4,
            "auto_multi_recovery_correction_attempt_count": 3,
            "auto_multi_acoustic_recovery_used": True,
            "auto_multi_acoustic_stability_repair_used": True,
            "auto_multi_acoustic_backend": "local_wespeaker_resnet34_spectral",
            "auto_multi_acoustic_model_sha256": ACOUSTIC_MODEL_SHA256,
            "auto_multi_acoustic_algorithm_version": "wespeaker-resnet34-spectral-v1",
            "pipeline_started": True,
            "asr_started": False,
            "translation_started": False,
            "tts_started": False,
            "mux_started": False,
            "status": "failed_no_charge",
            "terminal_state": "failed_no_charge",
            "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        }
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (
            json.dumps(job, ensure_ascii=False),
            f"engine_async_job:{ACOUSTIC_JOB_ID}",
        ),
    )
    conn.commit()
    conn.close()
    return db_path, job


def fixed_vocal_v2_preflight():
    return {
        "ok": True,
        "status": "PASS",
        "model_sha256": ACOUSTIC_MODEL_SHA256,
        "algorithm_version": ACOUSTIC_ALGORITHM_VERSION,
        "providers": ["CPUExecutionProvider"],
    }


def _persist_fixed_vocal_job(db_path, job):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE system_settings SET value=? WHERE key=?",
            (
                json.dumps(job, ensure_ascii=False),
                f"engine_async_job:{ACOUSTIC_JOB_ID}",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _persist_translation_asr_attempt(db_path, payload):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO system_settings
               (key,value,note,updated_at,updated_by)
               VALUES(?,?,?,?,?)""",
            (
                "provider_attempt:translation_asr",
                json.dumps(payload, ensure_ascii=False),
                str(payload.get("error") or ""),
                str(payload.get("at") or ""),
                str(OWNER_ID),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _exact_duration_live_failure(job):
    return {
        **job,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "source_duration_exact": 133.37542,
        "input_duration": 134,
        "multi_diarization_attempted": True,
        "multi_diarization_provider": "gemini_transcribe_multi_diarization",
        "multi_diarization_status": "PASS",
        "multi_diarization_detail": "words=147; speakers=4",
        "multi_diarization_http_status": 200,
        "multi_diarization_provider_word_count": 147,
        "multi_diarization_provider_speaker_count": 4,
        "multi_diarization_mapped_speaker_count": 0,
        "multi_diarization_raw_annotation_count": 151,
        "multi_diarization_terminal_empty": False,
        "multi_diarization_parse_rejection": "",
        "multi_diarization_dropped_weak_word_count": 1,
        "multi_diarization_dropped_weak_speaker_count": 1,
        "multi_diarization_weak_label_filter_applied": True,
    }


def _exact_deepgram_timeout_receipt():
    return {
        "called": True,
        "provider": "deepgram",
        "route": "listen",
        "status": "DEEPGRAM_EMPTY_TRANSCRIPT",
        "error": "deepgram_timeout",
        "at": "2026-09-02 22:31:08",
    }


def _seed_context_loss_failure(tmp_path, monkeypatch):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, _job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(
        rearm.app,
        "db_connect_readonly",
        lambda: sqlite3.connect(db_path),
    )
    monkeypatch.setattr(rearm.app, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(rearm.app, "SUBTITLE_DUB_PIPELINE_JOBS", {})

    initial = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    _persist_fixed_vocal_job(db_path, _exact_duration_live_failure(initial["job"]))
    duration = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    timeout_failure = {
        **duration["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "",
        "last_error_safe": "",
        "asr_started": True,
        "translation_started": False,
        "tts_started": False,
        "mux_started": False,
        "artifact_started": False,
        "delivery_attempted": False,
        "final_mp4_exists": False,
        "output_validated": False,
        "output_sent": False,
    }
    _persist_fixed_vocal_job(db_path, timeout_failure)
    _persist_translation_asr_attempt(db_path, _exact_deepgram_timeout_receipt())
    timeout = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    assert timeout["claimed"] is True

    context_failure = {
        **timeout["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "last_error_safe": "manual required",
        "asr_started": False,
        "translation_started": False,
        "tts_started": False,
        "mux_started": False,
        "artifact_started": False,
        "delivery_attempted": False,
        "final_mp4_exists": False,
        "output_validated": False,
        "output_sent": False,
    }
    source_file_unique_id = context_failure["job_key"].split("|")[2]
    context_failure["input_save"] = {
        **dict(context_failure.get("input_save") or {}),
        "file_id": DOWNLOADABLE_FILE_ID,
        "file_unique_id": source_file_unique_id,
        "original_filename": "test_nhieu_giong.mp4",
        "transport_input_size": 9_869_032,
    }
    context_failure["auto_multi_recovery"] = {
        **dict(context_failure.get("auto_multi_recovery") or {}),
        "source_file_id": DOWNLOADABLE_FILE_ID,
        "source_file_unique_id": source_file_unique_id,
    }
    _persist_fixed_vocal_job(db_path, context_failure)
    _persist_translation_asr_attempt(
        db_path,
        {
            "called": True,
            "provider": "deepgram",
            "route": "listen",
            "status": "PASS",
            "error": "-",
            "srt_blocks": 17,
            "at": "2026-09-03 09:35:38",
        },
    )
    return rearm, db_path, context_failure


def test_context_repair_rearms_exact_consumed_timeout_job_once(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )

    repair = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert repair["claimed"] is True
    repaired = repair["job"]
    assert repaired["auto_multi_private_pipeline_context_repair_used"] is True
    assert repaired["auto_multi_recovery_attempt_count"] == 4
    assert repaired["auto_multi_recovery_correction_attempt_count"] == 3
    assert repaired["auto_multi_fixed_vocal_v2_recovery_used"] is True
    assert repaired["auto_multi_fixed_vocal_v2_duration_repair_used"] is True
    assert repaired["auto_multi_fixed_vocal_v2_asr_timeout_repair_used"] is True
    assert repaired["status"] == bot.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS
    assert repaired["terminal_state"] == ""
    assert repaired["asr_started"] is False
    assert repaired["charged_xu"] == 0
    assert repaired["charge_status"] == "not_charged"
    assert repaired["job_key"] == context_failure["job_key"]

    terminal_again = {
        **repaired,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
    }
    _persist_fixed_vocal_job(db_path, terminal_again)
    duplicate = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    assert duplicate == {
        "ok": False,
        "claimed": False,
        "reason": "fixed_vocal_v2_rearm_not_allowed",
    }


def test_original_source_repair_rearms_consumed_context_job_once(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    context = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    assert context["claimed"] is True
    failed = {
        **context["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "last_error_safe": "manual required",
        "asr_started": False,
        "translation_started": False,
        "tts_started": False,
        "mux_started": False,
        "artifact_started": False,
        "delivery_attempted": False,
        "final_mp4_exists": False,
        "output_validated": False,
        "output_sent": False,
        "multi_acoustic_failure_code": "acoustic_failure_unknown",
        "multi_acoustic_failure_word_count": 145,
        "multi_acoustic_failure_duration_ms": 134_000,
    }
    _persist_fixed_vocal_job(db_path, failed)

    repaired = rearm.claim_same_attempt(
        acoustic_preflight=fixed_vocal_v2_preflight
    )

    assert repaired["claimed"] is True
    assert repaired["job"]["auto_multi_original_acoustic_source_repair_used"] is True
    assert repaired["job"]["auto_multi_private_pipeline_context_repair_used"] is True
    assert repaired["job"]["auto_multi_recovery_attempt_count"] == 4
    assert repaired["job"]["auto_multi_recovery_correction_attempt_count"] == 3
    assert repaired["job"]["status"] == bot.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS
    assert repaired["job"]["terminal_state"] == ""
    assert repaired["job"]["charged_xu"] == 0

    duplicate_state = {
        **repaired["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
    }
    _persist_fixed_vocal_job(db_path, duplicate_state)
    duplicate = rearm.claim_same_attempt(
        acoustic_preflight=fixed_vocal_v2_preflight
    )
    assert duplicate["claimed"] is False


def _seed_acoustic_runtime_budget_failure(tmp_path, monkeypatch):
    rearm, db_path, _context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    context = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    assert context["claimed"] is True
    original_failure = {
        **context["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "last_error_safe": "manual required",
        "asr_started": False,
        "translation_started": False,
        "tts_started": False,
        "mux_started": False,
        "artifact_started": False,
        "delivery_attempted": False,
        "final_mp4_exists": False,
        "output_validated": False,
        "output_sent": False,
        "multi_acoustic_failure_code": "acoustic_failure_unknown",
        "multi_acoustic_failure_word_count": 145,
        "multi_acoustic_failure_duration_ms": 134_000,
    }
    _persist_fixed_vocal_job(db_path, original_failure)
    original = rearm.claim_same_attempt(
        acoustic_preflight=fixed_vocal_v2_preflight
    )
    assert original["claimed"] is True
    runtime_failure = {
        **original["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "last_error_safe": "manual required",
        "asr_started": False,
        "translation_started": False,
        "tts_started": False,
        "mux_started": False,
        "artifact_started": False,
        "delivery_attempted": False,
        "final_mp4_exists": False,
        "output_validated": False,
        "output_sent": False,
        "multi_acoustic_failure_code": "acoustic_failure_unknown",
        "multi_acoustic_failure_word_count": 145,
        "multi_acoustic_failure_duration_ms": 134_000,
    }
    _persist_fixed_vocal_job(db_path, runtime_failure)
    return rearm, db_path, runtime_failure


def test_acoustic_runtime_budget_repair_rearms_consumed_original_source_once(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, failure = _seed_acoustic_runtime_budget_failure(
        tmp_path,
        monkeypatch,
    )

    repaired = rearm.claim_same_attempt(
        acoustic_preflight=fixed_vocal_v2_preflight
    )

    assert repaired["claimed"] is True
    job = repaired["job"]
    assert job["auto_multi_acoustic_runtime_budget_repair_used"] is True
    assert job["auto_multi_original_acoustic_source_repair_used"] is True
    assert job["auto_multi_private_pipeline_context_repair_used"] is True
    assert job["auto_multi_recovery_attempt_count"] == 4
    assert job["auto_multi_recovery_correction_attempt_count"] == 3
    assert job["status"] == bot.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS
    assert job["terminal_state"] == ""
    assert job["asr_started"] is False
    assert job["multi_acoustic_failure_code"] == ""
    assert job["multi_acoustic_failure_word_count"] == 0
    assert job["multi_acoustic_failure_duration_ms"] == 0
    assert job["charged_xu"] == 0

    duplicate_state = {
        **job,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "multi_acoustic_failure_code": "acoustic_failure_unknown",
        "multi_acoustic_failure_word_count": 145,
        "multi_acoustic_failure_duration_ms": 134_000,
    }
    _persist_fixed_vocal_job(db_path, duplicate_state)
    duplicate = rearm.claim_same_attempt(
        acoustic_preflight=fixed_vocal_v2_preflight
    )
    assert duplicate["claimed"] is False
    assert duplicate_state["job_key"] == failure["job_key"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("charged_xu", 1),
        ("output_sent", True),
        ("multi_acoustic_failure_code", "fixed_vocal_speaker_count_unstable"),
        ("multi_acoustic_failure_word_count", 144),
    ],
)
def test_acoustic_runtime_budget_repair_rejects_mutated_authority_without_write(
    tmp_path,
    monkeypatch,
    field,
    value,
):
    rearm, db_path, failure = _seed_acoustic_runtime_budget_failure(
        tmp_path,
        monkeypatch,
    )
    mutated = {**failure, field: value}
    before = json.dumps(mutated, ensure_ascii=False, separators=(",", ":"))
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (before, f"engine_async_job:{ACOUSTIC_JOB_ID}"),
    )
    conn.commit()
    conn.close()

    result = rearm.claim_same_attempt(
        acoustic_preflight=fixed_vocal_v2_preflight
    )

    assert result["claimed"] is False
    stored = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert stored == before


def test_context_repair_rejects_second_claim_and_identity_mismatch(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    wrong = {**context_failure, "public_code": "WRONG"}
    before = json.dumps(wrong, ensure_ascii=False, separators=(",", ":"))
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (before, f"engine_async_job:{ACOUSTIC_JOB_ID}"),
    )
    conn.commit()
    conn.close()

    result = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert result["claimed"] is False
    stored = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert stored == before


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("output_sent", True),
        ("charged_xu", 1),
        ("multi_acoustic_speaker_count", 5),
        ("multi_acoustic_overlap_mapped_count", 19),
        ("multi_acoustic_failure_word_count", 50),
    ),
)
def test_context_repair_rejects_output_charge_or_acoustic_evidence(
    tmp_path,
    monkeypatch,
    field,
    value,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    mutated = {**context_failure, field: value}
    before = json.dumps(mutated, ensure_ascii=False, separators=(",", ":"))
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (before, f"engine_async_job:{ACOUSTIC_JOB_ID}"),
    )
    conn.commit()
    conn.close()

    result = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert result["claimed"] is False
    stored = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert stored == before


def test_context_repair_cas_has_one_winner(tmp_path, monkeypatch):
    rearm, db_path, _context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    barrier = threading.Barrier(2)

    def claim():
        barrier.wait(timeout=5.0)
        return rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: claim(), range(2)))

    winners = [result for result in results if result.get("claimed") is True]
    losers = [result for result in results if result.get("claimed") is not True]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0]["reason"] in {
        "fixed_vocal_v2_rearm_not_allowed",
        "fixed_vocal_v2_rearm_cas_lost",
    }


def test_context_repair_rehydrates_missing_source_from_stored_file_id(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    source_path = context_failure["auto_multi_recovery"]["source_path"]
    source_bytes = b"byte-identical-source-from-stored-file-id"
    expected_sha256 = hashlib.sha256(source_bytes).hexdigest()
    context_failure["auto_multi_recovery"]["source_sha256"] = expected_sha256
    context_failure["source_sha256"] = expected_sha256
    context_failure["input_save"]["original_source_sha256"] = expected_sha256
    context_failure["input_save"]["transport_input_size"] = len(source_bytes)
    _persist_fixed_vocal_job(db_path, context_failure)
    if Path(source_path).exists():
        Path(source_path).unlink()
    before = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    monkeypatch.setattr(rearm, "SOURCE_SHA256", expected_sha256)
    monkeypatch.setattr(
        rearm.app,
        "_subdub_sha256_file",
        lambda value: hashlib.sha256(Path(value).read_bytes()).hexdigest(),
    )
    calls = []

    async def download(_context, state):
        calls.append(dict(state))
        return source_bytes, "video/mp4"

    monkeypatch.setattr(rearm.app, "video_dubbing_download_source", download)

    result = asyncio.run(rearm.ensure_exact_source(SimpleNamespace()))

    assert result["ok"] is True
    assert result["rehydrated"] is True
    assert Path(source_path).read_bytes() == source_bytes
    assert calls[0]["source_file_id"] == context_failure["input_save"]["file_id"]
    assert calls[0]["source_file_id"] != context_failure["job_key"].split("|")[2]
    after = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert after == before


def test_context_repair_reuses_existing_exact_source_without_download(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    source_path = Path(context_failure["auto_multi_recovery"]["source_path"])
    source_bytes = b"existing-byte-identical-source"
    expected_sha256 = hashlib.sha256(source_bytes).hexdigest()
    context_failure["auto_multi_recovery"]["source_sha256"] = expected_sha256
    context_failure["source_sha256"] = expected_sha256
    context_failure["input_save"]["original_source_sha256"] = expected_sha256
    context_failure["input_save"]["transport_input_size"] = len(source_bytes)
    _persist_fixed_vocal_job(db_path, context_failure)
    source_path.write_bytes(source_bytes)
    before = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    monkeypatch.setattr(rearm, "SOURCE_SHA256", expected_sha256)
    monkeypatch.setattr(
        rearm.app,
        "_subdub_sha256_file",
        lambda value: hashlib.sha256(Path(value).read_bytes()).hexdigest(),
    )

    async def unexpected_download(*_args, **_kwargs):
        raise AssertionError("existing exact source must not be downloaded")

    monkeypatch.setattr(
        rearm.app,
        "video_dubbing_download_source",
        unexpected_download,
    )

    result = asyncio.run(rearm.ensure_exact_source(SimpleNamespace()))

    assert result == {
        "ok": True,
        "rehydrated": False,
        "path": str(source_path.resolve()),
    }
    assert source_path.read_bytes() == source_bytes
    after = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert after == before


def test_context_repair_rejects_existing_wrong_hash_without_overwrite(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    source_path = Path(context_failure["auto_multi_recovery"]["source_path"])
    wrong_bytes = b"existing-source-with-wrong-hash"
    source_path.write_bytes(wrong_bytes)
    before = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    monkeypatch.setattr(
        rearm.app,
        "_subdub_sha256_file",
        lambda value: hashlib.sha256(Path(value).read_bytes()).hexdigest(),
    )

    async def unexpected_download(*_args, **_kwargs):
        raise AssertionError("existing wrong source must fail closed")

    monkeypatch.setattr(
        rearm.app,
        "video_dubbing_download_source",
        unexpected_download,
    )

    result = asyncio.run(rearm.ensure_exact_source(SimpleNamespace()))

    assert result == {
        "ok": False,
        "rehydrated": False,
        "reason": "source_sha256_mismatch",
    }
    assert source_path.read_bytes() == wrong_bytes
    assert not Path(f"{source_path}.rehydrate.tmp").exists()
    after = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert after == before


def test_context_repair_rejects_stored_file_id_mismatch_without_download(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    source_path = Path(context_failure["auto_multi_recovery"]["source_path"])
    source_path.unlink(missing_ok=True)
    context_failure["auto_multi_recovery"]["source_file_unique_id"] = (
        "AgAD-wrong-unique-id"
    )
    _persist_fixed_vocal_job(db_path, context_failure)
    before = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]

    async def unexpected_download(*_args, **_kwargs):
        raise AssertionError("mismatched file id must not be downloaded")

    monkeypatch.setattr(
        rearm.app,
        "video_dubbing_download_source",
        unexpected_download,
    )

    result = asyncio.run(rearm.ensure_exact_source(SimpleNamespace()))

    assert result == {
        "ok": False,
        "rehydrated": False,
        "reason": "source_file_id_invalid",
    }
    assert not source_path.exists()
    assert not Path(f"{source_path}.rehydrate.tmp").exists()
    after = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert after == before


def test_context_repair_rejects_download_hash_mismatch_without_source(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    source_path = Path(context_failure["auto_multi_recovery"]["source_path"])
    source_path.unlink(missing_ok=True)
    wrong_bytes = b"downloaded-bytes-with-wrong-hash"
    context_failure["input_save"]["transport_input_size"] = len(wrong_bytes)
    _persist_fixed_vocal_job(db_path, context_failure)
    before = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    calls = []

    async def download(_context, state):
        calls.append(dict(state))
        return wrong_bytes, "video/mp4"

    monkeypatch.setattr(rearm.app, "video_dubbing_download_source", download)

    result = asyncio.run(rearm.ensure_exact_source(SimpleNamespace()))

    assert result == {
        "ok": False,
        "rehydrated": False,
        "reason": "source_sha256_mismatch",
    }
    assert len(calls) == 1
    assert not source_path.exists()
    assert not Path(f"{source_path}.rehydrate.tmp").exists()
    after = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert after == before


def test_fixed_vocal_v2_rearm_keeps_same_fourth_attempt_and_wins_once(
    tmp_path,
    monkeypatch,
):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, _job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(rearm.app, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(rearm.app, "SUBTITLE_DUB_PIPELINE_JOBS", {})

    first = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert first["claimed"] is True
    recovered = first["job"]
    assert recovered["auto_multi_recovery_attempt_count"] == 4
    assert recovered["auto_multi_recovery_correction_attempt_count"] == 3
    assert recovered["auto_multi_acoustic_recovery_used"] is True
    assert recovered["auto_multi_acoustic_stability_repair_used"] is True
    assert recovered["auto_multi_fixed_vocal_v2_recovery_used"] is True
    assert recovered["auto_multi_acoustic_backend"] == (
        "local_wespeaker_resnet34_spectral"
    )
    assert recovered["auto_multi_acoustic_algorithm_version"] == (
        "wespeaker-resnet34-spectral-v1"
    )
    assert recovered["status"] == bot.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS
    assert recovered["terminal_state"] == ""
    terminal_again = {
        **recovered,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
    }
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (
            json.dumps(terminal_again, ensure_ascii=False, separators=(",", ":")),
            f"engine_async_job:{ACOUSTIC_JOB_ID}",
        ),
    )
    conn.commit()
    conn.close()
    second = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    assert second == {
        "ok": False,
        "claimed": False,
        "reason": "fixed_vocal_v2_rearm_not_allowed",
    }
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM system_settings").fetchone()[0] == 1
        stored = json.loads(
            conn.execute(
                "SELECT value FROM system_settings WHERE key=?",
                (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
            ).fetchone()[0]
        )
    finally:
        conn.close()
    assert stored == terminal_again


def test_fixed_vocal_v2_duration_repair_rearms_measured_post_live_failure_once(
    tmp_path,
    monkeypatch,
):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, _job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(rearm.app, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(rearm.app, "SUBTITLE_DUB_PIPELINE_JOBS", {})

    first = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    assert first["claimed"] is True
    failed = _exact_duration_live_failure(first["job"])
    _persist_fixed_vocal_job(db_path, failed)

    repair = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert repair["claimed"] is True
    repaired = repair["job"]
    assert repaired["auto_multi_recovery_attempt_count"] == 4
    assert repaired["auto_multi_recovery_correction_attempt_count"] == 3
    assert repaired["auto_multi_fixed_vocal_v2_recovery_used"] is True
    assert repaired["auto_multi_fixed_vocal_v2_duration_repair_used"] is True
    assert repaired["auto_multi_fixed_vocal_v2_duration_repair_authority"] == (
        "owner_confirmed_same_job_exact_duration"
    )
    assert repaired["auto_multi_fixed_vocal_v2_duration_repair_from_seconds"] == 134.0
    assert repaired["auto_multi_fixed_vocal_v2_duration_repair_to_seconds"] == (
        pytest.approx(133.37542)
    )
    terminal_again = {
        **repaired,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
    }
    _persist_fixed_vocal_job(db_path, terminal_again)
    duplicate = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    assert duplicate == {
        "ok": False,
        "claimed": False,
        "reason": "fixed_vocal_v2_rearm_not_allowed",
    }


def test_fixed_vocal_v2_asr_timeout_repair_rearms_measured_timeout_once(
    tmp_path,
    monkeypatch,
):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, _job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(rearm.app, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(rearm.app, "SUBTITLE_DUB_PIPELINE_JOBS", {})

    first = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    _persist_fixed_vocal_job(db_path, _exact_duration_live_failure(first["job"]))
    duration = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    assert duration["claimed"] is True
    timeout_failure = {
        **duration["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "",
        "last_error_safe": "",
        "asr_started": True,
        "translation_started": False,
        "tts_started": False,
        "mux_started": False,
        "artifact_started": False,
        "delivery_attempted": False,
        "final_mp4_exists": False,
        "output_validated": False,
        "output_sent": False,
    }
    _persist_fixed_vocal_job(db_path, timeout_failure)
    _persist_translation_asr_attempt(db_path, _exact_deepgram_timeout_receipt())

    repair = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert repair["claimed"] is True
    repaired = repair["job"]
    assert repaired["auto_multi_recovery_attempt_count"] == 4
    assert repaired["auto_multi_recovery_correction_attempt_count"] == 3
    assert repaired["auto_multi_fixed_vocal_v2_recovery_used"] is True
    assert repaired["auto_multi_fixed_vocal_v2_duration_repair_used"] is True
    assert repaired["auto_multi_fixed_vocal_v2_asr_timeout_repair_used"] is True
    assert repaired["auto_multi_fixed_vocal_v2_asr_timeout_repair_authority"] == (
        "owner_confirmed_same_job_deepgram_timeout"
    )
    assert repaired["auto_multi_fixed_vocal_v2_asr_timeout_receipt_at"] == (
        "2026-09-02 22:31:08"
    )
    assert repaired["auto_multi_fixed_vocal_v2_asr_timeout_seconds"] == 300
    assert repaired["asr_started"] is False
    terminal_again = {
        **repaired,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
    }
    _persist_fixed_vocal_job(db_path, terminal_again)
    duplicate = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    assert duplicate == {
        "ok": False,
        "claimed": False,
        "reason": "fixed_vocal_v2_rearm_not_allowed",
    }


@pytest.mark.parametrize(
    ("receipt_field", "receipt_value"),
    (
        ("called", False),
        ("provider", "key4u_audio"),
        ("route", "other"),
        ("status", "PASS"),
        ("error", "empty transcript"),
        ("at", "2026-09-02 22:31:09"),
    ),
)
def test_fixed_vocal_v2_asr_timeout_repair_rejects_receipt_mutation(
    tmp_path,
    monkeypatch,
    receipt_field,
    receipt_value,
):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, _job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    first = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    _persist_fixed_vocal_job(db_path, _exact_duration_live_failure(first["job"]))
    duration = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    timeout_failure = {
        **duration["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "last_error_stage": "",
        "last_error_safe": "",
        "asr_started": True,
    }
    _persist_fixed_vocal_job(db_path, timeout_failure)
    receipt = {**_exact_deepgram_timeout_receipt(), receipt_field: receipt_value}
    _persist_translation_asr_attempt(db_path, receipt)

    repair = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert repair == {
        "ok": False,
        "claimed": False,
        "reason": "fixed_vocal_v2_rearm_not_allowed",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_duration_exact", 133.0),
        ("input_duration", 133),
        ("auto_multi_fixed_vocal_v2_duration_repair_used", True),
        ("multi_diarization_provider_word_count", 146),
        ("multi_diarization_provider_speaker_count", 5),
        ("multi_diarization_mapped_speaker_count", 4),
        ("multi_diarization_raw_annotation_count", 150),
        ("multi_diarization_parse_rejection", "invalid"),
        ("asr_started", True),
        ("translation_started", True),
        ("output_sent", True),
        ("charged_xu", 1),
    ),
)
def test_fixed_vocal_v2_duration_repair_rejects_non_exact_live_authority(
    tmp_path,
    monkeypatch,
    field,
    value,
):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, _job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(rearm.app, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(rearm.app, "SUBTITLE_DUB_PIPELINE_JOBS", {})
    first = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    failed = {
        **first["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "source_duration_exact": 133.37542,
        "input_duration": 134,
        "multi_diarization_attempted": True,
        "multi_diarization_provider": "gemini_transcribe_multi_diarization",
        "multi_diarization_status": "PASS",
        "multi_diarization_detail": "words=147; speakers=4",
        "multi_diarization_http_status": 200,
        "multi_diarization_provider_word_count": 147,
        "multi_diarization_provider_speaker_count": 4,
        "multi_diarization_mapped_speaker_count": 0,
        "multi_diarization_raw_annotation_count": 151,
        "multi_diarization_terminal_empty": False,
        "multi_diarization_parse_rejection": "",
        "multi_diarization_dropped_weak_word_count": 1,
        "multi_diarization_dropped_weak_speaker_count": 1,
        "multi_diarization_weak_label_filter_applied": True,
        field: value,
    }
    old_value = json.dumps(failed, ensure_ascii=False)
    _persist_fixed_vocal_job(db_path, failed)

    repair = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert repair == {
        "ok": False,
        "claimed": False,
        "reason": "fixed_vocal_v2_rearm_not_allowed",
    }
    stored = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert json.loads(stored) == json.loads(old_value)


def test_fixed_vocal_v2_duration_repair_accepts_matching_nested_duration_only(
    tmp_path,
    monkeypatch,
):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, _job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(rearm.app, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(rearm.app, "SUBTITLE_DUB_PIPELINE_JOBS", {})
    first = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    failed = {
        **first["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "failed_no_charge",
        "current_stage": "failed_no_charge",
        "progress_stage": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "multi_diarization_attempted": True,
        "multi_diarization_provider": "gemini_transcribe_multi_diarization",
        "multi_diarization_status": "PASS",
        "multi_diarization_detail": "words=147; speakers=4",
        "multi_diarization_http_status": 200,
        "multi_diarization_provider_word_count": 147,
        "multi_diarization_provider_speaker_count": 4,
        "multi_diarization_mapped_speaker_count": 0,
        "multi_diarization_raw_annotation_count": 151,
        "multi_diarization_terminal_empty": False,
        "multi_diarization_parse_rejection": "",
        "multi_diarization_dropped_weak_word_count": 1,
        "multi_diarization_dropped_weak_speaker_count": 1,
        "multi_diarization_weak_label_filter_applied": True,
        "input_save": {
            **first["job"]["input_save"],
            "source_duration_exact": 133.37542,
            "duration": 134,
        },
    }
    failed.pop("source_duration_exact", None)
    failed.pop("input_duration", None)
    _persist_fixed_vocal_job(db_path, failed)

    repair = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert repair["claimed"] is True
    assert repair["job"]["auto_multi_fixed_vocal_v2_duration_repair_used"] is True


def test_fixed_vocal_v2_duration_repair_rejects_root_nested_duration_conflict(
    tmp_path,
    monkeypatch,
):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, _job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    first = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)
    failed = {
        **first["job"],
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "source_duration_exact": 133.37542,
        "input_duration": 134,
        "multi_diarization_attempted": True,
        "multi_diarization_provider": "gemini_transcribe_multi_diarization",
        "multi_diarization_status": "PASS",
        "multi_diarization_detail": "words=147; speakers=4",
        "multi_diarization_http_status": 200,
        "multi_diarization_provider_word_count": 147,
        "multi_diarization_provider_speaker_count": 4,
        "multi_diarization_mapped_speaker_count": 0,
        "multi_diarization_raw_annotation_count": 151,
        "multi_diarization_terminal_empty": False,
        "multi_diarization_parse_rejection": "",
        "multi_diarization_dropped_weak_word_count": 1,
        "multi_diarization_dropped_weak_speaker_count": 1,
        "multi_diarization_weak_label_filter_applied": True,
        "input_save": {
            **first["job"]["input_save"],
            "source_duration_exact": 132.0,
            "duration": 133,
        },
    }
    _persist_fixed_vocal_job(db_path, failed)

    repair = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert repair["claimed"] is False
    assert repair["reason"] == "fixed_vocal_v2_rearm_not_allowed"


def test_fixed_vocal_v2_preflight_fails_before_database_access(monkeypatch):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_calls = []

    def forbidden_db():
        db_calls.append(True)
        raise AssertionError("database must not open before fixed-vocal preflight")

    monkeypatch.setattr(rearm.app, "db_connect", forbidden_db)
    result = rearm.claim_same_attempt(
        acoustic_preflight=lambda: {"ok": False, "status": "FAIL"}
    )

    assert result == {
        "ok": False,
        "claimed": False,
        "reason": "fixed_vocal_v2_preflight_failed",
    }
    assert db_calls == []


@pytest.mark.parametrize(
    "mutation",
    (
        "already_used",
        "already_v2",
        "wrong_public_code",
        "wrong_owner",
        "wrong_job_key",
        "wrong_source",
        "wrong_backend",
        "wrong_model",
        "missing_acoustic_recovery",
        "missing_stability_repair",
        "attempt_changed",
        "charged",
        "charged_bool",
        "charge_status_changed",
        "output_exists",
        "asr_already_started",
        "selection_changed",
        "root_selection_conflict",
        "v2_evidence_present",
        "v2_failure_evidence_present",
    ),
)
def test_fixed_vocal_v2_rearm_rejects_mutated_authority_without_write(
    tmp_path,
    monkeypatch,
    mutation,
):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    if mutation == "already_used":
        job["auto_multi_fixed_vocal_v2_recovery_used"] = True
    elif mutation == "already_v2":
        job["auto_multi_acoustic_algorithm_version"] = ACOUSTIC_ALGORITHM_VERSION
    elif mutation == "wrong_public_code":
        job["public_code"] = "WRONG"
    elif mutation == "wrong_owner":
        job["user_id"] = OWNER_ID + 1
    elif mutation == "wrong_job_key":
        job["job_key"] = "wrong|route"
    elif mutation == "wrong_source":
        job["auto_multi_recovery"]["source_sha256"] = "0" * 64
    elif mutation == "wrong_backend":
        job["auto_multi_acoustic_backend"] = "other"
    elif mutation == "wrong_model":
        job["auto_multi_acoustic_model_sha256"] = "0" * 64
    elif mutation == "missing_acoustic_recovery":
        job["auto_multi_acoustic_recovery_used"] = False
    elif mutation == "missing_stability_repair":
        job["auto_multi_acoustic_stability_repair_used"] = False
    elif mutation == "attempt_changed":
        job["auto_multi_recovery_attempt_count"] = 5
    elif mutation == "charged":
        job["charged_xu"] = 1
    elif mutation == "charged_bool":
        job["charged_xu"] = False
    elif mutation == "charge_status_changed":
        job["charge_status"] = "charged"
    elif mutation == "output_exists":
        job["final_mp4_exists"] = True
    elif mutation == "asr_already_started":
        job["asr_started"] = True
    elif mutation == "selection_changed":
        job["auto_multi_recovery"]["target_language"] = "Vietnamese"
    elif mutation == "root_selection_conflict":
        job["target_language"] = "Vietnamese"
    elif mutation == "v2_evidence_present":
        job["multi_acoustic_backend"] = "local_wespeaker_resnet34_fixed_vocal"
        job["multi_acoustic_algorithm_version"] = ACOUSTIC_ALGORITHM_VERSION
        job["multi_acoustic_speaker_count"] = 5
    elif mutation == "v2_failure_evidence_present":
        job["multi_acoustic_failure_word_count"] = 50
    conn = sqlite3.connect(db_path)
    old_value = json.dumps(job, ensure_ascii=False)
    conn.execute(
        "UPDATE system_settings SET value=? WHERE key=?",
        (old_value, f"engine_async_job:{ACOUSTIC_JOB_ID}"),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(rearm.app, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(rearm.app, "SUBTITLE_DUB_PIPELINE_JOBS", {})

    result = rearm.claim_same_attempt(acoustic_preflight=fixed_vocal_v2_preflight)

    assert result == {
        "ok": False,
        "claimed": False,
        "reason": "fixed_vocal_v2_rearm_not_allowed",
    }
    stored = sqlite3.connect(db_path).execute(
        "SELECT value FROM system_settings WHERE key=?",
        (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
    ).fetchone()[0]
    assert stored == old_value


def test_fixed_vocal_v2_rearm_concurrent_claim_has_one_cas_winner(
    tmp_path,
    monkeypatch,
):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    db_path, _job = _seed_fixed_vocal_v1_terminal(tmp_path, monkeypatch)
    monkeypatch.setattr(rearm.app, "db_connect", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(rearm.app, "ENGINE_ASYNC_MEMORY_JOBS", {})
    monkeypatch.setattr(rearm.app, "SUBTITLE_DUB_PIPELINE_JOBS", {})
    barrier = threading.Barrier(2)

    def claim():
        barrier.wait(timeout=5.0)
        return rearm.claim_same_attempt(
            acoustic_preflight=fixed_vocal_v2_preflight
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: claim(), range(2)))

    winners = [result for result in results if result.get("claimed") is True]
    losers = [result for result in results if result.get("claimed") is not True]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0]["reason"] in {
        "fixed_vocal_v2_rearm_not_allowed",
        "fixed_vocal_v2_rearm_cas_lost",
    }
    stored = json.loads(
        sqlite3.connect(db_path).execute(
            "SELECT value FROM system_settings WHERE key=?",
            (f"engine_async_job:{ACOUSTIC_JOB_ID}",),
        ).fetchone()[0]
    )
    assert stored["auto_multi_fixed_vocal_v2_recovery_used"] is True
    assert stored["auto_multi_recovery_attempt_count"] == 4


def test_fixed_vocal_v2_runner_enters_existing_handler_once(monkeypatch):
    rearm = importlib.import_module("scripts.recover_subdub_fixed_vocal_v2")
    job = {
        "job_key": (
            f"{OWNER_ID}|{OWNER_ID}|AgADeSIAAh1tkVQ|"
            "subtitle_plus_dub|auto_multi_speaker"
        )
    }
    calls = []

    class FakeBot:
        def __init__(self, token):
            self.token = token

        async def __aenter__(self):
            calls.append(("bot_enter",))
            return self

        async def __aexit__(self, *_args):
            return False

        async def send_message(self, **_kwargs):
            return SimpleNamespace(message_id=1)

    async def fake_handler(update, context):
        calls.append(("handler", update.effective_user.id, list(context.args)))

    def fake_claim(**_kwargs):
        calls.append(("claim",))
        return {"ok": True, "claimed": True, "job": job}

    monkeypatch.setattr(
        rearm.app,
        "build_telegram_application",
        lambda: SimpleNamespace(bot=FakeBot("fixture-token")),
    )
    async def source_already_available(_telegram_bot):
        calls.append(("source",))
        return {
            "ok": False,
            "rehydrated": False,
            "reason": "context_repair_not_allowed",
        }
    monkeypatch.setattr(rearm, "ensure_exact_source", source_already_available)
    monkeypatch.setattr(
        rearm,
        "claim_same_attempt",
        fake_claim,
    )
    monkeypatch.setattr(rearm.app, "cmd_subdub_recover_failed_auto_multi", fake_handler)

    asyncio.run(rearm.run())

    assert calls == [
        ("bot_enter",),
        ("source",),
        ("claim",),
        (
            "handler",
            OWNER_ID,
            [
                ACOUSTIC_JOB_ID,
                SOURCE_SHA256,
                "English",
                "40",
                "150",
                "--confirm-paid",
                "--confirm-local-acoustic",
            ],
        )
    ]


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


def test_failed_auto_multi_allows_one_mapper_alignment_correction_only(
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
    failed = dict(first["job"])
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
            "multi_diarization_status": "PASS",
            "multi_diarization_detail": "words=147; speakers=4",
            "multi_diarization_http_status": 200,
            "multi_diarization_provider_word_count": 147,
            "multi_diarization_provider_speaker_count": 4,
            "multi_diarization_mapped_speaker_count": 0,
            "multi_diarization_raw_annotation_count": 151,
            "multi_diarization_terminal_empty": False,
            "multi_diarization_parse_rejection": "",
            "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        }
    )
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

    assert correction["ok"] is True
    assert correction["claimed"] is True
    assert correction["job"]["internal_job_id"] == JOB_ID
    assert correction["job"]["auto_multi_recovery_attempt_count"] == 2
    assert correction["job"]["auto_multi_recovery_correction_attempt_count"] == 1


def test_failed_auto_multi_allows_one_crosswalk_correction_after_mapper_alignment(
    tmp_path,
    monkeypatch,
):
    db_path, _job, _source, source_sha256 = _seed_job(tmp_path, monkeypatch)

    def claim():
        return bot.claim_subdub_failed_auto_multi_recovery(
            JOB_ID,
            owner_user_id=OWNER_ID,
            chat_id=OWNER_ID,
            source_sha256=source_sha256,
            target_language="English",
            original_volume_percent=40,
            dub_volume_percent=150,
            confirm_paid=True,
        )

    def mapper_failure(job):
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
                "multi_diarization_status": "PASS",
                "multi_diarization_detail": "words=147; speakers=4",
                "multi_diarization_http_status": 200,
                "multi_diarization_provider_word_count": 147,
                "multi_diarization_provider_speaker_count": 4,
                "multi_diarization_mapped_speaker_count": 0,
                "multi_diarization_raw_annotation_count": 151,
                "multi_diarization_terminal_empty": False,
                "multi_diarization_parse_rejection": "",
                "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
            }
        )
        return failed

    first = claim()
    _persist_recovery_job(db_path, mapper_failure(first["job"]))
    second = claim()
    assert second["claimed"] is True
    assert second["job"]["auto_multi_recovery_attempt_count"] == 2
    assert second["job"]["auto_multi_recovery_correction_attempt_count"] == 1

    _persist_recovery_job(db_path, mapper_failure(second["job"]))
    third = claim()

    assert third["ok"] is True
    assert third["claimed"] is True
    assert third["job"]["internal_job_id"] == JOB_ID
    assert third["job"]["auto_multi_recovery_attempt_count"] == 3
    assert third["job"]["auto_multi_recovery_correction_attempt_count"] == 2
    assert third["job"]["auto_multi_recovery_crosswalk_correction_used"] is True

    _persist_recovery_job(db_path, mapper_failure(third["job"]))
    fourth = claim()
    assert fourth["ok"] is False
    assert fourth["reason"] == "recovery_already_used"


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
        "source_file_id": DOWNLOADABLE_FILE_ID,
        "source_file_unique_id": job["job_key"].split("|")[2],
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
    assert state["source_file_id"] == DOWNLOADABLE_FILE_ID
    assert state["video_file_id"] == DOWNLOADABLE_FILE_ID
    assert state["source_file_unique_id"] == job["job_key"].split("|")[2]
    assert state["video_file_unique_id"] == job["job_key"].split("|")[2]
    assert state["_pipeline_source_path_override"] == str(source)
    assert state["_pipeline_workspace"] == job["workspace"]
    assert state["auto_exact_resume"] is False
    assert "auto_exact_receipt" not in state


def test_failed_auto_multi_recovery_state_never_promotes_unique_id_to_file_id(
    tmp_path,
    monkeypatch,
):
    _db_path, job, source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    unique_id = job["job_key"].split("|")[2]
    job["input_save"]["file_id"] = unique_id
    job["auto_multi_recovery"] = {
        "source_sha256": source_sha256,
        "source_path": str(source),
        "target_language": "English",
        "original_volume_percent": 40,
        "dub_volume_percent": 150,
        "owner_confirmed_paid": True,
    }

    state = bot.subdub_failed_auto_multi_recovery_state(job)

    assert state["source_file_unique_id"] == unique_id
    assert state["video_file_unique_id"] == unique_id
    assert state["source_file_id"] == ""
    assert state["video_file_id"] == ""


def test_failed_auto_multi_recovery_state_skips_legacy_unique_id_alias(
    tmp_path,
    monkeypatch,
):
    _db_path, job, source, source_sha256 = _seed_job(tmp_path, monkeypatch)
    unique_id = job["job_key"].split("|")[2]
    job["auto_multi_recovery"] = {
        "source_sha256": source_sha256,
        "source_path": str(source),
        "source_file_id": unique_id,
        "source_file_unique_id": unique_id,
        "target_language": "English",
        "original_volume_percent": 40,
        "dub_volume_percent": 150,
        "owner_confirmed_paid": True,
    }

    state = bot.subdub_failed_auto_multi_recovery_state(job)

    assert state["source_file_id"] == DOWNLOADABLE_FILE_ID
    assert state["video_file_id"] == DOWNLOADABLE_FILE_ID
    assert state["source_file_unique_id"] == unique_id


@pytest.mark.parametrize(
    "mutation",
    (
        {"source_file_unique_id": "different-unique-id"},
        {"source_file_unique_id": ["not", "text"]},
        {"source_file_id": ["not", "text"]},
        {"source_file_id": "conflicting-downloadable-id"},
    ),
)
def test_recovery_file_identity_rejects_mismatch_type_and_conflict(mutation):
    unique_id = "AgAD-authoritative-unique"
    current = {
        "job_key": f"1|1|{unique_id}|subtitle_plus_dub|auto_multi_speaker",
        "input_save": {
            "file_id": DOWNLOADABLE_FILE_ID,
            "file_unique_id": unique_id,
        },
    }

    assert bot._subdub_recovery_file_identity(current, mutation) == ("", "")


def test_context_repair_skips_legacy_unique_id_alias_for_download(
    tmp_path,
    monkeypatch,
):
    rearm, db_path, context_failure = _seed_context_loss_failure(
        tmp_path,
        monkeypatch,
    )
    unique_id = context_failure["job_key"].split("|")[2]
    source_path = Path(context_failure["auto_multi_recovery"]["source_path"])
    source_path.unlink(missing_ok=True)
    source_bytes = b"source-after-legacy-unique-id-alias"
    expected_sha256 = hashlib.sha256(source_bytes).hexdigest()
    context_failure["auto_multi_recovery"].update(
        {
            "source_sha256": expected_sha256,
            "source_file_id": unique_id,
            "source_file_unique_id": unique_id,
        }
    )
    context_failure["source_sha256"] = expected_sha256
    context_failure["input_save"]["file_id"] = DOWNLOADABLE_FILE_ID
    context_failure["input_save"]["transport_input_size"] = len(source_bytes)
    _persist_fixed_vocal_job(db_path, context_failure)
    monkeypatch.setattr(rearm, "SOURCE_SHA256", expected_sha256)
    monkeypatch.setattr(
        rearm.app,
        "_subdub_sha256_file",
        lambda value: hashlib.sha256(Path(value).read_bytes()).hexdigest(),
    )
    calls = []

    async def download(_context, state):
        calls.append(dict(state))
        return source_bytes, "video/mp4"

    monkeypatch.setattr(rearm.app, "video_dubbing_download_source", download)

    result = asyncio.run(rearm.ensure_exact_source(SimpleNamespace()))

    assert result["ok"] is True
    assert result["rehydrated"] is True
    assert calls[0]["source_file_id"] == DOWNLOADABLE_FILE_ID
    assert source_path.read_bytes() == source_bytes


def test_saved_input_preserves_downloadable_and_unique_file_ids(
    tmp_path,
    monkeypatch,
):
    source_bytes = b"downloaded-telegram-source"

    async def download(_context, state):
        assert state["source_file_id"] == DOWNLOADABLE_FILE_ID
        assert state["source_file_unique_id"] == "AgAD-unique-source"
        return source_bytes, "video/mp4"

    monkeypatch.setattr(bot, "video_dubbing_download_source", download)

    result = asyncio.run(
        bot.video_dubbing_save_input_for_pipeline(
            SimpleNamespace(bot=SimpleNamespace()),
            {
                "source_file_id": DOWNLOADABLE_FILE_ID,
                "source_file_unique_id": "AgAD-unique-source",
                "source_file_name": "fixture.mp4",
                "source_mime_type": "video/mp4",
                "source_file_size": len(source_bytes),
            },
            str(tmp_path),
        )
    )

    assert result["ok"] is True
    assert result["file_id"] == DOWNLOADABLE_FILE_ID
    assert result["file_unique_id"] == "AgAD-unique-source"
    assert result["source_bytes"] == source_bytes


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

    acoustic = SimpleNamespace(
        args=[
            ACOUSTIC_JOB_ID,
            SOURCE_SHA256,
            "English",
            "40",
            "150",
            "--confirm-paid",
            "--confirm-local-acoustic",
        ]
    )
    asyncio.run(bot.cmd_subdub_recover_failed_auto_multi(update, acoustic))
    assert len(claims) == 3
    assert claims[2][0] == ACOUSTIC_JOB_ID
    assert claims[2][1]["allow_legacy_observability_gap"] is False
    assert claims[2][1]["allow_acoustic_recovery"] is True
    assert executions[2]["job_id"] == JOB_ID


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
