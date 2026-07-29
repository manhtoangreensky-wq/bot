from __future__ import annotations

import json
from pathlib import Path

import pytest

import local_worker
from services import video_editengine1


def _run_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    mode: str,
    price_xu: int = 0,
) -> tuple[dict, list[str]]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "source.mp4"
    source.write_bytes(b"source-video")
    updates: list[dict] = []
    captions: list[str] = []

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(local_worker.shutil, "which", lambda _binary: "ffmpeg")
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda _job_id: workspace)
    monkeypatch.setattr(
        local_worker,
        "cleanup_job_workspace",
        lambda _workspace: {"ok": True, "removed": True},
    )
    monkeypatch.setattr(
        local_worker,
        "_local1_download_asset",
        lambda *_args, **_kwargs: str(source),
    )
    monkeypatch.setattr(local_worker, "delivery_file_allowed", lambda *_args, **_kwargs: True)

    def fake_manual_edit(_plan: dict, *, output_path: str, **_kwargs) -> dict:
        Path(output_path).write_bytes(b"rendered-video")
        return {"ok": True, "validation": {"ok": True, "video_codec": "h264"}}

    def fake_split_plan(*_args, **_kwargs) -> dict:
        outputs = []
        for index in range(1, 3):
            output = workspace / f"part-{index}.mp4"
            output.write_bytes(f"part-{index}".encode("utf-8"))
            outputs.append(
                {
                    "path": str(output),
                    "duration_ms": 1_000,
                    "validation": {"ok": True, "video_codec": "h264"},
                }
            )
        return {"ok": True, "outputs": outputs}

    monkeypatch.setattr(local_worker, "execute_manual_edit", fake_manual_edit)
    monkeypatch.setattr(local_worker, "execute_split_plan", fake_split_plan)

    def fake_delivery(_chat_id: str, _path: str, caption: str = "", **_kwargs) -> dict:
        captions.append(caption)
        index = len(captions)
        return {
            "sent": True,
            "message_id": f"message-{index}",
            "file_id": f"file-{index}",
        }

    monkeypatch.setattr(local_worker, "telegram_send_video_receipt", fake_delivery)
    monkeypatch.setattr(
        local_worker,
        "update_job",
        lambda job_id, status, error_short="", output_url="", output_file_id="", **_kwargs: updates.append(
            {
                "job_id": job_id,
                "status": status,
                "detail": error_short,
                "output_url": output_url,
                "output_file_id": output_file_id,
            }
        ),
    )

    payload = {
        "local1_contract": 1,
        "product_type": video_editengine1.PRODUCT_TYPE,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "worker_capability": video_editengine1.WORKER_CAPABILITY,
        "source_file_id": "source-file",
        "source_file_name": "source.mp4",
        "chat_id": "88",
        "local1_mode": mode,
        "price_xu": price_xu,
        "manual_edit_plan": {},
        "split_ranges": [{"index": 1, "start_ms": 0, "end_ms": 1_000}],
    }
    local_worker.run_video_local_edit(
        {"id": 2701, "job_type": video_editengine1.WORKER_JOB_TYPE, "input_file_id": json.dumps(payload)}
    )
    return updates[-1], captions


@pytest.mark.parametrize("mode", ["manual", "split"])
def test_canonical_local_free_worker_receipt_never_requests_charge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
) -> None:
    terminal, captions = _run_job(monkeypatch, tmp_path, mode=mode)

    assert terminal["status"] == "succeeded"
    detail = json.loads(terminal["detail"])
    receipt = json.loads(terminal["output_url"])
    assert detail["price_xu"] == 0
    assert detail["charge_status"] == "not_required_free"
    assert detail["charged_xu"] == 0
    assert receipt["charge_policy"] == "not_required_free"
    assert receipt["charge_status"] == "not_required_free"
    assert receipt["charged_xu"] == 0
    assert captions
    for caption in captions:
        lowered = caption.lower()
        assert "0 xu" in lowered
        assert "ghi phí" not in lowered
        assert "trừ xu" not in lowered


def test_existing_paid_worker_receipt_keeps_post_delivery_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(monkeypatch, tmp_path, mode="manual", price_xu=300)

    detail = json.loads(terminal["detail"])
    receipt = json.loads(terminal["output_url"])
    assert detail["price_xu"] == 300
    assert detail["charge_status"] == "pending_post_delivery"
    assert detail["charged_xu"] == 0
    assert receipt["charge_policy"] == "after_valid_mp4_delivery"
    assert receipt["charge_status"] == "pending_post_delivery"
    assert receipt["charged_xu"] == 0
    assert len(captions) == 1 and "ghi phí sau" in captions[0]


def test_canonical_local_worker_path_has_no_wallet_or_provider_execution() -> None:
    source = Path(local_worker.__file__).read_text(encoding="utf-8")
    start = source.index("def run_video_local_edit")
    end = source.index("def _aiedit_progress", start)
    worker = source[start:end]

    for forbidden in (
        "spend_fixed_credit_info",
        "deduct_dynamic_credit",
        "charge_user",
        "submit_video_edit",
        "submit_provider",
    ):
        assert forbidden not in worker
