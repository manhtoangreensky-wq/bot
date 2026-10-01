"""Canonical Bot Core upload staging authority for SubDub Web media intake.

SPEC_ID: BOT-SUBDUB-D1-UPLOAD-STAGING-AUTHORITY
Coordinates:
- Repository: manhtoangreensky-wq/bot
- Governed by: owner-governed-codex, locked-focus-engineering

Invariants:
1. Server generates opaque upload_id (upl_<32 hex chars>); client cannot supply it.
2. Owner binding is derived strictly from authenticated actor; client cannot forge owner.
3. Content & MIME validation with magic byte verification for supported media.
4. Size bounded by SUBDUB_UPLOAD_MAX_MB (default 50MB, max 500MB). Empty payload rejected.
5. Cross-owner access denied (403 fail-closed).
6. Nonexistent or invalid upload_id denied (404/400 fail-closed).
7. Internal filesystem paths are never leaked to external / Web callers.
8. Raw browser paths and remote URLs are strictly rejected as media authority.
9. Durable persistence in existing system_settings SQLite table without schema alteration.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
from typing import Any

logger = logging.getLogger("subdub_upload_staging")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING_DIR = REPO_ROOT / "data" / "uploads" / "staging"
UPLOAD_ID_SAFE_CHARS = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

# MIME and extension allowlists for SubDub media
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
ALLOWED_SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".txt"}
ALLOWED_EXTENSIONS = ALLOWED_VIDEO_EXTENSIONS | ALLOWED_AUDIO_EXTENSIONS | ALLOWED_SUBTITLE_EXTENSIONS

ALLOWED_MIME_TYPES = {
    # Video
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    # Audio
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
    "audio/ogg",
    "audio/flac",
    # Subtitles / Text
    "text/plain",
    "text/vtt",
    "application/x-subrip",
}

FORBIDDEN_AUTHORITY_KEYS = {
    "local_path",
    "file_path",
    "path",
    "url",
    "remote_url",
    "provider_url",
}


def get_staging_directory() -> Path:
    """Resolve and validate the staging directory root."""
    configured = os.getenv("SUBDUB_UPLOAD_STAGING_DIR", "").strip()
    root = Path(configured).resolve() if configured else DEFAULT_STAGING_DIR.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_max_upload_bytes() -> int:
    """Resolve maximum upload bytes from environment (default 50 MB, capped 500 MB)."""
    raw_mb = os.getenv("SUBDUB_UPLOAD_MAX_MB", "50").strip()
    try:
        val_mb = int(raw_mb)
    except (TypeError, ValueError):
        val_mb = 50
    bounded_mb = max(1, min(500, val_mb))
    return bounded_mb * 1024 * 1024


def sanitize_filename(filename: str, fallback: str = "media.bin") -> tuple[str, str]:
    """Extract and sanitize filename and lowercase extension."""
    clean = Path(str(filename or "").replace("\\", "/")).name
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", clean).strip(" ._-")[:120]
    if not clean:
        clean = fallback
    ext = Path(clean).suffix.lower()
    return clean, ext


def validate_media_content(extension: str, content: bytes, mime_type: str = "") -> tuple[bool, str]:
    """Validate container magic bytes and signature to prevent MIME spoofing."""
    if not content:
        return False, "EMPTY_PAYLOAD"

    clean_ext = extension.lower()
    clean_mime = str(mime_type or "").split(";", 1)[0].strip().lower()

    # Extension allowlist check
    if clean_ext not in ALLOWED_EXTENSIONS:
        return False, f"UNSUPPORTED_EXTENSION:{clean_ext}"

    # MIME allowlist check (if mime provided)
    if clean_mime and clean_mime not in ALLOWED_MIME_TYPES and clean_mime != "application/octet-stream":
        return False, f"UNSUPPORTED_MIME_TYPE:{clean_mime}"

    # Content signature checks
    if clean_ext in {".mp4", ".mov", ".m4a"}:
        # Must contain ftyp or moov within first 64 bytes
        if len(content) < 8:
            return False, "INVALID_MP4_HEADER"
        header_sample = content[:64]
        if b"ftyp" not in header_sample and b"moov" not in header_sample:
            return False, "INVALID_MP4_SIGNATURE"
    elif clean_ext == ".webm":
        # EBML header \x1a\x45\xdf\xa3
        if not content.startswith(b"\x1a\x45\xdf\xa3"):
            return False, "INVALID_WEBM_SIGNATURE"
    elif clean_ext == ".mkv":
        if not content.startswith(b"\x1a\x45\xdf\xa3"):
            return False, "INVALID_MKV_SIGNATURE"
    elif clean_ext == ".wav":
        if len(content) < 12 or not content.startswith(b"RIFF") or content[8:12] != b"WAVE":
            return False, "INVALID_WAV_SIGNATURE"
    elif clean_ext == ".ogg":
        if not content.startswith(b"OggS"):
            return False, "INVALID_OGG_SIGNATURE"
    elif clean_ext == ".mp3":
        # ID3 or MPEG sync bytes
        is_id3 = content.startswith(b"ID3")
        is_sync = (
            len(content) >= 2
            and content[0] == 0xFF
            and (content[1] & 0xE0) == 0xE0
        )
        if not (is_id3 or is_sync):
            return False, "INVALID_MP3_SIGNATURE"
    elif clean_ext in {".srt", ".vtt", ".txt"}:
        try:
            decoded = content.decode("utf-8-sig")
            if "\x00" in decoded:
                return False, "INVALID_TEXT_CONTAINS_NULL"
        except UnicodeDecodeError:
            return False, "INVALID_TEXT_ENCODING"

    return True, "OK"


def create_staged_upload(
    file_bytes: bytes,
    file_name: str,
    content_type: str,
    actor_id: str | int,
    idempotency_key: str = "",
    client_metadata: dict[str, Any] | None = None,
) -> tuple[bool, str, int, dict[str, Any]]:
    """Create a canonical staged upload, persist metadata in system_settings, and write bytes."""
    meta = dict(client_metadata or {})
    # Reject local browser paths or unverified remote URLs passed as authority
    for forbidden_key in FORBIDDEN_AUTHORITY_KEYS:
        if forbidden_key in meta and meta[forbidden_key]:
            return False, "LOCAL_PATH_OR_URL_REJECTED", 400, {}

    clean_actor = str(actor_id or "").strip()
    if clean_actor.startswith("telegram-"):
        clean_actor = clean_actor[len("telegram-"):].strip()
    if not clean_actor:
        return False, "ACTOR_ID_REQUIRED", 401, {}

    # Reject empty payload
    if not file_bytes:
        return False, "EMPTY_PAYLOAD", 400, {}

    # Validate size
    max_bytes = get_max_upload_bytes()
    if len(file_bytes) > max_bytes:
        return False, f"FILE_TOO_LARGE_MAX_{max_bytes // (1024*1024)}MB", 413, {}

    safe_name, ext = sanitize_filename(file_name)
    clean_mime = str(content_type or "application/octet-stream").split(";", 1)[0].strip().lower()

    # Validate MIME and signature
    valid, reason = validate_media_content(ext, file_bytes, clean_mime)
    if not valid:
        return False, f"INVALID_MIME_OR_CONTENT:{reason}", 400, {}

    # Generate server-controlled opaque upload_id
    upload_id = f"upl_{secrets.token_hex(16)}"

    # Prepare safe filesystem destination
    staging_dir = get_staging_directory()
    job_dir = (staging_dir / upload_id).resolve()
    # Path containment check
    if not str(job_dir).startswith(str(staging_dir)):
        return False, "UNSAFE_STAGING_PATH", 500, {}
    job_dir.mkdir(parents=True, exist_ok=True)

    dest_file = (job_dir / safe_name).resolve()
    if not str(dest_file).startswith(str(job_dir)):
        return False, "UNSAFE_STAGING_FILE_PATH", 500, {}

    try:
        dest_file.write_bytes(file_bytes)
    except Exception as exc:
        logger.error(f"Failed to write staged upload bytes: {exc}")
        return False, f"STORAGE_WRITE_FAILED:{type(exc).__name__}", 500, {}

    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    record = {
        "upload_id": upload_id,
        "owner_id": clean_actor,
        "file_name": safe_name,
        "content_type": clean_mime,
        "size_bytes": len(file_bytes),
        "sha256": sha256_hash,
        "local_path": str(dest_file),
        "idempotency_key": str(idempotency_key or "").strip(),
        "created_at": now_utc,
        "status": "staged",
    }

    # Persist record in existing system_settings SQLite table
    try:
        import bot
        setting_key = f"subdub_upload:{upload_id}"
        bot.set_system_setting(
            key=setting_key,
            value=json.dumps(record, ensure_ascii=False),
            note=f"SubDub staged upload owner:{clean_actor}",
            updated_by="subdub_upload_staging",
        )
    except Exception as exc:
        logger.error(f"Failed to persist staged upload to system_settings: {exc}")
        try:
            dest_file.unlink(missing_ok=True)
            job_dir.rmdir()
        except Exception:
            pass
        return False, f"DB_PERSISTENCE_FAILED:{type(exc).__name__}", 500, {}

    # Return safe public metadata (no local_path)
    public_data = to_public_metadata(record)
    return True, "OK", 200, public_data


def get_staged_upload(upload_id: str, actor_id: str | int | None = None) -> tuple[bool, str, int, dict[str, Any]]:
    """Lookup and consume staged upload by upload_id, enforcing actor ownership."""
    clean_id = str(upload_id or "").strip()
    if not UPLOAD_ID_SAFE_CHARS.fullmatch(clean_id):
        return False, "INVALID_UPLOAD_ID", 400, {}

    try:
        import bot
        setting_key = f"subdub_upload:{clean_id}"
        val = bot.get_system_setting(setting_key, "")
        if not val:
            return False, "UPLOAD_NOT_FOUND", 404, {}
        record = json.loads(val)
    except Exception as exc:
        logger.warning(f"Error reading staged upload {clean_id}: {exc}")
        return False, "UPLOAD_NOT_FOUND", 404, {}

    if not isinstance(record, dict) or record.get("upload_id") != clean_id:
        return False, "UPLOAD_NOT_FOUND", 404, {}

    # Verify physical file existence
    local_path = str(record.get("local_path") or "").strip()
    if not local_path or not Path(local_path).is_file():
        return False, "STAGED_FILE_MISSING", 404, {}

    # Enforce owner binding if actor_id provided
    if actor_id is not None:
        clean_actor = str(actor_id or "").strip()
        if clean_actor.startswith("telegram-"):
            clean_actor = clean_actor[len("telegram-"):].strip()
        record_owner = str(record.get("owner_id") or "").strip()
        if clean_actor != record_owner:
            return False, "FORBIDDEN_CROSS_OWNER", 403, {}

    return True, "OK", 200, record


def to_public_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Sanitize record for external/Web callers, strictly omitting physical paths."""
    return {
        "ok": True,
        "upload_id": str(record.get("upload_id") or ""),
        "owner_id": str(record.get("owner_id") or ""),
        "file_name": str(record.get("file_name") or ""),
        "content_type": str(record.get("content_type") or ""),
        "size_bytes": int(record.get("size_bytes") or 0),
        "sha256": str(record.get("sha256") or ""),
        "created_at": str(record.get("created_at") or ""),
        "status": str(record.get("status") or "staged"),
    }
