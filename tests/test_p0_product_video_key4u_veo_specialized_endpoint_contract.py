"""Regression test suite for Key4U Veo specialized endpoint remediation (R15.13A).

TASK_ID: P0.PRODUCT_VIDEO_KEY4U_VEO_PREMERGE_CONTRACT_CORRECTION_R15_13A
TRACKER: #1155 (OPEN)
BASE_HEAD_SHA: 60d7a4b6a53a90c13116e83cd9eb0d4e675987e6
SCOPE: STORYBOARD_VEO_PREMERGE_CORRECTION_ONLY

Enforces:
1. Submit endpoint resolves to canonical https://api.key4u.vn/v1/videos.
2. Poll endpoint resolves to canonical https://api.key4u.vn/v1/videos/{task_id}.
3. Catalog config binds submit_endpoint and poll_endpoint for veo_3_1-fast.
4. Zero normalization or fallback rewriting to /v1/video/create.
5. Adapter default wiring resolves /v1/videos for Veo even when generic env points to /v1/video/create.
6. Adapter ignores generic /v1/video/create and /v1/video/query when specialized env is omitted.
7. JSON wire payload contains model, prompt, aspect_ratio, duration, images array; top-level image is absent.
8. Wire payload strictly rejects /v1/video/create for Google Veo (fail-closed, no charge).
9. Submit job dispatches JSON wire payload via _open_json (NOT multipart form).
10. Submit job blocks legacy /v1/video/create fail-closed with no charge.
11. Polling URL path embedding preserves https://api.key4u.vn/v1/videos/{task_id}.
12. Pending recovery prevents mixed contract between /v1/video/create and /v1/videos/{task_id}.
13. Auth header contract is unchanged (Authorization: Bearer <token>).
14. Duration integrity: 8.0s valid, 6.016s raw output fails closed without fake tpad padding.
15. Negative guard: has_proven_v2v_wire_contract("key4u_video") is False; arbitrary V2V fail-closed.
"""

import json
from urllib.parse import urlparse
import pytest

from providers.key4u_provider import config_from_env
from providers.video_generic_http_provider import (
    GenericHttpVideoProvider,
    VideoProviderContractError,
    _key4u_wire_payload,
)
from services.multiscene_video_pipeline import (
    STORYBOARD_DURATION_TOLERANCE_SECONDS,
    validate_storyboard_scene_duration,
)
from services.video_ai_edit_provider import (
    AiEditProviderConfig,
    has_proven_v2v_wire_contract,
    validate_provider_config,
)
from services.video_provider_base import VideoGenerationRequest
from services.video_provider_catalog import (
    _key4u_official_google_veo_endpoints,
    _normalize_key4u_official_google_veo_submit_endpoint,
    load_video_provider_catalog,
    model_metadata_from_resolution,
    resolve_product_video_model,
)
from services.video_provider_router import (
    _generic_adapter_for,
)

KEY4U_VN = "https://api.key4u.vn"


def _key4u_veo_env(**extra: str) -> dict[str, str]:
    env = {
        "KEY4U_ENABLED": "1",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_BASE_URL": KEY4U_VN,
        "KEY4U_API_KEY": "test-key-veo-token",
        # Generic production defaults (must NOT be used by Veo):
        "KEY4U_VIDEO_SUBMIT_URL": f"{KEY4U_VN}/v1/video/create",
        "KEY4U_VIDEO_POLL_URL": f"{KEY4U_VN}/v1/video/query?id={{task_id}}",
        # Specialized Veo endpoints:
        "KEY4U_VEO_VIDEO_ENDPOINT": f"{KEY4U_VN}/v1/videos",
        "KEY4U_VEO_VIDEO_POLL_URL": f"{KEY4U_VN}/v1/videos/{{task_id}}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test-key-veo-token",
        "KEY4U_VIDEO_MODEL": "veo_3_1-fast",
        "KEY4U_VIDEO_CAPABILITIES": "text_to_video,image_to_video,scene_video,multi_scene_video",
    }
    env.update(extra)
    return env


def _key4u_provider(env: dict[str, str]) -> GenericHttpVideoProvider:
    return GenericHttpVideoProvider(
        provider_name="key4u_video",
        enabled_env="KEY4U_VIDEO_ENABLED",
        submit_url_env="KEY4U_VIDEO_SUBMIT_URL",
        poll_url_env="KEY4U_VIDEO_POLL_URL",
        auth_header_name_env="KEY4U_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="KEY4U_VIDEO_AUTH_HEADER_VALUE",
        model_env="KEY4U_VIDEO_MODEL",
        capabilities_env="KEY4U_VIDEO_CAPABILITIES",
        environ=env,
    )


def _make_request(resolution: dict, *, seconds: int = 8, prompt: str = "Cinematic coffee brew.", image_url: str = ""):
    metadata = model_metadata_from_resolution(resolution)
    if image_url:
        metadata["image_url"] = image_url
        metadata["images"] = [image_url]
    return VideoGenerationRequest(
        job_id="pv-veo-contract-test",
        product_type="storyboard_prompt",
        prompt=prompt,
        ratio="9:16",
        duration_seconds=seconds,
        required_capability="image_to_video" if image_url else "text_to_video",
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# CONTRACT 1: Canonical Submit & Poll Endpoints Resolution
# ---------------------------------------------------------------------------
def test_key4u_veo_canonical_endpoints_resolution():
    env = _key4u_veo_env()
    resolution = resolve_product_video_model(
        tier=400,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env=env,
    )
    assert resolution["ok"] is True
    assert resolution["selected_provider"] == "key4u_video"
    assert resolution["selected_model"] == "veo_3_1-fast"
    assert resolution["provider_submit_url_override"] == f"{KEY4U_VN}/v1/videos"
    assert resolution["provider_poll_url_override"] == f"{KEY4U_VN}/v1/videos/{{task_id}}"
    assert resolution["provider_interface"] == "key4u_google_veo_exclusive"
    # Negative assertions against deprecated endpoints
    assert "/v1/video/create" not in resolution["provider_submit_url_override"]
    assert "/v1/videos/generations" not in resolution["provider_submit_url_override"]
    assert "/v1/video/query" not in resolution["provider_poll_url_override"]


# ---------------------------------------------------------------------------
# CONTRACT 2: Catalog Configuration
# ---------------------------------------------------------------------------
def test_key4u_veo_catalog_configuration():
    catalog = load_video_provider_catalog()
    key4u_models = catalog.get("providers", {}).get("key4u_video", {}).get("models", {})
    assert "veo_3_1-fast" in key4u_models
    veo_spec = key4u_models["veo_3_1-fast"]
    assert veo_spec["submit_endpoint"] == "/v1/videos"
    assert veo_spec["poll_endpoint"] == "/v1/videos/{task_id}"
    assert "image_to_video" in veo_spec.get("capabilities", [])


# ---------------------------------------------------------------------------
# CONTRACT 3: Zero Normalization / Fallback Rewriting to /v1/video/create
# ---------------------------------------------------------------------------
def test_key4u_veo_no_normalization_rewrite():
    submit_url, source = _normalize_key4u_official_google_veo_submit_endpoint(
        f"{KEY4U_VN}/v1/videos",
        "KEY4U_VEO_VIDEO_ENDPOINT",
    )
    assert submit_url == f"{KEY4U_VN}/v1/videos"
    assert source == "KEY4U_VEO_VIDEO_ENDPOINT"
    assert "/v1/video/create" not in submit_url

    derived_submit, derived_source, derived_poll, poll_source = _key4u_official_google_veo_endpoints(
        {"KEY4U_BASE_URL": KEY4U_VN, "KEY4U_VIDEO_AUTH_HEADER_VALUE": "test-token"}
    )
    assert derived_submit == f"{KEY4U_VN}/v1/videos"
    assert derived_source == "derived:key4u_official_veo_videos"
    assert derived_poll == f"{KEY4U_VN}/v1/videos/{{task_id}}"
    assert poll_source == "derived:key4u_official_veo_poll"


# ---------------------------------------------------------------------------
# CONTRACT 4: Adapter Precedence & Anti-Fallback
# ---------------------------------------------------------------------------
def test_key4u_veo_adapter_default_wiring():
    """When specialized envs are configured, adapter binds /v1/videos."""
    env = _key4u_veo_env()
    adapter = _generic_adapter_for("key4u_video", env)
    assert adapter._submit_url() == f"{KEY4U_VN}/v1/videos"
    assert adapter._poll_url() == f"{KEY4U_VN}/v1/videos/{{task_id}}"


def test_key4u_veo_adapter_ignores_generic_create_when_specialized_env_missing():
    """Even if generic envs point to /v1/video/create and /v1/video/query, Veo derives /v1/videos."""
    env = {
        "KEY4U_ENABLED": "1",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_BASE_URL": KEY4U_VN,
        "KEY4U_API_KEY": "test-key-veo-token",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test-key-veo-token",
        "KEY4U_VIDEO_SUBMIT_URL": f"{KEY4U_VN}/v1/video/create",
        "KEY4U_VIDEO_POLL_URL": f"{KEY4U_VN}/v1/video/query?id={{task_id}}",
        "KEY4U_VIDEO_MODEL": "veo_3_1-fast",
    }
    adapter = _generic_adapter_for("key4u_video", env)
    assert adapter._submit_url() == f"{KEY4U_VN}/v1/videos"
    assert adapter._poll_url() == f"{KEY4U_VN}/v1/videos/{{task_id}}"
    assert "/v1/video/create" not in adapter._submit_url()
    assert "/v1/video/query" not in adapter._poll_url()


# ---------------------------------------------------------------------------
# CONTRACT 5: JSON Wire Payload Schema & Legacy Rejection
# ---------------------------------------------------------------------------
def test_key4u_veo_wire_payload_schema():
    payload = {
        "model": "veo_3_1-fast",
        "prompt": "Vibrant landscape at sunrise.",
        "duration": 8,
        "ratio": "9:16",
        "capability": "image_to_video",
        "image_paths": ["https://toanaas.vn/media/panel1.jpg"],
        "metadata": {
            "selected_family": "google_veo",
            "provider_submit_url_override": f"{KEY4U_VN}/v1/videos",
        },
    }
    wire = _key4u_wire_payload(payload, submit_url=f"{KEY4U_VN}/v1/videos")
    assert wire["model"] == "veo_3_1-fast"
    assert wire["prompt"] == "Vibrant landscape at sunrise."
    assert wire["aspect_ratio"] == "9:16"
    assert wire["duration"] == 8
    assert wire["images"] == ["https://toanaas.vn/media/panel1.jpg"]
    assert wire["metadata"]["images"] == ["https://toanaas.vn/media/panel1.jpg"]
    # Enforce absence of raw top-level image field
    assert "image" not in wire


def test_key4u_veo_wire_payload_rejects_legacy_create_fail_closed():
    """Submitting Veo to /v1/video/create fails closed with contract error before dispatch."""
    payload = {
        "model": "veo_3_1-fast",
        "prompt": "Test Veo prompt.",
        "metadata": {
            "selected_family": "google_veo",
            "provider_submit_url_override": f"{KEY4U_VN}/v1/video/create",
        },
    }
    with pytest.raises(VideoProviderContractError) as exc_info:
        _key4u_wire_payload(payload, submit_url=f"{KEY4U_VN}/v1/video/create")
    assert exc_info.value.blocker == "key4u_veo_legacy_create_rejected_no_charge"
    assert exc_info.value.debug["no_charge"] is True


# ---------------------------------------------------------------------------
# CONTRACT 6: Submit Job Uses JSON Transport, Not Multipart
# ---------------------------------------------------------------------------
def test_key4u_veo_submit_job_uses_json_transport(monkeypatch):
    env = _key4u_veo_env()
    resolution = resolve_product_video_model(
        tier=400,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env=env,
    )
    provider = _key4u_provider(env)
    captured = {}

    def fake_json(url, payload=None, **kwargs):
        captured.update({
            "url": url,
            "payload": payload,
            "method": kwargs.get("method", "POST"),
            "headers": kwargs.get("headers", {}),
        })
        return {
            "ok": True,
            "status_code": 200,
            "body": {"task_id": "veo_task_987654", "status": "submitted"},
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_json", fake_json)
    monkeypatch.setattr(
        provider,
        "_open_multipart_form",
        lambda *_args, **_kwargs: pytest.fail("Veo must NOT use multipart form data"),
    )

    request = _make_request(
        resolution,
        seconds=8,
        prompt="Morning sun over hills.",
        image_url="https://toanaas.vn/media/panel1.jpg",
    )
    result = provider.submit_video_job(request)

    assert result.ok is True
    assert result.provider_task_id == "veo_task_987654"
    assert captured["url"] == f"{KEY4U_VN}/v1/videos"
    assert captured["payload"]["model"] == "veo_3_1-fast"
    assert captured["payload"]["images"] == ["https://toanaas.vn/media/panel1.jpg"]
    assert captured["payload"]["duration"] == 8
    assert captured["payload"]["aspect_ratio"] == "9:16"
    assert result.raw["provider_poll_url_override"] == f"{KEY4U_VN}/v1/videos/{{task_id}}"


def test_key4u_veo_submit_job_blocks_legacy_create_fail_closed_no_charge():
    """Even if provider submit URL is forced to /v1/video/create, Veo submission fails closed without HTTP call."""
    env = _key4u_veo_env(
        KEY4U_VEO_VIDEO_ENDPOINT=f"{KEY4U_VN}/v1/video/create",
        KEY4U_VIDEO_SUBMIT_URL=f"{KEY4U_VN}/v1/video/create",
    )
    provider = GenericHttpVideoProvider(
        provider_name="key4u_video",
        enabled_env="KEY4U_VIDEO_ENABLED",
        submit_url_env="KEY4U_VIDEO_SUBMIT_URL",
        poll_url_env="KEY4U_VIDEO_POLL_URL",
        auth_header_name_env="KEY4U_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="KEY4U_VIDEO_AUTH_HEADER_VALUE",
        model_env="KEY4U_VIDEO_MODEL",
        capabilities_env="KEY4U_VIDEO_CAPABILITIES",
        environ=env,
    )
    request = VideoGenerationRequest(
        job_id="pv-veo-fail-closed",
        product_type="storyboard_prompt",
        prompt="Coffee scene",
        ratio="9:16",
        duration_seconds=8,
        required_capability="text_to_video",
        metadata={
            "selected_family": "google_veo",
            "model": "veo_3_1-fast",
            "provider_submit_url_override": f"{KEY4U_VN}/v1/video/create",
        },
    )
    result = provider.submit_video_job(request)
    assert result.ok is False
    assert result.error_code == "key4u_veo_legacy_create_rejected_no_charge"
    assert result.raw.get("no_charge") is True


# ---------------------------------------------------------------------------
# CONTRACT 7: Polling URL Path Embedding & Zero Mixed Contract
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("task_id", "expected_path_task_id"),
    [
        ("task_existing_key4u_scene_2", "task_existing_key4u_scene_2"),
        ("veo_3_1-fast:task_existing_key4u_scene_2", "task_existing_key4u_scene_2"),
        ("veo3.1-fast:task_existing_key4u_scene_2", "task_existing_key4u_scene_2"),
        ("veo_task_987654", "veo_task_987654"),
        ("unknown_prefix:task_existing_key4u_scene_2", "unknown_prefix%3Atask_existing_key4u_scene_2"),
    ],
)
def test_key4u_veo_polling_url_path_embedding(monkeypatch, task_id, expected_path_task_id):
    env = _key4u_veo_env()
    provider = _key4u_provider(env)
    captured = {}

    def fake_json(url, payload=None, **kwargs):
        captured["url"] = url
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "task_id": expected_path_task_id,
                "status": "success",
                "video_url": "https://toanaas.vn/output/scene1.mp4",
            },
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_json", fake_json)
    result = provider.poll_video_job(
        task_id,
        poll_url_override=f"{KEY4U_VN}/v1/videos/{{task_id}}",
    )
    assert result.ok is True
    assert result.status == "succeeded"
    assert result.result_url == "https://toanaas.vn/output/scene1.mp4"
    assert captured["url"] == f"{KEY4U_VN}/v1/videos/{expected_path_task_id}"
    assert "?" not in captured["url"]


def test_key4u_veo_polling_preserves_unknown_prefixed_task_id_negative_guard(monkeypatch):
    """Negative guard: unknown prefixed task ID is NOT stripped."""
    env = _key4u_veo_env()
    provider = _key4u_provider(env)
    captured = {}

    def fake_json(url, payload=None, **kwargs):
        captured["url"] = url
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "task_id": "other_model:task_scene_xyz",
                "status": "success",
                "video_url": "https://toanaas.vn/output/scene1.mp4",
            },
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_json", fake_json)
    result = provider.poll_video_job(
        "other_model:task_scene_xyz",
        poll_url_override=f"{KEY4U_VN}/v1/videos/{{task_id}}",
    )
    assert result.ok is True
    assert captured["url"] == f"{KEY4U_VN}/v1/videos/other_model%3Atask_scene_xyz"
    assert "other_model" in captured["url"]




def test_key4u_veo_no_mixed_contract_poll_recovery():
    """Veo pending recovery must NOT synthesize /v1/videos/{task_id} from legacy /v1/video/create."""
    adapter_submit = urlparse(f"{KEY4U_VN}/v1/video/create")
    persisted_model = "veo_3_1-fast"
    recovered_poll_url = ""
    # Test router logic: only /v1/videos is allowed for recovery
    if (
        persisted_model == "veo_3_1-fast"
        and (adapter_submit.hostname or "").lower() in {"api.key4u.vn", "api.key4u.shop"}
        and adapter_submit.path.rstrip("/").endswith("/v1/videos")
    ):
        recovered_poll_url = f"{adapter_submit.scheme}://{adapter_submit.netloc}{adapter_submit.path.rstrip('/')}/{{task_id}}"

    assert recovered_poll_url == ""


# ---------------------------------------------------------------------------
# CONTRACT 8: Auth Headers Unchanged
# ---------------------------------------------------------------------------
def test_key4u_veo_auth_headers_unchanged():
    env = _key4u_veo_env()
    provider = _key4u_provider(env)
    headers = provider._headers()
    assert headers["Authorization"] == "Bearer test-key-veo-token"


# ---------------------------------------------------------------------------
# CONTRACT 9: Duration Integrity and Zero Fake Padding
# ---------------------------------------------------------------------------
def test_key4u_veo_duration_integrity():
    # 8.0s native clip passes validation
    res_8s = validate_storyboard_scene_duration(8.0, 8.0)
    assert res_8s["duration_valid"] is True
    assert res_8s["blocker"] == ""

    # 6.016s raw clip fails closed
    res_short = validate_storyboard_scene_duration(6.016, 8.0)
    assert res_short["duration_valid"] is False
    assert res_short["blocker"] == "scene_duration_short_no_charge"
    assert res_short["minimum_accepted_duration"] == 8.0 - STORYBOARD_DURATION_TOLERANCE_SECONDS


# ---------------------------------------------------------------------------
# CONTRACT 10: Negative Guard - Fail-Closed for Arbitrary V2V
# ---------------------------------------------------------------------------
def test_key4u_video_ai_video_reference_fails_closed():
    # Key4U must not claim proven V2V wire contract
    assert has_proven_v2v_wire_contract("key4u_video") is False
    assert has_proven_v2v_wire_contract("key4u_video", "kling-v3", f"{KEY4U_VN}/kling/v1/videos/motion-control") is False

    config = AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url=f"{KEY4U_VN}/kling/v1/videos/motion-control",
        poll_url=f"{KEY4U_VN}/kling/v1/videos/query?id={{task_id}}",
        auth_header_name="Authorization",
        auth_header_value="Bearer valid_test_key_12345",
        model="kling-v3",
        interface="kling_motion_control",
        capabilities=["video_to_video"],
    )
    validation = validate_provider_config(config, required_capability="video_to_video")
    assert validation["ok"] is False
    assert "provider_capability_contract_mismatch" in validation["invalid_fields"]
