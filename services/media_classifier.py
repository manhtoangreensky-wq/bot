"""Deterministic classification helpers for the TOAN AAS Knowledge Vault."""

from __future__ import annotations

import mimetypes
import re
import unicodedata
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".srt", ".vtt"}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | TEXT_EXTENSIONS

TAG_RULES = {
    "product_ads": ("product ad", "quang cao san pham", "san pham", "product demo"),
    "affiliate": ("affiliate", "tiep thi lien ket"),
    "course": ("course", "khoa hoc", "bai giang"),
    "short_video": ("short video", "video ngan", "shorts"),
    "tiktok_reels": ("tiktok", "reels", "instagram reel"),
    "cinematic": ("cinematic", "dien anh"),
    "anime": ("anime", "manga"),
    "fashion": ("fashion", "thoi trang", "lookbook"),
    "food": ("food", "mon an", "am thuc"),
    "tech": ("technology", "tech", "cong nghe", "app", "software"),
    "business": ("business", "kinh doanh"),
    "marketing": ("marketing", "quang cao", "campaign"),
    "tutorial": ("tutorial", "huong dan", "workflow"),
    "agentic_ai": ("agentic ai", "ai agent", "agent workflow"),
    "app_workflow": ("app workflow", "web workflow", "automation", "n8n"),
    "motion_prompt": ("motion prompt", "camera movement", "chuyen dong"),
    "hand_product_demo": ("hand product", "cam san pham", "tay cam"),
}


def normalize_text(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(char for char in raw if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def tags_for_text(value: str) -> list[str]:
    text = normalize_text(value)
    tags = [
        tag
        for tag, markers in TAG_RULES.items()
        if any(normalize_text(marker) in text for marker in markers)
    ]
    return sorted(set(tags))


def category_for_text(value: str) -> str:
    tags = tags_for_text(value)
    priorities = (
        "product_ads",
        "affiliate",
        "course",
        "marketing",
        "agentic_ai",
        "app_workflow",
        "cinematic",
        "anime",
        "fashion",
        "food",
        "tech",
        "tutorial",
    )
    return next((tag for tag in priorities if tag in tags), "reference")


def media_type_for_path(path: str | Path, mime_type: str = "", description: str = "") -> str:
    source = Path(path)
    extension = source.suffix.lower()
    mime = str(mime_type or mimetypes.guess_type(source.name)[0] or "").lower()
    text = normalize_text(f"{source.name} {description}")
    if extension in VIDEO_EXTENSIONS or mime.startswith("video/"):
        return "video"
    if extension in IMAGE_EXTENSIONS or mime.startswith("image/"):
        return "image"
    if extension in AUDIO_EXTENSIONS or mime.startswith("audio/"):
        if any(marker in text for marker in ("sfx", "sound effect", "whoosh", "click", "pop")):
            return "sfx"
        if any(marker in text for marker in ("voice", "narration", "tts", "giong", "loi noi")):
            return "voice"
        return "music"
    if extension in TEXT_EXTENSIONS or mime.startswith("text/"):
        return "document"
    return "unknown"


def classify_source(
    path: str | Path,
    *,
    mime_type: str = "",
    extracted_text: str = "",
    description: str = "",
) -> dict[str, Any]:
    media_type = media_type_for_path(path, mime_type, description)
    combined = f"{Path(path).stem} {description} {extracted_text}"
    tags = tags_for_text(combined)
    return {
        "asset_type": media_type,
        "category": category_for_text(combined),
        "tags": tags,
        "use_case": next((tag for tag in tags if tag in {"product_ads", "affiliate", "course", "tutorial"}), ""),
        "needs_rights_review": any(
            marker in normalize_text(combined)
            for marker in ("brand", "logo", "celebrity", "nguoi that", "copyright")
        ),
    }


def supported_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS
