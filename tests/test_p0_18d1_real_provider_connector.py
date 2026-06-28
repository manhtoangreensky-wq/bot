import json
import sqlite3

import bot
import remote_worker
from services import remote_worker_api
from services import video_project_queue as queue
from services import video_real_render_connector as connector


def test_real_render_hook_not_always_unavailable(monkeypatch, tmp_path):
    output = tmp_path / "real-provider.mp4"
    output.write_bytes(b"real-provider-video")

    def fake_render(job, work_dir):
        assert job["original_user_prompt"] == "video quảng cáo nước hoa nam sang trọng đăng TikTok"
        assert work_dir
        return {"ok": True, "final_video_path": str(output)}

    monkeypatch.setattr(connector, "render_real_video_job", fake_render)
    final_path = remote_worker.render_real_video(
        {"job_id": "real-1", "original_user_prompt": "video quảng cáo nước hoa nam sang trọng đăng TikTok"},
        str(tmp_path),
    )
    assert final_path == str(output)


def test_real_render_connector_uses_blackbox_pipeline(monkeypatch, tmp_path):
    captured = {}
    output = tmp_path / "final.mp4"

    def fake_pipeline(**kwargs):
        captured.update(kwargs)
        output.write_bytes(b"real mp4")
        return {"ok": True, "final_video_path": str(output), "scene_count": kwargs["max_scenes"]}

    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    result = connector.render_real_video_job(
        {
            "job_id": "real-2",
            "user_id": "99",
            "original_user_prompt": "video 3 cảnh giới thiệu quán cà phê tối giản, ấm áp, đăng Reels",
            "scene_count": 3,
            "aspect_ratio": "9:16",
            "addon_plan": {"logo_enabled": True, "logo_text": "CAFE A", "logo_position": "top_center", "subtitle_enabled": True},
            "provider_order": "shopaikey,key4u",
        },
        str(tmp_path),
    )
    assert result["final_video_path"] == str(output)
    assert captured["user_prompt"] == "video 3 cảnh giới thiệu quán cà phê tối giản, ấm áp, đăng Reels"
    assert captured["max_scenes"] == 3
    assert captured["enable_logo"] is True
    assert captured["logo_text"] == "CAFE A"
    assert captured["logo_position"] == "top_center"
    assert callable(captured["render_video_func"])
    assert callable(captured["llm_func"])


def test_product_video_job_payload_contains_original_prompt_and_addon_plan(tmp_path):
    conn = sqlite3.connect(tmp_path / "payload.db")
    queue.ensure_video_project_queue_schema(conn)
    asset_pack = {
        "render_mode": "real",
        "original_user_prompt": "video quảng cáo nước hoa nam sang trọng đăng TikTok",
        "cleaned_user_prompt": "video quảng cáo nước hoa nam sang trọng đăng TikTok",
        "provider_order": "shopaikey,key4u",
    }
    addon_plan = {
        "voice_enabled": True,
        "voice_source": "default_female",
        "voice_volume_percent": 120,
        "music_enabled": True,
        "music_source": "default",
        "music_volume_percent": 10,
        "logo_enabled": True,
        "logo_source": "text",
        "logo_text": "TOAN AAS",
        "logo_position": "bottom_center",
        "subtitle_enabled": True,
    }
    project = queue.create_video_project(
        conn,
        user_id=123,
        profile_id="product_review",
        topic="video quảng cáo nước hoa nam sang trọng đăng TikTok",
        ratio="9:16",
        asset_pack=asset_pack,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        scene_cards_json=[{"scene_index": 1, "provider_prompt": "luxury perfume bottle hero shot"}],
        prompt_text=asset_pack["original_user_prompt"],
        addon_plan_json=addon_plan,
        invoice_json={"render_mode": "real", "total_xu": 300},
        scene_count=1,
        total_xu_estimated=300,
        is_confirmed=1,
        confirmed_at=queue.now_text(),
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=123)
    payload = remote_worker_api.build_worker_job_payload(queue.hydrate_video_job_payload(conn, job))
    assert payload["original_user_prompt"] == asset_pack["original_user_prompt"]
    assert payload["cleaned_user_prompt"] == asset_pack["cleaned_user_prompt"]
    assert payload["provider_order"] == "shopaikey,key4u"
    assert payload["addon_plan"]["logo_text"] == "TOAN AAS"
    assert payload["addon_plan"]["logo_position"] == "bottom_center"
    assert payload["addon_plan"]["voice_enabled"] is True
    assert payload["addon_plan"]["music_enabled"] is True
    assert payload["render_mode"] == "real"


def test_product_video_flow_does_not_drop_original_user_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "bot.db"))
    bot.init_db()
    uid = 181801
    session = {
        "product_id": "multi_scene_film",
        "topic": "video quảng cáo nước hoa nam sang trọng đăng TikTok",
        "draft": {
            "b14_profile_id": "product_review",
            "b14_quality_xu": 300,
            "b14_scene_count": 1,
            "b14_scene_count_selected": True,
            "b14_storyboard_plan": {"preview_text": "storyboard preview only", "scene_cards": [{"scene_index": 1, "provider_prompt": "hero scene"}]},
            "b14_addon_plan": {**bot.video_b14_default_addon_plan("product_review"), "logo_enabled": True, "logo_source": "text", "logo_text": "TOAN AAS", "logo_position": "top_right"},
        },
    }
    bot.save_video_session(uid, session)
    project = bot.video_b14_prepare_project_for_invoice(uid, session)
    asset_pack = json.loads(project["asset_pack_json"])
    assert asset_pack["original_user_prompt"] == "video quảng cáo nước hoa nam sang trọng đăng TikTok"
    assert project["prompt_text"] == "video quảng cáo nước hoa nam sang trọng đăng TikTok"


def test_prompt_builder_generates_soft_scene_prompts():
    plan = connector.real_video_scene_plan(
        {
            "original_user_prompt": "video quảng cáo nước hoa nam sang trọng đăng TikTok",
            "scene_count": 3,
            "aspect_ratio": "9:16",
            "profile_id": "luxury_ad",
        }
    )
    prompts = [scene["video_prompt"] for scene in plan["scenes"]]
    assert len(prompts) == 3
    assert all("video quảng cáo nước hoa nam sang trọng đăng TikTok" in prompt for prompt in prompts)
    assert all("no fake logo" in prompt and "no watermark" in prompt for prompt in prompts)
    assert len(set(prompts)) == 3


def test_addon_mux_failure_not_fake_success(monkeypatch, tmp_path):
    def fake_pipeline(**_kwargs):
        return {"ok": False, "error": "music_addon_source_missing", "final_video_path": ""}

    monkeypatch.setattr(connector, "process_multiscene_video_pipeline", fake_pipeline)
    try:
        connector.render_real_video_job(
            {"job_id": "real-3", "original_user_prompt": "video test", "addon_plan": {"music_enabled": False}},
            str(tmp_path),
        )
    except connector.RealVideoRenderError as exc:
        assert "music_addon_source_missing" in str(exc)
    else:
        raise AssertionError("expected connector failure")
