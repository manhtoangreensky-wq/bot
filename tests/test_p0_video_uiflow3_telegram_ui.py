from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot
from services import video_uiflow3


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")

CREATION_PRODUCTS = tuple(video_uiflow3.ENTRY_ADAPTERS)


class FakeQuery:
    def __init__(self, user_id: int, data: str, query_id: str = "query-1") -> None:
        self.data = data
        self.id = query_id
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id)
        self.edits: list[dict] = []
        self.answers: list[dict] = []

    async def answer(self, text: str | None = None, **kwargs) -> None:
        self.answers.append({"text": text, **kwargs})

    async def edit_message_text(self, text: str, **kwargs) -> None:
        self.edits.append({"text": text, **kwargs})


class FakeMessage:
    def __init__(self, *, message_id: int, text: str = "", photo=None, document=None, video=None) -> None:
        self.message_id = message_id
        self.text = text
        self.photo = list(photo or [])
        self.document = document
        self.video = video
        self.animation = None
        self.audio = None
        self.voice = None
        self.replies: list[dict] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append({"text": text, **kwargs})


def _click(context, user_id: int, data: str, query_id: str) -> FakeQuery:
    query = FakeQuery(user_id, data, query_id)
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=query), context))
    return query


def _send_text(context, user_id: int, text: str, message_id: int) -> FakeMessage:
    message = FakeMessage(message_id=message_id, text=text)
    handled = asyncio.run(bot.handle_video_uiflow3_pending_text(
        SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)),
        context,
    ))
    assert handled is True
    return message


def _send_photo(context, user_id: int, file_id: str, unique_id: str, message_id: int) -> FakeMessage:
    media = SimpleNamespace(
        file_id=file_id,
        file_unique_id=unique_id,
        file_size=1234,
        width=720,
        height=1280,
    )
    message = FakeMessage(message_id=message_id, photo=[media])
    handled = asyncio.run(bot.handle_video_uiflow3_pending_media(
        SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)),
        context,
    ))
    assert handled is True
    return message


def _send_video(context, user_id: int, file_id: str, unique_id: str, message_id: int) -> FakeMessage:
    media = SimpleNamespace(
        file_id=file_id,
        file_unique_id=unique_id,
        file_size=4321,
        mime_type="video/mp4",
        file_name="source.mp4",
        duration=8,
        width=720,
        height=1280,
    )
    message = FakeMessage(message_id=message_id, video=media)
    handled = asyncio.run(bot.handle_video_uiflow3_pending_media(
        SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)),
        context,
    ))
    assert handled is True
    return message


def _rows(markup) -> list[list[tuple[str, str]]]:
    return [
        [(button.text, button.callback_data) for button in row]
        for row in markup.inline_keyboard
    ]


def _callbacks(markup) -> list[str]:
    return [callback for row in _rows(markup) for _label, callback in row if callback]


def _locked_state() -> dict:
    state = video_uiflow3.new_state("video_ai_real", draft_id="telegram-ui")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=24)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Lan va Minh gioi thieu san pham.",
        approved_brief={
            "title": "Gioi thieu",
            "needs_characters": True,
            "needs_locations": True,
            "needs_dialogue": True,
            "needs_voice": True,
        },
    )
    return video_uiflow3.lock_content(state)


def test_public_menu_routes_seven_creation_products_to_vid3_and_keeps_idea_as_catalog() -> None:
    for product in CREATION_PRODUCTS:
        route = bot.VIDEO_PUBLIC_ROUTE_MATRIX[product]
        assert route["entry_callback"] == f"vid3|entry|{product}"
        assert route["handler"] == "handle_video_uiflow3_callback"
        assert route["parent_menu"] == "menu|main_video"
        assert route["back_target"] == "menu|main_video"
    idea_route = bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_idea"]
    assert idea_route["entry_callback"] == "videoidea|start"
    assert idea_route["handler"] == "handle_video_idea_callback"
    assert "vid3|entry|video_idea" not in _callbacks(bot.main_video_keyboard("vi"))
    assert '("vid3|", "handle_video_uiflow3_callback")' in BOT_SOURCE
    assert 'CallbackQueryHandler(handle_video_uiflow3_callback, pattern=r"^vid3\\|")' in BOT_SOURCE


def test_legacy_callback_owners_remain_registered_and_video_edit_is_untouched() -> None:
    for registration in (
        'CallbackQueryHandler(handle_video_product_callback, pattern=r"^vproduct\\|(?!b14_confirm(?:\\||$))")',
        'CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r"^vprofile\\|")',
        'CallbackQueryHandler(handle_video_trend2_callback, pattern=r"^vtrend\\|")',
        'CallbackQueryHandler(handle_storyboard2_callback, pattern=r"^vstory\\|")',
        'CallbackQueryHandler(handle_long_video_callback, pattern=r"^longvideo\\|")',
        'CallbackQueryHandler(handle_video_idea_callback, pattern=r"^videoidea\\|")',
        'CallbackQueryHandler(handle_video_editor_callback, pattern=r"^videoedit\\|")',
    ):
        assert registration in BOT_SOURCE


def test_format_and_content_hub_are_compact_with_unique_callbacks_and_exact_back() -> None:
    state = video_uiflow3.new_state("video_ai_real", draft_id="format-ui")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state["navigation"].update({"current_step": "format", "visible_step_stack": ["entry"]})
    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert "9:16" in " ".join(labels)
    assert "8 giay" in " ".join(labels)
    assert "Tiep tuc" in " ".join(labels)
    assert _rows(markup)[-1] == [("Quay lai", "vid3|back"), ("Menu Video", "menu|main_video")]
    callbacks = _callbacks(markup)
    assert len(callbacks) == len(set(callbacks))
    assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks)

    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=24)
    state["navigation"]["current_step"] = "content_hub"
    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert any("32" in label for label in labels)
    assert any("Y tuong" in label for label in labels)
    assert any("Tu nhap" in label for label in labels)
    assert "videoidea|start" in _callbacks(markup)
    assert "vid3|content|ideas" not in _callbacks(markup)


def test_production_bible_groups_character_count_details_images_voice_and_locations() -> None:
    state = _locked_state()
    state["navigation"]["current_step"] = "production_bible"
    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = [label for row in _rows(markup) for label, _callback in row]
    combined = " ".join(labels)
    assert "So nhan vat" in combined
    assert "Sua tung nhan vat" in combined
    assert "Boi canh" in combined
    assert "Anh tham chieu" in combined
    assert "Nhat quan" in combined

    state = video_uiflow3.set_character_count(state, 2)
    state["ui_view"] = "character_list"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert [label for row in _rows(markup) for label, _callback in row][:2] == [
        "NV1 - Nhan vat 1",
        "NV2 - Nhan vat 2",
    ]


def test_bible_editors_do_not_ask_scene_assignment_before_scene_plan_exists() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.set_location_count(state, 1)
    state["ui_view"] = "character_detail"
    state["active_character_id"] = "char_01"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|char_scenes|char_01" not in _callbacks(markup)

    state["ui_view"] = "location_detail"
    state["active_location_id"] = "loc_01"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|loc_scenes|loc_01" not in _callbacks(markup)

    state = video_uiflow3.confirm_scene_count(state, 2)
    state["ui_view"] = "character_detail"
    state["active_character_id"] = "char_01"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|char_scenes|char_01" in _callbacks(markup)


def test_scene_assignment_screen_combines_cast_dialogue_voice_and_music_with_auto_default() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.update_character(state, "char_01", display_name="Lan", gender="female")
    state = video_uiflow3.update_character(state, "char_02", display_name="Minh", gender="male")
    state = video_uiflow3.confirm_scene_count(state, 3)
    state = video_uiflow3.auto_assign_scenes(state)
    state["navigation"]["current_step"] = "scene_assignment"
    text, markup = bot.video_uiflow3_screen_payload(state)
    assert "Tu dong theo thu tu" in text
    assert "NV1" in text and "NV2" in text
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert "Canh 1" in labels
    assert "Canh 2" in labels
    assert "Canh 3" in labels
    assert any("Nhac" in label for label in labels)

    state["ui_view"] = "scene_detail"
    state["active_scene_id"] = "scene_01"
    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert any("Nhan vat" in label for label in labels)
    assert any("Loi thoai" in label for label in labels)
    assert any("Giong" in label for label in labels)
    assert not any("Nhac canh" in label for label in labels)

    state["capabilities"]["per_scene_music"] = True
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert any("Nhac canh" in label for row in _rows(markup) for label, _callback in row)


def test_summary_has_one_hub_and_each_editor_returns_to_summary() -> None:
    state = _locked_state()
    state["navigation"]["current_step"] = "summary"
    text, markup = bot.video_uiflow3_screen_payload(state)
    assert "TOM TAT VIDEO" in text
    callbacks = _callbacks(markup)
    assert "vid3|edit|content_lock" in callbacks
    assert "vid3|edit|production_bible" in callbacks
    assert "vid3|edit|scene_plan" in callbacks
    assert "vid3|edit|scene_assignment" in callbacks
    assert "vid3|edit|branding" in callbacks

    editor = video_uiflow3.begin_summary_edit(state, "production_bible")
    assert editor["navigation"]["return_to"] == "summary"
    assert video_uiflow3.finish_editor(editor)["navigation"]["current_step"] == "summary"


def test_summary_translates_dirty_dependency_codes_into_actionable_copy() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.revise_content(state, original_intent="Noi dung moi")
    state = video_uiflow3.lock_content(state)
    state["navigation"]["current_step"] = "summary"
    text, _markup = bot.video_uiflow3_screen_payload(state)
    assert "Rà soát lại Production Bible" in text
    assert "Rà soát lại kế hoạch cảnh" in text
    assert "_reconcile_required" not in text


def test_scene_plan_summary_editor_saves_directly_back_to_summary() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970038
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.auto_assign_scenes(state)
    state["owner_user_id"] = user_id
    state["navigation"]["current_step"] = "summary"
    bot.save_video_uiflow3_state(context, state)
    _click(context, user_id, "vid3|edit|scene_plan", "summary-plan-01")
    editing = bot.video_uiflow3_state(context)
    assert editing["navigation"]["current_step"] == "scene_plan"
    assert editing["navigation"]["return_to"] == "summary"
    _click(context, user_id, "vid3|scene_plan_done", "summary-plan-02")
    saved = bot.video_uiflow3_state(context)
    assert saved["navigation"]["current_step"] == "summary"
    assert saved["navigation"]["return_to"] is None


def test_real_callback_back_resume_and_stale_action_never_cross_product() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970031
    start = FakeQuery(user_id, "vid3|entry|video_ai_real", "start")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=start), context))
    state = bot.video_uiflow3_state(context)
    assert state["parent_product"] == "video_ai_real"
    assert start.edits

    mode = FakeQuery(user_id, "vid3|mode|prompt_video", "mode")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=mode), context))
    state = bot.video_uiflow3_state(context)
    assert state["navigation"]["current_step"] == "format"

    stale = FakeQuery(user_id, "vid3|character|char_99", "stale")
    before = bot.video_uiflow3_state(context)
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=stale), context))
    after = bot.video_uiflow3_state(context)
    assert after["parent_product"] == before["parent_product"] == "video_ai_real"
    assert after["navigation"]["current_step"] == before["navigation"]["current_step"]

    back = FakeQuery(user_id, "vid3|back", "back")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=back), context))
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "entry"

    resume = FakeQuery(user_id, "vid3|resume", "resume")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=resume), context))
    assert bot.video_uiflow3_state(context)["parent_product"] == "video_ai_real"


def test_stale_step_callback_cannot_skip_prerequisites_or_rewind_an_active_flow() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970036
    _click(context, user_id, "vid3|entry|video_ai_real", "guard-01")
    _click(context, user_id, "vid3|mode|prompt_video", "guard-02")
    before = bot.video_uiflow3_state(context)
    _click(context, user_id, "vid3|view|scene_count", "guard-03")
    after = bot.video_uiflow3_state(context)
    assert after["navigation"]["current_step"] == before["navigation"]["current_step"] == "format"

    _click(context, user_id, "vid3|ratio|9x16", "guard-04")
    _click(context, user_id, "vid3|duration|16", "guard-05")
    _click(context, user_id, "vid3|format_done", "guard-06")
    _click(context, user_id, "vid3|content|manual", "guard-07")
    _send_text(context, user_id, "Noi dung da khoa de kiem tra callback cu.", 301)
    _click(context, user_id, "vid3|content_lock", "guard-08")
    before = bot.video_uiflow3_state(context)
    _click(context, user_id, "vid3|ratio|16x9", "guard-09")
    after = bot.video_uiflow3_state(context)
    assert after["navigation"]["current_step"] == before["navigation"]["current_step"] == "production_bible"
    assert after["format"]["ratio"] == before["format"]["ratio"] == "9:16"


def test_resume_preserves_child_editor_and_initial_source_back_is_not_a_loop() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970034
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state["owner_user_id"] = user_id
    state["ui_view"] = "character_detail"
    state["active_character_id"] = "char_01"
    bot.save_video_uiflow3_state(context, state)
    _click(context, user_id, "vid3|resume", "resume-child")
    resumed = bot.video_uiflow3_state(context)
    assert resumed["ui_view"] == "character_detail"
    assert resumed["active_character_id"] == "char_01"

    source = video_uiflow3.new_state("video_trend", draft_id="source-back")
    _text, markup = bot.video_uiflow3_screen_payload(source)
    callbacks = _callbacks(markup)
    assert callbacks.count("menu|main_video") == 1
    assert "vid3|back" not in callbacks


def test_uiflow3_handlers_are_planning_only_and_media_dispatch_precedes_legacy_scene3() -> None:
    start = BOT_SOURCE.index("async def handle_video_uiflow3_callback")
    end = BOT_SOURCE.index("\nasync def ", start + 20)
    handler = BOT_SOURCE[start:end]
    for forbidden in (
        "execute_engine(",
        "create_video_job(",
        "enqueue",
        "provider.submit",
        "debit",
        "deduct",
        "charge_xu",
    ):
        assert forbidden not in handler
    photo = BOT_SOURCE[BOT_SOURCE.index("async def handle_photo"):BOT_SOURCE.index("async def handle_translation_media_pending_upload")]
    assert photo.index("handle_video_uiflow3_pending_media") < photo.index("handle_video_scene3_pending_media")
    text_start = BOT_SOURCE.index("async def handle_message")
    text_end = BOT_SOURCE.index("\nasync def ", text_start + 20)
    text = BOT_SOURCE[text_start:text_end]
    assert text.index("handle_video_uiflow3_pending_text") < text.index("handle_video_profile_studio_pending_text")


def test_entry_mode_requires_real_source_and_hides_unproved_video_to_video() -> None:
    state = video_uiflow3.new_state("video_ai_real", draft_id="mode-source")
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|mode|video_video" not in _callbacks(markup)

    image_mode = video_uiflow3.set_entry_mode(state, "image_video")
    assert image_mode["source"]["required"] is True
    assert image_mode["source"]["kind"] == "raw_images"
    assert image_mode["navigation"]["current_step"] == "source"

    capable = video_uiflow3.new_state(
        "video_ai_real",
        draft_id="mode-capable",
        capabilities={"video_to_video": True},
    )
    _text, markup = bot.video_uiflow3_screen_payload(capable)
    assert "vid3|mode|video_video" in _callbacks(markup)


def test_each_source_branch_accepts_only_its_advertised_media_kind() -> None:
    user_id = 970037
    image_context = SimpleNamespace(user_data={})
    _click(image_context, user_id, "vid3|entry|video_ai_real", "kind-01")
    _click(image_context, user_id, "vid3|mode|image_video", "kind-02")
    _text, markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(image_context))
    assert "vid3|source_media" in _callbacks(markup)
    assert "vid3|source_text" not in _callbacks(markup)
    _click(image_context, user_id, "vid3|source_media", "kind-03")
    _send_video(image_context, user_id, "wrong-video", "wrong-video-u", 401)
    assert bot.video_uiflow3_state(image_context)["source"]["assets"] == []
    assert (bot.video_uiflow3_state(image_context).get("pending_input") or {}).get("kind") == "source_media"

    selfshot_context = SimpleNamespace(user_data={})
    _click(selfshot_context, user_id, "vid3|entry|self_shot_scene_change", "kind-04")
    _click(selfshot_context, user_id, "vid3|source_media", "kind-05")
    _send_photo(selfshot_context, user_id, "wrong-photo", "wrong-photo-u", 402)
    assert bot.video_uiflow3_state(selfshot_context)["source"]["assets"] == []

    frame_context = SimpleNamespace(user_data={})
    _click(frame_context, user_id, "vid3|entry|frame_video_local", "kind-06")
    _click(frame_context, user_id, "vid3|source_media", "kind-07")
    _send_video(frame_context, user_id, "wrong-frame-video", "wrong-frame-video-u", 403)
    assert bot.video_uiflow3_state(frame_context)["source"]["assets"] == []


def test_compact_public_flow_persists_character_voice_dialogue_and_returns_summary() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970032
    _click(context, user_id, "vid3|entry|video_ai_real", "q01")
    _click(context, user_id, "vid3|mode|prompt_video", "q02")
    _click(context, user_id, "vid3|ratio|9x16", "q03")
    _click(context, user_id, "vid3|duration|16", "q04")
    _click(context, user_id, "vid3|format_done", "q05")
    _click(context, user_id, "vid3|content|manual", "q06")
    _send_text(context, user_id, "Lan va Minh gioi thieu san pham.", 101)
    _click(context, user_id, "vid3|content_lock", "q07")
    _click(context, user_id, "vid3|chars|2", "q08")

    _click(context, user_id, "vid3|character|char_01", "q09")
    _click(context, user_id, "vid3|char_gender|char_01|female", "q10")
    _click(context, user_id, "vid3|char_desc|char_01", "q11")
    _send_text(context, user_id, "Lan | Nguoi dan chu ao xanh.", 102)
    _click(context, user_id, "vid3|char_voice|char_01", "q12")
    _click(context, user_id, "vid3|voice|char_01|vf1", "q13")

    _click(context, user_id, "vid3|character|char_02", "q14")
    _click(context, user_id, "vid3|char_gender|char_02|male", "q15")
    _click(context, user_id, "vid3|char_desc|char_02", "q16")
    _send_text(context, user_id, "Minh | Nguoi tu van ao trang.", 103)
    _click(context, user_id, "vid3|char_voice|char_02", "q17")
    _click(context, user_id, "vid3|voice|char_02|vm1", "q18")

    _click(context, user_id, "vid3|view|production_bible", "q19")
    _click(context, user_id, "vid3|locs|1", "q20")
    _click(context, user_id, "vid3|location|loc_01", "q21")
    _click(context, user_id, "vid3|loc_desc|loc_01", "q22")
    _send_text(context, user_id, "Studio | Anh sang mem, nen sach.", 104)
    _click(context, user_id, "vid3|view|production_bible", "q23")
    _click(context, user_id, "vid3|bible_done", "q24")
    _click(context, user_id, "vid3|scene_count|2", "q25")
    _click(context, user_id, "vid3|scene_plan_done", "q26")

    state = bot.video_uiflow3_state(context)
    assert [scene["character_ids"] for scene in state["scenes"]] == [["char_01"], ["char_02"]]
    _click(context, user_id, "vid3|scene|scene_01", "q27")
    _click(context, user_id, "vid3|scene_dialogue|scene_01", "q28")
    _click(context, user_id, "vid3|dialogue_speaker|scene_01|char_01", "q29")
    _send_text(context, user_id, "Xin chao, day la san pham moi.", 105)
    _click(context, user_id, "vid3|view|scene_assignment", "q30")
    _click(context, user_id, "vid3|assignment_done", "q31")
    _click(context, user_id, "vid3|prompts_done", "q32")
    _click(context, user_id, "vid3|brand|none", "q33")
    _click(context, user_id, "vid3|branding_done", "q34")

    state = bot.video_uiflow3_state(context)
    assert state["navigation"]["current_step"] == "summary"
    assert state["audio"]["dialogue_segments"][0]["speaker_id"] == "char_01"
    assert state["audio"]["voice_cast"]["char_01"]["voice_id"] == "vi-VN-HoaiMyNeural"
    assert state["audio"]["voice_cast"]["char_02"]["voice_id"] == "vi-VN-NamMinhNeural"
    assert state["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }

    _click(context, user_id, "vid3|edit|production_bible", "q35")
    assert bot.video_uiflow3_state(context)["navigation"]["return_to"] == "summary"
    _click(context, user_id, "vid3|bible_done", "q36")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "summary"


def test_reference_uploads_keep_exact_owner_and_frame_batch_keeps_order() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970033
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.set_location_count(state, 1)
    state["owner_user_id"] = user_id
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|char_image|char_01", "m01")
    _send_photo(context, user_id, "char-photo", "char-unique", 201)
    _click(context, user_id, "vid3|loc_image|loc_01", "m02")
    _send_photo(context, user_id, "loc-photo", "loc-unique", 202)
    references = bot.video_uiflow3_state(context)["references"]
    assert [(item["owner_type"], item["owner_id"]) for item in references] == [
        ("character", "char_01"),
        ("location", "loc_01"),
    ]

    frame_context = SimpleNamespace(user_data={})
    _click(frame_context, user_id, "vid3|entry|frame_video_local", "f01")
    _click(frame_context, user_id, "vid3|source_media", "f02")
    _send_photo(frame_context, user_id, "frame-1", "frame-u1", 203)
    _send_photo(frame_context, user_id, "frame-2", "frame-u2", 204)
    frame_state = bot.video_uiflow3_state(frame_context)
    assert [item["telegram_file_id"] for item in frame_state["source"]["assets"]] == ["frame-1", "frame-2"]
    assert frame_state["navigation"]["current_step"] == "source"
    assert (frame_state.get("pending_input") or {}).get("kind") == "source_media"
    _click(frame_context, user_id, "vid3|source_done", "f03")
    assert bot.video_uiflow3_state(frame_context)["navigation"]["current_step"] == "format"


def test_music_controls_are_capability_gated_but_contract_remains_available() -> None:
    state = video_uiflow3.confirm_scene_count(_locked_state(), 1)
    state = video_uiflow3.auto_assign_scenes(state)
    state = video_uiflow3.set_music_scope(state, "per_scene")
    state["ui_view"] = "music_scope"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)
    assert "vid3|music_set|none" in callbacks
    assert "vid3|music_set|whole_video" not in callbacks
    assert "vid3|music_set|per_scene" not in callbacks

    state["capabilities"].update({"whole_video_music": True, "per_scene_music": True})
    _text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)
    assert "vid3|music_set|whole_video" in callbacks
    assert "vid3|music_set|per_scene" in callbacks


def test_video_guide_teaches_content_first_and_keeps_ideas_catalog_only() -> None:
    text, markup = bot.localized_menu_content("guide_video_ai", False, "vi", user_id=970035)
    assert "Nội dung trước" in text or "Xác nhận Nội dung" in text
    assert "tổng số nhân vật" in text
    assert "Ý tưởng video chỉ là kho" in text
    assert "không sở hữu RouteEngine" in text
    assert _callbacks(markup) == ["menu|main_video", "menu|main_guide", "menu|main"]
