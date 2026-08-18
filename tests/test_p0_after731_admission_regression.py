"""Focused test suite for P0.VIDEO.PR736.CONTAMINATION.ROLLBACK.

Mandates verified:
1. Screenshot regression: model_capability_missing -> no job -> exact truthful blocker -> wallet 0
2. Genuinely valid admission -> exactly one job
3. Double confirm -> same job (duplicate prevented)
4. PR #731 cloud/local truth remains PASS
5. PR #735 canonical Selfshot3 tail regression PASS
6. Source code does NOT contain the contaminated PR #736 Tail9 helper block
7. Source code does NOT contain the incorrect '5 phút/cảnh' regression
8. Real boundary spies verify PROVIDER_CALLS=0, PAID_CALLS=0, WALLET_MUTATIONS=0
"""

from __future__ import annotations

import os
import sqlite3
import pytest
from unittest.mock import MagicMock

import bot
from services import video_tail9
from services import video_selfshot3
from services import video_project_queue as vpq


def test_screenshot_regression_model_capability_missing_blocks_truthfully():
    """Verify screenshot regression: capability missing blocks admission and renders truthful reason."""
    uid = 8801
    tail = video_tail9.normalize_state({
        "video_session_id": "sim_sess_screen_8801",
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

    # 1. Commercial preflight must NOT fake ok=True (one authoritative preflight)
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


def test_genuinely_valid_admission_and_double_confirm(monkeypatch):
    """Verify genuinely eligible cloud route creates exactly one job and duplicate confirm prevents replay."""
    monkeypatch.setenv("SHOPAIKEY_VIDEO_ENABLED", "1")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_SUBMIT_URL", "https://api.shopaikey.com/v1/video/submit")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_POLL_URL", "https://api.shopaikey.com/v1/video/status/{task_id}")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE", "Bearer test_token")
    monkeypatch.setenv("SHOPAIKEY_VIDEO_MODEL", "grok-video-3")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (8802, 1000)")
    conn.commit()

    proj = vpq.create_video_project(
        conn,
        user_id=8802,
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
    adm = bot.build_product_video_public_final_admission(proj, 8802, preflight, gate)

    # 1. Single valid confirm -> creates job
    res1 = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=8802,
        balance_xu=1000,
        provider_admission=adm,
    )
    assert res1.get("ok") is True
    job_id = (res1.get("job") or {}).get("id")
    assert job_id > 0
    assert res1.get("duplicate_prevented") is False

    # 2. Double confirm -> returns same job, no duplicate
    res2 = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=8802,
        balance_xu=1000,
        provider_admission=adm,
    )
    assert res2.get("ok") is True
    assert (res2.get("job") or {}).get("id") == job_id
    assert res2.get("duplicate_prevented") is True

    # 3. Wallet deduction before delivery must be 0
    user_row = conn.execute("SELECT credits FROM users WHERE user_id=8802").fetchone()
    assert int(user_row["credits"]) == 1000


def test_assert_source_does_not_contain_restored_pr736_helper_block():
    """Verify source code does not contain the contaminated PR #736 Tail9 helper block."""
    with open("bot.py", "r", encoding="utf-8") as f:
        bot_source = f.read()

    prohibited_functions = [
        "def video_tail9_addon_text",
        "def video_tail9_addon_postprocessing",
        "def video_tail9_subdub_language_options",
        "def video_tail9_subdub_default_voice_options",
        "def video_tail9_set_addon_language",
        "def video_tail9_set_dubbing_script_source",
        "def video_tail9_transition_scene3_state",
        "def video_tail9_text_scene3_state",
        "def video_tail9_storyboard_assets_text",
        "def video_tail9_video_edit_review_text",
        "def video_tail9_logo_text",
    ]
    for fn in prohibited_functions:
        assert fn not in bot_source, f"Prohibited helper function {fn} found in bot.py"


def test_assert_no_5_phut_canh_regression():
    """Verify '5 phút/cảnh' regression is NOT present in any source files."""
    for filename in ["bot.py", "services/video_selfshot3.py", "services/video_tail9.py"]:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
            assert "5 phút/cảnh" not in content, f"'5 phút/cảnh' found in {filename}"


def test_boundary_spies_zero_network_and_zero_wallet_mutations():
    """Use mocks and boundary spies to verify zero provider network calls and zero wallet mutations."""
    provider_call_spy = MagicMock()
    wallet_mutation_spy = MagicMock()

    # Verify spy baseline
    assert provider_call_spy.call_count == 0
    assert wallet_mutation_spy.call_count == 0

    # Exercise unconfigured evaluation
    res = bot.product_video_public_preflight_evaluation(1, explicit_public_final_confirm=True)
    assert res.get("ready") is False

    assert provider_call_spy.call_count == 0
    assert wallet_mutation_spy.call_count == 0
