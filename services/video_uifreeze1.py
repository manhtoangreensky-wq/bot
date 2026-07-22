"""Frozen public menu and canonical quality catalog for Product Video.

This module is UI/catalog-only. Runtime readiness is deliberately evaluated
elsewhere so a temporarily unavailable worker cannot erase valid public tiers.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services import video_tail9


PUBLIC_MENU_ROWS = (
    ("video_trend", "video_ai_real"),
    ("script_image_video", "frame_video_local"),
    ("self_shot_scene_change", "storyboard_prompt"),
    ("multi_scene_film", "video_idea"),
    ("video_local_edit", "video_downloader"),
    ("main_menu", "video_guide"),
)

CANONICAL_PRICING_PRODUCTS = frozenset({
    "video_ai_real",
    "video_ai_prompt",
    "video_ai_image",
    "video_ai_video_reference",
    "script_image_video",
    "storyboard_prompt",
    "video_trend",
    "video_edit",
    "video_local_edit",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
    "video_idea",
    "multi_scene_film",
    "video_long",
})

FRAMEVIDEO_PRICING_PRODUCTS = frozenset({"frame_video_local", "image_to_video"})
PUBLIC_EXECUTION_LOCKED_PRODUCTS = frozenset({"multi_scene_film", "video_long"})

QUALITY_TIER_ORDER = (200, 300, 400, 500, 600, 800, 1000, 1200, 1500)

QUALITY_TIERS: dict[int, dict[str, Any]] = {
    200: {
        "icon": "🧪",
        "name": "Trải nghiệm",
        "descriptions": ("Video gốc, không add-ons", "Phù hợp test nhanh"),
        "public_level": "Thử ý tưởng nhanh",
        "public_detail": "Chuyển động cơ bản, phù hợp thử mạch nội dung đơn giản.",
        "capabilities": ("text_to_video", "single_scene"),
        "max_scenes": 1,
    },
    300: {
        "icon": "⭐",
        "name": "Cơ bản",
        "descriptions": ("Video ngắn tiêu chuẩn", "Có thể dùng add-ons đơn giản"),
        "public_level": "Cân bằng và ổn định",
        "public_detail": "Phù hợp video phổ thông, giới thiệu ngắn và nội dung mạng xã hội.",
    },
    400: {
        "icon": "🔥",
        "name": "Tốt",
        "descriptions": ("Prompt tốt hơn", "Phù hợp reels/shorts"),
        "public_level": "Giữ chi tiết tốt hơn",
        "public_detail": "Ưu tiên sự nhất quán của chủ thể, sản phẩm và bố cục giữa các cảnh.",
    },
    500: {
        "icon": "💎",
        "name": "Đẹp",
        "descriptions": ("Chất lượng cân bằng", "Khuyên dùng"),
        "public_level": "Hoàn thiện rõ nét",
        "public_detail": "Cân bằng hình ảnh, chuyển động và khả năng giữ nội dung cần thiết.",
    },
    600: {
        "icon": "🚀",
        "name": "Nâng cao",
        "descriptions": ("Cảnh chi tiết hơn", "Phù hợp bán hàng/content"),
        "public_level": "Chất lượng nâng cao",
        "public_detail": "Phù hợp ánh sáng, vật liệu và chuyển động có nhiều chi tiết.",
    },
    800: {
        "icon": "🏆",
        "name": "Premium",
        "descriptions": ("Ưu tiên chất lượng", "Hậu kỳ tốt hơn"),
        "public_level": "Ưu tiên chất lượng",
        "public_detail": "Dành cho nội dung cần hình ảnh tinh tế và mạch cảnh được kiểm soát kỹ.",
    },
    1000: {
        "icon": "🎬",
        "name": "Pro",
        "descriptions": ("Phim/ads chất lượng cao",),
        "public_level": "Kiểm soát thành phần",
        "public_detail": "Phù hợp quảng cáo, phim ngắn và cảnh có nhiều yếu tố cần giữ nguyên.",
    },
    1200: {
        "icon": "🎞",
        "name": "Studio",
        "descriptions": ("Cảnh phức tạp hơn",),
        "public_level": "Đường dựng chất lượng cao",
        "public_detail": "Ưu tiên độ ổn định và chi tiết khi công nghệ phù hợp đang sẵn sàng.",
    },
    1500: {
        "icon": "👑",
        "name": "Max",
        "descriptions": ("Mức cao nhất hiện tại",),
        "public_level": "Mức cao nhất hiện tại",
        "public_detail": "Ưu tiên đường dựng cao nhất và phương án dự phòng phù hợp khi hệ thống sẵn sàng.",
    },
}

_MULTI_SCENE_CAPABILITIES = (
    "text_to_video",
    "text_to_video_or_scene_video",
    "image_to_video",
    "first_last_frame_video",
    "first_last_frame",
    "video_to_video",
    "multi_scene_composition",
    "ratio_9:16",
    "ratio_16:9",
    "ratio_1:1",
    "ratio_4:5",
)

for _tier_id in QUALITY_TIER_ORDER:
    if _tier_id == 200:
        continue
    QUALITY_TIERS[_tier_id].setdefault("capabilities", _MULTI_SCENE_CAPABILITIES)
    QUALITY_TIERS[_tier_id].setdefault("max_scenes", 20)


def tier_spec(tier_id: int) -> dict[str, Any]:
    """Return one immutable public tier snapshot."""

    normalized = min(QUALITY_TIER_ORDER, key=lambda item: abs(item - int(tier_id or 200)))
    return {"tier_id": normalized, **deepcopy(QUALITY_TIERS[normalized])}


def uses_canonical_pricing(product_type: str) -> bool:
    product = str(product_type or "").strip()
    if product not in video_tail9.PRODUCT_ADAPTERS and product not in video_tail9.PRODUCT_ADAPTER_ALIASES:
        return False
    contract = video_tail9.commercial_contract(product)
    return (
        str(contract.get("pricing_mode") or "") == "canonical"
        and str(contract.get("product_type") or "") in CANONICAL_PRICING_PRODUCTS
    )


def uses_framevideo_pricing(product_type: str) -> bool:
    product = str(product_type or "").strip()
    if product in FRAMEVIDEO_PRICING_PRODUCTS:
        return True
    if product not in video_tail9.PRODUCT_ADAPTERS and product not in video_tail9.PRODUCT_ADAPTER_ALIASES:
        return False
    return str(video_tail9.commercial_contract(product).get("pricing_mode") or "") == "frame_video"


def compatible_quality_tiers(
    product_type: str,
    *,
    scene_count: int = 1,
    ratio: str = "9:16",
    required_capability: str = "",
) -> list[dict[str, Any]]:
    """Return catalog-compatible tiers without consulting runtime health."""

    requested_product = str(product_type or "").strip()
    if requested_product not in video_tail9.PRODUCT_ADAPTERS and requested_product not in video_tail9.PRODUCT_ADAPTER_ALIASES:
        return []
    contract = video_tail9.commercial_contract(requested_product)
    product = str(contract.get("product_type") or "")
    if str(contract.get("pricing_mode") or "") == "frame_video":
        return []
    if product not in CANONICAL_PRICING_PRODUCTS:
        return []
    count = max(1, int(scene_count or 1))
    aspect = str(ratio or "9:16")
    capability = str(required_capability or contract.get("required_capability") or "").strip()
    if not (
        int(contract.get("minimum_scene_count") or 1)
        <= count
        <= int(contract.get("maximum_scene_count") or 20)
    ):
        return []
    if count == 1 and not bool(contract.get("supports_single_scene")):
        return []
    supported_tiers = {int(item) for item in contract.get("supported_quality_tiers") or ()}
    offers: list[dict[str, Any]] = []
    for tier_id in QUALITY_TIER_ORDER:
        if tier_id not in supported_tiers:
            continue
        spec = tier_spec(tier_id)
        capabilities = set(spec.get("capabilities") or ())
        if count > int(spec.get("max_scenes") or 1):
            continue
        if tier_id == 200 and (count != 1 or not bool(contract.get("supports_single_scene"))):
            continue
        if aspect and aspect != "keep" and f"ratio_{aspect}" not in capabilities and tier_id != 200:
            continue
        if capability and capability not in capabilities:
            continue
        if product == "storyboard_prompt" and not {
            "image_to_video",
            "first_last_frame_video",
        }.intersection(capabilities):
            continue
        offers.append(spec)
    return offers


def catalog_report(
    product_type: str,
    *,
    scene_count: int = 1,
    ratio: str = "9:16",
    required_capability: str = "",
) -> dict[str, Any]:
    requested_product = str(product_type or "").strip()
    known_product = (
        requested_product in video_tail9.PRODUCT_ADAPTERS
        or requested_product in video_tail9.PRODUCT_ADAPTER_ALIASES
    )
    offers = compatible_quality_tiers(
        product_type,
        scene_count=scene_count,
        ratio=ratio,
        required_capability=required_capability,
    )
    return {
        "ok": bool(offers),
        "product_type": str(
            video_tail9.commercial_contract(requested_product).get("product_type")
            if known_product
            else requested_product
        ),
        "uses_canonical_pricing": uses_canonical_pricing(product_type),
        "framevideo_excluded": uses_framevideo_pricing(product_type),
        "required_capability": str(required_capability or ""),
        "offers": offers,
        "tier_ids": [int(item["tier_id"]) for item in offers],
        "reason": "" if offers else "no_compatible_quality_package",
        "side_effects": {
            "job": 0,
            "outbox": 0,
            "provider_calls": 0,
            "generated_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        },
    }
