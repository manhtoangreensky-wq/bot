from __future__ import annotations

import io
import json
import shutil
import socket
import sqlite3
import subprocess
import urllib.error
from pathlib import Path

import pytest

import local_worker
from services import video_edit_media_transport, video_editengine1
from services import video_local_editing as editing
from services import video_local_validation as validation
from services import video_tail9


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
WORKER_SOURCE = (ROOT / "local_worker.py").read_text(encoding="utf-8")


def _conn(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path) if path else ":memory:")
    conn.execute(
        """CREATE TABLE local_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            command TEXT,
            job_type TEXT,
            status TEXT,
            provider TEXT,
            input_file_id TEXT,
            created_at TEXT,
            xu_cost INTEGER,
            admin_only INTEGER,
            updated_at TEXT
        )"""
    )
    return conn


def _state(*, brightness: object = 100) -> dict:
    return {
        "source_file_id": "telegram-file",
        "inspection_complete": True,
        "source_metadata": {"ok": True, "duration_ms": 4_000, "has_audio": True},
        "selected_tool": "manual",
        "manual_edit_plan": {
            "source": "source.mp4",
            "trim": {"start_ms": 0, "end_ms": 4_000},
            "brightness_percent": brightness,
        },
        "video_tail9": {"audio_config": {}},
    }


def _runtime(**overrides) -> dict:
    value = {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": True,
        "ffmpeg_path_configured": True,
        "ffprobe_path_configured": True,
        "delivery_configured": True,
        "worker_id": "worker-edit-1",
        "heartbeat_age_seconds": 3,
    }
    value.update(overrides)
    return value


def _create(conn: sqlite3.Connection, *, session: str = "edit-session-1") -> dict:
    state = _state(brightness=120)
    return video_editengine1.create_job(
        conn,
        user_id=77,
        chat_id=88,
        edit_session_id=session,
        source_file_id=state["source_file_id"],
        source_metadata=state["source_metadata"],
        plan=state["manual_edit_plan"],
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 100}},
        quality_tier_id="300",
        price_xu=100,
        worker_payload={
            "source_file_id": state["source_file_id"],
            "source_file_name": "input.mp4",
            "source_video_hash": "c" * 64,
            "manual_edit_plan": state["manual_edit_plan"],
            "provider_call": False,
            "charge_policy": "after_valid_mp4_delivery",
            "price_xu": 100,
            "quoted_price_xu": 100,
        },
    )


def _receipt() -> dict:
    return {
        "delivery_message_id": "9001",
        "delivery_file_id": "telegram-output-file",
        "source_video_path": "source.mp4",
        "source_sha256": "c" * 64,
        "output_path": "toan_aas_video_edit_1.mp4",
        "output_sha256": "b" * 64,
        "output_size_bytes": 4096,
        "ffprobe": {
            "ok": True,
            "has_video": True,
            "has_audio": True,
            "video_codec": "h264",
            "audio_codec": "aac",
            "duration_ms": 4_000,
            "width": 640,
            "height": 360,
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "full_decode": True,
        },
        "output_count": 1,
        "charge_policy": "after_valid_mp4_delivery",
        "charge_status": "pending_post_delivery",
        "charged_xu": 0,
    }


def _multi_receipt(*, second_full_decode: bool) -> dict:
    first_probe = dict(_receipt()["ffprobe"])
    second_probe = {**first_probe, "full_decode": second_full_decode}
    artifacts = [
        {
            "index": 1,
            "message_id": "9101",
            "file_id": "telegram-part-1",
            "size": 2048,
            "sha256": "d" * 64,
            "ffprobe": first_probe,
        },
        {
            "index": 2,
            "message_id": "9102",
            "file_id": "telegram-part-2",
            "size": 2048,
            "sha256": "e" * 64,
            "ffprobe": second_probe,
        },
    ]
    return {
        **_receipt(),
        "delivery_message_id": artifacts[0]["message_id"],
        "delivery_file_id": artifacts[0]["file_id"],
        "output_path": "part-1.mp4,part-2.mp4",
        "output_size_bytes": 4096,
        "output_count": 2,
        "artifacts": artifacts,
    }


def _manual_command(tmp_path: Path, brightness: int, *, audio: bool = True) -> list[str]:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    plan = editing.default_manual_edit_plan(str(source))
    plan["trim"] = {"start_ms": 0, "end_ms": 4_000}
    plan["brightness_percent"] = brightness
    return editing.build_manual_ffmpeg_command(
        plan,
        output_path=str(tmp_path / f"output-{brightness}.mp4"),
        source_probe={
            "ok": True,
            "duration": 4.0,
            "duration_ms": 4_000,
            "width": 640,
            "height": 360,
            "fps": 24.0,
            "has_video": True,
            "has_audio": audio,
        },
        ffmpeg_path="ffmpeg",
    )


def test_editengine1_preflight_reports_exact_healthy_route() -> None:
    result = video_editengine1.preflight(_state(), _runtime())
    assert result == {
        "ok": True,
        "ready": True,
        "reason": "ok",
        "blocker": "",
        "checks": {
            "source_file": True,
            "source_probe": True,
            "operation": True,
            "brightness": True,
            "worker_enabled": True,
            "poll_enabled": True,
            "token_configured": True,
            "heartbeat": True,
            "ffmpeg": True,
            "ffprobe": True,
            "delivery": True,
        },
        "unsupported_addons": [],
        "product_type": "video_edit",
        "worker_job_type": "video_local_edit",
        "engine_route": "local_worker_ffmpeg",
        "owner": "local_video_edit",
        "queue": "local_worker_jobs",
        "worker_id": "worker-edit-1",
        "heartbeat_age_seconds": 3,
    }


def test_editengine1_tail_aliases_share_one_local_ffmpeg_adapter() -> None:
    persisted = video_tail9.new_state(product_type="video_edit", session_id="edit-persisted")
    public = video_tail9.new_state(product_type="video_local_edit", session_id="edit-public")
    for state in (persisted, public):
        assert state["engine_route"] == "local_worker_ffmpeg"
        assert state["video_flow_owner"] == "video_edit"
        assert state["audio_config"]["source_audio_available"] is True
        assert video_tail9.adapter_for(state["video_product_type"])["executor_product_type"] == "video_local_edit"
    assert persisted["video_product_type"] == "video_edit"
    assert public["video_product_type"] == "video_local_edit"


def test_editengine1_bot_preflight_dispatches_both_current_and_legacy_edit_ids() -> None:
    start = BOT_SOURCE.index("def video_tail9_preflight")
    end = BOT_SOURCE.index("def video_tail9_review_text", start)
    source = BOT_SOURCE[start:end]
    assert "video_editengine1.PRODUCT_TYPE" in source
    assert "video_editengine1.WORKER_JOB_TYPE" in source
    assert source.index("video_editengine1.preflight(") < source.index("video_flow6_preflight_for_state(")


@pytest.mark.parametrize(
    ("state", "runtime", "reason"),
    [
        (_state(brightness=19), _runtime(), "brightness_invalid"),
        (_state(brightness=201), _runtime(), "brightness_invalid"),
        (_state(brightness="invalid"), _runtime(), "brightness_invalid"),
        (_state(), _runtime(connected=False), "local_worker_heartbeat_stale"),
        (_state(), _runtime(ffmpeg_path_configured=False), "ffmpeg_missing"),
        (_state(), _runtime(ffprobe_path_configured=False), "ffprobe_missing"),
        (_state(), _runtime(delivery_configured=False), "telegram_delivery_unavailable"),
    ],
)
def test_editengine1_preflight_exact_blockers(state: dict, runtime: dict, reason: str) -> None:
    result = video_editengine1.preflight(state, runtime)
    assert result["ok"] is False
    assert result["reason"] == reason
    assert result["blocker"] == reason


def test_editengine1_preflight_rejects_unimplemented_addons_without_provider_call() -> None:
    state = _state()
    state["video_tail9"] = {"audio_config": {"music": True}}
    result = video_editengine1.preflight(state, _runtime())
    assert result["reason"] == "local_edit_addon_runtime_unavailable"
    assert result["unsupported_addons"] == ["music"]


def test_editengine1_final_confirm_is_idempotent_and_persists_owner_truth() -> None:
    conn = _conn()
    first = _create(conn)
    conn.commit()
    second = _create(conn)
    conn.commit()

    assert first["created"] is True
    assert second == {**first, "created": False}
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_edit_outbox").fetchone()[0] == 1
    job = video_editengine1.get_job_by_worker_id(conn, first["local_worker_job_id"])
    assert job["product_type"] == "video_edit"
    assert job["worker_job_type"] == "video_local_edit"
    assert job["engine_route"] == "local_worker_ffmpeg"
    assert job["worker_owner"] == "local_video_edit"
    assert job["source_video_path"] == "input.mp4"
    assert job["source_sha256"] == "c" * 64


def test_editengine1_second_connection_reuses_same_job_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "edit.db"
    first_conn = _conn(database)
    first = _create(first_conn)
    first_conn.commit()
    first_conn.close()

    second_conn = sqlite3.connect(database)
    second = _create(second_conn)
    second_conn.commit()
    assert second["created"] is False
    assert second["local_worker_job_id"] == first["local_worker_job_id"]
    assert second_conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1


def test_editengine1_success_requires_valid_delivery_receipt() -> None:
    conn = _conn()
    created = _create(conn)
    conn.commit()
    job = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt={},
    )
    conn.commit()
    assert job["status"] == "failed_no_charge"
    assert job["blocker"] == "delivery_receipt_invalid"
    assert job["receipt_state"] == "not_created"
    assert job["charge_state"] == "not_charged"
    assert job["charged_xu"] == 0


def test_editengine1_metadata_valid_decode_failed_receipt_never_becomes_delivered() -> None:
    conn = _conn()
    created = _create(conn)
    receipt = _receipt()
    receipt["ffprobe"] = {**receipt["ffprobe"], "full_decode": False}

    job = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=receipt,
    )

    assert job["status"] == "failed_no_charge"
    assert job["blocker"] == "delivery_receipt_invalid"
    assert job["receipt_state"] == "not_created"
    assert job["charge_state"] == "not_charged"
    assert job["charged_xu"] == 0


def test_editengine1_charge_claim_rechecks_full_decode_evidence() -> None:
    conn = _conn()
    created = _create(conn)
    worker_job_id = created["local_worker_job_id"]
    delivered = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=_receipt(),
    )
    assert delivered["status"] == "delivered"
    decode_failed = {**delivered["ffprobe"], "full_decode": False}
    conn.execute(
        "UPDATE video_edit_jobs SET ffprobe_json=?,charge_state='not_charged' "
        "WHERE local_worker_job_id=?",
        (json.dumps(decode_failed, ensure_ascii=False), worker_job_id),
    )

    assert video_editengine1.claim_charge(conn, worker_job_id=worker_job_id) is False
    assert conn.execute(
        "SELECT charge_state FROM video_edit_jobs WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone()[0] == "not_charged"


def test_editengine1_multi_artifact_decode_failure_never_becomes_delivered() -> None:
    conn = _conn()
    created = _create(conn)

    job = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=_multi_receipt(second_full_decode=False),
    )

    assert job["status"] == "failed_no_charge"
    assert job["blocker"] == "delivery_receipt_invalid"
    assert job["receipt_state"] == "not_created"
    assert job["charge_state"] == "not_charged"


def test_editengine1_multi_artifact_charge_rechecks_every_full_decode() -> None:
    conn = _conn()
    created = _create(conn)
    worker_job_id = created["local_worker_job_id"]
    delivered = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=_multi_receipt(second_full_decode=True),
    )
    assert delivered["status"] == "delivered"
    artifacts = list(delivered["artifact_receipts"])
    artifacts[1] = {
        **artifacts[1],
        "ffprobe": {**artifacts[1]["ffprobe"], "full_decode": False},
    }
    conn.execute(
        "UPDATE video_edit_jobs SET artifact_receipts_json=?,charge_state='not_charged' "
        "WHERE local_worker_job_id=?",
        (json.dumps(artifacts, ensure_ascii=False), worker_job_id),
    )

    assert video_editengine1.claim_charge(conn, worker_job_id=worker_job_id) is False
    assert conn.execute(
        "SELECT charge_state FROM video_edit_jobs WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone()[0] == "not_charged"


def test_editengine1_delivery_receipt_and_charge_are_once_only() -> None:
    conn = _conn()
    created = _create(conn)
    conn.commit()
    worker_job_id = created["local_worker_job_id"]
    rendered = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="running",
        detail={"stage": "processing_video"},
        receipt={},
    )
    assert rendered["status"] == "rendering"
    assert rendered["progress_percent"] == 55
    delivered = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=_receipt(),
    )
    conn.commit()
    assert delivered["status"] == "delivered"
    assert delivered["receipt_state"] == "created"
    assert delivered["delivery_message_id"] == "9001"
    assert delivered["output_size_bytes"] == 4096
    assert delivered["output_sha256"] == "b" * 64
    assert delivered["ffprobe"]["video_codec"] == "h264"
    assert video_editengine1.claim_charge(conn, worker_job_id=worker_job_id) is True
    assert video_editengine1.claim_charge(conn, worker_job_id=worker_job_id) is False
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=worker_job_id, ok=True, charged_xu=100)
    conn.commit()
    assert charged["status"] == "charged"
    assert charged["charged_xu"] == 100
    duplicate = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt={**_receipt(), "delivery_message_id": "duplicate"},
    )
    assert duplicate["delivery_message_id"] == "9001"
    assert duplicate["charged_xu"] == 100


def test_editengine1_rejects_a_charge_result_with_the_wrong_amount() -> None:
    conn = _conn()
    created = _create(conn)
    worker_job_id = created["local_worker_job_id"]
    video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=_receipt(),
    )
    assert video_editengine1.claim_charge(conn, worker_job_id=worker_job_id) is True

    result = video_editengine1.mark_charge_result(
        conn,
        worker_job_id=worker_job_id,
        ok=True,
        charged_xu=99,
    )

    assert result["status"] == "delivered"
    assert result["charge_state"] == "charge_failed"
    assert result["charged_xu"] == 0
    assert result["blocker"] == "charge_amount_mismatch"


def test_editengine1_worker_failure_is_terminal_no_charge() -> None:
    conn = _conn()
    created = _create(conn)
    conn.commit()
    failed = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="failed",
        detail={"reason": "ffmpeg_failed"},
        receipt={},
    )
    conn.commit()
    assert failed["status"] == "failed_no_charge"
    assert failed["blocker"] == "ffmpeg_failed"
    assert failed["receipt_state"] == "not_created"
    assert failed["charged_xu"] == 0
    assert conn.execute("SELECT status,terminal_reason FROM video_edit_outbox").fetchone() == (
        "terminal_failed",
        "ffmpeg_failed",
    )


@pytest.mark.parametrize(
    ("percent", "expression"),
    [(20, "eq=brightness=-0.400"), (80, "eq=brightness=-0.100"), (120, "eq=brightness=0.100"), (200, "eq=brightness=0.500")],
)
def test_editengine1_brightness_maps_to_real_ffmpeg_filter(tmp_path: Path, percent: int, expression: str) -> None:
    command = _manual_command(tmp_path, percent)
    joined = " ".join(command)
    assert expression in joined
    assert "libx264" in command
    assert "aac" in command
    assert "-shortest" not in command
    assert command[command.index("-t") + 1] == "4.000"


def test_editengine1_brightness_100_is_unchanged_and_no_audio_is_supported(tmp_path: Path) -> None:
    command = _manual_command(tmp_path, 100, audio=False)
    assert "eq=brightness=" not in " ".join(command)
    assert "-an" in command
    assert "-c:a" not in command
    assert "libx264" in command


def test_editengine1_real_ffmpeg_brightness_preserves_h264_aac_and_duration(tmp_path: Path) -> None:
    ffmpeg = validation.find_ffmpeg()
    ffprobe = validation.find_ffprobe(ffmpeg_path=ffmpeg)
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg/ffprobe unavailable")
    source = tmp_path / "source.mp4"
    fixture = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert fixture.returncode == 0, fixture.stderr[-1200:]
    plan = editing.default_manual_edit_plan(str(source))
    plan["trim"] = {"start_ms": 0, "end_ms": 2_000}
    plan["brightness_percent"] = 200
    output = tmp_path / "brightness-200.mp4"
    result = editing.execute_manual_edit(
        plan,
        output_path=str(output),
        workspace=tmp_path,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=45,
    )
    assert result["ok"] is True
    assert result["validation"]["video_codec"] == "h264"
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 2_000) <= 750
    assert not list(tmp_path.glob("*.partial.mp4"))
    audio_probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(output)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert audio_probe.returncode == 0
    assert audio_probe.stdout.strip() == "aac"


def test_editengine1_worker_renders_and_delivers_one_real_mp4(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ffmpeg = validation.find_ffmpeg()
    ffprobe = validation.find_ffprobe(ffmpeg_path=ffmpeg)
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg/ffprobe unavailable")

    source = tmp_path / "source.mp4"
    fixture = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert fixture.returncode == 0, fixture.stderr[-1200:]

    workspaces = tmp_path / "workspaces"
    updates: list[dict] = []
    deliveries: list[dict] = []

    def fake_download(
        _file_id,
        _file_name,
        workspace,
        _allowed,
        stem,
        **_kwargs,
    ) -> str:
        target = Path(workspace) / f"{stem}{source.suffix}"
        shutil.copyfile(source, target)
        return str(target)

    def fake_delivery(*, chat_id, artifact, caption="", **_kwargs):
        output_path = Path(artifact)
        deliveries.append({"chat_id": chat_id, "output_path": str(output_path), "caption": caption})
        return video_edit_media_transport.DeliveryReceipt(
            message_id="901",
            file_id="telegram-output-901",
            delivery_method="sendVideo",
            bytes_sent=output_path.stat().st_size,
            sha256=local_worker.video_ai_edit_validation.sha256_file(output_path),
        )

    def capture_update(job_id, status: str, error_short: str = "", output_url: str = "", output_file_id: str = "", **_kwargs) -> dict:
        updates.append({
            "job_id": job_id,
            "status": status,
            "detail": error_short,
            "output_url": output_url,
            "output_file_id": output_file_id,
        })
        return {"ok": True}

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: ffmpeg)
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": ffprobe)
    monkeypatch.setattr(
        local_worker,
        "create_video_edit_claim_workspace",
        lambda job_id, claim_attempt: validation.create_video_edit_claim_workspace(
            job_id,
            claim_attempt,
            root=workspaces,
        ),
    )
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "VIDEO_LOCAL_WORKSPACE_ROOT",
        workspaces,
    )
    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "123:test-token")
    monkeypatch.setattr(local_worker, "_video_edit_download_asset", fake_download)
    monkeypatch.setattr(
        video_edit_media_transport,
        "send_artifact_from_path",
        fake_delivery,
    )
    monkeypatch.setattr(local_worker, "update_job", capture_update)
    monkeypatch.setattr(
        local_worker,
        "reconcile_video_edit_cleanup_intent",
        lambda _intent: {"ok": True},
    )

    plan = editing.default_manual_edit_plan("")
    plan["trim"] = {"start_ms": 0, "end_ms": 2_000}
    plan["brightness_percent"] = 120
    local_worker.run_video_local_edit({
        "id": 901,
        "claim_attempt": 1,
        "job_type": video_editengine1.WORKER_JOB_TYPE,
        "user_id": "901",
        "input_file_id": json.dumps({
            "local1_contract": 1,
            "product_type": video_editengine1.PRODUCT_TYPE,
            "engine_route": video_editengine1.ENGINE_ROUTE,
            "worker_owner": video_editengine1.OUTBOX_OWNER,
            "worker_capability": video_editengine1.WORKER_CAPABILITY,
            "local1_mode": "manual",
            "source_file_id": "source-telegram-file",
            "source_file_name": "source.mp4",
            "user_id": "901",
            "chat_id": "88",
            "manual_edit_plan": plan,
            "price_xu": 300,
            "quoted_price_xu": 300,
            "quality_tier_id": "300",
            "charge_policy": "after_valid_mp4_delivery",
            "provider_call": False,
            "max_render_seconds": 45,
            "state_revision": 1,
        }),
    })

    assert len(deliveries) == 1, updates[-1]["detail"]
    terminal = updates[-1]
    assert terminal["status"] == "succeeded"
    assert terminal["output_file_id"] == "telegram-output-901"
    assert json.loads(terminal["detail"])["validation"] == "passed"
    receipt = json.loads(terminal["output_url"])
    assert receipt["delivery_message_id"] == "901"
    assert receipt["delivery_file_id"] == "telegram-output-901"
    assert receipt["ffprobe"]["ok"] is True
    assert receipt["ffprobe"]["video_codec"] == "h264"
    assert receipt["ffprobe"]["has_audio"] is True


def test_editengine1_worker_rejects_wrong_contract_before_download(monkeypatch: pytest.MonkeyPatch) -> None:
    downloads: list[str] = []
    deliveries: list[dict] = []
    updates: list[dict] = []

    monkeypatch.setattr(local_worker, "_video_edit_download_asset", lambda file_id, *_args, **_kwargs: downloads.append(file_id))
    monkeypatch.setattr(
        video_edit_media_transport,
        "send_artifact_from_path",
        lambda *args, **kwargs: deliveries.append({"args": args, "kwargs": kwargs}),
    )
    monkeypatch.setattr(
        local_worker,
        "update_job",
        lambda job_id, status, error_short="", **_kwargs: (
            updates.append(
                {"job_id": job_id, "status": status, "detail": error_short}
            )
            or {"ok": True}
        ),
    )
    monkeypatch.setattr(
        local_worker,
        "reconcile_video_edit_cleanup_intent",
        lambda _intent: {"ok": True},
    )

    local_worker.run_video_local_edit({
        "id": 902,
        "claim_attempt": 1,
        "job_type": video_editengine1.WORKER_JOB_TYPE,
        "input_file_id": json.dumps({
            "local1_contract": 1,
            "product_type": "frame_video",
            "engine_route": video_editengine1.ENGINE_ROUTE,
            "worker_owner": video_editengine1.OUTBOX_OWNER,
            "worker_capability": video_editengine1.WORKER_CAPABILITY,
            "source_file_id": "wrong-source",
            "chat_id": "88",
        }),
    })

    assert downloads == []
    assert deliveries == []
    assert len(updates) == 1
    assert updates[0]["job_id"] == 902
    assert updates[0]["status"] == "failed"
    receipt = json.loads(updates[0]["detail"])
    assert receipt["reason"] == "video_local_edit_contract_product_type"
    assert receipt["charge"] == 0


def test_editengine1_worker_dispatches_only_to_its_local_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[dict] = []
    monkeypatch.setattr(local_worker, "run_video_local_edit", lambda job: received.append(job))

    local_worker.process_job({"id": 902, "job_type": video_editengine1.WORKER_JOB_TYPE})

    assert received == [{"id": 902, "job_type": video_editengine1.WORKER_JOB_TYPE}]


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_editengine1_telegram_http_rejection_falls_back_once_to_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4-data")
    calls: list[str] = []

    def urlopen(request, timeout=0):
        url = str(request.full_url)
        calls.append(url)
        if url.endswith("/sendVideo"):
            raise urllib.error.HTTPError(url, 400, "bad request", {}, io.BytesIO())
        return _Response({"ok": True, "result": {"message_id": 99, "document": {"file_id": "doc-file"}}})

    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(local_worker.urllib.request, "urlopen", urlopen)
    result = local_worker.telegram_send_video_receipt(88, str(video), "done")
    assert result == {"sent": True, "file_id": "doc-file", "message_id": "99", "delivery_method": "sendDocument"}
    assert [url.rsplit("/", 1)[-1] for url in calls] == ["sendVideo", "sendDocument"]


def test_editengine1_telegram_timeout_does_not_duplicate_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4-data")
    calls = 0

    def timeout(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise socket.timeout("timeout")

    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(local_worker.urllib.request, "urlopen", timeout)
    with pytest.raises(RuntimeError, match="telegram_delivery_outcome_uncertain"):
        local_worker.telegram_send_video_receipt(88, str(video), "done")
    assert calls == 1


def test_editengine1_telegram_server_error_does_not_duplicate_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4-data")
    calls = 0

    def server_error(request, timeout=0):
        nonlocal calls
        calls += 1
        url = str(request.full_url)
        raise urllib.error.HTTPError(url, 500, "server error", {}, io.BytesIO())

    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(local_worker.urllib.request, "urlopen", server_error)
    with pytest.raises(RuntimeError, match="telegram_delivery_outcome_uncertain"):
        local_worker.telegram_send_video_receipt(88, str(video), "done")
    assert calls == 1


def test_editengine1_bot_charges_only_after_persisted_delivery_truth() -> None:
    start = BOT_SOURCE.index("def handle_video_local_edit_worker_job_update")
    end = BOT_SOURCE.index("async def submit_video_ai_edit_job", start)
    source = BOT_SOURCE[start:end]
    assert source.index("video_editengine1.record_worker_update(") < source.index("video_editengine1.claim_charge(")
    assert source.index("video_editengine1.claim_charge(") < source.index("spend_fixed_credit_info(")
    assert source.index("spend_fixed_credit_info(") < source.index("video_editengine1.mark_charge_result(")
    assert 'canonical.get("status") == "delivered"' in source


def test_editengine1_worker_receipt_contains_real_delivery_and_validation_truth() -> None:
    receipt_start = WORKER_SOURCE.index("def _video_edit_artifact_receipt")
    receipt_end = WORKER_SOURCE.index("def _legacy_local1_plan", receipt_start)
    receipt_source = WORKER_SOURCE[receipt_start:receipt_end]
    start = WORKER_SOURCE.index("def run_video_local_edit")
    end = WORKER_SOURCE.index("def _aiedit_progress", start)
    source = WORKER_SOURCE[start:end]
    for required in (
        "send_video_edit_artifact(",
        "_video_edit_artifact_receipt(",
        '"output_sha256"',
        '"output_size_bytes"',
        '"ffprobe"',
        'terminal_status = "succeeded"',
    ):
        assert required in source
    for required in (
        "telegram_delivery_identity(delivery)",
        '"message_id": message_id',
        '"file_id": file_id',
        '"delivery_method": delivery_method',
        '"bytes_sent": bytes_sent',
    ):
        assert required in receipt_source
    assert source.rindex("_video_edit_artifact_receipt(") < source.rindex(
        'terminal_status = "succeeded"'
    )


def test_editengine1_scope_has_no_real_provider_calls_or_early_charge() -> None:
    service = (ROOT / "services" / "video_editengine1.py").read_text(encoding="utf-8")
    submit_start = BOT_SOURCE.index("async def submit_local_video_editor_job")
    submit_end = BOT_SOURCE.index("async def handle_video_editor_pending_upload", submit_start)
    submit = BOT_SOURCE[submit_start:submit_end]
    for forbidden in ("ShopAIKey", "Key4U", "provider.submit", "requests.", "httpx"):
        assert forbidden not in service
        assert forbidden not in submit
    for forbidden in ("spend_fixed_credit_info", "deduct_dynamic_credit", "charge_user"):
        assert forbidden not in submit
