from __future__ import annotations

import copy
import re
import sqlite3

import pytest


def store_module():
    from services import local_video_planning_store

    return local_video_planning_store


def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def sample_plan(*, brief: str = "Video cần nhanh và rõ sản phẩm") -> dict[str, object]:
    return {
        "plan_schema_version": 1,
        "plan_id": "",
        "title": "Cắt dựng và nhịp · TikTok · 9:16",
        "goal": "cut_pacing",
        "editing_brief": brief,
        "platform_ratio": "tiktok_9x16",
        "source_duration": "60_120",
        "target_duration": "30",
        "available_assets": ["video", "logo"],
        "priorities": ["pace", "product_focus"],
        "selected_operations": ["cut", "best_segment", "pace", "qa"],
        "ordered_steps": [
            "Hướng thành phẩm tới khoảng 30 giây từ video nguồn khoảng 1–2 phút.",
            "Chọn và giữ đoạn sản phẩm rõ nhất.",
            "Kiểm tra thành phẩm.",
        ],
        "rights_notes": ["Chỉ sử dụng nội dung và tài nguyên có quyền sử dụng."],
        "created_at": 100,
        "updated_at": 113,
    }


def test_schema_is_idempotent_and_contains_only_planning_table():
    store = store_module()
    conn = connection()

    store.ensure_schema(conn)
    store.ensure_schema(conn)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "local_video_plans" in tables
    assert not {"video_projects", "video_jobs", "memory_plans"} & tables


def test_create_get_list_and_soft_delete_are_owner_scoped():
    store = store_module()
    conn = connection()
    store.ensure_schema(conn)

    saved = store.save_plan_from_session(
        conn,
        owner_id="7",
        chat_id="70",
        source_session_id="sid001",
        plan=sample_plan(),
        summary_text="Bản kế hoạch công khai",
        now="2026-08-11T12:00:00Z",
    )

    assert re.fullmatch(r"[a-f0-9]{12}", saved["plan_key"])
    assert saved["version"] == 1
    assert store.get_plan(conn, owner_id="7", chat_id="70", plan_key=saved["plan_key"])["title"] == sample_plan()["title"]
    assert store.get_plan(conn, owner_id="8", chat_id="70", plan_key=saved["plan_key"]) is None
    assert store.get_plan(conn, owner_id="7", chat_id="71", plan_key=saved["plan_key"]) is None
    assert [item["plan_key"] for item in store.list_plans(conn, owner_id="7", chat_id="70")] == [saved["plan_key"]]

    assert store.soft_delete_plan(
        conn,
        owner_id="8",
        chat_id="70",
        plan_key=saved["plan_key"],
        now="2026-08-11T12:01:00Z",
    ) is False
    assert store.soft_delete_plan(
        conn,
        owner_id="7",
        chat_id="70",
        plan_key=saved["plan_key"],
        now="2026-08-11T12:01:00Z",
    ) is True
    assert store.get_plan(conn, owner_id="7", chat_id="70", plan_key=saved["plan_key"]) is None
    assert store.list_plans(conn, owner_id="7", chat_id="70") == []

    restored = store.save_plan_from_session(
        conn,
        owner_id="7",
        chat_id="70",
        source_session_id="sid001",
        plan=sample_plan(brief="Lưu lại kế hoạch sau khi xóa"),
        summary_text="Bản kế hoạch được lưu lại",
        now="2026-08-11T12:02:00Z",
    )
    assert restored["plan_key"] == saved["plan_key"]
    assert restored["version"] == 3
    assert store.get_plan(conn, owner_id="7", chat_id="70", plan_key=saved["plan_key"]) is not None


def test_retry_same_source_session_is_idempotent_and_changed_content_updates_once():
    store = store_module()
    conn = connection()
    store.ensure_schema(conn)
    args = dict(owner_id="7", chat_id="70", source_session_id="sid001")

    first = store.save_plan_from_session(
        conn,
        **args,
        plan=sample_plan(),
        summary_text="summary-1",
        now="2026-08-11T12:00:00Z",
    )
    duplicate = store.save_plan_from_session(
        conn,
        **args,
        plan=sample_plan(),
        summary_text="summary-1",
        now="2026-08-11T12:00:10Z",
    )
    assert duplicate["plan_key"] == first["plan_key"]
    assert duplicate["version"] == 1
    assert conn.execute("SELECT COUNT(*) FROM local_video_plans").fetchone()[0] == 1

    timestamp_only = sample_plan()
    timestamp_only["updated_at"] = 999
    timestamp_retry = store.save_plan_from_session(
        conn,
        **args,
        plan=timestamp_only,
        summary_text="summary-1",
        now="2026-08-11T12:00:20Z",
    )
    assert timestamp_retry["version"] == 1
    assert timestamp_retry["plan"]["updated_at"] == sample_plan()["updated_at"]

    changed_plan = sample_plan(brief="Video cần nhanh, sáng và rõ sản phẩm")
    changed = store.save_plan_from_session(
        conn,
        **args,
        plan=changed_plan,
        summary_text="summary-2",
        now="2026-08-11T12:01:00Z",
    )
    assert changed["plan_key"] == first["plan_key"]
    assert changed["version"] == 2
    assert changed["plan"]["editing_brief"] == changed_plan["editing_brief"]
    assert conn.execute("SELECT COUNT(*) FROM local_video_plans").fetchone()[0] == 1


def test_update_uses_optimistic_version_and_never_crosses_owner():
    store = store_module()
    conn = connection()
    store.ensure_schema(conn)
    saved = store.save_plan_from_session(
        conn,
        owner_id="7",
        chat_id="70",
        source_session_id="sid001",
        plan=sample_plan(),
        summary_text="summary-1",
        now="2026-08-11T12:00:00Z",
    )
    revised = sample_plan(brief="Giữ 00:08–00:28 và bỏ phần mở đầu")

    with pytest.raises(store.PlanConflictError):
        store.update_plan(
            conn,
            owner_id="7",
            chat_id="70",
            plan_key=saved["plan_key"],
            expected_version=99,
            plan=revised,
            summary_text="summary-2",
            now="2026-08-11T12:01:00Z",
        )
    with pytest.raises(store.PlanNotFoundError):
        store.update_plan(
            conn,
            owner_id="8",
            chat_id="70",
            plan_key=saved["plan_key"],
            expected_version=1,
            plan=revised,
            summary_text="summary-2",
            now="2026-08-11T12:01:00Z",
        )

    updated = store.update_plan(
        conn,
        owner_id="7",
        chat_id="70",
        plan_key=saved["plan_key"],
        expected_version=1,
        plan=revised,
        summary_text="summary-2",
        now="2026-08-11T12:01:00Z",
    )
    assert updated["version"] == 2
    assert updated["plan"]["editing_brief"] == revised["editing_brief"]


def test_plan_validation_fails_closed_without_writing_a_row():
    store = store_module()
    conn = connection()
    store.ensure_schema(conn)
    invalid = copy.deepcopy(sample_plan())
    invalid["selected_operations"] = ["not-allowed"]

    with pytest.raises(store.PlanValidationError):
        store.save_plan_from_session(
            conn,
            owner_id="7",
            chat_id="70",
            source_session_id="sid001",
            plan=invalid,
            summary_text="summary",
        )
    assert conn.execute("SELECT COUNT(*) FROM local_video_plans").fetchone()[0] == 0


def test_list_is_bounded_newest_first_and_returns_detached_payloads():
    store = store_module()
    conn = connection()
    store.ensure_schema(conn)
    for index in range(5):
        store.save_plan_from_session(
            conn,
            owner_id="7",
            chat_id="70",
            source_session_id=f"sid{index:03d}",
            plan=sample_plan(brief=f"brief-{index}"),
            summary_text=f"summary-{index}",
            now=f"2026-08-11T12:0{index}:00Z",
        )

    page = store.list_plans(conn, owner_id="7", chat_id="70", limit=3, offset=0)
    assert [item["plan"]["editing_brief"] for item in page] == ["brief-4", "brief-3", "brief-2"]
    page[0]["plan"]["editing_brief"] = "mutated outside"
    fresh = store.get_plan(conn, owner_id="7", chat_id="70", plan_key=page[0]["plan_key"])
    assert fresh["plan"]["editing_brief"] == "brief-4"


def test_active_plan_limit_matches_every_plan_visible_in_default_library():
    store = store_module()
    conn = connection()
    store.ensure_schema(conn)
    for index in range(store.MAX_ACTIVE_PLANS):
        store.save_plan_from_session(
            conn,
            owner_id="7",
            chat_id="70",
            source_session_id=f"limit{index:03d}",
            plan=sample_plan(brief=f"visible-{index}"),
            summary_text=f"summary-{index}",
        )

    assert len(store.list_plans(conn, owner_id="7", chat_id="70")) == store.MAX_ACTIVE_PLANS
    with pytest.raises(store.PlanLimitError):
        store.save_plan_from_session(
            conn,
            owner_id="7",
            chat_id="70",
            source_session_id="limit999",
            plan=sample_plan(brief="must-not-be-hidden"),
            summary_text="summary-over-limit",
        )


def test_summary_snapshot_uses_telegram_visible_length_not_escaped_html_length():
    store = store_module()
    conn = connection()
    store.ensure_schema(conn)
    telegram_safe_html = "&amp;" * 900

    saved = store.save_plan_from_session(
        conn,
        owner_id="7",
        chat_id="70",
        source_session_id="summary001",
        plan=sample_plan(),
        summary_text=telegram_safe_html,
    )

    assert saved["summary_text"] == telegram_safe_html
    with pytest.raises(store.PlanValidationError):
        store.save_plan_from_session(
            conn,
            owner_id="7",
            chat_id="70",
            source_session_id="summary002",
            plan=sample_plan(brief="visible overflow"),
            summary_text="x" * 4097,
        )
