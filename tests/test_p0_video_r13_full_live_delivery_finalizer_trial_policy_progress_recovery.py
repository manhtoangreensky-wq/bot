import json
import sqlite3
from datetime import datetime, timedelta

import bot
from services import video_project_queue
from services import video_real_render_connector as connector


def _button_labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_trial_package_scene_keyboard_only_one_scene():
    session = {"draft": {"b14_quality_xu": 200}}
    labels = _button_labels(bot.video_b14_scene_count_keyboard(0, "vi", session))

    assert "🎞 1 cảnh" in labels
    assert "🎞 3 cảnh" not in labels
    assert "✍️ Nhập số khác" not in labels


def test_trial_package_scene_count_clamps_to_one_and_8s_invoice():
    session = {"draft": {"b14_quality_xu": 200, "b14_scene_count": 3}}

    invoice = bot.video_b14_invoice_for_session(session, user_id=123)

    assert invoice["scene_count"] == 1
    assert invoice["duration_seconds"] == 8
    assert invoice["total_xu"] == 200
    assert invoice["trial_policy_applied"] is True
    assert invoice["trial_scene_clamped"] is True


def test_basic_package_two_scenes_stays_16s_invoice():
    session = {"draft": {"b14_quality_xu": 300, "b14_scene_count": 2}}

    invoice = bot.video_b14_invoice_for_session(session, user_id=123)

    assert invoice["scene_count"] == 2
    assert invoice["duration_seconds"] == 16
    assert invoice["total_xu"] == 600


def test_trial_usage_limits_are_read_only_and_enforced_with_existing_rows(tmp_path):
    del tmp_path
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE video_projects(
            user_id INTEGER,
            profile_id TEXT,
            topic TEXT,
            ratio TEXT,
            status TEXT,
            quality_tier INTEGER,
            is_confirmed INTEGER,
            confirmed_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )"""
    )
    now = datetime(2026, 7, 8, 10, 0, 0)
    for idx in range(1):
        conn.execute(
            """INSERT INTO video_projects(user_id, profile_id, topic, ratio, status, quality_tier, is_confirmed, confirmed_at, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (42, "storytelling", f"trial {idx}", "9:16", "processing", 200, 1, now.isoformat(), now.isoformat(), now.isoformat()),
        )
    conn.commit()

    result = bot.video_b14_trial_usage_allowed(42, now_dt=now + timedelta(minutes=1), conn=conn)

    assert result["ok"] is False
    assert result["reason"] == "trial_daily_limit_reached"


def test_trial_paid_addons_blocked_but_free_logo_material_allowed():
    plan = {
        "voice_enabled": True,
        "voice_source": "uploaded",
        "music_enabled": True,
        "music_source": "default",
        "dub_enabled": True,
        "subtitle_enabled": True,
        "subtitle_source": "uploaded",
    }

    policy = bot.video_b14_trial_addon_policy(plan, quality_xu=200)
    sanitized = bot.video_b14_sanitize_trial_addons(plan, quality_xu=200)

    assert policy["paid_blocked"] is True
    assert "lồng tiếng" in policy["blocked_addons"]
    assert "nhạc tạo mới" in policy["blocked_addons"]
    assert sanitized["voice_enabled"] is True
    assert sanitized["music_enabled"] is False
    assert sanitized["dub_enabled"] is False


def test_progress_uses_elapsed_wait_not_raw_http_200_or_zero_forever():
    started = datetime(2026, 7, 8, 10, 0, 0)
    now = started + timedelta(minutes=10)
    payload = {
        "provider_task_id_saved": True,
        "continue_polling": True,
        "normalized_provider_status": "running",
        "provider_started_at": started.isoformat(),
        "provider_wait_max_seconds": 1200,
        "provider_progress_raw": 200,
        "http_200_not_used_as_progress": True,
    }

    telemetry = video_project_queue.reconcile_provider_progress_telemetry(
        {"status": "processing", "progress_percent": 20, "started_at": started.isoformat()},
        payload,
        now=now,
    )

    assert telemetry["provider_progress_public_suppressed"] is True
    assert telemetry["render_progress_source"] == "elapsed_provider_wait"
    assert 40 <= telemetry["render_video_progress_percent"] <= 45
    assert telemetry["render_video_progress_percent_public"] == str(telemetry["render_video_progress_percent"])
    assert telemetry["final_progress"] > 20


def test_public_rendering_block_keeps_elapsed_progress_bar():
    telemetry = {
        "provider_task_alive": True,
        "provider_progress_public_suppressed": True,
        "render_progress_public_mode": "elapsed_wait",
        "render_video_progress_percent_public": "42",
        "provider_wait_elapsed_seconds": 600,
        "provider_wait_max_seconds": 1200,
    }

    text = bot.video_b14_provider_rendering_block(telemetry)

    assert "<b>42%</b>" in text
    assert "Hệ thống đang dựng video" in text
    assert "provider" not in text.lower()


def test_duration_contract_rejects_short_final_for_two_scenes():
    project = {"scene_count": 2, "invoice_json": json.dumps({"scene_count": 2, "scene_seconds": 8, "duration_seconds": 16})}

    contract = video_project_queue.product_video_duration_contract(project, {}, {"ok": True, "duration": 8.0})

    assert contract["ok"] is False
    assert contract["reason"] == "final_duration_short_scene_coverage_missing"


def test_duration_contract_accepts_matching_final_for_two_scenes():
    project = {"scene_count": 2, "invoice_json": json.dumps({"scene_count": 2, "scene_seconds": 8, "duration_seconds": 16})}

    contract = video_project_queue.product_video_duration_contract(project, {}, {"ok": True, "duration": 16.0})

    assert contract["ok"] is True


def test_connector_expected_duration_uses_scene_seconds_8_not_legacy_6():
    job = {"scene_count": 3, "invoice_json": json.dumps({"scene_count": 3, "scene_seconds": 8})}

    assert connector.product_video_expected_duration_seconds(job) == 24


def test_logo_overlay_command_uses_video_width_ratio_and_position():
    material = {
        "logo_position": "top_right",
        "logo_width_ratio": 0.12,
        "logo_max_width_ratio": 0.18,
        "logo_margin_x_ratio": 0.04,
        "logo_margin_y_ratio": 0.035,
    }

    cmd = connector.build_product_video_logo_overlay_command("in.mp4", "logo.png", "out.mp4", material)
    joined = " ".join(cmd)

    assert "scale2ref" in joined
    assert "main_w*0.12" in joined
    assert "main_w-overlay_w-main_w*0.04" in joined
    assert "main_h*0.035" in joined


def test_logo_material_without_worker_file_is_not_claimed_applied(tmp_path):
    result = connector.apply_product_video_logo_overlay(
        str(tmp_path / "video.mp4"),
        str(tmp_path / "missing-logo.png"),
        str(tmp_path / "out.mp4"),
        {"logo_position": "top_right"},
    )

    assert result["ok"] is False
    assert result["reason"] == "logo_file_not_available_to_worker"
