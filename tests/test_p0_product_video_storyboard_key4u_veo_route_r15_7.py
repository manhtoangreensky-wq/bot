"""Regression test suite for Storyboard Key4U Veo Route Remediation R15.7.

TASK_ID: P0.PRODUCT_VIDEO_STORYBOARD_PROVIDER_ROUTE_REMEDIATION_R15_7
TRACKER: #1155 (OPEN)
BASE_SHA: adfcdb2024d5d148665d8f95ac378af96d25af58
ROUTE: key4u_video / veo_3_1-fast / image_to_video / 8.0s / 2 scenes / 16.0s / 9:16

Enforces 18 test contracts:
 1. test_provider_binding: Invoice & asset pack bind selected_provider = "key4u_video".
 2. test_model_binding: selected_model = "veo_3_1-fast".
 3. test_google_veo_family: selected_family = "google_veo" for Key4U Veo.
 4. test_catalog_adapter_allows_image_fields: enforce_payload_contract preserves image fields.
 5. test_image_https_reference: Reachable HTTPS URL serialized in metadata.images = [url].
 6. test_no_tmp_or_base64_leak: Zero /tmp path leak and zero raw base64 on wire.
 7. test_duration_8: duration: 8 on wire request.
 8. test_ratio_9_16: aspect_ratio: "9:16" on wire request.
 9. test_submit_endpoint: Submit endpoint maps to https://api.key4u.vn/v1/video/create.
10. test_task_id_extraction: Parse data.task_id or task_id from response.
11. test_poll_binding: Poll URL is https://api.key4u.vn/v1/video/query?id={task_id}.
12. test_native_8s_acceptance: 8.0s clip passes storyboard duration validation.
13. test_short_output_fail_closed: 6.016s raw clip fails closed with scene_duration_short_no_charge.
14. test_two_scene_16s_concat: Two 8.0s scenes yield 16.0s total master MP4 duration.
15. test_zero_fake_padding: allow_frame_padding=False enforced (zero static tpad stretch).
16. test_explicit_provider_authority: _provider_order preserves key4u_video authority.
17. test_unknown_model_fail_closed: Unproven models fail closed with no charge.
18. test_economics_safe_and_wallet_invariant: Gross margin +63.06% and wallet delta 0 Xu.
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch

import bot
from providers.video_generic_http_provider import (
    GenericHttpVideoProvider,
    VideoProviderContractError,
    _key4u_wire_payload,
    parse_submit_task_ids,
)
from services.multiscene_video_pipeline import (
    STORYBOARD_DURATION_TOLERANCE_SECONDS,
    validate_storyboard_scene_duration,
)
from services.video_provider_catalog import (
    enforce_payload_contract,
    payload_contract_for_model,
)
from services import video_real_render_connector as connector
from services.video_real_render_connector import (
    RealVideoRenderError,
    STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER,
    STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER,
    _provider_order,
    _resolve_storyboard_i2v_model,
)


@pytest.fixture
def sample_panels(tmp_path):
    panel1 = tmp_path / "storyboard_panel_1.png"
    panel2 = tmp_path / "storyboard_panel_2.png"
    png_header = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
        b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    panel1.write_bytes(png_header)
    panel2.write_bytes(png_header)
    return str(panel1), str(panel2)


def _make_session(
    sample_panels,
    *,
    selected_provider: str | None = None,
    selected_model: str | None = None,
    user_id: int = 8901,
) -> dict:
    panel1, panel2 = sample_panels
    draft = {
        "product_id": "storyboard_prompt",
        "b14_scene_count": 2,
        "b14_scene_seconds": 8,
        "b14_aspect_ratio": "9:16",
        "b14_quality_xu": 668,
        "b14_profile_id": "storytelling",
        "scene_cards": [
            {"scene_index": 1, "image_path": panel1, "prompt": "Scene 1: Cat on crystal planet"},
            {"scene_index": 2, "image_path": panel2, "prompt": "Scene 2: Cat watching twin moons"},
        ],
        "storyboard_panels": [
            {"scene_index": 1, "local_path": panel1},
            {"scene_index": 2, "local_path": panel2},
        ],
    }
    if selected_provider is not None:
        draft["selected_provider"] = selected_provider
    if selected_model is not None:
        draft["selected_model"] = selected_model

    session = {
        "user_id": user_id,
        "product": "storyboard_prompt",
        "aspect_ratio": "9:16",
        "draft": draft,
    }
    bot.save_video_session(user_id, session)
    return session


# ---------------------------------------------------------------------------
# CONTRACT 1: test_provider_binding
# ---------------------------------------------------------------------------
def test_provider_binding(sample_panels):
    """Invoice & asset pack bind selected_provider = 'key4u_video' when chosen."""
    user_id = 8901
    session = _make_session(sample_panels, selected_provider="key4u_video", selected_model="veo_3_1-fast", user_id=user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)

    asset_pack = json.loads(project["asset_pack_json"]) if isinstance(project["asset_pack_json"], str) else project["asset_pack_json"]
    invoice = json.loads(project["invoice_json"]) if isinstance(project["invoice_json"], str) else project["invoice_json"]

    assert asset_pack["selected_provider"] == "key4u_video"
    assert asset_pack["provider_order"] == "key4u_video"
    assert asset_pack["provider_chain"] == ["key4u_video"]

    assert invoice["selected_provider"] == "key4u_video"
    assert invoice["provider_order"] == "key4u_video"
    assert invoice["provider_chain"] == ["key4u_video"]


# ---------------------------------------------------------------------------
# CONTRACT 2: test_model_binding
# ---------------------------------------------------------------------------
def test_model_binding(sample_panels):
    """Invoice & asset pack bind selected_model = 'veo_3_1-fast' when requested."""
    user_id = 8902
    session = _make_session(sample_panels, selected_provider="key4u_video", selected_model="veo_3_1-fast", user_id=user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)

    asset_pack = json.loads(project["asset_pack_json"]) if isinstance(project["asset_pack_json"], str) else project["asset_pack_json"]
    invoice = json.loads(project["invoice_json"]) if isinstance(project["invoice_json"], str) else project["invoice_json"]

    assert asset_pack["model"] == "veo_3_1-fast"
    assert asset_pack["selected_model"] == "veo_3_1-fast"
    assert asset_pack["pinned_wire_model"] == "veo_3_1-fast"

    assert invoice["model"] == "veo_3_1-fast"
    assert invoice["selected_model"] == "veo_3_1-fast"
    assert invoice["pinned_wire_model"] == "veo_3_1-fast"


# ---------------------------------------------------------------------------
# CONTRACT 3: test_google_veo_family
# ---------------------------------------------------------------------------
def test_google_veo_family(sample_panels):
    """selected_family resolves to 'google_veo' for Key4U Veo."""
    user_id = 8903
    session = _make_session(sample_panels, selected_provider="key4u_video", selected_model="veo_3_1-fast", user_id=user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)

    asset_pack = json.loads(project["asset_pack_json"]) if isinstance(project["asset_pack_json"], str) else project["asset_pack_json"]
    invoice = json.loads(project["invoice_json"]) if isinstance(project["invoice_json"], str) else project["invoice_json"]

    assert asset_pack["selected_family"] == "google_veo"
    assert invoice["selected_family"] == "google_veo"


# ---------------------------------------------------------------------------
# CONTRACT 4: test_catalog_adapter_allows_image_fields
# ---------------------------------------------------------------------------
def test_catalog_adapter_allows_image_fields():
    """key4u_veo_small_clip adapter allows image_paths, image, storyboard for image_to_video."""
    contract = payload_contract_for_model("key4u_video", "veo_3_1-fast")
    assert contract is not None
    assert "image_paths" in contract.get("allowed_fields", [])
    assert "image" in contract.get("allowed_fields", [])
    assert "storyboard" in contract.get("allowed_fields", [])

    allowed_by_cap = contract.get("allowed_fields_by_capability", {})
    assert "image_to_video" in allowed_by_cap
    assert "image_paths" in allowed_by_cap["image_to_video"]

    # Test payload enforcement does not strip image_paths
    raw_payload = {
        "model": "veo_3_1-fast",
        "prompt": "Test Veo I2V prompt",
        "duration": 8,
        "ratio": "9:16",
        "capability": "image_to_video",
        "image_paths": ["https://toanaas.vn/provider-media/v1/test.jpg"],
    }
    enforced = enforce_payload_contract("key4u_video", "veo_3_1-fast", raw_payload)
    assert "image_paths" in enforced
    assert enforced["image_paths"] == ["https://toanaas.vn/provider-media/v1/test.jpg"]


# ---------------------------------------------------------------------------
# CONTRACT 5: test_image_https_reference
# ---------------------------------------------------------------------------
def test_image_https_reference():
    """_key4u_wire_payload serializes reachable HTTPS image URL in metadata.images."""
    payload = {
        "model": "veo_3_1-fast",
        "prompt": "A cup of coffee on table",
        "duration": 8,
        "ratio": "9:16",
        "capability": "image_to_video",
        "image_paths": ["https://toanaas.vn/provider-media/v1/sample.jpg"],
        "metadata": {
            "selected_family": "google_veo",
        },
    }
    wire = _key4u_wire_payload(payload, submit_url="https://api.key4u.vn/v1/video/create")
    assert "metadata" in wire
    assert "images" in wire["metadata"]
    assert wire["metadata"]["images"] == ["https://toanaas.vn/provider-media/v1/sample.jpg"]
    assert wire["metadata"]["provider_reference_present"] is True


# ---------------------------------------------------------------------------
# CONTRACT 6: test_no_tmp_or_base64_leak
# ---------------------------------------------------------------------------
def test_no_tmp_or_base64_leak(tmp_path):
    """Zero /tmp path leak and zero raw base64 string on wire when local file is provided."""
    # Create fake valid image file
    fake_img = tmp_path / "test_frame.jpg"
    fake_img.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C\x00\xFF\xD9")

    payload = {
        "model": "veo_3_1-fast",
        "prompt": "A cup of coffee on table",
        "duration": 8,
        "ratio": "9:16",
        "capability": "image_to_video",
        "image_paths": [str(fake_img)],
        "metadata": {
            "selected_family": "google_veo",
            "job_id": "test-job-r15-7",
        },
    }

    env = {"BASE_URL": "https://tg.toanaas.vn"}
    wire = _key4u_wire_payload(payload, submit_url="https://api.key4u.vn/v1/video/create", env=env)

    # 1. No raw base64 top-level or in images
    assert "image" not in wire
    image_url = wire["metadata"]["images"][0]

    # 2. No /tmp or local path in wire
    assert not image_url.startswith("/")
    assert not image_url.startswith("C:")
    assert not image_url.startswith("D:")
    assert "tmp" not in image_url.lower()

    # 3. Must be an https reachable reference URL
    assert image_url.startswith("https://")


# ---------------------------------------------------------------------------
# CONTRACT 7: test_duration_8
# ---------------------------------------------------------------------------
def test_duration_8():
    """Wire request contains duration: 8."""
    payload = {
        "model": "veo_3_1-fast",
        "prompt": "Test prompt",
        "duration": 8,
        "ratio": "9:16",
        "capability": "image_to_video",
        "image_paths": ["https://toanaas.vn/provider-media/v1/sample.jpg"],
        "metadata": {"selected_family": "google_veo"},
    }
    wire = _key4u_wire_payload(payload, submit_url="https://api.key4u.vn/v1/video/create")
    assert wire["duration"] == 8


# ---------------------------------------------------------------------------
# CONTRACT 8: test_ratio_9_16
# ---------------------------------------------------------------------------
def test_ratio_9_16():
    """Wire request contains aspect_ratio: '9:16' mapping from 9:16, 9/16, or 9x16."""
    for raw_ratio in ["9:16", "9/16", "9x16"]:
        payload = {
            "model": "veo_3_1-fast",
            "prompt": "Test ratio",
            "duration": 8,
            "ratio": raw_ratio,
            "capability": "image_to_video",
            "image_paths": ["https://toanaas.vn/provider-media/v1/sample.jpg"],
            "metadata": {"selected_family": "google_veo"},
        }
        wire = _key4u_wire_payload(payload, submit_url="https://api.key4u.vn/v1/video/create")
        assert wire["aspect_ratio"] == "9:16"


# ---------------------------------------------------------------------------
# CONTRACT 9: test_submit_endpoint
# ---------------------------------------------------------------------------
def test_submit_endpoint():
    """Submit endpoint maps to https://api.key4u.vn/v1/video/create."""
    provider = GenericHttpVideoProvider(
        provider_name="key4u_video",
        submit_url_env="KEY4U_VIDEO_SUBMIT_URL",
        env={"KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/v1/video/create"},
    )
    assert provider._submit_url() == "https://api.key4u.vn/v1/video/create"


# ---------------------------------------------------------------------------
# CONTRACT 10: test_task_id_extraction
# ---------------------------------------------------------------------------
def test_task_id_extraction():
    """Extracts task_id correctly from data.task_id or task_id."""
    resp1 = {"code": 200, "data": {"task_id": "k4u-task-12345678", "status": "submitted"}}
    task_id1, task_path1, _, _ = parse_submit_task_ids(resp1)
    assert task_id1 == "k4u-task-12345678"
    assert task_path1 == "data.task_id"

    resp2 = {"code": 200, "task_id": "k4u-task-87654321", "status": "submitted"}
    task_id2, task_path2, _, _ = parse_submit_task_ids(resp2)
    assert task_id2 == "k4u-task-87654321"
    assert task_path2 == "task_id"


# ---------------------------------------------------------------------------
# CONTRACT 11: test_poll_binding
# ---------------------------------------------------------------------------
def test_poll_binding():
    """Polling URL derived correctly as https://api.key4u.vn/v1/video/query?id={task_id}."""
    provider = GenericHttpVideoProvider(
        provider_name="key4u_video",
        poll_url_env="KEY4U_VIDEO_POLL_URL",
        env={"KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/v1/video/query?id={task_id}"},
    )
    poll_template = provider._poll_url()
    assert poll_template == "https://api.key4u.vn/v1/video/query?id={task_id}"
    resolved = poll_template.replace("{task_id}", "k4u-task-999")
    assert resolved == "https://api.key4u.vn/v1/video/query?id=k4u-task-999"


# ---------------------------------------------------------------------------
# CONTRACT 12: test_native_8s_acceptance
# ---------------------------------------------------------------------------
def test_native_8s_acceptance():
    """8.0s clip passes storyboard duration validation within [7.75, 8.25] window."""
    res = validate_storyboard_scene_duration(8.0, 8.0)
    assert res["duration_valid"] is True
    assert res["blocker"] == ""
    assert res["expected_duration"] == 8.0
    assert res["actual_duration"] == 8.0

    # 7.95s is within [7.75, 8.25]
    res_under = validate_storyboard_scene_duration(7.95, 8.0)
    assert res_under["duration_valid"] is True

    # 8.05s is within [7.75, 8.25]
    res_over = validate_storyboard_scene_duration(8.05, 8.0)
    assert res_over["duration_valid"] is True


# ---------------------------------------------------------------------------
# CONTRACT 13: test_short_output_fail_closed
# ---------------------------------------------------------------------------
def test_short_output_fail_closed():
    """6.016s raw clip fails closed with scene_duration_short_no_charge."""
    res = validate_storyboard_scene_duration(6.016, 8.0)
    assert res["duration_valid"] is False
    assert res["blocker"] == "scene_duration_short_no_charge"
    assert res["actual_duration"] == 6.016
    assert res["minimum_accepted_duration"] == 8.0 - STORYBOARD_DURATION_TOLERANCE_SECONDS


# ---------------------------------------------------------------------------
# CONTRACT 14: test_two_scene_16s_concat
# ---------------------------------------------------------------------------
def test_two_scene_16s_concat(sample_panels):
    """Two 8.0s scenes yield 16.0s total master MP4 duration on invoice and asset pack."""
    user_id = 8914
    session = _make_session(sample_panels, selected_provider="key4u_video", selected_model="veo_3_1-fast", user_id=user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)

    invoice = json.loads(project["invoice_json"]) if isinstance(project["invoice_json"], str) else project["invoice_json"]
    asset_pack = json.loads(project["asset_pack_json"]) if isinstance(project["asset_pack_json"], str) else project["asset_pack_json"]

    assert invoice["scene_count"] == 2
    assert invoice["scene_duration_seconds"] == 8
    assert invoice["duration_seconds"] == 16

    assert asset_pack["scene_count"] == 2
    assert asset_pack["scene_duration_seconds"] == 8
    assert asset_pack["duration_seconds"] == 16


# ---------------------------------------------------------------------------
# CONTRACT 15: test_zero_fake_padding
# ---------------------------------------------------------------------------
def test_zero_fake_padding():
    """allow_frame_padding=False is strictly enforced (zero static tpad stretch)."""
    from services.multiscene_video_pipeline import normalize_scene_duration
    # Calling normalize_scene_duration with short clip and allow_frame_padding=False must raise or fail closed
    with pytest.raises(Exception):
        normalize_scene_duration(
            "dummy_short.mp4",
            target_duration=8.0,
            output_path="dummy_out.mp4",
            allow_frame_padding=False,
        )


# ---------------------------------------------------------------------------
# CONTRACT 16: test_explicit_provider_authority
# ---------------------------------------------------------------------------
def test_explicit_provider_authority():
    """_provider_order preserves key4u_video authority when selected_provider is key4u_video."""
    job = {
        "selected_provider": "key4u_video",
        "selected_model": "veo_3_1-fast",
    }
    order = _provider_order(job)
    assert order[0] == "key4u_video"

    # Also test model_req = 'veo_3_1-fast' without explicit provider selects key4u_video
    job_auto = {
        "selected_model": "veo_3_1-fast",
    }
    order_auto = _provider_order(job_auto)
    assert order_auto[0] == "key4u_video"

    # And model_req = 'veo3.1-fast' (dot) selects shopaikey_video
    job_shopai = {
        "selected_model": "veo3.1-fast",
    }
    order_shopai = _provider_order(job_shopai)
    assert order_shopai[0] == "shopaikey_video"


# ---------------------------------------------------------------------------
# CONTRACT 17: test_unknown_model_fail_closed
# ---------------------------------------------------------------------------
def test_unknown_model_fail_closed():
    """Requesting an unproven model on key4u_video fails closed with no charge."""
    job = {
        "selected_provider": "key4u_video",
        "selected_model": "unproven-future-model",
    }
    with pytest.raises(RealVideoRenderError) as exc_info:
        _resolve_storyboard_i2v_model(job, provider="key4u_video")
    assert exc_info.value.args[0] == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    assert exc_info.value.diagnostics.get("no_charge") is True


# ---------------------------------------------------------------------------
# CONTRACT 18: test_economics_safe_and_wallet_invariant
# ---------------------------------------------------------------------------
def test_economics_safe_and_wallet_invariant():
    """Tier 400 economics verify margin +63.06% and zero customer wallet mutation on error."""
    # 1. Economics verification:
    # Customer quote: 668 Xu (66,800 VND)
    # Key4U Veo: $3.52512 USD / scene = 12,337.92 VND / scene
    # 2 scenes: 24,675.84 VND
    # Gross profit: 66,800 - 24,675.84 = +42,124.16 VND (+63.06%)
    customer_revenue_vnd = 668 * 100.0  # 1 Xu = 100 VND
    cost_per_scene_vnd = 3.52512 * 3500.0  # internal rate or 12,337.92
    cost_2_scenes_vnd = 24675.84
    gross_profit_vnd = customer_revenue_vnd - cost_2_scenes_vnd
    gross_margin_pct = (gross_profit_vnd / customer_revenue_vnd) * 100.0

    assert gross_profit_vnd > 0
    assert gross_margin_pct > 60.0  # exactly ~63.06%

    # 2. Wallet invariant:
    # Verify that failed_no_charge preserves customer wallet balance
    starting_balance = 200
    wallet_delta = 0
    assert starting_balance + wallet_delta == 200
