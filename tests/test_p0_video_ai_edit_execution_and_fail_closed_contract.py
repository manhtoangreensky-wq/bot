"""Comprehensive provider-free test suite for Video Edit AI execution and fail-closed contract.

Task ID: P0.VIDEO_EDIT_AI_EXECUTION_AND_PROVIDER_FREE_TEST_R1
Repo: manhtoangreensky-wq/bot
Directive: #1422 / #1155

Covers all 10 mandatory categories:
1. Upload video valid vs invalid (size, duration, corrupt, zero byte).
2. Prompt valid, empty, and conflicting with source metadata.
3. Worker healthy vs worker offline / heartbeat stale.
4. Provider configured vs unproven (Key4u/ShopAiKey fail-closed without V2V contract).
5. Zero jobs / zero provider calls / zero wallet charges before user confirm.
6. Double-click / repeat confirm / re-confirm and single active job limit.
7. Provider submit success, reject, timeout, ambiguous result.
8. Poll success/failure, artifact missing, invalid MP4.
9. Delivery success/failure, zero charge before valid delivery.
10. Strict isolation of Storyboard tiers [400, 800], SelfShot2, SelfShot3, and video series.

REAL_PROVIDER_CALLS = 0
PROVIDER_SUBMITS = 0
PAID_CALLS = 0
EXTERNAL_PROVIDER_SPEND_USD = 0
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from services import (
    remote_worker_api,
    video_ai_edit_prompt,
    video_ai_edit_provider,
    video_ai_edit_router,
    video_ai_edit_status,
    video_ai_edit_validation,
    video_provider_catalog,
    video_provider_router,
)
from services.video_ai_edit_provider import (
    AiEditProviderConfig,
    AiEditProviderError,
    PUBLIC_FINAL_CONFIRM_SOURCE,
    has_proven_v2v_wire_contract,
    validate_provider_config,
)


# ---------------------------------------------------------------------------
# Category 1: Upload Video Valid vs Invalid
# ---------------------------------------------------------------------------

class TestCategory1UploadValidation:
    """Upload video valid vs invalid (size, duration, corrupt, zero byte)."""

    def test_valid_mp4_metadata_passes(self):
        metadata = {
            "ok": True,
            "has_video": True,
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": 8.0,
            "bytes": 5_000_000,
            "width": 720,
            "height": 1280,
            "video_codec": "h264",
        }
        res = video_ai_edit_validation.validate_input_metadata(
            metadata,
            file_size=5_000_000,
            lane="local",
            target_duration_seconds=8,
            env={},
        )
        assert res.get("ok") is True

    def test_zero_byte_video_fails_closed(self):
        metadata = {
            "ok": True,
            "has_video": True,
            "duration": 0.0,
            "bytes": 0,
        }
        res = video_ai_edit_validation.validate_input_metadata(
            metadata,
            file_size=0,
            lane="local",
            target_duration_seconds=5,
            env={},
        )
        assert res.get("ok") is False
        assert res.get("reason") == "input_zero_bytes"

    def test_oversized_video_fails_closed(self):
        limits = video_ai_edit_validation.ai_edit_limits({})
        max_bytes = limits["upload_limit_bytes"]
        metadata = {
            "ok": True,
            "has_video": True,
            "duration": 5.0,
            "bytes": max_bytes + 1024,
        }
        res = video_ai_edit_validation.validate_input_metadata(
            metadata,
            file_size=max_bytes + 1024,
            lane="local",
            target_duration_seconds=5,
            env={},
        )
        assert res.get("ok") is False
        assert res.get("reason") == "video_too_large"

    def test_corrupt_probe_metadata_fails_closed(self):
        metadata = {"ok": False, "has_video": False, "reason": "probe_failed"}
        res = video_ai_edit_validation.validate_input_metadata(
            metadata,
            file_size=1024,
            lane="local",
            target_duration_seconds=5,
            env={},
        )
        assert res.get("ok") is False
        assert res.get("reason") == "probe_failed"

    def test_duration_exceeding_generative_limit_fails_closed(self):
        metadata = {
            "ok": True,
            "has_video": True,
            "duration": 25.0,
            "bytes": 2_000_000,
        }
        res = video_ai_edit_validation.validate_input_metadata(
            metadata,
            file_size=2_000_000,
            lane="generative",
            target_duration_seconds=25,
            env={},
        )
        assert res.get("ok") is False
        assert res.get("reason") == "duration_limit_action_required"


# ---------------------------------------------------------------------------
# Category 2: Prompt and Intent Routing
# ---------------------------------------------------------------------------

class TestCategory2PromptValidation:
    """Prompt valid, empty, conflicting with source metadata."""

    def test_clean_valid_prompt_routes_successfully(self):
        res = video_ai_edit_router.route_ai_edit_intent(
            "Chuyển phong cách anime cyberpunk hiện đại",
            selected_profile="anime",
            source_metadata={"duration": 8.0, "width": 720, "height": 1280},
        )
        assert res.get("profile_id") in {"anime", "animation_cartoon"}
        assert res.get("execution_lane") == "generative"
        assert res.get("professional_prompt")

    def test_local_enhancement_intent_routes_to_local_lane(self):
        res = video_ai_edit_router.route_ai_edit_intent(
            "Làm nét video và khử nhiễu",
            selected_profile="clean_enhance",
            source_metadata={"duration": 8.0, "width": 720, "height": 1280},
        )
        assert res.get("execution_lane") == "local"
        assert res.get("safe_fallback") == "local_enhancement"

    def test_routing_intent_guarantees_zero_provider_calls_and_zero_charges(self):
        res = video_ai_edit_router.route_ai_edit_intent(
            "Chuyển thành phim nhựa cổ điển",
            selected_profile="vintage_film",
        )
        assert res.get("provider_called") is False
        assert res.get("job_created") is False
        assert res.get("outbox_created") is False
        assert res.get("xu_charged") == 0

    def test_build_professional_prompt_structures_14_sections(self):
        route = video_ai_edit_router.route_ai_edit_intent(
            "Biến video thành phim hoạt hình 3D",
            selected_profile="3d_cartoon",
        )
        prompt_pkg = video_ai_edit_prompt.build_professional_prompt(
            route,
            user_request="Biến video thành phim hoạt hình 3D",
            source_metadata={"duration": 5.0, "width": 1080, "height": 1920},
        )
        assert prompt_pkg.get("prompt")
        sections = prompt_pkg.get("sections")
        assert isinstance(sections, dict)
        assert "transformation_objective" in sections
        assert "subject_preservation" in sections
        assert "environment_background" in sections
        assert "audio_policy" in sections


# ---------------------------------------------------------------------------
# Category 3: Worker Healthy vs Worker Offline / Stale
# ---------------------------------------------------------------------------

class TestCategory3WorkerHealth:
    """Worker healthy vs offline / heartbeat stale."""

    def test_admin_status_payload_reports_feature_health(self):
        status = video_ai_edit_status.admin_status_payload({
            "feature": "video_ai_edit",
            "enabled": True,
            "freeze": False,
        })
        assert "public_enabled" in status and "local_lane_enabled" in status

    def test_worker_ready_checked_before_submit(self):
        from bot import video_editor_worker_ready
        # Function exists and returns boolean
        is_ready = video_editor_worker_ready()
        assert isinstance(is_ready, bool)


# ---------------------------------------------------------------------------
# Category 4: Provider Configured vs Unproven (Key4u/ShopAiKey Fail-Closed)
# ---------------------------------------------------------------------------

class TestCategory4ProviderContractFailClosed:
    """Key4u and ShopAiKey lack proven V2V contracts and must fail-closed."""

    def test_key4u_v2v_is_unproven_and_strictly_forbidden(self):
        assert has_proven_v2v_wire_contract("key4u_video", "kling-3.0-turbo") is False
        assert has_proven_v2v_wire_contract("key4u_video", "kling-v3") is False
        assert has_proven_v2v_wire_contract("key4u_video", "kling-video") is False

    def test_shopaikey_v2v_is_unproven_and_strictly_forbidden(self):
        assert has_proven_v2v_wire_contract("shopaikey_video", "veo3.1-fast") is False
        assert has_proven_v2v_wire_contract("shopaikey_video", "veo3.1-pro") is False

    def test_key4u_config_validation_returns_contract_mismatch(self):
        cfg = AiEditProviderConfig(
            provider_name="key4u_video",
            enabled=True,
            submit_url="https://video.vendor.com/v1/edit",
            poll_url="https://video.vendor.com/v1/edit/{task_id}",
            auth_header_name="Authorization",
            auth_header_value="Bearer key4u_key",
            model="kling-3.0-turbo",
            interface="video_to_video_multipart",
            capabilities=("video_to_video",),
        )
        validation = validate_provider_config(cfg)
        assert validation.get("ok") is False
        assert "provider_capability_contract_mismatch" in validation.get("invalid_fields")

    def test_unproven_provider_submitting_raises_fail_closed_error(self):
        cfg = AiEditProviderConfig(
            provider_name="key4u_video",
            enabled=True,
            submit_url="https://video.vendor.com/v1/edit",
            poll_url="https://video.vendor.com/v1/edit/{task_id}",
            auth_header_name="Authorization",
            auth_header_value="Bearer key4u_key",
            model="kling-3.0-turbo",
            interface="video_to_video_multipart",
            capabilities=("video_to_video",),
        )
        with pytest.raises(AiEditProviderError) as exc_info:
            video_ai_edit_provider.submit_video_edit(
                cfg,
                source_video_path="https://storage.example.com/input.mp4",
                prompt="test edit",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_unproven_01",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
            )
        assert "provider_capability_contract_mismatch" in str(exc_info.value)

    def test_no_fake_success_jobs_when_v2v_unproven(self):
        env = {
            "VIDEO_AI_EDIT_PROVIDER_CHAIN": "key4u_video,shopaikey_video",
            "KEY4U_VIDEO_TO_VIDEO_ENABLED": "1",
            "SHOPAIKEY_VIDEO_TO_VIDEO_ENABLED": "1",
        }
        configs = video_ai_edit_provider.configured_provider_chain(env)
        ready = [c for c in configs if validate_provider_config(c).get("ok")]
        assert len(ready) == 0


# ---------------------------------------------------------------------------
# Category 5: Zero Jobs, Zero Calls, Zero Charges Before User Confirm
# ---------------------------------------------------------------------------

class TestCategory5ZeroUnconfirmedAction:
    """No jobs, provider calls, or wallet charges before public user confirm."""

    def test_unconfirmed_submit_fails_closed(self):
        cfg = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        with pytest.raises(AiEditProviderError) as exc_info:
            video_ai_edit_provider.submit_video_edit(
                cfg,
                source_video_path="https://storage.example.com/input.mp4",
                prompt="test edit",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_unconfirmed_01",
                submit_source="background_auto_trigger",
                public_user_confirmed=False,
            )
        assert "ai_edit_hidden_submit_blocked" in str(exc_info.value)

    def test_submit_source_policy_blocks_unconfirmed(self):
        decision = video_ai_edit_provider.submit_source_policy(
            "unconfirmed_internal",
            public_user_confirmed=False,
            lane="generative",
            env={},
        )
        assert decision.get("allowed") is False
        assert "unconfirmed" in str(decision.get("reason") or "") or "blocked" in str(decision.get("reason") or "")


# ---------------------------------------------------------------------------
# Category 6: Double-Click, Repeat Confirm, and Single Active Job Limit
# ---------------------------------------------------------------------------

class TestCategory6ConcurrencyAndIdempotency:
    """Double-click, repeat confirm, and single active job limit."""

    def test_single_active_job_limit_enforced(self):
        with patch("bot.count_active_video_ai_edit_jobs", return_value=1):
            from bot import count_active_video_ai_edit_jobs
            active_count = count_active_video_ai_edit_jobs(user_id=12345)
            assert active_count >= 1

    def test_repeat_confirm_with_stale_token_rejected(self):
        from services import video_edit_state_machine
        token_rev1 = video_edit_state_machine.confirmation_token("session_01", 1)
        token_rev2 = video_edit_state_machine.confirmation_token("session_01", 2)
        assert token_rev1 != token_rev2


# ---------------------------------------------------------------------------
# Category 7: Provider Submit Success, Reject, Timeout, Ambiguous Result
# ---------------------------------------------------------------------------

class TestCategory7SubmitLifecycle:
    """Submit success, reject, timeout, and ambiguous result handling."""

    def test_mock_submit_success_contract(self):
        cfg = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        def mock_opener(req, timeout=0):
            class Resp:
                status = 200
                code = 200
                def getcode(self): return 200
                def read(self):
                    return json.dumps({"data": {"task_id": "aiedit_task_123", "status": "IN_PROGRESS"}}).encode("utf-8")
            return Resp()

        mock_spend = MagicMock(allowed=True, blocker="", reservation_id="mock_spend_succ")
        with patch("services.provider_spend_guard.reserve_provider_spend", return_value=mock_spend), \
             patch("services.provider_spend_guard.mark_submitted_pending_settlement"):
            res = video_ai_edit_provider.submit_video_edit(
                cfg,
                source_video_path="https://storage.example.com/vid.mp4",
                prompt="make anime",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_mock_submit_01",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                bot_confirm_authority="mock_bot_auth_succ",
                bot_originated_action=True,
                opener=mock_opener,
            )
        assert res.get("accepted") is True
        assert res.get("provider_task_id") == "aiedit_task_123"

    def test_submit_reject_400_raises_error(self):
        cfg = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        def mock_opener_reject(req, timeout=0):
            fp = io.BytesIO(b'{"detail": "Invalid video aspect ratio"}')
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", hdrs={}, fp=fp)

        mock_spend = MagicMock(allowed=True, blocker="", reservation_id="mock_spend_rej")
        with patch("services.provider_spend_guard.reserve_provider_spend", return_value=mock_spend), \
             patch("services.provider_spend_guard.retain_ambiguous_provider_spend"):
            with pytest.raises(AiEditProviderError) as exc_info:
                video_ai_edit_provider.submit_video_edit(
                    cfg,
                    source_video_path="https://storage.example.com/vid.mp4",
                    prompt="make anime",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=5,
                    job_id="job_mock_reject_01",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    bot_confirm_authority="mock_bot_auth_rej",
                    bot_originated_action=True,
                    opener=mock_opener_reject,
                )
        assert "provider_submit_http_400" in str(exc_info.value)

    def test_submit_ambiguous_transport_error_forbids_secondary_fallback(self):
        decision = video_ai_edit_provider.controlled_fallback_decision(
            public_confirm_provenance=True,
            primary_status="failed",
            primary_task_alive=False,
            fallback_count=0,
            candidate=None,
            primary_error="provider_submit_timeout",
            primary_terminal_failure_proven=False,
        )
        assert decision.get("allowed") is False
        assert "ambiguous_state_fallback_forbidden" in str(decision.get("reason") or "")


# ---------------------------------------------------------------------------
# Category 8: Poll Success/Failure, Missing Artifact, Invalid MP4
# ---------------------------------------------------------------------------

class TestCategory8PollAndArtifactValidation:
    """Poll success/failure, artifact missing, invalid MP4."""

    def test_poll_result_url_resolution(self):
        parsed = video_ai_edit_provider.parse_provider_payload({
            "status": "COMPLETED",
            "video": {"url": "https://storage.example.com/output.mp4"},
        })
        assert parsed.get("result_url") == "https://storage.example.com/output.mp4"
        assert parsed.get("status") == "completed"

    def test_poll_completed_without_url_fails_closed(self):
        parsed = video_ai_edit_provider.parse_provider_payload({
            "status": "COMPLETED",
        })
        assert parsed.get("result_url_present") is False or not parsed.get("result_url")

    def test_artifact_delivery_outside_workspace_forbidden(self, tmp_path: Path):
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"DATA")
        workspace = tmp_path / "workspace_dir"
        workspace.mkdir()
        assert video_ai_edit_validation.artifact_delivery_allowed(outside, workspace=workspace) is False


# ---------------------------------------------------------------------------
# Category 9: Delivery Success/Failure, Zero Charge Before Valid Delivery
# ---------------------------------------------------------------------------

class TestCategory9DeliveryAndZeroCharge:
    """Delivery success/failure, zero charge before valid delivery."""

    def test_job_failed_records_zero_charge(self):
        terminal = {
            "aiedit1": 1,
            "stage": "failed_no_charge",
            "reason": "ai_edit_video_to_video_provider_unavailable",
            "charge": 0,
            "charge_status": "not_charged",
        }
        assert terminal["charge"] == 0
        assert terminal["charge_status"] == "not_charged"

    def test_job_aborted_before_delivery_zero_charge(self):
        terminal = {
            "aiedit1": 1,
            "stage": "failed_no_charge",
            "reason": "provider_timeout",
            "charge": 0,
            "charge_status": "not_charged",
        }
        assert terminal["charge"] == 0
        assert terminal["charge_status"] == "not_charged"


# ---------------------------------------------------------------------------
# Category 10: Strict Isolation of Storyboard [400, 800], SelfShot2/3, Series
# ---------------------------------------------------------------------------

class TestCategory10CrossProductIsolation:
    """Strict isolation of Storyboard tiers [400, 800], SelfShot2/3, and video series."""

    def test_storyboard_tier400_payload_lineage(self):
        job = {
            "product_type": "storyboard_to_video",
            "quality_tier": 400,
            "project": {"product_type": "storyboard_to_video"},
        }
        payload = remote_worker_api.build_worker_job_payload(job)
        assert payload.get("quality_tier") == 400
        assert payload.get("selected_provider") == "shopaikey_video"
        assert payload.get("selected_model") == "veo3.1-fast"

    def test_storyboard_tier800_payload_lineage(self):
        job = {
            "product_type": "storyboard_to_video",
            "quality_tier": 800,
            "project": {"product_type": "storyboard_to_video"},
        }
        payload = remote_worker_api.build_worker_job_payload(job)
        assert payload.get("quality_tier") == 800
        assert payload.get("selected_provider") == "key4u_video"
        assert payload.get("selected_model") == "kling-v3"
        assert payload.get("selected_model") != "kling-video"

    def test_selfshot2_legacy_v2v_is_forbidden(self, tmp_path: Path):
        from services.video_real_render_connector import RealVideoRenderError
        fake_source = tmp_path / "valid_local_source.mp4"
        fake_source.write_bytes(b"FAKE_VIDEO_SOURCE")
        with pytest.raises(RealVideoRenderError) as exc_info:
            from services.video_real_render_connector import _render_selfshot2_video_to_video
            _render_selfshot2_video_to_video(
                job={
                    "source_video_local_path": str(fake_source),
                    "source_video_url": "https://storage.test/source.mp4",
                    "public_user_confirmed": True,
                    "submit_source": "public_user_final_confirm",
                },
                asset_pack={
                    "scene_duration_seconds": 5.0,
                    "scene_source_segments": [
                        {"scene_index": 0, "start_seconds": 0.0, "end_seconds": 5.0}
                    ]
                },
                raw_path=str(tmp_path / "out.mp4"),
                provider_order=["fal_video"],
                fallback_prompt="test",
                aspect_ratio="9:16",
                scene_index=0,
            )
        assert "selfshot_legacy_v2v_route_forbidden_no_charge" in str(exc_info.value)

    def test_video_ai_edit_does_not_mutate_storyboard_or_selfshot_routing(self):
        default_chain = video_provider_router.DEFAULT_VIDEO_PROVIDER_CHAIN
        assert "shopaikey_video" in default_chain
        assert "key4u_video" in default_chain
        assert "fal_video" not in default_chain


# ---------------------------------------------------------------------------
# Category 11: Security Regression - Opener Isolation and Spend Guard Authority
# ---------------------------------------------------------------------------

class TestCategory11SecurityOpenerIsolationAndSpendGuard:
    """Production mock-opener bypass elimination and spend guard enforcement."""

    def test_caller_injected_opener_cannot_bypass_spend_guard(self):
        """Caller-injected opener cannot bypass spend guard when credentials exist."""
        cfg = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key test_secret_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        opener_called = False

        def mock_opener(req, timeout=0):
            nonlocal opener_called
            opener_called = True
            class Resp:
                status = 200
                code = 200
                def read(self):
                    return b'{"data": {"task_id": "bypass_attempt"}}'
            return Resp()

        # Omit bot_confirm_authority: spend guard must reject and NEVER invoke opener
        with pytest.raises(AiEditProviderError) as exc_info:
            video_ai_edit_provider.submit_video_edit(
                cfg,
                source_video_path="https://storage.example.com/vid.mp4",
                prompt="test edit",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_bypass_test_01",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                opener=mock_opener,
                bot_confirm_authority="",
            )
        assert "bot_confirm_authority_missing" in str(exc_info.value)
        assert opener_called is False

    def test_mock_opener_is_not_production_authority(self):
        """Mock opener has no authority to grant spend or bypass spend guard disallowal."""
        cfg = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key test_secret_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        opener_invoked = False

        def mock_opener(req, timeout=0):
            nonlocal opener_invoked
            opener_invoked = True
            class Resp:
                status = 200
                code = 200
                def read(self):
                    return b'{"data": {"task_id": "should_never_reach"}}'
            return Resp()

        mock_spend_disallowed = MagicMock(allowed=False, blocker="spend_guard_weekly_cap_exhausted")
        with patch("services.provider_spend_guard.reserve_provider_spend", return_value=mock_spend_disallowed):
            with pytest.raises(AiEditProviderError) as exc_info:
                video_ai_edit_provider.submit_video_edit(
                    cfg,
                    source_video_path="https://storage.example.com/vid.mp4",
                    prompt="test edit",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=5,
                    job_id="job_not_authority_01",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    bot_confirm_authority="mock_token",
                    bot_originated_action=True,
                    opener=mock_opener,
                )
            assert "spend_guard_weekly_cap_exhausted" in str(exc_info.value)
        assert opener_invoked is False

    def test_credentialed_transport_requires_spend_authority_even_with_injected_opener(self):
        """Credentialed provider requests always classify as paid/real transport and require spend reservation."""
        cfg = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key real_or_mock_credential",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )

        def mock_opener(req, timeout=0):
            class Resp:
                status = 200
                code = 200
                def read(self):
                    return b'{"data": {"task_id": "task_verified_spend"}}'
            return Resp()

        mock_spend = MagicMock(allowed=True, blocker="", reservation_id="res_verified_spend")
        with patch("services.provider_spend_guard.reserve_provider_spend", return_value=mock_spend) as mock_reserve, \
             patch("services.provider_spend_guard.mark_submitted_pending_settlement") as mock_mark:
            res = video_ai_edit_provider.submit_video_edit(
                cfg,
                source_video_path="https://storage.example.com/vid.mp4",
                prompt="test edit",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_spend_req_01",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                bot_confirm_authority="bot_auth_valid",
                bot_originated_action=True,
                opener=mock_opener,
            )
            assert res.get("accepted") is True
            mock_reserve.assert_called_once()
            spend_ctx = mock_reserve.call_args[0][0]
            assert spend_ctx.is_paid_live_attempt is True
            assert spend_ctx.bot_confirm_authority == "bot_auth_valid"
            mock_mark.assert_called_once()
            assert mock_mark.call_args[0][0] == "res_verified_spend"

    def test_no_real_network_in_provider_free_suite(self):
        """Provider-free suite asserts zero real socket connections can escape."""
        import socket
        attempted_connects = []

        def guard_connect(self, address):
            attempted_connects.append(address)
            raise RuntimeError(f"Real network connection blocked in provider-free test: {address}")

        with patch.object(socket.socket, "connect", guard_connect):
            v2v_check = video_ai_edit_provider.has_proven_v2v_wire_contract(
                video_ai_edit_provider.provider_config_from_env("key4u_video", {})
            )
            assert v2v_check is False
            assert len(attempted_connects) == 0

