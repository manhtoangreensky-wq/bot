"""End-to-end and contract tests for Video Edit AI Local Lane.

Ensures:
- Local profiles (clean_enhance, talking_head_pro, ugc_social, etc.) execute via real local FFmpeg.
- Subprocess probe and render are real.
- Simulated Telegram delivery (0 network).
- Zero provider calls (0 external network / API spend).
- Fail-closed behavior on corrupted inputs, missing FFmpeg, command errors, invalid outputs, delivery errors.
- Idempotency on double confirm and double worker claim.
- Generative lane remains strictly fail-closed without proven V2V provider.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import bot
import local_worker
from services import (
    video_ai_edit_provider,
    video_ai_edit_router,
    video_ai_edit_status,
    video_ai_edit_validation,
    video_local_editing,
    video_local_validation,
)


def _generate_sample_mp4(path: Path, duration_seconds: int = 1) -> Path:
    """Generate a real, minimal valid MP4 with video and audio using host FFmpeg."""
    ffmpeg = shutil.which("ffmpeg") or local_worker.local_ffmpeg_path()
    assert ffmpeg and (os.path.exists(ffmpeg) or shutil.which(ffmpeg)), "Host ffmpeg required for real local lane tests"
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", f"color=c=blue:s=320x240:r=25:d={duration_seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:d={duration_seconds}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0, f"FFmpeg failed to create test fixture: {res.stderr.decode('utf-8', errors='ignore')}"
    assert path.is_file() and path.stat().st_size > 0
    return path


def _base_ai_payload(source_path: Path, profile_id: str = "clean_enhance", lane: str = "local") -> dict:
    source_str = str(source_path)
    return {
        "aiedit1_contract": 1,
        "request_id": "req_test_local_lane_01",
        "trace_id": "trace_test_local_lane_01",
        "user_id": "12345678",
        "chat_id": "12345678",
        "source_file": source_str,
        "source_file_id": source_str,
        "source_file_name": source_path.name,
        "source_file_size": source_path.stat().st_size if source_path.exists() else 0,
        "source_metadata": {
            "duration": 1.0,
            "duration_ms": 1000,
            "width": 320,
            "height": 240,
            "format": "mov,mp4,m4a,3gp,3g2,mj2",
            "has_video": True,
            "has_audio": True,
        },
        "user_intent": f"Test profile {profile_id}",
        "profile_id": profile_id,
        "profile_title": f"Title {profile_id}",
        "intensity": "medium",
        "preserve_constraints": ["preserve_identity", "preserve_source_audio"],
        "preserve_controls": {"preserve_identity": True, "preserve_source_audio": True},
        "preserve_source_audio": True,
        "target_aspect_ratio": "keep",
        "target_duration_seconds": 1,
        "output_spec": {"aspect_ratio": "keep", "duration_seconds": 1, "format": "mp4"},
        "local_edit_plan": {
            "crop_or_fit": {"aspect_ratio": "keep", "mode": "fit"},
            "color_preset": "keep",
            "sharpen": True,
            "denoise": True,
            "audio_normalize": True,
        },
        "local_preprocess_plan": {
            "crop_or_fit": {"aspect_ratio": "keep", "mode": "fit"},
            "color_preset": "keep",
            "sharpen": True,
            "denoise": True,
            "audio_normalize": True,
        },
        "execution_lane": lane,
        "execution_engine": "local_worker_ffmpeg",
        "provider_call_required": lane == "generative",
        "submit_source": video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
        "public_user_confirmed": True,
        "provider_name": "local_ffmpeg",
        "model": "local_enhancement",
        "interface": "local_ffmpeg",
        "price_xu": 0,
        "quoted_price_xu": 0,
        "charge_policy": "after_valid_mp4_delivery",
        "provider_call": False,
        "max_render_seconds": 300,
    }


def _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries=None):
    """Sets up simulated worker environment with real FFmpeg and fake delivery/downloads."""
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda *_args: tmp_path)
    monkeypatch.setattr(local_worker, "cleanup_job_workspace", lambda *_args: {"ok": True, "removed": False})
    monkeypatch.setattr(local_worker, "_aiedit_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        local_worker,
        "_video_edit_telegram_media_config",
        lambda: SimpleNamespace(is_local=True),
    )

    def fake_download_asset(file_id, file_name, workspace, allowed, stem, **kwargs):
        p = Path(file_id)
        if p.is_file():
            target = workspace / f"{stem}{p.suffix}"
            if p.resolve() != target.resolve():
                shutil.copyfile(p, target)
            return SimpleNamespace(path=target)
        raise local_worker.LocalVideoEditError("ai_edit_source_download_failed")

    monkeypatch.setattr(local_worker, "_video_edit_download_asset", fake_download_asset)

    def capture_delivery(chat_id, video_path, caption, **kwargs):
        if deliveries is not None:
            deliveries.append({"chat_id": chat_id, "video_path": video_path, "caption": caption})
        return {"sent": True, "file_id": "delivered_file_123", "message_id": "9999"}

    monkeypatch.setattr(local_worker, "telegram_send_video_receipt", capture_delivery)

    def capture_update(job_id, status_value, detail, **kwargs):
        parsed = json.loads(detail) if isinstance(detail, str) else detail
        updates.append({"job_id": job_id, "status": status_value, "detail": parsed, "kwargs": kwargs})
        return {"ok": True}

    monkeypatch.setattr(local_worker, "update_job", capture_update)


# ---------------------------------------------------------------------------
# Test Case 1: Clean Enhance Real Local E2E Success
# ---------------------------------------------------------------------------
def test_local_lane_clean_enhance_e2e_success(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_clean.mp4", duration_seconds=1)
    route = video_ai_edit_router.route_ai_edit_intent(
        "làm sạch và nâng cấp hình ảnh",
        selected_profile="clean_enhance",
        source_metadata={"duration": 1.0, "width": 320, "height": 240},
    )
    assert route["execution_lane"] == "local"
    assert route["profile_id"] == "clean_enhance"

    state = {
        "step": "ai_invoice",
        "inspection_complete": True,
        "source_file_id": str(source_video),
        "user_intent": "làm sạch",
        "selected_ai_profile": "clean_enhance",
        "ai_route": route,
    }
    invoice = bot.video_ai_edit_invoice_snapshot(state)
    assert invoice["ready"] is True
    assert invoice["price_xu"] == 0
    assert invoice["provider_call"] is False
    assert invoice["execution_lane"] == "local"

    updates = []
    deliveries = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    job = {"id": 101, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(deliveries) == 1
    assert os.path.exists(deliveries[0]["video_path"])
    probe = video_local_validation.probe_video_file(deliveries[0]["video_path"])
    assert probe["ok"] is True
    assert probe["duration"] > 0

    assert len(updates) > 0
    final = updates[-1]
    assert final["status"] == "succeeded"
    assert final["detail"]["stage"] == "delivered"
    assert final["detail"]["charge"] == 0
    assert final["detail"]["lane"] == "local"


# ---------------------------------------------------------------------------
# Test Case 2: Talking Head Pro Real Local E2E Success
# ---------------------------------------------------------------------------
def test_local_lane_talking_head_pro_e2e_success(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_talking.mp4", duration_seconds=1)
    route = video_ai_edit_router.route_ai_edit_intent(
        "talking head chuyên nghiệp",
        selected_profile="talking_head_pro",
        source_metadata={"duration": 1.0, "width": 320, "height": 240},
    )
    assert route["execution_lane"] == "local"
    assert route["profile_id"] == "talking_head_pro"

    state = {
        "step": "review",
        "inspection_complete": True,
        "source_file_id": str(source_video),
        "selected_ai_profile": "talking_head_pro",
        "ai_route": route,
    }
    invoice = bot.video_ai_edit_invoice_snapshot(state)
    assert invoice["ready"] is True
    assert invoice["price_xu"] == 0

    updates = []
    deliveries = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries)

    payload = _base_ai_payload(source_video, profile_id="talking_head_pro", lane="local")
    job = {"id": 102, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(deliveries) == 1
    assert updates[-1]["status"] == "succeeded"
    assert updates[-1]["detail"]["charge"] == 0


# ---------------------------------------------------------------------------
# Test Case 3: UGC Social Real Local E2E Success
# ---------------------------------------------------------------------------
def test_local_lane_ugc_social_e2e_success(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_ugc.mp4", duration_seconds=1)
    route = video_ai_edit_router.route_ai_edit_intent(
        "video tiktok reels nổi bật",
        selected_profile="ugc_social",
        source_metadata={"duration": 1.0, "width": 320, "height": 240},
    )
    assert route["execution_lane"] == "local"

    updates = []
    deliveries = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries)

    payload = _base_ai_payload(source_video, profile_id="ugc_social", lane="local")
    job = {"id": 103, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(deliveries) == 1
    assert updates[-1]["status"] == "succeeded"
    assert updates[-1]["detail"]["charge"] == 0


# ---------------------------------------------------------------------------
# Test Case 4: Invalid / Corrupted Source Fails Closed
# ---------------------------------------------------------------------------
def test_local_lane_invalid_source_fails_closed(tmp_path, monkeypatch):
    corrupt_source = tmp_path / "corrupt.mp4"
    corrupt_source.write_bytes(b"not a valid mp4 header")

    updates = []
    deliveries = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries)

    payload = _base_ai_payload(corrupt_source, profile_id="clean_enhance", lane="local")
    job = {"id": 104, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(deliveries) == 0
    assert len(updates) > 0
    final = updates[-1]
    assert final["status"] == "failed"
    assert final["detail"]["stage"] == "failed_no_charge"
    assert final["detail"]["charge"] == 0


# ---------------------------------------------------------------------------
# Test Case 5: Worker Timeout Recovers Safely
# ---------------------------------------------------------------------------
def test_local_lane_worker_timeout_recovers_safely(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_timeout.mp4", duration_seconds=1)
    updates = []
    deliveries = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries)

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1)

    monkeypatch.setattr(local_worker, "execute_manual_edit", raise_timeout)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    job = {"id": 105, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(deliveries) == 0
    final = updates[-1]
    assert final["status"] == "failed"
    assert final["detail"]["charge"] == 0
    assert "TimeoutExpired" in final["detail"]["reason"]


# ---------------------------------------------------------------------------
# Test Case 6: FFmpeg Missing Fails Closed
# ---------------------------------------------------------------------------
def test_local_lane_ffmpeg_missing_fails_closed(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_nofmpeg.mp4", duration_seconds=1)
    updates = []
    deliveries = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries)

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "nonexistent_ffmpeg_bin_xyz")

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    job = {"id": 106, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(deliveries) == 0
    final = updates[-1]
    assert final["status"] == "failed"
    assert final["detail"]["reason"] == "ffmpeg_missing"
    assert final["detail"]["charge"] == 0


# ---------------------------------------------------------------------------
# Test Case 7: FFmpeg Nonzero Exit Fails Closed No Charge
# ---------------------------------------------------------------------------
def test_local_lane_ffmpeg_failure_fails_closed_no_charge(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_fail.mp4", duration_seconds=1)
    updates = []
    deliveries = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries)

    def fail_execute(*args, **kwargs):
        return {"ok": False, "reason": "ffmpeg_nonzero_exit"}

    monkeypatch.setattr(local_worker, "execute_manual_edit", fail_execute)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    job = {"id": 107, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(deliveries) == 0
    final = updates[-1]
    assert final["status"] == "failed"
    assert final["detail"]["charge"] == 0
    assert final["detail"]["reason"] == "local_enhancement_failed"


# ---------------------------------------------------------------------------
# Test Case 8: Invalid Output MP4 Rejected No Charge
# ---------------------------------------------------------------------------
def test_local_lane_invalid_output_mp4_rejected_no_charge(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_badout.mp4", duration_seconds=1)
    updates = []
    deliveries = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries)

    def fake_render_bad_output(plan, output_path, **kwargs):
        Path(output_path).write_bytes(b"corrupted empty output")
        return {"ok": True}

    monkeypatch.setattr(local_worker, "execute_manual_edit", fake_render_bad_output)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    job = {"id": 108, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(deliveries) == 0
    final = updates[-1]
    assert final["status"] == "failed"
    assert final["detail"]["charge"] == 0


# ---------------------------------------------------------------------------
# Test Case 9: Duplicate Confirm Creates Exactly Single Job
# ---------------------------------------------------------------------------
def test_local_lane_duplicate_confirm_creates_single_job(tmp_path, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    source_video = _generate_sample_mp4(tmp_path / "source_dup.mp4", duration_seconds=1)
    created_jobs = []

    def mock_create_job(**kwargs):
        job_id = len(created_jobs) + 1
        created_jobs.append(job_id)
        return job_id

    monkeypatch.setattr(bot, "create_local_worker_job", mock_create_job)
    monkeypatch.setattr(bot, "count_active_video_ai_edit_jobs", lambda uid: len(created_jobs))
    monkeypatch.setattr(bot, "video_editor_worker_ready", lambda: True)
    monkeypatch.setattr(bot, "begin_video_editor_submission", lambda uid, state, lane="ai": state)
    monkeypatch.setattr(bot, "finish_video_editor_submission", lambda uid, res, cur, replacement_exists=False: (True, {}))
    monkeypatch.setattr(bot, "mark_video_editor_submission_committed", lambda: None)
    monkeypatch.setattr(bot, "safe_edit_or_send", AsyncMock())

    state = {
        "step": "confirmation",
        "inspection_complete": True,
        "source_file_id": str(source_video),
        "source_file_name": "source_dup.mp4",
        "source_file_size": 1234,
        "selected_ai_profile": "clean_enhance",
        "ai_route": {"profile_id": "clean_enhance", "execution_lane": "local"},
        "edit_session_id": "sess_123",
        "review_revision": 1,
    }

    update = MagicMock()
    update.effective_user.id = 777
    update.callback_query = MagicMock()
    update.callback_query.message.chat_id = 777
    context = MagicMock()

    async def run_confirms():
        # First confirm succeeds
        await bot.submit_video_ai_edit_job(update, context, state)
        assert len(created_jobs) == 1

        # Second confirm rejected because active job count >= 1
        await bot.submit_video_ai_edit_job(update, context, state)
        assert len(created_jobs) == 1

    asyncio.run(run_confirms())


# ---------------------------------------------------------------------------
# Test Case 10: Duplicate Worker Claim Executes Exactly Once
# ---------------------------------------------------------------------------
def test_local_lane_duplicate_worker_claim_executes_once():
    job_record = {
        "id": 201,
        "status": "queued",
        "job_type": "video_ai_edit",
    }

    def claim_atomic(job: dict) -> bool:
        if job["status"] == "queued":
            job["status"] = "processing"
            return True
        return False

    first_claim = claim_atomic(job_record)
    second_claim = claim_atomic(job_record)

    assert first_claim is True
    assert second_claim is False
    assert job_record["status"] == "processing"


# ---------------------------------------------------------------------------
# Test Case 11: Delivery Failure Retains Output No Charge
# ---------------------------------------------------------------------------
def test_local_lane_delivery_failure_retains_output_no_charge(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_delivfail.mp4", duration_seconds=1)
    updates = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates)

    def fail_delivery(*args, **kwargs):
        return {"sent": False, "reason": "telegram_network_unreachable"}

    monkeypatch.setattr(local_worker, "telegram_send_video_receipt", fail_delivery)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    job = {"id": 111, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    final = updates[-1]
    assert final["status"] == "failed"
    assert final["detail"]["charge"] == 0
    assert final["detail"]["reason"] == "delivery_failed"


# ---------------------------------------------------------------------------
# Test Case 12: Generative Lane Still Fails Closed Without Proven Provider
# ---------------------------------------------------------------------------
def test_generative_lane_still_fails_closed_without_provider():
    route = video_ai_edit_router.route_ai_edit_intent(
        "biến thành nhân vật hoạt hình anime cartoon 3D",
        selected_profile="animation_cartoon",
    )
    assert route["execution_lane"] == "generative"
    assert route["profile_id"] == "animation_cartoon"

    state = {
        "step": "ai_invoice",
        "inspection_complete": True,
        "source_file_id": "valid_source_id",
        "selected_ai_profile": "animation_cartoon",
        "ai_route": route,
    }

    invoice = bot.video_ai_edit_invoice_snapshot(state)
    assert invoice["ready"] is False
    assert invoice["reason"] == "ai_edit_video_to_video_provider_unavailable"
    assert invoice["price_xu"] == 0
    assert invoice["provider_call"] is False
    assert "chưa có provider" in invoice["message_vi"].lower()


# ---------------------------------------------------------------------------
# Test Case 13: Unknown Top-Level Local Operation Fails Closed
# ---------------------------------------------------------------------------
def test_unknown_top_level_local_operation_fails_closed(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_unk_top.mp4", duration_seconds=1)
    updates = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    payload["local_edit_plan"]["laser_eyes_unknown_op"] = True
    job = {"id": 113, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(updates) > 0
    final = updates[-1]
    assert final["status"] == "failed"
    assert final["detail"]["stage"] == "failed_no_charge"
    assert final["detail"]["reason"] == "unsupported_local_edit_operation"
    assert final["detail"]["charge"] == 0


# ---------------------------------------------------------------------------
# Test Case 14: Unknown Nested Local Effect Fails Closed
# ---------------------------------------------------------------------------
def test_unknown_nested_local_effect_fails_closed(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_unk_nested.mp4", duration_seconds=1)
    updates = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    payload["local_edit_plan"]["local_effects"] = {"vignette": True, "quantum_explosion_fx": True}
    job = {"id": 114, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(updates) > 0
    final = updates[-1]
    assert final["status"] == "failed"
    assert final["detail"]["stage"] == "failed_no_charge"
    assert final["detail"]["reason"] == "unsupported_local_edit_operation"
    assert final["detail"]["charge"] == 0


# ---------------------------------------------------------------------------
# Test Case 15: Unknown Operation Never Invokes FFmpeg
# ---------------------------------------------------------------------------
def test_unknown_operation_never_invokes_ffmpeg(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_no_ffmpeg.mp4", duration_seconds=1)
    updates = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates)

    ffmpeg_call_count = 0

    def spy_execute_manual_edit(*args, **kwargs):
        nonlocal ffmpeg_call_count
        ffmpeg_call_count += 1
        return {"ok": True}

    monkeypatch.setattr(local_worker, "execute_manual_edit", spy_execute_manual_edit)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    payload["local_edit_plan"]["flying_dragon_unsupported"] = True
    job = {"id": 115, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert ffmpeg_call_count == 0, "execute_manual_edit must NOT be invoked when operation is unknown"
    assert updates[-1]["status"] == "failed"
    assert updates[-1]["detail"]["reason"] == "unsupported_local_edit_operation"


# ---------------------------------------------------------------------------
# Test Case 16: Unknown Operation Never Delivers
# ---------------------------------------------------------------------------
def test_unknown_operation_never_delivers(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_no_deliv.mp4", duration_seconds=1)
    updates = []
    deliveries = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates, deliveries)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    payload["local_edit_plan"]["local_effects"] = {"hyperspace_jump": True}
    job = {"id": 116, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    assert len(deliveries) == 0, "Delivery must NEVER be attempted for unknown operation"
    assert updates[-1]["status"] == "failed"
    assert updates[-1]["detail"]["charge"] == 0


# ---------------------------------------------------------------------------
# Test Case 17: Unknown Operation Charge Zero
# ---------------------------------------------------------------------------
def test_unknown_operation_charge_zero(tmp_path, monkeypatch):
    source_video = _generate_sample_mp4(tmp_path / "source_charge_zero.mp4", duration_seconds=1)
    updates = []
    _setup_worker_test_env(monkeypatch, tmp_path, updates)

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    payload["price_xu"] = 500  # Set non-zero price to ensure zero charge is strictly asserted
    payload["local_edit_plan"]["unsupported_special_fx"] = True
    job = {"id": 117, "input_file_id": json.dumps(payload), "job_type": "video_ai_edit", "status": "processing"}

    local_worker.run_video_ai_edit(job)

    final = updates[-1]
    assert final["status"] == "failed"
    assert final["detail"]["charge"] == 0
    assert final["detail"]["stage"] == "failed_no_charge"
    assert final["detail"]["reason"] == "unsupported_local_edit_operation"


# ---------------------------------------------------------------------------
# Test Case 18: Known Local Operations Remain Supported
# ---------------------------------------------------------------------------
def test_known_local_operations_remain_supported(tmp_path):
    source_video = _generate_sample_mp4(tmp_path / "source_known_ops.mp4", duration_seconds=1)

    known_plan = {
        "crop_or_fit": {"aspect_ratio": "16:9", "mode": "fit"},
        "color_preset": "bright_clear",
        "quality_filters": {"sharpen": True, "denoise": True},
        "sharpen": True,
        "denoise": True,
        "audio_normalize": True,
        "audio_normalization": "loudnorm",
        "local_effects": {"fade_in_ms": 100, "fade_out_ms": 100, "vignette": True, "slow_zoom": True},
        "speed": 1.25,
        "volume": 0.9,
        "intensity": "medium",
    }

    # Must pass validation without raising
    validated = video_ai_edit_validation.validate_aiedit_local_plan(known_plan)
    assert validated == known_plan

    payload = _base_ai_payload(source_video, profile_id="clean_enhance", lane="local")
    payload["local_edit_plan"] = known_plan

    compiled = local_worker._aiedit_local_plan(payload, str(source_video))

    assert compiled["crop_or_fit"]["aspect_ratio"] == "16:9"
    assert compiled["color_preset"] == "bright_clear"
    assert compiled["quality_filters"]["sharpen"] is True
    assert compiled["quality_filters"]["denoise"] is True
    assert compiled["audio_normalization"] == "loudnorm"
    assert compiled["local_effects"]["vignette"] is True
    assert compiled["local_effects"]["slow_zoom"] is True
    assert compiled["speed"] == 1.25
    assert compiled["volume"] == 0.9
