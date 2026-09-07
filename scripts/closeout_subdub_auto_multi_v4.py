"""Close out one delivered Auto Multi v4 video without replaying providers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
from types import SimpleNamespace
from typing import Callable, Mapping

import bot as app
from scripts import recover_subdub_auto_multi_v4 as v4
from scripts import recover_subdub_fixed_vocal_v2 as legacy


TIMING_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "subdub_auto_multi_missing_speech_cluster_timing_145.json"
)
TIMING_SHA256 = "7f571a38b78bd75f18307f3f41e52cd0926bae92b39a7fd32051e88da6ccf82c"
CLOSEOUT_MARKER = "auto_multi_v4_delivery_proof_closeout_used"
CLOSEOUT_AUTHORITY = "owner_confirmed_same_job_delivery_proof_receipt"
EXPECTED_REGISTERS = ["high", "low", "low", "high", "low"]
EXPECTED_TTS_CUES = 21


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _valid_sha256(value: object) -> bool:
    token = str(value or "").strip().lower()
    return len(token) == 64 and all(char in "0123456789abcdef" for char in token)


def _delivery_authority(current: dict) -> bool:
    input_save = current.get("input_save")
    source_probe = (input_save or {}).get("media_preflight")
    output = current.get("output_validation")
    receipt = current.get("auto_exact_receipt")
    history = current.get("auto_multi_v3_delivery_history")
    video_message_id = str(current.get("video_delivery_message_id") or "").strip()
    try:
        delivery_duration = float(current.get("video_delivery_duration_seconds") or 0.0)
        output_duration = float(
            (output or {}).get("actual_duration")
            or (output or {}).get("duration")
            or 0.0
        )
    except (TypeError, ValueError, OverflowError):
        return False
    return bool(
        type(current) is dict
        and isinstance(input_save, dict)
        and isinstance(source_probe, dict)
        and isinstance(output, dict)
        and isinstance(receipt, dict)
        and isinstance(history, dict)
        and str(current.get("internal_job_id") or current.get("job_id") or "")
        == v4.JOB_ID
        and current.get("public_code") == v4.PUBLIC_CODE
        and str(current.get("user_id") or "") == str(v4.OWNER_ID)
        and str(current.get("chat_id") or current.get("user_id") or "")
        == str(v4.OWNER_ID)
        and str(current.get("job_key") or "").endswith(
            "|subtitle_plus_dub|auto_multi_speaker"
        )
        and current.get(v4.V4_REPAIR_MARKER) is True
        and current.get(v4.V4_QUORUM_REPAIR_MARKER) is True
        and current.get("auto_multi_v4_recovery_authority")
        == v4.V4_REPAIR_AUTHORITY
        and current.get("auto_multi_acoustic_view_quorum_repair_authority")
        == v4.V4_QUORUM_REPAIR_AUTHORITY
        and current.get("status") == "delivered"
        and current.get("terminal_state") == "delivered"
        and current.get("charge_status") == "admin_free"
        and current.get("charged_xu") == 0
        and current.get("output_sent") is True
        and current.get("final_mp4_validated") is True
        and current.get("final_mp4_delivered") is True
        and current.get("output_validated") is True
        and current.get("delivery_attempt_uncertain") is not True
        and video_message_id
        and video_message_id != str(history.get("video_message_id") or "").strip()
        and not str(current.get("receipt_message_id") or "").strip()
        and not str(current.get("subdub_success_message_id") or "").strip()
        and current.get("receipt_sent_once") is not True
        and current.get("receipt_send_uncertain") is not True
        and input_save.get("original_source_sha256") == v4.SOURCE_SHA256
        and input_save.get("transport_input_size") == v4.SOURCE_BYTES
        and input_save.get("content_type") == "video/mp4"
        and source_probe.get("ok") is True
        and source_probe.get("has_video") is True
        and source_probe.get("has_audio") is True
        and output.get("ok") is True
        and output.get("container") == "mp4"
        and output.get("video_codec") == "h264"
        and output.get("audio_codec") == "aac"
        and output.get("has_video") is True
        and output.get("has_audio") is True
        and output.get("rotation") == 0
        and app.subdub_aspect_ratio_close(
            source_probe.get("display_width"),
            source_probe.get("display_height"),
            output.get("display_width"),
            output.get("display_height"),
        )
        and type(current.get("video_delivery_size_bytes")) is int
        and current.get("video_delivery_size_bytes") > 0
        and current.get("video_delivery_size_bytes") == output.get("size")
        and _valid_sha256(current.get("video_delivery_sha256"))
        and math.isfinite(delivery_duration)
        and delivery_duration > 0.0
        and math.isfinite(output_duration)
        and abs(delivery_duration - output_duration) <= 0.1
        and receipt.get("internal_job_id") == v4.JOB_ID
        and str(receipt.get("owner_user_id") or "") == str(v4.OWNER_ID)
        and receipt.get("claim_state") == "admin_free"
        and receipt.get("consumed") is True
        and _valid_sha256(receipt.get("sidecar_sha256"))
        and str(current.get("auto_multi_v3_video_delivery_message_id") or "")
        == str(history.get("video_message_id") or "")
        and str(current.get("auto_multi_v3_receipt_message_id") or "")
        == str(history.get("receipt_message_id") or "")
        and str(history.get("video_message_id") or "")
        and str(history.get("receipt_message_id") or "")
    )


def v4_delivery_closeout_candidate(current: dict) -> bool:
    if not _delivery_authority(current):
        return False
    if current.get(CLOSEOUT_MARKER) is True:
        return bool(app.subdub_auto_multi_terminal_proof_fields(current))
    return bool(v4.validated_v4_source_path(current))


def _acoustic_state_fields(result: Mapping[str, object]) -> dict:
    return {
        "multi_acoustic_backend": result.get("provider"),
        "multi_acoustic_model_sha256": result.get("model_sha256"),
        "multi_acoustic_algorithm_version": result.get("algorithm_version"),
        "multi_acoustic_speaker_count": result.get("detected_speaker_count"),
        "multi_acoustic_word_count": result.get("word_count"),
        "multi_acoustic_unit_count": result.get("unit_count"),
        "multi_acoustic_embedding_window_count": result.get("embedding_window_count"),
        "multi_acoustic_cluster_sizes": result.get("cluster_sizes"),
        "multi_acoustic_stability_pass": result.get("stability_pass"),
        "multi_acoustic_word_coverage_count": result.get("word_coverage_count"),
        "multi_acoustic_overlap_mapped_count": result.get("overlap_mapped_count"),
        "multi_acoustic_centroid_mapped_count": result.get("centroid_mapped_count"),
        "multi_acoustic_speaker_unit_counts": result.get("speaker_unit_counts"),
        "multi_acoustic_word_overlap_mapped_count": result.get("word_overlap_mapped_count"),
        "multi_acoustic_word_fallback_mapped_count": result.get("word_fallback_mapped_count"),
        "multi_acoustic_word_centroid_mapped_count": result.get("word_centroid_mapped_count"),
        "multi_acoustic_speaker_count_authority_asr_independent": result.get("speaker_count_authority_asr_independent"),
        "multi_acoustic_word_attribution_uses_asr_timeline": result.get("word_attribution_uses_asr_timeline"),
        "multi_acoustic_speaker_registers": result.get("speaker_registers"),
        "multi_acoustic_speaker_register_confidences": result.get("speaker_register_confidences"),
        "multi_acoustic_female_speaker_count": result.get("female_speaker_count"),
        "multi_acoustic_male_speaker_count": result.get("male_speaker_count"),
        "multi_acoustic_gender_model_sha256": result.get("gender_model_sha256"),
        "multi_acoustic_gender_ambiguous_window_count": result.get("gender_ambiguous_window_count"),
        "multi_acoustic_raw_speaker_count": result.get("raw_speaker_count"),
        "multi_acoustic_raw_embedding_window_count": result.get("raw_embedding_window_count"),
        "multi_acoustic_raw_cluster_sizes": result.get("raw_cluster_sizes"),
        "multi_acoustic_raw_speaker_unit_counts": result.get("raw_speaker_unit_counts"),
        "multi_acoustic_raw_overlap_speaker_unit_counts": result.get("raw_overlap_speaker_unit_counts"),
        "multi_acoustic_speech_supported_speaker_labels": result.get("speech_supported_speaker_labels"),
        "multi_acoustic_dropped_non_speech_speaker_labels": result.get("dropped_non_speech_speaker_labels"),
        "multi_acoustic_dropped_non_speech_speaker_count": len(
            list(result.get("dropped_non_speech_speaker_labels") or [])
        ),
    }


def v4_closeout_proof_fields(
    current: dict,
    acoustic_result: Mapping[str, object],
    *,
    voice_pools: dict[str, list[str]] | None = None,
) -> dict:
    if not _delivery_authority(current) or not isinstance(acoustic_result, Mapping):
        return {}
    segments = acoustic_result.get("segments")
    registers = list(acoustic_result.get("speaker_registers") or [])
    confidences = list(acoustic_result.get("speaker_register_confidences") or [])
    if not isinstance(segments, list) or not segments:
        return {}
    labels = app.subdub_speaker_cast.ordered_auto_speaker_labels(segments)
    expected_labels = [
        app.subdub_speaker_cast.normalized_speaker_key(0, index)
        for index in range(5)
    ]
    final_cues = [
        item
        for item in segments
        if isinstance(item, Mapping)
        and abs(float(item.get("start") or 0.0) - 126.005) <= 0.001
        and abs(float(item.get("end") or 0.0) - 126.505) <= 0.001
    ]
    tts_rows = current.get("tts_cue_qc")
    if (
        acoustic_result.get("ok") is not True
        or acoustic_result.get("raw_speaker_count") != 5
        or acoustic_result.get("detected_speaker_count") != 5
        or acoustic_result.get("word_count") != 145
        or acoustic_result.get("word_coverage_count") != 145
        or labels != expected_labels
        or registers != EXPECTED_REGISTERS
        or len(confidences) != 5
        or acoustic_result.get("female_speaker_count") != 2
        or acoustic_result.get("male_speaker_count") != 3
        or len(final_cues) != 1
        or final_cues[0].get("voice_register") != "high"
        or not isinstance(tts_rows, list)
        or len(tts_rows) != EXPECTED_TTS_CUES
        or any(not isinstance(row, dict) or row.get("ok") is not True for row in tts_rows)
    ):
        return {}
    bounded = app.auto_multi_speaker.bounded_multi_acoustic_evidence(
        _acoustic_state_fields(acoustic_result)
    )
    if not bounded:
        return {}
    classifications = {
        label: {
            "speaker_id": label,
            "voice_register": registers[index],
            "confidence": confidences[index],
        }
        for index, label in enumerate(labels)
    }
    pools = voice_pools or app.subdub_auto_validated_voice_pools(
        app.subdub_tts_provider_name()
    )
    try:
        casts = app.subdub_speaker_cast.assign_stable_voices(
            classifications,
            speaker_order=labels,
            validated_pools=pools,
            assignment_seed=str(
                (current.get("auto_exact_receipt") or {}).get("sidecar_sha256")
                or ""
            ),
        )
    except (
        app.subdub_speaker_cast.AutoCastUnavailable,
        app.subdub_speaker_cast.AutoCastManualRequired,
    ):
        return {}
    speaker_voices = {
        label: str(casts[label].get("voice_id") or "") for label in labels
    }
    if len(set(speaker_voices.values())) != 5 or not all(speaker_voices.values()):
        return {}
    cast_payload = json.dumps(
        sorted(speaker_voices.items()),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    input_save = dict(current.get("input_save") or {})
    source_probe = dict(input_save.get("media_preflight") or {})
    output = dict(current.get("output_validation") or {})
    candidate = {
        **current,
        **bounded,
        "auto_detected_speaker_count": 5,
        "auto_distinct_voice_count": 5,
        "auto_multi_voice_verified": True,
        "auto_multi_attribution_verified": True,
        "auto_multi_geometry_verified": True,
        "auto_multi_source_display_width": int(source_probe.get("display_width") or 0),
        "auto_multi_source_display_height": int(source_probe.get("display_height") or 0),
        "auto_multi_output_display_width": int(output.get("display_width") or 0),
        "auto_multi_output_display_height": int(output.get("display_height") or 0),
        "auto_multi_output_rotation": int(output.get("rotation") or 0),
        "auto_multi_cast_sha256": hashlib.sha256(cast_payload).hexdigest(),
    }
    proof = app.subdub_auto_multi_terminal_proof_fields(candidate)
    if not proof:
        return {}
    proof.update(
        {
            "tts_expected_segments": EXPECTED_TTS_CUES,
            "tts_generated_segments": EXPECTED_TTS_CUES,
            "tts_dropped_segments": 0,
            "auto_multi_final_cue_start": 126.005,
            "auto_multi_final_cue_end": 126.505,
            "auto_multi_final_cue_register": "high",
            "auto_multi_voice_id_hashes": [
                hashlib.sha256(speaker_voices[label].encode("utf-8")).hexdigest()
                for label in labels
            ],
            "auto_multi_speaker_voice_hashes": {
                label: hashlib.sha256(
                    speaker_voices[label].encode("utf-8")
                ).hexdigest()
                for label in labels
            },
            "multi_acoustic_speech_partition_base_shift_agreement": float(
                acoustic_result.get("speech_partition_base_shift_agreement") or 0.0
            ),
            "multi_acoustic_speech_partition_base_aggregate_agreement": float(
                acoustic_result.get("speech_partition_base_aggregate_agreement") or 0.0
            ),
        }
    )
    return proof


def _timing_words() -> list[dict]:
    if (
        not TIMING_PATH.is_file()
        or _sha256_file(TIMING_PATH) != TIMING_SHA256
    ):
        return []
    try:
        words = json.loads(TIMING_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    return words if isinstance(words, list) and len(words) == 145 else []


def measure_v4_closeout_acoustic(current: dict) -> dict:
    source = v4.validated_v4_source_path(current)
    words = _timing_words()
    input_save = dict(current.get("input_save") or {})
    duration = input_save.get("source_duration_exact")
    if not source or not words or type(duration) not in {int, float}:
        return {}
    if not v4.v4_preflight_result():
        return {}
    ffmpeg = app.frame_video_ffmpeg_path()
    if not ffmpeg:
        return {}
    with tempfile.TemporaryDirectory(prefix="subdub-v4-closeout-") as directory:
        pcm_path = Path(directory) / "source-stereo-44100-s16le.pcm"
        try:
            completed = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-y",
                    "-i",
                    source,
                    "-vn",
                    "-ac",
                    "2",
                    "-ar",
                    "44100",
                    "-f",
                    "s16le",
                    str(pcm_path),
                ],
                check=False,
                capture_output=True,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError):
            return {}
        if completed.returncode != 0 or not pcm_path.is_file():
            return {}
        try:
            return dict(
                app.auto_multi_speaker.subdub_multi_speaker_embedding_onnx
                .diarize_fixed_vocal_word_timeline(
                    str(pcm_path),
                    words,
                    duration_seconds=float(duration),
                    deadline_monotonic=time.monotonic() + 540.0,
                    stop_requested=lambda: False,
                )
            )
        except (
            app.subdub_speaker_cast.AutoCastUnavailable,
            app.subdub_speaker_cast.AutoCastManualRequired,
        ):
            return {}


def claim_v4_closeout_proof(
    acoustic_result: Mapping[str, object] | None = None,
    *,
    connection_factory: Callable[[], sqlite3.Connection] | None = None,
    voice_pools: dict[str, list[str]] | None = None,
) -> dict:
    current = v4.read_v4_terminal_job()
    if not v4_delivery_closeout_candidate(current):
        return {"ok": False, "claimed": False, "reason": "closeout_not_allowed"}
    if current.get(CLOSEOUT_MARKER) is True:
        return {"ok": True, "claimed": False, "job": current}
    measured = dict(acoustic_result or measure_v4_closeout_acoustic(current))
    proof = v4_closeout_proof_fields(
        current,
        measured,
        voice_pools=voice_pools,
    )
    if not proof:
        return {"ok": False, "claimed": False, "reason": "closeout_proof_invalid"}
    connect = connection_factory or app.db_connect
    conn = None
    try:
        conn = connect()
        conn.execute("BEGIN IMMEDIATE")
        key = app._engine_async_job_key(v4.JOB_ID)
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=? LIMIT 1",
            (key,),
        ).fetchone()
        old_value = str(row[0] or "") if row else ""
        latest = json.loads(old_value) if old_value else {}
        if not v4_delivery_closeout_candidate(latest) or latest.get(CLOSEOUT_MARKER) is True:
            conn.rollback()
            return {"ok": False, "claimed": False, "reason": "closeout_cas_not_allowed"}
        updated = {
            **latest,
            **proof,
            CLOSEOUT_MARKER: True,
            "auto_multi_v4_delivery_proof_closeout_authority": CLOSEOUT_AUTHORITY,
            "auto_multi_v4_delivery_proof_closeout_at": app.time.time(),
        }
        new_value = json.dumps(updated, ensure_ascii=False, separators=(",", ":"))
        cursor = conn.execute(
            """UPDATE system_settings
               SET value=?,note=?,updated_at=?,updated_by=?
               WHERE key=? AND value=?""",
            (
                new_value,
                "SubDub Auto Multi v4 delivered proof closeout",
                app.now_text(),
                str(v4.OWNER_ID),
                key,
                old_value,
            ),
        )
        if int(cursor.rowcount or 0) != 1:
            conn.rollback()
            return {"ok": False, "claimed": False, "reason": "closeout_cas_lost"}
        conn.commit()
        app.ENGINE_ASYNC_MEMORY_JOBS[v4.JOB_ID] = dict(updated)
        app.SUBTITLE_DUB_PIPELINE_JOBS[str(updated.get("job_key") or "")] = dict(
            updated
        )
        return {"ok": True, "claimed": True, "job": updated}
    except (json.JSONDecodeError, sqlite3.Error, TypeError, ValueError):
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
        return {"ok": False, "claimed": False, "reason": "closeout_cas_error"}
    finally:
        if conn is not None:
            conn.close()


async def finalize_v4_panel_and_receipt(telegram_bot, current: dict) -> dict:
    job = dict(current or {})
    job_key = str(job.get("job_key") or "")
    panel_message_id = str(job.get("status_panel_message_id") or "").strip()
    panel_chat_id = str(job.get("status_panel_chat_id") or job.get("chat_id") or "").strip()
    if (
        not v4_delivery_closeout_candidate(job)
        or not job_key
        or not panel_message_id
        or not panel_chat_id
    ):
        raise RuntimeError("v4_closeout_receipt_not_allowed")
    app.SUBTITLE_DUB_PIPELINE_JOBS[job_key] = dict(job)
    try:
        await telegram_bot.edit_message_text(
            chat_id=int(panel_chat_id),
            message_id=int(panel_message_id),
            text=app.subdub_progress_text("delivered", v4.JOB_ID, "vi"),
            parse_mode="HTML",
            reply_markup=app.subdub_progress_keyboard(v4.JOB_ID, "vi"),
        )
    except Exception as exc:
        if not app.subdub_panel_edit_already_terminal(exc):
            raise RuntimeError("v4_closeout_panel_unconfirmed") from exc
    job = app.update_subtitle_dub_pipeline_job(
        job_key,
        status="completed",
        terminal_state="delivered",
        lifecycle_state="delivered",
        current_stage="delivered",
        progress_stage="delivered",
        progress_percent=100,
        panel_finalized=True,
        panel_final_percent=100,
        panel_final_message_id=panel_message_id,
        status_panel_terminalized=True,
        status_panel_terminal_edit_confirmed=True,
        status_panel_terminal_edit_failed=False,
        status_panel_terminal_edit_error="",
        status_panel_terminal_edit_method="stored_message_id_closeout",
        refresh_stopped_after_terminal=True,
    )
    receipt_text = app.video_dubbing_receipt_text(job, job, "vi")
    sent = await app.subdub_send_success_receipt_once(
        legacy._RecoveryMessage(telegram_bot),
        job_key,
        receipt_text,
        reply_markup=app.video_dubbing_receipt_keyboard(
            "vi",
            "translation",
            job,
        ),
    )
    final_job = v4.read_v4_terminal_job()
    if sent is None and not str(final_job.get("receipt_message_id") or "").strip():
        raise RuntimeError("v4_closeout_receipt_unconfirmed")
    return final_job


async def run() -> None:
    claim = claim_v4_closeout_proof()
    if not claim.get("ok"):
        raise RuntimeError(str(claim.get("reason") or "v4_closeout_failed"))
    application = app.build_telegram_application()
    async with application.bot as telegram_bot:
        final_job = await finalize_v4_panel_and_receipt(
            telegram_bot,
            dict(claim.get("job") or {}),
        )
    verification = v4.verify_v4_terminal_job(final_job)
    if not verification.get("ok"):
        raise RuntimeError(
            str(verification.get("reason") or "v4_closeout_terminal_unverified")
        )


if __name__ == "__main__":
    asyncio.run(run())
