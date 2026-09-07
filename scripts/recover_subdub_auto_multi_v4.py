"""One-shot same-job Auto Multi v4 recovery; never deliver the v3 artifact."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
from types import SimpleNamespace
from typing import Callable

import bot as app
from scripts import recover_subdub_fixed_vocal_v2 as legacy


JOB_ID = legacy.JOB_ID
PUBLIC_CODE = legacy.PUBLIC_CODE
OWNER_ID = legacy.OWNER_ID
SOURCE_SHA256 = legacy.SOURCE_SHA256
SOURCE_BYTES = 9_869_032
SOURCE_BASENAME = "auto_multi_v4_original_source.mp4"
V4_REPAIR_MARKER = "auto_multi_five_speaker_gender_aspect_v4_recovery_used"
V4_REPAIR_AUTHORITY = "owner_confirmed_same_job_five_speaker_gender_aspect"

_RESET_FALSE_FIELDS = (
    "asr_started",
    "translation_started",
    "tts_started",
    "mux_started",
    "artifact_started",
    "delivery_attempted",
    "delivery_attempt_uncertain",
    "final_mp4_exists",
    "final_mp4_validated",
    "final_mp4_delivered",
    "output_validated",
    "output_sent",
    "terminal_public_outcome_sent",
    "public_error_sent",
    "public_failure_sent",
    "receipt_sent_once",
    "receipt_send_attempted",
    "receipt_send_failed",
    "receipt_send_uncertain",
    "delivery_success",
    "delivery_succeeded",
    "delivery_confirmed_before_success",
    "delivery_started",
    "delivery_recovery_started",
    "delivery_recovery_succeeded",
    "duplicate_delivery_prevented",
    "duplicate_success_prevented",
    "output_validated_before_success",
    "public_success_sent",
    "panel_finalized",
    "status_panel_terminalized",
    "status_panel_terminal_edit_confirmed",
    "status_panel_terminal_edit_failed",
    "status_panel_replacement_sent",
    "refresh_stopped_after_terminal",
    "late_fail_suppressed",
    "error_sent_after_delivery",
)
_RESET_TEXT_FIELDS = (
    "canonical_final_artifact_path",
    "final_mp4_path",
    "final_output_path",
    "output_path",
    "output_video_path",
    "final_video_path",
    "dub_video_path",
    "delivery_message_id",
    "video_delivery_message_id",
    "final_video_message_id",
    "subdub_final_video_message_id",
    "telegram_message_id",
    "receipt_message_id",
    "subdub_success_message_id",
    "subdub_delivery_started_at",
    "subdub_delivered_at",
    "delivered_at",
    "receipt_send_state",
    "receipt_send_error",
    "terminal_public_outcome_type",
    "terminal_public_outcome_message_id",
    "delivery_status",
    "delivery_method",
    "delivery_reason",
    "delivery_recovery_started_at",
    "delivery_recovery_completed_at",
    "video_delivery_file_id",
    "video_delivery_filename",
    "video_delivery_mime_type",
    "video_delivery_sha256",
    "audio_delivery_message_id",
    "srt_delivery_message_id",
    "panel_final_message_id",
)
_RESET_ZERO_FIELDS = (
    "delivery_attempt_count",
    "success_sent_count",
    "public_messages_sent",
    "video_delivery_size_bytes",
    "video_delivery_duration_seconds",
    "panel_final_percent",
    "public_error_sent_count",
    "public_failure_sent_count",
)
_STALE_PROOF_FIELDS = (
    "auto_detected_speaker_count",
    "auto_distinct_voice_count",
    "auto_multi_voice_verified",
    "auto_multi_attribution_verified",
    "auto_multi_cast_sha256",
    "auto_multi_geometry_verified",
    "auto_multi_source_display_width",
    "auto_multi_source_display_height",
    "auto_multi_output_display_width",
    "auto_multi_output_display_height",
    "auto_multi_output_rotation",
)


def new_session_nonce() -> str:
    return secrets.token_hex(12)


def v4_recovery_candidate(current: dict) -> bool:
    """Recognize only the exact delivered v3 four-speaker job to correct."""

    if type(current) is not dict or current.get(V4_REPAIR_MARKER) is True:
        return False
    input_save = current.get("input_save")
    validation = current.get("output_validation")
    if type(input_save) is not dict or type(validation) is not dict:
        return False
    return bool(
        validated_v4_source_path(current)
        and str(current.get("internal_job_id") or current.get("job_id") or "")
        == JOB_ID
        and current.get("public_code") == PUBLIC_CODE
        and str(current.get("user_id") or "") == str(OWNER_ID)
        and str(current.get("chat_id") or current.get("user_id") or "")
        == str(OWNER_ID)
        and str(current.get("job_key") or "").endswith(
            "|subtitle_plus_dub|auto_multi_speaker"
        )
        and current.get("status") == "delivered"
        and current.get("terminal_state") == "delivered"
        and current.get("output_sent") is True
        and current.get("final_mp4_delivered") is True
        and current.get("delivery_attempt_uncertain") is not True
        and type(current.get("charged_xu")) is int
        and current.get("charged_xu") == 0
        and current.get("charge_status") == "admin_free"
        and str(current.get("video_delivery_message_id") or "").strip()
        and str(current.get("receipt_message_id") or "").strip()
        and current.get("multi_acoustic_raw_speaker_count") == 5
        and current.get("multi_acoustic_speaker_count") == 4
        and current.get("auto_detected_speaker_count") == 4
        and current.get("auto_distinct_voice_count") == 4
        and current.get("target_language") == "English"
        and current.get("original_audio_volume_percent") == 40
        and current.get("dubbed_voice_volume_percent") == 150
        and current.get("voice_kind") == "auto_speaker_gender"
        and current.get("voice_selection_mode") == "auto_speaker"
        and current.get("auto_speaker_lane") == "multi"
        and str(input_save.get("original_source_sha256") or "").lower()
        == SOURCE_SHA256
        and input_save.get("transport_input_size") == SOURCE_BYTES
        and input_save.get("content_type") == "video/mp4"
        and validation.get("ok") is True
        and validation.get("container") == "mp4"
        and validation.get("video_codec") == "h264"
        and validation.get("audio_codec") == "aac"
        and validation.get("has_video") is True
        and validation.get("has_audio") is True
    )


def validated_v4_source_path(current: dict) -> str:
    """Return the pre-restored byte-identical source inside this job workspace."""

    if type(current) is not dict:
        return ""
    workspace = str(current.get("workspace") or "").strip()
    safety = app.subtitle_dub_workspace_path_safety(workspace)
    resolved_workspace = str(
        safety.get("resolved_path") or os.path.abspath(workspace)
    )
    try:
        source = (Path(resolved_workspace) / SOURCE_BASENAME).resolve(strict=True)
    except (OSError, RuntimeError):
        return ""
    if (
        safety.get("allowed") is not True
        or not app._workspace_path_is_descendant(str(source), resolved_workspace)
        or source.name != SOURCE_BASENAME
        or not source.is_file()
        or source.stat().st_size != SOURCE_BYTES
    ):
        return ""
    digest = hashlib.sha256()
    try:
        with source.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                digest.update(block)
    except OSError:
        return ""
    return str(source) if digest.hexdigest() == SOURCE_SHA256 else ""


def _load_job_readonly() -> dict:
    conn = None
    try:
        conn = app.db_connect_readonly()
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=? LIMIT 1",
            (app._engine_async_job_key(JOB_ID),),
        ).fetchone()
        current = json.loads(str(row[0] or "{}")) if row else {}
        return current if type(current) is dict else {}
    except (json.JSONDecodeError, sqlite3.Error, TypeError, ValueError):
        return {}
    finally:
        if conn is not None:
            conn.close()


async def ensure_exact_source(_telegram_bot) -> dict:
    current = _load_job_readonly()
    source = validated_v4_source_path(current)
    return (
        {"ok": True, "rehydrated": False, "path": source}
        if source
        else {"ok": False, "rehydrated": False, "reason": "v4_source_missing"}
    )


def v4_preflight_result(
    *,
    acoustic_preflight: Callable[[], dict] | None = None,
    gender_preflight: Callable[[], dict] | None = None,
) -> dict:
    acoustic = legacy._preflight_result(acoustic_preflight)
    gender_service = app.auto_multi_speaker.subdub_multi_speaker_gender_onnx
    gender_check = gender_preflight or gender_service.multi_gender_model_preflight
    try:
        gender = dict(gender_check() or {}) if callable(gender_check) else {}
    except Exception:
        return {}
    if not (
        acoustic
        and gender.get("ok") is True
        and gender.get("model_sha256") == gender_service.MULTI_GENDER_MODEL_SHA256
        and gender.get("model_bytes") == gender_service.MULTI_GENDER_MODEL_BYTES
        and list(gender.get("providers") or []) == ["CPUExecutionProvider"]
        and shutil.which("ffprobe")
    ):
        return {}
    return {
        "ok": True,
        "acoustic": acoustic,
        "gender": gender,
        "ffprobe": True,
    }


def read_v4_terminal_job() -> dict:
    conn = None
    try:
        conn = app.db_connect_readonly()
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=? LIMIT 1",
            (app._engine_async_job_key(JOB_ID),),
        ).fetchone()
        current = json.loads(str(row[0] or "{}")) if row else {}
        if type(current) is not dict:
            return {}
        return current
    except (json.JSONDecodeError, sqlite3.Error, TypeError, ValueError):
        return {}
    finally:
        if conn is not None:
            conn.close()


def verify_v4_terminal_job(job: dict) -> dict:
    validation = job.get("output_validation")
    registers = job.get("multi_acoustic_speaker_registers")
    delivery_sha256 = str(job.get("video_delivery_sha256") or "").strip().lower()
    delivery_size = job.get("video_delivery_size_bytes")
    delivery_duration = job.get("video_delivery_duration_seconds")
    try:
        validation_size = int((validation or {}).get("size") or 0)
        validation_duration = float(
            (validation or {}).get("actual_duration")
            or (validation or {}).get("duration")
            or 0.0
        )
        delivery_duration_value = float(delivery_duration or 0.0)
    except (TypeError, ValueError, OverflowError):
        validation_size = 0
        validation_duration = 0.0
        delivery_duration_value = 0.0
    source_width = job.get("auto_multi_source_display_width")
    source_height = job.get("auto_multi_source_display_height")
    output_width = job.get("auto_multi_output_display_width")
    output_height = job.get("auto_multi_output_display_height")
    valid = bool(
        type(job) is dict
        and str(job.get("internal_job_id") or job.get("job_id") or "") == JOB_ID
        and job.get("status") == "delivered"
        and job.get("terminal_state") == "delivered"
        and job.get("charged_xu") == 0
        and job.get("final_mp4_validated") is True
        and job.get("final_mp4_delivered") is True
        and job.get("output_validated") is True
        and str(job.get("video_delivery_message_id") or "").strip()
        and str(
            job.get("receipt_message_id")
            or job.get("subdub_success_message_id")
            or ""
        ).strip()
        and job.get("auto_detected_speaker_count") == 5
        and job.get("auto_distinct_voice_count") == 5
        and job.get("auto_multi_voice_verified") is True
        and job.get("auto_multi_attribution_verified") is True
        and job.get("auto_multi_geometry_verified") is True
        and isinstance(job.get("auto_multi_cast_sha256"), str)
        and len(job.get("auto_multi_cast_sha256")) == 64
        and all(
            character in "0123456789abcdef"
            for character in job.get("auto_multi_cast_sha256").lower()
        )
        and job.get("multi_acoustic_raw_speaker_count") == 5
        and job.get("multi_acoustic_speaker_count") == 5
        and job.get("multi_acoustic_word_count") == 145
        and job.get("multi_acoustic_word_coverage_count") == 145
        and job.get("multi_acoustic_female_speaker_count") == 2
        and job.get("multi_acoustic_male_speaker_count") == 3
        and job.get("multi_acoustic_gender_model_sha256")
        == app.auto_multi_speaker.subdub_multi_speaker_gender_onnx.MULTI_GENDER_MODEL_SHA256
        and isinstance(registers, list)
        and registers == ["high", "low", "low", "high", "low"]
        and type(source_width) is int
        and type(source_height) is int
        and type(output_width) is int
        and type(output_height) is int
        and source_width > 0
        and source_height > 0
        and output_width > 0
        and output_height > 0
        and abs(source_width / source_height - output_width / output_height)
        <= 0.03
        and job.get("auto_multi_output_rotation") == 0
        and isinstance(validation, dict)
        and validation.get("ok") is True
        and validation.get("container") == "mp4"
        and validation.get("video_codec") == "h264"
        and validation.get("audio_codec") == "aac"
        and validation.get("has_video") is True
        and validation.get("has_audio") is True
        and len(delivery_sha256) == 64
        and all(character in "0123456789abcdef" for character in delivery_sha256)
        and type(delivery_size) is int
        and delivery_size > 0
        and validation_size == delivery_size
        and math.isfinite(delivery_duration_value)
        and delivery_duration_value > 0.0
        and math.isfinite(validation_duration)
        and abs(validation_duration - delivery_duration_value) <= 0.1
    )
    return {
        "ok": valid,
        "job": job,
        "reason": "v4_terminal_evidence_missing" if not valid else "",
    }


def claim_v4_same_job(
    *,
    acoustic_preflight: Callable[[], dict] | None = None,
    gender_preflight: Callable[[], dict] | None = None,
) -> dict:
    """CAS the old v3 failure into one full v4 run without a new job."""

    preflight = v4_preflight_result(
        acoustic_preflight=acoustic_preflight,
        gender_preflight=gender_preflight,
    )
    if not preflight:
        return {"ok": False, "claimed": False, "reason": "v4_preflight_failed"}
    key = app._engine_async_job_key(JOB_ID)
    conn = None
    try:
        conn = app.db_connect()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=? LIMIT 1",
            (key,),
        ).fetchone()
        if not row:
            conn.rollback()
            return {"ok": False, "claimed": False, "reason": "job_not_found"}
        old_value = str(row[0] or "")
        current = json.loads(old_value)
        if (
            type(current) is not dict
            or current.get(V4_REPAIR_MARKER) is True
            or not v4_recovery_candidate(current)
        ):
            conn.rollback()
            return {
                "ok": False,
                "claimed": False,
                "reason": "v4_recovery_not_allowed",
            }
        source_path = validated_v4_source_path(current)
        if not source_path:
            conn.rollback()
            return {
                "ok": False,
                "claimed": False,
                "reason": "v4_source_missing",
            }

        rejected_path = str(
            current.get("canonical_final_artifact_path")
            or current.get("final_mp4_path")
            or ""
        ).strip()
        old_video_message_id = str(
            current.get("video_delivery_message_id") or ""
        ).strip()
        old_receipt_message_id = str(
            current.get("receipt_message_id") or ""
        ).strip()
        old_delivered_at = str(
            current.get("subdub_delivered_at")
            or current.get("delivered_at")
            or ""
        ).strip()
        old_video_sha256 = str(
            current.get("video_delivery_sha256") or ""
        ).strip().lower()
        old_video_size = current.get("video_delivery_size_bytes")
        old_video_duration = current.get("video_delivery_duration_seconds")
        delivery_history = {
            "video_message_id": old_video_message_id,
            "receipt_message_id": old_receipt_message_id,
            "video_sha256": old_video_sha256,
            "video_size_bytes": old_video_size,
            "video_duration_seconds": old_video_duration,
            "delivered_at": old_delivered_at,
        }
        input_save = dict(current.get("input_save") or {})
        source_unique_id = str(input_save.get("file_unique_id") or "").strip()
        for field in tuple(current):
            if field.startswith("multi_acoustic_") or field in _STALE_PROOF_FIELDS:
                current.pop(field, None)
        current.update(
            {
                "status": app.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS,
                "terminal_state": "",
                "lifecycle_state": app.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS,
                "current_stage": app.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS,
                "progress_stage": app.SUBDUB_FAILED_AUTO_MULTI_RECOVERY_STATUS,
                "progress_percent": 5,
                "last_error_stage": "",
                "last_error_safe": "",
                "last_technical_error": "",
                "success_blocked_reason": "",
                "charge_status": "not_charged",
                "delivery_attempts": 0,
                "output_validation": {},
                "auto_exact_receipt": {},
                "canonical_final_artifact_bytes": 0,
                "voice_kind": "auto_speaker_gender",
                "voice_selection_mode": "auto_speaker",
                "auto_speaker_lane": "multi",
                "auto_exact_session_nonce": new_session_nonce(),
                "target_language": "English",
                "original_audio_volume_percent": 40,
                "dubbed_voice_volume_percent": 150,
                V4_REPAIR_MARKER: True,
                "auto_multi_v4_recovery_authority": V4_REPAIR_AUTHORITY,
                "auto_multi_v4_recovery_claimed_at": app.time.time(),
                "auto_multi_v3_rejected_artifact_path": rejected_path,
                "auto_multi_v3_rejected_speaker_count": 4,
                "auto_multi_v3_video_delivery_message_id": old_video_message_id,
                "auto_multi_v3_receipt_message_id": old_receipt_message_id,
                "auto_multi_v3_delivered_at": old_delivered_at,
                "auto_multi_v3_delivery_history": delivery_history,
                "auto_multi_v4_target_speaker_count": 5,
                "auto_multi_v4_target_algorithm": (
                    app.auto_multi_speaker.subdub_multi_speaker_embedding_onnx
                    .FIXED_VOCAL_ALGORITHM_VERSION
                ),
                "auto_multi_recovery": {
                    "source_path": source_path,
                    "source_sha256": SOURCE_SHA256,
                    "source_file_unique_id": source_unique_id,
                    "source_file_id": "",
                    "target_language": "English",
                    "original_volume_percent": 40,
                    "dub_volume_percent": 150,
                    "owner_confirmed_paid": True,
                },
                "updated_at": app.time.time(),
                **{field: False for field in _RESET_FALSE_FIELDS},
                **{field: "" for field in _RESET_TEXT_FIELDS},
                **{field: 0 for field in _RESET_ZERO_FIELDS},
            }
        )
        new_value = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
        cursor = conn.execute(
            """UPDATE system_settings
               SET value=?,note=?,updated_at=?,updated_by=?
               WHERE key=? AND value=?""",
            (
                new_value,
                "SubDub Auto Multi v4 same-job five-speaker recovery",
                app.now_text(),
                str(OWNER_ID),
                key,
                old_value,
            ),
        )
        if int(cursor.rowcount or 0) != 1:
            conn.rollback()
            return {"ok": False, "claimed": False, "reason": "v4_cas_lost"}
        conn.commit()
        app.ENGINE_ASYNC_MEMORY_JOBS[JOB_ID] = dict(current)
        app.SUBTITLE_DUB_PIPELINE_JOBS[str(current.get("job_key") or "")] = dict(
            current
        )
        return {"ok": True, "claimed": True, "job": dict(current)}
    except (json.JSONDecodeError, sqlite3.Error, TypeError, ValueError):
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
        return {"ok": False, "claimed": False, "reason": "v4_cas_error"}
    finally:
        if conn is not None:
            conn.close()


async def run() -> None:
    """Run one full v4 same-job recovery, never the legacy delivery shortcut."""

    application = app.build_telegram_application()
    async with application.bot as telegram_bot:
        source = await ensure_exact_source(telegram_bot)
        if not source.get("ok"):
            raise RuntimeError(str(source.get("reason") or "source_rehydrate_failed"))
        claim = claim_v4_same_job()
        if not claim.get("claimed"):
            raise RuntimeError(str(claim.get("reason") or "v4_recovery_failed"))

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=OWNER_ID),
            message=legacy._RecoveryMessage(telegram_bot),
        )
        context = SimpleNamespace(
            args=[
                JOB_ID,
                SOURCE_SHA256,
                "English",
                "40",
                "150",
                "--confirm-paid",
                "--confirm-local-acoustic",
            ],
            bot=telegram_bot,
        )
        original_claim = app.claim_subdub_failed_auto_multi_recovery
        app.claim_subdub_failed_auto_multi_recovery = lambda *_args, **_kwargs: claim
        try:
            await app.cmd_subdub_recover_failed_auto_multi(update, context)
        finally:
            app.claim_subdub_failed_auto_multi_recovery = original_claim
        verification = verify_v4_terminal_job(read_v4_terminal_job())
        if not verification.get("ok"):
            raise RuntimeError(str(verification.get("reason") or "v4_terminal_unverified"))


if __name__ == "__main__":
    asyncio.run(run())
