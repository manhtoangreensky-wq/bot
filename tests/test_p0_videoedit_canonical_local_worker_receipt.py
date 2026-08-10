from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
import urllib.error
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
import local_worker
from services import (
    video_edit_media_transport,
    video_editengine1,
    video_local_editing,
)


def _run_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    mode: str,
    price_xu: int = 0,
    manual_plan: dict | None = None,
    manual_result_patch: dict | None = None,
    payload_patch: dict | None = None,
    observed_plans: list[dict] | None = None,
    downloaded_probe: dict | None = None,
    observed_worker_steps: list[str] | None = None,
    source_validation_calls: list[dict] | None = None,
    job_user_id: str = "701",
    transport_evidence: dict | None = None,
    liveness_evidence: list[str] | None = None,
    liveness_factory_calls: list[tuple[object, object, object, object]] | None = None,
    liveness_health_failure_at: int | None = None,
    liveness_failure_on_stop: bool = False,
    worker_policy_evidence: dict | None = None,
    delivery_receipts_override: list[
        video_edit_media_transport.DeliveryReceipt
    ]
    | None = None,
    source_download_receipt_override: video_edit_media_transport.DownloadReceipt
    | None = None,
    update_evidence: list[dict] | None = None,
    checkpoint_order_evidence: list[str] | None = None,
    job_patch: dict | None = None,
    setup_evidence: list[str] | None = None,
    cleanup_intent_persisted: bool = True,
    use_real_cleanup: bool = False,
    resume_project_present: bool = True,
    cleanup_order_evidence: list[str] | None = None,
    cleanup_intent_evidence: list[dict] | None = None,
) -> tuple[dict, list[str]]:
    project_workspace = tmp_path / "job_2701"
    workspace = project_workspace / "claim_1"
    workspace.mkdir(parents=True)
    source = workspace / "source.mp4"
    source.write_bytes(b"source-video")
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "VIDEO_LOCAL_WORKSPACE_ROOT",
        tmp_path,
    )
    updates: list[dict] = []
    captions: list[str] = []

    def record_observed_event(event: str) -> None:
        for evidence in (observed_worker_steps, liveness_evidence):
            if evidence is not None and evidence is not observed_worker_steps:
                evidence.append(event)
        if observed_worker_steps is not None:
            observed_worker_steps.append(event)

    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "123:test-token")
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org")
    monkeypatch.setenv("TELEGRAM_API_PROXY_SECRET", "")
    monkeypatch.setenv(
        "TELEGRAM_API_PROXY_SECRET_HEADER",
        "X-Toanaas-Proxy-Secret",
    )
    monkeypatch.setenv(
        "TELEGRAM_LOCAL_API_FILE_ROOT",
        "/var/lib/telegram-bot-api",
    )
    monkeypatch.setenv("TELEGRAM_LOCAL_API_MEDIA_PATH", "/localfile")

    def fake_local_ffmpeg_path() -> str:
        if setup_evidence is not None:
            setup_evidence.append("ffmpeg_lookup")
        return "ffmpeg"

    def fake_create_job_workspace(_job_id: object) -> Path:
        assert str(_job_id) in {workspace.name, "job_2701_claim_1"}
        if setup_evidence is not None:
            setup_evidence.append("workspace")
        return workspace

    def fake_create_video_edit_claim_workspace(
        job_id: object,
        claim_attempt: object,
    ) -> tuple[Path, Path]:
        assert job_id == 2701
        assert claim_attempt == 1
        if setup_evidence is not None:
            setup_evidence.append("workspace")
        return project_workspace, workspace

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", fake_local_ffmpeg_path)
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(local_worker.shutil, "which", lambda _binary: "ffmpeg")
    monkeypatch.setattr(local_worker, "create_job_workspace", fake_create_job_workspace)
    monkeypatch.setattr(
        local_worker,
        "create_video_edit_claim_workspace",
        fake_create_video_edit_claim_workspace,
    )
    def prepare_cleanup_intent(**kwargs) -> tuple[dict, dict]:
        key = f"job_{kwargs['job_id']}_claim_{kwargs['claim_attempt']}"
        workspace_present = kwargs["workspace"] is not None
        if workspace_present:
            assert kwargs["workspace"] == project_workspace
            assert kwargs.get("project_workspace") is True
            if setup_evidence is not None:
                setup_evidence.append("cleanup_intent")
        if workspace_present and not cleanup_intent_persisted:
            return (
                None,
                {
                    "persisted": False,
                    "workspace_present": True,
                    "reason": "cleanup_intent_persist_failed:OSError",
                },
            )
        return (
            {"job_id": kwargs["job_id"], "workspace_key": key},
            (
                {
                    "persisted": True,
                    "workspace_present": True,
                    "intent_key": f"{key}.json",
                    "workspace_key": key,
                    "tombstone_key": key,
                }
                if workspace_present
                else {"persisted": False, "workspace_present": False}
            ),
        )

    if use_real_cleanup:
        original_reconcile_cleanup = local_worker.reconcile_video_edit_cleanup_intent

        def observe_reconcile_cleanup(intent: dict) -> dict:
            if cleanup_intent_evidence is not None:
                cleanup_intent_evidence.append(deepcopy(intent))
            if cleanup_order_evidence is not None:
                cleanup_order_evidence.append("cleanup_reconcile")
            return original_reconcile_cleanup(intent)

        def cleanup_http_json(
            method: str,
            path: str,
            payload: dict,
            timeout: int,
            **_kwargs,
        ) -> dict:
            assert method == "POST"
            assert timeout == 10
            if path == "/internal/worker/video_edit_cleanup/claim":
                if cleanup_order_evidence is not None:
                    cleanup_order_evidence.append("cleanup_claim")
                return {
                    "ok": True,
                    "action": "cleanup",
                    "audit_owner": local_worker.LOCAL_WORKER_INSTANCE_ID,
                    "audit_attempt": 1,
                }
            if path == "/internal/worker/video_edit_cleanup/result":
                if cleanup_order_evidence is not None:
                    cleanup_order_evidence.append("cleanup_result")
                return {
                    "ok": True,
                    "cleanup_audit": {"state": "succeeded"},
                }
            pytest.fail(f"unexpected cleanup endpoint: {path}")

        monkeypatch.setattr(
            local_worker,
            "reconcile_video_edit_cleanup_intent",
            observe_reconcile_cleanup,
        )
        monkeypatch.setattr(local_worker, "http_json", cleanup_http_json)
    else:
        monkeypatch.setattr(
            local_worker,
            "prepare_video_edit_cleanup_intent",
            prepare_cleanup_intent,
        )
        monkeypatch.setattr(
            local_worker,
            "reconcile_video_edit_cleanup_intent",
            lambda _intent: {"ok": True},
        )
    if liveness_evidence is not None or liveness_health_failure_at is not None:
        health_check_count = 0

        class FakeVideoEditJobLiveness:
            def __init__(self) -> None:
                self._stopped = False

            def start(self) -> None:
                liveness_evidence.append("start")

            def update_stage(self, stage: str) -> None:
                liveness_evidence.append(f"stage:{stage}")

            def assert_healthy(self) -> None:
                nonlocal health_check_count
                health_check_count += 1
                if liveness_evidence is not None:
                    liveness_evidence.append("assert_healthy")
                if checkpoint_order_evidence is not None:
                    checkpoint_order_evidence.append("assert_healthy")
                if health_check_count == liveness_health_failure_at:
                    raise local_worker.LocalVideoEditError(
                        "video_local_edit_worker_lease_lost"
                    )
                if liveness_failure_on_stop and self._stopped:
                    raise local_worker.LocalVideoEditError(
                        "video_local_edit_worker_lease_lost"
                    )

            def stop(self) -> None:
                if self._stopped:
                    return
                self._stopped = True
                liveness_evidence.append("stop")

        def fake_video_edit_job_liveness(
            job_id: object,
            lease_seconds: object,
            interval_seconds: object,
            *,
            claim_attempt: object = None,
        ) -> FakeVideoEditJobLiveness:
            if liveness_factory_calls is not None:
                liveness_factory_calls.append(
                    (job_id, lease_seconds, interval_seconds, claim_attempt)
                )
            return FakeVideoEditJobLiveness()

        monkeypatch.setattr(
            local_worker,
            "video_edit_job_liveness",
            fake_video_edit_job_liveness,
            raising=False,
        )
    def fake_download(*_args, **_kwargs) -> str | video_edit_media_transport.DownloadReceipt:
        if setup_evidence is not None:
            setup_evidence.append("download")
        if observed_worker_steps is not None:
            observed_worker_steps.append("download")
        if worker_policy_evidence is not None:
            worker_policy_evidence.setdefault("events", []).append("download")
            worker_policy_evidence.setdefault("download_deadlines", []).append(
                _kwargs.get("deadline_monotonic")
            )
        if source_download_receipt_override is not None:
            return source_download_receipt_override
        return str(source)

    def materialize_bounded_fixture(
        destination: str | Path,
        *,
        logical_size: int,
        marker: str,
    ) -> str:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        seed = (str(marker or "fixture").encode("utf-8") + b"\0")
        block_size = 64 * 1024
        block = (seed * ((block_size // len(seed)) + 1))[:block_size]
        remaining = max(1, int(logical_size or 0))
        digest = hashlib.sha256()
        with target.open("wb") as handle:
            while remaining:
                chunk = block[: min(remaining, block_size)]
                handle.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
        return digest.hexdigest()

    def bounded_file_sha256(path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    if transport_evidence is None:
        monkeypatch.setattr(local_worker, "_local1_download_asset", fake_download)
        monkeypatch.setattr(
            local_worker,
            "_video_edit_download_asset",
            fake_download,
            raising=False,
        )
    else:
        transport_evidence.setdefault("downloads", [])
        transport_evidence.setdefault("download_calls", [])
        transport_evidence.setdefault("deliveries", [])
        transport_evidence.setdefault("delivery_calls", [])
        transport_evidence["full_file_reads"] = int(
            transport_evidence.get("full_file_reads") or 0
        )
        original_path_read_bytes = Path.read_bytes

        def observe_full_file_read(path: Path) -> bytes:
            transport_evidence["full_file_reads"] += 1
            return original_path_read_bytes(path)

        monkeypatch.setattr(Path, "read_bytes", observe_full_file_read)
        monkeypatch.setenv("TELEGRAM_API_BASE_URL", "https://tg.toanaas.vn")
        monkeypatch.setenv("TELEGRAM_API_PROXY_SECRET", "test-proxy-secret")
        monkeypatch.setenv(
            "TELEGRAM_API_PROXY_SECRET_HEADER",
            "X-Toanaas-Proxy-Secret",
        )
        monkeypatch.setenv(
            "TELEGRAM_LOCAL_API_FILE_ROOT",
            "/var/lib/telegram-bot-api",
        )
        monkeypatch.setenv("TELEGRAM_LOCAL_API_MEDIA_PATH", "/localfile")
        monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "123:test-token")

        def fixture_size_for(file_id: str, expected_bytes: int | None) -> int:
            if file_id == "source-file":
                actual_probe_bytes = int(
                    dict(downloaded_probe or {}).get("bytes") or 0
                )
                if actual_probe_bytes > 0:
                    return actual_probe_bytes
                declared_source_bytes = int(
                    dict(payload_patch or {}).get("source_file_size") or 0
                )
                if declared_source_bytes > 0:
                    return declared_source_bytes
            if expected_bytes is not None and int(expected_bytes) > 0:
                return int(expected_bytes)
            return 1024

        def fake_transport_download(
            *,
            config,
            file_id,
            destination,
            expected_bytes=None,
            expected_size=None,
            hard_max_bytes=None,
            workspace_reserve_bytes=0,
            require_private_parent=False,
            **_kwargs,
        ):
            expected = expected_bytes if expected_bytes is not None else expected_size
            logical_size = fixture_size_for(str(file_id or ""), expected)
            sha256 = materialize_bounded_fixture(
                destination,
                logical_size=logical_size,
                marker=str(file_id or "asset"),
            )
            transport = (
                "local_bot_api"
                if bool(getattr(config, "is_local", False))
                else "cloud_bot_api"
            )
            transport_evidence["downloads"].append(transport)
            transport_evidence["download_calls"].append(
                {
                    "file_id": str(file_id or ""),
                    "destination": str(destination),
                    "expected_bytes": expected,
                    "hard_max_bytes": hard_max_bytes,
                    "workspace_reserve_bytes": workspace_reserve_bytes,
                    "require_private_parent": require_private_parent,
                    "transport": transport,
                    "bytes_written": logical_size,
                    "config": config,
                    "deadline_monotonic": _kwargs.get("deadline_monotonic"),
                }
            )
            if worker_policy_evidence is not None:
                worker_policy_evidence.setdefault("events", []).append("download")
            return video_edit_media_transport.DownloadReceipt(
                path=str(destination),
                bytes_written=logical_size,
                sha256=sha256,
                lane="large_media",
                transport="localfile" if transport == "local_bot_api" else "file",
                declared_bytes=(int(expected) if expected is not None else logical_size),
            )

        def fake_transport_delivery(
            *,
            config,
            chat_id,
            artifact,
            request,
            caption="",
            preview_threshold_bytes=video_edit_media_transport.SHORT_MEDIA_MAX_BYTES,
            **_kwargs,
        ):
            del request
            record_observed_event("delivery")
            artifact_path = Path(artifact)
            artifact_size = artifact_path.stat().st_size
            delivery_method = (
                "sendVideo"
                if artifact_path.suffix.lower() == ".mp4"
                and artifact_size <= int(preview_threshold_bytes)
                else "sendDocument"
            )
            captions.append(str(caption or ""))
            delivery_index = len(captions)
            transport_evidence["deliveries"].append(delivery_method)
            transport_evidence["delivery_calls"].append(
                {
                    "chat_id": str(chat_id),
                    "artifact": str(artifact),
                    "delivery_method": delivery_method,
                    "bytes_sent": artifact_size,
                    "config": config,
                    "deadline_monotonic": _kwargs.get("deadline_monotonic"),
                }
            )
            return video_edit_media_transport.DeliveryReceipt(
                message_id=str(4_000 + delivery_index),
                file_id=f"transport-file-{delivery_index}",
                delivery_method=delivery_method,
                bytes_sent=artifact_size,
                sha256=bounded_file_sha256(artifact_path),
            )

        def legacy_download_must_not_run(*_args, **_kwargs) -> None:
            pytest.fail(
                "Video Edit transport evidence must not call telegram_download_file"
            )

        def legacy_delivery_must_not_run(*_args, **_kwargs) -> None:
            pytest.fail(
                "Video Edit transport evidence must not call telegram_send_video_receipt"
            )

        monkeypatch.setattr(
            video_edit_media_transport,
            "download_file_to_path",
            fake_transport_download,
        )
        monkeypatch.setattr(
            video_edit_media_transport,
            "send_artifact_from_path",
            fake_transport_delivery,
        )
        monkeypatch.setattr(
            local_worker,
            "video_edit_media_transport",
            video_edit_media_transport,
            raising=False,
        )
        monkeypatch.setattr(
            local_worker,
            "download_file_to_path",
            fake_transport_download,
            raising=False,
        )
        monkeypatch.setattr(
            local_worker,
            "send_artifact_from_path",
            fake_transport_delivery,
            raising=False,
        )
        monkeypatch.setattr(
            local_worker,
            "telegram_download_file",
            legacy_download_must_not_run,
        )
        monkeypatch.setattr(
            local_worker,
            "telegram_send_video_receipt",
            legacy_delivery_must_not_run,
        )
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
        if worker_policy_evidence is not None:
            worker_policy_evidence.setdefault("events", []).append("probe")
        return deepcopy(probe)

    original_validate_source_metadata = (
        local_worker.video_local_validation.validate_source_metadata
    )

    def observe_source_validation(
        metadata: dict,
        *,
        file_size: int = 0,
        **limits,
    ) -> dict:
        if observed_worker_steps is not None:
            observed_worker_steps.append("validate")
        if source_validation_calls is not None:
            source_validation_calls.append(
                {
                    "metadata": deepcopy(metadata),
                    "file_size": file_size,
                    **deepcopy(limits),
                }
            )
        return original_validate_source_metadata(
            metadata,
            file_size=file_size,
            **limits,
        )

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
        if worker_policy_evidence is not None:
            worker_policy_evidence.setdefault("events", []).append("execute")
            worker_policy_evidence.setdefault("executor_calls", []).append(
                {
                    "mode": "manual",
                    "timeout": _kwargs.get("timeout"),
                    "deadline_monotonic": _kwargs.get("deadline_monotonic"),
                    "workspace_budget_bytes": _kwargs.get("workspace_budget_bytes"),
                }
            )
        if transport_evidence is None:
            Path(output_path).write_bytes(b"rendered-video")
        else:
            output_size = int(
                transport_evidence.get("output_size_bytes")
                or dict(probe or {}).get("bytes")
                or len(b"rendered-video")
            )
            materialize_bounded_fixture(
                output_path,
                logical_size=output_size,
                marker="rendered-video",
            )
        validation = {
            "ok": True,
            "has_video": True,
            "video_codec": "h264",
            "duration_ms": 2_000,
            "width": 640,
            "height": 360,
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            # A real executor must report successful full decode before the
            # worker can checkpoint or deliver an MP4.  Existing fixtures are
            # successful artifacts unless a test overrides this field.
            "full_decode": True,
        }
        validation.update(dict(manual_result_patch or {}))
        return {
            "ok": True,
            "validation": validation,
        }

    def fake_split_plan(*_args, **_kwargs) -> dict:
        record_observed_event("execute")
        if worker_policy_evidence is not None:
            worker_policy_evidence.setdefault("events", []).append("execute")
            worker_policy_evidence.setdefault("executor_calls", []).append(
                {
                    "mode": "split",
                    "timeout": _kwargs.get("timeout"),
                    "deadline_monotonic": _kwargs.get("deadline_monotonic"),
                    "workspace_budget_bytes": _kwargs.get("workspace_budget_bytes"),
                }
            )
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
                        "full_decode": True,
                    },
                }
            )
        return {"ok": True, "outputs": outputs}

    monkeypatch.setattr(local_worker, "execute_manual_edit", fake_manual_edit)
    monkeypatch.setattr(local_worker, "execute_split_plan", fake_split_plan)

    def fake_delivery(*_args, **_kwargs) -> dict:
        pytest.fail(
            "Video Edit worker tests must not call telegram_send_video_receipt"
        )

    def fake_media_delivery(
        *,
        config,
        chat_id,
        artifact,
        request,
        caption="",
        **_kwargs,
    ) -> video_edit_media_transport.DeliveryReceipt:
        del config, chat_id, request
        record_observed_event("delivery")
        captions.append(str(caption or ""))
        index = len(captions)
        artifact_path = Path(artifact)
        if checkpoint_order_evidence is not None:
            checkpoint_order_evidence.append("delivery_accepted")
        if worker_policy_evidence is not None:
            worker_policy_evidence.setdefault("delivery_deadlines", []).append(
                _kwargs.get("deadline_monotonic")
            )
        default_receipt = video_edit_media_transport.DeliveryReceipt(
            message_id=str(1_000 + index),
            file_id=f"file-{index}",
            delivery_method="sendVideo",
            bytes_sent=artifact_path.stat().st_size,
            sha256=bounded_file_sha256(artifact_path),
        )
        if delivery_receipts_override is not None:
            return delivery_receipts_override[index - 1]
        return default_receipt

    if transport_evidence is None:
        monkeypatch.setattr(
            video_edit_media_transport,
            "send_artifact_from_path",
            fake_media_delivery,
        )
        monkeypatch.setattr(local_worker, "telegram_send_video_receipt", fake_delivery)
    def fake_update_job(
        job_id,
        status,
        error_short="",
        output_url="",
        output_file_id="",
        **_kwargs,
    ) -> dict:
        def has_percent_field(value: object) -> bool:
            if isinstance(value, dict):
                return any(
                    "percent" in str(key).lower() or has_percent_field(item)
                    for key, item in value.items()
                )
            if isinstance(value, (list, tuple)):
                return any(has_percent_field(item) for item in value)
            return False

        if has_percent_field(_kwargs):
            record_observed_event("percent_keyword")
        try:
            error_detail = json.loads(error_short)
        except (TypeError, json.JSONDecodeError):
            error_detail = None
        if has_percent_field(error_detail):
            record_observed_event("percent_error_short")
        if (
            isinstance(error_detail, dict)
            and isinstance(error_detail.get("artifact_receipts"), list)
        ):
            if checkpoint_order_evidence is not None:
                checkpoint_order_evidence.append("receipt_checkpoint")
        if liveness_evidence is not None and status != "running":
            liveness_evidence.append("terminal_update")
        if cleanup_order_evidence is not None and status != "running":
            cleanup_order_evidence.append("terminal_ack")
        update = {
            "job_id": job_id,
            "status": status,
            "detail": error_short,
            "output_url": output_url,
            "output_file_id": output_file_id,
        }
        updates.append(update)
        if update_evidence is not None:
            update_evidence.append(deepcopy(update))
        return {"ok": True, "job": {"id": job_id}}

    monkeypatch.setattr(local_worker, "update_job", fake_update_job)

    if worker_policy_evidence is not None:
        worker_policy_evidence.setdefault("events", [])
        worker_policy_evidence.setdefault("classification_calls", [])
        worker_policy_evidence.setdefault("adaptive_deadline_calls", [])
        worker_policy_evidence.setdefault("admission_calls", [])
        worker_policy_evidence.setdefault("executor_calls", [])
        worker_policy_evidence.setdefault("delivery_deadlines", [])
        worker_policy_evidence.setdefault("monotonic_calls", 0)
        started_at = float(worker_policy_evidence.get("started_at", 10.0))

        def fake_monotonic() -> float:
            worker_policy_evidence["monotonic_calls"] += 1
            return started_at

        original_classify_plan_execution = (
            local_worker.video_edit_long_media.classify_plan_execution
        )
        original_adaptive_deadline_seconds = (
            local_worker.video_edit_long_media.adaptive_deadline_seconds
        )
        original_admit_workspace = local_worker.video_edit_long_media.admit_workspace

        def observe_classification(plan: dict) -> str:
            worker_policy_evidence["events"].append("classify")
            result = original_classify_plan_execution(plan)
            worker_policy_evidence["classification_calls"].append(
                {"plan": deepcopy(plan), "result": result}
            )
            return result

        def observe_adaptive_deadline(**kwargs) -> int:
            call_index = len(worker_policy_evidence["adaptive_deadline_calls"])
            scripted_results = worker_policy_evidence.get("adaptive_results")
            result = (
                int(scripted_results[call_index])
                if isinstance(scripted_results, list)
                and call_index < len(scripted_results)
                else original_adaptive_deadline_seconds(**kwargs)
            )
            worker_policy_evidence["events"].append(
                f"adaptive:{call_index + 1}"
            )
            worker_policy_evidence["adaptive_deadline_calls"].append(
                {**deepcopy(kwargs), "result": result}
            )
            return result

        def observe_admission(**kwargs):
            worker_policy_evidence["events"].append("admit")
            worker_policy_evidence["admission_calls"].append(deepcopy(kwargs))
            configured = dict(
                worker_policy_evidence.get("admission_by_operation") or {}
            ).get(str(kwargs.get("operation") or ""))
            rejected_reason = str(
                worker_policy_evidence.get("reject_admission_reason") or ""
            )
            if isinstance(configured, dict):
                decision = local_worker.video_edit_long_media.AdmissionDecision(
                    bool(configured.get("accepted")),
                    str(configured.get("reason") or "accepted"),
                    {
                        "estimated_bytes": int(
                            configured.get("estimated_bytes") or 0
                        )
                    },
                )
            elif rejected_reason:
                decision = local_worker.video_edit_long_media.AdmissionDecision(
                    False,
                    rejected_reason,
                    {"estimated_bytes": 777},
                )
            else:
                decision = original_admit_workspace(**kwargs)
            worker_policy_evidence.setdefault("admission_decisions", []).append(
                decision
            )
            return decision

        monkeypatch.setattr(local_worker.time, "monotonic", fake_monotonic)
        monkeypatch.setattr(
            local_worker.video_edit_long_media,
            "classify_plan_execution",
            observe_classification,
        )
        monkeypatch.setattr(
            local_worker.video_edit_long_media,
            "adaptive_deadline_seconds",
            observe_adaptive_deadline,
        )
        monkeypatch.setattr(
            local_worker.video_edit_long_media,
            "admit_workspace",
            observe_admission,
        )
        monkeypatch.setattr(
            local_worker.shutil,
            "disk_usage",
            lambda _path: type(
                "DiskUsage",
                (),
                {"total": 2 * 10**12, "used": 10**12, "free": 10**12},
            )(),
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
        "split_ranges": [
            {"index": 1, "start_ms": 0, "end_ms": 1_000},
            {"index": 2, "start_ms": 1_000, "end_ms": 2_000},
        ],
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
    job = {
        "id": 2701,
        "claim_attempt": 1,
        "job_type": video_editengine1.WORKER_JOB_TYPE,
        "user_id": job_user_id,
        "input_file_id": json.dumps(payload),
    }
    job.update(dict(job_patch or {}))
    if not resume_project_present:
        local_worker.shutil.rmtree(project_workspace)
    local_worker.run_video_local_edit(job)
    return updates[-1], captions


def test_video_edit_download_asset_returns_the_transport_receipt_and_deadline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = b"streamed-video-evidence"
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    captured: list[dict] = []
    config = video_edit_media_transport.TelegramMediaConfig(
        token="123:test-token",
        api_root="https://api.telegram.org",
        proxy_secret_header="X-Toanaas-Proxy-Secret",
        proxy_secret="",
        local_file_root="/var/lib/telegram-bot-api",
        local_media_path="/localfile",
    )

    def fake_download_file_to_path(**kwargs):
        captured.append(dict(kwargs))
        destination = Path(kwargs["destination"])
        destination.write_bytes(payload)
        return video_edit_media_transport.DownloadReceipt(
            path=str(destination),
            bytes_written=len(payload),
            sha256=expected_sha256,
            lane="large_media",
            transport="file",
            declared_bytes=len(payload),
        )

    monkeypatch.setattr(
        video_edit_media_transport,
        "download_file_to_path",
        fake_download_file_to_path,
    )

    receipt = local_worker._video_edit_download_asset(
        "source-file",
        "source.mp4",
        tmp_path,
        local_worker.ALLOWED_SOURCE_EXTENSIONS,
        "source",
        media_config=config,
        deadline_monotonic=321.25,
    )

    assert isinstance(receipt, video_edit_media_transport.DownloadReceipt)
    assert Path(receipt.path).read_bytes() == payload
    assert receipt.bytes_written == len(payload)
    assert receipt.sha256 == expected_sha256
    assert captured[0]["deadline_monotonic"] == 321.25


def test_worker_media_config_accepts_canonical_telegram_token_alias() -> None:
    environ = {
        "TELEGRAM_TOKEN": "canonical-token",
        "BOT_TOKEN": "legacy-token",
    }

    assert local_worker.resolve_telegram_bot_token(environ) == "canonical-token"
    assert local_worker.resolve_telegram_bot_token(
        {**environ, "TELEGRAM_BOT_TOKEN": "worker-token"}
    ) == "worker-token"


def test_large_media_worker_rejects_cloud_transport_before_download_or_executor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={
            "media_lane": "large_media",
            "source_file_size": 21 * 1024 * 1024,
        },
        observed_worker_steps=evidence,
    )

    assert terminal["status"] == "failed"
    assert "video_local_edit_large_media_transport_unavailable" in terminal["detail"]
    assert "download" not in evidence
    assert "execute" not in evidence
    assert "delivery" not in evidence
    assert captions == []


def test_cleanup_intent_is_durable_before_first_workspace_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    setup: list[str] = []

    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        setup_evidence=setup,
    )

    assert terminal["status"] == "succeeded"
    assert setup[:4] == [
        "ffmpeg_lookup",
        "workspace",
        "cleanup_intent",
        "download",
    ]
    assert setup.count("cleanup_intent") == 1


def test_cleanup_intent_persistence_failure_stops_before_download_and_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    setup: list[str] = []
    runtime: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        setup_evidence=setup,
        observed_worker_steps=runtime,
        cleanup_intent_persisted=False,
    )

    assert terminal["status"] == "failed"
    assert "video_local_edit_cleanup_intent_persistence_failed" in terminal[
        "detail"
    ]
    assert "download" not in setup
    assert "execute" not in runtime
    assert "delivery" not in runtime
    assert captions == []


def test_video_edit_delivery_probe_rejects_metadata_valid_full_decode_failure() -> None:
    metadata_valid_but_decode_failed = {
        "ok": True,
        "has_video": True,
        "video_codec": "h264",
        "duration_ms": 2_000,
        "width": 640,
        "height": 360,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "full_decode": False,
    }

    assert video_editengine1.valid_mp4_delivery_probe(
        metadata_valid_but_decode_failed
    ) is False


def test_video_edit_worker_fences_metadata_valid_full_decode_failed_mp4_before_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_result_patch={"full_decode": False},
        observed_worker_steps=observed_steps,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "failed_no_charge"
    assert detail["reason"] == "output_validation_failed"
    assert "delivery" not in observed_steps
    assert terminal["output_file_id"] == ""
    assert captions == []


def test_video_edit_multipart_request_caps_socket_timeout_by_remaining_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_payload = b'{"ok":false,"error_code":400,"description":"rejected"}'
    observed_timeouts: list[float] = []

    class Response:
        headers = {"Content-Length": str(len(response_payload))}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _maximum: int) -> bytes:
            return response_payload

    def fake_open(_request, *, timeout):
        observed_timeouts.append(timeout)
        return Response()

    monkeypatch.setattr(local_worker, "telegram_open_no_redirect", fake_open)

    payload = local_worker._video_edit_multipart_request(
        method_name="sendVideo",
        url="https://api.telegram.org/bot123:test-token/sendVideo",
        headers={"Content-Length": "3"},
        content_length=3,
        body=iter((b"abc",)),
        follow_redirects=False,
        deadline_monotonic=105.25,
        monotonic=lambda: 100.0,
    )

    assert payload["status_code"] == 200
    assert observed_timeouts == [5.25]


@pytest.mark.parametrize("hash_field", ["source_video_hash", "source_sha256"])
@pytest.mark.parametrize(
    ("queued_hash", "expected_reason"),
    [
        pytest.param("f" * 63, "video_local_edit_source_hash_invalid", id="short"),
        pytest.param("g" * 64, "video_local_edit_source_hash_invalid", id="non-hex"),
        pytest.param("f" * 64, "video_local_edit_source_hash_mismatch", id="mismatch"),
    ],
)
def test_worker_rejects_invalid_or_mismatched_queued_source_hash_before_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    hash_field: str,
    queued_hash: str,
    expected_reason: str,
) -> None:
    observed_steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={hash_field: queued_hash},
        observed_worker_steps=observed_steps,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == expected_reason
    assert observed_steps == ["download"]
    assert captions == []


@pytest.mark.parametrize("hash_field", ["source_video_hash", "source_sha256"])
def test_worker_accepts_matching_uppercase_queued_source_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    hash_field: str,
) -> None:
    source_hash = hashlib.sha256(b"source-video").hexdigest().upper()

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={hash_field: source_hash},
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == 1
    assert json.loads(terminal["output_url"])["source_sha256"] == source_hash.lower()


def test_worker_rejects_same_size_download_receipt_hash_mismatch_before_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_steps: list[str] = []
    source = tmp_path / "workspace" / "source.mp4"
    receipt = video_edit_media_transport.DownloadReceipt(
        path=str(source),
        bytes_written=len(b"source-video"),
        sha256="f" * 64,
        lane="large_media",
        transport="fixture",
        declared_bytes=len(b"source-video"),
    )

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        source_download_receipt_override=receipt,
        observed_worker_steps=observed_steps,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "download_receipt_invalid"
    assert observed_steps == ["download"]
    assert captions == []


def _source_evidence_patch(location: str, value: object) -> dict:
    if location.startswith("metadata_manifest."):
        return {
            "source_metadata": {
                "source_manifest": {location.split(".", 1)[1]: value}
            }
        }
    if location.startswith("metadata."):
        return {"source_metadata": {location.split(".", 1)[1]: value}}
    if location.startswith("manifest."):
        return {"source_manifest": {location.split(".", 1)[1]: value}}
    return {location: value}


@pytest.mark.parametrize(
    "location",
    [
        "metadata.source_video_hash",
        "metadata.source_sha256",
        "metadata.sha256",
        "manifest.source_video_hash",
        "manifest.source_sha256",
        "manifest.sha256",
        "metadata_manifest.source_video_hash",
        "metadata_manifest.source_sha256",
        "metadata_manifest.sha256",
    ],
)
def test_worker_rejects_each_malformed_nested_source_hash_before_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    location: str,
) -> None:
    observed_steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch=_source_evidence_patch(location, "not-a-sha256"),
        observed_worker_steps=observed_steps,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_source_hash_invalid"
    assert observed_steps == ["download"]
    assert captions == []


def test_worker_rejects_conflicting_source_hash_evidence_before_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_steps: list[str] = []
    actual_sha256 = hashlib.sha256(b"source-video").hexdigest()

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={
            "source_video_hash": actual_sha256,
            "source_metadata": {
                "source_sha256": "f" * 64,
                "source_manifest": {"sha256": actual_sha256},
            },
        },
        observed_worker_steps=observed_steps,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_source_hash_mismatch"
    assert observed_steps == ["download"]
    assert captions == []


@pytest.mark.parametrize(
    "location",
    [
        "source_file_size",
        "metadata.bytes",
        "metadata.actual_bytes",
        "metadata.file_size",
        "manifest.source_file_size",
        "manifest.bytes",
        "manifest.actual_bytes",
        "manifest.file_size",
        "metadata_manifest.source_file_size",
        "metadata_manifest.bytes",
        "metadata_manifest.actual_bytes",
        "metadata_manifest.file_size",
    ],
)
def test_worker_rejects_each_mismatched_source_size_before_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    location: str,
) -> None:
    observed_steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch=_source_evidence_patch(location, len(b"source-video") + 1),
        observed_worker_steps=observed_steps,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_source_size_mismatch"
    assert observed_steps == ["download"]
    assert captions == []


@pytest.mark.parametrize(
    "location",
    [
        "manifest.source_file_size",
        "manifest.bytes",
        "manifest.actual_bytes",
        "manifest.file_size",
        "metadata_manifest.source_file_size",
        "metadata_manifest.bytes",
        "metadata_manifest.actual_bytes",
        "metadata_manifest.file_size",
    ],
)
def test_worker_rejects_each_malformed_manifest_source_size_before_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    location: str,
) -> None:
    observed_steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch=_source_evidence_patch(location, True),
        observed_worker_steps=observed_steps,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_source_size_invalid"
    assert observed_steps == ["download"]
    assert captions == []


def test_worker_accepts_reconciled_source_hash_and_size_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    actual_sha256 = hashlib.sha256(b"source-video").hexdigest()
    actual_bytes = len(b"source-video")

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={
            "source_video_hash": actual_sha256,
            "source_sha256": actual_sha256.upper(),
            "source_file_size": actual_bytes,
            "source_manifest": {
                "source_video_hash": actual_sha256,
                "source_sha256": actual_sha256.upper(),
                "sha256": actual_sha256,
                "source_file_size": actual_bytes,
                "bytes": actual_bytes,
                "actual_bytes": actual_bytes,
                "file_size": actual_bytes,
            },
            "source_metadata": {
                "source_video_hash": actual_sha256.upper(),
                "source_sha256": actual_sha256,
                "sha256": actual_sha256.upper(),
                "bytes": actual_bytes,
                "actual_bytes": actual_bytes,
                "file_size": actual_bytes,
                "source_manifest": {
                    "sha256": actual_sha256,
                    "source_file_size": actual_bytes,
                    "bytes": actual_bytes,
                    "actual_bytes": actual_bytes,
                    "file_size": actual_bytes,
                },
            },
        },
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == 1


def test_worker_accepts_missing_manifest_source_size_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={
            "source_manifest": {},
            "source_metadata": {"source_manifest": {}},
        },
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == 1


def test_worker_accepts_zero_manifest_source_size_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    zero_sizes = {
        "source_file_size": 0,
        "bytes": "0",
        "actual_bytes": 0,
        "file_size": "0",
    }

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={
            "source_manifest": dict(zero_sizes),
            "source_metadata": {"source_manifest": dict(zero_sizes)},
        },
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == 1


def test_worker_promotes_actual_source_deadline_before_assets_and_never_shortens(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transport_evidence: dict = {"downloads": [], "deliveries": []}
    policy_evidence: dict = {
        "started_at": 10.0,
        "adaptive_results": [100, 500, 300],
    }
    source_bytes = 2_048
    manual_plan = {
        "trim": {"start_ms": 0, "end_ms": 2_000},
        "concat_inputs": ["queued-concat.mp4"],
        "logo_overlay": {"position": "top_right", "path": "queued-logo.png"},
        "subtitle_file": "queued-subtitle.srt",
        "brightness_percent": 110,
    }

    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_plan=manual_plan,
        payload_patch={
            "source_file_size": source_bytes,
            "concat_sources": [
                {"file_id": "concat-file", "file_name": "concat.mp4"}
            ],
            "logo_source": {"file_id": "logo-file", "file_name": "logo.png"},
            "subtitle_source": {
                "file_id": "subtitle-file",
                "file_name": "subtitle.srt",
            },
        },
        downloaded_probe={
            "ok": True,
            "reason": "",
            "duration": 1_000.0,
            "duration_ms": 1_000_000,
            "width": 1280,
            "height": 720,
            "fps": 25.0,
            "has_video": True,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
            "bytes": source_bytes,
        },
        transport_evidence=transport_evidence,
        worker_policy_evidence=policy_evidence,
    )

    assert terminal["status"] == "succeeded"
    assert len(policy_evidence["adaptive_deadline_calls"]) == 3
    events = policy_evidence["events"]
    download_indexes = [
        index for index, event in enumerate(events) if event == "download"
    ]
    assert events.index("probe") < events.index("adaptive:2") < download_indexes[1]
    download_deadlines = [
        call["deadline_monotonic"]
        for call in transport_evidence["download_calls"]
    ]
    assert download_deadlines == [110.0, 510.0, 510.0, 510.0]
    final_promotion = policy_evidence["adaptive_deadline_calls"][2]
    assert final_promotion["source_bytes"] == sum(
        call["bytes_written"] for call in transport_evidence["download_calls"]
    )
    assert policy_evidence["executor_calls"][0]["deadline_monotonic"] == 510.0


@pytest.mark.parametrize(
    ("mode", "expected_operation"),
    [("manual", "manual"), ("split", "split")],
)
def test_worker_uses_one_adaptive_absolute_deadline_and_admission_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    expected_operation: str,
) -> None:
    evidence: dict = {"started_at": 41.5}

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode=mode,
        downloaded_probe={
            "ok": True,
            "reason": "",
            "duration": 1_000.0,
            "duration_ms": 1_000_000,
            "width": 1280,
            "height": 720,
            "fps": 25.0,
            "has_video": True,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
            "bytes": len(b"source-video"),
        },
        worker_policy_evidence=evidence,
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == (2 if mode == "split" else 1)
    assert evidence["monotonic_calls"] == 1
    assert evidence["events"].index("classify") < evidence["events"].index(
        "download"
    )
    assert evidence["events"].index("admit") < evidence["events"].index(
        "execute"
    )
    assert len(evidence["adaptive_deadline_calls"]) == (
        3 if mode == "manual" else 2
    )
    provisional = evidence["adaptive_deadline_calls"][0]
    promoted = evidence["adaptive_deadline_calls"][-1]
    assert promoted["duration_seconds"] == 1_000.0
    assert promoted["result"] > provisional["result"]
    expected_deadline = evidence["started_at"] + promoted["result"]
    execution = evidence["executor_calls"][0]
    admission = evidence["admission_calls"][0]
    decision = evidence["admission_decisions"][0]
    assert admission["operation"] == expected_operation
    assert admission["source_bytes"] == len(b"source-video")
    assert admission["materialized_input_bytes"] == len(b"source-video")
    assert admission["output_count"] == (1 if mode == "manual" else 2)
    assert execution["mode"] == mode
    assert execution["deadline_monotonic"] == expected_deadline
    assert execution["workspace_budget_bytes"] == decision.evidence[
        "estimated_bytes"
    ]
    assert evidence["delivery_deadlines"] == [expected_deadline] * len(captions)


def test_video_edit_render_timeout_uses_dedicated_ceiling_not_generic_600_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence: dict = {
        "started_at": 10.0,
        "adaptive_results": [120, 1_800, 1_800],
    }
    monkeypatch.setattr(local_worker, "LOCAL_WORKER_MAX_JOB_SECONDS", 600)
    monkeypatch.setattr(local_worker, "VIDEO_EDIT_MAX_DEADLINE_SECONDS", 3_600)

    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={"max_render_seconds": 30},
        downloaded_probe={
            "ok": True,
            "reason": "",
            "duration": 2_400.0,
            "duration_ms": 2_400_000,
            "width": 1920,
            "height": 1080,
            "fps": 25.0,
            "has_video": True,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
            "bytes": len(b"source-video"),
        },
        worker_policy_evidence=evidence,
    )

    assert terminal["status"] == "succeeded"
    executor = evidence["executor_calls"][0]
    assert executor["timeout"] == 3_600
    assert executor["timeout"] != local_worker.LOCAL_WORKER_MAX_JOB_SECONDS
    assert executor["deadline_monotonic"] == 1_810.0


def test_worker_admits_all_actual_asset_receipts_before_executor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transport_evidence: dict = {"downloads": [], "deliveries": []}
    policy_evidence: dict = {"started_at": 75.0}
    observed_plans: list[dict] = []
    manual_plan = {
        "trim": {"start_ms": 0, "end_ms": 2_000},
        "concat_inputs": ["queued-concat.mp4"],
        "logo_overlay": {"position": "top_right", "path": "queued-logo.png"},
        "subtitle_file": "queued-subtitle.srt",
        "brightness_percent": 110,
    }

    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_plan=manual_plan,
        payload_patch={
            "source_file_size": 2_048,
            "concat_sources": [
                {"file_id": "concat-file", "file_name": "concat.mp4"}
            ],
            "logo_source": {"file_id": "logo-file", "file_name": "logo.png"},
            "subtitle_source": {
                "file_id": "subtitle-file",
                "file_name": "subtitle.srt",
            },
        },
        observed_plans=observed_plans,
        transport_evidence=transport_evidence,
        worker_policy_evidence=policy_evidence,
    )

    assert terminal["status"] == "succeeded"
    calls = transport_evidence["download_calls"]
    assert [call["file_id"] for call in calls] == [
        "source-file",
        "concat-file",
        "logo-file",
        "subtitle-file",
    ]
    admission = policy_evidence["admission_calls"][0]
    actual_sizes = [call["bytes_written"] for call in calls]
    assert admission["operation"] == "concat"
    assert admission["source_bytes"] == actual_sizes[0]
    assert admission["asset_bytes"] == actual_sizes[1:]
    assert admission["materialized_input_bytes"] == sum(actual_sizes)
    assert policy_evidence["events"].count("download") == 4
    assert policy_evidence["events"].index("admit") > max(
        index
        for index, event in enumerate(policy_evidence["events"])
        if event == "download"
    )
    classified = policy_evidence["classification_calls"][0]["plan"]
    assert classified.get("input_video", "") == ""
    assert classified["concat_inputs"] == [True]
    assert classified["subtitle_file"] is True
    assert "path" not in classified["logo_overlay"]
    executed = observed_plans[0]
    assert Path(executed["input_video"]).name == "source.mp4"
    assert [Path(path).name for path in executed["concat_inputs"]] == [
        "concat_001.mp4"
    ]
    assert Path(executed["logo_overlay"]["path"]).name == "logo.png"
    assert Path(executed["subtitle_file"]).name == "subtitle.srt"


def test_worker_uses_maximum_of_all_compound_workspace_profiles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transport_evidence: dict = {"downloads": [], "deliveries": []}
    policy_evidence: dict = {
        "admission_by_operation": {
            "concat": {
                "accepted": True,
                "reason": "accepted",
                "estimated_bytes": 11_000,
            },
            "overlay": {
                "accepted": True,
                "reason": "accepted",
                "estimated_bytes": 33_000,
            },
            "transcode": {
                "accepted": True,
                "reason": "accepted",
                "estimated_bytes": 22_000,
            },
        }
    }
    manual_plan = {
        "concat_inputs": ["queued-concat.mp4"],
        "logo_overlay": {"position": "top_right", "path": "queued-logo.png"},
        "brightness_percent": 110,
    }

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_plan=manual_plan,
        payload_patch={
            "concat_sources": [
                {"file_id": "concat-file", "file_name": "concat.mp4"}
            ],
            "logo_source": {"file_id": "logo-file", "file_name": "logo.png"},
        },
        transport_evidence=transport_evidence,
        worker_policy_evidence=policy_evidence,
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == 1
    assert policy_evidence["classification_calls"][0]["result"] == (
        local_worker.video_edit_long_media.WHOLE_TIMELINE_REQUIRED
    )
    assert [
        call["operation"] for call in policy_evidence["admission_calls"]
    ] == ["concat", "overlay", "transcode"]
    assert policy_evidence["executor_calls"][0]["workspace_budget_bytes"] == 33_000


def test_worker_rejects_when_any_compound_workspace_profile_rejects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transport_evidence: dict = {"downloads": [], "deliveries": []}
    policy_evidence: dict = {
        "admission_by_operation": {
            "concat": {
                "accepted": True,
                "reason": "accepted",
                "estimated_bytes": 11_000,
            },
            "overlay": {
                "accepted": False,
                "reason": "insufficient_overlay_workspace",
                "estimated_bytes": 33_000,
            },
            "transcode": {
                "accepted": True,
                "reason": "accepted",
                "estimated_bytes": 22_000,
            },
        }
    }
    manual_plan = {
        "concat_inputs": ["queued-concat.mp4"],
        "logo_overlay": {"position": "top_right", "path": "queued-logo.png"},
        "brightness_percent": 110,
    }

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_plan=manual_plan,
        payload_patch={
            "concat_sources": [
                {"file_id": "concat-file", "file_name": "concat.mp4"}
            ],
            "logo_source": {"file_id": "logo-file", "file_name": "logo.png"},
        },
        transport_evidence=transport_evidence,
        worker_policy_evidence=policy_evidence,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "insufficient_overlay_workspace"
    assert [
        call["operation"] for call in policy_evidence["admission_calls"]
    ] == ["concat", "overlay", "transcode"]
    assert policy_evidence["executor_calls"] == []
    assert captions == []


def test_worker_workspace_rejection_fails_closed_before_executor_and_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence: dict = {"reject_admission_reason": "insufficient_workspace"}
    observed_steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        observed_worker_steps=observed_steps,
        worker_policy_evidence=evidence,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "insufficient_workspace"
    assert evidence["executor_calls"] == []
    assert "execute" not in observed_steps
    assert captions == []


def _durable_resume_artifact(index: int) -> dict:
    return {
        "index": index,
        "message_id": str(9_000 + index),
        "file_id": f"durable-file-{index}",
        "size": 4_096,
        "sha256": f"{index:x}" * 64,
        "ffprobe": {
            "ok": True,
            "has_video": True,
            "video_codec": "h264",
            "duration_ms": 1_000,
            "width": 640,
            "height": 360,
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "full_decode": True,
        },
        "delivery_method": "sendVideo",
        "bytes_sent": 4_096,
    }


def _durable_resume_contract(
    receipts: list[dict],
    *,
    expected_output_count: int,
    cursor: dict | None,
    compatibility: str,
) -> dict:
    digest = hashlib.sha256(
        json.dumps(
            receipts,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "video-local-edit-receipt-prefix-resume",
        "version": 1,
        "expected_output_count": expected_output_count,
        "artifact_receipt_prefix": receipts,
        "prefix_count": len(receipts),
        "prefix_digest": digest,
        "compatibility": compatibility,
        "delivery_cursor": cursor,
    }


@pytest.mark.parametrize(
    "cursor_state",
    ["sending", "unknown", "accepted", "delivered"],
)
def test_durable_delivery_cursor_fences_render_and_transport_before_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cursor_state: str,
) -> None:
    receipt = _durable_resume_artifact(1)
    receipts = [receipt] if cursor_state in {"accepted", "delivered"} else []
    cursor_kwargs = {
        "state": cursor_state,
        "output_index": 1,
        "attempt_id": "resume-manual-attempt-1",
    }
    if receipts:
        cursor_kwargs.update(
            message_id=receipt["message_id"],
            file_id=receipt["file_id"],
        )
    cursor = local_worker.video_edit_long_media.DeliveryCursor(
        **cursor_kwargs
    )
    setup: list[str] = []
    steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        observed_worker_steps=steps,
        setup_evidence=setup,
        job_patch={
            "source_sha256": "a" * 64,
            "resume_contract": _durable_resume_contract(
                receipts,
                expected_output_count=1,
                cursor=cursor.to_mapping(),
                compatibility="strict",
            ),
        },
    )

    detail = json.loads(terminal["detail"])
    assert "ffmpeg_lookup" not in setup
    assert "workspace" not in setup
    assert "download" not in setup
    assert "download" not in steps
    assert "delivery" not in steps
    assert captions == []
    if cursor_state in {"sending", "unknown"}:
        assert terminal["status"] == "failed"
        assert detail["stage"] == "delivery_unknown"
        assert detail["delivery_cursor"]["state"] == "unknown"
        assert terminal["output_file_id"] == ""
    else:
        assert terminal["status"] == "succeeded"
        assert detail["stage"] == "delivered"
        assert detail["delivery_cursor"]["state"] == "delivered"
        assert terminal["output_file_id"] == receipt["file_id"]


@pytest.mark.parametrize("compatibility", ["strict", "legacy_receipt_only"])
def test_durable_resume_manual_full_prefix_finalizes_without_setup_or_resend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    compatibility: str,
) -> None:
    receipt = _durable_resume_artifact(1)
    cursor = (
        local_worker.video_edit_long_media.DeliveryCursor(
            state="accepted",
            output_index=1,
            attempt_id="resume-manual-accepted-1",
            message_id=receipt["message_id"],
            file_id=receipt["file_id"],
        ).to_mapping()
        if compatibility == "strict"
        else None
    )
    setup: list[str] = []
    steps: list[str] = []
    updates: list[dict] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        observed_worker_steps=steps,
        setup_evidence=setup,
        update_evidence=updates,
        job_patch={
            "source_sha256": "a" * 64,
            "resume_contract": _durable_resume_contract(
                [receipt],
                expected_output_count=1,
                cursor=cursor,
                compatibility=compatibility,
            ),
        },
    )

    terminal_receipt = json.loads(terminal["output_url"])
    assert terminal["status"] == "succeeded"
    assert setup == ["cleanup_intent"]
    assert steps == []
    assert captions == []
    assert terminal_receipt["source_video_path"] == "source.mp4"
    assert terminal_receipt["source_sha256"] == "a" * 64
    assert terminal_receipt["output_path"] == "toan_aas_video_edit_2701.mp4"
    assert terminal_receipt["artifacts"] == [receipt]
    assert terminal_receipt["delivery_message_id"] == receipt["message_id"]
    assert terminal_receipt["delivery_file_id"] == receipt["file_id"]
    if compatibility == "strict":
        delivered_updates = [
            json.loads(update["detail"])
            for update in updates
            if update["status"] == "running"
            and json.loads(update["detail"]).get("delivery_cursor", {}).get("state") == "delivered"
        ]
        assert len(delivered_updates) == 1
        assert delivered_updates[0]["delivery_cursor"]["message_id"] == receipt["message_id"]
        assert delivered_updates[0]["delivery_cursor"]["file_id"] == receipt["file_id"]


def test_durable_resume_full_prefix_cleans_existing_project_only_after_terminal_ack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipt = _durable_resume_artifact(1)
    delivered = local_worker.video_edit_long_media.DeliveryCursor(
        state="delivered",
        output_index=1,
        attempt_id="resume-manual-delivered-cleanup",
        message_id=receipt["message_id"],
        file_id=receipt["file_id"],
    )
    setup: list[str] = []
    cleanup_order: list[str] = []
    cleanup_intents: list[dict] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        setup_evidence=setup,
        use_real_cleanup=True,
        cleanup_order_evidence=cleanup_order,
        cleanup_intent_evidence=cleanup_intents,
        job_patch={
            "source_sha256": "a" * 64,
            "resume_contract": _durable_resume_contract(
                [receipt],
                expected_output_count=1,
                cursor=delivered.to_mapping(),
                compatibility="strict",
            ),
        },
    )

    assert terminal["status"] == "succeeded"
    assert captions == []
    assert setup == []
    assert cleanup_intents == [
        {
            "schema": local_worker.video_edit_cleanup_audit.PROJECT_CLEANUP_AUDIT_SCHEMA,
            "version": local_worker.video_edit_cleanup_audit.PROJECT_CLEANUP_AUDIT_VERSION,
            "job_id": 2701,
            "delivery_claim_attempt": 1,
            "delivery_owner": local_worker.LOCAL_WORKER_INSTANCE_ID,
            "workspace_key": "job_2701_claim_1",
            "tombstone_key": "job_2701_claim_1",
            "workspace_present": True,
            "target_workspace_key": "job_2701",
        }
    ]
    assert cleanup_order.index("terminal_ack") < cleanup_order.index(
        "cleanup_reconcile"
    )
    assert not (tmp_path / "job_2701").exists()


def test_durable_resume_full_prefix_without_project_is_path_free_and_harmless(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipt = _durable_resume_artifact(1)
    cleanup_order: list[str] = []
    cleanup_intents: list[dict] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        use_real_cleanup=True,
        resume_project_present=False,
        cleanup_order_evidence=cleanup_order,
        cleanup_intent_evidence=cleanup_intents,
        job_patch={
            "source_sha256": "a" * 64,
            "resume_contract": _durable_resume_contract(
                [receipt],
                expected_output_count=1,
                cursor=None,
                compatibility="legacy_receipt_only",
            ),
        },
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "succeeded"
    assert captions == []
    assert detail["cleanup_intent"] == {
        "persisted": False,
        "workspace_present": False,
    }
    assert cleanup_intents == []
    assert cleanup_order == ["terminal_ack"]
    assert not (tmp_path / "job_2701").exists()


def test_durable_resume_split_partial_prefix_sends_only_suffix_and_advances_accepted_first(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prefix_receipt = _durable_resume_artifact(1)
    accepted = local_worker.video_edit_long_media.DeliveryCursor(
        state="accepted",
        output_index=1,
        attempt_id="resume-split-accepted-1",
        message_id=prefix_receipt["message_id"],
        file_id=prefix_receipt["file_id"],
    )
    updates: list[dict] = []
    order: list[str] = []
    steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        payload_patch={
            "split_ranges": [
                {"index": 1, "start_ms": 0, "end_ms": 1_000},
                {"index": 2, "start_ms": 1_000, "end_ms": 2_000},
            ],
        },
        observed_worker_steps=steps,
        update_evidence=updates,
        checkpoint_order_evidence=order,
        job_patch={
            "source_sha256": hashlib.sha256(b"source-video").hexdigest(),
            "resume_contract": _durable_resume_contract(
                [prefix_receipt],
                expected_output_count=2,
                cursor=accepted.to_mapping(),
                compatibility="strict",
            ),
        },
    )

    terminal_receipt = json.loads(terminal["output_url"])
    assert terminal["status"] == "succeeded"
    assert captions == ["✅ Phần 2/2 · 1.0 giây · Miễn phí · 0 Xu"]
    assert steps == ["download", "probe", "validate", "execute", "delivery"]
    assert terminal_receipt["artifacts"][0] == prefix_receipt
    assert [item["index"] for item in terminal_receipt["artifacts"]] == [1, 2]
    assert terminal_receipt["delivery_message_id"] == terminal_receipt["artifacts"][-1]["message_id"]
    assert terminal_receipt["delivery_file_id"] == terminal_receipt["artifacts"][-1]["file_id"]
    def parsed_detail(update: dict) -> dict:
        try:
            value = json.loads(update["detail"])
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    delivered_updates = [
        parsed_detail(update)
        for update in updates
        if update["status"] == "running"
        and parsed_detail(update).get("delivery_cursor", {}).get("state") == "delivered"
    ]
    assert delivered_updates[0]["delivery_cursor"] == {
        **accepted.to_mapping(),
        "state": "delivered",
    }
    assert order.index("receipt_checkpoint") < order.index("delivery_accepted")


def test_durable_resume_split_legacy_partial_prefix_becomes_strict_only_for_suffix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prefix_receipt = _durable_resume_artifact(1)
    updates: list[dict] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        payload_patch={
            "split_ranges": [
                {"index": 1, "start_ms": 0, "end_ms": 1_000},
                {"index": 2, "start_ms": 1_000, "end_ms": 2_000},
            ],
        },
        update_evidence=updates,
        job_patch={
            "source_sha256": hashlib.sha256(b"source-video").hexdigest(),
            "resume_contract": _durable_resume_contract(
                [prefix_receipt],
                expected_output_count=2,
                cursor=None,
                compatibility="legacy_receipt_only",
            ),
        },
    )

    terminal_receipt = json.loads(terminal["output_url"])
    cursor_states = []
    for update in updates:
        try:
            detail = json.loads(update["detail"])
        except (TypeError, json.JSONDecodeError):
            continue
        cursor = detail.get("delivery_cursor") if isinstance(detail, dict) else None
        if isinstance(cursor, dict):
            cursor_states.append((cursor["state"], cursor["output_index"]))
    assert terminal["status"] == "succeeded"
    assert captions == ["✅ Phần 2/2 · 1.0 giây · Miễn phí · 0 Xu"]
    assert cursor_states[:3] == [("sending", 2), ("accepted", 2), ("delivered", 2)]
    assert terminal["output_file_id"] == terminal_receipt["artifacts"][-1]["file_id"]
    assert terminal_receipt["delivery_file_id"] == terminal_receipt["artifacts"][-1]["file_id"]


def test_durable_resume_split_full_prefix_finalizes_with_deterministic_names_without_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    receipts = [_durable_resume_artifact(1), _durable_resume_artifact(2)]
    last = receipts[-1]
    delivered = local_worker.video_edit_long_media.DeliveryCursor(
        state="delivered",
        output_index=2,
        attempt_id="resume-split-delivered-2",
        message_id=last["message_id"],
        file_id=last["file_id"],
    )
    setup: list[str] = []
    steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        payload_patch={
            "split_ranges": [
                {"index": 1, "start_ms": 0, "end_ms": 1_000},
                {"index": 2, "start_ms": 1_000, "end_ms": 2_000},
            ],
        },
        observed_worker_steps=steps,
        setup_evidence=setup,
        job_patch={
            "source_sha256": "b" * 64,
            "resume_contract": _durable_resume_contract(
                receipts,
                expected_output_count=2,
                cursor=delivered.to_mapping(),
                compatibility="strict",
            ),
        },
    )

    terminal_receipt = json.loads(terminal["output_url"])
    assert terminal["status"] == "succeeded"
    assert setup == ["cleanup_intent"]
    assert steps == []
    assert captions == []
    assert terminal_receipt["output_path"] == (
        "toan_aas_part_001_of_002.mp4,toan_aas_part_002_of_002.mp4"
    )
    assert terminal_receipt["artifacts"] == receipts
    assert terminal_receipt["delivery_file_id"] == last["file_id"]


def test_durable_resume_rejects_uncontracted_nonempty_prefix_before_setup_or_resend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    setup: list[str] = []
    steps: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        observed_worker_steps=steps,
        setup_evidence=setup,
        job_patch={
            "artifact_receipt_prefix": [_durable_resume_artifact(1)],
            "delivery_cursor": 1,
            "source_sha256": "c" * 64,
        },
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "failed_no_charge"
    assert detail["reason"] == "video_local_edit_resume_contract_invalid"
    assert setup == []
    assert steps == []
    assert captions == []


@pytest.mark.parametrize(
    ("delivery_method", "bytes_sent", "sha256"),
    [
        pytest.param(
            "sendPhoto",
            len(b"part-1"),
            hashlib.sha256(b"part-1").hexdigest(),
            id="method",
        ),
        pytest.param(
            "sendVideo",
            len(b"part-1") + 1,
            hashlib.sha256(b"part-1").hexdigest(),
            id="bytes",
        ),
        pytest.param(
            "sendVideo",
            len(b"part-1"),
            "f" * 64,
            id="sha256",
        ),
    ],
)
def test_worker_rejects_mismatched_delivery_evidence_without_next_send(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    delivery_method: str,
    bytes_sent: int,
    sha256: str,
) -> None:
    mismatched = video_edit_media_transport.DeliveryReceipt(
        message_id="1001",
        file_id="file-1",
        delivery_method=delivery_method,
        bytes_sent=bytes_sent,
        sha256=sha256,
    )

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        delivery_receipts_override=[mismatched],
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "delivery_unknown"
    assert detail["reason"] == "telegram_delivery_receipt_invalid"
    assert detail["delivered"] == 0
    assert detail["charge"] == 0
    assert terminal["output_file_id"] == ""
    assert captions == ["✅ Phần 1/2 · 1.0 giây · Miễn phí · 0 Xu"]


def test_manual_acceptance_is_checkpointed_before_liveness_with_split_shape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updates: list[dict] = []
    order: list[str] = []
    liveness: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        liveness_evidence=liveness,
        update_evidence=updates,
        checkpoint_order_evidence=order,
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == 1
    checkpoints = []
    for update in updates:
        if update["status"] != "running":
            continue
        detail = json.loads(update["detail"])
        if "artifact_receipts" in detail:
            checkpoints.append(detail)
    assert [
        checkpoint["delivery_cursor"]["state"] for checkpoint in checkpoints
    ] == ["sending", "accepted", "delivered"]
    accepted_checkpoint = checkpoints[1]
    artifacts = accepted_checkpoint["artifact_receipts"]
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["index"] == 1
    assert artifact["message_id"] == "1001"
    assert artifact["file_id"] == "file-1"
    assert artifact["delivery_method"] == "sendVideo"
    assert artifact["bytes_sent"] == artifact["size"] == len(b"rendered-video")
    assert artifact["sha256"] == hashlib.sha256(b"rendered-video").hexdigest()
    assert video_editengine1.valid_mp4_delivery_probe(artifact["ffprobe"])
    accepted_index = order.index("delivery_accepted")
    checkpoint_index = order.index("receipt_checkpoint", accepted_index)
    next_health_index = order.index("assert_healthy", accepted_index + 1)
    assert accepted_index < checkpoint_index < next_health_index
    receipt = json.loads(terminal["output_url"])
    assert receipt["artifacts"] == artifacts
    assert receipt["delivery_message_id"] == artifact["message_id"]
    assert receipt["delivery_file_id"] == artifact["file_id"]


def test_update_job_forwards_liveness_stage_and_lease_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict, int, float | None]] = []

    def fake_http_json(
        method: str,
        path: str,
        payload: dict,
        timeout: int,
        *,
        total_deadline_seconds: float | None = None,
    ) -> dict:
        calls.append((method, path, payload, timeout, total_deadline_seconds))
        return {"ok": True}

    monkeypatch.setattr(local_worker, "http_json", fake_http_json)

    local_worker.update_job(
        2701,
        "running",
        "{}",
        stage="processing_video",
        lease_seconds=900,
    )
    local_worker.update_job(2701, "running", "{}")
    local_worker.update_job(
        2702,
        "succeeded",
        "legacy-detail",
        "legacy-output-url",
        "legacy-file-id",
    )
    local_worker.update_job(2703, "running", "{}", stage="delivering")
    local_worker.update_job(2704, "running", "{}", lease_seconds=600)

    assert calls[0] == (
        "POST",
        "/internal/worker/job_update",
        {
            "job_id": 2701,
            "status": "running",
            "worker_id": local_worker.LOCAL_WORKER_ID,
            "error_short": "{}",
            "output_url": "",
            "output_file_id": "",
            "stage": "processing_video",
            "lease_seconds": 900,
        },
        20,
        local_worker.VIDEO_EDIT_LIVENESS_UPDATE_TIMEOUT_SECONDS,
    )
    assert calls[1] == (
        "POST",
        "/internal/worker/job_update",
        {
            "job_id": 2701,
            "status": "running",
            "worker_id": local_worker.LOCAL_WORKER_ID,
            "error_short": "{}",
            "output_url": "",
            "output_file_id": "",
        },
        20,
        None,
    )
    assert calls[2] == (
        "POST",
        "/internal/worker/job_update",
        {
            "job_id": 2702,
            "status": "succeeded",
            "worker_id": local_worker.LOCAL_WORKER_ID,
            "error_short": "legacy-detail",
            "output_url": "legacy-output-url",
            "output_file_id": "legacy-file-id",
        },
        20,
        None,
    )
    assert calls[3] == (
        "POST",
        "/internal/worker/job_update",
        {
            "job_id": 2703,
            "status": "running",
            "worker_id": local_worker.LOCAL_WORKER_ID,
            "error_short": "{}",
            "output_url": "",
            "output_file_id": "",
            "stage": "delivering",
        },
        20,
        local_worker.VIDEO_EDIT_LIVENESS_UPDATE_TIMEOUT_SECONDS,
    )
    assert calls[4] == (
        "POST",
        "/internal/worker/job_update",
        {
            "job_id": 2704,
            "status": "running",
            "worker_id": local_worker.LOCAL_WORKER_ID,
            "error_short": "{}",
            "output_url": "",
            "output_file_id": "",
            "lease_seconds": 600,
        },
        20,
        local_worker.VIDEO_EDIT_LIVENESS_UPDATE_TIMEOUT_SECONDS,
    )


def test_http_json_total_deadline_closes_stalled_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    total_deadline_seconds = 0.05
    response_events: list[str] = []

    class FakeResponse:
        def __init__(self) -> None:
            self.closed = False
            self.closed_event = threading.Event()

        def __enter__(self):
            response_events.append("enter")
            return self

        def __exit__(self, *_args) -> None:
            response_events.append("exit")

        def close(self) -> None:
            self.closed = True
            response_events.append("close")
            self.closed_event.set()

        def read(self, size: int | None = None) -> bytes:
            if size is None or size <= 0 or size > 512 * 1024 + 1:
                pytest.fail("response reads must use the bounded JSON body limit")
            response_events.append("read")
            # One second is only a safety escape hatch for a broken cancellation
            # path; the real deadline must close the response much sooner.
            if not self.closed_event.wait(timeout=1):
                pytest.fail("the total deadline did not close the stalled response")
            raise OSError("response closed by total deadline")

    response = FakeResponse()

    def fake_urlopen(_request, timeout=0) -> FakeResponse:
        assert 0 < timeout <= total_deadline_seconds
        return response

    monkeypatch.setattr(local_worker.urllib.request, "urlopen", fake_urlopen)

    started_at = time.monotonic()
    with pytest.raises(TimeoutError):
        local_worker.http_json(
            "GET",
            "/internal/worker/stalled",
            timeout=20,
            total_deadline_seconds=total_deadline_seconds,
        )
    elapsed = time.monotonic() - started_at

    assert response.closed is True
    assert elapsed < 0.5
    assert [event for event in response_events if event != "close"] == [
        "enter",
        "read",
        "exit",
    ]
    assert response_events.index("read") < response_events.index("close")
    assert response_events.index("close") < response_events.index("exit")


def test_http_json_worker_credentials_use_no_redirect_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[tuple[str, float]] = []

    class Response:
        headers: dict[str, str] = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            assert 0 < size <= 512 * 1024 + 1
            return b'{"ok":true}'

    def open_no_redirect(request, timeout):
        opened.append((str(request.full_url), float(timeout)))
        assert request.get_header("Authorization") == (
            "Bearer " + local_worker.LOCAL_WORKER_TOKEN
        )
        assert request.get_header("X-local-worker-token") == (
            local_worker.LOCAL_WORKER_TOKEN
        )
        return Response()

    monkeypatch.setattr(local_worker, "telegram_open_no_redirect", open_no_redirect)
    monkeypatch.setattr(
        local_worker.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("worker credentials bypassed no-redirect transport")
        ),
    )

    assert local_worker.http_json("GET", "/internal/worker/poll", timeout=9) == {
        "ok": True
    }
    assert opened == [(local_worker.endpoint("/internal/worker/poll"), 9.0)]


def test_http_json_without_total_deadline_rejects_oversized_json_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OversizedResponse:
        headers: dict[str, str] = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            assert size == 512 * 1024 + 1
            return b"x" * size

    monkeypatch.setattr(
        local_worker,
        "telegram_open_no_redirect",
        lambda _request, timeout: OversizedResponse(),
    )
    monkeypatch.setattr(
        local_worker.urllib.request,
        "urlopen",
        lambda _request, timeout: OversizedResponse(),
    )

    with pytest.raises(ValueError, match="http_json_response_too_large"):
        local_worker.http_json("GET", "/internal/worker/poll", timeout=9)


def test_telegram_json_rejects_oversized_response_before_json_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OversizedResponse:
        headers: dict[str, str] = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            assert size == local_worker._VIDEO_EDIT_TELEGRAM_JSON_MAX_BYTES + 1
            return b"x" * size

    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        local_worker,
        "telegram_open_no_redirect",
        lambda _request, timeout: OversizedResponse(),
    )

    with pytest.raises(RuntimeError, match="telegram_api_invalid_json"):
        local_worker.telegram_json("getFile", {"file_id": "file-1"})


def test_video_edit_worker_liveness_tracks_real_stages_without_percent_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence: list[str] = []
    liveness_factory_calls: list[tuple[object, object, object, object]] = []

    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        observed_worker_steps=evidence,
        liveness_evidence=evidence,
        liveness_factory_calls=liveness_factory_calls,
    )

    assert terminal["status"] == "succeeded"
    expected_lease = max(30, min(3600, int(local_worker.LOCAL_WORKER_MAX_JOB_SECONDS)))
    expected_interval = min(30, max(5, expected_lease // 3))
    assert liveness_factory_calls == [
        (2701, expected_lease, expected_interval, 1)
    ]
    assert evidence == [
        "start",
        "stage:inspecting_input",
        "assert_healthy",
        "download",
        "assert_healthy",
        "probe",
        "validate",
        "stage:processing_video",
        "assert_healthy",
        "execute",
        "assert_healthy",
        "stage:delivering",
        "assert_healthy",
        "delivery",
        "assert_healthy",
        "stop",
        "assert_healthy",
        "terminal_update",
    ]
    assert evidence.count("assert_healthy") == 7
    assert evidence.count("terminal_update") == 1
    assert not any("percent" in event for event in evidence)


def test_video_edit_liveness_failure_stops_before_one_terminal_and_fences_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        observed_worker_steps=evidence,
        liveness_evidence=evidence,
        liveness_health_failure_at=5,
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "failed_no_charge"
    assert detail["charged_xu"] == 0
    assert detail["reason"] == "video_local_edit_worker_lease_lost"
    assert captions == []
    assert "delivery" not in evidence
    assert evidence == [
        "start",
        "stage:inspecting_input",
        "assert_healthy",
        "download",
        "assert_healthy",
        "probe",
        "validate",
        "stage:processing_video",
        "assert_healthy",
        "execute",
        "assert_healthy",
        "stage:delivering",
        "assert_healthy",
        "stop",
        "terminal_update",
    ]
    assert evidence.count("terminal_update") == 1


def test_video_edit_liveness_loss_after_manual_delivery_preserves_receipt_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        observed_worker_steps=evidence,
        liveness_evidence=evidence,
        liveness_health_failure_at=6,
    )

    detail = json.loads(terminal["detail"])
    receipt = json.loads(terminal["output_url"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "delivery_unknown"
    assert detail["delivered"] == 1
    assert detail["charge"] == 0
    assert terminal["output_file_id"] == "file-1"
    assert receipt["delivery_message_id"] == "1001"
    assert receipt["delivery_file_id"] == "file-1"
    assert [item["file_id"] for item in receipt["artifacts"]] == ["file-1"]
    assert len(captions) == 1
    assert evidence == [
        "start",
        "stage:inspecting_input",
        "assert_healthy",
        "download",
        "assert_healthy",
        "probe",
        "validate",
        "stage:processing_video",
        "assert_healthy",
        "execute",
        "assert_healthy",
        "stage:delivering",
        "assert_healthy",
        "delivery",
        "assert_healthy",
        "stop",
        "terminal_update",
    ]
    assert evidence.count("terminal_update") == 1


def test_video_edit_liveness_loss_during_shutdown_preserves_receipt_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        observed_worker_steps=evidence,
        liveness_evidence=evidence,
        liveness_failure_on_stop=True,
    )

    detail = json.loads(terminal["detail"])
    receipt = json.loads(terminal["output_url"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "delivery_unknown"
    assert detail["reason"] == "video_local_edit_worker_lease_lost"
    assert detail["delivered"] == 1
    assert detail["charge"] == 0
    assert terminal["output_file_id"] == "file-1"
    assert receipt["delivery_message_id"] == "1001"
    assert receipt["delivery_file_id"] == "file-1"
    assert [
        (item["message_id"], item["file_id"])
        for item in receipt["artifacts"]
    ] == [("1001", "file-1")]
    assert len(captions) == 1
    assert evidence == [
        "start",
        "stage:inspecting_input",
        "assert_healthy",
        "download",
        "assert_healthy",
        "probe",
        "validate",
        "stage:processing_video",
        "assert_healthy",
        "execute",
        "assert_healthy",
        "stage:delivering",
        "assert_healthy",
        "delivery",
        "assert_healthy",
        "stop",
        "assert_healthy",
        "terminal_update",
    ]
    assert evidence.count("delivery") == 1
    assert evidence.count("stop") == 1
    assert evidence.count("terminal_update") == 1


def test_split_delivery_fences_each_artifact_before_and_after_send(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence: list[str] = []

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        observed_worker_steps=evidence,
        liveness_evidence=evidence,
    )

    assert terminal["status"] == "succeeded"
    assert len(captions) == 2
    assert evidence == [
        "start",
        "stage:inspecting_input",
        "assert_healthy",
        "download",
        "assert_healthy",
        "probe",
        "validate",
        "stage:processing_video",
        "assert_healthy",
        "execute",
        "assert_healthy",
        "stage:delivering",
        "assert_healthy",
        "delivery",
        "assert_healthy",
        "assert_healthy",
        "delivery",
        "assert_healthy",
        "stop",
        "assert_healthy",
        "terminal_update",
    ]
    assert evidence.count("stage:delivering") == 1
    assert evidence.count("assert_healthy") == 9
    assert evidence.count("delivery") == 2
    assert evidence.count("terminal_update") == 1


def test_split_receipt_size_and_hash_are_computed_before_each_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence: list[str] = []
    original_getsize = local_worker.os.path.getsize
    original_sha256_file = local_worker.video_ai_edit_validation.sha256_file

    def observed_getsize(path) -> int:
        artifact = Path(path)
        if artifact.name in {"part-1.mp4", "part-2.mp4"}:
            evidence.append(f"size:{artifact.stem}")
        return original_getsize(path)

    def observed_sha256_file(path) -> str:
        artifact = Path(path)
        if artifact.name in {"part-1.mp4", "part-2.mp4"}:
            evidence.append(f"sha256:{artifact.stem}")
        return original_sha256_file(path)

    monkeypatch.setattr(local_worker.os.path, "getsize", observed_getsize)
    monkeypatch.setattr(
        local_worker.video_ai_edit_validation,
        "sha256_file",
        observed_sha256_file,
    )

    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="split",
        observed_worker_steps=evidence,
    )

    receipt_order = [
        event
        for event in evidence
        if event == "delivery"
        or event.startswith(("size:part-", "sha256:part-"))
    ]
    assert terminal["status"] == "succeeded"
    assert len(captions) == 2
    assert receipt_order == [
        "size:part-1",
        "sha256:part-1",
        "size:part-2",
        "sha256:part-2",
        "delivery",
        "delivery",
    ]


def test_video_edit_worker_large_media_uses_local_transport_and_document_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    large_bytes = 21 * 1024 * 1024
    evidence: dict = {
        "downloads": [],
        "deliveries": [],
        "full_file_reads": 0,
    }

    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={
            "media_lane": "large_media",
            "source_file_size": large_bytes,
        },
        downloaded_probe={
            "ok": True,
            "reason": "",
            "duration": 90.0,
            "duration_ms": 90_000,
            "width": 1280,
            "height": 720,
            "fps": 25.0,
            "has_video": True,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
            "bytes": large_bytes,
        },
        transport_evidence=evidence,
    )

    receipt = json.loads(terminal["output_url"])
    assert terminal["status"] == "succeeded"
    assert evidence["downloads"] == ["local_bot_api"]
    assert evidence["download_calls"][0]["config"].api_root == (
        "https://tg.toanaas.vn"
    )
    assert evidence["download_calls"][0]["hard_max_bytes"] is None
    assert evidence["download_calls"][0]["require_private_parent"] is True
    assert evidence["deliveries"] == ["sendDocument"]
    assert receipt["delivery_message_id"] == "4001"
    assert receipt["delivery_file_id"] == "transport-file-1"
    assert terminal["output_file_id"] == "transport-file-1"
    assert evidence["full_file_reads"] == 0


def test_video_edit_worker_streams_source_concat_logo_and_subtitle_with_asset_policies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_bytes = 2 * 1024 * 1024
    evidence: dict = {
        "downloads": [],
        "deliveries": [],
        "full_file_reads": 0,
    }
    observed_plans: list[dict] = []
    validation_calls: list[dict] = []

    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_plan={
            "trim": {"start_ms": 0, "end_ms": 2_000},
            "concat_inputs": ["telegram-concat-placeholder.mp4"],
            "logo_overlay": {
                "position": "top_right",
                "scale": 0.12,
                "opacity": 0.75,
            },
            "subtitle_file": "telegram-subtitle-placeholder.srt",
            "audio_normalization": "loudnorm",
        },
        payload_patch={
            "media_lane": "large_media",
            "source_file_size": source_bytes,
            "concat_sources": [
                {
                    "file_id": "concat-file",
                    "file_name": "concat.mp4",
                    "file_size": 3 * 1024 * 1024,
                }
            ],
            "logo_source": {
                "file_id": "logo-file",
                "file_name": "logo.png",
                "file_size": 256 * 1024,
            },
            "subtitle_source": {
                "file_id": "subtitle-file",
                "file_name": "subtitle.srt",
                "file_size": 32 * 1024,
            },
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
            "bytes": source_bytes,
        },
        observed_plans=observed_plans,
        source_validation_calls=validation_calls,
        transport_evidence=evidence,
    )

    assert terminal["status"] == "succeeded"
    assert evidence["downloads"] == ["local_bot_api"] * 4
    assert [
        (call["file_id"], call["hard_max_bytes"])
        for call in evidence["download_calls"]
    ] == [
        ("source-file", None),
        ("concat-file", None),
        ("logo-file", 10 * 1024 * 1024),
        ("subtitle-file", 5 * 1024 * 1024),
    ]
    assert validation_calls
    assert validation_calls[0]["file_size"] == source_bytes
    assert validation_calls[0]["maximum_bytes"] == 0
    assert validation_calls[0]["maximum_duration_seconds"] == 0
    assert len(observed_plans) == 1
    executed_plan = observed_plans[0]
    assert Path(executed_plan["input_video"]).name == "source.mp4"
    assert [Path(path).name for path in executed_plan["concat_inputs"]] == [
        "concat_001.mp4"
    ]
    assert executed_plan["audio_normalization"] == "loudnorm"
    assert Path(executed_plan["logo_overlay"]["path"]).name == "logo.png"
    assert Path(executed_plan["subtitle_file"]).name == "subtitle.srt"
    assert evidence["full_file_reads"] == 0


def test_public_logo_and_watermark_state_reaches_the_local_worker_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_id = 91_041
    bot.clear_video_editor_pending(user_id)

    class Message:
        def __init__(self, *, text: str = "", document=None, message_id: int) -> None:
            self.text = text
            self.document = document
            self.photo = []
            self.video = None
            self.audio = None
            self.voice = None
            self.animation = None
            self.message_id = message_id
            self.chat_id = user_id
            self.replies: list[tuple[str, dict]] = []

        async def reply_text(self, text: str, **kwargs):
            self.replies.append((text, kwargs))
            return self

    class Query:
        def __init__(self, data: str) -> None:
            self.id = f"public-worker-{data}"
            self.data = data
            self.from_user = SimpleNamespace(id=user_id, first_name="Video Edit")
            self.message = Message(message_id=7_002)
            self.answers: list[tuple[tuple, dict]] = []
            self.edits: list[tuple[str, dict]] = []

        async def answer(self, *args, **kwargs):
            self.answers.append((args, kwargs))

        async def edit_message_text(self, text: str, **kwargs):
            self.edits.append((text, kwargs))
            return self.message

    try:
        manual_plan = video_local_editing.default_manual_edit_plan("")
        manual_plan["trim"] = {"start_ms": 0, "end_ms": 2_000}
        bot.set_video_editor_pending(
            user_id,
            "await_logo",
            edit_mode="manual_edit",
            current_screen="logo_input",
            screen_id="logo_input",
            parent_callback="videoedit|branding",
            entry_parent_callback="videoedit|manual",
            logo_parent_callback="videoedit|branding",
            selected_tool="manual",
            entry_context="manual",
            last_section="manual",
            source_file_id="source-file",
            source_file_name="source.mp4",
            source_file_size=2 * 1024 * 1024,
            source_duration=2,
            source_duration_ms=2_000,
            source_video_hash="a" * 64,
            media_lane="short_media",
            source_metadata={
                "ok": True,
                "duration": 2.0,
                "duration_ms": 2_000,
                "width": 640,
                "height": 360,
                "has_audio": True,
            },
            inspection_complete=True,
            manual_edit_plan=manual_plan,
            concat_sources=[],
            logo_source={},
            watermark_config={},
            subtitle_source={},
            edit_session_id=f"edit-{user_id}",
            session_id=f"edit-{user_id}",
            state_revision=3,
            revision=3,
            status="source_ready",
            pending_field="logo",
        )

        logo_message = Message(
            document=SimpleNamespace(
                file_id="public-logo-file",
                file_name="logo.png",
                mime_type="image/png",
                file_size=256 * 1024,
            ),
            message_id=7_003,
        )
        assert asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    callback_query=None,
                    message=logo_message,
                    effective_user=SimpleNamespace(id=user_id),
                ),
                SimpleNamespace(user_data={}),
            )
        ) is True

        watermark_query = Query("videoedit|watermark_entry")
        assert asyncio.run(
            bot.handle_video_editor_callback(
                SimpleNamespace(callback_query=watermark_query),
                SimpleNamespace(user_data={}),
            )
        ) is not False
        watermark_message = Message(text="© TOAN AAS", message_id=7_004)
        assert asyncio.run(
            bot.handle_video_editor_pending_text(
                SimpleNamespace(
                    callback_query=None,
                    message=watermark_message,
                    effective_user=SimpleNamespace(id=user_id),
                ),
                SimpleNamespace(user_data={}),
            )
        ) is True

        public_state = deepcopy(bot.get_video_editor_pending(user_id) or {})
        assert public_state["logo_source"]["file_id"] == "public-logo-file"
        assert public_state["manual_edit_plan"]["logo_overlay"] == {
            "position": "top_right",
            "scale": 0.12,
            "opacity": 1.0,
        }
        assert public_state["manual_edit_plan"]["watermark_overlay"]["content"] == "© TOAN AAS"
        assert public_state["manual_edit_plan"]["watermark_overlay"]["opacity"] == 0.45

        observed_plans: list[dict] = []
        transport_evidence: dict = {
            "downloads": [],
            "deliveries": [],
            "full_file_reads": 0,
        }
        terminal, captions = _run_job(
            monkeypatch,
            tmp_path,
            mode="manual",
            manual_plan=deepcopy(public_state["manual_edit_plan"]),
            payload_patch={
                "user_id": str(user_id),
                "chat_id": str(user_id),
                "media_lane": "short_media",
                "source_file_size": 2 * 1024 * 1024,
                "logo_source": deepcopy(public_state["logo_source"]),
                "rights_confirmation": {
                    "confirmed": True,
                    "policy": "video_edit_rights_v1",
                    "user_id": str(user_id),
                    "review_revision": 3,
                    "confirmed_at_unix": 1_750_000_000,
                },
            },
            observed_plans=observed_plans,
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
                "bytes": 2 * 1024 * 1024,
            },
            transport_evidence=transport_evidence,
            job_user_id=str(user_id),
        )

        assert terminal["status"] == "succeeded"
        assert len(observed_plans) == 1
        worker_plan = observed_plans[0]
        assert Path(worker_plan["logo_overlay"]["path"]).name == "logo.png"
        assert worker_plan["logo_overlay"]["position"] == "top_right"
        assert worker_plan["watermark_overlay"]["content"] == "© TOAN AAS"
        assert worker_plan["watermark_overlay"]["opacity"] == 0.45
        assert transport_evidence["downloads"] == ["local_bot_api", "local_bot_api"]
        assert transport_evidence["full_file_reads"] == 0
        detail = json.loads(terminal["detail"])
        receipt = json.loads(terminal["output_url"])
        assert detail["price_xu"] == 0
        assert detail["charged_xu"] == 0
        assert receipt["charge_policy"] == "free_local_tool"
        assert receipt["charge_status"] == "not_required_free"
        assert receipt["charged_xu"] == 0
        assert captions and all("0 Xu" in caption for caption in captions)
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("persisted_lane", "actual_duration_seconds", "actual_bytes"),
    [
        pytest.param("short_media", 61.0, 1 * 1024 * 1024, id="duration-promotion"),
        pytest.param(
            "short_media",
            30.0,
            20 * 1024 * 1024 + 1,
            id="size-promotion",
        ),
        pytest.param(
            "large_media",
            30.0,
            1 * 1024 * 1024,
            id="persisted-large-no-demotion",
        ),
    ],
)
def test_video_edit_worker_promotes_actual_probe_to_large_lane_and_disables_public_rejection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    persisted_lane: str,
    actual_duration_seconds: float,
    actual_bytes: int,
) -> None:
    evidence: dict = {
        "downloads": [],
        "deliveries": [],
        "full_file_reads": 0,
    }
    validation_calls: list[dict] = []

    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={
            "media_lane": persisted_lane,
            "source_file_size": actual_bytes,
            "source_metadata": {
                "ok": True,
                "duration": 30.0,
                "duration_ms": 30_000,
                "width": 640,
                "height": 360,
                "has_audio": True,
            },
        },
        downloaded_probe={
            "ok": True,
            "reason": "",
            "duration": actual_duration_seconds,
            "duration_ms": int(actual_duration_seconds * 1_000),
            "width": 640,
            "height": 360,
            "fps": 25.0,
            "has_video": True,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
            "bytes": actual_bytes,
        },
        source_validation_calls=validation_calls,
        transport_evidence=evidence,
    )

    assert terminal["status"] == "succeeded"
    detail = json.loads(terminal["detail"])
    assert detail["media_lane"] == "large_media"
    assert len(validation_calls) == 1
    assert validation_calls[0]["file_size"] == actual_bytes
    assert validation_calls[0]["maximum_bytes"] == 0
    assert validation_calls[0]["maximum_duration_seconds"] == 0
    assert evidence["download_calls"][0]["hard_max_bytes"] is None
    assert evidence["full_file_reads"] == 0


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


def test_split_worker_uses_terminal_artifact_as_top_level_telegram_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, _captions = _run_job(monkeypatch, tmp_path, mode="split")
    receipt = json.loads(terminal["output_url"])

    assert terminal["status"] == "succeeded"
    assert receipt["delivery_message_id"] == "1002"
    assert receipt["delivery_file_id"] == "file-2"
    assert terminal["output_file_id"] == "file-2"
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


def test_paid_worker_never_silently_drops_unbound_legacy_audio_tracks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        price_xu=125,
        manual_plan={
            "trim": {"start_ms": 0, "end_ms": 2_000},
            "audio_tracks": [
                {
                    "path": "legacy-worker-audio.mp3",
                    "kind": "voice",
                    "volume": 1.0,
                    "start_ms": 0,
                    "end_ms": 1_000,
                }
            ],
        },
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["reason"] == "video_local_edit_asset_contract_invalid"
    assert captions == []


@pytest.mark.parametrize("track_volume", [0.0, 0.35])
def test_worker_materializes_audio_only_telegram_asset_into_executed_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    track_volume: float,
) -> None:
    observed_plans: list[dict] = []
    transport_evidence: dict = {}
    terminal, captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        manual_plan={
            "trim": {"start_ms": 0, "end_ms": 2_000},
            "audio_tracks": [
                {
                    "path": "",
                    "kind": "music",
                    "volume": track_volume,
                    "start_ms": 0,
                    "end_ms": 0,
                }
            ],
        },
        payload_patch={
            "audio_sources": [
                {
                    "file_id": "telegram-music-only",
                    "file_name": "music.m4a",
                    "file_size": 1_024,
                    "kind": "music",
                    "volume": track_volume,
                    "start_ms": 0,
                    "end_ms": 0,
                }
            ],
        },
        observed_plans=observed_plans,
        transport_evidence=transport_evidence,
    )

    assert terminal["status"] == "succeeded"
    assert captions
    audio_downloads = [
        call
        for call in transport_evidence["download_calls"]
        if call["file_id"] == "telegram-music-only"
    ]
    assert len(audio_downloads) == 1
    materialized_audio = Path(audio_downloads[0]["destination"])
    assert materialized_audio.is_file()
    assert materialized_audio.stat().st_size > 0
    assert len(observed_plans) == 1
    executed_tracks = observed_plans[0]["audio_tracks"]
    assert executed_tracks == [
        {
            "path": str(materialized_audio),
            "kind": "music",
            "volume": track_volume,
            "start_ms": 0,
            "end_ms": 0,
        }
    ]


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


def test_worker_rechecks_downloaded_source_duration_without_public_rejection(
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
    assert terminal["status"] == "succeeded"
    assert detail["media_lane"] == "large_media"
    assert captions
    assert observed_steps == ["download", "probe", "validate", "execute", "delivery"]
    assert len(validation_calls) == 1
    assert validation_calls[0]["file_size"] == len(b"source-video")
    assert validation_calls[0]["metadata"]["duration_ms"] == over_limit * 1_000
    assert validation_calls[0]["maximum_bytes"] == 0
    assert validation_calls[0]["maximum_duration_seconds"] == 0


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
