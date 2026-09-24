"""Unit tests for Key4u Minimax TTS transient error classification and retry logic.

Zero network calls, zero paid provider calls, zero wallet mutations.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import bot


# ---------------------------------------------------------------------------
# Unit tests: _is_transient_key4u_tts_error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("http_status", [429, 500, 502, 503, 504])
def test_is_transient_key4u_tts_error_transient_http_status(http_status):
    result = {"ok": False, "http_status": http_status}
    assert bot._is_transient_key4u_tts_error(result, "FAIL", http_status) is True


@pytest.mark.parametrize("http_status", [200, 400, 401, 403, 404, 422])
def test_is_transient_key4u_tts_error_non_transient_http_status(http_status):
    result = {"ok": False, "http_status": http_status, "error_message_safe": "client error"}
    assert bot._is_transient_key4u_tts_error(result, "FAIL", http_status) is False


@pytest.mark.parametrize("status_code", [
    "FAIL_TIMEOUT",
    "FAIL_PROVIDER_UNAVAILABLE",
    "FAIL_RATE_LIMIT",
    "FAIL_PROVIDER_GROUP_UNAVAILABLE",
    "fail_timeout",
    "fail_rate_limit",
])
def test_is_transient_key4u_tts_error_transient_status(status_code):
    result = {"ok": False, "status": status_code}
    assert bot._is_transient_key4u_tts_error(result, status_code, 0) is True


@pytest.mark.parametrize("status_code", [
    "FAIL_AUTH",
    "FAIL_INVALID_REQUEST",
    "FAIL_PARAM",
    "FAIL_VOICE_NOT_FOUND",
    "PASS",
])
def test_is_transient_key4u_tts_error_non_transient_status(status_code):
    result = {"ok": False, "status": status_code, "error_message_safe": "invalid request"}
    assert bot._is_transient_key4u_tts_error(result, status_code, 400) is False


@pytest.mark.parametrize("err_text", [
    "upstream server temporarily unavailable",
    "Rate limit exceeded, please try again later",
    "service_unavailable from upstream gateway",
    "Hệ thống đang quá tải, vui lòng thử lại",
    "Cluster is overloaded",
    "upstream read timeout",
    "connection reset by peer",
    "new_api_error occurred during synthesis",
])
def test_is_transient_key4u_tts_error_text_markers(err_text):
    result = {"ok": False, "error_message_safe": err_text}
    assert bot._is_transient_key4u_tts_error(result, "FAIL", 0) is True


def test_is_transient_key4u_tts_error_none_or_empty():
    assert bot._is_transient_key4u_tts_error({}, "", 0) is False
    assert bot._is_transient_key4u_tts_error(None, None, None) is False


# ---------------------------------------------------------------------------
# Unit tests: key4u_minimax_tts_bytes
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
            assert mock_provider.tts.call_count == 1

    asyncio.run(_test())


def test_key4u_minimax_tts_retries_transient_error_and_succeeds():
    async def _test():
        mock_provider = MagicMock()
        # 1st attempt: 503 Service Unavailable (transient)
        # 2nd attempt: Success with bytes
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
                text="Transient retry test",
                voice_id="Vietnamese_male_1",
            )

            assert status == "PASS"
            assert audio_bytes == b"recovered_audio_bytes"
            assert http_status == 200
            assert mock_provider.tts.call_count == 2

    asyncio.run(_test())


def test_key4u_minimax_tts_non_transient_stops_immediately():
    async def _test():
        mock_provider = MagicMock()
        # 1st attempt: 401 Unauthorized (permanent error, should NOT retry)
        mock_provider.tts = AsyncMock(return_value={
            "ok": False,
            "http_status": 401,
            "status": "FAIL_AUTH",
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
            assert "Invalid API key credentials" in detail
            # Exactly 1 call: must NOT retry non-transient error
            assert mock_provider.tts.call_count == 1

    asyncio.run(_test())


def test_key4u_minimax_tts_exhausts_retries_on_persistent_transient_error():
    async def _test():
        mock_provider = MagicMock()
        transient_failure = {
            "ok": False,
            "http_status": 429,
            "status": "FAIL_RATE_LIMIT",
            "error_message_safe": "Rate limit exceeded (quá tải)",
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

            assert status == "FAIL_RATE_LIMIT"
            assert audio_bytes == b""
            assert http_status == 429
            # Initial attempt + max_retries = 3 attempts total
            assert mock_provider.tts.call_count == max_retries + 1

    asyncio.run(_test())


def test_key4u_minimax_tts_url_download_retry_success():
    async def _test():
        mock_provider = MagicMock()
        # 1st attempt: 502 Bad Gateway
        # 2nd attempt: Success with output_url
        mock_provider.tts = AsyncMock(side_effect=[
            {
                "ok": False,
                "http_status": 502,
                "status": "FAIL_PROVIDER_UNAVAILABLE",
                "error_message_safe": "Bad Gateway",
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
            # 1 retry performed -> sleep called once with base_backoff * 1 = 0.25
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
