"""Cached preview navigation through emitted controls, owner SQL and fake audio transport."""
import asyncio
from copy import deepcopy
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


P = runpy.run_path(str(Path(__file__).with_name("test_voice_profile_stale_video_hint.py")))
F = P["FIXTURE"]


@pytest.fixture
def preview_runtime():
    generator = P["profile_runtime"].__wrapped__()
    ns, route, _unused_hint, conn = next(generator)
    try:
        yield ns, route, conn
    finally:
        generator.close()


def _emitted(ns, ctx, action):
    profile = {**P["READY"], "preview_audio_ref": "offline-demo"}
    markup = ns["voice_profile_actions_keyboard"](23, "vi", ctx, profile)
    return F["_callback"](markup, f"{action}:23")


def _click(route, data):
    handler, pattern = route
    assert pattern.search(data)
    query = F["Query"](data)
    query.message.chat_id = 901
    audios = []

    async def send_audio(**kwargs):
        audios.append(kwargs)

    asyncio.run(handler(SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=901)),
                        SimpleNamespace(bot=SimpleNamespace(send_audio=send_audio))))
    assert query.answers == [((), {})]
    return query, audios


@pytest.mark.parametrize("ctx", ["showroom", "video_addon"])
@pytest.mark.parametrize("action", ["voice_profile_listen", "voice_profile_download"])
@pytest.mark.parametrize("case", ["missing_demo", "foreign", "deleted"])
def test_missing_demo_or_owned_profile_keeps_recovery_context_without_send_or_write(preview_runtime, ctx, action, case):
    ns, route, conn = preview_runtime
    data = _emitted(ns, ctx, action)
    changes = {"missing_demo": {"preview_audio_ref": ""}, "foreign": {"user_id": "902", "preview_audio_ref": "offline-demo"},
               "deleted": {"deleted_at": "test-deleted", "preview_audio_ref": "offline-demo"}}[case]
    P["_seed"](conn, **changes)
    before = deepcopy(ns["USER_PENDING"])
    writes = conn.total_changes
    query, audios = _click(route, data)
    assert audios == []
    text, markup = query.message.replies[-1]
    assert text.startswith("⚠️")
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"music_quick|{ctx}|voice_profiles" in callbacks
    assert all(not value.startswith("music_quick|") or value.startswith(f"music_quick|{ctx}|") for value in callbacks)
    assert ns["USER_PENDING"] == before and conn.total_changes == writes


@pytest.mark.parametrize("ctx", ["showroom", "video_addon"])
@pytest.mark.parametrize("action", ["voice_profile_listen", "voice_profile_download"])
def test_owned_cached_demo_retains_existing_single_audio_delivery(preview_runtime, ctx, action):
    ns, route, conn = preview_runtime
    data = _emitted(ns, ctx, action)
    P["_seed"](conn, preview_audio_ref="offline-demo")
    before, writes = deepcopy(ns["USER_PENDING"]), conn.total_changes
    query, audios = _click(route, data)
    assert len(audios) == 1 and audios[0]["chat_id"] == 901 and audios[0]["audio"] == "offline-demo"
    assert query.message.replies == []
    assert ns["USER_PENDING"] == before and conn.total_changes == writes
