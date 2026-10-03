"""Test Suite for Web Product Video Safe Output URL Domain Whitelist Remediation.

Task: WEBAPP_PRODUCT_VIDEO_SAFE_OUTPUT_URL_DOMAIN_WHITELIST_REMEDIATION_R1
Tracker: Issue #605
Parent Live Receipt: #605 comment 5935577897
Contract: #605 comment 5935249985

Covers:
1. Signed ShopAIKey content URL accepted (exact host, path /v1/videos/<id>/content, exp, sig)
2. Wrong host rejected (HOST_WILDCARD_ALLOWED=NO)
3. Host suffix attack rejected (HOST_SUFFIX_MATCH_ALLOWED=NO)
4. Subdomain attack rejected (SUBDOMAIN_MATCH_ALLOWED=NO)
5. Insecure HTTP scheme rejected (HTTP_ALLOWED=NO)
6. Non-443 port rejected (NON_443_PORT_ALLOWED=NO)
7. Userinfo in URL rejected (USERINFO_ALLOWED=NO)
8. URL fragment rejected (FRAGMENT_ALLOWED=NO)
9. Missing exp or sig parameter rejected (SHOPAIKEY_CONTENT_ENDPOINT_SIGNED_QUERY_REQUIRED=YES)
10. Malformed or path-traversal URL rejected
11. Generic arbitrary extensionless URL rejected (GENERIC_ARBITRARY_EXTENSIONLESS_URL_ALLOWED=NO)
12. Unsafe redirect destinations rejected BEFORE contacting (DISALLOWED_REDIRECT_DESTINATION_REQUEST_COUNT=0)
13. ShopAIKey redirect max 1 enforced (SHOPAIKEY_CONTENT_ENDPOINT_REDIRECT_MAX=1)
14. Safe ShopAIKey redirect (1 hop to another valid signed ShopAIKey content URL) allowed
15. video/*, application/octet-stream, binary/octet-stream accepted with ffprobe
16. HTML and JSON bodies rejected without retry
17. Invalid/unreadable media rejected
18. Content-Length mismatch rejected
19. Signed query values (exp/sig) never logged (SIGNED_RESULT_URL_LOGGED=NO, RESULT_URL_QUERY_VALUE_LOGGED=NO)
20. Legacy safe .mp4/.webm/.mov behavior unchanged
21. Consumer execution with valid ShopAIKey signed URL succeeds end-to-end without UNSAFE_OUTPUT_REJECTED
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services.video_provider_base import (
    DisallowedRedirectError,
    IncompleteDownloadError,
    UnsafeOutputURLError,
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    is_safe_shopaikey_content_url,
    is_safe_video_output_url,
    materialize_video_url,
    sanitize_artifact_download_diagnostics,
    sanitize_output_url_for_logging,
    _HardenedVideoRedirectHandler,
)
from services.web_product_video_worker_consumer import (
    ConsumerExecutionOutcome,
    WebProductVideoDispatcherClient,
    execute_claimed_web_product_video_job,
)


VALID_SHOPAIKEY_URL = "https://api.shopaikey.com/v1/videos/task_Y9dvX3X2d9q9kXn6O25ltCvEo4iibzXt/content?exp=1791504000&sig=424074123350da54e35a932e474286d8"
VALID_SHOPAIKEY_URL_WITH_EXTRA_PARAMS = "https://api.shopaikey.com/v1/videos/task_12345_abc-xyz/content?resolution=720p&exp=1791504000&sig=424074123350da54e35a932e474286d8"
LEGACY_SAFE_MP4_URL = "https://cdn.example.com/videos/output_sample.mp4"
LEGACY_SAFE_MOV_URL = "https://storage.googleapis.com/toanaas-assets/video.mov"
LEGACY_SAFE_WEBM_URL = "https://s3.amazonaws.com/bucket-prod/rendered.webm"

SAMPLE_JOB: dict[str, Any] = {
    "job_id": "pvj_whitelist_test_001",
    "request_id": "VID-20261002-TEST01",
    "account_id": "acc_cust_test_494e",
    "product_key": "video_ai_prompt",
    "status": "processing",
    "payload": {
        "prompt": "Premium cosmetic skin care 5s",
        "aspect_ratio": "9:16",
        "duration": 5.0,
        "quality_tier": "200",
    },
    "attempts": 1,
    "worker_id": "vps-web-product-video-worker",
}

ENABLED_ENV: dict[str, str] = {
    "WEB_PRODUCT_VIDEO_WORKER_ENABLED": "true",
    "LOCAL_WORKER_TOKEN": "valid_token_test",
}


# ==============================================================================
# 1. ShopAIKey Content Endpoint Validation Tests
# ==============================================================================

def test_01_signed_shopaikey_content_url_accepted() -> None:
    """Exact signed ShopAIKey content URLs are accepted by is_safe_shopaikey_content_url and is_safe_video_output_url."""
    assert is_safe_shopaikey_content_url(VALID_SHOPAIKEY_URL) is True
    assert is_safe_video_output_url(VALID_SHOPAIKEY_URL) is True
    assert is_safe_shopaikey_content_url(VALID_SHOPAIKEY_URL_WITH_EXTRA_PARAMS) is True
    assert is_safe_video_output_url(VALID_SHOPAIKEY_URL_WITH_EXTRA_PARAMS) is True


def test_02_wrong_host_rejected() -> None:
    """Non-matching hostnames are rejected even if path and query look like ShopAIKey."""
    wrong_hosts = [
        "https://not-shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.org/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.net/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
    ]
    for url in wrong_hosts:
        assert is_safe_shopaikey_content_url(url) is False
        assert is_safe_video_output_url(url) is False


def test_03_suffix_attack_rejected() -> None:
    """Hostname suffix attacks are strictly rejected (HOST_SUFFIX_MATCH_ALLOWED=NO)."""
    suffix_attacks = [
        "https://api.shopaikey.com.evil.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com.attacker.io/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://evilapi.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.community/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
    ]
    for url in suffix_attacks:
        assert is_safe_shopaikey_content_url(url) is False
        assert is_safe_video_output_url(url) is False


def test_04_subdomain_rejected() -> None:
    """Subdomains of api.shopaikey.com are rejected (SUBDOMAIN_MATCH_ALLOWED=NO)."""
    subdomain_attacks = [
        "https://sub.api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://cdn.api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://v2.api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
    ]
    for url in subdomain_attacks:
        assert is_safe_shopaikey_content_url(url) is False
        assert is_safe_video_output_url(url) is False


def test_05_http_scheme_rejected() -> None:
    """Insecure HTTP scheme is strictly rejected (HTTP_ALLOWED=NO)."""
    insecure = "http://api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef"
    assert is_safe_shopaikey_content_url(insecure) is False
    assert is_safe_video_output_url(insecure) is False


def test_06_non_443_port_rejected() -> None:
    """Non-443 ports are strictly rejected (NON_443_PORT_ALLOWED=NO)."""
    non_443_urls = [
        "https://api.shopaikey.com:8443/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com:80/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com:444/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com:8080/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
    ]
    for url in non_443_urls:
        assert is_safe_shopaikey_content_url(url) is False
        assert is_safe_video_output_url(url) is False

    # Port 443 explicit is allowed
    explicit_443 = "https://api.shopaikey.com:443/v1/videos/task_123/content?exp=1791504000&sig=abcdef"
    assert is_safe_shopaikey_content_url(explicit_443) is True
    assert is_safe_video_output_url(explicit_443) is True


def test_07_userinfo_rejected() -> None:
    """URLs containing userinfo are strictly rejected (USERINFO_ALLOWED=NO)."""
    userinfo_urls = [
        "https://user:pass@api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://admin@api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://root:secret@api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef",
    ]
    for url in userinfo_urls:
        assert is_safe_shopaikey_content_url(url) is False
        assert is_safe_video_output_url(url) is False


def test_08_fragment_rejected() -> None:
    """URLs containing fragments are strictly rejected (FRAGMENT_ALLOWED=NO)."""
    fragment_urls = [
        "https://api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef#fragment",
        "https://api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abcdef#t=10",
        "https://cdn.example.com/videos/output.mp4#t=5",
    ]
    for url in fragment_urls:
        assert is_safe_shopaikey_content_url(url) is False
        assert is_safe_video_output_url(url) is False


def test_09_missing_exp_or_sig_rejected() -> None:
    """Missing or empty exp or sig query parameters are strictly rejected."""
    bad_queries = [
        "https://api.shopaikey.com/v1/videos/task_123/content",  # No query
        "https://api.shopaikey.com/v1/videos/task_123/content?exp=1791504000",  # Missing sig
        "https://api.shopaikey.com/v1/videos/task_123/content?sig=abcdef",  # Missing exp
        "https://api.shopaikey.com/v1/videos/task_123/content?exp=&sig=abcdef",  # Empty exp
        "https://api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=",  # Empty sig
        "https://api.shopaikey.com/v1/videos/task_123/content?exp=&sig=",  # Both empty
        "https://api.shopaikey.com/v1/videos/task_123/content?token=xyz",  # Wrong parameter names
    ]
    for url in bad_queries:
        assert is_safe_shopaikey_content_url(url) is False
        assert is_safe_video_output_url(url) is False


def test_10_malformed_and_traversal_paths_rejected() -> None:
    """Malformed paths, directory traversal, and non-canonical shapes are rejected."""
    malformed_paths = [
        "https://api.shopaikey.com/v1/videos/../admin/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com/v1/videos/%2e%2e/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com/v1/videos//content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com/v1/videos/task_123/delete?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com/v1/videos/task_123/content/extra?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com/v2/videos/task_123/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com/v1/videos/task_123?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com/v1/videos/task@123/content?exp=1791504000&sig=abcdef",
        "https://api.shopaikey.com/v1/videos/task 123/content?exp=1791504000&sig=abcdef",
    ]
    for url in malformed_paths:
        assert is_safe_shopaikey_content_url(url) is False
        assert is_safe_video_output_url(url) is False


def test_11_generic_arbitrary_extensionless_urls_rejected() -> None:
    """Generic arbitrary extensionless URLs on other domains are rejected (GENERIC_ARBITRARY_EXTENSIONLESS_URL_ALLOWED=NO)."""
    arbitrary_urls = [
        "https://cdn.example.com/v1/videos/task_123/content?exp=1&sig=2",
        "https://storage.googleapis.com/download/asset",
        "https://api.otherprovider.com/fetch_video",
        "https://s3.amazonaws.com/bucket/stream",
    ]
    for url in arbitrary_urls:
        assert is_safe_shopaikey_content_url(url) is False
        assert is_safe_video_output_url(url) is False


# ==============================================================================
# 2. Hardened Redirect Validation Tests
# ==============================================================================

def test_12_disallowed_redirect_destinations_blocked_before_request() -> None:
    """_HardenedVideoRedirectHandler rejects unsafe destinations BEFORE any HTTP connection is made."""
    handler = _HardenedVideoRedirectHandler(VALID_SHOPAIKEY_URL)

    disallowed_destinations = [
        ("http://api.shopaikey.com/v1/videos/task_2/content?exp=1&sig=2", "http downgrade"),
        ("https://127.0.0.1/v1/videos/task_2/content?exp=1&sig=2", "localhost IP"),
        ("https://localhost/v1/videos/task_2/content?exp=1&sig=2", "localhost domain"),
        ("https://169.254.169.254/latest/meta-data/", "link-local IP"),
        ("https://192.168.1.10/video.mp4", "private IP"),
        ("https://otherhost.com/v1/videos/task_2/content?exp=1&sig=2", "different host"),
        ("https://api.shopaikey.com.evil.com/v1/videos/task_2/content?exp=1&sig=2", "suffix attack"),
        ("https://api.shopaikey.com:8443/v1/videos/task_2/content?exp=1&sig=2", "non-443 port"),
        ("https://user:pass@api.shopaikey.com/v1/videos/task_2/content?exp=1&sig=2", "userinfo"),
        ("https://api.shopaikey.com/v1/videos/task_2/content", "missing signed query"),
    ]

    mock_req = MagicMock()
    for dest_url, label in disallowed_destinations:
        with pytest.raises(DisallowedRedirectError) as exc_info:
            handler.redirect_request(mock_req, None, 302, "Found", {}, dest_url)
        assert exc_info.value.code == 400, f"Expected 400 error for {label}"


def test_13_shopaikey_redirect_max_1_enforced() -> None:
    """ShopAIKey content endpoint allows at most 1 redirect hop, rejecting a 2nd redirect."""
    handler = _HardenedVideoRedirectHandler(VALID_SHOPAIKEY_URL)
    hop1 = "https://api.shopaikey.com/v1/videos/task_hop1/content?exp=1791504000&sig=abcdef"
    hop2 = "https://api.shopaikey.com/v1/videos/task_hop2/content?exp=1791504000&sig=abcdef"

    mock_req = MagicMock()
    # 1st redirect succeeds
    with patch("urllib.request.HTTPRedirectHandler.redirect_request", return_value=mock_req):
        res1 = handler.redirect_request(mock_req, None, 302, "Found", {}, hop1)
        assert res1 is mock_req
        assert handler.redirect_count == 1

    # 2nd redirect fails
    with pytest.raises(DisallowedRedirectError) as exc_info:
        handler.redirect_request(mock_req, None, 302, "Found", {}, hop2)
    assert "redirect_limit_exceeded_max_1" in (getattr(exc_info.value, "redirect_reason", "") or str(exc_info.value))


def test_14_legacy_safe_redirect_policy_enforced() -> None:
    """Legacy safe URLs enforce safe video output URL policy across redirects."""
    handler = _HardenedVideoRedirectHandler(LEGACY_SAFE_MP4_URL)
    mock_req = MagicMock()

    # Valid legacy redirect to another safe https .mp4
    safe_target = "https://cdn2.example.com/videos/final.mp4"
    with patch("urllib.request.HTTPRedirectHandler.redirect_request", return_value=mock_req):
        res = handler.redirect_request(mock_req, None, 302, "Found", {}, safe_target)
        assert res is mock_req

    # Unsafe redirect to internal IP is blocked
    with pytest.raises(DisallowedRedirectError):
        handler.redirect_request(mock_req, None, 302, "Found", {}, "https://10.0.0.1/video.mp4")

    # Unsafe redirect to non-video is blocked
    with pytest.raises(DisallowedRedirectError):
        handler.redirect_request(mock_req, None, 302, "Found", {}, "https://cdn.example.com/payload.exe")


# ==============================================================================
# 3. Payload Validation and Safe Download Tests
# ==============================================================================

def test_15_video_octet_stream_payload_accepted_with_ffprobe(tmp_path: Path) -> None:
    """Payloads with application/octet-stream and binary/octet-stream are accepted if probe succeeds."""
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir()

    for mime_type in ["application/octet-stream", "binary/octet-stream", "video/mp4"]:
        mock_response = MagicMock()
        mock_response.headers = {
            "Content-Type": mime_type,
            "Content-Length": "10000",
        }
        mock_response.geturl.return_value = VALID_SHOPAIKEY_URL
        mock_response.status = 200
        mock_response.getcode.return_value = 200
        stream = io.BytesIO(b"A" * 10000)
        mock_response.read = stream.read

        with patch("urllib.request.build_opener") as mock_opener_cls, \
             patch("services.video_final_output.probe_video", return_value={"ok": True, "duration": 5.0, "has_video": True, "has_audio": True}):
            mock_opener = MagicMock()
            mock_opener.open.return_value.__enter__.return_value = mock_response
            mock_opener_cls.return_value = mock_opener

            res = materialize_video_url(
                VALID_SHOPAIKEY_URL,
                job_id=f"job_{mime_type.replace('/', '_')}",
                output_dir=str(out_dir),
            )

        assert res.ok is True
        assert res.bytes == 10000
        assert res.diagnostics.get("mp4_validator_result") == "valid_mp4"


def test_16_html_and_json_payloads_rejected_without_retry(tmp_path: Path) -> None:
    """HTML or JSON bodies are detected and rejected with 0 retries."""
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir()

    bad_payloads = [
        (b"<!DOCTYPE html><html><body>Error</body></html>", "text/html", "provider_download_not_video"),
        (b'{"error": "Task not found"}', "application/json", "provider_download_not_video"),
        (b"<html lang='en'>Unauthorized</html>", "application/octet-stream", "provider_download_html_error"),
        (b'{"status": "failed", "code": 500}', "binary/octet-stream", "provider_download_json_error"),
    ]

    for body_bytes, ctype, expected_err in bad_payloads:
        mock_response = MagicMock()
        mock_response.headers = {
            "Content-Type": ctype,
            "Content-Length": str(len(body_bytes)),
        }
        mock_response.geturl.return_value = VALID_SHOPAIKEY_URL
        mock_response.status = 200
        mock_response.getcode.return_value = 200
        stream = io.BytesIO(body_bytes)
        mock_response.read = stream.read

        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener.open.return_value.__enter__.return_value = mock_response
            mock_opener_cls.return_value = mock_opener

            res = materialize_video_url(
                VALID_SHOPAIKEY_URL,
                job_id="job_non_video",
                output_dir=str(out_dir),
            )

        assert res.ok is False
        assert res.error_code == expected_err
        # Non-video payloads are not transient; retry count must be 0
        assert res.diagnostics.get("download_retries") == 0


def test_17_invalid_media_rejected_by_probe(tmp_path: Path) -> None:
    """Unreadable media bytes that fail ffprobe are rejected as output_unreadable."""
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir()

    mock_response = MagicMock()
    mock_response.headers = {
        "Content-Type": "video/mp4",
        "Content-Length": "5000",
    }
    mock_response.geturl.return_value = VALID_SHOPAIKEY_URL
    mock_response.status = 200
    mock_response.getcode.return_value = 200
    stream = io.BytesIO(b"\x00\x00\x00\x20garbage_bytes" + b"\x00" * 4983)
    mock_response.read = stream.read

    with patch("urllib.request.build_opener") as mock_opener_cls, \
         patch("services.video_final_output.probe_video", return_value={"ok": False, "reason": "output_unreadable"}):
        mock_opener = MagicMock()
        mock_opener.open.return_value.__enter__.return_value = mock_response
        mock_opener_cls.return_value = mock_opener

        res = materialize_video_url(
            VALID_SHOPAIKEY_URL,
            job_id="job_unreadable",
            output_dir=str(out_dir),
        )

    assert res.ok is False
    assert res.error_code == "output_unreadable"


def test_18_content_length_mismatch_rejected(tmp_path: Path) -> None:
    """Transferred byte count mismatching Content-Length header raises IncompleteDownloadError."""
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir()

    mock_response = MagicMock()
    mock_response.headers = {
        "Content-Type": "video/mp4",
        "Content-Length": "20000",
    }
    mock_response.geturl.return_value = VALID_SHOPAIKEY_URL
    mock_response.status = 200
    mock_response.getcode.return_value = 200
    # Returns only 5000 bytes instead of 20000
    stream = io.BytesIO(b"X" * 5000)
    mock_response.read = stream.read

    with patch("urllib.request.build_opener") as mock_opener_cls:
        mock_opener = MagicMock()
        mock_opener.open.return_value.__enter__.return_value = mock_response
        mock_opener_cls.return_value = mock_opener

        res = materialize_video_url(
            VALID_SHOPAIKEY_URL,
            job_id="job_short_read",
            output_dir=str(out_dir),
            sleep_func=lambda *a, **kw: None,
        )

    assert res.ok is False
    assert res.error_code == "provider_download_failed"
    assert res.diagnostics.get("download_error_class") == "IncompleteDownloadError"


# ==============================================================================
# 4. Safe Logging Tests
# ==============================================================================

def test_19_signed_query_never_logged() -> None:
    """Sanitized logging formats URL without exposing exp, sig, tokens, or query values."""
    signed_url = (
        "https://api.shopaikey.com/v1/videos/task_secret123/content"
        "?exp=1791504000&sig=424074123350da54e35a932e474286d8&secret_token=TOP_SECRET"
    )

    sanitized = sanitize_output_url_for_logging(signed_url)

    # Required: query values must NOT be present
    assert "1791504000" not in sanitized
    assert "424074123350da54e35a932e474286d8" not in sanitized
    assert "TOP_SECRET" not in sanitized
    assert "exp=" not in sanitized
    assert "sig=" not in sanitized
    assert "secret_token=" not in sanitized

    # Required: scheme, host, path, query_present are present
    assert sanitized == "https://api.shopaikey.com/v1/videos/task_secret123/content?query_present=True"


def test_20_consumer_logs_only_sanitized_url_on_rejection(caplog: pytest.LogCaptureFixture) -> None:
    """When consumer rejects an unsafe URL with query parameters, sensitive values are not logged."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)
    sensitive_bad_url = "https://evil.com/v1/videos/task_999/content?exp=99999999&sig=SUPER_SECRET_SIGNATURE"

    def unsafe_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "result_url": sensitive_bad_url,
            "file_url": sensitive_bad_url,
            "duration": 5.0,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    with caplog.at_level(logging.ERROR, logger="web_product_video_worker_consumer"):
        outcome = execute_claimed_web_product_video_job(
            SAMPLE_JOB,
            client=client,
            environ=ENABLED_ENV,
            executor_fn=unsafe_executor,
        )

    assert outcome.ok is False
    assert outcome.status == "UNSAFE_OUTPUT_REJECTED"

    # Verify no log record leaked the signature or exp
    captured_text = caplog.text
    assert "SUPER_SECRET_SIGNATURE" not in captured_text
    assert "99999999" not in captured_text
    assert "sig=" not in captured_text
    assert "exp=" not in captured_text
    assert "evil.com" in captured_text
    assert "query_present=True" in captured_text


# ==============================================================================
# 5. Backward Compatibility & End-to-End Consumer Acceptance
# ==============================================================================

def test_21_legacy_safe_mp4_mov_webm_unchanged() -> None:
    """Legacy URLs ending with .mp4, .mov, .webm remain valid and accepted."""
    assert is_safe_video_output_url(LEGACY_SAFE_MP4_URL) is True
    assert is_safe_video_output_url(LEGACY_SAFE_MOV_URL) is True
    assert is_safe_video_output_url(LEGACY_SAFE_WEBM_URL) is True


def test_22_consumer_accepts_valid_shopaikey_url_end_to_end(tmp_path: Path) -> None:
    """Consumer accepts valid ShopAIKey signed URL and proceeds to artifact probe without UNSAFE_OUTPUT_REJECTED."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)

    # Create dummy artifact on disk
    local_artifact = tmp_path / "rendered.mp4"
    local_artifact.write_bytes(b"\x00" * 8192)

    def shopaikey_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "result_url": VALID_SHOPAIKEY_URL,
            "file_url": VALID_SHOPAIKEY_URL,
            "output_path": str(local_artifact),
            "duration": 5.0,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    with patch("services.web_product_video_worker_consumer.probe_artifact_file", return_value={"ok": True, "duration": 5.0, "width": 720, "height": 1280, "file_size_bytes": 8192, "format": "mp4", "codec": "h264"}):
        outcome = execute_claimed_web_product_video_job(
            SAMPLE_JOB,
            client=client,
            environ=ENABLED_ENV,
            executor_fn=shopaikey_executor,
        )

    # Must NOT fail with UNSAFE_OUTPUT_REJECTED
    assert outcome.status != "UNSAFE_OUTPUT_REJECTED"
    assert outcome.blocker_reason != "UNSAFE_OUTPUT_URL"
    assert outcome.ok is True
    assert outcome.status == "COMPLETED"
    assert outcome.output_url == VALID_SHOPAIKEY_URL
    assert client.complete.call_count == 1
    assert client.fail.call_count == 0


# ==============================================================================
# 5. Shared Materializer Fail-Closed URL Validation Direct Tests
# ==============================================================================

def test_initial_http_shopaikey_rejected_before_network(tmp_path: Path) -> None:
    """TEST_INITIAL_HTTP_SHOPAIKEY_REJECTED_BEFORE_NETWORK=PASS"""
    with patch("urllib.request.build_opener") as mock_opener_cls, \
         patch("urllib.request.urlopen") as mock_urlopen:
        res = materialize_video_url(
            "http://api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=424074123350da54e35a932e474286d8",
            job_id="job_unsafe_http",
            output_dir=str(tmp_path),
        )

    assert res.ok is False
    assert res.error_code == "provider_result_url_unsafe"
    assert res.error_message == "provider_result_url_unsafe"
    assert res.diagnostics["download_attempts"] == 0
    assert res.diagnostics["download_retries"] == 0
    assert res.diagnostics["download_http_status"] == 0
    assert res.diagnostics["download_bytes"] == 0
    assert res.diagnostics["download_redirect_count"] == 0
    assert res.diagnostics["trusted_video_url"] is False
    assert res.diagnostics["download_error_class"] == "UnsafeOutputURLError"
    assert mock_opener_cls.call_count == 0
    assert mock_urlopen.call_count == 0


def test_initial_host_suffix_attack_rejected_before_network(tmp_path: Path) -> None:
    """TEST_INITIAL_HOST_SUFFIX_ATTACK_REJECTED_BEFORE_NETWORK=PASS"""
    with patch("urllib.request.build_opener") as mock_opener_cls, \
         patch("urllib.request.urlopen") as mock_urlopen:
        res = materialize_video_url(
            "https://api.shopaikey.com.attacker.com/v1/videos/task_123/content?exp=1791504000&sig=424074123350da54e35a932e474286d8",
            job_id="job_suffix_attack",
            output_dir=str(tmp_path),
        )

    assert res.ok is False
    assert res.error_code == "provider_result_url_unsafe"
    assert res.diagnostics["download_attempts"] == 0
    assert mock_opener_cls.call_count == 0
    assert mock_urlopen.call_count == 0


def test_initial_localhost_or_private_ip_mp4_rejected_before_network(tmp_path: Path) -> None:
    """TEST_INITIAL_LOCALHOST_OR_PRIVATE_IP_MP4_REJECTED_BEFORE_NETWORK=PASS"""
    unsafe_targets = [
        "http://localhost/video.mp4",
        "https://127.0.0.1/video.mp4",
        "https://10.0.0.1/video.mp4",
        "https://192.168.1.1/video.mp4",
        "https://169.254.169.254/video.mp4",
    ]
    for url in unsafe_targets:
        with patch("urllib.request.build_opener") as mock_opener_cls, \
             patch("urllib.request.urlopen") as mock_urlopen:
            res = materialize_video_url(url, job_id="job_private_ip", output_dir=str(tmp_path))

        assert res.ok is False
        assert res.error_code == "provider_result_url_unsafe"
        assert res.diagnostics["download_attempts"] == 0
        assert mock_opener_cls.call_count == 0
        assert mock_urlopen.call_count == 0


def test_initial_arbitrary_extensionless_other_host_rejected_before_network(tmp_path: Path) -> None:
    """TEST_INITIAL_ARBITRARY_EXTENSIONLESS_OTHER_HOST_REJECTED_BEFORE_NETWORK=PASS"""
    with patch("urllib.request.build_opener") as mock_opener_cls, \
         patch("urllib.request.urlopen") as mock_urlopen:
        res = materialize_video_url(
            "https://api.someotherhost.com/v1/videos/task_123/content?exp=1791504000&sig=424074123350da54e35a932e474286d8",
            job_id="job_other_host",
            output_dir=str(tmp_path),
        )

    assert res.ok is False
    assert res.error_code == "provider_result_url_unsafe"
    assert res.diagnostics["download_attempts"] == 0
    assert mock_opener_cls.call_count == 0
    assert mock_urlopen.call_count == 0


def test_valid_initial_shopaikey_signed_content_reaches_mocked_opener(tmp_path: Path) -> None:
    """TEST_VALID_INITIAL_SHOPAIKEY_SIGNED_CONTENT_REACHES_MOCKED_OPENER=PASS"""
    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "video/mp4", "Content-Length": "2048"}
    mock_response.geturl.return_value = VALID_SHOPAIKEY_URL
    mock_response.status = 200
    mock_response.getcode.return_value = 200
    mock_response.read = io.BytesIO(b"\x00" * 2048).read

    with patch("urllib.request.build_opener") as mock_opener_cls, \
         patch("services.video_final_output.probe_video", return_value={"ok": True, "duration": 5.0, "has_video": True, "has_audio": True}):
        mock_opener = MagicMock()
        mock_opener.open.return_value.__enter__.return_value = mock_response
        mock_opener_cls.return_value = mock_opener

        res = materialize_video_url(
            VALID_SHOPAIKEY_URL,
            job_id="job_valid_shop",
            output_dir=str(tmp_path),
        )

    assert res.ok is True
    assert mock_opener.open.call_count == 1
    assert res.diagnostics["download_attempts"] == 1
    assert res.diagnostics["download_http_status"] == 200
    assert res.diagnostics["download_bytes"] == 2048


def test_valid_initial_legacy_https_mp4_reaches_mocked_opener(tmp_path: Path) -> None:
    """TEST_VALID_INITIAL_LEGACY_HTTPS_MP4_REACHES_MOCKED_OPENER=PASS"""
    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "video/mp4", "Content-Length": "2048"}
    mock_response.geturl.return_value = LEGACY_SAFE_MP4_URL
    mock_response.status = 200
    mock_response.getcode.return_value = 200
    mock_response.read = io.BytesIO(b"\x00" * 2048).read

    with patch("urllib.request.build_opener") as mock_opener_cls, \
         patch("services.video_final_output.probe_video", return_value={"ok": True, "duration": 5.0, "has_video": True, "has_audio": True}):
        mock_opener = MagicMock()
        mock_opener.open.return_value.__enter__.return_value = mock_response
        mock_opener_cls.return_value = mock_opener

        res = materialize_video_url(
            LEGACY_SAFE_MP4_URL,
            job_id="job_valid_legacy",
            output_dir=str(tmp_path),
        )

    assert res.ok is True
    assert mock_opener.open.call_count == 1
    assert res.diagnostics["download_attempts"] == 1
    assert res.diagnostics["download_http_status"] == 200
    assert res.diagnostics["download_bytes"] == 2048


def test_generic_http_provider_materialize_unsafe_url_zero_network(tmp_path: Path) -> None:
    """TEST_GENERIC_HTTP_PROVIDER_MATERIALIZE_UNSAFE_URL_ZERO_NETWORK=PASS"""
    provider = GenericHttpVideoProvider(
        provider_name="test_generic_http",
        environ={"VIDEO_PROVIDER_OUTPUT_DIR": str(tmp_path)},
    )
    poll_result = VideoPollResult(
        ok=True,
        provider_name="test_generic_http",
        provider_task_id="task_unsafe_poll_999",
        result_url="http://insecure-domain.com/video.mp4",
        status="succeeded",
    )

    with patch("urllib.request.build_opener") as mock_opener_cls, \
         patch("urllib.request.urlopen") as mock_urlopen:
        artifact = provider.materialize_result(poll_result, job_id="job_generic_http_unsafe")

    assert artifact.ok is False
    assert artifact.error_code == "provider_result_url_unsafe"
    assert artifact.diagnostics["download_attempts"] == 0
    assert artifact.diagnostics["download_retries"] == 0
    assert artifact.diagnostics["download_http_status"] == 0
    assert artifact.diagnostics["download_bytes"] == 0
    assert artifact.diagnostics["download_redirect_count"] == 0
    assert mock_opener_cls.call_count == 0
    assert mock_urlopen.call_count == 0


def test_redirect_disallowed_destination_zero_request() -> None:
    """TEST_REDIRECT_DISALLOWED_DESTINATION_ZERO_REQUEST=PASS"""
    disallowed_destinations = [
        "http://api.shopaikey.com/v1/videos/task_123/content?exp=1791504000&sig=abc",  # HTTP downgrade
        "https://127.0.0.1/video.mp4",  # private IP
        "https://attacker.com/exploit.mp4",  # untrusted host
        "https://api.shopaikey.com.attacker.com/v1/videos/task_123/content?exp=1791504000&sig=abc",  # host suffix
        "https://api.shopaikey.com/v1/videos/task_123/content",  # missing exp/sig
    ]
    for disallowed_url in disallowed_destinations:
        handler = _HardenedVideoRedirectHandler(VALID_SHOPAIKEY_URL)
        with pytest.raises(DisallowedRedirectError) as exc_info:
            handler.redirect_request(
                req=MagicMock(),
                fp=None,
                code=302,
                msg="Found",
                headers={},
                newurl=disallowed_url,
            )
        assert exc_info.value.code == 400
        assert "disallowed" in exc_info.value.redirect_reason


def test_signed_query_not_present_in_failure_diagnostics_or_logs(tmp_path: Path) -> None:
    """TEST_SIGNED_QUERY_NOT_PRESENT_IN_FAILURE_DIAGNOSTICS_OR_LOGS=PASS"""
    secret_sig = "SECRET_SIG_VALUE_XYZ_99999"
    secret_exp = "1799999999"
    test_url = f"http://api.shopaikey.com/v1/videos/task_test_sec/content?exp={secret_exp}&sig={secret_sig}"

    with patch("urllib.request.build_opener") as mock_opener_cls:
        res = materialize_video_url(
            test_url,
            job_id="job_leak_test",
            output_dir=str(tmp_path),
        )

    assert res.ok is False
    assert res.error_code == "provider_result_url_unsafe"
    diag_str = str(res.diagnostics)
    assert secret_sig not in diag_str
    assert secret_exp not in diag_str
    assert "sig=" not in diag_str
    assert "exp=" not in diag_str


def test_sanitize_artifact_download_diagnostics_allowlist_and_safety() -> None:
    """Validate that sanitize_artifact_download_diagnostics strictly enforces allowlist, bounds, and strips secrets."""
    raw_dirty = {
        "download_error_class": "urllib.error.HTTPError: 400 Bad Request",
        "download_http_status": "400",
        "download_redirect_count": 1,
        "download_final_url_host": "HTTPS://CDN.EXAMPLE.COM:8080/path?sig=SECRET_SIG&exp=123",
        "download_attempts": "2",
        "download_retries": 1,
        "transient_retry_attempted": "true",
        "download_content_type": "Video/MP4; charset=binary",
        "download_content_length": 1048576,
        "download_bytes": 524288,
        "mp4_validator_result": "VALID_MP4",
        "content_length_verified": False,
        # Untrusted / secret fields that MUST be dropped:
        "full_url": "https://cdn.example.com/video.mp4?sig=SECRET&exp=123",
        "query": "sig=SECRET&exp=123",
        "token": "BEARER_SECRET_TOKEN",
        "headers": {"Authorization": "Bearer secret"},
        "cookie": "session=secret",
    }
    sanitized = sanitize_artifact_download_diagnostics(raw_dirty)

    # Allowlist keys present and properly bounded/sanitized
    assert sanitized["download_error_class"] == "HTTPError"
    assert sanitized["download_http_status"] == 400
    assert sanitized["download_redirect_count"] == 1
    assert sanitized["download_final_url_host"] == "cdn.example.com"
    assert sanitized["download_attempts"] == 2
    assert sanitized["download_retries"] == 1
    assert sanitized["transient_retry_attempted"] is True
    assert sanitized["download_content_type"] == "video/mp4"
    assert sanitized["download_content_length"] == 1048576
    assert sanitized["download_bytes"] == 524288
    assert sanitized["mp4_validator_result"] == "valid_mp4"
    assert sanitized["content_length_verified"] is False

    # Secrets and unknown keys strictly dropped
    assert "full_url" not in sanitized
    assert "query" not in sanitized
    assert "token" not in sanitized
    assert "headers" not in sanitized
    assert "cookie" not in sanitized

    dumped = json.dumps(sanitized)
    assert "SECRET" not in dumped
    assert "Bearer" not in dumped
    assert "session" not in dumped
    assert "8080" not in dumped


def test_materialize_video_url_disallowed_redirect_captures_host_and_status(tmp_path: Path) -> None:
    """When a redirect target is disallowed, materialize_video_url captures destination host and status 400."""
    initial_valid_url = VALID_SHOPAIKEY_URL
    disallowed_dest = "https://untrusted-cdn.evil.com/video.mp4"

    def fake_open(req, *args, **kwargs):
        raise DisallowedRedirectError(disallowed_dest, "redirect_destination_disallowed")

    mock_opener = MagicMock()
    mock_opener.open.side_effect = fake_open

    with patch("urllib.request.build_opener", return_value=mock_opener):
        res = materialize_video_url(
            initial_valid_url,
            job_id="test_redirect_diag",
            output_dir=str(tmp_path),
        )

    assert res.ok is False
    assert res.error_code == "provider_download_failed"
    assert res.diagnostics["download_error_class"] == "DisallowedRedirectError"
    assert res.diagnostics["download_http_status"] == 400
    assert res.diagnostics["download_final_url_host"] == "untrusted-cdn.evil.com"
    assert res.diagnostics["download_attempts"] == 1
    assert res.diagnostics["mp4_validator_result"] == "not_run_download_failed"


