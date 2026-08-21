from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.subdub_v2.contracts import validate_artifact
from services.subdub_v2.artifacts import StageArtifactRegistry
from services.subdub_v2.config import V2ResourceLimits
from services.subdub_v2.duration_fit import build_dub_script, split_tts_transport_chunks
from services.subdub_v2.fingerprints import canonical_json
from services.subdub_v2.profiles import get_audio_profile, get_subtitle_profile, wrap_subtitle_text
from services.subdub_v2.qc import build_stage_qc, me_separation_qc, validate_mp4_artifact, validate_provider_output
from services.subdub_v2.replay import replay_fixture
from services.subdub_v2.source_master import build_source_semantic_master
from services.subdub_v2.subtitle_adapter import build_subtitle_copy
from services.subdub_v2.translation_master import build_translation_master
from services.subdub_v2.voice_cast import build_voice_cast


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "subdub_v2" / "basic_fixture.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _masters() -> tuple[dict, dict]:
    data = _fixture()
    source = build_source_semantic_master(
        scope_id=data["scope_id"],
        source_id=data["source_id"],
        source_language=data["source_language"],
        source_selection=data["source_selection"],
        alignment_truth=data["alignment_truth"],
        media=data["media"],
        segments=data["segments"],
    )
    translation = build_translation_master(
        scope_id=data["scope_id"],
        source_master=source,
        target_language=data["target_language"],
        translations=data["translations"],
        glossary_version="fixture-glossary-v1",
    )
    return source, translation


def test_all_seven_schema_artifacts_carry_lineage_and_stage_qc_is_valid():
    source, translation = _masters()
    subtitle = build_subtitle_copy(source, translation)
    dub = build_dub_script(source, translation)
    voice = build_voice_cast(dub, voices={"speaker_01": "fixture_voice"})
    qc = build_stage_qc(
        scope_id=source["scope_id"],
        root_source_id=source["root_source_id"],
        job_id=source["job_id"],
        stage_name="final_media_qc",
        checked_artifact={"artifact_id": "final-mp4-fixture", "bytes": 128},
        checks=[{"check_id": "mp4_full_decode", "blocking": True, "status": "PASS"}],
        parent_artifact_ids=["final-mp4-fixture"],
    )
    artifacts = [source, translation, subtitle, dub, voice, qc]

    assert all(validate_artifact(item).ok for item in artifacts)
    assert dub["lineage"]["parent_artifact_ids"] == [translation["artifact_id"]]
    assert voice["lineage"]["parent_artifact_ids"] == [dub["artifact_id"]]
    assert qc["lineage"]["parent_artifact_ids"] == ["final-mp4-fixture"]


def test_tampered_output_fingerprint_is_rejected():
    source, _ = _masters()
    tampered = dict(source)
    tampered["source_language"] = "xx"

    result = validate_artifact(tampered)

    assert result.ok is False
    assert "output_fingerprint_mismatch" in result.errors

    missing_retention = dict(source)
    missing_retention.pop("retention_class")
    assert "retention_class" in validate_artifact(missing_retention).errors


def test_subtitle_profiles_do_not_force_cjk_through_vietnamese_cpl():
    vi = get_subtitle_profile("vi")
    zh = get_subtitle_profile("zh")
    thai = get_subtitle_profile("th")

    assert (vi.max_cpl, vi.max_lines) == (42, 2)
    assert zh.max_cpl != vi.max_cpl
    assert thai.max_cpl != vi.max_cpl
    assert len(wrap_subtitle_text("这是一个很长的中文测试句子", zh)) <= zh.max_lines


def test_chunk_offsets_are_converted_to_absolute_timeline():
    source = build_source_semantic_master(
        scope_id="scope-offset",
        source_id="source-offset",
        source_language="vi",
        source_selection="asr",
        alignment_truth="segment_timed",
        media={"duration_ms": 9000},
        segments=[
            {"source_index": 1, "local_start_ms": 100, "local_end_ms": 900, "chunk_offset_ms": 3000, "source_text_raw": "Mot"},
        ],
    )

    assert source["segments"][0]["start_ms"] == 3100
    assert source["segments"][0]["end_ms"] == 3900


def test_duration_fit_keeps_owner_speed_and_rejects_overlap():
    source, translation = _masters()
    dub = build_dub_script(source, translation)

    assert all(item["provider_speech_rate"] == 1.0 for item in dub["entries"])
    assert all(item["post_tempo"] == 1.0 for item in dub["entries"])
    assert dub["qc_summary"]["overlap_count"] == 0
    assert all(item["complete_utterance_required"] for item in dub["entries"])


def test_mp4_qc_never_accepts_metadata_without_bytes():
    result = validate_mp4_artifact({"duration_ms": 1000, "full_decode": True})

    assert result["valid"] is False
    assert result["reason"] == "missing_bytes"


def test_resource_planner_caps_3600_seconds_at_twelve_sequential_parts():
    limits = V2ResourceLimits()

    parts = limits.plan_parts(3600 * 1000)

    assert len(parts) == 12
    assert parts[0] == {"part_index": 1, "start_ms": 0, "end_ms": 300000}
    assert parts[-1]["end_ms"] == 3600 * 1000
    assert limits.validate(input_bytes=1, duration_ms=1, workspace_bytes=limits.workspace_limit(1) + 1) == ["workspace_bytes"]


def test_audio_loudness_is_selected_from_a_versioned_delivery_profile():
    profile = get_audio_profile("telegram_social_v1")

    assert profile.name == "telegram_social_v1"
    assert profile.loudness_target_lufs == -16.0
    assert profile.true_peak_dbfs == -1.0


def test_separation_cannot_claim_clean_without_artifact_qc():
    assert me_separation_qc({"source": "separation_fallback", "artifact_id": "none"})["pass"] is False
    assert me_separation_qc({"source": "separation_fallback", "artifact_id": "me-1", "qc_status": "PASS"})["pass"] is True


def test_persisted_registry_recovers_same_claim_without_replacement(tmp_path: Path):
    store = tmp_path / "stage_registry.json"
    first = StageArtifactRegistry(scope_id="scope-persist", store_path=store)
    claim = first.claim_side_effect("fixture", "group-1", "artifact-1", 1)
    first.mark_acceptance_unknown(claim.key, reason="timeout")

    recovered = StageArtifactRegistry(scope_id="scope-persist", store_path=store)
    same = recovered.claim_side_effect("fixture", "group-1", "artifact-1", 1)

    assert same.created is False
    assert same.state == "ACCEPTANCE_UNKNOWN"
    assert recovered.recovery_action(claim.key) == "inspect"


def test_fingerprints_redact_secret_like_and_admin_provider_fields():
    value = canonical_json(
        {
            "telegram_token": "must-not-appear",
            "MY_API_KEY": "must-not-appear-either",
            "admin_provider_metadata": {"task": "private"},
            "safe": "visible",
        }
    )

    assert "must-not-appear" not in value
    assert "private" not in value
    assert "visible" in value


def test_transport_chunker_does_not_split_inside_markup_and_reassembles():
    text = "Start <break time='1s'/> then continue safely. " * 20

    chunks = split_tts_transport_chunks(text, max_codepoints=55, max_bytes=100)

    assert "".join(item["text"] for item in chunks) == text
    assert all(item["text"].count("<") == item["text"].count(">") for item in chunks)


def test_http_200_task_or_url_without_artifact_is_not_success():
    assert validate_provider_output({"status_code": 200, "task_id": "x", "output_url": "https://invalid"}) == {
        "valid": False,
        "reason": "validated_artifact_required",
    }


def test_replay_writes_quantitative_metrics_without_side_effects(tmp_path: Path):
    report = replay_fixture(
        FIXTURE_PATH,
        metrics_path=tmp_path / "replay_metrics.json",
    )

    metrics = json.loads((tmp_path / "replay_metrics.json").read_text(encoding="utf-8"))
    assert report["replay_pass"] is True
    assert metrics["mp4_valid_rate"] == 1.0
    assert metrics["new_failures_introduced"] == 0
    assert report["provider_calls"] == report["wallet_mutations"] == 0
    assert len({lane["final_mp4"]["fingerprint"] for lane in report["lanes"].values()}) == 4


def test_stage_qc_blocks_missing_final_mp4():
    qc = build_stage_qc(
        scope_id="scope-qc",
        root_source_id="source-qc",
        job_id="job-qc",
        stage_name="final_media_qc",
        checked_artifact={"artifact_id": "missing", "bytes": 0},
        checks=[{"check_id": "mp4_exists", "blocking": True, "status": "FAIL"}],
    )

    assert qc["stage_state"] == "FAIL"
    assert qc["readiness"]["safe_for_next_stage"] is False
