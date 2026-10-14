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
import sqlite3
from typing import Any

logger = logging.getLogger("subdub_upload_staging")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING_DIR = REPO_ROOT / "data" / "uploads" / "staging"
UPLOAD_ID_SAFE_CHARS = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

# MIME and extension allowlists for SubDub and Image media
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
ALLOWED_SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".txt"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_EXTENSIONS = (
    ALLOWED_VIDEO_EXTENSIONS
    | ALLOWED_AUDIO_EXTENSIONS
    | ALLOWED_SUBTITLE_EXTENSIONS
    | ALLOWED_IMAGE_EXTENSIONS
)

ALLOWED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
}
ALLOWED_AUDIO_MIME_TYPES = {
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
}
ALLOWED_SUBTITLE_MIME_TYPES = {
    "text/plain",
    "text/vtt",
    "application/x-subrip",
}
ALLOWED_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
}
ALLOWED_MIME_TYPES = (
    ALLOWED_VIDEO_MIME_TYPES
    | ALLOWED_AUDIO_MIME_TYPES
    | ALLOWED_SUBTITLE_MIME_TYPES
    | ALLOWED_IMAGE_MIME_TYPES
)
IMAGE_UPLOAD_DEFAULT_MAX_MB = 20
IMAGE_UPLOAD_HARD_MAX_MB = 20
IMAGE_UPLOAD_MAX_MB = IMAGE_UPLOAD_DEFAULT_MAX_MB

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


def get_max_upload_bytes_for_extension(extension: str) -> int:
    """Resolve maximum upload bytes depending on media kind.

    Images are strictly bounded to max 20MB (or bounded IMAGE_UPLOAD_MAX_MB).
    Environment can reduce below 20MB, but CANNOT increase above 20MB.
    Video/Audio retain existing SUBDUB_UPLOAD_MAX_MB (default 50MB, cap 500MB).
    """
    clean_ext = str(extension or "").lower()
    if clean_ext in ALLOWED_IMAGE_EXTENSIONS:
        raw_mb = os.getenv("IMAGE_UPLOAD_MAX_MB", str(IMAGE_UPLOAD_DEFAULT_MAX_MB)).strip()
        try:
            val_mb = int(raw_mb)
        except (TypeError, ValueError):
            val_mb = IMAGE_UPLOAD_DEFAULT_MAX_MB
        bounded_mb = max(1, min(IMAGE_UPLOAD_HARD_MAX_MB, val_mb))
        return bounded_mb * 1024 * 1024
    return get_max_upload_bytes()


def sanitize_filename(filename: str, fallback: str = "media.bin") -> tuple[str, str]:
    """Extract and sanitize filename and lowercase extension."""
    clean = Path(str(filename or "").replace("\\", "/")).name
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", clean).strip(" ._-")[:120]
    if not clean:
        clean = fallback
    ext = Path(clean).suffix.lower()
    return clean, ext


def validate_jpeg_structure(content: bytes) -> tuple[bool, str]:
    """Validate JPEG Start-of-Image (SOI), segment progression, and End-of-Image (EOI)."""
    if len(content) < 4 or not content.startswith(b"\xff\xd8"):
        return False, "INVALID_JPEG_SOI"
    if not content.startswith(b"\xff\xd8\xff"):
        return False, "INVALID_JPEG_MARKER"

    trimmed = content.rstrip(b"\r\n\x00 ")
    if not trimmed.endswith(b"\xff\xd9"):
        return False, "INVALID_JPEG_EOI_MISSING"

    idx = 2
    length = len(content)
    has_sos = False

    while idx < length:
        if content[idx] != 0xFF:
            if has_sos:
                next_ff = content.find(b"\xff", idx)
                if next_ff == -1:
                    return False, "TRUNCATED_JPEG_NO_EOI"
                idx = next_ff
                continue
            return False, "INVALID_JPEG_MARKER_ALIGNMENT"

        while idx < length and content[idx] == 0xFF:
            idx += 1
        if idx >= length:
            return False, "TRUNCATED_JPEG_AT_MARKER"

        marker = content[idx]
        idx += 1

        if marker in (0x00, 0x01) or (0xD0 <= marker <= 0xD7):
            continue
        elif marker == 0xD8:
            return False, "UNEXPECTED_NESTED_SOI"
        elif marker == 0xD9:
            break
        else:
            if idx + 2 > length:
                return False, "TRUNCATED_JPEG_SEGMENT_LENGTH"
            seg_len = (content[idx] << 8) | content[idx + 1]
            if seg_len < 2:
                return False, "INVALID_JPEG_SEGMENT_LENGTH"
            if idx + seg_len > length:
                return False, "TRUNCATED_JPEG_SEGMENT_BODY"
            if marker == 0xDA:
                has_sos = True
            idx += seg_len

    try:
        import io
        from PIL import Image
        with Image.open(io.BytesIO(content)) as im:
            im.verify()
            if im.format != "JPEG":
                return False, f"UNEXPECTED_IMAGE_FORMAT:{im.format}"
    except Exception as exc:
        return False, f"MALFORMED_JPEG_STRUCTURE:{type(exc).__name__}"

    return True, "OK"


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

    # Extension and MIME consistency check for images
    if clean_ext in ALLOWED_IMAGE_EXTENSIONS and clean_mime and clean_mime != "application/octet-stream":
        if clean_ext == ".png" and clean_mime != "image/png":
            return False, f"MIME_EXTENSION_MISMATCH:{clean_mime}_VS_{clean_ext}"
        if clean_ext in {".jpg", ".jpeg"} and clean_mime != "image/jpeg":
            return False, f"MIME_EXTENSION_MISMATCH:{clean_mime}_VS_{clean_ext}"
        if clean_ext == ".webp" and clean_mime != "image/webp":
            return False, f"MIME_EXTENSION_MISMATCH:{clean_mime}_VS_{clean_ext}"

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
    elif clean_ext == ".png":
        if len(content) < 8 or not content.startswith(b"\x89PNG\r\n\x1a\n"):
            return False, "INVALID_PNG_SIGNATURE"
    elif clean_ext in {".jpg", ".jpeg"}:
        ok_jpg, reason_jpg = validate_jpeg_structure(content)
        if not ok_jpg:
            return False, f"INVALID_JPEG_SIGNATURE:{reason_jpg}"
    elif clean_ext == ".webp":
        if len(content) < 12 or not content.startswith(b"RIFF") or content[8:12] != b"WEBP":
            return False, "INVALID_WEBP_SIGNATURE"

    return True, "OK"


def ensure_staged_upload_idempotency_schema(conn: sqlite3.Connection | None = None) -> None:
    """Ensure the staged_upload_idempotency table and state columns exist in SQLite database."""
    should_close = False
    if conn is None:
        try:
            import bot
            conn = bot.db_connect()
            should_close = True
        except Exception as exc:
            logger.warning(f"Failed to connect to db for idempotency schema: {exc}")
            return
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS staged_upload_idempotency (
                actor_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                upload_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                file_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                relative_path TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT 'RESERVED',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (actor_id, idempotency_key)
            )
            """
        )
        cursor = conn.execute("PRAGMA table_info(staged_upload_idempotency)")
        cols = {row[1] for row in cursor.fetchall()}
        if "size_bytes" not in cols:
            conn.execute("ALTER TABLE staged_upload_idempotency ADD COLUMN size_bytes INTEGER NOT NULL DEFAULT 0")
        if "relative_path" not in cols:
            conn.execute("ALTER TABLE staged_upload_idempotency ADD COLUMN relative_path TEXT NOT NULL DEFAULT ''")
        if "state" not in cols:
            conn.execute("ALTER TABLE staged_upload_idempotency ADD COLUMN state TEXT NOT NULL DEFAULT 'READY'")
        if "updated_at" not in cols:
            conn.execute("ALTER TABLE staged_upload_idempotency ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_staged_upload_upload_id ON staged_upload_idempotency (upload_id)")
        conn.commit()
    except Exception as exc:
        logger.warning(f"Failed to ensure staged_upload_idempotency schema: {exc}")
    finally:
        if should_close and conn:
            conn.close()


def _sync_legacy_system_settings(record: dict[str, Any]) -> None:
    """Best-effort synchronization to legacy system_settings for backward compatibility."""
    try:
        import bot
        upload_id = str(record.get("upload_id") or "").strip()
        actor_id = str(record.get("owner_id") or "").strip()
        idemp_key = str(record.get("idempotency_key") or "").strip()
        if not upload_id:
            return
        setting_key = f"subdub_upload:{upload_id}"
        bot.set_system_setting(
            key=setting_key,
            value=json.dumps(record, ensure_ascii=False),
            note=f"SubDub staged upload owner:{actor_id}",
            updated_by="subdub_upload_staging",
        )
        if idemp_key:
            bot.set_system_setting(
                key=f"subdub_upload_idem:{actor_id}:{idemp_key}",
                value=json.dumps({
                    "upload_id": upload_id,
                    "sha256": record.get("sha256"),
                    "file_name": record.get("file_name"),
                    "content_type": record.get("content_type"),
                }, ensure_ascii=False),
                note=f"SubDub upload idempotency owner:{actor_id}",
                updated_by="subdub_upload_staging",
            )
    except Exception as exc:
        logger.warning(f"Secondary legacy system_settings sync skipped/failed (non-fatal): {exc}")


def create_staged_upload(
    file_bytes: bytes,
    file_name: str,
    content_type: str,
    actor_id: str | int,
    idempotency_key: str = "",
    client_metadata: dict[str, Any] | None = None,
) -> tuple[bool, str, int, dict[str, Any]]:
    """Create a canonical staged upload, persist metadata in SQLite idempotency table, and write bytes.

    State machine:
    1. BEGIN IMMEDIATE -> lookup (actor_id, idempotency_key).
       If absent -> reserve upload_id in 'RESERVED' state.
       If present -> reuse existing upload_id (never generate a 2nd ID).
    2. Write physical bytes to (staging_dir / upload_id / file_name) and verify SHA.
    3. Finalize row to 'READY' state.
    4. Best-effort sync to legacy system_settings (secondary authority).
    """
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

    safe_name, ext = sanitize_filename(file_name)
    clean_mime = str(content_type or "application/octet-stream").split(";", 1)[0].strip().lower()

    # Validate size against media-specific limit
    max_bytes = get_max_upload_bytes_for_extension(ext)
    if len(file_bytes) > max_bytes:
        return False, f"FILE_TOO_LARGE_MAX_{max_bytes // (1024*1024)}MB", 413, {}

    # Validate MIME and signature
    valid, reason = validate_media_content(ext, file_bytes, clean_mime)
    if not valid:
        return False, f"INVALID_MIME_OR_CONTENT:{reason}", 400, {}

    # Validate SHA256 integrity if caller provided expected sha256
    supplied_sha = str(
        meta.get("sha256")
        or meta.get("expected_sha256")
        or ""
    ).strip().lower()
    actual_sha = hashlib.sha256(file_bytes).hexdigest().lower()
    if supplied_sha and supplied_sha != actual_sha:
        return False, "SHA256_MISMATCH", 400, {}

    clean_idemp = str(idempotency_key or "").strip()
    if not clean_idemp:
        clean_idemp = f"auto_{secrets.token_hex(16)}"

    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 1. RESERVE STABLE ID UNDER SQLITE TRANSACTION BEFORE SIDE EFFECT
    import bot
    conn = bot.db_connect()
    ensure_staged_upload_idempotency_schema(conn)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT upload_id, sha256, file_name, content_type, size_bytes, relative_path, state, created_at
            FROM staged_upload_idempotency
            WHERE actor_id = ? AND idempotency_key = ?
            """,
            (clean_actor, clean_idemp),
        ).fetchone()

        if row:
            ex_upload_id, ex_sha, ex_name, ex_mime, ex_size, ex_rel_path, ex_state, ex_created_at = row
            # Payload divergence check
            if (
                str(ex_sha).lower() != actual_sha
                or str(ex_name) != safe_name
                or str(ex_mime).lower() != clean_mime
            ):
                conn.commit()
                return False, "IDEMPOTENCY_CONFLICT", 409, {"message": "Idempotency key already exists with mismatched payload"}

            upload_id = ex_upload_id
            staging_dir = get_staging_directory()
            rel_path = ex_rel_path or f"{upload_id}/{safe_name}"
            dest_file = (staging_dir / rel_path).resolve()

            # If already finalized READY and physical file intact -> exact replay
            if str(ex_state).upper() == "READY" and dest_file.is_file():
                try:
                    if hashlib.sha256(dest_file.read_bytes()).hexdigest().lower() == actual_sha:
                        conn.commit()
                        record = {
                            "upload_id": upload_id,
                            "owner_id": clean_actor,
                            "file_name": safe_name,
                            "content_type": clean_mime,
                            "size_bytes": len(file_bytes),
                            "sha256": actual_sha,
                            "local_path": str(dest_file),
                            "idempotency_key": clean_idemp,
                            "created_at": ex_created_at,
                            "status": "staged",
                        }
                        _sync_legacy_system_settings(record)
                        return True, "OK", 200, to_public_metadata(record)
                except Exception as exc:
                    logger.warning(f"Error checking existing ready file: {exc}")

            # Crash recovery path: row was RESERVED or file missing. Re-use SAME upload_id!
            conn.commit()
        else:
            # Generate upload_id ONCE and insert RESERVED row
            upload_id = f"upl_{secrets.token_hex(16)}"
            rel_path = f"{upload_id}/{safe_name}"
            conn.execute(
                """
                INSERT INTO staged_upload_idempotency
                (actor_id, idempotency_key, upload_id, sha256, file_name, content_type, size_bytes, relative_path, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RESERVED', ?, ?)
                """,
                (clean_actor, clean_idemp, upload_id, actual_sha, safe_name, clean_mime, len(file_bytes), rel_path, now_utc, now_utc),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        # Concurrent race won by another connection
        try:
            conn.rollback()
        except Exception:
            pass
        row = conn.execute(
            """
            SELECT upload_id, sha256, file_name, content_type, size_bytes, relative_path, state, created_at
            FROM staged_upload_idempotency
            WHERE actor_id = ? AND idempotency_key = ?
            """,
            (clean_actor, clean_idemp),
        ).fetchone()
        if not row:
            conn.close()
            return False, "CONCURRENT_INSERT_RACE", 500, {}
        ex_upload_id, ex_sha, ex_name, ex_mime, ex_size, ex_rel_path, ex_state, ex_created_at = row
        if (
            str(ex_sha).lower() != actual_sha
            or str(ex_name) != safe_name
            or str(ex_mime).lower() != clean_mime
        ):
            conn.close()
            return False, "IDEMPOTENCY_CONFLICT", 409, {"message": "Idempotency key already exists with mismatched payload"}
        upload_id = ex_upload_id
        staging_dir = get_staging_directory()
        rel_path = ex_rel_path or f"{upload_id}/{safe_name}"
        dest_file = (staging_dir / rel_path).resolve()
        if str(ex_state).upper() == "READY" and dest_file.is_file():
            try:
                if hashlib.sha256(dest_file.read_bytes()).hexdigest().lower() == actual_sha:
                    conn.close()
                    record = {
                        "upload_id": upload_id,
                        "owner_id": clean_actor,
                        "file_name": safe_name,
                        "content_type": clean_mime,
                        "size_bytes": len(file_bytes),
                        "sha256": actual_sha,
                        "local_path": str(dest_file),
                        "idempotency_key": clean_idemp,
                        "created_at": ex_created_at,
                        "status": "staged",
                    }
                    _sync_legacy_system_settings(record)
                    return True, "OK", 200, to_public_metadata(record)
            except Exception:
                pass
    finally:
        conn.close()

    # 2. WRITE PHYSICAL BYTES TO DETERMINISTIC PATH
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
        # Check if file already written with correct SHA
        write_needed = True
        if dest_file.is_file():
            try:
                if hashlib.sha256(dest_file.read_bytes()).hexdigest().lower() == actual_sha:
                    write_needed = False
            except Exception:
                pass
        if write_needed:
            dest_file.write_bytes(file_bytes)
    except Exception as exc:
        logger.error(f"Failed to write staged upload bytes: {exc}")
        return False, f"STORAGE_WRITE_FAILED:{type(exc).__name__}", 500, {}

    # Verify physical file
    if hashlib.sha256(dest_file.read_bytes()).hexdigest().lower() != actual_sha:
        return False, "STORAGE_VERIFY_FAILED", 500, {}

    # 3. FINALIZE CANONICAL METADATA TO 'READY' STATE
    conn = bot.db_connect()
    try:
        conn.execute(
            """
            UPDATE staged_upload_idempotency
            SET state = 'READY',
                size_bytes = ?,
                relative_path = ?,
                updated_at = ?
            WHERE upload_id = ?
            """,
            (len(file_bytes), f"{upload_id}/{safe_name}", now_utc, upload_id),
        )
        conn.commit()
    except Exception as exc:
        logger.error(f"Failed to finalize staged_upload_idempotency to READY: {exc}")
        return False, f"DB_PERSISTENCE_FAILED:{type(exc).__name__}", 500, {}
    finally:
        conn.close()

    record = {
        "upload_id": upload_id,
        "owner_id": clean_actor,
        "file_name": safe_name,
        "content_type": clean_mime,
        "size_bytes": len(file_bytes),
        "sha256": actual_sha,
        "local_path": str(dest_file),
        "idempotency_key": clean_idemp,
        "created_at": now_utc,
        "status": "staged",
    }

    # 4. BEST-EFFORT SYNC TO LEGACY SYSTEM_SETTINGS (SECONDARY AUTHORITY)
    try:
        _sync_legacy_system_settings(record)
    except Exception as exc:
        logger.warning(f"Legacy system_settings sync failed (non-fatal): {exc}")

    # Return safe public metadata (no local_path)
    public_data = to_public_metadata(record)
    return True, "OK", 200, public_data


def get_staged_upload(upload_id: str, actor_id: str | int | None = None) -> tuple[bool, str, int, dict[str, Any]]:
    """Lookup and consume staged upload by upload_id, enforcing actor ownership.

    Reads from canonical staged_upload_idempotency table as PRIMARY authority.
    Falls back to system_settings for legacy backward compatibility.
    """
    clean_id = str(upload_id or "").strip()
    if not UPLOAD_ID_SAFE_CHARS.fullmatch(clean_id):
        return False, "INVALID_UPLOAD_ID", 400, {}

    clean_actor = ""
    if actor_id is not None:
        clean_actor = str(actor_id or "").strip()
        if clean_actor.startswith("telegram-"):
            clean_actor = clean_actor[len("telegram-"):].strip()

    # 1. PRIMARY AUTHORITY: staged_upload_idempotency
    try:
        import bot
        ensure_staged_upload_idempotency_schema()
        conn = bot.db_connect()
        try:
            row = conn.execute(
                """
                SELECT upload_id, actor_id, file_name, content_type, size_bytes, sha256, relative_path, state, created_at, idempotency_key
                FROM staged_upload_idempotency
                WHERE upload_id = ?
                LIMIT 1
                """,
                (clean_id,),
            ).fetchone()
        finally:
            conn.close()

        if row:
            row_uid, row_actor, row_name, row_mime, row_size, row_sha, row_rel_path, row_state, row_created, row_idemp = row
            if str(row_state).upper() != "READY":
                return False, "UPLOAD_NOT_READY", 404, {}
            if clean_actor and clean_actor != str(row_actor).strip():
                return False, "FORBIDDEN_CROSS_OWNER", 403, {}
            staging_dir = get_staging_directory()
            rel_path = row_rel_path or f"{clean_id}/{row_name}"
            dest_file = (staging_dir / rel_path).resolve()
            if not dest_file.is_file():
                return False, "STAGED_FILE_MISSING", 404, {}
            record = {
                "upload_id": row_uid,
                "owner_id": str(row_actor).strip(),
                "file_name": row_name,
                "content_type": row_mime,
                "size_bytes": int(row_size),
                "sha256": row_sha,
                "local_path": str(dest_file),
                "idempotency_key": row_idemp,
                "created_at": row_created,
                "status": "staged",
            }
            return True, "OK", 200, record
    except Exception as exc:
        logger.warning(f"Error querying primary staged_upload_idempotency for {clean_id}: {exc}")

    # 2. SECONDARY FALLBACK: system_settings (for legacy pre-FIX2 records)
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
    if clean_actor:
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
