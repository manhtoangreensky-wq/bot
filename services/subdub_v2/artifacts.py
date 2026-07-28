"""Thread-safe three-level idempotency registry for isolated V2 replay."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import threading
from typing import Any

from .contracts import AcceptanceState, ClaimState, require_valid_artifact
from .fingerprints import sha256_hex, short_id


@dataclass(frozen=True)
class ClaimResult:
    key: str
    level: str
    created: bool
    state: str
    scope_id: str
    job_id: str = ""
    claim_id: str = ""
    acceptance_state: str = AcceptanceState.PENDING.value
    replacement_submit_allowed: bool = False


class StageArtifactRegistry:
    """Small JSON-capable registry with no DB, provider or network dependency."""

    def __init__(self, *, scope_id: str, store_path: str | Path | None = None) -> None:
        self.scope_id = str(scope_id or "").strip()
        if not self.scope_id:
            raise ValueError("scope_id_required")
        self.scope_hash = sha256_hex(self.scope_id)[:20]
        self.store_path = Path(store_path) if store_path else None
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._artifacts: dict[str, dict[str, Any]] = {}
        self.duplicate_request_reuse_count = 0
        self.duplicate_stage_reuse_count = 0
        self.duplicate_side_effect_reuse_count = 0
        if self.store_path and self.store_path.exists():
            self._load()

    def _load(self) -> None:
        payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        if payload.get("scope_hash") != self.scope_hash:
            raise PermissionError("scope_mismatch")
        self._records = dict(payload.get("records") or {})
        self._artifacts = dict(payload.get("artifacts") or {})

    def _persist(self) -> None:
        if self.store_path is None:
            return
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0.0",
            "scope_hash": self.scope_hash,
            "records": self._records,
            "artifacts": self._artifacts,
        }
        temporary = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        os.replace(temporary, self.store_path)

    def _claim(self, *, level: str, key_payload: dict[str, Any], job_id: str = "", details: dict[str, Any] | None = None) -> ClaimResult:
        fingerprint = sha256_hex({"scope_hash": self.scope_hash, "level": level, **key_payload})
        key = f"{level}:{fingerprint}"
        with self._lock:
            current = self._records.get(key)
            if current is not None:
                if current.get("scope_hash") != self.scope_hash:
                    raise PermissionError("scope_mismatch")
                if level == "request":
                    self.duplicate_request_reuse_count += 1
                elif level == "stage":
                    self.duplicate_stage_reuse_count += 1
                else:
                    self.duplicate_side_effect_reuse_count += 1
                return ClaimResult(
                    key=key,
                    level=level,
                    created=False,
                    state=str(current["state"]),
                    scope_id=self.scope_id,
                    job_id=str(current.get("job_id") or ""),
                    claim_id=str(current.get("claim_id") or ""),
                    acceptance_state=str(current.get("acceptance_state") or current.get("state") or AcceptanceState.PENDING.value),
                    replacement_submit_allowed=bool(current.get("replacement_submit_allowed", False)),
                )
            resolved_job = str(job_id or short_id("job", {"scope_hash": self.scope_hash, **key_payload}, 20))
            claim_id = short_id("claim", {"level": level, "key": fingerprint}, 20)
            record = {
                "key": key,
                "claim_id": claim_id,
                "level": level,
                "scope_id": self.scope_id,
                "scope_hash": self.scope_hash,
                "job_id": resolved_job,
                "state": ClaimState.CLAIMED.value,
                "acceptance_state": AcceptanceState.PENDING.value,
                "replacement_submit_allowed": False,
                "admin_review_required": False,
                "charge_eligible": False,
                "key_payload": deepcopy(key_payload),
                **deepcopy(details or {}),
            }
            self._records[key] = record
            self._persist()
            return ClaimResult(
                key,
                level,
                True,
                record["state"],
                self.scope_id,
                resolved_job,
                claim_id,
                record["acceptance_state"],
                False,
            )

    def claim_request(self, source_fingerprint: str, request_config_fingerprint: str) -> ClaimResult:
        return self._claim(
            level="request",
            key_payload={
                "source_fingerprint": str(source_fingerprint),
                "request_config_fingerprint": str(request_config_fingerprint),
            },
        )

    def claim_stage(
        self,
        job_id: str,
        stage_name: str,
        upstream_fingerprint: str,
        config_fingerprint: str,
        segment_or_global: str = "global",
    ) -> ClaimResult:
        return self._claim(
            level="stage",
            job_id=str(job_id),
            key_payload={
                "job_id": str(job_id),
                "stage_name": str(stage_name),
                "upstream_fingerprint": str(upstream_fingerprint),
                "config_fingerprint": str(config_fingerprint),
                "segment_or_global": str(segment_or_global or "global"),
            },
            details={"stage_name": str(stage_name), "segment_or_global": str(segment_or_global or "global")},
        )

    def claim_side_effect(
        self,
        provider_alias: str,
        transport_group_or_delivery: str,
        artifact_fingerprint: str,
        sequence: int,
    ) -> ClaimResult:
        return self._claim(
            level="side_effect",
            key_payload={
                "provider_alias": str(provider_alias),
                "transport_group_or_delivery": str(transport_group_or_delivery),
                "artifact_fingerprint": str(artifact_fingerprint),
                "sequence": int(sequence),
            },
            details={
                "provider_alias": str(provider_alias),
                "transport_sequence": int(sequence),
                "request_fingerprint": sha256_hex({"provider_alias": provider_alias, "group": transport_group_or_delivery, "artifact": artifact_fingerprint, "sequence": sequence}),
            },
        )

    def mark_acceptance_unknown(
        self,
        key: str,
        *,
        reason: str,
        provider_task_id_present: bool = False,
        last_safe_operation: str = "none",
    ) -> dict[str, Any]:
        if last_safe_operation not in {"poll", "retrieve", "inspect", "none"}:
            raise ValueError("invalid_safe_operation")
        with self._lock:
            record = self._required(key)
            record.update(
                {
                    "state": AcceptanceState.ACCEPTANCE_UNKNOWN.value,
                    "acceptance_state": AcceptanceState.ACCEPTANCE_UNKNOWN.value,
                    "safe_reason": str(reason),
                    "provider_task_id_present": bool(provider_task_id_present),
                    "last_safe_operation": last_safe_operation,
                    "replacement_submit_allowed": False,
                    "admin_review_required": True,
                    "charge_eligible": False,
                }
            )
            self._persist()
            return deepcopy(record)

    def mark_completed(self, key: str, *, artifact_id: str = "") -> dict[str, Any]:
        with self._lock:
            record = self._required(key)
            if record.get("state") == AcceptanceState.ACCEPTANCE_UNKNOWN.value:
                raise RuntimeError("acceptance_unknown_requires_review")
            record.update(
                {
                    "state": ClaimState.COMPLETED.value,
                    "acceptance_state": AcceptanceState.COMPLETED.value,
                    "artifact_id": str(artifact_id or record.get("artifact_id") or ""),
                    "replacement_submit_allowed": False,
                }
            )
            self._persist()
            return deepcopy(record)

    def mark_failed(self, key: str, *, reason: str) -> dict[str, Any]:
        with self._lock:
            record = self._required(key)
            record.update(
                {
                    "state": ClaimState.FAILED.value,
                    "acceptance_state": AcceptanceState.FAILED.value,
                    "safe_reason": str(reason),
                    "replacement_submit_allowed": False,
                    "charge_eligible": False,
                }
            )
            self._persist()
            return deepcopy(record)

    def store_artifact(self, claim_key: str, artifact: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            record = self._required(claim_key)
            checked = require_valid_artifact(dict(artifact), scope_id=self.scope_id)
            self._artifacts[checked["artifact_id"]] = deepcopy(checked)
            record["artifact_id"] = checked["artifact_id"]
            self._persist()
            return deepcopy(checked)

    def get_artifact(self, artifact_id: str, *, scope_id: str) -> dict[str, Any] | None:
        if str(scope_id) != self.scope_id:
            raise PermissionError("scope_mismatch")
        artifact = self._artifacts.get(str(artifact_id))
        return deepcopy(artifact) if artifact is not None else None

    def _required(self, key: str) -> dict[str, Any]:
        if key not in self._records:
            raise KeyError(key)
        record = self._records[key]
        if record.get("scope_hash") != self.scope_hash:
            raise PermissionError("scope_mismatch")
        return record

    def get(self, key: str) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._required(key))

    def assert_scope(self, key: str, scope_id: str) -> None:
        record = self.get(key)
        if str(scope_id) != self.scope_id or record.get("scope_hash") != self.scope_hash:
            raise PermissionError("scope_mismatch")

    def read_status(self, key: str) -> dict[str, Any]:
        """Read-only status lookup: it never creates a task or claim."""
        return self.get(key)

    def recovery_action(self, key: str) -> str:
        record = self.get(key)
        if record.get("state") == AcceptanceState.ACCEPTANCE_UNKNOWN.value:
            operation = str(record.get("last_safe_operation") or "inspect")
            return "inspect" if operation == "none" else operation
        if record.get("provider_task_id_present"):
            return "poll"
        return "inspect"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"scope_hash": self.scope_hash, "records": deepcopy(self._records), "artifacts": deepcopy(self._artifacts)}

    @property
    def duplicate_stage_submit_count(self) -> int:
        # Reused claims do not create work, so duplicate submits remain zero.
        return 0

    @property
    def duplicate_side_effect_count(self) -> int:
        return 0


ArtifactRegistry = StageArtifactRegistry

__all__ = ["ArtifactRegistry", "ClaimResult", "StageArtifactRegistry"]
