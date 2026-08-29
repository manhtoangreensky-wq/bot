from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import bot
from services import video_flow7


def _source(function) -> str:
    return inspect.getsource(function)


class _Query:
    def __init__(self, data: str, query_id: str) -> None:
        self.data = data
        self.id = query_id
        self.from_user = SimpleNamespace(id=7126457028)
        self.answer_count = 0

    async def answer(self, *_args, **_kwargs) -> None:
        self.answer_count += 1


def test_all_four_trend_lanes_converge_on_restored_content_flow() -> None:
    entry = _source(bot.video_trend2_entry_keyboard)
    callback = _source(bot._handle_video_trend2_callback_impl)
    pending = _source(bot.handle_video_trend2_pending_text)

    for callback_data in (
        "vtrend|catalog|latest",
        "vtrend|manual_trend",
        "vtrend|search",
        "vtrend|video_upload",
    ):
        assert callback_data in entry

    for source_branch in (
        'if action == "pick":',
        'if action == "search_pick":',
        'if action == "video_accept":',
    ):
        assert source_branch in callback
    assert 'elif pending == "manual_trend":' in pending
    assert 'video_trend2_open_screen(state, "scene_count"' in pending

    ratio_branch = callback[
        callback.index('if action == "ratio":'):
        callback.index('if action == "ratio_custom":')
    ]
    assert 'video_trend2_open_screen(state, "content_source", parent="aspect_ratio")' in ratio_branch
    assert "video_trend_prepare_entity_bridge" not in ratio_branch


def test_restored_trend_content_screens_and_callbacks_are_public() -> None:
    for screen in ("content_source", "profiles", "suggestions", "preview"):
        assert screen in bot.VIDEO_TREND2_PUBLIC_SCREENS
        assert screen in bot.VIDEO_TREND2_PARENT

    callback = _source(bot._handle_video_trend2_callback_impl)
    assert "VIDEO_TREND2_LEGACY_CONTENT_ACTIONS" not in callback
    for action in (
        "profiles",
        "profile",
        "suggestions_more",
        "suggestion",
        "manual_content",
        "edit_content",
        "idea_catalog",
        "continue",
    ):
        assert f'action == "{action}"' in callback or f'action in {{"manual_content", "edit_content"}}' in callback

    renderer = _source(bot.video_trend2_render)
    assert 'screen in {"content_source", "profiles", "suggestions", "preview"}' not in renderer
    for screen in ("content_source", "profiles", "suggestions", "preview"):
        assert f'if screen == "{screen}":' in renderer


def test_manual_trend_and_manual_content_use_the_full_flow_not_direct_tail() -> None:
    pending = _source(bot.handle_video_trend2_pending_text)
    before_search = pending[: pending.index('if pending == "trend_search":')]
    assert "video_manual_lane_open_shared_tail" not in before_search

    manual_trend = pending[
        pending.index('elif pending == "manual_trend":'):
        pending.index('elif pending == "scene_count":')
    ]
    assert '"manual_input": True' in manual_trend
    assert '"intake_lane": "manual"' in manual_trend
    assert 'video_trend2_open_screen(state, "scene_count"' in manual_trend

    manual_content = pending[
        pending.index('elif pending in {"manual_content", "edit_content"}:'):
        pending.index("else:\n        return False")
    ]
    assert 'video_trend2_open_screen(state, "preview"' in manual_content
    assert '"content_choice"' in manual_content


def test_trend_sequence_restores_content_idea_before_entities_and_tail() -> None:
    sequence = video_flow7.product_sequence("video_trend")
    assert sequence[:7] == (
        "trend_source",
        "scene_count",
        "aspect_ratio",
        "content_source",
        "content_profile_or_preset",
        "content_choice",
        "character",
    )
    assert sequence[-6:] == (
        "addons",
        "review",
        "quality",
        "invoice",
        "confirm",
        "status",
    )


def test_trend_reuses_existing_content_profile_and_context_controls() -> None:
    content_keyboard = _source(bot.video_trend2_content_source_keyboard)
    for label in (
        "Chọn loại nội dung",
        "Kho Ý tưởng video",
        "Tự nhập nội dung",
    ):
        assert label in content_keyboard

    requirements = tuple(bot.VIDEO_AI_REAL_PILOT_REQUIREMENT_CATEGORIES)
    assert any(key == "locations" or "Bối cảnh" in label for key, label in requirements)
    assert "video_trend_prepare_entity_bridge" in _source(bot._handle_video_trend2_callback_impl)


def test_ratio_callback_opens_restored_content_source_at_runtime(monkeypatch) -> None:
    rendered: list[dict] = []

    async def capture_render(_target, _context, state: dict, _lang: str = "vi"):
        rendered.append(dict(state))
        return state

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_trend2_render", capture_render)
    context = SimpleNamespace(user_data={
        bot.VIDEO_TREND2_STATE_KEY: {
            "screen": "aspect_ratio",
            "selected_trend": {"trend_id": "catalog-1", "title": "Trend đã chọn"},
            "scene_count": 2,
        }
    })
    query = _Query("vtrend|ratio|9:16", "restore-ratio")

    asyncio.run(
        bot._handle_video_trend2_callback_impl(
            SimpleNamespace(callback_query=query),
            context,
        )
    )

    state = context.user_data[bot.VIDEO_TREND2_STATE_KEY]
    assert query.answer_count == 1
    assert state["screen"] == "content_source"
    assert state["screen_parents"]["content_source"] == "aspect_ratio"
    assert state["aspect_ratio"] == "9:16"
    assert rendered[-1]["screen"] == "content_source"


def test_manual_trend_text_opens_scene_count_at_runtime(monkeypatch) -> None:
    rendered: list[dict] = []

    async def capture_render(_target, _context, state: dict, _lang: str = "vi"):
        rendered.append(dict(state))
        return state

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_trend2_render", capture_render)
    context = SimpleNamespace(user_data={
        bot.VIDEO_TREND2_STATE_KEY: {
            "screen": "entry",
            "pending_input": "manual_trend",
            "input_return_screen": "entry",
        }
    })
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=7126457028),
        message=SimpleNamespace(text="Xu hướng combat game AI vui vẻ"),
    )

    assert asyncio.run(bot.handle_video_trend2_pending_text(update, context)) is True

    state = context.user_data[bot.VIDEO_TREND2_STATE_KEY]
    assert state["screen"] == "scene_count"
    assert state["selected_trend"]["manual_input"] is True
    assert state["selected_trend"]["intake_lane"] == "manual"
    assert rendered[-1]["screen"] == "scene_count"


def test_manual_content_text_opens_preview_at_runtime(monkeypatch) -> None:
    rendered: list[dict] = []

    async def capture_render(_target, _context, state: dict, _lang: str = "vi"):
        rendered.append(dict(state))
        return state

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_trend2_render", capture_render)
    context = SimpleNamespace(user_data={
        bot.VIDEO_TREND2_STATE_KEY: {
            "screen": "content_source",
            "pending_input": "manual_content",
            "input_return_screen": "content_source",
            "selected_trend": {"trend_id": "manual_trend", "title": "Trend đã chọn"},
            "scene_count": 2,
            "aspect_ratio": "9:16",
        }
    })
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=7126457028),
        message=SimpleNamespace(text="Hai đội tranh tài trong đấu trường game hư cấu rồi bắt tay vui vẻ."),
    )

    assert asyncio.run(bot.handle_video_trend2_pending_text(update, context)) is True

    state = context.user_data[bot.VIDEO_TREND2_STATE_KEY]
    assert state["screen"] == "preview"
    assert state["content_choice"]["id"] == "manual:trend"
    assert "đấu trường game hư cấu" in state["content_choice"]["content"]
    assert rendered[-1]["screen"] == "preview"
