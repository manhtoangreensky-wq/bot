import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import bot


class FakeMessage:
    chat_id = 190000

    def __init__(self, text: str = ""):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.replies.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="UIFLOW1")
        self.data = data
        self.message = FakeMessage()
        self.edits = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _press(user_id: int, callback: str):
    query = FakeQuery(user_id, callback)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.edits
    edit = query.edits[-1]
    return edit["text"], edit.get("reply_markup"), bot.get_video_session(user_id)


def _open(user_id: int, product_id: str):
    bot.clear_video_session(user_id)
    return _press(user_id, f"vproduct|open|{product_id}")


def _changed_files():
    repo = Path(__file__).resolve().parents[1]
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        line.strip().replace("\\", "/")
        for line in (tracked.stdout + "\n" + untracked.stdout).splitlines()
        if line.strip()
    }


def test_uiflow1_canonical_flow_map_exists():
    flow_map = bot.video_uiflow1_canonical_flow_map()
    assert flow_map["canonical_reference"] == "video_trend"
    assert "add_materials" in flow_map["sequence"]
    assert "profile_context_suggestion" in flow_map["sequence"]
    assert "type_specific_suggestion" in flow_map["sequence"]
    assert "storyboard_prompt_review" in flow_map["sequence"]
    assert flow_map["must_include"]["review_before_confirm"] is True
    assert "frame_video_local" in flow_map["excluded_products"]
    assert flow_map["provider_calls_allowed"] is False
    assert flow_map["charge_allowed"] is False


def test_uiflow1_hot_trend_flow_locked():
    labels = _labels(bot.task3d_product_intro_keyboard("video_trend", "vi"))
    callbacks = _callbacks(bot.task3d_product_intro_keyboard("video_trend", "vi"))
    assert "🔥 Gợi ý trend hot" in labels
    assert "✍️ Tự nhập trend/ý tưởng" in labels
    assert "vproduct|trend_today" in callbacks
    assert "vproduct|trend_custom" in callbacks
    assert bot.VIDEO_STEP_BACK_MATRIX["video_trend"]["profile_select"] == "trend_ideas"
    assert bot.VIDEO_STEP_BACK_MATRIX["video_trend"]["idea_suggestions"] == "profile_select"
    assert bot.VIDEO_STEP_BACK_MATRIX["video_trend"]["asset_intake"] == "idea_suggestions"
    assert bot.VIDEO_STEP_BACK_MATRIX["video_trend"]["storyboard_preview"] == "b14_creative_controls"


def test_uiflow1_img2vid_untouched():
    callbacks = _callbacks(bot.task3d_product_intro_keyboard("frame_video_local", "vi"))
    assert "framevideo|start" in callbacks
    assert "framevideo|ai_first" in callbacks
    assert "vproduct|b14_profile|auto" not in callbacks
    assert "frame_video_local" not in bot.VIDEO_UIFLOW1_CANONICAL_PROFILE_PRODUCTS


def test_uiflow1_realistic_video_prompt_suggestion_no_jump_to_style():
    user_id = 190001
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    text, markup, session = _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    assert session["current_step"] == "suggest_prompt"
    assert "Gợi ý prompt video" in text
    assert "vproduct|microflow_choose|0" in _callbacks(markup)

    _press(user_id, "vproduct|microflow_choose|0")
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "profile_select"
    assert session["draft"]["provider_called"] is False
    assert session["draft"]["xu_charged"] == 0

    text, markup, session = _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    assert session["current_step"] == "idea_suggestions"
    assert "Gợi ý ý tưởng cho" in text
    assert "Phim ngắn / trailer" in text
    assert "Tùy chỉnh phong cách video" not in text
    assert "vproduct|b14_idea_select|0" in _callbacks(markup)


def test_uiflow1_realistic_video_prompt_flow_reaches_add_materials_then_review():
    user_id = 190002
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    _press(user_id, "vproduct|b14_profile|cinematic_trailer")
    text, markup, session = _press(user_id, "vproduct|b14_idea_select|0")
    assert session["current_step"] == "asset_intake"
    assert "Muốn video sát ý hơn" in text
    assert "📷 Tôi có ảnh sẵn" not in _labels(markup)
    for expected in (
        "🖼 Tạo ảnh AI trước",
        "📚 Gợi ý bố cục ảnh",
        "🎨 Dùng prompt ảnh từ storyboard",
        "⏭ Bỏ qua",
        "✅ Xong phần tư liệu",
    ):
        assert expected in _labels(markup)

    text, _markup, session = _press(user_id, "vproduct|b14_profile_back")
    assert session["current_step"] == "idea_suggestions"
    assert "Gợi ý ý tưởng cho" in text

    _press(user_id, "vproduct|b14_idea_select|0")
    _press(user_id, "vproduct|asset_skip")
    text, _markup, session = _press(user_id, "vproduct|asset_skip_confirm")
    assert session["current_step"] == "b14_creative_controls"
    assert "Tùy chỉnh phong cách video" in text

    text, _markup, session = _press(user_id, "vproduct|b14_creative_done")
    assert session["current_step"] == "storyboard_preview"
    assert "Storyboard" in text


def test_uiflow1_each_video_type_routes_to_profile_specific_suggestion():
    profile_ids = [profile_id for _label, profile_id in bot.VIDEO_B14_3_PROFILE_BUTTONS]
    for index, profile_id in enumerate(profile_ids, start=1):
        user_id = 190100 + index
        _open(user_id, "video_ai_real")
        _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
        _press(user_id, "vproduct|suggest_prompt|video_ai_real")
        _press(user_id, "vproduct|microflow_choose|0")
        text, markup, session = _press(user_id, f"vproduct|b14_profile|{profile_id}")
        assert session["current_step"] == "idea_suggestions"
        assert "Gợi ý ý tưởng cho" in text
        assert bot.video_b14_profile_button_label(profile_id).split(" ", 1)[-1] in text
        assert "vproduct|b14_idea_select|0" in _callbacks(markup)


def test_uiflow1_non_img2vid_products_reach_add_materials_after_profile_suggestion():
    product_callbacks = {
        "video_ai_real": ("vproduct|ai_prompt_menu|video_ai_real", "vproduct|suggest_prompt|video_ai_real"),
        "script_image_video": (None, "vproduct|script_ideas|script_image_video"),
        "multi_scene_film": (None, "vproduct|film_story|multi_scene_film"),
    }
    for offset, (product_id, callbacks) in enumerate(product_callbacks.items(), start=1):
        user_id = 190200 + offset
        _open(user_id, product_id)
        parent, suggestion = callbacks
        if parent:
            _press(user_id, parent)
        _press(user_id, suggestion)
        _press(user_id, "vproduct|microflow_choose|0")
        _press(user_id, "vproduct|b14_profile|product_review")
        text, _markup, session = _press(user_id, "vproduct|b14_idea_select|0")
        assert session["product_id"] == product_id
        assert session["current_step"] == "asset_intake"
        assert "Muốn video sát ý hơn" in text
        assert session["draft"]["provider_called"] is False
        assert session["draft"]["xu_charged"] == 0


def test_uiflow1_storyboard_requires_asset_step_before_b14_review():
    user_id = 190301
    _open(user_id, "storyboard_prompt")
    text, markup, session = _press(user_id, "vproduct|storyboard_suggest|storyboard_prompt")
    assert session["current_step"] == "storyboard_idea"
    assert "Gợi ý storyboard" in text
    assert "vproduct|microflow_choose|0" in _callbacks(markup)

    _press(user_id, "vproduct|microflow_choose|0")
    assert bot.get_video_session(user_id)["current_step"] == "storyboard_suggestion_scene_count"
    text, markup, session = _press(user_id, "vproduct|storyboard_scene_count|4")
    assert session["current_step"] == "storyboard_image_scenes"
    assert "Storyboard ảnh/prompt ảnh" in text
    assert "vproduct|storyboard_use" in _callbacks(markup)

    _press(user_id, "vproduct|storyboard_use")
    _press(user_id, "vproduct|storyboard_video_duration|5")
    _press(user_id, "vproduct|storyboard_continue_profile")
    _press(user_id, "vproduct|b14_profile|storytelling")
    text, _markup, session = _press(user_id, "vproduct|b14_idea_select|0")
    assert session["current_step"] == "asset_intake"
    assert "Muốn video sát ý hơn" in text


def test_uiflow1_back_matrix_for_aligned_products():
    for product_id in bot.VIDEO_UIFLOW1_CANONICAL_PROFILE_PRODUCTS:
        matrix = bot.VIDEO_STEP_BACK_MATRIX[product_id]
        assert matrix["idea_suggestions"] == "profile_select"
        assert matrix["asset_intake"] == "idea_suggestions"
        assert matrix["b14_creative_controls"] == "asset_intake"
        assert matrix["storyboard_preview"] == "b14_creative_controls"


def test_uiflow1_no_provider_submit_or_charge_from_planning_callbacks():
    user_id = 190401
    _open(user_id, "video_ai_real")
    for callback in (
        "vproduct|ai_prompt_menu|video_ai_real",
        "vproduct|suggest_prompt|video_ai_real",
        "vproduct|microflow_choose|0",
        "vproduct|b14_profile|product_review",
        "vproduct|b14_idea_select|0",
        "vproduct|asset_skip",
        "vproduct|asset_skip_confirm",
        "vproduct|b14_creative_done",
    ):
        _press(user_id, callback)
        session = bot.get_video_session(user_id)
        assert session["draft"].get("provider_called") is False
        assert session["draft"].get("xu_charged", 0) == 0


def test_uiflow1_scope_only_bot_and_tests():
    changed = _changed_files()
    assert "bot.py" in changed
    assert changed & {
        "tests/test_p0_video_uiflow1_align_video_ai_flows_to_hot_trend.py",
        "tests/test_p0_video_uiflow_lock_current_good_flow.py",
    }
    forbidden_prefixes = (
        "providers/",
        "services/subtitle",
        "services/music",
        "services/voice",
        "services/payment",
        "local_worker.py",
        "remote_worker.py",
        "video_image_to_video_flow.py",
    )
    for path in changed:
        assert not path.startswith(forbidden_prefixes), path
