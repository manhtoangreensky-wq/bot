from __future__ import annotations

import inspect
import os
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_MALE_VOICE_ID = os.getenv("MINIMAX_DEFAULT_MALE_VOICE_ID", "male-qn-qingse")
DEFAULT_FEMALE_VOICE_ID = os.getenv("MINIMAX_DEFAULT_FEMALE_VOICE_ID", "female-shaonv")
VOICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{1,127}$")
PUBLIC_SAFE_VOICE_NOT_READY = "Voice này chưa sẵn sàng để dùng, anh/chị chọn voice khác hoặc tạo lại voice."
PUBLIC_SAFE_TTS_ERROR = "TOAN AAS chưa tạo được giọng đọc lúc này. Anh/chị thử lại hoặc chọn giọng khác."


@dataclass(frozen=True)
class VoiceIdResolution:
    ok: bool
    provider_voice_id: str = ""
    voice_label: str = ""
    reason: str = ""
    public_message: str = ""
    profile_id: int = 0


@dataclass(frozen=True)
class AudioArtifact:
    ok: bool
    path: str = ""
    duration_seconds: float = 0.0
    size_bytes: int = 0
    reason: str = ""
    public_message: str = ""


def normalize_voice_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = re.sub(r"\s+", "-", raw.replace("_", "-"))
    normalized = re.sub(r"[^A-Za-z0-9.-]", "", normalized)
    return normalized[:128]


def validate_provider_voice_id(value: str | None) -> bool:
    normalized = normalize_voice_id(value)
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered in {"default", "none", "null", "saved", "uploaded", "voice-profile", "default-male", "default-female"}:
        return False
    return bool(VOICE_ID_PATTERN.match(normalized))


def _safe_label(profile: dict | None, fallback: str = "") -> str:
    label = str((profile or {}).get("display_name") or fallback or "").strip()
    return re.sub(r"\s+", " ", label)[:120] or "Voice"


def resolve_provider_voice_id(
    *,
    voice_source: str = "",
    profile: dict | None = None,
    uploaded_profile: dict | None = None,
    default_male_voice_id: str | None = None,
    default_female_voice_id: str | None = None,
    requested_voice_id: str | None = None,
) -> VoiceIdResolution:
    source = str(voice_source or "").strip().lower()
    if source in {"default_male", "male", "nam"}:
        voice_id = normalize_voice_id(default_male_voice_id or DEFAULT_MALE_VOICE_ID)
        return VoiceIdResolution(
            ok=validate_provider_voice_id(voice_id),
            provider_voice_id=voice_id,
            voice_label="Nam mặc định",
            reason="" if validate_provider_voice_id(voice_id) else "missing_default_male_voice_id",
            public_message="" if validate_provider_voice_id(voice_id) else PUBLIC_SAFE_VOICE_NOT_READY,
        )
    if source in {"default_female", "female", "nữ", "nu"}:
        voice_id = normalize_voice_id(default_female_voice_id or DEFAULT_FEMALE_VOICE_ID)
        return VoiceIdResolution(
            ok=validate_provider_voice_id(voice_id),
            provider_voice_id=voice_id,
            voice_label="Nữ mặc định",
            reason="" if validate_provider_voice_id(voice_id) else "missing_default_female_voice_id",
            public_message="" if validate_provider_voice_id(voice_id) else PUBLIC_SAFE_VOICE_NOT_READY,
        )
    selected_profile = dict(profile or uploaded_profile or {})
    if source in {"saved", "saved_voice", "voice_profile"} or selected_profile:
        provider_voice_id = normalize_voice_id(selected_profile.get("provider_voice_id"))
        if not validate_provider_voice_id(provider_voice_id):
            return VoiceIdResolution(
                ok=False,
                provider_voice_id="",
                voice_label=_safe_label(selected_profile, "Voice đã lưu"),
                reason="missing_provider_voice_id",
                public_message=PUBLIC_SAFE_VOICE_NOT_READY,
                profile_id=int(selected_profile.get("id") or 0),
            )
        return VoiceIdResolution(
            ok=True,
            provider_voice_id=provider_voice_id,
            voice_label=_safe_label(selected_profile, "Voice đã lưu"),
            profile_id=int(selected_profile.get("id") or 0),
        )
    if source in {"uploaded", "uploaded_voice"}:
        selected_profile = dict(uploaded_profile or profile or {})
        provider_voice_id = normalize_voice_id(selected_profile.get("provider_voice_id"))
        if not validate_provider_voice_id(provider_voice_id):
            return VoiceIdResolution(
                ok=False,
                provider_voice_id="",
                voice_label=_safe_label(selected_profile, "Voice đã gửi"),
                reason="missing_provider_voice_id",
                public_message=PUBLIC_SAFE_VOICE_NOT_READY,
                profile_id=int(selected_profile.get("id") or 0),
            )
        return VoiceIdResolution(
            ok=True,
            provider_voice_id=provider_voice_id,
            voice_label=_safe_label(selected_profile, "Voice đã gửi"),
            profile_id=int(selected_profile.get("id") or 0),
        )
    requested = normalize_voice_id(requested_voice_id)
    if validate_provider_voice_id(requested):
        return VoiceIdResolution(ok=True, provider_voice_id=requested, voice_label="Voice")
    return VoiceIdResolution(ok=False, reason="missing_provider_voice_id", public_message=PUBLIC_SAFE_VOICE_NOT_READY)


def _duration_seconds(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as audio:
                frames = audio.getnframes()
                rate = audio.getframerate() or 1
                return round(frames / float(rate), 3)
        except Exception:
            return 0.0
    return 0.0


def validate_audio_artifact(path: str | os.PathLike[str] | None, *, min_bytes: int = 16) -> AudioArtifact:
    file_path = Path(str(path or "")).expanduser()
    if not file_path.exists() or not file_path.is_file():
        return AudioArtifact(ok=False, reason="audio_missing", public_message=PUBLIC_SAFE_TTS_ERROR)
    size = file_path.stat().st_size
    if size < max(1, int(min_bytes or 1)):
        return AudioArtifact(ok=False, path=str(file_path.resolve()), size_bytes=size, reason="audio_empty", public_message=PUBLIC_SAFE_TTS_ERROR)
    return AudioArtifact(ok=True, path=str(file_path.resolve()), duration_seconds=_duration_seconds(file_path), size_bytes=size)


def _audio_bytes_from_result(result: Any) -> bytes:
    if isinstance(result, (bytes, bytearray)):
        return bytes(result)
    if isinstance(result, dict):
        for key in ("audio_bytes", "bytes", "data", "audio"):
            value = result.get(key)
            if isinstance(value, (bytes, bytearray)):
                return bytes(value)
        path = str(result.get("path") or result.get("audio_path") or "").strip()
        if path and Path(path).exists():
            return Path(path).read_bytes()
    if isinstance(result, (list, tuple)):
        return b"".join(_audio_bytes_from_result(item) for item in result)
    return b""


def safe_public_error(error: str = "") -> str:
    text = str(error or "").lower()
    if any(term in text for term in ("provider", "api", "endpoint", "minimax", "traceback", "token")):
        return PUBLIC_SAFE_TTS_ERROR
    return str(error or "").strip() or PUBLIC_SAFE_TTS_ERROR


def synthesize_text_to_audio(
    *,
    text: str,
    provider_voice_id: str,
    output_path: str | os.PathLike[str],
    tts_func: Callable[..., Any] | None = None,
    max_seconds: int | None = None,
) -> AudioArtifact:
    del max_seconds
    clean_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean_text:
        return AudioArtifact(ok=False, reason="text_missing", public_message="TOAN AAS cần lời đọc trước khi tạo giọng.")
    voice_id = normalize_voice_id(provider_voice_id)
    if not validate_provider_voice_id(voice_id):
        return AudioArtifact(ok=False, reason="missing_provider_voice_id", public_message=PUBLIC_SAFE_VOICE_NOT_READY)
    output = Path(str(output_path or "")).expanduser()
    if not output.name:
        return AudioArtifact(ok=False, reason="output_path_missing", public_message=PUBLIC_SAFE_TTS_ERROR)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not callable(tts_func):
            return AudioArtifact(ok=False, reason="tts_func_missing", public_message=PUBLIC_SAFE_TTS_ERROR)
        result = tts_func(clean_text, voice_id=voice_id, output_path=str(output))
        if inspect.isawaitable(result):
            return AudioArtifact(ok=False, reason="tts_func_async_not_supported", public_message=PUBLIC_SAFE_TTS_ERROR)
        audio_bytes = _audio_bytes_from_result(result)
        if audio_bytes:
            output.write_bytes(audio_bytes)
        artifact = validate_audio_artifact(output)
        if not artifact.ok:
            return artifact
        return artifact
    except Exception as exc:
        return AudioArtifact(ok=False, reason=type(exc).__name__, public_message=safe_public_error(str(exc)))
