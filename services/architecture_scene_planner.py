"""Deterministic walkthrough shot planning for Architecture Studio."""

from __future__ import annotations

import re
from typing import Any


SCENE_PATTERNS: dict[str, tuple[dict[str, str], ...]] = {
    "architecture_walkthrough": (
        {"space": "Ngoại cảnh/công trình", "start_frame": "góc tiếp cận ổn định", "camera_motion": "slow dolly-in", "visual_focus": "tổng thể công trình", "transition": "tiến tự nhiên tới lối vào"},
        {"space": "Lối vào", "start_frame": "ngay trước cửa", "camera_motion": "doorway transition", "visual_focus": "ngưỡng cửa và sảnh", "transition": "đi tiếp vào không gian chính"},
        {"space": "Phòng khách", "start_frame": "từ sảnh nhìn vào", "camera_motion": "smooth room walkthrough", "visual_focus": "bố cục và vật liệu", "transition": "đi theo trục lưu thông"},
        {"space": "Bếp/phòng ăn", "start_frame": "từ phòng khách", "camera_motion": "slow lateral glide", "visual_focus": "liên hệ bếp và bàn ăn", "transition": "chuyển qua hành lang"},
        {"space": "Phòng ngủ", "start_frame": "từ cửa phòng", "camera_motion": "static cinematic push-in", "visual_focus": "không gian nghỉ", "transition": "rời phòng theo cùng hướng"},
        {"space": "Phòng tắm", "start_frame": "từ hành lang", "camera_motion": "short controlled reveal", "visual_focus": "vật liệu và thiết bị", "transition": "quay về trục chính"},
        {"space": "Ban công/cảnh quan", "start_frame": "từ trong nhìn ra", "camera_motion": "gentle crane-up reveal", "visual_focus": "kết nối trong-ngoài", "transition": "mở sang góc kết"},
        {"space": "Toàn cảnh kết", "start_frame": "góc hero đã xác định", "camera_motion": "static cinematic push-in", "visual_focus": "giá trị nổi bật", "transition": "fade out tự nhiên"},
    ),
    "interior_design": (
        {"space": "Hiện trạng", "start_frame": "góc máy tham chiếu", "camera_motion": "static hold", "visual_focus": "hình học cần giữ", "transition": "match cut vật liệu"},
        {"space": "Vật liệu", "start_frame": "cùng góc máy", "camera_motion": "slow push-in", "visual_focus": "bảng vật liệu", "transition": "material reveal"},
        {"space": "Nội thất", "start_frame": "cùng trục nhìn", "camera_motion": "gentle lateral glide", "visual_focus": "bố trí đồ nội thất", "transition": "lighting reveal"},
        {"space": "Ánh sáng", "start_frame": "góc tổng", "camera_motion": "static cinematic push-in", "visual_focus": "ánh sáng và chiều sâu", "transition": "hero reveal"},
        {"space": "Toàn cảnh hoàn thiện", "start_frame": "góc hero", "camera_motion": "slow dolly-in", "visual_focus": "thiết kế hoàn chỉnh", "transition": "fade out"},
    ),
    "space_renovation": (
        {"space": "Hiện trạng", "start_frame": "góc tham chiếu nguyên bản", "camera_motion": "static hold", "visual_focus": "cấu trúc và vấn đề hiện tại", "transition": "before/after match cut"},
        {"space": "Chuyển đổi vật liệu", "start_frame": "cùng góc và tỷ lệ", "camera_motion": "subtle push-in", "visual_focus": "vật liệu thay đổi", "transition": "continuity cut"},
        {"space": "Bố trí mới", "start_frame": "cùng trục nhìn", "camera_motion": "slow lateral glide", "visual_focus": "nội thất và lưu thông", "transition": "lighting reveal"},
        {"space": "Ánh sáng hoàn thiện", "start_frame": "góc rộng ổn định", "camera_motion": "static cinematic push-in", "visual_focus": "chiều sâu không gian", "transition": "hero reveal"},
        {"space": "Kết quả", "start_frame": "góc hero trùng hiện trạng", "camera_motion": "slow dolly-in", "visual_focus": "before/after trung thực", "transition": "fade out"},
    ),
    "architecture_exterior": (
        {"space": "Tiếp cận từ đường", "start_frame": "street-level", "camera_motion": "slow dolly-in", "visual_focus": "tỷ lệ công trình", "transition": "facade reveal"},
        {"space": "Mặt tiền", "start_frame": "góc chính diện hai điểm tụ", "camera_motion": "gentle crane-up", "visual_focus": "hình khối và mặt đứng", "transition": "detail cut"},
        {"space": "Chi tiết vật liệu", "start_frame": "gần mặt đứng", "camera_motion": "slow lateral glide", "visual_focus": "vật liệu và khe bóng", "transition": "side view"},
        {"space": "Góc bên/cảnh quan", "start_frame": "góc chéo liên tục", "camera_motion": "gentle orbit", "visual_focus": "công trình với cảnh quan", "transition": "hero view"},
        {"space": "Toàn cảnh kết", "start_frame": "góc hero", "camera_motion": "static cinematic push-in", "visual_focus": "tổng thể ban ngày/đêm", "transition": "fade out"},
    ),
    "floorplan_visualization": (
        {"space": "Mặt bằng gốc", "start_frame": "top-down fixed", "camera_motion": "static hold", "visual_focus": "bố trí nguyên bản", "transition": "wireframe reveal"},
        {"space": "Khối 3D", "start_frame": "top-down same alignment", "camera_motion": "slow crane-down", "visual_focus": "tường và phân khu", "transition": "material reveal"},
        {"space": "Vật liệu/nội thất", "start_frame": "góc chéo từ mặt bằng", "camera_motion": "controlled orbit", "visual_focus": "không gian ưu tiên", "transition": "walkthrough entry"},
        {"space": "Không gian chính", "start_frame": "từ lối vào hợp lý", "camera_motion": "smooth short walkthrough", "visual_focus": "bố cục đúng mặt bằng", "transition": "hero view"},
        {"space": "Phối cảnh kết", "start_frame": "góc tổng", "camera_motion": "static cinematic push-in", "visual_focus": "mặt bằng và phối cảnh tương ứng", "transition": "fade out"},
    ),
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+", _clean(value))
        return int(match.group()) if match else int(default)


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [_clean(item) for item in values if _clean(item)]


def _duration_parts(total: int, count: int) -> list[int]:
    total = max(count, int(total or count * 8))
    base, remainder = divmod(total, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _requested_spaces(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("room_order") or payload.get("spaces") or []
    if isinstance(raw, str):
        raw = re.split(r"\s*(?:,|>|→|->|;| rồi | sau đó )\s*", raw)
    return [_clean(item) for item in raw if _clean(item)]


def build_architecture_scene_plan(payload: dict[str, Any]) -> dict[str, Any]:
    profile_id = _clean(payload.get("profile_id") or "architecture_walkthrough")
    total = _safe_int(payload.get("duration") or payload.get("duration_seconds"), 0)
    ratio = _clean(payload.get("aspect_ratio") or "16:9")
    requested_spaces = _requested_spaces(payload)
    templates = list(SCENE_PATTERNS.get(profile_id) or SCENE_PATTERNS["architecture_walkthrough"])
    if requested_spaces:
        templates = []
        for index, space in enumerate(requested_spaces):
            templates.append({
                "space": space,
                "start_frame": "trạng thái cuối của cảnh trước" if index else _clean(payload.get("start_point") or "điểm bắt đầu do khách chọn"),
                "camera_motion": "smooth room-to-room continuity" if index else "slow controlled dolly-in",
                "visual_focus": f"không gian {space}",
                "transition": "đi tiếp theo trục lưu thông" if index < len(requested_spaces) - 1 else "hero close",
            })
    requested_count = _safe_int(payload.get("scene_count"), 0)
    count = requested_count if requested_count > 0 else len(templates)
    count = max(1, min(20, count))
    if len(templates) < count:
        last = templates[-1]
        while len(templates) < count:
            templates.append({
                **last,
                "space": f"{last['space']} - góc bổ sung {len(templates) + 1}",
                "camera_motion": "short controlled detail move",
                "transition": "continuity cut",
            })
    templates = templates[:count]
    total = max(count, total or count * 8)
    durations = _duration_parts(total, count)
    preserve = _text_list(payload.get("preserve_requirements"))
    if not preserve:
        preserve = ["Giữ hình học, cửa/cửa sổ, vật liệu và bố cục nhất quán"]
    shots: list[dict[str, Any]] = []
    for index, (template, duration) in enumerate(zip(templates, durations), start=1):
        shots.append({
            "index": index,
            "duration_seconds": duration,
            "space": template["space"],
            "start_frame": template["start_frame"],
            "camera_motion": template["camera_motion"],
            "visual_focus": template["visual_focus"],
            "transition": template["transition"],
            "preserve_rules": list(preserve),
        })
    return {
        "total_duration_seconds": total,
        "aspect_ratio": ratio,
        "scene_count": count,
        "shots": shots,
        "duration_coverage_seconds": sum(item["duration_seconds"] for item in shots),
        "exact_duration_coverage": sum(item["duration_seconds"] for item in shots) == total,
        "camera_teleport_detected": False,
        "accuracy_note": "Độ chính xác kích thước phụ thuộc mặt bằng hoặc số đo khách cung cấp.",
        "provider_called": False,
    }
