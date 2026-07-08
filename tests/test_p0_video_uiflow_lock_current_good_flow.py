import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import bot


ROOT = Path(__file__).resolve().parents[1]


class FakeMessage:
    chat_id = 191000

    def __init__(self, text: str = ""):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.replies.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="UIFLOWLOCK")
        self.data = data
        self.message = FakeMessage()
        self.edits = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _rows(markup):
    return [[(button.text, button.callback_data) for button in row] for row in markup.inline_keyboard]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _press(user_id: int, callback: str):
    query = FakeQuery(user_id, callback)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.edits
    edit = query.edits[-1]
    return edit["text"], edit.get("reply_markup"), bot.get_video_session(user_id)


def _open(user_id: int, product_id: str):
    bot.clear_video_session(user_id)
    return _press(user_id, f"vproduct|open|{product_id}")


def _run_prompt_to_review(user_id: int):
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    _press(user_id, "vproduct|b14_idea_select|0")
    _press(user_id, "vproduct|asset_skip")
    _press(user_id, "vproduct|asset_skip_confirm")
    return _press(user_id, "vproduct|b14_creative_done")


def _changed_files() -> set[str]:
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        line.strip().replace("\\", "/")
        for line in (tracked.stdout + "\n" + untracked.stdout).splitlines()
        if line.strip() and not line.startswith(".pytest_tmp/")
    }


def _assert_no_provider_or_charge(session):
    draft = session.get("draft") or {}
    assert draft.get("provider_called") is False
    assert draft.get("xu_charged", 0) == 0


def test_videoflow_lock_main_video_menu_buttons_snapshot():
    assert _rows(bot.main_video_keyboard("vi")) == [
        [("🔥 Video theo trend", "vproduct|open|video_trend"), ("🎬 Video AI chân thật", "vproduct|open|video_ai_real")],
        [("🧩 Kịch bản → Video", "vproduct|open|script_image_video"), ("🎞 Ghép ảnh thành video", "vproduct|open|frame_video_local")],
        [("🎥 Tự quay & đổi cảnh AI", "vproduct|open|self_shot_scene_change"), ("🎬 Phim AI nhiều cảnh", "vproduct|open|multi_scene_film")],
        [("🧠 Ý tưởng video", "vproduct|open|video_idea"), ("🎬 Storyboard + Prompt", "vproduct|open|storyboard_prompt")],
        [("📚 Kho prompt video", "vpromptlib|start"), ("📥 Tải video từ link", "vdownload|start")],
        [("🛠 Chỉnh sửa video local", "vproduct|open|video_local_edit"), ("🏠 Menu chính", "menu|main")],
    ]


def test_videoflow_lock_video_ai_entry_buttons_snapshot():
    assert _rows(bot.task3d_product_intro_keyboard("video_ai_real", "vi")) == [
        [("📝 Prompt → Video AI", "vproduct|ai_prompt_menu|video_ai_real"), ("🖼 Ảnh → Video AI", "vproduct|ai_image_menu|video_ai_real")],
        [("🎞 Video mẫu → Video AI", "vproduct|ai_video_menu|video_ai_real"), ("📊 Phân tích video", "menu|hint_video_status")],
        [("⬅️ Menu video", "menu|main_video"), ("🏠 Menu chính", "menu|main")],
    ]


def test_videoflow_lock_video_type_menu_buttons_snapshot():
    rows = _rows(bot.video_b14_profile_selection_keyboard("vi"))
    assert rows[0] == [("📖 Kể chuyện", "vproduct|b14_profile|storytelling"), ("🛒 Review sản phẩm", "vproduct|b14_profile|product_review")]
    assert rows[5] == [("🎧 Chill / lofi / visualizer", "vproduct|b14_profile|lofi_audio_visualizer"), ("🎞 Phim ngắn / trailer", "vproduct|b14_profile|cinematic_trailer")]
    assert rows[-2] == [("🧠 Tự động đề xuất", "vproduct|b14_profile|auto"), ("✍️ Tự nhập ý tưởng", "vproduct|input_text")]
    assert rows[-1] == [("🔙 Quay lại", "vproduct|back"), ("🏠 Menu chính", "menu|main")]


def test_videoflow_lock_style_customization_buttons_snapshot():
    assert _rows(bot.video_b14_creative_controls_keyboard("vi")) == [
        [("🔥 Chủ đề / ngữ cảnh", "vproduct|b14_creative_field|topic_mode"), ("🎨 Màu sắc", "vproduct|b14_creative_field|color_palette")],
        [("🎥 Phong cách", "vproduct|b14_creative_field|visual_style"), ("🎬 Chuyển động", "vproduct|b14_creative_field|camera_motion")],
        [("📷 Góc máy", "vproduct|b14_creative_field|camera_angle"), ("🎞 Nhịp dựng", "vproduct|b14_creative_field|pacing")],
        [("💫 Cảm xúc", "vproduct|b14_creative_field|emotion_tone"), ("🚫 Điều cần tránh", "vproduct|b14_negative_prompt")],
        [("🔄 Đổi phong cách nhanh", "vproduct|b14_creative_field|visual_style"), ("⏭ Dùng mặc định theo profile", "vproduct|b14_creative_default")],
        [("✅ Xem storyboard/prompt", "vproduct|b14_creative_done"), ("📸 Thêm tư liệu", "vproduct|asset_intro")],
        [("🏠 Menu chính", "menu|main")],
    ]


def test_videoflow_lock_add_materials_buttons_snapshot():
    assert _rows(bot.video_asset_intake_keyboard("vi")) == [
        [("🖼 Tạo ảnh AI trước", "vproduct|asset_create_ai_image"), ("📚 Gợi ý bố cục ảnh", "vproduct|asset_layout_ideas")],
        [("🎨 Dùng prompt ảnh từ storyboard", "vproduct|asset_storyboard_prompt"), ("📸 Gửi ảnh nhân vật/sản phẩm", "vproduct|asset_wait|subject")],
        [("🏞 Gửi ảnh bối cảnh", "vproduct|asset_wait|background"), ("🧩 Gửi ảnh storyboard", "vproduct|asset_wait|storyboard")],
        [("🏷 Gửi logo", "vproduct|asset_wait|logo"), ("🎙 Gửi voice/audio", "vproduct|asset_wait|voice")],
        [("🎵 Gửi nhạc nền", "vproduct|asset_wait|music"), ("⏭ Bỏ qua", "vproduct|asset_skip")],
        [("✅ Xong phần tư liệu", "vproduct|asset_done")],
        [("🔙 Quay lại", "vproduct|b14_profile_back"), ("🏠 Menu chính", "menu|main")],
    ]


def test_videoflow_lock_no_dead_video_callbacks():
    callbacks = []
    for markup in (
        bot.main_video_keyboard("vi"),
        bot.task3d_product_intro_keyboard("video_ai_real", "vi"),
        bot.video_b14_profile_selection_keyboard("vi"),
        bot.video_b14_creative_controls_keyboard("vi"),
        bot.video_asset_intake_keyboard("vi"),
    ):
        callbacks.extend(_callbacks(markup))
    allowed_prefixes = ("vproduct|", "menu|", "vpromptlib|", "vdownload|")
    assert callbacks
    assert all(callback.startswith(allowed_prefixes) for callback in callbacks)
    assert "def handle_video_product_callback" in Path(ROOT / "bot.py").read_text(encoding="utf-8")


def test_videoflow_lock_prompt_to_video_sequence():
    user_id = 191101
    _open(user_id, "video_ai_real")
    assert bot.get_video_session(user_id)["current_step"] == "intro"
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    assert bot.get_video_session(user_id)["current_step"] == "ai_prompt_menu"
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    assert bot.get_video_session(user_id)["current_step"] == "suggest_prompt"
    _press(user_id, "vproduct|microflow_choose|0")
    assert bot.get_video_session(user_id)["current_step"] == "profile_select"
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    assert bot.get_video_session(user_id)["current_step"] == "idea_suggestions"
    _press(user_id, "vproduct|b14_idea_select|0")
    assert bot.get_video_session(user_id)["current_step"] == "asset_intake"
    _press(user_id, "vproduct|asset_skip")
    _press(user_id, "vproduct|asset_skip_confirm")
    assert bot.get_video_session(user_id)["current_step"] == "b14_creative_controls"
    _press(user_id, "vproduct|b14_creative_done")
    assert bot.get_video_session(user_id)["current_step"] == "storyboard_preview"


def test_videoflow_lock_image_to_video_sequence():
    user_id = 191102
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_image_menu|video_ai_real")
    text, markup, session = _press(user_id, "vproduct|suggest_image|video_ai_real")
    assert session["current_step"] == "suggest_image"
    assert "Gợi ý ảnh" in text or "Gợi ý tạo ảnh" in text
    assert "vproduct|microflow_choose|0" in _callbacks(markup)


def test_videoflow_lock_video_reference_sequence():
    user_id = 191103
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_video_menu|video_ai_real")
    text, markup, session = _press(user_id, "vproduct|suggest_video|video_ai_real")
    assert session["current_step"] == "suggest_video"
    assert "Gợi ý cách làm video" in text or "Gợi ý tạo video" in text
    assert "vproduct|microflow_choose|0" in _callbacks(markup)


def test_videoflow_lock_type_selection_sequence():
    user_id = 191104
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    text, _markup, session = _press(user_id, "vproduct|b14_profile|product_review")
    assert session["current_step"] == "idea_suggestions"
    assert "Gợi ý ý tưởng cho" in text
    assert "Review sản phẩm" in text


def test_videoflow_lock_short_film_trailer_sequence():
    user_id = 191105
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    text, _markup, session = _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    assert session["current_step"] == "idea_suggestions"
    assert "Phim ngắn / trailer" in text


def test_videoflow_lock_add_materials_not_skipped():
    user_id = 191106
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    text, _markup, session = _press(user_id, "vproduct|b14_idea_select|0")
    assert session["current_step"] == "asset_intake"
    assert "Muốn video sát ý hơn" in text


def test_videoflow_lock_review_before_confirm():
    text, markup, session = _run_prompt_to_review(191107)
    assert session["current_step"] == "storyboard_preview"
    assert "Storyboard" in text
    assert "vproduct|storyboard_confirm" in _callbacks(markup)


def test_videoflow_lock_back_from_type_suggestion():
    user_id = 191201
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "suggest_prompt"
    assert "Gợi ý prompt video" in text


def test_videoflow_lock_back_from_profile_suggestion():
    user_id = 191202
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    text, _markup, session = _press(user_id, "vproduct|back")
    assert session["current_step"] == "profile_select"
    assert "Chọn loại video" in text


def test_videoflow_lock_back_from_style_customization():
    user_id = 191203
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    _press(user_id, "vproduct|b14_idea_select|0")
    _press(user_id, "vproduct|asset_skip")
    _press(user_id, "vproduct|asset_skip_confirm")
    text, _markup, session = _press(user_id, "vproduct|asset_intro")
    assert session["current_step"] == "asset_intake"
    assert "Muốn video sát ý hơn" in text


def test_videoflow_lock_back_from_add_materials():
    user_id = 191204
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    _press(user_id, "vproduct|b14_idea_select|0")
    text, _markup, session = _press(user_id, "vproduct|b14_profile_back")
    assert session["current_step"] == "idea_suggestions"
    assert "Gợi ý ý tưởng cho" in text


def test_videoflow_lock_back_from_review():
    text, _markup, session = _run_prompt_to_review(191205)
    assert session["current_step"] == "storyboard_preview"
    text, _markup, session = _press(191205, "vproduct|b14_creative_screen")
    assert session["current_step"] == "b14_creative_controls"
    assert "Tùy chỉnh phong cách video" in text


def test_videoflow_lock_menu_video_returns_video_menu():
    callbacks = _callbacks(bot.task3d_product_intro_keyboard("video_ai_real", "vi"))
    assert "menu|main_video" in callbacks
    assert "Video TOAN AAS" in bot.menu_text_main_video()


def test_videoflow_lock_menu_main_returns_main_menu():
    for markup in (bot.main_video_keyboard("vi"), bot.video_asset_intake_keyboard("vi")):
        assert "menu|main" in _callbacks(markup)


def test_videoflow_lock_add_materials_all_buttons_present():
    labels = _labels(bot.video_asset_intake_keyboard("vi"))
    assert "📷 Tôi có ảnh sẵn" not in labels
    for expected in (
        "🖼 Tạo ảnh AI trước",
        "📚 Gợi ý bố cục ảnh",
        "🎨 Dùng prompt ảnh từ storyboard",
        "📸 Gửi ảnh nhân vật/sản phẩm",
        "🏞 Gửi ảnh bối cảnh",
        "🧩 Gửi ảnh storyboard",
        "🏷 Gửi logo",
        "🎙 Gửi voice/audio",
        "🎵 Gửi nhạc nền",
        "⏭ Bỏ qua",
        "✅ Xong phần tư liệu",
        "🔙 Quay lại",
        "🏠 Menu chính",
    ):
        assert expected in labels


def test_videoflow_lock_add_materials_skip_explicit_only():
    user_id = 191301
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    _press(user_id, "vproduct|b14_idea_select|0")
    text, markup, session = _press(user_id, "vproduct|asset_done")
    assert session["current_step"] == "asset_intake"
    assert any("Tiếp tục không ảnh" in label for label in _labels(markup))
    assert "bỏ qua ảnh tư liệu" in text.lower()


def test_videoflow_lock_add_materials_done_goes_review():
    user_id = 191302
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    _press(user_id, "vproduct|b14_idea_select|0")
    _press(user_id, "vproduct|asset_skip")
    _press(user_id, "vproduct|asset_skip_confirm")
    text, _markup, session = _press(user_id, "vproduct|b14_creative_done")
    assert session["current_step"] == "storyboard_preview"
    assert "Storyboard" in text


def test_videoflow_lock_add_materials_back_exact():
    test_videoflow_lock_back_from_add_materials()


def test_videoflow_lock_planning_copy_no_file_created():
    for text in (
        bot.task3d_public_copy("video_ai_real", "vi"),
        bot.video_microflow_text("ai_prompt_menu", "video_ai_real", {}, "vi"),
        bot.video_b14_profile_selection_text({}, 0, "vi"),
    ):
        assert "chưa tạo file thật" in text


def test_videoflow_lock_planning_copy_no_xu_charged():
    for text in (
        bot.task3d_public_copy("video_ai_real", "vi"),
        bot.video_microflow_text("ai_prompt_menu", "video_ai_real", {}, "vi"),
        bot.video_b14_profile_selection_text({}, 0, "vi"),
    ):
        assert "chưa trừ Xu" in text


def test_videoflow_lock_no_provider_submit_from_planning_callbacks():
    user_id = 191401
    _open(user_id, "video_ai_real")
    for callback in (
        "vproduct|ai_prompt_menu|video_ai_real",
        "vproduct|suggest_prompt|video_ai_real",
        "vproduct|microflow_choose|0",
        "vproduct|b14_profile|cinematic_trailer",
        "vproduct|b14_idea_select|0",
        "vproduct|asset_skip",
        "vproduct|asset_skip_confirm",
        "vproduct|b14_creative_done",
    ):
        _press(user_id, callback)
        _assert_no_provider_or_charge(bot.get_video_session(user_id))


def test_videoflow_lock_hot_trend_untouched():
    rows = _rows(bot.task3d_product_intro_keyboard("video_trend", "vi"))
    assert rows == [
        [("🔥 Gợi ý trend hot", "vproduct|trend_today"), ("✍️ Tự nhập trend/ý tưởng", "vproduct|trend_custom")],
        [("⬅️ Menu video", "menu|main_video"), ("🏠 Menu chính", "menu|main")],
    ]
    assert bot.VIDEO_STEP_BACK_MATRIX["video_trend"]["asset_intake"] == "idea_suggestions"


def test_videoflow_lock_img2vid_untouched():
    callbacks = _callbacks(bot.task3d_product_intro_keyboard("frame_video_local", "vi"))
    assert "framevideo|start" in callbacks
    assert "framevideo|ai_first" in callbacks
    assert "vproduct|b14_profile|auto" not in callbacks


def test_videoflow_lock_no_music_changes():
    assert not any(path.startswith("services/music") or "suno" in path.lower() for path in _changed_files())


def test_videoflow_lock_no_product_video_provider_changes():
    forbidden = ("services/video_provider_router.py", "services/video_real_render_connector.py", "providers/video_generic_http_provider.py")
    assert not (set(forbidden) & _changed_files())


def test_videoflow_lock_no_storyboard_engine_changes():
    assert not any("storyboard" in path.lower() and not path.startswith("tests/") for path in _changed_files())


def test_videoflow_lock_no_subdub_changes():
    assert not any("subdub" in path.lower() or "subtitle_dub" in path.lower() for path in _changed_files())


def test_videoflow_lock_no_voice_changes():
    assert not any("voice" in path.lower() and not path.startswith("tests/") for path in _changed_files())


def test_videoflow_lock_no_payos_pricing_db_webhook_changes():
    joined = " ".join(_changed_files()).lower()
    for forbidden in ("payos", "wallet", "pricing_matrix", "migrations", "webhook"):
        assert forbidden not in joined
