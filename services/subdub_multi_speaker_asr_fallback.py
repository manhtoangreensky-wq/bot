"""Fail-closed provider re-diarization for underclustered SubDub multi jobs."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import os
import re
import threading
import warnings
from collections.abc import Awaitable, Callable
from typing import Any
import wave

import httpx

from services import subdub_speaker_cast as speaker_cast


AUTO_CAST_UNAVAILABLE = "AUTO_CAST_UNAVAILABLE"
GEMINI_TRANSCRIBE_MODEL = "gemini-3.5-transcribe"
GEMINI_INTERACTIONS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/interactions"
)
KEY4U_FALLBACK_BASE_URL = "https://api.key4u.vn/v1"
MIN_MULTI_SPEAKERS = 3
MAX_GEMINI_DIARIZATION_SPEAKERS = 8
MIN_WORDS_PER_SPEAKER = 2
MIN_SEGMENT_SPEAKER_CONFIDENCE = 0.70
MAX_REDIARIZATION_SECONDS = 5 * 60
TARGET_SAMPLE_RATE = 16_000
PCM_STREAM_CHUNK_BYTES = 1024 * 1024
KEY4U_TRANSCRIPT_MAX_ATTEMPTS = 2
KEY4U_TRANSCRIPT_RETRY_DELAY_SECONDS = 1.0
GEMINI_INTERACTION_MAX_POLLS = 40
GEMINI_INTERACTION_POLL_SECONDS = 3.0
GEMINI_EMPTY_RESULT_MAX_ATTEMPTS = 3
GEMINI_EMPTY_RESULT_RETRY_DELAY_SECONDS = 1.0
MAX_DIRECT_AUDIO_BYTES = MAX_REDIARIZATION_SECONDS * 44_100 * 2 * 2
_REDIARIZATION_LOCK = threading.Lock()


def _offset_seconds(value: object) -> float:
    text = str(value or "").strip().lower()
    if text.endswith("s"):
        text = text[:-1]
    try:
        parsed = float(text)
    except (TypeError, ValueError, OverflowError):
        return -1.0
    return parsed if math.isfinite(parsed) else -1.0


def _ordered_speaker_labels(items: object) -> list[str]:
    labels: list[str] = []
    if not isinstance(items, list):
        return labels
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("speaker") or "").strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def detected_speaker_count(segments: object) -> int:
    labels: list[str] = []
    if not isinstance(segments, list):
        return 0
    for item in segments:
        if not isinstance(item, dict):
            continue
        raw = item.get("speaker_id")
        if raw is None:
            raw = item.get("speaker")
        label = str(raw).strip() if raw is not None else ""
        if label and label not in labels:
            labels.append(label)
    return len(labels)


def gemini_word_info_annotation_count(payload: object) -> int:
    count = 0
    steps = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(steps, list):
        return 0
    for step in steps:
        content = step.get("content") if isinstance(step, dict) else None
        if not isinstance(content, list):
            continue
        for content_item in content:
            annotations = (
                content_item.get("annotations")
                if isinstance(content_item, dict)
                else None
            )
            if not isinstance(annotations, list):
                continue
            count += sum(
                isinstance(annotation, dict)
                and str(annotation.get("type") or "").strip().lower()
                == "word_info"
                for annotation in annotations
            )
    return count


def _canonical_words(words: object) -> list[dict]:
    """Deduplicate exact rows and reject one word identity claimed by two labels."""

    if not isinstance(words, list):
        return []
    canonical: list[dict] = []
    speakers_by_identity: dict[tuple[float, float, str], str] = {}
    for item in words:
        if not isinstance(item, dict):
            return []
        speaker = str(item.get("speaker") or "").strip()
        text = re.sub(r"\s+", " ", str(item.get("word") or "")).strip()
        try:
            start = round(float(item.get("start")), 3)
            end = round(float(item.get("end")), 3)
        except (TypeError, ValueError, OverflowError):
            return []
        if (
            not speaker
            or not text
            or not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0.0
            or end <= start
        ):
            return []
        identity = (start, end, text.casefold())
        existing = speakers_by_identity.get(identity)
        if existing is not None:
            if existing != speaker:
                return []
            continue
        speakers_by_identity[identity] = speaker
        canonical.append(
            {
                "word": text,
                "start": start,
                "end": end,
                "speaker": speaker,
            }
        )
    canonical.sort(
        key=lambda item: (
            item["start"],
            item["end"],
            item["speaker"],
            item["word"].casefold(),
        )
    )
    return canonical


def extract_gemini_multi_diarized_words(payload: object) -> list[dict]:
    """Extract 3-8 first-seen labels; no expected-speaker count is accepted."""

    words: list[dict] = []
    steps = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(steps, list):
        return []
    for step in steps:
        content = step.get("content") if isinstance(step, dict) else None
        if not isinstance(content, list):
            continue
        for content_item in content:
            annotations = (
                content_item.get("annotations")
                if isinstance(content_item, dict)
                else None
            )
            if not isinstance(annotations, list):
                continue
            for annotation in annotations:
                if (
                    not isinstance(annotation, dict)
                    or str(annotation.get("type") or "").strip().lower()
                    != "word_info"
                ):
                    continue
                speaker = str(
                    annotation.get("speaker")
                    or annotation.get("speaker_label")
                    or ""
                ).strip()
                start = _offset_seconds(annotation.get("start_offset"))
                end = _offset_seconds(annotation.get("end_offset"))
                text = str(
                    annotation.get("text") or annotation.get("word") or ""
                ).strip()
                if speaker and text and start >= 0.0 and end > start:
                    words.append(
                        {
                            "word": text,
                            "start": round(start, 3),
                            "end": round(end, 3),
                            "speaker": speaker,
                        }
                    )
    words = _canonical_words(words)
    if not words:
        return []
    labels = _ordered_speaker_labels(words)
    if not MIN_MULTI_SPEAKERS <= len(labels) <= MAX_GEMINI_DIARIZATION_SPEAKERS:
        return []
    if any(
        sum(item["speaker"] == label for item in words)
        < MIN_WORDS_PER_SPEAKER
        for label in labels
    ):
        return []
    return words


def apply_multi_diarized_words_to_segments(
    segments: object,
    words: object,
) -> list[dict]:
    """Map word-level provider identities onto existing timestamped cues."""

    if (
        not isinstance(segments, list)
        or not segments
        or not isinstance(words, list)
        or not words
    ):
        return []
    words = _canonical_words(words)
    if not words:
        return []
    labels = _ordered_speaker_labels(words)
    if not MIN_MULTI_SPEAKERS <= len(labels) <= MAX_GEMINI_DIARIZATION_SPEAKERS:
        return []
    if any(
        sum(item["speaker"] == label for item in words)
        < MIN_WORDS_PER_SPEAKER
        for label in labels
    ):
        return []
    label_numbers = {label: index for index, label in enumerate(labels)}
    mapped: list[dict] = []
    previous_start = -1.0
    for raw_segment in segments:
        if not isinstance(raw_segment, dict):
            return []
        try:
            start = float(raw_segment.get("start"))
            end = float(raw_segment.get("end"))
        except (TypeError, ValueError, OverflowError):
            return []
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0.0
            or end <= start
            or start < previous_start
        ):
            return []
        previous_start = start
        evidence = {label: 0.0 for label in labels}
        word_counts = {label: 0 for label in labels}
        for item in words:
            if not isinstance(item, dict):
                continue
            label = str(item.get("speaker") or "").strip()
            if label not in evidence:
                continue
            try:
                word_start = float(item.get("start"))
                word_end = float(item.get("end"))
            except (TypeError, ValueError, OverflowError):
                continue
            overlap = max(0.0, min(end, word_end) - max(start, word_start))
            if overlap > 0.0:
                evidence[label] += overlap
                word_counts[label] += 1
        total = sum(evidence.values())
        if total <= 0.0:
            return []
        selected = max(evidence, key=evidence.get)
        confidence = evidence[selected] / total
        if confidence < MIN_SEGMENT_SPEAKER_CONFIDENCE or word_counts[selected] < 1:
            return []
        speaker_number = label_numbers[selected]
        mapped.append(
            {
                **raw_segment,
                "speaker": speaker_number,
                "speaker_confidence": round(float(confidence), 6),
                "speaker_id": speaker_cast.normalized_speaker_key(
                    0,
                    speaker_number,
                ),
                "chunk_index": 0,
            }
        )
    if (
        len(mapped) != len(segments)
        or detected_speaker_count(mapped) != len(labels)
    ):
        return []
    return mapped


def _provider_timestamp_segments_valid(payload: object) -> bool:
    segments = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(segments, list) or not segments:
        return False
    previous_start = -1.0
    for segment in segments:
        if not isinstance(segment, dict):
            return False
        try:
            start = float(segment.get("start"))
            end = float(segment.get("end"))
        except (TypeError, ValueError, OverflowError):
            return False
        if (
            not str(segment.get("text") or "").strip()
            or not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0.0
            or end <= start
            or start < previous_start
        ):
            return False
        previous_start = start
    return True


def _key4u_transcript_retryable(payload: object) -> bool:
    if not isinstance(payload, dict):
        return True
    transcript = str(payload.get("text") or "").strip()
    segments = payload.get("segments")
    if transcript and isinstance(segments, list) and segments:
        return payload.get("provider_timestamps") is True
    try:
        http_status = int(payload.get("http_status") or 0)
    except (TypeError, ValueError, OverflowError):
        http_status = 0
    if http_status:
        return bool(
            200 <= http_status < 300
            or http_status in {408, 425, 429}
            or 500 <= http_status < 600
        )
    return str(payload.get("status") or "").strip().upper() in {
        "",
        "EMPTY_TRANSCRIPT",
        "FAIL",
        "FAIL_PROVIDER_ERROR",
        "FAIL_RETRYABLE",
        "FAIL_TIMEOUT",
        "SEGMENT_GENERATION_FAILED",
    }


async def run_multi_speaker_fallback(
    audio_bytes: bytes,
    content_type: str,
    *,
    key4u_transcribe: Callable[..., Awaitable[dict]],
    key4u_api_key: str,
    key4u_endpoint: str,
    gemini_api_key: str,
    language: str = "auto",
    duration_seconds: float = 0.0,
) -> dict:
    """Recover one confirmed multi job from timed Key4U + Gemini identities."""

    try:
        duration_value = float(duration_seconds or 0.0)
    except (TypeError, ValueError, OverflowError):
        duration_value = 0.0
    if (
        not math.isfinite(duration_value)
        or not 0.0 < duration_value <= MAX_REDIARIZATION_SECONDS
        or len(audio_bytes or b"") > MAX_DIRECT_AUDIO_BYTES
    ):
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "",
            "text": "",
            "segments": [],
            "key4u_attempt_count": 0,
            "key4u_retry_used": False,
            "detail": "multi_speaker_fallback_media_out_of_bounds",
        }
    if not (
        audio_bytes
        and callable(key4u_transcribe)
        and key4u_api_key
        and key4u_endpoint
        and gemini_api_key
    ):
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "",
            "text": "",
            "segments": [],
            "key4u_attempt_count": 0,
            "key4u_retry_used": False,
            "detail": "multi_speaker_fallback_not_configured",
        }
    if not _REDIARIZATION_LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "",
            "text": "",
            "segments": [],
            "key4u_attempt_count": 0,
            "key4u_retry_used": False,
            "detail": "multi_speaker_fallback_busy",
        }
    key4u: dict = {}
    key4u_attempt_count = 0
    try:
        for attempt_index in range(KEY4U_TRANSCRIPT_MAX_ATTEMPTS):
            key4u_attempt_count += 1
            key4u = await key4u_transcribe(
                audio_bytes,
                content_type,
                base_url=KEY4U_FALLBACK_BASE_URL,
                api_key=key4u_api_key,
                endpoint=key4u_endpoint,
                model="whisper-1",
                language=language,
            )
            if (
                key4u.get("ok")
                and str(key4u.get("text") or "").strip()
                and key4u.get("provider_timestamps") is True
                and _provider_timestamp_segments_valid(key4u)
            ):
                break
            if (
                attempt_index + 1 >= KEY4U_TRANSCRIPT_MAX_ATTEMPTS
                or not _key4u_transcript_retryable(key4u)
            ):
                break
            await asyncio.sleep(KEY4U_TRANSCRIPT_RETRY_DELAY_SECONDS)
        transcript = str(key4u.get("text") or "").strip()
        key4u_segments = list(key4u.get("segments") or [])
        if (
            not key4u.get("ok")
            or not transcript
            or key4u.get("provider_timestamps") is not True
            or not _provider_timestamp_segments_valid(key4u)
        ):
            return {
                "ok": False,
                "status": AUTO_CAST_UNAVAILABLE,
                "provider": "key4u_audio",
                "text": "",
                "segments": [],
                "key4u_attempt_count": key4u_attempt_count,
                "key4u_retry_used": key4u_attempt_count > 1,
                "detail": "multi_key4u_provider_timestamps_required",
            }
        diarization = await gemini_transcribe_multi_diarized_words(
            audio_bytes,
            content_type,
            api_key=gemini_api_key,
            language=language,
        )
        mapped = apply_multi_diarized_words_to_segments(
            key4u_segments,
            list(diarization.get("words") or []),
        )
        if not diarization.get("ok") or not mapped:
            return {
                "ok": False,
                "status": AUTO_CAST_UNAVAILABLE,
                "provider": "key4u_audio+gemini_multi_diarization",
                "text": "",
                "segments": [],
                "key4u_attempt_count": key4u_attempt_count,
                "key4u_retry_used": key4u_attempt_count > 1,
                "detail": "multi_speaker_diarization_unavailable",
            }
        return {
            **key4u,
            "ok": True,
            "status": "PASS",
            "provider": "key4u_audio+gemini_multi_diarization",
            "text": transcript,
            "segments": mapped,
            "key4u_attempt_count": key4u_attempt_count,
            "key4u_retry_used": key4u_attempt_count > 1,
            "detected_speaker_count": detected_speaker_count(mapped),
            "detail": (
                f"key4u_segments={len(key4u_segments)}; "
                f"gemini_words={len(diarization.get('words') or [])}; "
                f"speakers={detected_speaker_count(mapped)}"
            ),
        }
    finally:
        _REDIARIZATION_LOCK.release()


def _pcm_as_mono_wav(
    pcm_path: str,
    *,
    sample_rate: int,
    channels: int,
    stop_requested: Callable[[], bool] | None = None,
) -> bytes:
    if (
        type(sample_rate) is not int
        or type(channels) is not int
        or sample_rate < 8_000
        or channels not in {1, 2}
    ):
        return b""
    path = os.path.abspath(str(pcm_path or ""))
    if not os.path.isfile(path):
        return b""
    size = os.path.getsize(path)
    frame_bytes = channels * 2
    maximum = MAX_REDIARIZATION_SECONDS * sample_rate * frame_bytes
    if size <= 0 or size > maximum or size % frame_bytes:
        return b""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import audioop
    except ImportError:
        return b""
    output = io.BytesIO()
    rate_state = None
    chunk_bytes = max(
        frame_bytes,
        (PCM_STREAM_CHUNK_BYTES // frame_bytes) * frame_bytes,
    )
    try:
        with open(path, "rb") as source, wave.open(output, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(TARGET_SAMPLE_RATE)
            while True:
                if callable(stop_requested) and stop_requested():
                    return b""
                raw = source.read(chunk_bytes)
                if not raw:
                    break
                if len(raw) % frame_bytes:
                    return b""
                mono = (
                    audioop.tomono(raw, 2, 0.5, 0.5)
                    if channels == 2
                    else raw
                )
                if sample_rate != TARGET_SAMPLE_RATE:
                    mono, rate_state = audioop.ratecv(
                        mono,
                        2,
                        1,
                        sample_rate,
                        TARGET_SAMPLE_RATE,
                        rate_state,
                    )
                handle.writeframesraw(mono)
    except (
        OSError,
        OverflowError,
        ValueError,
        wave.Error,
        audioop.error,
    ):
        return b""
    return output.getvalue()


async def _drain_conversion(worker: asyncio.Task) -> None:
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if worker.done():
        try:
            worker.result()
        except (asyncio.CancelledError, Exception):
            pass


def _gemini_audio_media_type(content_type: str) -> str:
    media_type = str(content_type or "").split(";", 1)[0].strip().lower()
    return media_type if media_type in {
        "audio/wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/aiff",
        "audio/aac",
        "audio/ogg",
        "audio/flac",
        "audio/m4a",
        "audio/l16",
        "audio/opus",
        "audio/alaw",
        "audio/mulaw",
    } else "audio/mpeg"


def _gemini_request_body(
    audio_bytes: bytes,
    content_type: str,
    transcription_config: dict[str, Any],
) -> bytes:
    request_payload = {
        "model": GEMINI_TRANSCRIBE_MODEL,
        "input": [
            {
                "type": "audio",
                "data": base64.b64encode(audio_bytes).decode("ascii"),
                "mime_type": _gemini_audio_media_type(content_type),
            }
        ],
        "generation_config": {"transcription_config": transcription_config},
    }
    return json.dumps(
        request_payload,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


async def gemini_transcribe_multi_diarized_words(
    audio_bytes: bytes,
    content_type: str,
    *,
    api_key: str,
    language: str = "auto",
) -> dict:
    """Ask Gemini to discover speakers automatically; no count hint is sent."""

    if not audio_bytes or not api_key:
        return {
            "ok": False,
            "status": "MISSING",
            "words": [],
            "speaker_ids": [],
            "http_status": 0,
            "detail": "gemini_multi_transcribe_not_configured",
        }
    normalized_language = str(language or "").strip().lower().replace("_", "-")
    language_codes = [] if normalized_language in {"", "auto", "unknown"} else [
        str(language or "").replace("_", "-")[:35]
    ]
    transcription_config: dict[str, Any] = {
        "mode": {
            "type": "verbatim",
            "diarization_mode": "speaker",
            "timestamp_granularities": ["word"],
        }
    }
    if language_codes:
        transcription_config["language_codes"] = language_codes
    serialization = asyncio.create_task(
        asyncio.to_thread(
            _gemini_request_body,
            audio_bytes,
            content_type,
            transcription_config,
        )
    )
    try:
        try:
            request_body = await asyncio.shield(serialization)
        except asyncio.CancelledError:
            await _drain_conversion(serialization)
            raise
        async with httpx.AsyncClient(timeout=180.0) as client:
            for attempt in range(GEMINI_EMPTY_RESULT_MAX_ATTEMPTS):
                response = await client.post(
                    GEMINI_INTERACTIONS_URL,
                    headers={
                        "x-goog-api-key": api_key,
                        "Content-Type": "application/json",
                    },
                    content=request_body,
                )
                response_http_status = int(response.status_code)
                try:
                    response_payload = response.json()
                except Exception:
                    response_payload = {}
                interaction_status = str(
                    response_payload.get("status")
                    if isinstance(response_payload, dict)
                    else ""
                ).strip().lower()
                interaction_id = str(
                    response_payload.get("id")
                    if isinstance(response_payload, dict)
                    else ""
                ).strip()
                interaction_name = interaction_id.rsplit("/", 1)[-1]
                if not re.fullmatch(r"[A-Za-z0-9._~-]{1,512}", interaction_name):
                    interaction_name = ""
                poll_count = 0
                while (
                    interaction_status in {"created", "in_progress", "queued"}
                    and interaction_name
                    and poll_count < GEMINI_INTERACTION_MAX_POLLS
                ):
                    await asyncio.sleep(GEMINI_INTERACTION_POLL_SECONDS)
                    response = await client.get(
                        f"{GEMINI_INTERACTIONS_URL}/{interaction_name}",
                        headers={"x-goog-api-key": api_key},
                    )
                    poll_count += 1
                    response_http_status = int(response.status_code)
                    try:
                        response_payload = response.json()
                    except Exception:
                        response_payload = {}
                    interaction_status = str(
                        response_payload.get("status")
                        if isinstance(response_payload, dict)
                        else ""
                    ).strip().lower()

                raw_annotation_count = gemini_word_info_annotation_count(
                    response_payload
                )
                terminal_empty = bool(
                    response_http_status < 400
                    and interaction_status in {"completed", "incomplete"}
                    and raw_annotation_count == 0
                )
                words = extract_gemini_multi_diarized_words(response_payload)
                labels = _ordered_speaker_labels(words)
                if response_http_status < 400 and words:
                    return {
                        "ok": True,
                        "status": "PASS",
                        "provider": "gemini_transcribe_multi_diarization",
                        "words": words,
                        "speaker_ids": labels,
                        "http_status": response_http_status,
                        "raw_annotation_count": raw_annotation_count,
                        "terminal_empty": False,
                        "detail": f"words={len(words)}; speakers={len(labels)}",
                    }
                if (
                    terminal_empty
                    and attempt + 1 < GEMINI_EMPTY_RESULT_MAX_ATTEMPTS
                ):
                    await asyncio.sleep(GEMINI_EMPTY_RESULT_RETRY_DELAY_SECONDS)
                    continue
                return {
                    "ok": False,
                    "status": AUTO_CAST_UNAVAILABLE,
                    "provider": "gemini_transcribe_multi_diarization",
                    "words": [],
                    "speaker_ids": [],
                    "http_status": response_http_status,
                    "raw_annotation_count": raw_annotation_count,
                    "terminal_empty": terminal_empty,
                    "detail": (
                        "gemini_multi_diarization_invalid:"
                        f"http={response_http_status};status={interaction_status or 'missing'}"
                    ),
                }
    except httpx.TimeoutException:
        return {
            "ok": False,
            "status": "FAIL_TIMEOUT",
            "provider": "gemini_transcribe_multi_diarization",
            "words": [],
            "speaker_ids": [],
            "http_status": 0,
            "detail": "gemini_multi_transcribe_timeout",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "FAIL_PROVIDER_ERROR",
            "provider": "gemini_transcribe_multi_diarization",
            "words": [],
            "speaker_ids": [],
            "http_status": 0,
            "detail": f"gemini_multi_transcribe_error:{type(exc).__name__}",
        }
    finally:
        if not serialization.done():
            await _drain_conversion(serialization)


async def rediarize_underclustered_segments(
    segments: list[dict],
    *,
    pcm_path: str,
    sample_rate: int,
    channels: int,
    api_key: str = "",
    language: str = "auto",
    provider_call_allowed: bool = False,
    gemini_diarize: Callable[..., Awaitable[dict]] | None = None,
) -> dict:
    """Replace a two-label primary result only with proven 3-8 label evidence."""

    primary_speaker_count = detected_speaker_count(segments)
    if not 1 <= primary_speaker_count < MIN_MULTI_SPEAKERS:
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "",
            "segments": [],
            "detail": "multi_rediarization_requires_underclustered_input",
        }
    if provider_call_allowed is not True:
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "",
            "segments": [],
            "detail": "multi_rediarization_confirmation_required",
        }
    configured_key = str(api_key or os.getenv("GEMINI_API_KEY") or "").strip()
    if not configured_key:
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "",
            "segments": [],
            "detail": "multi_rediarization_not_configured",
        }
    if not _REDIARIZATION_LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "",
            "segments": [],
            "detail": "multi_rediarization_busy",
        }
    stop_event = threading.Event()
    conversion = asyncio.create_task(
        asyncio.to_thread(
            _pcm_as_mono_wav,
            pcm_path,
            sample_rate=sample_rate,
            channels=channels,
            stop_requested=stop_event.is_set,
        )
    )
    try:
        try:
            wav_bytes = await asyncio.shield(conversion)
        except asyncio.CancelledError:
            stop_event.set()
            await _drain_conversion(conversion)
            raise
        if not wav_bytes:
            return {
                "ok": False,
                "status": AUTO_CAST_UNAVAILABLE,
                "provider": "",
                "segments": [],
                "detail": "multi_rediarization_pcm_invalid",
            }
        diarize = gemini_diarize or gemini_transcribe_multi_diarized_words
        diarization = await diarize(
            wav_bytes,
            "audio/wav",
            api_key=configured_key,
            language=language,
        )
        words = list(diarization.get("words") or [])
        mapped = apply_multi_diarized_words_to_segments(segments, words)
        speaker_count = detected_speaker_count(mapped)
        if (
            not diarization.get("ok")
            or not mapped
            or not MIN_MULTI_SPEAKERS
            <= speaker_count
            <= MAX_GEMINI_DIARIZATION_SPEAKERS
        ):
            return {
                "ok": False,
                "status": AUTO_CAST_UNAVAILABLE,
                "provider": "gemini_transcribe_multi_diarization",
                "segments": [],
                "provider_status": str(diarization.get("status") or AUTO_CAST_UNAVAILABLE),
                "provider_http_status": int(diarization.get("http_status") or 0),
                "provider_word_count": len(words),
                "provider_speaker_count": len(diarization.get("speaker_ids") or []),
                "mapped_speaker_count": speaker_count,
                "provider_raw_annotation_count": int(
                    diarization.get("raw_annotation_count") or 0
                ),
                "provider_terminal_empty": bool(
                    diarization.get("terminal_empty") is True
                ),
                "detail": str(
                    diarization.get("detail")
                    or "multi_speaker_diarization_unavailable"
                )[:180],
            }
        return {
            "ok": True,
            "status": "PASS",
            "provider": "gemini_transcribe_multi_diarization",
            "segments": mapped,
            "detected_speaker_count": speaker_count,
            "provider_status": str(diarization.get("status") or "PASS"),
            "provider_http_status": int(diarization.get("http_status") or 0),
            "provider_word_count": len(words),
            "provider_speaker_count": len(diarization.get("speaker_ids") or []),
            "mapped_speaker_count": speaker_count,
            "provider_raw_annotation_count": int(
                diarization.get("raw_annotation_count") or 0
            ),
            "provider_terminal_empty": False,
            "detail": f"segments={len(mapped)}; speakers={speaker_count}",
        }
    finally:
        stop_event.set()
        if not conversion.done():
            await _drain_conversion(conversion)
        _REDIARIZATION_LOCK.release()
