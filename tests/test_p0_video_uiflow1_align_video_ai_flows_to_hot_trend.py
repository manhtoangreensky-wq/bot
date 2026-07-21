import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import bot


_CONTEXTS = {}


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
    context = _CONTEXTS.setdefault(user_id, SimpleNamespace(user_data={}))
    handler = bot.handle_video_profile_studio_callback if callback.startswith("vprofile|") else bot.handle_video_product_callback
    asyncio.run(handler(SimpleNamespace(callback_query=query), context))
    assert query.edits
    edit = query.edits[-1]
    return edit["text"], edit.get("reply_markup"), bot.get_video_session(user_id)


def _open(user_id: int, product_id: str):
    bot.clear_video_session(user_id)
    _CONTEXTS[user_id] = SimpleNamespace(user_data={})
    return _press(user_id, f"vproduct|open|{product_id}")


def _scene2_state(user_id: int):
    return bot.video_profile_studio_state(_CONTEXTS[user_id])


def _scene2_profile_id():
    return str(bot.profile_router.STUDIO_PROFILE_OPTIONS[0]["selection_id"])


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
    assert "✍️ Tự nhập trend" in labels
    assert "🗂 Ý tưởng video có sẵn" in labels
    assert "vproduct|trend_today" in callbacks
    assert "vproduct|trend_custom" in callbacks
    assert "video_trend" in bot.VIDEO_SCENE2_PUBLIC_PRODUCTS
    assert bot.VIDEO_SCENE2_CANONICAL_STEPS[:3] == ("subject", "scene_count", "profile")


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
    assert session["current_step"] == "scene2_scene_count"
    assert _scene2_state(user_id)["step"] == "scene_count"
    assert not session.get("package_id")
    assert "b14_quality_xu" not in session["draft"]
    assert session["draft"]["provider_called"] is False
    assert session["draft"]["xu_charged"] == 0

    text, markup, _session = _press(user_id, "vprofile|count|2")
    assert _scene2_state(user_id)["step"] == "profile"
    assert "Chọn profile phù hợp" in text
    assert f"vprofile|select|{_scene2_profile_id()}" in _callbacks(markup)


def test_uiflow1_realistic_video_prompt_flow_reaches_add_materials_then_review():
    user_id = 190002
    _open(user_id, "video_ai_real")
    _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
    _press(user_id, "vproduct|suggest_prompt|video_ai_real")
    _press(user_id, "vproduct|microflow_choose|0")
    _press(user_id, "vprofile|count|2")
    _press(user_id, f"vprofile|select|{_scene2_profile_id()}")
    _press(user_id, "vprofile|context|1")
    text, markup, _session = _press(user_id, "vprofile|requirements_skip")
    assert _scene2_state(user_id)["step"] == "reference_assets"
    assert "Tư liệu nhận diện" in text
    assert "vprofile|assets|none" in _callbacks(markup)

    _press(user_id, "vprofile|assets|none")
    text, _markup, _session = _press(user_id, "vprofile|build")
    assert _scene2_state(user_id)["step"] == "scene_plan"
    assert "Kế hoạch" in text or "cảnh" in text


def test_uiflow1_each_video_type_routes_to_profile_specific_suggestion():
    profile_ids = [str(item["selection_id"]) for item in bot.profile_router.STUDIO_PROFILE_OPTIONS]
    for index, profile_id in enumerate(profile_ids, start=1):
        user_id = 190100 + index
        _open(user_id, "video_ai_real")
        _press(user_id, "vproduct|ai_prompt_menu|video_ai_real")
        _press(user_id, "vproduct|suggest_prompt|video_ai_real")
        _press(user_id, "vproduct|microflow_choose|0")
        _press(user_id, "vprofile|count|2")
        text, markup, _session = _press(user_id, f"vprofile|select|{profile_id}")
        assert _scene2_state(user_id)["step"] == "profile_context"
        assert "hướng nội dung theo profile" in text
        assert "vprofile|context|1" in _callbacks(markup)


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
        text, markup, session = _press(user_id, "vprofile|count|2")
        assert session["product_id"] == product_id
        assert _scene2_state(user_id)["step"] == "profile"
        assert "Chọn profile phù hợp" in text
        assert f"vprofile|select|{_scene2_profile_id()}" in _callbacks(markup)
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
    text, markup, session = _press(user_id, "vproduct|storyboard_continue_profile")
    assert session["current_step"] == "scene2_scene_count"
    assert _scene2_state(user_id)["step"] == "scene_count"
    assert "Gói hiện tại" not in text
    assert "vprofile|count|2" in _callbacks(markup)


def test_uiflow1_back_matrix_for_aligned_products():
    assert bot.VIDEO_SCENE2_CANONICAL_STEPS == (
        "subject", "scene_count", "profile", "profile_context", "requirements",
        "content_addons", "scene_plan", "prompt_review", "postproduction_addons",
        "quality_price", "final_report", "final_confirm",
    )


def test_uiflow1_no_provider_submit_or_charge_from_planning_callbacks():
    user_id = 190401
    _open(user_id, "video_ai_real")
    for callback in (
        "vproduct|ai_prompt_menu|video_ai_real",
        "vproduct|suggest_prompt|video_ai_real",
        "vproduct|microflow_choose|0",
        "vprofile|count|2",
        f"vprofile|select|{_scene2_profile_id()}",
        "vprofile|context|1",
        "vprofile|requirements_skip",
        "vprofile|assets|none",
        "vprofile|build",
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
