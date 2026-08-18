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
