# -*- coding: utf-8 -*-
"""
Tests for First-Party Ephemeral Provider Reference Transport Closure (R13.1 Remediation).
Subtask: PR1211_SECURITY_TTL_LIFECYCLE_REMEDIATION

Remediated Invariants:
1. Real image signature validation: verifies JPEG/PNG/WEBP magic bytes and extension consistency.
2. HTTPS-only external reference policy: reject http, file, data, localhost, private/loopback IPs.
3. Remove production /tmp failover: fail closed if configured or canonical root is unwritable.
4. GET/HEAD resolution is purely read-only: never mkdir, never touch probe file, 404 if root absent.
5. Authoritative sidecar metadata: mandatory (.meta.json). Missing or corrupt -> 404 (no mtime fallback).
6. Strict metadata consistency: token, filename, mime, size, hash, and expiration must match.
7. Base URL contract validation: public HTTPS only, no credentials/queries/fragments/private IPs.
8. Bounded TTL: default 7200s, clamped 60s - 21600s.
9. TTL sweep execution: expired purged, unexpired preserved.
"""

import os
import json
import time
import hashlib
import pytest
from pathlib import Path
from unittest.mock import patch

from services import provider_reference_transport as transport
from providers.video_generic_http_provider import VideoProviderContractError


@pytest.fixture
def isolated_storage_root(tmp_path):
    root = tmp_path / "provider_refs"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def transport_env(isolated_storage_root):
    return {
        "PROVIDER_REFERENCE_STORAGE_DIR": str(isolated_storage_root),
        "PROVIDER_REFERENCE_BASE_URL": "https://toanaas.vn/provider-media/v1",
        "PROVIDER_REFERENCE_TTL_SECONDS": "7200",
    }


@pytest.fixture
def valid_jpeg(tmp_path):
    img = tmp_path / "input_keyframe.jpg"
    # Valid JPEG header: FF D8 FF
    content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C" + b"\x00" * 64
    img.write_bytes(content)
    return img


@pytest.fixture
def valid_png(tmp_path):
    img = tmp_path / "input_keyframe.png"
    # Valid PNG header: 89 50 4E 47 0D 0A 1A 0A
    content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 32
    img.write_bytes(content)
    return img


@pytest.fixture
def valid_webp(tmp_path):
    img = tmp_path / "input_keyframe.webp"
    # Valid WEBP header: RIFF....WEBP
    content = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32
    img.write_bytes(content)
    return img


# ==============================================================================
# 1. REAL IMAGE SIGNATURE VALIDATION & EXTENSION CONSISTENCY
# ==============================================================================

def test_image_signature_validation_real_formats(valid_jpeg, valid_png, valid_webp, transport_env):
    """Real image magic bytes pass validation for JPEG, PNG, WEBP."""
    res_jpeg = transport.prepare_provider_image_reference(valid_jpeg, env=transport_env)
    assert res_jpeg["ok"] is True
    assert res_jpeg["mime_type"] == "image/jpeg"

    res_png = transport.prepare_provider_image_reference(valid_png, env=transport_env)
    assert res_png["ok"] is True
    assert res_png["mime_type"] == "image/png"

    res_webp = transport.prepare_provider_image_reference(valid_webp, env=transport_env)
    assert res_webp["ok"] is True
    assert res_webp["mime_type"] == "image/webp"


def test_image_signature_validation_fake_jpg_rejected(tmp_path, transport_env):
    """Text pretending to be .jpg is rejected with signature mismatch."""
    fake_jpg = tmp_path / "pretending.jpg"
    fake_jpg.write_text("Hello world I am a text file pretending to be jpg")

    with pytest.raises(VideoProviderContractError) as exc_info:
        transport.prepare_provider_image_reference(fake_jpg, env=transport_env)
    assert exc_info.value.blocker == "provider_image_signature_mismatch"
    assert exc_info.value.debug.get("no_charge") is True


def test_image_signature_validation_png_renamed_jpg_rejected(tmp_path, valid_png, transport_env):
    """PNG bytes renamed to .jpg are rejected due to extension/signature mismatch."""
    mismatched = tmp_path / "mismatched.jpg"
    mismatched.write_bytes(valid_png.read_bytes())

    with pytest.raises(VideoProviderContractError) as exc_info:
        transport.prepare_provider_image_reference(mismatched, env=transport_env)
    assert exc_info.value.blocker == "provider_image_signature_mismatch"
    assert exc_info.value.debug.get("no_charge") is True


def test_image_signature_validation_zero_bytes_rejected(tmp_path, transport_env):
    """Empty 0-byte file is rejected with provider_image_input_empty."""
    empty_file = tmp_path / "empty.jpg"
    empty_file.touch()

    with pytest.raises(VideoProviderContractError) as exc_info:
        transport.prepare_provider_image_reference(empty_file, env=transport_env)
    assert exc_info.value.blocker == "provider_image_input_empty"
    assert exc_info.value.debug.get("no_charge") is True


# ==============================================================================
# 2. HTTPS-ONLY EXTERNAL REFERENCE POLICY
# ==============================================================================

def test_external_reference_https_accepted():
    """Valid public HTTPS external reference is accepted."""
    url = "https://cdn.example.com/images/keyframe_01.jpg"
    ok, reason = transport.validate_external_reference_url(url)
    assert ok is True
    assert reason == ""


def test_external_reference_insecure_http_rejected():
    """Insecure http:// external reference is strictly rejected."""
    url = "http://cdn.example.com/images/keyframe_01.jpg"
    ok, reason = transport.validate_external_reference_url(url)
    assert ok is False
    assert reason == "provider_image_external_url_insecure_http_rejected"


def test_external_reference_localhost_and_loopback_rejected():
    """Localhost and loopback IPs are strictly rejected."""
    bad_urls = [
        "https://localhost/image.jpg",
        "https://127.0.0.1/image.jpg",
        "https://[::1]/image.jpg",
        "https://0.0.0.0/image.jpg",
    ]
    for bad in bad_urls:
        ok, reason = transport.validate_external_reference_url(bad)
        assert ok is False
        assert "localhost" in reason or "private_ip" in reason


def test_external_reference_private_ip_rejected():
    """Private and link-local IP addresses are strictly rejected."""
    private_urls = [
        "https://10.0.0.5/image.jpg",
        "https://192.168.1.100/image.jpg",
        "https://172.16.0.1/image.jpg",
        "https://169.254.169.254/latest/meta-data",
    ]
    for bad in private_urls:
        ok, reason = transport.validate_external_reference_url(bad)
        assert ok is False
        assert reason == "provider_image_external_url_private_ip_rejected"


def test_external_reference_credentials_rejected():
    """URLs containing embedded credentials are strictly rejected."""
    url = "https://admin:secret@cdn.example.com/image.jpg"
    ok, reason = transport.validate_external_reference_url(url)
    assert ok is False
    assert reason == "provider_image_external_url_credentials_forbidden"


# ==============================================================================
# 3. BASE URL CONTRACT VALIDATION
# ==============================================================================

def test_base_url_validation_public_https_ok():
    """Authoritative public HTTPS base URL is valid."""
    ok, reason = transport.validate_base_url("https://toanaas.vn/provider-media/v1")
    assert ok is True
    assert reason == ""


def test_base_url_validation_insecure_or_localhost_rejected():
    """Insecure scheme or localhost in base URL is rejected."""
    ok_http, _ = transport.validate_base_url("http://toanaas.vn/provider-media/v1")
    assert ok_http is False

    ok_local, _ = transport.validate_base_url("https://localhost/provider-media/v1")
    assert ok_local is False

    ok_priv, _ = transport.validate_base_url("https://10.0.0.1/provider-media/v1")
    assert ok_priv is False


# ==============================================================================
# 4. STORAGE ROOT UNWRITABLE / NO /tmp FAILOVER
# ==============================================================================

def test_storage_root_unwritable_fails_closed(valid_jpeg, monkeypatch):
    """Unwritable storage root fails closed without falling back to /tmp."""
    unwritable_env = {
        "PROVIDER_REFERENCE_STORAGE_DIR": "/sys/kernel/security/unwritable_provider_refs",
        "PROVIDER_REFERENCE_BASE_URL": "https://toanaas.vn/provider-media/v1",
    }
    orig_mkdir = Path.mkdir

    def mock_mkdir(self, *args, **kwargs):
        if "unwritable_provider_refs" in str(self):
            raise PermissionError("Permission denied: unwritable storage root")
        return orig_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)
    with pytest.raises(VideoProviderContractError) as exc_info:
        transport.prepare_provider_image_reference(valid_jpeg, env=unwritable_env)
    assert exc_info.value.blocker == "shopaikey_veo_i2v_public_reference_unavailable_no_charge"
    assert exc_info.value.debug.get("reason") == "storage_root_unwritable"
    assert exc_info.value.debug.get("no_charge") is True


# ==============================================================================
# 5. METADATA SIDECAR ATOMICITY & MANDATORY SERVING REQUIREMENT
# ==============================================================================

def test_metadata_write_failure_deletes_image_and_fails_closed(valid_jpeg, transport_env, isolated_storage_root):
    """If metadata sidecar cannot be written, the copied image is deleted and preparation fails closed."""
    with patch("pathlib.Path.write_text", side_effect=OSError("Disk full")):
        with pytest.raises(VideoProviderContractError) as exc_info:
            transport.prepare_provider_image_reference(valid_jpeg, env=transport_env)
        assert exc_info.value.blocker == "shopaikey_veo_i2v_public_reference_unavailable_no_charge"
        assert exc_info.value.debug.get("reason") == "metadata_write_failed"
        assert exc_info.value.debug.get("no_charge") is True

    # Confirm no orphan image left in storage root
    copied_files = [f for f in isolated_storage_root.iterdir() if f.name != ".probe_"]
    assert len(copied_files) == 0, "Image must be unlinked when metadata write fails"


def test_missing_metadata_sidecar_returns_404(valid_jpeg, transport_env, isolated_storage_root):
    """An orphan image without metadata sidecar must NOT be served (returns 404, no mtime fallback)."""
    res = transport.prepare_provider_image_reference(valid_jpeg, env=transport_env)
    token = res["token"]
    meta_path = isolated_storage_root / f"{token}.meta.json"
    assert meta_path.exists()

    # Delete sidecar metadata
    meta_path.unlink()

    # Resolution MUST fail with 404 metadata_missing
    resolved = transport.resolve_provider_reference(token, env=transport_env)
    assert resolved["ok"] is False
    assert resolved["status_code"] == 404
    assert resolved["reason"] == "metadata_missing"


def test_corrupt_metadata_sidecar_returns_404(valid_jpeg, transport_env, isolated_storage_root):
    """Malformed/corrupted JSON in metadata sidecar returns 404."""
    res = transport.prepare_provider_image_reference(valid_jpeg, env=transport_env)
    token = res["token"]
    meta_path = isolated_storage_root / f"{token}.meta.json"
    meta_path.write_text("{malformed json corrupt content...")

    resolved = transport.resolve_provider_reference(token, env=transport_env)
    assert resolved["ok"] is False
    assert resolved["status_code"] == 404
    assert resolved["reason"] == "metadata_corrupt"


def test_inconsistent_metadata_sidecar_returns_404(valid_jpeg, transport_env, isolated_storage_root):
    """Metadata with mismatched token, filename, or timestamps returns 404."""
    res = transport.prepare_provider_image_reference(valid_jpeg, env=transport_env)
    token = res["token"]
    meta_path = isolated_storage_root / f"{token}.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # Case 1: Token mismatch
    meta["token"] = "different_token_mismatch_1234567890"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    assert transport.resolve_provider_reference(token, env=transport_env)["status_code"] == 404

    # Case 2: Inconsistent timestamps (expires_at <= created_at)
    meta["token"] = token
    meta["expires_at"] = meta["created_at"] - 100
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    assert transport.resolve_provider_reference(token, env=transport_env)["status_code"] == 404


# ==============================================================================
# 6. GET/HEAD ROUTE READ-ONLY & FASTAPI INTEGRATION
# ==============================================================================

def test_resolve_provider_reference_does_not_mutate_filesystem(transport_env, isolated_storage_root):
    """GET/HEAD resolution is purely read-only and does not create directories or probe files."""
    # When storage root does not exist: returns 404 without creating the directory
    nonexistent_env = {
        "PROVIDER_REFERENCE_STORAGE_DIR": str(isolated_storage_root / "nonexistent_subfolder"),
        "PROVIDER_REFERENCE_BASE_URL": "https://toanaas.vn/provider-media/v1",
    }
    res = transport.resolve_provider_reference("some_token_1234567890_abcdef", env=nonexistent_env)
    assert res["ok"] is False
    assert res["status_code"] == 404
    assert res["reason"] == "storage_root_missing"
    assert not (isolated_storage_root / "nonexistent_subfolder").exists()


def test_fastapi_route_get_and_head_hardened(valid_jpeg, transport_env, monkeypatch):
    """Verify HTTP GET and HEAD on /provider-media/v1/{token} using FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from bot import fastapi_app

    for k, v in transport_env.items():
        monkeypatch.setenv(k, v)

    ref = transport.prepare_provider_image_reference(valid_jpeg, env=transport_env)
    token = ref["token"]
    filename = ref["filename"]

    client = TestClient(fastapi_app)

    # 1. GET with full filename
    res_get = client.get(f"/provider-media/v1/{filename}")
    assert res_get.status_code == 200
    assert res_get.headers.get("content-type") == "image/jpeg"
    assert res_get.headers.get("cache-control") == "private, no-store"
    assert hashlib.sha256(res_get.content).hexdigest() == ref["sha256"]

    # 2. HEAD with full filename (empty body)
    res_head = client.head(f"/provider-media/v1/{filename}")
    assert res_head.status_code == 200
    assert res_head.headers.get("content-type") == "image/jpeg"
    assert len(res_head.content) == 0

    # 3. GET with bare token
    res_bare = client.get(f"/provider-media/v1/{token}")
    assert res_bare.status_code == 200
    assert hashlib.sha256(res_bare.content).hexdigest() == ref["sha256"]

    # 4. GET expired token returns 404
    res_expired = transport.prepare_provider_image_reference(valid_jpeg, ttl_seconds=60, env=transport_env)
    # Fast forward in resolve
    now = time.time()
    resolved_expired = transport.resolve_provider_reference(res_expired["token"], env=transport_env, now=now + 100)
    assert resolved_expired["status_code"] == 404

    # 5. GET path traversal attempt returns 404
    res_trav = client.get("/provider-media/v1/..%2f..%2fetc%2fpasswd")
    assert res_trav.status_code == 404


# ==============================================================================
# 7. JOB-SCOPED CLEANUP & TTL SWEEP
# ==============================================================================

def test_cleanup_provider_image_references_for_job(valid_jpeg, transport_env, isolated_storage_root):
    """cleanup_provider_image_references_for_job cleans all files matching job_id."""
    ref1 = transport.prepare_provider_image_reference(valid_jpeg, job_id="job_target_999", env=transport_env)
    ref2 = transport.prepare_provider_image_reference(valid_jpeg, job_id="job_target_999", env=transport_env)
    ref_other = transport.prepare_provider_image_reference(valid_jpeg, job_id="job_other_111", env=transport_env)

    assert Path(ref1["file_path"]).exists()
    assert Path(ref2["file_path"]).exists()
    assert Path(ref_other["file_path"]).exists()

    cleaned = transport.cleanup_provider_image_references_for_job("job_target_999", env=transport_env)
    assert cleaned == 2

    # Target job references are deleted
    assert not Path(ref1["file_path"]).exists()
    assert not Path(ref2["file_path"]).exists()
    # Other job reference is strictly preserved
    assert Path(ref_other["file_path"]).exists()


def test_cleanup_expired_provider_references_preserves_active(valid_jpeg, transport_env):
    """TTL sweep purges expired references while strictly preserving active ones."""
    ref_exp = transport.prepare_provider_image_reference(valid_jpeg, ttl_seconds=60, env=transport_env)
    ref_act = transport.prepare_provider_image_reference(valid_jpeg, ttl_seconds=7200, env=transport_env)

    now = time.time()
    purged = transport.cleanup_expired_provider_references(env=transport_env, now=now + 120)
    assert purged >= 1

    assert not Path(ref_exp["file_path"]).exists()
    assert Path(ref_act["file_path"]).exists()
