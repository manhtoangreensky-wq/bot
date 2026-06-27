"""Reference asset intake for generated video planning.

No Telegram objects, provider calls, billing, or rendering live here. Callers
can store Telegram file ids as plain strings and decide later how to download
or pass them to a provider.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


ASSET_TYPES = {
    "subject_reference",
    "product_reference",
    "object_reference",
    "character_reference",
    "scene_background",
    "style_reference",
    "storyboard_frame",
    "logo",
    "voice_audio",
    "music_audio",
    "existing_video",
    "subtitle_file",
}

PUBLIC_ASSET_LIMITS = {
    "subject_reference": 3,
    "product_reference": 3,
    "object_reference": 3,
    "character_reference": 3,
    "scene_background": 5,
    "style_reference": 5,
    "storyboard_frame": 10,
    "logo": 1,
    "voice_audio": 1,
    "music_audio": 1,
    "existing_video": 1,
    "subtitle_file": 1,
}


@dataclass
class AssetSlot:
    slot_id: str
    asset_type: str
    file_id: str
    local_path: str | None = None
    mime_type: str = ""
    source_message_id: int | None = None
    caption: str = ""
    scene_index: int | None = None
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.asset_type not in ASSET_TYPES:
            raise ValueError(f"unknown_asset_type:{self.asset_type}")
        self.weight = max(0.0, min(1.0, float(self.weight or 0.0)))
        if self.scene_index is not None:
            self.scene_index = max(1, min(10, int(self.scene_index)))


@dataclass
class VideoAssetPack:
    subject_refs: list[AssetSlot] = field(default_factory=list)
    product_refs: list[AssetSlot] = field(default_factory=list)
    object_refs: list[AssetSlot] = field(default_factory=list)
    character_refs: list[AssetSlot] = field(default_factory=list)
    background_refs: list[AssetSlot] = field(default_factory=list)
    style_refs: list[AssetSlot] = field(default_factory=list)
    storyboard_frames: list[AssetSlot] = field(default_factory=list)
    logo_refs: list[AssetSlot] = field(default_factory=list)
    voice_audio_refs: list[AssetSlot] = field(default_factory=list)
    music_audio_refs: list[AssetSlot] = field(default_factory=list)
    existing_video_refs: list[AssetSlot] = field(default_factory=list)
    subtitle_files: list[AssetSlot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


ASSET_LIST_FIELD = {
    "subject_reference": "subject_refs",
    "product_reference": "product_refs",
    "object_reference": "object_refs",
    "character_reference": "character_refs",
    "scene_background": "background_refs",
    "style_reference": "style_refs",
    "storyboard_frame": "storyboard_frames",
    "logo": "logo_refs",
    "voice_audio": "voice_audio_refs",
    "music_audio": "music_audio_refs",
    "existing_video": "existing_video_refs",
    "subtitle_file": "subtitle_files",
}


def new_asset_pack(notes: list[str] | None = None) -> VideoAssetPack:
    return VideoAssetPack(notes=list(notes or []))


def pack_to_dict(pack: VideoAssetPack) -> dict[str, Any]:
    return asdict(pack)


def asset_slot_from_dict(payload: dict[str, Any]) -> AssetSlot:
    return AssetSlot(**dict(payload or {}))


def pack_from_dict(payload: dict[str, Any] | None) -> VideoAssetPack:
    payload = dict(payload or {})
    pack = VideoAssetPack(notes=list(payload.get("notes") or []))
    for asset_type, field_name in ASSET_LIST_FIELD.items():
        items = [asset_slot_from_dict(item) for item in list(payload.get(field_name) or [])]
        if asset_type == "storyboard_frame":
            items = sorted(items, key=lambda item: (item.scene_index or 999, item.created_at))
        setattr(pack, field_name, items)
    return pack


def classify_asset_type(mime_type: str = "", caption: str = "", explicit_type: str = "") -> str:
    explicit = str(explicit_type or "").strip()
    if explicit in ASSET_TYPES:
        return explicit
    text = f"{mime_type} {caption}".lower()
    if "logo" in text or "watermark" in text:
        return "logo"
    if "voice" in text or "giọng" in text or "audio/voice" in text:
        return "voice_audio"
    if "music" in text or "nhạc" in text:
        return "music_audio"
    if "subtitle" in text or text.endswith(".srt") or text.endswith(".vtt"):
        return "subtitle_file"
    if "video/" in text:
        return "existing_video"
    if "storyboard" in text or "cảnh số" in text or "scene" in text:
        return "storyboard_frame"
    if "background" in text or "bối cảnh" in text or "scene_background" in text:
        return "scene_background"
    if "style" in text or "phong cách" in text:
        return "style_reference"
    if "product" in text or "sản phẩm" in text:
        return "product_reference"
    if "object" in text or "đồ vật" in text:
        return "object_reference"
    if "character" in text or "nhân vật" in text or "person" in text or "người" in text:
        return "character_reference"
    return "subject_reference"


def _list_for(pack: VideoAssetPack, asset_type: str) -> list[AssetSlot]:
    if asset_type not in ASSET_LIST_FIELD:
        raise ValueError(f"unknown_asset_type:{asset_type}")
    return getattr(pack, ASSET_LIST_FIELD[asset_type])


def can_add_asset(pack: VideoAssetPack, asset_type: str, *, admin: bool = False) -> tuple[bool, str]:
    if admin:
        return True, "admin_bypass"
    limit = PUBLIC_ASSET_LIMITS.get(asset_type, 1)
    current = len(_list_for(pack, asset_type))
    if current >= limit:
        return False, f"limit_reached:{asset_type}:{limit}"
    return True, "ok"


def add_asset(
    pack: VideoAssetPack,
    *,
    asset_type: str,
    file_id: str,
    local_path: str | None = None,
    mime_type: str = "",
    source_message_id: int | None = None,
    caption: str = "",
    scene_index: int | None = None,
    weight: float = 1.0,
    admin: bool = False,
) -> AssetSlot:
    allowed, reason = can_add_asset(pack, asset_type, admin=admin)
    if not allowed:
        raise ValueError(reason)
    slot = AssetSlot(
        slot_id=f"{asset_type}-{int(time.time() * 1000)}-{len(_list_for(pack, asset_type)) + 1}",
        asset_type=asset_type,
        file_id=str(file_id or ""),
        local_path=local_path,
        mime_type=str(mime_type or ""),
        source_message_id=source_message_id,
        caption=str(caption or ""),
        scene_index=scene_index,
        weight=weight,
    )
    items = _list_for(pack, asset_type)
    items.append(slot)
    if asset_type == "storyboard_frame":
        items.sort(key=lambda item: (item.scene_index or 999, item.created_at))
    return slot


def asset_count(pack: VideoAssetPack) -> int:
    return sum(len(getattr(pack, field_name)) for field_name in ASSET_LIST_FIELD.values())


def asset_reference_summary(pack: VideoAssetPack) -> str:
    parts = []
    labels = {
        "subject_refs": "subject",
        "product_refs": "product",
        "object_refs": "object",
        "character_refs": "character",
        "background_refs": "background",
        "style_refs": "style",
        "storyboard_frames": "storyboard",
        "logo_refs": "logo",
        "voice_audio_refs": "voice",
        "music_audio_refs": "music",
        "existing_video_refs": "existing video",
        "subtitle_files": "subtitle",
    }
    for field_name, label in labels.items():
        count = len(getattr(pack, field_name))
        if count:
            parts.append(f"{label}:{count}")
    if not parts:
        return "no reference assets"
    return ", ".join(parts)


def safe_asset_summary(pack: VideoAssetPack) -> str:
    lines = [f"Assets: {asset_reference_summary(pack)}"]
    if pack.notes:
        lines.append("Notes: " + "; ".join(str(note)[:80] for note in pack.notes[:3]))
    if pack.storyboard_frames:
        order = ", ".join(str(item.scene_index or index + 1) for index, item in enumerate(pack.storyboard_frames[:10]))
        lines.append(f"Storyboard order: {order}")
    return "\n".join(lines)


def asset_upload_triggers_render() -> bool:
    return False
