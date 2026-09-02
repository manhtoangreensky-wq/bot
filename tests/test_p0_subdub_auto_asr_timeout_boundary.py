import asyncio
import hashlib
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeTimeout(Exception):
    pass


class _FakeAsyncClient:
    timeout_values = []
    should_timeout = True

    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, *args, timeout=None, **kwargs):
        del args, kwargs
        type(self).timeout_values.append(timeout)
        if type(self).should_timeout:
            raise _FakeTimeout("request exceeded test timeout")
        return SimpleNamespace(
            status_code=200,
            text='{"metadata":{"duration":1},"results":{"channels":[{"alternatives":[{"transcript":"hello","words":[{"word":"hello","start":0,"end":1,"speaker":0}]}]}]}}',
            headers={"content-type": "application/json"},
            json=lambda: {
                "metadata": {"duration": 1},
                "results": {
                    "channels": [{
                        "alternatives": [{
                            "transcript": "hello",
                            "words": [{"word": "hello", "start": 0, "end": 1, "speaker": 0}],
                        }],
                    }],
                },
            },
        )


def _load_deepgram_timeout_surface():
    source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
    class_start = source.index("class AgentDeepgram:")
    class_end = source.index("\ndef subdub_deepgram_request_params(", class_start)
    params_start = class_end + 1
    params_end = source.index("\ndef deepgram_word_items(", params_start)
    adapter_start = source.index("async def deepgram_asr_adapter(")
    adapter_end = source.index("\ndef detect_image_format(", adapter_start)
    namespace = {
        "httpx": SimpleNamespace(
            AsyncClient=_FakeAsyncClient,
            TimeoutException=_FakeTimeout,
        ),
        "DEEPGRAM_API_KEY": "test-key",
        "AUTO_CAST_UNAVAILABLE": "AUTO_CAST_UNAVAILABLE",
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "sanitize_log_text": lambda value: str(value or ""),
        "deepgram_word_items": lambda _data: [],
        "deepgram_srt_from_response": lambda _data: "01\n00:00:00,000 --> 00:00:01,000\nhello\n",
        "deepgram_vtt_from_srt": lambda _value: "WEBVTT\n",
        "srt_has_timestamp_blocks": lambda _value: True,
        "video_dubbing_srt_timestamp": lambda value: f"00:00:0{int(value)},000",
    }
    for snippet in (
        source[class_start:class_end],
        source[params_start:params_end],
        source[adapter_start:adapter_end],
    ):
        exec(compile(snippet, "bot.py", "exec"), namespace)
    return namespace


def _load_asr_forwarding_surface():
    source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
    start = source.index("async def asr_transcribe_audio(")
    end = source.index("\ndef shopaikey_provider_error_from_payload(", start)
    calls = []

    async def fake_deepgram_adapter(*_args, **kwargs):
        calls.append(kwargs.get("timeout_seconds"))
        return {
            "ok": False,
            "status": "deepgram_timeout",
            "detail": "request_timeout",
            "transcript": "",
            "transcript_json": {},
        }

    namespace = {
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "AUTO_CAST_UNAVAILABLE": "AUTO_CAST_UNAVAILABLE",
        "ASR_PROVIDER": "auto",
        "DEEPGRAM_API_KEY": "test-key",
        "deepgram_asr_adapter": fake_deepgram_adapter,
        "deepgram_segments_from_response": lambda _payload: [],
        "save_provider_attempt": lambda *_args, **_kwargs: None,
        "subdub_long_media": SimpleNamespace(
            is_no_speech_result=lambda *_args, **_kwargs: False,
        ),
    }
    exec(compile(source[start:end], "bot.py", "exec"), namespace)
    return namespace["asr_transcribe_audio"], calls


def _load_media_duration_forwarding_surface(asr_result=None, *, chunking_enabled=False):
    source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
    helper_start = source.index("def subdub_delivery_timeout_seconds_for_duration(")
    helper_end = source.index("\nSUBDUB_MEDIA_BINARY_PROBE_TIMEOUT_SECONDS", helper_start)
    transcribe_start = source.index("async def transcribe_media_to_segments(")
    transcribe_end = source.index("\nasync def video_dubbing_resolve_source_script(", transcribe_start)
    calls = []

    async def fake_asr(*_args, **kwargs):
        calls.append(kwargs.get("timeout_seconds"))
        return dict(asr_result or {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": "hello",
            "segments": [{"index": 1, "start": 0.0, "end": 1.0, "text": "hello", "speaker": 0}],
            "duration_seconds": 1,
            "detail": "fixture",
        })

    def video_dubbing_transcribe_bytes(*_args, **_kwargs):
        raise AssertionError("Auto diarization must use scoped ASR")

    async def fake_long_media_transcribe(
        _source_bytes,
        _content_type,
        _ranges,
        *,
        transcribe_chunk,
        **_kwargs,
    ):
        chunk_result = await transcribe_chunk(b"chunk-audio", "audio/wav")
        return {
            "ok": bool(chunk_result.get("ok")),
            "status": str(chunk_result.get("status") or "PASS"),
            "provider": str(chunk_result.get("provider") or "deepgram"),
            "text": str(chunk_result.get("text") or ""),
            "segments": list(chunk_result.get("segments") or []),
            "duration_seconds": 98,
            "chunk_count": 1,
            "chunk_strategy": "fixture_chunk",
            "global_timing_preserved": True,
        }

    namespace = {
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "AUTO_CAST_UNAVAILABLE": "AUTO_CAST_UNAVAILABLE",
        "SUBDUB_LONG_VIDEO_DELIVERY_TIMEOUT_SECONDS": 30 * 60,
        "SUBDUB_DIRECT_ASR_MAX_SECONDS": 60,
        "_safe_int": lambda value, default=0: int(value or default),
        "hashlib": hashlib,
        "inspect": inspect,
        "subdub_long_video_chunk_plan": lambda _duration, **_kwargs: {
            "chunking_enabled": bool(chunking_enabled),
            "chunk_metadata": [{"index": 1, "start": 0.0, "end": 98.0}],
            "chunk_count": 1,
        },
        "subdub_long_media": SimpleNamespace(
            transcribe_long_media_chunks=fake_long_media_transcribe,
        ),
        "subdub_emit_progress_callback": lambda *_args, **_kwargs: asyncio.sleep(0),
        "asr_transcribe_audio": fake_asr,
        "video_dubbing_transcribe_bytes": video_dubbing_transcribe_bytes,
        "video_dubbing_qc_segments": lambda segments, **_kwargs: list(segments),
        "subdub_detect_language_from_text": lambda _text, language: language or "auto",
        "sanitize_log_text": lambda value: str(value or ""),
    }
    exec(compile(source[helper_start:helper_end], "bot.py", "exec"), namespace)
    exec(compile(source[transcribe_start:transcribe_end], "bot.py", "exec"), namespace)
    return namespace["transcribe_media_to_segments"], calls


def _load_timeout_policy():
    source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
    start = source.index("def subdub_delivery_timeout_seconds_for_duration(")
    end = source.index("\nSUBDUB_MEDIA_BINARY_PROBE_TIMEOUT_SECONDS", start)
    namespace = {"SUBDUB_LONG_VIDEO_DELIVERY_TIMEOUT_SECONDS": 30 * 60}
    exec(compile(source[start:end], "bot.py", "exec"), namespace)
    return namespace["subdub_delivery_timeout_seconds_for_duration"]


class AutoAsrTimeoutBoundaryTests(unittest.TestCase):
    def setUp(self):
        _FakeAsyncClient.timeout_values = []
        _FakeAsyncClient.should_timeout = True

    def test_auto_deepgram_uses_duration_timeout_and_preserves_timeout_status(self):
        namespace = _load_deepgram_timeout_surface()
        adapter = namespace["deepgram_asr_adapter"]

        try:
            result = asyncio.run(
                adapter(
                    b"audio",
                    "audio/wav",
                    require_diarization=True,
                    timeout_seconds=300,
                )
            )
        except TypeError as exc:
            self.fail(f"Auto ASR must accept a duration-derived timeout: {exc}")

        self.assertEqual(_FakeAsyncClient.timeout_values, [300.0])
        self.assertEqual(result["status"], "deepgram_timeout")
        self.assertEqual(result["ok"], False)

    def test_auto_multi_word_timeline_uses_duration_timeout_and_preserves_timeout_status(self):
        namespace = _load_deepgram_timeout_surface()
        adapter = namespace["deepgram_asr_adapter"]

        result = asyncio.run(
            adapter(
                b"audio",
                "audio/wav",
                require_diarization=False,
                timeout_seconds=300,
            )
        )

        self.assertEqual(_FakeAsyncClient.timeout_values, [300.0])
        self.assertEqual(result["status"], "deepgram_timeout")
        self.assertEqual(result["ok"], False)

    def test_non_diarized_adapter_preserves_timeout_error_when_diagnostic_status_is_fail(self):
        namespace = _load_deepgram_timeout_surface()
        adapter = namespace["deepgram_asr_adapter"]

        async def timeout_diagnostic(*_args, **_kwargs):
            return {
                "status": "FAIL",
                "http_status": 0,
                "error": "deepgram_timeout",
                "transcript": "",
                "transcript_json": {},
            }

        namespace["AgentDeepgram"].diagnostic = timeout_diagnostic
        result = asyncio.run(adapter(b"audio", "audio/wav", timeout_seconds=300))

        self.assertEqual(result["status"], "deepgram_timeout")
        self.assertEqual(result["ok"], False)

    def test_owner_timeout_bands_remain_exact(self):
        timeout_for_duration = _load_timeout_policy()
        cases = (
            (0, 5 * 60),
            (5 * 60 - 0.001, 5 * 60),
            (5 * 60, 15 * 60),
            (10 * 60 - 0.001, 15 * 60),
            (10 * 60, 25 * 60),
            (20 * 60 - 0.001, 25 * 60),
            (20 * 60, 30 * 60),
        )
        for duration, expected in cases:
            with self.subTest(duration=duration):
                self.assertEqual(timeout_for_duration(duration), expected)

    def test_manual_deepgram_default_timeout_remains_60_seconds(self):
        namespace = _load_deepgram_timeout_surface()
        diagnostic = namespace["AgentDeepgram"].diagnostic

        result = asyncio.run(diagnostic(b"audio", "audio/wav"))

        self.assertEqual(_FakeAsyncClient.timeout_values, [60.0])
        self.assertEqual(result["status"], "FAIL")

    def test_auto_asr_forwards_timeout_to_deepgram_without_losing_classification(self):
        asr_transcribe_audio, calls = _load_asr_forwarding_surface()

        try:
            result = asyncio.run(
                asr_transcribe_audio(
                    b"audio",
                    "audio/wav",
                    allow_confirmed_product=True,
                    require_diarization=True,
                    timeout_seconds=300,
                )
            )
        except TypeError as exc:
            self.fail(f"Auto ASR must forward the duration-derived timeout: {exc}")

        self.assertEqual(calls, [300.0])
        self.assertEqual(result["status"], "deepgram_timeout")

    def test_auto_multi_word_timeline_does_not_relabel_deepgram_timeout(self):
        asr_transcribe_audio, calls = _load_asr_forwarding_surface()

        result = asyncio.run(
            asr_transcribe_audio(
                b"audio",
                "audio/wav",
                allow_confirmed_product=True,
                require_auto_multi_word_timeline=True,
                media_duration_seconds=133.37542,
                timeout_seconds=300,
            )
        )

        self.assertEqual(calls, [300.0])
        self.assertEqual(result["status"], "deepgram_timeout")

    def test_media_duration_selects_five_minute_timeout_for_auto_asr(self):
        transcribe_media, calls = _load_media_duration_forwarding_surface()

        result = asyncio.run(
            transcribe_media(
                {
                    "bytes": b"audio",
                    "content_type": "audio/wav",
                    "media_kind": "audio",
                    "duration_seconds": 98,
                },
                duration_seconds=98,
                allow_confirmed_product=True,
                require_diarization=True,
            )
        )

        self.assertTrue(result["output_valid"])
        self.assertEqual(calls, [300.0])

    def test_media_timeout_is_not_relabelled_as_empty_or_auto_unavailable(self):
        transcribe_media, _calls = _load_media_duration_forwarding_surface({
            "ok": False,
            "status": "deepgram_timeout",
            "provider": "deepgram",
            "text": "",
            "segments": [],
            "detail": "request_timeout",
        })

        result = asyncio.run(
            transcribe_media(
                {
                    "bytes": b"audio",
                    "content_type": "audio/wav",
                    "media_kind": "audio",
                    "duration_seconds": 98,
                },
                duration_seconds=98,
                allow_confirmed_product=True,
                require_diarization=True,
            )
        )

        self.assertFalse(result["output_valid"])
        self.assertEqual(result["status"], "deepgram_timeout")

    def test_chunked_auto_media_forwards_same_duration_timeout(self):
        transcribe_media, calls = _load_media_duration_forwarding_surface(
            chunking_enabled=True,
        )

        result = asyncio.run(
            transcribe_media(
                {
                    "bytes": b"audio",
                    "content_type": "audio/wav",
                    "media_kind": "audio",
                    "duration_seconds": 98,
                },
                duration_seconds=98,
                allow_confirmed_product=True,
                require_diarization=True,
            )
        )

        self.assertTrue(result["output_valid"])
        self.assertEqual(result["chunk_strategy"], "fixture_chunk")
        self.assertEqual(calls, [300.0])


if __name__ == "__main__":
    unittest.main()
