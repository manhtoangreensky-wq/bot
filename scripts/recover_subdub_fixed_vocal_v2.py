"""One-shot same-job rearm from the deployed Auto Multi acoustic v1 to v2."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from types import SimpleNamespace
from typing import Callable

from telegram import Bot

import bot as app


JOB_ID = "b4cb6d5fe8a7bdfce507"
PUBLIC_CODE = "B4CB6D5FE8"
OWNER_ID = 7_126_457_028
SOURCE_SHA256 = "83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e"
PREVIOUS_BACKEND = "local_wespeaker_resnet34_spectral"
PREVIOUS_ALGORITHM = "wespeaker-resnet34-spectral-v1"
REARM_MARKER = "auto_multi_fixed_vocal_v2_recovery_used"


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
            "multi_acoustic_failure_code",
            "multi_acoustic_failure_word_count",
            "multi_acoustic_failure_duration_ms",
        )
        actual_v2_evidence_present = any(
            bool(current.get(field)) for field in actual_evidence_fields
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
            and current.get(REARM_MARKER) is not True
            and current.get("auto_multi_acoustic_backend") == PREVIOUS_BACKEND
            and current.get("auto_multi_acoustic_model_sha256")
            == service.MODEL_SHA256
            and current.get("auto_multi_acoustic_algorithm_version")
            == PREVIOUS_ALGORITHM
            and not root_selection_conflicts
            and not actual_v2_evidence_present
            and current.get("pipeline_started") is True
            and current.get("last_error_stage") == "AUTO_CAST_MANUAL_REQUIRED"
            and type(current.get("charged_xu")) is int
            and current.get("charged_xu") == 0
            and current.get("charge_status") == "not_charged"
            and all(
                field in current and current.get(field) is False
                for field in false_fields
            )
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
    async with Bot(token=app.TELEGRAM_TOKEN) as telegram_bot:
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
