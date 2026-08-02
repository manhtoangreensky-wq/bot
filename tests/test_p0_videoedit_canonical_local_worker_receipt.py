from __future__ import annotations

import json
import urllib.error
from copy import deepcopy
from pathlib import Path

import pytest

import local_worker
from services import video_editengine1, video_local_editing


def _run_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    mode: str,
    price_xu: int = 0,
    manual_plan: dict | None = None,
    payload_patch: dict | None = None,
    observed_plans: list[dict] | None = None,
    downloaded_probe: dict | None = None,
    observed_worker_steps: list[str] | None = None,
    source_validation_calls: list[dict] | None = None,
    job_user_id: str = "701",
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
    def fake_download(*_args, **_kwargs) -> str:
        if observed_worker_steps is not None:
            observed_worker_steps.append("download")
        return str(source)

    monkeypatch.setattr(local_worker, "_local1_download_asset", fake_download)
    monkeypatch.setattr(local_worker, "delivery_file_allowed", lambda *_args, **_kwargs: True)
    probe = downloaded_probe or {
        "ok": True,
        "reason": "",
        "duration": 2.0,
        "duration_ms": 2_000,
        "width": 640,
        "height": 360,
        "fps": 25.0,
        "has_video": True,
        "has_audio": True,
        "audio_stream_count": 1,
        "format_name": "mp4",
        "bytes": source.stat().st_size,
    }
    def fake_probe(*_args, **_kwargs) -> dict:
        if observed_worker_steps is not None:
            observed_worker_steps.append("probe")
        return deepcopy(probe)

    original_validate_source_metadata = (
        local_worker.video_local_validation.validate_source_metadata
    )

    def observe_source_validation(metadata: dict, *, file_size: int = 0) -> dict:
        if observed_worker_steps is not None:
            observed_worker_steps.append("validate")
        if source_validation_calls is not None:
            source_validation_calls.append(
                {"metadata": deepcopy(metadata), "file_size": file_size}
            )
        return original_validate_source_metadata(metadata, file_size=file_size)

    monkeypatch.setattr(local_worker.video_local_validation, "probe_video_file", fake_probe)
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "validate_source_metadata",
        observe_source_validation,
    )

    def fake_manual_edit(_plan: dict, *, output_path: str, **_kwargs) -> dict:
        if observed_worker_steps is not None:
            observed_worker_steps.append("execute")
        if observed_plans is not None:
            observed_plans.append(deepcopy(_plan))
        Path(output_path).write_bytes(b"rendered-video")
        return {
            "ok": True,
            "validation": {
                "ok": True,
                "has_video": True,
                "video_codec": "h264",
                "duration_ms": 2_000,
                "width": 640,
                "height": 360,
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            },
        }

    def fake_split_plan(*_args, **_kwargs) -> dict:
        outputs = []
        for index in range(1, 3):
            output = workspace / f"part-{index}.mp4"
            output.write_bytes(f"part-{index}".encode("utf-8"))
            outputs.append(
                {
                    "path": str(output),
                    "duration_ms": 1_000,
                    "validation": {
                        "ok": True,
                        "has_video": True,
                        "video_codec": "h264",
                        "duration_ms": 1_000,
                        "width": 640,
                        "height": 360,
                        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                    },
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
            "message_id": str(1_000 + index),
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
        "source_metadata": {
            "ok": True,
            "duration": 2.0,
            "duration_ms": 2_000,
            "width": 640,
            "height": 360,
            "has_audio": True,
        },
        "user_id": "701",
        "chat_id": "88",
        "local1_mode": mode,
        "price_xu": price_xu,
        "quoted_price_xu": price_xu,
        "quality_tier_id": "local-free" if price_xu == 0 else "300",
        "charge_policy": "free_local_tool" if price_xu == 0 else "after_valid_mp4_delivery",
        "provider_call": False,
        "plan_schema_version": "video-edit-plan-v1",
        "state_revision": 3,
        "manual_edit_plan": (
            video_local_editing.neutral_split_manual_plan()
            if mode == "split" and manual_plan is None
            else {
                "trim": {"start_ms": 0, "end_ms": 2_000},
                "brightness_percent": 110,
            }
            if manual_plan is None else manual_plan
        ),
        "split_ranges": [{"index": 1, "start_ms": 0, "end_ms": 1_000}],
        "rights_confirmation": {
            "confirmed": True,
            "policy": "video_edit_rights_v1",
            "user_id": "701",
            "review_revision": 3,
            "confirmed_at_unix": 1_750_000_000,
        },
    }
    patch = dict(payload_patch or {})
    drop_rights = bool(patch.pop("_drop_rights_confirmation", False))
    payload.update(patch)
    if drop_rights:
        payload.pop("rights_confirmation", None)
    local_worker.run_video_local_edit(
        {
            "id": 2701,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "user_id": job_user_id,
            "input_file_id": json.dumps(payload),
        }
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
    assert receipt["charge_policy"] == "free_local_tool"
    assert receipt["charge_status"] == "not_required_free"
    assert receipt["charged_xu"] == 0
    assert captions
    for caption in captions:
        lowered = caption.lower()
        assert "0 xu" in lowered
        assert "ghi phí" not in lowered
        assert "trừ xu" not in lowered


def test_split_worker_uses_first_artifact_as_top_level_telegram_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, _captions = _run_job(monkeypatch, tmp_path, mode="split")
    receipt = json.loads(terminal["output_url"])

    assert terminal["status"] == "succeeded"
    assert receipt["delivery_message_id"] == "1001"
    assert receipt["delivery_file_id"] == "file-1"
    assert terminal["output_file_id"] == "file-1"
    assert [item["message_id"] for item in receipt["artifacts"]] == ["1001", "1002"]


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


def test_paid_legacy_worker_without_mode_defaults_to_manual_only_without_split_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="",
        price_xu=300,
        payload_patch={"split_ranges": []},
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == 1


def test_paid_legacy_worker_without_mode_rejects_split_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="",
        price_xu=300,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_mode_missing_with_split"
    assert captions == []


def test_paid_source_alias_with_real_edit_is_removed_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[dict] = []
    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        price_xu=300,
        manual_plan={
            "source": "stale-legacy-path.mp4",
            "trim": {"start_ms": 0, "end_ms": 2_000},
            "brightness_percent": 110,
        },
        observed_plans=observed,
    )

    assert terminal["status"] == "succeeded"
    assert len(observed) == 1
    assert "source" not in observed[0]
    assert Path(observed[0]["input_video"]).name == "source.mp4"


def test_paid_source_alias_without_a_real_edit_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        price_xu=300,
        manual_plan={"source": "stale-legacy-path.mp4"},
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_plan_missing"
    assert captions == []


@pytest.mark.parametrize("mode", ["", "provider_magic"])
def test_missing_or_unknown_local_mode_fails_closed_without_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
) -> None:
    terminal, captions = _run_job(monkeypatch, tmp_path, mode=mode)

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "failed_no_charge"
    assert detail["reason"] == "video_local_edit_mode_invalid"
    assert captions == []


def test_worker_rejects_boolean_local1_contract_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={"local1_contract": True},
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_contract_local1_contract"
    assert captions == []


def test_canonical_manual_job_rejects_an_empty_plan_instead_of_delivering_a_noop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(monkeypatch, tmp_path, mode="manual", manual_plan={})

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "failed_no_charge"
    assert detail["reason"] == "video_local_edit_plan_missing"
    assert captions == []


@pytest.mark.parametrize(
    "rights",
    [
        None,
        {},
        {
            "confirmed": False,
            "policy": "video_edit_rights_v1",
            "user_id": "701",
            "review_revision": 3,
            "confirmed_at_unix": 1_750_000_000,
        },
        {
            "confirmed": True,
            "policy": "wrong_policy",
            "user_id": "701",
            "review_revision": 3,
            "confirmed_at_unix": 1_750_000_000,
        },
        {
            "confirmed": True,
            "policy": "video_edit_rights_v1",
            "user_id": "999",
            "review_revision": 3,
            "confirmed_at_unix": 1_750_000_000,
        },
        {
            "confirmed": True,
            "policy": "video_edit_rights_v1",
            "user_id": "701",
            "review_revision": 0,
            "confirmed_at_unix": 1_750_000_000,
        },
        {
            "confirmed": True,
            "policy": "video_edit_rights_v1",
            "user_id": "701",
            "review_revision": 3,
            "confirmed_at_unix": 0,
        },
    ],
)
def test_local_free_worker_requires_valid_durable_rights_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rights: dict | None,
) -> None:
    payload_patch = (
        {"rights_confirmation": rights}
        if rights is not None
        else {"_drop_rights_confirmation": True}
    )
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch=payload_patch,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_rights_confirmation_invalid"
    assert captions == []


def test_worker_binds_rights_confirmation_to_the_claimed_job_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        job_user_id="701",
        payload_patch={
            "user_id": "999",
            "rights_confirmation": {
                "confirmed": True,
                "policy": "video_edit_rights_v1",
                "user_id": "999",
                "review_revision": 3,
                "confirmed_at_unix": 1_750_000_000,
            },
        },
    )

    assert terminal["status"] == "failed"
    assert "video_local_edit_rights_confirmation_invalid" in terminal["detail"]
    assert captions == []


def test_worker_binds_rights_confirmation_to_the_claimed_review_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={"state_revision": 4},
    )

    assert terminal["status"] == "failed"
    assert "video_local_edit_rights_confirmation_invalid" in terminal["detail"]
    assert captions == []


@pytest.mark.parametrize(
    ("manual_plan", "asset_patch"),
    [
        (
            {"trim": {"start_ms": 0, "end_ms": 2_000}, "brightness_percent": 120},
            {},
        ),
        (
            {"trim": {"start_ms": 0, "end_ms": 2_000}, "brightness_percent": 100},
            {"concat_sources": [{"file_id": "concat-only", "file_name": "concat.mp4"}]},
        ),
        (
            {"trim": {"start_ms": 0, "end_ms": 2_000}, "brightness_percent": 100},
            {"logo_source": {"file_id": "logo-only", "file_name": "logo.png"}},
        ),
        (
            {"trim": {"start_ms": 0, "end_ms": 2_000}, "brightness_percent": 100},
            {"subtitle_source": {"file_id": "subtitle-only", "file_name": "subtitle.srt"}},
        ),
    ],
)
def test_split_worker_rejects_each_manual_operation_or_asset_independently(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    manual_plan: dict,
    asset_patch: dict,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        manual_plan=manual_plan,
        payload_patch=asset_patch,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_split_manual_conflict"
    assert captions == []


def test_split_worker_rejects_unknown_manual_plan_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manual_plan = video_local_editing.neutral_split_manual_plan()
    manual_plan["unknown_split_operation"] = True
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        manual_plan=manual_plan,
    )

    assert terminal["status"] == "failed"
    assert "video_local_edit_split_manual_conflict" in terminal["detail"]
    assert captions == []


@pytest.mark.parametrize(
    ("plan_patch", "asset_patch"),
    [
        ({"concat_inputs": ["concat_1.mp4"]}, {}),
        (
            {"concat_inputs": ["concat_1.mp4", "concat_2.mp4"]},
            {"concat_sources": [{"file_id": "concat-only", "file_name": "concat.mp4"}]},
        ),
        ({"logo_overlay": {"position": "top_right", "opacity": 1.0}}, {}),
        ({"subtitle_file": "subtitle.srt"}, {}),
        (
            {},
            {"concat_sources": [{"file_id": "concat-only", "file_name": "concat.mp4"}]},
        ),
        ({}, {"logo_source": {"file_id": "logo-only", "file_name": "logo.png"}}),
        (
            {},
            {"subtitle_source": {"file_id": "subtitle-only", "file_name": "subtitle.srt"}},
        ),
    ],
)
def test_manual_worker_rejects_unbound_plan_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    plan_patch: dict,
    asset_patch: dict,
) -> None:
    manual_plan = {
        "trim": {"start_ms": 0, "end_ms": 2_000},
        "brightness_percent": 110,
        **plan_patch,
    }
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_plan=manual_plan,
        payload_patch={
            "concat_sources": [],
            "logo_source": {},
            "subtitle_source": {},
            **asset_patch,
        },
    )

    assert terminal["status"] == "failed"
    assert "video_local_edit_asset_contract_invalid" in terminal["detail"]
    assert captions == []


@pytest.mark.parametrize("malformed_plan", ["not-a-plan", ["trim"]])
def test_split_worker_rejects_non_mapping_manual_plan_before_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    malformed_plan,
) -> None:
    observed_steps: list[str] = []
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        payload_patch={"manual_edit_plan": malformed_plan},
        observed_worker_steps=observed_steps,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_split_plan_invalid"
    assert observed_steps == []
    assert captions == []


def test_split_worker_accepts_duration_independent_neutral_manual_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    downloaded_probe = {
        "ok": True,
        "reason": "",
        "duration": 2.1,
        "duration_ms": 2_100,
        "width": 640,
        "height": 360,
        "fps": 25.0,
        "has_video": True,
        "has_audio": True,
        "audio_stream_count": 1,
        "format_name": "mp4",
        "bytes": 12,
    }

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        manual_plan={},
        downloaded_probe=downloaded_probe,
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == 2


def test_worker_rechecks_downloaded_source_duration_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    over_limit = local_worker.video_local_validation.MAX_DURATION_SECONDS + 1
    observed_steps: list[str] = []
    validation_calls: list[dict] = []
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        downloaded_probe={
            "ok": True,
            "reason": "",
            "duration": float(over_limit),
            "duration_ms": over_limit * 1_000,
            "width": 640,
            "height": 360,
            "fps": 25.0,
            "has_video": True,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
            "bytes": 12,
        },
        observed_worker_steps=observed_steps,
        source_validation_calls=validation_calls,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "duration_too_long"
    assert captions == []
    assert observed_steps == ["download", "probe", "validate"]
    assert len(validation_calls) == 1
    assert validation_calls[0]["file_size"] == len(b"source-video")
    assert validation_calls[0]["metadata"]["duration_ms"] == over_limit * 1_000


def test_worker_uses_downloaded_duration_for_the_final_noop_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_steps: list[str] = []
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_plan={"trim": {"start_ms": 0, "end_ms": 2_000}},
        payload_patch={
            "source_metadata": {
                "ok": True,
                "duration": 4.0,
                "duration_ms": 4_000,
                "width": 640,
                "height": 360,
                "has_audio": True,
            }
        },
        downloaded_probe={
            "ok": True,
            "reason": "",
            "duration": 2.0,
            "duration_ms": 2_000,
            "width": 640,
            "height": 360,
            "fps": 25.0,
            "has_video": True,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
            "bytes": 12,
        },
        observed_worker_steps=observed_steps,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_plan_missing"
    assert observed_steps == ["download", "probe", "validate"]
    assert captions == []


@pytest.mark.parametrize(
    "payload_patch",
    [
        {"quality_tier_id": "300"},
        {"quoted_price_xu": 1},
        {"charge_policy": "after_valid_mp4_delivery"},
        {"provider_call": True},
    ],
)
def test_local_free_worker_rejects_contradictory_billing_identity_before_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload_patch: dict,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch=payload_patch,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "failed_no_charge"
    assert detail["reason"] == "video_local_edit_free_contract_invalid"
    assert captions == []


def test_worker_rejects_negative_price_instead_of_coercing_it_to_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(monkeypatch, tmp_path, mode="manual", price_xu=-1)

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "failed_no_charge"
    assert detail["reason"] == "video_local_edit_price_invalid"
    assert captions == []


@pytest.mark.parametrize("price_xu", [-0.5, 1.5])
def test_worker_rejects_fractional_price_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    price_xu: float,
) -> None:
    terminal, captions = _run_job(monkeypatch, tmp_path, mode="manual", price_xu=price_xu)

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_price_invalid"
    assert captions == []


def test_free_worker_rejects_the_legacy_source_plan_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_plan={
            "source": "legacy-source.mp4",
            "trim": {"start_ms": 0, "end_ms": 2_000},
        },
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_legacy_plan_invalid"
    assert captions == []


def test_worker_rejects_malformed_local_assets_before_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={"concat_sources": [{"file_name": "missing-file-id.mp4"}]},
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "failed_no_charge"
    assert detail["reason"] == "video_local_edit_asset_contract_invalid"
    assert captions == []


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


def test_document_fallback_server_error_is_normalized_as_delivery_uncertainty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    video = tmp_path / "output.mp4"
    video.write_bytes(b"mp4")
    calls = 0

    def fake_urlopen(request, timeout=0):
        nonlocal calls
        calls += 1
        code = 400 if calls == 1 else 500
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "telegram error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(local_worker.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="telegram_delivery_outcome_uncertain"):
        local_worker.telegram_send_video_receipt("88", str(video))

    assert calls == 2
