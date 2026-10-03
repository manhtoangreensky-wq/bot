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
            "voice_profile_can_generate_tts",
            "voice_profile_can_preview",
            "user_voice_profile_rows",
            "user_voice_profile_count",
            "voice_vault_page_size",
            "voice_profile_display_code",
            "user_voice_profile_by_display_code",
            "voice_vault_keyboard",
            "voice_profile_actions_keyboard",
            "update_user_voice_profile",
            "soft_delete_voice_profile",
        ):
            exec(
                compile(
                    "from __future__ import annotations\n" + CALLBACK_FIXTURE["_source"](name),
                    f"bot.py:{name}",
                    "exec",
                ),
                ns,
            )
        ns.update(
            html=html,
            ui_text=lambda *_args: "Home",
            now_text=lambda: "fixture-now",
            minimax_voice_adapter=PROFILE_FIXTURE["minimax_voice_adapter"],
            VOICE_PROFILE_FINAL_READY_STATUSES={"active", "ready", "saved"},
            VOICE_PROFILE_PREVIEW_STATUSES={"active", "ready", "saved", "preview_ready"},
        )
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


def test_stable_profile_id_callback_cannot_open_another_users_voice(voice_vault_runtime):
    ns, route, conn = voice_vault_runtime
    conn.execute(
        "INSERT INTO voice_profiles VALUES (?, ?, 'active', ?, ?, NULL, 0, '')",
        (104, "902", "foreign-provider-id", "Foreign voice 104"),
    )
    conn.commit()
    before_click_writes = conn.total_changes

    query = CALLBACK_FIXTURE["_click"](
        route, "music_quick|showroom|voice_profile_select:104"
    )

    text, markup = query.message.replies[-1]
    assert "không tìm thấy giọng này trong tài khoản" in text.lower()
    assert "Foreign voice 104" not in text
    actual_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert not any(str(data).endswith("voice_profile_select:104") for data in actual_callbacks)
    assert conn.total_changes == before_click_writes


def test_delete_callback_cannot_soft_delete_another_users_voice(voice_vault_runtime):
    ns, route, conn = voice_vault_runtime
    conn.execute("ALTER TABLE voice_profiles ADD COLUMN updated_at TEXT")
    conn.execute(
        "INSERT INTO voice_profiles VALUES (?, ?, 'active', ?, ?, NULL, 0, '', NULL)",
        (104, "902", "foreign-provider-id", "Foreign voice 104"),
    )
    conn.commit()
    before = conn.execute(
        "SELECT user_id, status, deleted_at, is_default, updated_at FROM voice_profiles WHERE id=104"
    ).fetchone()
    before_click_writes = conn.total_changes

    query = CALLBACK_FIXTURE["_click"](
        route, "music_quick|showroom|voice_profile_delete:104"
    )

    text, markup = query.message.replies[-1]
    assert "không xóa được giọng này" in text.lower()
    assert "Foreign voice 104" not in text
    actual_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert not any(str(data).endswith(("voice_profile_select:104", "voice_profile_delete:104")) for data in actual_callbacks)
    after = conn.execute(
        "SELECT user_id, status, deleted_at, is_default, updated_at FROM voice_profiles WHERE id=104"
    ).fetchone()
    assert tuple(after) == before
    assert conn.total_changes == before_click_writes


def test_foreign_profile_preview_callback_returns_callers_vault_only(voice_vault_runtime):
    ns, route, conn = voice_vault_runtime
    conn.execute(
        "INSERT INTO voice_profiles VALUES (?, ?, 'active', ?, ?, NULL, 0, '')",
        (104, "902", "foreign-provider-id", "Foreign voice 104"),
    )
    conn.commit()
    before_click_writes = conn.total_changes

    query = CALLBACK_FIXTURE["_click"](
        route, "music_quick|showroom|voice_profile_listen:104"
    )

    text, markup = query.message.replies[-1]
    assert "không tìm thấy giọng này trong tài khoản" in text.lower()
    expected_callbacks = [
        button.callback_data
        for row in ns["voice_vault_keyboard"](901, "vi", "showroom").inline_keyboard
        for button in row
    ]
    actual_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert actual_callbacks == expected_callbacks
    assert not any(str(data).endswith(":104") for data in actual_callbacks)
    assert "Foreign voice 104" not in text
    assert conn.total_changes == before_click_writes


def test_owned_profile_without_preview_keeps_existing_preview_guidance(voice_vault_runtime):
    ns, route, conn = voice_vault_runtime
    conn.execute(
        "INSERT INTO voice_profiles VALUES (?, ?, 'active', ?, ?, NULL, 0, '')",
        (105, "901", "test-voice-105", "Owned voice 105"),
    )
    conn.commit()
    before_click_writes = conn.total_changes

    query = CALLBACK_FIXTURE["_click"](
        route, "music_quick|showroom|voice_profile_listen:105"
    )

    text, markup = query.message.replies[-1]
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "chưa có bản nghe thử" in text.lower()
    assert "music_quick|showroom|voice_profile_delete:105" in callbacks
    assert "Foreign voice 104" not in text
    assert conn.total_changes == before_click_writes


@pytest.mark.parametrize(
    "action",
    ("voice_profile_download", "voice_profile_edit_text", "voice_profile_generate"),
)
def test_foreign_voice_actions_return_callers_vault_without_state_changes(voice_vault_runtime, action):
    from copy import deepcopy

    ns, route, conn = voice_vault_runtime
    conn.execute(
        "INSERT INTO voice_profiles VALUES (?, ?, 'active', ?, ?, NULL, 0, '')",
        (104, "902", "foreign-provider-id", "Foreign voice 104"),
    )
    conn.commit()
    before_click_writes = conn.total_changes
    before_pending = deepcopy(ns["USER_PENDING"])
    # This copy function is only needed by the existing not-ready failure branch;
    # the test asserts the branch routes to owner-scoped recovery before reaching it.
    ns["voice_profile_not_ready_text"] = lambda *_args: "⚠️ Giọng chưa sẵn sàng."

    query = CALLBACK_FIXTURE["_click"](
        route, f"music_quick|showroom|{action}:104"
    )

    text, markup = query.message.replies[-1]
    assert "không tìm thấy giọng này trong tài khoản" in text.lower()
    expected_callbacks = [
        button.callback_data
        for row in ns["voice_vault_keyboard"](901, "vi", "showroom").inline_keyboard
        for button in row
    ]
    actual_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert actual_callbacks == expected_callbacks
    assert not any(str(data).endswith(":104") for data in actual_callbacks)
    assert "Foreign voice 104" not in text
    assert ns["USER_PENDING"] == before_pending
    assert conn.total_changes == before_click_writes


@pytest.mark.parametrize("action", ("voice_profile_default", "voice_profile_rename"))
@pytest.mark.parametrize("profile_case", ("foreign", "missing"))
def test_foreign_or_stale_default_and_rename_return_callers_vault_without_changes(
    voice_vault_runtime, action, profile_case
):
    from copy import deepcopy

    ns, route, conn = voice_vault_runtime
    conn.execute("ALTER TABLE voice_profiles ADD COLUMN updated_at TEXT")
    profile_id = 104 if profile_case == "foreign" else 999
    if profile_case == "foreign":
        conn.execute(
            "INSERT INTO voice_profiles (id, user_id, status, provider_voice_id, display_name, deleted_at, is_default, preview_audio_ref, updated_at) "
            "VALUES (?, ?, 'active', ?, ?, NULL, 1, '', NULL)",
            (profile_id, "902", "foreign-provider-id", "Foreign voice 104"),
        )
        conn.commit()
    if action == "voice_profile_default":
        exec(
            compile(
                "from __future__ import annotations\n" + CALLBACK_FIXTURE["_source"]("set_default_voice_profile"),
                "bot.py:set_default_voice_profile",
                "exec",
            ),
            ns,
        )

    before_rows = conn.execute(
        "SELECT id, user_id, is_default, updated_at FROM voice_profiles ORDER BY id"
    ).fetchall()
    before_writes = conn.total_changes
    before_pending = deepcopy(ns["USER_PENDING"])

    query = CALLBACK_FIXTURE["_click"](
        route, f"music_quick|showroom|{action}:{profile_id}"
    )

    text, markup = query.message.replies[-1]
    if action == "voice_profile_default":
        assert "chỉ giọng đã lưu thành công" in text.lower()
    else:
        assert "không tìm thấy giọng này" in text.lower()
    expected_callbacks = [
        button.callback_data
        for row in ns["voice_vault_keyboard"](901, "vi", "showroom").inline_keyboard
        for button in row
    ]
    actual_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert actual_callbacks == expected_callbacks
    assert not any(str(data).endswith(f":{profile_id}") for data in actual_callbacks)
    assert "Foreign voice 104" not in text
    assert ns["USER_PENDING"] == before_pending
    after_rows = conn.execute(
        "SELECT id, user_id, is_default, updated_at FROM voice_profiles ORDER BY id"
    ).fetchall()
    assert [tuple(row) for row in after_rows] == [tuple(row) for row in before_rows]
    assert conn.total_changes == before_writes


def test_owned_default_callback_keeps_default_change_scoped_to_owner(voice_vault_runtime):
    ns, route, conn = voice_vault_runtime
    conn.execute("ALTER TABLE voice_profiles ADD COLUMN updated_at TEXT")
    conn.execute(
        "INSERT INTO voice_profiles (id, user_id, status, provider_voice_id, display_name, deleted_at, is_default, preview_audio_ref, updated_at) "
        "VALUES (104, '902', 'active', 'foreign-provider-id', 'Foreign voice 104', NULL, 1, '', NULL)"
    )
    conn.commit()
    exec(
        compile(
            "from __future__ import annotations\n" + CALLBACK_FIXTURE["_source"]("set_default_voice_profile"),
            "bot.py:set_default_voice_profile",
            "exec",
        ),
        ns,
    )

    query = CALLBACK_FIXTURE["_click"](
        route, "music_quick|showroom|voice_profile_default:101"
    )

    text = query.message.replies[-1][0]
    assert "đã đặt làm giọng mặc định" in text.lower()
    defaults = conn.execute(
        "SELECT user_id, id, is_default FROM voice_profiles ORDER BY user_id, id"
    ).fetchall()
    assert [tuple(row) for row in defaults if row[0] == "901"] == [
        ("901", 101, 1), ("901", 102, 0), ("901", 103, 0)
    ]
    assert [tuple(row) for row in defaults if row[0] == "902"] == [("902", 104, 1)]


def test_owned_rename_callback_still_starts_rename_for_selected_profile(voice_vault_runtime):
    from copy import deepcopy

    ns, route, conn = voice_vault_runtime
    before_pending = deepcopy(ns["USER_PENDING"])

    query = CALLBACK_FIXTURE["_click"](
        route, "music_quick|showroom|voice_profile_rename:101"
    )

    text = query.message.replies[-1][0]
    assert "hãy nhập tên mới" in text.lower()
    assert ns["USER_PENDING"] != before_pending
