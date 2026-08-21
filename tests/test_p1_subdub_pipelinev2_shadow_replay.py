from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.subdub_v2.artifacts import StageArtifactRegistry
from services.subdub_v2.config import V2Flags, V2ResourceLimits
from services.subdub_v2.contracts import AcceptanceState, StageState, validate_artifact
from services.subdub_v2.delivery import ShadowDeliveryLedger
from services.subdub_v2.duration_fit import split_tts_transport_chunks
from services.subdub_v2.replay import replay_fixture
from services.subdub_v2.source_master import build_source_semantic_master
from services.subdub_v2.subtitle_adapter import build_subtitle_copy
from services.subdub_v2.translation_master import build_translation_master


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "subdub_v2" / "basic_fixture.json"


def fixture_data() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def make_source(data: dict) -> dict:
    return build_source_semantic_master(
        scope_id=data["scope_id"],
        source_id=data["source_id"],
        source_language=data["source_language"],
        source_selection=data["source_selection"],
        alignment_truth=data["alignment_truth"],
        media=data["media"],
        segments=data["segments"],
    )


def make_translation(data: dict, source: dict) -> dict:
    return build_translation_master(
        scope_id=data["scope_id"],
        source_master=source,
        target_language=data["target_language"],
        translations=data["translations"],
        glossary_version="fixture-glossary-v1",
    )


def test_v2_flags_are_default_off_and_rollback_is_v1():
    flags = V2Flags.from_mapping({})

    assert flags.enabled is False
    assert flags.public_allowed is False
    assert flags.shadow_replay is False
    assert flags.admin_preview is False
    assert flags.selects_v1 is True
    assert V2Flags.from_mapping({"SUBDUB_PIPELINE_V2_ENABLED": "1", "SUBDUB_PIPELINE_V2_PUBLIC_ALLOWED": "1"}).public_allowed is True


def test_resource_limits_reject_oversized_long_project():
    limits = V2ResourceLimits()

    failures = limits.validate(input_bytes=501 * 1024 * 1024, duration_ms=3600 * 1000, part_count=12)

    assert "input_bytes" in failures
    assert limits.validate(input_bytes=500 * 1024 * 1024, duration_ms=3600 * 1000, part_count=12) == []


def test_source_master_has_stable_ids_absolute_timeline_and_lineage():
    data = fixture_data()
    source = make_source(data)

    assert source["schema_name"] == "source_semantic_master"
    assert source["alignment_truth"] == "segment_timed"
    assert [item["start_ms"] for item in source["segments"]] == [0, 2200, 4800]
    assert all(item["segment_id"].startswith("seg-") for item in source["segments"])
    assert source["root_source_id"] == data["source_id"]
    assert source["lineage"]["parent_artifact_ids"] == []
    assert validate_artifact(source).ok


def test_translation_master_is_one_lineage_and_subtitle_timing_is_source_locked():
    data = fixture_data()
    source = make_source(data)
    translation = make_translation(data, source)
    copy = build_subtitle_copy(source, translation)

    assert translation["schema_name"] == "translation_master"
    assert len(translation["entries"]) == 3
    assert copy["qc_summary"]["timeline_equal_to_source"] is True
    assert [(cue["start_ms"], cue["end_ms"]) for cue in copy["cues"]] == [
        (0, 2200), (2200, 4800), (4800, 7000)
    ]
    assert copy["lineage"]["parent_artifact_ids"] == [translation["artifact_id"]]
    assert validate_artifact(translation).ok
    assert validate_artifact(copy).ok


def test_tts_transport_chunks_are_utf8_safe_and_reassemble_exactly():
    text = "Xin chào — đây là một câu dài. " * 300

    chunks = split_tts_transport_chunks(text, max_codepoints=120, max_bytes=256)

    assert len(chunks) > 1
    assert "".join(item["text"] for item in chunks) == text
    assert [item["transport_sequence"] for item in chunks] == list(range(1, len(chunks) + 1))
    assert all(len(item["text"].encode("utf-8")) <= 256 for item in chunks)
    assert all(not item["text"].endswith(" ") for item in chunks[:-1])


def test_three_level_idempotency_returns_existing_claims():
    registry = StageArtifactRegistry(scope_id="scope-a")

    first_request = registry.claim_request("source-hash", "config-hash")
    second_request = registry.claim_request("source-hash", "config-hash")
    first_stage = registry.claim_stage(first_request.job_id, "source_master", "input-hash", "config-hash")
    second_stage = registry.claim_stage(first_request.job_id, "source_master", "input-hash", "config-hash")
    first_side_effect = registry.claim_side_effect("fixture-tts", "ttsgrp-1", "artifact-hash", 1)
    second_side_effect = registry.claim_side_effect("fixture-tts", "ttsgrp-1", "artifact-hash", 1)

    assert first_request.created is True
    assert second_request.created is False
    assert first_stage.created is True
    assert second_stage.created is False
    assert first_side_effect.created is True
    assert second_side_effect.created is False


def test_acceptance_unknown_blocks_replacement_submit_and_charge():
    registry = StageArtifactRegistry(scope_id="scope-a")
    claim = registry.claim_side_effect("fixture-tts", "ttsgrp-unknown", "artifact-hash", 1)

    registry.mark_acceptance_unknown(claim.key, reason="transport_timeout")
    recovered = registry.claim_side_effect("fixture-tts", "ttsgrp-unknown", "artifact-hash", 1)

    assert recovered.created is False
    assert recovered.state == AcceptanceState.ACCEPTANCE_UNKNOWN.value
    assert registry.get(claim.key)["replacement_submit_allowed"] is False
    assert registry.get(claim.key)["charge_eligible"] is False


def test_scope_isolation_rejects_cross_user_artifact_reads():
    registry = StageArtifactRegistry(scope_id="scope-a")
    claim = registry.claim_request("source-hash", "config-hash")

    with pytest.raises(PermissionError):
        registry.assert_scope(claim.key, "scope-b")


def test_shadow_delivery_requires_receipt_before_charge_and_never_delivers():
    ledger = ShadowDeliveryLedger(scope_id="scope-a")

    with pytest.raises(RuntimeError, match="receipt_required"):
        ledger.charge("receipt-missing")
    receipt = ledger.persist_receipt(
        job_id="job-1",
        lane="translated_combo",
        final_artifact_id="final-mp4-1",
        final_qc_artifact_id="qc-1",
    )
    ledger.charge(receipt["receipt_id"])

    assert ledger.provider_calls == 0
    assert ledger.customer_deliveries == 0
    assert ledger.wallet_mutations == 0
    assert ledger.events == ["validated", "receipt_persisted", "charge_suppressed_shadow"]


def test_replay_runs_four_lanes_with_shared_masters_and_zero_side_effects():
    report = replay_fixture(FIXTURE_PATH, flags=V2Flags.shadow_defaults_for_test())

    assert report["shadow_contract_pass"] is True
    assert report["replay_pass"] is True
    assert report["provider_calls"] == 0
    assert report["wallet_mutations"] == 0
    assert report["customer_deliveries"] == 0
    assert report["metrics"]["source_master_reuse_rate"] == 1.0
    assert report["metrics"]["translation_master_reuse_rate"] == 1.0
    assert report["metrics"]["dub_overlap_count"] == 0
    assert report["metrics"]["dub_truncation_count"] == 0
    assert report["metrics"]["combo_consistency_rate"] == 1.0
    assert set(report["lanes"]) == {"source_subtitle", "translated_subtitle", "translated_dub", "translated_combo"}
    assert all(item["final_mp4"]["valid"] for item in report["lanes"].values())
    assert all(item["compose_count"] == 1 for item in report["lanes"].values())


def test_stage_state_enum_contains_acceptance_unknown():
    assert StageState.PASS.value == "PASS"
    assert AcceptanceState.ACCEPTANCE_UNKNOWN.value == "ACCEPTANCE_UNKNOWN"
