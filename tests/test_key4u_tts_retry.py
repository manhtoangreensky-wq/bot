"""Unit tests for Key4u Minimax TTS transient error classification and retry logic.

Strict duplicate-paid-submit financial safety enforcement:
- Ambiguous transport failures (timeout, connection reset, http_status=0) FAIL CLOSED (0 retries, call_count=1).
- Generic new_api_error without structured transient proof FAILS CLOSED (0 retries, call_count=1).
- Permanent errors (401, 400, 403, 404, 422, FAIL_AUTH) FAIL CLOSED (0 retries, call_count=1).
- Explicit server-side rejections (429, 503, 500/502 with capacity markers) bounded retry.
- Zero network calls, zero paid provider calls, zero wallet mutations.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import bot


# ---------------------------------------------------------------------------
# Unit tests: _is_transient_key4u_tts_error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("http_status", [429, 503])
def test_is_transient_explicit_retry_safe_http_status(http_status):
    result = {"ok": False, "http_status": http_status}
    assert bot._is_transient_key4u_tts_error(result, "FAIL", http_status) is True


@pytest.mark.parametrize("http_status", [200, 400, 401, 403, 404, 405, 422, 504])
def test_is_transient_non_transient_or_ambiguous_http_status(http_status):
    result = {"ok": False, "http_status": http_status, "error_message_safe": "client or gateway error"}
    assert bot._is_transient_key4u_tts_error(result, "FAIL", http_status) is False


@pytest.mark.parametrize("status_code", [
    "FAIL_RATE_LIMIT",
    "FAIL_PROVIDER_GROUP_UNAVAILABLE",
    "fail_rate_limit",
])
def test_is_transient_explicit_safe_status(status_code):
    result = {"ok": False, "status": status_code, "http_status": 503}
    assert bot._is_transient_key4u_tts_error(result, status_code, 503) is True


@pytest.mark.parametrize("http_status", [500, 502])
@pytest.mark.parametrize("status_code", [
    "FAIL_RATE_LIMIT",
    "FAIL_PROVIDER_GROUP_UNAVAILABLE",
    "FAIL_PROVIDER_UNAVAILABLE",
    "FAIL",
    "FAIL_EXCEPTION",
])
def test_is_transient_500_502_structured_status_cannot_bypass_capacity_gate(http_status, status_code):
    """HTTP 500/502 with structured status but lacking capacity markers must fail closed (False)."""
    result = {
        "ok": False,
        "status": status_code,
        "http_status": http_status,
        "error_message_safe": "Internal server error occurred",
        "detail": "upstream failure",
    }
    assert bot._is_transient_key4u_tts_error(result, status_code, http_status) is False


@pytest.mark.parametrize("http_status", [500, 502])
@pytest.mark.parametrize("status_code", [
    "FAIL_RATE_LIMIT",
    "FAIL_PROVIDER_GROUP_UNAVAILABLE",
    "FAIL_PROVIDER_UNAVAILABLE",
    "FAIL",
])
def test_is_transient_500_502_with_explicit_capacity_marker_retries(http_status, status_code):
    """HTTP 500/502 with explicit capacity marker in body text is retry-safe (True)."""
    result = {
        "ok": False,
        "status": status_code,
        "http_status": http_status,
        "error_message_safe": "The model service is temporarily unavailable. Please try again later.",
        "detail": "cluster overloaded",
    }
    assert bot._is_transient_key4u_tts_error(result, status_code, http_status) is True



@pytest.mark.parametrize("status_code", [
    "FAIL_TIMEOUT",
    "FAIL_EXCEPTION",
    "FAIL_AUTH",
    "FAIL_BAD_REQUEST",
    "FAIL_NOT_FOUND",
    "FAIL_MODEL_NOT_FOUND",
    "FAIL_PARAM",
    "FAIL_VOICE_NOT_FOUND",
    "PASS",
])
def test_is_transient_non_retryable_status(status_code):
    result = {"ok": False, "status": status_code}
    assert bot._is_transient_key4u_tts_error(result, status_code, 0) is False


@pytest.mark.parametrize("err_text", [
    "The model service is temporarily unavailable. Please try again later.",
    "upstream server temporarily unavailable",
    "Rate limit exceeded, please try again later",
    "service_unavailable from upstream gateway",
    "Hệ thống đang quá tải, vui lòng thử lại",
    "Cluster is overloaded",
])
def test_is_transient_structured_rejection_text_with_confirmed_http(err_text):
    result = {"ok": False, "error_message_safe": err_text, "http_status": 500}
    assert bot._is_transient_key4u_tts_error(result, "FAIL", 500) is True


@pytest.mark.parametrize("err_text", [
    "read timeout",
    "gateway timeout",
    "connection reset by peer",
    "connection dropped",
    "new_api_error occurred during synthesis",
    "new_api_error",
    "invalid api key credentials",
    "voice_id not found",
])
def test_is_transient_ambiguous_transport_or_generic_errors_rejected(err_text):
    # With HTTP 0 (ambiguous network)
    result_net = {"ok": False, "error_message_safe": err_text, "http_status": 0}
    assert bot._is_transient_key4u_tts_error(result_net, "FAIL", 0) is False

    # With HTTP 500 but ambiguous / generic marker
    result_500 = {"ok": False, "error_message_safe": err_text, "http_status": 500}
    assert bot._is_transient_key4u_tts_error(result_500, "FAIL", 500) is False


def test_is_transient_key4u_tts_error_none_or_empty():
    assert bot._is_transient_key4u_tts_error({}, "", 0) is False
    assert bot._is_transient_key4u_tts_error(None, None, None) is False


# ---------------------------------------------------------------------------
# Unit tests: key4u_minimax_tts_bytes duplicate-paid-submit safety
# ---------------------------------------------------------------------------

def test_key4u_minimax_tts_success_first_attempt():
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(return_value={
            "ok": True,
            "output_bytes": b"synthetic_audio_bytes_123",
            "http_status": 200,
            "status": "PASS",
        })

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 2), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Test synthesis",
                voice_id="Vietnamese_male_1",
            )

            assert status == "PASS"
            assert audio_bytes == b"synthetic_audio_bytes_123"
            assert http_status == 200
            assert "route=key4u_minimax" in detail
            # Exactly 1 call
            assert mock_provider.tts.call_count == 1

    asyncio.run(_test())


def test_key4u_minimax_tts_timeout_stops_immediately_call_count_one():
    """Ambiguous delivery: timeout must never be auto-retried without idempotency."""
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(return_value={
            "ok": False,
            "http_status": 0,
            "status": "FAIL_TIMEOUT",
            "error_class": "FAIL_TIMEOUT",
            "error_message_safe": "Client read timeout after 30s",
        })

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 2), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Timeout safety test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "FAIL_TIMEOUT"
            assert audio_bytes == b""
            assert http_status == 0
            # Financial safety invariant: exactly 1 call, NO duplicate submit
            assert mock_provider.tts.call_count == 1

    asyncio.run(_test())


def test_key4u_minimax_tts_connection_reset_stops_immediately_call_count_one():
    """Ambiguous delivery: connection reset after write must never be auto-retried."""
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(return_value={
            "ok": False,
            "http_status": 0,
            "status": "FAIL_EXCEPTION",
            "error_class": "RemoteProtocolError",
            "error_message_safe": "connection reset by peer",
        })

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 2), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Connection reset test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "FAIL_EXCEPTION"
            assert audio_bytes == b""
            assert http_status == 0
            # Financial safety invariant: exactly 1 call, NO duplicate submit
            assert mock_provider.tts.call_count == 1

    asyncio.run(_test())


def test_key4u_minimax_tts_generic_new_api_error_stops_immediately_call_count_one():
    """Generic error marker: new_api_error alone without structured transient proof must not retry."""
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(return_value={
            "ok": False,
            "http_status": 500,
            "status": "FAIL",
            "error_class": "new_api_error",
            "error_message_safe": "new_api_error: unexpected error occurred",
        })

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 2), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Generic new_api_error test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "FAIL"
            assert audio_bytes == b""
            assert http_status == 500
            # Financial safety invariant: exactly 1 call, NO retry on string matching alone
            assert mock_provider.tts.call_count == 1

    asyncio.run(_test())


def test_key4u_minimax_tts_401_auth_error_stops_immediately_call_count_one():
    """Permanent client error: 401 must not retry."""
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(return_value={
            "ok": False,
            "http_status": 401,
            "status": "FAIL_AUTH",
            "error_class": "FAIL_AUTH",
            "error_message_safe": "Invalid API key credentials",
        })

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 3), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Auth error test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "FAIL_AUTH"
            assert audio_bytes == b""
            assert http_status == 401
            assert mock_provider.tts.call_count == 1

    asyncio.run(_test())


def test_key4u_minimax_tts_explicit_503_retries_and_succeeds():
    """Explicit server-side 503 rejection is retry-safe."""
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(side_effect=[
            {
                "ok": False,
                "http_status": 503,
                "status": "FAIL_PROVIDER_UNAVAILABLE",
                "error_message_safe": "Service temporarily unavailable",
            },
            {
                "ok": True,
                "output_bytes": b"recovered_audio_bytes",
                "http_status": 200,
                "status": "PASS",
            },
        ])

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 2), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Explicit 503 retry test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "PASS"
            assert audio_bytes == b"recovered_audio_bytes"
            assert http_status == 200
            assert mock_provider.tts.call_count == 2

    asyncio.run(_test())


def test_key4u_minimax_tts_explicit_429_retries_and_succeeds():
    """Explicit server-side 429 rate limit is retry-safe."""
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(side_effect=[
            {
                "ok": False,
                "http_status": 429,
                "status": "FAIL_RATE_LIMIT",
                "error_message_safe": "Rate limit exceeded (quá tải)",
            },
            {
                "ok": True,
                "output_bytes": b"recovered_audio_bytes_429",
                "http_status": 200,
                "status": "PASS",
            },
        ])

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 2), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Explicit 429 retry test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "PASS"
            assert audio_bytes == b"recovered_audio_bytes_429"
            assert http_status == 200
            assert mock_provider.tts.call_count == 2

    asyncio.run(_test())


def test_key4u_minimax_tts_original_incident_error_retries_on_structured_rejection():
    """Original incident: 'The model service is temporarily unavailable. Please try again later.'
    retries when accompanied by structured HTTP rejection.
    """
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(side_effect=[
            {
                "ok": False,
                "http_status": 503,
                "status": "FAIL_PROVIDER_UNAVAILABLE",
                "error_message_safe": "The model service is temporarily unavailable. Please try again later.",
            },
            {
                "ok": True,
                "output_bytes": b"incident_recovered_audio",
                "http_status": 200,
                "status": "PASS",
            },
        ])

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 2), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Incident retry test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "PASS"
            assert audio_bytes == b"incident_recovered_audio"
            assert http_status == 200
            assert mock_provider.tts.call_count == 2

    asyncio.run(_test())


def test_key4u_minimax_tts_exhausts_retries_on_persistent_transient_error():
    async def _test():
        mock_provider = MagicMock()
        transient_failure = {
            "ok": False,
            "http_status": 503,
            "status": "FAIL_PROVIDER_UNAVAILABLE",
            "error_message_safe": "The model service is temporarily unavailable. Please try again later.",
        }
        mock_provider.tts = AsyncMock(return_value=transient_failure)

        max_retries = 2
        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", max_retries), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Persistent failure test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "FAIL_PROVIDER_UNAVAILABLE"
            assert audio_bytes == b""
            assert http_status == 503
            # Initial attempt + max_retries = 3 attempts total
            assert mock_provider.tts.call_count == max_retries + 1

    asyncio.run(_test())


def test_key4u_minimax_tts_url_download_retry_success():
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(side_effect=[
            {
                "ok": False,
                "http_status": 503,
                "status": "FAIL_PROVIDER_UNAVAILABLE",
                "error_message_safe": "Temporarily unavailable",
            },
            {
                "ok": True,
                "output_url": "https://example.com/audio_download.mp3",
                "http_status": 200,
                "status": "PASS",
            },
        ])

        mock_download = AsyncMock(return_value=(b"downloaded_mp3_content", "download_ok", 200))

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "_download_audio_url_bytes", mock_download), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 2), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.0):

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Download retry test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "PASS"
            assert audio_bytes == b"downloaded_mp3_content"
            assert http_status == 200
            assert mock_provider.tts.call_count == 2
            mock_download.assert_awaited_once_with("https://example.com/audio_download.mp3")

    asyncio.run(_test())


def test_key4u_minimax_tts_backoff_sleep_called():
    async def _test():
        mock_provider = MagicMock()
        mock_provider.tts = AsyncMock(side_effect=[
            {
                "ok": False,
                "http_status": 503,
                "status": "FAIL_PROVIDER_UNAVAILABLE",
                "error_message_safe": "Service unavailable",
            },
            {
                "ok": True,
                "output_bytes": b"recovered_audio",
                "http_status": 200,
                "status": "PASS",
            },
        ])

        with patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "key4u_provider_instance", return_value=mock_provider), \
             patch.object(bot, "KEY4U_TTS_MAX_RETRIES", 2), \
             patch.object(bot, "KEY4U_TTS_RETRY_BACKOFF", 0.25), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Sleep backoff test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "PASS"
            assert audio_bytes == b"recovered_audio"
            mock_sleep.assert_awaited_once_with(0.25)

    asyncio.run(_test())


def test_key4u_minimax_tts_unconfigured_fails_fast():
    async def _test():
        with patch.object(bot, "key4u_minimax_tts_configured", return_value=False), \
             patch.object(bot, "key4u_provider_instance") as mock_get_provider:

            status, audio_bytes, detail, http_status = await bot.key4u_minimax_tts_bytes(
                text="Unconfigured test",
            )

            assert status == "MISSING"
            assert audio_bytes == b""
            assert http_status == 0
            assert mock_get_provider.call_count == 0

    asyncio.run(_test())
