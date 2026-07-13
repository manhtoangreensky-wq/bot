"""Truthful public and admin status rendering for AI Video Editing."""

from __future__ import annotations

import html
import json
from typing import Any

from services.video_ai_edit_provider import mask_task_id


STAGE_ORDER = {
    "received_video": 1,
    "inspecting_video": 2,
    "preparing_style": 3,
    "submitting_edit": 4,
    "ai_processing": 5,
    "downloading_result": 6,
    "validating_result": 7,
    "delivering_result": 8,
    "delivered": 9,
    "failed_no_charge": 10,
}

PUBLIC_STAGE_LABELS = {
    "received_video": "Đã nhận video",
    "inspecting_video": "Đang kiểm tra video",
    "preparing_style": "Đang chuẩn bị phong cách",
    "submitting_edit": "Đang gửi yêu cầu chỉnh sửa",
    "ai_processing": "Hệ thống đang xử lý video",
    "downloading_result": "Đang tải kết quả",
    "validating_result": "Đang kiểm tra video kết quả",
    "delivering_result": "Đang gửi kết quả",
    "delivered": "Hoàn tất",
    "failed_no_charge": "Chưa xử lý được, không trừ Xu",
}

TERMINAL_STAGES = frozenset({"delivered", "failed_no_charge"})
INTERNAL_PUBLIC_TERMS = (
    "shopaikey", "key4u", "provider", "api", "result_url", "artifact",
    "canonical", "terminal", "fallback", "worker", "polling",
)


def parse_progress(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    if not text.startswith("{"):
        return {}
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) and payload.get("aiedit1") else {}


def reconcile_progress(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any]:
    before = dict(previous or {})
    incoming = dict(current or {})
    old_stage = str(before.get("stage") or "received_video")
    new_stage = str(incoming.get("stage") or old_stage)
    if old_stage in TERMINAL_STAGES:
        return before
    if new_stage not in STAGE_ORDER:
        new_stage = old_stage
    if STAGE_ORDER.get(new_stage, 0) < STAGE_ORDER.get(old_stage, 0):
        new_stage = old_stage
    result = {**before, **incoming, "aiedit1": 1, "stage": new_stage}
    old_poll = max(0, int(before.get("poll_count") or 0))
    result["poll_count"] = max(old_poll, max(0, int(incoming.get("poll_count") or 0)))
    actual = incoming.get("provider_progress_percent")
    if actual is None:
        result.pop("provider_progress_percent", None)
        result["provider_progress_source"] = "unavailable"
    else:
        try:
            result["provider_progress_percent"] = max(0, min(100, int(actual)))
            result["provider_progress_source"] = "provider_actual"
        except (TypeError, ValueError):
            result.pop("provider_progress_percent", None)
            result["provider_progress_source"] = "unavailable"
    return result


def progress_json(stage: str, **fields: Any) -> str:
    payload = reconcile_progress({}, {"aiedit1": 1, "stage": stage, **fields})
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _clean_failure(reason: str) -> str:
    mapping = {
        "ai_edit_price_unconfigured": "Giá chỉnh sửa AI chưa được cấu hình. Hệ thống chưa tạo tác vụ và chưa trừ Xu.",
        "ai_edit_video_to_video_provider_unavailable": "Nguồn chỉnh sửa tạo sinh chưa sẵn sàng. Anh/chị có thể chọn phương án nâng cấp cục bộ, hệ thống chưa trừ Xu.",
        "duration_limit_action_required": "Video dài hơn giới hạn xử lý tạo sinh. Vui lòng rút ngắn video hoặc chọn nâng cấp cục bộ.",
        "provider_poll_timeout": "Hệ thống chưa nhận được video kết quả trong thời gian cho phép. Hệ thống không trừ Xu.",
        "provider_terminal_failure": "Hệ thống chưa tạo được video kết quả. Hệ thống không trừ Xu.",
        "output_validation_failed": "Video kết quả chưa đạt kiểm tra an toàn. Hệ thống không trừ Xu.",
        "delivery_failed": "Hệ thống chưa gửi được video kết quả. Hệ thống chưa trừ Xu.",
    }
    return mapping.get(str(reason or ""), "Hệ thống chưa xử lý được video này. Hệ thống không trừ Xu.")


def public_status_text(job: dict[str, Any], progress: dict[str, Any] | None = None) -> str:
    payload = reconcile_progress({}, progress or parse_progress(job.get("error_short")))
    status = str(job.get("status") or "queued").lower()
    stage = str(payload.get("stage") or "received_video")
    delivered = bool(
        status == "succeeded"
        and stage == "delivered"
        and str(job.get("output_file_id") or "").strip()
        and payload.get("validation") == "passed"
        and payload.get("delivery") == "sent"
    )
    if not delivered and stage == "delivered":
        stage = "validating_result"
    if status in {"failed", "cancelled"}:
        stage = "failed_no_charge"
    price = max(0, int(job.get("xu_cost") or payload.get("price_xu") or 0))
    lines = [
        "✨ <b>Trạng thái chỉnh sửa video AI</b>", "",
        f"• Mã xử lý: <code>#{html.escape(str(job.get('id') or '-'))}</code>",
        f"• Trạng thái: <b>{html.escape(PUBLIC_STAGE_LABELS.get(stage, 'Đang xử lý'))}</b>",
        f"• Chi phí dự kiến: <b>{price} Xu</b>" if price else "• Chi phí: <b>0 Xu</b>",
    ]
    actual_percent = payload.get("provider_progress_percent")
    if payload.get("provider_progress_source") == "provider_actual" and actual_percent is not None and not delivered:
        lines.append(f"• Tiến độ nguồn: <b>{max(0, min(99, int(actual_percent)))}%</b>")
    elif stage == "ai_processing":
        lines.append("• Nguồn xử lý chưa trả phần trăm thực; hệ thống đang chờ kết quả.")
    if delivered:
        lines.extend(["", "✅ Video MP4 hợp lệ đã được gửi vào cuộc trò chuyện."])
    elif stage == "failed_no_charge":
        lines.extend(["", _clean_failure(str(payload.get("reason") or ""))])
    else:
        lines.extend(["", "Hệ thống chỉ báo hoàn tất sau khi video cuối đã kiểm tra và gửi thành công."])
    text = "\n".join(lines)
    lowered = text.lower()
    if any(term in lowered for term in INTERNAL_PUBLIC_TERMS):
        for term in INTERNAL_PUBLIC_TERMS:
            text = text.replace(term, "hệ thống").replace(term.title(), "Hệ thống")
    return text


def admin_status_payload(feature: dict[str, Any], *, last_job: dict[str, Any] | None = None) -> dict[str, Any]:
    providers = []
    for item in feature.get("providers") or []:
        provider = dict(item or {})
        provider.pop("auth_header_value", None)
        providers.append({
            "provider_name": provider.get("provider_name"),
            "enabled": bool(provider.get("enabled")),
            "configured": bool(provider.get("ok")),
            "model": provider.get("model"),
            "interface": provider.get("interface"),
            "invalid_fields": list(provider.get("invalid_fields") or []),
        })
    job = dict(last_job or {})
    progress = parse_progress(job.get("error_short"))
    return {
        "public_enabled": bool(feature.get("public_enabled")),
        "local_lane_enabled": bool(feature.get("local_lane_enabled")),
        "generative_lane_enabled": bool(feature.get("generative_lane_enabled")),
        "provider_capability_available": bool(feature.get("provider_capability_available")),
        "public_maintenance_freeze": bool(feature.get("public_maintenance_freeze")),
        "hidden_submit_freeze": bool(feature.get("hidden_submit_freeze")),
        "pricing_configured": bool((feature.get("pricing") or {}).get("configured")),
        "price_xu": int((feature.get("pricing") or {}).get("price_xu") or 0),
        "providers": providers,
        "last_job_id": job.get("id"),
        "last_job_result": job.get("status"),
        "last_provider_status": progress.get("provider_status"),
        "last_failure_reason": progress.get("reason"),
    }


def job_debug_payload(job: dict[str, Any]) -> dict[str, Any]:
    raw_input = str(job.get("input_file_id") or "")
    try:
        source = json.loads(raw_input) if raw_input.startswith("{") else {}
    except (ValueError, json.JSONDecodeError):
        source = {}
    progress = parse_progress(job.get("error_short"))
    return {
        "job_id": job.get("id"),
        "status": job.get("status"),
        "profile": source.get("profile_id"),
        "intent": str(source.get("user_intent") or "")[:300],
        "source_metadata": dict(source.get("source_metadata") or {}),
        "preserve_constraints": list(source.get("preserve_constraints") or []),
        "prompt_hash": source.get("prompt_hash"),
        "provider": source.get("provider_name") or job.get("provider"),
        "model": source.get("model"),
        "interface": source.get("interface"),
        "submit_source": source.get("submit_source"),
        "task_id": mask_task_id(str(progress.get("provider_task_id") or "")),
        "poll_count": int(progress.get("poll_count") or 0),
        "result_url_present": bool(progress.get("result_url_present")),
        "validation": progress.get("validation"),
        "delivery": progress.get("delivery"),
        "charge_status": progress.get("charge_status") or ("charged" if progress.get("charge") else "not_charged"),
        "cleanup": progress.get("cleanup"),
        "failure_reason": progress.get("reason"),
    }


__all__ = [
    "PUBLIC_STAGE_LABELS", "STAGE_ORDER", "admin_status_payload", "job_debug_payload",
    "parse_progress", "progress_json", "public_status_text", "reconcile_progress",
]
