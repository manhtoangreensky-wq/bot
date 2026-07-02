"""Artifact storage backend for TOAN AAS generated media.

The module keeps Railway lightweight by allowing generated artifacts to be
stored on a VPS while preserving the local backend as the default behavior.
Secrets and internal host names are never included in public metadata.
"""

from __future__ import annotations

import base64
import hashlib
import io
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
HEAVY_PRODUCT_AREAS = {
    "worker_results",
    "artifacts",
    "tmp",
    "music",
    "subdub",
    "video",
    "cache",
    "dub_assets",
    "voice_assets",
    "translation_assets",
    "subtitle_assets",
}
REMOTE_BACKENDS = {"vps_sftp", "vps_http"}


@dataclass(frozen=True)
class ArtifactStorageConfig:
    backend: str = "local"
    vps_host: str = ""
    vps_port: int = 22
    vps_user: str = "toanaas"
    vps_base_dir: str = "/opt/toanaas-storage"
    vps_ssh_key_path: str = ""
    vps_ssh_private_key: str = ""
    vps_ssh_private_key_b64: str = ""
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
        vps_ssh_private_key=str(data.get("ARTIFACT_VPS_SSH_PRIVATE_KEY") or ""),
        vps_ssh_private_key_b64=str(data.get("ARTIFACT_VPS_SSH_PRIVATE_KEY_B64") or "").strip(),
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


def _hash_fileobj(handle) -> str:
    digest = hashlib.sha256()
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


def _normalize_private_key_text(value: str) -> str:
    text = str(value or "").strip()
    if "\\n" in text and "\n" not in text:
        text = text.replace("\\n", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def _write_secure_runtime_key_file(key_text: str) -> str:
    digest = hashlib.sha256(key_text.encode("utf-8")).hexdigest()[:24]
    key_dir = Path(tempfile.gettempdir()) / "toanaas-artifact-keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    key_path = key_dir / f"artifact-vps-{digest}.key"
    if not key_path.exists() or key_path.read_text(encoding="utf-8", errors="ignore") != key_text:
        key_path.write_text(key_text, encoding="utf-8")
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return str(key_path)


def _raw_private_key_from_b64(value: str) -> dict:
    try:
        decoded = base64.b64decode(str(value or "").strip(), validate=True)
        return {"ok": True, "key_text": _normalize_private_key_text(decoded.decode("utf-8"))}
    except Exception:
        return {"ok": False, "reason": "vps_sftp_key_invalid"}


def _vps_sftp_key_source(config: ArtifactStorageConfig) -> dict:
    key_path = str(config.vps_ssh_key_path or "").strip()
    if key_path:
        if os.path.exists(key_path) and os.access(key_path, os.R_OK):
            return {"ok": True, "kind": "path", "path": key_path}
    raw_key = _normalize_private_key_text(config.vps_ssh_private_key)
    if raw_key:
        runtime_path = _write_secure_runtime_key_file(raw_key)
        return {"ok": True, "kind": "raw", "key_text": raw_key, "path": runtime_path}
    raw_b64 = str(config.vps_ssh_private_key_b64 or "").strip()
    if raw_b64:
        decoded = _raw_private_key_from_b64(raw_b64)
        if not decoded.get("ok"):
            return decoded
        runtime_path = _write_secure_runtime_key_file(str(decoded.get("key_text") or ""))
        return {"ok": True, "kind": "b64", "key_text": decoded["key_text"], "path": runtime_path}
    return {"ok": False, "reason": "vps_sftp_key_missing"}


def _paramiko_module() -> dict:
    try:
        import paramiko  # type: ignore
    except Exception:
        return {"ok": False, "reason": "paramiko_missing", "paramiko": None}
    return {"ok": True, "paramiko": paramiko}


def _load_vps_private_key(config: ArtifactStorageConfig) -> dict:
    source = _vps_sftp_key_source(config)
    if not source.get("ok"):
        return source
    module = _paramiko_module()
    if not module.get("ok"):
        return {"ok": False, "reason": module.get("reason") or "paramiko_missing"}
    paramiko = module["paramiko"]
    loaders = (
        getattr(paramiko, "Ed25519Key", None),
        getattr(paramiko, "RSAKey", None),
        getattr(paramiko, "ECDSAKey", None),
    )
    last_error = ""
    for loader in [item for item in loaders if item is not None]:
        try:
            if source.get("kind") == "path":
                key = loader.from_private_key_file(str(source.get("path") or ""))
            else:
                key = loader.from_private_key(io.StringIO(str(source.get("key_text") or "")))
            return {"ok": True, "key": key, "kind": source.get("kind"), "runtime_key_path": source.get("path") or ""}
        except Exception as exc:
            last_error = type(exc).__name__
            continue
    return {"ok": False, "reason": "vps_sftp_key_invalid", "last_error": last_error}


def vps_sftp_config_diagnostic(config: ArtifactStorageConfig) -> dict:
    module = _paramiko_module()
    key_source = _vps_sftp_key_source(config)
    reason = ""
    if config.backend == "vps_sftp":
        if not config.vps_host or not config.vps_user:
            reason = "vps_sftp_config_missing"
        elif not key_source.get("ok"):
            reason = str(key_source.get("reason") or "")
        else:
            key_loaded = _load_vps_private_key(config)
            if not key_loaded.get("ok"):
                reason = str(key_loaded.get("reason") or "")
    return {
        "backend": config.backend,
        "host_configured": bool(config.vps_host),
        "port": int(config.vps_port),
        "user_configured": bool(config.vps_user),
        "base_dir": str(config.vps_base_dir or ""),
        "key_path_configured": bool(str(config.vps_ssh_key_path or "").strip()),
        "key_path_exists": bool(str(config.vps_ssh_key_path or "").strip() and os.path.exists(str(config.vps_ssh_key_path))),
        "raw_private_key_configured": bool(str(config.vps_ssh_private_key or "").strip()),
        "private_key_b64_configured": bool(str(config.vps_ssh_private_key_b64 or "").strip()),
        "public_base_url_configured": bool(str(config.public_base_url or "").strip()),
        "paramiko_available": bool(module.get("ok")),
        "last_safe_blocker": reason or "-",
    }


def _open_vps_sftp(config: ArtifactStorageConfig) -> dict:
    if not config.vps_host or not config.vps_user:
        return {"ok": False, "reason": "vps_sftp_config_missing"}
    key_result = _load_vps_private_key(config)
    if not key_result.get("ok"):
        return {"ok": False, "reason": key_result.get("reason") or "vps_sftp_key_invalid"}
    module = _paramiko_module()
    if not module.get("ok"):
        return {"ok": False, "reason": module.get("reason") or "paramiko_missing"}
    paramiko = module["paramiko"]
    transport = None
    try:
        transport = paramiko.Transport((config.vps_host, int(config.vps_port)))
        transport.connect(username=config.vps_user, pkey=key_result["key"])
        sftp = paramiko.SFTPClient.from_transport(transport)
        return {"ok": True, "transport": transport, "sftp": sftp}
    except Exception as exc:
        try:
            if transport:
                transport.close()
        except Exception:
            pass
        exc_name = type(exc).__name__
        if "Authentication" in exc_name or "auth" in exc_name.lower():
            return {"ok": False, "reason": "vps_sftp_auth_failed"}
        return {"ok": False, "reason": f"vps_sftp_connect_failed:{exc_name}"}


def _upload_vps_sftp(local_path: str, remote_path: str, config: ArtifactStorageConfig) -> dict:
    opened = _open_vps_sftp(config)
    if not opened.get("ok"):
        return {"ok": False, "reason": opened.get("reason") or "vps_sftp_connect_failed"}
    sftp = opened.get("sftp")
    transport = opened.get("transport")
    try:
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


def _verify_vps_sftp(local_path: str, remote_path: str, config: ArtifactStorageConfig) -> dict:
    if not remote_path:
        return {"ok": False, "reason": "vps_sftp_remote_path_missing"}
    opened = _open_vps_sftp(config)
    if not opened.get("ok"):
        return {"ok": False, "reason": opened.get("reason") or "vps_sftp_connect_failed"}
    sftp = opened.get("sftp")
    transport = opened.get("transport")
    try:
        expected_size = int(Path(local_path).stat().st_size)
        expected_hash = artifact_sha256(local_path)
        remote_size = int(sftp.stat(remote_path).st_size)
        with sftp.open(remote_path, "rb") as handle:
            remote_hash = _hash_fileobj(handle)
        return {
            "ok": remote_size == expected_size and remote_hash == expected_hash,
            "backend": config.backend,
            "remote_size": remote_size,
            "remote_hash": remote_hash,
            "size_matches": remote_size == expected_size,
            "hash_matches": remote_hash == expected_hash,
            "reason": "remote_verified" if remote_size == expected_size and remote_hash == expected_hash else "remote_mismatch",
        }
    except Exception as exc:
        return {"ok": False, "backend": config.backend, "reason": f"remote_verify_failed:{type(exc).__name__}"}
    finally:
        try:
            if sftp:
                sftp.close()
        finally:
            if transport:
                transport.close()


def _verify_public_url(local_path: str, public_url: str, config: ArtifactStorageConfig) -> dict:
    if not public_url:
        return {"ok": False, "backend": config.backend, "reason": "public_url_missing"}
    expected_size = int(Path(local_path).stat().st_size)
    expected_hash = artifact_sha256(local_path)
    try:
        digest = hashlib.sha256()
        remote_size = 0
        with urllib.request.urlopen(public_url, timeout=180) as response:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                remote_size += len(chunk)
                digest.update(chunk)
        remote_hash = digest.hexdigest()
        return {
            "ok": remote_size == expected_size and remote_hash == expected_hash,
            "backend": config.backend,
            "remote_size": remote_size,
            "remote_hash": remote_hash,
            "size_matches": remote_size == expected_size,
            "hash_matches": remote_hash == expected_hash,
            "reason": "remote_verified" if remote_size == expected_size and remote_hash == expected_hash else "remote_mismatch",
        }
    except Exception as exc:
        return {"ok": False, "backend": config.backend, "reason": f"remote_verify_failed:{type(exc).__name__}"}


def verify_stored_artifact(
    local_path: str | os.PathLike[str],
    metadata: Mapping[str, object] | None,
    *,
    config: ArtifactStorageConfig | None = None,
    verifier: Callable[[str, dict, ArtifactStorageConfig], dict] | None = None,
) -> dict:
    cfg = config or config_from_env()
    local = Path(local_path)
    if not local.exists() or not local.is_file():
        return {"ok": False, "backend": cfg.backend, "reason": "local_artifact_missing"}
    raw = dict(metadata or {})
    if verifier:
        result = verifier(str(local), raw, cfg)
        return {
            "backend": cfg.backend,
            "ok": bool(result.get("ok")),
            "remote_size": int(result.get("remote_size") or raw.get("artifact_size") or 0),
            "remote_hash": str(result.get("remote_hash") or raw.get("artifact_hash") or ""),
            "size_matches": bool(result.get("size_matches", result.get("ok"))),
            "hash_matches": bool(result.get("hash_matches", result.get("ok"))),
            "reason": str(result.get("reason") or ("remote_verified" if result.get("ok") else "remote_verify_failed")),
        }
    expected_size = int(local.stat().st_size)
    expected_hash = artifact_sha256(local)
    backend = str(raw.get("backend") or cfg.backend)
    if backend == "local":
        return {
            "ok": True,
            "backend": backend,
            "remote_size": expected_size,
            "remote_hash": expected_hash,
            "size_matches": True,
            "hash_matches": True,
            "reason": "local_verified",
        }
    if backend == "vps_sftp":
        return _verify_vps_sftp(str(local), str(raw.get("remote_path") or ""), cfg)
    if backend == "vps_http":
        return _verify_public_url(str(local), str(raw.get("public_url") or ""), cfg)
    return {"ok": False, "backend": backend, "reason": "artifact_backend_unsupported"}


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
