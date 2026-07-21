import asyncio
from types import SimpleNamespace

import bot


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.chat_id = 280000
        self.message_id = 700
        self.replies = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.replies.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, user_id, data):
        self.from_user = SimpleNamespace(id=user_id, first_name="SCENE2")
        self.data = data
        self.message = FakeMessage()
        self.edits = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _context():
    return SimpleNamespace(user_data={})


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if getattr(button, "callback_data", None)
    ]


def _press_product(user_id, context, callback):
    query = FakeQuery(user_id, callback)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), context))
    assert query.edits
    return query.edits[-1], bot.get_video_session(user_id), bot.video_profile_studio_state(context)


def _press_profile(user_id, context, callback):
    query = FakeQuery(user_id, callback)
    asyncio.run(bot.handle_video_profile_studio_callback(SimpleNamespace(callback_query=query), context))
    assert query.edits
    return query.edits[-1], bot.get_video_session(user_id), bot.video_profile_studio_state(context)


def _send_profile_text(user_id, context, text):
    message = FakeMessage(text)
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=user_id),
    )
    handled = asyncio.run(bot.handle_video_profile_studio_pending_text(update, context))
    assert handled is True
    assert message.replies
    return message.replies[-1], bot.video_profile_studio_state(context)


def _assert_planning_has_no_side_effect(user_id, context):
    session = bot.get_video_session(user_id)
    draft = dict(session.get("draft") or {})
    state = bot.video_profile_studio_state(context)
    assert not session.get("provider_job_id")
    assert not draft.get("b14_project_id")
    assert not draft.get("provider_called")
    assert not draft.get("job_created")
    assert not draft.get("outbox_created")
    assert draft.get("xu_charged", 0) == 0
    assert state.get("provider_called") is False
    assert state.get("job_created") is False
    assert state.get("outbox_created") is False
    assert state.get("xu_charged", 0) == 0


def _first_profile_id():
    return str(bot.profile_router.STUDIO_PROFILE_OPTIONS[0]["selection_id"])


def test_scene2_actual_product_video_handler_subject_then_scene_then_profile():
    user_id = 280001
    context = _context()
    bot.clear_video_session(user_id)

    _press_product(user_id, context, "vproduct|open|video_ai_real")
    _press_product(user_id, context, "vproduct|ai_prompt_menu|video_ai_real")
    _press_product(user_id, context, "vproduct|suggest_prompt|video_ai_real")
    edit, session, state = _press_product(user_id, context, "vproduct|microflow_choose|0")

    assert state["step"] == "scene_count"
    assert state["subject"]
    assert session["current_step"] == "scene2_scene_count"
    assert "Gói hiện tại" not in edit["text"]
    assert "vprofile|count|2" in _callbacks(edit["reply_markup"])
    assert not session.get("package_id")
    assert "b14_quality_xu" not in session["draft"]

    _edit, _session, state = _press_profile(user_id, context, "vprofile|count|2")
    assert state["step"] == "technical_profile"
    assert state["scene_count"] == 2
    assert state["quality_xu"] == 0
    _assert_planning_has_no_side_effect(user_id, context)


def test_scene2_knowledge1_real_handler_and_boundaries():
    user_id = 280002
    context = _context()
    bot.clear_video_session(user_id)

    _press_profile(user_id, context, "vprofile|menu")
    _press_profile(user_id, context, "vprofile|start")
    edit, state = _send_profile_text(user_id, context, "Giới thiệu căn hộ có nhiều ánh sáng tự nhiên")
    assert state["step"] == "scene_count"
    assert "Gói hiện tại" not in edit["text"]
    assert "vprofile|count|2" in _callbacks(edit["reply_markup"])

    for invalid in (0, 21):
        edit, _session, state = _press_profile(user_id, context, f"vprofile|count|{invalid}")
        assert state["step"] == "scene_count"
        assert state["scene_count"] == 0
        assert "1–20" in edit["text"]

    _edit, _session, state = _press_profile(user_id, context, "vprofile|count|20")
    assert state["step"] == "technical_profile"
    assert state["scene_count"] == 20
    _assert_planning_has_no_side_effect(user_id, context)


def test_scene2_arch1_handoff_enters_scene_count_without_package(monkeypatch):
    user_id = 280003
    context = _context()
    bot.clear_video_session(user_id)
    context.user_data[bot.ARCHITECTURE_PROFILE_SESSION_KEY] = {
        "step": "output",
        "answers": {"user_text": "Walkthrough căn hộ phong cách tối giản", "aspect_ratio": "16:9"},
        "references": [{"file_id": "arch-ref-1", "asset_type": "reference"}],
        "draft": {
            "profile_id": "residential_interior",
            "professional_video_prompt": "A complete residential walkthrough",
            "negative_prompt": "distortion",
            "scene_plan": [{"scene_index": 1, "goal": "entrance"}],
        },
    }
    monkeypatch.setattr(bot.architecture_profile_status, "record_handoff", lambda *args, **kwargs: None)
    query = FakeQuery(user_id, "archprofile|handoff_video")
    asyncio.run(bot.handle_architecture_profile_callback(SimpleNamespace(callback_query=query), context))
    assert query.edits
    edit = query.edits[-1]
    state = bot.video_profile_studio_state(context)
    session = bot.get_video_session(user_id)

    assert state["step"] == "scene_count"
    assert state["source_product_id"] == "video_ai_real"
    assert state["source_fields"]["architecture_video_prompt"]
    assert "Gói hiện tại" not in edit["text"]
    assert not session.get("package_id")
    assert "b14_quality_xu" not in session["draft"]
    _assert_planning_has_no_side_effect(user_id, context)


def test_scene2_stale_legacy_package_and_scene_callbacks_cannot_jump_forward():
    user_id = 280004
    context = _context()
    bot.clear_video_session(user_id)
    stale = bot.default_video_session(user_id)
    stale.update({
        "product_id": "video_ai_real",
        "current_step": "b14_quality",
        "topic": "Video giới thiệu sản phẩm",
        "package_id": "basic",
        "draft": {"topic": "Video giới thiệu sản phẩm", "b14_quality_xu": 300, "selected_tier": "basic"},
    })
    bot.save_video_session(user_id, stale)

    edit, session, state = _press_product(user_id, context, "vproduct|b14_quality|300")
    assert state["step"] == "scene_count"
    assert "Gói hiện tại" not in edit["text"]
    assert not session.get("package_id")
    assert "b14_quality_xu" not in session["draft"]
    assert "selected_tier" not in session["draft"]

    _edit, session, state = _press_product(user_id, context, "vproduct|b14_scene_count|2")
    assert state["step"] == "scene_count"
    assert state["scene_count"] == 0
    assert "b14_quality_xu" not in session["draft"]
    _assert_planning_has_no_side_effect(user_id, context)


def test_scene2_direct_profile_callback_cannot_skip_subject_or_scene_count():
    user_id = 280005
    context = _context()
    bot.clear_video_session(user_id)

    _edit, _session, state = _press_profile(user_id, context, f"vprofile|select|{_first_profile_id()}")
    assert state["step"] == "await_subject"
    assert state.get("scene_count", 0) == 0

    _send_profile_text(user_id, context, "Câu chuyện thương hiệu có mở đầu và kết luận rõ")
    _edit, _session, state = _press_profile(user_id, context, f"vprofile|select|{_first_profile_id()}")
    assert state["step"] == "scene_count"
    assert not state.get("selection_id")
    _assert_planning_has_no_side_effect(user_id, context)


def test_scene2_exact_forward_order_and_back_stack_before_final_confirm():
    user_id = 280006
    context = _context()
    bot.clear_video_session(user_id)
    bot.start_public_video_scene2_state(
        context,
        user_id,
        "video_ai_real",
        origin_step="test_public_subject",
        topic="Một câu chuyện sản phẩm hoàn chỉnh",
    )

    _press_profile(user_id, context, "vprofile|count|2")
    assert bot.video_profile_studio_state(context)["step"] == "technical_profile"
    _press_profile(user_id, context, "vprofile|back")
    assert bot.video_profile_studio_state(context)["step"] == "scene_count"
    _press_profile(user_id, context, "vprofile|count|2")

    _press_profile(user_id, context, f"vprofile|select|{_first_profile_id()}")
    assert bot.video_profile_studio_state(context)["step"] == "suggestion"
    _press_profile(user_id, context, "vprofile|back")
    assert bot.video_profile_studio_state(context)["step"] == "technical_profile"
    _press_profile(user_id, context, f"vprofile|select|{_first_profile_id()}")

    _press_profile(user_id, context, "vprofile|suggest|1")
    assert bot.video_profile_studio_state(context)["step"] == "requirements"
    _press_profile(user_id, context, "vprofile|req_done")
    assert bot.video_profile_studio_state(context)["step"] == "materials"
    _press_profile(user_id, context, "vprofile|material_done")
    assert bot.video_profile_studio_state(context)["step"] == "creative_controls"
    _press_profile(user_id, context, "vprofile|creative_done")
    assert bot.video_profile_studio_state(context)["step"] == "content_addons"
    _press_profile(user_id, context, "vprofile|back")
    assert bot.video_profile_studio_state(context)["step"] == "creative_controls"
    _press_profile(user_id, context, "vprofile|creative_done")

    _press_profile(user_id, context, "vprofile|content_done")
    assert bot.video_profile_studio_state(context)["step"] == "scene_plan"
    _press_profile(user_id, context, "vprofile|scene_done")
    assert bot.video_profile_studio_state(context)["step"] == "image_strategy"
    _press_profile(user_id, context, "vprofile|image_strategy_done")
    assert bot.video_profile_studio_state(context)["step"] == "image_prompts"
    _press_profile(user_id, context, "vprofile|image_prompt_done")
    assert bot.video_profile_studio_state(context)["step"] == "video_prompts"
    _press_profile(user_id, context, "vprofile|video_prompt_done")
    assert bot.video_profile_studio_state(context)["step"] == "transitions"
    _press_profile(user_id, context, "vprofile|transitions_done")
    assert bot.video_profile_studio_state(context)["step"] == "full_review"
    _press_profile(user_id, context, "vprofile|review_done")
    assert bot.video_profile_studio_state(context)["step"] == "post_addons"
    _press_profile(user_id, context, "vprofile|post_done")
    assert bot.video_profile_studio_state(context)["step"] == "aspect_ratio"
    _press_profile(user_id, context, "vprofile|ratio|9x16")
    assert bot.video_profile_studio_state(context)["step"] == "quality"
    _press_profile(user_id, context, "vprofile|tier|300")
    assert bot.video_profile_studio_state(context)["step"] == "final_report"
    _press_profile(user_id, context, "vprofile|handoff")
    assert bot.video_profile_studio_state(context)["step"] == "final_confirmation"
    _assert_planning_has_no_side_effect(user_id, context)

    _press_profile(user_id, context, "vprofile|invoice_back")
    assert bot.video_profile_studio_state(context)["step"] == "final_report"
    _press_profile(user_id, context, "vprofile|back")
    assert bot.video_profile_studio_state(context)["step"] == "quality"


def test_scene2_contract_owns_all_product_planners_but_not_img2vid_or_aiedit():
    assert bot.VIDEO_SCENE2_CANONICAL_STEPS == (
        "subject", "scene_count", "technical_profile", "suggestion",
        "requirements", "materials", "creative_controls", "content_addons", "scene_plan",
        "image_strategy", "image_prompts", "video_prompts", "transitions", "full_review", "post_addons",
        "aspect_ratio", "quality", "final_report", "final_confirmation",
    )
    assert bot.VIDEO_SCENE2_PUBLIC_PRODUCTS == {
        "video_trend", "video_ai_real", "script_image_video", "self_shot_scene_change",
        "video_idea", "storyboard_prompt", "multi_scene_film",
    }
    assert "frame_video_local" not in bot.VIDEO_SCENE2_PUBLIC_PRODUCTS
    assert "video_ai_edit" not in bot.VIDEO_SCENE2_PUBLIC_PRODUCTS
    assert bot.video_profile_scene1_count_keyboard("vi").inline_keyboard[0][1].callback_data == "vprofile|count|2"


def test_scene2_trend_selfshot_and_video_idea_actual_handoffs_cannot_bypass_scene_count():
    # Trend selection is a real public callback handoff.
    trend_user = 280007
    trend_context = _context()
    bot.clear_video_session(trend_user)
    bot.task3d_session_step(
        trend_user,
        "trend_ideas",
        product_id="video_trend",
        trend_ideas=[{"title": "Xu hướng kể chuyện sản phẩm", "summary": "Một mạch nội dung rõ"}],
        provider_called=False,
        xu_charged=0,
    )
    edit, session, state = _press_product(trend_user, trend_context, "vproduct|trend_select|0")
    assert state["step"] == "scene_count"
    assert session["current_step"] == "scene2_scene_count"
    assert "Gói hiện tại" not in edit["text"]

    # Self-shot keeps its supplied source media but scene count still precedes profile.
    selfshot_user = 280008
    selfshot_context = _context()
    bot.clear_video_session(selfshot_user)
    session = bot.video_microflow_store_options(
        selfshot_user,
        product_id="self_shot_scene_change",
        step="selfshot_ideas",
        kind="selfshot",
        topic="Đổi cảnh cho video tự quay",
        scene_count=2,
    )
    draft = dict(session.get("draft") or {})
    draft["source_media_ref"] = "selfshot-video"
    draft["source_media_refs"] = ["selfshot-video"]
    session["draft"] = draft
    bot.save_video_session(selfshot_user, session)
    edit, _session, state = _press_product(selfshot_user, selfshot_context, "vproduct|microflow_choose|0")
    assert state["step"] == "scene_count"
    assert state["assets"]["source_product_id"] == "self_shot_scene_change"
    assert "Gói hiện tại" not in edit["text"]

    # Video Idea may choose a target product first, but its first target planning
    # action must still enter SCENE2 rather than package/profile legacy screens.
    idea_user = 280009
    idea_context = _context()
    bot.clear_video_session(idea_user)
    bot.video_microflow_store_options(
        idea_user,
        product_id="video_idea",
        step="idea_suggestions",
        kind="video_idea",
        topic="Video thương hiệu gần gũi",
        scene_count=2,
    )
    _press_product(idea_user, idea_context, "vproduct|microflow_choose|0")
    _press_product(idea_user, idea_context, "vproduct|idea_develop|video_ai_real")
    edit, session, state = _press_product(idea_user, idea_context, "vproduct|ideas|video_ai_real")
    assert state["step"] == "scene_count"
    assert session["current_step"] == "scene2_scene_count"
    assert "Gói hiện tại" not in edit["text"]

    for user_id, context in (
        (trend_user, trend_context),
        (selfshot_user, selfshot_context),
        (idea_user, idea_context),
    ):
        _assert_planning_has_no_side_effect(user_id, context)


def test_scene2_callback_registration_is_unique():
    source = open(bot.__file__, encoding="utf-8").read()
    assert source.count("CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r\"^vprofile\\|\")") == 1
    assert source.count("CallbackQueryHandler(handle_video_product_callback, pattern=r\"^vproduct\\|(?!b14_confirm") == 1
