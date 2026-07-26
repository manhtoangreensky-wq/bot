from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

from services import video_tail9, video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _load_function(name: str, namespace: dict | None = None):
    scope = dict(namespace or {})
    exec("from __future__ import annotations\n" + _function_source(name), scope)
    return scope[name]


def _callbacks(rows) -> list[str]:
    return [str(callback) for row in rows for _label, callback in row]


def _ready_content_state() -> dict:
    state = video_tail9.new_state(
        product_type="video_ai_real",
        session_id="tail-confirm-logo-idea",
        scene_count=1,
        ratio="9:16",
    )
    return video_tail9.apply_content_contract(
        state,
        {
            "content_source": "idea_catalog",
            "canonical_content_mode": "idea_catalog",
            "selected_prompt_text": "Prompt đã chọn từ Kho Ý tưởng video.",
            "selected_prompt_revision": 2,
            "per_scene_content": [{"scene": 1, "content": "Cảnh mở đầu"}],
            "plan_status": "ready",
        },
    )


def test_tail_requires_branding_summary_review_then_audio_before_quality() -> None:
    state = _ready_content_state()
    assert video_tail9.next_required_screen(state) == "logo"
    assert video_tail9.prepare_summary(state)["summary_status"] == "not_ready"

    state = video_tail9.mark_branding_complete(state)
    assert state["logo_status"] == "skipped"
    assert state["watermark_status"] == "skipped"
    assert video_tail9.next_required_screen(state) == "summary"

    state = video_tail9.prepare_summary(state)
    assert state["summary_status"] == "ready"
    assert video_tail9.next_required_screen(state) == "review"

    state = video_tail9.mark_review_complete(state)
    assert video_tail9.next_required_screen(state) == "audio"

    state = video_tail9.mark_audio_complete(state)
    assert state["audio_status"] == "skipped"
    assert video_tail9.next_required_screen(state) == ""


def test_branding_done_preserves_saved_logo_and_skips_only_missing_watermark() -> None:
    state = video_tail9.mark_audio_complete(_ready_content_state(), skipped=True)
    state["logo_config"] = {
        "enabled": True,
        "asset_file_id": "telegram-logo-file",
        "position": "top_right",
    }
    state["logo_status"] = "configured"

    completed = video_tail9.mark_branding_complete(state)

    assert completed["logo_status"] == "configured"
    assert completed["logo_config"]["asset_file_id"] == "telegram-logo-file"
    assert completed["watermark_status"] == "skipped"


def test_invoice_opens_a_distinct_confirmation_screen_before_submit() -> None:
    validated = video_scene3_flow.validate_two_column_rows
    invoice_keyboard = _load_function(
        "video_tail9_invoice_keyboard",
        {"video_scene3_keyboard": validated},
    )
    confirm_keyboard = _load_function(
        "video_tail9_confirm_keyboard",
        {"video_scene3_keyboard": validated},
    )

    assert _callbacks(invoice_keyboard()).count("video_tail|confirm|open") == 1
    confirm_callbacks = _callbacks(confirm_keyboard())
    assert confirm_callbacks.count("video_tail|confirm|submit") == 1
    assert confirm_callbacks.count("video_tail|confirm|back") == 1
    assert "video_tail|quality|open" not in confirm_callbacks

    handler = _function_source("handle_video_tail_callback")
    confirm = handler[handler.index('if section == "confirm":') :]
    open_at = confirm.index('if action == "open":')
    submit_at = confirm.index('if action == "submit":')
    provider_bridge_at = confirm.index('query.data = "vproduct|b14_confirm"')
    assert open_at < submit_at < provider_bridge_at


def test_confirm_open_is_side_effect_free_and_renders_only_the_confirmation() -> None:
    tail = video_tail9.mark_branding_skipped(_ready_content_state())
    tail = video_tail9.prepare_summary(tail)
    tail = video_tail9.mark_review_complete(tail)
    tail = video_tail9.mark_audio_complete(tail, skipped=True)
    tail = video_tail9.select_package(
        tail,
        quality_tier_id="300",
        package_id="product_video_300",
        pricing_snapshot={"total_xu": 300, "price_xu": 300},
        capability_snapshot={"ok": True, "engine_route": "video_ai_canonical"},
    )
    rendered: list[str] = []
    saved: list[dict] = []

    async def render(_query, _uid, _context, screen):
        rendered.append(screen)
        return screen

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(tail), "scene3", {}),
            "video_tail9": video_tail9,
            "save_video_tail9_state": lambda _uid, _context, state, _owner, _host: saved.append(dict(state)),
            "video_tail9_render": render,
        },
    )

    class Query:
        id = "confirm-open-side-effect-free"
        data = "video_tail|confirm|open"
        from_user = SimpleNamespace(id=914003)
        answers = 0

        async def answer(self, *_args, **_kwargs):
            self.answers += 1

    query = Query()
    result = asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert result == "confirm"
    assert rendered == ["confirm"]
    assert query.answers == 1
    assert saved[-1]["job_id"] == ""
    assert saved[-1]["final_confirmed"] is False


def test_stale_audio_done_cannot_bypass_branding_and_summary() -> None:
    tail = _ready_content_state()
    rendered: list[str] = []

    async def render(_query, _uid, _context, screen):
        rendered.append(screen)
        return screen

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(tail), "scene3", {}),
            "video_tail9": video_tail9,
            "save_video_tail9_state": lambda *_args, **_kwargs: None,
            "video_tail9_render": render,
        },
    )

    class Query:
        id = "audio-done-opens-logo"
        data = "video_tail|audio|done"
        from_user = SimpleNamespace(id=914004)

        async def answer(self, *_args, **_kwargs):
            return None

    result = asyncio.run(handler(SimpleNamespace(callback_query=Query()), SimpleNamespace()))

    assert result == "logo"
    assert rendered == ["logo"]


def test_confirm_recovery_returns_to_invoice_instead_of_quality_catalog() -> None:
    guard = _function_source("video_tail9_callback_guard")
    assert '"confirm": "invoice"' in guard
    assert '"confirm": "video_tail|confirm|back"' in guard


def test_summary_and_quality_renderers_enforce_the_shared_tail_order() -> None:
    renderer = _function_source("video_tail9_render")
    assert "video_tail9.next_required_screen(tail)" in renderer
    assert 'return await video_tail9_render(query, user_id, context, required_screen)' in renderer


def test_stale_quality_and_confirm_callbacks_cannot_skip_required_tail_screens() -> None:
    handler = _function_source("handle_video_tail_callback")
    quality = handler[
        handler.index('if section == "quality":') : handler.index('if section == "confirm":')
    ]
    confirm = handler[handler.index('if section == "confirm":') :]

    quality_gate = quality.index("video_tail9.next_required_screen(tail)")
    quality_select = quality.index('if action == "select":')
    confirm_gate = confirm.index("video_tail9.next_required_screen(tail)")
    confirm_open = confirm.index('if action == "open":')
    assert quality_gate < quality_select
    assert confirm_gate < confirm_open
    assert 'if tail.get("final_confirmed"):' in quality[:quality_select]
    quality_stage_gate = quality.index('str(tail.get("status_stage") or "") != "quality"')
    quality_apply = quality.index("quality = max(200")
    assert quality_select < quality_stage_gate < quality_apply
    assert 'if tail.get("final_confirmed"):' in confirm[:confirm_open]
    assert 'str(tail.get("status_stage") or "") != "invoice"' in confirm[:confirm_open]


def test_confirmed_local_edit_recovery_never_returns_to_quality() -> None:
    handler = _function_source("handle_video_tail_callback")
    assert "video_tail9_render_confirmed_status" in handler
    assert "video_tail9_status_recovery_text" in BOT_SOURCE
    assert "video_tail9_status_recovery_keyboard" in BOT_SOURCE

    confirmed_status = _function_source("video_tail9_render_confirmed_status")
    assert 'video_tail9_render(query, uid, context, "quality")' not in confirmed_status


def test_idea_prompt_review_and_back_keep_the_idea_owner() -> None:
    assert "def video_tail9_idea_prompt_state" in BOT_SOURCE
    handler = _function_source("handle_video_tail_callback")
    review = handler[
        handler.index('if section == "review":') : handler.index('if section == "summary":')
    ]
    idea_route = review.index("video_tail9_idea_prompt_state(tail, host)")
    generic_route = review.index('target = "video_prompts"')
    assert idea_route < generic_route
    assert "video_tail9_uses_idea_catalog(tail, host)" in review
    assert "video_idea_prompt_owner_recovery_text" in review
    assert "video_idea_prompt_owner_recovery_keyboard" in review
    assert 'restore_developing_video_pending(uid, "videoidea", idea_state, "idea2_prompt")' in review
    assert "video_idea_prompt_selection_keyboard(idea_state)" in review

    prompt_handler = _function_source("handle_video_idea_prompt_callback")
    back = prompt_handler[prompt_handler.index('if action == "back":') :]
    assert "video_idea_prompt_preset_list_payload(state, lang)" in back
    assert 'target = "video_prompts"' not in back


def test_tail_and_idea_namespaces_have_one_callback_owner_without_generic_x() -> None:
    assert BOT_SOURCE.count('("video_tail|", "handle_video_tail_callback")') == 1
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_tail_callback, pattern=r"^video_tail\\|"'
    ) == 1
    assert BOT_SOURCE.count('("idea_video|", "handle_video_idea_prompt_callback")') == 1
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_idea_prompt_callback, pattern=r"^idea_video\\|")'
    ) == 1

    tail_handler = _function_source("handle_video_tail_callback")
    idea_handler = _function_source("handle_video_idea_prompt_callback")
    assert "generic X" not in tail_handler + idea_handler
    assert "provider.submit" not in tail_handler[: tail_handler.index('if action == "submit":')]
