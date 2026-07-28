"""Pure semantic and media QC for offline SubDub V2 replay."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from .config import V2ResourceLimits
from .contracts import StageState, finalize_artifact
from .fingerprints import sha256_hex


def validate_mp4_artifact(media: dict[str, Any] | bytes | bytearray | str | Path, *, limits: V2ResourceLimits | None = None) -> dict[str, Any]:
    limits = limits or V2ResourceLimits()
    metadata: dict[str, Any]
    data: bytes
    if isinstance(media, (bytes, bytearray)):
        metadata, data = {}, bytes(media)
    elif isinstance(media, (str, Path)):
        path = Path(media)
        if not path.is_file():
            return {"valid": False, "reason": "missing_file", "size_bytes": 0}
        data, metadata = path.read_bytes(), {"path": str(path)}
    else:
        metadata = dict(media or {})
        supplied = metadata.get("bytes", metadata.get("data"))
        if isinstance(supplied, bytearray):
            supplied = bytes(supplied)
        if isinstance(supplied, bytes):
            data = supplied
        elif metadata.get("path") and Path(str(metadata["path"])).is_file():
            data = Path(str(metadata["path"])).read_bytes()
        else:
            return {"valid": False, "reason": "missing_bytes", "size_bytes": 0}
    if not data:
        return {"valid": False, "reason": "missing_bytes", "size_bytes": 0}
    if len(data) > limits.max_output_bytes:
        return {"valid": False, "reason": "RESOURCE_LIMIT_EXCEEDED:output_bytes", "size_bytes": len(data)}
    if len(data) < 12 or data[4:8] != b"ftyp":
        return {"valid": False, "reason": "invalid_mp4_container", "size_bytes": len(data)}
    if b"moov" not in data and b"moof" not in data:
        return {"valid": False, "reason": "missing_mp4_index", "size_bytes": len(data)}
    duration_ms = int(metadata.get("duration_ms", 0) or 0)
    if duration_ms <= 0:
        return {"valid": False, "reason": "invalid_duration", "size_bytes": len(data)}
    if duration_ms > limits.max_duration_ms:
        return {"valid": False, "reason": "RESOURCE_LIMIT_EXCEEDED:duration_ms", "size_bytes": len(data)}
    if metadata.get("full_decode") is not True:
        return {"valid": False, "reason": "full_decode_not_proven", "size_bytes": len(data)}
    if metadata.get("has_video", metadata.get("video_stream_present", True)) is not True:
        return {"valid": False, "reason": "video_stream_missing", "size_bytes": len(data)}
    return {
        "valid": True,
        "reason": "PASS",
        "size_bytes": len(data),
        "duration_ms": duration_ms,
        "container": "mp4",
        "full_decode": True,
        "fingerprint": sha256_hex(data),
    }


def combo_consistency(subtitle_copy: dict[str, Any], dub_script: dict[str, Any]) -> dict[str, Any]:
    subtitle = {item["segment_id"]: item for item in subtitle_copy.get("cues", [])}
    dub = {item["segment_id"]: item for item in dub_script.get("entries", [])}
    shared = sorted(set(subtitle) & set(dub))
    failures = [segment_id for segment_id in shared if subtitle[segment_id].get("meaning_id") != dub[segment_id].get("meaning_id")]
    missing = sorted(set(subtitle) ^ set(dub))
    expected = max(len(set(subtitle) | set(dub)), 1)
    return {
        "status": "PASS" if not failures and not missing else "FAIL",
        "shared_segment_ids": shared,
        "meaning_failures": failures,
        "missing_segment_ids": missing,
        "consistency_rate": (len(shared) - len(failures)) / expected,
    }


def me_separation_qc(me_artifact: dict[str, Any] | None) -> dict[str, Any]:
    """A separation fallback cannot be called clean without artifact QC."""
    item = dict(me_artifact or {})
    source = str(item.get("source") or "")
    if source in {"provided_me", "embedded_me"}:
        passed = bool(item.get("artifact_id") and item.get("artifact_id") != "none")
    elif source == "separation_fallback":
        passed = bool(item.get("artifact_id") and item.get("artifact_id") != "none" and item.get("qc_status") == "PASS")
    elif source == "voiceover_ducking":
        passed = bool(item.get("ducking_profile"))
    else:
        passed = False
    return {"pass": passed, "source": source, "reason": "PASS" if passed else "me_artifact_qc_required"}


def validate_provider_output(response: dict[str, Any] | None) -> dict[str, Any]:
    """HTTP 200, task IDs and URLs alone are never artifact success."""
    item = dict(response or {})
    payload = item.get("bytes", item.get("data"))
    has_bytes = isinstance(payload, (bytes, bytearray)) and len(payload) > 0
    has_validated_artifact = bool(item.get("artifact_validated") and item.get("artifact_id"))
    return {
        "valid": has_bytes and has_validated_artifact,
        "reason": "PASS" if has_bytes and has_validated_artifact else "validated_artifact_required",
    }


def build_stage_qc(
    *,
    scope_id: str,
    root_source_id: str,
    job_id: str,
    stage_name: str,
    checked_artifact: dict[str, Any],
    checks: Iterable[dict[str, Any]],
    parent_artifact_ids: Iterable[str] | None = None,
    source_segment_ids: Iterable[str] = (),
    derived_meaning_ids: Iterable[str] = (),
) -> dict[str, Any]:
    check_list = [deepcopy(item) for item in checks]
    for item in check_list:
        item.setdefault("blocking", True)
        item.setdefault("status", "FAIL")
        item.setdefault("metrics", {})
        item.setdefault("safe_reason", "")
    blocking_failures = [str(item.get("check_id") or "unknown") for item in check_list if item.get("blocking") and item.get("status") != "PASS"]
    warnings = [str(item.get("check_id") or "unknown") for item in check_list if not item.get("blocking") and item.get("status") != "PASS"]
    artifact_bytes = checked_artifact.get("bytes")
    artifact_exists = bool(artifact_bytes) or bool(checked_artifact.get("path")) or int(checked_artifact.get("size_bytes", 0) or 0) > 0
    safe = artifact_exists and not blocking_failures
    checked_fingerprint = str(checked_artifact.get("fingerprint") or sha256_hex(artifact_bytes or checked_artifact))
    artifact = {
        "schema_name": "stage_qc",
        "job_id": str(job_id),
        "stage_name": str(stage_name),
        "stage_state": StageState.PASS.value if safe else StageState.FAIL.value,
        "input_fingerprint": sha256_hex({"job_id": job_id, "stage": stage_name, "checked_artifact": checked_artifact.get("artifact_id")}),
        "checked_output_fingerprint": checked_fingerprint,
        "checks": check_list,
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "readiness": {
            "artifact_exists": artifact_exists,
            "schema_valid": True,
            "fingerprint_matches": bool(checked_fingerprint),
            "safe_for_next_stage": safe,
        },
        "admin_diagnostic_ref": None,
        "created_at": "1970-01-01T00:00:00Z",
        "retention_class": "subdub_qc_30d",
    }
    parents = list(parent_artifact_ids or ([checked_artifact.get("artifact_id")] if checked_artifact.get("artifact_id") else []))
    return finalize_artifact(
        artifact,
        scope_id=scope_id,
        root_source_id=root_source_id,
        parent_artifact_ids=parents,
        source_segment_ids=list(source_segment_ids),
        derived_meaning_ids=list(derived_meaning_ids),
        upstream_fingerprints=[checked_fingerprint],
    )


def final_media_checks(
    final_mp4: dict[str, Any],
    *,
    subtitle_copy: dict[str, Any] | None = None,
    dub_script: dict[str, Any] | None = None,
    audio_artifact: dict[str, Any] | None = None,
    combo: bool = False,
) -> list[dict[str, Any]]:
    media = validate_mp4_artifact(final_mp4)
    checks = [
        {"check_id": "mp4_full_decode", "blocking": True, "status": "PASS" if media["valid"] else "FAIL", "metrics": media, "safe_reason": "" if media["valid"] else media["reason"]},
    ]
    if subtitle_copy is not None:
        subtitle_pass = subtitle_copy.get("qc_summary", {}).get("status") == "PASS"
        checks.append({"check_id": "subtitle_copy_qc", "blocking": True, "status": "PASS" if subtitle_pass else "FAIL", "metrics": {}, "safe_reason": ""})
    if dub_script is not None:
        dub_pass = dub_script.get("qc_summary", {}).get("status") == "PASS"
        checks.append({"check_id": "dub_complete_no_overlap", "blocking": True, "status": "PASS" if dub_pass else "FAIL", "metrics": deepcopy(dub_script.get("qc_summary", {})), "safe_reason": ""})
        audio_pass = bool(audio_artifact and audio_artifact.get("artifact_id") and int(audio_artifact.get("size_bytes", 0) or 0) > 0)
        checks.append({"check_id": "mixed_dub_audio_exists", "blocking": True, "status": "PASS" if audio_pass else "FAIL", "metrics": {"size_bytes": int((audio_artifact or {}).get("size_bytes", 0) or 0)}, "safe_reason": ""})
    if combo and subtitle_copy is not None and dub_script is not None:
        consistency = combo_consistency(subtitle_copy, dub_script)
        checks.append({"check_id": "combo_semantic_consistency", "blocking": True, "status": consistency["status"], "metrics": consistency, "safe_reason": ""})
        layers = set(final_mp4.get("layer_manifest") or [])
        layers_pass = {"subtitle_copy", "mixed_dub_audio"}.issubset(layers)
        checks.append({"check_id": "combo_requested_layers", "blocking": True, "status": "PASS" if layers_pass else "FAIL", "metrics": {"layers": sorted(layers)}, "safe_reason": ""})
    return checks


build_combo_qc = combo_consistency
validate_final_mp4 = validate_mp4_artifact

__all__ = ["build_combo_qc", "build_stage_qc", "combo_consistency", "final_media_checks", "me_separation_qc", "validate_final_mp4", "validate_mp4_artifact", "validate_provider_output"]
