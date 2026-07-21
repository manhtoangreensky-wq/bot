"""Shared TTS provider contract for optional speech backends."""

from __future__ import annotations

import os
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


OutputFormat = Literal["wav", "mp3"]


PUBLIC_TTS_UNAVAILABLE = "TOAN AAS chưa tạo được giọng đọc lúc này. Anh/chị thử lại hoặc chọn giọng khác."


@dataclass(frozen=True)
class TTSRequest:
    text: str
    language: str = ""
    gender: str | None = None
    voice_id: str | None = None
    reference_audio_path: str | None = None
    speed: float | None = None
    emotion: str | None = None
    output_format: OutputFormat = "wav"
    output_path: str | None = None
    admin: bool = False


@dataclass(frozen=True)
class TTSResult:
    ok: bool
    audio_path: str = ""
    duration: float = 0.0
    bytes: int = 0
    sample_rate: int = 0
    provider_name: str = ""
    requested_gender: str = ""
    resolved_gender: str = ""
    resolved_voice_id: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""
    error_code: str = ""
    public_message: str = ""


class BaseTTSProvider:
    provider_name = "base"

    def synthesize(
        self,
        text: str,
        language: str,
        gender: str | None,
        voice_id: str | None,
        reference_audio_path: str | None,
        speed: float | None,
        emotion: str | None,
        output_format: OutputFormat,
    ) -> TTSResult:
        raise NotImplementedError


def safe_public_tts_error(error_code: str = "") -> str:
    lowered = str(error_code or "").lower()
    for secret_word in ("provider", "api", "endpoint", "token", "key", "model_path", "traceback", "voxcpm2"):
        if secret_word in lowered:
            return PUBLIC_TTS_UNAVAILABLE
    return PUBLIC_TTS_UNAVAILABLE


def audio_duration_seconds(path: str | os.PathLike[str] | None) -> tuple[float, int]:
    file_path = Path(str(path or "")).expanduser()
    if file_path.suffix.lower() != ".wav":
        return 0.0, 0
    try:
        with wave.open(str(file_path), "rb") as audio:
            frames = audio.getnframes()
            sample_rate = int(audio.getframerate() or 0)
            duration = float(frames) / float(sample_rate or 1)
            return round(max(0.0, duration), 3), sample_rate
    except Exception:
        return 0.0, 0


def validate_tts_audio_file(
    path: str | os.PathLike[str] | None,
    *,
    min_bytes: int = 16,
    require_duration: bool = True,
) -> TTSResult:
    file_path = Path(str(path or "")).expanduser()
    if not file_path.exists() or not file_path.is_file():
        return TTSResult(ok=False, error_code="audio_missing", public_message=PUBLIC_TTS_UNAVAILABLE)
    size = int(file_path.stat().st_size or 0)
    if size < max(1, int(min_bytes or 1)):
        return TTSResult(ok=False, audio_path=str(file_path.resolve()), bytes=size, error_code="audio_empty", public_message=PUBLIC_TTS_UNAVAILABLE)
    duration, sample_rate = audio_duration_seconds(file_path)
    if require_duration and duration <= 0:
        return TTSResult(ok=False, audio_path=str(file_path.resolve()), bytes=size, error_code="duration_missing", public_message=PUBLIC_TTS_UNAVAILABLE)
    return TTSResult(ok=True, audio_path=str(file_path.resolve()), duration=duration, bytes=size, sample_rate=sample_rate)
