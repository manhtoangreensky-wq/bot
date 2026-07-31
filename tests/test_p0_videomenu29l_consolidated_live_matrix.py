import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "docs" / "reports" / "P0_VIDEOMENU_ROUTEENGINE29L_LIVE_MATRIX.json"
REPORT_PATH = ROOT / "docs" / "reports" / "P0_VIDEOMENU_ROUTEENGINE29L_LIVE_MATRIX.md"
BASELINE_MAIN_SHA = "94ad8a97d128cfcbbd3439ec602c5c2f9fbde225"
LAST_VERIFIED_WORKER_SHA = "2622328872800abc08ec44372d49e05e8433618a"
PRODUCT_MODES = {
    "product_video": ["single_scene", "multi_scene"],
    "frame_video": ["single_scene", "multi_scene"],
    "animated_video": ["single_scene", "multi_scene"],
    "human_ai_video": ["single_scene", "multi_scene"],
    "summary_video": ["single_scene", "multi_scene"],
    "podcast_video": ["single_scene", "multi_scene"],
}
ENTRY_ENGINE_OWNERS = {
    "video_ai_realistic": "product_video",
    "video_trend": "product_video",
    "script_to_video": "product_video",
    "storyboard_to_video": "product_video",
    "video_idea": "product_video",
    "frame_to_video": "frame_video",
    "selfshot_scene_change": "human_ai_video",
    "selfshot_cinematic": "human_ai_video",
    "animated_video": "animated_video",
    "summary_video": "summary_video",
    "podcast_video": "podcast_video",
}
DEFAULT_FLAG_SOURCES = {
    "product_video": (
        ("services/product_video_one_scene_engine.py", "FEATURE_FLAG_DEFAULTS"),
        ("services/product_video_multiscene_engine.py", "MULTISCENE_FLAG_DEFAULTS"),
    ),
    "frame_video": (("services/frame_video_engine.py", "FRAME_VIDEO_ENGINE_FLAG_DEFAULTS"),),
    "animated_video": (
        ("services/animated_video_engine.py", "ANIMATED_VIDEO_ENGINE_FLAG_DEFAULTS"),
    ),
    "human_ai_video": (
        ("services/human_ai_video_engine.py", "HUMAN_AI_VIDEO_ENGINE_FLAG_DEFAULTS"),
    ),
    "summary_video": (
        ("services/summary_video_engine.py", "SUMMARY_VIDEO_ENGINE_FLAG_DEFAULTS"),
    ),
    "podcast_video": (
        ("services/podcast_video_engine.py", "PODCAST_VIDEO_ENGINE_FLAG_DEFAULTS"),
    ),
}
LIVE_FIELDS = {
    "deployment_id",
    "admin_live_smoke_job",
    "mp4_bytes",
    "duration_seconds",
    "codec",
    "resolution",
    "delivery_count",
    "receipt_count",
    "report_count",
}


def _matrix() -> dict:
    assert MATRIX_PATH.is_file(), "29L canonical JSON evidence matrix is missing"
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _products(matrix: dict) -> dict[str, dict]:
    return {item["product_type"]: item for item in matrix["products"]}


def _literal_assignment(relative_path: str, assignment_name: str) -> dict[str, bool]:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    marker = f"{assignment_name} = "
    assignment_start = source.find(marker)
    assert assignment_start >= 0, f"{assignment_name} is missing from {relative_path}"
    literal_start = source.find("{", assignment_start + len(marker))
    literal_end = source.find("\n}", literal_start)
    assert literal_start >= 0 and literal_end >= 0
    value = ast.literal_eval(source[literal_start : literal_end + 2])
    assert isinstance(value, dict)
    return value


def test_29l_matrix_covers_owned_products_and_releases_video_edit() -> None:
    matrix = _matrix()
    assert matrix["schema_version"] == "routeengine29l.v1"
    assert matrix["generated_from_main_sha"] == BASELINE_MAIN_SHA
    assert set(_products(matrix)) == set(PRODUCT_MODES)
    assert matrix["scope"]["included_products"] == list(PRODUCT_MODES)
    released = matrix["scope"]["excluded_products"]["video_editing"]
    assert released["owner"] == "video_edit_task"
    assert released["route_engine_released"] is True
    assert released["implementation_claimed_by_29l"] is False


def test_29l_each_product_records_real_lineage_modes_and_prompt_contract() -> None:
    products = _products(_matrix())
    for product_type, expected_modes in PRODUCT_MODES.items():
        item = products[product_type]
        assert item["modes"] == expected_modes
        assert item["engine_files"]
        assert item["flow_contract"]
        assert item["prompt_contract"]
        assert item["offline_fixture"]["status"] == "PASS"
        assert item["offline_fixture"]["artifact_kind"] == "real_local_mp4"
        assert item["offline_fixture"]["mp4_bytes"] == "asserted_gt_zero_not_retained"
        assert item["offline_fixture"]["duration_seconds"] == "asserted_positive_not_retained"
        assert item["offline_fixture"]["codec"] == "ffprobe_validated_not_retained"
        assert item["offline_fixture"]["resolution"] == "ffprobe_validated_not_retained"
        for field in ("route_head_shas", "merge_shas"):
            assert item[field]
            assert all(re.fullmatch(r"[0-9a-f]{40}", value) for value in item[field])


def test_29l_locked_entries_map_selectively_without_changing_parent_or_back() -> None:
    mapping = _matrix()["locked_flow_entry_mapping"]
    assert set(mapping) == set(ENTRY_ENGINE_OWNERS)
    for entry, engine_product in ENTRY_ENGINE_OWNERS.items():
        contract = mapping[entry]
        assert contract["engine_product"] == engine_product
        assert contract["preserves_parent_state"] is True
        assert contract["public_flow_changed"] is False
        assert contract["back_route_changed"] is False
        assert contract["mode_policy"] in {
            "single_or_multi",
            "multi_scene_only",
            "owner_footage_single_or_multi",
            "independent_default_off",
        }


def test_29l_rollback_flags_match_real_default_off_engine_contracts() -> None:
    products = _products(_matrix())
    for product_type, sources in DEFAULT_FLAG_SOURCES.items():
        expected: dict[str, bool] = {}
        for relative_path, assignment_name in sources:
            expected.update(_literal_assignment(relative_path, assignment_name))
        assert expected
        assert all(value is False for value in expected.values())
        rollback = products[product_type]["rollback"]
        assert rollback["default_flags"] == expected
        assert rollback["dispatch_allowed_by_default"] is False
        assert rollback["automatic_paid_retry"] is False
        assert rollback["automatic_paid_fallback"] is False
        if any("PROVIDER_ENABLED" in name for name in expected):
            assert rollback["provider_control"] == "explicit_default_off_flag"
        else:
            assert rollback["provider_control"] == "local_only_no_provider"


def test_29l_worker_and_live_truth_fail_closed_without_current_evidence() -> None:
    matrix = _matrix()
    worker = matrix["worker"]
    assert worker["last_verified_worker_sha"] == LAST_VERIFIED_WORKER_SHA
    assert worker["expected_runtime_sha"] == BASELINE_MAIN_SHA
    assert worker["current_worker_sha"] is None
    assert worker["worker_sha_match"] == "UNVERIFIED"
    assert worker["heartbeat"] == "UNVERIFIED"
    assert worker["dispatch_allowed"] is False
    assert worker["blocker"] == "worker_current_runtime_unverified"

    for item in matrix["products"]:
        production = item["production"]
        assert production["live_pass"] is False
        assert production["blockers"]
        assert all(production[field] is None for field in LIVE_FIELDS)
        assert production["provider_submit_count"] == 0
        assert production["real_provider_calls"] == 0
        assert production["paid_provider_calls"] == 0
        assert production["duplicate_submit"] == 0
        assert production["duplicate_delivery"] == 0
        assert production["stuck_jobs"] == 0
        assert production["wallet_mutations"] == 0
        assert production["admin_charge_xu"] == 0

    aggregate = matrix["aggregate"]
    assert aggregate["all_video_menu_routes_live_pass"] is False
    assert aggregate["production_provider_submits"] == 0
    assert aggregate["real_provider_calls"] == 0
    assert aggregate["paid_provider_calls"] == 0
    assert aggregate["production_telegram_deliveries"] == 0
    assert aggregate["wallet_mutations"] == 0
    assert aggregate["fake_success"] == 0
    assert aggregate["automatic_paid_retry"] == 0
    assert aggregate["automatic_paid_fallback"] == 0


def test_29l_regression_evidence_is_separated_from_live_evidence() -> None:
    evidence = _matrix()["regression_evidence"]
    assert evidence == {
        "accepted_29b_29k_passed": 245,
        "accepted_29b_29l_passed": 252,
        "focused_29k_passed": 24,
        "focused_29l_passed": 7,
        "locked_ui_branch_passed": 144,
        "locked_ui_clean_main_passed": 144,
        "ffmpeg_security_output_passed": 102,
        "new_failures": 0,
        "snapshot_updates": 0,
        "ui_files_changed": 0,
    }


def test_29l_human_report_states_truth_without_claiming_live_or_video_edit() -> None:
    assert REPORT_PATH.is_file(), "29L human-readable report is missing"
    report = REPORT_PATH.read_text(encoding="utf-8")
    for heading in (
        "## Production Truth",
        "## Product Matrix",
        "## Prompt And Flow Fidelity",
        "## Rollback",
        "## Remaining Live Gates",
    ):
        assert heading in report
    for label in (
        "Product Video",
        "Frame Video",
        "Animated Video",
        "Human/AI Video",
        "Summary Video",
        "Podcast Video",
    ):
        assert label in report
    assert "worker_current_runtime_unverified" in report
    assert "VIDEO EDIT ROUTE/ENGINE RELEASED=YES" in report
    assert "ALL VIDEO MENU ROUTES LIVE PASS=NO" in report
    assert "ALL VIDEO MENU ROUTES LIVE PASS=YES" not in report
