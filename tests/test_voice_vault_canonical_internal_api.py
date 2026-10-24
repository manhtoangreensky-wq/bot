import json
import os
import sys
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot
from services.voice_vault_service import (
    list_owner_voice_profiles,
    rename_owner_voice_profile,
    set_default_owner_voice_profile,
    soft_delete_owner_voice_profile,
    get_voice_profile_preview_delivery,
)
from services.subdub_voice_resolution import resolve_subdub_voice_authority


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    original_db = bot.DB_FILE
    bot.DB_FILE = path

    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE voice_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                provider TEXT DEFAULT '',
                provider_voice_id TEXT DEFAULT '',
                display_name TEXT DEFAULT '',
                consent_status TEXT DEFAULT 'confirmed',
                consent_at TEXT DEFAULT '',
                source_file_id TEXT DEFAULT '',
                source_file_ref TEXT DEFAULT '',
                preview_audio_ref TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                is_default INTEGER DEFAULT 0,
                created_at TEXT DEFAULT '2026-10-24 10:00:00',
                updated_at TEXT DEFAULT '2026-10-24 10:00:00',
                deleted_at TEXT,
                last_used_at TEXT,
                metadata_json TEXT DEFAULT '{}'
            )
        """)
        conn.commit()

    yield path

    bot.DB_FILE = original_db
    try:
        os.remove(path)
    except Exception:
        pass


def _seed_profile(user_id: str, display_name: str, status: str = "active", is_default: int = 0, preview_ref: str = "", provider_voice: str = "custom_voice_123"):
    with sqlite3.connect(bot.DB_FILE) as conn:
        cur = conn.execute(
            """
            INSERT INTO voice_profiles (user_id, provider, provider_voice_id, display_name, status, is_default, preview_audio_ref)
            VALUES (?, 'minimax', ?, ?, ?, ?, ?)
            """,
            (user_id, provider_voice, display_name, status, is_default, preview_ref),
        )
        conn.commit()
        return cur.lastrowid


def test_list_owner_scope_and_foreign_isolation(test_db):
    pid1 = _seed_profile("1001", "Voice Owner 1", status="active")
    pid2 = _seed_profile("1001", "Voice Owner 1 Def", status="ready", is_default=1)
    pid_other = _seed_profile("1002", "Voice Other User", status="active")
    pid_del = _seed_profile("1001", "Deleted Voice", status="deleted")

    # Owner 1 listing
    items_1001 = list_owner_voice_profiles("1001")
    ids_1001 = [p["id"] for p in items_1001]
    assert pid1 in ids_1001
    assert pid2 in ids_1001
    assert pid_other not in ids_1001  # LIST_FOREIGN_ISOLATION
    assert pid_del not in ids_1001    # DELETED_PROFILE_NOT_ACTIVE
    assert len(items_1001) == 2       # LIST_OWNER_SCOPE

    # Other owner listing
    items_1002 = list_owner_voice_profiles("1002")
    ids_1002 = [p["id"] for p in items_1002]
    assert pid_other in ids_1002
    assert pid1 not in ids_1002
    assert len(items_1002) == 1


def test_rename_success_and_validation_and_foreign_blocked(test_db):
    pid = _seed_profile("1001", "Old Name")

    # RENAME_SUCCESS
    ok, code, status, res = rename_owner_voice_profile("1001", pid, "Brand New Name")
    assert ok is True
    assert status == 200
    assert res["profile"]["display_name"] == "Brand New Name"

    # RENAME_INVALID_NAME (< 2 chars)
    ok_inv, code_inv, status_inv, _ = rename_owner_voice_profile("1001", pid, "A")
    assert ok_inv is False
    assert status_inv == 400
    assert code_inv == "INVALID_DISPLAY_NAME"

    # RENAME_FOREIGN_BLOCKED
    ok_foreign, code_foreign, status_foreign, _ = rename_owner_voice_profile("9999", pid, "Hacked Name")
    assert ok_foreign is False
    assert status_foreign == 404
    assert code_foreign == "PROFILE_NOT_FOUND"


def test_set_default_success_and_readiness_fail_and_foreign_blocked(test_db):
    pid_ready = _seed_profile("1001", "Ready Voice", status="active", is_default=0, provider_voice="voice_ready_001")
    pid_not_ready = _seed_profile("1001", "Draft Voice", status="pending_name", is_default=0, provider_voice="")

    # SET_DEFAULT_NOT_READY_FAIL
    ok_nr, code_nr, status_nr, _ = set_default_owner_voice_profile("1001", pid_not_ready)
    assert ok_nr is False
    assert status_nr == 400
    assert code_nr == "VOICE_PROFILE_NOT_READY"

    # SET_DEFAULT_FOREIGN_BLOCKED
    ok_fb, code_fb, status_fb, _ = set_default_owner_voice_profile("9999", pid_ready)
    assert ok_fb is False
    assert status_fb == 404
    assert code_fb == "PROFILE_NOT_FOUND"

    # SET_DEFAULT_SUCCESS
    ok_def, code_def, status_def, res_def = set_default_owner_voice_profile("1001", pid_ready)
    assert ok_def is True
    assert status_def == 200
    assert res_def["is_default"] is True


def test_soft_delete_success_idempotent_and_foreign_blocked(test_db):
    pid = _seed_profile("1001", "To Be Deleted", status="active", is_default=1)

    # SOFT_DELETE_FOREIGN_BLOCKED
    ok_fb, code_fb, status_fb, _ = soft_delete_owner_voice_profile("9999", pid)
    assert ok_fb is False
    assert status_fb == 404
    assert code_fb == "PROFILE_NOT_FOUND"

    # SOFT_DELETE_SUCCESS
    ok_del, code_del, status_del, res_del = soft_delete_owner_voice_profile("1001", pid)
    assert ok_del is True
    assert status_del == 200
    assert res_del["deleted"] is True

    # Check database state
    with sqlite3.connect(bot.DB_FILE) as conn:
        row = conn.execute("SELECT status, is_default, deleted_at FROM voice_profiles WHERE id=?", (pid,)).fetchone()
        assert row[0] == "deleted"
        assert row[1] == 0
        assert row[2] is not None

    # SOFT_DELETE_IDEMPOTENT
    ok_idem, code_idem, status_idem, res_idem = soft_delete_owner_voice_profile("1001", pid)
    assert ok_idem is True
    assert status_idem == 200
    assert res_idem["deleted"] is True

    # DELETED_PROFILE_NOT_ACTIVE
    profiles = list_owner_voice_profiles("1001")
    assert pid not in [p["id"] for p in profiles]


def test_preview_delivery_contracts(test_db):
    temp_audio = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    temp_audio.write(b"\xFF\xFB\x90\x44" + b"\x00" * 100)
    temp_audio.close()

    try:
        pid_ready_file = _seed_profile("1001", "With Preview File", status="active", preview_ref=temp_audio.name)
        pid_ready_url = _seed_profile("1001", "With Preview URL", status="active", preview_ref="https://cdn.toanaas.vn/preview.mp3")
        pid_missing_art = _seed_profile("1001", "Missing Artifact", status="active", preview_ref="")
        pid_missing_disk = _seed_profile("1001", "Missing On Disk", status="active", preview_ref="C:/invalid/path.mp3")
        pid_not_ready = _seed_profile("1001", "Not Ready", status="deleted", preview_ref=temp_audio.name)

        # PREVIEW_READY_SUCCESS (file delivery)
        ok_f, code_f, status_f, res_f, fpath = get_voice_profile_preview_delivery("1001", pid_ready_file)
        assert ok_f is True
        assert status_f == 200
        assert fpath == temp_audio.name
        assert "password" not in json.dumps(res_f)  # NO_PRIVATE_METADATA_LEAK

        # PREVIEW_READY_SUCCESS (url delivery)
        ok_u, code_u, status_u, res_u, _ = get_voice_profile_preview_delivery("1001", pid_ready_url)
        assert ok_u is True
        assert status_u == 200
        assert res_u["preview_url"] == "https://cdn.toanaas.vn/preview.mp3"

        # PREVIEW_MISSING_ARTIFACT_TRUTHFUL
        ok_ma, code_ma, status_ma, _, _ = get_voice_profile_preview_delivery("1001", pid_missing_art)
        assert ok_ma is False
        assert status_ma == 404
        assert code_ma == "PREVIEW_MISSING_ARTIFACT"

        # PREVIEW_MISSING_ARTIFACT_TRUTHFUL (missing file on disk)
        ok_md, code_md, status_md, _, _ = get_voice_profile_preview_delivery("1001", pid_missing_disk)
        assert ok_md is False
        assert status_md == 404
        assert code_md == "PREVIEW_MISSING_ARTIFACT"

        # PREVIEW_READY_FALSE_BLOCKED
        ok_nr, code_nr, status_nr, _, _ = get_voice_profile_preview_delivery("1001", pid_not_ready)
        assert ok_nr is False
        assert status_nr == 404  # Deleted profile treated as not found
        assert code_nr == "PROFILE_NOT_FOUND"

        # PREVIEW_FOREIGN_BLOCKED
        ok_for, code_for, status_for, _, _ = get_voice_profile_preview_delivery("9999", pid_ready_file)
        assert ok_for is False
        assert status_for == 404
        assert code_for == "PROFILE_NOT_FOUND"

    finally:
        try:
            os.remove(temp_audio.name)
        except Exception:
            pass


def test_handoff_contracts(test_db):
    pid_ready = _seed_profile("1001", "Subdub Voice", status="active", provider_voice="voice_ready_777")
    pid_not_ready = _seed_profile("1001", "Not Ready Voice", status="pending_name", provider_voice="")
    pid_del = _seed_profile("1001", "Deleted Voice", status="deleted")

    # HANDOFF_OWNER_SUCCESS
    ok_sub, err_sub, status_sub, res_sub = resolve_subdub_voice_authority(
        "1001",
        {"mode": "dub", "voice_profile_id": pid_ready, "target_language": "vi"}
    )
    assert ok_sub is True
    assert status_sub == 200
    assert res_sub["voice_selection_mode"] in ("manual", "custom")
    assert res_sub["voice_profile_id"] == pid_ready
    assert res_sub["resolved_voice_id_masked"] != ""  # Masked
    assert res_sub["resolved_voice_id_masked"] != "voice_ready_777"  # NO_PRIVATE_METADATA_LEAK

    # HANDOFF_FOREIGN_BLOCKED
    ok_for, err_for, status_for, _ = resolve_subdub_voice_authority(
        "9999",
        {"mode": "dub", "voice_profile_id": pid_ready, "target_language": "vi"}
    )
    assert ok_for is False
    assert status_for == 403
    assert err_for == "FORBIDDEN_CROSS_OWNER"

    # HANDOFF_DELETED_NOT_READY_FAIL
    ok_dn, err_dn, status_dn, _ = resolve_subdub_voice_authority(
        "1001",
        {"mode": "dub", "voice_profile_id": pid_not_ready, "target_language": "vi"}
    )
    assert ok_dn is False
    assert status_dn == 422
    assert err_dn in ("VOICE_NOT_READY", "PROFILE_NOT_READY")

    ok_del, err_del, status_del, _ = resolve_subdub_voice_authority(
        "1001",
        {"mode": "dub", "voice_profile_id": pid_del, "target_language": "vi"}
    )
    assert ok_del is False
    assert status_del == 422
    assert err_del == "PROFILE_NOT_FOUND"
