"""A generic scene plan must not turn an explicitly selected product into Storyboard."""

from copy import deepcopy
import json
import sqlite3

import pytest

import bot
from services import video_project_queue as queue


@pytest.fixture
def isolated_session(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    state = {}

    class Connection:
        def close(self):
            pass

        def __getattr__(self, name):
            return getattr(conn, name)

    monkeypatch.setattr(bot, "db_connect", lambda: Connection())
    monkeypatch.setattr(bot, "get_video_session", lambda _uid: deepcopy(state))
    monkeypatch.setattr(bot, "save_video_session", lambda _uid, value: state.update(deepcopy(value)))
    monkeypatch.setattr(bot, "video_b14_is_admin_or_owner", lambda _uid: False)
    yield state, conn
    conn.close()


def session_for(product, *, tier=800, flow_kind=""):
    state = {
        "topic": "Two distinct approved scenes",
        "flow_kind": flow_kind,
        "draft": {
            "b14_profile_id": "storytelling",
            "b14_quality_xu": tier,
            "b14_scene_count": 2,
            "b14_scene_seconds": 8,
            "b14_aspect_ratio": "9:16",
            "b14_storyboard_plan": {
                "preview_text": "Scene one then scene two",
                "scene_count": 2,
                "aspect_ratio": "9:16",
                "scenes": [
                    {"scene_id": f"s{i}", "scene_index": i, "target_duration_sec": 8, "visual_prompt": f"Scene {i}"}
                    for i in (1, 2)
                ],
            },
            "asset_pack": {"product_type": product} if product else {},
        },
    }
    if product:
        state["product_id"] = product
    return state


@pytest.mark.parametrize("product", ("video_trend", "video_ai_prompt"))
@pytest.mark.parametrize("flow_kind", ("", "storyboard"))
def test_explicit_non_storyboard_keeps_project_identity_and_generic_price(isolated_session, product, flow_kind):
    stored, conn = isolated_session
    session = session_for(product, flow_kind=flow_kind)
    stored.update(deepcopy(session))
    invoice = bot.video_b14_invoice_for_session(session, 901)
    assert invoice["quality_xu"] == 2143
    project = bot.video_b14_prepare_project_for_invoice(901, session)
    assets = json.loads(project["asset_pack_json"])
    saved_invoice = json.loads(project["invoice_json"])
    assert assets["product_type"] == product
    assert saved_invoice["product_type"] == product
    assert assets["engine_adapter"] != "storyboard_scene_image_video_engine"
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 0


@pytest.mark.parametrize("product,flow_kind", (("storyboard_prompt", ""), (None, ""), (None, "storyboard")))
def test_real_and_legacy_storyboard_keep_existing_tier800_contract(isolated_session, product, flow_kind):
    stored, conn = isolated_session
    session = session_for(product, flow_kind=flow_kind)
    stored.update(deepcopy(session))
    invoice = bot.video_b14_invoice_for_session(session, 901)
    assert invoice["quality_xu"] == 1714
    assert invoice["total_xu"] == 3086
    project = bot.video_b14_prepare_project_for_invoice(901, session)
    assets = json.loads(project["asset_pack_json"])
    assert assets["product_type"] == "storyboard_prompt"
    assert assets["selected_provider"] == "key4u_video"
    assert assets["selected_model"] == "kling-v3"
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 0
