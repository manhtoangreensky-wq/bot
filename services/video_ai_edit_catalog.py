"""Canonical public catalog for the provider-gated AI Video Edit lane.

This module is deliberately provider-neutral.  Public UX availability and
production execution readiness are separate facts; every capability remains
production-disabled until a real provider contract is proven.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Iterable


OPTIONS_PER_PAGE = 4


@dataclass(frozen=True, slots=True)
class AIEditCategory:
    stable_id: str
    public_label: str


@dataclass(frozen=True, slots=True)
class AIEditCapability:
    stable_id: str
    category: str
    public_label: str
    public_description: str
    detail_kind: str
    provider_capability_kind: str
    processing_group_hint: str
    requires_text: bool = False
    requires_reference_image: bool = False
    requires_mask: bool = False
    enabled_offline: bool = True
    enabled_production: bool = False
    pricing_behavior: str = "BILLABLE_GROUP"


@dataclass(frozen=True, slots=True)
class AIEditCapabilityPage:
    category: AIEditCategory
    page_index: int
    page_count: int
    items: tuple[AIEditCapability, ...]


CATEGORIES = (
    AIEditCategory("scene", "🎨 Cảnh & phông nền"),
    AIEditCategory("person", "👤 Người / nhân vật"),
    AIEditCategory("object", "📦 Vật thể & sản phẩm"),
    AIEditCategory("style", "✨ Phong cách hình ảnh"),
    AIEditCategory("text", "📝 Chữ & yêu cầu khác"),
)


def _item(
    stable_id: str,
    category: str,
    label: str,
    description: str,
    *,
    detail_kind: str = "text",
    primitive: str = "PROMPT_MODIFY",
    group: str = "PROMPT_MODIFY",
    requires_text: bool = True,
    requires_reference_image: bool = False,
) -> AIEditCapability:
    return AIEditCapability(
        stable_id=stable_id,
        category=category,
        public_label=label,
        public_description=description,
        detail_kind=detail_kind,
        provider_capability_kind=primitive,
        processing_group_hint=group,
        requires_text=requires_text,
        requires_reference_image=requires_reference_image,
    )


CAPABILITIES = (
    # Scene / background (12)
    _item("scene_background", "scene", "Đổi phông nền", "Mô tả phông nền mong muốn."),
    _item("scene_location", "scene", "Đổi địa điểm", "Mô tả địa điểm mới."),
    _item("scene_lighting", "scene", "Đổi ánh sáng", "Mô tả ánh sáng mong muốn."),
    _item("scene_weather", "scene", "Đổi thời tiết", "Mô tả thời tiết mong muốn."),
    _item("scene_day_time", "scene", "Đổi thời gian trong ngày", "Chọn thời điểm mong muốn."),
    _item("scene_season", "scene", "Đổi mùa", "Mô tả mùa mong muốn."),
    _item("scene_overall_color", "scene", "Đổi màu sắc tổng thể", "Mô tả tông màu mong muốn."),
    _item("scene_mood", "scene", "Đổi mood / không khí", "Mô tả không khí mong muốn."),
    _item("scene_luxury", "scene", "Làm cảnh sang trọng hơn", "Mô tả mức độ sang trọng."),
    _item("scene_modern", "scene", "Làm cảnh hiện đại hơn", "Mô tả phong cách hiện đại."),
    _item("scene_clean", "scene", "Làm cảnh sạch/gọn hơn", "Mô tả phần cần làm sạch/gọn."),
    _item("scene_custom", "scene", "Tự mô tả thay đổi cảnh", "Mô tả đầy đủ thay đổi cảnh."),

    # Person / character (7)
    _item(
        "person_replace",
        "person",
        "Thay người / nhân vật",
        "Gửi ảnh mẫu của người hoặc nhân vật thay thế.",
        detail_kind="reference_image",
        primitive="SWAP",
        group="SWAP",
        requires_text=False,
        requires_reference_image=True,
    ),
    _item("person_outfit", "person", "Thay trang phục", "Mô tả trang phục mới."),
    _item("person_outfit_color", "person", "Đổi màu trang phục", "Mô tả màu trang phục mới."),
    _item("person_accessory", "person", "Thêm phụ kiện", "Mô tả phụ kiện cần thêm.", primitive="ADD", group="ADD"),
    _item(
        "person_appearance_reference",
        "person",
        "Thay ngoại hình theo ảnh mẫu",
        "Gửi ảnh ngoại hình mẫu.",
        detail_kind="reference_image",
        primitive="SWAP",
        group="SWAP",
        requires_text=False,
        requires_reference_image=True,
    ),
    _item("person_hair", "person", "Đổi tóc / kiểu tóc", "Mô tả tóc hoặc kiểu tóc mới."),
    _item("person_custom", "person", "Tự mô tả thay đổi nhân vật", "Mô tả đầy đủ thay đổi nhân vật."),

    # Object / product (8)
    _item("object_add", "object", "Thêm vật thể / sản phẩm", "Mô tả vật thể hoặc sản phẩm cần thêm.", primitive="ADD", group="ADD"),
    _item("object_replace", "object", "Thay vật thể / sản phẩm", "Mô tả vật thể cũ và vật thể thay thế.", primitive="SWAP", group="SWAP"),
    _item("object_remove", "object", "Xóa vật thể", "Mô tả vật thể cần xóa.", primitive="REMOVE", group="REMOVE"),
    _item("object_color", "object", "Đổi màu vật thể", "Mô tả vật thể và màu mới."),
    _item("object_accessory", "object", "Thêm phụ kiện", "Mô tả phụ kiện cần thêm.", primitive="ADD", group="ADD"),
    _item("object_prop_replace", "object", "Thay đồ vật trong cảnh", "Mô tả đồ vật cũ và đồ vật mới.", primitive="SWAP", group="SWAP"),
    _item("object_character_add", "object", "Thêm nhân vật vào cảnh", "Mô tả nhân vật cần thêm.", primitive="ADD", group="ADD"),
    _item("object_custom", "object", "Tự mô tả vật thể cần sửa", "Mô tả đầy đủ vật thể cần sửa."),

    # Style (8)
    _item("style_cinematic", "style", "Điện ảnh", "Áp dụng phong cách điện ảnh.", detail_kind="preset", primitive="RESTYLE", group="RESTYLE", requires_text=False),
    _item("style_realistic", "style", "Chân thật", "Áp dụng phong cách chân thật.", detail_kind="preset", primitive="RESTYLE", group="RESTYLE", requires_text=False),
    _item("style_anime", "style", "Hoạt hình / Anime", "Áp dụng phong cách hoạt hình hoặc anime.", detail_kind="preset", primitive="RESTYLE", group="RESTYLE", requires_text=False),
    _item("style_3d", "style", "3D", "Áp dụng phong cách 3D.", detail_kind="preset", primitive="RESTYLE", group="RESTYLE", requires_text=False),
    _item("style_comic", "style", "Truyện tranh", "Áp dụng phong cách truyện tranh.", detail_kind="preset", primitive="RESTYLE", group="RESTYLE", requires_text=False),
    _item("style_art", "style", "Tranh nghệ thuật", "Áp dụng phong cách tranh nghệ thuật.", detail_kind="preset", primitive="RESTYLE", group="RESTYLE", requires_text=False),
    _item("style_advertising", "style", "Phong cách quảng cáo", "Áp dụng phong cách quảng cáo.", detail_kind="preset", primitive="RESTYLE", group="RESTYLE", requires_text=False),
    _item("style_custom", "style", "Tự mô tả phong cách", "Mô tả đầy đủ phong cách mong muốn.", primitive="RESTYLE", group="RESTYLE"),

    # Text / other (4)
    _item("text_replace", "text", "Thay chữ trong video", "Mô tả chữ cũ và chữ mới.", detail_kind="text_replace", primitive="TEXT_REPLACE", group="TEXT_REPLACE"),
    _item("detail_add", "text", "Thêm chi tiết", "Mô tả chi tiết cần thêm.", primitive="ADD", group="ADD"),
    _item("detail_remove", "text", "Xóa chi tiết", "Mô tả chi tiết cần xóa.", primitive="REMOVE", group="REMOVE"),
    _item("custom_request", "text", "Tự mô tả yêu cầu", "Mô tả đầy đủ yêu cầu chỉnh sửa."),
)


_CATEGORY_BY_ID = {item.stable_id: item for item in CATEGORIES}
_CAPABILITY_BY_ID = {item.stable_id: item for item in CAPABILITIES}
_CATALOG_ORDER = {item.stable_id: index for index, item in enumerate(CAPABILITIES)}

if len(_CATEGORY_BY_ID) != len(CATEGORIES):
    raise RuntimeError("duplicate_ai_edit_category")
if len(_CAPABILITY_BY_ID) != len(CAPABILITIES):
    raise RuntimeError("duplicate_ai_edit_capability")
if any(item.category not in _CATEGORY_BY_ID for item in CAPABILITIES):
    raise RuntimeError("unknown_ai_edit_category")


def category(stable_id: str) -> AIEditCategory:
    try:
        return _CATEGORY_BY_ID[str(stable_id or "")]
    except KeyError as exc:
        raise ValueError("unknown_ai_edit_category") from exc


def capability(stable_id: str) -> AIEditCapability:
    try:
        return _CAPABILITY_BY_ID[str(stable_id or "")]
    except KeyError as exc:
        raise ValueError("unknown_ai_edit_capability") from exc


def capabilities_for_category(category_id: str) -> tuple[AIEditCapability, ...]:
    category(category_id)
    return tuple(item for item in CAPABILITIES if item.category == category_id)


def page_count(category_id: str) -> int:
    return max(1, ceil(len(capabilities_for_category(category_id)) / OPTIONS_PER_PAGE))


def capability_page(category_id: str, page_index: int) -> AIEditCapabilityPage:
    items = capabilities_for_category(category_id)
    total = page_count(category_id)
    index = int(page_index)
    if index < 0 or index >= total:
        raise ValueError("unknown_ai_edit_page")
    start = index * OPTIONS_PER_PAGE
    return AIEditCapabilityPage(
        category=category(category_id),
        page_index=index,
        page_count=total,
        items=items[start : start + OPTIONS_PER_PAGE],
    )


def normalized_selection(values: Iterable[Any] | None) -> tuple[str, ...]:
    selected = {
        str(value or "")
        for value in (values or ())
        if str(value or "") in _CAPABILITY_BY_ID
    }
    return tuple(sorted(selected, key=_CATALOG_ORDER.__getitem__))


def toggle_capability_state(state: dict[str, Any] | None, capability_id: str) -> dict[str, Any]:
    """Toggle one stable ID and prune only details/references owned by it."""

    item = capability(capability_id)
    current = dict(state or {})
    selected = list(normalized_selection(current.get("ai_edit_selected")))
    details = dict(current.get("ai_edit_details") or {})
    references = dict(current.get("ai_edit_references") or {})
    if item.stable_id in selected:
        selected.remove(item.stable_id)
        details.pop(item.stable_id, None)
        references.pop(item.stable_id, None)
    else:
        selected.append(item.stable_id)
    current["ai_edit_selected"] = list(normalized_selection(selected))
    current["ai_edit_details"] = details
    current["ai_edit_references"] = references
    return current


def detail_complete(state: dict[str, Any] | None, capability_id: str) -> bool:
    item = capability(capability_id)
    current = dict(state or {})
    details = dict((current.get("ai_edit_details") or {}).get(item.stable_id) or {})
    references = dict((current.get("ai_edit_references") or {}).get(item.stable_id) or {})
    if item.requires_reference_image:
        return bool(
            references.get("file_id")
            and references.get("file_unique_id")
            and references.get("source_fingerprint")
        )
    if item.detail_kind == "text_replace":
        return bool(str(details.get("target_text") or "").strip() and str(details.get("new_text") or "").strip())
    if item.requires_text:
        return bool(str(details.get("text") or "").strip())
    return True


def missing_detail_ids(state: dict[str, Any] | None) -> tuple[str, ...]:
    selected = normalized_selection((state or {}).get("ai_edit_selected"))
    return tuple(item_id for item_id in selected if not detail_complete(state, item_id))


__all__ = [
    "AIEditCapability",
    "AIEditCapabilityPage",
    "AIEditCategory",
    "CAPABILITIES",
    "CATEGORIES",
    "OPTIONS_PER_PAGE",
    "capabilities_for_category",
    "capability",
    "capability_page",
    "category",
    "detail_complete",
    "missing_detail_ids",
    "normalized_selection",
    "page_count",
    "toggle_capability_state",
]
