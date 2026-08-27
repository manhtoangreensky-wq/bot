"""Fail-closed two-speaker ASR fallback for confirmed SubDub Auto jobs."""

from __future__ import annotations

import base64
import math
from collections.abc import Awaitable, Callable
from typing import Any

import httpx


AUTO_CAST_UNAVAILABLE = "AUTO_CAST_UNAVAILABLE"
GEMINI_TRANSCRIBE_MODEL = "gemini-3.5-transcribe"
GEMINI_INTERACTIONS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/interactions"
)
KEY4U_FALLBACK_BASE_URL = "https://api.key4u.vn/v1"
MIN_SEGMENT_SPEAKER_CONFIDENCE = 0.70
MIN_SEGMENTS_PER_SPEAKER = 2


def _offset_seconds(value: object) -> float:
    text = str(value or "").strip().lower()
    if text.endswith("s"):
        text = text[:-1]
    try:
        parsed = float(text)
    except (TypeError, ValueError, OverflowError):
        return -1.0
    return parsed if math.isfinite(parsed) else -1.0


def extract_gemini_diarized_words(payload: object) -> list[dict]:
    """Extract exactly two timed speaker labels without exposing raw payloads."""

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
    words.sort(key=lambda item: (item["start"], item["end"], item["speaker"]))
    labels = list(dict.fromkeys(item["speaker"] for item in words))
    if len(labels) != 2:
        return []
    if any(
        sum(item["speaker"] == label for item in words)
        < MIN_SEGMENTS_PER_SPEAKER
        for label in labels
    ):
        return []
    return words


def provider_timestamp_segments_valid(payload: object) -> bool:
    """Accept only real provider segments with complete ordered timestamps."""

    segments = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(segments, list) or not segments:
        return False
    previous_start = -1.0
    for segment in segments:
        if not isinstance(segment, dict):
            return False
        text = str(segment.get("text") or segment.get("transcript") or "").strip()
        try:
            start = float(segment.get("start"))
            end = float(segment.get("end"))
        except (TypeError, ValueError, OverflowError):
            return False
        if (
            not text
            or not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0.0
            or end <= start
            or start < previous_start
        ):
            return False
        previous_start = start
    return True


def apply_diarized_words_to_segments(
    segments: object,
    words: object,
) -> list[dict]:
    """Map Gemini speaker time evidence onto Key4U Whisper cue boundaries."""

    if (
        not isinstance(segments, list)
        or not segments
        or not isinstance(words, list)
        or not words
    ):
        return []
    labels = list(
        dict.fromkeys(
            str(item.get("speaker") or "").strip()
            for item in words
            if isinstance(item, dict) and str(item.get("speaker") or "").strip()
        )
    )
    if len(labels) != 2:
        return []
    label_numbers = {label: index for index, label in enumerate(labels)}
    mapped: list[dict] = []
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
        ):
            return []
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
        if (
            confidence < MIN_SEGMENT_SPEAKER_CONFIDENCE
            or word_counts[selected] < 1
        ):
            return []
        mapped.append(
            {
                **raw_segment,
                "speaker": label_numbers[selected],
                "speaker_confidence": round(float(confidence), 6),
            }
        )
    mapped_counts = {
        label_number: sum(item.get("speaker") == label_number for item in mapped)
        for label_number in (0, 1)
    }
    if (
        len(mapped) != len(segments)
        or min(mapped_counts.values(), default=0) < MIN_SEGMENTS_PER_SPEAKER
    ):
        return []
    return mapped


async def gemini_transcribe_diarized_words(
    audio_bytes: bytes,
    content_type: str,
    *,
    api_key: str,
    language: str = "auto",
) -> dict:
    if not audio_bytes or not api_key:
        return {
            "ok": False,
            "status": "MISSING",
            "words": [],
            "speaker_ids": [],
            "http_status": 0,
            "detail": "gemini_transcribe_not_configured",
        }
    media_type = str(content_type or "audio/mpeg").split(";", 1)[0].strip()
    allowed_media_types = {
        "audio/wav", "audio/mp3", "audio/aiff", "audio/aac", "audio/ogg",
        "audio/flac", "audio/mpeg", "audio/m4a", "audio/l16", "audio/opus",
        "audio/alaw", "audio/mulaw",
    }
    if media_type not in allowed_media_types:
        media_type = "audio/mpeg"
    language_code = str(language or "").strip()
    normalized_language = language_code.lower().replace("_", "-")
    if normalized_language in {"", "auto", "unknown"}:
        language_codes: list[str] = []
    elif normalized_language in {"zh", "zh-cn", "chinese"}:
        language_codes = ["zh-CN"]
    elif normalized_language in {"zh-tw", "chinese-traditional"}:
        language_codes = ["zh-TW"]
    else:
        language_codes = [language_code.replace("_", "-")[:35]]
    transcription_config: dict[str, Any] = {
        "mode": {
            "type": "verbatim",
            "diarization_mode": "speaker",
            "timestamp_granularities": ["word"],
        }
    }
    if language_codes:
        transcription_config["language_codes"] = language_codes
    request_payload = {
        "model": GEMINI_TRANSCRIBE_MODEL,
        "input": [
            {
                "type": "audio",
                "data": base64.b64encode(audio_bytes).decode("ascii"),
                "mime_type": media_type,
            }
        ],
        "generation_config": {"transcription_config": transcription_config},
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                GEMINI_INTERACTIONS_URL,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json=request_payload,
            )
        try:
            response_payload = response.json()
        except Exception:
            response_payload = {}
        words = extract_gemini_diarized_words(response_payload)
        labels = list(dict.fromkeys(item["speaker"] for item in words))
        if response.status_code < 400 and words and len(labels) == 2:
            return {
                "ok": True,
                "status": "PASS",
                "provider": "gemini_transcribe",
                "words": words,
                "speaker_ids": labels,
                "http_status": int(response.status_code),
                "detail": (
                    f"words={len(words)}; speakers={len(labels)}; "
                    f"model={GEMINI_TRANSCRIBE_MODEL}"
                ),
            }
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "gemini_transcribe",
            "words": [],
            "speaker_ids": [],
            "http_status": int(response.status_code),
            "detail": f"gemini_transcribe_invalid_diarization:http={response.status_code}",
        }
    except httpx.TimeoutException:
        return {
            "ok": False,
            "status": "FAIL_TIMEOUT",
            "provider": "gemini_transcribe",
            "words": [],
            "speaker_ids": [],
            "http_status": 0,
            "detail": "gemini_transcribe_timeout",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "FAIL_PROVIDER_ERROR",
            "provider": "gemini_transcribe",
            "words": [],
            "speaker_ids": [],
            "http_status": 0,
            "detail": f"gemini_transcribe_error:{type(exc).__name__}",
        }


async def run_two_speaker_fallback(
    audio_bytes: bytes,
    content_type: str,
    *,
    key4u_transcribe: Callable[..., Awaitable[dict]],
    key4u_api_key: str,
    key4u_endpoint: str,
    gemini_api_key: str,
    language: str = "auto",
) -> dict:
    if not (
        audio_bytes
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
            "detail": "two_speaker_fallback_not_configured",
        }
    key4u = await key4u_transcribe(
        audio_bytes,
        content_type,
        base_url=KEY4U_FALLBACK_BASE_URL,
        api_key=key4u_api_key,
        endpoint=key4u_endpoint,
        model="whisper-1",
        language=language,
    )
    transcript = str(key4u.get("text") or "").strip()
    key4u_segments = list(key4u.get("segments") or [])
    if (
        not key4u.get("ok")
        or not transcript
        or not key4u_segments
        or key4u.get("provider_timestamps") is not True
        or not provider_timestamp_segments_valid({"segments": key4u_segments})
    ):
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "key4u_audio",
            "text": "",
            "segments": [],
            "detail": (
                "key4u_provider_timestamps_required"
                if transcript and key4u_segments
                else "key4u_two_speaker_transcript_unavailable"
            ),
        }
    diarization = await gemini_transcribe_diarized_words(
        audio_bytes,
        content_type,
        api_key=gemini_api_key,
        language=language,
    )
    words = list(diarization.get("words") or [])
    mapped_segments = apply_diarized_words_to_segments(key4u_segments, words)
    if not diarization.get("ok") or not mapped_segments:
        return {
            "ok": False,
            "status": AUTO_CAST_UNAVAILABLE,
            "provider": "key4u_audio+gemini_diarization",
            "text": "",
            "segments": [],
            "detail": "two_speaker_diarization_unavailable",
        }
    return {
        **key4u,
        "ok": True,
        "status": "PASS",
        "provider": "key4u_audio+gemini_diarization",
        "text": transcript,
        "segments": mapped_segments,
        "detail": (
            f"key4u_segments={len(key4u_segments)}; "
            f"gemini_words={len(words)}; speakers=2"
        ),
    }
