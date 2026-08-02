from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

from services import video_scene3_flow, video_tail9, video_uifreeze1


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?=@|(?:async )?def [A-Za-z_])", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _load_function(name: str, namespace: dict | None = None):
    scope = dict(namespace or {})
    exec("from __future__ import annotations\n" + _function_source(name), scope)
    return scope[name]


def _callbacks(markup) -> list[list[str]]:
    rows = getattr(markup, "inline_keyboard", markup)
    return [
        [str(getattr(button, "callback_data", button[1])) for button in row]
        for row in rows
    ]


def _ready_tail(*, source: str = "idea_catalog", scene_count: int = 1) -> dict:
    state = video_tail9.new_state(
        product_type="video_ai_real",
        session_id=f"tailflow16-{source}-{scene_count}",
        scene_count=scene_count,
        ratio="9:16",
        estimated_duration=scene_count * 8,
    )
    return video_tail9.apply_content_contract(
        state,
        {
            "content_source": source,
            "canonical_content_mode": source,
            "selected_prompt_text": "Prompt đã chọn và giữ nguyên.",
            "selected_prompt_revision": 4,
            "per_scene_content": [
                {"scene_index": index, "provider_prompt": f"Prompt cảnh {index}"}
                for index in range(1, scene_count + 1)
            ],
            "plan_status": "ready",
        },
    )


def _invoice_ready_tail() -> dict:
    state = _ready_tail()
    state = video_tail9.mark_branding_skipped(state)
    state = video_tail9.mark_audio_complete(state, skipped=True)
    state = video_tail9.prepare_summary(state)
    return video_tail9.select_package(
        state,
        quality_tier_id="200",
        package_id="product_video_200",
        pricing_snapshot={
            "quality_xu": 200,
            "price_xu": 200,
            "total_xu": 200,
            "scene_count": 1,
        },
        capability_snapshot={"ok": True, "engine_route": "video_ai_canonical"},
    )


def test_tailflow16_exact_state_order_has_no_separate_review() -> None:
    state = _ready_tail()
    assert video_tail9.TAIL_FLOW_VERSION == 17
    assert video_tail9.next_required_screen(state) == "logo"

    state = video_tail9.mark_branding_skipped(state)
    assert video_tail9.next_required_screen(state) == "summary"

    state = video_tail9.prepare_summary(state)
    assert state["summary_status"] == "ready"
    assert state["review_status"] == "ready"
    assert video_tail9.next_required_screen(state) == ""


def test_unified_summary_has_exact_title_and_four_rows() -> None:
    text_source = _function_source("video_tail9_summary_text")
    assert "📄 <b>Tổng hợp và kiểm tra video</b>" in text_source

    keyboard = _load_function(
        "video_tail9_summary_keyboard",
        {
            "video_scene3_keyboard": video_scene3_flow.validate_two_column_rows,
            "video_editengine1": SimpleNamespace(PRODUCT_TYPE="video_local_edit"),
        },
    )
    rows = _callbacks(keyboard(_ready_tail()))
    assert rows == [
        ["video_tail|review|scenes", "video_tail|review|edit"],
        ["video_tail|review|prompts", "video_tail|summary|logo"],
        ["video_tail|summary|audio", "video_tail|summary|continue"],
        ["video_tail|summary|back", "menu|main"],
    ]


def test_logo_and_planning_audio_forward_and_back_buttons_match_contract() -> None:
    namespace = {
        "video_scene3_keyboard": video_scene3_flow.validate_two_column_rows,
        "video_editengine1": SimpleNamespace(PRODUCT_TYPE="video_local_edit"),
        "VIDEO_TAIL9_AUDIO_LABELS": {
            "source_audio": "Âm thanh gốc",
            "dubbing": "Lồng tiếng",
            "music": "Nhạc nền",
            "sfx": "Hiệu ứng âm thanh",
            "subtitles": "Phụ đề",
        },
    }
    logo = _load_function("video_tail9_logo_keyboard", namespace)
    normal_logo = _callbacks(logo(_ready_tail()))
    edit_logo = _callbacks(logo({**_ready_tail(), "branding_back_to": "summary"}))

    assert normal_logo[-1] == ["video_tail|review|prompts", "menu|main"]
    assert edit_logo[-1] == ["video_tail|summary|open", "menu|main"]
    assert "def video_tail9_audio_keyboard" not in BOT_SOURCE
    assert "def video_tail9_volume_keyboard" not in BOT_SOURCE


def test_legacy_review_and_summary_callbacks_cannot_form_a_loop() -> None:
    handler = _function_source("handle_video_tail_callback")
    review = handler[handler.index('if section == "review":') : handler.index('if section == "summary":')]
    summary = handler[handler.index('if section == "summary":') : handler.index('if section == "audio":')]

    assert 'action in {"open", "summary", "review"}' in review
    assert 'video_tail9_render(query, uid, context, "summary")' in review
    assert 'if action == "audio":' in review
    assert "video_tail9_open_planning_audio" in review
    assert 'video_tail9_render(query, uid, context, "audio")' not in review
    assert 'video_tail9_render(query, uid, context, "review")' not in summary
    assert 'if action in {"open", "review"}:' in summary
    assert 'if action == "continue":' in summary
    assert 'video_tail9_render(query, uid, context, "quality")' in summary
    assert 'if action == "audio":' in summary
    assert "video_tail9_open_planning_audio" in summary
    assert 'video_tail9_render(query, uid, context, "audio")' not in summary
    assert 'if action == "back":' in summary


def test_scene_prompt_completion_enters_required_tail_gate_before_summary() -> None:
    profile_handler = _function_source("handle_video_profile_studio_callback")
    block = profile_handler[
        profile_handler.index('if action == "video_prompt_done":') :
        profile_handler.index('if action == "review_image_prompts":')
    ]
    normal_completion = block[block.index('if video_flow7_kind(state) == "storyboard":') :]

    assert 'video_profile_studio_step(context, state, "full_review"' in normal_completion
    assert 'video_tail9_render(query, uid, context, "summary")' in normal_completion
    assert 'video_tail9_render(query, uid, context, "review")' not in normal_completion


def test_summary_back_resets_logo_back_target_before_opening_logo() -> None:
    handler = _function_source("handle_video_tail_callback")
    summary = handler[handler.index('if section == "summary":') : handler.index('if section == "audio":')]
    back = summary[summary.index('if action == "back":') :]

    assert 'tail["branding_back_to"] = "prompt"' in back
    assert 'save_video_tail9_state(uid, context, tail, owner, host)' in back
    assert back.index('tail["branding_back_to"] = "prompt"') < back.index(
        'video_tail9_render(query, uid, context, "logo")'
    )


def test_content_and_prompt_edits_return_to_unified_summary() -> None:
    profile_handler = _function_source("handle_video_profile_studio_callback")
    tail_handler = _function_source("handle_video_tail_callback")
    selfshot_result = _function_source("video_selfshotflow4_handle_result")

    assert 'video_tail_return_to="summary"' in tail_handler
    assert 'if action == "scene_done":' in profile_handler
    assert 'target == "video_prompts" and str(state.get("video_tail_return_to") or "") == "summary"' in profile_handler
    assert 'if action == "image_prompt_done":' in profile_handler
    assert 'if action == "video_prompt_done":' in profile_handler
    assert 'return await video_tail9_render(query, uid, context, "summary")' in profile_handler
    assert 'current = {**host, "video_tail_return_to": "summary"}' in tail_handler
    assert 'return_to_summary = str(current.pop("video_tail_return_to", "") or "") == "summary"' in selfshot_result
    assert '"summary" if return_to_summary else "logo"' in selfshot_result


def test_normal_logo_and_audio_completion_each_advance_once() -> None:
    handler = _function_source("handle_video_tail_callback")
    audio = handler[handler.index('if section == "audio":') : handler.index('if section == "logo":')]
    logo = handler[handler.index('if section == "logo":') : handler.index('if section == "quality":')]

    assert audio.count('video_tail9_render(query, uid, context, "summary")') == 1
    assert "video_tail9_open_planning_audio" in audio
    assert 'video_tail9_render(query, uid, context, "quality")' not in audio
    assert 'action in {"back", "done", "skip"}' in audio
    assert logo.count('video_tail9_render(query, uid, context, "summary")') >= 2


def test_single_scene3_audio_owner_is_restored_on_normal_and_summary_paths() -> None:
    handler = _function_source("handle_video_profile_studio_callback")
    requirements = handler[handler.index('if action == "req_none":') : handler.index('if action == "material":')]

    assert 'if action == "audio_open":' in handler
    assert 'post_return_step="audio_plan"' in handler
    assert 'if action in {"audio_done", "audio_skip"}:' in handler
    assert 'return_step == "summary"' in handler
    assert 'video_profile_studio_step(context, state, "audio_plan")' in requirements
    assert 'video_profile_studio_step(context, state, "scene_plan")' not in requirements


def test_required_back_stack_is_single_parent_chain() -> None:
    handler = _function_source("handle_video_tail_callback")
    quality = handler[handler.index('if section == "quality":') : handler.index('if section == "confirm":')]
    confirm = handler[handler.index('if section == "confirm":') :]

    assert 'video_tail9_render(query, uid, context, "summary")' in quality
    assert 'video_tail9_render(query, uid, context, "invoice")' in confirm
    assert 'video_tail9_render(query, uid, context, "audio")' not in quality

    invoice_keyboard = _load_function(
        "video_tail9_invoice_keyboard",
        {"video_scene3_keyboard": video_scene3_flow.validate_two_column_rows},
    )
    confirmation_keyboard = _load_function(
        "video_tail9_confirm_keyboard",
        {"video_scene3_keyboard": video_scene3_flow.validate_two_column_rows},
    )
    assert _callbacks(invoice_keyboard())[-1][0] == "video_tail|quality|open"
    assert _callbacks(confirmation_keyboard())[-1][0] == "video_tail|confirm|back"


def test_idea_owner_prompt_and_scene_context_survive_unified_tail() -> None:
    state = _ready_tail(source="idea_catalog", scene_count=2)
    expected = {
        key: state[key]
        for key in (
            "video_product_type",
            "video_flow_owner",
            "content_source",
            "selected_prompt",
            "scene_count",
            "ratio",
            "scene_content",
        )
    }
    for transition in (
        video_tail9.mark_branding_skipped,
        lambda current: video_tail9.mark_audio_complete(current, skipped=True),
        video_tail9.prepare_summary,
    ):
        state = transition(state)
        assert {key: state[key] for key in expected} == expected


def test_tier_200_and_multiscene_pricing_regression_remain_locked() -> None:
    one_scene = video_uifreeze1.catalog_report(
        "video_ai_real",
        scene_count=1,
        ratio="9:16",
        required_capability="text_to_video",
    )
    two_scene = video_uifreeze1.catalog_report(
        "video_ai_real",
        scene_count=2,
        ratio="9:16",
        required_capability="text_to_video",
    )
    frame = video_uifreeze1.catalog_report("frame_video_local", scene_count=1, ratio="9:16")

    assert 200 in one_scene["tier_ids"]
    assert 200 not in two_scene["tier_ids"]
    assert frame["framevideo_excluded"] is True
    assert frame["offers"] == []


def test_submitted_state_is_idempotent_and_persists_public_status_fields() -> None:
    state = _invoice_ready_tail()
    first, created = video_tail9.mark_submitted(
        state,
        user_id=16001,
        job_id="73",
        public_processing_code="#73",
        submitted_at="2026-07-26T12:30:00+07:00",
        execution_state="queued",
    )
    second, created_again = video_tail9.mark_submitted(
        first,
        user_id=16001,
        job_id="73",
        public_processing_code="#73",
        submitted_at="2026-07-26T12:31:00+07:00",
        execution_state="processing",
    )

    assert created is True
    assert created_again is False
    assert second["job_id"] == "73"
    assert second["submit_user_id"] == "16001"
    assert second["public_processing_code"] == "#73"
    assert second["submitted_at"] == "2026-07-26T12:30:00+07:00"
    assert second["execution_state"] == "queued"
    assert second["final_confirmed"] is True
    assert second["status_stage"] == "confirmed"


def test_missing_memory_tail_recovers_same_persisted_job_and_invoice() -> None:
    recovered = video_tail9.recover_submission(
        _ready_tail(),
        {
            "user_id": 16002,
            "job_id": 91,
            "status": "processing",
            "submitted_at": "2026-07-26T13:00:00+07:00",
            "invoice_id": "pv:tailflow16:1:300",
            "quality_tier_id": 300,
            "package_id": "product_video_300",
            "scene_count": 1,
            "total_xu": 300,
        },
    )

    assert recovered["final_confirmed"] is True
    assert recovered["job_id"] == "91"
    assert recovered["public_processing_code"] == "#91"
    assert recovered["invoice_id"] == "pv:tailflow16:1:300"
    assert recovered["quality_tier_id"] == "300"
    assert recovered["package_id"] == "product_video_300"
    assert recovered["pricing_snapshot"]["total_xu"] == 300
    assert recovered["execution_state"] == "processing"


def test_persisted_recovery_is_scoped_to_same_product_session_and_owner() -> None:
    context_source = _function_source("video_tail9_context")
    handler = _function_source("handle_video_tail_callback")

    assert "same_recovery_scope = bool(" in context_source
    assert 'recovery_session_id == str(tail.get("video_session_id") or "")' in context_source
    assert "video_tail9.adapter_for(recovery_product)" in context_source
    assert 'recovery_owner == str(tail.get("video_flow_owner") or "")' in context_source
    for field in (
        "video_tail_submit_session_id",
        "video_tail_submit_product_type",
        "video_tail_submit_owner",
        "video_tail_submit_user_id",
    ):
        assert field in handler


def test_submit_with_accepted_job_always_hands_off_to_status() -> None:
    tail = _invoice_ready_tail()
    saved: list[dict] = []
    status_calls: list[dict] = []
    session = {
        "draft": {
            "b14_queue_job_id": 314,
            "b14_queue_job": {"id": 314, "status": "queued"},
            "b14_invoice": {"total_xu": 200, "quality_xu": 200},
        }
    }

    async def bridge(_update, _context):
        return "legacy-handler-returned"

    async def render_status(_query, _context, _uid, current, _owner, _host):
        status_calls.append(dict(current))
        return "status-panel"

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(tail), "scene3", {}),
            "video_tail9": video_tail9,
            "save_video_tail9_state": lambda _uid, _context, current, _owner, _host: saved.append(dict(current)),
            "video_tail9_apply_to_session": lambda *_args, **_kwargs: session,
            "handle_product_video_public_confirm_callback": bridge,
            "get_video_session": lambda _uid: session,
            "save_video_session": lambda _uid, current: current,
            "video_tail9_render_confirmed_status": render_status,
            "video_b14_is_admin_or_owner": lambda _uid: False,
            "get_user": lambda _uid: (200, None, None),
            "product_video_public_preflight_evaluation": lambda *_args, **_kwargs: {"ready": True},
            "product_video_worker_admission_status": lambda: {"worker_version_compatible": True},
            "now_text_safe": lambda: "2026-07-26T14:00:00+07:00",
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "VIDEO_TAIL9_STATE_KEY": "video_tail9",
        },
    )

    class Query:
        id = "tailflow16-submit-accepted"
        data = "video_tail|confirm|submit"
        from_user = SimpleNamespace(id=16003)

        async def answer(self, *_args, **_kwargs):
            return None

    result = asyncio.run(handler(SimpleNamespace(callback_query=Query()), SimpleNamespace()))

    assert result == "status-panel"
    assert len(status_calls) == 1
    assert status_calls[0]["job_id"] == "314"
    assert status_calls[0]["public_processing_code"] == "#314"
    assert saved[-1]["final_confirmed"] is True


def test_submit_exception_recovers_accepted_job_instead_of_returning_to_invoice() -> None:
    tail, _created = video_tail9.mark_submitted(
        _invoice_ready_tail(),
        user_id=16004,
        job_id="315",
        public_processing_code="#315",
        submitted_at="2026-07-26T14:05:00+07:00",
        execution_state="queued",
    )
    status_calls: list[dict] = []
    rendered_screens: list[str] = []

    async def failing_handler(_update, _context):
        raise RuntimeError("status handoff interrupted")

    async def render_status(_query, _context, _uid, current, _owner, _host):
        status_calls.append(dict(current))
        return "status-panel"

    async def legacy_render(_query, _uid, _context, screen):
        rendered_screens.append(screen)
        return screen

    guard = _load_function(
        "video_tail9_callback_guard",
        {
            "ApplicationHandlerStop": type("ApplicationHandlerStop", (Exception,), {}),
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
            "video_tail9_context": lambda _uid, _context: (dict(tail), "scene3", {}),
            "video_tail9_render_confirmed_status": render_status,
            "video_tail9_render": legacy_render,
        },
    )

    class Query:
        data = "video_tail|confirm|submit"
        from_user = SimpleNamespace(id=16004)

        async def answer(self, *_args, **_kwargs):
            return None

    result = asyncio.run(
        guard(failing_handler)(SimpleNamespace(callback_query=Query()), SimpleNamespace())
    )

    assert result == "status-panel"
    assert len(status_calls) == 1
    assert status_calls[0]["job_id"] == "315"
    assert rendered_screens == []


def test_submit_exception_without_job_opens_canonical_status_instead_of_blocker() -> None:
    tail = _invoice_ready_tail()
    rendered_screens: list[str] = []
    blocker_calls: list[str] = []
    status_calls: list[dict] = []

    async def failing_handler(_update, _context):
        raise RuntimeError("submit interrupted before acceptance")

    async def legacy_render(_query, _uid, _context, screen):
        rendered_screens.append(screen)
        return screen

    async def safe_send(_query, text, **_kwargs):
        blocker_calls.append(str(text))
        return "submit-blocker"

    async def render_status(_query, _context, _uid, current, _owner, _host):
        status_calls.append(dict(current))
        return "status-panel"

    guard = _load_function(
        "video_tail9_callback_guard",
        {
            "ApplicationHandlerStop": type("ApplicationHandlerStop", (Exception,), {}),
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
            "video_tail9_context": lambda _uid, _context: (dict(tail), "scene3", {}),
            "video_tail9_render": legacy_render,
            "video_tail9_prepare_submit_status": lambda _uid, _context, current, _owner, _host, snapshot: {
                **current,
                "submit_attempted": True,
                "submit_preflight_snapshot": dict(snapshot),
            },
            "video_tail9_render_confirmed_status": render_status,
            "video_tail9_submit_blocker_text": lambda: "Không thể gửi tác vụ lúc này.",
            "video_tail9_submit_blocker_keyboard": lambda: "submit-blocker-keyboard",
            "safe_edit_or_send": safe_send,
        },
    )

    class Query:
        data = "video_tail|confirm|submit"
        from_user = SimpleNamespace(id=16005)

        async def answer(self, *_args, **_kwargs):
            return None

    result = asyncio.run(
        guard(failing_handler)(SimpleNamespace(callback_query=Query()), SimpleNamespace())
    )

    assert result == "status-panel"
    assert blocker_calls == []
    assert rendered_screens == []
    assert len(status_calls) == 1


def test_submit_source_has_no_silent_job_branch_and_marks_status_render() -> None:
    handler = _function_source("handle_video_tail_callback")
    confirm = handler[handler.index('if section == "confirm":') :]
    status_sender = _function_source("video_b14_send_or_edit_status_panel")

    assert "video_tail9.recover_submission" in confirm
    assert "video_tail9.mark_submitted" not in confirm
    assert "video_tail9_render_confirmed_status" in confirm
    assert "video_tail9_prepare_submit_status" in confirm
    assert 'if response is None or bridge_preflight_blocked:' in confirm
    assert "video_tail9_submit_blocker_keyboard" not in confirm
    assert "_product_video_status_panel_rendered" in status_sender


def test_preconfirm_tail_contract_has_zero_provider_job_and_wallet_side_effects() -> None:
    report = video_uifreeze1.catalog_report(
        "video_ai_real",
        scene_count=1,
        ratio="9:16",
        required_capability="text_to_video",
    )
    assert report["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
