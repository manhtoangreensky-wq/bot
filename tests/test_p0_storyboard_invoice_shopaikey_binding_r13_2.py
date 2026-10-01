"""Tests for Storyboard invoice and asset pack binding to ShopAIKey Veo 3.1 Fast and Key4U Kling (R13.2).

Scope: P0.PRODUCT_VIDEO
Tracking Issue: #1155
Verification:
1. Default Storyboard invoice and asset_pack binds to shopaikey_video / veo3.1-fast / google_veo.
2. Explicit shopaikey_video selection binds to shopaikey_video / veo3.1-fast / google_veo.
3. Explicit key4u_video selection binds to key4u_video / kling-v3 / kling.
4. Explicit kling-3.0-turbo model selection binds to key4u_video / kling-3.0-turbo / kling.
5. Explicit veo3.1-fast model selection binds to shopaikey_video / veo3.1-fast / google_veo.
6. Unproven model on shopaikey_video fails closed with zero charge.
7. Unproven model on key4u_video fails closed with zero charge.
8. Unknown model fails closed with zero charge.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

import bot
from services.video_real_render_connector import (
    RealVideoRenderError,
    STORYBOARD_DEFAULT_I2V_MODEL_BY_PROVIDER,
    STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER,
    STORYBOARD_PROVEN_I2V_MODELS_BY_PROVIDER,
)


@pytest.fixture
def sample_panels(tmp_path):
    """Create two valid dummy PNG panel image files on disk."""
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
    user_id: int = 8801,
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


def test_storyboard_invoice_defaults_to_shopaikey_veo31_fast(sample_panels):
    """When neither provider nor model is explicitly chosen, invoice and asset_pack default to shopaikey_video / veo3.1-fast."""
    user_id = 8801
    session = _make_session(sample_panels, user_id=user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)

    asset_pack = json.loads(project["asset_pack_json"]) if isinstance(project["asset_pack_json"], str) else project["asset_pack_json"]
    invoice = json.loads(project["invoice_json"]) if isinstance(project["invoice_json"], str) else project["invoice_json"]

    # Asset pack assertions
    assert asset_pack["selected_provider"] == "shopaikey_video"
    assert asset_pack["provider_order"] == "shopaikey_video"
    assert asset_pack["provider_chain"] == ["shopaikey_video"]
    assert asset_pack["model"] == "veo3.1-fast"
    assert asset_pack["selected_model"] == "veo3.1-fast"
    assert asset_pack["pinned_wire_model"] == "veo3.1-fast"
    assert asset_pack["selected_family"] == "google_veo"

    # Invoice assertions
    assert invoice["selected_provider"] == "shopaikey_video"
    assert invoice["provider_order"] == "shopaikey_video"
    assert invoice["provider_chain"] == ["shopaikey_video"]
    assert invoice["model"] == "veo3.1-fast"
    assert invoice["selected_model"] == "veo3.1-fast"
    assert invoice["pinned_wire_model"] == "veo3.1-fast"
    assert invoice["selected_family"] == "google_veo"
    assert invoice["orchestration_mode"] == "per_scene_8s"
    assert invoice["required_capability"] == "image_to_video"


def test_storyboard_invoice_explicit_shopaikey_provider(sample_panels):
    """Explicitly selecting shopaikey_video binds to veo3.1-fast and google_veo."""
    user_id = 8802
    session = _make_session(sample_panels, selected_provider="shopaikey_video", user_id=user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)

    asset_pack = json.loads(project["asset_pack_json"])
    invoice = json.loads(project["invoice_json"])

    assert asset_pack["selected_provider"] == "shopaikey_video"
    assert asset_pack["model"] == "veo3.1-fast"
    assert asset_pack["selected_family"] == "google_veo"

    assert invoice["selected_provider"] == "shopaikey_video"
    assert invoice["model"] == "veo3.1-fast"
    assert invoice["selected_family"] == "google_veo"


def test_storyboard_invoice_explicit_key4u_provider_backward_compat(sample_panels):
    """Explicitly selecting key4u_video binds to kling-v3 and kling."""
    user_id = 8803
    session = _make_session(sample_panels, selected_provider="key4u_video", user_id=user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)

    asset_pack = json.loads(project["asset_pack_json"])
    invoice = json.loads(project["invoice_json"])

    assert asset_pack["selected_provider"] == "key4u_video"
    assert asset_pack["provider_order"] == "key4u_video"
    assert asset_pack["provider_chain"] == ["key4u_video"]
    assert asset_pack["model"] == "kling-v3"
    assert asset_pack["selected_family"] == "kling"

    assert invoice["selected_provider"] == "key4u_video"
    assert invoice["provider_order"] == "key4u_video"
    assert invoice["provider_chain"] == ["key4u_video"]
    assert invoice["model"] == "kling-v3"
    assert invoice["selected_family"] == "kling"


def test_storyboard_invoice_explicit_kling_model_resolves_key4u(sample_panels):
    """Requesting kling-3.0-turbo resolves provider to key4u_video and family to kling."""
    user_id = 8804
    session = _make_session(sample_panels, selected_model="kling-3.0-turbo", user_id=user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)

    asset_pack = json.loads(project["asset_pack_json"])
    invoice = json.loads(project["invoice_json"])

    assert asset_pack["selected_provider"] == "key4u_video"
    assert asset_pack["model"] == "kling-3.0-turbo"
    assert asset_pack["selected_model"] == "kling-3.0-turbo"
    assert asset_pack["selected_family"] == "kling"

    assert invoice["selected_provider"] == "key4u_video"
    assert invoice["model"] == "kling-3.0-turbo"
    assert invoice["selected_model"] == "kling-3.0-turbo"
    assert invoice["selected_family"] == "kling"


def test_storyboard_invoice_explicit_veo_model_resolves_shopaikey(sample_panels):
    """Requesting veo3.1-fast resolves provider to shopaikey_video and family to google_veo."""
    user_id = 8805
    session = _make_session(sample_panels, selected_model="veo3.1-fast", user_id=user_id)
    project = bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)

    asset_pack = json.loads(project["asset_pack_json"])
    invoice = json.loads(project["invoice_json"])

    assert asset_pack["selected_provider"] == "shopaikey_video"
    assert asset_pack["model"] == "veo3.1-fast"
    assert asset_pack["selected_family"] == "google_veo"

    assert invoice["selected_provider"] == "shopaikey_video"
    assert invoice["model"] == "veo3.1-fast"
    assert invoice["selected_family"] == "google_veo"


def test_storyboard_invoice_unproven_model_shopaikey_fails_closed(sample_panels):
    """Requesting a model not allowed on shopaikey_video fails closed with zero charge."""
    user_id = 8806
    session = _make_session(sample_panels, selected_provider="shopaikey_video", selected_model="kling-v3", user_id=user_id)
    with pytest.raises(RealVideoRenderError) as exc_info:
        bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)
    assert exc_info.value.args[0] == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    diag = exc_info.value.diagnostics
    assert diag.get("no_charge") is True
    assert diag.get("provider") == "shopaikey_video"
    assert diag.get("model") == "kling-v3"


def test_storyboard_invoice_unproven_model_key4u_fails_closed(sample_panels):
    """Requesting a model not allowed on key4u_video fails closed with zero charge."""
    user_id = 8807
    session = _make_session(sample_panels, selected_provider="key4u_video", selected_model="veo3.1-fast", user_id=user_id)
    with pytest.raises(RealVideoRenderError) as exc_info:
        bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)
    assert exc_info.value.args[0] == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    diag = exc_info.value.diagnostics
    assert diag.get("no_charge") is True
    assert diag.get("provider") == "key4u_video"
    assert diag.get("model") == "veo3.1-fast"


def test_storyboard_invoice_unknown_model_fails_closed(sample_panels):
    """Requesting completely unknown model fails closed with zero charge."""
    user_id = 8808
    session = _make_session(sample_panels, selected_model="random-diffusion-xyz", user_id=user_id)
    with pytest.raises(RealVideoRenderError) as exc_info:
        bot.video_b14_prepare_project_for_invoice(user_id=user_id, session=session)
    assert exc_info.value.args[0] == STORYBOARD_I2V_MODEL_NOT_PROVEN_BLOCKER
    diag = exc_info.value.diagnostics
    assert diag.get("no_charge") is True
    assert diag.get("model") == "random-diffusion-xyz"
