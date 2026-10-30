"""Unit tests for RealtimeTranslateSession FSM, sequence idempotency, and metering (RT-01).

Governed by owner-governed-codex, locked-focus-engineering.
"""

try:
    import pytest
except ImportError:
    import contextlib
    class _MockPytest:
        @staticmethod
        def raises(exc):
            @contextlib.contextmanager
            def _cm():
                try:
                    yield
                except exc:
                    pass
                else:
                    raise AssertionError(f"Expected {exc} was not raised")
            return _cm()
    pytest = _MockPytest()

from services.realtime_translate_session import (
    RealtimeSessionConfig,
    RealtimeSessionState,
    RealtimeTranscriptSegment,
    RealtimeTranslateMode,
    RealtimeTranslateSession,
)


def test_session_lifecycle_transitions():
    config = RealtimeSessionConfig(
        owner_id="user_123",
        source_language="en",
        target_language="vi",
        mode=RealtimeTranslateMode.LIVE_DUB_BILINGUAL,
    )
    session = RealtimeTranslateSession("sess_test_01", config)

    # Initial state
    assert session.state == RealtimeSessionState.CREATED
    assert session.started_at is None

    # Start session
    session.start()
    assert session.state == RealtimeSessionState.ACTIVE
    assert session.started_at is not None

    # Pause session
    session.pause()
    assert session.state == RealtimeSessionState.PAUSED

    # Resume session
    session.resume()
    assert session.state == RealtimeSessionState.ACTIVE

    # End session
    session.end()
    assert session.state == RealtimeSessionState.ENDED
    assert session.ended_at is not None

    # Invalid transition from ENDED to ACTIVE must raise ValueError
    with pytest.raises(ValueError):
        session.start()


def test_session_sequence_deduplication():
    config = RealtimeSessionConfig(owner_id="user_123")
    session = RealtimeTranslateSession("sess_test_02", config)
    session.start()

    # Sequence 1: accepted
    assert session.accept_audio_sequence(1, duration_ms=1000) is True
    session.mark_sequence_processed(1)

    # Sequence 1 again: duplicate must be rejected
    assert session.accept_audio_sequence(1, duration_ms=1000) is False

    # Sequence 2: accepted
    assert session.accept_audio_sequence(2, duration_ms=1000) is True
    session.mark_sequence_processed(2)

    # Sequence 1 (out-of-order lower seq): must be rejected
    assert session.accept_audio_sequence(1, duration_ms=1000) is False

    # Check total audio accrued
    assert session.total_audio_ms == 2000


def test_session_metering_block_accrual():
    config = RealtimeSessionConfig(owner_id="user_123", metering_block_seconds=60)
    session = RealtimeTranslateSession("sess_test_03", config)
    session.start()

    # Feed 45 seconds -> 0 full blocks
    session.accept_audio_sequence(1, duration_ms=45000)
    assert session.compute_pending_metering_blocks() == 0

    # Feed another 20 seconds (total 65s) -> 1 block accrued
    session.accept_audio_sequence(2, duration_ms=20000)
    assert session.compute_pending_metering_blocks() == 1

    # Calling again immediately without new audio -> 0 blocks
    assert session.compute_pending_metering_blocks() == 0

    # Feed another 60 seconds (total 125s) -> 1 more block accrued (total 2)
    session.accept_audio_sequence(3, duration_ms=60000)
    assert session.compute_pending_metering_blocks() == 1
    assert session.consumed_blocks == 2


def test_session_srt_and_vtt_export():
    config = RealtimeSessionConfig(owner_id="user_123")
    session = RealtimeTranslateSession("sess_test_04", config)

    # Add segments
    session.add_segment(
        RealtimeTranscriptSegment(
            segment_id="seg_01",
            sequence=1,
            start_ms=1000,
            end_ms=3500,
            source_text="Hello world",
            translated_text="Xin chào thế giới",
            is_final=True,
        )
    )
    session.add_segment(
        RealtimeTranscriptSegment(
            segment_id="seg_02",
            sequence=2,
            start_ms=4000,
            end_ms=6200,
            source_text="This is live translation",
            translated_text="Đây là bản dịch trực tiếp",
            is_final=True,
        )
    )

    srt = session.export_srt()
    assert "00:00:01,000 --> 00:00:03,500" in srt
    assert "Xin chào thế giới" in srt
    assert "00:00:04,000 --> 00:00:06,200" in srt
    assert "Đây là bản dịch trực tiếp" in srt

    vtt = session.export_vtt()
    assert "WEBVTT" in vtt
    assert "00:00:01.000 --> 00:00:03.500" in vtt
    assert "Xin chào thế giới" in vtt
