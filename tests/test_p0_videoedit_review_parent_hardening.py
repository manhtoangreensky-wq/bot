from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
from services import video_edit_state_machine as machine
from services import video_local_editing


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def _ready_screen_state(screen: str) -> dict:
    plan = video_local_editing.default_manual_edit_plan("")
    plan["trim"] = {"start_ms": 0, "end_ms": 10_000}
    return {
        "step": screen,
        "edit_mode": "manual_edit",
        "current_screen": screen,
        "screen_id": screen,
        "selected_tool": "manual",
        "last_section": "manual",
        "source_file_id": "telegram-source",
        "source_file_name": "source.mp4",
        "source_display_name": "source.mp4",
        "source_file_size": 4_096,
        "source_duration_ms": 10_000,
        "source_metadata": {
            "ok": True,
            "duration": 10.0,
            "duration_ms": 10_000,
            "width": 1_280,
            "height": 720,
            "fps": 30.0,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
        },
        "inspection_complete": True,
        "manual_edit_plan": plan,
    }


class _CallbackMessage:
    chat_id = 88_100

    def __init__(self) -> None:
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return None


class _CallbackQuery:
    def __init__(self, user_id: int, data: str) -> None:
        self.id = f"videoedit-hardening-{user_id}-{data}"
        self.from_user = SimpleNamespace(id=user_id, first_name="Video Edit")
        self.data = data
        self.message = _CallbackMessage()
        self.edits: list[tuple[str, dict]] = []
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))
        return None

    async def edit_message_text(self, text: str, **kwargs):
        self.edits.append((text, kwargs))
        return None


class _UploadMessage:
    def __init__(self, message_id: int, *, fail_replies: bool = False, on_reply=None) -> None:
        self.message_id = message_id
        self.fail_replies = fail_replies
        self.on_reply = on_reply
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        if self.on_reply is not None:
            callback_result = self.on_reply()
            if inspect.isawaitable(callback_result):
                await callback_result
        if self.fail_replies:
            raise RuntimeError("telegram reply unavailable")
        return None


def _press_videoedit(user_id: int, callback: str) -> _CallbackQuery:
    query = _CallbackQuery(user_id, callback)
    asyncio.run(
        bot.handle_video_editor_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        )
    )
    return query


def _store_destructive_manual_state(
    user_id: int,
    *,
    session_id: str,
    brightness_percent: int,
) -> dict:
    state = _ready_screen_state("workspace")
    plan = dict(state["manual_edit_plan"])
    plan["brightness_percent"] = brightness_percent
    state.pop("step", None)
    state.update(
        {
            "edit_session_id": session_id,
            "session_id": session_id,
            "state_revision": brightness_percent,
            "revision": brightness_percent,
            "manual_edit_plan": plan,
        }
    )
    return bot.set_video_editor_pending(user_id, "options", **state)


def _video_source(file_id: str = "candidate-video") -> dict:
    return {
        "source_file_id": file_id,
        "source_file_unique_id": f"unique-{file_id}",
        "source_file_name": "candidate.mp4",
        "source_file_size": 4_096,
        "source_mime_type": "video/mp4",
    }


def _successful_probe() -> dict:
    return {
        "ok": True,
        "duration": 10.0,
        "duration_ms": 10_000,
        "width": 1_280,
        "height": 720,
        "fps": 30.0,
        "has_video": True,
        "has_audio": True,
        "audio_stream_count": 1,
        "format_name": "mp4",
        "bytes": 4_096,
        "source_sha256": "a" * 64,
    }


@pytest.mark.parametrize(
    ("screen", "expected_text", "expected_back"),
    [
        ("cut", bot.video_local_cut_options_text("vi"), "videoedit|workspace"),
        (
            "join",
            bot.video_local_join_options_text(_ready_screen_state("join"), "vi"),
            "videoedit|workspace",
        ),
        ("frame", bot.video_local_frame_text("vi"), "videoedit|workspace"),
        (
            "transform",
            bot.video_local_transform_text("vi"),
            "videoedit|workspace",
        ),
        ("color", bot.video_local_color_text("vi"), "videoedit|workspace"),
        (
            "audio",
            bot.video_edit_audio_text(_ready_screen_state("audio"), "vi"),
            "videoedit|workspace",
        ),
        ("overlay", bot.video_local_overlay_text("vi"), "videoedit|workspace"),
        (
            "effects",
            bot.video_edit_effects_text("vi", source_ready=True),
            "videoedit|workspace",
        ),
    ],
)
def test_videoedit_canonical_renderer_keeps_every_exact_review_parent(
    screen: str,
    expected_text: str,
    expected_back: str,
) -> None:
    text, markup, parse_mode = bot.video_editor_current_render_model(
        _ready_screen_state(screen),
        "vi",
    )

    assert text == expected_text
    assert expected_back in _callbacks(markup)
    assert parse_mode == "HTML"


def test_videoedit_ai_review_returns_to_the_prompt_that_opened_it() -> None:
    state = {"return_to": "ai_prompt", "step": "review"}

    assert machine.review_back_callback(state) == "videoedit|ai_prompt"
    assert bot.video_edit_review_return_action(state) == "ai_prompt"


def test_videoedit_complete_local_ai_lane_keeps_every_back_edge_and_creates_no_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88_109
    bot.clear_video_editor_pending(user_id)
    submit_calls: list[dict] = []

    async def successful_probe(*_args):
        return _successful_probe()

    async def forbidden_submit(*_args, **_kwargs):
        submit_calls.append(dict(_kwargs))
        raise AssertionError("AI planning navigation must not submit a job")

    monkeypatch.setattr(
        bot,
        "video_editor_source_from_update",
        lambda _update: _video_source("ai-source"),
    )
    monkeypatch.setattr(bot, "inspect_video_editor_source", successful_probe)
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(
        bot,
        "video_edit_runtime_capability_admission",
        lambda feature_key, _state=None: {
            "ready": True,
            "feature_key": feature_key,
            "reason": "ready",
        },
    )
    monkeypatch.setattr(bot, "submit_video_edit_local_free_job", forbidden_submit)

    def last_callbacks(query: _CallbackQuery) -> list[str]:
        payload = query.edits[-1][1] if query.edits else query.message.replies[-1][1]
        return _callbacks(payload["reply_markup"])

    try:
        entry = _press_videoedit(user_id, "videoedit|ai")
        assert "videoedit|hub" in last_callbacks(entry)

        upload_message = _UploadMessage(7_900)
        upload_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id),
            message=upload_message,
            callback_query=None,
        )
        assert asyncio.run(
            bot.handle_video_editor_pending_upload(
                upload_update,
                SimpleNamespace(user_data={}),
            )
        ) is True
        source_callbacks = _callbacks(upload_message.replies[-1][1]["reply_markup"])
        assert "videoedit|ai_intent" in source_callbacks
        assert "videoedit|ai" in source_callbacks

        intent = _press_videoedit(user_id, "videoedit|ai_intent")
        assert "videoedit|ai_source" in last_callbacks(intent)

        intent_message = _UploadMessage(7_901)
        intent_message.text = "Làm sáng video nhưng giữ nguyên nội dung và âm thanh"
        assert asyncio.run(
            bot.handle_video_editor_pending_text(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=intent_message,
                    callback_query=None,
                ),
                SimpleNamespace(user_data={}),
            )
        ) is True
        compiled_state = dict(bot.get_video_editor_pending(user_id) or {})
        assert compiled_state["provider_call"] is False
        assert compiled_state["manual_edit_plan"]

        suggestions = _press_videoedit(user_id, "videoedit|ai_suggestions")
        suggestion_callbacks = last_callbacks(suggestions)
        assert "videoedit|ai_source" in suggestion_callbacks
        pick_callbacks = [
            callback
            for callback in suggestion_callbacks
            if callback.startswith("videoedit|ai_pick|")
        ]
        assert pick_callbacks

        settings = _press_videoedit(user_id, pick_callbacks[0])
        assert "videoedit|ai_suggestions" in last_callbacks(settings)

        prompt = _press_videoedit(user_id, "videoedit|ai_review")
        assert "videoedit|ai_settings" in last_callbacks(prompt)

        review = _press_videoedit(user_id, "videoedit|ai_invoice")
        assert "videoedit|ai_prompt" in last_callbacks(review)

        confirmation = _press_videoedit(user_id, "videoedit|confirmation")
        confirmation_callbacks = last_callbacks(confirmation)
        assert "videoedit|review" in confirmation_callbacks
        assert any(
            callback.startswith("videoedit|confirm_local|")
            for callback in confirmation_callbacks
        )

        final_state = dict(bot.get_video_editor_pending(user_id) or {})
        assert final_state["provider_call"] is False
        assert final_state["current_screen"] == "confirmation"
        assert submit_calls == []

        all_callbacks = (
            last_callbacks(entry)
            + source_callbacks
            + last_callbacks(intent)
            + suggestion_callbacks
            + last_callbacks(settings)
            + last_callbacks(prompt)
            + last_callbacks(review)
            + confirmation_callbacks
        )
        assert not any(
            callback.startswith(
                ("vproduct|", "framevideo|", "subdub|", "lvs27a|", "lvs27b|")
            )
            for callback in all_callbacks
        )
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("return_to", "expected"),
    [
        ("ai_suggestions", "videoedit|ai_suggestions"),
        ("ai_settings", "videoedit|ai_settings"),
    ],
)
def test_videoedit_ai_review_keeps_every_exact_planning_parent(
    return_to: str,
    expected: str,
) -> None:
    assert machine.review_back_callback({"return_to": return_to}) == expected
    assert bot.video_edit_review_return_action({"return_to": return_to}) == return_to


def test_videoedit_canonical_ai_plan_can_reenter_prompt_without_reviving_provider_execution() -> None:
    source = Path(bot.__file__).read_text(encoding="utf-8")
    start = source.index("VIDEO_EDIT_LEGACY_AI_CONTROL_ACTIONS = {")
    end = source.index('if action.startswith("ai_"):', start)
    redirect_guard = source[start:end]

    assert "canonical_ai_planning_action" in redirect_guard
    assert "and not canonical_ai_planning_action" in redirect_guard
    assert 'action in {"ai_review", "ai_prompt"}' in redirect_guard
    assert "submit_video_ai_edit_job" not in redirect_guard


def test_videoedit_legacy_review_dispatches_through_the_canonical_renderer() -> None:
    source = Path(bot.__file__).read_text(encoding="utf-8")
    start = source.index('if action in {"edit_operation", "edit"}:')
    end = source.index('if action == "prompts":', start)
    legacy_return_block = source[start:end]

    assert "video_editor_current_render_model" in legacy_return_block


def test_videoedit_legacy_tail_review_commit_uses_full_state_cas() -> None:
    source = Path(bot.__file__).read_text(encoding="utf-8")
    start = source.index("async def video_edit_legacy_tail_compatibility(")
    end = source.index("\n\n@video_tail9_callback_guard", start)
    helper = source[start:end]

    assert "video_editor_state_snapshot" in helper
    assert "compare_and_set_video_editor_pending" in helper
    assert "rerender_video_editor_after_stale_commit" in helper
    assert "return set_video_editor_pending" not in helper


def test_videoedit_legacy_tail_cas_preserves_and_rerenders_a_job_status_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88_002
    initial = _ready_screen_state("workspace")
    initial.pop("step", None)
    bot.set_video_editor_pending(user_id, "options", **initial)
    job = {
        "id": 8124,
        "user_id": str(user_id),
        "job_type": bot.video_editengine1.WORKER_JOB_TYPE,
        "status": "queued",
        "xu_cost": 0,
    }
    monkeypatch.setattr(bot, "get_local_worker_job", lambda job_id: job if job_id == 8124 else None)
    monkeypatch.setattr(
        bot,
        "video_local_job_progress_payload",
        lambda _job: {"stage": "received", "processed": 0, "total": 1, "delivered": 0},
    )
    monkeypatch.setattr(bot, "video_editengine1_job_for_worker", lambda _job_id: {})
    rendered: list[str] = []
    winner: dict = {}

    async def fake_safe_edit_or_send(_query, text, *, post_render=None, **_kwargs):
        rendered.append(str(text))
        if len(rendered) == 1:
            winner.update(
                bot.update_video_editor_pending(
                    user_id,
                    "job_status",
                    current_screen="job_status",
                    screen_id="job_status",
                    job_id=8124,
                    status="queued",
                )
            )
        if post_render is not None:
            result = post_render()
            if inspect.isawaitable(result):
                await result
        return True

    class _Query:
        async def answer(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_safe_edit_or_send)
    try:
        asyncio.run(
            bot.video_edit_legacy_tail_compatibility(
                _Query(),
                user_id,
                {},
                {},
            )
        )

        assert bot.video_editor_state_snapshot(bot.get_video_editor_pending(user_id)) == winner
        assert len(rendered) == 2
        assert "Trạng thái chỉnh sửa video" in rendered[-1]
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_canonical_renderer_reconstructs_a_winning_job_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = {
        "id": 8123,
        "user_id": "88001",
        "job_type": "video_local_edit",
        "status": "queued",
        "xu_cost": 0,
    }
    monkeypatch.setattr(bot, "get_local_worker_job", lambda job_id: job if job_id == 8123 else None)
    monkeypatch.setattr(
        bot,
        "video_local_job_progress_payload",
        lambda _job: {"stage": "received", "processed": 0, "total": 1, "delivered": 0},
    )
    monkeypatch.setattr(bot, "video_editengine1_job_for_worker", lambda _job_id: {})
    state = _ready_screen_state("job_status")
    state.update({"step": "job_status", "current_screen": "job_status", "job_id": 8123})

    text, markup, parse_mode = bot.video_editor_current_render_model(state, "vi")

    assert "Trạng thái chỉnh sửa video" in text
    assert "#8123" in text
    assert "videoedit|status|8123" in _callbacks(markup)
    assert parse_mode == "HTML"


@pytest.mark.parametrize("product_type", ["video_edit", "video_local_edit"])
def test_videoedit_shared_tail_surfaces_only_canonical_local_actions(
    product_type: str,
) -> None:
    tail = {"video_product_type": product_type}
    text = bot.video_tail9_summary_text(tail)
    callbacks = _callbacks(bot.video_tail9_summary_keyboard(tail))
    review_callbacks = _callbacks(bot.video_tail9_video_edit_review_keyboard())
    operation_callbacks = _callbacks(bot.video_tail9_video_edit_operations_keyboard())
    source_callbacks = _callbacks(bot.video_tail9_video_edit_source_keyboard())

    assert "Tiếp tục chọn gói" not in text
    assert "quy trình chỉnh sửa" in text.lower()
    assert callbacks
    assert review_callbacks
    owned_callbacks = callbacks + review_callbacks + operation_callbacks + source_callbacks
    assert all(
        callback.startswith("videoedit|") or callback == "menu|main"
        for callback in owned_callbacks
    )
    assert not any(callback.startswith("video_tail|") for callback in owned_callbacks)


def test_videoedit_unbound_legacy_split_reset_callback_fails_closed() -> None:
    user_id = 88_109
    bot.clear_video_editor_pending(user_id)
    try:
        before = _store_destructive_manual_state(
            user_id,
            session_id="unbound-callback-session",
            brightness_percent=130,
        )

        stale = _press_videoedit(user_id, "videoedit|split_reset_manual")

        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == bot.video_editor_state_snapshot(before)
        assert stale.answers
        assert stale.answers[-1][1].get("show_alert") is True
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize("replacement_kind", ["new_plan", "new_session"])
def test_videoedit_split_reset_warning_is_bound_to_the_exact_warned_state(
    replacement_kind: str,
) -> None:
    user_id = 88_110
    bot.clear_video_editor_pending(user_id)
    try:
        _store_destructive_manual_state(
            user_id,
            session_id="warned-session",
            brightness_percent=130,
        )
        warning = _press_videoedit(user_id, "videoedit|split_from_manual")
        warning_markup = warning.edits[-1][1]["reply_markup"]
        reset_callbacks = [
            callback
            for callback in _callbacks(warning_markup)
            if callback.startswith("videoedit|split_reset_manual")
        ]

        assert len(reset_callbacks) == 1
        warned_callback = reset_callbacks[0]

        if replacement_kind == "new_plan":
            current = dict(bot.get_video_editor_pending(user_id) or {})
            newer_plan = dict(current.get("manual_edit_plan") or {})
            newer_plan["brightness_percent"] = 175
            winner = bot.update_video_editor_pending(
                user_id,
                manual_edit_plan=newer_plan,
                state_revision=131,
                revision=131,
            )
        else:
            winner = _store_destructive_manual_state(
                user_id,
                session_id="replacement-session",
                brightness_percent=175,
            )

        stale = _press_videoedit(user_id, warned_callback)

        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == bot.video_editor_state_snapshot(winner)
        assert stale.answers
        assert stale.answers[-1][1].get("show_alert") is True
        assert warned_callback.startswith("videoedit|split_reset_manual|")
        assert warned_callback.removeprefix("videoedit|split_reset_manual|")
        assert len(warned_callback.encode("utf-8")) <= 64
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_bot_intake_claim_is_exclusive_while_probe_is_in_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88_120
    bot.clear_video_editor_pending(user_id)
    probe_calls: list[str] = []

    async def fake_inspect(_context, source):
        probe_calls.append(str(source.get("source_file_id") or ""))
        return _successful_probe()

    monkeypatch.setattr(
        bot,
        "video_editor_source_from_update",
        lambda _update: _video_source(),
    )
    monkeypatch.setattr(bot, "inspect_video_editor_source", fake_inspect)
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    try:
        bot.start_video_edit_lane_state(
            user_id,
            "manual_edit",
            edit_session_id="busy-intake-session",
        )
        busy = bot.update_video_editor_pending(
            user_id,
            intake_in_progress=True,
            last_media_message_id=7_201,
        )
        message = _UploadMessage(7_202)

        asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=message,
                    callback_query=None,
                ),
                SimpleNamespace(user_data={}),
            )
        )

        assert probe_calls == []
        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == bot.video_editor_state_snapshot(busy)
    finally:
        bot.clear_video_editor_pending(user_id)


def test_canonical_videoedit_intake_never_mutates_shared_recent_media_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88_121
    bot.clear_video_editor_pending(user_id)
    cache_calls: list[int] = []
    prior_recent = {"file_id": "other-product-video", "created_at": 1.0}
    bot.LAST_USER_VIDEO[user_id] = dict(prior_recent)

    async def successful_probe(*_args):
        return _successful_probe()

    def forbidden_shared_cache(_update):
        cache_calls.append(user_id)
        bot.LAST_USER_VIDEO[user_id] = {
            "file_id": "stale-videoedit-candidate",
            "created_at": 2.0,
        }
        return "video"

    monkeypatch.setattr(
        bot,
        "video_editor_source_from_update",
        lambda _update: _video_source("isolated-videoedit-source"),
    )
    monkeypatch.setattr(bot, "inspect_video_editor_source", successful_probe)
    monkeypatch.setattr(bot, "cache_recent_media_state", forbidden_shared_cache)
    try:
        bot.start_video_edit_lane_state(
            user_id,
            "manual_edit",
            edit_session_id="shared-cache-isolation-session",
        )
        message = _UploadMessage(7_211)

        assert asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=message,
                    callback_query=None,
                ),
                SimpleNamespace(user_data={}),
            )
        ) is True

        assert cache_calls == []
        assert bot.LAST_USER_VIDEO[user_id] == prior_recent
    finally:
        bot.clear_video_editor_pending(user_id)
        bot.LAST_USER_VIDEO.pop(user_id, None)


def test_all_videoedit_upload_lanes_avoid_the_cross_product_recent_media_cache() -> None:
    source = Path(bot.__file__).read_text(encoding="utf-8")
    start = source.index("async def handle_video_editor_pending_upload")
    end = source.index("async def handle_video_editor_invalid_intake_text", start)

    assert "cache_recent_media_state(" not in source[start:end]


@pytest.mark.parametrize("probe_ok", [True, False], ids=["completion", "failure"])
def test_videoedit_probe_result_uses_full_state_cas_and_rerenders_the_winner(
    monkeypatch: pytest.MonkeyPatch,
    probe_ok: bool,
) -> None:
    user_id = 88_130 + int(probe_ok)
    bot.clear_video_editor_pending(user_id)
    winner: dict = {}

    async def fake_inspect(_context, _source):
        await asyncio.sleep(0)
        winner.update(
            bot.video_editor_state_snapshot(
                bot.update_video_editor_pending(
                    user_id,
                    requested_group="color",
                    return_to="videoedit|color",
                    status="newer_state_won_during_probe",
                )
            )
        )
        if probe_ok:
            return _successful_probe()
        return {"ok": False, "reason": "ffprobe_failed"}

    monkeypatch.setattr(
        bot,
        "video_editor_source_from_update",
        lambda _update: _video_source(),
    )
    monkeypatch.setattr(bot, "inspect_video_editor_source", fake_inspect)
    monkeypatch.setattr(
        bot,
        "video_editor_telegram_probe_fallback",
        lambda _source, reason: {"ok": False, "reason": reason},
    )
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    try:
        claimed_identity = bot.start_video_edit_lane_state(
            user_id,
            "manual_edit",
            edit_session_id="claimed-intake-session",
        )
        message = _UploadMessage(7_301 + int(probe_ok))

        result = asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=message,
                    callback_query=None,
                ),
                SimpleNamespace(user_data={}),
            )
        )

        assert result is True
        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == winner
        assert winner["edit_session_id"] == claimed_identity["edit_session_id"]
        assert winner["state_revision"] == claimed_identity["state_revision"]
        expected_text, expected_markup, expected_parse_mode = (
            bot.video_editor_current_render_model(winner, "vi")
        )
        actual_text, actual_kwargs = message.replies[-1]
        assert expected_text in actual_text
        assert _callbacks(actual_kwargs["reply_markup"]) == _callbacks(expected_markup)
        assert actual_kwargs.get("parse_mode") == expected_parse_mode
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_intake_exception_rollback_cannot_restore_over_a_newer_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88_140
    bot.clear_video_editor_pending(user_id)
    winner: dict = {}

    async def fake_inspect(_context, _source):
        await asyncio.sleep(0)
        winner.update(
            bot.video_editor_state_snapshot(
                bot.update_video_editor_pending(
                    user_id,
                    requested_group="effects",
                    return_to="videoedit|effects",
                    status="newer_state_won_before_reply_failure",
                )
            )
        )
        return _successful_probe()

    monkeypatch.setattr(
        bot,
        "video_editor_source_from_update",
        lambda _update: _video_source(),
    )
    monkeypatch.setattr(bot, "inspect_video_editor_source", fake_inspect)
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    try:
        bot.start_video_edit_lane_state(
            user_id,
            "manual_edit",
            edit_session_id="rollback-claimed-session",
        )
        message = _UploadMessage(7_401, fail_replies=True)

        result = asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=message,
                    callback_query=None,
                ),
                SimpleNamespace(user_data={}),
            )
        )

        assert result is True
        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == winner
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_reply_failure_guard_preserves_concurrent_winner_with_full_state_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88_141
    bot.clear_video_editor_pending(user_id)
    winner: dict = {}
    fired = False

    monkeypatch.setattr(
        bot,
        "video_editor_source_from_update",
        lambda _update: _video_source(),
    )

    async def successful_probe(*_args):
        return _successful_probe()

    monkeypatch.setattr(bot, "inspect_video_editor_source", successful_probe)
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)

    async def commit_newer_state_before_reply_failure() -> None:
        nonlocal fired
        if fired:
            return
        fired = True
        current = dict(bot.get_video_editor_pending(user_id) or {})
        winner.update(
            bot.update_video_editor_pending(
                user_id,
                requested_group="effects",
                status="newer_state_won_during_reply",
                state_revision=bot.safe_int(current.get("state_revision"), 0) + 1,
                revision=bot.safe_int(current.get("revision"), 0) + 1,
            )
        )

    async def run_concurrent_winner() -> None:
        await asyncio.create_task(commit_newer_state_before_reply_failure())

    try:
        bot.start_video_edit_lane_state(
            user_id,
            "manual_edit",
            edit_session_id="reply-race-session",
        )
        message = _UploadMessage(
            7_402,
            fail_replies=True,
            on_reply=run_concurrent_winner,
        )
        result = asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    message=message,
                    callback_query=None,
                ),
                SimpleNamespace(user_data={}),
            )
        )

        assert result is True
        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == bot.video_editor_state_snapshot(winner)
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_callback_guard_preserves_a_concurrent_full_state_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88_143
    bot.clear_video_editor_pending(user_id)
    winner: dict = {}
    state = _ready_screen_state("effects")
    state.pop("step", None)
    state.update(
        {
            "entry_context": "manual_effects",
            "last_section": "manual",
            "state_revision": 10,
            "revision": 10,
        }
    )
    bot.set_video_editor_pending(user_id, "manual_effects", **state)

    monkeypatch.setattr(
        bot,
        "video_edit_runtime_capability_admission",
        lambda *_args, **_kwargs: {"ready": True, "reason": "ready"},
    )

    async def commit_concurrent_winner() -> None:
        current = dict(bot.get_video_editor_pending(user_id) or {})
        winner.update(
            bot.update_video_editor_pending(
                user_id,
                status="callback_concurrent_winner",
                requested_group="audio",
                state_revision=bot.safe_int(current.get("state_revision"), 0) + 1,
                revision=bot.safe_int(current.get("revision"), 0) + 1,
            )
        )

    async def fail_after_concurrent_winner(*_args, **_kwargs):
        await asyncio.create_task(commit_concurrent_winner())
        raise RuntimeError("telegram callback render unavailable")

    monkeypatch.setattr(bot, "safe_edit_or_send", fail_after_concurrent_winner)
    query = _CallbackQuery(user_id, "videoedit|effect_pick|effect_fade")
    try:
        assert asyncio.run(
            bot.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        ) is True

        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == bot.video_editor_state_snapshot(winner)
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_auxiliary_upload_guard_preserves_a_concurrent_full_state_winner() -> None:
    user_id = 88_144
    bot.clear_video_editor_pending(user_id)
    winner: dict = {}
    state = _ready_screen_state("overlay")
    state.pop("step", None)
    state.update({"state_revision": 20, "revision": 20})
    bot.set_video_editor_pending(user_id, "await_logo", **state)

    async def commit_concurrent_winner() -> None:
        current = dict(bot.get_video_editor_pending(user_id) or {})
        winner.update(
            bot.update_video_editor_pending(
                user_id,
                status="auxiliary_upload_concurrent_winner",
                requested_group="subtitle",
                state_revision=bot.safe_int(current.get("state_revision"), 0) + 1,
                revision=bot.safe_int(current.get("revision"), 0) + 1,
            )
        )

    async def auxiliary_upload_with_failed_reply(_update, _context):
        bot.update_video_editor_screen(
            user_id,
            "logo_options",
            parent_callback="videoedit|overlay",
            logo_source={"file_id": "logo-candidate"},
        )
        await asyncio.create_task(commit_concurrent_winner())
        raise RuntimeError("telegram auxiliary reply unavailable")

    guarded = bot.video_editor_message_state_guard(
        auxiliary_upload_with_failed_reply
    )
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id))
    try:
        with pytest.raises(RuntimeError, match="auxiliary reply unavailable"):
            asyncio.run(guarded(update, SimpleNamespace(user_data={})))

        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == bot.video_editor_state_snapshot(winner)
    finally:
        bot.clear_video_editor_pending(user_id)


def test_outer_media_guard_never_recovers_over_a_videoedit_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88_145
    bot.clear_video_editor_pending(user_id)
    winner: dict = {}
    recovery_calls: list[str] = []
    state = _ready_screen_state("overlay")
    state.pop("step", None)
    state.update({"state_revision": 30, "revision": 30})
    bot.set_video_editor_pending(user_id, "await_logo", **state)

    async def commit_concurrent_winner() -> None:
        current = dict(bot.get_video_editor_pending(user_id) or {})
        winner.update(
            bot.update_video_editor_pending(
                user_id,
                status="outer_guard_concurrent_winner",
                requested_group="subtitle",
                state_revision=bot.safe_int(current.get("state_revision"), 0) + 1,
                revision=bot.safe_int(current.get("revision"), 0) + 1,
            )
        )

    async def failed_videoedit_upload(_update, _context):
        bot.update_video_editor_screen(
            user_id,
            "logo_options",
            parent_callback="videoedit|overlay",
            logo_source={"file_id": "logo-candidate"},
        )
        await asyncio.create_task(commit_concurrent_winner())
        raise RuntimeError("telegram upload reply unavailable")

    async def forbidden_product_recovery(_update, _context, *, handler_name: str):
        recovery_calls.append(handler_name)
        bot.update_video_editor_pending(
            user_id,
            status="product_recovery_overwrite",
        )
        return True

    monkeypatch.setattr(
        bot,
        "recover_product_video_media_failure",
        forbidden_product_recovery,
    )
    guarded = bot.product_video_media_failure_guard(
        bot.video_editor_message_state_guard(failed_videoedit_upload)
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=_UploadMessage(7_501),
    )
    try:
        assert asyncio.run(guarded(update, SimpleNamespace(user_data={}))) is True
        assert recovery_calls == []
        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == bot.video_editor_state_snapshot(winner)
    finally:
        bot.clear_video_editor_pending(user_id)


def test_outer_media_guard_keeps_normal_videoedit_recovery_after_exact_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88_146
    bot.clear_video_editor_pending(user_id)
    recovery_calls: list[str] = []
    recovery_states: list[dict] = []
    state = _ready_screen_state("overlay")
    state.pop("step", None)
    state.update({"state_revision": 40, "revision": 40})
    initial = bot.set_video_editor_pending(user_id, "await_logo", **state)

    async def failed_videoedit_upload(_update, _context):
        bot.update_video_editor_screen(
            user_id,
            "logo_options",
            parent_callback="videoedit|overlay",
            logo_source={"file_id": "logo-candidate"},
        )
        raise RuntimeError("telegram upload reply unavailable")

    async def recover_normal_upload(update, _context, *, handler_name: str):
        recovery_calls.append(handler_name)
        recovery_states.append(
            bot.video_editor_state_snapshot(
                bot.get_video_editor_pending(user_id)
            )
        )
        await update.message.reply_text(
            "⚠️ Chưa mở được tệp vừa gửi. Kế hoạch vẫn được giữ nguyên."
        )
        return True

    monkeypatch.setattr(
        bot,
        "recover_product_video_media_failure",
        recover_normal_upload,
    )
    guarded = bot.product_video_media_failure_guard(
        bot.video_editor_message_state_guard(failed_videoedit_upload)
    )
    message = _UploadMessage(7_502)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=message,
    )
    try:
        assert asyncio.run(guarded(update, SimpleNamespace(user_data={}))) is True
        assert recovery_calls == ["failed_videoedit_upload"]
        assert recovery_states == [bot.video_editor_state_snapshot(initial)]
        assert message.replies
        assert "Kế hoạch vẫn được giữ nguyên" in message.replies[-1][0]
        assert bot.video_editor_state_snapshot(
            bot.get_video_editor_pending(user_id)
        ) == bot.video_editor_state_snapshot(initial)
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_stale_rerender_log_never_exposes_private_exception_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs: list[str] = []

    async def fail_render(*_args, **_kwargs):
        raise RuntimeError("PRIVATE_VIDEO_EDIT_PATH")

    class _Logger:
        @staticmethod
        def warning(message, *args):
            logs.append(str(message) % args if args else str(message))

    monkeypatch.setattr(bot, "safe_edit_or_send", fail_render)
    monkeypatch.setattr(bot, "logger", _Logger())
    query = _CallbackQuery(88_142, "videoedit|workspace")

    asyncio.run(
        bot.rerender_video_editor_after_stale_commit(
            query,
            _ready_screen_state("workspace"),
            "vi",
        )
    )

    assert logs
    assert "RuntimeError" in "\n".join(logs)
    assert "PRIVATE_VIDEO_EDIT_PATH" not in "\n".join(logs)
