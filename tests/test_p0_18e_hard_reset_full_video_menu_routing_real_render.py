import asyncio
import sqlite3
from types import SimpleNamespace

import bot
from services import remote_worker_api
from services import video_project_queue as queue


PUBLIC_UID = 918501
ADMIN_UID = int(bot.ADMIN_ID)


class FakeMessage:
    chat_id = 918500
    message_id = 1

    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P018E")
        self.data = data
        self.message = FakeMessage()
        self.answered = False
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _press(user_id: int, data: str):
    query = FakeQuery(user_id, data)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query, bot.get_video_session(user_id)


def _temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "p0_18e_video.db"

    def _connect():
        conn = sqlite3.connect(db_path)
        queue.ensure_video_project_queue_schema(conn)
        return conn

    monkeypatch.setattr(bot, "db_connect", _connect)
    return db_path


def _seed_video_session(user_id: int, *, product_id: str = "video_ai_real", scene_count: int = 3):
    bot.clear_video_session(user_id)
    session = bot.task3d_session_step(
        user_id,
        "profile_select",
        product_id=product_id,
        return_to="menu|main_video",
        topic="review máy xay mini màu xanh, ánh sáng đẹp, có logo TOAN AAS",
        provider_called=False,
        xu_charged=0,
    )
    session = bot.video_b14_set_profile(user_id, session, "product_review")
    session = bot.task3d_session_step(
        user_id,
        "storyboard_preview",
        topic="review máy xay mini màu xanh, ánh sáng đẹp, có logo TOAN AAS",
        provider_called=False,
        xu_charged=0,
    )
    bot.video_b14_build_storyboard_for_session(user_id, bot.get_video_session(user_id), scene_count=scene_count)
    return bot.get_video_session(user_id)


def _seed_product_video_job(conn, *, user_id=ADMIN_UID, admin=True, scene_count=3):
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "scene_mode": "single" if scene_count == 1 else "multi",
        "test_pattern": False,
        "admin_video_delivery": False,
        "owner_admin_test_mode": False,
        "safe_output_delivery_test": False,
        "fake_renderer_allowed": False,
        "real_renderer_required": True,
        "provider_call": True,
        "public_user": not admin,
        "admin_only": bool(admin),
        "created_by_admin": bool(admin),
        "no_charge": bool(admin),
        "scene_count": scene_count,
        "duration_seconds": scene_count * 6,
        "original_user_prompt": "video sản phẩm thật, không test pattern",
        "provider_order": "shopaikey,key4u",
    }
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="product_review",
        topic="Product video route",
        ratio="9:16",
        asset_pack=asset_pack,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        is_confirmed=1,
        confirmed_at=queue.now_text(),
        invoice_json={**asset_pack, "total_xu": 0 if admin else 900},
        addon_plan_json={},
        total_xu_estimated=0 if admin else 900,
        scene_count=scene_count,
    )
    job = queue.enqueue_video_render_job(conn, project_id=int(project["project_id"]), user_id=user_id, max_attempts=1)
    queue.update_video_project(conn, int(project["project_id"]), job_id=int(job["id"]))
    return queue.get_video_project(conn, int(project["project_id"])), job


def test_video_main_menu_contract_routes_are_exact():
    markup = bot.main_video_keyboard("vi")
    assert _labels(markup) == [
        "🎥 Tạo video AI",
        "🖼 Ảnh thành video",
        "🎭 Tự quay / đổi cảnh AI",
        "🧩 Prompt video",
        "🌐 Dịch phụ đề / Video",
        "📂 Kho video",
        "🏠 Menu chính",
    ]
    assert _callbacks(markup) == [
        "vproduct|open|video_ai_real",
        "vproduct|open|image_to_video",
        "vproduct|open|self_shot_scene_change",
        "vpromptlib|start",
        "videodub|start|video",
        "menu|video_vault",
        "menu|main",
    ]
    forbidden = {"vdownload|start", "videoedit|start", "vproduct|open|multi_scene_film", "vproduct|open|video_trend"}
    assert not forbidden.intersection(_callbacks(markup))


def test_image_to_video_uses_product_draft_not_legacy_unified_flow():
    user_id = PUBLIC_UID + 1
    query, session = _press(user_id, "vproduct|open|image_to_video")
    assert query.answered is True
    assert session["product_id"] == "image_to_video"
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in query.edits[-1]["text"]
    assert "Ghép ảnh" not in query.edits[-1]["text"]


def test_storyboard_confirm_requires_scene_mode_before_addons():
    user_id = PUBLIC_UID + 2
    _seed_video_session(user_id, scene_count=3)
    query, session = _press(user_id, "vproduct|storyboard_confirm")
    assert session["current_step"] == "b14_scene_mode"
    assert "Chọn cách dựng video" in query.edits[-1]["text"]
    assert "vproduct|b14_scene_mode|single" in _callbacks(query.edits[-1]["reply_markup"])
    assert "vproduct|b14_scene_mode|multi" in _callbacks(query.edits[-1]["reply_markup"])


def test_single_scene_path_preserves_draft_state_and_real_payload(monkeypatch, tmp_path):
    _temp_db(monkeypatch, tmp_path)
    user_id = PUBLIC_UID + 3
    _seed_video_session(user_id, scene_count=3)
    _press(user_id, "vproduct|storyboard_confirm")
    _press(user_id, "vproduct|b14_scene_mode|single")
    _press(user_id, "vproduct|b14_addon_done")
    _press(user_id, "vproduct|b14_aspect|9:16")
    query, session = _press(user_id, "vproduct|b14_quality|300")
    draft = session["draft"]
    assert session["current_step"] == "b14_invoice"
    assert draft["video_scene_mode"] == "single"
    assert draft["video_scene_count"] == 1
    assert draft["b14_invoice"]["scene_count"] == 1
    assert draft["asset_pack"]["source"] == "product_video"
    assert draft["asset_pack"]["render_mode"] == "real"
    assert draft["asset_pack"]["test_pattern"] is False
    assert draft["asset_pack"]["admin_video_delivery"] is False
    assert "Hóa đơn tạo video" in query.edits[-1]["text"]


def test_multi_scene_invoice_payload_has_real_product_worker_flags(monkeypatch, tmp_path):
    _temp_db(monkeypatch, tmp_path)
    user_id = PUBLIC_UID + 4
    session = _seed_video_session(user_id, scene_count=3)
    session = bot.task3d_session_step(
        user_id,
        "b14_scene_count",
        b14_quality_xu=500,
        b14_scene_mode="multi",
        b14_scene_count=3,
        b14_scene_count_selected=True,
        b14_aspect_ratio="16:9",
        provider_called=False,
        xu_charged=0,
    )
    project = bot.video_b14_prepare_project_for_invoice(user_id, session)
    session = bot.get_video_session(user_id)
    asset_pack = session["draft"]["asset_pack"]
    assert project["status"] == "draft_invoice"
    assert session["draft"]["video_scene_mode"] == "multi"
    assert session["draft"]["video_scene_count"] == 3
    assert asset_pack["source"] == "product_video"
    assert asset_pack["render_mode"] == "real"
    assert asset_pack["fake_renderer_allowed"] is False
    assert asset_pack["provider_call"] is True


def test_invoice_addons_return_to_invoice(monkeypatch, tmp_path):
    _temp_db(monkeypatch, tmp_path)
    user_id = PUBLIC_UID + 5
    session = _seed_video_session(user_id, scene_count=1)
    session = bot.task3d_session_step(
        user_id,
        "b14_invoice",
        b14_quality_xu=300,
        b14_scene_mode="single",
        b14_scene_count=1,
        b14_scene_count_selected=True,
        b14_aspect_ratio="9:16",
        provider_called=False,
        xu_charged=0,
    )
    bot.video_b14_prepare_project_for_invoice(user_id, session)
    _press(user_id, "vproduct|b14_invoice_screen")
    query, session = _press(user_id, "vproduct|b14_addons_from_invoice")
    assert session["current_step"] == "b14_addons"
    assert session["draft"]["b14_addons_return_to"] == "invoice"
    assert "vproduct|b14_invoice_screen" in _callbacks(query.edits[-1]["reply_markup"])
    query, session = _press(user_id, "vproduct|b14_addon_done")
    assert session["current_step"] == "b14_invoice"
    assert "Hóa đơn tạo video" in query.edits[-1]["text"]


def test_worker_claim_uses_product_lane_not_admin_video_or_canary(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18e_worker.db")
    queue.ensure_video_project_queue_schema(conn)
    try:
        project, job = _seed_product_video_job(conn, admin=True, scene_count=3)
        admin_claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="admin-video-worker",
            capabilities=["admin_video", "ffmpeg"],
            admin_video_only=True,
        )
        assert admin_claim["job"] is None
        assert queue.get_video_render_job(conn, int(job["id"]))["status"] == "queued"
        owner_claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="owner-product-worker",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert owner_claim["job"]["job_id"] == str(job["id"])
        assert owner_claim["job"]["source"] == "product_video"
        assert owner_claim["job"]["render_mode"] == "real"
        assert owner_claim["job"]["test_pattern"] is False
        assert owner_claim["job"]["admin_video_delivery"] is False
        assert remote_worker_api.is_remote_worker_product_video_job(owner_claim["job"], project) is True
    finally:
        conn.close()


def test_product_completion_rejects_test_pattern_output(tmp_path):
    conn = sqlite3.connect(tmp_path / "p0_18e_fake_block.db")
    queue.ensure_video_project_queue_schema(conn)
    try:
        _project, job = _seed_product_video_job(conn, admin=True, scene_count=1)
        claim = remote_worker_api.claim_remote_worker_job(
            conn,
            worker_id="owner-product-worker",
            capabilities=["owner_product_video", "product_video", "ffmpeg"],
            owner_product_video_only=True,
        )
        assert claim["job"]["job_id"] == str(job["id"])
        result = remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="owner-product-worker",
            job_id=int(job["id"]),
            result={"render_mode": "admin_test_pattern", "test_pattern": True, "renderer": "testsrc"},
        )
        assert result["ok"] is False
        assert "test_pattern" in result["reason"]
        assert queue.get_video_render_job(conn, int(job["id"]))["status"] == "failed"
    finally:
        conn.close()


def test_product_status_copy_is_clean_public_language():
    session = {
        "draft": {
            "b14_queue_job_id": 919,
            "b14_invoice": {"scene_count": 3, "duration_seconds": 18, "quality_xu": 300, "package_label": "300 Xu"},
            "b14_addon_plan": {"voice_enabled": False, "music_enabled": False, "subtitle_enabled": False, "dub_enabled": False, "logo_enabled": False},
        }
    }
    text = bot.video_b14_queue_status_text(session, {"job": {"id": 919, "status": "failed", "last_error": "real_video_renderer_unavailable"}}, PUBLIC_UID, "vi")
    lowered = text.lower()
    assert "hệ thống chưa dựng được video" in lowered
    for forbidden in ("owner/admin test mode", "admin_video", "canary", "test_pattern", "render_mode", "api key", "provider"):
        assert forbidden not in lowered


def test_video_vault_route_is_plain_customer_copy():
    text, markup = bot.localized_menu_content("video_vault", False, "vi", PUBLIC_UID + 6)
    assert "Kho video" in text
    assert "không trừ Xu" in text
    assert "menu|main_video" in _callbacks(markup)
    for forbidden in ("provider", "worker", "render_mode", "test_pattern", "canary"):
        assert forbidden not in text.lower()
