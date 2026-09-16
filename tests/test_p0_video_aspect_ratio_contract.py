import sqlite3
import json
import pytest
from providers.video_generic_http_provider import _shopaikey_wire_payload, _key4u_wire_payload
import services.video_final_output as vfo
from services.video_project_queue import (
    ensure_video_project_queue_schema,
    complete_video_job,
    get_video_project,
    get_video_render_job,
)


def test_shopaikey_wire_payload_maps_9_16_to_aspect_ratio():
    payload = {"model": "veo3.1-fast", "prompt": "a cinematic video", "ratio": "9:16"}
    wire = _shopaikey_wire_payload(payload)
    assert wire["aspect_ratio"] == "9:16"
    assert wire["aspectRatio"] == "9:16"


def test_shopaikey_wire_payload_maps_16_9_to_aspect_ratio():
    payload = {"model": "veo3.1-fast", "prompt": "a landscape video", "ratio": "16:9"}
    wire = _shopaikey_wire_payload(payload)
    assert wire["aspect_ratio"] == "16:9"
    assert wire["aspectRatio"] == "16:9"


def test_shopaikey_wire_payload_preserves_canonical_ratio():
    payload_9_16 = {"model": "veo3.1-fast", "prompt": "test", "ratio": "9:16"}
    wire_9_16 = _shopaikey_wire_payload(payload_9_16)
    assert wire_9_16["ratio"] == "9:16"
    assert wire_9_16["aspect_ratio"] == "9:16"

    payload_16_9 = {"model": "veo3.1-fast", "prompt": "test", "ratio": "16:9"}
    wire_16_9 = _shopaikey_wire_payload(payload_16_9)
    assert wire_16_9["ratio"] == "16:9"
    assert wire_16_9["aspect_ratio"] == "16:9"


def test_key4u_9_16_ratio_mapping_regression():
    payload = {
        "metadata": {
            "selected_family": "google_veo",
            "provider_submit_url_override": "https://api.key4u.vn/v1/video/create",
        },
        "prompt": "test",
        "ratio": "9:16",
        "model": "veo3.1",
    }
    wire = _key4u_wire_payload(payload)
    assert wire["aspect_ratio"] == "9:16"


def test_key4u_16_9_ratio_mapping_regression():
    payload = {
        "metadata": {
            "selected_family": "google_veo",
            "provider_submit_url_override": "https://api.key4u.vn/v1/video/create",
        },
        "prompt": "test",
        "ratio": "16:9",
        "model": "veo3.1",
    }
    wire = _key4u_wire_payload(payload)
    assert wire["aspect_ratio"] == "16:9"


def test_requested_9_16_accepts_portrait_equivalent_geometry(monkeypatch):
    monkeypatch.setattr(
        vfo,
        "probe_video",
        lambda path, **_k: {
            "ok": True,
            "path": path,
            "bytes": 10240,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
            "width": 720,
            "height": 1280,
        },
    )
    res = vfo.validate_final_video_output(
        path="/fake/video.mp4",
        result={"ratio": "9:16", "visual_classification": "final_ai_video"},
    )
    assert res["ok"] is True
    assert res.get("terminal_state") == "final_delivered"


def test_requested_16_9_accepts_landscape_equivalent_geometry(monkeypatch):
    monkeypatch.setattr(
        vfo,
        "probe_video",
        lambda path, **_k: {
            "ok": True,
            "path": path,
            "bytes": 10240,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
            "width": 1280,
            "height": 720,
        },
    )
    res = vfo.validate_final_video_output(
        path="/fake/video.mp4",
        result={"ratio": "16:9", "visual_classification": "final_ai_video"},
    )
    assert res["ok"] is True
    assert res.get("terminal_state") == "final_delivered"


def test_requested_9_16_rejects_landscape_output(monkeypatch):
    monkeypatch.setattr(
        vfo,
        "probe_video",
        lambda path, **_k: {
            "ok": True,
            "path": path,
            "bytes": 10240,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
            "width": 1280,
            "height": 720,
        },
    )
    res = vfo.validate_final_video_output(
        path="/fake/video.mp4",
        result={"ratio": "9:16", "visual_classification": "final_ai_video"},
    )
    assert res["ok"] is False
    assert res["reason"] == "geometry_mismatch_rejected"
    assert res["geometry_orientation"] == "landscape"
    assert res["expected_orientation"] == "portrait"


def test_requested_16_9_rejects_portrait_output(monkeypatch):
    monkeypatch.setattr(
        vfo,
        "probe_video",
        lambda path, **_k: {
            "ok": True,
            "path": path,
            "bytes": 10240,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
            "width": 720,
            "height": 1280,
        },
    )
    res = vfo.validate_final_video_output(
        path="/fake/video.mp4",
        result={"ratio": "16:9", "visual_classification": "final_ai_video"},
    )
    assert res["ok"] is False
    assert res["reason"] == "geometry_mismatch_rejected"
    assert res["geometry_orientation"] == "portrait"
    assert res["expected_orientation"] == "landscape"


def _setup_test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_video_project_queue_schema(conn)
    asset_pack = json.dumps({"source": "product_video", "render_mode": "real", "provider_call": True})
    conn.execute(
        """INSERT INTO video_projects (
            project_id, user_id, status, ratio, total_xu_estimated, is_confirmed, asset_pack_json
        ) VALUES (
            1, 7126457028, 'processing', '9:16', 80, 1, ?
        )""",
        (asset_pack,),
    )
    conn.execute(
        """INSERT INTO video_jobs (
            id, project_id, status, attempts, max_attempts, progress_percent
        ) VALUES (
            1, 1, 'processing', 1, 3, 50
        )"""
    )
    conn.commit()
    return conn


def test_geometry_mismatch_blocks_success_delivery(monkeypatch):
    conn = _setup_test_db()
    monkeypatch.setattr(
        vfo,
        "probe_video",
        lambda path, **_k: {
            "ok": True,
            "path": path,
            "bytes": 10240,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
            "width": 1280,
            "height": 720,
        },
    )
    res = complete_video_job(
        conn,
        job_id=1,
        final_video_path="/fake/job18_landscape.mp4",
        result={"ratio": "9:16", "visual_classification": "final_ai_video"},
    )
    assert res.get("status") == "failed"
    project = get_video_project(conn, 1)
    assert project["status"] == "failed"
    assert project["video_delivered_at"] is None
    assert project["video_delivery_message_id"] is None


def test_geometry_mismatch_blocks_success_receipt(monkeypatch):
    conn = _setup_test_db()
    monkeypatch.setattr(
        vfo,
        "probe_video",
        lambda path, **_k: {
            "ok": True,
            "path": path,
            "bytes": 10240,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
            "width": 1280,
            "height": 720,
        },
    )
    res = complete_video_job(
        conn,
        job_id=1,
        final_video_path="/fake/job18_landscape.mp4",
        result={"ratio": "9:16", "visual_classification": "final_ai_video"},
    )
    assert res.get("status") == "failed"
    project = get_video_project(conn, 1)
    assert project["video_success_message_id"] is None
    assert project["video_terminal_state"] == "failed_no_charge"


def test_geometry_mismatch_blocks_charge(monkeypatch):
    conn = _setup_test_db()
    monkeypatch.setattr(
        vfo,
        "probe_video",
        lambda path, **_k: {
            "ok": True,
            "path": path,
            "bytes": 10240,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
            "width": 1280,
            "height": 720,
        },
    )
    res = complete_video_job(
        conn,
        job_id=1,
        final_video_path="/fake/job18_landscape.mp4",
        result={"ratio": "9:16", "visual_classification": "final_ai_video"},
    )
    assert res.get("status") == "failed"
    job = get_video_render_job(conn, 1)
    payload = json.loads(job["result_json"] or "{}")
    assert payload.get("terminal_state") == "failed_no_charge"
    assert payload.get("wallet_charge_recorded") is not True
    assert payload.get("charge") in (None, 0)


def test_geometry_mismatch_does_not_resubmit_provider(monkeypatch):
    conn = _setup_test_db()
    monkeypatch.setattr(
        vfo,
        "probe_video",
        lambda path, **_k: {
            "ok": True,
            "path": path,
            "bytes": 10240,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
            "width": 1280,
            "height": 720,
        },
    )
    res = complete_video_job(
        conn,
        job_id=1,
        final_video_path="/fake/job18_landscape.mp4",
        result={"ratio": "9:16", "visual_classification": "final_ai_video"},
    )
    assert res.get("status") == "failed"
    job = get_video_render_job(conn, 1)
    assert job["status"] == "failed"
    assert job["attempts"] == 1
    assert job["last_error"] == "geometry_mismatch_rejected"
