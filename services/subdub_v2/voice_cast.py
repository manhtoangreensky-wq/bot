"""Offline voice-cast contract; it never resolves or calls a provider voice."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .contracts import finalize_artifact
from .fingerprints import sha256_hex, short_id


def build_voice_cast(
    dub_script: dict[str, Any],
    *,
    voices: Mapping[str, str] | None = None,
    voice_language: str | None = None,
    me_policy: str = "provided_me",
) -> dict[str, Any]:
    voices = dict(voices or {})
    speaker_ids = sorted({str(item.get("speaker_id") or "speaker_01") for item in dub_script.get("entries", [])})
    casts = [
        {
            "speaker_id": speaker,
            "voice_alias": str(voices.get(speaker) or f"fixture_voice_{speaker}"),
            "voice_gender": "neutral",
            "voice_language": str(voice_language or "auto"),
            "admin_provider_voice_ref": None,
        }
        for speaker in speaker_ids
    ]
    artifact = {
        "schema_name": "voice_cast",
        "voice_policy_version": "subdub_voice_cast_v1",
        "dub_script_artifact_id": dub_script["artifact_id"],
        "diarization": {"required": False, "status": "not_requested", "reason": "single_speaker" if len(speaker_ids) <= 1 else "owner_selected"},
        "casts": casts,
        "me_policy": {"source": me_policy, "artifact_id": "none", "qc_required": True},
        "input_fingerprint": sha256_hex({"dub_script": dub_script["artifact_id"], "voices": voices, "policy": me_policy}),
        "retention_class": "subdub_semantic_72h",
    }
    return finalize_artifact(
        artifact,
        scope_id=dub_script["scope_id"],
        root_source_id=dub_script["root_source_id"],
        parent_artifact_ids=[dub_script["artifact_id"]],
        source_segment_ids=[item["segment_id"] for item in dub_script.get("entries", [])],
        derived_meaning_ids=[item["meaning_id"] for item in dub_script.get("entries", [])],
        upstream_fingerprints=[dub_script["output_fingerprint"]],
    )


__all__ = ["build_voice_cast"]
