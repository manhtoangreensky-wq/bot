from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from services import human_ai_video_engine as engine
from services import video_engine_contract


RUNTIME_SHA = "b" * 40


def _binary(name: str) -> str:
    return str(os.environ.get(f"HUMAN_AI_VIDEO_{name.upper()}") or shutil.which(name) or "")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_png(path: Path, rgb: tuple[int, int, int], width: int = 48, height: int = 48) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    row = bytes([0, *rgb * width])
    raw = row * height
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _write_source_video(path: Path, duration: float = 3.6) -> None:
    ffmpeg = _binary("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required")
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=160x96:rate=12:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr[-1000:]


def _consent(**overrides) -> dict:
    values = {
        "source_ownership": {"approved": True, "receipt_id": "owner-receipt-29i"},
        "person_consent": {"approved": True, "receipt_id": "person-receipt-29i"},
        "face_identity_consent": {"approved": True, "receipt_id": "face-receipt-29i"},
        "voice_consent": {"approved": True, "receipt_id": "voice-receipt-29i"},
        "brand_rights": {"approved": True, "receipt_id": "brand-receipt-29i"},
    }
    values.update(overrides)
    return values


def _subject_manifest() -> dict:
    return {
        "selection_mode": "person",
        "selection_type": "person",
        "confirmed": True,
        "stable_ids": True,
        "selected_ids": ["person-main"],
        "subject_ids": ["person-main"],
        "person_subject_ids": ["person-main"],
        "object_subject_ids": [],
        "subjects": [
            {
                "subject_id": "person-main",
                "track_id": "person-main",
                "subject_type": "person",
                "description": "consented owner-supplied presenter",
                "provenance": "user_confirmed_source_bound",
            }
        ],
        "interaction_graph": [],
    }


def _snapshot_ss2(source: Path, scene_count: int = 3) -> dict:
    total = 3.6
    span = total / scene_count
    scenes = []
    prompts = []
    for index in range(1, scene_count + 1):
        start = round((index - 1) * span, 3)
        end = round(index * span, 3)
        scenes.append(
            {
                "scene_id": index,
                "scene_index": index,
                "source_segment_start": start,
                "source_segment_end": end,
                "source_segment_selected": True,
                "main_action": f"preserve source action beat {index}",
                "camera_motion": "source_camera",
                "start_state": "source_segment_start" if index == 1 else "inherits_previous_end",
                "end_state": "closed_story_state" if index == scene_count else "natural_completed_action_ready_for_next_scene",
                "duration": span,
            }
        )
        prompts.append(
            {
                "scene_id": index,
                "scene_index": index,
                "prompt": f"Approved SelfShot2 prompt scene {index}; preserve identity and source motion.",
                "negative_prompt": "no face drift, no duplicate person, no broken frames",
                "source_segment_start": start,
                "source_segment_end": end,
            }
        )
    return {
        "product_type": "self_shot_scene_change",
        "product_id": "self_shot_scene_change",
        "flow_owner": "selfshot2",
        "plan_status": "ready",
        "plan_approved": True,
        "local_execution_truth": "owner_footage_edit",
        "source_video": {
            "asset_id": "source-human-29i",
            "path": str(source),
            "sha256": _sha256(source),
            "uploaded_by_user_id": 172203,
        },
        "source_analysis": {
            "duration_seconds": total,
            "width": 160,
            "height": 96,
            "source_hash": _sha256(source),
        },
        "subject_manifest": _subject_manifest(),
        "preserve_constraints": {
            "person_identity": True,
            "action_expression": True,
            "person_object_relation": True,
        },
        "scene_count": scene_count,
        "scene_plan": scenes,
        "video_prompts": prompts,
        "aspect_ratio": "1:1",
        "selected_content": {
            "id": "owner-footage",
            "title": "Owner footage edit",
            "summary": "Use only selected source segments and preserve the presenter.",
        },
        "audio_plan": {"source": {"enabled": True, "volume": 100}},
        "final_assets": {},
    }


def _snapshot_ss3(source: Path) -> dict:
    subject = _subject_manifest()
    subject["source_bound"] = True
    return {
        "product_type": "self_shot_cinematic_transform",
        "product_id": "self_shot_cinematic_transform",
        "flow_owner": "selfshot3",
        "selfshot_mode": "one_take_cinematic",
        "plan_status": "ready",
        "plan_approved": True,
        "local_execution_truth": "owner_footage_edit",
        "source_video": {
            "asset_id": "source-human-29i",
            "path": str(source),
            "sha256": _sha256(source),
            "uploaded_by_user_id": 172203,
        },
        "source_analysis": {
            "duration_seconds": 3.6,
            "width": 160,
            "height": 96,
            "source_hash": _sha256(source),
        },
        "source_segment": {"start_ms": 0, "end_ms": 1200, "duration_ms": 1200},
        "subject_manifest": subject,
        "relationship_locks": [],
        "layer_rules": {
            "identity": "preserve",
            "body": "preserve",
            "motion": "preserve",
            "relationship": "preserve",
            "camera": "preserve",
            "source_audio": "preserve",
            "wardrobe": "preserve",
            "environment": "preserve",
            "lighting": "preserve",
            "effects": "preserve",
        },
        "transformation_stages": [
            {
                "stage_id": "stage-1",
                "start_ms": 0,
                "end_ms": 1200,
                "camera_policy": "preserve_source_camera",
                "audio_policy": "preserve_timeline_sync",
            }
        ],
        "compiled_prompt": {
            "compiler_version": "selfshot3-v1",
            "mode": "one_take_cinematic",
            "identity_lock": ["person-main"],
            "stage_prompts": [
                {
                    "stage_id": "stage-1",
                    "prompt": "Approved one-take source-footage prompt; preserve all source pixels and timing.",
                    "negative_prompt": "no face replacement, no identity drift, no temporal flicker",
                }
            ],
        },
        "scene_count": 1,
        "scene_plan": [{"scene_index": 1, "title": "One take", "duration": 1.2}],
        "video_prompts": [
            {
                "stage_id": "stage-1",
                "prompt": "Approved one-take source-footage prompt; preserve all source pixels and timing.",
                "negative_prompt": "no face replacement, no identity drift, no temporal flicker",
            }
        ],
        "aspect_ratio": "1:1",
        "audio_plan": {"source": {"enabled": True, "volume": 100}},
        "final_assets": {},
    }


def _flags(**overrides: str) -> dict[str, str]:
    values = dict(engine.HUMAN_AI_VIDEO_ENGINE_FLAG_DEFAULTS)
    values.update(overrides)
    return values


def _manifest(**overrides) -> dict:
    values = video_engine_contract.build_worker_manifest(
        worker_sha=RUNTIME_SHA,
        worker_instance_id="fixture-worker-29i",
        supported_products=["human_ai_video"],
        supported_modes=["single_scene", "multi_scene"],
        renderer_name="local-ffmpeg-human-ai-engine",
        renderer_version="29i-test",
        ffmpeg_version="fixture-local",
        provider_enabled=False,
        local_enabled=True,
        queue_ready=True,
        worker_connected=True,
        heartbeat_fresh=True,
        health_ok=True,
        worker_status="healthy",
        capabilities=[engine.CANONICAL_WORKER_CAPABILITY],
        local_capabilities={engine.CANONICAL_WORKER_CAPABILITY: True},
        provider_availability={},
    )
    values.update({"engine_adapters": [engine.ENGINE_ADAPTER], "artifact_ready": True})
    values.update(overrides)
    return values


def _plan(snapshot: dict, **overrides):
    return engine.compile_human_ai_video_plan(
        approved_snapshot=snapshot,
        rights_consent=overrides.pop("rights_consent", _consent()),
        execution_kind=overrides.pop("execution_kind", "owner_footage_edit"),
        transition=overrides.pop("transition", "cut"),
        transition_seconds=overrides.pop("transition_seconds", 0.0),
        final_assets=overrides.pop("final_assets", snapshot.get("final_assets") or {}),
        **overrides,
    )


def _request(plan: engine.HumanAIVideoPlan, **overrides):
    return engine.build_human_ai_video_request(
        user_id=172203,
        confirmation_id="confirm-29i",
        language="vi",
        plan=plan,
        explicit_confirmation_receipt={"confirmation_id": "confirm-29i"},
        runtime_sha=RUNTIME_SHA,
        expected_worker_sha=RUNTIME_SHA,
        admin_no_charge=True,
        **overrides,
    )


def test_29i_default_off_route_and_truthful_capability_contract() -> None:
    assert engine.human_ai_video_engine_flags({}) == {
        name: False for name in engine.HUMAN_AI_VIDEO_ENGINE_FLAG_DEFAULTS
    }
    profile = video_engine_contract.product_route_contract("human_ai_video")
    assert profile["state"] == "PROFILE_ONLY"
    assert profile["connected"] is False
    route = video_engine_contract.product_route_contract(
        "human_ai_video",
        mode="single_scene",
        environ=_flags(HUMAN_AI_VIDEO_ENGINE_ENABLED="1"),
    )
    assert route == engine.shared_human_ai_video_engine_route()
    contract = engine.human_ai_video_engine_contract()
    assert contract["supported_execution_kinds"] == ("owner_footage_edit",)
    assert set(contract["unsupported_execution_kinds"]) >= {
        "avatar_generation",
        "ai_presenter",
        "lip_sync",
        "face_clone",
        "voice_clone",
        "ai_video_generation",
    }
    assert route["provider_enabled"] is False


def test_29i_plan_freezes_locked_selfshot_prompt_subject_source_and_consent(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _write_source_video(source)
    plan = _plan(_snapshot_ss2(source, scene_count=3))
    assert plan.flow_product_type == "self_shot_scene_change"
    assert plan.mode == "multi_scene"
    assert [scene.scene_index for scene in plan.scenes] == [1, 2, 3]
    assert plan.scenes[0].prompt.startswith("Approved SelfShot2 prompt scene 1")
    assert plan.scenes[0].subject_ids == ("person-main",)
    assert plan.source_asset_sha256 == _sha256(source)
    assert plan.rights_consent["person_consent"]["receipt_id"] == "person-receipt-29i"
    assert engine.validate_human_ai_video_plan(plan)["ok"] is True


def test_29i_rejects_missing_consent_and_every_unsupported_generation_claim(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _write_source_video(source)
    snapshot = _snapshot_ss3(source)
    missing = _consent(person_consent={"approved": False, "receipt_id": ""})
    with pytest.raises(ValueError, match="person_consent_receipt_required"):
        _plan(snapshot, rights_consent=missing)
    for kind in (
        "avatar_generation",
        "ai_presenter",
        "lip_sync",
        "face_clone",
        "voice_clone",
        "ai_video_generation",
        "direct_video_to_video",
    ):
        with pytest.raises(ValueError, match="human_ai_execution_kind_unsupported"):
            _plan(snapshot, execution_kind=kind)


def test_29i_rejects_unapproved_visual_transformation_in_local_footage_lane(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _write_source_video(source)
    snapshot = _snapshot_ss3(source)
    snapshot["layer_rules"]["environment"] = "transform"
    with pytest.raises(ValueError, match="human_ai_generation_capability_missing"):
        _plan(snapshot)


def test_29i_default_off_dispatch_has_zero_side_effects(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _write_source_video(source)
    plan = _plan(_snapshot_ss3(source))
    request = _request(plan)
    ledger = engine.HumanAIVideoEngineLedger()
    result = engine.dispatch_human_ai_video(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        environ={},
    )
    assert result["blocker"] == "human_ai_video_engine_disabled"
    assert result["submitted"] is False
    assert ledger.provider_calls == ledger.delivery_count == 0


def test_29i_single_scene_owner_footage_renders_real_mp4_with_lineage_evidence(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    source = tmp_path / "source.mp4"
    _write_source_video(source)
    plan = _plan(_snapshot_ss3(source))
    request = _request(plan)
    ledger = engine.HumanAIVideoEngineLedger()
    result = engine.execute_human_ai_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(HUMAN_AI_VIDEO_ENGINE_ENABLED="1"),
        source_asset_paths={plan.source_asset_id: str(source)},
    )
    assert result["ok"] is True
    assert result["validation"]["full_decode"] is True
    assert result["validation"]["scene_count"] == 1
    assert result["validation"]["scene_order"] == [1]
    assert result["validation"]["identity_continuity"]["ok"] is True
    assert result["validation"]["identity_continuity"]["method"] == "verified_source_footage_lineage"
    assert result["validation"]["identity_continuity"]["biometric_comparison_claimed"] is False
    assert result["validation"]["audio_non_silent"] is True
    assert Path(result["output_path"]).stat().st_size > 1000
    evidence = json.loads(
        (Path(result["evidence_dir"]) / "scene_001_manifest.json").read_text(encoding="utf-8")
    )
    assert evidence["source_asset_sha256"] == _sha256(source)
    assert evidence["prompt"].startswith("Approved one-take source-footage prompt")
    assert evidence["consent_receipt_ids"]["face_identity_consent"] == "face-receipt-29i"
    replay = engine.execute_human_ai_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(HUMAN_AI_VIDEO_ENGINE_ENABLED="1"),
        source_asset_paths={plan.source_asset_id: str(source)},
    )
    assert replay["idempotent_replay"] is True
    assert ledger.render_count == 1
    assert ledger.compose_count == 1


def test_29i_multiscene_owner_footage_preserves_order_prompt_audio_and_scene_coverage(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    source = tmp_path / "source.mp4"
    _write_source_video(source)
    plan = _plan(_snapshot_ss2(source, scene_count=3))
    request = _request(plan)
    ledger = engine.HumanAIVideoEngineLedger()
    result = engine.execute_human_ai_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(HUMAN_AI_VIDEO_ENGINE_ENABLED="1"),
        source_asset_paths={plan.source_asset_id: str(source)},
    )
    assert result["ok"] is True
    assert result["validation"]["scene_order"] == [1, 2, 3]
    assert result["validation"]["scene_coverage_complete"] is True
    assert result["validation"]["full_decode"] is True
    assert result["validation"]["audio_stream_count"] == 1
    assert result["validation"]["audio_non_silent"] is True
    assert result["validation"]["motion_valid"] is True
    assert ledger.render_count == 3
    assert ledger.compose_count == 1
    manifests = [
        json.loads(
            (Path(result["evidence_dir"]) / f"scene_{index:03d}_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        for index in (1, 2, 3)
    ]
    assert [item["scene_index"] for item in manifests] == [1, 2, 3]
    assert [item["source_segment_start"] for item in manifests] == [0.0, 1.2, 2.4]
    assert [item["prompt"] for item in manifests] == [
        f"Approved SelfShot2 prompt scene {index}; preserve identity and source motion."
        for index in (1, 2, 3)
    ]


def test_29i_source_fingerprint_mismatch_fails_before_render_or_delivery(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _write_source_video(source)
    plan = _plan(_snapshot_ss3(source))
    request = _request(plan)
    source.write_bytes(source.read_bytes() + b"changed-after-approval")
    ledger = engine.HumanAIVideoEngineLedger()
    result = engine.execute_human_ai_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(HUMAN_AI_VIDEO_ENGINE_ENABLED="1"),
        source_asset_paths={plan.source_asset_id: str(source)},
    )
    assert result["ok"] is False
    assert result["blocker"] == "human_ai_source_asset_fingerprint_mismatch"
    assert ledger.render_count == 0
    assert ledger.delivery_count == 0


def test_29i_logo_watermark_and_subtitle_positions_are_frozen_and_applied(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    source = tmp_path / "source.mp4"
    logo = tmp_path / "logo.png"
    _write_source_video(source)
    _write_png(logo, (30, 210, 220))
    final_assets = {
        "enable_subtitle": True,
        "logo_enabled": True,
        "logo_asset_id": "human-brand-logo",
        "logo_path": str(logo),
        "logo_sha256": _sha256(logo),
        "logo_position": "top_left",
        "watermark_text": "HUMAN 29I",
        "watermark_position": "bottom_right",
    }
    plan = _plan(_snapshot_ss3(source), final_assets=final_assets)
    assert plan.final_assets["logo_position"] == "top_left"
    assert plan.final_assets["watermark_position"] == "bottom_right"
    request = _request(plan)
    ledger = engine.HumanAIVideoEngineLedger()
    result = engine.execute_human_ai_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(HUMAN_AI_VIDEO_ENGINE_ENABLED="1"),
        source_asset_paths={plan.source_asset_id: str(source)},
        final_asset_paths={"human-brand-logo": str(logo)},
    )
    assert result["ok"] is True
    assert result["validation"]["subtitle_applied"] is True
    assert result["validation"]["logo_applied"] is True
    assert result["validation"]["watermark_applied"] is True


def test_29i_finalization_is_exactly_once_and_admin_is_free(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    source = tmp_path / "source.mp4"
    _write_source_video(source)
    plan = _plan(_snapshot_ss3(source))
    request = _request(plan)
    ledger = engine.HumanAIVideoEngineLedger()
    rendered = engine.execute_human_ai_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(HUMAN_AI_VIDEO_ENGINE_ENABLED="1"),
        source_asset_paths={plan.source_asset_id: str(source)},
    )
    calls: list[str] = []

    def deliver(_payload: dict) -> dict:
        calls.append("delivery")
        return {"accepted": True, "message_id": "fixture-message-29i", "production": False}

    def receipt(_payload: dict) -> dict:
        calls.append("receipt")
        return {"persisted": True, "receipt_id": "fixture-receipt-29i"}

    def charge(_payload: dict) -> dict:
        calls.append("charge")
        return {"recorded": True, "amount_xu": 0, "wallet_mutated": False}

    def report(_payload: dict) -> dict:
        calls.append("report")
        return {"emitted": True, "report_id": "fixture-report-29i"}

    first = engine.finalize_human_ai_video(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=deliver,
        receipt_persister=receipt,
        charger=charge,
        terminal_reporter=report,
    )
    second = engine.finalize_human_ai_video(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=deliver,
        receipt_persister=receipt,
        charger=charge,
        terminal_reporter=report,
    )
    assert first["ok"] is True
    assert second["idempotent_replay"] is True
    assert calls == ["delivery", "receipt", "charge", "report"]
    assert ledger.provider_calls == 0
    assert ledger.paid_provider_calls == 0
    assert ledger.wallet_mutations == 0


def test_29i_finalization_rejects_production_delivery_and_wallet_mutation(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    artifact = tmp_path / "final.mp4"
    _write_source_video(source)
    artifact.write_bytes(b"validated-local-artifact")
    plan = _plan(_snapshot_ss3(source))
    request = _request(plan)
    base_record = {
        "request": request,
        "artifact_path": str(artifact),
        "artifact_sha256": _sha256(artifact),
        "output_bytes": artifact.stat().st_size,
        "evidence_dir": str(tmp_path),
        "terminal_state": "rendered_validated",
        "validation": {"ok": True},
        "delivery": {},
        "receipt": {},
        "charge": {},
        "terminal_report": {},
    }

    production_ledger = engine.HumanAIVideoEngineLedger()
    production_ledger.records_by_job_id["production-job"] = {
        **base_record,
        "job_id": "production-job",
    }
    blocked = engine.finalize_human_ai_video(
        ledger=production_ledger,
        job_id="production-job",
        deliverer=lambda _payload: {"accepted": True, "message_id": "prod", "production": True},
        receipt_persister=lambda _payload: {"persisted": True, "receipt_id": "forbidden"},
        charger=lambda _payload: {"recorded": True, "amount_xu": 0, "wallet_mutated": False},
        terminal_reporter=lambda _payload: {"emitted": True},
    )
    assert blocked["blocker"] == "production_telegram_delivery_forbidden"
    assert production_ledger.receipt_count == 0

    wallet_ledger = engine.HumanAIVideoEngineLedger()
    wallet_ledger.records_by_job_id["wallet-job"] = {
        **base_record,
        "job_id": "wallet-job",
        "delivery": {"accepted": True, "message_id": "fixture"},
        "receipt": {"persisted": True, "receipt_id": "fixture"},
    }
    wallet_blocked = engine.finalize_human_ai_video(
        ledger=wallet_ledger,
        job_id="wallet-job",
        deliverer=lambda _payload: {"accepted": True, "message_id": "duplicate"},
        receipt_persister=lambda _payload: {"persisted": True, "receipt_id": "duplicate"},
        charger=lambda _payload: {"recorded": True, "amount_xu": 0, "wallet_mutated": True},
        terminal_reporter=lambda _payload: {"emitted": True},
    )
    assert wallet_blocked["blocker"] == "charge_not_recorded"
    assert wallet_ledger.terminal_report_count == 0
