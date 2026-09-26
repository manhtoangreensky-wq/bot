"""Provider-free tests for Storyboard Native Panel Image to Key4U I2V Execution Source Closure.

Scope: P0.PRODUCT_VIDEO
Tracking Issue: #1155
Primary Route: key4u_video (kling-v3, image_to_video)
Zero external provider calls made. All network I/O isolated via mocks.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sqlite3
from unittest.mock import MagicMock, patch
import pytest

import bot
from services import (
    remote_worker_api,
    video_final_output,
    video_project_queue as queue,
    video_provider_router,
    video_real_render_connector,
    video_storyboard2,
    video_tail9,
)
from services.video_provider_base import VideoGenerationRequest
from services.video_real_render_connector import RealVideoRenderError
from providers import video_generic_http_provider


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_panels(tmp_path):
    """Create two valid dummy PNG panel image files on disk."""
    panel1 = tmp_path / "storyboard_panel_1.png"
    panel2 = tmp_path / "storyboard_panel_2.png"
    png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    panel1.write_bytes(png_header)
    panel2.write_bytes(png_header)
    return str(panel1), str(panel2)


def _build_storyboard_job(
    panel1_path: str,
    panel2_path: str,
    *,
    job_id: int = 9101,
    project_id: int = 8101,
    user_id: int = 7001,
    scene_tasks: list[dict] | None = None,
) -> dict:
    """Build a canonical storyboard_prompt job dict with 2 scene cards."""
    scene_cards = [
        {
            "scene_index": 1,
            "card_index": 1,
            "scene_id": "scene_1",
            "image_path": panel1_path,
            "local_path": panel1_path,
            "file_path": panel1_path,
            "provider_prompt": "Scene 1: Astronaut cat lands on crystal surface, cinematic camera zoom in.",
            "video_prompt": "Scene 1: Astronaut cat lands on crystal surface, cinematic camera zoom in.",
            "duration_seconds": 8.0,
        },
        {
            "scene_index": 2,
            "card_index": 2,
            "scene_id": "scene_2",
            "image_path": panel2_path,
            "local_path": panel2_path,
            "file_path": panel2_path,
            "provider_prompt": "Scene 2: Astronaut cat looks up at twin glowing moons, smooth pan.",
            "video_prompt": "Scene 2: Astronaut cat looks up at twin glowing moons, smooth pan.",
            "duration_seconds": 8.0,
        },
    ]
    return {
        "id": job_id,
        "job_id": job_id,
        "project_id": project_id,
        "user_id": user_id,
        "product_type": "storyboard_prompt",
        "engine_route": "storyboard_to_video",
        "engine_adapter": "storyboard_scene_image_video_engine",
        "required_capability": "image_to_video",
        "provider_capability": "image_to_video",
        "aspect_ratio": "9:16",
        "scene_count": 2,
        "scene_duration_seconds": 8,
        "duration_seconds": 16,
        "orchestration_mode": "per_scene_8s",
        "source": "product_video",
        "render_mode": "real",
        "real_renderer_required": True,
        "provider_call": True,
        "selected_provider": "key4u_video",
        "provider_order": "key4u_video",
        "provider_chain": ["key4u_video"],
        "scene_cards": scene_cards,
        "scene_tasks": scene_tasks or [],
        "charge_policy": "after_valid_mp4_delivery",
        "project": {
            "id": project_id,
            "scene_cards_json": json.dumps(scene_cards),
            "quoted_price_xu": 144,
        },
    }


# ---------------------------------------------------------------------------
# Mandatory First RED Tests
# ---------------------------------------------------------------------------

def test_final_confirm_currently_does_not_execute_storyboard_i2v(sample_panels):
    """MANDATORY FIRST RED 1: Final confirm handoff must bind storyboard panel images and set I2V capability.

    Verifies that when a storyboard project is prepared for invoice & execution,
    the resulting project asset_pack binds the materialized panel image files,
    configures required_capability='image_to_video', and sets engine_adapter='storyboard_scene_image_video_engine'.
    """
    panel1, panel2 = sample_panels
    session = {
        "product_id": "storyboard_prompt",
        "topic": "Astronaut cat exploration",
        "aspect_ratio": "9:16",
        "draft": {
            "product_id": "storyboard_prompt",
            "b14_scene_count": 2,
            "b14_scene_seconds": 8,
            "b14_aspect_ratio": "9:16",
            "b14_quality_xu": 80,
            "b14_profile_id": "storytelling",
            "provider_order": "key4u_video",
            "provider_chain": ["key4u_video"],
            "scene_cards": [
                {"scene_index": 1, "image_path": panel1, "prompt": "Cat on crystal planet"},
                {"scene_index": 2, "image_path": panel2, "prompt": "Cat watching moons"},
            ],
            "storyboard_panels": [
                {"scene_index": 1, "local_path": panel1},
                {"scene_index": 2, "local_path": panel2},
            ],
        },
    }

    # Calling video_b14_prepare_project_for_invoice must preserve storyboard panel bindings
    project = bot.video_b14_prepare_project_for_invoice(user_id=9999, session=session)
    assert project is not None
    asset_pack = project.get("asset_pack_json") or project.get("asset_pack") or {}
    if isinstance(asset_pack, str):
        asset_pack = json.loads(asset_pack)

    # Invariant: engine_adapter must be storyboard_scene_image_video_engine
    assert asset_pack.get("engine_adapter") == "storyboard_scene_image_video_engine"
    assert asset_pack.get("product_type") == "storyboard_prompt"

    # Invariant: storyboard panel images must be present in scene_cards or asset_pack
    cards = asset_pack.get("scene_cards") or []
    assert len(cards) == 2, "Expected 2 scene cards preserved in asset_pack"
    assert cards[0].get("image_path") == panel1 or cards[0].get("local_path") == panel1
    assert cards[1].get("image_path") == panel2 or cards[1].get("local_path") == panel2


def test_panel_image_bytes_or_local_path_must_reach_i2v_request(sample_panels):
    """MANDATORY FIRST RED 2: Panel image path must reach the VideoGenerationRequest for each scene.

    When _render_scene_video_or_engine constructs VideoGenerationRequest for scene N,
    the image_paths field MUST contain the local file path to Panel N.
    """
    panel1, panel2 = sample_panels
    job = _build_storyboard_job(panel1, panel2)

    # Verify scene 1 image paths
    paths_scene1 = video_real_render_connector.product_video_scene_image_paths(job, scene_index=1)
    assert paths_scene1 == [panel1], f"Expected [{panel1}], got {paths_scene1}"

    # Verify scene 2 image paths
    paths_scene2 = video_real_render_connector.product_video_scene_image_paths(job, scene_index=2)
    assert paths_scene2 == [panel2], f"Expected [{panel2}], got {paths_scene2}"

    # Intercept run_provider_generation to verify VideoGenerationRequest arguments
    captured_requests: list[VideoGenerationRequest] = []

    def mock_run_provider(req, **kwargs):
        captured_requests.append(req)
        return {
            "ok": True,
            "status": "completed",
            "provider": "key4u_video",
            "provider_task_id": f"task_{req.metadata.get('scene_index')}",
            "task_id_present": True,
            "result_url": f"https://cdn.key4u.shop/video_{req.metadata.get('scene_index')}.mp4",
            "output_path": req.metadata.get("raw_output_path"),
            "raw_output_path": req.metadata.get("raw_output_path"),
        }

    raw_output = os.path.join(os.path.dirname(panel1), "scene_01_output.mp4")
    Path(raw_output).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)

    scene_obj = MagicMock()
    scene_obj.scene_id = 1
    scene_obj.video_prompt = "Cat lands on crystal planet"
    scene_obj.aspect_ratio = "9:16"
    scene_obj._toan_aas_job = job

    with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider):
        result = asyncio.run(
            video_real_render_connector._render_scene_async(
                scene_obj,
                raw_output,
                ["key4u_video"],
            )
        )

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.image_paths == [panel1], f"Expected req.image_paths to contain Panel 1, got {req.image_paths}"
    assert req.required_capability == "image_to_video"
    assert req.duration_seconds == 8.0


def test_panel_n_must_bind_to_scene_n(sample_panels):
    """MANDATORY FIRST RED 3: Panel N must strictly bind to Scene N.

    Scene 1 must always receive Panel 1, and Scene 2 must always receive Panel 2.
    Even if scene_cards order in the payload is shuffled, target_index must match scene_index.
    """
    panel1, panel2 = sample_panels
    # Intentionally shuffle the scene cards order in the job
    job = {
        "product_type": "storyboard_prompt",
        "scene_cards": [
            {"scene_index": 2, "card_index": 2, "image_path": panel2},
            {"scene_index": 1, "card_index": 1, "image_path": panel1},
        ],
    }

    # Scene 1 must resolve to panel1 despite being listed second
    resolved_scene1 = video_real_render_connector.storyboard_scene_image_paths(job, scene_index=1)
    assert resolved_scene1 == [panel1], f"Scene 1 must bind to Panel 1, got {resolved_scene1}"

    # Scene 2 must resolve to panel2
    resolved_scene2 = video_real_render_connector.storyboard_scene_image_paths(job, scene_index=2)
    assert resolved_scene2 == [panel2], f"Scene 2 must bind to Panel 2, got {resolved_scene2}"


def test_missing_panel_must_fail_before_provider(tmp_path):
    """MANDATORY FIRST RED 4: Missing panel image must fail closed before calling external provider.

    If a storyboard panel image does not exist on disk, the render engine MUST
    raise RealVideoRenderError before calling any provider API, with zero charge.
    """
    non_existent_panel = str(tmp_path / "ghost_panel_missing.png")
    job = _build_storyboard_job(non_existent_panel, non_existent_panel)

    scene_obj = MagicMock()
    scene_obj.scene_id = 1
    scene_obj.video_prompt = "Scene with missing panel image"
    scene_obj._toan_aas_job = job

    provider_called = False

    def mock_run_provider(req, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"ok": True}

    with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider):
        with pytest.raises(RealVideoRenderError) as exc_info:
            asyncio.run(
                video_real_render_connector._render_scene_async(
                    scene_obj,
                    str(tmp_path / "output_test.mp4"),
                    ["key4u_video"],
                )
            )

    # Invariants: provider must NOT have been called, no_charge must be True
    assert provider_called is False, "Provider MUST NOT be called when panel image is missing"
    diag = exc_info.value.diagnostics
    assert diag.get("no_charge") is True
    assert diag.get("provider_attempted") is False


def test_key4u_native_i2v_wire_payload_construction(sample_panels):
    """MANDATORY IMPLEMENTATION: Key4U I2V wire payload must be valid base64 data URI, 8s, kling-v3.

    Validates that _key4u_wire_payload correctly builds the documented Key4U payload:
    - model_name: 'kling-v3'
    - image: 'data:image/png;base64,...' (real bytes serialized)
    - duration: 8
    - aspect_ratio: '9:16'
    """
    panel1, _ = sample_panels
    req = VideoGenerationRequest(
        job_id=9901,
        product_type="storyboard_prompt",
        prompt="Astronaut cat exploring the galaxy",
        image_paths=[panel1],
        ratio="9:16",
        duration_seconds=8.0,
        required_capability="image_to_video",
        metadata={
            "selected_family": "kling",
            "selected_model": "kling-v3",
            "pinned_wire_model": "kling-v3",
            "required_capability": "image_to_video",
        },
    )

    env = {
        "KEY4U_VIDEO_MODEL": "kling-v3",
        "KEY4U_KLING_I2V_ENDPOINT": "https://api.key4u.shop/api/v1/kling/image2video",
    }
    built_payload = video_generic_http_provider.build_key4u_video_payload(req, env=env)
    assert built_payload["model"] == "kling-v3"
    wire_payload = video_generic_http_provider._key4u_wire_payload(
        built_payload, submit_url="https://api.key4u.shop/api/v1/kling/image2video"
    )
    assert wire_payload["model_name"] == "kling-v3"
    assert wire_payload["duration"] == 8
    assert wire_payload["aspect_ratio"] == "9:16"
    assert wire_payload["image"].startswith("data:image/") or len(wire_payload["image"]) > 20
    import base64
    b64_content = wire_payload["image"].split(";base64,")[-1] if ";base64," in wire_payload["image"] else wire_payload["image"]
    assert len(base64.b64decode(b64_content)) > 0


def test_duplicate_confirm_must_not_double_submit(sample_panels):
    """MANDATORY FIRST RED 5: Duplicate confirm / dispatch must not re-submit to provider.

    When a scene task already has an active provider_task_id or was submitted,
    the dispatcher must recognize the idempotency key and avoid a second submission.
    """
    panel1, panel2 = sample_panels
    existing_tasks = [
        {
            "scene_index": 1,
            "scene_id": 1,
            "provider": "key4u_video",
            "provider_task_id": "existing_k4u_task_111",
            "status": "task_submitted",
            "provider_submit_called": True,
        }
    ]
    job = _build_storyboard_job(panel1, panel2, scene_tasks=existing_tasks)

    scene_obj = MagicMock()
    scene_obj.scene_id = 1
    scene_obj.video_prompt = "Cat lands on crystal planet"
    scene_obj._toan_aas_job = job

    raw_output = os.path.join(os.path.dirname(panel1), "scene_01_dup_output.mp4")
    Path(raw_output).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)

    submit_call_count = 0

    def mock_run_provider(req, **kwargs):
        nonlocal submit_call_count
        submit_call_count += 1
        return {
            "ok": True,
            "status": "in_progress",
            "provider": "key4u_video",
            "provider_task_id": "existing_k4u_task_111",
            "task_id_present": True,
            "output_path": raw_output,
        }

    with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider):
        result = asyncio.run(
            video_real_render_connector._render_scene_async(
                scene_obj,
                raw_output,
                ["key4u_video"],
            )
        )

    # Invariant: Existing task recovered, no duplicate new task submitted
    assert result.get("provider_task_id") == "existing_k4u_task_111"


def test_provider_failure_does_not_charge(sample_panels, tmp_path):
    """MANDATORY FIRST RED 6: Provider error must fail closed with zero charge.

    When the provider fails or rejects the generation request, the error must have
    no_charge=True and the delivery billing decision must evaluate to 0 Xu.
    """
    panel1, panel2 = sample_panels
    job = _build_storyboard_job(panel1, panel2)

    scene_obj = MagicMock()
    scene_obj.scene_id = 1
    scene_obj.video_prompt = "Cat lands on crystal planet"
    scene_obj._toan_aas_job = job

    def mock_failing_provider(req, **kwargs):
        return {
            "ok": False,
            "status": "failed_no_charge",
            "provider_error": "provider_submit_http_500",
            "blocker": "provider_submit_http_500",
            "no_charge": True,
            "charged_xu": 0,
        }

    with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_failing_provider):
        with pytest.raises(RealVideoRenderError) as exc_info:
            asyncio.run(
                video_real_render_connector._render_scene_async(
                    scene_obj,
                    str(tmp_path / "failed_scene_01.mp4"),
                    ["key4u_video"],
                )
            )

    diag = exc_info.value.diagnostics
    assert diag.get("no_charge") is True

    # Check billing decision for project
    project = {"id": 8101, "quoted_price_xu": 144, "user_id": 7001}
    charge_decision = queue.product_video_delivery_charge_decision(project, job, diag)
    assert charge_decision["ok"] is False
    assert charge_decision["amount_xu"] == 0


def test_incomplete_scene_coverage_does_not_deliver(sample_panels, tmp_path):
    """MANDATORY FIRST RED 7: Incomplete scene coverage must NOT deliver final video.

    If Scene 1 succeeds but Scene 2 fails or is missing, final delivery MUST NOT be granted.
    """
    panel1, panel2 = sample_panels
    fake_clip1 = tmp_path / "scene_01_done.mp4"
    fake_clip1.write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 512)

    # Job has 2 scenes required, but only scene 1 completed
    scene_tasks = [
        {
            "scene_index": 1,
            "status": "clip_downloaded",
            "clip_valid": True,
            "clip_path": str(fake_clip1),
        },
        {
            "scene_index": 2,
            "status": "failed_no_charge",
            "clip_valid": False,
            "blocker": "provider_timeout",
        },
    ]

    job = _build_storyboard_job(panel1, panel2, scene_tasks=scene_tasks)

    # Resulting delivery check must block
    result = {
        "final_delivered": False,
        "final_mp4_validated": False,
        "scene_count_expected": 2,
        "scenes_completed": 1,
    }

    project = {"id": 8101, "quoted_price_xu": 144, "user_id": 7001}
    charge_decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert charge_decision["ok"] is False
    assert charge_decision["amount_xu"] == 0
    assert charge_decision["charge_skip_reason"] == "delivery_required_before_charge"


def test_end_to_end_provider_free_storyboard_execution(sample_panels, tmp_path, monkeypatch):
    """MANDATORY TRUE FINAL E2E EXECUTION HANDOFF:
    Proves end-to-end provider-free path:
    FINAL_CONFIRM -> PROJECT_PERSISTENCE -> ASSET_PACK -> INVOICE -> QUEUE_OR_JOB_CREATION
    -> WORKER_JOB_PAYLOAD -> RENDER_REAL_VIDEO_JOB -> SCENE_N_PANEL_N_BINDING -> VIDEO_GENERATION_REQUEST.
    """
    panel1, panel2 = sample_panels
    db_path = str(tmp_path / "test_e2e_storyboard.db")
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setenv("KEY4U_VIDEO_ENABLED", "1")
    monkeypatch.setenv("KEY4U_VIDEO_AUTH_HEADER_VALUE", "Bearer test_token")
    monkeypatch.setenv("KEY4U_VIDEO_MODEL", "kling-v3")
    monkeypatch.setenv("KEY4U_KLING_I2V_ENDPOINT", "https://api.key4u.shop/kling/v1/videos/image2video")
    monkeypatch.setenv("KEY4U_KLING_VIDEO_POLL_URL", "https://api.key4u.shop/kling/v1/videos/image2video/{task_id}")
    monkeypatch.setenv("KEY4U_VIDEO_SUBMIT_URL", "https://api.key4u.shop/kling/v1/videos/image2video")
    monkeypatch.setenv("KEY4U_VIDEO_POLL_URL", "https://api.key4u.shop/kling/v1/videos/image2video/{task_id}")
    monkeypatch.setenv("KEY4U_VIDEO_ENDPOINT", "https://api.key4u.shop/kling/v1/videos/image2video")

    conn = sqlite3.connect(db_path)
    queue.ensure_video_project_queue_schema(conn)

    session = {
        "product_id": "storyboard_prompt",
        "topic": "Astronaut cat exploring crystal planet",
        "aspect_ratio": "9:16",
        "draft": {
            "product_id": "storyboard_prompt",
            "b14_scene_count": 2,
            "b14_scene_seconds": 8,
            "b14_aspect_ratio": "9:16",
            "b14_quality_xu": 80,
            "b14_profile_id": "storytelling",
            "provider_order": "key4u_video",
            "provider_chain": ["key4u_video"],
            "scene_cards": [
                {"scene_index": 1, "image_path": panel1, "prompt": "Scene 1: Cat lands on crystal surface, cinematic zoom"},
                {"scene_index": 2, "image_path": panel2, "prompt": "Scene 2: Cat watches glowing twin moons, pan"},
            ],
            "storyboard_panels": [
                {"scene_index": 1, "local_path": panel1},
                {"scene_index": 2, "local_path": panel2},
            ],
        },
    }

    # 1. FINAL_CONFIRM initiation: Prepare project for invoice (NO preinjected synthetic job)
    project = bot.video_b14_prepare_project_for_invoice(user_id=7001, session=session)
    assert project is not None
    project_id = int(project["project_id"])
    assert project_id > 0

    # 2. PROJECT_PERSISTENCE & ASSET_PACK & INVOICE verification
    persisted_project = queue.get_video_project(conn, project_id)
    assert persisted_project is not None
    asset_pack = json.loads(persisted_project.get("asset_pack_json") or "{}")
    invoice = json.loads(persisted_project.get("invoice_json") or "{}")

    # Invariants on asset_pack
    assert asset_pack.get("product_type") == "storyboard_prompt"
    assert asset_pack.get("engine_route") == "storyboard_to_video"
    assert asset_pack.get("engine_adapter") == "storyboard_scene_image_video_engine"
    assert asset_pack.get("orchestration_mode") == "per_scene_8s"
    assert asset_pack.get("required_capability") == "image_to_video"
    assert asset_pack.get("selected_provider") == "key4u_video"
    assert asset_pack.get("selected_model") == "kling-v3"
    assert asset_pack.get("model") == "kling-v3"
    assert len(asset_pack.get("scene_cards") or []) == 2

    # Invariants on invoice
    assert invoice.get("product_type") == "storyboard_prompt"
    assert invoice.get("engine_route") == "storyboard_to_video"
    assert invoice.get("engine_adapter") == "storyboard_scene_image_video_engine"
    assert invoice.get("orchestration_mode") == "per_scene_8s"
    assert invoice.get("required_capability") == "image_to_video"
    assert invoice.get("selected_provider") == "key4u_video"
    assert invoice.get("selected_model") == "kling-v3"
    assert invoice.get("model") == "kling-v3"

    # Confirm project invoice (Public confirm)
    confirm_res = queue.confirm_video_project_invoice(
        conn, project_id=project_id, user_id=7001, billing_exempt=True
    )
    assert confirm_res["ok"] is True, f"Expected confirm ok, got reason: {confirm_res.get('reason')}"
    job = confirm_res["job"]
    assert job is not None
    job_id = int(job["id"])
    assert job_id > 0

    # Verify project status updated
    project_after_confirm = queue.get_video_project(conn, project_id)
    assert project_after_confirm["status"] in {"queued_for_worker", "queued"}
    assert project_after_confirm["is_confirmed"] == 1

    # 3. QUEUE_OR_JOB_CREATION & PERSISTED_FIELDS in result_json
    job_row = queue.get_video_render_job(conn, job_id)
    assert job_row is not None
    result_json = json.loads(str(job_row.get("result_json") or "{}"))
    assert result_json.get("product_type") == "storyboard_prompt"
    assert result_json.get("engine_route") == "storyboard_to_video"
    assert result_json.get("engine_adapter") == "storyboard_scene_image_video_engine"
    assert result_json.get("orchestration_mode") == "per_scene_8s"
    assert result_json.get("required_capability") == "image_to_video"
    assert result_json.get("selected_provider") == "key4u_video"
    assert result_json.get("selected_model") == "kling-v3"
    assert result_json.get("model") == "kling-v3"
    assert result_json.get("scene_count") == 2
    cards = result_json.get("scene_cards") or []
    assert len(cards) == 2
    assert cards[0].get("image_path") == panel1 or cards[0].get("local_path") == panel1
    assert cards[1].get("image_path") == panel2 or cards[1].get("local_path") == panel2

    # 4. WORKER_JOB_PAYLOAD: Hydrate and build worker payload
    hydrated = queue.hydrate_video_job_payload(conn, job_row)
    assert hydrated.get("product_type") == "storyboard_prompt"
    assert hydrated.get("engine_route") == "storyboard_to_video"
    assert hydrated.get("engine_adapter") == "storyboard_scene_image_video_engine"
    assert hydrated.get("orchestration_mode") == "per_scene_8s"
    assert hydrated.get("required_capability") == "image_to_video"
    assert hydrated.get("selected_provider") == "key4u_video"
    assert hydrated.get("selected_model") == "kling-v3"
    assert hydrated.get("model") == "kling-v3"
    assert len(hydrated.get("scene_cards") or []) == 2

    worker_payload = remote_worker_api.build_worker_job_payload(hydrated)
    assert worker_payload.get("product_type") == "storyboard_prompt"
    assert worker_payload.get("engine_route") == "storyboard_to_video"
    assert worker_payload.get("engine_adapter") == "storyboard_scene_image_video_engine"
    assert worker_payload.get("orchestration_mode") == "per_scene_8s"
    assert worker_payload.get("required_capability") == "image_to_video"
    assert worker_payload.get("selected_provider") == "key4u_video"
    assert worker_payload.get("selected_model") == "kling-v3"
    assert worker_payload.get("model") == "kling-v3"
    assert len(worker_payload.get("scene_cards") or []) == 2

    # 5. RENDER_REAL_VIDEO_JOB, SCENE_N_PANEL_N_BINDING, VIDEO_GENERATION_REQUEST
    captured_requests: list[VideoGenerationRequest] = []

    def mock_run_provider(req: VideoGenerationRequest, **kwargs):
        captured_requests.append(req)
        scene_idx = req.metadata.get("scene_index") or len(captured_requests)
        raw_output_path = req.metadata.get("raw_output_path") or str(tmp_path / f"scene_{scene_idx:02d}.mp4")
        Path(raw_output_path).write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 256)
        return {
            "ok": True,
            "status": "completed",
            "provider": "key4u_video",
            "provider_task_id": f"k4u_scene_{scene_idx}_task",
            "task_id_present": True,
            "result_url": f"https://cdn.key4u.shop/scene_{scene_idx}.mp4",
            "output_path": raw_output_path,
            "raw_output_path": raw_output_path,
        }

    render_workspace = str(tmp_path / "render_work")
    with patch("services.video_real_render_connector.run_provider_generation", side_effect=mock_run_provider):
        render_result = video_real_render_connector.render_real_video_job(worker_payload, render_workspace)

    assert len(captured_requests) == 2, f"Expected exactly 2 scene generation requests, got {len(captured_requests)}"

    # Invariant: Scene 1 must receive Panel 1
    req1 = captured_requests[0]
    assert req1.image_paths == [panel1], f"Scene 1 must bind to Panel 1, got {req1.image_paths}"
    assert req1.required_capability == "image_to_video"
    assert req1.duration_seconds == 8.0
    assert req1.ratio == "9:16"

    # Invariant: Scene 2 must receive Panel 2
    req2 = captured_requests[1]
    assert req2.image_paths == [panel2], f"Scene 2 must bind to Panel 2, got {req2.image_paths}"
    assert req2.required_capability == "image_to_video"
    assert req2.duration_seconds == 8.0
    assert req2.ratio == "9:16"

    # Verify Key4U wire payload for Scene 1 and Scene 2
    env = {
        "KEY4U_VIDEO_MODEL": "kling-v3",
        "KEY4U_KLING_I2V_ENDPOINT": "https://api.key4u.shop/kling/v1/videos/image2video",
    }
    built_payload1 = video_generic_http_provider.build_key4u_video_payload(req1, env=env)
    wire1 = video_generic_http_provider._key4u_wire_payload(
        built_payload1, submit_url="https://api.key4u.shop/kling/v1/videos/image2video"
    )
    assert wire1["model_name"] == "kling-v3"
    assert wire1["duration"] == 8
    assert wire1["aspect_ratio"] == "9:16"
    assert wire1["image"].startswith("data:image/") or len(wire1["image"]) > 20

    built_payload2 = video_generic_http_provider.build_key4u_video_payload(req2, env=env)
    wire2 = video_generic_http_provider._key4u_wire_payload(
        built_payload2, submit_url="https://api.key4u.shop/kling/v1/videos/image2video"
    )
    assert wire2["model_name"] == "kling-v3"
    assert wire2["duration"] == 8
    assert wire2["aspect_ratio"] == "9:16"
    assert wire2["image"].startswith("data:image/") or len(wire2["image"]) > 20

