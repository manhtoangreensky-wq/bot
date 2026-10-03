"""Voice upload owns wrong-type text; exercise emitted consent and dispatch seams."""
import asyncio
from copy import deepcopy
import html
import json
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


F = runpy.run_path(str(Path(__file__).with_name("test_voice_settings_input_back.py")))


def _runtime(ctx):
    ns, route = F["_runtime"]("default", ctx)
    saved = []
    ns.update(
        json=json, html=html, VOICE_FLOW_ROOT_SCREEN="voice_hub",
        VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT="Local sample text",
        now_text=lambda: "test-consent", ui_text=lambda *_args: "Home",
        music_no_xu_text=lambda _lang: "No processing or charge",
        save_user_voice_profile=lambda *args, **kwargs: saved.append((args, kwargs)) or 23,
    )
    for name in (
        "build_2col_keyboard", "encode_voice_back_stack", "decode_voice_back_stack",
        "voice_flow_back_action_from_stack", "voice_flow_pending_fields", "set_voice_flow_pending",
        "voice_clone_keyboard", "voice_clone_upload_text", "voice_clone_sample_confirmation_text",
        "voice_clone_step_back_keyboard", "message_media_candidate", "media_content_type",
        "handle_music_guided_pending_media",
    ):
        exec(compile("from __future__ import annotations\n" + F["_source"](name), f"bot.py:{name}", "exec"), ns)
    assert "MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)" in F["SOURCE"]
    boundary = "    if await handle_music_guided_pending_text(update, context):\n        return\n"
    assert boundary in F["_source"]("handle_message")
    exec("async def actual_music_text_boundary(update,context):\n" + boundary + "    return 'fallthrough'\n", ns)
    consent = F["_callback"](ns["voice_clone_keyboard"]("vi", ctx), "voice_consent")
    F["_click"](route, consent)
    assert ns["get_music_guided_pending"](901)["pending_action"] == "voice_clone_upload"
    return ns, route, saved


def _text(ns, value):
    message = F["Message"](value)
    outcome = asyncio.run(ns["actual_music_text_boundary"](
        SimpleNamespace(message=message, effective_user=SimpleNamespace(id=901)), SimpleNamespace()
    ))
    return outcome, message


@pytest.mark.parametrize("ctx", ["showroom", "video_addon"])
@pytest.mark.parametrize("text", ["hello, sending my sample shortly", "123"])
def test_wrong_text_keeps_upload_state_and_next_audio_reaches_sample_confirmation(ctx, text):
    ns, route, saved = _runtime(ctx)
    before = deepcopy(ns["get_music_guided_pending"](901))
    outcome, message = _text(ns, text)
    assert outcome is None, "upload input must claim wrong-type text rather than fall into chat"
    assert ns["get_music_guided_pending"](901) == before
    assert len(message.replies) == 1
    upload_text, markup = message.replies[0]
    assert upload_text == ns["voice_clone_upload_text"]("vi")
    back = F["_callback"](markup, "voice_clone")
    assert back == ns["product_context_callback"]("music_quick", ctx, "voice_clone")
    assert route[1].search(back)
    assert saved == []
    audio_message = F["Message"]()
    audio_message.voice = None
    audio_message.audio = SimpleNamespace(file_id="offline-audio-file", mime_type="audio/mpeg")
    audio_message.video = audio_message.document = audio_message.photo = None
    consumed = asyncio.run(ns["handle_music_guided_pending_media"](
        SimpleNamespace(message=audio_message, effective_user=SimpleNamespace(id=901)), SimpleNamespace()
    ))
    assert consumed is True and len(saved) == 1
    assert saved[0][0][0:2] == (901, "offline-audio-file")
    after = ns["get_music_guided_pending"](901)
    assert after["pending_action"] == "voice_clone_sample_confirm"
    assert after["product_context"] == ctx and after["voice_sample_file_id"] == "offline-audio-file"


@pytest.mark.parametrize("ctx", ["showroom", "video_addon"])
@pytest.mark.parametrize("text", ["", "/start"])
def test_blank_and_command_text_are_not_claimed_or_drop_upload_state(ctx, text):
    ns, _route, saved = _runtime(ctx)
    before = deepcopy(ns["get_music_guided_pending"](901))
    outcome, message = _text(ns, text)
    assert outcome == "fallthrough"
    assert ns["get_music_guided_pending"](901) == before
    assert message.replies == [] and saved == []


def test_valid_voice_speed_text_keeps_existing_setting_path():
    ns, _route, saved = _runtime("showroom")
    ns["set_music_guided_pending"](901, "voice_tts_speed_input", product_context="showroom")
    outcome, message = _text(ns, "1.4")
    assert outcome is None and ns["get_music_guided_pending"](901) is None
    assert ns["get_music_guided_result"](901)["tts_speed"] == "1.4"
    assert "settings_title" in message.replies[-1][0] and saved == []
