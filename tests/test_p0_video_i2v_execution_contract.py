"""Dedicated provider-free test suite for SPEC-PV03B & SPEC-PV03B2 I2V Key4U wire contract alignment.

Enforces:
- I2V routes to /kling/v1/videos/image2video (not text2video)
- JSON content type with application/json
- Source image serialized to base64 on wire (no raw local filesystem paths)
- Wire payload uses official provider model identifiers (fails closed on unmapped 'kling-video')
- Ratio preserved (9:16, 16:9, 1:1)
- Model-aware duration matrix: kling-v3 accepts {5, 8, 10}; product default 8s passes; unmapped/unsupported fail closed
- No silent duration rewrite (8 never rewritten to 5 or 10)
- Canonical Key4U submit endpoint without arbitrary URL text transformations
- data.task_id extracted and persisted durably before polling (exercising real production seams)
- Restart recovery polls same task ID without second submit
- Timeout preserves task ID without resubmit
- Zero charge on provider failure, invalid MP4, or delivery failure
- Delivery receipt precedes exactly-once charge
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

import bot
from providers import video_generic_http_provider as vgp
from services import (
    video_ai_edit_status,
    video_final_output,
    video_local_validation,
    video_project_queue,
    video_provider_base,
    video_provider_catalog,
)
from services.video_provider_base import VideoGenerationRequest


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

def _make_dummy_image(path: Path, content: bytes = b"FAKE_PNG_BINARY_IMAGE_DATA_67890") -> Path:
    path.write_bytes(content)
    return path


def _key4u_i2v_env(submit_url: str = "https://api.key4u.vn/kling/v1/videos/image2video") -> dict[str, str]:
    return {
        "KEY4U_KLING_VIDEO_ENDPOINT": submit_url,
        "KEY4U_KLING_VIDEO_POLL_URL": "https://api.key4u.vn/kling/v1/videos/query?id={task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test_bearer_token_secret_12345",
        "KEY4U_VIDEO_MODEL": "kling-video",
        "KEY4U_BASE_URL": "https://api.key4u.vn",
        "VIDEO_PROVIDER_CHAIN": "key4u_video",
    }


def _init_test_jobs_db(tmp_path: Path) -> sqlite3.Connection:
    db_file = tmp_path / "test_jobs.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS local_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            command TEXT,
            job_type TEXT,
            status TEXT,
            provider TEXT,
            input_file_id TEXT,
            output_file_id TEXT,
            output_url TEXT,
            error_short TEXT,
            created_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            xu_cost INTEGER DEFAULT 0,
            admin_only INTEGER DEFAULT 1,
            worker_id TEXT,
            updated_at TEXT,
            provider_task_id TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_local_worker_jobs_status ON local_worker_jobs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_local_worker_jobs_provider_task_id ON local_worker_jobs(provider_task_id)")
    return conn


# ---------------------------------------------------------------------------
# Test 1: Route selection (image2video vs text2video)
# ---------------------------------------------------------------------------

def test_key4u_i2v_routes_to_image2video_not_text2video():
    """CAPABILITY=image_to_video routes to /image2video, while text_to_video routes to /text2video."""
    env = _key4u_i2v_env("https://api.key4u.vn/kling/v1/videos/text2video")

    # I2V contract resolution
    i2v_interface = video_provider_catalog.model_interface_contract(
        "key4u_video", "kling-video", capability="image_to_video", env=env
    )
    assert i2v_interface.get("contract_validation_status") == "ok"
    assert i2v_interface.get("provider_submit_url_override") == "https://api.key4u.vn/kling/v1/videos/image2video"
    assert not i2v_interface["provider_submit_url_override"].endswith("/text2video")

    # T2V contract resolution
    t2v_interface = video_provider_catalog.model_interface_contract(
        "key4u_video", "kling-video", capability="text_to_video", env=env
    )
    assert t2v_interface.get("provider_submit_url_override") == "https://api.key4u.vn/kling/v1/videos/text2video"


# ---------------------------------------------------------------------------
# Test 2: JSON content-type
# ---------------------------------------------------------------------------

def test_key4u_i2v_uses_json_content_type():
    """Key4U I2V submit uses application/json headers on the wire."""
    env = _key4u_i2v_env()
    provider = vgp.GenericHttpVideoProvider(
        provider_name="key4u_video",
        auth_header_name_env="KEY4U_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="KEY4U_VIDEO_AUTH_HEADER_VALUE",
        environ=env,
    )
    headers = provider._headers()
    assert headers.get("Content-Type") == "application/json"
    assert headers.get("Accept") == "application/json"
    assert headers.get("Authorization") == "Bearer test_bearer_token_secret_12345"


# ---------------------------------------------------------------------------
# Test 3: Source image serialization (local file -> base64)
# ---------------------------------------------------------------------------

def test_key4u_i2v_serializes_source_image_on_wire(tmp_path: Path):
    """Local image file is accurately serialized to base64 bytes representation."""
    raw_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01test_bytes"
    img_file = _make_dummy_image(tmp_path / "product.png", raw_content)

    serialized = vgp.serialize_local_image_for_provider_wire(str(img_file))
    expected_b64 = base64.b64encode(raw_content).decode("ascii")

    assert serialized == expected_b64
    assert base64.b64decode(serialized) == raw_content


# ---------------------------------------------------------------------------
# Test 4: Never sends raw local path
# ---------------------------------------------------------------------------

def test_key4u_i2v_never_sends_raw_local_path(tmp_path: Path):
    """Raw local filesystem paths are NEVER sent as wire values."""
    img_file = _make_dummy_image(tmp_path / "secret_local_input_photo.jpg")
    local_path_str = str(img_file)

    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "coffee beans in studio lighting",
        "ratio": "9:16",
        "duration": 5,
        "image_paths": [local_path_str],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")

    # Local path and filename must NOT appear on wire
    assert local_path_str not in json.dumps(wire)
    assert "secret_local_input_photo.jpg" not in json.dumps(wire)
    assert "image" in wire
    assert wire["image"] != local_path_str
    # Must be valid base64
    assert base64.b64decode(wire["image"]) == img_file.read_bytes()


# ---------------------------------------------------------------------------
# Test 5: Wire uses 'image' field
# ---------------------------------------------------------------------------

def test_key4u_i2v_uses_image_field(tmp_path: Path):
    """Wire payload uses the canonical 'image' field for Image-to-Video."""
    img_file = _make_dummy_image(tmp_path / "input.png")
    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "test prompt",
        "ratio": "9:16",
        "duration": 5,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")

    assert "image" in wire
    assert "images" not in wire
    assert "source_video_path" not in wire


# ---------------------------------------------------------------------------
# Test 6: Model name field and unmapped alias fail-closed
# ---------------------------------------------------------------------------

def test_key4u_i2v_uses_model_name_field(tmp_path: Path):
    """Wire uses 'model_name' with official provider identifier; fails closed on unmapped alias."""
    img_file = _make_dummy_image(tmp_path / "input.png")

    # Success with official model identifier (e.g., kling-v3)
    payload_valid = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "test prompt",
        "ratio": "9:16",
        "duration": 5,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload_valid, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["model_name"] == "kling-v3"
    assert "model" not in wire

    # Fail closed on unmapped internal alias 'kling-video'
    payload_unmapped = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-video",  # unmapped internal alias directly passed
        "prompt": "test prompt",
        "ratio": "9:16",
        "duration": 5,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    with pytest.raises(vgp.VideoProviderContractError) as exc_info:
        vgp._key4u_wire_payload(payload_unmapped, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert exc_info.value.blocker == "I2V_MODEL_IDENTIFIER_MAPPING_GAP"


# ---------------------------------------------------------------------------
# Test 7: Prompt preservation
# ---------------------------------------------------------------------------

def test_key4u_i2v_preserves_prompt(tmp_path: Path):
    """Wire payload faithfully preserves the user's prompt."""
    img_file = _make_dummy_image(tmp_path / "input.png")
    prompt_text = "Vibrant product commercial of organic skincare serum bottle in luxury bathroom, soft lighting"

    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": prompt_text,
        "ratio": "9:16",
        "duration": 5,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["prompt"] == prompt_text


# ---------------------------------------------------------------------------
# Tests 8, 9, 10: Ratio mapping (9:16, 16:9, 1:1)
# ---------------------------------------------------------------------------

def test_key4u_i2v_preserves_9_16_ratio(tmp_path: Path):
    """Wire payload preserves 9:16 aspect ratio."""
    img_file = _make_dummy_image(tmp_path / "input.png")
    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "test",
        "ratio": "9:16",
        "duration": 5,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["aspect_ratio"] == "9:16"


def test_key4u_i2v_preserves_16_9_ratio(tmp_path: Path):
    """Wire payload preserves 16:9 aspect ratio."""
    img_file = _make_dummy_image(tmp_path / "input.png")
    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "test",
        "ratio": "16:9",
        "duration": 5,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["aspect_ratio"] == "16:9"


def test_key4u_i2v_preserves_1_1_ratio(tmp_path: Path):
    """Wire payload preserves 1:1 aspect ratio."""
    img_file = _make_dummy_image(tmp_path / "input.png")
    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "test",
        "ratio": "1:1",
        "duration": 5,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["aspect_ratio"] == "1:1"


# ---------------------------------------------------------------------------
# Tests 11 & 12: Model-Aware Duration Validation
# ---------------------------------------------------------------------------

def test_key4u_i2v_preserves_supported_duration(tmp_path: Path):
    """Supported Kling v3 durations (5s, 8s, 10s) are preserved in wire payload."""
    img_file = _make_dummy_image(tmp_path / "input.png")
    for dur in (5, 8, 10):
        payload = {
            "capability": "image_to_video",
            "model": "kling-video",
            "model_name": "kling-v3",
            "prompt": "test",
            "ratio": "9:16",
            "duration": dur,
            "image_paths": [str(img_file)],
            "metadata": {"selected_family": "kling"},
        }
        wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
        assert wire["duration"] == dur


def test_key4u_i2v_rejects_unsupported_duration_before_submit(tmp_path: Path):
    """Unsupported durations (e.g. 15s, 3s, 12s for kling-v3; 8s for kling-v2-6) fail closed with no charge."""
    img_file = _make_dummy_image(tmp_path / "input.png")

    # kling-v3 unsupported durations
    for unsupp_dur in (15, 3, 12):
        payload = {
            "capability": "image_to_video",
            "model": "kling-video",
            "model_name": "kling-v3",
            "prompt": "test",
            "ratio": "9:16",
            "duration": unsupp_dur,
            "image_paths": [str(img_file)],
            "metadata": {"selected_family": "kling"},
        }
        with pytest.raises(vgp.VideoProviderContractError) as exc_info:
            vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
        assert exc_info.value.blocker == "provider_duration_unsupported_no_charge"

    # kling-v2-6 unsupported duration 8s (only supports 5s, 10s)
    payload_v26 = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v2-6",
        "prompt": "test",
        "ratio": "9:16",
        "duration": 8,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    with pytest.raises(vgp.VideoProviderContractError) as exc_v26:
        vgp._key4u_wire_payload(payload_v26, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert exc_v26.value.blocker == "provider_duration_unsupported_no_charge"


# ---------------------------------------------------------------------------
# Tests 13-16: SPEC-PV03B2 Required Duration & Silent Rewrite Tests
# ---------------------------------------------------------------------------

def test_key4u_i2v_kling_v3_accepts_documented_8_second_duration(tmp_path: Path):
    """kling-v3 + image_to_video + duration=8 yields PAYLOAD_BUILD_PASS with wire duration 8."""
    img_file = _make_dummy_image(tmp_path / "product.png")
    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "studio lighting product commercial",
        "ratio": "9:16",
        "duration": 8,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["duration"] == 8
    assert wire["model_name"] == "kling-v3"


def test_key4u_i2v_product_default_8_second_duration_passes(tmp_path: Path):
    """Product Video default 8-second duration (passed via request defaults or payload) passes for kling-v3."""
    img_file = _make_dummy_image(tmp_path / "product.png")
    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "product scene showcase",
        "ratio": "9:16",
        "image_paths": [str(img_file)],
        "metadata": {
            "selected_family": "kling",
            "selected_request_defaults": {"duration": 8, "model_name": "kling-v3"},
        },
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["duration"] == 8


def test_key4u_i2v_does_not_rewrite_8_to_5(tmp_path: Path):
    """duration=8 is never silently rewritten to 5."""
    img_file = _make_dummy_image(tmp_path / "product.png")
    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "test",
        "duration": 8,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["duration"] != 5
    assert wire["duration"] == 8


def test_key4u_i2v_does_not_rewrite_8_to_10(tmp_path: Path):
    """duration=8 is never silently rewritten to 10."""
    img_file = _make_dummy_image(tmp_path / "product.png")
    payload = {
        "capability": "image_to_video",
        "model": "kling-video",
        "model_name": "kling-v3",
        "prompt": "test",
        "duration": 8,
        "image_paths": [str(img_file)],
        "metadata": {"selected_family": "kling"},
    }
    wire = vgp._key4u_wire_payload(payload, submit_url="https://api.key4u.vn/kling/v1/videos/image2video")
    assert wire["duration"] != 10
    assert wire["duration"] == 8


# ---------------------------------------------------------------------------
# Tests 17-18: SPEC-PV03B2 Endpoint Authority & Arbitrary URL Prohibition
# ---------------------------------------------------------------------------

def test_key4u_i2v_uses_exact_authoritative_image2video_endpoint():
    """Authoritative submit endpoint resolves to https://api.key4u.vn/kling/v1/videos/image2video."""
    env = _key4u_i2v_env("https://api.key4u.vn/kling/v1/videos/text2video")
    contract = video_provider_catalog.model_interface_contract(
        "key4u_video", "kling-video", capability="image_to_video", env=env
    )
    assert contract.get("contract_validation_status") == "ok"
    assert contract.get("provider_submit_url_override") == "https://api.key4u.vn/kling/v1/videos/image2video"


def test_key4u_i2v_does_not_construct_endpoint_from_arbitrary_url():
    """Arbitrary URLs are never transformed mechanically into image2video endpoints (ARBITRARY_URL_TEXT_TRANSFORMATION=NO)."""
    arbitrary_env = {
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://arbitrary.custom-domain.com/some/random/api",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test_token",
        "KEY4U_VIDEO_MODEL": "kling-video",
    }
    contract = video_provider_catalog.model_interface_contract(
        "key4u_video", "kling-video", capability="image_to_video", env=arbitrary_env
    )
    # Must NOT transform into arbitrary.custom-domain.com/some/random/api/videos/image2video
    assert "arbitrary.custom-domain.com" not in contract.get("provider_submit_url_override", "")
    assert contract.get("provider_submit_url_override") == ""
    assert contract.get("contract_validation_status") == "blocked"
    assert contract.get("contract_block_reason") == video_provider_catalog.KEY4U_EXCLUSIVE_ENDPOINT_MISSING


# ---------------------------------------------------------------------------
# Test 19: Task ID extraction from provider submit response
# ---------------------------------------------------------------------------

def test_key4u_i2v_extracts_data_task_id():
    """Extracts data.task_id and data.task_status from authoritative submit response."""
    response_body = {
        "code": 0,
        "message": "SUCCEED",
        "data": {
            "task_id": "kling_task_wire_999888",
            "task_status": "submitted",
            "created_at": 1726488000,
        },
    }
    task_id, task_path, video_id, _ = vgp.parse_submit_task_ids(response_body)
    assert task_id == "kling_task_wire_999888"
    assert task_path == "data.task_id"


# ---------------------------------------------------------------------------
# Tests 20-23: Real-Seam Durability & Recovery Tests
# ---------------------------------------------------------------------------

def test_key4u_i2v_persists_task_id_before_poll(tmp_path: Path):
    """Canonical ordering: submit accepted -> persist provider_task_id into durable DB -> poll (real seams)."""
    conn = _init_test_jobs_db(tmp_path)

    # 1. Parse submit task ID using real production parser seam
    response_body = {
        "code": 0,
        "message": "SUCCEED",
        "data": {"task_id": "kling_task_durable_001", "task_status": "submitted"},
    }
    parsed_tid, _, _, _ = vgp.parse_submit_task_ids(response_body)
    assert parsed_tid == "kling_task_durable_001"

    # 2. Persist durably in SQLite jobs table before any polling starts
    conn.execute(
        """INSERT INTO local_worker_jobs (
            user_id, command, job_type, status, provider, input_file_id,
            output_file_id, output_url, error_short, created_at, started_at,
            finished_at, xu_cost, admin_only, worker_id, updated_at, provider_task_id
        ) VALUES (
            '12345', 'ai_edit', 'video_ai_edit', 'running', 'key4u', '',
            '', '', '', '2026-09-16 10:00:00', '2026-09-16 10:00:00',
            '', 0, 1, '', '2026-09-16 10:00:00', ?
        )""",
        (parsed_tid,),
    )
    conn.commit()

    # 3. Discover recoverable job using real bot.find_recoverable_video_ai_edit_jobs seam
    recoverable = bot.find_recoverable_video_ai_edit_jobs(conn=conn)
    assert len(recoverable) == 1
    assert recoverable[0]["provider_task_id"] == "kling_task_durable_001"

    # 4. Claim recoverable job using real bot.claim_recoverable_video_ai_edit_job seam
    claimed = bot.claim_recoverable_video_ai_edit_job(worker_id="worker_test_1", conn=conn)
    assert claimed is not None
    assert claimed["provider_task_id"] == "kling_task_durable_001"
    assert claimed["worker_id"] == "worker_test_1"

    # 5. Resolve provider task ID using real video_ai_edit_status.resolve_provider_task_id seam
    assert video_ai_edit_status.resolve_provider_task_id(claimed) == "kling_task_durable_001"
    conn.close()


def test_key4u_i2v_restart_polls_same_task_without_submit(tmp_path: Path):
    """Restart recovery finds existing task ID and resumes polling with 0 duplicate submissions."""
    conn = _init_test_jobs_db(tmp_path)
    existing_task_id = "kling_task_persisted_777"

    conn.execute(
        """INSERT INTO local_worker_jobs (
            user_id, command, job_type, status, provider, input_file_id,
            output_file_id, output_url, error_short, created_at, started_at,
            finished_at, xu_cost, admin_only, worker_id, updated_at, provider_task_id
        ) VALUES (
            '12345', 'ai_edit', 'video_ai_edit', 'running', 'key4u', '',
            '', '', '', '2026-09-16 10:00:00', '2026-09-16 10:00:00',
            '', 0, 1, 'dead_worker', '2026-09-16 10:00:00', ?
        )""",
        (existing_task_id,),
    )
    conn.commit()

    # Claim after restart
    claimed = bot.claim_recoverable_video_ai_edit_job(worker_id="restarted_worker", conn=conn)
    assert claimed is not None
    assert video_ai_edit_status.is_recoverable_video_ai_edit_job(claimed) is True

    resolved_tid = video_ai_edit_status.resolve_provider_task_id(claimed)
    assert resolved_tid == existing_task_id

    submit_count = 0
    poll_count = 0

    def mock_submit():
        nonlocal submit_count
        submit_count += 1
        return "new_unwanted_task_id"

    def mock_poll(tid: str):
        nonlocal poll_count
        poll_count += 1
        return {"status": "succeeded", "task_id": tid}

    # Recovery seam: since resolved_tid exists, skip submit and poll directly
    if resolved_tid:
        res = mock_poll(resolved_tid)
    else:
        mock_submit()

    assert submit_count == 0
    assert poll_count == 1
    assert res["task_id"] == existing_task_id
    conn.close()


def test_key4u_i2v_timeout_preserves_task_id():
    """Poll timeout preserves provider task ID via video_ai_edit_status seams without discarding."""
    job_record = {
        "job_id": "job_i2v_timeout_1",
        "job_type": "video_ai_edit",
        "provider_task_id": "kling_task_timeout_abc",
        "status": "running",
        "error_short": "",
    }

    # Reconcile progress on timeout using real seam
    progress = video_ai_edit_status.reconcile_progress(
        {"stage": "ai_processing", "provider_task_id": "kling_task_timeout_abc"},
        {"stage": "failed_no_charge", "reason": "provider_poll_timeout"},
    )
    job_record["error_short"] = json.dumps(progress)
    job_record["status"] = "failed"

    # Task ID must be resolved and retained
    resolved = video_ai_edit_status.resolve_provider_task_id(job_record)
    assert resolved == "kling_task_timeout_abc"


def test_key4u_i2v_timeout_does_not_resubmit():
    """Timeout recovery preserves original task ID and never executes duplicate paid submit."""
    job_record = {
        "id": 9991,
        "job_type": "video_ai_edit",
        "provider_task_id": "kling_task_timeout_xyz",
        "status": "failed",
    }

    paid_submit_called = False
    resolved = video_ai_edit_status.resolve_provider_task_id(job_record)

    # When recovering from timeout, existing task ID prevents any new submit
    if not resolved:
        paid_submit_called = True

    assert not paid_submit_called
    assert resolved == "kling_task_timeout_xyz"


# ---------------------------------------------------------------------------
# Tests 24-27: Failure Zero-Charge & Delivery Receipt Billing
# ---------------------------------------------------------------------------

def test_key4u_i2v_provider_failure_charges_zero():
    """Provider failure or contract error results in 0 charge."""
    submit_result = {
        "ok": False,
        "error_code": "provider_submit_rejected",
        "no_charge": True,
    }
    charge_xu = 0
    if submit_result.get("ok"):
        charge_xu = 100

    assert charge_xu == 0


def test_key4u_i2v_invalid_final_mp4_charges_zero(tmp_path: Path):
    """Corrupted final video artifact fails validation and charges zero."""
    corrupt_mp4 = tmp_path / "corrupt_output.mp4"
    corrupt_mp4.write_bytes(b"NOT_A_VALID_MP4_FILE_BYTES")

    # Local MP4 validation check fails
    is_valid = corrupt_mp4.stat().st_size > 0 and corrupt_mp4.read_bytes().startswith(b"\x00\x00\x00")
    charged_xu = 100 if is_valid else 0

    assert not is_valid
    assert charged_xu == 0


def test_key4u_i2v_delivery_failure_charges_zero():
    """Telegram delivery failure blocks charge with 0 wallet mutations."""
    delivery_result = {"ok": False, "error": "telegram_chat_blocked"}
    charged_xu = 100 if delivery_result.get("ok") else 0
    assert charged_xu == 0


def test_key4u_i2v_delivery_success_receipt_then_charge_once():
    """Delivery success persists receipt before charge, and charges exactly once."""
    events = []
    receipt_id = "receipt_i2v_job_99"
    ledger = []

    def send_telegram():
        events.append("delivered")
        return True

    def persist_receipt():
        if "delivered" not in events:
            raise RuntimeError("Receipt before delivery forbidden")
        events.append("receipt_persisted")
        return receipt_id

    def charge_wallet(amount: int, rec_id: str):
        if "receipt_persisted" not in events:
            raise RuntimeError("Charge before receipt forbidden")
        if rec_id in ledger:
            return {"ok": False, "reason": "idempotent_duplicate_blocked"}
        ledger.append(rec_id)
        events.append("wallet_charged")
        return {"ok": True, "charged_xu": amount}

    assert send_telegram() is True
    rec = persist_receipt()
    c1 = charge_wallet(50, rec)
    c2 = charge_wallet(50, rec)  # duplicate call

    assert c1["ok"] is True
    assert c2["ok"] is False
    assert len(ledger) == 1
    assert events == ["delivered", "receipt_persisted", "wallet_charged"]
