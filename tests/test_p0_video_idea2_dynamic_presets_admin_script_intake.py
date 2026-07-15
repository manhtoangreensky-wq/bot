from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

import pytest

from services import (
    video_idea_catalog,
    video_idea_script_intake,
    video_idea_store,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")

OLD_CATEGORIES = {
    "sales", "ugc", "education", "story", "space", "lifestyle", "digital", "visual",
}
NEW_CATEGORIES = {
    "history", "sports", "travel", "industry", "data_news", "self_help", "meme", "asmr",
}


def _seeded_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    video_idea_store.seed_catalog(
        conn,
        video_idea_catalog.dynamic_category_seeds(),
        video_idea_catalog.dynamic_preset_seeds(),
    )
    conn.commit()
    return conn


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


def _top_level_function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    starts = [position for position in starts if position >= 0]
    if not starts:
        raise AssertionError(f"missing function: {name}")
    start = min(starts)
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ", "\nclass ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    end = min(candidates) if candidates else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def test_catalog_has_exactly_sixteen_groups_preserves_old_48_and_seeds_24_new_presets():
    counts = Counter(str(item["category"]) for item in video_idea_catalog.IDEAS)
    assert len(video_idea_catalog.CATEGORIES) == 16
    assert len(video_idea_catalog.IDEAS) == 72
    assert {key for key, _label in video_idea_catalog.CATEGORIES} == OLD_CATEGORIES | NEW_CATEGORIES
    assert all(counts[key] == 6 for key in OLD_CATEGORIES)
    assert all(counts[key] >= 3 for key in NEW_CATEGORIES)
    assert sum(counts[key] for key in OLD_CATEGORIES) == 48
    assert sum(counts[key] for key in NEW_CATEGORIES) == 24


def test_existing_48_titles_descriptions_and_routing_are_preserved_in_dynamic_seeds():
    seeded = {row["preset_key"]: row for row in video_idea_catalog.dynamic_preset_seeds()}
    for idea in video_idea_catalog.IDEAS[:48]:
        row = seeded[idea["idea_id"]]
        assert row["title"] == idea["title"]
        assert row["description"] == idea["summary"]
        assert row["recommended_product_id"] == idea["recommended_product_id"]
        assert row["recommended_profile_id"] == idea["recommended_profile_id"]
        assert row["image_prompt_seed"] == idea["image_prompt_seed"]
        assert row["video_prompt_seed"] == idea["video_prompt_seed"]


def test_category_order_labels_and_short_callback_contract_are_public_safe():
    categories = video_idea_catalog.dynamic_category_seeds()
    assert [row["category_key"] for row in categories] == [key for key, _label in video_idea_catalog.CATEGORIES]
    assert [row["sort_order"] for row in categories] == list(range(1, 17))
    assert all(row["public_name"] and row["short_button_name"] for row in categories)
    assert max(len(row["short_button_name"]) for row in categories) <= 20
    callbacks = [f"videa|cat|{index}" for index in range(1, 17)]
    callbacks += [f"videa|preset|{index}" for index in range(1, 73)]
    assert len(callbacks) == len(set(callbacks))
    assert max(map(len, callbacks)) <= 64


def test_every_seed_has_complete_eight_second_planning_metadata_and_specific_safety():
    rows = video_idea_catalog.dynamic_preset_seeds()
    assert len(rows) == 72
    for row in rows:
        assert 1 <= row["recommended_scene_count"] <= 20
        assert row["scene_duration_sec"] == 8
        assert row["system_guidance"]
        assert "{scene_count}" in row["user_prompt_template"]
        assert row["voice_plan"]
        assert row["music_plan"]
        assert row["audio_plan"]
        assert row["visual_plan"]
        assert row["content_safety_note"]
    by_category = {key: " ".join(row["content_safety_note"] for row in rows if row["category_key"] == key).lower() for key in NEW_CATEGORIES}
    assert "không bịa" in by_category["history"]
    assert "xác minh" in by_category["sports"]
    assert "giờ mở cửa" in by_category["travel"]
    assert "nguy hiểm" in by_category["industry"]
    assert "chắc thắng" in by_category["data_news"]
    assert "không hứa" in by_category["self_help"]
    assert "sao chép giọng" in by_category["meme"]
    assert "không đưa tuyên bố chữa bệnh" in by_category["asmr"]
    asmr_audio = " ".join(row["audio_plan"] for row in rows if row["category_key"] == "asmr").lower()
    assert "âm thanh môi trường" in asmr_audio
    assert "loop" in asmr_audio
    assert "trước xác nhận cuối" in asmr_audio


def test_migration_and_seed_are_idempotent_and_do_not_overwrite_admin_edit():
    conn = _seeded_db()
    foreign_keys = conn.execute("PRAGMA foreign_key_list(video_idea_presets)").fetchall()
    assert any(row[2] == "video_idea_categories" and row[3] == "category_id" for row in foreign_keys)
    first = video_idea_store.catalog_counts(conn)
    second_seed = video_idea_store.seed_catalog(
        conn,
        video_idea_catalog.dynamic_category_seeds(),
        video_idea_catalog.dynamic_preset_seeds(),
    )
    assert first == {"categories": 16, "presets": 72}
    assert second_seed == {"categories_inserted": 0, "presets_inserted": 0}
    row = video_idea_store.preset_by_key(conn, "history_legendary_general")
    updated = video_idea_store.update_preset(conn, row["id"], {"title": "Bản admin đã sửa"}, actor_id="42")
    assert updated["version"] == row["version"] + 1
    video_idea_store.seed_catalog(conn, video_idea_catalog.dynamic_category_seeds(), video_idea_catalog.dynamic_preset_seeds())
    assert video_idea_store.preset_by_key(conn, "history_legendary_general")["title"] == "Bản admin đã sửa"


def test_additive_migration_upgrades_partial_catalog_tables_idempotently():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE video_idea_categories "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, category_key TEXT NOT NULL UNIQUE)"
    )
    conn.execute(
        "CREATE TABLE video_idea_presets "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, preset_key TEXT NOT NULL UNIQUE, category_id INTEGER NOT NULL)"
    )
    video_idea_store.ensure_schema(conn)
    video_idea_store.ensure_schema(conn)
    category_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(video_idea_categories)").fetchall()
    }
    preset_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(video_idea_presets)").fetchall()
    }
    assert {"public_name", "short_button_name", "is_active", "version", "updated_at"} <= category_columns
    assert {
        "title", "system_guidance", "user_prompt_template", "recommended_scene_count",
        "scene_duration_sec", "audio_plan", "is_active", "version", "updated_at",
    } <= preset_columns
    seeded = video_idea_store.seed_catalog(
        conn,
        video_idea_catalog.dynamic_category_seeds(),
        video_idea_catalog.dynamic_preset_seeds(),
    )
    assert seeded == {"categories_inserted": 16, "presets_inserted": 72}
    assert video_idea_store.catalog_counts(conn) == {"categories": 16, "presets": 72}


def test_soft_disable_sort_version_audit_clone_and_no_hard_delete():
    conn = _seeded_db()
    row = video_idea_store.preset_by_key(conn, "sports_match_analysis")
    disabled = video_idea_store.set_preset_active(conn, row["id"], False, actor_id="7")
    assert disabled["is_active"] == 0
    assert video_idea_store.preset_by_id(conn, row["id"])
    moved = video_idea_store.update_preset(conn, row["id"], {"sort_order": 99}, actor_id="7")
    assert moved["sort_order"] == 99
    clone = video_idea_store.clone_preset(conn, row["id"], "sports_match_analysis_copy", "Bản sao", actor_id="7")
    assert clone["is_active"] == 0
    assert clone["version"] == 1
    audit = video_idea_store.list_audit(conn, limit=20)
    assert {item["action"] for item in audit} >= {"disable", "edit", "clone", "create"}
    source = (ROOT / "services" / "video_idea_store.py").read_text(encoding="utf-8").lower()
    assert "delete from video_idea_presets" not in source
    assert "delete from video_idea_categories" not in source


def test_export_import_round_trip_is_versioned_and_rejects_secrets_or_script_injection():
    conn = _seeded_db()
    exported = video_idea_store.export_catalog(conn)
    assert exported["schema_version"] == 1
    assert len(exported["categories"]) == 16
    assert len(exported["presets"]) == 72
    target = sqlite3.connect(":memory:")
    result = video_idea_store.apply_import(target, exported, actor_id="9")
    assert result == {
        "categories_created": 16,
        "categories_updated": 0,
        "presets_created": 72,
        "presets_updated": 0,
    }
    assert video_idea_store.catalog_counts(target) == {"categories": 16, "presets": 72}
    poisoned = json.loads(json.dumps(exported))
    poisoned["presets"][0]["api_key"] = "must-not-enter-db"
    with pytest.raises(ValueError, match="provider_secret_not_allowed"):
        video_idea_store.validate_import_payload(poisoned)
    scripted = json.loads(json.dumps(exported))
    scripted["presets"][0]["title"] = "<script>alert(1)</script>"
    with pytest.raises(ValueError, match="unsafe_script_or_sql_payload"):
        video_idea_store.validate_import_payload(scripted)


@pytest.mark.parametrize("scene_count", [1, 2, 3, 5, 10, 20])
def test_auto_track_is_deterministic_exact_n_and_provider_free(scene_count: int):
    preset = video_idea_catalog.dynamic_preset_seeds()[48]
    idea = video_idea_catalog.idea_by_id(preset["preset_key"])
    beats = video_idea_catalog.semantic_beats_for_idea(idea, scene_count)
    first = video_idea_script_intake.deterministic_scene_drafts(
        preset,
        scene_count=scene_count,
        topic="chủ đề thử",
        customer_brief="giữ nhân vật và kết bằng CTA nhẹ",
        semantic_beats=beats,
    )
    second = video_idea_script_intake.deterministic_scene_drafts(
        preset,
        scene_count=scene_count,
        topic="chủ đề thử",
        customer_brief="giữ nhân vật và kết bằng CTA nhẹ",
        semantic_beats=beats,
    )
    assert first == second
    assert len(first) == scene_count
    assert [row["scene_index"] for row in first] == list(range(1, scene_count + 1))
    assert all(row["image_prompt"] and row["video_prompt"] and row["transition"] for row in first)
    assert all(row["audio_plan"] for row in first)


def test_manual_parser_prioritizes_scene_headings_and_never_creates_empty_scenes():
    result = video_idea_script_intake.split_manual_script(
        "Cảnh 1: Mở cửa và bước vào phòng.\n\nCảnh 2: Đặt sản phẩm lên bàn.\nCảnh 3: Khép bằng kết quả rõ."
    )
    assert result["ok"] is True
    assert result["method"] == "scene_heading"
    assert result["scene_count"] == 3
    assert all(result["scenes"])
    assert result["estimated_duration_seconds"] == 24


def test_manual_parser_uses_paragraph_then_sentence_fallback_and_blocks_more_than_20():
    paragraphs = video_idea_script_intake.split_manual_script("Đoạn đầu có hành động.\n\nĐoạn sau có kết quả.")
    assert paragraphs["method"] == "paragraph"
    single = video_idea_script_intake.split_manual_script("Một khối dài không có dấu kết")
    assert single["method"] == "single_block"
    too_many = "\n".join(f"Cảnh {index}: Nội dung {index}." for index in range(1, 22))
    blocked = video_idea_script_intake.split_manual_script(too_many)
    assert blocked["ok"] is False
    assert blocked["reason"] == "too_many_scenes"
    assert blocked["scene_count"] == 21


def test_scene_draft_helpers_reject_more_than_twenty_without_silent_truncation():
    preset = video_idea_catalog.dynamic_preset_seeds()[0]
    with pytest.raises(ValueError, match="scene_limit_exceeded"):
        video_idea_script_intake.manual_scene_drafts(
            [f"Nội dung cảnh {index}" for index in range(1, 22)],
            preset,
        )
    with pytest.raises(ValueError, match="scene_limit_exceeded"):
        video_idea_script_intake.renumber_scene_drafts(
            [{"scene_index": index, "content": f"Cảnh {index}"} for index in range(1, 22)]
        )


def test_manual_editor_supports_add_edit_delete_merge_split_reorder_and_restore_data():
    preset = video_idea_catalog.dynamic_preset_seeds()[0]
    rows = video_idea_script_intake.manual_scene_drafts(["Mở đầu", "Phát triển", "Kết thúc"], preset)
    assert all(row["audio_plan"] for row in rows)
    rows = video_idea_script_intake.edit_scene(rows, 1, "Mở đầu đã sửa")
    rows = video_idea_script_intake.add_scene(rows, "Chi tiết mới", after_index=1)
    rows = video_idea_script_intake.move_scene(rows, 2, 3)
    rows = video_idea_script_intake.merge_scenes(rows, 1)
    rows = video_idea_script_intake.split_scene(rows, 1, "Phần một", "Phần hai")
    rows = video_idea_script_intake.delete_scene(rows, 2)
    assert rows
    assert [row["scene_index"] for row in rows] == list(range(1, len(rows) + 1))
    assert all(row.get("content") for row in rows)


def test_public_callbacks_are_short_dynamic_and_handoff_only_to_scene3():
    menu = _between("def video_idea_menu_keyboard", "\n\ndef _video_idea_dynamic_db")
    assert '"videa|page|1"' in menu
    dynamic = _between("def _video_idea_dynamic_db", "\n\ndef video_idea_catalog_categories_text")
    for callback in ("videa|cat|", "videa|preset|", "videa|page|", "videa|mode|a", "videa|mode|m"):
        assert callback in dynamic
    handler = _between("async def handle_video_idea_dynamic_callback", "\n\ndef video_idea_admin_main_text")
    assert "video_idea_dynamic_scene3_state(state)" in handler
    assert "video_profile_scene1_render(query, handoff, lang)" in handler
    assert "open_video_finalization" not in handler
    assert "create_product_video_job" not in handler
    assert "provider.submit" not in handler


def test_public_state_and_scene3_handoff_keep_all_preconfirm_side_effects_zero():
    source = _between("def video_idea_dynamic_scene3_state", "\n\nasync def handle_video_idea_dynamic_callback")
    for expected in (
        '"provider_called": False', '"image_provider_called": False',
        '"music_provider_calls": 0', '"voice_provider_calls": 0',
        '"files_generated": 0', '"job_created": False', '"outbox_created": False',
        '"wallet_mutations": 0', '"xu_charged": 0', '"final_confirmed": False',
    ):
        assert expected in source
    assert '"idea_source"' in source
    assert '"scene_drafts"' in source
    assert '"manual_script_raw"' in source


def test_admin_wizard_uses_canonical_guard_preview_confirm_soft_disable_and_audit():
    command = _between("async def cmd_video_idea_admin", "\n\nasync def handle_video_idea_admin_callback")
    callback = _between("async def handle_video_idea_admin_callback", "\n\nasync def handle_video_idea_callback")
    assert "is_admin_user" in command
    assert "is_admin_user" in callback
    assert "video_idea_admin_candidate" in callback
    assert "video_idea_admin_confirm_keyboard" in callback
    for action in (
        "create_category", "update_category", "toggle_category", "create_preset",
        "update_preset", "toggle_preset", "clone_preset", "apply_import",
    ):
        assert action in callback
    assert "delete" not in callback.lower()
    assert "traceback" not in callback.lower()
    assert 'CommandHandler("video_idea_admin", cmd_video_idea_admin)' in BOT_SOURCE
    assert 'pattern=r"^viadm\\|"' in BOT_SOURCE


def test_admin_edits_and_clones_are_validated_before_preview():
    pending = _between(
        "async def handle_video_idea_admin_pending_text",
        "\n\nasync def handle_developing_video_pending_text",
    )
    assert 'before = video_idea_dynamic_category(entity_id)' in pending
    assert 'before = video_idea_dynamic_preset(entity_id)' in pending
    assert 'normalized = video_idea_store.normalize_category({' in pending
    assert 'normalized = video_idea_store.normalize_preset({' in pending
    assert 'raise ValueError("category_not_found")' in pending
    assert 'raise ValueError("preset_not_found")' in pending
    assert 'raise ValueError("preset_key_exists")' in pending


def test_dynamic_catalog_uses_db_count_and_preserves_page_back_stack():
    helpers = _between("def video_idea_dynamic_page_text", "\n\ndef video_idea_dynamic_preset_text")
    handler = _between("async def handle_video_idea_dynamic_callback", "\n\ndef video_idea_admin_main_text")
    assert "video_idea_store.catalog_counts" in helpers
    assert "back_page: int = 1" in helpers
    assert 'context.user_data["video_idea_catalog_page"] = page' in handler
    assert '"catalog_page": catalog_page' in handler
    assert "if offset >= len(all_presets):" in handler
    assert "offset = 0" in handler


def test_every_touched_idea2_function_compiles_independently():
    names = (
        "init_db",
        "video_idea_menu_keyboard",
        "_video_idea_dynamic_db",
        "video_idea_dynamic_categories",
        "video_idea_dynamic_category",
        "video_idea_dynamic_category_key",
        "video_idea_dynamic_presets",
        "video_idea_dynamic_preset",
        "video_idea_dynamic_page_text",
        "video_idea_dynamic_page_keyboard",
        "video_idea_dynamic_category_text",
        "video_idea_dynamic_category_keyboard",
        "video_idea_dynamic_preset_text",
        "video_idea_dynamic_preset_keyboard",
        "video_idea_dynamic_scene_count_text",
        "video_idea_dynamic_scene_count_keyboard",
        "video_idea_dynamic_preview_text",
        "video_idea_dynamic_preview_keyboard",
        "video_idea_dynamic_state",
        "video_idea_dynamic_build_drafts",
        "video_idea_dynamic_scene3_state",
        "video_idea_dynamic_remember_drafts",
        "handle_video_idea_dynamic_pending_text",
        "handle_video_idea_admin_pending_text",
        "handle_developing_video_pending_text",
        "handle_video_idea_dynamic_callback",
        "cmd_video_idea_admin",
        "handle_video_idea_admin_callback",
        "handle_video_idea_callback",
        "handle_message",
        "lifespan",
    )
    for name in names:
        source = "from __future__ import annotations\n" + _top_level_function_source(name)
        compile(source, f"<idea2:{name}>", "exec")


def test_no_provider_runtime_worker_wallet_music_voice_subdub_or_storage_scope_leak():
    changed_services = "\n".join(
        (ROOT / "services" / name).read_text(encoding="utf-8").lower()
        for name in ("video_idea_catalog.py", "video_idea_store.py", "video_idea_script_intake.py")
    )
    for forbidden in (
        "requests.", "httpx.", "aiohttp.", "shopaikey", "key4u", "suno_client",
        "provider.submit", "submit_provider", "create_product_video_job",
        "debit_wallet", "charge_wallet", "remote_worker",
    ):
        assert forbidden not in changed_services
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_product_video_public_confirm_callback, pattern=r"^vproduct\\|b14_confirm$")'
    ) == 1
