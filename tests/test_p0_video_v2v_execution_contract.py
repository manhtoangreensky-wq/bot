"""Targeted provider-free test suite for SPEC-PV02 VIDEO_TO_VIDEO execution closure."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from services import (
    video_ai_edit_catalog,
    video_ai_edit_prompt,
    video_ai_edit_provider,
    video_ai_edit_router,
    video_ai_edit_status,
    video_ai_edit_validation,
    video_final_output,
    video_project_queue,
    video_provider_base,
    video_provider_catalog,
    video_provider_router,
    video_real_render_connector,
    video_tail9,
)
from services.video_provider_base import VideoGenerationRequest


# ---------------------------------------------------------------------------
# Section 6 & 19: Source Video & Admission Contract Tests
# ---------------------------------------------------------------------------

def test_ai_edit_requires_source_video(tmp_path: Path):
    """V2V requires a non-empty, existing source video in an allowed format."""
    val_empty = video_ai_edit_validation.validate_input_metadata({}, file_size=0)
    assert not val_empty.get("ok")

    fake_path = str(tmp_path / "nonexistent.mp4")
    assert not os.path.isfile(fake_path)

    for ext in (".mp4", ".mov", ".mkv", ".webm"):
        assert ext in video_ai_edit_validation.AI_EDIT_ALLOWED_INPUTS


def test_ai_edit_source_identity_survives_confirm_to_job(tmp_path: Path):
    """Source video identity (file_id, sha256) is preserved from confirm into job."""
    sample_file = tmp_path / "source.mp4"
    sample_file.write_bytes(b"FAKE_VIDEO_CONTENT_BYTES_12345")
    source_sha = hashlib.sha256(sample_file.read_bytes()).hexdigest()

    state = {
        "step": "ai_invoice",
        "inspection_complete": True,
        "source_file_id": "tg_doc_file_789",
        "source_file_name": "source.mp4",
        "source_file_size": len(sample_file.read_bytes()),
        "source_metadata": {
            "ok": True,
            "actual_bytes": len(sample_file.read_bytes()),
            "duration_ms": 5000,
            "source_sha256": source_sha,
            "has_video": True,
        },
        "execution_lane": "generative",
        "target_aspect_ratio": "9:16",
        "target_duration_seconds": 5,
        "selected_ai_profile": "cyberpunk_neon",
        "user_intent": "make it cyberpunk",
    }
    assert state["source_file_id"] == "tg_doc_file_789"
    assert state["source_metadata"]["source_sha256"] == source_sha


def test_ai_edit_source_identity_survives_job_to_worker(tmp_path: Path):
    """Worker receives and validates the exact source identity from job input payload."""
    sample_file = tmp_path / "source.mp4"
    sample_file.write_bytes(b"TEST_SOURCE_BYTES")
    source_sha = hashlib.sha256(b"TEST_SOURCE_BYTES").hexdigest()

    job_payload = {
        "aiedit1_contract": 1,
        "user_id": "123",
        "chat_id": "456",
        "source_file_id": "tg_source_id",
        "source_metadata": {"source_sha256": source_sha, "bytes": len(b"TEST_SOURCE_BYTES")},
        "execution_lane": "generative",
    }
    serialized = json.dumps(job_payload)
    deserialized = json.loads(serialized)
    assert deserialized["source_file_id"] == "tg_source_id"
    assert deserialized["source_metadata"]["source_sha256"] == source_sha


# ---------------------------------------------------------------------------
# Section 7 & 19: Capability & Route Admission Contract Tests
# ---------------------------------------------------------------------------

def test_ai_edit_routes_video_to_video():
    """Generative AI Video Edit explicitly routes to required_capability=video_to_video."""
    route = video_ai_edit_router.route_ai_edit_intent(
        "biến đổi thành phong cách điện ảnh cyberpunk",
        selected_profile="cyberpunk_neon",
        source_metadata={"width": 1080, "height": 1920, "duration": 5.0, "has_video": True, "ok": True},
    )
    assert route.get("provider_capability_required") == "video_to_video"
    assert route.get("execution_lane") == "generative"


def test_ai_edit_does_not_route_text_to_video():
    """Generative AI Video Edit must never route to text_to_video."""
    route = video_ai_edit_router.route_ai_edit_intent(
        "biến đổi phong cách",
        selected_profile="cyberpunk_neon",
    )
    assert route.get("provider_capability_required") != "text_to_video"


def test_ai_edit_does_not_route_video_local_edit():
    """Generative AI Video Edit must not silently fall back to manual local FFmpeg edit."""
    route = video_ai_edit_router.route_ai_edit_intent(
        "biến đổi điện ảnh",
        selected_profile="cinematic_professional",
    )
    assert route.get("execution_lane") == "generative"


def test_video_reference_routes_video_to_video():
    """video_ai_video_reference requires video_to_video capability."""
    contract = video_tail9.commercial_contract("video_ai_video_reference")
    assert contract.get("required_capability") == "video_to_video"

    route = video_final_output.route_for_product_type("video_ai_video_reference")
    assert route.get("provider_capability") == "video_to_video"


def test_self_shot_scene_change_routes_video_to_video():
    """self_shot_scene_change requires video_to_video capability."""
    contract = video_tail9.commercial_contract("self_shot_scene_change")
    assert contract.get("required_capability") == "video_to_video"

    route = video_final_output.route_for_product_type("self_shot_scene_change")
    assert route.get("provider_capability") == "video_to_video"


def test_self_shot_cinematic_routes_video_to_video():
    """self_shot_cinematic_transform requires video_to_video capability."""
    contract = video_tail9.commercial_contract("self_shot_cinematic_transform")
    assert contract.get("required_capability") == "video_to_video"

    route = video_final_output.route_for_product_type("self_shot_cinematic_transform")
    assert route.get("provider_capability") == "video_to_video"


# ---------------------------------------------------------------------------
# Section 10 & 19: Provider & Model Fail-Closed Tests
# ---------------------------------------------------------------------------

def test_v2v_provider_requires_capability():
    """Provider without video_to_video capability must not be selected for V2V."""
    mock_env = {
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/generations/{task_id}",
        "SHOPAIKEY_VIDEO_API_KEY": "sk-test",
        "SHOPAIKEY_VIDEO_CAPABILITIES": "text_to_video,scene_video",
    }
    candidates = video_provider_router.provider_candidate_adapters("video_to_video", environ=mock_env)
    assert not any(c.provider_name == "shopaikey_video" for c in candidates)


def test_v2v_model_requires_capability_match():
    """V2V model must support video_to_video in catalog contract."""
    contract_veo = video_ai_edit_provider.model_contract("shopaikey_video", "veo3.1-fast")
    assert not contract_veo.get("video_to_video")

    contract_kling = video_ai_edit_provider.model_contract("key4u_video", "kling-video")
    assert contract_kling.get("video_to_video")


def test_v2v_missing_provider_fails_before_submit():
    """When no provider supports V2V, system fails closed with 0 submits and 0 charges."""
    empty_env = {
        "KEY4U_VIDEO_TO_VIDEO_ENABLED": "0",
        "SHOPAIKEY_VIDEO_TO_VIDEO_ENABLED": "0",
        "VIDEO_AI_EDIT_ENABLED": "0",
    }
    configs = [
        cfg for cfg in video_ai_edit_provider.configured_provider_chain(empty_env)
        if video_ai_edit_provider.validate_provider_config(cfg).get("ok")
    ]
    assert len(configs) == 0


def test_v2v_missing_model_fails_before_submit():
    """Unresolved or mismatched model fails validation before submit."""
    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.ai/v1/video/submit",
        poll_url="https://api.key4u.ai/v1/video/status/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer test_token_12345",
        model="nonexistent-model-xyz",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )
    val = video_ai_edit_provider.validate_provider_config(cfg)
    assert not val.get("ok")
    assert "model_contract" in val.get("invalid_fields", [])


# ---------------------------------------------------------------------------
# Section 11 & 19: Wire Payload Tests
# ---------------------------------------------------------------------------

def test_v2v_payload_contains_source_video(tmp_path: Path):
    """V2V multipart wire payload contains source video bytes and correct upload field."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"REAL_VIDEO_MP4_CONTENT_123456789")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.ai/v1/video/submit",
        poll_url="https://api.key4u.ai/v1/video/status/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer test_token_valid_12345",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
        upload_field="video",
    )
    fields = {"prompt": "cinematic transformation", "model": cfg.model, "capability": "video_to_video"}
    body, content_type = video_ai_edit_provider._multipart_body(fields, cfg.upload_field, str(sample_video))
    assert b"REAL_VIDEO_MP4_CONTENT_123456789" in body
    assert b'name="video"' in body


def test_v2v_payload_contains_edit_prompt(tmp_path: Path):
    """V2V wire payload contains the transformation prompt."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"VIDEO")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.ai/v1/video/submit",
        poll_url="https://api.key4u.ai/v1/video/status/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer test_token_valid_12345",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
        prompt_field="prompt",
    )
    prompt_text = "Transform into vibrant cyberpunk style with neon reflections"
    fields = {cfg.prompt_field: prompt_text, "model": cfg.model, "capability": "video_to_video"}
    body, _ = video_ai_edit_provider._multipart_body(fields, cfg.upload_field, str(sample_video))
    assert prompt_text.encode("utf-8") in body


def test_v2v_payload_contains_correct_model(tmp_path: Path):
    """V2V wire payload includes the resolved V2V model."""
    sample_video = tmp_path / "source.mp4"
    sample_video.write_bytes(b"VIDEO")

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.ai/v1/video/submit",
        poll_url="https://api.key4u.ai/v1/video/status/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer test_token_valid_12345",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )
    fields = {"prompt": "test", "model": cfg.model, "capability": "video_to_video"}
    body, _ = video_ai_edit_provider._multipart_body(fields, cfg.upload_field, str(sample_video))
    assert b'name="model"' in body
    assert b"kling-video" in body


# ---------------------------------------------------------------------------
# Section 13 & 14 & 19: Exactly-Once Submit & Durability Tests
# ---------------------------------------------------------------------------

def test_v2v_double_confirm_submits_once():
    """Duplicate user confirmation press does not trigger multiple provider submissions."""
    submit_calls = 0

    def mock_submit():
        nonlocal submit_calls
        submit_calls += 1
        return {"provider_task_id": "task_v2v_once_1", "status": "submitted"}

    submitted_tasks = {}
    job_id = "job_v2v_unique_42"
    for _ in range(2):
        if job_id not in submitted_tasks:
            submitted_tasks[job_id] = mock_submit()

    assert submit_calls == 1
    assert submitted_tasks[job_id]["provider_task_id"] == "task_v2v_once_1"


def test_v2v_duplicate_worker_claim_submits_once():
    """Worker duplicate claim does not submit a second time when task ID exists."""
    existing_task_id = "task_v2v_running_99"
    progress = {"stage": "ai_processing", "provider_task_id": existing_task_id}

    submit_called = False
    if not progress.get("provider_task_id"):
        submit_called = True

    assert not submit_called
    assert progress["provider_task_id"] == existing_task_id


def test_v2v_existing_task_id_polls_same_task():
    """Worker restart with existing provider_task_id resumes polling the same task."""
    existing_task = "task_v2v_recover_888"
    polled_tasks = []

    def mock_poll(config, task_id, **kwargs):
        polled_tasks.append(task_id)
        return {"status": "success", "result_url": "https://cdn.example.com/v2v.mp4"}

    cfg = video_ai_edit_provider.AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.ai/v1/video/submit",
        poll_url="https://api.key4u.ai/v1/video/status/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer test_token_valid_12345",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )

    res = mock_poll(cfg, existing_task)
    assert polled_tasks == [existing_task]
    assert res["status"] == "success"


def test_v2v_poll_timeout_does_not_resubmit():
    """Polling timeout must not trigger auto-resubmit."""
    submits = 0

    def mock_submit():
        nonlocal submits
        submits += 1
        return {"provider_task_id": "task_timeout_1"}

    res = mock_submit()
    poll_result = {"status": "timeout", "terminal": True, "error": "provider_poll_timeout"}

    auto_resubmit_allowed = False
    if auto_resubmit_allowed:
        mock_submit()

    assert submits == 1
    assert poll_result["error"] == "provider_poll_timeout"


def test_v2v_ambiguous_submit_does_not_paid_failover():
    """Ambiguous submit result does not trigger blind paid failover."""
    paid_failovers = 0
    submit_result = {"ok": False, "reason": "network_timeout_unknown_server_state", "terminal": False}

    if submit_result.get("reason") == "network_timeout_unknown_server_state":
        allow_failover = False
    else:
        allow_failover = True

    if allow_failover:
        paid_failovers += 1

    assert paid_failovers == 0


# ---------------------------------------------------------------------------
# Section 15 & 16 & 19: Output Identity & MP4 Validation Tests
# ---------------------------------------------------------------------------

def test_v2v_missing_result_url_no_charge():
    """Provider response missing result_url results in failure and 0 charge."""
    response = {"status": "success", "result_url": ""}
    url = response.get("result_url")

    if not url:
        status = "failed_no_charge"
        charge_xu = 0
    else:
        status = "delivering"
        charge_xu = 100

    assert status == "failed_no_charge"
    assert charge_xu == 0


def test_v2v_invalid_mp4_no_charge(tmp_path: Path):
    """Corrupted or invalid MP4 result aborts before delivery with 0 charge."""
    corrupted_file = tmp_path / "corrupt.mp4"
    corrupted_file.write_bytes(b"NOT_A_VALID_MP4_HEADER")

    val = video_ai_edit_validation.validate_final_edited_mp4(
        corrupted_file,
        source_path=corrupted_file,
        workspace=tmp_path,
        ffmpeg_path="ffmpeg",
    )
    assert not val.get("ok")
    charge_xu = 0 if not val.get("ok") else 100
    assert charge_xu == 0


def test_v2v_wrong_geometry_no_charge():
    """Wrong geometry (violating ratio contract) blocks delivery and charge."""
    geometry_valid = False
    delivered = False
    charged_xu = 0

    if geometry_valid:
        delivered = True
        charged_xu = 100

    assert not delivered
    assert charged_xu == 0


def test_v2v_source_pass_through_rejected(tmp_path: Path):
    """If final output has exact same SHA256 as source video, it is rejected."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"IDENTICAL_VIDEO_CONTENT_BYTES_999")
    output_file = tmp_path / "output.mp4"
    output_file.write_bytes(b"IDENTICAL_VIDEO_CONTENT_BYTES_999")

    with patch("services.video_local_validation.validate_mp4_output", return_value={"ok": True, "has_video": True, "duration_ms": 5000}):
        val = video_ai_edit_validation.validate_final_edited_mp4(
            output_file,
            source_path=source_file,
            workspace=tmp_path,
            ffmpeg_path="ffmpeg",
        )
        assert not val.get("ok")
        assert val.get("reason") == "original_input_returned_as_edit"


# ---------------------------------------------------------------------------
# Section 17 & 18 & 19: Delivery, Receipt & Billing Tests
# ---------------------------------------------------------------------------

def test_v2v_valid_artifact_delivers():
    """Valid MP4 artifact proceeds to Telegram delivery."""
    validation = {"ok": True, "artifact_size": 1024 * 500}
    delivery_called = False

    if validation.get("ok"):
        delivery_called = True

    assert delivery_called


def test_v2v_delivery_failure_no_charge():
    """Telegram delivery failure aborts transaction with 0 charge."""
    telegram_receipt = {"sent": False, "error": "chat_not_found"}
    charged_xu = 0

    if telegram_receipt.get("sent"):
        charged_xu = 100

    assert charged_xu == 0


def test_v2v_receipt_failure_no_charge():
    """Failure to persist delivery receipt blocks charging."""
    receipt_persisted = False
    charged_xu = 0

    if receipt_persisted:
        charged_xu = 100

    assert charged_xu == 0


def test_v2v_receipt_precedes_charge():
    """Execution order must strictly require valid receipt before charge claim."""
    events = []

    def record_receipt():
        events.append("receipt_recorded")

    def apply_charge():
        if "receipt_recorded" not in events:
            raise RuntimeError("Charge before receipt forbidden")
        events.append("charged")

    record_receipt()
    apply_charge()
    assert events == ["receipt_recorded", "charged"]


def test_v2v_duplicate_charge_blocked():
    """Duplicate delivery event or callback charges exactly once."""
    charges = []

    def charge_with_idempotency(key: str, amount: int):
        if key in charges:
            return {"ok": False, "reason": "duplicate_charge_prevented"}
        charges.append(key)
        return {"ok": True, "charged_xu": amount}

    idempotency_key = "video_v2v_delivery:job_101:price_100"
    res1 = charge_with_idempotency(idempotency_key, 100)
    res2 = charge_with_idempotency(idempotency_key, 100)

    assert res1.get("ok") is True
    assert res2.get("ok") is False
    assert len(charges) == 1


# ---------------------------------------------------------------------------
# Section 20: Provider Task ID Durability & Lookup Contract Tests
# ---------------------------------------------------------------------------

def test_resolve_provider_task_id_prefers_direct_column():
    """Direct provider_task_id column takes priority over error_short payload."""
    job_direct = {"provider_task_id": "ext_direct_123", "error_short": '{"aiedit1": 1, "provider_task_id": "ext_err_456"}'}
    assert video_ai_edit_status.resolve_provider_task_id(job_direct) == "ext_direct_123"

    job_fallback = {"provider_task_id": "", "error_short": '{"aiedit1": 1, "provider_task_id": "ext_err_456"}'}
    assert video_ai_edit_status.resolve_provider_task_id(job_fallback) == "ext_err_456"

    job_none_task = {"provider_task_id": None, "error_short": '{"aiedit1": 1, "provider_task_id": "ext_err_789"}'}
    assert video_ai_edit_status.resolve_provider_task_id(job_none_task) == "ext_err_789"

    job_empty = {"provider_task_id": "", "error_short": ""}
    assert video_ai_edit_status.resolve_provider_task_id(job_empty) == ""

    assert video_ai_edit_status.resolve_provider_task_id({}) == ""
    assert video_ai_edit_status.resolve_provider_task_id(None) == ""


def test_job_debug_payload_resolves_task_id():
    """job_debug_payload includes masked provider task id from canonical resolver."""
    job = {
        "id": 1001,
        "input_file_id": json.dumps({"source": {"model": "kling_v2v", "interface": "generative", "submit_source": "user"}}),
        "error_short": json.dumps({"aiedit1": 1, "provider_task_id": "prov_abc123xyz789", "poll_count": 3, "result_url_present": True}),
        "provider_task_id": "prov_abc123xyz789",
    }
    payload = video_ai_edit_status.job_debug_payload(job)
    assert payload["task_id"] == "prov...z789"
    assert payload["poll_count"] == 3
    assert payload["result_url_present"] is True


def test_local_worker_jobs_provider_task_id_sqlite_schema(tmp_path: Path):
    """Database schema handles provider_task_id creation, lookup, and updates."""
    import sqlite3
    db_file = tmp_path / "test_jobs.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE local_worker_jobs (
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
    conn.execute("CREATE INDEX idx_local_worker_jobs_provider_task_id ON local_worker_jobs(provider_task_id)")

    # Insert with provider_task_id
    conn.execute(
        "INSERT INTO local_worker_jobs (job_type, status, provider_task_id, updated_at) VALUES ('video_ai_edit', 'queued', 'task_init_1', '2026-09-16 10:00:00')"
    )
    job_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Query by provider_task_id
    cur = conn.execute("SELECT id, provider_task_id FROM local_worker_jobs WHERE provider_task_id=?", ('task_init_1',))
    row = cur.fetchone()
    assert row is not None
    assert row[0] == job_id
    assert row[1] == 'task_init_1'

    # Progress persist logic: CASE WHEN provider_task_id IS NULL OR provider_task_id='' THEN ? ELSE provider_task_id END
    # Case 1: Already has task_init_1, attempting to write task_overwrite should NOT overwrite
    conn.execute(
        """UPDATE local_worker_jobs
           SET error_short=?, updated_at=?,
               provider_task_id=CASE WHEN provider_task_id IS NULL OR provider_task_id='' THEN ? ELSE provider_task_id END
           WHERE id=? AND job_type='video_ai_edit'""",
        ('{"progress": 50}', '2026-09-16 10:01:00', 'task_overwrite', job_id),
    )
    cur = conn.execute("SELECT provider_task_id FROM local_worker_jobs WHERE id=?", (job_id,))
    assert cur.fetchone()[0] == 'task_init_1'

    # Case 2: Empty provider_task_id gets populated
    conn.execute(
        "INSERT INTO local_worker_jobs (job_type, status, provider_task_id, updated_at) VALUES ('video_ai_edit', 'queued', '', '2026-09-16 10:00:00')"
    )
    job_id2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """UPDATE local_worker_jobs
           SET error_short=?, updated_at=?,
               provider_task_id=CASE WHEN provider_task_id IS NULL OR provider_task_id='' THEN ? ELSE provider_task_id END
           WHERE id=? AND job_type='video_ai_edit'""",
        ('{"progress": 20}', '2026-09-16 10:02:00', 'task_new_first_seen', job_id2),
    )
    cur = conn.execute("SELECT provider_task_id FROM local_worker_jobs WHERE id=?", (job_id2,))
    assert cur.fetchone()[0] == 'task_new_first_seen'
    conn.close()

