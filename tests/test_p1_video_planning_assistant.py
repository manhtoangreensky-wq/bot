from __future__ import annotations

import copy
import importlib
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "services" / "video_planning_assistant.py"
SID = "sid001"


def service():
    return importlib.import_module("services.video_planning_assistant")


def cb(svc, verb: str, *args: object) -> str:
    return svc.callback_data(SID, verb, *args)


def select(svc, state: dict[str, object], verb: str, *args: object, now: int = 101):
    return svc.apply_callback(state, cb(svc, verb, *args), now=now)["session"]


def build_summary_session(svc, *, brief: str = "") -> dict[str, object]:
    state = svc.new_session(SID, now=100)
    state = select(svc, state, "goal", "cut_pacing")
    if brief:
        state = svc.apply_text_input(state, brief, now=102)["session"]
    else:
        state = select(svc, state, "brief_skip", now=102)
    state = select(svc, state, "platform", "tiktok_9x16", now=103)
    state = select(svc, state, "source", "60_120", now=104)
    state = select(svc, state, "target", "30", now=105)
    state = select(svc, state, "asset", "video", now=106)
    state = select(svc, state, "asset", "logo", now=107)
    state = select(svc, state, "assets_done", now=108)
    state = select(svc, state, "priority", "pace", now=109)
    state = select(svc, state, "priority", "product_focus", now=110)
    state = select(svc, state, "priorities_done", now=111)
    assert state["selected_operations"]
    state = select(svc, state, "operations_done", now=112)
    state = select(svc, state, "safety_done", now=113)
    assert state["screen"] == "summary"
    return state


def row_pairs(view: dict[str, object]):
    return [pair for row in view["rows"] for pair in row]


def test_option_c_entry_and_session_schema_are_exact():
    svc = service()
    assert svc.CALLBACK_PREFIX == "lvs27b"
    assert svc.STATE_KEY == "local_video_studio27b_public"
    assert svc.PREVIEW_VERSION == "27B"
    assert svc.public_entry_rows(True) == (("🧭 Lên kế hoạch chỉnh sửa", "lvs27b|open"),)
    assert svc.public_entry_rows(False) == ()
    assert tuple(option_id for option_id, _label in svc.GOAL_OPTIONS) == (
        "cut_pacing", "reframe", "transition_motion", "sound_post"
    )
    assert svc.new_session(SID, now=100) == {
        "version": "27B",
        "plan_schema_version": 1,
        "session_id": SID,
        "plan_id": "",
        "created_at": 100,
        "updated_at": 100,
        "screen": "goal",
        "history": [],
        "goal": "",
        "editing_brief": "",
        "platform_ratio": "",
        "source_duration": "",
        "target_duration": "",
        "available_assets": [],
        "priorities": [],
        "selected_operations": [],
        "processed_callback_ids": [],
        "sent_summary_fingerprint": "",
    }


def test_guided_flow_auto_advances_and_multi_selects_are_sticky():
    svc = service()
    state = svc.new_session(SID, now=100)
    screens = [state["screen"]]
    state = select(svc, state, "goal", "cut_pacing"); screens.append(state["screen"])
    state = svc.apply_text_input(state, "Video bán hàng cần nhanh và rõ sản phẩm", now=102)["session"]; screens.append(state["screen"])
    state = select(svc, state, "platform", "tiktok_9x16"); screens.append(state["screen"])
    state = select(svc, state, "source", "60_120"); screens.append(state["screen"])
    state = select(svc, state, "target", "30"); screens.append(state["screen"])
    state = select(svc, state, "asset", "video")
    assert state["screen"] == "assets" and state["available_assets"] == ["video"]
    state = select(svc, state, "assets_done"); screens.append(state["screen"])
    state = select(svc, state, "priority", "pace")
    assert state["screen"] == "priorities"
    state = select(svc, state, "priorities_done"); screens.append(state["screen"])
    assert {"cut", "pace", "best_segment"}.issubset(set(state["selected_operations"]))
    state = select(svc, state, "operations_done"); screens.append(state["screen"])
    state = select(svc, state, "safety_done"); screens.append(state["screen"])
    assert screens == [
        "goal", "brief", "platform", "source_duration", "target_duration",
        "assets", "priorities", "operations", "safety", "summary",
    ]


def test_brief_is_bounded_skip_is_supported_and_keyword_advice_is_local():
    svc = service()
    state = select(svc, svc.new_session(SID, now=100), "goal", "reframe")
    with pytest.raises(svc.PreviewActionError):
        svc.apply_text_input(state, "")
    with pytest.raises(svc.PreviewActionError):
        svc.apply_text_input(state, "x" * 601)
    text = "Video sản phẩm cần nhanh, sáng hơn, rõ âm lượng, logo, watermark, phụ đề và khung 9:16."
    state = svc.apply_text_input(state, text, now=101)["session"]
    assert state["editing_brief"] == text
    state["available_assets"] = ["video", "logo", "watermark", "subtitles"]
    assert {"cut", "pace", "best_segment", "brightness", "audio", "logo", "watermark", "subtitles", "reframe"}.issubset(set(svc.suggest_operations(state)))
    skipped = select(svc, select(svc, svc.new_session(SID, now=100), "goal", "sound_post"), "brief_skip")
    assert skipped["screen"] == "platform" and skipped["editing_brief"] == ""


def test_summary_preserves_user_timestamps_and_never_invents_them():
    svc = service()
    brief = "Bỏ 00:00–00:08; giữ sản phẩm 00:08–00:28; logo góc trên trái."
    with_ranges = svc.planning_summary_text(build_summary_session(svc, brief=brief))
    assert brief in with_ranges and "00:00–00:08" in with_ranges and "00:08–00:28" in with_ranges
    without_ranges = svc.planning_summary_text(build_summary_session(svc))
    assert not re.search(r"\b\d{2}:\d{2}[–—-]\d{2}:\d{2}\b", without_ranges)
    assert "chưa có mốc thời gian" in without_ranges.lower()


def test_summary_is_a_human_plan_without_technical_leakage():
    svc = service()
    state = build_summary_session(svc, brief="Muốn video nhanh, giữ sản phẩm chính và logo không che mặt.")
    text = svc.planning_summary_text(state)
    for required in ("KẾ HOẠCH CHỈNH SỬA", "TikTok", "9:16", "Video nguồn", "Thành phẩm", "Các bước đề xuất", "1.", "không xử lý media", "không trừ Xu"):
        assert required in text
    lowered = text.lower()
    for forbidden in ("capability", "readiness", "provider", "ffmpeg", "job", "task_id", "sha", "\\users\\"):
        assert forbidden not in lowered
    labels = [label for label, _callback in row_pairs(svc.render_view(state))]
    assert labels[:3] == ["💾 Lưu kế hoạch", "💬 Gửi kế hoạch vào chat", "📂 Kế hoạch của tôi"]


def test_summary_actions_are_distinct_and_semantically_idempotent():
    svc = service(); state = build_summary_session(svc)
    persist = svc.apply_callback(state, cb(svc, "persist"), now=120, callback_id="persist-1")
    assert persist["persist_plan"]["plan_schema_version"] == 1 and persist["send_text"] == "" and persist["open_saved_plans"] is False
    send = svc.apply_callback(state, cb(svc, "send"), now=121, callback_id="send-1")
    assert send["persist_plan"] is None and send["send_text"] == svc.planning_summary_text(state)
    plans = svc.apply_callback(state, cb(svc, "plans"), now=122, callback_id="plans-1")
    assert plans["persist_plan"] is None and plans["send_text"] == "" and plans["open_saved_plans"] is True


def test_saved_plan_library_actions_are_owner_adapter_requests_only():
    svc = service(); state = build_summary_session(svc); plan_key = "abcdef123456"
    library = svc.apply_callback(state, cb(svc, "library"), now=123)
    assert library["saved_plan_action"] == "library" and library["saved_plan_key"] == ""
    current = svc.apply_callback(state, cb(svc, "current"), now=123)
    assert current["saved_plan_action"] == "current" and current["saved_plan_key"] == ""
    for verb in ("view", "edit", "delete", "delete_confirm"):
        callback = cb(svc, verb, plan_key)
        assert len(callback.encode("utf-8")) <= 64
        result = svc.apply_callback(state, callback, now=124)
        assert result["saved_plan_action"] == verb and result["saved_plan_key"] == plan_key


def test_plan_roundtrip_restores_editable_summary_without_session_metadata():
    svc = service()
    state = build_summary_session(svc, brief="Giữ đoạn sản phẩm 00:10–00:25 và tăng sáng nhẹ.")
    plan = svc.serialize_plan(state)
    assert "history" not in plan and "processed_callback_ids" not in plan
    assert plan["rights_notes"] and plan["created_at"] == 100 and plan["updated_at"] == 113
    restored = svc.session_from_plan(plan, session_id="sid002", now=200)
    assert restored["session_id"] == "sid002" and restored["screen"] == "summary"
    roundtrip = svc.serialize_plan(restored)
    for field in set(plan) - {"created_at", "updated_at"}:
        assert roundtrip[field] == plan[field]
    assert roundtrip["created_at"] == roundtrip["updated_at"] == 200
    malformed = copy.deepcopy(plan); malformed["priorities"] = ["not-allowed"]
    with pytest.raises(svc.PreviewActionError):
        svc.session_from_plan(malformed, session_id="sid003", now=201)


def test_duration_copy_is_neutral_and_branding_requires_available_assets():
    svc = service()
    state = build_summary_session(svc)
    state["source_duration"] = "under30"
    state["target_duration"] = "60"
    steps = svc.ordered_steps(state)
    assert "Rút video" not in steps[0]
    assert "Khoảng 60 giây" in steps[0]
    state["target_duration"] = "keep"
    assert "Giữ thành phẩm gần thời lượng nguồn" in svc.ordered_steps(state)[0]

    state["available_assets"] = ["none"]
    state["priorities"] = ["branding"]
    state["selected_operations"] = ["qa"]
    assert not {"logo", "watermark"} & set(svc.suggest_operations(state))
    plan = svc.serialize_plan(state)
    assert any("chuẩn bị logo hoặc watermark" in note.lower() for note in plan["rights_notes"])

    state["available_assets"] = ["video", "logo"]
    suggested = set(svc.suggest_operations(state))
    assert "logo" in suggested and "watermark" not in suggested


def test_ordered_steps_use_stable_editing_order_and_keep_qa_last():
    svc = service()
    state = build_summary_session(svc)
    state["available_assets"] = ["video", "logo", "watermark"]
    state["selected_operations"] = ["qa", "watermark", "cut", "logo", "brightness"]

    plan = svc.serialize_plan(state)

    assert plan["selected_operations"] == ["cut", "brightness", "logo", "watermark", "qa"]
    assert plan["ordered_steps"][-1] == svc.PUBLIC_OPERATION_STEPS["qa"]
    assert plan["ordered_steps"].index(svc.PUBLIC_OPERATION_STEPS["cut"]) < plan["ordered_steps"].index(
        svc.PUBLIC_OPERATION_STEPS["logo"]
    )


@pytest.mark.parametrize(
    ("assets", "operations", "missing_asset"),
    [
        (["video", "logo"], ["logo", "watermark", "qa"], "watermark"),
        (["video", "watermark"], ["logo", "watermark", "qa"], "logo"),
    ],
)
def test_rights_notes_name_each_selected_branding_asset_that_is_missing(
    assets, operations, missing_asset
):
    svc = service()
    state = build_summary_session(svc)
    state["available_assets"] = assets
    state["selected_operations"] = operations

    notes = svc.rights_notes(state)

    assert any(missing_asset in note.casefold() for note in notes)


def test_explicit_branding_request_is_planned_and_flags_the_missing_asset():
    svc = service()
    state = build_summary_session(
        svc,
        brief="Thêm watermark ở vùng không che sản phẩm.",
    )
    state["available_assets"] = ["video"]
    state["selected_operations"] = svc.suggest_operations(state)

    plan = svc.serialize_plan(state)

    assert "watermark" in plan["selected_operations"]
    assert any("watermark" in note.casefold() for note in plan["rights_notes"])


def test_keep_duration_does_not_add_cut_when_user_unselected_cut():
    svc = service()
    state = build_summary_session(svc)
    state["target_duration"] = "keep"
    state["selected_operations"] = ["qa"]

    plan = svc.serialize_plan(state)

    assert not any("cắt" in step.casefold() for step in plan["ordered_steps"])


def test_back_returns_exact_parent_and_root_returns_menu_video():
    svc = service(); state = build_summary_session(svc)
    expected = ["safety", "operations", "priorities", "assets", "target_duration", "source_duration", "platform", "brief", "goal"]
    for screen in expected:
        state = select(svc, state, "back"); assert state["screen"] == screen
    assert ("⬅️ Menu Video", cb(svc, "back")) in row_pairs(svc.render_view(state))
    assert svc.apply_callback(state, cb(svc, "back"), now=300)["exit_parent"] is True


def test_callbacks_are_short_allowlisted_and_malformed_state_fails_closed():
    svc = service(); state = build_summary_session(svc)
    for view_state in (svc.new_session(SID, now=100), state):
        for _label, callback in row_pairs(svc.render_view(view_state)):
            assert len(callback.encode("utf-8")) <= 64; svc.parse_callback(callback)
    with pytest.raises(svc.PreviewActionError): svc.parse_callback("lvs27b|sid001|unknown")
    with pytest.raises(svc.PreviewActionError): svc.parse_callback("other|sid001|back")
    broken = copy.deepcopy(state); broken["selected_operations"] = ["not-allowed"]
    with pytest.raises(svc.PreviewActionError): svc.normalize_session(broken)


def test_module_is_pure_and_has_no_execution_or_money_dependencies():
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in ("sqlite3", "subprocess", "ffmpeg", "video_edit", "video_project", "wallet", "payment", "provider", "telegram"):
        assert forbidden not in source.lower()
