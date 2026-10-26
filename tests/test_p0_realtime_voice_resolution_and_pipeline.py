"""Unit tests for Realtime Voice Resolution and End-to-End Adapter Pipeline (RT-01).

Governed by owner-governed-codex, locked-focus-engineering.
"""

import asyncio
try:
    import pytest
except ImportError:
    class _MockPytest:
        class mark:
            @staticmethod
            def asyncio(f):
                return f
    pytest = _MockPytest()

from services.realtime_asr_adapter import (
    RealtimeASRAdapter,
    RealtimeASRResult,
    set_test_asr_mock_handler,
)
from services.realtime_audio_ingress import (
    RealtimeAudioIngressBuffer,
    SpeechSegment,
)
from services.realtime_translate_session import (
    RealtimeSessionConfig,
    RealtimeTranscriptSegment,
    RealtimeTranslateMode,
    RealtimeTranslateSession,
)
from services.realtime_translation_adapter import (
    RealtimeTranslationAdapter,
    RealtimeTranslationResult,
    set_test_translation_mock_handler,
)
from services.realtime_tts_adapter import (
    RealtimeTTSAdapter,
    RealtimeTTSResult,
    set_test_tts_mock_handler,
)
from services.realtime_voice_resolution import RealtimeVoiceResolver


def test_voice_resolution_authority():
    resolver = RealtimeVoiceResolver()

    # Default Vietnamese male
    v_vi_male = resolver.resolve(target_language="vi", gender_preference="male")
    assert v_vi_male.voice_id == "vi-VN-NamMinhNeural"
    assert v_vi_male.gender == "male"
    assert v_vi_male.language_code == "vi"

    # Vietnamese female
    v_vi_female = resolver.resolve(target_language="vi", gender_preference="female")
    assert v_vi_female.voice_id == "vi-VN-HoaiMyNeural"
    assert v_vi_female.gender == "female"

    # English male
    v_en_male = resolver.resolve(target_language="en", gender_preference="male")
    assert v_en_male.voice_id == "en-US-GuyNeural"

    # Voice Vault profile lookup
    vault_data = {
        "vault_toan_01": {
            "voice_id": "custom-voice-clone-toan",
            "provider": "voice_vault",
            "gender": "male",
        }
    }
    v_vault = resolver.resolve(
        target_language="vi",
        voice_profile_id="vault_toan_01",
        voice_vault_data=vault_data,
    )
    assert v_vault.voice_id == "custom-voice-clone-toan"
    assert v_vault.provider == "voice_vault"


@pytest.mark.asyncio
async def test_end_to_end_realtime_pipeline_mocked():
    # Setup test mock handlers
    def mock_asr(segment: SpeechSegment, language: str) -> RealtimeASRResult:
        return RealtimeASRResult(
            ok=True,
            text="Welcome to TOAN AAS live dubbing system",
            start_ms=segment.start_ms,
            end_ms=segment.end_ms,
            language="en",
            provider="mock_faster_whisper",
        )

    def mock_trans(text: str, target_lang: str) -> RealtimeTranslationResult:
        return RealtimeTranslationResult(
            ok=True,
            source_text=text,
            translated_text="Chào mừng bạn đến với hệ thống lồng tiếng trực tiếp TOAN AAS",
            target_language=target_lang,
            provider="mock_llm",
        )

    def mock_tts(text: str, voice) -> RealtimeTTSResult:
        return RealtimeTTSResult(
            ok=True,
            audio_base64="UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
            duration_ms=2100,
            format="mp3",
            provider=voice.provider,
        )

    set_test_asr_mock_handler(mock_asr)
    set_test_translation_mock_handler(mock_trans)
    set_test_tts_mock_handler(mock_tts)

    try:
        # Initialize session
        config = RealtimeSessionConfig(
            owner_id="user_owner_01",
            source_language="en",
            target_language="vi",
            mode=RealtimeTranslateMode.LIVE_DUB,
        )
        session = RealtimeTranslateSession("sess_live_e2e_01", config)
        session.start()

        # Ingress buffer
        ingress = RealtimeAudioIngressBuffer()
        asr_adapter = RealtimeASRAdapter()
        trans_adapter = RealtimeTranslationAdapter(target_language="vi")
        voice_resolver = RealtimeVoiceResolver()
        tts_adapter = RealtimeTTSAdapter()

        # Synthetic PCM chunk
        pcm_bytes = b"\x10\x20" * 8000  # 0.5s audio
        ingress.push_chunk(seq=1, pcm_bytes=pcm_bytes, timestamp_ms=0)
        speech_segment = ingress.flush()
        assert speech_segment is not None

        # Accept sequence in session
        assert session.accept_audio_sequence(1, duration_ms=speech_segment.duration_ms) is True

        # 1. ASR
        asr_res = await asr_adapter.transcribe(speech_segment, language="en")
        assert asr_res.ok
        assert asr_res.text == "Welcome to TOAN AAS live dubbing system"

        # 2. Translation
        trans_res = await trans_adapter.translate(asr_res.text, target_language="vi")
        assert trans_res.ok
        assert "Chào mừng bạn" in trans_res.translated_text

        # 3. Voice Resolution
        resolved_voice = voice_resolver.resolve(target_language="vi", gender_preference="male")
        assert resolved_voice.voice_id == "vi-VN-NamMinhNeural"

        # 4. TTS
        tts_res = await tts_adapter.synthesize(trans_res.translated_text, resolved_voice)
        assert tts_res.ok
        assert tts_res.audio_base64 is not None
        assert tts_res.duration_ms == 2100

        # Record segment in session
        final_seg = RealtimeTranscriptSegment(
            segment_id=speech_segment.segment_id,
            sequence=1,
            start_ms=speech_segment.start_ms,
            end_ms=speech_segment.end_ms,
            source_text=asr_res.text,
            translated_text=trans_res.translated_text,
            is_final=True,
            tts_audio_base64=tts_res.audio_base64,
        )
        session.add_segment(final_seg)
        session.mark_sequence_processed(1)

        # Check export
        srt = session.export_srt()
        assert "Chào mừng bạn đến với hệ thống lồng tiếng trực tiếp TOAN AAS" in srt

    finally:
        # Reset mock handlers
        set_test_asr_mock_handler(None)
        set_test_translation_mock_handler(None)
        set_test_tts_mock_handler(None)
