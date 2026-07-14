import sqlite3
from pathlib import Path

import bot
from services import video_final_output, video_project_queue


def _memory_conn():
    conn = sqlite3.connect(":memory:")
    video_project_queue.ensure_video_project_queue_schema(conn)
    return conn


def test_video_main_menu_contract_locked():
    product_ids = [button for row in bot.VIDEO_MENU_ROWS for button in row]
    assert "video_trend" in product_ids
    assert "video_ai_real" in product_ids
    assert "storyboard_prompt" in product_ids
    assert "Video theo trend" in bot.VIDEO_PRODUCT_REGISTRY["video_trend"]["public_label"]
    assert "Video AI chân thật" in bot.VIDEO_PRODUCT_REGISTRY["video_ai_real"]["public_label"]
    assert bot.VIDEO_PRODUCT_REGISTRY["storyboard_prompt"]["public_label"] == "🎞 Storyboard"


def test_video_suggestion_contract_from_p0_18n5_locked():
    payload = bot.video_microflow_audit_payload()
    checks = {row["name"]: row["ok"] for row in payload["checks"]}
    assert payload["ok"] is True
    assert checks["suggestions_have_multiple_selectable_options"] is True
    assert checks["option_keyboard_not_single_use_direction"] is True
    assert checks["suggestion_buttons_show_options_before_count"] is True


def test_video_back_routing_contract_locked():
    assert bot.video_back_audit_payload()["ok"] is True


def test_video_flow_contract_audit_passes():
    assert bot.video_flow_contract_audit_payload()["ok"] is True


def test_all_video_products_have_engine_route():
    payload = bot.video_engine_route_audit_payload()
    assert payload["ok"] is True
    for key in [
        "video_trend",
        "video_ai_prompt",
        "video_ai_image",
        "video_ai_video_reference",
        "script_to_video",
        "image_to_video",
        "self_shot_scene_change",
        "multi_scene_film",
        "video_idea_to_product",
        "storyboard_prompt",
        "prompt_vault_to_video",
        "video_local_edit",
    ]:
        route = video_final_output.route_for_product_type(key)
        assert route["product_type"] == key
        assert route["adapter"]
        assert route["input_requirements"]


def test_video_product_type_mapping_for_all_locked_products():
    cases = {
        "video_trend": "video_trend",
        "script_image_video": "script_to_video",
        "storyboard_prompt": "storyboard_prompt",
        "frame_video_local": "image_to_video",
        "self_shot_scene_change": "self_shot_scene_change",
        "multi_scene_film": "multi_scene_film",
        "video_idea": "video_idea_to_product",
    }
    for product_id, expected in cases.items():
        assert bot.video_engine_product_type_for_session({"product_id": product_id, "draft": {}}) == expected
    assert bot.video_engine_product_type_for_session({"product_id": "video_ai_real", "draft": {"entry_choice": "ai_prompt_menu"}}) == "video_ai_prompt"
    assert bot.video_engine_product_type_for_session({"product_id": "video_ai_real", "draft": {"entry_choice": "ai_image_menu"}}) == "video_ai_image"
    assert bot.video_engine_product_type_for_session({"product_id": "video_ai_real", "draft": {"entry_choice": "ai_video_menu"}}) == "video_ai_video_reference"


def test_no_video_provider_call_before_final_confirm_static_contract():
    source = bot.inspect.getsource(bot.handle_video_product_callback)
    assert "b14_confirm" in source
    pre_confirm = source.split('if action == "b14_confirm"', 1)[0]
    assert "confirm_video_project_invoice(" not in pre_confirm
    assert "render_real_video" not in pre_confirm


def test_final_confirm_project_payload_has_product_type_and_real_engine_route():
    session = {
        "product_id": "video_ai_real",
        "topic": "quảng cáo nước hoa nam",
        "draft": {
            "entry_choice": "ai_prompt_menu",
            "b14_profile_id": "storytelling",
            "b14_quality_xu": 200,
            "b14_scene_count": 1,
            "b14_aspect_ratio": "9:16",
        },
    }
    project = bot.video_b14_prepare_project_for_invoice(180180, session)
    asset_pack = video_final_output.json_loads(project.get("asset_pack_json"), {})
    invoice = video_final_output.json_loads(project.get("invoice_json"), {})
    assert asset_pack["source"] == "product_video"
    assert asset_pack["render_mode"] == "real"
    assert asset_pack["test_pattern"] is False
    assert asset_pack["admin_video_delivery"] is False
    assert asset_pack["product_type"] == "video_ai_prompt"
    assert asset_pack["engine_adapter"] == "text_to_video"
    assert invoice["product_type"] == "video_ai_prompt"


def test_confirm_video_project_invoice_sets_final_rendering_and_enqueues_job():
    conn = _memory_conn()
    project = video_project_queue.create_video_project(
        conn,
        user_id=1,
        profile_id="storytelling",
        topic="demo",
        asset_pack={"source": "product_video", "render_mode": "real", "real_renderer_required": True, "product_type": "video_ai_prompt"},
    )
    project = video_project_queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json={"total_xu": 0, "product_type": "video_ai_prompt"},
        total_xu_estimated=0,
    )
    result = video_project_queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=1)
    assert result["ok"] is True
    assert result["project"]["status"] == "queued_for_worker"
    assert result["project"]["video_terminal_state"] == "final_rendering"
    assert result["job"]["status"] == "queued"


def test_draft_not_marked_final_success():
    result = video_final_output.validate_final_video_output(
        path="",
        result={"visual_classification": "partial_simple_video", "renderer": "local_scene_composer"},
    )
    assert result["ok"] is False
    assert result["reason"] == "placeholder_not_final_video"


def test_final_success_requires_valid_mp4(monkeypatch, tmp_path):
    video_path = tmp_path / "final.mp4"
    video_path.write_bytes(b"not empty")
    monkeypatch.setattr(
        video_final_output,
        "probe_video",
        lambda path, ffprobe="": {"ok": True, "path": str(path), "bytes": 9, "duration": 6.0, "has_video": True, "has_audio": True},
    )
    result = video_final_output.validate_final_video_output(path=str(video_path), result={"visual_classification": "final_ai_video"}, require_audio=True)
    assert result["ok"] is True
    assert result["duration"] == 6.0
    assert result["terminal_state"] == "final_delivered"


def test_zero_duration_video_not_delivered(monkeypatch, tmp_path):
    video_path = tmp_path / "zero.mp4"
    video_path.write_bytes(b"not empty")
    monkeypatch.setattr(
        video_final_output,
        "probe_video",
        lambda path, ffprobe="": {"ok": False, "reason": "output_zero_duration", "path": str(path), "bytes": 9, "duration": 0, "has_video": True},
    )
    result = video_final_output.validate_final_video_output(path=str(video_path), result={"visual_classification": "final_ai_video"})
    assert result["ok"] is False
    assert result["reason"] == "output_zero_duration"


def test_video_queue_completion_rejects_placeholder_product_output(monkeypatch, tmp_path):
    conn = _memory_conn()
    project = video_project_queue.create_video_project(
        conn,
        user_id=1,
        profile_id="storytelling",
        topic="demo",
        asset_pack={"source": "product_video", "render_mode": "real", "real_renderer_required": True, "product_type": "video_ai_prompt"},
    )
    project = video_project_queue.update_video_project(conn, int(project["project_id"]), status="queued_for_worker", is_confirmed=1)
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=1)
    path = tmp_path / "draft.mp4"
    path.write_bytes(b"draft")
    result = video_project_queue.complete_video_job(
        conn,
        job_id=int(job["id"]),
        final_video_path=str(path),
        result={"visual_classification": "partial_simple_video", "renderer": "local_scene_composer"},
    )
    assert result["status"] == "failed"
    assert result["project"]["video_terminal_state"] == "failed_no_charge"


def test_video_queue_completion_accepts_valid_final_mp4(monkeypatch, tmp_path):
    conn = _memory_conn()
    project = video_project_queue.create_video_project(
        conn,
        user_id=1,
        profile_id="storytelling",
        topic="demo",
        asset_pack={"source": "product_video", "render_mode": "real", "real_renderer_required": True, "product_type": "video_ai_prompt"},
    )
    project = video_project_queue.update_video_project(conn, int(project["project_id"]), status="queued_for_worker", is_confirmed=1)
    job = video_project_queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=1)
    path = tmp_path / "final.mp4"
    path.write_bytes(b"final video")
    monkeypatch.setattr(
        video_final_output,
        "validate_final_video_output",
        lambda **kwargs: {"ok": True, "bytes": 11, "duration": 6.0, "has_video": True, "has_audio": False},
    )
    result = video_project_queue.complete_video_job(
        conn,
        job_id=int(job["id"]),
        final_video_path=str(path),
        result={"visual_classification": "final_ai_video", "renderer": "provider_scene_video"},
    )
    assert result["ok"] is True
    assert result["project"]["status"] == "completed"
    assert result["project"]["video_terminal_state"] == "final_delivered"


def test_debug_read_only_commands_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "video_job_debug" in source
    assert "video_render_debug" in source
    assert "video_delivery_debug" in source
    assert "video_engine_route_audit" in source
    assert "video_final_output_audit" in source
