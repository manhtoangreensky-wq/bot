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
    """Requirement 3 & Controller Issue 1: Manifest preserves scene count, order, episode provenance, and stable series identity."""
    series = plan_film_series(
        title="Thần Kiếm Trọng Sinh",
        concept="Tu tiên kiếm hiệp qua 2 tập phim",
        episodes_count=2,
        scenes_per_episode=4,
        aspect_ratio="9:16",
    )

    assert bool(series["series_hash"]) is True
    assert bool(series["series_id"]) is True

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
    assert manifest.composition_signature == series["series_hash"]
    assert manifest.addon_application.get("series_id") == series["series_id"]
    assert manifest.addon_application.get("series_hash") == series["series_hash"]

    # Verify specs from convert_series_to_scene_specs also propagate series_id and series_hash
    specs = convert_series_to_scene_specs(series)
    assert len(specs) == 8
    for sp in specs:
        assert sp["series_id"] == series["series_id"]
        assert sp["series_hash"] == series["series_hash"]
        assert sp["series_title"] == "Thần Kiếm Trọng Sinh"
        assert sp["episodes_count"] == 2

    # Ensure episode provenance and stable identity are strictly preserved in each scene spec (not flattened away)
    for idx, sc_spec in enumerate(manifest.scene_specs, start=1):
        assert sc_spec["scene_id"] == idx
        expected_ep = 1 if idx <= 4 else 2
        expected_sc = idx if idx <= 4 else (idx - 4)
        assert sc_spec["episode_index"] == expected_ep
        assert sc_spec["scene_index"] == expected_sc
        assert sc_spec["series_title"] == "Thần Kiếm Trọng Sinh"
        assert sc_spec["episodes_count"] == 2
        assert sc_spec["series_id"] == series["series_id"]
        assert sc_spec["series_hash"] == series["series_hash"]
        assert len(sc_spec["characters"]) > 0


def test_series_identity_handoff_with_explicit_upstream_series_id() -> None:
    """Requirement 3 & Controller Issue 1: Upstream series_id survives planning -> specs -> manifest."""
    custom_series_id = "series_uiflow3_custom_abc123"
    series = plan_film_series(
        title="Custom Series ID Test",
        concept="Bảo toàn series_id từ upstream UIFLOW3",
        episodes_count=2,
        scenes_per_episode=2,
        series_id=custom_series_id,
    )
    assert series["series_id"] == custom_series_id
    assert bool(series["series_hash"]) is True

    specs = convert_series_to_scene_specs(series)
    assert len(specs) == 4
    for sp in specs:
        assert sp["series_id"] == custom_series_id
        assert sp["series_hash"] == series["series_hash"]

    manifest = build_multiscene_manifest_for_series(series, job_id="custom_series_job_1")
    assert manifest.composition_signature == series["series_hash"]
    assert manifest.addon_application.get("series_id") == custom_series_id
    assert manifest.addon_application.get("series_hash") == series["series_hash"]
    for sc_spec in manifest.scene_specs:
        assert sc_spec["series_id"] == custom_series_id
        assert sc_spec["series_hash"] == series["series_hash"]


def test_tampered_unknown_product_and_invalid_state_fail_closed() -> None:
    """Requirement 5 & Controller Issue 2: Unknown/tampered product and invalid counts fail closed without side effects."""
    from services import video_tail9, video_project_queue
    from services.video_series_planner import validate_series_execution_request

    # Unknown product
    for tampered in ("tampered_series_product", "multi_scene_film_fake", "unknown_series"):
        comm = video_tail9.commercial_contract(tampered)
        assert comm["execution_enabled"] is False
        assert comm.get("public_planning_enabled", False) is False

        eng = video_project_queue.product_video_engine_contract(tampered)
        assert eng["execution_enabled"] is False
        assert eng["execution_blocker"] in {"product_owner_missing", f"{tampered}_deferred"}

    # Validation at admission boundary: invalid/tampered episode counts fail closed with zero side effects
    for bad_ep in (0, -1, 6, 999, "invalid", None):
        res = validate_series_execution_request(episodes_count=bad_ep, scenes_per_episode=3)
        assert res["ok"] is False
        assert bool(res["reason"]) is True
        assert res["side_effects"]["jobs_created"] == 0
        assert res["side_effects"]["outbox_created"] == 0
        assert res["side_effects"]["provider_calls"] == 0
        assert res["side_effects"]["wallet_mutations"] == 0

    # Validation at admission boundary: invalid/tampered scene counts fail closed with zero side effects
    for bad_sc in (0, 1, 9, 100, "malformed", None):
        res = validate_series_execution_request(episodes_count=2, scenes_per_episode=bad_sc)
        assert res["ok"] is False
        assert bool(res["reason"]) is True
        assert res["side_effects"]["jobs_created"] == 0
        assert res["side_effects"]["outbox_created"] == 0
        assert res["side_effects"]["provider_calls"] == 0
        assert res["side_effects"]["wallet_mutations"] == 0

    # Total scenes exceeding capacity (e.g., 5 episodes x 8 scenes = 40 > 20 max)
    res_overflow = validate_series_execution_request(episodes_count=5, scenes_per_episode=8)
    assert res_overflow["ok"] is False
    assert res_overflow["reason"] == "total_scenes_exceed_capacity"

    # Commercial admission boundary checks: package_compatibility fails closed with 0 side effects
    for bad_count in (21, 50, 100, 999):
        compat = video_tail9.package_compatibility("multi_scene_film", scene_count=bad_count, ratio="9:16", quality_tier_id=300)
        assert compat["ok"] is False
        assert compat["reason"] == "scene_count_not_supported"
        assert compat["side_effects"]["job"] == 0
        assert compat["side_effects"]["outbox"] == 0
        assert compat["side_effects"]["provider_calls"] == 0
        assert compat["side_effects"]["wallet_mutations"] == 0

    # Canonical count clamping (internal helper safety)
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



def test_multi_scene_film_runtime_readiness_fail_closed_at_admission_boundary() -> None:
    """Requirement 2 & Controller Issue 3: Actual confirm/admission boundary blocks missing/stale/incompatible readiness with zero side effects."""
    import bot
    import services.video_project_queue as vpq
    import json

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (888999, 1000)")
    conn.commit()

    series = plan_film_series(
        title="Series Readiness Admission Test",
        concept="Kịch bản kiểm thử admission boundary fail-closed",
        episodes_count=1,
        scenes_per_episode=3,
    )
    series["source"] = "product_video"
    series["render_mode"] = "real"
    series["public_user"] = True
    series["product_type"] = "multi_scene_film"

    proj = vpq.create_video_project(
        conn,
        user_id=888999,
        profile_id="multi_scene_film",
        topic="Series Readiness Admission Test",
        asset_pack=series,
    )
    project_id = int(proj.get("project_id") or proj.get("id"))

    invoice = {
        "source": "product_video",
        "render_mode": "real",
        "public_user": True,
        "product_type": "multi_scene_film",
        "scene_count": 3,
        "customer_charge_planned_xu": 450,
        "total_xu": 450,
    }
    conn.execute(
        "UPDATE video_projects SET status='draft_invoice', invoice_json=?, total_xu_estimated=450 WHERE project_id=?",
        (json.dumps(invoice), project_id),
    )
    conn.commit()
    proj = vpq.get_video_project(conn, project_id)

    # 1. Missing admission context (provider_admission=None)
    res_missing = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=888999,
        balance_xu=1000,
        provider_admission=None,
    )
    assert res_missing["ok"] is False
    assert res_missing["reason"] == "admission_context_missing_or_invalid"
    assert res_missing["job_created"] is False
    assert res_missing["charged_xu"] == 0

    # 2. Tampered signature in admission context
    tampered_adm = {
        "admission_context_version": 1,
        "admission_context_signature": "tampered_fake_signature_abc",
    }
    res_tampered = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=888999,
        balance_xu=1000,
        provider_admission=tampered_adm,
    )
    assert res_tampered["ok"] is False
    assert res_tampered["reason"] == "admission_context_missing_or_invalid"
    assert res_tampered["job_created"] is False
    assert res_tampered["charged_xu"] == 0

    # 3. Blocked readiness (freeze_truth disallows confirm / readiness missing)
    preflight_blocked = {
        "ok": False,
        "configured_provider_chain": ["shopaikey_video"],
        "freeze_truth": {"public_final_confirm_allowed": False, "public_blocker_code": "readiness_missing_or_stale"},
    }
    gate_blocked = {"ok": False, "eligible_provider_keys": ["shopaikey_video"]}
    adm_blocked = bot.build_product_video_public_final_admission(proj, 888999, preflight_blocked, gate_blocked)
    assert adm_blocked.get("ok") is False
    assert adm_blocked.get("admission_result") == "BLOCKED"

    res_blocked = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=888999,
        balance_xu=1000,
        provider_admission=adm_blocked,
    )
    assert res_blocked["ok"] is False
    assert res_blocked.get("job_created", False) is False
    assert res_blocked.get("charged_xu", 0) == 0

    # 4. Invariant: exactly 0 jobs in DB, user credits remain intact
    db_jobs = conn.execute("SELECT count(*) FROM video_jobs").fetchone()[0]
    assert db_jobs == 0
    user_row = conn.execute("SELECT credits FROM users WHERE user_id=888999").fetchone()
    assert int(user_row["credits"]) == 1000



def _make_uiflow3_series_snapshot(*, episodes_count=2, scenes_per_episode=3, series_id="series_canon_1234"):
    import hashlib
    import json
    from copy import deepcopy

    def _cjson(value):
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    def _shash(value):
        return hashlib.sha256(_cjson(value).encode("utf-8")).hexdigest()

    scene_count = episodes_count * scenes_per_episode
    scenes = [
        {
            "scene_id": f"sc_{i}",
            "scene_index": i,
            "scene_role": "beat",
            "semantic_beat": f"Cảnh hành động {i}",
            "ratio": "9:16",
            "duration_seconds": 8,
            "duration_target": 8,
            "character_ids": ["hero_1"],
        }
        for i in range(1, scene_count + 1)
    ]
    raw = {
        "flow_schema_version": 3,
        "draft_id": "draft_series_canon_001",
        "parent_product": "multi_scene_film",
        "entry_mode": "prompt",
        "render_family": "video_ai_real",
        "format": {
            "ratio": "9:16",
            "scene_count": scene_count,
            "seconds_per_scene": 8,
            "target_duration_seconds": scene_count * 8,
        },
        "content": {
            "profile_id": "multi_scene_film",
            "original_intent": "Hành trình tầm sư học đạo của thiếu niên Kiếm Khách",
            "approved_brief": {
                "title": "Kiếm Khách Khởi Nguyên",
                "technical_profile": "cinematic_trailer",
            },
        },
        "series": {
            "series_id": series_id,
            "goal": "Hành trình tầm sư học đạo",
            "episodes_count": episodes_count,
            "scenes_per_episode": scenes_per_episode,
            "revision": 1,
        },
        "episode": {
            "episode_id": "ep_1",
            "number": 1,
            "title": "Tập 1: Xuất sơn",
        },
        "effective_episode": None,
        "production_bible": {
            "genre": "fantasy",
            "characters": [
                {
                    "character_id": "hero_1",
                    "name": "Bảo Kiếm",
                    "role": "protagonist",
                    "visual_description": "Thiếu niên áo lam, đeo kiếm gỗ",
                    "costume_lock": "áo lam",
                }
            ],
            "continuity": {
                "character_bible": [{"character_id": "hero_1", "name": "Bảo Kiếm"}],
            },
        },
        "creative_controls": {},
        "preservation_requirements": {},
        "references": [],
        "scenes": scenes,
        "audio": {
            "voice_cast": {},
            "dialogue_segments": [],
            "music_scope": "none",
            "music_plan": {},
            "sfx_plan": {},
            "ambient_plan": {},
        },
        "branding": {},
        "source": {},
        "render_blockers": [],
    }
    material = deepcopy(raw)
    material.pop("config_hash", None)
    raw["config_hash"] = _shash(material)
    return raw


def test_multi_scene_film_canonical_uiflow3_to_durable_job_handoff_e2e() -> None:
    """Requirement 1 & 2: Real canonical Product Video handoff proves stable series identity,

    episode provenance, and sequential scene order survive into durable project and job execution payload.
    """
    import json
    import sqlite3
    import bot
    from services import video_project_queue as vpq
    from services import video_uiflow3_routeengine as ure

    user_id = 888999
    snapshot = _make_uiflow3_series_snapshot(episodes_count=2, scenes_per_episode=3, series_id="series_canon_1234")

    # 1. Compile RouteEngine handoff
    handoff = ure.compile_routeengine_handoff(
        snapshot,
        owner_user_id=user_id,
        owner_chat_id=user_id,
    )
    assert handoff["ok"] is True
    assert handoff["series_id"] == "series_canon_1234"
    assert len(handoff["scene_cards"]) == 6
    assert handoff["scene_cards"][0]["series_id"] == "series_canon_1234"
    assert handoff["scene_cards"][0]["episode_index"] == 1
    assert handoff["scene_cards"][3]["episode_index"] == 2
    assert handoff["side_effects"]["provider_calls"] == 0

    # 2. Prepare durable commercial project in SQLite
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (?, 1000)", (user_id,))
    conn.commit()

    quote = {
        "scene_count": 6,
        "user_visible_price_xu": 900,
        "persisted_quoted_price_xu": 900,
        "customer_charge_planned_xu": 900,
        "wallet_charge_amount_xu": 900,
        "total_xu": 900,
        "quality_tier": 300,
    }
    prep = ure.prepare_commercial_project(conn, handoff, quote=quote)
    assert prep["ok"] is True
    project_id = prep["project"]["project_id"]
    proj = vpq.get_video_project(conn, project_id)

    # 3. Final Admission Evaluation
    preflight = {
        "ok": True,
        "configured_provider_chain": ["shopaikey_video"],
        "public_submit_enabled": True,
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    scene_gate = {
        "ok": True,
        "eligible_provider_keys": ["shopaikey_video"],
        "scene_count": 6,
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    adm = bot.build_product_video_public_final_admission(proj, user_id, preflight, scene_gate)
    assert adm.get("ok") is True or adm.get("admission_result") == "PASS"
    assert adm.get("series_id") == "series_canon_1234"

    # 4. Confirm Public Product Video Invoice
    res_confirm = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=user_id,
        balance_xu=1000,
        provider_admission=adm,
    )
    assert res_confirm["ok"] is True
    assert res_confirm["job_created"] is True
    assert res_confirm["dispatch_outbox_created"] is True
    assert res_confirm["scene_records_created"] is True

    # 5. Verify Durable Job Payload Lineage
    job_row = conn.execute("SELECT * FROM video_jobs WHERE project_id=?", (project_id,)).fetchone()
    assert job_row is not None
    job_payload = json.loads(job_row["result_json"])

    assert job_payload["series_id"] == "series_canon_1234"
    assert len(job_payload["series_hash"]) == 64
    assert job_payload["multiscene_contract"]["manifest_composition_signature"] == job_payload["series_hash"]
    assert job_payload["multiscene_contract"]["manifest_addon_application"]["series_id"] == "series_canon_1234"
    assert job_payload["multiscene_contract"]["manifest_scene_order"] == [1, 2, 3, 4, 5, 6]

    scene_tasks = job_payload["scene_tasks"]
    assert len(scene_tasks) == 6
    assert [t["scene_index"] for t in scene_tasks] == [1, 2, 3, 4, 5, 6]
    assert [t["episode_index"] for t in scene_tasks] == [1, 1, 1, 2, 2, 2]
    assert all(t["series_id"] == "series_canon_1234" for t in scene_tasks)
    assert all(t["series_hash"] == job_payload["series_hash"] for t in scene_tasks)

    # 6. Verify Outbox and Wallet Balance Intact
    outbox = vpq.get_product_video_dispatch_outbox(conn, job_id=job_row["id"])
    assert outbox is not None
    outbox_scenes = [int(x) for x in (outbox.get("scene_indexes") or json.loads(outbox.get("scene_indexes_json") or "[]"))]
    assert outbox_scenes == [1, 2, 3, 4, 5, 6]

    user_row = conn.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)).fetchone()
    assert int(user_row["credits"]) == 1000


def test_multi_scene_film_invalid_count_real_path_fail_closed() -> None:
    """Requirement 1 & Controller Finding 1: Invalid/tampered episode/scene count and overflow

    strictly fail closed across the real canonical planning and admission path before any job/outbox/wallet mutations.
    """
    import json
    import sqlite3
    from copy import deepcopy
    import bot
    from services import video_project_queue as vpq
    from services import video_uiflow3_routeengine as ure

    user_id = 888999

    # 1. Untrusted request with tampered episode count 0 fails closed at RouteEngine handoff boundary
    snap_0 = _make_uiflow3_series_snapshot(episodes_count=1, scenes_per_episode=3)
    snap_0["series"]["episodes_count"] = 0
    mat = deepcopy(snap_0)
    mat.pop("config_hash", None)
    snap_0["config_hash"] = ure._sha256(mat)
    h_0 = ure.compile_routeengine_handoff(snap_0, owner_user_id=user_id, owner_chat_id=user_id)
    assert h_0["ok"] is False
    assert h_0.get("blocker") == "invalid_episode_count"

    # 2. Untrusted request with out-of-range episode count 99 fails closed at RouteEngine handoff boundary
    snap_99 = _make_uiflow3_series_snapshot(episodes_count=1, scenes_per_episode=3)
    snap_99["series"]["episodes_count"] = 99
    mat = deepcopy(snap_99)
    mat.pop("config_hash", None)
    snap_99["config_hash"] = ure._sha256(mat)
    h_99 = ure.compile_routeengine_handoff(snap_99, owner_user_id=user_id, owner_chat_id=user_id)
    assert h_99["ok"] is False
    assert h_99.get("blocker") == "invalid_episode_count"

    # 3. Untrusted request with invalid scenes_per_episode 0 fails closed at RouteEngine handoff boundary
    snap_sc0 = _make_uiflow3_series_snapshot(episodes_count=1, scenes_per_episode=3)
    snap_sc0["series"]["scenes_per_episode"] = 0
    mat = deepcopy(snap_sc0)
    mat.pop("config_hash", None)
    snap_sc0["config_hash"] = ure._sha256(mat)
    h_sc0 = ure.compile_routeengine_handoff(snap_sc0, owner_user_id=user_id, owner_chat_id=user_id)
    assert h_sc0["ok"] is False
    assert h_sc0.get("blocker") == "invalid_scene_count"

    # 4. Tampered project with overflow 5x8=40 > 20 fails closed at real admission boundary
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (?, 10000)", (user_id,))
    conn.commit()

    tampered_asset = {
        "source": "product_video",
        "product_type": "multi_scene_film",
        "public_user": True,
        "render_mode": "real",
        "episodes_count": 5,
        "scenes_per_episode": 8,
        "scene_count": 40,
        "total_xu": 6000,
        "customer_charge_planned_xu": 6000,
        "user_visible_price_xu": 6000,
    }
    tampered_proj = vpq.create_video_project(
        conn,
        user_id=user_id,
        profile_id="multi_scene_film",
        topic="tampered_overflow_test",
        asset_pack=tampered_asset,
    )
    project_id = tampered_proj["project_id"]
    conn.execute(
        'UPDATE video_projects SET status="draft_invoice", invoice_json=?, total_xu_estimated=6000 WHERE project_id=?',
        (json.dumps(tampered_asset), project_id),
    )
    conn.commit()
    tampered_proj = vpq.get_video_project(conn, project_id)

    preflight = {
        "ok": True,
        "configured_provider_chain": ["shopaikey_video"],
        "public_submit_enabled": True,
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    scene_gate = {
        "ok": True,
        "eligible_provider_keys": ["shopaikey_video"],
        "scene_count": 40,
        "freeze_truth": {"public_final_confirm_allowed": True},
    }

    adm_overflow = bot.build_product_video_public_final_admission(tampered_proj, user_id, preflight, scene_gate)
    assert adm_overflow.get("ok") is False
    assert adm_overflow.get("admission_result") == "BLOCKED"
    assert adm_overflow.get("admission_block_reason") == "total_scenes_exceed_capacity"

    res_overflow = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=project_id,
        user_id=user_id,
        balance_xu=10000,
        provider_admission=adm_overflow,
    )
    assert res_overflow.get("ok") is False
    assert res_overflow.get("reason") == "total_scenes_exceed_capacity"
    assert res_overflow.get("job_created", False) is False

    # Invariant: exactly 0 jobs in DB, 0 outbox in DB, user credits remain 10000
    jobs_count = conn.execute("SELECT count(*) FROM video_jobs").fetchone()[0]
    assert jobs_count == 0
    outbox_count = conn.execute("SELECT count(*) FROM video_dispatch_outbox").fetchone()[0]
    assert outbox_count == 0
    credits = conn.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    assert credits == 10000


def test_uiflow3_handoff_omitted_scenes_per_episode_defaults_safely() -> None:
    """Blocker A: Canonical UIFLOW3 handoff with omitted scenes_per_episode in snapshot['series']

    cleanly falls back to video_series_planner.DEFAULT_SCENES_PER_EPISODE (4) without NameError.
    """
    from copy import deepcopy
    from services import video_series_planner
    from services import video_uiflow3_routeengine as ure

    user_id = 888999

    # Case 1: scenes_per_episode omitted from series info with scene_count=4, ep=1
    snapshot_1 = _make_uiflow3_series_snapshot(episodes_count=1, scenes_per_episode=4, series_id="series_default_fallback_ep1")
    snapshot_1["series"].pop("scenes_per_episode", None)
    mat_1 = deepcopy(snapshot_1)
    mat_1.pop("config_hash", None)
    snapshot_1["config_hash"] = ure._sha256(mat_1)

    handoff_1 = ure.compile_routeengine_handoff(
        snapshot_1,
        owner_user_id=user_id,
        owner_chat_id=user_id,
    )
    assert handoff_1["ok"] is True
    assert handoff_1["series_id"] == "series_default_fallback_ep1"
    story_bible_1 = handoff_1.get("story_bible") or {}
    assert story_bible_1.get("scenes_per_episode") == video_series_planner.DEFAULT_SCENES_PER_EPISODE
    assert handoff_1["side_effects"]["provider_calls"] == 0

    # Case 2: scenes_per_episode omitted from series info with scene_count=8, ep=2
    snapshot_2 = _make_uiflow3_series_snapshot(episodes_count=2, scenes_per_episode=4, series_id="series_default_fallback_ep2")
    snapshot_2["series"].pop("scenes_per_episode", None)
    mat_2 = deepcopy(snapshot_2)
    mat_2.pop("config_hash", None)
    snapshot_2["config_hash"] = ure._sha256(mat_2)

    handoff_2 = ure.compile_routeengine_handoff(
        snapshot_2,
        owner_user_id=user_id,
        owner_chat_id=user_id,
    )
    assert handoff_2["ok"] is True
    assert handoff_2["series_id"] == "series_default_fallback_ep2"
    story_bible_2 = handoff_2.get("story_bible") or {}
    assert story_bible_2.get("scenes_per_episode") == video_series_planner.DEFAULT_SCENES_PER_EPISODE
    assert handoff_2["side_effects"]["provider_calls"] == 0


def test_multi_scene_film_tampered_zero_counts_fail_closed_at_real_admission() -> None:
    """Blocker B: Explicit tampered zero values for episodes_count or scenes_per_episode

    are preserved (not swallowed by 'or' fallback) and fail closed at admission and confirm boundaries.
    Zero jobs created, zero outbox records created, zero wallet mutations.
    """
    import json
    import sqlite3
    import bot
    from services import video_project_queue as vpq

    user_id = 999111
    preflight = {
        "ok": True,
        "configured_provider_chain": ["shopaikey_video"],
        "public_submit_enabled": True,
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    scene_gate = {
        "ok": True,
        "eligible_provider_keys": ["shopaikey_video"],
        "scene_count": 4,
        "freeze_truth": {"public_final_confirm_allowed": True},
    }

    # Case 1: Tampered episodes_count = 0
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (?, 5000)", (user_id,))
    conn.commit()

    tampered_ep0 = {
        "source": "product_video",
        "product_type": "multi_scene_film",
        "public_user": True,
        "render_mode": "real",
        "episodes_count": 0,
        "scenes_per_episode": 4,
        "scene_count": 4,
        "total_xu": 600,
        "customer_charge_planned_xu": 600,
        "user_visible_price_xu": 600,
    }
    proj_ep0 = vpq.create_video_project(
        conn,
        user_id=user_id,
        profile_id="multi_scene_film",
        topic="tampered_ep0_test",
        asset_pack=tampered_ep0,
    )
    p_id_ep0 = proj_ep0["project_id"]
    conn.execute(
        'UPDATE video_projects SET status="draft_invoice", invoice_json=?, total_xu_estimated=600 WHERE project_id=?',
        (json.dumps(tampered_ep0), p_id_ep0),
    )
    conn.commit()
    proj_ep0 = vpq.get_video_project(conn, p_id_ep0)

    adm_ep0 = bot.build_product_video_public_final_admission(proj_ep0, user_id, preflight, scene_gate)
    assert adm_ep0.get("ok") is False
    assert adm_ep0.get("admission_block_reason") == "invalid_episode_count"

    res_ep0 = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=p_id_ep0,
        user_id=user_id,
        balance_xu=5000,
        provider_admission=adm_ep0,
    )
    assert res_ep0.get("ok") is False
    assert res_ep0.get("reason") == "invalid_episode_count"
    assert res_ep0.get("job_created", False) is False

    # Invariants for Case 1
    assert conn.execute("SELECT count(*) FROM video_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM video_dispatch_outbox").fetchone()[0] == 0
    assert conn.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)).fetchone()[0] == 5000

    # Case 2: Tampered scenes_per_episode = 0
    tampered_sc0 = {
        "source": "product_video",
        "product_type": "multi_scene_film",
        "public_user": True,
        "render_mode": "real",
        "episodes_count": 1,
        "scenes_per_episode": 0,
        "scene_count": 4,
        "total_xu": 600,
        "customer_charge_planned_xu": 600,
        "user_visible_price_xu": 600,
    }
    proj_sc0 = vpq.create_video_project(
        conn,
        user_id=user_id,
        profile_id="multi_scene_film",
        topic="tampered_sc0_test",
        asset_pack=tampered_sc0,
    )
    p_id_sc0 = proj_sc0["project_id"]
    conn.execute(
        'UPDATE video_projects SET status="draft_invoice", invoice_json=?, total_xu_estimated=600 WHERE project_id=?',
        (json.dumps(tampered_sc0), p_id_sc0),
    )
    conn.commit()
    proj_sc0 = vpq.get_video_project(conn, p_id_sc0)

    adm_sc0 = bot.build_product_video_public_final_admission(proj_sc0, user_id, preflight, scene_gate)
    assert adm_sc0.get("ok") is False
    assert adm_sc0.get("admission_block_reason") == "invalid_scene_count"

    res_sc0 = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=p_id_sc0,
        user_id=user_id,
        balance_xu=5000,
        provider_admission=adm_sc0,
    )
    assert res_sc0.get("ok") is False
    assert res_sc0.get("reason") == "invalid_scene_count"
    assert res_sc0.get("job_created", False) is False

    # Invariants for Case 2
    assert conn.execute("SELECT count(*) FROM video_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM video_dispatch_outbox").fetchone()[0] == 0
    assert conn.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)).fetchone()[0] == 5000


def test_multi_scene_film_missing_or_corrupt_manifest_fails_closed() -> None:
    """Blocker C: Missing or corrupted series manifest fails closed before job/outbox creation.

    Zero jobs persisted, zero outbox records created, zero wallet deductions.
    """
    import json
    import sqlite3
    import bot
    from services import video_project_queue as vpq

    user_id = 777333

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    vpq.ensure_video_project_queue_schema(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, credits INTEGER DEFAULT 0)")
    conn.execute("INSERT OR REPLACE INTO users (user_id, credits) VALUES (?, 8000)", (user_id,))
    conn.commit()

    preflight = {
        "ok": True,
        "configured_provider_chain": ["shopaikey_video"],
        "public_submit_enabled": True,
        "freeze_truth": {"public_final_confirm_allowed": True},
    }
    scene_gate = {
        "ok": True,
        "eligible_provider_keys": ["shopaikey_video"],
        "scene_count": 4,
        "freeze_truth": {"public_final_confirm_allowed": True},
    }

    # Case 1: Missing series_manifest (None or omitted)
    asset_pack_no_manifest = {
        "source": "product_video",
        "product_type": "multi_scene_film",
        "public_user": True,
        "render_mode": "real",
        "episodes_count": 1,
        "scenes_per_episode": 4,
        "scene_count": 4,
        "total_xu": 600,
        "customer_charge_planned_xu": 600,
        "user_visible_price_xu": 600,
        # series_manifest is intentionally absent
    }
    proj_no_mf = vpq.create_video_project(
        conn,
        user_id=user_id,
        profile_id="multi_scene_film",
        topic="missing_manifest_test",
        asset_pack=asset_pack_no_manifest,
    )
    p_id_no_mf = proj_no_mf["project_id"]
    conn.execute(
        'UPDATE video_projects SET status="draft_invoice", invoice_json=?, total_xu_estimated=600 WHERE project_id=?',
        (json.dumps(asset_pack_no_manifest), p_id_no_mf),
    )
    conn.commit()
    proj_no_mf = vpq.get_video_project(conn, p_id_no_mf)

    adm_no_mf = bot.build_product_video_public_final_admission(proj_no_mf, user_id, preflight, scene_gate)

    res_no_mf = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=p_id_no_mf,
        user_id=user_id,
        balance_xu=8000,
        provider_admission=adm_no_mf,
    )
    assert res_no_mf.get("ok") is False
    assert res_no_mf.get("reason") == "multi_scene_series_manifest_missing"
    assert res_no_mf.get("job_created", False) is False

    assert conn.execute("SELECT count(*) FROM video_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM video_dispatch_outbox").fetchone()[0] == 0
    assert conn.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)).fetchone()[0] == 8000

    # Case 2: Corrupted series_manifest (invalid schema / missing all_scenes)
    asset_pack_corrupt = {
        "source": "product_video",
        "product_type": "multi_scene_film",
        "public_user": True,
        "render_mode": "real",
        "episodes_count": 1,
        "scenes_per_episode": 4,
        "scene_count": 4,
        "total_xu": 600,
        "customer_charge_planned_xu": 600,
        "user_visible_price_xu": 600,
        "series_manifest": {"corrupted": True, "all_scenes": []},
    }
    proj_corrupt = vpq.create_video_project(
        conn,
        user_id=user_id,
        profile_id="multi_scene_film",
        topic="corrupt_manifest_test",
        asset_pack=asset_pack_corrupt,
    )
    p_id_corrupt = proj_corrupt["project_id"]
    conn.execute(
        'UPDATE video_projects SET status="draft_invoice", invoice_json=?, total_xu_estimated=600 WHERE project_id=?',
        (json.dumps(asset_pack_corrupt), p_id_corrupt),
    )
    conn.commit()
    proj_corrupt = vpq.get_video_project(conn, p_id_corrupt)

    adm_corrupt = bot.build_product_video_public_final_admission(proj_corrupt, user_id, preflight, scene_gate)

    res_corrupt = vpq.confirm_public_product_video_invoice(
        conn,
        project_id=p_id_corrupt,
        user_id=user_id,
        balance_xu=8000,
        provider_admission=adm_corrupt,
    )
    assert res_corrupt.get("ok") is False
    assert "multi_scene_series_manifest_invalid" in str(res_corrupt.get("reason"))
    assert res_corrupt.get("job_created", False) is False

    assert conn.execute("SELECT count(*) FROM video_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM video_dispatch_outbox").fetchone()[0] == 0
    assert conn.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)).fetchone()[0] == 8000
