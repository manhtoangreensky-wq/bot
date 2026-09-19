"""AutoPost Publishable Asset Handoff Canonical Authority Service.

Establishes the common artifact/handoff boundary that lets AutoPost consume completed
output from:
- Video Product
- Video Edit
- SubDub (Guarded)
- Existing Finished Video (Guarded)
without coupling AutoPost to the internal implementation of those processors.

Core Invariants:
1. AUTOPOST != VIDEO_PROCESSOR
2. Authoritative Public Entrypoint Re-Resolves Source Truth:
   create_autopost_handoff_from_source(conn, source_product, source_ref, requesting_user_id)
3. Shared Producer Terminal Completion Gate:
   All paths (both completion-only and standard) require terminal completed state:
   job.status == 'completed' AND project.status == 'completed' AND
   project.video_terminal_state in {'final_mp4_ready', 'final_delivered', 'delivered'}
4. No Boolean Trust Bypass:
   Caller-created PublishableAsset cannot create a handoff by passing a trust flag.
   Internal persistence helper _persist_canonical_autopost_handoff is private and private-only.
5. PV12 Identity Contract:
   Completion-only reconciliation SHA authority agreement (Fail-Closed on drift)
6. Video Edit Canonical Terminal Contract:
   delivered/charged with created receipt and valid physical MP4
7. SubDub / Existing Video: Guarded (Fail-Closed on unavailable canonical storage authority)
8. Storage Reference Truth: Only actual producer remote IDs (no fabricated schemes)
9. Durable DB Receipt Authority: Draft creation loads receipt from DB & revalidates artifact
10. Lineage Owner Scoping: Cross-owner parent lineage strictly forbidden
11. Concurrent Idempotency: SQLite-safe deterministic UNIQUE conflict recovery
12. Initial AutoPost Publication Draft: PLANNED (Zero live dispatch, zero billing)
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
from services.video_project_queue import _canonical_persisted_final_mp4_path
import services.video_editengine1 as video_editengine1


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _is_64_hex(val: Any) -> bool:
    if not isinstance(val, str):
        return False
    s = val.strip().lower()
    return bool(re.fullmatch(r"^[0-9a-f]{64}$", s))


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

SUPPORTED_PURPOSES = {"autopost"}


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
    canonical_storage_ref: str = ""
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
            handoff_id TEXT NOT NULL UNIQUE,
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


# =========================================================================
# Producer Canonical Resolvers
# =========================================================================

def adapt_product_video_output(
    conn: sqlite3.Connection,
    job_id: int | str,
    requesting_user_id: int,
    *,
    parent_asset_id: Optional[str] = None,
) -> tuple[Optional[PublishableAsset], str]:
    """Canonical resolver for Video Product completed output.

    Enforces finalizer invariants:
    - Shared terminal completion gate: applies to ALL paths (both completion-only and standard)
      job.status == 'completed'
      project.status == 'completed'
      project.video_terminal_state in {'final_mp4_ready', 'final_delivered', 'delivered'}
    - Reject queued, processing, failed, cancelled, or intermediate scene clips
    - Strict owner verification
    - Path resolved via _canonical_persisted_final_mp4_path
    - PV12 identity contract:
      For completion-only reconciliation:
        recon_sha and project_sha must be strict 64-hex
        where both exist: recon_sha == project_sha == physical_sha
        Fail-closed on authority drift (no preference)
      For standard completed:
        persisted_sha == physical_sha
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

    # 2. Shared Terminal Completion State Validation (applies to ALL paths before branching)
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

    proj_status = str(project.get("status") or "").strip().lower()
    if proj_status != "completed":
        return None, f"project_status_not_completed:{proj_status}"

    terminal_state = str(project.get("video_terminal_state") or "").strip().lower()
    if terminal_state not in {"final_mp4_ready", "final_delivered", "delivered"}:
        return None, f"invalid_project_terminal_state:{terminal_state}"

    # 3. Intermediate Clip Rejection
    result_payload = {}
    if job.get("result_json"):
        try:
            result_payload = (
                json.loads(job["result_json"])
                if isinstance(job["result_json"], str)
                else dict(job["result_json"])
            )
        except Exception:
            result_payload = {}

    if result_payload.get("is_intermediate_clip") or result_payload.get("scene_index") is not None:
        return None, "intermediate_scene_clip_rejected"

    # 4. Canonical Path Resolution (Hardened PV12 resolver)
    final_path = _canonical_persisted_final_mp4_path(project, result_payload)
    if not final_path:
        return None, "canonical_artifact_path_missing"

    # 5. Media Integrity Probe
    valid, probe, reason = _validate_final_mp4(final_path)
    if not valid:
        return None, reason

    # 6. Physical SHA256 computation
    physical_sha = _compute_sha256(final_path)

    # 7. PV12 Identity Contract Check
    is_completion_only = bool(result_payload.get("completion_only_reconciliation_used"))
    if is_completion_only:
        recon_sha = str(result_payload.get("completion_only_reconciliation_sha256") or "").strip().lower()
        if not _is_64_hex(recon_sha):
            return None, "completion_only_reconciliation_sha_invalid"

        project_sha = str(project.get("video_artifact_hash") or "").strip().lower()
        if project_sha:
            if not _is_64_hex(project_sha):
                return None, "project_artifact_sha_invalid"
            # Strict authority agreement: fail-closed on drift
            if project_sha != recon_sha:
                return None, "completion_sha_authority_drift_blocked"

        if physical_sha != recon_sha:
            return None, "physical_sha_mismatch"
    else:
        persisted_sha = str(
            project.get("video_artifact_hash")
            or result_payload.get("video_artifact_hash")
            or result_payload.get("final_mp4_sha256")
            or ""
        ).strip().lower()

        if persisted_sha:
            if not _is_64_hex(persisted_sha):
                return None, "project_artifact_sha_invalid"
            if persisted_sha != physical_sha:
                return None, "artifact_replacement_detected"

    artifact_sha = physical_sha
    asset_id = _generate_asset_id(SourceProduct.VIDEO_PRODUCT.value, str(jid), artifact_sha)

    # Storage ref: use genuine remote file ID if proven, else empty (no fabricated ref://)
    remote_file_id = str(project.get("final_video_file_id") or result_payload.get("output_file_id") or "").strip()
    storage_ref = f"telegram_file_id:{remote_file_id}" if remote_file_id else ""

    caption = str(result_payload.get("caption") or project.get("topic") or "").strip()
    completed_at = str(
        job.get("completed_at")
        or project.get("video_delivered_at")
        or project.get("updated_at")
        or _now_iso()
    )

    asset = PublishableAsset(
        asset_id=asset_id,
        owner_id=owner_id,
        source_product=SourceProduct.VIDEO_PRODUCT.value,
        source_job_id=str(jid),
        source_asset_id=remote_file_id or asset_id,
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
    """Canonical resolver for Video Edit completed output.

    Enforces video edit invariants:
    - Reads from video_editengine1 canonical source
    - Requires canonical terminal state: status in ('delivered', 'charged')
    - Requires receipt_state == 'created' and delivered_at present
    - Rejects queued, processing, failed, and arbitrary non-terminal states (e.g. 'completed', 'success')
    - Resolves only canonical output_path and output_sha256 (never source_video_path or worker temp)
    - Strict owner verification
    - SHA256 physical binding check
    """
    try:
        jid = int(job_id)
    except (TypeError, ValueError):
        return None, "invalid_job_id"

    # Use video_editengine1 schema and lookup
    video_editengine1.ensure_schema(conn)
    row = conn.execute(
        """SELECT id,user_id,status,receipt_state,delivered_at,output_path,
                  output_sha256,output_file_id,delivery_file_id,tail_json,
                  finished_at,updated_at
           FROM video_edit_jobs WHERE id=? OR local_worker_job_id=?""",
        (jid, jid),
    ).fetchone()

    if not row:
        return None, "job_not_found"

    fields = (
        "id", "user_id", "status", "receipt_state", "delivered_at", "output_path",
        "output_sha256", "output_file_id", "delivery_file_id", "tail_json",
        "finished_at", "updated_at",
    )
    job = dict(zip(fields, row))

    # 1. Owner Binding
    owner_id = int(job.get("user_id") or 0)
    if owner_id != int(requesting_user_id):
        return None, "owner_mismatch"

    # 2. Terminal State Check
    status = str(job.get("status") or "").strip().lower()
    if status == "queued":
        return None, "job_queued"
    if status in {"processing", "running", "rendering"}:
        return None, "job_processing"
    if status in {"failed", "failed_no_charge", "delivery_unknown", "cancelled", "error"}:
        return None, "job_failed"
    if status not in {"delivered", "charged"}:
        return None, f"video_edit_not_in_terminal_delivered_state:{status}"

    receipt_state = str(job.get("receipt_state") or "").strip().lower()
    if receipt_state != "created":
        return None, f"video_edit_receipt_state_invalid:{receipt_state}"

    if not job.get("delivered_at"):
        return None, "video_edit_not_delivered"

    # 3. Canonical Output Path Only (Never source input video or worker temp)
    output_path = str(job.get("output_path") or "").strip()
    if not output_path:
        return None, "missing_final_artifact_path"

    # 4. Media Integrity Probe
    valid, probe, reason = _validate_final_mp4(output_path)
    if not valid:
        return None, reason

    # 5. SHA Binding & Replacement Safety
    recorded_sha = str(job.get("output_sha256") or "").strip().lower()
    if not _is_64_hex(recorded_sha):
        return None, "video_edit_output_sha_invalid"

    physical_sha = _compute_sha256(output_path)
    if physical_sha != recorded_sha:
        return None, "artifact_replacement_detected"

    artifact_sha = physical_sha
    actual_job_id = str(job.get("id") or jid)
    asset_id = _generate_asset_id(SourceProduct.VIDEO_EDIT.value, actual_job_id, artifact_sha)

    # Storage ref: genuine remote file ID if present, else empty (no fabricated ref://)
    remote_file_id = str(job.get("output_file_id") or job.get("delivery_file_id") or "").strip()
    storage_ref = f"telegram_file_id:{remote_file_id}" if remote_file_id else ""

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
        source_job_id=actual_job_id,
        source_asset_id=remote_file_id or asset_id,
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
) -> tuple[Optional[PublishableAsset], str]:
    """Guarded adapter for SubDub.

    Current canonical SubDub runtime stores ephemeral job receipts in bot memory
    and lacks a durable SQLite service-layer storage table.
    Fails closed deterministically to prevent false authority claims.
    """
    return None, "subdub_canonical_authority_unavailable"


def adapt_existing_video_output(
    conn: Optional[sqlite3.Connection],
    asset_record: Any,
    requesting_user_id: int,
    *,
    parent_asset_id: Optional[str] = None,
) -> tuple[Optional[PublishableAsset], str]:
    """Guarded adapter for Existing Finished Video.

    No durable canonical media vault table exists in the current system.
    Arbitrary dictionaries cannot establish authority.
    Fails closed deterministically.
    """
    return None, "existing_video_canonical_authority_unavailable"


# =========================================================================
# AutoPost Handoff Service & Receiver Boundary
# =========================================================================

def create_autopost_handoff_from_source(
    conn: sqlite3.Connection,
    source_product: str | SourceProduct,
    source_ref: Any,
    requesting_user_id: int,
    *,
    purpose: str = "autopost",
    parent_asset_id: Optional[str] = None,
) -> tuple[Optional[HandoffReceipt], str]:
    """Authoritative public handoff entrypoint.

    Workflow:
    1. Validate purpose against allowlist ('autopost')
    2. Validate parent lineage ownership (strictly owner-scoped)
    3. Resolve canonical source producer truth
    4. Verify owner binding and terminal completion state
    5. Resolve canonical artifact path & expected hash
    6. Verify physical probe & hash
    7. Persist idempotent handoff receipt via private persistence helper
    """
    ensure_autopost_handoff_schema(conn)

    # 1. Purpose allowlist check
    norm_purpose = str(purpose or "").strip().lower()
    if norm_purpose not in SUPPORTED_PURPOSES:
        return None, "unsupported_purpose"

    # 2. Lineage Owner Binding Check
    norm_parent_id = str(parent_asset_id or "").strip() if parent_asset_id else None
    if norm_parent_id:
        cur = conn.cursor()
        cur.execute(
            """SELECT owner_id, lineage_json FROM autopost_handoff_receipts
               WHERE asset_id=? OR handoff_id=? LIMIT 1""",
            (norm_parent_id, norm_parent_id),
        )
        parent_row = cur.fetchone()
        if not parent_row:
            return None, "parent_asset_not_found"
        parent_owner_id = int(parent_row[0])
        if parent_owner_id != int(requesting_user_id):
            return None, "cross_owner_lineage_forbidden"

    # 3. Re-resolve producer canonical state
    product_str = str(getattr(source_product, "value", source_product)).strip().lower()
    if product_str == SourceProduct.VIDEO_PRODUCT.value:
        asset, err = adapt_product_video_output(
            conn,
            job_id=source_ref,
            requesting_user_id=requesting_user_id,
            parent_asset_id=norm_parent_id,
        )
    elif product_str == SourceProduct.VIDEO_EDIT.value:
        asset, err = adapt_video_edit_output(
            conn,
            job_id=source_ref,
            requesting_user_id=requesting_user_id,
            parent_asset_id=norm_parent_id,
        )
    elif product_str == SourceProduct.SUBDUB.value:
        asset, err = adapt_subdub_output(
            conn,
            job_id=str(source_ref),
            requesting_user_id=requesting_user_id,
            parent_asset_id=norm_parent_id,
        )
    elif product_str == SourceProduct.EXISTING_VIDEO.value:
        asset, err = adapt_existing_video_output(
            conn,
            asset_record=source_ref,
            requesting_user_id=requesting_user_id,
            parent_asset_id=norm_parent_id,
        )
    else:
        return None, f"unsupported_source_product:{product_str}"

    if not asset:
        return None, err

    # 4. Delegate to private persistence helper
    return _persist_canonical_autopost_handoff(
        conn,
        asset,
        requesting_user_id=requesting_user_id,
        purpose=norm_purpose,
    )


def _persist_canonical_autopost_handoff(
    conn: sqlite3.Connection,
    asset: PublishableAsset,
    requesting_user_id: int,
    purpose: str = "autopost",
) -> tuple[Optional[HandoffReceipt], str]:
    """Private persistence helper for canonical handoff receipts.

    Internal only: cannot be reached from client-derived data.
    Enforces SQLite-safe concurrent idempotency handling via IntegrityError recovery.
    """
    ensure_autopost_handoff_schema(conn)

    norm_purpose = str(purpose or "").strip().lower()
    if norm_purpose not in SUPPORTED_PURPOSES:
        return None, "unsupported_purpose"

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

    cur = conn.cursor()

    def _load_existing_receipt() -> Optional[HandoffReceipt]:
        cur.execute(
            """SELECT * FROM autopost_handoff_receipts
               WHERE owner_id=? AND asset_id=? AND artifact_sha256=? AND purpose=?
               LIMIT 1""",
            (asset.owner_id, asset.asset_id, asset.artifact_sha256, norm_purpose),
        )
        row = cur.fetchone()
        if not row:
            return None
        existing = dict(row)
        lineage = json.loads(existing.get("lineage_json") or "[]")
        return HandoffReceipt(
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

    # 4. Idempotency Check (SELECT check before insert)
    existing_receipt = _load_existing_receipt()
    if existing_receipt:
        return existing_receipt, "idempotent_existing_receipt"

    # 5. Build Owner-Scoped Lineage Chain
    lineage = [asset.asset_id]
    if asset.parent_asset_id:
        lineage.append(asset.parent_asset_id)
        cur.execute(
            """SELECT owner_id, lineage_json FROM autopost_handoff_receipts
               WHERE asset_id=? OR handoff_id=? LIMIT 1""",
            (asset.parent_asset_id, asset.parent_asset_id),
        )
        parent_row = cur.fetchone()
        if parent_row:
            p_owner = int(parent_row[0])
            if p_owner != int(asset.owner_id):
                return None, "cross_owner_lineage_forbidden"
            if parent_row[1]:
                try:
                    parent_lineage = json.loads(parent_row[1])
                    for item in parent_lineage:
                        if item not in lineage:
                            lineage.append(item)
                except Exception:
                    pass

    # 6. Create Durable Receipt (with concurrent UNIQUE conflict recovery)
    handoff_hash = hashlib.sha256(
        f"{asset.owner_id}:{asset.asset_id}:{asset.artifact_sha256}:{norm_purpose}".encode("utf-8")
    ).hexdigest()[:24]
    handoff_id = f"hnd_{handoff_hash}"
    now_ts = _now_iso()

    try:
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
                norm_purpose,
                "created",
                asset.parent_asset_id,
                json.dumps(lineage),
                json.dumps(asset.to_server_dict()),
                now_ts,
                None,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Concurrent race / replay unique conflict path: recover and return canonical receipt
        conflict_existing = _load_existing_receipt()
        if conflict_existing:
            return conflict_existing, "idempotent_existing_receipt"
        raise

    receipt = HandoffReceipt(
        handoff_id=handoff_id,
        asset_id=asset.asset_id,
        owner_id=asset.owner_id,
        source_product=asset.source_product,
        source_job_id=asset.source_job_id,
        artifact_sha256=asset.artifact_sha256,
        purpose=norm_purpose,
        status="created",
        parent_asset_id=asset.parent_asset_id,
        lineage=lineage,
        created_at=now_ts,
        expires_at=None,
    )
    return receipt, "created"


def receive_autopost_handoff_to_draft(
    conn: sqlite3.Connection,
    handoff_id: str,
    requesting_user_id: int,
) -> tuple[Optional[PublicationDraft], str]:
    """AutoPost receiver boundary: accepts a durable handoff ID and registers a publication draft.

    Contract:
    - Loads receipt strictly from database (rejects caller-forged objects)
    - Validates owner matches requesting_user_id
    - Validates status is 'created' (usable)
    - Revalidates artifact: physical SHA must match stored expected SHA
    - Creates a draft in initial status PLANNED
    - Zero platform dispatch, zero external API calls, zero billing side effects
    """
    ensure_autopost_handoff_schema(conn)

    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM autopost_handoff_receipts WHERE handoff_id=? LIMIT 1",
        (str(handoff_id or "").strip(),),
    )
    row = cur.fetchone()
    if not row:
        return None, "receipt_not_found"

    receipt = dict(row)

    # 1. Owner verification
    if int(receipt.get("owner_id") or 0) != int(requesting_user_id):
        return None, "owner_mismatch"

    # 2. Status verification
    if str(receipt.get("status") or "").strip().lower() != "created":
        return None, "receipt_not_usable"

    # 3. Artifact Revalidation between handoff and draft
    snapshot_json = receipt.get("asset_snapshot_json")
    try:
        snapshot = json.loads(snapshot_json) if snapshot_json else {}
    except Exception:
        snapshot = {}

    internal_path = str(snapshot.get("internal_artifact_path") or "").strip()
    if internal_path:
        if not os.path.isfile(internal_path):
            return None, "draft_artifact_missing"
        physical_sha = _compute_sha256(internal_path)
        expected_sha = str(receipt.get("artifact_sha256") or "").strip().lower()
        if physical_sha != expected_sha:
            return None, "draft_artifact_tampered_or_modified"

    def _load_existing_draft() -> Optional[PublicationDraft]:
        cur.execute(
            "SELECT * FROM autopost_publication_drafts WHERE handoff_id=? LIMIT 1",
            (receipt["handoff_id"],),
        )
        existing_row = cur.fetchone()
        if not existing_row:
            return None
        existing = dict(existing_row)
        return PublicationDraft(
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

    # 4. Idempotency Check for Draft
    existing_draft = _load_existing_draft()
    if existing_draft:
        return existing_draft, "idempotent_existing_draft"

    draft_hash = hashlib.sha256(f"{receipt['handoff_id']}:{receipt['owner_id']}".encode("utf-8")).hexdigest()[:24]
    draft_id = f"draft_{draft_hash}"
    now_ts = _now_iso()
    caption_draft = str(snapshot.get("caption_candidate") or "").strip()

    try:
        conn.execute(
            """INSERT INTO autopost_publication_drafts (
                draft_id, handoff_id, asset_id, owner_id, caption_draft,
                selected_channels_json, schedule_at, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                draft_id,
                receipt["handoff_id"],
                receipt["asset_id"],
                receipt["owner_id"],
                caption_draft,
                json.dumps([]),
                None,
                "PLANNED",
                now_ts,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conflict_draft = _load_existing_draft()
        if conflict_draft:
            return conflict_draft, "idempotent_existing_draft"
        raise

    draft = PublicationDraft(
        draft_id=draft_id,
        handoff_id=receipt["handoff_id"],
        asset_id=receipt["asset_id"],
        owner_id=receipt["owner_id"],
        caption_draft=caption_draft,
        selected_channels=[],
        schedule=None,
        status="PLANNED",
        created_at=now_ts,
    )
    return draft, "draft_created"
