from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import ui_navigation, video_scene3_flow, video_tail9, video_uifreeze1


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


def _validated_keyboard(rows):
    return video_scene3_flow.validate_two_column_rows(rows)


def _callbacks(rows) -> list[str]:
    return [str(callback) for row in rows for _label, callback in row]


def test_invoice_keyboard_renders_with_one_owner_per_callback() -> None:
    keyboard = _load_function(
        "video_tail9_invoice_keyboard",
        {"video_scene3_keyboard": _validated_keyboard},
    )
    callbacks = _callbacks(keyboard())

    assert len(callbacks) == len(set(callbacks))
    assert callbacks.count("video_tail|confirm|open") == 1
    assert callbacks.count("video_tail|quality|open") == 1


def test_public_blocker_keyboard_renders_without_duplicate_callbacks() -> None:
    keyboard = _load_function(
        "video_tail9_public_blocker_keyboard",
        {"video_scene3_keyboard": _validated_keyboard},
    )
    callbacks = _callbacks(keyboard())

    assert len(callbacks) == len(set(callbacks))
    assert "video_tail|summary|open" in callbacks
    assert "video_tail|quality|back" in callbacks


def test_logo_and_watermark_position_keyboards_render_all_nine_positions() -> None:
    keyboard = _load_function(
        "video_tail9_position_keyboard",
        {"video_scene3_keyboard": _validated_keyboard},
    )

    for target in ("logo", "watermark"):
        rows = keyboard(target)
        callbacks = _callbacks(rows)
        position_callbacks = [
            callback
            for callback in callbacks
            if callback.startswith(f"video_tail|logo|setpos|{target}|")
        ]

        assert len(position_callbacks) == 9
        assert len(callbacks) == len(set(callbacks))
        assert callbacks[-2:] == ["video_tail|logo|open", "menu|main"]


def test_bottom_navigation_preserves_the_three_by_three_position_grid() -> None:
    def button(text: str, callback: str):
        return SimpleNamespace(text=text, callback_data=callback)

    positions = (
        ("↖️ Trên trái", "top_left"), ("⬆️ Trên giữa", "top_center"), ("↗️ Trên phải", "top_right"),
        ("⬅️ Giữa trái", "center_left"), ("⏺ Chính giữa", "center"), ("➡️ Giữa phải", "center_right"),
        ("↙️ Dưới trái", "bottom_left"), ("⬇️ Dưới giữa", "bottom_center"), ("↘️ Dưới phải", "bottom_right"),
    )
    rows = [
        [button(label, f"video_tail|logo|setpos|logo|{position}") for label, position in positions[0:3]],
        [button(label, f"video_tail|logo|setpos|logo|{position}") for label, position in positions[3:6]],
        [button(label, f"video_tail|logo|setpos|logo|{position}") for label, position in positions[6:9]],
        [button("⬅️ Quay lại", "video_tail|logo|open"), button("🏠 Menu chính", "menu|main")],
    ]

    normalized = ui_navigation.canonicalize_bottom_navigation(
        rows,
        button_factory=lambda text, callback_data: button(text, callback_data),
    )
    callbacks = [item.callback_data for row in normalized for item in row]

    assert [len(row) for row in normalized] == [3, 3, 3, 2]
    assert len([callback for callback in callbacks if callback.startswith("video_tail|logo|setpos|logo|")]) == 9
    assert "video_tail|logo|setpos|logo|center_left" in callbacks
    assert ui_navigation.is_back_button(rows[1][0]) is False


def test_watermark_text_reaches_position_screen_and_persists_tail_owner() -> None:
    tail = video_tail9.new_state(
        product_type="video_ai_real",
        session_id="tailflow14-watermark",
        scene_count=1,
        ratio="9:16",
    )
    editor_state = {"step": "video_tail9_watermark_input", "video_tail9": tail}
    saved: list[dict] = []
    rendered: list[dict] = []
    position_keyboard = _load_function(
        "video_tail9_position_keyboard",
        {"video_scene3_keyboard": _validated_keyboard},
    )

    def update_editor(_uid, step, **fields):
        editor_state.update(fields)
        editor_state["step"] = step
        return dict(editor_state)

    async def render(_target, text, **kwargs):
        rendered.append({"text": text, **kwargs})
        return True

    handler = _load_function(
        "handle_video_tail9_pending_text",
        {
            "get_video_editor_pending": lambda _uid: dict(editor_state),
            "get_video_session": lambda _uid: {},
            "video_tail9_context": lambda _uid, _context: (dict(tail), "video_edit", dict(editor_state)),
            "video_tail9": video_tail9,
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "save_video_tail9_state": lambda _uid, _context, value, _owner, _host: saved.append(dict(value)),
            "update_video_editor_pending": update_editor,
            "save_video_session": lambda *_args, **_kwargs: None,
            "safe_edit_or_send": render,
            "video_tail9_audio_text": lambda _tail: "audio",
            "video_tail9_audio_keyboard": lambda _tail: [],
            "video_tail9_position_text": lambda target: f"position:{target}",
            "video_tail9_position_keyboard": position_keyboard,
        },
    )
    update = SimpleNamespace(
        message=SimpleNamespace(text="TOAN AAS"),
        effective_user=SimpleNamespace(id=914001),
    )

    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert saved[-1]["watermark_config"]["text"] == "TOAN AAS"
    assert saved[-1]["brand_pending_target"] == "watermark"
    assert editor_state["step"] == "confirmation"
    assert len(rendered) == 1
    assert len([
        callback
        for callback in _callbacks(rendered[0]["reply_markup"])
        if callback.startswith("video_tail|logo|setpos|watermark|")
    ]) == 9


def test_tail_pending_text_has_a_defined_subdub_guard_and_precedes_stale_studio() -> None:
    assert "VIDEO_DUBBING_PENDING_TEXT_STEPS = frozenset" in BOT_SOURCE
    assert "def subdub_text_input_owns_message" in BOT_SOURCE

    handler = _function_source("handle_message")
    tail_owner = handler.index("handle_video_tail9_pending_text(update, context)")
    stale_studio = handler.index("handle_video_profile_studio_pending_text(update, context)")

    assert tail_owner < stale_studio


@pytest.mark.parametrize(
    "tier_id",
    (200, 300, 400, 500, 600, 700, 800, 1000, 1200, 1500),
)
def test_each_video_ai_real_tier_opens_exactly_one_invoice(tier_id: int) -> None:
    tail = video_tail9.new_state(
        product_type="video_ai_real",
        session_id="tailflow14-invoice",
        scene_count=1,
        ratio="9:16",
    )
    host = {
        "content_source": "content_profiles",
        "selected_prompt": "Prompt video hoàn chỉnh.",
        "scene_count": 1,
    }
    tail = video_tail9.apply_content_contract(
        tail,
        {
            "content_source": "content_profiles",
            "canonical_content_mode": "content_profiles",
            "selected_prompt_text": "Prompt video hoàn chỉnh.",
            "per_scene_content": [{"scene": 1}],
            "plan_status": "ready",
        },
    )
    tail = video_tail9.mark_branding_skipped(tail)
    tail = video_tail9.mark_audio_complete(tail, skipped=True)
    tail = video_tail9.prepare_summary(tail)
    tail["status_stage"] = "quality"
    rendered: list[dict] = []
    saved = {"tail": dict(tail)}
    invoice_keyboard = _load_function(
        "video_tail9_invoice_keyboard",
        {"video_scene3_keyboard": _validated_keyboard},
    )
    blocker_keyboard = _load_function(
        "video_tail9_public_blocker_keyboard",
        {"video_scene3_keyboard": _validated_keyboard},
    )

    def save_tail(_uid, _context, value, _owner, _host):
        saved["tail"] = dict(value)

    async def render_tail(_query, _uid, _context, screen):
        rendered.append({"screen": screen})
        return True

    async def answer_best_effort(query, text="", **kwargs):
        try:
            await query.answer(text or None, **kwargs)
        except Exception:
            return None

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(saved["tail"]), "scene3", dict(host)),
            "video_tail9": video_tail9,
            "video_tail9_answer_best_effort": answer_best_effort,
            "save_video_tail9_state": save_tail,
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "video_selfshot3_scene_count_for_quality": lambda current, _quality: int(current.get("scene_count") or 1),
            "video_selfshot3": SimpleNamespace(PRODUCT_ID="self_shot_cinematic_transform"),
            "video_tail9_commercial_preflight": lambda *_args, **_kwargs: {
                "ok": True,
                "engine_route": "video_ai_canonical",
                "required_capability": "text_to_video",
            },
            "video_tail9_catalog_report": lambda *_args, **_kwargs: {
                "ok": True,
                "tier_ids": [200, 300],
                "offers": [{"tier_id": 200}, {"tier_id": 300}],
            },
            "video_tail9_apply_to_session": lambda *_args, **_kwargs: {"draft": {}, "scene_count": 1},
            "video_b14_invoice_for_session": lambda *_args, **_kwargs: {
                "quality_xu": 300,
                "price_xu": 300,
                "total_xu": 300,
                "package_label": "Gói Tiêu chuẩn",
            },
            "video_tail9_render": render_tail,
            "video_tail9_public_blocker_text": lambda: "blocker",
            "video_tail9_public_blocker_keyboard": blocker_keyboard,
            "get_user_language": lambda _uid: "vi",
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )

    class Query:
        id = f"tailflow14-select-{tier_id}"
        data = f"video_tail|quality|select|{tier_id}"
        from_user = SimpleNamespace(id=914002)

        async def answer(self, *_args, **_kwargs):
            raise TimeoutError("telegram callback ack timed out")

    update = SimpleNamespace(callback_query=Query())

    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert rendered == [{"screen": "invoice"}]
    assert saved["tail"]["quality_tier_id"] == str(tier_id)
    assert saved["tail"]["status_stage"] == "invoice"
    assert video_tail9.invoice_allowed(saved["tail"]) == (True, "ok")
    assert _callbacks(invoice_keyboard()).count("video_tail|confirm|open") == 1


def test_invoice_confirm_opens_confirmation_when_callback_ack_times_out() -> None:
    tail = video_tail9.new_state(
        product_type="video_ai_real",
        execution_product_type="video_ai_prompt",
        session_id="tailflow14-confirm-timeout",
        scene_count=2,
        ratio="9:16",
    )
    tail = video_tail9.apply_content_contract(
        tail,
        {
            "content_source": "manual",
            "canonical_content_mode": "manual",
            "selected_prompt_text": "Prompt hai cảnh đã duyệt.",
            "per_scene_content": [{"scene": 1}, {"scene": 2}],
            "plan_status": "ready",
        },
    )
    tail = video_tail9.select_package(
        tail,
        quality_tier_id="400",
        package_id="product_video_400",
        pricing_snapshot={"quality_xu": 400, "total_xu": 720},
        capability_snapshot={"ok": True},
    )
    rendered: list[str] = []

    async def render_tail(_query, _uid, _context, screen):
        rendered.append(screen)
        return True

    async def answer_best_effort(query, text="", **kwargs):
        try:
            await query.answer(text or None, **kwargs)
        except Exception:
            return None

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(tail), "scene3", {}),
            "video_tail9": video_tail9,
            "video_tail9_answer_best_effort": answer_best_effort,
            "save_video_tail9_state": lambda *_args, **_kwargs: None,
            "video_tail9_render": render_tail,
            "get_user_language": lambda _uid: "vi",
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )

    class Query:
        id = "tailflow14-confirm-timeout"
        data = "video_tail|confirm|open"
        from_user = SimpleNamespace(id=914003)

        async def answer(self, *_args, **_kwargs):
            raise TimeoutError("telegram callback ack timed out")

    update = SimpleNamespace(callback_query=Query())

    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert rendered == ["confirm"]


def test_final_submit_renders_status_when_runtime_preflight_is_not_ready() -> None:
    tail = video_tail9.new_state(
        product_type="video_ai_real",
        execution_product_type="video_ai_prompt",
        session_id="tailflow14-submit-status",
        scene_count=2,
        ratio="9:16",
    )
    tail = video_tail9.apply_content_contract(
        tail,
        {
            "content_source": "manual",
            "canonical_content_mode": "manual",
            "selected_prompt_text": "Prompt hai cảnh đã duyệt.",
            "per_scene_content": [{"scene": 1}, {"scene": 2}],
            "plan_status": "ready",
        },
    )
    tail = video_tail9.select_package(
        tail,
        quality_tier_id="400",
        package_id="product_video_400",
        pricing_snapshot={"quality_xu": 400, "total_xu": 720},
        capability_snapshot={"ok": True},
    )
    saved = {"tail": dict(tail)}
    rendered: list[dict] = []

    def save_tail(_uid, _context, value, _owner, _host):
        saved["tail"] = dict(value)

    async def answer_best_effort(query, text="", **kwargs):
        try:
            await query.answer(text or None, **kwargs)
        except Exception:
            return None

    def submit_preflight(current, *, provider_ready, **_kwargs):
        if provider_ready:
            return {"allowed": True, "blocker_code": ""}
        return {
            "allowed": False,
            "blocker_code": "provider_unavailable",
            "public_message": "TOAN AAS chưa thể bắt đầu xử lý video lúc này.",
        }

    def prepare_status(_uid, _context, current, _owner, _host, snapshot=None):
        prepared = dict(current)
        prepared.update({
            "submit_attempted": True,
            "status_stage": "confirmed",
            "submit_preflight_snapshot": dict(snapshot or {}),
        })
        saved["tail"] = prepared
        return prepared

    async def render_status(_query, _context, _uid, current, _owner, _host):
        rendered.append({
            "screen": "status",
            "blocker": (current.get("submit_preflight_snapshot") or {}).get("blocker_code"),
        })
        return True

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(saved["tail"]), "scene3", {}),
            "video_tail9": video_tail9,
            "video_tail9_answer_best_effort": answer_best_effort,
            "save_video_tail9_state": save_tail,
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "VIDEO_TAIL9_DEFERRED_RUNTIME_PRODUCTS": {"video_ai_real"},
            "video_b14_is_admin_or_owner": lambda _uid: True,
            "get_user": lambda _uid: (200, 0, False),
            "video_tail9_preflight": lambda *_args, **_kwargs: {"ok": True},
            "video_tail9_prepare_submit_status": prepare_status,
            "video_tail9_render_confirmed_status": render_status,
            "product_video_public_preflight_evaluation": lambda *_args, **_kwargs: {
                "ready": False,
                "blocker_code": "provider_unavailable",
            },
            "product_video_worker_admission_status": lambda: {
                "worker_version_compatible": False,
                "worker_admission_block_reason": "worker_unavailable",
            },
            "get_user_language": lambda _uid: "vi",
            "logger": SimpleNamespace(
                warning=lambda *_args, **_kwargs: None,
                exception=lambda *_args, **_kwargs: None,
            ),
        },
    )
    original_evaluator = video_tail9.evaluate_submit_preflight
    video_tail9.evaluate_submit_preflight = submit_preflight

    class Query:
        id = "tailflow14-submit-status"
        data = "video_tail|confirm|submit"
        from_user = SimpleNamespace(id=914004)

        async def answer(self, *_args, **_kwargs):
            raise TimeoutError("telegram callback ack timed out")

    try:
        assert asyncio.run(
            handler(SimpleNamespace(callback_query=Query()), SimpleNamespace())
        ) is True
    finally:
        video_tail9.evaluate_submit_preflight = original_evaluator

    assert saved["tail"]["submit_attempted"] is True
    assert rendered == [{"screen": "status", "blocker": "provider_unavailable"}]


def test_quality_back_is_owned_by_quality_and_returns_to_unified_summary() -> None:
    handler = _function_source("handle_video_tail_callback")
    quality = handler[handler.index('if section == "quality":'):handler.index('if section == "confirm":')]

    assert 'if action == "back":' in quality
    assert 'video_tail9_render(query, uid, context, "summary")' in quality


def test_one_scene_ai_and_trend_keep_the_200_experience_tier() -> None:
    for product_type in ("video_ai_real", "video_trend"):
        report = video_uifreeze1.catalog_report(product_type, scene_count=1, ratio="9:16")

        assert report["ok"] is True
        assert report["tier_ids"][0] == 200


def test_tail_preconfirm_contract_remains_side_effect_free() -> None:
    report = video_uifreeze1.catalog_report("video_ai_real", scene_count=1, ratio="9:16")

    assert report["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
