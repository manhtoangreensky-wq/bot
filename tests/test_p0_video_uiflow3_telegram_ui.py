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
    def __init__(self, user_id: int, data: str, query_id: str = "query-1", *, chat_id: int | None = None) -> None:
        self.data = data
        self.id = query_id
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id if chat_id is None else chat_id)
        self.edits: list[dict] = []
        self.answers: list[dict] = []

    async def answer(self, text: str | None = None, **kwargs) -> None:
        self.answers.append({"text": text, **kwargs})

    async def edit_message_text(self, text: str, **kwargs) -> None:
        self.edits.append({"text": text, **kwargs})


class FakeMessage:
    def __init__(
        self,
        *,
        message_id: int,
        text: str = "",
        photo=None,
        document=None,
        video=None,
        chat_id: int | None = None,
    ) -> None:
        self.message_id = message_id
        self.text = text
        self.chat_id = chat_id
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
    state = bot.video_uiflow3_state(context)
    wire_data = video_uiflow3.scope_callback(state, data) if state else data
    query = FakeQuery(user_id, wire_data, query_id)
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=query), context))
    return query


def _send_text(context, user_id: int, text: str, message_id: int) -> FakeMessage:
    message = FakeMessage(message_id=message_id, text=text, chat_id=user_id)
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
    message = FakeMessage(message_id=message_id, photo=[media], chat_id=user_id)
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
    message = FakeMessage(message_id=message_id, video=media, chat_id=user_id)
    handled = asyncio.run(bot.handle_video_uiflow3_pending_media(
        SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)),
        context,
    ))
    assert handled is True
    return message


def test_uiflow3_selfshot_source_keeps_real_telegram_probe_metadata():
    user_id = 963201
    context = SimpleNamespace(user_data={})
    _click(context, user_id, "vid3|entry|self_shot_scene_change", "selfshot-probe-01")
    _click(context, user_id, "vid3|source_media", "selfshot-probe-02")

    _send_video(
        context,
        user_id,
        "selfshot-probe-video",
        "selfshot-probe-unique",
        963202,
    )

    source = bot.video_uiflow3_state(context)["source"]["assets"][-1]
    metadata = source["metadata"]
    assert metadata["duration_seconds"] == 8
    assert metadata["width"] == 720
    assert metadata["height"] == 1280


def _rows(markup) -> list[list[tuple[str, str]]]:
    def logical_callback(value: str) -> str:
        parts = str(value or "").split("|")
        if len(parts) >= 4 and parts[:2] == ["vid3", "d"]:
            return "|".join(("vid3", *parts[3:]))
        return str(value or "")

    return [
        [(button.text, logical_callback(button.callback_data)) for button in row]
        for row in markup.inline_keyboard
    ]


def _callbacks(markup) -> list[str]:
    return [callback for row in _rows(markup) for _label, callback in row if callback]


def _wire_callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _click_visible(context, user_id: int, logical_data: str, query_id: str) -> FakeQuery:
    state = bot.video_uiflow3_state(context)
    assert state, "a visible UIFLOW3 callback requires an active draft"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    wire_data = ""
    for row in markup.inline_keyboard:
        for button in row:
            candidate = str(button.callback_data or "")
            parts = candidate.split("|")
            logical = "|".join(("vid3", *parts[3:])) if len(parts) >= 4 and parts[:2] == ["vid3", "d"] else candidate
            if logical == logical_data:
                wire_data = candidate
                break
        if wire_data:
            break
    assert wire_data, f"callback is not visible on the current screen: {logical_data}"
    query = FakeQuery(user_id, wire_data, query_id)
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=query), context))
    return query


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


def _ready_long_video_planning_state() -> dict:
    state = video_uiflow3.new_state("multi_scene_film", draft_id="long-planning-only")
    state = video_uiflow3.set_entry_mode(state, "series_plan")
    state = video_uiflow3.set_series_goal(state, "Lap mot series co cac tap ke thua cung Production Bible.")
    state = video_uiflow3.set_format(state, ratio="16:9", target_duration_seconds=600)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Lap ke hoach tap phim dau tien.",
        approved_brief={
            "title": "Tap phim dau tien",
            "goal": "Hoan tat mot ke hoach san xuat co the tiep tuc sau nay",
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.set_episode_identity(state, number=1, title="Tap phim dau tien")
    state = video_uiflow3.set_episode_content(state, "Lap ke hoach tap phim dau tien.")
    state = video_uiflow3.lock_episode_content(state)
    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "episode",
        "scene_plan",
        "scene_assignment",
        "prompts",
        "branding",
        "summary",
    )
    state["navigation"]["current_step"] = "summary"
    return video_uiflow3.normalize_state(state)


def _ready_supported_video_planning_state() -> dict:
    state = video_uiflow3.new_state("video_ai_real", draft_id="supported-summary-save")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=8)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Video mot canh khong co nhan vat.",
        approved_brief={
            "title": "Video mot canh",
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "prompts",
        "branding",
        "summary",
    )
    state["navigation"]["current_step"] = "summary"
    return video_uiflow3.normalize_state(state)


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


def test_content_hub_shows_the_separate_idea_catalog_beside_32_content_types() -> None:
    state = video_uiflow3.new_state("video_ai_real", draft_id="idea-parent-screen")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=16)
    state["navigation"]["current_step"] = "content_hub"

    _text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)

    assert "vid3|idea_catalog" in callbacks
    assert "vid3|content|profiles" in callbacks
    assert "vid3|content|manual" in callbacks
    assert "videoidea|start" not in callbacks


def test_visible_idea_action_opens_separate_catalog_without_losing_v3_draft() -> None:
    user_id = 970084
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("video_ai_real", draft_id="idea-parent-open")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=16)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "content_hub"
    bot.save_video_uiflow3_state(context, state)

    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|idea_catalog" in _callbacks(markup)
    query = _click(context, user_id, "vid3|idea_catalog", "idea-parent-open-01")

    handoff = dict(context.user_data.get("video_idea_parent_handoff") or {})
    assert handoff["uiflow3_draft_id"] == "idea-parent-open"
    assert handoff["uiflow3_parent_product"] == "video_ai_real"
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "content_hub"
    assert query.edits


def test_selected_idea_returns_to_same_v3_draft_content_lock() -> None:
    user_id = 970085
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("video_ai_real", draft_id="idea-parent-return")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=16)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "content_hub"
    bot.save_video_uiflow3_state(context, state)
    query = FakeQuery(user_id, "videoidea|continue", "idea-parent-return-01")

    asyncio.run(bot.video_uiflow3_accept_idea_candidate(
        query,
        context,
        user_id,
        {
            "uiflow3_draft_id": "idea-parent-return",
            "uiflow3_parent_product": "video_ai_real",
            "uiflow3_owner_user_id": user_id,
            "uiflow3_owner_chat_id": user_id,
        },
        {
            "idea_id": "idea-101",
            "idea_title": "Mot tinh huong ban hang de hieu",
            "idea_selected_prompt": "Lan trinh bay van de, giai phap va ket qua trong hai canh lien mach.",
            "selected_profile": "educational_story",
            "idea_preset_content": {"goal": "Giai thich ro rang"},
        },
    ))

    current = bot.video_uiflow3_state(context)
    assert current["draft_id"] == "idea-parent-return"
    assert current["navigation"]["current_step"] == "content_lock"
    assert current["content"]["source"] == "idea_catalog"
    assert current["content"]["idea_id"] == "idea-101"
    assert current["content"]["original_intent"].startswith("Lan trinh bay")
    assert current["content"]["locked"] is False
    assert current["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    assert query.edits and "✅ Nội dung đã chọn" in query.edits[-1]["text"]


def test_long_video_summary_saves_planning_snapshot_without_unlocking_submit() -> None:
    user_id = 970071
    context = SimpleNamespace(user_data={})
    state = _ready_long_video_planning_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    bot.save_video_uiflow3_state(context, state)

    assert video_uiflow3.readiness_errors(state) == ["public_submit_locked"]

    query = _click(context, user_id, "vid3|summary_done", "long-plan-save-01")
    current = bot.video_uiflow3_state(context)

    snapshot = current["legacy_compat"]["approved_snapshot"]
    assert snapshot["parent_product"] == "multi_scene_film"
    assert snapshot["config_hash"]
    assert current["legacy_compat"]["commercial_tail_ready"] is False
    assert current["navigation"]["current_step"] == "summary"
    assert current["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    assert query.answers
    answer = str(query.answers[-1].get("text") or "")
    assert "Đã lưu kế hoạch" in answer
    assert "chỉ cho phép lập kế hoạch" in answer


def test_long_video_collects_series_goal_and_episode_before_scene_planning() -> None:
    user_id = 970078
    context = SimpleNamespace(user_data={})
    _click(context, user_id, "vid3|entry|multi_scene_film", "series-flow-01")
    _click(context, user_id, "vid3|mode|series_plan", "series-flow-02")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "series_goal"

    _text, markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    assert {"vid3|series_goal_edit", "vid3|series_goal_done"}.issubset(_callbacks(markup))
    _click(context, user_id, "vid3|series_goal_edit", "series-flow-03")
    _send_text(context, user_id, "Series ky nang ban hang cho nguoi moi.", 601)
    _click(context, user_id, "vid3|series_goal_done", "series-flow-04")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "format"

    state = bot.video_uiflow3_state(context)
    state = video_uiflow3.set_format(state, ratio="16:9", target_duration_seconds=600)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Noi dung chung cua series.",
        approved_brief={"title": "Series ban hang"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|bible_done", "series-flow-05")
    episode = bot.video_uiflow3_state(context)
    assert episode["navigation"]["current_step"] == "episode"
    _text, markup = bot.video_uiflow3_screen_payload(episode)
    assert {
        "vid3|episode_identity",
        "vid3|episode_content",
        "vid3|episode_entities",
        "vid3|episode_done",
    }.issubset(_callbacks(markup))

    _click(context, user_id, "vid3|episode_identity", "series-flow-06")
    _send_text(context, user_id, "2 | Tap bat dau", 602)
    _click(context, user_id, "vid3|episode_content", "series-flow-07")
    _send_text(context, user_id, "Tap 2 mo dau bang mot tinh huong ban hang.", 603)
    _click(context, user_id, "vid3|episode_done", "series-flow-08")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "scene_count"

    _click(context, user_id, "vid3|back", "series-flow-09")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "episode"


def test_long_video_episode_entity_override_is_compact_and_returns_to_episode() -> None:
    user_id = 970079
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("multi_scene_film", draft_id="episode-entities")
    state = video_uiflow3.set_series_goal(state, "Series hai nguoi dan.")
    state = video_uiflow3.set_format(state, ratio="16:9", target_duration_seconds=600)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Tap co hai nguoi dan.",
        approved_brief={"title": "Hai nguoi dan"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 2)
    state = video_uiflow3.set_location_count(state, 0)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "episode"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|episode_entities", "episode-entity-01")
    _text, markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    assert "vid3|episode_entity|characters|char_01" in _callbacks(markup)
    assert "vid3|episode_entity|characters|char_02" in _callbacks(markup)

    _click(context, user_id, "vid3|episode_entity|characters|char_01", "episode-entity-02")
    assert video_uiflow3.effective_episode_contract(bot.video_uiflow3_state(context))["character_ids"] == ["char_02"]
    _click(context, user_id, "vid3|view|episode", "episode-entity-03")
    restored = bot.video_uiflow3_state(context)
    assert restored["navigation"]["current_step"] == "episode"
    assert "ui_view" not in restored


def test_episode_override_editor_covers_optional_actors_continuity_and_series_reset() -> None:
    user_id = 970086
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("multi_scene_film", draft_id="episode-full-overrides")
    state = video_uiflow3.set_series_goal(state, "Series co day du tac nhan.")
    state = video_uiflow3.set_format(state, ratio="16:9", target_duration_seconds=600)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Tap co nhan vat, san pham va dao cu.",
        approved_brief={"title": "Tap day du tac nhan"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 1)
    state = video_uiflow3.set_location_count(state, 1)
    state = video_uiflow3.add_product(state, name="San pham A")
    state = video_uiflow3.add_prop(state, name="Dao cu A")
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "episode"
    bot.save_video_uiflow3_state(context, state)

    _click_visible(context, user_id, "vid3|episode_entities", "episode-full-01")
    _text, markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    callbacks = _callbacks(markup)
    assert "vid3|episode_entity|products|prod_01" in callbacks
    assert "vid3|episode_entity|props|prop_01" in callbacks
    assert "vid3|episode_continuity|identity" in callbacks
    assert "vid3|episode_inherit" in callbacks

    _click_visible(
        context,
        user_id,
        "vid3|episode_entity|products|prod_01",
        "episode-full-02",
    )
    _click_visible(
        context,
        user_id,
        "vid3|episode_continuity|identity",
        "episode-full-03",
    )
    effective = video_uiflow3.effective_episode_contract(bot.video_uiflow3_state(context))
    assert effective["product_ids"] == []
    assert effective["continuity"]["identity"] is False

    _click_visible(context, user_id, "vid3|episode_inherit", "episode-full-04")
    reset = bot.video_uiflow3_state(context)
    assert reset["episode"]["entity_overrides"] == {}
    assert reset["episode"]["continuity_overrides"] == {}
    assert video_uiflow3.effective_episode_contract(reset)["product_ids"] == ["prod_01"]


def test_source_scene_limit_error_is_actionable_for_media_intake() -> None:
    message = bot.video_uiflow3_input_error(
        ValueError("source_scene_limit_exceeded"),
        media=True,
    )

    assert "đạt giới hạn" in message.lower()
    assert "tệp đã nhận vẫn được giữ" in message.lower()


def test_video_ai_real_summary_requires_quality_before_quote() -> None:
    user_id = 970072
    context = SimpleNamespace(user_data={})
    state = _ready_supported_video_planning_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    bot.save_video_uiflow3_state(context, state)

    assert video_uiflow3.readiness_errors(state) == []

    query = _click(context, user_id, "vid3|summary_done", "supported-plan-save-01")
    current = bot.video_uiflow3_state(context)

    assert current["navigation"]["current_step"] == "package"
    assert current["legacy_compat"]["approved_snapshot"]["parent_product"] == "video_ai_real"
    assert query.answers[-1].get("text") is None

    query = _click(context, user_id, "vid3|quality_done", "supported-plan-save-02")
    current = bot.video_uiflow3_state(context)
    assert current["navigation"]["current_step"] == "package"
    assert query.answers[-1].get("text") == "Hãy chọn một gói chất lượng trước khi xem báo giá."


def test_public_route_metadata_matches_actual_uiflow3_entry_screens() -> None:
    expected_children = {
        "video_trend": ("vid3|source_text",),
        "video_ai_real": (
            "vid3|mode|prompt_video",
            "vid3|mode|image_video",
            "menu|guide_video_ai",
        ),
        "script_image_video": ("vid3|source_text",),
        "frame_video_local": ("vid3|source_media", "vid3|image_ai|source", "vid3|source_status"),
        "self_shot_scene_change": ("vid3|source_media", "vid3|source_status"),
        "storyboard_prompt": ("vid3|mode|storyboard_generate", "vid3|mode|storyboard_upload"),
        "multi_scene_film": ("vid3|mode|series_plan",),
    }
    assert set(expected_children) == set(CREATION_PRODUCTS)

    for product, children in expected_children.items():
        route = bot.VIDEO_PUBLIC_ROUTE_MATRIX[product]
        adapter = video_uiflow3.ENTRY_ADAPTERS[product]
        state = video_uiflow3.new_state(product, draft_id=f"route-{product}")
        _text, markup = bot.video_uiflow3_screen_payload(state)
        callbacks = _callbacks(markup)

        assert route["first_step"] == adapter["initial_step"]
        assert route["flow_type"] == "content_first_canonical"
        assert route["canonical"] is True
        assert tuple(route["expected_children"]) == children
        assert set(children).issubset(callbacks)
        assert callbacks.count("menu|main_video") == 1


def test_uiflow3_admin_audits_use_the_canonical_graph_not_legacy_steps() -> None:
    semantics = bot.video_semantics_audit_payload()
    assert semantics["ok"] is True, semantics

    callback_payload = bot.video_callback_audit_payload()
    callback_rows = {
        row["product_id"]: row
        for row in callback_payload["rows"]
        if row["product_id"] in CREATION_PRODUCTS
    }
    assert set(callback_rows) == set(CREATION_PRODUCTS)
    for product, row in callback_rows.items():
        route = bot.VIDEO_PUBLIC_ROUTE_MATRIX[product]
        assert tuple(row["callbacks"]) == (*tuple(route["expected_children"]), "menu|main_video")
        assert row["ok"] is True

    rows = [
        row
        for row in bot.video_back_audit_rows_detailed()
        if row["video_tool"] in CREATION_PRODUCTS
    ]
    assert len(rows) == len(CREATION_PRODUCTS)
    for row in rows:
        assert row["step"] == video_uiflow3.ENTRY_ADAPTERS[row["video_tool"]]["initial_step"]
        assert row["expected"] == "menu|main_video"
        assert row["actual"] == "menu|main_video"
        assert row["ok"] is True


def test_full_video_back_audit_has_no_false_failure_after_uiflow3_migration() -> None:
    payload = bot.video_back_audit_payload()
    failures = [
        {
            "video_tool": row["video_tool"],
            "step": row["step"],
            "expected": row["expected"],
            "actual": row["actual"],
        }
        for row in payload["detail_rows"]
        if not row["ok"]
    ]
    assert failures == []
    assert payload["ok"] is True


def test_each_creation_entry_opens_only_its_owned_first_screen_and_exact_menu_back() -> None:
    user_id = 970055
    for index, product in enumerate(CREATION_PRODUCTS, 1):
        context = SimpleNamespace(user_data={})
        _click(context, user_id, f"vid3|entry|{product}", f"entry-owner-{index}")

        state = bot.video_uiflow3_state(context)
        text, markup = bot.video_uiflow3_screen_payload(state)
        callbacks = _callbacks(markup)
        wire_callbacks = _wire_callbacks(markup)

        assert state["parent_product"] == product
        assert bot.VIDEO_UIFLOW3_PRODUCT_LABELS[product] in text or state["navigation"]["current_step"] == "source"
        assert callbacks.count("menu|main_video") == 1
        allowed_direct_callbacks = {
            callback
            for callback in bot.VIDEO_PUBLIC_ROUTE_MATRIX[product]["expected_children"]
            if not callback.startswith("vid3|")
        }
        assert all(
            callback == "menu|main_video"
            or callback.startswith("vid3|d|")
            or callback in allowed_direct_callbacks
            for callback in wire_callbacks
        )
        assert not any(
            callback.endswith(f"|entry|{other}")
            for callback in wire_callbacks
            for other in CREATION_PRODUCTS
            if other != product
        )


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
    assert "giây/cảnh" not in " ".join(labels)
    assert "Thời lượng nằm ở bước Chất lượng" in text
    assert _rows(markup)[-1] == [("⬅️ Quay lại", "vid3|back"), ("🎬 Menu Video", "menu|main_video")]
    callbacks = _callbacks(markup)
    assert len(callbacks) == len(set(callbacks))
    assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks)

    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=24)
    state["navigation"]["current_step"] = "content_hub"
    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert any("32" in label for label in labels)
    assert any("ý tưởng" in label.lower() for label in labels)
    assert any("Tự mô tả" in label for label in labels)
    assert "vid3|idea_catalog" in _callbacks(markup)
    assert "videoidea|start" not in _callbacks(markup)
    assert "vid3|content|ideas" not in _callbacks(markup)


def test_content_hub_offers_source_only_when_source_content_really_exists() -> None:
    state = video_uiflow3.new_state("video_ai_real", draft_id="source-visibility")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=24)
    state["source"]["complete"] = True
    state["navigation"]["current_step"] = "content_hub"

    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|content|source" not in _callbacks(markup)
    assert "vid3|idea_catalog" in _callbacks(markup)
    assert "videoidea|start" not in _callbacks(markup)

    with_source = video_uiflow3.set_source_metadata(state, text="Noi dung nguon co that")
    with_source["navigation"]["current_step"] = "content_hub"
    _text, markup = bot.video_uiflow3_screen_payload(with_source)
    assert "vid3|content|source" in _callbacks(markup)


def test_32_content_public_route_locks_profile_before_any_character_or_scene() -> None:
    user_id = 970073
    context = SimpleNamespace(user_data={})
    _click(context, user_id, "vid3|entry|video_ai_real", "profile-route-01")
    _click(context, user_id, "vid3|mode|prompt_video", "profile-route-02")
    _click(context, user_id, "vid3|scene_count|1", "profile-route-03")
    _click(context, user_id, "vid3|ratio|9x16", "profile-route-04")
    _click(context, user_id, "vid3|duration_scene|8", "profile-route-05")
    _click(context, user_id, "vid3|format_done", "profile-route-06")
    _click(context, user_id, "vid3|content|profiles", "profile-route-07")

    choosing = bot.video_uiflow3_state(context)
    assert choosing["navigation"]["current_step"] == "content_hub"
    assert choosing.get("ui_view") == "profiles"
    _text, markup = bot.video_uiflow3_screen_payload(choosing)
    profile_callbacks = [item for item in _callbacks(markup) if item.startswith("vid3|profile|")]
    assert profile_callbacks

    selected_profile_id = profile_callbacks[0].split("|", 2)[-1]
    _click(context, user_id, profile_callbacks[0], "profile-route-08")

    candidate = bot.video_uiflow3_state(context)
    assert candidate["content"]["source"] == "content_catalog"
    assert candidate["content"]["profile_id"] == selected_profile_id
    assert candidate["content"]["candidate_ready"] is True
    assert candidate["content"]["locked"] is False
    assert candidate["navigation"]["current_step"] == "content_lock"
    assert candidate["bible"]["characters"] == []
    assert candidate["scenes"] == []

    _click(context, user_id, "vid3|content_lock", "profile-route-09")
    locked = bot.video_uiflow3_state(context)
    assert locked["content"]["locked"] is True
    assert locked["navigation"]["current_step"] == "production_bible"


def test_scene_count_buttons_respect_active_product_minimum_and_maximum() -> None:
    script = video_uiflow3.new_state("script_image_video", draft_id="script-scene-bounds")
    script = video_uiflow3.set_source_metadata(script, text="Kich ban ngan")
    script = video_uiflow3.set_format(script, ratio="9:16", target_duration_seconds=8)
    script = video_uiflow3.set_content_candidate(
        script,
        source="source",
        original_intent="Kich ban ngan",
        approved_brief={"title": "Kich ban ngan"},
    )
    script = video_uiflow3.lock_content(script)
    script["navigation"]["current_step"] = "scene_count"
    _text, markup = bot.video_uiflow3_screen_payload(script)
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert "Bot 1 canh" not in labels
    assert "vid3|scene_count|1" not in _callbacks(markup)

    long_video = video_uiflow3.new_state("multi_scene_film", draft_id="long-scene-bounds")
    long_video = video_uiflow3.set_format(long_video, ratio="16:9", target_duration_seconds=99999)
    long_video = video_uiflow3.set_content_candidate(
        long_video,
        source="manual",
        original_intent="Ke hoach video dai tap",
        approved_brief={"title": "Video dai tap"},
    )
    long_video = video_uiflow3.lock_content(long_video)
    long_video["navigation"]["current_step"] = "scene_count"
    _text, markup = bot.video_uiflow3_screen_payload(long_video)
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert "Them 1 canh" not in labels
    assert "vid3|scene_count|13" not in _callbacks(markup)


def test_production_bible_groups_character_count_details_images_voice_and_locations() -> None:
    state = _locked_state()
    state["navigation"]["current_step"] = "production_bible"
    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = [label for row in _rows(markup) for label, _callback in row]
    combined = " ".join(labels)
    assert "Số nhân vật" in combined
    assert "Danh sách nhân vật" in combined
    assert "Số bối cảnh" in combined
    assert "Ảnh tham chiếu" in combined
    assert "Giữ nhất quán" in combined

    state = video_uiflow3.set_character_count(state, 2)
    state["ui_view"] = "character_list"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert [label for row in _rows(markup) for label, _callback in row][:2] == [
        "👤 Nhân vật 1",
        "👤 Nhân vật 2",
    ]


def test_production_bible_keeps_optional_actors_in_one_compact_editor() -> None:
    state = _locked_state()
    state["navigation"]["current_step"] = "production_bible"

    text, markup = bot.video_uiflow3_screen_payload(state)

    assert "Tùy chỉnh chi tiết" in text
    assert "vid3|view|bible_extras" in _callbacks(markup)


def test_bible_done_never_invents_explicit_zero_count_confirmations() -> None:
    user_id = 970047
    context = SimpleNamespace(user_data={})
    state = _locked_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    query = _click(context, user_id, "vid3|bible_done", "bible-count-01")

    after = bot.video_uiflow3_state(context)
    assert after["bible"]["character_count_confirmed"] is False
    assert after["bible"]["location_count_confirmed"] is False
    assert after["navigation"]["current_step"] == "production_bible"
    assert query.answers


def test_bible_auto_explicitly_confirms_zero_for_skipped_entities_without_dead_end() -> None:
    user_id = 970059
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("video_ai_real", draft_id="skip-entities")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=24)
    state = video_uiflow3.set_content_candidate(
        state,
        source="content_catalog",
        profile_id="lofi_visualizer",
        original_intent="Video lofi khong co nhan vat va loi thoai.",
        approved_brief={
            "title": "Lofi",
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|bible_auto", "bible-skip-01")
    automatic = bot.video_uiflow3_state(context)
    assert automatic["bible"]["characters"] == []
    assert automatic["bible"]["locations"] == []
    assert automatic["bible"]["character_count_confirmed"] is True
    assert automatic["bible"]["location_count_confirmed"] is True

    _click(context, user_id, "vid3|bible_done", "bible-skip-02")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "scene_count"


def test_bible_done_blocks_incomplete_character_and_location_profiles_at_their_owner_step() -> None:
    user_id = 970069
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.set_location_count(state, 1)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    query = _click(context, user_id, "vid3|bible_done", "bible-profile-01")

    current = bot.video_uiflow3_state(context)
    assert current["navigation"]["current_step"] == "production_bible"
    assert query.answers
    answer = str(query.answers[-1].get("text") or "")
    assert "Nhân vật chưa chọn giới tính" in answer or "Nhân vật chưa có mô tả" in answer


def test_bible_done_persists_the_continuity_defaults_shown_as_selected() -> None:
    user_id = 970070
    context = SimpleNamespace(user_data={})
    state = _locked_state()
    state["needs"].update({
        "characters": "SKIP",
        "locations": "SKIP",
        "reference_assets": "SKIP",
        "continuity": "REQUIRED",
    })
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(state, "continuity")
    bot.save_video_uiflow3_state(context, state)

    _text, markup = bot.video_uiflow3_screen_payload(state)
    selected_labels = [label for row in _rows(markup) for label, _callback in row]
    assert all(
        any(label.startswith("✅") and expected in label for label in selected_labels)
        for expected in ("Khuôn mặt", "Trang phục", "Sản phẩm", "Bối cảnh")
    )

    _click(context, user_id, "vid3|view|production_bible", "continuity-defaults-01")
    _click(context, user_id, "vid3|bible_done", "continuity-defaults-02")

    current = bot.video_uiflow3_state(context)
    assert current["bible"]["continuity"] == {
        "identity": True,
        "wardrobe": True,
        "product": True,
        "location": True,
    }
    assert current["navigation"]["current_step"] == "scene_count"


def test_compact_bible_extras_persist_and_assign_optional_scene_actors() -> None:
    user_id = 970048
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.update_character(state, "char_01", display_name="Lan", gender="female", description="Nguoi ban hang")
    state = video_uiflow3.update_character(state, "char_02", display_name="Minh", gender="male", description="Khach hang")
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|view|bible_extras", "extras-01")
    assert bot.video_uiflow3_state(context).get("ui_view") == "bible_extras"
    _click(context, user_id, "vid3|narrator_edit", "extras-02")
    _send_text(context, user_id, "Nguoi dan | Am ap | narrator-a", 401)
    _click(context, user_id, "vid3|product_add", "extras-03")
    _send_text(context, user_id, "May pha ca phe | thiet bi | Giu dung logo va hinh dang", 402)
    _click(context, user_id, "vid3|prop_add", "extras-04")
    _send_text(context, user_id, "Tach ca phe | dat tren ban", 403)
    _click(context, user_id, "vid3|relationship_add", "extras-05")
    _send_text(context, user_id, "NV1 | NV2 | seller_customer", 404)
    _click(context, user_id, "vid3|product_image|prod_01", "extras-06")
    _send_photo(context, user_id, "product-image", "product-image-u", 405)
    _click(context, user_id, "vid3|prop_image|prop_01", "extras-06b")
    _send_photo(context, user_id, "prop-image", "prop-image-u", 406)

    state = bot.video_uiflow3_state(context)
    assert state["bible"]["narrator"]["narrator_id"] == "narrator_01"
    assert state["bible"]["products"][0]["product_id"] == "prod_01"
    assert state["bible"]["props"][0]["prop_id"] == "prop_01"
    assert state["bible"]["relationships"][0]["character_ids"] == ["char_01", "char_02"]
    assert any(item["owner_id"] == "prod_01" for item in state["references"])
    assert any(item["owner_id"] == "prop_01" for item in state["references"])

    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.auto_assign_scenes(state)
    state["navigation"]["current_step"] = "scene_assignment"
    bot.save_video_uiflow3_state(context, state)
    _click(context, user_id, "vid3|scene_entities|scene_01", "extras-07")
    _click(context, user_id, "vid3|scene_product|scene_01|prod_01", "extras-08")
    _click(context, user_id, "vid3|scene_prop|scene_01|prop_01", "extras-09")
    _click(context, user_id, "vid3|scene_narrator|scene_01", "extras-10")

    scene = bot.video_uiflow3_state(context)["scenes"][0]
    assert scene["product_ids"] == ["prod_01"]
    assert scene["prop_ids"] == ["prop_01"]
    assert scene["narrator_enabled"] is True


def test_relationship_input_uses_visible_nv_numbers_but_persists_stable_ids() -> None:
    user_id = 970060
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.set_character_count(state, 1)
    state = video_uiflow3.set_character_count(state, 2)
    assert [item["character_id"] for item in state["bible"]["characters"]] == ["char_01", "char_03"]
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(state, "bible_extras")
    bot.save_video_uiflow3_state(context, state)

    text, _markup = bot.video_uiflow3_screen_payload(state)
    assert "Nhân vật 1 (chưa đặt tên)" in text
    assert "Nhân vật 2 (chưa đặt tên)" in text
    assert "char_01=" not in text and "char_03=" not in text
    assert "Nhan vat" not in text

    _click(context, user_id, "vid3|relationship_add", "relationship-01")
    prompt_text, _markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    assert "Nhân vật 1 | Nhân vật 2" in prompt_text
    assert "char_01 | char_02" not in prompt_text
    _send_text(context, user_id, "NV1 | NV2 | dong nghiep", 410)

    relationship = bot.video_uiflow3_state(context)["bible"]["relationships"][0]
    assert relationship["character_ids"] == ["char_01", "char_03"]


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
    state["navigation"]["current_step"] = "production_bible"
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
    assert "gán nhân vật theo thứ tự" in text
    assert "Nhân vật 1" in text and "Nhân vật 2" in text
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert all(any(f"Cảnh {index}" in label for label in labels) for index in (1, 2, 3))
    assert not any("Nhạc" in label for label in labels)

    state["capabilities"].update({"whole_video_music": True, "per_scene_music": True})
    _text, markup = bot.video_uiflow3_screen_payload(state)
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert any("Âm thanh và phụ đề" in label for label in labels)
    assert "vid3|view|audio_options" in _callbacks(markup)
    state["capabilities"].update({"whole_video_music": False, "per_scene_music": False})

    state["ui_view"] = "scene_detail"
    state["active_scene_id"] = "scene_01"
    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert any("Nhân vật" in label for label in labels)
    assert any("Lời thoại" in label for label in labels)
    assert any("Giọng" in label for label in labels)
    assert not any("Nhạc cảnh" in label for label in labels)

    state["capabilities"]["per_scene_music"] = True
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert any("Nhạc cảnh" in label for row in _rows(markup) for label, _callback in row)


def test_scene_detail_hides_empty_actor_and_audio_submenus_until_they_have_content() -> None:
    state = video_uiflow3.confirm_scene_count(_locked_state(), 1)
    state = video_uiflow3.assign_scene(state, "scene_01", character_ids=[])
    state["navigation"]["current_step"] = "scene_assignment"
    state["ui_view"] = "scene_detail"
    state["active_scene_id"] = "scene_01"

    _text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)
    assert "vid3|scene_cast|scene_01" not in callbacks
    assert "vid3|scene_loc|scene_01" not in callbacks
    assert "vid3|scene_entities|scene_01" not in callbacks
    assert "vid3|scene_dialogue|scene_01" not in callbacks
    assert "vid3|scene_voice|scene_01" not in callbacks

    state = video_uiflow3.add_product(state, name="San pham A")
    state["ui_view"] = "scene_detail"
    state["active_scene_id"] = "scene_01"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|scene_entities|scene_01" in _callbacks(markup)


def test_voice_picker_offers_distinct_planning_slots_for_same_gender_cast() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.update_character(state, "char_01", gender="female")
    state = video_uiflow3.update_character(state, "char_02", gender="female")
    state["ui_view"] = "voice_select"
    state["active_character_id"] = "char_01"

    text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)
    labels = [label for row in _rows(markup) for label, _callback in row]

    assert "vid3|voice|char_01|vf1" in callbacks
    assert "vid3|voice|char_01|vf2" in callbacks
    assert "vid3|voice|char_01|vm1" not in callbacks
    assert "vid3|voice|char_01|vm2" not in callbacks
    assert "👩 Giọng nữ 1" in labels
    assert "👩 Giọng nữ 2" in labels
    assert "Giọng đã chọn chỉ được dùng cho video khi hệ thống xác minh sẵn sàng" in text


def test_voice_picker_hides_slots_used_by_another_character_and_rejects_forged_reuse() -> None:
    user_id = 970065
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        gender="female",
        voice_id=bot.VIDEO_UIFLOW3_VOICE_ALIASES["vf1"],
    )
    state = video_uiflow3.update_character(state, "char_02", gender="female")
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "voice_select",
        active_character_id="char_02",
        ui_return_callback="vid3|character|char_02",
    )
    bot.save_video_uiflow3_state(context, state)

    _text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)
    assert "vid3|voice|char_02|vf1" not in callbacks
    assert "vid3|voice|char_02|vf2" in callbacks

    rejected = _click(context, user_id, "vid3|voice|char_02|vf1", "voice-reuse-01")
    after = bot.video_uiflow3_state(context)
    assert after["bible"]["characters"][1]["voice_id"] == ""
    assert rejected.answers


def test_voice_picker_sets_missing_gender_and_rejects_mismatched_voice_category() -> None:
    user_id = 970057
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|char_voice|char_01", "voice-gender-01")
    _text, markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    callbacks = _callbacks(markup)
    assert "vid3|voice_gender|char_01|female" in callbacks
    assert "vid3|voice_gender|char_01|male" in callbacks
    assert "vid3|voice|char_01|vf1" not in callbacks
    assert "vid3|voice|char_01|vm1" not in callbacks

    _click(context, user_id, "vid3|voice_gender|char_01|female", "voice-gender-02")
    selected = bot.video_uiflow3_state(context)
    assert selected["bible"]["characters"][0]["gender"] == "female"
    _text, markup = bot.video_uiflow3_screen_payload(selected)
    callbacks = _callbacks(markup)
    assert "vid3|voice|char_01|vf1" in callbacks
    assert "vid3|voice|char_01|vm1" not in callbacks

    rejected = _click(context, user_id, "vid3|voice|char_01|vm1", "voice-gender-03")
    after = bot.video_uiflow3_state(context)
    assert after["bible"]["characters"][0]["voice_id"] == ""
    assert rejected.answers


def test_changing_character_gender_clears_an_incompatible_existing_voice() -> None:
    user_id = 970058
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        gender="female",
        voice_id=bot.VIDEO_UIFLOW3_VOICE_ALIASES["vf1"],
    )
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|char_gender|char_01|male", "voice-gender-04")

    changed = bot.video_uiflow3_state(context)
    character = changed["bible"]["characters"][0]
    assert character["gender"] == "male"
    assert character["voice_id"] == ""
    assert "char_01" not in changed["audio"]["voice_cast"]


def test_scene_sfx_and_ambient_editors_are_hidden_until_capability_and_return_to_scene() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.auto_assign_scenes(state)
    state["navigation"]["current_step"] = "scene_assignment"
    state["ui_view"] = "scene_entities"
    state["active_scene_id"] = "scene_01"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|scene_sfx|scene_01" not in _callbacks(markup)
    assert "vid3|scene_ambient|scene_01" not in _callbacks(markup)

    user_id = 970051
    context = SimpleNamespace(user_data={})
    state["capabilities"].update({"scene_sfx": True, "scene_ambient": True})
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    bot.save_video_uiflow3_state(context, state)
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|scene_sfx|scene_01" in _callbacks(markup)
    assert "vid3|scene_ambient|scene_01" in _callbacks(markup)

    _click(context, user_id, "vid3|scene_sfx|scene_01", "scene-audio-01")
    _click(context, user_id, "vid3|scene_sfx_set|scene_01|door", "scene-audio-02")
    _click(context, user_id, "vid3|scene_entities|scene_01", "scene-audio-03")
    _click(context, user_id, "vid3|scene_ambient|scene_01", "scene-audio-04")
    _click(context, user_id, "vid3|scene_ambient_set|scene_01|cafe", "scene-audio-05")

    scene = bot.video_uiflow3_state(context)["scenes"][0]
    assert scene["sfx_ids"] == ["door"]
    assert scene["ambient_id"] == "cafe"
    current = bot.video_uiflow3_state(context)
    assert current["ui_view"] == "scene_entities"
    _text, markup = bot.video_uiflow3_screen_payload(current)
    assert "vid3|scene|scene_01" in _callbacks(markup)


def test_scene_advanced_and_custom_voice_return_to_the_exact_scene_editor() -> None:
    user_id = 970044
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.update_character(state, "char_01", gender="male")
    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.auto_assign_scenes(state)
    state["owner_user_id"] = user_id
    state["navigation"]["current_step"] = "scene_assignment"
    state["ui_view"] = "prompt_advanced"
    state["active_scene_id"] = "scene_01"
    bot.save_video_uiflow3_state(context, state)

    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|scene|scene_01" in _callbacks(markup)
    assert "vid3|view|prompts" not in _callbacks(markup)

    _click(context, user_id, "vid3|scene_voice|scene_01", "scene-voice-01")
    _click(context, user_id, "vid3|scene_voice_char|scene_01|char_01", "scene-voice-02")
    _click(context, user_id, "vid3|voice|char_01|vm1", "scene-voice-02b")
    assert bot.video_uiflow3_state(context)["active_scene_id"] == "scene_01"
    assert bot.video_uiflow3_state(context)["ui_view"] == "scene_voice"
    _click(context, user_id, "vid3|scene_voice_char|scene_01|char_01", "scene-voice-02c")
    _click(context, user_id, "vid3|voice_custom|char_01", "scene-voice-03")
    pending = bot.video_uiflow3_state(context)["pending_input"]
    assert pending["back_callback"] == "vid3|scene_voice_char|scene_01|char_01"
    _send_text(context, user_id, "verified-scene-voice", 396)
    restored = bot.video_uiflow3_state(context)
    assert restored["ui_view"] == "scene_voice"
    assert restored["active_scene_id"] == "scene_01"
    _text, markup = bot.video_uiflow3_screen_payload(restored)
    assert "vid3|scene|scene_01" in _callbacks(markup)


def test_scene_dialogue_editor_lists_and_removes_only_its_own_lines() -> None:
    user_id = 970063
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.update_character(state, "char_01", display_name="Lan", gender="female")
    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.assign_scene(state, "scene_01", character_ids=["char_01"])
    state = video_uiflow3.set_dialogue(state, "scene_01", speaker_id="char_01", text="Xin chao")
    state = video_uiflow3.set_dialogue(state, "scene_01", speaker_id="char_01", text="Hen gap lai")
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "scene_assignment"
    state = bot.video_uiflow3_open_view(state, "dialogue_speaker", active_scene_id="scene_01")
    bot.save_video_uiflow3_state(context, state)

    text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)
    assert "Xin chao" in text and "Hen gap lai" in text
    assert "vid3|dialogue_remove|scene_01|dlg_01" in callbacks
    assert "vid3|dialogue_remove|scene_01|dlg_02" in callbacks
    assert "vid3|scene|scene_01" in callbacks

    _click(context, user_id, "vid3|dialogue_remove|scene_01|dlg_01", "dialogue-remove-01")
    updated = bot.video_uiflow3_state(context)
    assert [item["dialogue_id"] for item in updated["audio"]["dialogue_segments"]] == ["dlg_02"]
    assert updated["ui_view"] == "dialogue_speaker"
    assert updated["active_scene_id"] == "scene_01"


def test_summary_has_one_hub_and_each_editor_returns_to_summary() -> None:
    state = _locked_state()
    state["navigation"]["current_step"] = "summary"
    text, markup = bot.video_uiflow3_screen_payload(state)
    assert "Rà soát cuối" in text
    callbacks = _callbacks(markup)
    assert "vid3|edit|content_lock" in callbacks
    assert "vid3|edit|production_bible" in callbacks
    assert "vid3|edit|scene_plan" in callbacks
    assert "vid3|edit|scene_assignment" in callbacks
    assert "vid3|edit|branding" in callbacks
    labels = [label for row in _rows(markup) for label, _callback in row]
    assert any("Hoàn tất rà soát và chọn chất lượng" in label for label in labels)
    assert not any("Xu/cảnh" in label for label in labels)
    assert bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_ai_real"]["legacy_entry_callback"] not in callbacks

    editor = video_uiflow3.begin_summary_edit(state, "production_bible")
    assert editor["navigation"]["return_to"] == "summary"
    assert video_uiflow3.finish_editor(editor)["navigation"]["current_step"] == "summary"


def test_resume_drops_pending_input_whose_entity_owner_no_longer_exists() -> None:
    user_id = 970080
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    state["ui_view"] = "input_prompt"
    state["pending_input"] = {
        "kind": "character_description",
        "back_callback": "vid3|character|char_99",
        "draft_id": state["draft_id"],
        "owner_user_id": user_id,
        "owner_chat_id": user_id,
        "character_id": "char_99",
    }
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|resume", "resume-stale-owner-01")

    resumed = bot.video_uiflow3_state(context)
    assert resumed["navigation"]["current_step"] == "production_bible"
    assert "pending_input" not in resumed
    assert "ui_view" not in resumed


def test_non_series_episode_step_and_history_fail_closed() -> None:
    state = _locked_state()
    state["navigation"]["current_step"] = "episode"
    state["navigation"]["visible_step_stack"] = ["entry", "format", "episode"]

    clean = bot.video_uiflow3_canonical_screen_state(state)

    assert clean["navigation"]["current_step"] != "episode"
    assert "episode" not in clean["navigation"]["visible_step_stack"]
    text, _markup = bot.video_uiflow3_screen_payload(clean)
    assert "TAP DANG LAP" not in text


def test_malformed_episode_entity_callback_is_rejected_without_mutation() -> None:
    user_id = 970081
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("multi_scene_film", draft_id="episode-arity")
    state = video_uiflow3.set_series_goal(state, "Series hai nhan vat.")
    state = video_uiflow3.set_format(state, ratio="16:9", target_duration_seconds=600)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Tap co hai nhan vat.",
        approved_brief={"title": "Hai nhan vat"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 2)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "episode"
    bot.save_video_uiflow3_state(context, state)

    query = _click(
        context,
        user_id,
        "vid3|episode_entity|characters|char_01|ignored",
        "episode-arity-01",
    )

    current = bot.video_uiflow3_state(context)
    assert current["episode"]["entity_overrides"] == {}
    assert "episode-arity-01" not in current["handled_callback_ids"]
    assert query.answers and query.answers[-1].get("show_alert") is True


def test_summary_saves_planning_voice_without_claiming_render_readiness() -> None:
    user_id = 970082
    context = SimpleNamespace(user_data={})
    state = _ready_supported_video_planning_state()
    state = video_uiflow3.set_character_count(state, 1)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        display_name="Lan",
        gender="female",
        description="Nguoi dan chinh.",
        voice_id="plan-vi-female-02",
    )
    state = video_uiflow3.auto_assign_scenes(state)
    state["needs"].update({"characters": "REQUIRED", "voice": "REQUIRED"})
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "scene_plan",
        "scene_assignment",
        "dialogue",
        "prompts",
    )
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "summary"
    bot.save_video_uiflow3_state(context, state)

    assert "char_01_voice_not_server_renderable" in video_uiflow3.readiness_errors(state)
    query = _click_visible(context, user_id, "vid3|summary_done", "planning-voice-save-01")

    current = bot.video_uiflow3_state(context)
    assert current["legacy_compat"]["approved_snapshot"]["parent_product"] == "video_ai_real"
    assert current["legacy_compat"]["commercial_tail_ready"] is False
    assert current["navigation"]["current_step"] == "summary"
    assert current["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    assert query.answers[-1].get("show_alert") is True
    assert "giọng" in str(query.answers[-1].get("text") or "").lower()


def test_existing_source_asset_is_reusable_from_reference_editor() -> None:
    user_id = 970083
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("frame_video_local", draft_id="source-reference-ui")
    state = video_uiflow3.add_source_asset(
        state,
        asset_type="frame",
        telegram_file_id="source-frame-ui-1",
        fingerprint="sha256:source-frame-ui-1",
    )
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=8)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Lan xuat hien trong anh nguon.",
        approved_brief={"title": "Lan trong anh nguon"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 1)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        display_name="Lan",
        gender="female",
        description="Nhan vat trong anh nguon.",
    )
    state = video_uiflow3.set_location_count(state, 0)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    _click_visible(context, user_id, "vid3|view|references", "source-reference-ui-01")
    _text, markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    assert "vid3|source_ref|source_01" in _callbacks(markup)

    _click_visible(context, user_id, "vid3|source_ref|source_01", "source-reference-ui-02")
    _text, markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    assert "vid3|source_ref_set|source_01|character|char_01" in _callbacks(markup)

    _click_visible(
        context,
        user_id,
        "vid3|source_ref_set|source_01|character|char_01",
        "source-reference-ui-03",
    )
    mapped = bot.video_uiflow3_state(context)
    assert mapped["ui_view"] == "references"
    assert mapped["references"][0]["owner_id"] == "char_01"
    assert mapped["references"][0]["source"] == "source_intake"


def test_summary_rejects_forged_editor_target_without_leaving_summary() -> None:
    user_id = 970077
    context = SimpleNamespace(user_data={})
    state = _ready_supported_video_planning_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "summary"
    bot.save_video_uiflow3_state(context, state)

    query = _click(context, user_id, "vid3|edit|source", "summary-forged-edit-01")

    preserved = bot.video_uiflow3_state(context)
    assert preserved["navigation"]["current_step"] == "summary"
    assert preserved["navigation"]["return_to"] is None
    assert query.answers[-1]["show_alert"] is True


def test_source_reference_product_mapping_keeps_non_pilot_flow_on_references() -> None:
    user_id = 970078
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("script_image_video", draft_id="protected-source-product")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=8)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Video sản phẩm thuộc flow được bảo vệ.",
        approved_brief={"title": "Sản phẩm được bảo vệ"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.add_product(state, name="Sản phẩm A")
    state = video_uiflow3.add_source_asset(
        state,
        asset_type="image",
        telegram_file_id="protected-product-source",
        fingerprint="telegram:protected-product-source",
    )
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(state, "references")
    bot.save_video_uiflow3_state(context, state)

    _click_visible(context, user_id, "vid3|source_ref|source_01", "protected-source-product-1")
    _click_visible(
        context,
        user_id,
        "vid3|source_ref_set|source_01|product|prod_01",
        "protected-source-product-2",
    )

    mapped = bot.video_uiflow3_state(context)
    assert mapped["ui_view"] == "references"
    assert mapped["references"][0]["owner_id"] == "prod_01"


def test_summary_exposes_prompt_reconciliation_and_returns_without_a_dead_end() -> None:
    user_id = 970075
    context = SimpleNamespace(user_data={})
    state = _ready_supported_video_planning_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["dirty_sections"] = ["prompts", "summary"]
    bot.save_video_uiflow3_state(context, state)

    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|edit|prompts" in _callbacks(markup)

    _click(context, user_id, "vid3|edit|prompts", "summary-prompt-01")
    editing = bot.video_uiflow3_state(context)
    assert editing["navigation"]["current_step"] == "prompts"
    assert editing["navigation"]["return_to"] == "summary"

    _click(context, user_id, "vid3|prompts_done", "summary-prompt-02")
    restored = bot.video_uiflow3_state(context)
    assert restored["navigation"]["current_step"] == "summary"
    assert restored["navigation"]["return_to"] is None
    assert "prompts" not in restored["navigation"]["dirty_sections"]
    assert "prompts_reconcile_required" not in video_uiflow3.readiness_errors(restored)


def test_summary_format_change_reconciles_scene_count_then_returns_to_summary() -> None:
    user_id = 970076
    context = SimpleNamespace(user_data={})
    state = _ready_supported_video_planning_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    bot.save_video_uiflow3_state(context, state)

    _text, summary_markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|edit|format" in _callbacks(summary_markup)

    _click(context, user_id, "vid3|edit|format", "summary-format-01")
    _click(context, user_id, "vid3|duration|16", "summary-format-02")
    editing = bot.video_uiflow3_state(context)
    assert editing["navigation"]["current_step"] == "format"
    assert editing["navigation"]["return_to"] == "summary"
    assert editing["format"]["scene_count_confirmed"] is False

    _click(context, user_id, "vid3|format_done", "summary-format-03")
    summary = bot.video_uiflow3_state(context)
    assert summary["navigation"]["current_step"] == "summary"
    _text, summary_markup = bot.video_uiflow3_screen_payload(summary)
    assert "vid3|edit|scene_count" in _callbacks(summary_markup)

    _click(context, user_id, "vid3|edit|scene_count", "summary-format-04")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "scene_count"
    _click(context, user_id, "vid3|scene_count|2", "summary-format-05")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "scene_plan"
    _click(context, user_id, "vid3|scene_plan_auto", "summary-format-06")
    _click(context, user_id, "vid3|scene_plan_done", "summary-format-07")

    restored = bot.video_uiflow3_state(context)
    assert restored["navigation"]["current_step"] == "summary"
    assert restored["navigation"]["return_to"] is None
    assert restored["format"]["scene_count"] == 2
    assert restored["format"]["scene_count_confirmed"] is True


def test_summary_content_editor_returns_to_summary_after_content_lock_confirmation() -> None:
    user_id = 970049
    context = SimpleNamespace(user_data={})
    state = _locked_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "summary"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|edit|content_lock", "summary-content-01")
    _click(context, user_id, "vid3|content_edit", "summary-content-02")
    _send_text(context, user_id, state["content"]["original_intent"], 406)
    editing = bot.video_uiflow3_state(context)
    assert editing["navigation"]["current_step"] == "content_lock"
    assert editing["navigation"]["return_to"] == "summary"

    _click(context, user_id, "vid3|content_lock", "summary-content-03")

    restored = bot.video_uiflow3_state(context)
    assert restored["navigation"]["current_step"] == "summary"
    assert restored["navigation"]["return_to"] is None


def test_summary_translates_dirty_dependency_codes_into_actionable_copy() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.revise_content(state, original_intent="Noi dung moi")
    state = video_uiflow3.lock_content(state)
    state["navigation"]["current_step"] = "summary"
    text, _markup = bot.video_uiflow3_screen_payload(state)
    assert "Rà soát lại nhân vật và bối cảnh" in text
    assert "Rà soát lại kế hoạch cảnh" in text
    assert "_reconcile_required" not in text


def test_summary_translates_required_planning_gaps_without_internal_codes() -> None:
    labels = bot.video_uiflow3_readiness_labels([
        "locations_required",
        "dialogue_required",
        "char_01_voice_missing",
        "scene_02_location_missing",
        "dlg_01_speaker_not_in_scene",
        "character_count_unconfirmed",
        "location_count_unconfirmed",
        "char_01_gender_missing",
        "char_01_description_missing",
        "char_01_reference_missing",
        "loc_01_description_missing",
        "loc_01_reference_missing",
        "scene_01_semantic_beat_missing",
        "scene_01_main_action_missing",
        "scene_01_completion_state_missing",
        "reference_assets_required",
        "music_required",
        "continuity_required",
        "narrator_required",
        "products_required",
    ])
    text = " | ".join(labels)
    assert "bối cảnh bắt buộc" in text
    assert "lời thoại bắt buộc" in text
    assert "chưa có giọng" in text
    assert "Cảnh còn thiếu bối cảnh" in text
    assert "Người nói chưa được gán vào cảnh" in text
    assert "Chưa xác nhận tổng số nhân vật" in text
    assert "Chưa xác nhận tổng số bối cảnh" in text
    assert "Nhân vật chưa chọn giới tính" in text
    assert "Nhân vật chưa có mô tả" in text
    assert "Nhân vật chưa có ảnh tham chiếu" in text
    assert "Bối cảnh chưa có mô tả" in text
    assert "Bối cảnh chưa có ảnh tham chiếu" in text
    assert "Cảnh chưa có ý chính" in text
    assert "Cảnh chưa có hành động chính" in text
    assert "Cảnh chưa có kết quả cuối" in text
    assert "Thiếu ảnh tham chiếu bắt buộc" in text
    assert "Chưa chọn nhạc bắt buộc" in text
    assert "Chưa xác nhận quy tắc nhất quán" in text
    assert "Chưa có người dẫn chuyện bắt buộc" in text
    assert "Chưa có sản phẩm bắt buộc" in text
    assert "locations_required" not in text
    assert "speaker_not_in_scene" not in text
    assert "semantic_beat_missing" not in text


def test_summary_caps_long_content_and_readiness_details_below_telegram_limit() -> None:
    state = _locked_state()
    state["content"]["original_intent"] = "Noi dung rat dai. " * 500
    state = video_uiflow3.set_character_count(state, 20)
    state = video_uiflow3.set_location_count(state, 20)
    state = video_uiflow3.confirm_scene_count(state, 20)
    state["navigation"]["current_step"] = "summary"

    text, _markup = bot.video_uiflow3_screen_payload(state)

    assert len(text) < 4096
    assert "mục khác cần hoàn tất" in text


def test_scene_plan_summary_editor_saves_directly_back_to_summary() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970038
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
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


def test_scene_plan_requires_real_content_and_offers_non_destructive_rule_draft() -> None:
    user_id = 970062
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.confirm_scene_count(_locked_state(), 2)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "scene_plan"
    bot.save_video_uiflow3_state(context, state)

    text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)
    assert "vid3|scene_plan_auto" in callbacks
    assert "vid3|scene_plan_done" not in callbacks
    assert "Chưa đủ ý chính" in text

    _click(context, user_id, "vid3|scene_plan_auto", "scene-plan-auto-01")
    drafted = bot.video_uiflow3_state(context)
    assert video_uiflow3.scene_plan_complete(drafted) is True
    assert drafted["scenes"][1]["start_state"] == drafted["scenes"][0]["completion_state"]
    _text, markup = bot.video_uiflow3_screen_payload(drafted)
    assert "vid3|scene_plan_done" in _callbacks(markup)


def test_real_callback_back_resume_and_stale_action_never_cross_product() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970031
    start = FakeQuery(user_id, "vid3|entry|video_ai_real", "start")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=start), context))
    state = bot.video_uiflow3_state(context)
    assert state["parent_product"] == "video_ai_real"
    assert start.edits

    _click(context, user_id, "vid3|mode|prompt_video", "mode")
    state = bot.video_uiflow3_state(context)
    assert state["navigation"]["current_step"] == "scene_count"

    before = bot.video_uiflow3_state(context)
    _click(context, user_id, "vid3|character|char_99", "stale")
    after = bot.video_uiflow3_state(context)
    assert after["parent_product"] == before["parent_product"] == "video_ai_real"
    assert after["navigation"]["current_step"] == before["navigation"]["current_step"]

    _click(context, user_id, "vid3|back", "back")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "entry"

    resume = FakeQuery(user_id, "vid3|resume", "resume")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=resume), context))
    assert bot.video_uiflow3_state(context)["parent_product"] == "video_ai_real"


def test_video_menu_exposes_resume_only_for_a_valid_draft_and_restores_its_exact_step() -> None:
    user_id = 970074
    context = SimpleNamespace(user_data={})
    state = _locked_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    menu_query = FakeQuery(user_id, "menu|main_video", "menu-resume-01")
    asyncio.run(bot.handle_menu_callback(SimpleNamespace(callback_query=menu_query), context))

    assert menu_query.edits
    menu_markup = menu_query.edits[-1]["reply_markup"]
    assert "vid3|resume" in _wire_callbacks(menu_markup)

    resume_query = FakeQuery(user_id, "vid3|resume", "menu-resume-02")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=resume_query), context))
    resumed = bot.video_uiflow3_state(context)
    assert resumed["parent_product"] == "video_ai_real"
    assert resumed["navigation"]["current_step"] == "production_bible"
    assert resume_query.edits
    assert "Nhân vật và bối cảnh" in resume_query.edits[-1]["text"]

    empty_context = SimpleNamespace(user_data={})
    empty_menu_query = FakeQuery(user_id, "menu|main_video", "menu-resume-03")
    asyncio.run(bot.handle_menu_callback(SimpleNamespace(callback_query=empty_menu_query), empty_context))
    assert "vid3|resume" not in _wire_callbacks(empty_menu_query.edits[-1]["reply_markup"])


def test_status_and_summary_callbacks_answer_telegram_exactly_once() -> None:
    user_id = 970064
    source_context = SimpleNamespace(user_data={})
    _click(source_context, user_id, "vid3|entry|frame_video_local", "answer-once-01")
    source_query = _click(source_context, user_id, "vid3|source_status", "answer-once-02")
    assert len(source_query.answers) == 1

    summary_context = SimpleNamespace(user_data={})
    state = _locked_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "summary"
    bot.save_video_uiflow3_state(summary_context, state)
    summary_query = _click(summary_context, user_id, "vid3|summary_done", "answer-once-03")
    assert len(summary_query.answers) == 1


def test_corrupt_or_catalog_parent_resume_fails_closed_without_cross_product_render() -> None:
    context = SimpleNamespace(user_data={
        bot.VIDEO_UIFLOW3_STATE_KEY: {
            "flow_schema_version": 3,
            "draft_id": "invalid-parent",
            "parent_product": "video_idea",
        },
    })
    query = _click(context, 970036, "vid3|resume", "invalid-parent-resume")
    assert query.edits == []
    assert query.answers
    assert "Phiên lập kế hoạch đã hết hạn" in str(query.answers[-1].get("text") or "")


def test_resume_keeps_the_rendered_quality_step_and_scopes_new_buttons() -> None:
    user_id = 970066
    context = SimpleNamespace(user_data={})
    state = _locked_state()
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "package"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|resume", "resume-normalize-01")

    resumed = bot.video_uiflow3_state(context)
    assert resumed["navigation"]["current_step"] == "package"
    text, markup = bot.video_uiflow3_screen_payload(resumed)
    assert "Chọn chất lượng" in text
    assert "vid3|quality|300" in _callbacks(markup)


def test_resume_discards_a_child_view_owned_by_another_step_instead_of_rendering_dead_buttons() -> None:
    user_id = 970067
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.confirm_scene_count(_locked_state(), 1)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    state["ui_view"] = "scene_detail"
    state["active_scene_id"] = "scene_01"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|resume", "resume-owner-01")

    resumed = bot.video_uiflow3_state(context)
    assert resumed["navigation"]["current_step"] == "production_bible"
    assert "ui_view" not in resumed
    _text, markup = bot.video_uiflow3_screen_payload(resumed)
    callbacks = _callbacks(markup)
    assert "vid3|view|character_count" in callbacks
    assert "vid3|scene_cast|scene_01" not in callbacks


def test_resume_discards_a_child_view_whose_entity_no_longer_exists() -> None:
    scene_child_views = (
        "scene_plan_detail", "scene_cast", "scene_location", "dialogue_speaker",
        "scene_voice", "scene_music", "scene_sfx", "scene_ambient", "scene_detail",
        "scene_entities", "scene_product", "scene_prop",
    )
    stale_children = [
        ("production_bible", "character_detail", {"active_character_id": "char_99"}),
        ("production_bible", "voice_select", {"active_character_id": "char_99"}),
        ("production_bible", "location_detail", {"active_location_id": "loc_99"}),
        (
            "production_bible",
            "entity_scene_assign",
            {"assignment_owner_type": "character", "assignment_owner_id": "char_99"},
        ),
        (
            "production_bible",
            "references",
            {"reference_filter_type": "product", "reference_filter_id": "product_99"},
        ),
        ("scene_plan", "scene_plan_detail", {"active_scene_id": "scene_99"}),
        *[
            ("scene_assignment", view, {"active_scene_id": "scene_99"})
            for view in scene_child_views
            if view != "scene_plan_detail"
        ],
        (
            "scene_assignment",
            "voice_select",
            {"active_character_id": "char_01", "active_scene_id": "scene_99"},
        ),
        ("scene_assignment", "voice_select", {"active_character_id": "char_01"}),
        ("scene_assignment", "prompt_advanced", {}),
        ("prompts", "prompt_advanced", {"active_scene_id": "scene_99"}),
    ]

    for index, (parent_step, view, fields) in enumerate(stale_children, 1):
        user_id = 970070 + index
        context = SimpleNamespace(user_data={})
        state = video_uiflow3.set_character_count(_locked_state(), 1)
        state = video_uiflow3.set_location_count(state, 1)
        state = video_uiflow3.confirm_scene_count(state, 1)
        state["owner_user_id"] = user_id
        state["owner_chat_id"] = user_id
        state["navigation"]["current_step"] = parent_step
        state["ui_view"] = view
        state.update(fields)
        bot.save_video_uiflow3_state(context, state)

        _click(context, user_id, "vid3|resume", f"resume-entity-{index}")

        resumed = bot.video_uiflow3_state(context)
        assert resumed["navigation"]["current_step"] == parent_step
        assert "ui_view" not in resumed
        bot.video_uiflow3_screen_payload(resumed)


def test_foreign_callback_deactivates_pending_input_but_preserves_resume_step(monkeypatch) -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970039
    _click(context, user_id, "vid3|entry|video_ai_real", "leave-01")
    _click(context, user_id, "vid3|mode|prompt_video", "leave-02")
    _click(context, user_id, "vid3|scene_count|2", "leave-03")
    _click(context, user_id, "vid3|ratio|9x16", "leave-04")
    _click(context, user_id, "vid3|duration_scene|8", "leave-05")
    _click(context, user_id, "vid3|format_done", "leave-06")
    _click(context, user_id, "vid3|content|manual", "leave-07")
    before = bot.video_uiflow3_state(context)
    assert before["pending_input"]["kind"] == "manual_content"

    monkeypatch.setattr(bot, "current_system_mode", lambda: {})
    foreign = FakeQuery(user_id, "menu|main", "leave-menu")
    asyncio.run(bot.safe_mode_callback_guard(SimpleNamespace(callback_query=foreign), context))
    after = bot.video_uiflow3_state(context)
    assert "pending_input" not in after
    assert after.get("ui_view") != "input_prompt"
    assert after["navigation"]["current_step"] == before["navigation"]["current_step"] == "content_hub"
    assert after["ui_revision"] == before["ui_revision"] + 1

    message = FakeMessage(message_id=390, text="Tin nhan danh cho flow khac")
    handled = asyncio.run(bot.handle_video_uiflow3_pending_text(
        SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)),
        context,
    ))
    assert handled is False


def test_leaving_uiflow3_invalidates_every_old_screen_button_until_resume(monkeypatch) -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970061
    _click(context, user_id, "vid3|entry|video_ai_real", "leave-token-01")
    _click(context, user_id, "vid3|mode|prompt_video", "leave-token-02")
    state = bot.video_uiflow3_state(context)
    _text, markup = bot.video_uiflow3_screen_payload(state)
    old_scene_count = next(
        callback for callback in _wire_callbacks(markup)
        if callback.endswith("|scene_count|2")
    )

    monkeypatch.setattr(bot, "current_system_mode", lambda: {})
    foreign = FakeQuery(user_id, "menu|main_video", "leave-token-menu")
    asyncio.run(bot.safe_mode_callback_guard(SimpleNamespace(callback_query=foreign), context))
    suspended = bot.video_uiflow3_state(context)
    assert suspended["navigation"]["current_step"] == "scene_count"
    assert suspended["ui_revision"] == state["ui_revision"] + 1

    stale = FakeQuery(user_id, old_scene_count, "leave-token-03")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=stale), context))
    after_stale = bot.video_uiflow3_state(context)
    assert after_stale["format"]["scene_count"] == 0
    assert stale.answers

    _click(context, user_id, "vid3|resume", "leave-token-04")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "scene_count"


def test_pending_input_requires_matching_draft_and_owner() -> None:
    owner_id = 970040
    context = SimpleNamespace(user_data={})
    state = _locked_state()
    state["owner_user_id"] = owner_id
    state["owner_chat_id"] = owner_id
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_await_input(
        state,
        "character_count",
        back_callback="vid3|view|production_bible",
    )
    bot.save_video_uiflow3_state(context, state)

    other_message = FakeMessage(message_id=391, text="2")
    handled = asyncio.run(bot.handle_video_uiflow3_pending_text(
        SimpleNamespace(message=other_message, effective_user=SimpleNamespace(id=owner_id + 1)),
        context,
    ))
    assert handled is False

    raw = context.user_data[bot.VIDEO_UIFLOW3_STATE_KEY]
    raw["pending_input"]["draft_id"] = "different-draft"
    owner_message = FakeMessage(message_id=392, text="2")
    handled = asyncio.run(bot.handle_video_uiflow3_pending_text(
        SimpleNamespace(message=owner_message, effective_user=SimpleNamespace(id=owner_id)),
        context,
    ))
    assert handled is False

    raw["pending_input"]["draft_id"] = raw["draft_id"]
    missing_chat_message = FakeMessage(message_id=393, text="2")
    handled = asyncio.run(bot.handle_video_uiflow3_pending_text(
        SimpleNamespace(message=missing_chat_message, effective_user=SimpleNamespace(id=owner_id)),
        context,
    ))
    assert handled is False

    matching_message = FakeMessage(message_id=394, text="2", chat_id=owner_id)
    handled = asyncio.run(bot.handle_video_uiflow3_pending_text(
        SimpleNamespace(message=matching_message, effective_user=SimpleNamespace(id=owner_id)),
        context,
    ))
    assert handled is True
    assert len(bot.video_uiflow3_state(context)["bible"]["characters"]) == 2


def test_pending_input_from_another_step_cannot_mutate_the_current_editor() -> None:
    owner_id = 970068
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state["owner_user_id"] = owner_id
    state["owner_chat_id"] = owner_id
    state["navigation"]["current_step"] = "production_bible"
    state["ui_view"] = "input_prompt"
    state["pending_input"] = {
        "kind": "scene_plan",
        "scene_id": "scene_01",
        "draft_id": state["draft_id"],
        "owner_user_id": owner_id,
        "owner_chat_id": owner_id,
        "back_callback": "vid3|view|scene_plan",
    }
    bot.save_video_uiflow3_state(context, state)

    message = FakeMessage(message_id=395, text="Sai | Buoc | Hien tai", chat_id=owner_id)
    handled = asyncio.run(bot.handle_video_uiflow3_pending_text(
        SimpleNamespace(message=message, effective_user=SimpleNamespace(id=owner_id)),
        context,
    ))

    assert handled is False
    current = bot.video_uiflow3_state(context)
    assert current["navigation"]["current_step"] == "production_bible"
    assert current.get("scenes") == []


def test_callback_from_foreign_chat_cannot_mutate_the_owned_draft() -> None:
    user_id = 970046
    context = SimpleNamespace(user_data={})
    _click(context, user_id, "vid3|entry|video_ai_real", "chat-owner-01")
    _click(context, user_id, "vid3|mode|prompt_video", "chat-owner-02")
    before = bot.video_uiflow3_state(context)
    assert before["format"]["target_duration_seconds"] == 0
    stale_or_foreign = video_uiflow3.scope_callback(before, "vid3|duration|24")
    query = FakeQuery(user_id, stale_or_foreign, "chat-owner-03", chat_id=user_id + 9000)

    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=query), context))

    after = bot.video_uiflow3_state(context)
    assert after["format"]["target_duration_seconds"] == 0
    assert query.answers


def test_slash_navigation_clears_v3_pending_media_before_protected_flow_intake(monkeypatch) -> None:
    user_id = 970050
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state = bot.video_uiflow3_await_input(
        state,
        "character_image",
        back_callback="vid3|character|char_01",
        character_id="char_01",
    )
    bot.save_video_uiflow3_state(context, state)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "current_system_mode", lambda: {})
    monkeypatch.setattr(bot, "localized_menu_content", lambda *_args: ("SubDub", bot.InlineKeyboardMarkup([])))
    command_message = FakeMessage(message_id=407, text="/subdub")
    update = SimpleNamespace(
        message=command_message,
        effective_message=command_message,
        effective_user=SimpleNamespace(id=user_id),
    )

    asyncio.run(bot.safe_mode_message_guard(update, context))
    asyncio.run(bot.cmd_subdub(update, context))

    after = bot.video_uiflow3_state(context)
    assert "pending_input" not in after
    media = SimpleNamespace(file_id="protected-image", file_unique_id="protected-image-u", file_size=1234, width=720, height=1280)
    protected_message = FakeMessage(message_id=408, photo=[media])
    intercepted = asyncio.run(bot.handle_video_uiflow3_pending_media(
        SimpleNamespace(message=protected_message, effective_user=SimpleNamespace(id=user_id)),
        context,
    ))
    assert intercepted is False


def test_stale_step_callback_cannot_skip_prerequisites_or_rewind_an_active_flow() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970036
    _click(context, user_id, "vid3|entry|video_ai_real", "guard-01")
    _click(context, user_id, "vid3|mode|prompt_video", "guard-02")
    before = bot.video_uiflow3_state(context)
    _click(context, user_id, "vid3|view|scene_plan", "guard-03")
    after = bot.video_uiflow3_state(context)
    assert after["navigation"]["current_step"] == before["navigation"]["current_step"] == "scene_count"

    _click(context, user_id, "vid3|scene_count|2", "guard-04")
    _click(context, user_id, "vid3|ratio|9x16", "guard-05")
    _click(context, user_id, "vid3|duration_scene|8", "guard-06")
    _click(context, user_id, "vid3|format_done", "guard-07")
    _click(context, user_id, "vid3|content|manual", "guard-08")
    _send_text(context, user_id, "Noi dung da khoa de kiem tra callback cu.", 301)
    _click(context, user_id, "vid3|content_lock", "guard-09")
    before = bot.video_uiflow3_state(context)
    _click(context, user_id, "vid3|ratio|16x9", "guard-10")
    after = bot.video_uiflow3_state(context)
    assert after["navigation"]["current_step"] == before["navigation"]["current_step"] == "production_bible"
    assert after["format"]["ratio"] == before["format"]["ratio"] == "9:16"


def test_non_entry_callbacks_are_draft_scoped_and_old_same_step_buttons_fail_closed() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970045
    _click(context, user_id, "vid3|entry|video_ai_real", "draft-scope-01")
    first = bot.video_uiflow3_state(context)
    _text, markup = bot.video_uiflow3_screen_payload(first)
    old_mode_callback = next(
        callback for callback in _wire_callbacks(markup)
        if callback.endswith("|mode|prompt_video")
    )
    assert old_mode_callback.startswith("vid3|d|")
    assert len(old_mode_callback.encode("utf-8")) <= 64

    _click(context, user_id, "vid3|entry|video_ai_real", "draft-scope-02")
    second = bot.video_uiflow3_state(context)
    assert second["draft_id"] != first["draft_id"]
    assert second["entry_mode"] == ""

    stale = FakeQuery(user_id, old_mode_callback, "draft-scope-03")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=stale), context))
    after_stale = bot.video_uiflow3_state(context)
    assert after_stale["draft_id"] == second["draft_id"]
    assert after_stale["entry_mode"] == ""
    assert stale.answers

    unscoped = FakeQuery(user_id, "vid3|mode|prompt_video", "draft-scope-04")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=unscoped), context))
    assert bot.video_uiflow3_state(context)["entry_mode"] == ""

    _text, fresh_markup = bot.video_uiflow3_screen_payload(second)
    fresh_mode_callback = next(
        callback for callback in _wire_callbacks(fresh_markup)
        if callback.endswith("|mode|prompt_video")
    )
    assert fresh_mode_callback != old_mode_callback
    fresh = FakeQuery(user_id, fresh_mode_callback, "draft-scope-05")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=fresh), context))
    assert bot.video_uiflow3_state(context)["entry_mode"] == "prompt_video"


def test_same_draft_old_screen_callback_cannot_mutate_the_new_visible_state() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970052
    _click(context, user_id, "vid3|entry|video_ai_real", "same-draft-01")
    _click(context, user_id, "vid3|mode|prompt_video", "same-draft-02")

    state = bot.video_uiflow3_state(context)
    _text, old_markup = bot.video_uiflow3_screen_payload(state)
    old_scene_count = next(
        callback for callback in _wire_callbacks(old_markup)
        if callback.endswith("|scene_count|2")
    )

    _click(context, user_id, "vid3|scene_count|1", "same-draft-03")
    stale = FakeQuery(user_id, old_scene_count, "same-draft-04")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=stale), context))

    current = bot.video_uiflow3_state(context)
    assert current["format"]["scene_count"] == 1
    assert current["format"]["target_duration_seconds"] == 8
    assert stale.answers


def test_reference_gallery_is_owner_filtered_and_back_returns_to_owner_editor() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970053
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.set_location_count(state, 1)
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_01",
        role="primary_identity",
        telegram_file_id="char-file",
        fingerprint="char-fingerprint",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="location",
        owner_id="loc_01",
        role="primary_location",
        telegram_file_id="loc-file",
        fingerprint="loc-fingerprint",
    )
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "production_bible"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|character|char_01", "refs-owner-01")
    _text, character_markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    assert "vid3|refs|character|char_01" in _callbacks(character_markup)
    _click(context, user_id, "vid3|refs|character|char_01", "refs-owner-02")

    rendered = bot.video_uiflow3_state(context)
    text, markup = bot.video_uiflow3_screen_payload(rendered)
    assert "Ảnh tham chiếu · Nhân vật 1" in text
    assert "Bối cảnh" not in text
    assert "char_01" not in text
    assert "asset_01" not in text
    assert "char-file" not in text
    assert "vid3|character|char_01" in _callbacks(markup)
    assert "vid3|view|production_bible" not in _callbacks(markup)


def test_scene_detail_uses_visible_location_label_instead_of_internal_id() -> None:
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.set_location_count(state, 1)
    state = video_uiflow3.update_location(state, "loc_01", name="Quan ca phe")
    state = video_uiflow3.confirm_scene_count(state, 1)
    state = video_uiflow3.assign_scene(
        state,
        "scene_01",
        character_ids=["char_01"],
        location_id="loc_01",
    )
    state["navigation"]["current_step"] = "scene_assignment"
    state = bot.video_uiflow3_open_view(state, "scene_detail", active_scene_id="scene_01")

    text, _markup = bot.video_uiflow3_screen_payload(state)

    assert "Bối cảnh: Quan ca phe" in text
    assert "loc_01" not in text


def test_prompt_advanced_has_a_real_scene_editor_and_exact_parent_back() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970054
    state = video_uiflow3.confirm_scene_count(_locked_state(), 1)
    state = video_uiflow3.auto_assign_scenes(state)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    state["navigation"]["current_step"] = "prompts"
    bot.save_video_uiflow3_state(context, state)

    _click(context, user_id, "vid3|prompt_advanced", "advanced-01")
    text, markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    assert "vid3|scene_advanced|scene_01" in _callbacks(markup)
    assert "vid3|view|prompts" in _callbacks(markup)
    assert "Tùy chỉnh nâng cao theo cảnh" in text

    _click(context, user_id, "vid3|scene_advanced|scene_01", "advanced-02")
    _text, markup = bot.video_uiflow3_screen_payload(bot.video_uiflow3_state(context))
    assert "vid3|scene_direction|scene_01" in _callbacks(markup)
    assert "vid3|view|prompt_advanced" in _callbacks(markup)

    _click(context, user_id, "vid3|view|prompt_advanced", "advanced-02b")
    parent = bot.video_uiflow3_state(context)
    assert parent.get("ui_view") == "prompt_advanced"
    assert not parent.get("active_scene_id")
    _text, markup = bot.video_uiflow3_screen_payload(parent)
    assert "vid3|scene_advanced|scene_01" in _callbacks(markup)

    _click(context, user_id, "vid3|scene_advanced|scene_01", "advanced-02c")

    _click(context, user_id, "vid3|scene_direction|scene_01", "advanced-03")
    _send_text(context, user_id, "Medium shot | Canh ngang | Di chuyen cham", 409)
    scene = bot.video_uiflow3_state(context)["scenes"][0]
    assert scene["framing"] == "Medium shot"
    assert scene["movement"] == "Canh ngang"
    assert scene["lighting"] == "Di chuyen cham"


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


def test_source_text_and_custom_scene_count_back_follow_visible_history_not_service_side_effects() -> None:
    trend_context = SimpleNamespace(user_data={})
    trend_user = 970041
    _click(trend_context, trend_user, "vid3|entry|video_trend", "history-source-01")
    _click(trend_context, trend_user, "vid3|source_text", "history-source-02")
    _send_text(trend_context, trend_user, "Chu de trend dang len", 393)
    trend_state = bot.video_uiflow3_state(trend_context)
    assert trend_state["navigation"]["current_step"] == "format"
    assert trend_state["navigation"]["visible_step_stack"][-1] == "source"
    _click(trend_context, trend_user, "vid3|back", "history-source-03")
    assert bot.video_uiflow3_state(trend_context)["navigation"]["current_step"] == "source"

    duration_context = SimpleNamespace(user_data={})
    duration_user = 970042
    _click(duration_context, duration_user, "vid3|entry|video_ai_real", "history-duration-01")
    _click(duration_context, duration_user, "vid3|mode|prompt_video", "history-duration-02")
    _click(duration_context, duration_user, "vid3|scene_custom", "history-duration-03")
    _send_text(duration_context, duration_user, "4", 394)
    duration_state = bot.video_uiflow3_state(duration_context)
    assert duration_state["navigation"]["current_step"] == "format"
    assert duration_state["format"]["scene_count"] == 4
    assert "content_hub" not in duration_state["navigation"]["visible_step_stack"]
    _click(duration_context, duration_user, "vid3|back", "history-duration-04")
    assert bot.video_uiflow3_state(duration_context)["navigation"]["current_step"] == "scene_count"

    media_context = SimpleNamespace(user_data={})
    media_user = 970043
    _click(media_context, media_user, "vid3|entry|self_shot_scene_change", "history-media-01")
    _click(media_context, media_user, "vid3|source_media", "history-media-02")
    _send_video(media_context, media_user, "self-shot", "self-shot-u", 395)
    media_state = bot.video_uiflow3_state(media_context)
    assert media_state["navigation"]["current_step"] == "format"
    assert media_state["navigation"]["visible_step_stack"][-1] == "source"
    _click(media_context, media_user, "vid3|back", "history-media-03")
    assert bot.video_uiflow3_state(media_context)["navigation"]["current_step"] == "source"


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
    assert photo.index("handle_video_uiflow3_pending_media") < photo.index("handle_storyboard2_pending_media")
    assert photo.index("handle_video_uiflow3_pending_media") < photo.index("handle_video_scene3_pending_media")
    text_start = BOT_SOURCE.index("async def handle_message")
    text_end = BOT_SOURCE.index("\nasync def ", text_start + 20)
    text = BOT_SOURCE[text_start:text_end]
    assert text.index("handle_video_uiflow3_pending_text") < text.index("handle_video_profile_studio_pending_text")


def test_entry_mode_requires_real_source_and_keeps_video_to_video_out_of_public_ui() -> None:
    state = video_uiflow3.new_state("video_ai_real", draft_id="mode-source")
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|mode|video_video" not in _callbacks(markup)

    image_mode = video_uiflow3.set_entry_mode(state, "image_video")
    assert image_mode["source"]["required"] is True
    assert image_mode["source"]["kind"] == "raw_images"
    assert image_mode["navigation"]["current_step"] == "scene_count"

    capable = video_uiflow3.new_state(
        "video_ai_real",
        draft_id="mode-capable",
        capabilities={"video_to_video": True},
    )
    _text, markup = bot.video_uiflow3_screen_payload(capable)
    assert "vid3|mode|video_video" not in _callbacks(markup)

    user_id = 970076
    context = SimpleNamespace(user_data={})
    capable["owner_user_id"] = user_id
    capable["owner_chat_id"] = user_id
    bot.save_video_uiflow3_state(context, capable)
    rejected = _click(context, user_id, "vid3|mode|video_video", "mode-video-hidden-01")
    rejected_state = bot.video_uiflow3_state(context)
    assert rejected_state["entry_mode"] == ""
    assert rejected_state["navigation"]["current_step"] == "entry"
    assert rejected.answers


def test_each_source_branch_accepts_only_its_advertised_media_kind() -> None:
    user_id = 970037
    image_context = SimpleNamespace(user_data={})
    _click(image_context, user_id, "vid3|entry|video_ai_real", "kind-01")
    _click(image_context, user_id, "vid3|mode|image_video", "kind-02")
    _click(image_context, user_id, "vid3|scene_count|1", "kind-02a")
    _click(image_context, user_id, "vid3|ratio|9x16", "kind-02b")
    _click(image_context, user_id, "vid3|duration_scene|8", "kind-02c")
    _click(image_context, user_id, "vid3|format_done", "kind-02d")
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


def test_image_product_collects_multiple_source_photos_before_content() -> None:
    user_id = 970079
    context = SimpleNamespace(user_data={})
    _click(context, user_id, "vid3|entry|video_ai_real", "image-batch-01")
    _click(context, user_id, "vid3|mode|image_video", "image-batch-02")
    _click(context, user_id, "vid3|scene_count|2", "image-batch-03")
    _click(context, user_id, "vid3|ratio|9x16", "image-batch-04")
    _click(context, user_id, "vid3|duration_scene|8", "image-batch-05")
    _click(context, user_id, "vid3|format_done", "image-batch-06")
    _click(context, user_id, "vid3|source_media", "image-batch-07")

    _send_photo(context, user_id, "image-source-1", "image-source-u1", 404)
    first = bot.video_uiflow3_state(context)
    assert first["navigation"]["current_step"] == "source"
    assert (first.get("pending_input") or {}).get("kind") == "source_media"

    _send_photo(context, user_id, "image-source-2", "image-source-u2", 405)
    second = bot.video_uiflow3_state(context)
    assert [item["telegram_file_id"] for item in second["source"]["assets"]] == [
        "image-source-1",
        "image-source-2",
    ]
    assert second["navigation"]["current_step"] == "source"

    _input_text, input_markup = bot.video_uiflow3_screen_payload(second)
    assert "vid3|view|source" in _callbacks(input_markup)
    _click(context, user_id, "vid3|view|source", "image-batch-08")
    source = bot.video_uiflow3_state(context)
    assert source["navigation"]["current_step"] == "source"
    assert not source.get("pending_input")
    _source_text, source_markup = bot.video_uiflow3_screen_payload(source)
    assert "vid3|source_done" in _callbacks(source_markup)

    _click(context, user_id, "vid3|source_done", "image-batch-09")
    final = bot.video_uiflow3_state(context)
    assert final["navigation"]["current_step"] == "content_hub"
    assert final["format"]["ratio"] == "9:16"
    assert final["format"]["target_duration_seconds"] == 0
    assert final["format"]["scene_count"] == 2


def test_compact_public_flow_persists_character_voice_dialogue_and_returns_summary() -> None:
    context = SimpleNamespace(user_data={})
    user_id = 970032
    _click(context, user_id, "vid3|entry|video_ai_real", "q01")
    _click(context, user_id, "vid3|mode|prompt_video", "q02")
    _click(context, user_id, "vid3|scene_count|2", "q02a")
    _click(context, user_id, "vid3|ratio|9x16", "q03")
    _click(context, user_id, "vid3|duration_scene|8", "q04")
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
    _click(context, user_id, "vid3|scene_plan_auto", "q25b")
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

    state.pop("ui_view", None)
    state["navigation"]["current_step"] = "scene_assignment"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|music_scope" not in _callbacks(markup)
    assert "vid3|view|audio_options" in _callbacks(markup)

    state["capabilities"].update({"whole_video_music": True, "per_scene_music": True})
    state["ui_view"] = "music_scope"
    _text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)
    assert "vid3|music_set|whole_video" in callbacks
    assert "vid3|music_set|per_scene" in callbacks


def test_video_guide_teaches_content_first_and_returns_to_video_menu() -> None:
    text, markup = bot.localized_menu_content("guide_video_ai", False, "vi", user_id=970035)
    assert "Nội dung trước" in text or "Xác nhận Nội dung" in text
    assert "tổng số nhân vật" in text
    assert "Ý tưởng video chỉ là kho" in text
    assert "RouteEngine" not in text
    assert _callbacks(markup) == ["menu|main_video", "menu|main"]
    assert "menu|main_guide" not in _callbacks(markup)
