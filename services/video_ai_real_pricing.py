"""Verified image and per-scene video pricing for the Video AI Real pilot.

This module is deliberately side-effect free. It stores reviewed public price
evidence and calculates a conservative UI quote; it never selects a runtime
provider, calls an API, creates a job, or mutates a wallet.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_FLOOR
from typing import Any


XU_TO_VND = Decimal("100")
SALE_MULTIPLIER = Decimal("3")
PROVIDER_PRIORITY = ("shopaikey", "key4u")
SOURCE_CHECKED_ON = "2026-08-09"
PROVIDER_USD_TO_VND = {
    "shopaikey": Decimal("3250"),
    "key4u": Decimal("3000"),
}
PROVIDER_SOURCE_URLS = {
    "shopaikey": "https://shopaikey.com/models",
    "key4u": "https://key4u.vn/models",
}


_MODEL_ROWS: tuple[dict[str, Any], ...] = (
    {
        "key": "grok3_5",
        "label": "Grok 3",
        "seconds": 5,
        "quality": "Tiêu chuẩn 720p",
        "resolution": "720p",
        "description": "Clip ngắn, chuyển động rõ và có âm thanh; hợp quảng cáo hoặc nội dung mạng xã hội một hành động.",
        "providers": {
            "shopaikey": {
                "model": "grok-video-3",
                "catalog_model": "grok-video-3",
                "request_metadata": {"duration": 5, "resolution": "720P"},
                "usd_per_scene": "0.400",
                "pricing_basis": "mỗi lần tạo",
            },
            "key4u": {
                "model": "grok-imagine-video",
                "usd_per_second": "0.420",
                "pricing_basis": "mỗi giây video đầu ra 720p",
            },
        },
    },
    {
        "key": "grok3_10",
        "label": "Grok 3",
        "seconds": 10,
        "quality": "Tiêu chuẩn 720p - cảnh dài",
        "resolution": "720p",
        "description": "Cảnh dài hơn cho lời thoại hoặc hai nhịp chuyển động liên tục, vẫn giữ phong cách video chân thật.",
        "providers": {
            "shopaikey": {
                "model": "grok-video-3",
                "catalog_model": "grok-video-3-10s",
                "request_metadata": {"duration": 10, "resolution": "720P"},
                "usd_per_scene": "0.400",
                "pricing_basis": "mỗi lần tạo 10 giây",
            },
            "key4u": {
                "model": "grok-imagine-video",
                "usd_per_second": "0.420",
                "pricing_basis": "mỗi giây video đầu ra 720p",
            },
        },
    },
    {
        "key": "veo31_fast_8",
        "label": "Veo 3.1 Fast",
        "seconds": 8,
        "quality": "Chất lượng tốt - tạo nhanh",
        "resolution": "720p/1080p theo provider",
        "description": "Hình ảnh ổn định, chuyển động mượt và âm thanh đồng bộ; cân bằng tốt giữa tốc độ và chất lượng.",
        "providers": {
            "shopaikey": {
                "model": "veo3.1-fast",
                "usd_per_scene": "0.700",
                "pricing_basis": "mỗi lần tạo",
            },
            "key4u": {
                "model": "veo_3_1-fast",
                "usd_per_scene": "0.576",
                "pricing_basis": "mỗi lần tạo",
            },
        },
    },
    {
        "key": "veo31_pro_8",
        "label": "Veo 3.1 Pro",
        "seconds": 8,
        "quality": "Cao cấp - ưu tiên chi tiết",
        "resolution": "1080p/4K theo provider",
        "description": "Ưu tiên độ chi tiết, ánh sáng và tính nhất quán; phù hợp cảnh sản phẩm hoặc hình ảnh cần chất lượng cao.",
        "providers": {
            "shopaikey": {
                "model": "veo3.1-pro",
                "usd_per_scene": "3.500",
                "pricing_basis": "mỗi lần tạo",
            },
            "key4u": {
                "model": "veo_3_1",
                "usd_per_scene": "0.768",
                "pricing_basis": "mỗi lần tạo",
            },
        },
    },
)


_IMAGE_MODEL_ROWS: tuple[dict[str, Any], ...] = (
    {
        "key": "grok_image",
        "label": "Grok Image",
        "quality": "Nhanh - ảnh chân thật",
        "description": "Tạo ảnh nhanh cho nội dung mạng xã hội, ảnh sản phẩm cơ bản và bản nháp hình ảnh.",
        "providers": {
            "shopaikey": {
                "model": "grok-imagine-image",
                "usd_per_image": "0.208",
                "pricing_basis": "mỗi ảnh",
            },
            "key4u": {
                "model": "grok-imagine-image",
                "usd_per_image": "0.208",
                "pricing_basis": "mỗi ảnh",
            },
        },
    },
    {
        "key": "grok_image_pro",
        "label": "Grok Image Pro",
        "quality": "Cao cấp - chi tiết tốt hơn",
        "description": "Ưu tiên độ chính xác, chi tiết và độ hoàn thiện cho ảnh quảng cáo hoặc key visual.",
        "providers": {
            "shopaikey": {
                "model": "grok-imagine-image-pro",
                "usd_per_image": "0.728",
                "pricing_basis": "mỗi ảnh",
            },
            "key4u": {
                "model": "grok-imagine-image-pro",
                "usd_per_image": "0.728",
                "pricing_basis": "mỗi ảnh",
            },
        },
    },
)


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
    exchange = PROVIDER_USD_TO_VND[provider]
    cost_vnd = usd_per_scene * exchange
    return {
        "provider": provider,
        "model": str(raw.get("model") or ""),
        "catalog_model": str(raw.get("catalog_model") or raw.get("model") or ""),
        "request_metadata": deepcopy(dict(raw.get("request_metadata") or {})),
        "usd_per_scene": float(usd_per_scene),
        "usd_to_vnd": int(exchange),
        "cost_vnd": int(cost_vnd),
        "pricing_basis": str(raw.get("pricing_basis") or ""),
        "source_url": PROVIDER_SOURCE_URLS[provider],
        "checked_on": SOURCE_CHECKED_ON,
    }


def model_catalog() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in _MODEL_ROWS:
        row = deepcopy(source)
        costs = [_provider_cost(row, provider) for provider in PROVIDER_PRIORITY]
        priced_by = max(costs, key=lambda item: (int(item["cost_vnd"]), -PROVIDER_PRIORITY.index(item["provider"])))
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


def model_by_key(model_key: str) -> dict[str, Any]:
    key = str(model_key or "").strip()
    model = next((row for row in model_catalog() if row["key"] == key), None)
    if not model:
        raise ValueError("video_ai_real_model_invalid")
    return model


def _image_provider_cost(row: dict[str, Any], provider: str) -> dict[str, Any]:
    raw = dict((row.get("providers") or {}).get(provider) or {})
    usd_per_image = _decimal(raw.get("usd_per_image"))
    exchange = PROVIDER_USD_TO_VND[provider]
    cost_vnd = int(usd_per_image * exchange)
    return {
        "provider": provider,
        "model": str(raw.get("model") or ""),
        "usd_per_image": float(usd_per_image),
        "usd_to_vnd": int(exchange),
        "cost_vnd": cost_vnd,
        "pricing_basis": str(raw.get("pricing_basis") or ""),
        "source_url": PROVIDER_SOURCE_URLS[provider],
        "checked_on": SOURCE_CHECKED_ON,
    }


def image_model_catalog() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in _IMAGE_MODEL_ROWS:
        row = deepcopy(source)
        costs = [_image_provider_cost(row, provider) for provider in PROVIDER_PRIORITY]
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


def image_model_by_key(model_key: str) -> dict[str, Any]:
    key = str(model_key or "").strip()
    model = next((row for row in image_model_catalog() if row["key"] == key), None)
    if not model:
        raise ValueError("video_ai_real_image_model_invalid")
    return model


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
