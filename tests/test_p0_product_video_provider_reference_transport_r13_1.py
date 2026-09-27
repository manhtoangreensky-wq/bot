# -*- coding: utf-8 -*-
"""
Tests for First-Party Ephemeral Provider Reference Transport Closure (R13.1).
Subtask: FIRST_PARTY_EPHEMERAL_REFERENCE_TRANSPORT_CLOSURE

Requirements:
1. Isolated storage root: dedicated directory under /opt/toanaas-storage/provider_refs.
2. 256 bits entropy: tokens generated via secrets.token_urlsafe(32).
3. Zero external cloud storage dependencies (no S3, R2, GCS, Cloudinary, MinIO).
4. No filesystem path leak: paths are strictly isolated and never exposed.
5. Strict containment: path traversal, directory escape, and symlinks are strictly rejected.
6. Safe MIME validation: only image/jpeg, image/png, and image/webp allowed.
7. Bounded TTL: default 7200s (2 hours), max 21600s (6 hours).
8. Fast-fail closed: missing or invalid images fail closed before provider submission (no charge).
9. FastAPI route @fastapi_app.get and @fastapi_app.head for /provider-media/v1/{token}.
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
def dummy_jpeg(tmp_path):
    img = tmp_path / "input_keyframe.jpg"
    # Minimal JPEG header + payload
    content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C" + b"\x00" * 64
    img.write_bytes(content)
    return img


# ==============================================================================
# 1. CORE TRANSPORT MATERIALIZATION & METADATA TESTS
# ==============================================================================

def test_prepare_provider_image_reference_success(dummy_jpeg, transport_env, isolated_storage_root):
    """Test materializing a valid JPEG into provider reference transport."""
    result = transport.prepare_provider_image_reference(
        dummy_jpeg,
        provider="shopaikey_video",
        purpose="image_to_video",
        job_id="job_test_123",
        env=transport_env,
    )

    assert result["ok"] is True
    token = result["token"]
    assert len(token) >= 40, "Token must have at least 256 bits entropy"
    assert result["public_url"].startswith("https://toanaas.vn/provider-media/v1/")
    assert result["public_url"].endswith(f"{token}.jpg")
    assert result["mime_type"] == "image/jpeg"
    assert result["file_size"] == len(dummy_jpeg.read_bytes())
    assert result["sha256"] == hashlib.sha256(dummy_jpeg.read_bytes()).hexdigest()

    # Verify physical file in storage root
    dest_path = Path(result["file_path"])
    assert dest_path.exists()
    assert dest_path.parent.resolve() == isolated_storage_root.resolve()
    assert dest_path.read_bytes() == dummy_jpeg.read_bytes()

    # Verify metadata sidecar
    meta_path = isolated_storage_root / f"{token}.meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["token"] == token
    assert meta["provider"] == "shopaikey_video"
    assert meta["purpose"] == "image_to_video"
    assert meta["job_id"] == "job_test_123"
    assert meta["ttl_seconds"] == 7200


def test_prepare_provider_image_reference_png_and_webp(tmp_path, transport_env):
    """Test supporting PNG and WEBP formats."""
    png_file = tmp_path / "sample.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    png_res = transport.prepare_provider_image_reference(png_file, env=transport_env)
    assert png_res["ok"] is True
    assert png_res["mime_type"] == "image/png"
    assert png_res["filename"].endswith(".png")

    webp_file = tmp_path / "sample.webp"
    webp_file.write_bytes(b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 32)
    webp_res = transport.prepare_provider_image_reference(webp_file, env=transport_env)
    assert webp_res["ok"] is True
    assert webp_res["mime_type"] == "image/webp"
    assert webp_res["filename"].endswith(".webp")


# ==============================================================================
# 2. NEGATIVE SECURITY MATRIX & GUARDRAILS
# ==============================================================================

def test_security_first_red_type_size_guard(tmp_path, transport_env):
    """FIRST RED TYPE/SIZE GUARD: Unsupported extensions, empty files, and oversize files fail closed."""
    # Unsupported extension
    txt_file = tmp_path / "script.txt"
    txt_file.write_text("not an image")
    with pytest.raises(VideoProviderContractError) as exc_info:
        transport.prepare_provider_image_reference(txt_file, env=transport_env)
    assert exc_info.value.blocker == "provider_image_extension_unsupported"
    assert exc_info.value.debug.get("no_charge") is True

    # Empty file
    empty_img = tmp_path / "empty.jpg"
    empty_img.touch()
    with pytest.raises(VideoProviderContractError) as exc_info:
        transport.prepare_provider_image_reference(empty_img, env=transport_env)
    assert exc_info.value.blocker == "provider_image_input_empty"
    assert exc_info.value.debug.get("no_charge") is True

    # Missing file
    with pytest.raises(VideoProviderContractError) as exc_info:
        transport.prepare_provider_image_reference(tmp_path / "nonexistent.jpg", env=transport_env)
    assert exc_info.value.blocker == "provider_image_input_missing_or_invalid"
    assert exc_info.value.debug.get("no_charge") is True


def test_security_first_red_path_traversal(transport_env):
    """FIRST RED PATH TRAVERSAL: Traversal sequences in tokens must be rejected."""
    traversal_candidates = [
        "../../etc/passwd",
        "..\\..\\windows\\win.ini",
        "../provider_refs/secret.jpg",
        "%2e%2e%2fetc%2fpasswd",
        "token/with/slash",
        "token\x00nullbyte",
    ]
    for bad_token in traversal_candidates:
        res = transport.resolve_provider_reference(bad_token, env=transport_env)
        assert res["ok"] is False
        assert res["status_code"] == 404, f"Traversal token {bad_token} must return 404"


def test_security_first_red_unknown_token(transport_env):
    """FIRST RED UNKNOWN TOKEN: Non-existent token returns 404."""
    res = transport.resolve_provider_reference("valid_looking_token_that_does_not_exist_in_storage", env=transport_env)
    assert res["ok"] is False
    assert res["status_code"] == 404


def test_security_first_red_expiry(dummy_jpeg, transport_env, isolated_storage_root):
    """FIRST RED EXPIRY: Expired tokens return 404."""
    res = transport.prepare_provider_image_reference(
        dummy_jpeg,
        ttl_seconds=60,
        env=transport_env,
    )
    token = res["token"]

    # Resolution before expiry: OK
    now = time.time()
    ok_res = transport.resolve_provider_reference(token, env=transport_env, now=now + 10)
    assert ok_res["ok"] is True

    # Resolution after expiry (70 seconds later): 404
    expired_res = transport.resolve_provider_reference(token, env=transport_env, now=now + 70)
    assert expired_res["ok"] is False
    assert expired_res["status_code"] == 404
    assert expired_res["reason"] == "token_expired"


def test_security_symlink_escape(isolated_storage_root, dummy_jpeg, transport_env):
    """SYMLINK ESCAPE: Symlinks inside the storage root must be rejected."""
    # Create a symlink pointing to an arbitrary file outside storage root
    outside_file = isolated_storage_root.parent / "outside_secret.jpg"
    outside_file.write_bytes(dummy_jpeg.read_bytes())

    symlink_path = isolated_storage_root / "symlink_escape_test_token_12345.jpg"
    try:
        symlink_path.symlink_to(outside_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this filesystem / user permissions")

    res = transport.resolve_provider_reference("symlink_escape_test_token_12345.jpg", env=transport_env)
    assert res["ok"] is False
    assert res["status_code"] == 404
    assert res["reason"] == "symlink_rejected"


# ==============================================================================
# 3. FASTAPI ROUTE & HTTP/HEAD INTEGRATION
# ==============================================================================

def test_fastapi_route_get_and_head(dummy_jpeg, transport_env, monkeypatch):
    """Verify HTTP GET and HEAD on /provider-media/v1/{token} using FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from bot import fastapi_app

    # Set storage root and base url in environment
    for k, v in transport_env.items():
        monkeypatch.setenv(k, v)

    # Materialize dummy image
    ref = transport.prepare_provider_image_reference(dummy_jpeg, env=transport_env)
    token = ref["token"]
    filename = ref["filename"]

    client = TestClient(fastapi_app)

    # 1. HTTP GET request
    response_get = client.get(f"/provider-media/v1/{filename}")
    assert response_get.status_code == 200
    assert response_get.headers.get("content-type") == "image/jpeg"
    assert response_get.headers.get("cache-control") == "private, no-store"
    assert int(response_get.headers.get("content-length")) == len(dummy_jpeg.read_bytes())
    # Verify exact byte content and SHA256 match
    assert hashlib.sha256(response_get.content).hexdigest() == ref["sha256"]

    # 2. HTTP HEAD request
    response_head = client.head(f"/provider-media/v1/{filename}")
    assert response_head.status_code == 200
    assert response_head.headers.get("content-type") == "image/jpeg"
    assert response_head.headers.get("cache-control") == "private, no-store"
    assert int(response_head.headers.get("content-length")) == len(dummy_jpeg.read_bytes())
    assert len(response_head.content) == 0, "HEAD request body must be empty"

    # 3. GET with bare token (no extension in URL path)
    response_bare = client.get(f"/provider-media/v1/{token}")
    assert response_bare.status_code == 200
    assert hashlib.sha256(response_bare.content).hexdigest() == ref["sha256"]

    # 4. GET unknown token
    response_unknown = client.get("/provider-media/v1/completely_unknown_token_404.jpg")
    assert response_unknown.status_code == 404

    # 5. GET path traversal attempt
    response_traversal = client.get("/provider-media/v1/..%2f..%2fetc%2fpasswd")
    assert response_traversal.status_code == 404


# ==============================================================================
# 4. LIFECYCLE & CLEANUP TESTS
# ==============================================================================

def test_cleanup_provider_image_reference(dummy_jpeg, transport_env, isolated_storage_root):
    """Test explicit cleanup of reference and its metadata."""
    ref = transport.prepare_provider_image_reference(dummy_jpeg, env=transport_env)
    token = ref["token"]
    img_path = Path(ref["file_path"])
    meta_path = isolated_storage_root / f"{token}.meta.json"

    assert img_path.exists()
    assert meta_path.exists()

    # Clean up using URL
    cleaned = transport.cleanup_provider_image_reference(ref["public_url"], env=transport_env)
    assert cleaned is True
    assert not img_path.exists()
    assert not meta_path.exists()

    # Subsequent resolution returns 404
    res = transport.resolve_provider_reference(token, env=transport_env)
    assert res["ok"] is False
    assert res["status_code"] == 404


def test_cleanup_expired_provider_references(dummy_jpeg, transport_env, isolated_storage_root):
    """Test sweep function purges expired references while keeping active references."""
    # Item 1: Expired reference (TTL 60s)
    ref_expired = transport.prepare_provider_image_reference(dummy_jpeg, ttl_seconds=60, env=transport_env)
    # Item 2: Active reference (TTL 7200s)
    ref_active = transport.prepare_provider_image_reference(dummy_jpeg, ttl_seconds=7200, env=transport_env)

    now = time.time()
    # Sweep at now + 120s (ref_expired is past TTL, ref_active is still active)
    purged = transport.cleanup_expired_provider_references(env=transport_env, now=now + 120)
    assert purged >= 1

    # Expired item is gone
    assert not Path(ref_expired["file_path"]).exists()
    # Active item remains intact
    assert Path(ref_active["file_path"]).exists()
