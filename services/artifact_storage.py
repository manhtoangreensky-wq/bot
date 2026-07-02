"""Artifact storage backend for TOAN AAS generated media.

The module keeps Railway lightweight by allowing generated artifacts to be
stored on a VPS while preserving the local backend as the default behavior.
Secrets and internal host names are never included in public metadata.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


ARTIFACT_SAFE_EXTENSIONS = {
    ".aac",
    ".ass",
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".png",
    ".srt",
    ".tmp",
    ".txt",
    ".vtt",
    ".wav",
    ".webm",
    ".webp",
    ".zip",
}
HEAVY_PRODUCT_AREAS = {"worker_results", "artifacts", "tmp", "music", "subdub", "video", "cache"}
REMOTE_BACKENDS = {"vps_sftp", "vps_http"}


@dataclass(frozen=True)
class ArtifactStorageConfig:
    backend: str = "local"
    vps_host: str = ""
    vps_port: int = 22
    vps_user: str = "toanaas"
    vps_base_dir: str = "/opt/toanaas-storage"
    vps_ssh_key_path: str = ""
    public_base_url: str = ""
    ttl_hours: int = 24
    tmp_ttl_hours: int = 6
    max_mb: int = 1024

    @property
    def is_remote(self) -> bool:
        return self.backend in REMOTE_BACKENDS


def config_from_env(env: Mapping[str, str] | None = None) -> ArtifactStorageConfig:
    data = env or os.environ
    return ArtifactStorageConfig(
        backend=str(data.get("ARTIFACT_STORAGE_BACKEND") or "local").strip().lower() or "local",
        vps_host=str(data.get("ARTIFACT_VPS_HOST") or "").strip(),
        vps_port=_safe_int(data.get("ARTIFACT_VPS_PORT"), 22),
        vps_user=str(data.get("ARTIFACT_VPS_USER") or "toanaas").strip() or "toanaas",
        vps_base_dir=str(data.get("ARTIFACT_VPS_BASE_DIR") or "/opt/toanaas-storage").strip() or "/opt/toanaas-storage",
        vps_ssh_key_path=str(data.get("ARTIFACT_VPS_SSH_KEY_PATH") or "").strip(),
        public_base_url=str(data.get("ARTIFACT_PUBLIC_BASE_URL") or "").strip(),
        ttl_hours=max(1, _safe_int(data.get("ARTIFACT_TTL_HOURS"), 24)),
        tmp_ttl_hours=max(1, _safe_int(data.get("ARTIFACT_TMP_TTL_HOURS"), 6)),
        max_mb=max(1, _safe_int(data.get("ARTIFACT_MAX_MB"), 1024)),
    )


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _sanitize_component(value: object, fallback: str = "artifact") -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip())[:120]
    clean = clean.strip(".-")
    while ".." in clean:
        clean = clean.replace("..", ".")
    return clean or fallback


def safe_product_area(value: object) -> str:
    area = _sanitize_component(value, "artifacts").lower()
    return area if area in HEAVY_PRODUCT_AREAS else "artifacts"


def artifact_sha256(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifact_file(path: str | os.PathLike[str], *, max_mb: int = 1024) -> dict:
    target = Path(path)
    if not target.exists() or not target.is_file():
        return {"ok": False, "reason": "artifact_missing"}
    size = int(target.stat().st_size)
    if size <= 0:
        return {"ok": False, "reason": "artifact_empty"}
    if size > int(max_mb) * 1024 * 1024:
        return {"ok": False, "reason": "artifact_too_large", "size": size}
    suffix = target.suffix.lower()
    if suffix not in ARTIFACT_SAFE_EXTENSIONS:
        return {"ok": False, "reason": "artifact_extension_blocked", "extension": suffix}
    return {"ok": True, "size": size, "extension": suffix}


def build_remote_path(
    local_path: str | os.PathLike[str],
    *,
    config: ArtifactStorageConfig,
    product_area: str = "artifacts",
    job_id: int | str = "",
    now: float | None = None,
) -> str:
    timestamp = time.strftime("%Y%m%d", time.gmtime(now or time.time()))
    area = safe_product_area(product_area)
    job_part = f"job_{_sanitize_component(job_id, 'general')}" if str(job_id or "").strip() else "general"
    filename = _sanitize_component(Path(local_path).name, "artifact.bin")
    base = str(config.vps_base_dir or "/opt/toanaas-storage").replace("\\", "/").rstrip("/")
    return posixpath.normpath(posixpath.join(base, area, timestamp, job_part, filename))


def public_url_for_remote_path(config: ArtifactStorageConfig, remote_path: str) -> str:
    base_url = str(config.public_base_url or "").strip().rstrip("/")
    if not base_url:
        return ""
    base_dir = str(config.vps_base_dir or "/opt/toanaas-storage").replace("\\", "/").rstrip("/")
    remote = str(remote_path or "").replace("\\", "/")
    if remote.startswith(base_dir + "/"):
        relative = remote[len(base_dir) + 1 :]
    else:
        relative = remote.lstrip("/")
    safe_parts = [urllib.parse.quote(part) for part in relative.split("/") if part]
    return "/".join([base_url, *safe_parts]) if safe_parts else base_url


def _upload_vps_sftp(local_path: str, remote_path: str, config: ArtifactStorageConfig) -> dict:
    try:
        import paramiko  # type: ignore
    except Exception:
        return {"ok": False, "reason": "paramiko_missing"}
    if not config.vps_host or not config.vps_user or not config.vps_ssh_key_path:
        return {"ok": False, "reason": "vps_sftp_config_missing"}
    transport = None
    sftp = None
    try:
        key = paramiko.RSAKey.from_private_key_file(config.vps_ssh_key_path)
        transport = paramiko.Transport((config.vps_host, int(config.vps_port)))
        transport.connect(username=config.vps_user, pkey=key)
        sftp = paramiko.SFTPClient.from_transport(transport)
        current = ""
        for part in str(posixpath.dirname(remote_path)).split("/"):
            if not part:
                current = "/"
                continue
            current = posixpath.join(current, part)
            try:
                sftp.mkdir(current)
            except Exception:
                pass
        sftp.put(local_path, remote_path)
        return {"ok": True, "remote_path": remote_path}
    except Exception as exc:
        return {"ok": False, "reason": f"vps_sftp_upload_failed:{type(exc).__name__}"}
    finally:
        try:
            if sftp:
                sftp.close()
        finally:
            if transport:
                transport.close()


def store_artifact(
    local_path: str | os.PathLike[str],
    *,
    config: ArtifactStorageConfig | None = None,
    product_area: str = "artifacts",
    job_id: int | str = "",
    delete_local_after_upload: bool = False,
    uploader: Callable[[str, str, ArtifactStorageConfig], dict] | None = None,
    now: float | None = None,
) -> dict:
    cfg = config or config_from_env()
    validation = validate_artifact_file(local_path, max_mb=cfg.max_mb)
    if not validation.get("ok"):
        return {"ok": False, "backend": cfg.backend, **validation}
    target = Path(local_path)
    remote_path = ""
    public_url = ""
    uploaded = False
    if cfg.backend == "local":
        reason = "local_backend"
    elif cfg.backend == "vps_sftp":
        remote_path = build_remote_path(target, config=cfg, product_area=product_area, job_id=job_id, now=now)
        upload_result = (uploader or _upload_vps_sftp)(str(target), remote_path, cfg)
        if not upload_result.get("ok"):
            return {"ok": False, "backend": cfg.backend, **upload_result}
        remote_path = str(upload_result.get("remote_path") or remote_path)
        public_url = public_url_for_remote_path(cfg, remote_path)
        uploaded = True
        reason = "vps_sftp_uploaded"
    elif cfg.backend == "vps_http":
        remote_path = build_remote_path(target, config=cfg, product_area=product_area, job_id=job_id, now=now)
        if not uploader:
            return {"ok": False, "backend": cfg.backend, "reason": "vps_http_uploader_missing"}
        upload_result = uploader(str(target), remote_path, cfg)
        if not upload_result.get("ok"):
            return {"ok": False, "backend": cfg.backend, **upload_result}
        remote_path = str(upload_result.get("remote_path") or remote_path)
        public_url = str(upload_result.get("public_url") or public_url_for_remote_path(cfg, remote_path))
        uploaded = True
        reason = "vps_http_uploaded"
    else:
        return {"ok": False, "backend": cfg.backend, "reason": "artifact_backend_unsupported"}

    size = int(validation.get("size") or 0)
    digest = artifact_sha256(target)
    original_local_path = str(target)
    if uploaded and delete_local_after_upload:
        try:
            target.unlink()
        except OSError:
            return {"ok": False, "backend": cfg.backend, "reason": "local_cleanup_after_upload_failed"}
    local_available = target.exists()
    return {
        "ok": True,
        "backend": cfg.backend,
        "product_area": safe_product_area(product_area),
        "job_id": str(job_id or ""),
        "local_path": original_local_path if local_available else "",
        "original_local_path": original_local_path,
        "remote_path": remote_path,
        "public_url": public_url,
        "artifact_size": size,
        "artifact_hash": digest,
        "uploaded_at": int(now or time.time()),
        "expires_at": int((now or time.time()) + max(1, cfg.ttl_hours) * 3600),
        "local_deleted_after_upload": bool(uploaded and delete_local_after_upload and not local_available),
        "uploaded": bool(uploaded),
        "recoverable": bool(local_available or public_url or remote_path),
        "reason": reason,
    }


def public_metadata(metadata: Mapping[str, object] | None = None) -> dict:
    raw = dict(metadata or {})
    return {
        "backend": raw.get("backend") or "",
        "product_area": raw.get("product_area") or "",
        "job_id": raw.get("job_id") or "",
        "public_url": raw.get("public_url") or "",
        "artifact_size": int(raw.get("artifact_size") or 0),
        "artifact_hash": raw.get("artifact_hash") or "",
        "uploaded_at": int(raw.get("uploaded_at") or 0),
        "expires_at": int(raw.get("expires_at") or 0),
        "recoverable": bool(raw.get("recoverable")),
    }


def delivery_reference(metadata: Mapping[str, object] | None = None) -> dict:
    raw = dict(metadata or {})
    local_path = str(raw.get("local_path") or "")
    if local_path and Path(local_path).exists():
        return {"ok": True, "kind": "local_path", "value": local_path}
    public_url = str(raw.get("public_url") or "")
    if public_url:
        return {"ok": True, "kind": "public_url", "value": public_url}
    remote_path = str(raw.get("remote_path") or "")
    if remote_path:
        return {"ok": True, "kind": "remote_path", "value": remote_path}
    return {"ok": False, "reason": "artifact_not_recoverable"}


def recover_artifact_to_temp(
    metadata: Mapping[str, object] | None,
    *,
    temp_dir: str | os.PathLike[str] | None = None,
    downloader: Callable[[str, str], None] | None = None,
) -> dict:
    ref = delivery_reference(metadata)
    if not ref.get("ok"):
        return ref
    if ref["kind"] == "local_path":
        return {"ok": True, "path": ref["value"], "temporary": False}
    if ref["kind"] != "public_url":
        return {"ok": False, "reason": "remote_download_not_configured"}
    filename = _sanitize_component(Path(urllib.parse.urlparse(ref["value"]).path).name, "artifact.bin")
    target_dir = Path(temp_dir or tempfile.gettempdir())
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    if downloader:
        downloader(str(ref["value"]), str(target))
    else:
        with urllib.request.urlopen(str(ref["value"]), timeout=120) as response:
            target.write_bytes(response.read())
    if not target.exists() or target.stat().st_size <= 0:
        return {"ok": False, "reason": "downloaded_artifact_empty"}
    return {"ok": True, "path": str(target), "temporary": True}
