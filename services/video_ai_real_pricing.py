"""Verified image and per-scene video pricing for the Video AI Real pilot.

This module is deliberately side-effect free. It stores reviewed public price
evidence and calculates a conservative UI quote; it never selects a runtime
provider, calls an API, creates a job, or mutates a wallet.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any


XU_TO_VND = Decimal("100")
SALE_MULTIPLIER = Decimal("3")
PROVIDER_PRIORITY = ("shopaikey", "key4u")
SOURCE_CHECKED_ON = "2026-08-11"
CATALOG_VERSION = "2026-08-11.video.5"
IMAGE_CATALOG_VERSION = "2026-08-11.image.1"
PROVIDER_EXCHANGE_RATE_CATALOG_VERSION = "2026-08-11.fx.1"
DEFAULT_PROVIDER_USD_TO_VND = Decimal("3500")
PROVIDER_SOURCE_URLS = {
    "shopaikey": "https://shopaikey.com/models",
    "key4u": "https://key4u.vn/models",
}
PROVIDER_EXCHANGE_RATE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "provider_key": "shopaikey",
        "currency": "USD",
        "quote_currency": "VND",
        "vnd_per_usd": 3250,
        "source_reference": "ShopAIKey model catalog: 1 USD = 3,250 VND",
        "source_url": "https://shopaikey.com/models",
        "verified_at": SOURCE_CHECKED_ON,
        "verified_by": "owner_governed_catalog_review",
        "approval_status": "canonical_approved",
        "is_default": False,
        "catalog_version": PROVIDER_EXCHANGE_RATE_CATALOG_VERSION,
    },
    {
        "provider_key": "key4u",
        "currency": "USD",
        "quote_currency": "VND",
        "vnd_per_usd": 3500,
        "source_reference": "Owner-verified live top-up checkout: 1 USD costs 3,500 VND",
        "source_url": "https://key4u.vn/pricing",
        "verified_at": SOURCE_CHECKED_ON,
        "verified_by": "owner_live_topup_evidence",
        "approval_status": "canonical_approved",
        "is_default": True,
        "catalog_version": PROVIDER_EXCHANGE_RATE_CATALOG_VERSION,
    },
    {
        "provider_key": "default",
        "currency": "USD",
        "quote_currency": "VND",
        "vnd_per_usd": 3500,
        "source_reference": "Owner pricing policy: unknown providers use 3,500 VND per USD",
        "source_url": "",
        "verified_at": SOURCE_CHECKED_ON,
        "verified_by": "owner_pricing_policy",
        "approval_status": "canonical_approved",
        "is_default": True,
        "catalog_version": PROVIDER_EXCHANGE_RATE_CATALOG_VERSION,
    },
)
VIDEO_PROVIDER_USD_TO_VND = {
    row["provider_key"]: Decimal(str(row["vnd_per_usd"]))
    for row in PROVIDER_EXCHANGE_RATE_ROWS
    if row["provider_key"] != "default"
}
VIDEO_PROVIDER_ADAPTER_KEYS = {
    "shopaikey": "shopaikey_video",
    "key4u": "key4u_video",
}

# Image and Music have separate owners. Preserve their pre-existing conversion
# inputs in this branch; their canonical task will replace them independently.
PROVIDER_USD_TO_VND = {
    "shopaikey": Decimal("3250"),
    "key4u": Decimal("3000"),
}


def provider_exchange_rate_catalog() -> list[dict[str, Any]]:
    return deepcopy(list(PROVIDER_EXCHANGE_RATE_ROWS))


def provider_usd_to_vnd(provider: str = "") -> Decimal:
    return VIDEO_PROVIDER_USD_TO_VND.get(
        str(provider or "").strip().lower(),
        DEFAULT_PROVIDER_USD_TO_VND,
    )


_MODEL_ROWS: tuple[dict[str, Any], ...] = (
    {
        "key": "social_fast_5",
        "label": "Nhanh gọn",
        "public_icon": "⚡",
        "public_level": "Cơ bản 720p",
        "seconds": 5,
        "quality": "Nhanh gọn, chuyển động rõ",
        "resolution": "720p",
        "description": "Tạo nhanh một hành động ngắn, bố cục dễ nhìn và chuyển động vừa phải.",
        "use_case": "Video thử ý tưởng, bài đăng ngắn, cảnh mở đầu hoặc sản phẩm chuyển động đơn giản.",
        "capability_key": "text_or_image_video_basic",
        "providers": {
            "shopaikey": {
                "model": "grok-video-3",
                "request_metadata": {"duration": 5, "resolution": "720P"},
                "usd_per_scene": "0.400",
                "pricing_basis": "mỗi lần tạo 5 giây",
                "source_reference": "ShopAIKey model catalog: grok-video-3",
            },
            "key4u": {
                "model": "pixverse-video",
                "request_metadata": {"duration": 5, "resolution": "720p"},
                "usd_per_second": "0.369",
                "pricing_basis": "0,369 USD mỗi giây; một cảnh 5 giây",
                "source_reference": "Key4U Model Hub: PixVerse V6 720p không âm thanh",
            },
        },
    },
    {
        "key": "grok3_5",
        "label": "Tiêu chuẩn có âm thanh",
        "public_icon": "🌱",
        "public_level": "Tiêu chuẩn 720p",
        "seconds": 5,
        "quality": "Tiêu chuẩn, có thể tạo âm thanh cùng cảnh",
        "resolution": "720p",
        "description": "Clip ngắn có chuyển động và âm thanh, giữ đúng một hành động trọn vẹn.",
        "use_case": "Quảng cáo ngắn, video mạng xã hội và cảnh có một câu thoại hoặc hiệu ứng âm thanh.",
        "capability_key": "text_or_image_video_with_audio",
        "providers": {
            "shopaikey": {
                "model": "grok-video-3",
                "catalog_model": "grok-video-3",
                "request_metadata": {"duration": 5, "resolution": "720P"},
                "usd_per_scene": "0.400",
                "pricing_basis": "mỗi lần tạo 5 giây",
                "source_reference": "ShopAIKey model catalog: grok-video-3",
            },
            "key4u": {
                "model": "grok-imagine-video",
                "request_metadata": {"duration": 5, "resolution": "720p"},
                "usd_per_second": "0.420",
                "pricing_basis": "0,420 USD mỗi giây; một cảnh 5 giây",
                "source_reference": "Key4U Model Hub: Grok Imagine Video 720p output",
            },
        },
    },
    {
        "key": "veo31_fast_8",
        "label": "Cân bằng rõ nét",
        "public_icon": "✨",
        "public_level": "Cân bằng 720p đến 1080p",
        "seconds": 8,
        "quality": "Hình ảnh ổn định, âm thanh đồng bộ",
        "resolution": "720p/1080p theo provider",
        "description": "Hình ảnh ổn định, chuyển động mượt và âm thanh đồng bộ; cân bằng tốt giữa tốc độ và chất lượng.",
        "use_case": "Video bán hàng, giới thiệu dịch vụ, nội dung có lời thoại và cảnh cần rõ chủ thể.",
        "capability_key": "text_or_image_video_balanced_audio",
        "providers": {
            "shopaikey": {
                "model": "veo3.1-fast",
                "request_metadata": {"duration": 8},
                "usd_per_scene": "0.700",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "ShopAIKey model catalog: veo3.1-fast",
            },
            "key4u": {
                "model": "veo_3_1-fast",
                "request_metadata": {"duration": 8},
                "usd_per_scene": "0.576",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "Key4U Model Hub: veo_3_1-fast",
            },
        },
    },
    {
        "key": "motion_standard_5",
        "label": "Chuyển động ổn định",
        "public_icon": "🎥",
        "public_level": "Chuyển động nâng cao",
        "seconds": 5,
        "quality": "Ưu tiên chuyển động người và máy quay",
        "resolution": "720p/1080p theo chế độ",
        "description": "Kiểm soát chuyển động nhân vật và máy quay tốt hơn, phù hợp cảnh có hành động rõ.",
        "use_case": "Nhân vật thao tác sản phẩm, đi lại, biểu diễn hoặc cảnh cần chuyển động camera ổn định.",
        "capability_key": "controlled_motion_video",
        "providers": {
            "shopaikey": {
                "model": "veo3.1-fast",
                "request_metadata": {"duration": 5, "sound": False},
                "usd_per_scene": "0.700",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "ShopAIKey model catalog: veo3.1-fast",
            },
            "key4u": {
                "model": "kling-video",
                "request_metadata": {"model_name": "kling-v3", "mode": "std", "duration": 5, "sound": False},
                "usd_per_scene": "1.020",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "Key4U kling-video detail: Kling-2, v3 std, no audio",
            },
        },
    },
    {
        "key": "motion_audio_5",
        "label": "Chuyển động có âm thanh",
        "public_icon": "🔊",
        "public_level": "Nâng cao có âm thanh",
        "seconds": 5,
        "quality": "Chuyển động ổn định và âm thanh cùng cảnh",
        "resolution": "720p/1080p theo chế độ",
        "description": "Giữ chuyển động rõ, đồng thời tạo âm thanh phù hợp với hành động trong cảnh.",
        "use_case": "Cảnh hành động có tiếng động, lời thoại ngắn hoặc nội dung cần âm thanh ăn khớp hình ảnh.",
        "capability_key": "controlled_motion_video_with_audio",
        "providers": {
            "shopaikey": {
                "model": "veo3.1-fast",
                "request_metadata": {"duration": 5, "sound": True},
                "usd_per_scene": "0.700",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "ShopAIKey model catalog: veo3.1-fast",
            },
            "key4u": {
                "model": "kling-video",
                "request_metadata": {"model_name": "kling-v3", "mode": "std", "duration": 5, "sound": True},
                "usd_per_scene": "1.530",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "Key4U kling-video detail: Kling-2, v3 std, audio",
            },
        },
    },
    {
        "key": "kling_long_audio_15",
        "label": "Cảnh dài có âm thanh",
        "public_icon": "⏱️",
        "public_level": "Nâng cao 15 giây",
        "seconds": 15,
        "quality": "Cảnh dài, chuyển động rõ và có âm thanh",
        "resolution": "1080p theo chế độ",
        "description": "Giữ một hành động dài hoặc lời thoại trọn vẹn trong một cảnh 15 giây.",
        "use_case": "Quảng cáo một cảnh dài, trình diễn sản phẩm, hội thoại hoặc hành động cần thêm thời gian.",
        "capability_key": "long_motion_video_with_audio",
        "providers": {
            "key4u": {
                "model": "kling-video",
                "request_metadata": {
                    "model_name": "kling-v3",
                    "mode": "pro",
                    "duration": 15,
                    "sound": True,
                },
                "usd_per_scene": "2.040",
                "pricing_basis": "mỗi lần tạo 3 đến 15 giây",
                "source_reference": "Key4U kling-video detail: Kling v3 pro có âm thanh",
            },
        },
    },
    {
        "key": "motion_pro_audio_10",
        "label": "Cao cấp linh hoạt",
        "public_icon": "🏆",
        "public_level": "Cao cấp 3 đến 15 giây",
        "seconds": 10,
        "quality": "Chuyển động phức tạp, có âm thanh",
        "resolution": "1080p theo chế độ",
        "description": "Cảnh dài hơn, ưu tiên độ ổn định của chủ thể, chuyển động và âm thanh.",
        "use_case": "Cảnh quảng cáo cao cấp, hành động nhiều nhịp hoặc lời thoại dài hơn trong một cảnh.",
        "capability_key": "pro_motion_video_with_audio",
        "providers": {
            "shopaikey": {
                "model": "veo3.1-pro",
                "request_metadata": {"duration": 8},
                "usd_per_scene": "3.500",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "ShopAIKey model catalog: veo3.1-pro",
            },
            "key4u": {
                "model": "kling-video",
                "request_metadata": {"model_name": "kling-v3", "mode": "pro", "duration": 10, "sound": True},
                "usd_per_scene": "2.040",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "Key4U kling-video detail: Kling-2, v3 pro, audio",
            },
        },
    },
    {
        "key": "human_performance_6",
        "label": "Diễn xuất chân thật",
        "public_icon": "🎭",
        "public_level": "Diễn xuất 768p đến 1080p",
        "seconds": 6,
        "quality": "Ưu tiên biểu cảm và chuyển động cơ thể",
        "resolution": "768p/1080p",
        "description": "Tập trung biểu cảm khuôn mặt, chuyển động cơ thể và độ chân thật của nhân vật.",
        "use_case": "Video người thật, UGC, thời trang, diễn xuất và cảnh cận mặt cần biểu cảm tự nhiên.",
        "capability_key": "human_performance_video",
        "providers": {
            "shopaikey": {
                "model": "veo3.1-pro",
                "request_metadata": {"duration": 8},
                "usd_per_scene": "3.500",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "ShopAIKey model catalog: veo3.1-pro",
            },
            "key4u": {
                "model": "MiniMax-Hailuo-2.3",
                "request_metadata": {"duration": 6, "resolution": "768P"},
                "usd_per_scene": "3.200",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "Key4U Model Hub: MiniMax Hailuo 2.3, 768p/6 giây",
            },
        },
    },
    {
        "key": "multi_angle_reference_8",
        "label": "Đa góc máy",
        "public_icon": "🎬",
        "public_level": "Cao cấp 1080p đa góc máy",
        "seconds": 8,
        "quality": "Nhất quán tham chiếu và nhiều góc máy",
        "resolution": "1080p",
        "description": "Ưu tiên tính nhất quán của nhân vật, sản phẩm và góc máy khi dùng ảnh tham chiếu.",
        "use_case": "Quảng cáo sản phẩm, nhân vật nhiều góc, chuyển cảnh có kiểm soát và storyboard tham chiếu.",
        "capability_key": "multi_angle_reference_video",
        "providers": {
            "shopaikey": {
                "model": "veo3.1-pro-components",
                "request_metadata": {"duration": 8},
                "usd_per_scene": "3.500",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "ShopAIKey model catalog: veo3.1-pro-components",
            },
            "key4u": {
                "model": "viduq3-mix",
                "request_metadata": {"duration": 8, "resolution": "1080p"},
                "usd_per_second": "1.500",
                "pricing_basis": "1,500 USD mỗi giây; một cảnh 8 giây",
                "source_reference": "Key4U Model Hub: Vidu Q3 Mix 1080p, hỗ trợ 1 đến 16 giây",
            },
        },
    },
    {
        "key": "cinematic_multishot_10",
        "label": "Điện ảnh nhiều cảnh",
        "public_icon": "👑",
        "public_level": "Điện ảnh 1080p",
        "seconds": 10,
        "quality": "Kể chuyện nhiều góc quay trong một cảnh",
        "resolution": "1080p",
        "description": "Ưu tiên bám sát câu lệnh, chuyển động mượt và mạch kể điện ảnh nhiều góc quay.",
        "use_case": "Phim ngắn, quảng cáo điện ảnh, cảnh nhiều chủ thể và tình tiết cần chuyển góc liền mạch.",
        "capability_key": "cinematic_multishot_video",
        "providers": {
            "shopaikey": {
                "model": "veo3.1-pro",
                "request_metadata": {"duration": 8},
                "usd_per_scene": "3.500",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "ShopAIKey model catalog: veo3.1-pro",
            },
            "key4u": {
                "model": "doubao-seedance-1-0-pro-250528",
                "request_metadata": {"duration": 10, "resolution": "1080p"},
                "usd_per_scene": "22.500",
                "pricing_basis": "mỗi lần tạo",
                "source_reference": "Key4U Model Hub: Seedance 1.0 Pro, Doubao-2 group; ByteDance official multi-shot 1080p",
            },
        },
    },
)


QUALITY_TIER_MODEL_KEYS: dict[int, str] = {
    200: "social_fast_5",
    300: "grok3_5",
    400: "veo31_fast_8",
    500: "motion_standard_5",
    600: "motion_audio_5",
    700: "kling_long_audio_15",
    800: "motion_pro_audio_10",
    1000: "human_performance_6",
    1200: "multi_angle_reference_8",
    1500: "cinematic_multishot_10",
}

VIDEO_RUNTIME_FALLBACK_MODEL_KEYS = frozenset({
    "social_fast_5",
    "grok3_5",
    "veo31_fast_8",
    "motion_standard_5",
    "motion_audio_5",
    "motion_pro_audio_10",
    "multi_angle_reference_8",
})


_IMAGE_MODEL_ROWS: tuple[dict[str, Any], ...] = (
    {
        "key": "image_fast_clear",
        "label": "Nhanh gọn",
        "public_icon": "⚡",
        "public_level": "Cơ bản rõ nét",
        "quality": "Tạo nhanh, bố cục rõ và bám sát nội dung chính",
        "resolution": "Độ phân giải cao",
        "description": "Tạo nhanh ảnh rõ chủ thể, phù hợp thử ý tưởng và nội dung cần số lượng đều.",
        "use_case": "Bản nháp, ảnh bài đăng, minh họa nội dung và thử nhiều hướng hình ảnh.",
        "capability_key": "text_to_image_fast",
        "providers": {
            "shopaikey": {
                "adapter_key": "openai_image_generation",
                "model": "doubao-seedream-3-0-t2i-250415",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.1000",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "ShopAIKey Models: doubao-seedream-3-0-t2i-250415, $0.1000/lần",
            },
            "key4u": {
                "adapter_key": "openai_image_generation",
                "model": "doubao-seedream-3-0-t2i-250415",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.1000",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "Key4U Model Hub: doubao-seedream-3-0-t2i-250415, $0.100/lần",
            },
        },
    },
    {
        "key": "image_balanced",
        "label": "Cân bằng",
        "public_icon": "✨",
        "public_level": "Tiêu chuẩn linh hoạt",
        "quality": "Nhanh, ổn định và dễ chỉnh theo câu lệnh",
        "resolution": "Độ phân giải cao",
        "description": "Cân bằng tốc độ, độ chi tiết và khả năng bám nội dung cho nhu cầu sử dụng hằng ngày.",
        "use_case": "Ảnh sản phẩm cơ bản, bài đăng mạng xã hội, nhân vật và bối cảnh thông dụng.",
        "capability_key": "text_to_image_balanced",
        "providers": {
            "shopaikey": {
                "adapter_key": "openai_image_generation",
                "model": "gemini-2.5-flash-image",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.1500",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "ShopAIKey Models: gemini-2.5-flash-image, $0.1500/lần",
            },
            "key4u": {
                "adapter_key": "openai_image_generation",
                "model": "gemini-2.5-flash-image",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.1500",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "Key4U Model Hub: gemini-2.5-flash-image, $0.150/lần",
            },
        },
    },
    {
        "key": "image_photoreal",
        "label": "Chân thật",
        "public_icon": "📸",
        "public_level": "Chân thật tự nhiên",
        "quality": "Ánh sáng, chất liệu và chủ thể tự nhiên",
        "resolution": "Độ phân giải cao",
        "description": "Ưu tiên cảm giác chân thật, chi tiết tự nhiên và hình ảnh dễ dùng ngay.",
        "use_case": "Ảnh người, sản phẩm, phong cách đời thường và nội dung quảng cáo mạng xã hội.",
        "capability_key": "text_to_image_photoreal",
        "providers": {
            "shopaikey": {
                "adapter_key": "openai_image_generation",
                "model": "grok-imagine-image",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.2080",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "ShopAIKey Models: grok-imagine-image, $0.2080/lần",
            },
            "key4u": {
                "adapter_key": "openai_image_generation",
                "model": "grok-imagine-image",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.2080",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "Key4U Model Hub: grok-imagine-image, $0.208/lần",
            },
        },
    },
    {
        "key": "image_creative_detail",
        "label": "Sáng tạo chi tiết",
        "public_icon": "🎨",
        "public_level": "Chi tiết quảng cáo",
        "quality": "Chi tiết cao, chữ và bố cục sáng tạo tốt",
        "resolution": "Độ phân giải cao",
        "description": "Tăng độ hoàn thiện, chất liệu và khả năng trình bày chữ trong bố cục phức tạp.",
        "use_case": "Ảnh bán hàng, poster, key visual, bao bì và thiết kế cần nhiều chi tiết.",
        "capability_key": "text_to_image_creative_detail",
        "providers": {
            "shopaikey": {
                "adapter_key": "openai_image_generation",
                "model": "qwen-image-max",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.5000",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "ShopAIKey Models: qwen-image-max, $0.5000/lần",
            },
            "key4u": {
                "adapter_key": "openai_image_generation",
                "model": "qwen-image-max",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.5000",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "Key4U Model Hub: qwen-image-max, $0.500/lần",
            },
        },
    },
    {
        "key": "image_premium_control",
        "label": "Cao cấp",
        "public_icon": "👑",
        "public_level": "Cao cấp kiểm soát",
        "quality": "Độ chính xác và hoàn thiện cao",
        "resolution": "Độ phân giải cao",
        "description": "Ưu tiên độ chính xác, chi tiết và độ hoàn thiện cho yêu cầu hình ảnh quan trọng.",
        "use_case": "Key visual, ảnh quảng cáo cao cấp, hình chủ đạo thương hiệu và nội dung cần kiểm soát kỹ.",
        "capability_key": "text_to_image_premium_control",
        "providers": {
            "shopaikey": {
                "adapter_key": "openai_image_generation",
                "model": "grok-imagine-image-pro",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.7280",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "ShopAIKey Models: grok-imagine-image-pro, $0.7280/lần",
            },
            "key4u": {
                "adapter_key": "openai_image_generation",
                "model": "grok-imagine-image-pro",
                "currency": "USD",
                "billable_unit": "image",
                "usd_per_image": "0.7280",
                "pricing_basis": "mỗi lần tạo một ảnh",
                "source_reference": "Key4U Model Hub: grok-imagine-image-pro, $0.728/lần",
            },
        },
    },
)


IMAGE_TIER_MODEL_KEYS: dict[str, str] = {
    "low": "image_fast_clear",
    "standard": "image_balanced",
    "standard_warranty": "image_balanced",
    "common": "image_creative_detail",
    "common_warranty": "image_creative_detail",
    "high": "image_premium_control",
    "high_warranty": "image_premium_control",
}

IMAGE_TIER_RETRY_COUNTS: dict[str, int] = {
    "low": 0,
    "standard": 0,
    "standard_warranty": 1,
    "common": 0,
    "common_warranty": 1,
    "high": 0,
    "high_warranty": 1,
}


_MUSIC_MODEL_ROWS: tuple[dict[str, Any], ...] = (
    {
        "key": "suno_music",
        "label": "Nhạc AI Suno",
        "unit": "track",
        "description": "Tạo một track nhạc AI cho toàn video hoặc cho một cảnh riêng.",
        "providers": {
            "shopaikey": {
                "model": "suno_music",
                "usd_per_track": "0.800",
                "pricing_basis": "mỗi lần tạo track",
            },
            "key4u": {
                "model": "suno_music_open",
                "usd_per_track": "0.240",
                "pricing_basis": "mỗi lần tạo track",
            },
        },
    },
)


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception as exc:
        raise ValueError("video_ai_real_price_invalid") from exc


def round_sale_xu(value: Any) -> int:
    """Round to tens: a remainder below 3 goes down, 3 or more goes up."""

    amount = max(Decimal("0"), _decimal(value))
    lower_ten = (amount / Decimal("10")).to_integral_value(rounding=ROUND_FLOOR) * Decimal("10")
    rounded = lower_ten if amount - lower_ten < Decimal("3") else lower_ten + Decimal("10")
    return int(rounded)


VIDEO_MULTISCENE_DISCOUNT_BANDS: tuple[tuple[int, int, int], ...] = (
    (2, 5, 10),
    (6, 10, 15),
    (11, 20, 20),
)


def video_multiscene_discount_percent(scene_count: Any) -> int:
    """Return the public discount for one multi-scene Video order."""

    try:
        count = int(scene_count or 1)
    except (TypeError, ValueError):
        count = 1
    count = max(1, min(20, count))
    return next(
        (
            discount
            for minimum, maximum, discount in VIDEO_MULTISCENE_DISCOUNT_BANDS
            if minimum <= count <= maximum
        ),
        0,
    )


def video_multiscene_price(unit_xu: Any, scene_count: Any) -> dict[str, int]:
    """Calculate a whole-Xu Video subtotal and the owner-approved scene discount."""

    try:
        count = int(scene_count or 1)
    except (TypeError, ValueError):
        count = 1
    count = max(1, min(20, count))
    unit = max(0, int(_decimal(unit_xu).to_integral_value(rounding=ROUND_HALF_UP)))
    subtotal = unit * count
    discount_percent = video_multiscene_discount_percent(count)
    discount_xu = int(
        (Decimal(subtotal) * Decimal(discount_percent) / Decimal("100")).to_integral_value(
            rounding=ROUND_HALF_UP
        )
    )
    return {
        "scene_count": count,
        "unit_xu": unit,
        "subtotal_xu": subtotal,
        "discount_percent": discount_percent,
        "discount_xu": discount_xu,
        "total_xu": max(0, subtotal - discount_xu),
    }


def _provider_order(costs: list[dict[str, Any]]) -> list[str]:
    ordered = sorted(
        costs,
        key=lambda item: (
            int(item["cost_vnd"]),
            PROVIDER_PRIORITY.index(str(item["provider"])),
        ),
    )
    return [str(item["provider"]) for item in ordered]


def _provider_cost(row: dict[str, Any], provider: str) -> dict[str, Any]:
    raw = dict((row.get("providers") or {}).get(provider) or {})
    seconds = max(1, int(row.get("seconds") or 1))
    usd_per_scene = _decimal(raw.get("usd_per_scene"))
    if usd_per_scene <= 0:
        usd_per_scene = _decimal(raw.get("usd_per_second")) * Decimal(seconds)
    exchange = provider_usd_to_vnd(provider)
    cost_vnd = usd_per_scene * exchange
    fallback_eligible = str(row.get("key") or "") in VIDEO_RUNTIME_FALLBACK_MODEL_KEYS
    return {
        "provider_key": provider,
        "provider": provider,
        "adapter_key": VIDEO_PROVIDER_ADAPTER_KEYS[provider],
        "capability_key": str(row.get("capability_key") or "text_to_video"),
        "model_key": str(raw.get("model") or ""),
        "model": str(raw.get("model") or ""),
        "catalog_model": str(raw.get("catalog_model") or raw.get("model") or ""),
        "request_metadata": deepcopy(dict(raw.get("request_metadata") or {})),
        "currency": "USD",
        "billable_unit": "scene",
        "cost_minor": int((usd_per_scene * Decimal("1000000")).to_integral_value(rounding=ROUND_HALF_UP)),
        "cost_minor_scale": 1000000,
        "exact_cost": str(usd_per_scene),
        "usd_per_scene": float(usd_per_scene),
        "usd_to_vnd": int(exchange),
        "cost_vnd": int(cost_vnd),
        "pricing_basis": str(raw.get("pricing_basis") or ""),
        "source_reference": str(raw.get("source_reference") or ""),
        "source_url": PROVIDER_SOURCE_URLS[provider],
        "checked_on": SOURCE_CHECKED_ON,
        "verified_at": SOURCE_CHECKED_ON,
        "verified_by": "owner_governed_catalog_review",
        "approval_status": "canonical_approved",
        "fallback_eligible": fallback_eligible,
        "catalog_version": CATALOG_VERSION,
    }


def model_catalog() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in _MODEL_ROWS:
        row = deepcopy(source)
        costs = [
            _provider_cost(row, provider)
            for provider in PROVIDER_PRIORITY
            if provider in (row.get("providers") or {})
        ]
        if not costs:
            raise ValueError("video_ai_real_provider_price_missing")
        priced_by = max(
            costs,
            key=lambda item: (
                _decimal(item["exact_cost"]),
                -PROVIDER_PRIORITY.index(item["provider"]),
            ),
        )
        pricing_cost_vnd_decimal = _decimal(priced_by["exact_cost"]) * DEFAULT_PROVIDER_USD_TO_VND
        pricing_cost_vnd = int(pricing_cost_vnd_decimal)
        raw_sale_xu = pricing_cost_vnd_decimal / XU_TO_VND * SALE_MULTIPLIER
        row.update({
            "selectable": True,
            "provider_priority": _provider_order(costs),
            "provider_costs": costs,
            "pricing_provider": str(priced_by["provider"]),
            "pricing_cost_usd": str(priced_by["exact_cost"]),
            "pricing_cost_vnd": pricing_cost_vnd,
            "public_pricing_usd_to_vnd": int(DEFAULT_PROVIDER_USD_TO_VND),
            "price_multiplier": int(SALE_MULTIPLIER),
            "raw_sale_xu": float(raw_sale_xu),
            "unit_xu": round_sale_xu(raw_sale_xu),
            "source_checked_on": SOURCE_CHECKED_ON,
            "catalog_version": CATALOG_VERSION,
            "approval_status": "canonical_approved",
            "fallback_eligible": str(row.get("key") or "") in VIDEO_RUNTIME_FALLBACK_MODEL_KEYS,
        })
        result.append(row)
    return result


def model_by_key(model_key: str) -> dict[str, Any]:
    key = str(model_key or "").strip()
    model = next((row for row in model_catalog() if row["key"] == key), None)
    if not model:
        raise ValueError("video_ai_real_model_invalid")
    return model


def public_quality_catalog() -> list[dict[str, Any]]:
    """Return customer-facing quality data without provider or model details."""

    rows: list[dict[str, Any]] = []
    for tier_id, model_key in QUALITY_TIER_MODEL_KEYS.items():
        model = model_by_key(model_key)
        resolution = str(model.get("resolution") or "")
        resolution = (
            resolution
            .replace(" theo provider", "")
            .replace(" theo chế độ", "")
            .replace("/", " đến ")
        )
        rows.append({
            "tier_id": int(tier_id),
            "icon": str(model.get("public_icon") or "🎬"),
            "name": str(model.get("label") or "Chất lượng video"),
            "public_level": str(model.get("public_level") or model.get("quality") or "Chất lượng video"),
            "public_detail": str(model.get("description") or ""),
            "quality_characteristic": str(model.get("quality") or ""),
            "resolution": resolution,
            "use_case": str(model.get("use_case") or model.get("description") or "Video theo nội dung đã duyệt."),
            "seconds": max(1, int(model.get("seconds") or 1)),
            "unit_xu": max(1, int(model.get("unit_xu") or 1)),
        })
    return rows


def public_quality_by_tier(tier_id: int) -> dict[str, Any]:
    selected = int(tier_id or 0)
    quality = next(
        (row for row in public_quality_catalog() if int(row["tier_id"]) == selected),
        None,
    )
    if not quality:
        raise ValueError("video_quality_invalid")
    return deepcopy(quality)


def _image_provider_cost(row: dict[str, Any], provider: str) -> dict[str, Any]:
    raw = dict((row.get("providers") or {}).get(provider) or {})
    usd_per_image = _decimal(raw.get("usd_per_image"))
    if usd_per_image <= 0:
        raise ValueError("image_provider_price_missing")
    exchange = PROVIDER_USD_TO_VND[provider]
    cost_vnd = int((usd_per_image * exchange).to_integral_value(rounding=ROUND_HALF_UP))
    fallback_eligible = len(row.get("providers") or {}) > 1
    return {
        "provider_key": provider,
        "provider": provider,
        "adapter_key": str(raw.get("adapter_key") or "openai_image_generation"),
        "capability_key": str(row.get("capability_key") or "text_to_image"),
        "model_key": str(raw.get("model") or ""),
        "model": str(raw.get("model") or ""),
        "currency": str(raw.get("currency") or "USD"),
        "billable_unit": str(raw.get("billable_unit") or "image"),
        "cost_minor": int((usd_per_image * Decimal("1000000")).to_integral_value(rounding=ROUND_HALF_UP)),
        "cost_minor_scale": 1000000,
        "exact_cost": str(usd_per_image),
        "usd_per_image": float(usd_per_image),
        "usd_to_vnd": int(exchange),
        "cost_vnd": cost_vnd,
        "pricing_basis": str(raw.get("pricing_basis") or ""),
        "source_reference": str(raw.get("source_reference") or ""),
        "source_url": PROVIDER_SOURCE_URLS[provider],
        "checked_on": SOURCE_CHECKED_ON,
        "verified_at": SOURCE_CHECKED_ON,
        "verified_by": "owner_governed_catalog_review",
        "approval_status": "canonical_approved",
        "fallback_eligible": fallback_eligible,
        "catalog_version": IMAGE_CATALOG_VERSION,
    }


def image_model_catalog() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in _IMAGE_MODEL_ROWS:
        row = deepcopy(source)
        costs = [
            _image_provider_cost(row, provider)
            for provider in PROVIDER_PRIORITY
            if provider in (row.get("providers") or {})
        ]
        if not costs:
            raise ValueError("image_provider_price_missing")
        priced_by = max(
            costs,
            key=lambda item: (
                int(item["cost_vnd"]),
                -PROVIDER_PRIORITY.index(item["provider"]),
            ),
        )
        raw_sale_xu = Decimal(int(priced_by["cost_vnd"])) / XU_TO_VND * SALE_MULTIPLIER
        provider_order = _provider_order(costs)
        row.update({
            "selectable": True,
            "provider_priority": provider_order,
            "cost_priority": provider_order,
            "provider_costs": costs,
            "pricing_provider": str(priced_by["provider"]),
            "pricing_cost_vnd": int(priced_by["cost_vnd"]),
            "price_multiplier": int(SALE_MULTIPLIER),
            "raw_sale_xu": float(raw_sale_xu),
            "unit_xu": round_sale_xu(raw_sale_xu),
            "source_checked_on": SOURCE_CHECKED_ON,
            "catalog_version": IMAGE_CATALOG_VERSION,
            "approval_status": "canonical_approved",
            "fallback_eligible": len(costs) > 1,
        })
        result.append(row)
    return result


def image_model_by_key(model_key: str) -> dict[str, Any]:
    key = str(model_key or "").strip()
    model = next((row for row in image_model_catalog() if row["key"] == key), None)
    if not model:
        raise ValueError("video_ai_real_image_model_invalid")
    return model


def public_image_quality_catalog() -> list[dict[str, Any]]:
    """Return public image packages without exposing providers or model names."""

    models = {row["key"]: row for row in image_model_catalog()}
    rows: list[dict[str, Any]] = []
    for tier_key, model_key in IMAGE_TIER_MODEL_KEYS.items():
        model = models[model_key]
        retry_count = max(0, int(IMAGE_TIER_RETRY_COUNTS.get(tier_key, 0)))
        attempt_count = 1 + retry_count
        raw_sale_xu = (
            Decimal(int(model["pricing_cost_vnd"]))
            / XU_TO_VND
            * SALE_MULTIPLIER
            * Decimal(attempt_count)
        )
        label = str(model.get("label") or "Chất lượng ảnh")
        if retry_count:
            label = f"{label} + bảo hành"
        rows.append({
            "tier_key": tier_key,
            "icon": "🛡" if retry_count else str(model.get("public_icon") or "🖼"),
            "name": label,
            "public_level": str(model.get("public_level") or model.get("quality") or "Chất lượng ảnh"),
            "quality_characteristic": str(model.get("quality") or ""),
            "resolution": str(model.get("resolution") or ""),
            "public_detail": str(model.get("description") or ""),
            "use_case": str(model.get("use_case") or model.get("description") or "Ảnh theo nội dung đã duyệt."),
            "retry_warranty_count": retry_count,
            "attempt_count_priced": attempt_count,
            "unit_xu": round_sale_xu(raw_sale_xu),
        })
    return rows


def public_image_quality_by_tier(tier_key: str) -> dict[str, Any]:
    key = str(tier_key or "").strip().lower()
    quality = next((row for row in public_image_quality_catalog() if row["tier_key"] == key), None)
    if not quality:
        raise ValueError("image_quality_invalid")
    return deepcopy(quality)


def _music_provider_cost(row: dict[str, Any], provider: str) -> dict[str, Any]:
    raw = dict((row.get("providers") or {}).get(provider) or {})
    usd_per_track = _decimal(raw.get("usd_per_track"))
    exchange = PROVIDER_USD_TO_VND[provider]
    cost_vnd = int(usd_per_track * exchange)
    return {
        "provider": provider,
        "model": str(raw.get("model") or ""),
        "usd_per_track": float(usd_per_track),
        "usd_to_vnd": int(exchange),
        "cost_vnd": cost_vnd,
        "pricing_basis": str(raw.get("pricing_basis") or ""),
        "source_url": PROVIDER_SOURCE_URLS[provider],
        "checked_on": SOURCE_CHECKED_ON,
    }


def music_model_catalog() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in _MUSIC_MODEL_ROWS:
        row = deepcopy(source)
        costs = [_music_provider_cost(row, provider) for provider in PROVIDER_PRIORITY]
        priced_by = max(
            costs,
            key=lambda item: (
                int(item["cost_vnd"]),
                -PROVIDER_PRIORITY.index(item["provider"]),
            ),
        )
        raw_sale_xu = Decimal(int(priced_by["cost_vnd"])) / XU_TO_VND * SALE_MULTIPLIER
        row.update({
            "selectable": True,
            "provider_priority": _provider_order(costs),
            "provider_costs": costs,
            "pricing_provider": str(priced_by["provider"]),
            "pricing_cost_vnd": int(priced_by["cost_vnd"]),
            "price_multiplier": int(SALE_MULTIPLIER),
            "raw_sale_xu": float(raw_sale_xu),
            "unit_xu": round_sale_xu(raw_sale_xu),
            "source_checked_on": SOURCE_CHECKED_ON,
        })
        result.append(row)
    return result
