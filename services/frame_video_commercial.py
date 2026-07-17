"""Commercial contracts for the public image-to-video flow.

This module is provider-free. It validates quotes, delivery receipts,
preflight truth, and the local worker mapping without creating jobs,
calling providers, rendering files, or mutating wallets.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services import frame_video_runtime


PUBLIC_JOB_TYPE = "frame_video_local"
WORKER_JOB_TYPE = "frame_video_render"
EXECUTION_OWNER = "local_worker"
PRICING_SOURCE = "tiered_media_pricing"

QUALITY_DETAILS = {
    "fast": {
        "label": "Nhanh",
        "technology": "FFmpeg local, H.264",
        "strength": "Tạo nhanh, file gọn, phù hợp xem trên điện thoại",
        "limit": "Ít chi tiết hơn ở chuyển động và chữ nhỏ",
        "eta": "Nhanh nhất trong ba gói local",
    },
    "balanced": {
        "label": "Cân bằng",
        "technology": "FFmpeg local, H.264 chất lượng cân bằng",
        "strength": "Cân bằng độ nét, tốc độ và dung lượng",
        "limit": "Không tạo chuyển động AI mới từ ảnh",
        "eta": "Thời gian xử lý trung bình",
    },
    "beautiful": {
        "label": "Đẹp",
        "technology": "FFmpeg local, H.264 ưu tiên chi tiết",
        "strength": "Giữ chữ, cạnh và chi tiết ảnh tốt hơn",
        "limit": "Render lâu hơn và file lớn hơn",
        "eta": "Lâu hơn gói Cân bằng",
    },
}


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def image_quote(
    tier_payload: dict[str, Any] | None,
    *,
    count: int,
    ratio: str,
    prompt: str,
    minimum_count: int = 2,
) -> dict[str, Any]:
    tier = dict(tier_payload or {})
    minimum = max(1, min(_safe_int(minimum_count, 2), frame_video_runtime.FRAME_VIDEO_MAX_IMAGES))
    image_count = max(minimum, min(_safe_int(count, minimum), frame_video_runtime.FRAME_VIDEO_MAX_IMAGES))
    unit_price = max(0, _safe_int(tier.get("cost"), 0))
    model = str(tier.get("model") or "").strip()
    enabled = bool(tier.get("enabled"))
    blockers: list[str] = []
    if not enabled:
        blockers.append("image_tier_disabled")
    if not model:
        blockers.append("image_model_unavailable")
    if unit_price <= 0:
        blockers.append("image_pricing_unavailable")
    if not str(prompt or "").strip():
        blockers.append("image_prompt_missing")
    return {
        "ok": not blockers,
        "blocker": blockers[0] if blockers else "",
        "blockers": blockers,
        "pricing_source": PRICING_SOURCE,
        "tier": str(tier.get("tier") or ""),
        "label": str(tier.get("label") or ""),
        "model": model,
        "image_count": image_count,
        "unit_price_xu": unit_price,
        "addon_xu": 0,
        "total_price_xu": unit_price * image_count,
        "ratio": str(ratio or "9:16").replace("x", ":"),
        "quality": str(tier.get("note") or ""),
        "retry_warranty_count": max(0, _safe_int(tier.get("retry_warranty_count"), 0)),
        "side_effects": {
            "jobs": 0,
            "provider_calls": 0,
            "generated_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        },
    }


def record_image_receipt(
    state: dict[str, Any] | None,
    *,
    image_job_id: int,
    model: str,
    prompt: str,
    ratio: str,
    artifact: str,
    message_id: int,
    charged_xu: int,
    timestamp: str,
) -> dict[str, Any]:
    if int(image_job_id or 0) <= 0:
        raise ValueError("image_job_id_required")
    if int(message_id or 0) <= 0:
        raise ValueError("image_delivery_message_id_required")
    if not str(artifact or "").strip():
        raise ValueError("image_artifact_required")
    clean = deepcopy(state or {})
    receipts = list(clean.get("generated_image_receipts") or [])
    receipt_key = f"{int(image_job_id)}:{int(message_id)}"
    existing = next((row for row in receipts if str(row.get("receipt_key") or "") == receipt_key), None)
    if existing:
        return clean
    if any(int(row.get("message_id") or 0) == int(message_id) for row in receipts):
        raise ValueError("duplicate_image_delivery_message_id")
    receipts.append(
        {
            "receipt_key": receipt_key,
            "image_job_id": int(image_job_id),
            "model": str(model or ""),
            "prompt": str(prompt or ""),
            "ratio": str(ratio or ""),
            "artifact": str(artifact or ""),
            "message_id": int(message_id),
            "xu_charged": max(0, int(charged_xu or 0)),
            "charge_recorded": bool(int(charged_xu or 0) > 0),
            "timestamp": str(timestamp or ""),
        }
    )
    clean["generated_image_receipts"] = receipts
    return clean


def apply_image_batch_charge(
    state: dict[str, Any] | None,
    *,
    charged_xu: int,
) -> dict[str, Any]:
    clean = deepcopy(state or {})
    if clean.get("image_batch_charge_recorded"):
        return clean
    receipts = list(clean.get("generated_image_receipts") or [])
    if not receipts:
        raise ValueError("image_delivery_receipts_required")
    total = max(0, int(charged_xu or 0))
    unit = total // len(receipts) if receipts else 0
    remainder = total - (unit * len(receipts))
    for index, receipt in enumerate(receipts):
        receipt["xu_charged"] = unit + (remainder if index == 0 else 0)
        receipt["charge_recorded"] = True
    clean["generated_image_receipts"] = receipts
    clean["image_batch_charge_recorded"] = True
    clean["image_generation_charged_amount"] = total
    clean["image_generation_paid"] = True
    return clean


def apply_single_image_charge(
    state: dict[str, Any] | None,
    *,
    image_job_id: int,
    message_id: int,
    charged_xu: int,
) -> dict[str, Any]:
    """Record one delivered image charge without reopening the original batch."""

    clean = deepcopy(state or {})
    receipt_key = f"{int(image_job_id or 0)}:{int(message_id or 0)}"
    receipts = list(clean.get("generated_image_receipts") or [])
    target = next((row for row in receipts if str(row.get("receipt_key") or "") == receipt_key), None)
    if not target:
        raise ValueError("image_delivery_receipt_missing")
    if target.get("charge_recorded"):
        return clean
    target["xu_charged"] = max(0, int(charged_xu or 0))
    target["charge_recorded"] = True
    clean["generated_image_receipts"] = receipts
    clean["image_generation_charged_amount"] = sum(
        max(0, _safe_int(row.get("xu_charged"), 0)) for row in receipts
    )
    clean["image_generation_paid"] = bool(receipts) and all(bool(row.get("charge_recorded")) for row in receipts)
    clean["image_regeneration_charge_count"] = max(
        0,
        _safe_int(clean.get("image_regeneration_charge_count"), 0),
    ) + 1
    return clean


def video_quote(
    state: dict[str, Any] | None,
    price_breakdown: dict[str, Any] | None,
) -> dict[str, Any]:
    clean = deepcopy(state or {})
    breakdown = deepcopy(price_breakdown or {})
    quality = str(clean.get("quality") or "balanced")
    if quality not in QUALITY_DETAILS:
        quality = "balanced"
    quality_detail = dict(QUALITY_DETAILS[quality])
    total = max(0, _safe_int(breakdown.get("total"), 0))
    blockers: list[str] = []
    if total <= 0:
        blockers.append("video_pricing_unavailable")
    return {
        "ok": not blockers,
        "blocker": blockers[0] if blockers else "",
        "blockers": blockers,
        "pricing_source": PRICING_SOURCE,
        "public_job_type": PUBLIC_JOB_TYPE,
        "mapped_job_type": WORKER_JOB_TYPE,
        "execution_owner": EXECUTION_OWNER,
        "image_count": len(clean.get("photos") or []),
        "duration_seconds": frame_video_runtime.expected_duration_seconds(clean),
        "ratio": str(clean.get("ratio") or "9x16").replace("x", ":"),
        "quality": quality,
        "quality_detail": quality_detail,
        "transition": str(clean.get("transition") or "fade"),
        "motion": str(clean.get("motion") or "none"),
        "base_xu": max(0, _safe_int(breakdown.get("base"), 0)),
        "addon_xu": max(0, _safe_int(breakdown.get("addon_xu"), 0)),
        "music_xu": max(0, _safe_int(breakdown.get("music_xu"), 0)),
        "total_price_xu": total,
    }


def preflight(
    state: dict[str, Any] | None,
    *,
    ffmpeg_path: str,
    ffprobe_path: str,
    worker_connected: bool,
    output_writable: bool,
    package_available: bool,
) -> dict[str, Any]:
    clean = deepcopy(state or {})
    plan = frame_video_runtime.validate_plan(clean)
    direct_ready = bool(str(ffmpeg_path or "").strip() and str(ffprobe_path or "").strip())
    worker_ready = bool(worker_connected)
    blockers: list[str] = []
    if not plan.get("ok"):
        blockers.append(str((plan.get("errors") or ["invalid_manifest"])[0]))
    if not package_available:
        blockers.append("video_package_unavailable")
    if not direct_ready and not worker_ready:
        blockers.append("execution_owner_unavailable")
    if not str(ffmpeg_path or "").strip() and not worker_ready:
        blockers.append("ffmpeg_unavailable")
    if not str(ffprobe_path or "").strip() and not worker_ready:
        blockers.append("ffprobe_unavailable")
    if not output_writable:
        blockers.append("output_storage_not_writable")
    execution_owner = "local_ffmpeg" if direct_ready else (EXECUTION_OWNER if worker_ready else "")
    return {
        "ok": not blockers,
        "blocker": blockers[0] if blockers else "",
        "blockers": blockers,
        "public_job_type": PUBLIC_JOB_TYPE,
        "mapped_job_type": WORKER_JOB_TYPE,
        "execution_owner": execution_owner,
        "asset_manifest_count": len(plan.get("manifest") or []),
        "timeline_built": bool(plan.get("ok") and plan.get("config")),
        "ffmpeg_command_created": False,
        "output_path": "",
        "side_effects": {
            "job": 0,
            "outbox": 0,
            "invoice": 0,
            "provider_calls": 0,
            "rendered_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        },
    }


def job_debug(
    frame_job: dict[str, Any] | None,
    worker_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job = dict(frame_job or {})
    worker = dict(worker_job or {})
    config = dict(job.get("config") or {})
    return {
        "public_job_type": str(job.get("job_type") or PUBLIC_JOB_TYPE),
        "mapped_job_type": str(worker.get("job_type") or config.get("mapped_job_type") or WORKER_JOB_TYPE),
        "execution_owner": str(job.get("owner") or config.get("execution_owner") or ""),
        "claim_attempted": bool(worker),
        "claim_result": str(worker.get("status") or "not_claimed"),
        "lease_owner": str(job.get("lease_owner") or worker.get("worker_id") or ""),
        "worker_heartbeat": str(job.get("heartbeat_updated_at") or worker.get("updated_at") or ""),
        "asset_manifest_count": len(job.get("image_manifest") or []),
        "timeline_built": bool(config.get("timeline_built")),
        "render_started": bool(job.get("started_at") or str(worker.get("status") or "") in {"running", "succeeded"}),
        "ffmpeg_command_created": bool(config.get("ffmpeg_command_created")),
        "output_path": str(job.get("output_path") or ""),
        "blocker": str(job.get("blocker") or ""),
        "error_code": str(job.get("error_code") or worker.get("error_short") or ""),
    }
