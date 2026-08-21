"""Single semantic translation master used by translated lanes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .contracts import finalize_artifact
from .fingerprints import sha256_hex, short_id


def _language_code(value: str) -> str:
    return str(value or "auto").strip().lower().replace("_", "-").split("-", 1)[0]


def _translation_map(translations: Iterable[dict[str, Any]] | dict[str, Any]) -> dict[str, dict[str, Any]]:
    if isinstance(translations, dict):
        values = []
        for key, value in translations.items():
            item = dict(value) if isinstance(value, dict) else {"semantic_translation": value}
            item.setdefault("source_index", key)
            values.append(item)
    else:
        values = [dict(item) for item in (translations or [])]
    result: dict[str, dict[str, Any]] = {}
    for item in values:
        if item.get("segment_id"):
            result[f"id:{item['segment_id']}"] = item
        if item.get("source_index") is not None:
            result[f"index:{item['source_index']}"] = item
    return result


def _entry_for_segment(mapping: dict[str, dict[str, Any]], segment: dict[str, Any]) -> dict[str, Any] | None:
    return mapping.get(f"id:{segment['segment_id']}") or mapping.get(f"index:{segment['source_index']}")


def build_translation_master(
    *,
    scope_id: str,
    source_master: dict[str, Any],
    target_language: str,
    translations: Iterable[dict[str, Any]] | dict[str, Any],
    glossary_version: str = "none",
    context: dict[str, Any] | None = None,
    translation_policy_version: str = "semantic_translation_v1",
) -> dict[str, Any]:
    mapping = _translation_map(translations)
    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    name_failures: list[str] = []
    number_failures: list[str] = []
    glossary_failures: list[str] = []
    source_language = str(source_master.get("source_language") or "auto")
    target_language = str(target_language or "auto")
    for segment in source_master.get("segments", []):
        supplied = _entry_for_segment(mapping, segment)
        if supplied is None:
            missing.append(segment["segment_id"])
            continue
        translated = str(supplied.get("semantic_translation", supplied.get("text", "")) or "").strip()
        if not translated:
            missing.append(segment["segment_id"])
            continue
        identity_translation = (
            _language_code(source_language) != _language_code(target_language)
            and translated.casefold() == str(segment["source_text_normalized"]).casefold()
            and not supplied.get("identity_allowed", False)
        )
        if identity_translation:
            name_failures.append(f"identity_translation:{segment['segment_id']}")
        meaning_id = str(
            supplied.get("meaning_id")
            or short_id(
                "meaning",
                {
                    "segment_id": segment["segment_id"],
                    "target_language": target_language,
                    "text": translated,
                    "policy": translation_policy_version,
                },
                16,
            )
        )
        proper_checks = deepcopy(supplied.get("proper_noun_checks") or [])
        number_checks = deepcopy(supplied.get("number_checks") or [])
        glossary_checks = deepcopy(supplied.get("glossary_checks") or [])
        name_failures.extend(
            [f"{segment['segment_id']}:{idx}" for idx, value in enumerate(proper_checks) if isinstance(value, dict) and value.get("status") == "FAIL"]
        )
        number_failures.extend(
            [f"{segment['segment_id']}:{idx}" for idx, value in enumerate(number_checks) if isinstance(value, dict) and value.get("status") == "FAIL"]
        )
        glossary_failures.extend(
            [f"{segment['segment_id']}:{idx}" for idx, value in enumerate(glossary_checks) if isinstance(value, dict) and value.get("status") == "FAIL"]
        )
        entries.append(
            {
                "segment_id": segment["segment_id"],
                "meaning_id": meaning_id,
                "source_text": segment["source_text_normalized"],
                "semantic_translation": translated,
                "proper_noun_checks": proper_checks,
                "number_checks": number_checks,
                "glossary_checks": glossary_checks,
                "dub_candidates": deepcopy(supplied.get("dub_candidates") or []),
                "translation_status": "FAIL" if identity_translation else "PASS",
            }
        )
    source_ids = [item["segment_id"] for item in source_master.get("segments", [])]
    entry_ids = [item["segment_id"] for item in entries]
    allowed_keys = {
        f"id:{segment['segment_id']}" for segment in source_master.get("segments", [])
    } | {
        f"index:{segment['source_index']}" for segment in source_master.get("segments", [])
    }
    extra = sorted(key for key in mapping if key not in allowed_keys)
    context_fingerprint = sha256_hex(context or {"source_language": source_language, "target_language": target_language})
    status = "PASS" if not missing and not name_failures and not number_failures and not glossary_failures else "FAIL"
    artifact = {
        "schema_name": "translation_master",
        "source_master_artifact_id": source_master["artifact_id"],
        "source_id": source_master["root_source_id"],
        "source_language": source_language,
        "target_language": target_language,
        "translation_policy_version": translation_policy_version,
        "glossary_version": str(glossary_version or "none"),
        "context_fingerprint": context_fingerprint,
        "entries": entries,
        "qc_summary": {
            "status": status,
            "missing_segment_ids": missing,
            "extra_segment_ids": extra,
            "name_failures": name_failures,
            "number_failures": number_failures,
            "glossary_failures": glossary_failures,
        },
        "input_fingerprint": sha256_hex({"source": source_master["artifact_id"], "context": context_fingerprint}),
        "retention_class": "subdub_semantic_72h",
    }
    return finalize_artifact(
        artifact,
        scope_id=scope_id,
        root_source_id=source_master["root_source_id"],
        parent_artifact_ids=[source_master["artifact_id"]],
        source_segment_ids=entry_ids,
        derived_meaning_ids=[item["meaning_id"] for item in entries],
        upstream_fingerprints=[source_master["output_fingerprint"], context_fingerprint],
    )


def translation_entry_for_segment(translation_master: dict[str, Any], segment_id: str) -> dict[str, Any] | None:
    return next((item for item in translation_master.get("entries", []) if item.get("segment_id") == segment_id), None)


build_translation_master_artifact = build_translation_master


def validate_translation_master(artifact: dict[str, Any]) -> bool:
    return artifact.get("qc_summary", {}).get("status") == "PASS" and not artifact.get("qc_summary", {}).get("missing_segment_ids")


__all__ = ["build_translation_master", "build_translation_master_artifact", "translation_entry_for_segment", "validate_translation_master"]
