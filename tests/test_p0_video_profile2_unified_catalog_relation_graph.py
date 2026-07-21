from __future__ import annotations

import sqlite3
from pathlib import Path

from services import video_idea_catalog, video_profile_catalog, video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def test_catalog_has_exactly_32_unique_profiles_across_three_pages():
    status = video_profile_catalog.mapping_status()
    assert status["profiles"] == 32
    assert status["pages"] == 3
    assert status["duplicate_public_names"] == 0
    assert status["dead_link_targets"] == []

    page_counts = {
        page_group: len(
            [
                item
                for item in video_profile_catalog.PROFILE_SEEDS
                if item["page_group"] == page_group
            ]
        )
        for page_group, _label in video_profile_catalog.PAGE_GROUPS
    }
    assert page_counts == {
        "sales_social": 10,
        "story_knowledge_emotion": 10,
        "industry_visual": 12,
    }
    assert len({item["profile_key"] for item in video_profile_catalog.PROFILE_SEEDS}) == 32


def test_relation_graph_is_complete_safe_and_uses_all_relation_types():
    rows = video_profile_catalog.link_seeds()
    keys = set(video_profile_catalog.PROFILE_BY_KEY)
    assert set(video_profile_catalog.PROFILE_LINK_TARGETS) == keys
    assert all(row["source_profile_key"] in keys for row in rows)
    assert all(row["target_profile_key"] in keys for row in rows)
    assert all(row["source_profile_key"] != row["target_profile_key"] for row in rows)
    assert {row["relation_type"] for row in rows} == video_profile_catalog.RELATION_TYPES
    assert all(1 <= len(targets) <= 5 for targets in video_profile_catalog.PROFILE_LINK_TARGETS.values())


def test_all_legacy_and_idea_mappings_are_complete_and_target_canonical_profiles():
    keys = set(video_profile_catalog.PROFILE_BY_KEY)
    assert len(video_profile_catalog.LEGACY_CONTENT_PROFILE_MAP) == 12
    assert len(video_profile_catalog.LEGACY_TECHNICAL_PROFILE_MAP) == 14
    assert len(video_profile_catalog.IDEA_GROUP_PROFILE_MAP) == 16

    for mapping in (
        video_profile_catalog.LEGACY_CONTENT_PROFILE_MAP,
        video_profile_catalog.LEGACY_TECHNICAL_PROFILE_MAP,
    ):
        for primary, linked in mapping.values():
            assert primary in keys
            assert set(linked) <= keys
    for targets in video_profile_catalog.IDEA_GROUP_PROFILE_MAP.values():
        assert targets
        assert set(targets) <= keys


def test_sqlite_catalog_seed_is_idempotent_and_admin_rows_need_no_code_change():
    conn = sqlite3.connect(":memory:")
    first = video_profile_catalog.seed_catalog(conn)
    second = video_profile_catalog.seed_catalog(conn)
    assert first["profiles_inserted"] == 32
    assert first["links_inserted"] == len(video_profile_catalog.link_seeds())
    assert second == {"profiles_inserted": 0, "links_inserted": 0}

    added = video_profile_catalog.upsert_profile(
        conn,
        {
            "profile_key": "admin_medical_explainer",
            "icon": "🩺",
            "public_name": "Giải thích y khoa đã kiểm chứng",
            "short_name": "Giải thích y khoa",
            "page_group": "story_knowledge_emotion",
            "description": "Giải thích thông tin sức khỏe có nguồn và giới hạn rõ.",
            "default_scene_pattern": ["Câu hỏi", "Nguồn", "Giải thích", "Lưu ý"],
            "narrative_tags": ["explainer"],
            "industry_tags": ["health"],
            "goal_tags": ["education"],
        },
    )
    assert added["profile_key"] == "admin_medical_explainer"
    linked = video_profile_catalog.upsert_link(
        conn,
        {
            "source_profile_key": "admin_medical_explainer",
            "target_profile_key": "knowledge_explainer",
            "relation_type": "recommended_with",
            "weight": 90,
            "reason": "Dùng khung giải thích rõ ràng.",
        },
    )
    assert linked["target_profile_key"] == "knowledge_explainer"
    assert any(
        item["profile_key"] == "admin_medical_explainer"
        for item in video_profile_catalog.list_profiles(
            conn,
            page_group="story_knowledge_emotion",
        )
    )
    conn.close()


def test_old_sessions_migrate_without_losing_subject_scene_assets_or_choices():
    old = {
        "subject": "Câu chuyện danh tướng",
        "scene_count": 5,
        "content_type": "history",
        "technical_profile": "cinematic_vfx",
        "assets": {"items": [{"file_id": "legacy-image"}]},
        "requirements": {"identity": "giữ đúng nhân vật"},
    }
    migrated = video_scene3_flow.normalize_state(old)
    assert migrated["primary_profile"] == "character_animation_vfx"
    assert migrated["linked_profiles"] == ["short_film_trailer", "documentary_series"]
    assert migrated["subject"] == old["subject"]
    assert migrated["scene_count"] == 5
    assert migrated["assets"] == old["assets"]
    assert migrated["requirements"] == old["requirements"]

    canonical = video_profile_catalog.migrate_session_profile_state({
        **old,
        "profile_bundle_version": video_profile_catalog.SCHEMA_VERSION,
        "primary_profile": "",
        "linked_profiles": [],
    })
    assert canonical["primary_profile"] == ""
    assert canonical["linked_profiles"] == []

    for legacy_key, (expected_primary, _linked) in video_profile_catalog.LEGACY_CONTENT_PROFILE_MAP.items():
        result = video_profile_catalog.canonical_bundle_from_legacy(legacy_key, "")
        assert result["primary_profile"] == expected_primary
    for legacy_key, (expected_primary, _linked) in video_profile_catalog.LEGACY_TECHNICAL_PROFILE_MAP.items():
        result = video_profile_catalog.canonical_bundle_from_legacy("", legacy_key)
        assert result["primary_profile"] == expected_primary


def test_primary_selection_never_auto_enables_links_and_link_limit_is_two():
    state = video_scene3_flow.default_state(
        product_type="video_ai_real",
        subject="Quảng cáo mỹ phẩm có người mẫu",
    )
    state["scene_count"] = 3
    selected = video_scene3_flow.select_primary_profile(state, "sales_ads")
    assert selected["primary_profile"] == "sales_ads"
    assert selected["linked_profiles"] == []

    selected, changed = video_scene3_flow.toggle_linked_profile(
        selected,
        "fashion_beauty_lookbook",
    )
    assert changed is True
    selected, changed = video_scene3_flow.toggle_linked_profile(
        selected,
        "character_animation_vfx",
    )
    assert changed is True
    blocked, changed = video_scene3_flow.toggle_linked_profile(
        selected,
        "product_3d_showcase",
    )
    assert changed is False
    assert blocked["linked_profiles"] == [
        "fashion_beauty_lookbook",
        "character_animation_vfx",
    ]


def test_bundle_drives_exact_n_semantic_beats_and_planning_context():
    state = video_scene3_flow.default_state(
        product_type="video_ai_real",
        subject="Review ứng dụng quản lý công việc",
    )
    state["scene_count"] = 4
    state = video_scene3_flow.select_primary_profile(state, "product_review_demo")
    state, _changed = video_scene3_flow.toggle_linked_profile(state, "app_website_saas")
    state, _changed = video_scene3_flow.toggle_linked_profile(state, "tutorial_howto")

    beats = video_profile_catalog.semantic_beats_for_bundle(
        state["primary_profile"],
        state["linked_profiles"],
        state["scene_count"],
    )
    assert len(beats) == 4
    assert all("Review / demo sản phẩm" in item["main_idea"] for item in beats)
    package = video_scene3_flow.build_planning_package(state)
    assert len((package.get("plan") or {}).get("scenes") or []) == 4
    assert package["provider_called"] is False
    assert package["job_created"] is False
    assert package["outbox_created"] is False
    assert package["xu_charged"] == 0


def test_idea2_handoff_maps_to_primary_profile_without_auto_linking():
    state = video_idea_catalog.build_scene3_handoff_state(
        {
            "title": "Showcase dây chuyền tự động",
            "scene_count": 3,
            "category": "industry",
            "recommended_profile_id": "tutorial_explainer",
            "summary": "Giải thích quy trình và lợi ích.",
        },
        product_id_override="video_ai_real",
    )
    assert state["primary_profile"] == "tutorial_howto"
    assert state["linked_profiles"] == []
    assert state["profile_bundle_version"] == video_profile_catalog.SCHEMA_VERSION
    assert state["provider_called"] is False
    assert state["image_provider_called"] is False
    assert state["job_created"] is False
    assert state["outbox_created"] is False
    assert state["wallet_mutations"] == 0
    assert state["xu_charged"] == 0


def test_public_bot_contract_uses_one_profile_and_read_only_legacy_callbacks():
    assert 'f"vprofile|profile_select|{str(item.get(\'profile_key\') or \'\')}"' in BOT_SOURCE
    assert '"vprofile|profile_page|' in BOT_SOURCE
    assert '"vprofile|profile_link_toggle|' not in BOT_SOURCE
    links_keyboard = BOT_SOURCE[
        BOT_SOURCE.index("def video_scene3_profile_links_keyboard"):
        BOT_SOURCE.index("def video_scene3_profile_suggestions_text")
    ]
    assert "return video_scene3_profile_keyboard(state)" in links_keyboard
    assert '"profile_links": lambda:' in BOT_SOURCE
    assert '"profile_suggestions": lambda:' in BOT_SOURCE
    assert "for index in range(0, len(options), 2)" in BOT_SOURCE
    for legacy_action in ("profile_link_toggle", "profile_links_done", "profile_links_skip"):
        action_anchor = BOT_SOURCE.index(f'if action == "{legacy_action}":')
        action_block = BOT_SOURCE[action_anchor:].split("\n    if action ==", 1)[0]
        assert '"technical_profile", push=False' in action_block
        assert "linked_profiles=[]" in action_block
    assert "Legacy 14-profile callback" in BOT_SOURCE
    legacy_anchor = BOT_SOURCE.index("# Legacy 14-profile callback")
    legacy_block = BOT_SOURCE[legacy_anchor:].split(
        'if action == "profile_page":',
        1,
    )[0]
    assert "select_primary_profile" not in legacy_block
    assert '"technical_profile", push=False' in legacy_block


def test_profile_back_stack_and_preconfirm_side_effects_are_canonical():
    state = video_scene3_flow.default_state(
        product_type="video_ai_real",
        subject="Video căn hộ cao cấp",
    )
    state["scene_count"] = 2
    state = video_scene3_flow.select_primary_profile(
        state,
        "real_estate_place_walkthrough",
    )
    state["step"] = "profile_links"
    assert video_scene3_flow.canonical_back_step(state) == "technical_profile"
    state["step"] = "character"
    assert video_scene3_flow.canonical_back_step(state) == "content_choice"
    state["step"] = "profile_suggestions"
    assert video_scene3_flow.canonical_back_step(state) == "technical_profile"

    for key, expected in {
        "provider_called": False,
        "image_provider_called": False,
        "music_provider_calls": 0,
        "voice_provider_calls": 0,
        "files_generated": 0,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }.items():
        assert state[key] == expected
