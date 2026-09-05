"""One-shot same-job rearm from the deployed Auto Multi acoustic v1 to v2."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Callable

import bot as app


JOB_ID = "b4cb6d5fe8a7bdfce507"
PUBLIC_CODE = "B4CB6D5FE8"
OWNER_ID = 7_126_457_028
SOURCE_SHA256 = "83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e"
PREVIOUS_BACKEND = "local_wespeaker_resnet34_spectral"
PREVIOUS_ALGORITHM = "wespeaker-resnet34-spectral-v1"
REARM_MARKER = "auto_multi_fixed_vocal_v2_recovery_used"
DURATION_REPAIR_MARKER = "auto_multi_fixed_vocal_v2_duration_repair_used"
ASR_TIMEOUT_REPAIR_MARKER = "auto_multi_fixed_vocal_v2_asr_timeout_repair_used"
CONTEXT_REPAIR_MARKER = "auto_multi_private_pipeline_context_repair_used"
ORIGINAL_SOURCE_REPAIR_MARKER = "auto_multi_original_acoustic_source_repair_used"
ACOUSTIC_RUNTIME_BUDGET_REPAIR_MARKER = (
    "auto_multi_acoustic_runtime_budget_repair_used"
)
ACOUSTIC_FULL_MEDIA_DURATION_REPAIR_MARKER = (
    "auto_multi_acoustic_full_media_duration_repair_used"
)
PENDING_MULTI_LANE_REPAIR_MARKER = "auto_multi_pending_lane_repair_used"


def _context_repair_candidate(current: dict) -> bool:
    if type(current) is not dict:
        return False
    service = app.auto_multi_speaker.subdub_multi_speaker_embedding_onnx
    recovery = current.get("auto_multi_recovery")
    input_save = current.get("input_save")
    if type(recovery) is not dict or type(input_save) is not dict:
        return False
    root_source_sha256 = current.get("source_sha256")
    root_target_language = current.get("target_language")
    root_original_volume = current.get("original_audio_volume_percent")
    root_dub_volume = current.get("dubbed_voice_volume_percent")
    root_conflict = bool(
        root_source_sha256 not in {None, ""}
        and (
            type(root_source_sha256) is not str
            or root_source_sha256.strip().lower() != SOURCE_SHA256
        )
    ) or bool(
        root_target_language not in {None, ""}
        and root_target_language != "English"
    ) or bool(
        root_original_volume is not None
        and (type(root_original_volume) is not int or root_original_volume != 40)
    ) or bool(
        root_dub_volume is not None
        and (type(root_dub_volume) is not int or root_dub_volume != 150)
    )


    actual_evidence = any(
        bool(current.get(field))
        for field in (
            "multi_acoustic_backend",
            "multi_acoustic_model_sha256",
            "multi_acoustic_algorithm_version",
            "multi_acoustic_speaker_count",
            "multi_acoustic_word_count",
            "multi_acoustic_unit_count",
            "multi_acoustic_embedding_window_count",
            "multi_acoustic_cluster_sizes",
            "multi_acoustic_stability_pass",
            "multi_acoustic_word_coverage_count",
            "multi_acoustic_overlap_mapped_count",
            "multi_acoustic_centroid_mapped_count",
            "multi_acoustic_speaker_unit_counts",
            "multi_acoustic_failure_code",
            "multi_acoustic_failure_word_count",
            "multi_acoustic_failure_duration_ms",
        )
    )
    false_fields = (
        "asr_started",
        "translation_started",
        "tts_started",
        "mux_started",
        "artifact_started",
        "delivery_attempted",
        "final_mp4_exists",
        "output_validated",
        "output_sent",
    )
    output_fields = (
        "final_mp4_path",
        "final_output_path",
        "output_path",
        "output_video_path",
        "final_video_path",
        "dub_video_path",
        "video_delivery_message_id",
        "final_video_message_id",
        "delivery_message_id",
        "telegram_message_id",
    )
    return bool(
        current.get(REARM_MARKER) is True
        and current.get(DURATION_REPAIR_MARKER) is True
        and current.get(ASR_TIMEOUT_REPAIR_MARKER) is True
        and current.get(CONTEXT_REPAIR_MARKER) is not True
        and current.get("auto_multi_fixed_vocal_v2_recovery_authority")
        == "owner_confirmed_same_job_upgrade"
        and current.get("auto_multi_fixed_vocal_v2_duration_repair_authority")
        == "owner_confirmed_same_job_exact_duration"
        and current.get("auto_multi_fixed_vocal_v2_asr_timeout_repair_authority")
        == "owner_confirmed_same_job_deepgram_timeout"
        and str(current.get("internal_job_id") or current.get("job_id") or "")
        == JOB_ID
        and current.get("public_code") == PUBLIC_CODE
        and str(current.get("user_id") or "") == str(OWNER_ID)
        and str(current.get("chat_id") or current.get("user_id") or "")
        == str(OWNER_ID)
        and str(current.get("job_key") or "").endswith(
            "|subtitle_plus_dub|auto_multi_speaker"
        )
        and current.get("status") == "failed_no_charge"
        and current.get("terminal_state") == "failed_no_charge"
        and current.get("auto_multi_recovery_attempt_count") == 4
        and current.get("auto_multi_recovery_correction_attempt_count") == 3
        and current.get("auto_multi_acoustic_recovery_used") is True
        and current.get("auto_multi_acoustic_stability_repair_used") is True
        and current.get("auto_multi_acoustic_backend") == PREVIOUS_BACKEND
        and current.get("auto_multi_acoustic_model_sha256") == service.MODEL_SHA256
        and current.get("auto_multi_acoustic_algorithm_version")
        == PREVIOUS_ALGORITHM
        and current.get("pipeline_started") is True
        and current.get("last_error_stage") == "AUTO_CAST_MANUAL_REQUIRED"
        and type(current.get("charged_xu")) is int
        and current.get("charged_xu") == 0
        and current.get("charge_status") == "not_charged"
        and all(field in current and current.get(field) is False for field in false_fields)
        and not any(str(current.get(field) or "").strip() for field in output_fields)
        and recovery.get("owner_confirmed_paid") is True
        and str(recovery.get("source_sha256") or "").lower() == SOURCE_SHA256
        and recovery.get("target_language") == "English"
        and recovery.get("original_volume_percent") == 40
        and recovery.get("dub_volume_percent") == 150
        and not root_conflict
        and not actual_evidence
    )


def _original_source_repair_candidate(current: dict) -> bool:
    if type(current) is not dict:
        return False
    service = app.auto_multi_speaker.subdub_multi_speaker_embedding_onnx
    recovery = current.get("auto_multi_recovery")
    if type(recovery) is not dict:
        return False
    success_evidence = any(
        bool(current.get(field))
        for field in (
            "multi_acoustic_backend",
            "multi_acoustic_model_sha256",
            "multi_acoustic_algorithm_version",
            "multi_acoustic_speaker_count",
            "multi_acoustic_word_count",
            "multi_acoustic_unit_count",
            "multi_acoustic_embedding_window_count",
            "multi_acoustic_cluster_sizes",
            "multi_acoustic_stability_pass",
            "multi_acoustic_word_coverage_count",
            "multi_acoustic_overlap_mapped_count",
            "multi_acoustic_centroid_mapped_count",
            "multi_acoustic_speaker_unit_counts",
        )
    )


    false_fields = (
        "asr_started",
        "translation_started",
        "tts_started",
        "mux_started",
        "artifact_started",
        "delivery_attempted",
        "final_mp4_exists",
        "output_validated",
        "output_sent",
    )
    output_fields = (
        "final_mp4_path",
        "final_output_path",
        "output_path",
        "output_video_path",
        "final_video_path",
        "dub_video_path",
        "video_delivery_message_id",
        "final_video_message_id",
        "delivery_message_id",
        "telegram_message_id",
    )
    return bool(
        current.get(REARM_MARKER) is True
        and current.get(DURATION_REPAIR_MARKER) is True
        and current.get(ASR_TIMEOUT_REPAIR_MARKER) is True
        and current.get(CONTEXT_REPAIR_MARKER) is True
        and current.get(ORIGINAL_SOURCE_REPAIR_MARKER) is not True
        and current.get("auto_multi_private_pipeline_context_repair_authority")
        == "owner_confirmed_same_job_private_pipeline_context"
        and str(current.get("internal_job_id") or current.get("job_id") or "")
        == JOB_ID
        and current.get("public_code") == PUBLIC_CODE
        and str(current.get("user_id") or "") == str(OWNER_ID)
        and str(current.get("chat_id") or current.get("user_id") or "")
        == str(OWNER_ID)
        and str(current.get("job_key") or "").endswith(
            "|subtitle_plus_dub|auto_multi_speaker"
        )
        and current.get("status") == "failed_no_charge"
        and current.get("terminal_state") == "failed_no_charge"
        and current.get("auto_multi_recovery_attempt_count") == 4
        and current.get("auto_multi_recovery_correction_attempt_count") == 3
        and current.get("auto_multi_acoustic_recovery_used") is True
        and current.get("auto_multi_acoustic_stability_repair_used") is True
        and current.get("auto_multi_acoustic_backend") == PREVIOUS_BACKEND
        and current.get("auto_multi_acoustic_model_sha256") == service.MODEL_SHA256
        and current.get("auto_multi_acoustic_algorithm_version")
        == PREVIOUS_ALGORITHM
        and current.get("pipeline_started") is True
        and current.get("last_error_stage") == "AUTO_CAST_MANUAL_REQUIRED"
        and current.get("multi_acoustic_failure_code")
        == "acoustic_failure_unknown"
        and current.get("multi_acoustic_failure_word_count") == 145
        and current.get("multi_acoustic_failure_duration_ms") == 134_000
        and type(current.get("charged_xu")) is int
        and current.get("charged_xu") == 0
        and current.get("charge_status") == "not_charged"
        and all(field in current and current.get(field) is False for field in false_fields)
        and not any(str(current.get(field) or "").strip() for field in output_fields)
        and recovery.get("owner_confirmed_paid") is True
        and str(recovery.get("source_sha256") or "").lower() == SOURCE_SHA256
        and recovery.get("target_language") == "English"
        and recovery.get("original_volume_percent") == 40
        and recovery.get("dub_volume_percent") == 150
        and not success_evidence
    )


def _acoustic_runtime_budget_repair_candidate(current: dict) -> bool:
    if type(current) is not dict:
        return False
    recovery = current.get("auto_multi_recovery")
    if type(recovery) is not dict:
        return False
    success_evidence = any(
        bool(current.get(field))
        for field in (
            "multi_acoustic_backend",
            "multi_acoustic_model_sha256",
            "multi_acoustic_algorithm_version",
            "multi_acoustic_speaker_count",
            "multi_acoustic_word_count",
            "multi_acoustic_unit_count",
            "multi_acoustic_embedding_window_count",
            "multi_acoustic_cluster_sizes",
            "multi_acoustic_stability_pass",
            "multi_acoustic_word_coverage_count",
            "multi_acoustic_overlap_mapped_count",
            "multi_acoustic_centroid_mapped_count",
            "multi_acoustic_speaker_unit_counts",
        )
    )
    false_fields = (
        "asr_started",
        "translation_started",
        "tts_started",
        "mux_started",
        "artifact_started",
        "delivery_attempted",
        "final_mp4_exists",
        "output_validated",
        "output_sent",
    )
    output_fields = (
        "final_mp4_path",
        "final_output_path",
        "output_path",
        "output_video_path",
        "final_video_path",
        "dub_video_path",
        "video_delivery_message_id",
        "final_video_message_id",
        "delivery_message_id",
        "telegram_message_id",
    )
    return bool(
        current.get(REARM_MARKER) is True
        and current.get(DURATION_REPAIR_MARKER) is True
        and current.get(ASR_TIMEOUT_REPAIR_MARKER) is True
        and current.get(CONTEXT_REPAIR_MARKER) is True
        and current.get(ORIGINAL_SOURCE_REPAIR_MARKER) is True
        and current.get(ACOUSTIC_RUNTIME_BUDGET_REPAIR_MARKER) is not True
        and current.get("auto_multi_private_pipeline_context_repair_authority")
        == "owner_confirmed_same_job_private_pipeline_context"
        and current.get("auto_multi_original_acoustic_source_repair_authority")
        == "owner_confirmed_same_job_original_acoustic_source"
        and str(current.get("internal_job_id") or current.get("job_id") or "")
        == JOB_ID
        and current.get("public_code") == PUBLIC_CODE
        and str(current.get("user_id") or "") == str(OWNER_ID)
        and str(current.get("chat_id") or current.get("user_id") or "")
        == str(OWNER_ID)
        and str(current.get("job_key") or "").endswith(
            "|subtitle_plus_dub|auto_multi_speaker"
        )
        and current.get("status") == "failed_no_charge"
        and current.get("terminal_state") == "failed_no_charge"
        and current.get("auto_multi_recovery_attempt_count") == 4
        and current.get("auto_multi_recovery_correction_attempt_count") == 3
        and current.get("pipeline_started") is True
        and current.get("last_error_stage") == "AUTO_CAST_MANUAL_REQUIRED"
        and current.get("multi_acoustic_failure_code")
        == "acoustic_failure_unknown"
        and current.get("multi_acoustic_failure_word_count") == 145
        and current.get("multi_acoustic_failure_duration_ms") == 134_000
        and type(current.get("charged_xu")) is int
        and current.get("charged_xu") == 0
        and current.get("charge_status") == "not_charged"
        and all(field in current and current.get(field) is False for field in false_fields)
        and not any(str(current.get(field) or "").strip() for field in output_fields)
        and recovery.get("owner_confirmed_paid") is True
        and str(recovery.get("source_sha256") or "").lower() == SOURCE_SHA256
        and recovery.get("target_language") == "English"
        and recovery.get("original_volume_percent") == 40
        and recovery.get("dub_volume_percent") == 150
        and not success_evidence
    )


def _acoustic_full_media_duration_repair_candidate(current: dict) -> bool:
    if type(current) is not dict:
        return False
    recovery = current.get("auto_multi_recovery")
    input_save = current.get("input_save")
    if type(recovery) is not dict or type(input_save) is not dict:
        return False
    try:
        source_duration = float(
            input_save.get("source_duration_exact")
            or current.get("source_duration_exact")
            or 0.0
        )
    except (TypeError, ValueError, OverflowError):
        source_duration = 0.0
    success_evidence = any(
        bool(current.get(field))
        for field in (
            "multi_acoustic_backend",
            "multi_acoustic_model_sha256",
            "multi_acoustic_algorithm_version",
            "multi_acoustic_speaker_count",
            "multi_acoustic_word_count",
            "multi_acoustic_unit_count",
            "multi_acoustic_embedding_window_count",
            "multi_acoustic_cluster_sizes",
            "multi_acoustic_stability_pass",
            "multi_acoustic_word_coverage_count",
            "multi_acoustic_overlap_mapped_count",
            "multi_acoustic_centroid_mapped_count",
            "multi_acoustic_speaker_unit_counts",
        )
    )
    false_fields = (
        "asr_started",
        "translation_started",
        "tts_started",
        "mux_started",
        "artifact_started",
        "delivery_attempted",
        "final_mp4_exists",
        "output_validated",
        "output_sent",
    )
    output_fields = (
        "final_mp4_path",
        "final_output_path",
        "output_path",
        "output_video_path",
        "final_video_path",
        "dub_video_path",
        "video_delivery_message_id",
        "final_video_message_id",
        "delivery_message_id",
        "telegram_message_id",
    )
    return bool(
        current.get(REARM_MARKER) is True
        and current.get(DURATION_REPAIR_MARKER) is True
        and current.get(ASR_TIMEOUT_REPAIR_MARKER) is True
        and current.get(CONTEXT_REPAIR_MARKER) is True
        and current.get(ORIGINAL_SOURCE_REPAIR_MARKER) is True
        and current.get(ACOUSTIC_RUNTIME_BUDGET_REPAIR_MARKER) is True
        and current.get(ACOUSTIC_FULL_MEDIA_DURATION_REPAIR_MARKER) is not True
        and current.get("auto_multi_private_pipeline_context_repair_authority")
        == "owner_confirmed_same_job_private_pipeline_context"
        and current.get("auto_multi_original_acoustic_source_repair_authority")
        == "owner_confirmed_same_job_original_acoustic_source"
        and current.get("auto_multi_acoustic_runtime_budget_repair_authority")
        == "owner_confirmed_same_job_duration_scaled_acoustic_budget"
        and str(current.get("internal_job_id") or current.get("job_id") or "")
        == JOB_ID
        and current.get("public_code") == PUBLIC_CODE
        and str(current.get("user_id") or "") == str(OWNER_ID)
        and str(current.get("chat_id") or current.get("user_id") or "")
        == str(OWNER_ID)
        and str(current.get("job_key") or "").endswith(
            "|subtitle_plus_dub|auto_multi_speaker"
        )
        and current.get("status") == "failed_no_charge"
        and current.get("terminal_state") == "failed_no_charge"
        and current.get("auto_multi_recovery_attempt_count") == 4
        and current.get("auto_multi_recovery_correction_attempt_count") == 3
        and current.get("pipeline_started") is True
        and current.get("last_error_stage") == "AUTO_CAST_MANUAL_REQUIRED"
        and current.get("multi_acoustic_failure_code")
        == "fixed_vocal_speaker_count_unstable"
        and current.get("multi_acoustic_failure_word_count") == 145
        and current.get("multi_acoustic_failure_duration_ms") == 134_000
        and type(current.get("input_duration")) is int
        and current.get("input_duration") == 134
        and math.isfinite(source_duration)
        and abs(source_duration - 133.37542) <= 0.00001
        and type(current.get("charged_xu")) is int
        and current.get("charged_xu") == 0
        and current.get("charge_status") == "not_charged"
        and all(field in current and current.get(field) is False for field in false_fields)
        and not any(str(current.get(field) or "").strip() for field in output_fields)
        and recovery.get("owner_confirmed_paid") is True
        and str(recovery.get("source_sha256") or "").lower() == SOURCE_SHA256
        and recovery.get("target_language") == "English"
        and recovery.get("original_volume_percent") == 40
        and recovery.get("dub_volume_percent") == 150
        and not success_evidence
    )


def _pending_multi_lane_repair_candidate(current: dict) -> bool:
    if type(current) is not dict:
        return False
    if (
        current.get(ACOUSTIC_FULL_MEDIA_DURATION_REPAIR_MARKER) is not True
        or current.get(PENDING_MULTI_LANE_REPAIR_MARKER) is True
        or current.get("auto_multi_acoustic_full_media_duration_repair_authority")
        != "owner_confirmed_same_job_full_original_media_duration"
    ):
        return False
    prior = dict(current)
    prior[ACOUSTIC_FULL_MEDIA_DURATION_REPAIR_MARKER] = False
    return _acoustic_full_media_duration_repair_candidate(prior)


def _load_context_repair_job_readonly() -> dict:
    conn = None
    try:
        conn = app.db_connect_readonly()
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=? LIMIT 1",
            (app._engine_async_job_key(JOB_ID),),
        ).fetchone()
        current = json.loads(str(row[0] or "{}")) if row else {}
        return current if _context_repair_candidate(current) else {}
    except (json.JSONDecodeError, OSError, sqlite3.Error, TypeError, ValueError):
        return {}
    finally:
        if conn is not None:
            conn.close()


async def ensure_exact_source(telegram_bot) -> dict:
    """Rehydrate the exact same-job source before CAS without touching DB."""

    current = _load_context_repair_job_readonly()
    if not current:
        return {"ok": False, "rehydrated": False, "reason": "context_repair_not_allowed"}
    recovery = dict(current.get("auto_multi_recovery") or {})
    input_save = dict(current.get("input_save") or {})
    workspace = str(current.get("workspace") or "").strip()
    safety = app.subtitle_dub_workspace_path_safety(workspace)
    workspace_resolved = str(
        safety.get("resolved_path") or os.path.abspath(workspace)
    )
    source_path = str(recovery.get("source_path") or "").strip()
    source_resolved = os.path.abspath(source_path)
    if (
        not safety.get("allowed")
        or not os.path.isdir(workspace_resolved)
        or not app._workspace_path_is_descendant(source_resolved, workspace_resolved)
        or os.path.basename(source_resolved) != os.path.basename(source_path)
    ):
        return {"ok": False, "rehydrated": False, "reason": "source_path_unsafe"}
    if os.path.isfile(source_resolved):
        if (
            os.path.getsize(source_resolved) > 0
            and app._subdub_sha256_file(source_resolved) == SOURCE_SHA256
        ):
            return {"ok": True, "rehydrated": False, "path": source_resolved}
        return {"ok": False, "rehydrated": False, "reason": "source_sha256_mismatch"}
    stored_file_unique_id, stored_file_id = (
        app._subdub_recovery_file_identity(current, recovery)
    )
    input_file_id = str(input_save.get("file_id") or "").strip()
    expected_size = int(
        input_save.get("transport_input_size")
        or current.get("input_size_bytes")
        or 0
    )
    if (
        not stored_file_unique_id
        or not stored_file_id
        or stored_file_id == stored_file_unique_id
        or input_file_id not in {"", stored_file_unique_id, stored_file_id}
        or expected_size <= 0
    ):
        return {"ok": False, "rehydrated": False, "reason": "source_file_id_invalid"}
    source_bytes, content_type = await app.video_dubbing_download_source(
        SimpleNamespace(bot=telegram_bot),
        {
            "source_file_id": stored_file_id,
            "video_file_id": stored_file_id,
            "source_file_name": os.path.basename(source_resolved),
            "source_file_size": expected_size,
            "video_file_size": expected_size,
            "source_mime_type": "video/mp4",
            "_pipeline_is_admin": True,
        },
    )
    digest = hashlib.sha256(source_bytes).hexdigest()
    if (
        content_type != "video/mp4"
        or len(source_bytes) != expected_size
        or digest != SOURCE_SHA256
    ):
        return {"ok": False, "rehydrated": False, "reason": "source_sha256_mismatch"}
    temporary = Path(source_resolved + ".rehydrate.tmp")
    try:
        temporary.write_bytes(source_bytes)
        if temporary.stat().st_size != expected_size or app._subdub_sha256_file(str(temporary)) != SOURCE_SHA256:
            raise OSError("source_rehydrate_verify_failed")
        os.replace(str(temporary), source_resolved)
    except OSError:
        temporary.unlink(missing_ok=True)
        return {"ok": False, "rehydrated": False, "reason": "source_rehydrate_write_failed"}
    return {"ok": True, "rehydrated": True, "path": source_resolved}


def _preflight_result(
    acoustic_preflight: Callable[[], dict] | None,
) -> dict:
    service = app.auto_multi_speaker.subdub_multi_speaker_embedding_onnx
    preflight = acoustic_preflight or app._subdub_multi_acoustic_model_preflight
    if not callable(preflight):
        return {}
    try:
        result = dict(preflight() or {})
    except Exception:
        return {}
    if not (
        result.get("ok") is True
        and result.get("status") == "PASS"
        and result.get("model_sha256") == service.MODEL_SHA256
        and result.get("algorithm_version") == service.FIXED_VOCAL_ALGORITHM_VERSION
        and list(result.get("providers") or []) == ["CPUExecutionProvider"]
    ):
        return {}
    return result


def claim_same_attempt(
    *,
    acoustic_preflight: Callable[[], dict] | None = None,
) -> dict:
    """CAS-rearm the exact failed v1 job once without incrementing its attempt."""

    preflight = _preflight_result(acoustic_preflight)
    if not preflight:
        return {
            "ok": False,
            "claimed": False,
            "reason": "fixed_vocal_v2_preflight_failed",
        }
    service = app.auto_multi_speaker.subdub_multi_speaker_embedding_onnx
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
        recovery = current.get("auto_multi_recovery")
        attempt_row = conn.execute(
            """SELECT value,updated_at,updated_by
               FROM system_settings
               WHERE key='provider_attempt:translation_asr'
               LIMIT 1"""
        ).fetchone()
        provider_attempt = {}
        provider_attempt_updated_at = ""
        provider_attempt_updated_by = ""
        if attempt_row:
            provider_attempt = json.loads(str(attempt_row[0] or "{}"))
            if type(provider_attempt) is not dict:
                provider_attempt = {}
            provider_attempt_updated_at = str(attempt_row[1] or "")
            provider_attempt_updated_by = str(attempt_row[2] or "")
        false_fields = (
            "asr_started",
            "translation_started",
            "tts_started",
            "mux_started",
            "artifact_started",
            "delivery_attempted",
            "final_mp4_exists",
            "output_validated",
            "output_sent",
        )
        path_fields = (
            "final_mp4_path",
            "final_output_path",
            "output_path",
            "output_video_path",
            "final_video_path",
            "dub_video_path",
            "video_delivery_message_id",
            "final_video_message_id",
            "delivery_message_id",
            "telegram_message_id",
        )
        root_source_sha256 = current.get("source_sha256")
        root_target_language = current.get("target_language")
        root_original_volume = current.get("original_audio_volume_percent")
        root_dub_volume = current.get("dubbed_voice_volume_percent")
        root_selection_conflicts = bool(
            (
                root_source_sha256 not in {None, ""}
                and (
                    not isinstance(root_source_sha256, str)
                    or root_source_sha256.strip().lower() != SOURCE_SHA256
                )
            )
            or (
                root_target_language not in {None, ""}
                and root_target_language != "English"
            )
            or (
                root_original_volume is not None
                and (
                    type(root_original_volume) is not int
                    or root_original_volume != 40
                )
            )
            or (
                root_dub_volume is not None
                and (type(root_dub_volume) is not int or root_dub_volume != 150)
            )
        )
        actual_evidence_fields = (
            "multi_acoustic_backend",
            "multi_acoustic_model_sha256",
            "multi_acoustic_algorithm_version",
            "multi_acoustic_speaker_count",
            "multi_acoustic_word_count",
            "multi_acoustic_unit_count",
            "multi_acoustic_embedding_window_count",
            "multi_acoustic_cluster_sizes",
            "multi_acoustic_stability_pass",
            "multi_acoustic_word_coverage_count",
            "multi_acoustic_overlap_mapped_count",
            "multi_acoustic_centroid_mapped_count",
            "multi_acoustic_speaker_unit_counts",
            "multi_acoustic_failure_code",
            "multi_acoustic_failure_word_count",
            "multi_acoustic_failure_duration_ms",
        )
        actual_v2_evidence_present = any(
            bool(current.get(field)) for field in actual_evidence_fields
        )
        input_save = current.get("input_save")
        if type(input_save) is not dict:
            input_save = {}
        root_source_duration_exact = current.get("source_duration_exact")
        nested_source_duration_exact = input_save.get("source_duration_exact")
        source_duration_exact = (
            root_source_duration_exact
            if type(root_source_duration_exact) in {int, float}
            else nested_source_duration_exact
        )
        root_input_duration = current.get("input_duration")
        nested_input_duration = input_save.get("duration")
        input_duration = (
            root_input_duration
            if type(root_input_duration) is int
            else nested_input_duration
        )
        duration_authority_conflict = bool(
            type(root_source_duration_exact) in {int, float}
            and type(nested_source_duration_exact) in {int, float}
            and abs(
                float(root_source_duration_exact)
                - float(nested_source_duration_exact)
            )
            > 0.00001
        ) or bool(
            type(root_input_duration) is int
            and type(nested_input_duration) is int
            and root_input_duration != nested_input_duration
        )
        initial_rearm = bool(
            current.get(REARM_MARKER) is not True
            and current.get(DURATION_REPAIR_MARKER) is not True
            and current.get(ASR_TIMEOUT_REPAIR_MARKER) is not True
        )
        duration_repair = bool(
            current.get(REARM_MARKER) is True
            and current.get(DURATION_REPAIR_MARKER) is not True
            and current.get("auto_multi_fixed_vocal_v2_recovery_authority")
            == "owner_confirmed_same_job_upgrade"
            and type(source_duration_exact) in {int, float}
            and 0.0 < float(source_duration_exact) <= 300.0
            and abs(float(source_duration_exact) - 133.37542) <= 0.00001
            and type(input_duration) is int
            and input_duration == 134
            and abs(float(input_duration) - float(source_duration_exact)) > 0.25
            and current.get("multi_diarization_attempted") is True
            and current.get("multi_diarization_provider")
            == "gemini_transcribe_multi_diarization"
            and current.get("multi_diarization_status") == "PASS"
            and current.get("multi_diarization_detail")
            == "words=147; speakers=4"
            and current.get("multi_diarization_http_status") == 200
            and current.get("multi_diarization_provider_word_count") == 147
            and current.get("multi_diarization_provider_speaker_count") == 4
            and current.get("multi_diarization_mapped_speaker_count") == 0
            and current.get("multi_diarization_raw_annotation_count") == 151
            and current.get("multi_diarization_terminal_empty") is False
            and current.get("multi_diarization_parse_rejection") == ""
            and current.get("multi_diarization_dropped_weak_word_count") == 1
            and current.get("multi_diarization_dropped_weak_speaker_count") == 1
            and current.get("multi_diarization_weak_label_filter_applied") is True
            and not duration_authority_conflict
            and not actual_v2_evidence_present
        )
        exact_timeout_receipt = bool(
            provider_attempt.get("called") is True
            and provider_attempt.get("provider") == "deepgram"
            and provider_attempt.get("route") == "listen"
            and provider_attempt.get("status") == "DEEPGRAM_EMPTY_TRANSCRIPT"
            and provider_attempt.get("error") == "deepgram_timeout"
            and provider_attempt.get("at") == "2026-09-02 22:31:08"
            and provider_attempt_updated_at == "2026-09-02 22:31:08"
            and provider_attempt_updated_by == str(OWNER_ID)
        )
        asr_timeout_repair = bool(
            current.get(REARM_MARKER) is True
            and current.get(DURATION_REPAIR_MARKER) is True
            and current.get(ASR_TIMEOUT_REPAIR_MARKER) is not True
            and current.get("auto_multi_fixed_vocal_v2_recovery_authority")
            == "owner_confirmed_same_job_upgrade"
            and current.get("auto_multi_fixed_vocal_v2_duration_repair_authority")
            == "owner_confirmed_same_job_exact_duration"
            and current.get("auto_multi_fixed_vocal_v2_duration_repair_from_seconds")
            == 134.0
            and type(
                current.get("auto_multi_fixed_vocal_v2_duration_repair_to_seconds")
            ) in {int, float}
            and abs(
                float(
                    current.get(
                        "auto_multi_fixed_vocal_v2_duration_repair_to_seconds"
                    )
                )
                - 133.37542
            )
            <= 0.00001
            and current.get("asr_started") is True
            and current.get("last_error_stage") in {None, ""}
            and current.get("last_error_safe") in {None, ""}
            and exact_timeout_receipt
            and not duration_authority_conflict
            and not actual_v2_evidence_present
        )
        context_repair = _context_repair_candidate(current)
        original_source_repair = _original_source_repair_candidate(current)
        acoustic_runtime_budget_repair = (
            _acoustic_runtime_budget_repair_candidate(current)
        )
        acoustic_full_media_duration_repair = (
            _acoustic_full_media_duration_repair_candidate(current)
        )
        pending_multi_lane_repair = _pending_multi_lane_repair_candidate(current)
        downstream_false_fields = tuple(
            field for field in false_fields if field != "asr_started"
        )
        stage_authority_valid = bool(
            (
                asr_timeout_repair
                and current.get("asr_started") is True
                and all(
                    field in current and current.get(field) is False
                    for field in downstream_false_fields
                )
            )
            or (
                not asr_timeout_repair
                and all(
                    field in current and current.get(field) is False
                    for field in false_fields
                )
            )
        )
        failure_authority_valid = bool(
            (asr_timeout_repair and current.get("last_error_stage") in {None, ""})
            or (
                not asr_timeout_repair
                and current.get("last_error_stage") == "AUTO_CAST_MANUAL_REQUIRED"
            )
        )
        allowed = bool(
            type(current) is dict
            and type(recovery) is dict
            and app.subdub_failed_auto_multi_recovery_state(current)
            and str(current.get("internal_job_id") or current.get("job_id") or "")
            == JOB_ID
            and current.get("public_code") == PUBLIC_CODE
            and str(current.get("user_id") or "") == str(OWNER_ID)
            and str(current.get("chat_id") or current.get("user_id") or "")
            == str(OWNER_ID)
            and str(current.get("job_key") or "").endswith(
                "|subtitle_plus_dub|auto_multi_speaker"
            )
            and current.get("status") == "failed_no_charge"
            and current.get("terminal_state") == "failed_no_charge"
            and current.get("auto_multi_recovery_attempt_count") == 4
            and current.get("auto_multi_recovery_correction_attempt_count") == 3
            and current.get("auto_multi_acoustic_recovery_used") is True
            and current.get("auto_multi_acoustic_stability_repair_used") is True
            and (
                initial_rearm
                or duration_repair
                or asr_timeout_repair
                or context_repair
                or original_source_repair
                or acoustic_runtime_budget_repair
                or acoustic_full_media_duration_repair
                or pending_multi_lane_repair
            )
            and current.get("auto_multi_acoustic_backend") == PREVIOUS_BACKEND
            and current.get("auto_multi_acoustic_model_sha256")
            == service.MODEL_SHA256
            and current.get("auto_multi_acoustic_algorithm_version")
            == PREVIOUS_ALGORITHM
            and not root_selection_conflicts
            and (
                original_source_repair
                or acoustic_runtime_budget_repair
                or acoustic_full_media_duration_repair
                or pending_multi_lane_repair
                or not actual_v2_evidence_present
            )
            and current.get("pipeline_started") is True
            and failure_authority_valid
            and type(current.get("charged_xu")) is int
            and current.get("charged_xu") == 0
            and current.get("charge_status") == "not_charged"
            and stage_authority_valid
            and not any(str(current.get(field) or "").strip() for field in path_fields)
            and recovery.get("owner_confirmed_paid") is True
            and str(recovery.get("source_sha256") or "").lower() == SOURCE_SHA256
            and recovery.get("target_language") == "English"
            and recovery.get("original_volume_percent") == 40
            and recovery.get("dub_volume_percent") == 150
        )
        if not allowed:
            conn.rollback()
            return {
                "ok": False,
                "claimed": False,
                "reason": "fixed_vocal_v2_rearm_not_allowed",
            }
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
                REARM_MARKER: True,
                **(
                    {
                        DURATION_REPAIR_MARKER: True,
                        "auto_multi_fixed_vocal_v2_duration_repair_authority": (
                            "owner_confirmed_same_job_exact_duration"
                        ),
                        "auto_multi_fixed_vocal_v2_duration_repair_from_seconds": (
                            float(input_duration)
                        ),
                        "auto_multi_fixed_vocal_v2_duration_repair_to_seconds": (
                            float(source_duration_exact)
                        ),
                    }
                    if duration_repair
                    else {}
                ),
                **(
                    {
                        CONTEXT_REPAIR_MARKER: True,
                        "auto_multi_private_pipeline_context_repair_authority": (
                            "owner_confirmed_same_job_private_pipeline_context"
                        ),
                        "auto_multi_private_pipeline_context_repair_claimed_at": (
                            app.time.time()
                        ),
                        "asr_started": False,
                    }
                    if context_repair
                    else {}
                ),
                **(
                    {
                        ORIGINAL_SOURCE_REPAIR_MARKER: True,
                        "auto_multi_original_acoustic_source_repair_authority": (
                            "owner_confirmed_same_job_original_acoustic_source"
                        ),
                        "auto_multi_original_acoustic_source_repair_claimed_at": (
                            app.time.time()
                        ),
                        "multi_acoustic_failure_code": "",
                        "multi_acoustic_failure_word_count": 0,
                        "multi_acoustic_failure_duration_ms": 0,
                        "asr_started": False,
                    }
                    if original_source_repair
                    else {}
                ),
                **(
                    {
                        ACOUSTIC_RUNTIME_BUDGET_REPAIR_MARKER: True,
                        "auto_multi_acoustic_runtime_budget_repair_authority": (
                            "owner_confirmed_same_job_duration_scaled_acoustic_budget"
                        ),
                        "auto_multi_acoustic_runtime_budget_repair_claimed_at": (
                            app.time.time()
                        ),
                        "multi_acoustic_failure_code": "",
                        "multi_acoustic_failure_word_count": 0,
                        "multi_acoustic_failure_duration_ms": 0,
                        "asr_started": False,
                    }
                    if acoustic_runtime_budget_repair
                    else {}
                ),
                **(
                    {
                        ACOUSTIC_FULL_MEDIA_DURATION_REPAIR_MARKER: True,
                        "auto_multi_acoustic_full_media_duration_repair_authority": (
                            "owner_confirmed_same_job_full_original_media_duration"
                        ),
                        "auto_multi_acoustic_full_media_duration_repair_claimed_at": (
                            app.time.time()
                        ),
                        "multi_acoustic_failure_code": "",
                        "multi_acoustic_failure_word_count": 0,
                        "multi_acoustic_failure_duration_ms": 0,
                        "asr_started": False,
                    }
                    if acoustic_full_media_duration_repair
                    else {}
                ),
                **(
                    {
                        PENDING_MULTI_LANE_REPAIR_MARKER: True,
                        "auto_multi_pending_lane_repair_authority": (
                            "owner_confirmed_same_job_preserve_multi_lane"
                        ),
                        "auto_multi_pending_lane_repair_claimed_at": app.time.time(),
                        "multi_acoustic_failure_code": "",
                        "multi_acoustic_failure_word_count": 0,
                        "multi_acoustic_failure_duration_ms": 0,
                        "asr_started": False,
                    }
                    if pending_multi_lane_repair
                    else {}
                ),
                **(
                    {
                        ASR_TIMEOUT_REPAIR_MARKER: True,
                        "auto_multi_fixed_vocal_v2_asr_timeout_repair_authority": (
                            "owner_confirmed_same_job_deepgram_timeout"
                        ),
                        "auto_multi_fixed_vocal_v2_asr_timeout_receipt_at": (
                            "2026-09-02 22:31:08"
                        ),
                        "auto_multi_fixed_vocal_v2_asr_timeout_seconds": 300,
                        "asr_started": False,
                    }
                    if asr_timeout_repair
                    else {}
                ),
                "auto_multi_fixed_vocal_v2_recovery_authority": (
                    "owner_confirmed_same_job_upgrade"
                ),
                "auto_multi_fixed_vocal_v2_recovery_from_backend": (
                    PREVIOUS_BACKEND
                ),
                "auto_multi_fixed_vocal_v2_recovery_from_algorithm": (
                    PREVIOUS_ALGORITHM
                ),
                "auto_multi_fixed_vocal_v2_recovery_target_backend": (
                    service.FIXED_VOCAL_PROVIDER
                ),
                "auto_multi_fixed_vocal_v2_recovery_target_algorithm": (
                    service.FIXED_VOCAL_ALGORITHM_VERSION
                ),
                "auto_multi_fixed_vocal_v2_recovery_claimed_at": app.time.time(),
                "updated_at": app.time.time(),
            }
        )
        new_value = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
        cursor = conn.execute(
            """UPDATE system_settings
               SET value=?,note=?,updated_at=?,updated_by=?
               WHERE key=? AND value=?""",
            (
                new_value,
                "SubDub same-job fixed-vocal v2 rearm",
                app.now_text(),
                str(OWNER_ID),
                key,
                old_value,
            ),
        )
        if int(cursor.rowcount or 0) != 1:
            conn.rollback()
            return {
                "ok": False,
                "claimed": False,
                "reason": "fixed_vocal_v2_rearm_cas_lost",
            }
        conn.commit()
        app.ENGINE_ASYNC_MEMORY_JOBS[JOB_ID] = dict(current)
        app.SUBTITLE_DUB_PIPELINE_JOBS[str(current.get("job_key") or "")] = dict(
            current
        )
        return {"ok": True, "claimed": True, "job": dict(current)}
    except (json.JSONDecodeError, OSError, sqlite3.Error, TypeError, ValueError):
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
        return {
            "ok": False,
            "claimed": False,
            "reason": "fixed_vocal_v2_rearm_cas_error",
        }
    finally:
        if conn is not None:
            conn.close()


async def run() -> None:
    application = app.build_telegram_application()
    async with application.bot as telegram_bot:
        source = await ensure_exact_source(telegram_bot)
        if not source.get("ok") and source.get("reason") != "context_repair_not_allowed":
            raise RuntimeError(str(source.get("reason") or "source_rehydrate_failed"))
        claim = claim_same_attempt()
        if not claim.get("claimed"):
            raise RuntimeError(
                str(claim.get("reason") or "fixed_vocal_v2_rearm_failed")
            )

        async def reply_text(text, **kwargs):
            return await telegram_bot.send_message(
                chat_id=OWNER_ID,
                text=text,
                **kwargs,
            )

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=OWNER_ID),
            message=SimpleNamespace(chat_id=OWNER_ID, reply_text=reply_text),
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


if __name__ == "__main__":
    asyncio.run(run())
