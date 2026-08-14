"""Shadow delivery receipt ordering with all external effects suppressed."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .contracts import finalize_artifact
from .fingerprints import sha256_hex, short_id


class ShadowDeliveryLedger:
    def __init__(self, *, scope_id: str) -> None:
        self.scope_id = str(scope_id or "").strip()
        if not self.scope_id:
            raise ValueError("scope_id_required")
        self.provider_calls = 0
        self.customer_deliveries = 0
        self.wallet_mutations = 0
        self.production_traffic = 0
        self.events: list[str] = []
        self._receipts: dict[str, dict[str, Any]] = {}
        self._charge_claims: set[str] = set()

    def persist_receipt(
        self,
        *,
        job_id: str,
        lane: str,
        final_artifact_id: str,
        final_qc_artifact_id: str,
        final_artifact_fingerprint: str = "",
        final_size_bytes: int = 1,
        final_duration_ms: int = 1,
        root_source_id: str = "",
        final_mp4_validated: bool = True,
    ) -> dict[str, Any]:
        if not final_artifact_id or not final_qc_artifact_id or not final_mp4_validated:
            raise RuntimeError("validated_artifact_required")
        if int(final_size_bytes or 0) <= 0 or int(final_duration_ms or 0) <= 0:
            raise RuntimeError("validated_mp4_required")
        receipt_id = short_id("delivery", {"scope_id": self.scope_id, "job_id": job_id, "lane": lane, "artifact": final_artifact_id}, 20)
        if receipt_id in self._receipts:
            return deepcopy(self._receipts[receipt_id])
        if not self.events or self.events[-1] != "validated":
            self.events.append("validated")
        receipt = {
            "schema_name": "delivery_receipt",
            "receipt_id": receipt_id,
            "job_id": str(job_id),
            "lane": str(lane),
            "final_artifact_id": str(final_artifact_id),
            "final_artifact_fingerprint": str(final_artifact_fingerprint or sha256_hex(final_artifact_id)),
            "final_size_bytes": max(1, int(final_size_bytes or 0)),
            "final_duration_ms": max(1, int(final_duration_ms or 0)),
            "final_qc_artifact_id": str(final_qc_artifact_id),
            "delivery_channel": "shadow_fixture",
            "delivery_message_id": None,
            "delivered_at": None,
            "delivery_status": "NOT_DELIVERED_SHADOW",
            "charge_eligibility": "INELIGIBLE_SHADOW",
            "charge_idempotency_key": sha256_hex({"scope_id": self.scope_id, "receipt_id": receipt_id}),
            "charge_state": "NOT_CLAIMED",
            "public_report_state": "NOT_SENT",
            "input_fingerprint": sha256_hex({"final_artifact": final_artifact_id, "final_qc": final_qc_artifact_id}),
            "retention_class": "subdub_delivery_90d",
        }
        receipt = finalize_artifact(
            receipt,
            scope_id=self.scope_id,
            root_source_id=str(root_source_id or final_artifact_id),
            parent_artifact_ids=[str(final_qc_artifact_id)],
            upstream_fingerprints=[receipt["final_artifact_fingerprint"]],
        )
        self._receipts[receipt_id] = receipt
        self.events.append("receipt_persisted")
        return deepcopy(receipt)

    def charge(self, receipt_id: str) -> dict[str, Any]:
        receipt = self._receipts.get(str(receipt_id))
        if receipt is None:
            raise RuntimeError("receipt_required")
        if receipt_id in self._charge_claims:
            return deepcopy(receipt)
        self._charge_claims.add(receipt_id)
        receipt["charge_state"] = "NOT_CLAIMED"
        self.events.append("charge_suppressed_shadow")
        return deepcopy(receipt)

    def deliver(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("customer_delivery_forbidden_in_shadow")

    def get_receipt(self, receipt_id: str, *, scope_id: str | None = None) -> dict[str, Any] | None:
        if scope_id is not None and str(scope_id) != self.scope_id:
            raise PermissionError("scope_mismatch")
        value = self._receipts.get(str(receipt_id))
        return deepcopy(value) if value is not None else None

    @property
    def receipts(self) -> list[dict[str, Any]]:
        return [deepcopy(value) for value in self._receipts.values()]


DeliveryLedger = ShadowDeliveryLedger

__all__ = ["DeliveryLedger", "ShadowDeliveryLedger"]
