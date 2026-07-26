from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

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
    assert callbacks.count("video_tail|confirm") == 1
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


def test_selecting_tier_300_opens_exactly_one_invoice() -> None:
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
    invoices: list[dict] = []
    invoice_keyboard = _load_function(
        "video_tail9_invoice_keyboard",
        {"video_scene3_keyboard": _validated_keyboard},
    )
    blocker_keyboard = _load_function(
        "video_tail9_public_blocker_keyboard",
        {"video_scene3_keyboard": _validated_keyboard},
    )

    async def render_invoice(_target, text, **kwargs):
        invoices.append({"text": text, **kwargs})
        return True

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(tail), "scene3", dict(host)),
            "video_tail9": video_tail9,
            "save_video_tail9_state": lambda *_args, **_kwargs: None,
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
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
            "video_tail9_invoice_text": lambda *_args, **_kwargs: "🧾 Hóa đơn video",
            "video_tail9_invoice_keyboard": invoice_keyboard,
            "video_tail9_public_blocker_text": lambda: "blocker",
            "video_tail9_public_blocker_keyboard": blocker_keyboard,
            "get_user_language": lambda _uid: "vi",
            "safe_edit_or_send": render_invoice,
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )

    class Query:
        id = "tailflow14-select-300"
        data = "video_tail|quality|select|300"
        from_user = SimpleNamespace(id=914002)

        async def answer(self, *_args, **_kwargs):
            return None

    update = SimpleNamespace(callback_query=Query())

    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert len(invoices) == 1
    assert "Hóa đơn" in invoices[0]["text"]
    assert _callbacks(invoices[0]["reply_markup"]).count("video_tail|confirm") == 1


def test_quality_back_is_owned_by_quality_and_returns_to_summary() -> None:
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
