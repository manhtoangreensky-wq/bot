"""Durable, submit-free recovery for Product Video one-scene jobs.

Callers provide transport boundaries. This module can only inspect the status
of an already persisted provider task, materialize its existing output, and
continue idempotent finalization. All public and recovery flags default OFF.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from services import product_video_one_scene_engine as one_scene
from services import video_engine_contract


RECOVERY_SCHEMA_VERSION = 1
DEFAULT_POLL_INTERVAL_SECONDS = 30.0
DEFAULT_LEASE_SECONDS = 60.0

POLL_RECOVERY_FLAG_DEFAULTS = {
    "PRODUCT_VIDEO_POLL_RECOVERY_ENABLED": False,
    "PRODUCT_VIDEO_POLL_RECOVERY_PUBLIC_ALLOWED": False,
    "PRODUCT_VIDEO_POLL_RECOVERY_AUTO_RESUBMIT": False,
    "PRODUCT_VIDEO_POLL_RECOVERY_AUTO_FALLBACK": False,
}

_COUNTER_DEFAULTS = {
    "provider_status_get_calls": 0,
    "fixture_provider_calls": 0,
    "real_provider_calls": 0,
    "artifact_fetch_calls": 0,
    "delivery_calls": 0,
    "receipt_calls": 0,
    "charge_calls": 0,
    "terminal_report_calls": 0,
    "wallet_mutations": 0,
    "production_telegram_deliveries": 0,
}


class ProviderTaskUnknown(RuntimeError):
    """A status GET proved that the persisted provider task does not exist."""


class RecoveryCheckpointError(RuntimeError):
    """A durable checkpoint cannot be trusted."""


class RecoveryCheckpointNotFound(RecoveryCheckpointError):
    """No durable checkpoint exists for the requested job."""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes", "on"}


def _enum_value(value: Any) -> str:
    return _clean(value.value if isinstance(value, Enum) else value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _clean(value)


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    return parsed if parsed > 0 else float(default)


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _json_safe(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return _sha256_text(encoded)


def _iso_timestamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def product_video_poll_recovery_flags(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {
        name: _flag(source.get(name, default))
        for name, default in POLL_RECOVERY_FLAG_DEFAULTS.items()
    }


def product_video_poll_recovery_contract(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    flags = product_video_poll_recovery_flags(environ)
    return {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "product_family": one_scene.PRODUCT_FAMILY,
        "mode": one_scene.MODE,
        "enabled": flags["PRODUCT_VIDEO_POLL_RECOVERY_ENABLED"],
        "public_allowed": flags["PRODUCT_VIDEO_POLL_RECOVERY_PUBLIC_ALLOWED"],
        "poll_method": "GET",
        "same_provider_task_only": True,
        "replacement_submit_allowed": False,
        "automatic_fallback_allowed": False,
        "delivery_acceptance_unknown_policy": "manual_review_no_resend",
        "flags": flags,
    }


class ProductVideoPollRecoveryStore:
    """Atomic JSON checkpoints and exclusive per-job recovery leases."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.checkpoints_dir = self.root / "checkpoints"
        self.leases_dir = self.root / "leases"
        self.artifacts_dir = self.root / "artifacts"
        for directory in (self.checkpoints_dir, self.leases_dir, self.artifacts_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _job_key(job_id: str) -> str:
        clean_job_id = _clean(job_id)
        if not clean_job_id:
            raise RecoveryCheckpointError("recovery_job_id_required")
        return _sha256_text(clean_job_id)

    def checkpoint_path(self, job_id: str) -> Path:
        return self.checkpoints_dir / f"{self._job_key(job_id)}.json"

    def lease_path(self, job_id: str) -> Path:
        return self.leases_dir / f"{self._job_key(job_id)}.lease.json"

    def artifact_path(self, job_id: str) -> Path:
        return self.artifacts_dir / f"{self._job_key(job_id)}.mp4"

    def save(self, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
        payload = _json_safe(checkpoint)
        if not isinstance(payload, dict):
            raise RecoveryCheckpointError("recovery_checkpoint_invalid")
        job_id = _clean(payload.get("job_id"))
        if not job_id:
            raise RecoveryCheckpointError("recovery_job_id_required")
        path = self.checkpoint_path(job_id)
        temporary = path.with_name(
            f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
        )
        try:
            with open(temporary, "x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
        return json.loads(json.dumps(payload))

    def load(self, job_id: str) -> dict[str, Any]:
        path = self.checkpoint_path(job_id)
        if not path.is_file():
            raise RecoveryCheckpointNotFound("recovery_checkpoint_not_found")
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError) as exc:
            raise RecoveryCheckpointError("recovery_checkpoint_invalid") from exc
        if not isinstance(loaded, dict) or _clean(loaded.get("job_id")) != _clean(job_id):
            raise RecoveryCheckpointError("recovery_checkpoint_invalid")
        return loaded

    def acquire_lease(
        self,
        *,
        job_id: str,
        owner: str,
        now_epoch: float,
        lease_seconds: float,
    ) -> dict[str, Any]:
        clean_owner = _clean(owner)
        if not clean_owner:
            return {"acquired": False, "blocker": "recovery_lease_owner_required"}
        path = self.lease_path(job_id)
        stale_recovered = False
        for _attempt in range(3):
            token = uuid.uuid4().hex
            payload = {
                "job_id": _clean(job_id),
                "owner": clean_owner,
                "token": token,
                "acquired_at_epoch": float(now_epoch),
                "expires_at_epoch": float(now_epoch) + float(lease_seconds),
            }
            encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
            try:
                descriptor = os.open(
                    path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, TypeError, ValueError):
                    try:
                        expires = path.stat().st_mtime + float(lease_seconds)
                    except OSError:
                        expires = float(now_epoch) + float(lease_seconds)
                    existing = {"expires_at_epoch": expires}
                try:
                    expires_at = float(existing.get("expires_at_epoch") or 0)
                except (TypeError, ValueError):
                    expires_at = float(now_epoch) + float(lease_seconds)
                if expires_at > float(now_epoch):
                    return {
                        "acquired": False,
                        "blocker": "recovery_lease_active",
                        "stale_recovered": stale_recovered,
                    }
                try:
                    path.unlink()
                    stale_recovered = True
                except FileNotFoundError:
                    pass
                except OSError:
                    return {
                        "acquired": False,
                        "blocker": "recovery_lease_active",
                        "stale_recovered": stale_recovered,
                    }
                continue
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return {
                "acquired": True,
                "token": token,
                "stale_recovered": stale_recovered,
            }
        return {
            "acquired": False,
            "blocker": "recovery_lease_active",
            "stale_recovered": stale_recovered,
        }

    def release_lease(self, *, job_id: str, token: str) -> None:
        path = self.lease_path(job_id)
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, TypeError, ValueError):
            return
        if _clean(current.get("token")) == _clean(token):
            path.unlink(missing_ok=True)


def _normalized_stage(
    value: Any,
    *,
    success_field: str,
    success_state: str,
) -> dict[str, Any]:
    stage = dict(value) if isinstance(value, Mapping) else {}
    if stage.get(success_field):
        stage["state"] = success_state
    elif _clean(stage.get("state")).upper() == "INTENT_PERSISTED":
        stage["state"] = "ACCEPTANCE_UNKNOWN"
    return _json_safe(stage)


def _new_counters(value: Any = None) -> dict[str, int]:
    source = dict(value) if isinstance(value, Mapping) else {}
    return {
        name: _nonnegative_int(source.get(name, default))
        for name, default in _COUNTER_DEFAULTS.items()
    }


def persist_product_video_poll_checkpoint(
    *,
    store: ProductVideoPollRecoveryStore,
    record: Mapping[str, Any],
    expected_duration_seconds: int | float,
    motion_promised: bool,
    audio_promised: bool,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Persist the identity and completed stages of an existing 29C job."""

    now = time.time() if now_epoch is None else float(now_epoch)
    job_id = _clean(record.get("job_id"))
    request = record.get("request")
    if not job_id or request is None:
        raise RecoveryCheckpointError("one_scene_job_not_found")
    request_payload = dict(getattr(request, "payload", {}) or {})
    checkpoint = {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "job_id": job_id,
        "request_id": _clean(getattr(request, "request_id", "")),
        "idempotency_key": _clean(getattr(request, "idempotency_key", "")),
        "product_family": _enum_value(getattr(request, "product_type", "")),
        "mode": one_scene.MODE,
        "engine_mode": _enum_value(getattr(request, "mode", "")),
        "scene_count": _nonnegative_int(request_payload.get("scene_count")),
        "provider": _clean(record.get("provider") or getattr(request, "provider_selection", "")),
        "provider_task_id": _clean(record.get("provider_task_id")),
        "provider_state": _clean(
            record.get("provider_state") or one_scene.ProviderState.NOT_SUBMITTED.value
        ).upper(),
        "expected_worker_sha": _clean(getattr(request, "expected_worker_sha", "")),
        "expected_duration_seconds": float(expected_duration_seconds),
        "motion_promised": bool(motion_promised),
        "audio_promised": bool(audio_promised),
        "admin_no_charge": bool(request_payload.get("admin_no_charge")),
        "charge_plan": dict(request_payload.get("charge_plan") or {}),
        "artifact_path": _clean(record.get("artifact_path")),
        "artifact_url": _clean(record.get("artifact_url") or record.get("output_url")),
        "validation": dict(record.get("validation") or {}),
        "delivery": _normalized_stage(
            record.get("delivery"), success_field="accepted", success_state="ACCEPTED"
        ),
        "receipt": _normalized_stage(
            record.get("receipt"), success_field="persisted", success_state="PERSISTED"
        ),
        "charge": _normalized_stage(
            record.get("charge"), success_field="recorded", success_state="RECORDED"
        ),
        "terminal_report": _normalized_stage(
            record.get("terminal_report"), success_field="emitted", success_state="EMITTED"
        ),
        "terminal_state": _clean(record.get("terminal_state")),
        "blocker": _clean(record.get("blocker")),
        "stage_fingerprints": dict(record.get("stage_fingerprints") or {}),
        "counters": _new_counters(record.get("recovery_counters")),
        "poll_count": 0,
        "last_poll_epoch": 0.0,
        "next_poll_epoch": now,
        "updated_at_epoch": now,
    }
    try:
        existing = store.load(job_id)
    except RecoveryCheckpointNotFound:
        existing = None
    if existing is not None:
        immutable_fields = (
            "job_id",
            "request_id",
            "idempotency_key",
            "product_family",
            "mode",
            "scene_count",
            "provider",
        )
        if any(existing.get(name) != checkpoint.get(name) for name in immutable_fields):
            raise RecoveryCheckpointError("recovery_checkpoint_identity_mismatch")
        old_task = _clean(existing.get("provider_task_id"))
        new_task = _clean(checkpoint.get("provider_task_id"))
        if old_task and new_task and old_task != new_task:
            raise RecoveryCheckpointError("provider_task_identity_mismatch")
        return existing
    return store.save(checkpoint)


def _result(
    checkpoint: Mapping[str, Any] | None,
    *,
    ok: bool,
    blocker: str = "",
    outcome: str = "blocked",
    idempotent_replay: bool = False,
    stale_lease_recovered: bool = False,
) -> dict[str, Any]:
    current = dict(checkpoint or {})
    counters = _new_counters(current.get("counters"))
    return {
        "ok": bool(ok),
        "blocker": _clean(blocker),
        "outcome": _clean(outcome),
        "job_id": _clean(current.get("job_id")),
        "provider": _clean(current.get("provider")),
        "provider_task_id": _clean(current.get("provider_task_id")),
        "provider_state": _clean(current.get("provider_state")),
        "terminal_state": _clean(current.get("terminal_state")),
        "idempotent_replay": bool(idempotent_replay),
        "stale_lease_recovered": bool(stale_lease_recovered),
        "provider_submit_calls": 0,
        "paid_provider_calls": 0,
        **counters,
    }


def _semantic_blocker(checkpoint: Mapping[str, Any]) -> str:
    if _nonnegative_int(checkpoint.get("schema_version")) != RECOVERY_SCHEMA_VERSION:
        return "recovery_schema_version_unsupported"
    if _clean(checkpoint.get("product_family")) != one_scene.PRODUCT_FAMILY:
        return "recovery_product_mismatch"
    if _clean(checkpoint.get("mode")) != one_scene.MODE:
        return "recovery_mode_mismatch"
    if _nonnegative_int(checkpoint.get("scene_count")) != 1:
        return "one_scene_required"
    return ""


def _save(
    store: ProductVideoPollRecoveryStore,
    checkpoint: dict[str, Any],
    *,
    now_epoch: float,
) -> dict[str, Any]:
    checkpoint["updated_at_epoch"] = float(now_epoch)
    return store.save(checkpoint)


def _block_unknown_stage(stage: Mapping[str, Any], name: str) -> str:
    state = _clean(stage.get("state")).upper()
    if state in {"INTENT_PERSISTED", "ACCEPTANCE_UNKNOWN"}:
        return f"{name}_acceptance_unknown"
    if state in {"REJECTED", "FAILED", "INVALID"}:
        return f"{name}_not_completed"
    return ""


def _copy_to_durable_artifact(
    store: ProductVideoPollRecoveryStore,
    *,
    job_id: str,
    source_path: str,
) -> str:
    source = Path(source_path)
    if not source.is_file():
        return ""
    destination = store.artifact_path(job_id)
    if source.resolve() != destination.resolve():
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}.{time.time_ns()}.tmp"
        )
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return str(destination)


def recover_product_video_one_scene(
    *,
    store: ProductVideoPollRecoveryStore,
    job_id: str,
    lease_owner: str,
    actual_worker_sha: str,
    expected_provider_task_id: str,
    status_getter: Callable[[dict[str, Any]], Mapping[str, Any]],
    artifact_fetcher: Callable[[dict[str, Any]], Mapping[str, Any]],
    artifact_validator: Callable[..., Mapping[str, Any]],
    deliverer: Callable[[dict[str, Any]], Mapping[str, Any]],
    receipt_persister: Callable[[dict[str, Any]], Mapping[str, Any]],
    charger: Callable[[dict[str, Any]], Mapping[str, Any]],
    terminal_reporter: Callable[[dict[str, Any]], Mapping[str, Any]],
    environ: Mapping[str, Any] | None = None,
    public_request: bool = False,
    now_epoch: float | None = None,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any]:
    """Resume one durable job without creating a provider task or replacement job."""

    now = time.time() if now_epoch is None else float(now_epoch)
    flags = product_video_poll_recovery_flags(environ)
    if not flags["PRODUCT_VIDEO_POLL_RECOVERY_ENABLED"]:
        return _result(
            None,
            ok=False,
            blocker="product_video_poll_recovery_disabled",
        )
    if public_request and not flags["PRODUCT_VIDEO_POLL_RECOVERY_PUBLIC_ALLOWED"]:
        return _result(
            None,
            ok=False,
            blocker="product_video_poll_recovery_public_disabled",
        )
    try:
        checkpoint = store.load(job_id)
    except RecoveryCheckpointNotFound:
        return _result(None, ok=False, blocker="recovery_checkpoint_not_found")
    except RecoveryCheckpointError:
        return _result(None, ok=False, blocker="recovery_checkpoint_invalid")

    semantic_blocker = _semantic_blocker(checkpoint)
    if semantic_blocker:
        return _result(checkpoint, ok=False, blocker=semantic_blocker)
    if _clean(checkpoint.get("expected_worker_sha")) != _clean(actual_worker_sha):
        return _result(checkpoint, ok=False, blocker="worker_sha_mismatch")
    if checkpoint.get("terminal_report", {}).get("emitted"):
        return _result(
            checkpoint,
            ok=True,
            outcome="final_delivered",
            idempotent_replay=True,
        )

    try:
        provider_state = one_scene.ProviderState(
            _clean(checkpoint.get("provider_state")).upper()
        )
    except ValueError:
        return _result(checkpoint, ok=False, blocker="provider_state_unknown")
    if provider_state in {
        one_scene.ProviderState.NOT_SUBMITTED,
        one_scene.ProviderState.SUBMITTING,
    }:
        return _result(checkpoint, ok=False, blocker="provider_task_not_accepted")
    if provider_state is one_scene.ProviderState.ACCEPTANCE_UNKNOWN:
        return _result(
            checkpoint,
            ok=False,
            blocker="provider_acceptance_unknown_manual_review",
        )
    if provider_state is one_scene.ProviderState.FAILED:
        return _result(
            checkpoint,
            ok=False,
            blocker=_clean(checkpoint.get("blocker")) or "provider_failed",
            outcome="failed_no_charge",
        )

    provider_task_id = _clean(checkpoint.get("provider_task_id"))
    if not provider_task_id:
        return _result(checkpoint, ok=False, blocker="provider_task_id_missing")
    if (
        _clean(expected_provider_task_id)
        and _clean(expected_provider_task_id) != provider_task_id
    ):
        return _result(checkpoint, ok=False, blocker="stale_recovery_identity")
    if (
        provider_state in {one_scene.ProviderState.ACCEPTED, one_scene.ProviderState.RUNNING}
        and now < float(checkpoint.get("next_poll_epoch") or 0)
    ):
        return _result(checkpoint, ok=False, blocker="provider_poll_not_due")

    lease = store.acquire_lease(
        job_id=job_id,
        owner=lease_owner,
        now_epoch=now,
        lease_seconds=_positive_float(lease_seconds, DEFAULT_LEASE_SECONDS),
    )
    if not lease.get("acquired"):
        return _result(
            checkpoint,
            ok=False,
            blocker=_clean(lease.get("blocker")) or "recovery_lease_active",
            stale_lease_recovered=bool(lease.get("stale_recovered")),
        )
    token = _clean(lease.get("token"))
    stale_recovered = bool(lease.get("stale_recovered"))
    try:
        checkpoint = store.load(job_id)
        semantic_blocker = _semantic_blocker(checkpoint)
        if semantic_blocker:
            return _result(
                checkpoint,
                ok=False,
                blocker=semantic_blocker,
                stale_lease_recovered=stale_recovered,
            )
        if _clean(checkpoint.get("expected_worker_sha")) != _clean(actual_worker_sha):
            return _result(
                checkpoint,
                ok=False,
                blocker="worker_sha_mismatch",
                stale_lease_recovered=stale_recovered,
            )
        reloaded_task_id = _clean(checkpoint.get("provider_task_id"))
        if reloaded_task_id != provider_task_id or (
            _clean(expected_provider_task_id)
            and _clean(expected_provider_task_id) != reloaded_task_id
        ):
            return _result(
                checkpoint,
                ok=False,
                blocker="stale_recovery_identity",
                stale_lease_recovered=stale_recovered,
            )
        if checkpoint.get("terminal_report", {}).get("emitted"):
            return _result(
                checkpoint,
                ok=True,
                outcome="final_delivered",
                idempotent_replay=True,
                stale_lease_recovered=stale_recovered,
            )
        provider_state = one_scene.ProviderState(
            _clean(checkpoint.get("provider_state")).upper()
        )

        if provider_state in {
            one_scene.ProviderState.ACCEPTED,
            one_scene.ProviderState.RUNNING,
        }:
            counters = _new_counters(checkpoint.get("counters"))
            counters["provider_status_get_calls"] += 1
            if _clean(checkpoint.get("provider")) == "fake_provider":
                counters["fixture_provider_calls"] += 1
            else:
                counters["real_provider_calls"] += 1
            checkpoint["counters"] = counters
            checkpoint["poll_count"] = _nonnegative_int(checkpoint.get("poll_count")) + 1
            checkpoint["last_poll_epoch"] = now
            checkpoint["next_poll_epoch"] = now + _positive_float(
                poll_interval_seconds, DEFAULT_POLL_INTERVAL_SECONDS
            )
            checkpoint = _save(store, checkpoint, now_epoch=now)
            try:
                response = dict(
                    status_getter(
                        {
                            "method": "GET",
                            "provider": _clean(checkpoint.get("provider")),
                            "provider_task_id": provider_task_id,
                            "job_id": _clean(job_id),
                        }
                    )
                    or {}
                )
            except ProviderTaskUnknown:
                checkpoint["provider_state"] = one_scene.ProviderState.FAILED.value
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = "provider_task_unknown"
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_task_unknown",
                    outcome="failed_no_charge",
                    stale_lease_recovered=stale_recovered,
                )
            except Exception as exc:
                checkpoint["blocker"] = "provider_status_unavailable"
                checkpoint["safe_error"] = type(exc).__name__
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_status_unavailable",
                    outcome="waiting_provider",
                    stale_lease_recovered=stale_recovered,
                )
            response_task_id = _clean(response.get("provider_task_id"))
            response_provider = _clean(response.get("provider"))
            if response_task_id != provider_task_id:
                checkpoint["blocker"] = "provider_task_identity_mismatch"
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_task_identity_mismatch",
                    stale_lease_recovered=stale_recovered,
                )
            if response_provider != _clean(checkpoint.get("provider")):
                checkpoint["blocker"] = "provider_identity_mismatch"
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_identity_mismatch",
                    stale_lease_recovered=stale_recovered,
                )
            try:
                next_state = one_scene.ProviderState(
                    _clean(response.get("state") or response.get("status")).upper()
                )
            except ValueError:
                checkpoint["blocker"] = "provider_status_unknown"
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_status_unknown",
                    outcome="waiting_provider",
                    stale_lease_recovered=stale_recovered,
                )
            if next_state not in {
                one_scene.ProviderState.ACCEPTED,
                one_scene.ProviderState.RUNNING,
                one_scene.ProviderState.COMPLETED,
                one_scene.ProviderState.FAILED,
            }:
                checkpoint["blocker"] = "provider_status_unknown"
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_status_unknown",
                    outcome="waiting_provider",
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["provider_state"] = next_state.value
            checkpoint["blocker"] = ""
            if next_state is one_scene.ProviderState.COMPLETED:
                checkpoint["artifact_path"] = _clean(
                    response.get("artifact_path") or checkpoint.get("artifact_path")
                )
                checkpoint["artifact_url"] = _clean(
                    response.get("artifact_url")
                    or response.get("output_url")
                    or checkpoint.get("artifact_url")
                )
                checkpoint.setdefault("stage_fingerprints", {})[
                    "provider_completed"
                ] = _fingerprint(
                    {
                        "provider": response_provider,
                        "provider_task_id": response_task_id,
                        "state": next_state.value,
                    }
                )
            elif next_state is one_scene.ProviderState.FAILED:
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = "provider_failed"
            checkpoint = _save(store, checkpoint, now_epoch=now)
            if next_state in {
                one_scene.ProviderState.ACCEPTED,
                one_scene.ProviderState.RUNNING,
            }:
                return _result(
                    checkpoint,
                    ok=False,
                    outcome="waiting_provider",
                    stale_lease_recovered=stale_recovered,
                )
            if next_state is one_scene.ProviderState.FAILED:
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_failed",
                    outcome="failed_no_charge",
                    stale_lease_recovered=stale_recovered,
                )

        artifact_path = _clean(checkpoint.get("artifact_path"))
        if not Path(artifact_path).is_file():
            artifact_url = _clean(checkpoint.get("artifact_url"))
            if not artifact_url:
                checkpoint["blocker"] = "provider_output_missing"
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_output_missing",
                    stale_lease_recovered=stale_recovered,
                )
            if not callable(artifact_fetcher):
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_output_materializer_missing",
                    stale_lease_recovered=stale_recovered,
                )
            counters = _new_counters(checkpoint.get("counters"))
            counters["artifact_fetch_calls"] += 1
            checkpoint["counters"] = counters
            checkpoint = _save(store, checkpoint, now_epoch=now)
            destination = store.artifact_path(job_id)
            try:
                fetched = dict(
                    artifact_fetcher(
                        {
                            "method": "GET",
                            "provider": _clean(checkpoint.get("provider")),
                            "provider_task_id": provider_task_id,
                            "artifact_url": artifact_url,
                            "destination_path": str(destination),
                            "job_id": _clean(job_id),
                        }
                    )
                    or {}
                )
            except Exception as exc:
                checkpoint["blocker"] = "provider_output_fetch_failed"
                checkpoint["safe_error"] = type(exc).__name__
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_output_fetch_failed",
                    stale_lease_recovered=stale_recovered,
                )
            artifact_path = _clean(fetched.get("artifact_path") or destination)
            if not fetched.get("ok") or not Path(artifact_path).is_file():
                checkpoint["blocker"] = "provider_output_fetch_failed"
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="provider_output_fetch_failed",
                    stale_lease_recovered=stale_recovered,
                )
        try:
            durable_artifact = _copy_to_durable_artifact(
                store,
                job_id=job_id,
                source_path=artifact_path,
            )
        except OSError:
            durable_artifact = ""
        if not durable_artifact:
            checkpoint["blocker"] = "provider_output_missing"
            checkpoint = _save(store, checkpoint, now_epoch=now)
            return _result(
                checkpoint,
                ok=False,
                blocker="provider_output_missing",
                stale_lease_recovered=stale_recovered,
            )
        checkpoint["artifact_path"] = durable_artifact
        artifact_digest = _sha256_file(durable_artifact)
        validation = dict(checkpoint.get("validation") or {})
        validated_fingerprint = _clean(
            checkpoint.get("stage_fingerprints", {}).get("artifact_validated")
        )
        if validation.get("ok") and validated_fingerprint:
            if validated_fingerprint != artifact_digest:
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = "artifact_fingerprint_mismatch"
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="artifact_fingerprint_mismatch",
                    outcome="failed_no_charge",
                    stale_lease_recovered=stale_recovered,
                )
        else:
            try:
                validation = dict(
                    artifact_validator(
                        durable_artifact,
                        expected_duration_seconds=float(
                            checkpoint.get("expected_duration_seconds") or 0
                        ),
                        motion_promised=bool(checkpoint.get("motion_promised")),
                        audio_promised=bool(checkpoint.get("audio_promised")),
                        result={
                            "renderer": "fake_provider_fixture"
                            if _clean(checkpoint.get("provider")) == "fake_provider"
                            else "provider_scene_video",
                            "visual_classification": "final_ai_video",
                            "scene_count": 1,
                        },
                    )
                    or {}
                )
            except Exception as exc:
                checkpoint["validation"] = {
                    "ok": False,
                    "reason": "artifact_validation_failed",
                    "safe_error": type(exc).__name__,
                }
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = "artifact_validation_failed"
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="artifact_validation_failed",
                    outcome="failed_no_charge",
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["validation"] = _json_safe(validation)
            if not validation.get("ok"):
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = _clean(
                    validation.get("reason") or "final_output_invalid"
                )
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker=checkpoint["blocker"],
                    outcome="failed_no_charge",
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint.setdefault("stage_fingerprints", {})[
                "artifact_validated"
            ] = artifact_digest
            checkpoint = _save(store, checkpoint, now_epoch=now)

        delivery_key = f"delivery:{job_id}:{artifact_digest}"
        delivery = dict(checkpoint.get("delivery") or {})
        if delivery.get("accepted"):
            if not _clean(delivery.get("message_id")):
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="delivery_record_invalid",
                    stale_lease_recovered=stale_recovered,
                )
        else:
            stage_blocker = _block_unknown_stage(delivery, "delivery")
            if stage_blocker:
                return _result(
                    checkpoint,
                    ok=False,
                    blocker=stage_blocker,
                    stale_lease_recovered=stale_recovered,
                )
            counters = _new_counters(checkpoint.get("counters"))
            counters["delivery_calls"] += 1
            checkpoint["counters"] = counters
            checkpoint["delivery"] = {
                "state": "INTENT_PERSISTED",
                "accepted": False,
                "idempotency_key": delivery_key,
            }
            checkpoint = _save(store, checkpoint, now_epoch=now)
            try:
                delivered = dict(
                    deliverer(
                        {
                            "job_id": job_id,
                            "artifact_path": durable_artifact,
                            "artifact_sha256": artifact_digest,
                            "idempotency_key": delivery_key,
                            "production": False,
                        }
                    )
                    or {}
                )
            except Exception as exc:
                checkpoint["delivery"] = {
                    **dict(checkpoint.get("delivery") or {}),
                    "state": "ACCEPTANCE_UNKNOWN",
                    "safe_error": type(exc).__name__,
                }
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="delivery_acceptance_unknown",
                    stale_lease_recovered=stale_recovered,
                )
            if not delivered.get("accepted") or not _clean(delivered.get("message_id")):
                checkpoint["delivery"] = {
                    **delivered,
                    "state": "REJECTED",
                    "accepted": False,
                    "idempotency_key": delivery_key,
                }
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="delivery_not_accepted",
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["delivery"] = {
                **delivered,
                "state": "ACCEPTED",
                "accepted": True,
                "idempotency_key": delivery_key,
            }
            if delivered.get("production"):
                counters = _new_counters(checkpoint.get("counters"))
                counters["production_telegram_deliveries"] += 1
                checkpoint["counters"] = counters
            checkpoint.setdefault("stage_fingerprints", {})[
                "delivery_accepted"
            ] = _fingerprint(checkpoint["delivery"])
            checkpoint = _save(store, checkpoint, now_epoch=now)

        delivered_at = _iso_timestamp(now)
        receipt_seed = {
            "job_id": job_id,
            "delivered": True,
            "delivery_idempotency_key": delivery_key,
            "delivery_message_id": _clean(checkpoint["delivery"].get("message_id")),
            "output_sha256": artifact_digest,
            "output_bytes": Path(durable_artifact).stat().st_size,
            "delivered_at": delivered_at,
        }
        receipt = dict(checkpoint.get("receipt") or {})
        if not receipt.get("persisted"):
            stage_blocker = _block_unknown_stage(receipt, "receipt")
            if stage_blocker:
                return _result(
                    checkpoint,
                    ok=False,
                    blocker=stage_blocker,
                    stale_lease_recovered=stale_recovered,
                )
            counters = _new_counters(checkpoint.get("counters"))
            counters["receipt_calls"] += 1
            checkpoint["counters"] = counters
            checkpoint["receipt"] = {
                "state": "INTENT_PERSISTED",
                "persisted": False,
                "idempotency_key": delivery_key,
            }
            checkpoint = _save(store, checkpoint, now_epoch=now)
            try:
                persisted = dict(receipt_persister(receipt_seed) or {})
            except Exception as exc:
                checkpoint["receipt"] = {
                    **dict(checkpoint.get("receipt") or {}),
                    "state": "ACCEPTANCE_UNKNOWN",
                    "safe_error": type(exc).__name__,
                }
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="receipt_acceptance_unknown",
                    stale_lease_recovered=stale_recovered,
                )
            receipt_contract = video_engine_contract.VideoDeliveryReceipt(
                **receipt_seed,
                receipt_id=_clean(persisted.get("receipt_id")),
            )
            if not persisted.get("persisted") or not receipt_contract.valid:
                checkpoint["receipt"] = {
                    **receipt_seed,
                    **persisted,
                    "state": "INVALID",
                    "persisted": False,
                }
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="delivery_receipt_not_persisted",
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["receipt"] = {
                **_json_safe(receipt_contract),
                **persisted,
                "state": "PERSISTED",
                "persisted": True,
            }
            checkpoint.setdefault("stage_fingerprints", {})[
                "receipt_persisted"
            ] = _fingerprint(checkpoint["receipt"])
            checkpoint = _save(store, checkpoint, now_epoch=now)
        elif not _clean(receipt.get("receipt_id")):
            return _result(
                checkpoint,
                ok=False,
                blocker="delivery_receipt_invalid",
                stale_lease_recovered=stale_recovered,
            )

        charge = dict(checkpoint.get("charge") or {})
        if not charge.get("recorded"):
            stage_blocker = _block_unknown_stage(charge, "charge")
            if stage_blocker:
                return _result(
                    checkpoint,
                    ok=False,
                    blocker=stage_blocker,
                    stale_lease_recovered=stale_recovered,
                )
            admin_no_charge = bool(checkpoint.get("admin_no_charge"))
            charge_plan = dict(checkpoint.get("charge_plan") or {})
            amount = 0 if admin_no_charge else _nonnegative_int(charge_plan.get("amount_xu"))
            if not admin_no_charge and amount <= 0:
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="charge_plan_missing",
                    stale_lease_recovered=stale_recovered,
                )
            charge_key = f"charge:{job_id}:{amount}"
            counters = _new_counters(checkpoint.get("counters"))
            counters["charge_calls"] += 1
            checkpoint["counters"] = counters
            checkpoint["charge"] = {
                "state": "INTENT_PERSISTED",
                "recorded": False,
                "amount_xu": amount,
                "idempotency_key": charge_key,
            }
            checkpoint = _save(store, checkpoint, now_epoch=now)
            try:
                charged = dict(
                    charger(
                        {
                            "job_id": job_id,
                            "amount_xu": amount,
                            "admin_no_charge": admin_no_charge,
                            "receipt_id": checkpoint["receipt"].get("receipt_id"),
                            "idempotency_key": charge_key,
                        }
                    )
                    or {}
                )
            except Exception as exc:
                checkpoint["charge"] = {
                    **dict(checkpoint.get("charge") or {}),
                    "state": "ACCEPTANCE_UNKNOWN",
                    "safe_error": type(exc).__name__,
                }
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="charge_acceptance_unknown",
                    stale_lease_recovered=stale_recovered,
                )
            if charged.get("wallet_mutated"):
                counters = _new_counters(checkpoint.get("counters"))
                counters["wallet_mutations"] += 1
                checkpoint["counters"] = counters
            if not charged.get("ok"):
                checkpoint["charge"] = {
                    **charged,
                    "state": "REJECTED",
                    "recorded": False,
                    "amount_xu": amount,
                    "idempotency_key": charge_key,
                }
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="charge_not_recorded",
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["charge"] = {
                **charged,
                "state": "RECORDED",
                "recorded": True,
                "amount_xu": amount,
                "idempotency_key": charge_key,
            }
            checkpoint.setdefault("stage_fingerprints", {})[
                "charge_recorded"
            ] = _fingerprint(checkpoint["charge"])
            checkpoint = _save(store, checkpoint, now_epoch=now)

        report = dict(checkpoint.get("terminal_report") or {})
        if not report.get("emitted"):
            stage_blocker = _block_unknown_stage(report, "terminal_report")
            if stage_blocker:
                return _result(
                    checkpoint,
                    ok=False,
                    blocker=stage_blocker,
                    stale_lease_recovered=stale_recovered,
                )
            report_key = f"terminal-report:{job_id}"
            counters = _new_counters(checkpoint.get("counters"))
            counters["terminal_report_calls"] += 1
            checkpoint["counters"] = counters
            checkpoint["terminal_report"] = {
                "state": "INTENT_PERSISTED",
                "emitted": False,
                "idempotency_key": report_key,
            }
            checkpoint = _save(store, checkpoint, now_epoch=now)
            try:
                emitted = dict(
                    terminal_reporter(
                        {
                            "job_id": job_id,
                            "terminal_state": "final_delivered",
                            "artifact_sha256": artifact_digest,
                            "receipt_id": checkpoint["receipt"].get("receipt_id"),
                            "charge_idempotency_key": checkpoint["charge"].get(
                                "idempotency_key"
                            ),
                            "idempotency_key": report_key,
                        }
                    )
                    or {}
                )
            except Exception as exc:
                checkpoint["terminal_report"] = {
                    **dict(checkpoint.get("terminal_report") or {}),
                    "state": "ACCEPTANCE_UNKNOWN",
                    "safe_error": type(exc).__name__,
                }
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="terminal_report_acceptance_unknown",
                    stale_lease_recovered=stale_recovered,
                )
            if not emitted.get("emitted") or not _clean(emitted.get("report_id")):
                checkpoint["terminal_report"] = {
                    **emitted,
                    "state": "REJECTED",
                    "emitted": False,
                    "idempotency_key": report_key,
                }
                checkpoint = _save(store, checkpoint, now_epoch=now)
                return _result(
                    checkpoint,
                    ok=False,
                    blocker="terminal_report_not_emitted",
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["terminal_report"] = {
                **emitted,
                "state": "EMITTED",
                "emitted": True,
                "idempotency_key": report_key,
            }
            checkpoint.setdefault("stage_fingerprints", {})[
                "terminal_report_emitted"
            ] = _fingerprint(checkpoint["terminal_report"])
        checkpoint["provider_state"] = one_scene.ProviderState.COMPLETED.value
        checkpoint["terminal_state"] = "final_delivered"
        checkpoint["blocker"] = ""
        checkpoint = _save(store, checkpoint, now_epoch=now)
        return _result(
            checkpoint,
            ok=True,
            outcome="final_delivered",
            stale_lease_recovered=stale_recovered,
        )
    except RecoveryCheckpointError:
        return _result(
            checkpoint,
            ok=False,
            blocker="recovery_checkpoint_invalid",
            stale_lease_recovered=stale_recovered,
        )
    finally:
        store.release_lease(job_id=job_id, token=token)
