"""Truthful capability catalog for the public video editing planner."""

from __future__ import annotations

from copy import deepcopy
import re
import unicodedata
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
        "Bỏ một khoảng ở giữa và nối phần trước/sau thành đúng một file MP4 theo thứ tự.",
        section="manual",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Khoảng bỏ phải nằm trong đoạn đã chọn; đầu ra luôn được kiểm tra là một MP4.",
    ),
    _capability(
        "manual_split",
        "Chia đoạn",
        "Chia theo thời lượng, số phần hoặc mốc thời gian tự chọn.",
        section="manual",
        execution_owner="video_local_editing",
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
        "Chỉnh toàn bộ âm thanh gốc ở mức 20, 40, 60, 80, 100% hoặc mức tùy chọn.",
        section="audio",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Áp dụng cho toàn bộ track đã trộn.",
    ),
    _capability(
        "audio_loudnorm",
        "Cân bằng âm lượng tự động",
        "Cân bằng độ lớn của toàn bộ track âm thanh bằng bộ lọc local loudnorm.",
        section="audio",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Chỉ mở khi nguồn có audio và worker xác nhận bộ lọc loudnorm.",
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
            ("audio_dialogue", "Giọng nói / đối thoại", "Chỉnh riêng lời nói khi video có lớp giọng tách biệt."),
            ("audio_music", "Nhạc nền", "Chỉnh riêng nhạc khi video có lớp nhạc tách biệt."),
            ("audio_ambience", "Âm thanh môi trường", "Chỉnh riêng âm thanh môi trường khi video có lớp âm thanh tách biệt."),
            ("audio_sfx", "Hiệu ứng âm thanh", "Chỉnh riêng hiệu ứng khi video có lớp hiệu ứng tách biệt."),
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
    _capability(
        "enhance_denoise",
        "Giảm nhiễu và nén vỡ",
        "Giảm nhiễu và artifact do nén bằng bộ lọc local hqdn3d đã kiểm tra.",
        section="restore",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Có thể làm mất chi tiết nếu lọc quá mạnh; worker phải kiểm tra hqdn3d trước khi chạy.",
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
            ("enhance_motion_deblur", "Giảm mờ chuyển động", "Khôi phục chi tiết bị nhòe do chuyển động.", "Không mở khi chưa có engine deblur thật."),
            ("enhance_stabilize", "Chống rung", "Ổn định khung hình rung.", "Có thể phải crop viền."),
            ("enhance_frame_interpolation", "Làm mượt 30/50/60 FPS", "Nội suy khung hình theo FPS đích.", "Có nguy cơ bóng ma ở chuyển động nhanh."),
            ("enhance_old_video", "Khôi phục video cũ", "Kết hợp phục hồi nhiễu, màu và chi tiết.", "Chỉ mở khi chuỗi xử lý thật được kiểm chứng."),
            ("enhance_face_restore", "Khôi phục khuôn mặt", "Phục hồi khuôn mặt bằng mô hình chuyên dụng.", "Ẩn vì runtime hiện chưa chứng minh năng lực."),
        )
    ),
    _capability(
        "effect_fade",
        "Mờ vào / mờ ra",
        "Thêm fade-in hoặc fade-out ngắn bằng bộ lọc local, giữ một MP4 đầu ra.",
        section="effects",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Thời lượng fade được giới hạn theo thời lượng video đã kiểm tra.",
    ),
    _capability(
        "effect_vignette",
        "Viền tối nhẹ",
        "Thêm vignette nhẹ để hướng mắt về trung tâm khung hình bằng FFmpeg local.",
        section="effects",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Có thể làm tối các chi tiết ở mép; xem lại trước khi xác nhận.",
    ),
    _capability(
        "effect_slow_zoom",
        "Zoom chậm",
        "Tạo zoom rất chậm, giới hạn biên độ và tốc độ bằng bộ lọc local.",
        section="effects",
        execution_owner="video_local_editing",
        local_or_provider="local",
        enabled=True,
        cost_policy="0 Xu",
        risk_notes="Cần worker xác nhận zoompan; có thể thay đổi nhẹ cảm nhận khung hình.",
    ),
    *(
        _capability(
            key,
            name,
            description,
            section="effects",
            execution_owner="video_ai_edit_provider_guarded",
            local_or_provider="provider_after_final_confirm",
            enabled=False,
            risk_notes="Chưa phải thao tác local; chỉ hiển thị ở phần giải thích chưa sẵn sàng.",
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


# These fragments intentionally use only fields accepted by
# ``video_local_editing.normalize_manual_edit_plan``.  A capability can be
# selected from Manual, Assistant, or Quality, then merged into the same
# declarative plan without opening a provider or a commercial tail.
LOCAL_PLAN_PATCHES: dict[str, dict[str, Any]] = {
    "manual_trim_edges": {"trim": {}},
    "manual_remove_middle": {"remove_middle": {}},
    "manual_split": {"trim": {}},
    "manual_concat_reorder": {"concat_inputs": []},
    "manual_speed": {"speed": 1.0},
    "manual_rotate_flip": {"rotation": 0, "flip": "none"},
    "audio_master_volume": {"volume": 1.0},
    "audio_loudnorm": {"audio_normalization": "loudnorm"},
    "aspect_basic_crop": {"crop_or_fit": {"aspect_ratio": "keep", "mode": "crop"}},
    "aspect_keep_frame": {"crop_or_fit": {"aspect_ratio": "keep", "mode": "fit"}},
    "enhance_basic_sharpen": {"quality_filters": {"sharpen": True}},
    "enhance_light_color": {"color_preset": "bright_clear"},
    "enhance_denoise": {"quality_filters": {"denoise": True}},
    "effect_fade": {"local_effects": {"fade_in_ms": 300, "fade_out_ms": 300}},
    "effect_vignette": {"local_effects": {"vignette": True}},
    "effect_slow_zoom": {"local_effects": {"slow_zoom": True}},
}


CAPABILITY_BY_KEY = {item["feature_key"]: deepcopy(dict(item)) for item in CAPABILITIES}


def public_actionable_capabilities() -> list[dict[str, Any]]:
    """Return only capabilities that can execute in the local editor now.

    This is deliberately stricter than ``enabled`` alone.  A catalog row is
    public-actionable only when it has a local owner, is marked local, and has
    a declarative plan fragment.  Provider/planning-only rows remain available
    through ``capabilities_for(..., include_disabled=True)`` for truthful
    explanation screens, but never leak into an action keyboard.
    """
    return [
        deepcopy(item)
        for item in CAPABILITIES
        if (
            item.get("enabled") is True
            and item.get("execution_owner") == "video_local_editing"
            and item.get("local_or_provider") == "local"
            and item.get("feature_key") in LOCAL_PLAN_PATCHES
        )
    ]


def plan_patch(feature_key: str) -> dict[str, Any]:
    """Return an isolated local edit-plan fragment for ``feature_key``.

    Unknown, disabled, and provider-owned keys return an empty mapping.  The
    returned object is a deep copy so a conversational session cannot mutate
    the process-wide capability contract or another user's plan.
    """
    key = str(feature_key or "").strip()
    item = CAPABILITY_BY_KEY.get(key) or {}
    if not (
        item.get("enabled") is True
        and item.get("execution_owner") == "video_local_editing"
        and item.get("local_or_provider") == "local"
    ):
        return {}
    return deepcopy(LOCAL_PLAN_PATCHES.get(key) or {})


def _merge_plan_patch(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge nested plan fragments without erasing previous selections."""
    result = deepcopy(dict(base or {}))
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_plan_patch(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _fold_vietnamese(value: Any) -> str:
    """Normalize Vietnamese text for deterministic, accent-tolerant matching."""
    text = unicodedata.normalize("NFKD", str(value or "")).lower()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("đ", "d")
    return re.sub(r"[^a-z0-9:]+", " ", text).strip()


# Ordered by the canonical plan output, not by the order in which keywords
# happen to occur in a user's sentence.  This makes equivalent Vietnamese
# requests compile to byte-for-byte equivalent JSON-like dictionaries.
_LOCAL_INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("aspect_basic_crop", ("video doc", "tiktok", "reels", "shorts", "9:16", "9x16")),
    ("enhance_light_color", ("lam sang", "can sang", "anh sang", "mau", "color", "bright")),
    ("enhance_basic_sharpen", ("lam ro", " ro ", "ro hon", "lam net", "sac net", "sharpen", "clear")),
    ("enhance_denoise", ("giam nhieu", "khu nhieu", "nen vo", "denoise")),
    ("audio_loudnorm", ("am luong deu", "can bang am luong", "chuan hoa am luong", "loudnorm", "normalize audio")),
    ("effect_fade", ("mo vao", "mo ra", "fade")),
    ("effect_vignette", ("vien toi", "vignette")),
    ("effect_slow_zoom", ("zoom cham", "phong nhe", "slow zoom")),
)

_UNSUPPORTED_INTENT_TERMS: tuple[str, ...] = (
    "parallax",
    "phep thuat",
    "tao canh",
    "tao nen",
    "mo rong nen",
    "thay nen",
    "hat sang",
    "duong sang",
    "phuc hoi khuon mat",
    "theo doi chu the",
    "face restore",
)


def _no_side_effect_fields() -> dict[str, Any]:
    return {
        "job_created": False,
        "outbox_created": False,
        "file_generated": False,
        "provider_called": False,
        "wallet_mutated": False,
        "xu_charged": 0,
    }


def compile_local_intent(user_intent: str) -> dict[str, Any]:
    """Compile a Vietnamese request into a deterministic local edit plan.

    The compiler is pure: it only returns a plan fragment and truthful copy;
    it never queues work, calls providers, writes files, or touches Xu.  A
    request containing a known provider-only transformation fails closed even
    when it also contains local words, so no accidental partial execution is
    advertised as success.
    """
    normalized = _fold_vietnamese(user_intent)
    base = _no_side_effect_fields()
    base.update(
        {
            "input_text": str(user_intent or ""),
            "normalized_intent": normalized,
            "feature_keys": [],
            "plan_patch": {},
            "unsupported": False,
            "ok": False,
        }
    )
    if not normalized:
        base["message_vi"] = "Hãy mô tả thao tác local như làm sáng, làm rõ, giảm nhiễu hoặc video dọc TikTok; chưa tạo tác vụ và chưa trừ Xu."
        return base

    unsupported = [term for term in _UNSUPPORTED_INTENT_TERMS if term in normalized]
    if unsupported:
        base["unsupported"] = True
        base["reason"] = "local_capability_unavailable"
        base["message_vi"] = (
            "Yêu cầu này cần năng lực chưa có trong bộ chỉnh sửa local ("
            + ", ".join(unsupported)
            + "). Chưa tạo tác vụ, chưa gọi provider và chưa trừ Xu. "
            "Bạn có thể chọn làm sáng, làm rõ, giảm nhiễu, cân bằng âm lượng hoặc crop 9:16."
        )
        return base

    selected: list[str] = []
    searchable = f" {normalized} "
    for key, terms in _LOCAL_INTENT_RULES:
        if any(term in searchable for term in terms) and plan_patch(key):
            selected.append(key)
    if not selected:
        base["reason"] = "no_local_capability_match"
        base["message_vi"] = (
            "Chưa nhận ra thao tác local từ yêu cầu này. Hãy thử làm sáng, làm rõ, giảm nhiễu, "
            "cân bằng âm lượng hoặc video dọc TikTok; chưa tạo tác vụ và chưa trừ Xu."
        )
        return base

    compiled: dict[str, Any] = {}
    for key in selected:
        patch = plan_patch(key)
        # The public phrase "video dọc TikTok" carries an explicit ratio;
        # retain the generic capability patch for other callers but compile
        # this intent to the concrete local crop requested by the user.
        if key == "aspect_basic_crop" and any(
            token in searchable for token in ("tiktok", "reels", "shorts", "video doc", "9:16", "9x16")
        ):
            patch = _merge_plan_patch(
                patch,
                {"crop_or_fit": {"aspect_ratio": "9:16", "mode": "crop"}},
            )
        compiled = _merge_plan_patch(compiled, patch)
    base.update(
        {
            "ok": True,
            "feature_keys": selected,
            "plan_patch": compiled,
            # ``manual_edit_plan`` is an explicit alias for callers that pass
            # the result directly to the canonical editor state.
            "manual_edit_plan": deepcopy(compiled),
            "message_vi": (
                "Đã lập kế hoạch chỉnh sửa local: "
                + ", ".join(str(capability(key).get("public_name") or key) for key in selected)
                + ". 0 Xu; chưa tạo tác vụ cho tới khi bạn xem lại và xác nhận."
            ),
        }
    )
    return base


# Compatibility aliases make the contract easy to consume from older lane
# adapters without duplicating compiler logic.
compile_vietnamese_intent = compile_local_intent
local_intent_to_plan = compile_local_intent


def validate_capability_catalog() -> bool:
    keys = [item.get("feature_key") for item in CAPABILITIES]
    return bool(
        len(keys) == len(set(keys))
        and all(REQUIRED_CAPABILITY_FIELDS <= set(item) for item in CAPABILITIES)
    )


def capability(feature_key: str) -> dict[str, Any]:
    return deepcopy(CAPABILITY_BY_KEY.get(str(feature_key or "")) or {})


def capabilities_for(section: str, *, include_disabled: bool = False) -> list[dict[str, Any]]:
    selected = [
        deepcopy(item)
        for item in CAPABILITIES
        if item.get("section") == str(section or "")
    ]
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
            "Nguồn có các lớp âm thanh tách riêng."
            if independently_adjustable
            else "Nguồn chỉ có âm thanh đã trộn; hệ thống chỉ chỉnh âm lượng tổng."
            if has_audio
            else "Nguồn không có âm thanh."
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
