from __future__ import annotations

import asyncio
import json
import sqlite3
from copy import deepcopy
from types import SimpleNamespace

import bot
import pytest
from fastapi.testclient import TestClient
from services import video_project_queue as queue


def _strict_addon_plan() -> dict:
    return {
        "contract_version": "product-video-addons-v1",
        "requested_addons": ["transitions"],
        "subtitle": {"enabled": False, "source": "none"},
        "dubbing": {"enabled": False, "source": "none"},
        "music": {"enabled": False, "source": "none"},
        "sfx": {"enabled": False, "source": "none"},
        "logo": {"enabled": False, "source": "none"},
        "watermark": {"enabled": False, "text": ""},
        "text_overlays": [],
        "transition_plan": [
            {"from_scene": 1, "to_scene": 2, "type": "dissolve"}
        ],
        "materialization_requirements": [
            {
                "name": "transitions",
                "required": True,
                "material_identity": "transition-1-2",
                "material_kind": "inline_transition_plan",
            }
        ],
        "silent_drop_allowed": False,
    }


def _invoice() -> dict:
    return {
        "quality_xu": 80,
        "routing_quality_tier": 400,
        "package_name": "Nhanh gọn · 8 giây/cảnh",
        "package_label": "Nhanh gọn · 8 giây/cảnh",
        "scene_count": 2,
        "scene_seconds": 8,
        "scene_duration_seconds": 8,
        "duration_seconds": 16,
        "subtotal_xu": 160,
        "discount_percent": 10,
        "discount_xu": 16,
        "addon_items": [{"key": "transitions", "label": "Chuyển cảnh", "price_xu": 0}],
        "addons_xu": 0,
        "addons_disabled_by_package": False,
        "total_xu": 144,
        "user_id": 7126457028,
    }


def test_generic_project_persistence_keeps_strict_tail_addon_contract_exact(
    monkeypatch,
) -> None:
    strict_plan = _strict_addon_plan()
    session = {
        "product_id": "video_ai_real",
        "topic": "Nghệ nhân hoàn thiện bình gốm xanh",
        "aspect_ratio": "9:16",
        "draft": {
            "b14_profile_id": "storytelling",
            "b14_storyboard_plan": {
                "preview_text": "Hai cảnh làm gốm",
                "scene_cards": [
                    {"scene_index": 1, "provider_prompt": "Tạo hình bình gốm"},
                    {"scene_index": 2, "provider_prompt": "Hoàn thiện bình gốm"},
                ],
            },
            "b14_addon_plan": deepcopy(strict_plan),
            "b14_quality_xu": 400,
            "b14_scene_count": 2,
            "b14_scene_count_selected": True,
        },
    }
    captured = {}

    monkeypatch.setattr(bot, "video_uiflow3_handoff_from_session", lambda _session: {})
    monkeypatch.setattr(bot, "video_b14_invoice_for_session", lambda *_args: _invoice())
    monkeypatch.setattr(bot, "video_b14_is_admin_or_owner", lambda _user_id: True)
    monkeypatch.setattr(
        bot,
        "product_video_logo_material_from_session",
        lambda _session: {"logo_enabled": False},
    )
    monkeypatch.setattr(
        bot,
        "create_video_project",
        lambda *_args, **_kwargs: {"project_id": 31},
    )
    monkeypatch.setattr(bot, "save_video_project_storyboard", lambda *_args: None)
    monkeypatch.setattr(
        bot,
        "video_b14_creative_controls_to_storyboard",
        lambda _session: {},
    )

    def capture_update(project_id, **fields):
        captured.update(fields)
        return {"project_id": project_id, **fields}

    monkeypatch.setattr(bot, "update_video_project", capture_update)
    monkeypatch.setattr(bot, "save_video_session", lambda _user_id, value: value)

    bot.video_b14_prepare_project_for_invoice(7126457028, session)

    assert captured["addon_plan_json"] == strict_plan
    assert captured["addon_plan_json"] is not strict_plan
    assert captured["addon_plan_json"]["requested_addons"] == ["transitions"]
    assert not {
        "voice",
        "dubbing",
        "music",
        "subtitle",
    }.intersection(captured["addon_plan_json"]["requested_addons"])


def test_worker_addon_plan_keeps_legacy_sessions_on_existing_normalizer() -> None:
    session = {
        "draft": {
            "b14_profile_id": "storytelling",
            "b14_addon_plan": {
                "voice_enabled": False,
                "music_enabled": True,
                "music_source": "default",
                "subtitle_enabled": False,
            },
        }
    }

    expected = bot.video_b14_addon_plan_from_session(session)
    actual = bot.video_b14_worker_addon_plan_from_session(session)

    assert actual == expected
    assert actual is not expected


def test_customer_delivery_report_contains_business_truth_without_internal_terms() -> None:
    addon_plan = {
        **_strict_addon_plan(),
        "requested_addons": ["music", "transitions"],
        "music": {"enabled": True, "source": "vault"},
    }
    invoice = {
        **_invoice(),
        "addon_items": [
            {"key": "music_ai", "label": "Nhạc nền", "price_xu": 10},
            {"key": "transitions", "label": "Chuyển cảnh", "price_xu": 0},
        ],
        "addons_xu": 10,
        "total_xu": 154,
    }
    project = {
        "project_id": 23,
        "user_id": "7126457028",
        "ratio": "9:16",
        "quality_tier": 400,
        "scene_count": 2,
        "invoice_json": json.dumps(invoice, ensure_ascii=False),
        "addon_plan_json": json.dumps(addon_plan, ensure_ascii=False),
    }
    job = {
        "id": 26,
        "result_json": json.dumps(
            {
                "public_product_type": "video_ai_real",
                "addon_application": {
                    "requested": ["music", "transitions"],
                    "applied": ["music", "transitions"],
                    "missing": [],
                },
            },
            ensure_ascii=False,
        ),
    }

    data = bot.product_video_delivery_report_data(
        project,
        job,
        {"ok": True, "charged_xu": 0, "charge_skip_reason": "admin_owner_free"},
    )
    text = bot.product_video_delivery_report_text(data)

    assert data == {
        "product_label": "Video AI chân thật",
        "quality_label": "Nhanh gọn · 8 giây/cảnh",
        "scene_count": 2,
        "duration_seconds": 16,
        "ratio": "9:16",
        "video_price_xu": 144,
        "selected_addon_count": 2,
        "free_addon_count": 1,
        "paid_addon_count": 1,
        "applied_addon_count": 2,
        "addon_total_xu": 10,
        "invoice_total_xu": 154,
        "charged_xu": 0,
        "delivery_status": "Đã gửi video thành công",
    }
    for expected in (
        "✅ Video đã hoàn tất",
        "Sản phẩm: Video AI chân thật",
        "Chất lượng: Nhanh gọn · 8 giây/cảnh",
        "Video: 2 cảnh · 16 giây · 9:16",
        "Giá video: 144 Xu",
        "Add-on đã chọn: 2 mục",
        "Miễn phí: 1 · Có phí: 1",
        "Add-on đã áp dụng: 2/2",
        "Phí Add-on: 10 Xu",
        "Tổng hóa đơn: 154 Xu",
        "Xu thực trả: 0 Xu",
        "Trạng thái: Đã gửi video thành công",
    ):
        assert expected in text
    forbidden = (
        "provider",
        "worker",
        "job id",
        "task id",
        "sha",
        "manifest",
        "json",
        "engine route",
        "internal",
    )
    assert not any(token in text.lower() for token in forbidden)


@pytest.mark.parametrize(
    ("runtime_product_type", "public_label"),
    [
        ("trend_video", "Video theo trend"),
        ("video_ai_prompt", "Video AI chân thật"),
        ("video_ai_image", "Video AI chân thật"),
        ("video_ai_video_reference", "Video AI chân thật"),
    ],
)
def test_customer_delivery_report_maps_runtime_product_alias_to_public_label(
    runtime_product_type: str,
    public_label: str,
) -> None:
    project = {
        "ratio": "9:16",
        "quality_tier": 400,
        "scene_count": 2,
        "invoice_json": json.dumps(_invoice(), ensure_ascii=False),
        "addon_plan_json": json.dumps(_strict_addon_plan(), ensure_ascii=False),
    }
    job = {
        "result_json": json.dumps(
            {
                "public_product_type": runtime_product_type,
                "addon_application": {
                    "requested": ["transitions"],
                    "applied": ["transitions"],
                },
            },
            ensure_ascii=False,
        )
    }

    data = bot.product_video_delivery_report_data(
        project,
        job,
        {"charged_xu": 0},
    )

    assert data["product_label"] == public_label
    assert runtime_product_type not in bot.product_video_delivery_report_text(data)


@pytest.mark.parametrize(
    "protected_product_type",
    ["video_local_edit", "multi_scene_film", "video_long", "long_video"],
)
def test_customer_delivery_report_skips_owner_protected_products_before_db_claim(
    monkeypatch,
    protected_product_type: str,
) -> None:
    completion = {
        "ok": True,
        "job": {
            "id": 19,
            "result_json": json.dumps(
                {"public_product_type": protected_product_type},
                ensure_ascii=False,
            ),
        },
        "project": {"project_id": 23, "user_id": "7126457028"},
    }
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=object()))
    monkeypatch.setattr(
        bot,
        "db_connect",
        lambda: (_ for _ in ()).throw(AssertionError("protected report must not claim DB")),
    )

    report = asyncio.run(
        bot.maybe_send_product_video_delivery_report(
            completion,
            {"ok": True, "sent": True},
            {"ok": True, "charged_xu": 0},
        )
    )

    assert report == {
        "sent": False,
        "reason": "report_not_applicable",
    }


@pytest.mark.parametrize("profile_id", ["video_local_edit", "multi_scene_film"])
def test_delivery_report_product_type_falls_back_to_protected_project_profile(
    profile_id: str,
) -> None:
    assert bot.product_video_delivery_report_product_type(
        {"profile_id": profile_id},
        {"result_json": "{}"},
    ) == profile_id


def test_worker_completion_orders_report_after_receipt_and_settlement(monkeypatch) -> None:
    calls = []
    completion = {
        "ok": True,
        "job": {"id": 19, "job_type": queue.VIDEO_RENDER_JOB_TYPE, "result_json": "{}"},
        "project": {"project_id": 23, "user_id": "7126457028"},
    }

    class FakeConn:
        def close(self):
            return None

    async def deliver(_result):
        calls.append("delivery")
        return {"sent": True, "telegram_message_id": "903"}

    def note_delivery(_conn, **_kwargs):
        calls.append("receipt")
        return {"ok": True, "sent": True}

    def settle(_job_id, **_kwargs):
        calls.append("settlement")
        return {"ok": True, "charged_xu": 0, "charge_after_delivery_attempted": True}

    async def report(_result, _receipt, _settlement):
        calls.append("report")
        return {"sent": True, "telegram_message_id": "904"}

    monkeypatch.setattr(bot, "verify_remote_worker_api_access", lambda _request: None)
    monkeypatch.setattr(
        bot,
        "_record_owner_product_video_worker_identity",
        lambda *_args, **_kwargs: {"owner_heartbeat_request_received": False},
    )
    monkeypatch.setattr(bot, "db_connect", lambda: FakeConn())
    monkeypatch.setattr(
        bot.remote_worker_api,
        "complete_remote_worker_job",
        lambda *_args, **_kwargs: completion,
    )
    monkeypatch.setattr(bot, "maybe_send_remote_worker_final_video", deliver)
    monkeypatch.setattr(bot.video_project_queue, "note_video_delivery_result", note_delivery)
    monkeypatch.setattr(bot, "product_video_charge_after_final_delivery", settle)
    monkeypatch.setattr(
        bot,
        "maybe_send_product_video_delivery_report",
        report,
        raising=False,
    )

    response = TestClient(bot.fastapi_app).post(
        "/api/v1/worker/complete",
        json={"worker_id": "vps-toanaas-01", "job_id": 19, "result": {}},
    )

    assert response.status_code == 200
    assert calls == ["delivery", "receipt", "settlement", "report"]
    assert response.json()["delivery_report"]["sent"] is True


def test_customer_delivery_report_is_persisted_and_not_sent_twice(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "delivery-report.db"

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    conn = connect()
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=7126457028,
        ratio="9:16",
        asset_pack={"source": "product_video", "product_type": "video_ai_real"},
    )
    project_id = int(project["project_id"])
    queue.update_video_project(
        conn,
        project_id,
        addon_plan_json=_strict_addon_plan(),
        invoice_json=_invoice(),
        quality_tier=400,
        scene_count=2,
        total_xu_estimated=144,
        video_delivered_at="2026-08-28 10:30:00",
        video_delivery_message_id="900",
        video_success_message_id="900",
        video_terminal_state="final_delivered",
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=project_id,
        user_id=7126457028,
    )
    job_id = int(job["id"])
    result_payload = {
        "public_product_type": "video_ai_real",
        "charge_after_delivery_attempted": True,
        "charged_xu": 0,
        "charge_skip_reason": "admin_owner_free",
        "addon_application": {
            "requested": ["transitions"],
            "applied": ["transitions"],
            "missing": [],
        },
    }
    conn.execute(
        "UPDATE video_jobs SET status='completed',result_json=? WHERE id=?",
        (json.dumps(result_payload, ensure_ascii=False), job_id),
    )
    conn.commit()
    completion = {
        "ok": True,
        "job": queue.get_video_render_job(conn, job_id),
        "project": queue.get_video_project(conn, project_id),
    }
    conn.close()

    messages = []

    class FakeBot:
        async def send_message(self, *, chat_id, text):
            messages.append((chat_id, text))
            return SimpleNamespace(message_id=901)

    monkeypatch.setattr(bot, "db_connect", connect)
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=FakeBot()))

    first = asyncio.run(
        bot.maybe_send_product_video_delivery_report(
            completion,
            {"ok": True, "sent": True},
            {"ok": True, "charged_xu": 0, "charge_after_delivery_attempted": True},
        )
    )
    second = asyncio.run(
        bot.maybe_send_product_video_delivery_report(
            completion,
            {"ok": True, "sent": True},
            {"ok": True, "charged_xu": 0, "charge_after_delivery_attempted": True},
        )
    )

    assert first["sent"] is True
    assert first["telegram_message_id"] == "901"
    assert second["sent"] is False
    assert second["duplicate_prevented"] is True
    assert len(messages) == 1
    conn = connect()
    stored = json.loads(queue.get_video_render_job(conn, job_id)["result_json"])
    conn.close()
    assert stored["delivery_report_sent"] is True
    assert stored["delivery_report_message_id"] == "901"


def test_duplicate_worker_completion_retries_only_missing_report(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "duplicate-report-retry.db"

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    conn = connect()
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=7126457028,
        ratio="9:16",
        asset_pack={"source": "product_video", "product_type": "video_ai_real"},
    )
    project_id = int(project["project_id"])
    queue.update_video_project(
        conn,
        project_id,
        addon_plan_json=_strict_addon_plan(),
        invoice_json=_invoice(),
        quality_tier=400,
        scene_count=2,
        total_xu_estimated=144,
        video_delivered_at="2026-08-28 10:30:00",
        video_delivery_message_id="900",
        video_success_message_id="900",
        video_terminal_state="final_delivered",
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=project_id,
        user_id=7126457028,
    )
    job_id = int(job["id"])
    conn.execute(
        "UPDATE video_jobs SET status='completed',result_json=? WHERE id=?",
        (
            json.dumps(
                {
                    "public_product_type": "video_ai_real",
                    "charge_after_delivery_attempted": True,
                    "charged_xu": 0,
                    "charge_skip_reason": "admin_owner_free",
                    "addon_application": {
                        "requested": ["transitions"],
                        "applied": ["transitions"],
                    },
                },
                ensure_ascii=False,
            ),
            job_id,
        ),
    )
    conn.commit()
    completion = {
        "ok": True,
        "duplicate": True,
        "job": queue.get_video_render_job(conn, job_id),
        "project": queue.get_video_project(conn, project_id),
    }
    conn.close()
    messages = []

    class FakeBot:
        async def send_message(self, *, chat_id, text):
            messages.append((chat_id, text))
            return SimpleNamespace(message_id=901)

    monkeypatch.setattr(bot, "verify_remote_worker_api_access", lambda _request: None)
    monkeypatch.setattr(
        bot,
        "_record_owner_product_video_worker_identity",
        lambda *_args, **_kwargs: {"owner_heartbeat_request_received": False},
    )
    monkeypatch.setattr(bot, "db_connect", connect)
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=FakeBot()))
    monkeypatch.setattr(
        bot.remote_worker_api,
        "complete_remote_worker_job",
        lambda *_args, **_kwargs: completion,
    )
    settlement_calls = []
    monkeypatch.setattr(
        bot,
        "product_video_charge_after_final_delivery",
        lambda *_args, **_kwargs: settlement_calls.append(True),
    )

    first = TestClient(bot.fastapi_app).post(
        "/api/v1/worker/complete",
        json={"worker_id": "vps-toanaas-01", "job_id": job_id, "result": {}},
    )
    second = TestClient(bot.fastapi_app).post(
        "/api/v1/worker/complete",
        json={"worker_id": "vps-toanaas-01", "job_id": job_id, "result": {}},
    )

    assert first.status_code == 200
    assert first.json()["delivery"]["duplicate_prevented"] is True
    assert first.json()["delivery_report"]["sent"] is True
    assert second.json()["delivery_report"]["duplicate_prevented"] is True
    assert len(messages) == 1
    assert settlement_calls == []


def test_report_failure_does_not_reverse_delivery_or_repeat_settlement(monkeypatch) -> None:
    calls = []
    completion = {
        "ok": True,
        "job": {"id": 19, "job_type": queue.VIDEO_RENDER_JOB_TYPE, "result_json": "{}"},
        "project": {"project_id": 23, "user_id": "7126457028"},
    }

    class FakeConn:
        def close(self):
            return None

    monkeypatch.setattr(bot, "verify_remote_worker_api_access", lambda _request: None)
    monkeypatch.setattr(
        bot,
        "_record_owner_product_video_worker_identity",
        lambda *_args, **_kwargs: {"owner_heartbeat_request_received": False},
    )
    monkeypatch.setattr(bot, "db_connect", lambda: FakeConn())
    monkeypatch.setattr(
        bot.remote_worker_api,
        "complete_remote_worker_job",
        lambda *_args, **_kwargs: completion,
    )
    monkeypatch.setattr(
        bot,
        "maybe_send_remote_worker_final_video",
        lambda _result: asyncio.sleep(
            0,
            result={"sent": True, "telegram_message_id": "903"},
        ),
    )
    monkeypatch.setattr(
        bot.video_project_queue,
        "note_video_delivery_result",
        lambda *_args, **_kwargs: {"ok": True, "sent": True},
    )

    def settle(_job_id, **_kwargs):
        calls.append("settlement")
        return {"ok": True, "charged_xu": 0, "charge_after_delivery_attempted": True}

    async def report(*_args, **_kwargs):
        return {"sent": False, "reason": "TimedOut"}

    monkeypatch.setattr(bot, "product_video_charge_after_final_delivery", settle)
    monkeypatch.setattr(
        bot,
        "maybe_send_product_video_delivery_report",
        report,
        raising=False,
    )

    response = TestClient(bot.fastapi_app).post(
        "/api/v1/worker/complete",
        json={"worker_id": "vps-toanaas-01", "job_id": 19, "result": {}},
    )

    assert response.status_code == 200
    assert response.json()["delivery_receipt"]["sent"] is True
    assert response.json()["delivery_settlement"]["charged_xu"] == 0
    assert response.json()["delivery_report"] == {"sent": False, "reason": "TimedOut"}
    assert calls == ["settlement"]


def test_report_exception_is_best_effort_after_durable_delivery(monkeypatch) -> None:
    completion = {
        "ok": True,
        "job": {"id": 19, "job_type": queue.VIDEO_RENDER_JOB_TYPE, "result_json": "{}"},
        "project": {"project_id": 23, "user_id": "7126457028"},
    }

    class FakeConn:
        def close(self):
            return None

    monkeypatch.setattr(bot, "verify_remote_worker_api_access", lambda _request: None)
    monkeypatch.setattr(
        bot,
        "_record_owner_product_video_worker_identity",
        lambda *_args, **_kwargs: {"owner_heartbeat_request_received": False},
    )
    monkeypatch.setattr(bot, "db_connect", lambda: FakeConn())
    monkeypatch.setattr(
        bot.remote_worker_api,
        "complete_remote_worker_job",
        lambda *_args, **_kwargs: completion,
    )
    monkeypatch.setattr(
        bot,
        "maybe_send_remote_worker_final_video",
        lambda _result: asyncio.sleep(
            0,
            result={"sent": True, "telegram_message_id": "903"},
        ),
    )
    monkeypatch.setattr(
        bot.video_project_queue,
        "note_video_delivery_result",
        lambda *_args, **_kwargs: {"ok": True, "sent": True},
    )
    monkeypatch.setattr(
        bot,
        "product_video_charge_after_final_delivery",
        lambda *_args, **_kwargs: {
            "ok": True,
            "charged_xu": 0,
            "charge_after_delivery_attempted": True,
        },
    )

    async def report(*_args, **_kwargs):
        raise RuntimeError("report_storage_unavailable")

    monkeypatch.setattr(bot, "maybe_send_product_video_delivery_report", report)

    response = TestClient(bot.fastapi_app).post(
        "/api/v1/worker/complete",
        json={"worker_id": "vps-toanaas-01", "job_id": 19, "result": {}},
    )

    assert response.status_code == 200
    assert response.json()["delivery_receipt"]["sent"] is True
    assert response.json()["delivery_settlement"]["charged_xu"] == 0
    assert response.json()["delivery_report"] == {
        "sent": False,
        "reason": "RuntimeError",
    }
