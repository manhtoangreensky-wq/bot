from __future__ import annotations

import asyncio
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(
        r"\n(?=@|(?:async )?def [A-Za-z_])",
        BOT_SOURCE[match.end() :],
    )
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def test_search_results_from_text_message_use_reply_renderer() -> None:
    calls: list[tuple[str, str]] = []

    async def reply_long(target, text, reply_markup=None):
        calls.append((target.kind, text))
        return reply_markup

    async def callback_only(*_args, **_kwargs):
        raise AssertionError("callback renderer received a normal Message")

    namespace = {
        "safe_reply_long_html": reply_long,
        "safe_edit_or_send_long_html": callback_only,
        "video_trend2_search_results_text": lambda _state: "SEARCH RESULTS",
        "video_trend2_search_results_keyboard": lambda _state: "KEYBOARD",
    }
    exec(
        "from __future__ import annotations\n" + _function_source("video_trend2_render"),
        namespace,
    )

    message = type("Message", (), {"kind": "message", "reply_text": object()})()
    result = asyncio.run(
        namespace["video_trend2_render"](
            message,
            object(),
            {"screen": "search_results"},
        )
    )

    assert calls == [("message", "SEARCH RESULTS")]
    assert result == "KEYBOARD"


def test_video_analysis_from_media_message_edits_the_progress_message() -> None:
    calls: list[tuple[str, str]] = []

    async def reply_long(target, text, reply_markup=None):
        raise AssertionError("editable progress Message must not leave a stale status")

    async def callback_only(*_args, **_kwargs):
        raise AssertionError("callback renderer received a normal Message")

    namespace = {
        "safe_reply_long_html": reply_long,
        "safe_edit_or_send_long_html": callback_only,
        "video_trend2_video_analysis_text": lambda _state: "VIDEO ANALYSIS",
        "video_trend2_video_analysis_keyboard": lambda _state: "KEYBOARD",
    }
    exec(
        "from __future__ import annotations\n" + _function_source("video_trend2_render"),
        namespace,
    )

    class Message:
        kind = "message"
        reply_text = object()

        async def edit_text(self, text, parse_mode=None, reply_markup=None):
            calls.append((self.kind, text))
            assert parse_mode == "HTML"
            return reply_markup

    message = Message()
    result = asyncio.run(
        namespace["video_trend2_render"](
            message,
            object(),
            {"screen": "video_analysis"},
        )
    )

    assert calls == [("message", "VIDEO ANALYSIS")]
    assert result == "KEYBOARD"


def test_script_and_trend_entity_bridge_show_quick_create_without_extra_detail_lane() -> None:
    payload = _function_source("_video_uiflow3_screen_payload_unscoped")
    start = payload.index('if step == "production_bible":')
    end = payload.index('if step == "episode":', start)
    production_bible = payload[start:end]

    assert "video_entity_bridge_marker(state)" in production_bible
    assert '("⚡ Tạo nhanh", "vid3|quick_build")' in production_bible
    assert "bridge_quick_rows" in production_bible
    assert "bridge_detail_summary" in production_bible
    assert '"" if bridge_quick' in production_bible
    bridge_rows = production_bible.split("bridge_quick_rows", 1)[1].split(
        "bridge_quick_copy",
        1,
    )[0]
    quick_only = bridge_rows.split("if bridge_quick", 1)[0]
    assert "bible_extras" not in quick_only
    assert "bible_extras" in bridge_rows


def test_product_quick_create_rotates_variant_and_enters_addon_directly() -> None:
    builder = _function_source("video_ai_real_build_quick_plan")
    callback = _function_source("handle_video_uiflow3_callback")
    start = callback.index('elif action == "quick_build":')
    end = callback.index('elif action == "bible_done":', start)
    quick = callback[start:end]

    assert 'legacy.get("product_quick_build_revision")' in quick
    assert 'legacy["product_quick_build_revision"] = quick_revision' in quick
    assert "video_entity_bridge_marker(state)" in quick
    assert 'video_tail9_render(query, user_id, context, "addon")' in quick
    assert '"product_quick_build_revision"' in builder
    assert "seed_parts = [" in builder
    assert "if quick_revision > 0:" in builder
    assert "seed_parts.append(str(quick_revision))" in builder
    assert (
        "seed_number = quick_revision if quick_revision > 0 else int(seed[:8], 16)"
        in builder
    )
