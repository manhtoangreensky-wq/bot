"""Versioned V2 artifact contracts and validation.

The contracts are deliberately plain dictionaries so replay artifacts remain
portable and can be inspected without importing the production bot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .fingerprints import artifact_fingerprint, sha256_hex


SCHEMA_VERSIONS = {
    "source_semantic_master": "1.0.0",
    "translation_master": "1.0.0",
    "subtitle_copy": "1.0.0",
    "dub_script": "1.0.0",
    "voice_cast": "1.0.0",
    "stage_qc": "1.0.0",
    "delivery_receipt": "1.0.0",
}
SCHEMA_NAMES = frozenset(SCHEMA_VERSIONS)
SCHEMA_REQUIRED_FIELDS = {
    "source_semantic_master": {"job_id", "source_id", "media", "segments", "alignment_truth", "qc_summary"},
    "translation_master": {"source_master_artifact_id", "target_language", "entries", "qc_summary"},
    "subtitle_copy": {"source_master_artifact_id", "subtitle_profile", "cues", "qc_summary"},
    "dub_script": {"source_master_artifact_id", "translation_master_artifact_id", "entries", "qc_summary"},
    "voice_cast": {"voice_policy_version", "casts", "me_policy"},
    "stage_qc": {"job_id", "stage_name", "stage_state", "checks", "readiness"},
    "delivery_receipt": {"receipt_id", "job_id", "lane", "final_artifact_id", "final_qc_artifact_id", "charge_state"},
}


class StageState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAIL = "FAIL"
    WAITING_REVIEW = "WAITING_REVIEW"
    CANCELLED = "CANCELLED"


class AcceptanceState(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ACCEPTANCE_UNKNOWN = "ACCEPTANCE_UNKNOWN"


class ClaimState(str, Enum):
    UNCLAIMED = "UNCLAIMED"
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"
    ACCEPTANCE_UNKNOWN = "ACCEPTANCE_UNKNOWN"
    FAILED = "FAILED"


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.ok


def _lineage(
    *,
    scope_id: str,
    root_source_id: str,
    parent_artifact_ids: list[str] | tuple[str, ...],
    source_segment_ids: list[str] | tuple[str, ...] = (),
    derived_meaning_ids: list[str] | tuple[str, ...] = (),
    upstream_fingerprints: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    parent_ids = [str(item) for item in parent_artifact_ids if str(item).strip()]
    source_ids = [str(item) for item in source_segment_ids if str(item).strip()]
    meaning_ids = [str(item) for item in derived_meaning_ids if str(item).strip()]
    upstream = [str(item) for item in upstream_fingerprints if str(item).strip()]
    lineage_payload = {
        "scope_id": str(scope_id),
        "root_source_id": str(root_source_id),
        "parent_artifact_ids": parent_ids,
        "source_segment_ids": source_ids,
        "derived_meaning_ids": meaning_ids,
        "upstream_fingerprints": upstream,
    }
    return {
        **lineage_payload,
        "lineage_id": f"lineage-{sha256_hex(lineage_payload)[:16]}",
        "lineage_fingerprint": sha256_hex(lineage_payload),
    }


def finalize_artifact(
    artifact: dict[str, Any],
    *,
    scope_id: str,
    root_source_id: str,
    parent_artifact_ids: list[str] | tuple[str, ...] = (),
    source_segment_ids: list[str] | tuple[str, ...] = (),
    derived_meaning_ids: list[str] | tuple[str, ...] = (),
    upstream_fingerprints: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    current = dict(artifact or {})
    schema_name = str(current.get("schema_name") or "").strip()
    if schema_name not in SCHEMA_NAMES:
        raise ContractError("unknown_schema")
    current["schema_version"] = str(current.get("schema_version") or SCHEMA_VERSIONS[schema_name])
    if current["schema_version"] != SCHEMA_VERSIONS[schema_name]:
        raise ContractError("unsupported_schema_version")
    current["scope_id"] = str(scope_id or "")
    current["root_source_id"] = str(root_source_id or "")
    current["lineage"] = _lineage(
        scope_id=scope_id,
        root_source_id=root_source_id,
        parent_artifact_ids=parent_artifact_ids,
        source_segment_ids=source_segment_ids,
        derived_meaning_ids=derived_meaning_ids,
        upstream_fingerprints=upstream_fingerprints,
    )
    current["output_fingerprint"] = artifact_fingerprint(current)
    current["artifact_id"] = f"{schema_name}:{current['schema_version']}:{current['output_fingerprint'][:16]}"
    return current


def _validate_lineage(current: dict[str, Any], errors: list[str]) -> None:
    lineage = current.get("lineage")
    if not isinstance(lineage, dict):
        errors.append("lineage")
        return
    lineage_keys = (
        "lineage_id",
        "lineage_fingerprint",
        "scope_id",
        "root_source_id",
        "parent_artifact_ids",
        "source_segment_ids",
        "derived_meaning_ids",
        "upstream_fingerprints",
    )
    for key in lineage_keys:
        if key not in lineage:
            errors.append(f"lineage.{key}")
    for key in ("parent_artifact_ids", "source_segment_ids", "derived_meaning_ids", "upstream_fingerprints"):
        if key in lineage and not isinstance(lineage.get(key), list):
            errors.append(f"lineage.{key}_type")
    if str(lineage.get("scope_id") or "") != str(current.get("scope_id") or ""):
        errors.append("lineage.scope_mismatch")
    if str(lineage.get("root_source_id") or "") != str(current.get("root_source_id") or ""):
        errors.append("lineage.root_source_mismatch")
    payload = {
        "scope_id": str(lineage.get("scope_id") or ""),
        "root_source_id": str(lineage.get("root_source_id") or ""),
        "parent_artifact_ids": list(lineage.get("parent_artifact_ids") or []),
        "source_segment_ids": list(lineage.get("source_segment_ids") or []),
        "derived_meaning_ids": list(lineage.get("derived_meaning_ids") or []),
        "upstream_fingerprints": list(lineage.get("upstream_fingerprints") or []),
    }
    expected_fingerprint = sha256_hex(payload)
    if lineage.get("lineage_fingerprint") and lineage.get("lineage_fingerprint") != expected_fingerprint:
        errors.append("lineage_fingerprint_mismatch")
    if lineage.get("lineage_id") and lineage.get("lineage_id") != f"lineage-{expected_fingerprint[:16]}":
        errors.append("lineage_id_mismatch")


def _validate_schema_invariants(current: dict[str, Any], schema_name: str, errors: list[str]) -> None:
    for field in SCHEMA_REQUIRED_FIELDS.get(schema_name, set()):
        if field not in current:
            errors.append(field)
    lineage = current.get("lineage") if isinstance(current.get("lineage"), dict) else {}
    parents = list(lineage.get("parent_artifact_ids") or [])
    if schema_name == "source_semantic_master" and parents:
        errors.append("lineage.source_has_parent")
    if schema_name in {"translation_master", "dub_script", "voice_cast"} and len(parents) != 1:
        errors.append("lineage.parent_count")
    if schema_name == "source_semantic_master":
        if current.get("alignment_truth") not in {"word_aligned", "segment_timed", "alignment_unavailable"}:
            errors.append("alignment_truth")
        previous_start = -1
        for segment in current.get("segments") or []:
            start = int(segment.get("start_ms", -1))
            end = int(segment.get("end_ms", -1))
            if start < 0 or end <= start or start < previous_start:
                errors.append("segment_timeline")
                break
            previous_start = start
    if schema_name == "translation_master" and current.get("qc_summary", {}).get("status") == "PASS":
        if not current.get("entries") or current.get("qc_summary", {}).get("missing_segment_ids"):
            errors.append("translation_coverage")
    if schema_name == "subtitle_copy" and current.get("qc_summary", {}).get("status") == "PASS":
        if not current.get("qc_summary", {}).get("timeline_equal_to_source"):
            errors.append("subtitle_timeline")
    if schema_name == "dub_script" and current.get("qc_summary", {}).get("status") == "PASS":
        summary = current.get("qc_summary", {})
        if summary.get("overlap_count") or summary.get("truncated_count"):
            errors.append("dub_completeness")
    if schema_name == "stage_qc" and current.get("stage_state") not in {item.value for item in StageState}:
        errors.append("stage_state")


def validate_artifact(
    artifact: dict[str, Any] | None,
    *,
    expected_schema: str = "",
    scope_id: str = "",
) -> ValidationResult:
    current = dict(artifact or {})
    errors: list[str] = []
    schema_name = str(current.get("schema_name") or "").strip()
    if schema_name not in SCHEMA_NAMES:
        errors.append("schema_name")
    elif str(current.get("schema_version") or "") != SCHEMA_VERSIONS[schema_name]:
        errors.append("schema_version")
    if expected_schema and schema_name != expected_schema:
        errors.append("expected_schema")
    if not str(current.get("artifact_id") or "").strip():
        errors.append("artifact_id")
    if not str(current.get("output_fingerprint") or "").strip():
        errors.append("output_fingerprint")
    if not str(current.get("scope_id") or "").strip():
        errors.append("scope_id")
    if scope_id and str(current.get("scope_id")) != str(scope_id):
        errors.append("scope_mismatch")
    if not str(current.get("root_source_id") or "").strip():
        errors.append("root_source_id")
    if not str(current.get("input_fingerprint") or "").strip():
        errors.append("input_fingerprint")
    if not str(current.get("retention_class") or "").strip():
        errors.append("retention_class")
    _validate_lineage(current, errors)
    if schema_name in SCHEMA_NAMES:
        _validate_schema_invariants(current, schema_name, errors)
        stored_fingerprint = str(current.get("output_fingerprint") or "")
        if stored_fingerprint and stored_fingerprint != artifact_fingerprint(current):
            errors.append("output_fingerprint_mismatch")
        expected_id = f"{schema_name}:{SCHEMA_VERSIONS[schema_name]}:{stored_fingerprint[:16]}"
        if stored_fingerprint and str(current.get("artifact_id") or "") != expected_id:
            errors.append("artifact_id_mismatch")
    return ValidationResult(not errors, tuple(errors))


def require_valid_artifact(artifact: dict[str, Any], *, expected_schema: str = "", scope_id: str = "") -> dict[str, Any]:
    result = validate_artifact(artifact, expected_schema=expected_schema, scope_id=scope_id)
    if not result.ok:
        raise ContractError("invalid_artifact:" + ",".join(result.errors))
    return artifact
