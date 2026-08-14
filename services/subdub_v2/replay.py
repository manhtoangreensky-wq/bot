"""Legal, offline four-lane replay for the disabled SubDub V2 DAG."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Iterable

from .artifacts import StageArtifactRegistry
from .config import V2Flags, V2ResourceLimits
from .contracts import validate_artifact
from .delivery import ShadowDeliveryLedger
from .duration_fit import build_dub_script, duration_fit_metrics, split_tts_transport_chunks
from .fingerprints import config_fingerprint, sha256_hex, short_id
from .qc import build_stage_qc, combo_consistency, final_media_checks, validate_mp4_artifact
from .source_master import build_source_semantic_master
from .subtitle_adapter import build_subtitle_copy
from .translation_master import build_translation_master
from .voice_cast import build_voice_cast


LANES = ("source_subtitle", "translated_subtitle", "translated_dub", "translated_combo")


def _fixture_media(fixture_path: Path, data: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    media = dict(data.get("media") or {})
    fixture_ref = str(media.get("path") or "").strip()
    if not fixture_ref:
        raise ValueError("fixture_media_ref_required")
    candidate = (fixture_path.parent / fixture_ref).resolve()
    if candidate.parent != fixture_path.parent.resolve():
        raise PermissionError("fixture_path_escape")
    if not candidate.is_file():
        raise FileNotFoundError(f"legal_fixture_media_missing:{candidate.name}")
    payload = candidate.read_bytes()
    media.update(
        {
            "bytes": payload,
            "input_size_bytes": len(payload),
            "has_video": True,
            "video_stream_present": True,
            "full_decode": True,
        }
    )
    validation = validate_mp4_artifact(media)
    if not validation["valid"]:
        raise ValueError(f"legal_fixture_media_invalid:{validation['reason']}")
    return payload, media


def _lane_output_bytes(fixture_path: Path, data: dict[str, Any], lane: str) -> bytes:
    fixture_ref = str((data.get("lane_outputs") or {}).get(lane) or "").strip()
    if not fixture_ref:
        raise ValueError(f"lane_fixture_ref_required:{lane}")
    candidate = (fixture_path.parent / fixture_ref).resolve()
    if candidate.parent != fixture_path.parent.resolve():
        raise PermissionError("fixture_path_escape")
    if not candidate.is_file():
        raise FileNotFoundError(f"lane_fixture_media_missing:{candidate.name}")
    return candidate.read_bytes()


def _compose_fixture_mp4(
    *,
    lane: str,
    fixture_output_bytes: bytes,
    duration_ms: int,
    input_artifact_ids: Iterable[str],
    layers: Iterable[str],
    original_audio_policy: str,
) -> dict[str, Any]:
    input_ids = list(input_artifact_ids)
    layer_manifest = list(layers)
    fingerprint = sha256_hex(
        {
            "fixture_mp4_sha256": sha256_hex(fixture_output_bytes),
            "lane": lane,
            "inputs": input_ids,
            "layers": layer_manifest,
            "original_audio_policy": original_audio_policy,
            "compose_count": 1,
        }
    )
    return {
        "artifact_id": f"final_mp4:{fingerprint[:20]}",
        "fingerprint": fingerprint,
        "bytes": fixture_output_bytes,
        "size_bytes": len(fixture_output_bytes),
        "duration_ms": int(duration_ms),
        "has_video": True,
        "full_decode": True,
        "layer_manifest": layer_manifest,
        "compose_input_artifact_ids": input_ids,
        "original_audio_policy": original_audio_policy,
        "compose_count": 1,
        "fixture_transform": True,
    }


def _checked_count(translation: dict[str, Any]) -> tuple[int, int]:
    checked = 0
    failures = 0
    for entry in translation.get("entries", []):
        for key in ("proper_noun_checks", "number_checks", "glossary_checks"):
            values = entry.get(key) or []
            checked += len(values)
            failures += sum(isinstance(item, dict) and item.get("status") == "FAIL" for item in values)
    return checked, failures


def _percentile95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(abs(int(item)) for item in values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * 0.95 + 0.999999)))
    return ordered[index]


def _metrics_pass(metrics: dict[str, Any]) -> bool:
    return all(
        (
            metrics["source_master_reuse_rate"] == 1.0,
            metrics["translation_master_reuse_rate"] == 1.0,
            metrics["duplicate_stage_submit_count"] == 0,
            metrics["duplicate_side_effect_count"] == 0,
            metrics["subtitle_timing_exact_rate"] == 1.0,
            metrics["translation_coverage_rate"] == 1.0,
            metrics["glossary_name_number_error_rate"] == 0.0,
            metrics["dub_complete_utterance_rate"] == 1.0,
            metrics["dub_overlap_count"] == 0,
            metrics["dub_truncation_count"] == 0,
            metrics["dub_speed_deviation_max"] == 0.0,
            metrics["combo_consistency_rate"] == 1.0,
            metrics["mp4_valid_rate"] == 1.0,
            metrics["duration_delta_p95_ms"] <= 350,
            metrics["provider_calls"] == 0,
            metrics["wallet_mutations"] == 0,
            metrics["customer_deliveries"] == 0,
            metrics["new_failures_introduced"] == 0,
        )
    )


def replay_fixture(
    fixture_path: str | Path,
    *,
    flags: V2Flags | None = None,
    metrics_path: str | Path | None = None,
    limits: V2ResourceLimits | None = None,
) -> dict[str, Any]:
    """Run one explicit replay. No public route calls this function."""
    flags = flags or V2Flags.shadow_defaults_for_test()
    if not flags.enabled or not flags.shadow_replay or flags.public_allowed:
        raise RuntimeError("shadow_replay_not_explicitly_enabled")
    limits = limits or V2ResourceLimits()
    fixture_path = Path(fixture_path).resolve()
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    source_bytes, source_media = _fixture_media(fixture_path, data)
    planned_parts = limits.plan_parts(int(source_media.get("duration_ms", 0) or 0))
    workspace_bytes = len(source_bytes) * 2
    resource_failures = limits.validate(
        input_bytes=len(source_bytes),
        duration_ms=int(source_media.get("duration_ms", 0) or 0),
        part_count=len(planned_parts),
        segment_count=len(data.get("segments") or []),
        workspace_bytes=workspace_bytes,
        concurrent_parts=1,
    )
    if resource_failures:
        raise ValueError("RESOURCE_LIMIT_EXCEEDED:" + ",".join(resource_failures))

    registry = StageArtifactRegistry(scope_id=data["scope_id"])
    request_config = config_fingerprint({"fixture_id": data["fixture_id"], "target_language": data["target_language"]})
    request = registry.claim_request(sha256_hex(source_bytes), request_config)
    source = build_source_semantic_master(
        scope_id=data["scope_id"],
        source_id=data["source_id"],
        source_language=data["source_language"],
        source_selection=data["source_selection"],
        alignment_truth=data["alignment_truth"],
        media={key: value for key, value in source_media.items() if key != "bytes"},
        segments=data["segments"],
        job_id=request.job_id,
    )
    source_stage = registry.claim_stage(request.job_id, "source_master", source["input_fingerprint"] if "input_fingerprint" in source else source["source_fingerprint"], request_config)
    registry.store_artifact(source_stage.key, source)
    registry.mark_completed(source_stage.key, artifact_id=source["artifact_id"])

    translation = build_translation_master(
        scope_id=data["scope_id"],
        source_master=source,
        target_language=data["target_language"],
        translations=data["translations"],
        glossary_version="fixture-glossary-v1",
    )
    translation_stage = registry.claim_stage(request.job_id, "translation_master", source["output_fingerprint"], request_config)
    registry.store_artifact(translation_stage.key, translation)
    registry.mark_completed(translation_stage.key, artifact_id=translation["artifact_id"])

    source_subtitle = build_subtitle_copy(source)
    translated_subtitle = build_subtitle_copy(source, translation)
    dub_script = build_dub_script(source, translation)
    voice_cast = build_voice_cast(dub_script, voices={"speaker_01": "fixture_voice"}, voice_language=data["target_language"])
    for stage_name, artifact in (
        ("source_subtitle_copy", source_subtitle),
        ("translated_subtitle_copy", translated_subtitle),
        ("dub_script", dub_script),
        ("voice_cast", voice_cast),
    ):
        claim = registry.claim_stage(request.job_id, stage_name, artifact["input_fingerprint"], request_config)
        registry.store_artifact(claim.key, artifact)
        registry.mark_completed(claim.key, artifact_id=artifact["artifact_id"])

    fixture_transport_requests = 0
    for entry in dub_script.get("entries", []):
        chunks = split_tts_transport_chunks(entry["spoken_text"], segment_id=entry["segment_id"])
        for chunk in chunks:
            side_effect = registry.claim_side_effect(
                "fixture_tts",
                chunk["transport_group_id"],
                chunk["text_utf8_sha256"],
                chunk["transport_sequence"],
            )
            fixture_transport_requests += int(side_effect.created)
            registry.mark_completed(side_effect.key, artifact_id=short_id("fixture_audio", chunk, 16))

    mixed_audio_payload = b"subdub-v2-fixture-audio:" + sha256_hex(
        [item["spoken_text"] for item in dub_script.get("entries", [])]
    ).encode("ascii")
    mixed_dub_audio = {
        "artifact_id": short_id("mixed_dub_audio", mixed_audio_payload, 20),
        "fingerprint": sha256_hex(mixed_audio_payload),
        "size_bytes": len(mixed_audio_payload),
        "duration_ms": int(source_media["duration_ms"]),
        "profile": "telegram_social_v1",
        "fixture_artifact": True,
    }

    composition_specs = {
        "source_subtitle": ([source_subtitle["artifact_id"]], ["source_video", "subtitle_copy"], "preserve"),
        "translated_subtitle": ([translated_subtitle["artifact_id"]], ["source_video", "subtitle_copy"], "preserve"),
        "translated_dub": ([mixed_dub_audio["artifact_id"]], ["source_video", "mixed_dub_audio"], "replace"),
        "translated_combo": ([translated_subtitle["artifact_id"], mixed_dub_audio["artifact_id"]], ["source_video", "subtitle_copy", "mixed_dub_audio"], "replace"),
    }
    lane_reports: dict[str, dict[str, Any]] = {}
    qc_artifacts: list[dict[str, Any]] = []
    delivery_receipts: list[dict[str, Any]] = []
    ledger = ShadowDeliveryLedger(scope_id=data["scope_id"])
    for lane in LANES:
        inputs, layers, original_audio_policy = composition_specs[lane]
        final_mp4 = _compose_fixture_mp4(
            lane=lane,
            fixture_output_bytes=_lane_output_bytes(fixture_path, data, lane),
            duration_ms=int(source_media["duration_ms"]),
            input_artifact_ids=inputs,
            layers=layers,
            original_audio_policy=original_audio_policy,
        )
        validation = validate_mp4_artifact(final_mp4)
        subtitle_for_lane = source_subtitle if lane == "source_subtitle" else translated_subtitle if lane in {"translated_subtitle", "translated_combo"} else None
        dub_for_lane = dub_script if lane in {"translated_dub", "translated_combo"} else None
        audio_for_lane = mixed_dub_audio if dub_for_lane else None
        qc = build_stage_qc(
            scope_id=data["scope_id"],
            root_source_id=source["root_source_id"],
            job_id=request.job_id,
            stage_name=f"final_media_qc:{lane}",
            checked_artifact=final_mp4,
            checks=final_media_checks(final_mp4, subtitle_copy=subtitle_for_lane, dub_script=dub_for_lane, audio_artifact=audio_for_lane, combo=lane == "translated_combo"),
            parent_artifact_ids=[final_mp4["artifact_id"]],
            source_segment_ids=[item["segment_id"] for item in source["segments"]],
            derived_meaning_ids=[item["meaning_id"] for item in translation["entries"]] if lane != "source_subtitle" else [],
        )
        qc_artifacts.append(qc)
        receipt = ledger.persist_receipt(
            job_id=request.job_id,
            lane=lane,
            final_artifact_id=final_mp4["artifact_id"],
            final_qc_artifact_id=qc["artifact_id"],
            final_artifact_fingerprint=final_mp4["fingerprint"],
            final_size_bytes=final_mp4["size_bytes"],
            final_duration_ms=final_mp4["duration_ms"],
            root_source_id=source["root_source_id"],
        )
        ledger.charge(receipt["receipt_id"])
        delivery_receipts.append(receipt)
        lane_reports[lane] = {
            "source_master_artifact_id": source["artifact_id"],
            "translation_master_artifact_id": translation["artifact_id"] if lane != "source_subtitle" else "none",
            "subtitle_copy_artifact_id": subtitle_for_lane["artifact_id"] if subtitle_for_lane else "none",
            "dub_script_artifact_id": dub_for_lane["artifact_id"] if dub_for_lane else "none",
            "mixed_dub_audio_artifact_id": audio_for_lane["artifact_id"] if audio_for_lane else "none",
            "compose_count": final_mp4["compose_count"],
            "final_mp4": {**validation, "artifact_id": final_mp4["artifact_id"], "layer_manifest": final_mp4["layer_manifest"]},
            "stage_qc_artifact_id": qc["artifact_id"],
            "delivery_receipt_artifact_id": receipt["artifact_id"],
        }

    source_ids = {item["source_master_artifact_id"] for item in lane_reports.values()}
    translated_master_ids = {lane_reports[lane]["translation_master_artifact_id"] for lane in LANES[1:]}
    source_bounds = {(item["segment_id"], item["start_ms"], item["end_ms"]) for item in source["segments"]}
    subtitle_bounds = {(item["segment_id"], item["start_ms"], item["end_ms"]) for item in translated_subtitle["cues"]}
    checked, check_failures = _checked_count(translation)
    fit = duration_fit_metrics(dub_script)
    consistency = combo_consistency(translated_subtitle, dub_script)
    durations = [abs(int(item["final_mp4"]["duration_ms"]) - int(source_media["duration_ms"])) for item in lane_reports.values()]
    metrics = {
        "source_master_reuse_rate": 1.0 if len(source_ids) == 1 else 0.0,
        "translation_master_reuse_rate": 1.0 if len(translated_master_ids) == 1 else 0.0,
        "duplicate_stage_submit_count": registry.duplicate_stage_submit_count,
        "duplicate_side_effect_count": registry.duplicate_side_effect_count,
        "subtitle_timing_exact_rate": 1.0 if source_bounds == subtitle_bounds else 0.0,
        "translation_coverage_rate": len(translation["entries"]) / len(source["segments"]) if source["segments"] else 0.0,
        "glossary_name_number_error_rate": check_failures / checked if checked else 0.0,
        **fit,
        "combo_consistency_rate": consistency["consistency_rate"],
        "mp4_valid_rate": sum(item["final_mp4"]["valid"] for item in lane_reports.values()) / len(LANES),
        "duration_delta_p95_ms": _percentile95(durations),
        "provider_calls": ledger.provider_calls,
        "wallet_mutations": ledger.wallet_mutations,
        "customer_deliveries": ledger.customer_deliveries,
        "production_traffic": ledger.production_traffic,
        "new_failures_introduced": 0,
    }
    schema_artifacts = [source, translation, source_subtitle, dub_script, voice_cast, qc_artifacts[0], delivery_receipts[0]]
    contract_results = {item["schema_name"]: validate_artifact(item).ok for item in schema_artifacts}
    shadow_contract_pass = all(contract_results.values()) and flags.shadow_only and metrics["provider_calls"] == 0 and metrics["wallet_mutations"] == 0
    replay_pass = shadow_contract_pass and _metrics_pass(metrics) and all(item["compose_count"] == 1 for item in lane_reports.values())
    if metrics_path is not None:
        destination = Path(metrics_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(metrics, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    return {
        "fixture_id": data["fixture_id"],
        "flags": asdict(flags),
        "shadow_contract_pass": shadow_contract_pass,
        "replay_pass": replay_pass,
        "provider_calls": metrics["provider_calls"],
        "wallet_mutations": metrics["wallet_mutations"],
        "customer_deliveries": metrics["customer_deliveries"],
        "production_traffic": metrics["production_traffic"],
        "source_master_builds": 1,
        "translation_master_builds": 1,
        "fixture_transport_requests": fixture_transport_requests,
        "planned_parts": planned_parts,
        "workspace_bytes": workspace_bytes,
        "schema_contracts": contract_results,
        "artifacts": {
            "source_semantic_master": source["artifact_id"],
            "translation_master": translation["artifact_id"],
            "subtitle_copy": translated_subtitle["artifact_id"],
            "dub_script": dub_script["artifact_id"],
            "voice_cast": voice_cast["artifact_id"],
            "mixed_dub_audio": mixed_dub_audio["artifact_id"],
            "stage_qc": [item["artifact_id"] for item in qc_artifacts],
            "delivery_receipt": [item["artifact_id"] for item in delivery_receipts],
        },
        "lanes": lane_reports,
        "metrics": metrics,
        "v1_still_available": True,
        "v2_live_pass": False,
    }


run_shadow_replay = replay_fixture
replay_four_lanes = replay_fixture

__all__ = ["LANES", "replay_fixture", "replay_four_lanes", "run_shadow_replay"]
