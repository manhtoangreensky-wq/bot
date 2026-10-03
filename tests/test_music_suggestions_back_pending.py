"""Music return-to-suggestions releases only its own editor input."""
import asyncio
from copy import deepcopy
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


F = runpy.run_path(str(Path(__file__).with_name("test_voice_settings_input_back.py")))


def _runtime(ctx, mode="song"):
    ns, route = F["_runtime"]("default", ctx)
    ns.update(
        ui_text=lambda *_args: "Home", normalize_music_product_tier_for_mode=lambda tier, mode: tier,
        normalize_song_vocal_mode=lambda value: value,
        music_product_style_input_text=lambda *_args: "Style input",
        music_product_suggestions_text=lambda *_args: "Suggestions",
    )
    for name in (
        "build_2col_keyboard", "normalize_music_product_mode", "music_product_mode_from_result",
        "music_flow_back_keyboard", "music_product_suggestions_keyboard", "music_product_invoice_keyboard",
    ):
        exec(compile("from __future__ import annotations\n" + F["_source"](name), f"bot.py:{name}", "exec"), ns)
    ns["save_music_guided_result"](901, {
        "music_product_mode": mode, "music_product_tier": "music_tier_basic", "song_vocal": "female",
        "music_user_idea": "Keep idea", "music_selected_suggestion_id": "2",
        "music_suggestions": [{"id": "1", "title": "keep 1"}, {"id": "2", "title": "keep 2"}],
    })
    return ns, route


def _back(ns, route, ctx, action):
    if action == "music_product_back_suggestions":
        from_lyrics = ns["music_flow_back_keyboard"]("music_product_back_style", "vi", ctx)
        style = F["_click"](route, F["_callback"](from_lyrics, "music_product_back_style"))
        return F["_callback"](style.message.replies[-1][1], action)
    invoice = ns["music_product_invoice_keyboard"](ns["get_music_guided_result"](901), "vi", ctx)
    return F["_callback"](invoice, action)


@pytest.mark.parametrize("ctx", ["showroom", "video_addon"])
@pytest.mark.parametrize("action", ["music_product_back_suggestions", "music_product_back_details"])
@pytest.mark.parametrize("pending", ["music_product_song_style", "music_product_song_lyrics", "music_product_background_details"])
def test_suggestion_back_releases_own_editor_and_keeps_result(ctx, action, pending):
    ns, route = _runtime(ctx, "background" if "background" in pending else "song")
    callback = _back(ns, route, ctx, action)
    ns["set_music_guided_pending"](901, pending, product_context=ctx)
    before = deepcopy(ns["get_music_guided_result"](901))
    ns["USER_PENDING"]["unrelated:901"] = {"keep": "other state"}
    query = F["_click"](route, callback)
    assert ns["get_music_guided_pending"](901) is None
    assert ns["get_music_guided_result"](901) == before
    assert ns["USER_PENDING"]["unrelated:901"] == {"keep": "other state"}
    text, markup = query.message.replies[-1]
    assert text == "Suggestions"
    expected = ns["music_product_suggestions_keyboard"](before["music_product_mode"], "vi", ctx)
    assert [b.callback_data for row in markup.inline_keyboard for b in row] == [b.callback_data for row in expected.inline_keyboard for b in row]
    ordinary = F["Message"]("ordinary text after Back")
    assert asyncio.run(ns["handle_music_guided_pending_text"](
        SimpleNamespace(message=ordinary, effective_user=SimpleNamespace(id=901)), SimpleNamespace()
    )) is False
    assert ordinary.replies == []


@pytest.mark.parametrize("pending,owned_ctx", [("voice_tts_text_input", "showroom"), ("music_product_song_style", "video_addon")])
def test_stale_other_context_back_preserves_unrelated_input(pending, owned_ctx):
    ns, route = _runtime("showroom")
    callback = _back(ns, route, "showroom", "music_product_back_details")
    ns["set_music_guided_pending"](901, pending, product_context=owned_ctx)
    before = deepcopy(ns["get_music_guided_pending"](901))
    F["_click"](route, callback)
    assert ns["get_music_guided_pending"](901) == before


def test_direct_invoice_back_without_editor_input_retains_suggestion_screen():
    ns, route = _runtime("showroom")
    callback = _back(ns, route, "showroom", "music_product_back_details")
    query = F["_click"](route, callback)
    assert query.message.replies[-1][0] == "Suggestions"
    assert ns["get_music_guided_pending"](901) is None
