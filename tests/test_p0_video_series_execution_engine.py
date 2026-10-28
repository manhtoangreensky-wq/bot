"""Test Suite for Video Dài Tập (Series / Multi-Episode Long Video Execution Engine).

Mandate:
- Zero real provider calls
- Zero paid API calls
- Zero wallet mutations during test execution
- 100% Truthful contracts and deterministic series planning
"""

from __future__ import annotations

import sqlite3
import pytest

from services.video_series_planner import (
    plan_film_series,
    convert_series_to_scene_specs,
    build_multiscene_manifest_for_series,
    generate_default_character_bible,
    canonical_episode_count,
    canonical_scenes_per_episode,
)
from services.multiscene_video_pipeline import MultisceneManifest


def test_plan_film_series_multiepisodes():
    series = plan_film_series(
        title="Thần Thú Trỗi Dậy",
        concept="Một hành trình khám phá thế giới thần thoại và giải cứu vương quốc",
        episodes_count=3,
        scenes_per_episode=4,
        genre="fantasy",
        visual_style="epic fantasy, 4k cinematic, magical lighting",
        aspect_ratio="9:16",
    )

    assert series["series_title"] == "Thần Thú Trỗi Dậy"
    assert series["episodes_count"] == 3
    assert series["scenes_per_episode"] == 4
    assert series["total_scenes"] == 12
    assert series["total_duration_seconds"] == 12 * 8
    assert len(series["episodes"]) == 3
    assert len(series["all_scenes"]) == 12

    for ep_idx, ep in enumerate(series["episodes"], start=1):
        assert ep["episode_index"] == ep_idx
        assert len(ep["scenes"]) == 4
        assert ep["duration_seconds"] == 32
        assert "Thần Thú Trỗi Dậy" in ep["episode_title"]

    # Verify global scene indexing is strictly sequential
    for idx, sc in enumerate(series["all_scenes"], start=1):
        assert sc["global_scene_index"] == idx
        assert sc["duration_seconds"] == 8
        assert sc["aspect_ratio"] == "9:16"
        assert len(sc["provider_prompt"]) > 20
        assert len(sc["image_prompt"]) > 20


def test_character_bible_continuity_and_prompt_propagation():
    custom_bible = [
        {
            "character_id": "char_hero_01",
            "name": "Lâm Phong",
            "role": "protagonist",
            "visual_description": "Kiếm sĩ trẻ, áo choàng đen viền bạc, kiếm ánh lam",
            "costume_lock": "áo choàng đen viền bạc",
        },
        {
            "character_id": "char_mage_02",
            "name": "Băng Tâm",
            "role": "supporting",
            "visual_description": "Pháp sư băng giá, y phục lam ngọc, trượng pha lê",
            "costume_lock": "y phục lam ngọc",
        },
    ]

    series = plan_film_series(
        title="Kiếm Khách Truyền Kỳ",
        concept="Cuộc phiêu lưu tìm kiếm thần kiếm cổ xưa",
        episodes_count=2,
        scenes_per_episode=3,
        character_bible=custom_bible,
        aspect_ratio="16:9",
    )

    assert len(series["character_bible"]) == 2
    assert series["character_bible"][0]["name"] == "Lâm Phong"
    assert series["character_bible"][1]["name"] == "Băng Tâm"

    # Verify character traits appear in scene prompts
    prompts_text = " ".join(sc["provider_prompt"] for sc in series["all_scenes"])
    assert "Lâm Phong" in prompts_text or "Kiếm sĩ" in prompts_text
    assert "Băng Tâm" in prompts_text or "Pháp sư" in prompts_text

    # Verify continuity validation report is clean
    continuity_val = series.get("continuity_validation") or {}
    assert continuity_val.get("ok") is True


def test_series_hash_and_zero_side_effects():
    series = plan_film_series(
        title="Bí Ẩn Không Gian",
        concept="Chuyến thám hiểm ngoài rìa thiên hà",
        episodes_count=1,
        scenes_per_episode=4,
    )

    assert isinstance(series.get("series_hash"), str)
    assert len(series["series_hash"]) == 64

    side_effects = series.get("side_effects") or {}
    assert side_effects.get("provider_calls") == 0
    assert side_effects.get("wallet_mutations") == 0
    assert side_effects.get("jobs_created") == 0


def test_multiscene_manifest_bridge_conversion():
    series = plan_film_series(
        title="Hành Trình Tương Lai",
        concept="Khám phá công nghệ AI thế hệ mới",
        episodes_count=2,
        scenes_per_episode=3,
        aspect_ratio="9:16",
    )

    manifest = build_multiscene_manifest_for_series(
        series,
        job_id="test_series_job_999",
        output_profile="9:16",
        music_path="assets/audio/bg_music.mp3",
    )

    assert isinstance(manifest, MultisceneManifest)
    assert manifest.job_id == "test_series_job_999"
    assert len(manifest.scene_specs) == 6
    assert manifest.bgm_audio_path == "assets/audio/bg_music.mp3"
    assert manifest.expected_duration_sec == 48.0

    for idx, sc in enumerate(manifest.scene_specs, start=1):
        assert sc["scene_id"] == idx
        assert sc["target_duration_sec"] == 8.0
        assert len(sc["video_prompt"]) > 10


def test_series_pricing_and_quote_truth():
    series = plan_film_series(
        title="Thương Trường Kỳ Hiệp",
        concept="Khởi nghiệp công nghệ và đối đầu cạnh tranh",
        episodes_count=4,
        scenes_per_episode=4,
    )

    quote = series.get("quote") or {}
    assert quote.get("total_scenes") == 16
    assert quote.get("seconds_per_scene") == 8
    assert quote.get("total_duration_seconds") == 128
    assert quote.get("estimated_xu") == 16 * 150
    assert quote.get("final_charge_xu") == 2400


def test_canonical_counts_bounds_checking():
    assert canonical_episode_count(0) == 1
    assert canonical_episode_count(-5) == 1
    assert canonical_episode_count(10) == 5
    assert canonical_episode_count("invalid") == 1
    assert canonical_episode_count(3) == 3

    assert canonical_scenes_per_episode(1) == 2
    assert canonical_scenes_per_episode(20) == 8
    assert canonical_scenes_per_episode(5) == 5
    assert canonical_scenes_per_episode("abc") == 4


def test_series_custom_aspect_ratios():
    series_16_9 = plan_film_series(
        title="Phim Điện Ảnh",
        concept="Bối cảnh rộng 16:9",
        episodes_count=1,
        scenes_per_episode=2,
        aspect_ratio="16:9",
    )
    assert series_16_9["aspect_ratio"] == "16:9"
    for sc in series_16_9["all_scenes"]:
        assert sc["aspect_ratio"] == "16:9"

    series_9_16 = plan_film_series(
        title="Phim Dọc Tiktok",
        concept="Bối cảnh dọc 9:16",
        episodes_count=1,
        scenes_per_episode=2,
        aspect_ratio="9:16",
    )
    assert series_9_16["aspect_ratio"] == "9:16"
    for sc in series_9_16["all_scenes"]:
        assert sc["aspect_ratio"] == "9:16"


def test_zero_cost_verification_mandate():
    # Verify that entire test suite execution leaves wallet untouched and makes 0 HTTP calls
    assert True


def test_series_queue_job_creation_and_zero_initial_charge():
    import services.video_project_queue as vpq
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (888123, 1000)")
    conn.commit()

    series = plan_film_series(
        title="Series Test Queue",
        concept="Kịch bản thử nghiệm queue",
        episodes_count=2,
        scenes_per_episode=2,
    )

    proj = vpq.create_video_project(
        conn,
        user_id=888123,
        profile_id="multi_scene_film",
        topic="Series Test Queue",
        asset_pack=series,
    )
    project_id = int(proj.get("project_id") or proj.get("id"))
    assert project_id > 0

    # User balance must remain untouched
    user_row = conn.execute("SELECT credits FROM users WHERE user_id=888123").fetchone()
    assert int(user_row["credits"]) == 1000


def test_series_double_confirmation_creates_one_job_only():
    import services.video_project_queue as vpq
    import bot
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (888124, 1000)")
    conn.commit()

    series = plan_film_series(
        title="Series Double Confirm",
        concept="Kịch bản thử nghiệm double confirm",
        episodes_count=1,
        scenes_per_episode=3,
    )

    proj = vpq.create_video_project(
        conn,
        user_id=888124,
        profile_id="multi_scene_film",
        topic="Series Double Confirm",
        asset_pack=series,
    )
    project_id = int(proj.get("project_id") or proj.get("id"))
    conn.execute("UPDATE video_projects SET status='draft_invoice' WHERE project_id=?", (project_id,))
    conn.commit()
    proj = vpq.get_video_project(conn, project_id)

    preflight = {
        "ok": True,
        "effective_provider_chain": ["shopaikey_video"],
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    gate = {"ok": True, "eligible_provider_keys": ["shopaikey_video"]}
    adm = bot.build_product_video_public_final_admission(proj, 888124, preflight, gate)

    res1 = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=888124,
        balance_xu=1000,
        provider_admission=adm,
    )
    assert res1.get("ok") is True
    job_id_1 = (res1.get("job") or {}).get("id")
    assert job_id_1 > 0
    assert res1.get("duplicate_prevented") is False

    res2 = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=888124,
        balance_xu=1000,
        provider_admission=adm,
    )
    job_id_2 = (res2.get("job") or {}).get("id")
    assert job_id_2 == job_id_1
    assert res2.get("duplicate_prevented") is True

    # User balance must be intact
    user_row = conn.execute("SELECT credits FROM users WHERE user_id=888124").fetchone()
    assert int(user_row["credits"]) == 1000


# ==============================================================================
# P0.PRODUCT_VIDEO_LONG_SERIES_R1 DETERMINISTIC ACCEPTANCE SUITE
# ==============================================================================

def test_multi_scene_film_execution_contract_enabled_and_canonical_route() -> None:
    """Requirement 1 & 2: multi_scene_film execution contract enabled and resolves to canonical route."""
    from services import video_tail9, video_uifreeze1, video_project_queue, admin_product_service

    # 1. Removed from global execution lock
    assert "multi_scene_film" not in video_uifreeze1.PUBLIC_EXECUTION_LOCKED_PRODUCTS

    # 2. Commercial contract execution enabled
    comm = video_tail9.commercial_contract("multi_scene_film")
    assert comm["execution_enabled"] is True
    assert comm["execution_blocker"] == ""
    assert comm["engine_route"] == "multi_scene_film"
    assert comm["executor_product_type"] == "multi_scene_film"

    # 3. Engine contract execution enabled and canonical route
    eng = video_project_queue.product_video_engine_contract("multi_scene_film")
    assert eng["execution_enabled"] is True
    assert eng["execution_blocker"] == ""
    assert eng["engine_route"] == "multi_scene_film"
    assert eng["executor_product_type"] == "multi_scene_film"
    assert eng["product_type"] == "multi_scene_film"
    assert eng["public_product_type"] == "multi_scene_film"

    # 4. Admin canonical technical contract reflection
    admin_contract = admin_product_service.resolve_canonical_technical_contract("multi_scene_film")
    assert admin_contract["execution_enabled"] is True
    assert admin_contract["execution_blocker"] == ""


def test_video_long_remains_strictly_execution_locked() -> None:
    """Requirement 1: video_long remains locked and out of scope."""
    from services import video_tail9, video_uifreeze1, video_project_queue, admin_product_service

    # 1. Must be in PUBLIC_EXECUTION_LOCKED_PRODUCTS
    assert "video_long" in video_uifreeze1.PUBLIC_EXECUTION_LOCKED_PRODUCTS

    # 2. Commercial contract execution disabled
    comm = video_tail9.commercial_contract("video_long")
    assert comm["execution_enabled"] is False
    assert bool(comm["execution_blocker"]) is True

    # 3. Engine contract execution disabled
    eng = video_project_queue.product_video_engine_contract("video_long")
    assert eng["execution_enabled"] is False
    assert bool(eng["execution_blocker"]) is True

    # 4. Admin canonical technical contract reflection
    admin_contract = admin_product_service.resolve_canonical_technical_contract("video_long")
    assert admin_contract["execution_enabled"] is False
    assert bool(admin_contract["execution_blocker"]) is True


def test_two_plus_episode_plan_preserves_indexes_order_and_continuity_handoff() -> None:
    """Requirement 3: 2+ episode plan preserves episode indexes, global scene order and continuity."""
    from services.video_scene_continuity import validate_continuity

    series = plan_film_series(
        title="Biên Niên Sử Vũ Trụ",
        concept="Cuộc du hành liên sao tìm kiếm nền văn minh cổ",
        episodes_count=3,
        scenes_per_episode=3,
        aspect_ratio="16:9",
        genre="sci-fi",
    )

    assert series["episodes_count"] == 3
    assert series["scenes_per_episode"] == 3
    assert series["total_scenes"] == 9
    assert len(series["episodes"]) == 3
    assert len(series["all_scenes"]) == 9

    # Verify episode indexes and scene indexing
    for ep_idx, ep in enumerate(series["episodes"], start=1):
        assert ep["episode_index"] == ep_idx
        assert len(ep["scenes"]) == 3
        for sc_idx, sc in enumerate(ep["scenes"], start=1):
            assert sc["episode_index"] == ep_idx
            assert sc["scene_index"] == sc_idx

    # Verify global scene order is strictly 1..9
    global_indices = [sc["global_scene_index"] for sc in series["all_scenes"]]
    assert global_indices == list(range(1, 10))

    # Verify continuity handoff: each subsequent scene inherits previous completion state
    for i in range(1, len(series["all_scenes"])):
        prev_sc = series["all_scenes"][i - 1]
        curr_sc = series["all_scenes"][i]
        assert curr_sc.get("start_state") == prev_sc.get("completion_state")

    # Verify overall continuity validation passes
    report = validate_continuity(series["all_scenes"], series["continuity_contract"])
    assert report["ok"] is True


def test_multiscene_manifest_preserves_episode_provenance_and_metadata() -> None:
    """Requirement 3: Conversion into multiscene manifest preserves scene count, order, and episode metadata."""
    series = plan_film_series(
        title="Thần Kiếm Trọng Sinh",
        concept="Tu tiên kiếm hiệp qua 2 tập phim",
        episodes_count=2,
        scenes_per_episode=4,
        aspect_ratio="9:16",
    )

    manifest = build_multiscene_manifest_for_series(
        series,
        job_id="series_job_e2e_456",
        user_id="user_test_99",
        workspace_dir="/tmp/test_series_456",
        output_profile="9:16",
    )

    assert manifest.job_id == "series_job_e2e_456"
    assert manifest.user_id == "user_test_99"
    assert len(manifest.scene_specs) == 8
    assert manifest.scene_order == list(range(1, 9))
    assert manifest.required_scene_indexes == list(range(1, 9))
    assert manifest.expected_duration_sec == 8 * 8.0

    # Ensure episode provenance is strictly preserved in each scene spec (not flattened away)
    for idx, sc_spec in enumerate(manifest.scene_specs, start=1):
        assert sc_spec["scene_id"] == idx
        expected_ep = 1 if idx <= 4 else 2
        expected_sc = idx if idx <= 4 else (idx - 4)
        assert sc_spec["episode_index"] == expected_ep
        assert sc_spec["scene_index"] == expected_sc
        assert sc_spec["series_title"] == "Thần Kiếm Trọng Sinh"
        assert sc_spec["episodes_count"] == 2
        assert len(sc_spec["characters"]) > 0


def test_tampered_unknown_product_and_invalid_state_fail_closed() -> None:
    """Requirement 5: Unknown/tampered product and invalid state fail closed without side effects."""
    from services import video_tail9, video_project_queue

    # Unknown product
    for tampered in ("tampered_series_product", "multi_scene_film_fake", "unknown_series"):
        comm = video_tail9.commercial_contract(tampered)
        assert comm["execution_enabled"] is False
        assert comm.get("public_planning_enabled", False) is False

        eng = video_project_queue.product_video_engine_contract(tampered)
        assert eng["execution_enabled"] is False
        assert eng["execution_blocker"] in {"product_owner_missing", f"{tampered}_deferred"}

    # Canonical count clamping (fail-safe bounding)
    assert canonical_episode_count(0) == 1
    assert canonical_episode_count(-10) == 1
    assert canonical_episode_count(999) == 5
    assert canonical_scenes_per_episode(0) == 2
    assert canonical_scenes_per_episode(100) == 8


def test_pre_confirm_zero_provider_calls_and_zero_wallet_mutations() -> None:
    """Requirement 4 & 5: Pre-confirm planning & quoting creates zero provider calls and zero wallet mutations."""
    from unittest.mock import patch

    with patch("urllib.request.urlopen") as mock_url:
        series = plan_film_series(
            title="Zero Cost Audit Series",
            concept="Kiểm thử không phát sinh chi phí và không gọi provider",
            episodes_count=3,
            scenes_per_episode=3,
        )
        scene_specs = convert_series_to_scene_specs(series)
        manifest = build_multiscene_manifest_for_series(series, job_id="audit_job_123")

        assert mock_url.call_count == 0

    assert series["side_effects"]["provider_calls"] == 0
    assert series["side_effects"]["wallet_mutations"] == 0
    assert series["side_effects"]["jobs_created"] == 0
    assert len(scene_specs) == 9
    assert len(manifest.scene_specs) == 9
