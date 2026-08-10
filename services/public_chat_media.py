"""Pure validation and routing rules for public-chat media inputs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import math
from pathlib import Path
import re
from typing import Literal, Sequence


AttachmentKind = Literal["image", "audio", "video", "pdf"]
PUBLIC_ATTACHMENT_LIMITS = {
    "image": 10 * 1024 * 1024,
    "audio": 20 * 1024 * 1024,
    "video": 20 * 1024 * 1024,
    "pdf": 20 * 1024 * 1024,
}
PUBLIC_ATTACHMENT_MAX_PAGES = 80
PUBLIC_ATTACHMENT_MAX_COUNT = 4
PUBLIC_ATTACHMENT_MAX_PDFS = 1
PUBLIC_AUDIO_MAX_DURATION_SECONDS = 30 * 60
PUBLIC_VIDEO_MAX_DURATION_SECONDS = 15 * 60

_MIME_KIND: dict[str, str] = {
    "text/plain": "text",
    "image/jpeg": "image", "image/jpg": "image", "image/png": "image", "image/webp": "image",
    "audio/mpeg": "audio", "audio/mp3": "audio", "audio/wav": "audio", "audio/x-wav": "audio",
    "audio/ogg": "audio", "audio/opus": "audio", "audio/mp4": "audio",
    "video/mp4": "video", "video/webm": "video", "video/quicktime": "video",
    "application/pdf": "pdf",
}
_SUFFIXES = {
    "text": {".txt"},
    "image": {".jpg", ".jpeg", ".png", ".webp"},
    "audio": {".mp3", ".wav", ".ogg", ".opus", ".m4a"},
    "video": {".mp4", ".webm", ".mov"},
    "pdf": {".pdf"},
}


class MediaValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MediaInput:
    kind: str
    mime_type: str
    size_bytes: int
    filename: str
    provider_file_name: str = ""


@dataclass(frozen=True)
class VideoReadiness:
    state: str
    ready: bool
    terminal_failure: bool


@dataclass(frozen=True)
class PublicChatAttachment:
    kind: AttachmentKind
    mime_type: str
    file_name: str
    declared_bytes: int
    actual_bytes: int
    sha256: str
    temporary_path: Path
    duration_seconds: float = 0.0
    page_count: int = 0


def _mime(value: str) -> str:
    return str(value or "").strip().lower().split(";", 1)[0]


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise MediaValidationError(f"{name} must be a non-negative integer")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MediaValidationError(f"{name} must be a non-negative integer") from exc
    if not parsed.is_finite() or parsed != parsed.to_integral_value() or parsed < 0:
        raise MediaValidationError(f"{name} must be a non-negative integer")
    return int(parsed)


def validate_media_input(media: MediaInput) -> MediaInput:
    if not isinstance(media, MediaInput):
        raise MediaValidationError("media input is invalid")
    kind = str(media.kind or "").strip().lower()
    mime_type = _mime(media.mime_type)
    size = _integer(media.size_bytes, "size_bytes")
    filename = Path(str(media.filename or "")).name
    expected = _MIME_KIND.get(mime_type)
    if kind not in {"text", "image", "audio", "video", "pdf"} or expected != kind:
        raise MediaValidationError("unsupported or mismatched media type")
    suffix = Path(filename).suffix.lower()
    if not filename or (suffix and suffix not in _SUFFIXES[kind]):
        raise MediaValidationError("unsupported file extension")
    limit = 1 * 1024 * 1024 if kind == "text" else PUBLIC_ATTACHMENT_LIMITS[kind]
    if size < 1 or size > limit:
        raise MediaValidationError("media size is outside the allowed range")
    return media


def validate_text_output(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MediaValidationError("public chat output must be non-empty text")
    return value.strip()


def assess_video_readiness(value: object) -> VideoReadiness:
    state = getattr(value, "state", value)
    if isinstance(state, dict):
        state = state.get("name") or state.get("state")
    state = getattr(state, "name", state)
    normalized = str(state or "").strip().upper().split(".")[-1]
    return VideoReadiness(
        state=normalized or "UNKNOWN",
        ready=normalized == "ACTIVE",
        terminal_failure=normalized in {"FAILED", "ERROR", "CANCELLED", "CANCELED", "EXPIRED"},
    )


def classify_attachment(mime_type: str, file_name: str) -> AttachmentKind | None:
    kind = _MIME_KIND.get(_mime(mime_type))
    if kind not in {"image", "audio", "video", "pdf"}:
        return None
    suffix = Path(str(file_name or "")).suffix.lower()
    return kind if not suffix or suffix in _SUFFIXES[kind] else None  # type: ignore[return-value]


def _signature_matches(kind: str, prefix: bytes) -> bool:
    if kind == "image":
        return prefix.startswith(b"\xff\xd8\xff") or prefix.startswith(b"\x89PNG\r\n\x1a\n") or (
            prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP"
        )
    if kind == "audio":
        return prefix.startswith((b"ID3", b"OggS")) or (
            prefix.startswith(b"RIFF") and prefix[8:12] == b"WAVE"
        ) or (len(prefix) >= 12 and prefix[4:8] == b"ftyp") or (
            len(prefix) >= 2 and prefix[0] == 0xFF and prefix[1] & 0xE0 == 0xE0
        )
    if kind == "video":
        return (len(prefix) >= 12 and prefix[4:8] == b"ftyp") or prefix.startswith(b"\x1a\x45\xdf\xa3")
    return prefix.startswith(b"%PDF-")


def _pdf_metadata(path: Path) -> tuple[int, bool]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise MediaValidationError("PDF parser unavailable") from exc
    try:
        reader = PdfReader(str(path), strict=False)
        return (0, True) if reader.is_encrypted else (len(reader.pages), False)
    except Exception as exc:
        raise MediaValidationError("invalid or unreadable PDF") from exc


def validate_attachment(
    *,
    temporary_path: Path,
    mime_type: str,
    file_name: str,
    declared_bytes: int = 0,
    duration_seconds: float = 0.0,
) -> PublicChatAttachment:
    path = Path(temporary_path)
    kind = classify_attachment(mime_type, file_name)
    if kind is None:
        raise MediaValidationError("unsupported MIME type or extension")
    declared = _integer(declared_bytes, "declared_bytes")
    if declared > PUBLIC_ATTACHMENT_LIMITS[kind] or not path.is_file():
        raise MediaValidationError("attachment size exceeds the limit or file is unavailable")
    digest = hashlib.sha256()
    actual = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            actual += len(chunk)
            if actual > PUBLIC_ATTACHMENT_LIMITS[kind]:
                raise MediaValidationError("attachment size exceeds the limit")
            digest.update(chunk)
    if actual < 1 or not _signature_matches(kind, path.read_bytes()[:32]):
        raise MediaValidationError("attachment signature mismatch")
    if isinstance(duration_seconds, bool):
        raise MediaValidationError("duration is invalid")
    try:
        duration = float(duration_seconds or 0)
    except (TypeError, ValueError) as exc:
        raise MediaValidationError("duration is invalid") from exc
    if not math.isfinite(duration) or duration < 0:
        raise MediaValidationError("duration is invalid")
    if kind == "audio" and duration > PUBLIC_AUDIO_MAX_DURATION_SECONDS:
        raise MediaValidationError("audio duration exceeds limit")
    if kind == "video" and duration > PUBLIC_VIDEO_MAX_DURATION_SECONDS:
        raise MediaValidationError("video duration exceeds limit")
    pages = 0
    if kind == "pdf":
        pages, encrypted = _pdf_metadata(path)
        if encrypted or pages > PUBLIC_ATTACHMENT_MAX_PAGES:
            raise MediaValidationError("PDF is encrypted or too long")
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(file_name or "attachment").name)[:120] or "attachment"
    return PublicChatAttachment(
        kind, _mime(mime_type), safe_name, declared, actual, digest.hexdigest(), path, duration, pages
    )


def detect_creation_intent(text: str) -> str:
    value = " ".join(str(text or "").casefold().split())
    action = r"(?:tạo|tao|làm|lam|vẽ|ve|dựng|dung|generate|create|make|draw|render)"
    image_target = r"(?:ảnh|anh|hình|hinh|image|picture|photo)"
    video_target = r"(?:video|clip)"
    any_target = rf"(?:{image_target}|{video_target})"
    if (
        re.search(r"\b(?:giá|gia|price|cost|bao nhiêu|how much)\b", value)
        and re.search(rf"\b{action}\b.{{0,24}}\b{any_target}\b", value)
    ):
        return "none"
    if re.search(
        rf"(?:\b(?:hướng dẫn|huong dan|tutorial)\b.{{0,32}}|\b(?:cách|cach|how to)\s+)\b{action}\b.{{0,24}}\b{any_target}\b",
        value,
    ):
        return "none"
    if re.search(
        rf"\b{action}\b.{{0,16}}\b(?:kịch bản|kich ban|prompt|dàn ý|dan y|ý tưởng|y tuong)\b.{{0,16}}\b{video_target}\b",
        value,
    ):
        return "none"
    if re.search(rf"\b{action}\b.{{0,24}}\b{video_target}\b|(?:生成|创建|製作|制作).{{0,8}}(?:视频|影片|video)", value):
        return "video"
    if re.search(rf"\b{action}\b.{{0,24}}\b{image_target}\b|(?:生成|创建|製作|制作).{{0,8}}(?:图片|圖片|图像|影像|image)", value):
        return "image"
    return "none"


def capability_decision(mode: str, kinds: Sequence[str], requested_output: str = "text") -> dict[str, str]:
    selected = str(mode or "").lower()
    output = str(requested_output or "text").lower()
    if output in {"image", "video"}:
        return {"route": "media_handoff", "kind": output}
    if output != "text" or selected not in {"free", "pro"}:
        return {"route": "unsupported", "reason": "text_only" if output != "text" else "unknown_mode"}
    allowed = {"free": {"image", "audio", "video", "pdf"}, "pro": {"image", "pdf"}}[selected]
    normalized = [str(item).lower() for item in kinds]
    if any(item not in {"image", "audio", "video", "pdf"} for item in normalized):
        return {"route": "unsupported", "reason": "unknown_attachment"}
    if any(item not in allowed for item in normalized):
        return {"route": "unsupported", "reason": "capability"}
    return {"route": "gemini" if selected == "free" else "opus"}


def attachment_memory_label(item: PublicChatAttachment) -> str:
    label = f"{item.kind}:{item.file_name}:{item.sha256[:12]}"
    if item.page_count:
        label += f":pages={item.page_count}"
    if item.duration_seconds:
        label += f":duration={int(item.duration_seconds)}s"
    return label[:220]


def attachment_reservation_tokens(items: Sequence[PublicChatAttachment]) -> int:
    if len(items) > PUBLIC_ATTACHMENT_MAX_COUNT:
        raise MediaValidationError("attachment count exceeds the limit")
    total = 0
    pdfs = 0
    for item in items:
        if item.kind == "image":
            total += 8_192
        elif item.kind == "pdf":
            pdfs += 1
            if pdfs > PUBLIC_ATTACHMENT_MAX_PDFS:
                raise MediaValidationError("PDF count exceeds the limit")
            if not 1 <= item.page_count <= PUBLIC_ATTACHMENT_MAX_PAGES:
                raise MediaValidationError("PDF page count is invalid")
            total += 8_000 * item.page_count
        elif item.kind not in {"audio", "video"}:
            raise MediaValidationError("unknown attachment")
    return total


__all__ = [
    "AttachmentKind", "MediaInput", "MediaValidationError", "PUBLIC_ATTACHMENT_LIMITS",
    "PUBLIC_ATTACHMENT_MAX_COUNT", "PUBLIC_ATTACHMENT_MAX_PAGES", "PUBLIC_ATTACHMENT_MAX_PDFS",
    "PublicChatAttachment", "VideoReadiness", "assess_video_readiness", "attachment_memory_label",
    "attachment_reservation_tokens", "capability_decision", "classify_attachment", "detect_creation_intent",
    "validate_attachment", "validate_media_input", "validate_text_output",
]
