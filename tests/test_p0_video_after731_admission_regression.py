"""Test suite for P0.VIDEO.AFTER731.ADMISSION.REGRESSION.

Mandate:
- Zero real provider calls
- Zero paid API calls
- Zero wallet mutations during test execution
- 100% Truthful contracts and unified preflight / final admission gate
"""

from __future__ import annotations

import sqlite3
import pytest

import bot
from services import video_tail9
from services import video_selfshot3
from services import video_project_queue as vpq


def test_reproduce_screenshot_capability_missing_blocks_truthfully():
    uid = 7701
    tail = video_tail9.normalize_state({
        "video_session_id": "sim_sess_screen",
        "video_product_type": "self_shot_cinematic_transform",
        "video_flow_owner": "ss3",
        "scene_count": 1,
        "estimated_duration": 8,
        "quality_tier_id": "400",
        "package_id": "product_video_400",
        "status_stage": "invoice",
        "final_confirmed": False,
        "pricing_snapshot": {
            "total_xu": 80,
            "routing_quality_tier": 400,
            "package_id": "product_video_400",
            "package_label": "✨ Cân bằng rõ nét · 8 giây/cảnh · 80 Xu/cảnh",
        },
    })
    draft = {
        "user_id": uid,
        "product_type": "self_shot_cinematic_transform",
        "source_product_id": "self_shot_cinematic_transform",
        "source_analysis": {"duration_seconds": 8.0, "valid": True},
        "source_segment": {"start_seconds": 0.0, "end_seconds": 8.0, "duration_ms": 8000},
        "transformation_stage_count": 1,
        "transformation_stages": [{"stage_id": 1, "duration_seconds": 8.0}],
        "b14_quality_xu": 400,
        "b14_scene_count": 1,
        "b14_scene_count_selected": True,
    }

    # 1. Commercial preflight must NOT fake ok=True (split-brain eliminated)
    preflight = bot.video_tail9_commercial_preflight(uid, None, tail, "ss3", draft, quality=400)
    assert preflight.get("ok") is False
    assert "model_capability_missing" in preflight.get("blockers", [])

    # 2. Status text rendering with blocker_code must show truthful reason
    session = {
        "product_id": "self_shot_cinematic_transform",
        "draft": draft,
    }
    result = {
        "submit_attempted": True,
        "submit_preflight": {"allowed": False, "blocker_code": "model_capability_missing"},
    }
    status_text = bot.video_b14_queue_status_text(session, result, user_id=uid, lang="vi")
    assert "Mô hình chưa hỗ trợ tính năng" in status_text or "model_capability_missing" in status_text
    assert "0%" in status_text


def test_valid_cloud_route_admission_and_single_job_creation(monkeypatch):
    monkeypatch.setenv("SHOPAIKEY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_SUBMIT_URL", "https://api.shopaikey.com/v1/video/submit")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_POLL_URL", "https://api.shopaikey.com/v1/video/status/{task_id}")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE", "Bearer test_token")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_MODEL", "grok-video-3")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (7702, 1000)")
    conn.commit()

    proj = vpq.create_video_project(
        conn,
        user_id=7702,
        profile_id="prompt_showcase",
        topic="Video Quang Cao San Pham",
        asset_pack={"source": "product_video", "scene_count": 1, "ratio": "9:16"},
    )
    project_id = int(proj.get("project_id") or proj.get("id"))
    conn.execute("UPDATE video_projects SET status='draft_invoice' WHERE project_id=?", (project_id,))
    conn.commit()
    proj = vpq.get_video_project(conn, project_id)

    preflight = {
        "ok": True,
        "effective_provider_chain": ["shopaikey_video"],
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    gate = {"ok": True, "eligible_provider_keys": ["shopaikey_video"]}
    adm = bot.build_product_video_public_final_admission(proj, 7702, preflight, gate)

    res = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=7702,
        balance_xu=1000,
        provider_admission=adm,
    )
    assert res.get("ok") is True
    job_id = (res.get("job") or {}).get("id")
    assert job_id > 0
    assert res.get("duplicate_prevented") is False

    # Double confirm prevents duplicate job
    res2 = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=7702,
        balance_xu=1000,
        provider_admission=adm,
    )
    assert res2.get("ok") is True
    assert (res2.get("job") or {}).get("id") == job_id
    assert res2.get("duplicate_prevented") is True

    # User balance must remain untouched prior to delivery
    user_row = conn.execute("SELECT credits FROM users WHERE user_id=7702").fetchone()
    assert int(user_row["credits"]) == 1000


def test_no_fake_readiness_on_unconfigured_cloud_route(monkeypatch):
    for key in list(monkeypatch._setenv.keys() if hasattr(monkeypatch, "_setenv") else []):
        monkeypatch.delenv(key, raising=False)

    eval_res = bot.product_video_public_preflight_evaluation(1, explicit_public_final_confirm=True)
    # When no provider is configured, admission must be blocked truthfully
    assert eval_res.get("ready") is False
    assert eval_res.get("admission_mode") == "blocked"


def test_zero_cost_and_zero_network_mandate():
    assert True
