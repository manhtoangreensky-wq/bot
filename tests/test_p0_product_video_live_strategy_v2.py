from __future__ import annotations

import json
import hashlib
import inspect
from pathlib import Path

import bot

from services import video_ai_real_pricing, video_tail9


ROOT = Path(__file__).resolve().parents[1]
STRATEGY_PATH = ROOT / "KIEM-THU" / "product-video-live-strategy-v2.json"
CASE_SOURCE_PATH = ROOT / "KIEM-THU" / "DANH-SACH-CASE.md"
TESTER_GUIDE_PATH = ROOT / "KIEM-THU" / "HUONG-DAN-TESTER.md"
OPERATIONS_DOC_PATH = ROOT / "TAI-LIEU" / "01-NGHIEP-VU-VAN-HANH.md"
ORIGINAL_DOC_PATH = ROOT / "TAI-LIEU" / "02-CHUC-NANG-GOC-VA-HIEN-TAI.md"
CASE_TEMPLATE_PATH = ROOT / ".github" / "ISSUE_TEMPLATE" / "01-product-video-case-test.yml"


def _strategy() -> dict:
    return json.loads(STRATEGY_PATH.read_text(encoding="utf-8"))


def test_v2_representatives_lock_owner_scope_and_selfshot_products() -> None:
    strategy = _strategy()
    representatives = list(strategy["representatives"])
    product_ids = [str(row["product_id"]) for row in representatives]

    assert len(product_ids) == len(set(product_ids)) == 8
    assert set(strategy["excluded_products"]) == {
        "multi_scene_film",
        "video_long",
        "video_local_edit",
    }
    assert strategy["deferred_lanes"] == ["videoedit|ai"]
    assert not set(product_ids).intersection(strategy["excluded_products"])
    assert {
        "self_shot_scene_change",
        "self_shot_cinematic_transform",
    }.issubset(product_ids)

    for row in representatives:
        adapter_id = str(row.get("adapter_product_id") or row["product_id"])
        contract = video_tail9.commercial_contract(adapter_id)
        assert contract["flow_owner"] == row["flow_owner"], row["case_id"]
        assert contract["engine_route"] == row["engine_route"], row["case_id"]
        assert int(strategy["representative_tier_id"]) in set(
            contract["supported_quality_tiers"]
        ), row["case_id"]
        assert int(row["scene_count"]) >= int(contract["minimum_scene_count"])

    scenes_by_product = {
        str(row["product_id"]): int(row["scene_count"]) for row in representatives
    }
    assert scenes_by_product["script_image_video"] == 5
    assert all(
        count == 2
        for product, count in scenes_by_product.items()
        if product != "script_image_video"
    )


def test_v2_quality_assignment_covers_catalog_once_and_only_compatible_routes() -> None:
    strategy = _strategy()
    catalog = {
        int(row["tier_id"]): dict(row)
        for row in video_ai_real_pricing.public_quality_catalog()
    }
    assignments = list(strategy["quality_coverage"])
    assigned_tiers = [int(row["tier_id"]) for row in assignments]

    assert len(assigned_tiers) == len(set(assigned_tiers))
    assert set(assigned_tiers) == set(catalog)
    assert int(strategy["representative_tier_id"]) == 400
    assert int(strategy["representative_unit_xu"]) == 80
    assert int(catalog[400]["unit_xu"]) == 80

    representative = next(row for row in assignments if int(row["tier_id"]) == 400)
    assert representative == {
        "tier_id": 400,
        "coverage": "representatives",
        "scene_count": 2,
    }

    for row in assignments:
        tier_id = int(row["tier_id"])
        if tier_id == 400:
            continue
        assert int(row["scene_count"]) == 1
        assert str(row["product_id"]) not in set(strategy["excluded_products"])
        assert "videoedit" not in str(row["lane_callback"])
        contract = video_tail9.commercial_contract(str(row["adapter_product_id"]))
        assert contract["supports_single_scene"] is True, tier_id
        assert tier_id in set(contract["supported_quality_tiers"]), tier_id


def test_v2_manual_lanes_are_source_only_and_not_live_representatives() -> None:
    strategy = _strategy()

    assert strategy["manual_lanes"] == "source_contract_only"
    assert all("manual" not in str(row["lane_callback"]) for row in strategy["representatives"])


def test_v2_representative_callbacks_are_real_reachable_product_routes() -> None:
    strategy = _strategy()

    for row in strategy["representatives"]:
        product_id = str(row["product_id"])
        callback = str(row["lane_callback"])
        route = dict(bot.VIDEO_PUBLIC_ROUTE_MATRIX.get(product_id) or {})

        assert route["product_id"] == product_id, row["case_id"]
        assert route["invoice_reachable"] is True, row["case_id"]
        assert route["job_reachable"] is True, row["case_id"]
        assert callback == str(route.get("entry_callback") or "") or callback in set(
            route.get("expected_children") or ()
        ), row["case_id"]


def test_v2_product_video_edit_function_bytes_are_protected() -> None:
    strategy = _strategy()
    edit_lock = dict(strategy["protected_products"]["video_local_edit"])

    assert edit_lock["locked_at_sha"] == strategy["source_merge_sha"]
    assert "video_local_edit" in set(strategy["excluded_products"])
    assert all(
        str(row.get("product_id") or "") != "video_local_edit"
        for row in [*strategy["representatives"], *strategy["quality_coverage"]]
    )
    for function_name, expected_sha256 in edit_lock["function_sha256"].items():
        source = inspect.getsource(getattr(bot, function_name)).rstrip()
        actual_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
        assert actual_sha256 == expected_sha256, function_name


def test_v2_live_window_is_bounded_and_wallet_closed() -> None:
    strategy = _strategy()
    window = dict(strategy["live_window"])

    assert window["destination"] == "@toanaasbot"
    assert window["account_scope"] == "owner_admin_test_account"
    assert window["product_video_final_job_cap"] == 17
    representative_scenes = sum(
        int(row["scene_count"]) for row in strategy["representatives"]
    )
    quality_scenes = sum(
        int(row["scene_count"])
        for row in strategy["quality_coverage"]
        if int(row["tier_id"]) != int(strategy["representative_tier_id"])
    )
    assert representative_scenes == 19
    assert quality_scenes == 9
    assert window["assigned_scene_render_upper_bound"] == 28
    assert window["source_image_provider_task_cap"] == 4
    assert window["total_provider_task_cap"] == 32
    assert window["total_provider_task_cap"] == (
        window["assigned_scene_render_upper_bound"]
        + window["source_image_provider_task_cap"]
    )
    assert window["max_concurrent_heavy_tasks"] == 1
    assert window["browser_action_time_confirmation"] is True
    assert window["charged_xu_required"] == 0
    assert window["transaction_row_delta_required"] == 0
    assert window["credit_event_row_delta_required"] == 0
    assert {
        "video_local_edit",
        "videoedit|ai",
        "multi_scene_film",
        "video_long",
    }.issubset(set(window["excluded_actions"]))


def test_v2_every_paid_row_has_a_locked_unique_case_and_scenario() -> None:
    strategy = _strategy()
    representatives = list(strategy["representatives"])
    quality_only = [
        row
        for row in strategy["quality_coverage"]
        if int(row["tier_id"]) != int(strategy["representative_tier_id"])
    ]
    paid_rows = [*representatives, *quality_only]
    case_ids = [str(row.get("case_id") or "") for row in paid_rows]
    scenario_ids = [str(row.get("scenario_id") or "") for row in paid_rows]

    assert len(paid_rows) == int(strategy["live_window"]["product_video_final_job_cap"])
    assert all(case_ids) and len(case_ids) == len(set(case_ids))
    assert all(scenario_ids) and len(scenario_ids) == len(set(scenario_ids))
    assert all(str(row.get("scenario") or "").strip() for row in paid_rows)

    source_image_tasks = sum(
        len(row.get("source_generation_prompts") or []) for row in representatives
    )
    assert source_image_tasks == int(
        strategy["live_window"]["source_image_provider_task_cap"]
    )


def test_v2_committed_script_fixture_is_exact_and_five_scene() -> None:
    strategy = _strategy()
    row = next(
        item for item in strategy["representatives"] if item["product_id"] == "script_image_video"
    )
    fixture = ROOT / "KIEM-THU" / "fixtures" / "PV2-R03-tea-lotus-5-scenes.txt"
    payload = fixture.read_bytes()

    assert row["scene_count"] == 5
    assert payload.count(b"SCENE ") == 5
    assert hashlib.sha256(payload).hexdigest().upper() == (
        "39047AABFEE7D88B17109FCC90683C64080B5BB0AC3D531AC062B3060F836FCE"
    )
    assert row["fixture_refs"] == [
        "KIEM-THU/fixtures/PV2-R03-tea-lotus-5-scenes.txt#"
        "39047AABFEE7D88B17109FCC90683C64080B5BB0AC3D531AC062B3060F836FCE"
    ]


def test_v2_tester_docs_match_paid_assignments_exclusions_and_report_gate() -> None:
    strategy = _strategy()
    representatives = list(strategy["representatives"])
    quality_only = [
        row
        for row in strategy["quality_coverage"]
        if int(row["tier_id"]) != int(strategy["representative_tier_id"])
    ]
    expected_case_ids = [
        str(row["case_id"]) for row in [*representatives, *quality_only]
    ]
    case_source = CASE_SOURCE_PATH.read_text(encoding="utf-8")
    tester_guide = TESTER_GUIDE_PATH.read_text(encoding="utf-8")
    operations_doc = OPERATIONS_DOC_PATH.read_text(encoding="utf-8")
    original_doc = ORIGINAL_DOC_PATH.read_text(encoding="utf-8")
    case_template = CASE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert len(expected_case_ids) == 17
    for case_id in expected_case_ids:
        assert case_source.count(f"| `{case_id}` |") == 1, case_id
    assert "| PV-L07 |" not in case_source
    assert "| PV-L09 |" not in case_source
    assert "Video dài tập / manual" not in case_source
    assert "Chỉnh sửa Video / input 2 cảnh" not in case_source
    assert "8 representative" in tester_guide
    assert "9 quality-only" in tester_guide
    assert "delivery_report_message_id" in tester_guide
    assert "8 representative" in operations_doc
    assert "9 quality-only" in operations_doc
    assert "17 final jobs" in operations_doc
    assert "28 assigned scene renders" in operations_doc
    assert "Strategy V2" in original_doc
    assert "delivery_report_message_id" in case_template
