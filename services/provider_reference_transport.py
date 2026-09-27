"""First-party ephemeral reference-image transport service.

Provides bounded, high-entropy capability references for third-party AI video providers
(such as Google Veo / ShopAIKey) to fetch input keyframes over HTTPS.

Invariants & Security Contracts:
1. Isolated storage root: dedicated directory under /opt/toanaas-storage/provider_refs.
2. No silent /tmp failover: production uses exact configured or canonical root; fails closed if unwritable.
3. Split root semantics: GET/HEAD resolution is purely read-only and never mutates storage root.
4. 256 bits entropy: tokens generated via secrets.token_urlsafe(32).
5. Zero external cloud storage dependencies (no S3, R2, GCS, Cloudinary, MinIO).
6. No filesystem path leak: paths are strictly isolated and never exposed.
7. Strict containment: path traversal, directory escape, and symlinks are strictly rejected.
8. Real image signature validation: verifies JPEG/PNG/WEBP magic bytes and extension consistency.
9. HTTPS-only external reference policy: external reference inputs must be public HTTPS; loopback/private IPs rejected.
10. Mandatory authoritative sidecar metadata: no sidecar -> no serve (404); strict field consistency.
11. Bounded TTL: default 7200s (2 hours), max 21600s (6 hours).
12. Fast-fail closed: missing or invalid images fail closed before provider submission (no charge).
13. Diagnostic isolation: capability tokens are never leaked into ordinary logs/diagnostics.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
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
ALLOWED_MIME_TYPES = set(EXTENSION_MIME_MAP.values())

TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,128}(\.(jpg|jpeg|png|webp))?$")

# Magic byte signatures
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WEBP_RIFF = b"RIFF"
WEBP_MAGIC = b"WEBP"


def reference_storage_root(env: Mapping[str, str] | None = None) -> Path:
    """Returns the configured or default storage root path without performing any filesystem mutation.
    
    Used by resolution/GET/HEAD paths. Does NOT create directories, touch probe files,
    or silently fall back to /tmp.
    """
    env_data = env if env is not None else os.environ
    configured = str(env_data.get("PROVIDER_REFERENCE_STORAGE_DIR") or "").strip()
    if configured:
        return Path(configured)
    return Path(DEFAULT_PROVIDER_REFERENCE_STORAGE_DIR)


def ensure_reference_storage_writable(env: Mapping[str, str] | None = None) -> Path:
    """Ensures the authoritative storage root exists and is writable for publication.

    Used ONLY in the preparation path. Never silently falls back to /tmp.
    Fails closed if the directory cannot be created or written safely.
    """
    from providers.video_generic_http_provider import VideoProviderContractError

    root = reference_storage_root(env)
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / f".probe_{secrets.token_hex(4)}"
        probe.touch()
        probe.unlink()
        return root
    except Exception as exc:
        raise VideoProviderContractError(
            "shopaikey_veo_i2v_public_reference_unavailable_no_charge",
            stage="payload_build",
            debug={
                "blocker": "shopaikey_veo_i2v_public_reference_unavailable_no_charge",
                "reason": "storage_root_unwritable",
                "error": type(exc).__name__,
                "no_charge": True,
            },
        ) from exc


def validate_base_url(base_url: str) -> tuple[bool, str]:
    """Validates that a provider reference base URL is an authoritative, public HTTPS URL.

    Rejects insecure HTTP, credentials, fragments, queries, localhost, and private IPs.
    """
    cleaned = str(base_url or "").strip()
    if not cleaned:
        return False, "base_url_empty"

    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme != "https":
        return False, "base_url_scheme_not_https"

    if "@" in parsed.netloc or parsed.username or parsed.password:
        return False, "base_url_credentials_forbidden"

    if parsed.query or parsed.fragment:
        return False, "base_url_query_or_fragment_forbidden"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "base_url_invalid_host"

    if host in {"localhost", "0.0.0.0", "127.0.0.1", "::1", "::"}:
        return False, "base_url_localhost_forbidden"

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False, "base_url_private_ip_forbidden"
    except ValueError:
        pass

    path = parsed.path.rstrip("/")
    if not path:
        return False, "base_url_path_missing"

    return True, ""


def get_base_url(env: Mapping[str, str] | None = None) -> str:
    """Returns the validated base HTTPS URL under which provider references are exposed.

    Fails closed if the configured base URL fails validation.
    """
    from providers.video_generic_http_provider import VideoProviderContractError

    env_data = env if env is not None else os.environ
    configured = str(env_data.get("PROVIDER_REFERENCE_BASE_URL") or "").strip()
    url = configured if configured else DEFAULT_PROVIDER_REFERENCE_BASE_URL
    valid, reason = validate_base_url(url)
    if not valid:
        raise VideoProviderContractError(
            "shopaikey_veo_i2v_public_reference_unavailable_no_charge",
            stage="payload_build",
            debug={
                "blocker": "shopaikey_veo_i2v_public_reference_unavailable_no_charge",
                "reason": f"invalid_base_url:{reason}",
                "no_charge": True,
            },
        )
    return url.rstrip("/")


def validate_external_reference_url(url: str) -> tuple[bool, str]:
    """Validates an externally supplied reference URL under strict HTTPS policy.

    Rejects:
    - insecure http://
    - file://, data:
    - localhost, 127.0.0.1, ::1, 0.0.0.0
    - private, link-local, or loopback IP literals
    - embedded credentials (user:pass@host)
    - empty or malformed hostnames
    """
    cleaned = str(url or "").strip()
    if not cleaned:
        return False, "provider_image_external_url_empty"

    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme == "http":
        return False, "provider_image_external_url_insecure_http_rejected"

    if parsed.scheme != "https":
        return False, "provider_image_external_url_unsupported_scheme"

    if "@" in parsed.netloc or parsed.username or parsed.password:
        return False, "provider_image_external_url_credentials_forbidden"

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "provider_image_external_url_invalid_host"

    if host in {"localhost", "0.0.0.0", "127.0.0.1", "::1", "::"}:
        return False, "provider_image_external_url_localhost_rejected"

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False, "provider_image_external_url_private_ip_rejected"
    except ValueError:
        pass

    return True, ""


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


def detect_image_format_signature(header: bytes) -> str | None:
    """Determines canonical image format from magic byte signature."""
    if len(header) >= 3 and header.startswith(JPEG_MAGIC):
        return ".jpg"
    if len(header) >= 8 and header.startswith(PNG_MAGIC):
        return ".png"
    if len(header) >= 12 and header.startswith(WEBP_RIFF) and header[8:12] == WEBP_MAGIC:
        return ".webp"
    return None


def validate_image_file(path: str | Path, *, max_bytes: int = MAX_PROVIDER_REFERENCE_IMAGE_BYTES) -> tuple[bool, str, str, int]:
    """Validates an image file with deterministic magic byte signature verification.

    Verifies:
    1. File existence and regular file check.
    2. Non-zero byte length.
    3. Size within max_bytes limit.
    4. Allowed extension (.jpg, .jpeg, .png, .webp).
    5. Real magic byte signature matching the declared extension.

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

    try:
        with open(target, "rb") as f:
            header = f.read(32)
    except Exception:
        return False, "provider_image_input_missing_or_invalid", "", size

    detected_ext = detect_image_format_signature(header)
    if not detected_ext:
        return False, "provider_image_signature_mismatch", "", size

    # Suffix vs signature consistency
    canonical_suffix = ".jpg" if suffix in {".jpg", ".jpeg"} else suffix
    if detected_ext != canonical_suffix:
        return False, "provider_image_signature_mismatch", "", size

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
    
    Guarantees:
    - Real image signature validation (magic bytes).
    - Authoritative, durable sidecar metadata (.meta.json).
    - If metadata write fails, the copied image is deleted and execution fails closed.
    - Opportunistic sweep of expired tokens.
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

    base_url = get_base_url(env)
    storage_root = ensure_reference_storage_writable(env)

    # Opportunistic bounded sweep of expired references before materialization
    try:
        cleanup_expired_provider_references(env, max_items=20)
    except Exception:
        pass

    src_path = Path(local_path)
    ext = src_path.suffix.lower() if src_path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS else ".jpg"

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

    # Strict metadata persistence requirement: failure deletes image and fails closed
    try:
        meta_path.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        raise VideoProviderContractError(
            "shopaikey_veo_i2v_public_reference_unavailable_no_charge",
            stage="payload_build",
            debug={
                "provider": provider,
                "blocker": "shopaikey_veo_i2v_public_reference_unavailable_no_charge",
                "reason": "metadata_write_failed",
                "error": type(exc).__name__,
                "no_charge": True,
            },
        ) from exc

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
    
    Enforces strict read-only security checks:
    - Root existence: does NOT create directories or touch probe files; 404 if absent.
    - Token regex match: only alphanumeric, hyphen, underscore, optional image extension.
    - Path traversal rejection: no '../', '\\', '%2e', or absolute paths.
    - Symlink rejection: symlinks inside storage root are strictly rejected.
    - Containment: resolved path must be directly inside storage root.
    - Authoritative sidecar metadata MANDATORY: missing, corrupt, or inconsistent metadata -> 404.
    - Expiration check: returns 404 if TTL has passed.
    - Size and MIME consistency against metadata.
    """
    clean_token = str(token_str or "").strip()
    if not clean_token or len(clean_token) > 150:
        return {"ok": False, "status_code": 404, "reason": "token_invalid"}

    # Defense against traversal and strange characters
    if not TOKEN_PATTERN.match(clean_token):
        return {"ok": False, "status_code": 404, "reason": "token_format_rejected"}

    if any(delim in clean_token for delim in ("/", "\\", "..", "%", "\x00")):
        return {"ok": False, "status_code": 404, "reason": "path_traversal_blocked"}

    # Read-only root check (never mutates filesystem)
    root = reference_storage_root(env)
    if not root.exists() or not root.is_dir():
        return {"ok": False, "status_code": 404, "reason": "storage_root_missing"}

    storage_root = root.resolve()

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
        if not str(candidate_path).startswith(str(storage_root)):
            return {"ok": False, "status_code": 404, "reason": "path_containment_breach"}

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

    # Sidecar metadata is AUTHORITATIVE and MANDATORY
    meta_path = storage_root / f"{stem_token}.meta.json"
    if not meta_path.exists() or meta_path.is_symlink() or not meta_path.is_file():
        return {"ok": False, "status_code": 404, "reason": "metadata_missing"}

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "status_code": 404, "reason": "metadata_corrupt"}

    if not isinstance(meta, dict):
        return {"ok": False, "status_code": 404, "reason": "metadata_invalid"}

    # Strict metadata consistency check
    if str(meta.get("token") or "") != stem_token:
        return {"ok": False, "status_code": 404, "reason": "metadata_token_mismatch"}

    if str(meta.get("filename") or "") != candidate_path.name:
        return {"ok": False, "status_code": 404, "reason": "metadata_filename_mismatch"}

    mime_type = str(meta.get("mime_type") or "")
    if mime_type not in ALLOWED_MIME_TYPES:
        return {"ok": False, "status_code": 404, "reason": "metadata_mime_unsupported"}

    try:
        created_at = float(meta.get("created_at") or 0.0)
        expires_at = float(meta.get("expires_at") or 0.0)
    except (ValueError, TypeError):
        return {"ok": False, "status_code": 404, "reason": "metadata_timestamp_invalid"}

    if created_at <= 0 or expires_at <= created_at:
        return {"ok": False, "status_code": 404, "reason": "metadata_timestamp_inconsistent"}

    current_time = now if now is not None else time.time()
    if current_time > expires_at:
        return {"ok": False, "status_code": 404, "reason": "token_expired"}

    size = candidate_path.stat().st_size
    expected_size = meta.get("file_size")
    if expected_size is not None and int(expected_size) != size:
        return {"ok": False, "status_code": 404, "reason": "file_size_mismatch"}

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

    if "://" in val:
        parsed = urllib.parse.urlsplit(val)
        val = Path(parsed.path).name

    stem = val
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break

    if not TOKEN_PATTERN.match(stem):
        return False

    root = reference_storage_root(env)
    if not root.exists():
        return False
    storage_root = root.resolve()
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


def cleanup_provider_image_references_for_job(job_id: str, env: Mapping[str, str] | None = None) -> int:
    """Cleans up all references associated with a specific job_id upon terminal completion."""
    target_job = str(job_id or "").strip()
    if not target_job:
        return 0

    root = reference_storage_root(env)
    if not root.exists() or not root.is_dir():
        return 0

    storage_root = root.resolve()
    cleaned_count = 0

    try:
        for meta_file in storage_root.glob("*.meta.json"):
            if meta_file.is_symlink():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if str(meta.get("job_id") or "").strip() == target_job:
                    token = meta.get("token") or meta_file.stem
                    if cleanup_provider_image_reference(token, env=env):
                        cleaned_count += 1
            except Exception:
                continue
    except Exception:
        pass

    return cleaned_count


def cleanup_expired_provider_references(
    env: Mapping[str, str] | None = None,
    *,
    now: float | None = None,
    max_items: int = 100,
) -> int:
    """Sweeps the reference storage directory and deletes expired items.
    
    Returns the count of purged items.
    """
    root = reference_storage_root(env)
    if not root.exists() or not root.is_dir():
        return 0

    storage_root = root.resolve()
    current_time = now if now is not None else time.time()
    purged_count = 0

    # Pass 1: scan .meta.json files
    try:
        for meta_file in storage_root.glob("*.meta.json"):
            if purged_count >= max_items:
                break
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
            if purged_count >= max_items:
                break
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
