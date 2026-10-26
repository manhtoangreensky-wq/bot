"""Unit tests for Web Realtime Gateway endpoints, HMAC token, and Session API (RT-02).

Governed by owner-governed-codex, locked-focus-engineering.
"""

import time
from services.copyfast_realtime_translate import (
    generate_stream_token,
    verify_stream_token,
    CreateSessionRequest,
    create_live_translate_session,
    get_session_status,
    export_session_subtitles,
    _ACTIVE_SESSIONS,
)
from services.realtime_translate_session import RealtimeTranscriptSegment


class MockRequest:
    def __init__(self, user_id="test_owner_88"):
        self.state = type("State", (), {"user_id": user_id})()


def test_stream_token_generation_and_verification():
    session_id = "rts_test_123"
    owner_id = "user_456"
    exp = int(time.time()) + 300

    token = generate_stream_token(session_id, owner_id, exp)
    assert token is not None

    # Valid verification
    verified_owner = verify_stream_token(token, session_id)
    assert verified_owner == owner_id

    # Wrong session ID must fail
    assert verify_stream_token(token, "wrong_session") is None

    # Expired token must fail
    expired_token = generate_stream_token(session_id, owner_id, int(time.time()) - 10)
    assert verify_stream_token(expired_token, session_id) is None


def test_session_creation_and_retrieval():
    import asyncio

    req = CreateSessionRequest(
        source_language="en",
        target_language="vi",
        mode="LIVE_DUB_BILINGUAL",
    )
    mock_request = MockRequest(user_id="user_owner_99")

    response = asyncio.run(create_live_translate_session(req, mock_request))
    assert response.ok is True
    assert response.session_id.startswith("rts_")
    assert response.stream_token is not None
    assert "/stream?token=" in response.websocket_url

    # Check status
    status = asyncio.run(get_session_status(response.session_id))
    assert status["ok"] is True
    assert status["state"] == "created"
    assert status["source_language"] == "en"
    assert status["target_language"] == "vi"

    # Add a dummy segment
    session = _ACTIVE_SESSIONS[response.session_id]
    session.add_segment(
        RealtimeTranscriptSegment(
            segment_id="seg_01",
            sequence=1,
            start_ms=0,
            end_ms=2500,
            source_text="Breaking news",
            translated_text="Tin nóng",
            is_final=True,
        )
    )

    # Export SRT
    srt_res = asyncio.run(export_session_subtitles(response.session_id, format="srt"))
    assert srt_res["ok"] is True
    assert "Tin nóng" in srt_res["content"]

    # Export VTT
    vtt_res = asyncio.run(export_session_subtitles(response.session_id, format="vtt"))
    assert vtt_res["ok"] is True
    assert "WEBVTT" in vtt_res["content"]
    assert "Tin nóng" in vtt_res["content"]
