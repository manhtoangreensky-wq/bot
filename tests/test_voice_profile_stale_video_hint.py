"""Stale profile hint through real action builder, owner SQL and registered handler."""
from copy import deepcopy
from pathlib import Path
import runpy
import sqlite3
from types import SimpleNamespace

import pytest
from services import minimax_voice_adapter


FIXTURE = runpy.run_path(str(Path(__file__).with_name("test_voice_settings_input_back.py")))
READY = {"id": 23, "user_id": "901", "status": "active", "provider_voice_id": "test-voice-id",
         "display_name": "Owned voice", "deleted_at": None, "is_default": 0, "preview_audio_ref": ""}


@pytest.fixture
def profile_runtime():
    ns, route = FIXTURE["_runtime"]("saved", "showroom")
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE voice_profiles (id INTEGER, user_id TEXT, status TEXT, provider_voice_id TEXT, display_name TEXT, deleted_at TEXT, is_default INTEGER, preview_audio_ref TEXT)")
    ns.update(
        db_connect=lambda: conn, sqlite3=sqlite3,
        minimax_voice_adapter=minimax_voice_adapter,
        VOICE_PROFILE_FINAL_READY_STATUSES={"active", "ready", "saved"},
        VOICE_PROFILE_PREVIEW_STATUSES={"active", "ready", "saved", "preview_ready"},
        public_hub_copy=lambda _lang: {}, ui_text=lambda *_args: "Home",
        default_tts_voices_distinct=lambda: True,
        logger=SimpleNamespace(warning=lambda *_args: None),
        sanitize_log_text=lambda value: str(value),
    )
    for name in (
        "build_2col_keyboard", "get_user_voice_profile", "user_voice_profile_rows",
        "user_voice_profile_count", "voice_vault_page_size", "voice_profile_display_code",
        "voice_profile_can_generate_tts", "voice_profile_can_preview",
        "voice_profile_actions_keyboard", "voice_vault_keyboard",
    ):
        exec(compile("from __future__ import annotations\n" + FIXTURE["_source"](name), f"bot.py:{name}", "exec"), ns)
    markup = ns["voice_profile_actions_keyboard"](23, "vi", "showroom", READY)
    data = FIXTURE["_callback"](markup, "voice_profile_video_hint:23")
    assert data == "music_quick|showroom|voice_profile_video_hint:23"
    yield ns, route, data, conn
    conn.close()


def _seed(conn, **changes):
    profile = {**READY, **changes}
    conn.execute("INSERT INTO voice_profiles VALUES (?,?,?,?,?,?,?,?)", tuple(profile.values()))
    conn.commit()


@pytest.mark.parametrize("case", ["missing", "deleted", "foreign", "preview", "failed", "no_provider_id", "local_id", "reserved_id"])
def test_stale_or_unready_video_hint_never_claims_ready_and_returns_owned_vault(profile_runtime, case):
    ns, route, data, conn = profile_runtime
    changes = {
        "deleted": {"deleted_at": "test-deleted"}, "foreign": {"user_id": "902"},
        "preview": {"status": "preview_ready"}, "failed": {"status": "error"},
        "no_provider_id": {"provider_voice_id": ""}, "local_id": {"provider_voice_id": "23"},
        "reserved_id": {"provider_voice_id": "default"},
    }
    if case != "missing":
        _seed(conn, **changes[case])
    before_writes = conn.total_changes
    before_pending = deepcopy(ns["USER_PENDING"])
    query = FIXTURE["_click"](route, data)
    text, markup = query.message.replies[-1]
    assert "Giọng này đã sẵn sàng" not in text
    assert text.startswith("⚠️")
    assert markup.inline_keyboard
    actual = [button.callback_data for row in markup.inline_keyboard for button in row]
    expected = [button.callback_data for row in ns["voice_vault_keyboard"](901, "vi", "showroom").inline_keyboard for button in row]
    assert actual == expected
    assert "music_quick|showroom|voice_hub" in actual
    assert ns["USER_PENDING"] == before_pending
    assert conn.total_changes == before_writes


def test_ready_owned_profile_and_repeat_keep_information_without_state_or_db_write(profile_runtime):
    ns, route, data, conn = profile_runtime
    _seed(conn)
    before_pending = deepcopy(ns["USER_PENDING"])
    before_writes = conn.total_changes
    for _ in range(2):
        query = FIXTURE["_click"](route, data)
        text, markup = query.message.replies[-1]
        assert text.startswith("🎬 Giọng này đã sẵn sàng.")
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        assert data in callbacks and "music_quick|showroom|voice_profiles" in callbacks
    assert ns["USER_PENDING"] == before_pending
    assert conn.total_changes == before_writes
