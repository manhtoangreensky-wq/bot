"""Truthful capability catalog for the public video editing planner."""

from __future__ import annotations

from typing import Any


REQUIRED_CAPABILITY_FIELDS = frozenset(
    {
        "feature_key",
        "public_name",
        "description",
        "execution_owner",
        "local_or_provider",
        "enabled",
        "input_requirements",
        "supported_formats",
        "max_duration",
        "cost_policy",
        "preview_supported",
        "risk_notes",
    }
)


def _capability(
    feature_key: str,
    public_name: str,
    description: str,
    *,
    section: str,
    execution_owner: str,
    local_or_provider: str,
    enabled: bool,
    input_requirements: str = "Một video MP4, MOV, MKV hoặc WebM hợp lệ",
    supported_formats: tuple[str, ...] = ("mp4", "mov", "mkv", "webm"),
    max_duration: int = 1800,
    cost_policy: str = "Hiển thị trước xác nhận cuối",
    preview_supported: bool = True,
    risk_notes: str = "",
) -> dict[str, Any]:
    return {
        "feature_key": feature_key,
        "public_name": public_name,
        "description": description,
        "section": section,
        "execution_owner": execution_owner,
        "local_or_provider": local_or_provider,
        "enabled": bool(enabled),
        "input_requirements": input_requirements,
        "supported_formats": list(supported_formats),
        "max_duration": int(max_duration),
        "cost_policy": cost_policy,
        "preview_supported": bool(preview_supported),
        "risk_notes": risk_notes,
    }


CAPABILITIES = (
    _capability(
        "manual_trim_edges",
        "Cắt đầu/cuối",
        "Giữ đúng một khoảng liên tục trong video nguồn.",
        section="manual",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
    ),
    _capability(
        "manual_remove_middle",
        "Bỏ đoạn giữa",
        "Tách và xuất các phần được giữ theo đúng thứ tự; không quảng cáo là một file nối lại nếu chưa ghép.",
        section="manual",
        execution_owner="video_smart_splitter",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Các phần còn lại được xuất riêng nếu chưa có bước ghép tiếp.",
    ),
    _capability(
        "manual_split",
        "Chia đoạn",
        "Chia theo thời lượng, số phần hoặc mốc thời gian tự chọn.",
        section="manual",
        execution_owner="video_smart_splitter",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
    ),
    _capability(
        "manual_concat_reorder",
        "Ghép và đổi thứ tự",
        "Ghép tối đa 10 video theo thứ tự người dùng đã duyệt.",
        section="manual",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
    ),
    _capability(
        "manual_speed",
        "Đổi tốc độ",
        "Đổi tốc độ hình và âm thanh theo cùng một hệ số được hỗ trợ.",
        section="manual",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
    ),
    _capability(
        "manual_rotate_flip",
        "Xoay / lật",
        "Xoay 90 độ hoặc lật ngang, dọc mà không gọi AI.",
        section="manual",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
    ),
    _capability(
        "audio_master_volume",
        "Âm lượng tổng",
        "Chỉnh toàn bộ track âm thanh gốc ở mức 20, 40, 60, 80, 100% hoặc mức tùy chọn.",
        section="audio",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Áp dụng cho toàn bộ track đã trộn.",
    ),
    *(
        _capability(
            key,
            name,
            description,
            section="audio",
            execution_owner="separate_audio_track_required",
            local_or_provider="local_when_separate_track_exists",
            enabled=False,
            cost_policy="Không mở khi nguồn chỉ có một track trộn",
            risk_notes="Không được tuyên bố tách stem nếu chưa có track riêng hoặc separator thật.",
        )
        for key, name, description in (
            ("audio_dialogue", "Giọng nói / đối thoại", "Chỉnh riêng lời nói khi nguồn có track giọng tách biệt."),
            ("audio_music", "Nhạc nền", "Chỉnh riêng nhạc khi nguồn có track nhạc tách biệt."),
            ("audio_ambience", "Âm thanh môi trường", "Chỉnh riêng ambience khi nguồn có track môi trường tách biệt."),
            ("audio_sfx", "Hiệu ứng âm thanh", "Chỉnh riêng SFX khi nguồn có track hiệu ứng tách biệt."),
        )
    ),
    _capability(
        "aspect_basic_crop",
        "Crop theo khung",
        "Crop hình học theo tỉ lệ đã chọn; không gọi là theo dõi chủ thể.",
        section="aspect",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Có thể cắt mất chi tiết ở mép khung; cần xem kế hoạch trước.",
    ),
    _capability(
        "aspect_keep_frame",
        "Giữ toàn cảnh có viền",
        "Giữ đủ hình nguồn và thêm vùng đệm đơn sắc khi tỉ lệ đích khác video gốc.",
        section="aspect",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Runtime hiện chỉ có vùng đệm đơn sắc; không gọi là nền mờ hoặc mở rộng nền AI.",
    ),
    *(
        _capability(
            key,
            name,
            description,
            section="aspect",
            execution_owner="capability_gated_ai_editor",
            local_or_provider="provider_after_final_confirm",
            enabled=False,
            risk_notes="Chỉ hiện công khai khi runtime xác nhận hỗ trợ thật.",
        )
        for key, name, description in (
            ("aspect_subject_tracking", "Theo dõi chủ thể", "Giữ chủ thể trong khung khi đổi tỉ lệ."),
            ("aspect_background_expand", "Mở rộng nền", "Tạo thêm vùng nền thay vì cắt chủ thể."),
            ("aspect_blur_background", "Nền mờ", "Giữ toàn bộ hình nguồn trên nền mờ phù hợp tỉ lệ."),
            ("aspect_safe_zone", "Vùng an toàn chữ/logo", "Giữ vùng trống để chữ và logo không che chủ thể."),
        )
    ),
    _capability(
        "enhance_basic_sharpen",
        "Làm rõ cơ bản",
        "Tăng nét nhẹ bằng bộ lọc local; không tạo thêm chi tiết mới như AI upscale.",
        section="restore",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Tăng quá mức có thể làm lộ nhiễu hoặc viền giả.",
    ),
    _capability(
        "enhance_light_color",
        "Cân sáng và màu",
        "Điều chỉnh sáng, tương phản và màu bằng preset local đã kiểm soát.",
        section="restore",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
    ),
    *(
        _capability(
            key,
            name,
            description,
            section="restore",
            execution_owner="capability_not_wired",
            local_or_provider="hidden_until_runtime_ready",
            enabled=False,
            risk_notes=risk,
        )
        for key, name, description, risk in (
            ("enhance_upscale", "Nâng độ phân giải", "Nâng độ phân giải có phục hồi chi tiết.", "Scale thường không được gọi là AI upscale."),
            ("enhance_denoise", "Giảm nhiễu và nén vỡ", "Giảm nhiễu và artifact do nén.", "Có thể làm mất chi tiết nếu lọc quá mạnh."),
            ("enhance_motion_deblur", "Giảm mờ chuyển động", "Khôi phục chi tiết bị nhòe do chuyển động.", "Không mở khi chưa có engine deblur thật."),
            ("enhance_stabilize", "Chống rung", "Ổn định khung hình rung.", "Có thể phải crop viền."),
            ("enhance_frame_interpolation", "Làm mượt 30/50/60 FPS", "Nội suy khung hình theo FPS đích.", "Có nguy cơ bóng ma ở chuyển động nhanh."),
            ("enhance_old_video", "Khôi phục video cũ", "Kết hợp phục hồi nhiễu, màu và chi tiết.", "Chỉ mở khi chuỗi xử lý thật được kiểm chứng."),
            ("enhance_face_restore", "Khôi phục khuôn mặt", "Phục hồi khuôn mặt bằng mô hình chuyên dụng.", "Ẩn vì runtime hiện chưa chứng minh năng lực."),
        )
    ),
    *(
        _capability(
            key,
            name,
            description,
            section="effects",
            execution_owner="video_ai_edit_provider_guarded",
            local_or_provider="provider_after_final_confirm",
            enabled=True,
            risk_notes="Chỉ là kế hoạch trước xác nhận cuối; còn phụ thuộc năng lực nguồn xử lý được duyệt.",
        )
        for key, name, description in (
            ("effect_zoom_pan", "Zoom / lia nhẹ", "Di chuyển khung hình nhẹ theo điểm nhấn."),
            ("effect_parallax", "Parallax", "Tạo cảm giác chiều sâu có kiểm soát từ khung hình phù hợp."),
            ("effect_moving_light", "Ánh sáng chuyển động", "Thêm chuyển động ánh sáng tinh tế."),
            ("effect_light_outline", "Đường sáng / viền động", "Nhấn chủ thể bằng đường sáng hoặc viền động nhẹ."),
            ("effect_particles", "Hạt sáng", "Thêm hạt sáng vừa phải, không che chủ thể."),
            ("effect_subtle_transition", "Chuyển cảnh tinh tế", "Tạo chuyển tiếp nhẹ, tránh hiệu ứng phô trương."),
        )
    ),
)


CAPABILITY_BY_KEY = {item["feature_key"]: dict(item) for item in CAPABILITIES}


def validate_capability_catalog() -> bool:
    keys = [item.get("feature_key") for item in CAPABILITIES]
    return bool(
        len(keys) == len(set(keys))
        and all(REQUIRED_CAPABILITY_FIELDS <= set(item) for item in CAPABILITIES)
    )


def capability(feature_key: str) -> dict[str, Any]:
    return dict(CAPABILITY_BY_KEY.get(str(feature_key or "")) or {})


def capabilities_for(section: str, *, include_disabled: bool = False) -> list[dict[str, Any]]:
    selected = [dict(item) for item in CAPABILITIES if item.get("section") == str(section or "")]
    if include_disabled:
        return selected
    return [item for item in selected if item.get("enabled")]


def audio_source_truth(metadata: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(metadata or {})
    has_audio = bool(data.get("has_audio"))
    stream_count = max(0, int(data.get("audio_stream_count") or (1 if has_audio else 0)))
    separate_stems = bool(data.get("separate_audio_stems") or data.get("named_audio_tracks"))
    independently_adjustable = bool(has_audio and separate_stems and stream_count > 1)
    return {
        "has_audio": has_audio,
        "audio_stream_count": stream_count,
        "separate_stems": separate_stems,
        "independently_adjustable": independently_adjustable,
        "public_summary": (
            "Nguồn có các track âm thanh tách riêng."
            if independently_adjustable
            else "Nguồn chỉ có âm thanh đã trộn; hệ thống chỉ chỉnh âm lượng tổng."
            if has_audio
            else "Nguồn không có track âm thanh."
        ),
    }


def local_upgrade_suggestions(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return rule-based suggestions only from measured source metadata."""
    data = dict(metadata or {})
    width = max(0, int(data.get("width") or 0))
    height = max(0, int(data.get("height") or 0))
    fps = max(0.0, float(data.get("fps") or 0.0))
    duration = max(0.0, float(data.get("duration") or 0.0))
    size_bytes = max(0, int(data.get("bytes") or 0))
    suggestions: list[dict[str, Any]] = []

    if width and height and min(width, height) < 720:
        suggestions.append(
            {
                "feature_key": "enhance_basic_sharpen",
                "reason": f"Video nguồn có kích thước {width}×{height}, phù hợp kiểm tra làm rõ nhẹ.",
                "risk": "Không tạo thêm chi tiết mới như AI upscale.",
                "selected": False,
                "cost_xu": 0,
            }
        )
    if fps and fps < 29.0:
        suggestions.append(
            {
                "feature_key": "enhance_frame_interpolation",
                "reason": f"FPS nguồn là {fps:.2f}; có thể cân nhắc làm mượt khi runtime hỗ trợ.",
                "risk": "Hiện chưa mở vì nội suy có thể tạo bóng ma ở chuyển động nhanh.",
                "selected": False,
                "cost_xu": 0,
            }
        )
    if duration > 0 and size_bytes > 0:
        estimated_mbps = size_bytes * 8 / duration / 1_000_000
        if estimated_mbps < 1.2:
            suggestions.append(
                {
                    "feature_key": "enhance_denoise",
                    "reason": f"Bitrate ước tính từ file là {estimated_mbps:.2f} Mbps; nên kiểm tra nén vỡ trước khi nâng cấp.",
                    "risk": "Chỉ là dấu hiệu từ dung lượng/thời lượng, không khẳng định video có nhiễu.",
                    "selected": False,
                    "cost_xu": 0,
                }
            )
    if data.get("has_audio"):
        suggestions.append(
            {
                "feature_key": "audio_master_volume",
                "reason": "Video nguồn có âm thanh; có thể chỉnh âm lượng tổng nếu cần.",
                "risk": audio_source_truth(data)["public_summary"],
                "selected": False,
                "cost_xu": 0,
            }
        )
    return suggestions[:4]


def no_side_effect_plan() -> dict[str, Any]:
    return {
        "job_created": False,
        "outbox_created": False,
        "provider_called": False,
        "file_generated": False,
        "wallet_mutated": False,
        "xu_charged": 0,
    }
