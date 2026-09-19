"""AutoPost Publishable Asset Handoff Foundation.

Establishes the common artifact/handoff boundary that lets AutoPost consume completed
output from:
- Video Product
- Video Edit
- SubDub
- Existing Finished Video
without coupling AutoPost to the internal implementation of those processors.

Core Invariants:
1. AUTOPOST != VIDEO_PROCESSOR
2. Final-Artifact Only (Fail Closed on incomplete/failed/temporary artifacts)
3. Strict Owner Binding (requesting_user == artifact_owner)
4. Artifact Hash Binding & Replacement Safety (Metadata SHA == Physical SHA)
5. Deterministic Handoff Idempotency (Same owner, asset, sha, purpose -> single receipt)
6. Non-Compulsory Pipeline with Preserved Derivation Lineage (parent_asset_id)
7. Initial AutoPost Publication Draft: PLANNED (Zero live dispatch, zero billing)
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import os
import re
import sqlite3
from typing import Any, Optional

from services import video_local_validation


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _compute_sha256(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


class SourceProduct(str, Enum):
    VIDEO_PRODUCT = "video_product"
    VIDEO_EDIT = "video_edit"
    SUBDUB = "subdub"
    EXISTING_VIDEO = "existing_video"


SUPPORTED_SOURCE_PRODUCTS = {
    SourceProduct.VIDEO_PRODUCT.value,
    SourceProduct.VIDEO_EDIT.value,
    SourceProduct.SUBDUB.value,
    SourceProduct.EXISTING_VIDEO.value,
}


@dataclass
class PublishableAsset:
    """Canonical server-side contract representing a finished media asset eligible for AutoPost handoff."""

    asset_id: str
    owner_id: int
    source_product: str
    source_job_id: str
    source_asset_id: str
    artifact_sha256: str
    byte_size: int
    duration_seconds: float
    width: int
    height: int
    artifact_state: str
    processing_completed_at: str
    canonical_storage_ref: str
    internal_artifact_path: str = ""
    parent_asset_id: Optional[str] = None
    media_type: str = "video"
    mime_type: str = "video/mp4"
    caption_candidate: str = ""
    language: str = "vi"
    publish_eligible: bool = True
    publish_blockers: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)

    def to_client_dict(self) -> dict[str, Any]:
        """Serialize safe metadata for client consumption without exposing raw server paths."""
        data = asdict(self)
        data.pop("internal_artifact_path", None)
        return data

    def to_server_dict(self) -> dict[str, Any]:
        """Serialize complete record for internal server-side storage and verification."""
        return asdict(self)


@dataclass
class HandoffReceipt:
    """Durable, immutable handoff record between a video producer and AutoPost."""

    handoff_id: str
    asset_id: str
    owner_id: int
    source_product: str
    source_job_id: str
    artifact_sha256: str
    purpose: str = "autopost"
    status: str = "created"
    parent_asset_id: Optional[str] = None
    lineage: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    expires_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PublicationDraft:
    """AutoPost initial publication preparation draft in PLANNED state."""

    draft_id: str
    handoff_id: str
    asset_id: str
    owner_id: int
    caption_draft: str
    selected_channels: list[str] = field(default_factory=list)
    schedule: Optional[str] = None
    status: str = "PLANNED"
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_autopost_handoff_schema(conn: sqlite3.Connection) -> None:
    """Create durable persistence tables for AutoPost handoff receipts and drafts."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS autopost_handoff_receipts (
            handoff_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            source_product TEXT NOT NULL,
            source_job_id TEXT NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            purpose TEXT NOT NULL,
            status TEXT NOT NULL,
            parent_asset_id TEXT,
            lineage_json TEXT NOT NULL,
            asset_snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            UNIQUE (owner_id, asset_id, artifact_sha256, purpose)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ahr_owner ON autopost_handoff_receipts (owner_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ahr_asset ON autopost_handoff_receipts (asset_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ahr_sha ON autopost_handoff_receipts (artifact_sha256)")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS autopost_publication_drafts (
            draft_id TEXT PRIMARY KEY,
            handoff_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            caption_draft TEXT NOT NULL,
            selected_channels_json TEXT NOT NULL,
            schedule_at TEXT,
            status TEXT NOT NULL DEFAULT 'PLANNED',
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apd_owner ON autopost_publication_drafts (owner_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apd_handoff ON autopost_publication_drafts (handoff_id)")
    conn.commit()


def _validate_final_mp4(path: str) -> tuple[bool, dict[str, Any], str]:
    """Strictly validate a physical MP4 file for finality, positive size, and media integrity."""
    if not path or not isinstance(path, str):
        return False, {}, "artifact_path_missing"
    if not os.path.isfile(path):
        return False, {}, "artifact_file_not_found"
    size = os.path.getsize(path)
    if size <= 0:
        return False, {}, "artifact_zero_byte"
    try:
        probe = video_local_validation.probe_video_file(path)
    except Exception as exc:
        return False, {}, f"probe_exception:{type(exc).__name__}"
    if not probe.get("ok"):
        return False, probe, str(probe.get("reason") or "invalid_mp4_artifact")
    return True, probe, ""


def _generate_asset_id(source_product: str, source_job_id: str, sha256: str) -> str:
    digest = hashlib.sha256(f"{source_product}:{source_job_id}:{sha256}".encode("utf-8")).hexdigest()[:16]
    prefix = source_product[:3].lower()
    return f"ast_{prefix}_{digest}"


def _generate_storage_ref(source_product: str, asset_id: str, filename: str = "final.mp4") -> str:
    return f"ref://toanaas-assets/{source_product}/{asset_id}/{filename}"


# =========================================================================
# Producer Adapters
# =========================================================================

def adapt_product_video_output(
    conn: sqlite3.Connection,
    job_id: int | str,
    requesting_user_id: int,
    *,
    parent_asset_id: Optional[str] = None,
) -> tuple[Optional[PublishableAsset], str]:
    """Read adapter for Video Product completed output.

    Enforces finalizer invariants:
    - Must be a completed job with valid terminal state
    - Reject queued, processing, failed, cancelled, or intermediate scene clips
    - Strict owner verification
    - SHA256 binding and replacement safety check
    """
    try:
        jid = int(job_id)
    except (TypeError, ValueError):
        return None, "invalid_job_id"

    cur = conn.cursor()
    cur.execute("SELECT * FROM video_jobs WHERE id=?", (jid,))
    job_row = cur.fetchone()
    if not job_row:
        return None, "job_not_found"
    job = dict(job_row)

    project_id = int(job.get("project_id") or 0)
    cur.execute("SELECT * FROM video_projects WHERE project_id=?", (project_id,))
    proj_row = cur.fetchone()
    if not proj_row:
        return None, "project_not_found"
    project = dict(proj_row)

    # 1. Owner Binding
    owner_id = int(project.get("user_id") or job.get("user_id") or 0)
    if owner_id != int(requesting_user_id):
        return None, "owner_mismatch"

    # 2. Final-Artifact Status Check
    job_status = str(job.get("status") or "").strip().lower()
    if job_status in {"queued", "submitted", "pending"}:
        return None, "job_queued"
    if job_status == "processing":
        return None, "job_processing"
    if job_status in {"failed", "error"}:
        return None, "job_failed"
    if job_status == "cancelled":
        return None, "job_cancelled"
    if job_status != "completed":
        return None, f"job_status_not_completed:{job_status}"

    terminal_state = str(project.get("video_terminal_state") or "").strip().lower()
    if terminal_state not in {"final_mp4_ready", "final_delivered", "delivered"}:
        return None, f"invalid_project_terminal_state:{terminal_state}"

    # 3. Reject Intermediate Clips
    result_payload = {}
    if job.get("result_json"):
        try:
            result_payload = json.loads(job["result_json"]) if isinstance(job["result_json"], str) else dict(job["result_json"])
        except Exception:
            result_payload = {}

    if result_payload.get("is_intermediate_clip") or result_payload.get("scene_index") is not None:
        return None, "intermediate_scene_clip_rejected"

    # 4. Resolve Canonical Path
    final_path = str(
        project.get("final_video_path")
        or result_payload.get("final_video_path")
        or result_payload.get("final_mp4_path")
        or ""
    ).strip()
    if not final_path:
        return None, "missing_final_artifact_path"

    # 5. Media Integrity Probe
    valid, probe, reason = _validate_final_mp4(final_path)
    if not valid:
        return None, reason

    # 6. SHA Binding & Replacement Safety
    physical_sha = _compute_sha256(final_path)
    persisted_sha = str(
        project.get("video_artifact_hash")
        or result_payload.get("completion_only_reconciliation_sha256")
        or result_payload.get("artifact_sha256")
        or ""
    ).strip().lower()

    if persisted_sha and persisted_sha != physical_sha:
        return None, "artifact_replacement_detected"

    artifact_sha = physical_sha
    asset_id = _generate_asset_id(SourceProduct.VIDEO_PRODUCT.value, str(jid), artifact_sha)
    storage_ref = _generate_storage_ref(SourceProduct.VIDEO_PRODUCT.value, asset_id)

    caption = str(result_payload.get("caption") or project.get("topic") or "").strip()
    completed_at = str(job.get("completed_at") or project.get("video_delivered_at") or project.get("updated_at") or _now_iso())

    asset = PublishableAsset(
        asset_id=asset_id,
        owner_id=owner_id,
        source_product=SourceProduct.VIDEO_PRODUCT.value,
        source_job_id=str(jid),
        source_asset_id=str(project.get("final_video_file_id") or result_payload.get("output_file_id") or asset_id),
        parent_asset_id=parent_asset_id,
        artifact_sha256=artifact_sha,
        byte_size=os.path.getsize(final_path),
        duration_seconds=float(probe.get("duration") or 0.0),
        width=int(probe.get("width") or 0),
        height=int(probe.get("height") or 0),
        artifact_state="final_ready",
        processing_completed_at=completed_at,
        canonical_storage_ref=storage_ref,
        internal_artifact_path=final_path,
        caption_candidate=caption,
        language="vi",
        publish_eligible=True,
        publish_blockers=[],
    )
    return asset, ""


def adapt_video_edit_output(
    conn: sqlite3.Connection,
    job_id: int | str,
    requesting_user_id: int,
    *,
    parent_asset_id: Optional[str] = None,
) -> tuple[Optional[PublishableAsset], str]:
    """Read adapter for Video Edit completed output.

    Enforces video edit invariants:
    - Resolves only canonical output_path and output_sha256
    - Never resolves source input video, intermediate FFmpeg temp files
    - Strict owner verification
    - SHA256 binding and replacement safety check
    """
    try:
        jid = int(job_id)
    except (TypeError, ValueError):
        return None, "invalid_job_id"

    cur = conn.cursor()
    cur.execute("SELECT * FROM video_edit_jobs WHERE id=?", (jid,))
    row = cur.fetchone()
    if not row:
        return None, "job_not_found"
    job = dict(row)

    # 1. Owner Binding
    owner_id = int(job.get("user_id") or 0)
    if owner_id != int(requesting_user_id):
        return None, "owner_mismatch"

    # 2. Status Check
    status = str(job.get("status") or "").strip().lower()
    if status == "queued":
        return None, "job_queued"
    if status in {"processing", "running"}:
        return None, "job_processing"
    if status in {"failed", "cancelled", "error"}:
        return None, "job_failed"
    if status not in {"completed", "delivered", "success"}:
        return None, f"job_status_not_completed:{status}"

    # 3. Canonical Output Path Only (Never source input video or worker temp)
    output_path = str(job.get("output_path") or "").strip()
    if not output_path:
        return None, "missing_final_artifact_path"

    # 4. Media Integrity Probe
    valid, probe, reason = _validate_final_mp4(output_path)
    if not valid:
        return None, reason

    # 5. SHA Binding & Replacement Safety
    physical_sha = _compute_sha256(output_path)
    recorded_sha = str(job.get("output_sha256") or "").strip().lower()

    if recorded_sha and recorded_sha != physical_sha:
        return None, "artifact_replacement_detected"

    artifact_sha = physical_sha
    asset_id = _generate_asset_id(SourceProduct.VIDEO_EDIT.value, str(jid), artifact_sha)
    storage_ref = _generate_storage_ref(SourceProduct.VIDEO_EDIT.value, asset_id)

    # Inherit or resolve lineage: check if edit job recorded a parent asset id
    resolved_parent = parent_asset_id
    if not resolved_parent and job.get("tail_json"):
        try:
            tail = json.loads(job["tail_json"])
            resolved_parent = tail.get("source_asset_id") or tail.get("parent_asset_id")
        except Exception:
            pass

    completed_at = str(job.get("finished_at") or job.get("delivered_at") or job.get("updated_at") or _now_iso())

    asset = PublishableAsset(
        asset_id=asset_id,
        owner_id=owner_id,
        source_product=SourceProduct.VIDEO_EDIT.value,
        source_job_id=str(jid),
        source_asset_id=str(job.get("output_file_id") or asset_id),
        parent_asset_id=resolved_parent,
        artifact_sha256=artifact_sha,
        byte_size=os.path.getsize(output_path),
        duration_seconds=float(probe.get("duration") or 0.0),
        width=int(probe.get("width") or 0),
        height=int(probe.get("height") or 0),
        artifact_state="final_ready",
        processing_completed_at=completed_at,
        canonical_storage_ref=storage_ref,
        internal_artifact_path=output_path,
        caption_candidate="",
        language="vi",
        publish_eligible=True,
        publish_blockers=[],
    )
    return asset, ""


def adapt_subdub_output(
    conn: Optional[sqlite3.Connection],
    job_id: str,
    requesting_user_id: int,
    *,
    parent_asset_id: Optional[str] = None,
    in_memory_job: Optional[dict[str, Any]] = None,
) -> tuple[Optional[PublishableAsset], str]:
    """Read adapter for SubDub completed output.

    Enforces SubDub invariants:
    - Resolves final completed SubDub output
    - Requires completed status and delivered terminal state
    - Rejects jobs where full video failed (e.g. partial audio fallback only)
    - Strict owner verification
    - SHA256 binding and replacement safety check
    """
    job = dict(in_memory_job or {})
    jid = str(job_id or "").strip()

    if not job and conn is not None and jid:
        try:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key=? LIMIT 1",
                (f"subdub:job:{jid}",),
            ).fetchone()
            if row and row[0]:
                job = json.loads(row[0])
        except Exception:
            pass

    if not job:
        return None, "job_not_found"

    # 1. Owner Binding
    owner_id = int(job.get("user_id") or 0)
    if owner_id != int(requesting_user_id):
        return None, "owner_mismatch"

    # 2. Status Check
    status = str(job.get("status") or "").strip().lower()
    terminal = str(job.get("terminal_state") or "").strip().lower()
    if status == "running" or job.get("lifecycle_state") in {"processing", "received_file"}:
        return None, "job_processing"
    if status in {"failed", "failed_no_charge"} or job.get("full_video_failed"):
        return None, "job_failed"
    if terminal not in {"delivered", "completed"} and not (status == "completed" and job.get("output_sent")):
        return None, "not_final_delivered"

    # 3. Output Path
    final_path = str(
        job.get("final_video_path")
        or job.get("output_video_path")
        or job.get("video_output")
        or job.get("output_path")
        or ""
    ).strip()
    if not final_path:
        return None, "missing_final_artifact_path"

    # 4. Media Integrity Probe
    valid, probe, reason = _validate_final_mp4(final_path)
    if not valid:
        return None, reason

    # 5. SHA Binding & Replacement Safety
    physical_sha = _compute_sha256(final_path)
    recorded_sha = str(
        job.get("video_delivery_sha256")
        or job.get("output_sha256")
        or job.get("final_sha256")
        or ""
    ).strip().lower()

    if recorded_sha and recorded_sha != physical_sha:
        return None, "artifact_replacement_detected"

    artifact_sha = physical_sha
    asset_id = _generate_asset_id(SourceProduct.SUBDUB.value, jid, artifact_sha)
    storage_ref = _generate_storage_ref(SourceProduct.SUBDUB.value, asset_id)

    completed_at = str(
        job.get("subdub_delivered_at")
        or job.get("delivered_at")
        or job.get("completed_at")
        or _now_iso()
    )

    asset = PublishableAsset(
        asset_id=asset_id,
        owner_id=owner_id,
        source_product=SourceProduct.SUBDUB.value,
        source_job_id=jid,
        source_asset_id=str(job.get("video_delivery_file_id") or asset_id),
        parent_asset_id=parent_asset_id or job.get("parent_asset_id"),
        artifact_sha256=artifact_sha,
        byte_size=os.path.getsize(final_path),
        duration_seconds=float(probe.get("duration") or 0.0),
        width=int(probe.get("width") or 0),
        height=int(probe.get("height") or 0),
        artifact_state="final_ready",
        processing_completed_at=completed_at,
        canonical_storage_ref=storage_ref,
        internal_artifact_path=final_path,
        caption_candidate=str(job.get("source_caption") or "").strip(),
        language=str(job.get("target_language") or "vi"),
        publish_eligible=True,
        publish_blockers=[],
    )
    return asset, ""


def adapt_existing_video_output(
    conn: Optional[sqlite3.Connection],
    asset_record: dict[str, Any],
    requesting_user_id: int,
    *,
    parent_asset_id: Optional[str] = None,
) -> tuple[Optional[PublishableAsset], str]:
    """Read adapter for existing uploaded or pre-existing finished video.

    Only operates on proven canonical records with valid media and ownership.
    """
    if not asset_record or not isinstance(asset_record, dict):
        return None, "invalid_asset_record"

    owner_id = int(asset_record.get("owner_id") or asset_record.get("owner_user_id") or 0)
    if owner_id != int(requesting_user_id):
        return None, "owner_mismatch"

    local_path = str(asset_record.get("local_path") or asset_record.get("path") or "").strip()
    if not local_path:
        return None, "missing_final_artifact_path"

    valid, probe, reason = _validate_final_mp4(local_path)
    if not valid:
        return None, reason

    physical_sha = _compute_sha256(local_path)
    expected_sha = str(asset_record.get("sha256") or asset_record.get("artifact_sha256") or "").strip().lower()
    if expected_sha and expected_sha != physical_sha:
        return None, "artifact_replacement_detected"

    artifact_sha = physical_sha
    source_asset_id = str(asset_record.get("asset_id") or asset_record.get("media_id") or "existing").strip()
    asset_id = _generate_asset_id(SourceProduct.EXISTING_VIDEO.value, source_asset_id, artifact_sha)
    storage_ref = _generate_storage_ref(SourceProduct.EXISTING_VIDEO.value, asset_id)

    asset = PublishableAsset(
        asset_id=asset_id,
        owner_id=owner_id,
        source_product=SourceProduct.EXISTING_VIDEO.value,
        source_job_id=source_asset_id,
        source_asset_id=source_asset_id,
        parent_asset_id=parent_asset_id or asset_record.get("parent_asset_id"),
        artifact_sha256=artifact_sha,
        byte_size=os.path.getsize(local_path),
        duration_seconds=float(probe.get("duration") or 0.0),
        width=int(probe.get("width") or 0),
        height=int(probe.get("height") or 0),
        artifact_state="final_ready",
        processing_completed_at=str(asset_record.get("created_at") or _now_iso()),
        canonical_storage_ref=storage_ref,
        internal_artifact_path=local_path,
        caption_candidate=str(asset_record.get("caption") or "").strip(),
        language="vi",
        publish_eligible=True,
        publish_blockers=[],
    )
    return asset, ""


# =========================================================================
# AutoPost Handoff Service & Receiver Boundary
# =========================================================================

def create_autopost_handoff(
    conn: sqlite3.Connection,
    asset: PublishableAsset,
    requesting_user_id: int,
    *,
    purpose: str = "autopost",
) -> tuple[Optional[HandoffReceipt], str]:
    """Create an immutable, idempotent handoff receipt for an eligible publishable asset.

    Guarantees:
    - Zero media rendering / copying
    - Fail-closed if artifact SHA has changed or physical file missing
    - Strictly bound to requesting owner
    - Deterministic duplicate deduplication (returns existing receipt)
    - Preserves derivation lineage
    """
    ensure_autopost_handoff_schema(conn)

    # 1. Owner Binding
    if int(requesting_user_id) != int(asset.owner_id):
        return None, "owner_mismatch"

    # 2. Eligibility Check
    if not asset.publish_eligible:
        return None, f"asset_not_publish_eligible:{','.join(asset.publish_blockers)}"

    # 3. Artifact Replacement Safety
    if asset.internal_artifact_path:
        if not os.path.isfile(asset.internal_artifact_path):
            return None, "artifact_file_missing"
        current_physical_sha = _compute_sha256(asset.internal_artifact_path)
        if current_physical_sha != asset.artifact_sha256:
            return None, "artifact_replacement_detected"

    # 4. Idempotency Check
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM autopost_handoff_receipts
           WHERE owner_id=? AND asset_id=? AND artifact_sha256=? AND purpose=?
           LIMIT 1""",
        (asset.owner_id, asset.asset_id, asset.artifact_sha256, purpose),
    )
    existing_row = cur.fetchone()
    if existing_row:
        existing = dict(existing_row)
        lineage = json.loads(existing.get("lineage_json") or "[]")
        receipt = HandoffReceipt(
            handoff_id=existing["handoff_id"],
            asset_id=existing["asset_id"],
            owner_id=existing["owner_id"],
            source_product=existing["source_product"],
            source_job_id=existing["source_job_id"],
            artifact_sha256=existing["artifact_sha256"],
            purpose=existing["purpose"],
            status=existing["status"],
            parent_asset_id=existing.get("parent_asset_id"),
            lineage=lineage,
            created_at=existing["created_at"],
            expires_at=existing.get("expires_at"),
        )
        return receipt, "idempotent_existing_receipt"

    # 5. Build Lineage Chain
    lineage = [asset.asset_id]
    if asset.parent_asset_id:
        lineage.append(asset.parent_asset_id)
        # Traverse prior handoffs to trace ancestry C -> B -> A
        cur.execute(
            "SELECT lineage_json FROM autopost_handoff_receipts WHERE asset_id=? LIMIT 1",
            (asset.parent_asset_id,),
        )
        parent_row = cur.fetchone()
        if parent_row and parent_row[0]:
            try:
                parent_lineage = json.loads(parent_row[0])
                for item in parent_lineage:
                    if item not in lineage:
                        lineage.append(item)
            except Exception:
                pass

    # 6. Create Durable Receipt
    handoff_hash = hashlib.sha256(
        f"{asset.owner_id}:{asset.asset_id}:{asset.artifact_sha256}:{purpose}".encode("utf-8")
    ).hexdigest()[:24]
    handoff_id = f"hnd_{handoff_hash}"
    now_ts = _now_iso()

    conn.execute(
        """INSERT INTO autopost_handoff_receipts (
            handoff_id, asset_id, owner_id, source_product, source_job_id,
            artifact_sha256, purpose, status, parent_asset_id, lineage_json,
            asset_snapshot_json, created_at, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            handoff_id,
            asset.asset_id,
            asset.owner_id,
            asset.source_product,
            asset.source_job_id,
            asset.artifact_sha256,
            purpose,
            "created",
            asset.parent_asset_id,
            json.dumps(lineage),
            json.dumps(asset.to_server_dict()),
            now_ts,
            None,
        ),
    )
    conn.commit()

    receipt = HandoffReceipt(
        handoff_id=handoff_id,
        asset_id=asset.asset_id,
        owner_id=asset.owner_id,
        source_product=asset.source_product,
        source_job_id=asset.source_job_id,
        artifact_sha256=asset.artifact_sha256,
        purpose=purpose,
        status="created",
        parent_asset_id=asset.parent_asset_id,
        lineage=lineage,
        created_at=now_ts,
        expires_at=None,
    )
    return receipt, "created"


def receive_autopost_handoff_to_draft(
    conn: sqlite3.Connection,
    handoff: HandoffReceipt,
    asset: PublishableAsset,
    requesting_user_id: int,
) -> tuple[Optional[PublicationDraft], str]:
    """AutoPost receiver boundary: accepts a valid handoff and registers a publication draft.

    Contract:
    - Creates a draft in initial status PLANNED
    - Zero platform dispatch, zero external API calls, zero billing side effects
    """
    ensure_autopost_handoff_schema(conn)

    # 1. Owner & Asset Verification
    if int(requesting_user_id) != int(handoff.owner_id) or int(requesting_user_id) != int(asset.owner_id):
        return None, "owner_mismatch"
    if handoff.asset_id != asset.asset_id:
        return None, "asset_id_mismatch"
    if handoff.artifact_sha256 != asset.artifact_sha256:
        return None, "artifact_sha_mismatch"

    # 2. Idempotency Check for Draft
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM autopost_publication_drafts WHERE handoff_id=? LIMIT 1",
        (handoff.handoff_id,),
    )
    existing_row = cur.fetchone()
    if existing_row:
        existing = dict(existing_row)
        draft = PublicationDraft(
            draft_id=existing["draft_id"],
            handoff_id=existing["handoff_id"],
            asset_id=existing["asset_id"],
            owner_id=existing["owner_id"],
            caption_draft=existing["caption_draft"],
            selected_channels=json.loads(existing.get("selected_channels_json") or "[]"),
            schedule=existing.get("schedule_at"),
            status=existing["status"],
            created_at=existing["created_at"],
        )
        return draft, "idempotent_existing_draft"

    draft_hash = hashlib.sha256(f"{handoff.handoff_id}:{handoff.owner_id}".encode("utf-8")).hexdigest()[:24]
    draft_id = f"draft_{draft_hash}"
    now_ts = _now_iso()

    conn.execute(
        """INSERT INTO autopost_publication_drafts (
            draft_id, handoff_id, asset_id, owner_id, caption_draft,
            selected_channels_json, schedule_at, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            draft_id,
            handoff.handoff_id,
            asset.asset_id,
            handoff.owner_id,
            asset.caption_candidate,
            json.dumps([]),
            None,
            "PLANNED",
            now_ts,
        ),
    )
    conn.commit()

    draft = PublicationDraft(
        draft_id=draft_id,
        handoff_id=handoff.handoff_id,
        asset_id=asset.asset_id,
        owner_id=handoff.owner_id,
        caption_draft=asset.caption_candidate,
        selected_channels=[],
        schedule=None,
        status="PLANNED",
        created_at=now_ts,
    )
    return draft, "draft_created"
