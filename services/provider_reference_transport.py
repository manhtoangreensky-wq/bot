"""First-party ephemeral reference-image transport service.

Provides bounded, high-entropy capability references for third-party AI video providers
(such as Google Veo / ShopAIKey) to fetch input keyframes over HTTPS.

Invariants:
1. Isolated storage root: dedicated directory under /opt/toanaas-storage/provider_refs.
2. 256 bits entropy: tokens generated via secrets.token_urlsafe(32).
3. Zero external cloud storage dependencies (no S3, R2, GCS, Cloudinary, MinIO).
4. No filesystem path leak: paths are strictly isolated and never sent to external providers.
5. Strict containment: path traversal, directory escape, and symlinks are strictly rejected.
6. Safe MIME validation: only image/jpeg, image/png, and image/webp allowed.
7. Bounded TTL: default 7200s (2 hours), max 21600s (6 hours).
8. Fast-fail closed: missing or invalid images fail closed before provider submission (no charge).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_REFERENCE_STORAGE_DIR = "/opt/toanaas-storage/provider_refs"
DEFAULT_PROVIDER_REFERENCE_BASE_URL = "https://toanaas.vn/provider-media/v1"
DEFAULT_PROVIDER_REFERENCE_TTL_SECONDS = 7200  # 2 hours
MIN_PROVIDER_REFERENCE_TTL_SECONDS = 60  # 1 minute
MAX_PROVIDER_REFERENCE_TTL_SECONDS = 21600  # 6 hours
MAX_PROVIDER_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
EXTENSION_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
MIME_EXTENSION_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,128}(\.(jpg|jpeg|png|webp))?$")


def get_storage_root(env: Mapping[str, str] | None = None) -> Path:
    """Returns the authoritative storage root for provider references.
    
    If the default production directory /opt/toanaas-storage/provider_refs
    is not accessible or not writable (e.g. running unit tests or in local dev),
    falls back cleanly to a dedicated temporary folder.
    """
    env_data = env if env is not None else os.environ
    configured = str(env_data.get("PROVIDER_REFERENCE_STORAGE_DIR") or "").strip()
    if configured:
        target = Path(configured)
        target.mkdir(parents=True, exist_ok=True)
        return target

    default_target = Path(DEFAULT_PROVIDER_REFERENCE_STORAGE_DIR)
    try:
        default_target.mkdir(parents=True, exist_ok=True)
        test_file = default_target / f".probe_{secrets.token_hex(4)}"
        test_file.touch()
        test_file.unlink()
        return default_target
    except Exception:
        fallback = Path(tempfile.gettempdir()) / "toanaas_provider_refs"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def get_base_url(env: Mapping[str, str] | None = None) -> str:
    """Returns the base HTTPS URL under which provider references are exposed."""
    env_data = env if env is not None else os.environ
    configured = str(env_data.get("PROVIDER_REFERENCE_BASE_URL") or "").strip()
    if configured:
        return configured.rstrip("/")
    return DEFAULT_PROVIDER_REFERENCE_BASE_URL.rstrip("/")


def get_ttl_seconds(env: Mapping[str, str] | None = None, override: int | None = None) -> int:
    """Returns clamped TTL in seconds."""
    if override is not None:
        try:
            val = int(override)
            return max(MIN_PROVIDER_REFERENCE_TTL_SECONDS, min(MAX_PROVIDER_REFERENCE_TTL_SECONDS, val))
        except (ValueError, TypeError):
            pass
    env_data = env if env is not None else os.environ
    raw = env_data.get("PROVIDER_REFERENCE_TTL_SECONDS")
    if raw is not None:
        try:
            val = int(raw)
            return max(MIN_PROVIDER_REFERENCE_TTL_SECONDS, min(MAX_PROVIDER_REFERENCE_TTL_SECONDS, val))
        except (ValueError, TypeError):
            pass
    return DEFAULT_PROVIDER_REFERENCE_TTL_SECONDS


def compute_file_sha256(path: Path) -> str:
    """Computes SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_image_file(path: str | Path, *, max_bytes: int = MAX_PROVIDER_REFERENCE_IMAGE_BYTES) -> tuple[bool, str, str, int]:
    """Validates an image file for reference transport.
    
    Returns:
        (ok, error_code, mime_type, file_size)
    """
    target = Path(path)
    try:
        if not target.is_file():
            return False, "provider_image_input_missing_or_invalid", "", 0
    except Exception:
        return False, "provider_image_input_missing_or_invalid", "", 0

    suffix = target.suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        return False, "provider_image_extension_unsupported", "", 0

    try:
        size = target.stat().st_size
    except Exception:
        return False, "provider_image_input_missing_or_invalid", "", 0

    if size <= 0:
        return False, "provider_image_input_empty", "", 0

    if size > max_bytes:
        return False, "provider_image_input_too_large", "", size

    mime_type = EXTENSION_MIME_MAP.get(suffix, "image/jpeg")
    return True, "", mime_type, size


def prepare_provider_image_reference(
    local_path: str | Path,
    *,
    provider: str = "shopaikey_video",
    purpose: str = "image_to_video",
    job_id: str = "",
    ttl_seconds: int | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Materializes a local image into the first-party provider reference transport.
    
    Allocates a 256-bit URL-safe token, copies the image into the isolated storage root,
    and returns metadata including the reachable HTTPS URL.
    
    Fails closed if the image is missing, empty, oversized, or unsupported.
    """
    from providers.video_generic_http_provider import VideoProviderContractError

    ok, error_code, mime_type, file_size = validate_image_file(local_path)
    if not ok:
        raise VideoProviderContractError(
            error_code,
            stage="payload_build",
            debug={
                "provider": provider,
                "blocker": error_code,
                "purpose": purpose,
                "file_size": file_size,
                "no_charge": True,
            },
        )

    src_path = Path(local_path)
    ext = src_path.suffix.lower() if src_path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS else ".jpg"
    storage_root = get_storage_root(env)

    # 256-bit high-entropy token (32 bytes = 43 URL-safe characters)
    token = secrets.token_urlsafe(32)
    filename = f"{token}{ext}"
    dest_path = storage_root / filename

    try:
        shutil.copyfile(str(src_path), str(dest_path))
    except Exception as exc:
        raise VideoProviderContractError(
            "shopaikey_veo_i2v_public_reference_unavailable_no_charge",
            stage="payload_build",
            debug={
                "provider": provider,
                "blocker": "shopaikey_veo_i2v_public_reference_unavailable_no_charge",
                "error": type(exc).__name__,
                "no_charge": True,
            },
        ) from exc

    sha256_hash = compute_file_sha256(dest_path)
    now = time.time()
    ttl = get_ttl_seconds(env, override=ttl_seconds)
    expires_at = now + ttl
    base_url = get_base_url(env)
    public_url = f"{base_url}/{filename}"

    meta_payload = {
        "token": token,
        "filename": filename,
        "provider": str(provider or "").strip(),
        "purpose": str(purpose or "").strip(),
        "job_id": str(job_id or "").strip(),
        "mime_type": mime_type,
        "file_size": file_size,
        "sha256": sha256_hash,
        "created_at": now,
        "expires_at": expires_at,
        "ttl_seconds": ttl,
        "public_url": public_url,
    }
    meta_path = storage_root / f"{token}.meta.json"
    try:
        meta_path.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {
        "ok": True,
        "token": token,
        "filename": filename,
        "file_path": str(dest_path),
        "public_url": public_url,
        "mime_type": mime_type,
        "file_size": file_size,
        "sha256": sha256_hash,
        "created_at": now,
        "expires_at": expires_at,
        "ttl_seconds": ttl,
    }


def resolve_provider_reference(
    token_str: str,
    env: Mapping[str, str] | None = None,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """Resolves and validates a provider capability token for serving.
    
    Enforces strict security checks:
    - Token regex match: only alphanumeric, hyphen, underscore, optional image extension.
    - Path traversal rejection: no '../', '\\', '%2e', or absolute paths.
    - Symlink rejection: symlinks inside storage root are strictly rejected.
    - Containment: resolved path must be directly inside storage root.
    - Expiration check: returns 404 if TTL has passed.
    - Extension / MIME safety: only allowed image types.
    """
    clean_token = str(token_str or "").strip()
    if not clean_token or len(clean_token) > 150:
        return {"ok": False, "status_code": 404, "reason": "token_invalid"}

    # Defense against traversal and strange characters
    if not TOKEN_PATTERN.match(clean_token):
        return {"ok": False, "status_code": 404, "reason": "token_format_rejected"}

    if any(delim in clean_token for delim in ("/", "\\", "..", "%", "\x00")):
        return {"ok": False, "status_code": 404, "reason": "path_traversal_blocked"}

    storage_root = get_storage_root(env).resolve()

    raw_path = storage_root / clean_token
    if raw_path.is_symlink():
        return {"ok": False, "status_code": 404, "reason": "symlink_rejected"}

    # If extension omitted, probe for candidate with extension
    if not raw_path.exists():
        found = False
        for ext in ALLOWED_IMAGE_EXTENSIONS:
            probe = storage_root / f"{clean_token}{ext}"
            if probe.is_symlink():
                return {"ok": False, "status_code": 404, "reason": "symlink_rejected"}
            if probe.exists():
                raw_path = probe
                found = True
                break
        if not found:
            return {"ok": False, "status_code": 404, "reason": "file_not_found"}

    candidate_path = raw_path.resolve()

    # Strict containment check
    try:
        if not candidate_path.is_relative_to(storage_root):
            return {"ok": False, "status_code": 404, "reason": "path_containment_breach"}
    except AttributeError:
        # Compatibility fallback
        if not str(candidate_path).startswith(str(storage_root)):
            return {"ok": False, "status_code": 404, "reason": "path_containment_breach"}

    # Symlink rejection
    if candidate_path.is_symlink():
        return {"ok": False, "status_code": 404, "reason": "symlink_rejected"}

    if not candidate_path.is_file():
        return {"ok": False, "status_code": 404, "reason": "not_a_regular_file"}

    # Extract base token without extension
    stem_token = candidate_path.name
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        if stem_token.endswith(ext):
            stem_token = stem_token[: -len(ext)]
            break

    # Read sidecar metadata for TTL and MIME verification
    meta_path = storage_root / f"{stem_token}.meta.json"
    expires_at = 0.0
    mime_type = EXTENSION_MIME_MAP.get(candidate_path.suffix.lower(), "image/jpeg")

    current_time = now if now is not None else time.time()

    if meta_path.exists() and not meta_path.is_symlink():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            expires_at = float(meta.get("expires_at") or 0.0)
            if meta.get("mime_type"):
                mime_type = str(meta["mime_type"])
        except Exception:
            pass

    # Expiry verification
    if expires_at > 0 and current_time > expires_at:
        return {"ok": False, "status_code": 404, "reason": "token_expired"}

    # If no metadata sidecar exists, check file modification time against max TTL
    if expires_at <= 0:
        try:
            mtime = candidate_path.stat().st_mtime
            if current_time - mtime > MAX_PROVIDER_REFERENCE_TTL_SECONDS:
                return {"ok": False, "status_code": 404, "reason": "token_expired_stat"}
        except Exception:
            pass

    size = candidate_path.stat().st_size
    if size <= 0 or size > MAX_PROVIDER_REFERENCE_IMAGE_BYTES:
        return {"ok": False, "status_code": 404, "reason": "invalid_file_size"}

    return {
        "ok": True,
        "status_code": 200,
        "token": stem_token,
        "path": candidate_path,
        "mime_type": mime_type,
        "file_size": size,
    }


def cleanup_provider_image_reference(reference_id_or_url: str, env: Mapping[str, str] | None = None) -> bool:
    """Removes a materialized provider reference and its sidecar metadata safely."""
    val = str(reference_id_or_url or "").strip()
    if not val:
        return False

    # If full URL passed, parse filename
    if "://" in val:
        parsed = urllib.parse.urlsplit(val)
        val = Path(parsed.path).name

    # Sanitize token
    stem = val
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break

    if not TOKEN_PATTERN.match(stem):
        return False

    storage_root = get_storage_root(env).resolve()
    cleaned = False

    for ext in ALLOWED_IMAGE_EXTENSIONS:
        target = (storage_root / f"{stem}{ext}").resolve()
        try:
            if target.is_relative_to(storage_root) and target.is_file() and not target.is_symlink():
                target.unlink(missing_ok=True)
                cleaned = True
        except Exception:
            pass

    meta_target = (storage_root / f"{stem}.meta.json").resolve()
    try:
        if meta_target.is_relative_to(storage_root) and meta_target.is_file() and not meta_target.is_symlink():
            meta_target.unlink(missing_ok=True)
            cleaned = True
    except Exception:
        pass

    return cleaned


def cleanup_expired_provider_references(
    env: Mapping[str, str] | None = None,
    *,
    now: float | None = None,
) -> int:
    """Sweeps the reference storage directory and deletes expired items.
    
    Returns the count of purged items.
    """
    storage_root = get_storage_root(env).resolve()
    if not storage_root.exists() or not storage_root.is_dir():
        return 0

    current_time = now if now is not None else time.time()
    purged_count = 0

    # Pass 1: scan .meta.json files
    try:
        for meta_file in storage_root.glob("*.meta.json"):
            if meta_file.is_symlink():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                expires_at = float(meta.get("expires_at") or 0.0)
                if expires_at > 0 and current_time > expires_at:
                    token = meta.get("token") or meta_file.stem
                    cleanup_provider_image_reference(token, env=env)
                    purged_count += 1
            except Exception:
                continue
    except Exception:
        pass

    # Pass 2: scan orphaned image files older than MAX_PROVIDER_REFERENCE_TTL_SECONDS
    try:
        for item in storage_root.iterdir():
            if item.is_file() and not item.is_symlink() and item.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS:
                try:
                    if current_time - item.stat().st_mtime > MAX_PROVIDER_REFERENCE_TTL_SECONDS:
                        item.unlink(missing_ok=True)
                        purged_count += 1
                except Exception:
                    pass
    except Exception:
        pass

    return purged_count
