"""A stale Voice Vault button must not resolve to a different profile."""
import html
from pathlib import Path
import runpy
import sqlite3

import pytest


PROFILE_FIXTURE = runpy.run_path(str(Path(__file__).with_name("test_voice_profile_stale_video_hint.py")))
CALLBACK_FIXTURE = PROFILE_FIXTURE["FIXTURE"]


@pytest.fixture
def voice_vault_runtime():
    generator = PROFILE_FIXTURE["profile_runtime"].__wrapped__()
    ns, route, _unused_hint, conn = next(generator)
    try:
        for name in (
            "build_2col_keyboard",
            "get_user_voice_profile",
            "user_voice_profile_rows",
            "user_voice_profile_count",
            "voice_vault_page_size",
            "voice_profile_display_code",
            "user_voice_profile_by_display_code",
            "voice_vault_keyboard",
        ):
            exec(
                compile(
                    "from __future__ import annotations\n" + CALLBACK_FIXTURE["_source"](name),
                    f"bot.py:{name}",
                    "exec",
                ),
                ns,
            )
        ns.update(html=html, ui_text=lambda *_args: "Home")
        for profile_id in (101, 102, 103):
            conn.execute(
                "INSERT INTO voice_profiles VALUES (?, ?, 'active', ?, ?, NULL, 0, '')",
                (profile_id, "901", f"test-voice-{profile_id}", f"Fixture voice {profile_id}"),
            )
        conn.commit()
        yield ns, route, conn
    finally:
        generator.close()


def test_emitted_voice_vault_selection_keeps_profile_identity_after_list_changes(voice_vault_runtime):
    ns, route, conn = voice_vault_runtime
    markup = ns["voice_vault_keyboard"](901, "vi", "showroom", 0)
    selected_button = next(
        button for row in markup.inline_keyboard for button in row if button.text == "2"
    )
    expected_profile = ns["user_voice_profile_by_display_code"](901, 2)
    assert expected_profile["id"] == 102

    # The top item disappears after Telegram rendered the list. The old button
    # must still identify profile 102, not reinterpret display slot 2 as 101.
    conn.execute("DELETE FROM voice_profiles WHERE id=103")
    conn.commit()
    before_click_writes = conn.total_changes

    query = CALLBACK_FIXTURE["_click"](route, selected_button.callback_data)

    text, _response_markup = query.message.replies[-1]
    assert "Fixture voice 102" in text
    assert conn.total_changes == before_click_writes


def test_legacy_slot_callback_expires_instead_of_selecting_different_profile(voice_vault_runtime):
    ns, route, conn = voice_vault_runtime
    # This callback can remain in an already-sent Telegram message from before
    # stable profile IDs were emitted. It has no identity beyond display slot 2.
    legacy_callback = "music_quick|showroom|voice_profile_select_code:2"
    conn.execute("DELETE FROM voice_profiles WHERE id=103")
    conn.commit()
    before_click_writes = conn.total_changes

    query = CALLBACK_FIXTURE["_click"](route, legacy_callback)

    text, markup = query.message.replies[-1]
    assert "màn kho voice cũ đã hết hạn" in text.lower()
    actual_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "music_quick|showroom|voice_profile_select:102" in actual_callbacks
    assert "Fixture voice 101" not in text and "Fixture voice 102" not in text
    assert conn.total_changes == before_click_writes
