from __future__ import annotations

import inspect
import hashlib
import os
import re
import wave
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class VoiceVaultEntry:
    ok: bool
    profile_id: int = 0
    provider_voice_id: str = ""
    display_name: str = ""
    source: str = ""
    reason: str = ""
    public_message: str = ""


@dataclass(frozen=True)
class VoicePreviewPolicy:
    allowed: bool
    explicit: bool
    short: bool
    no_charge: bool
    max_seconds: int
    reason: str = ""
    public_message: str = ""


@dataclass(frozen=True)
class CustomVoiceFlowState:
    ready: bool
    locked: bool
    fallback_available: bool
    reason: str = ""
    public_message: str = ""


@dataclass(frozen=True)
class CustomVoiceCreateResult:
    ok: bool
    provider_voice_id: str = ""
    display_name: str = ""
    error_code: str = ""
    error_message: str = ""
    public_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


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


def _profile_id(profile: dict | None) -> int:
    try:
        return int((profile or {}).get("id") or 0)
    except Exception:
        return 0


def _profile_voice_id_is_local_id(profile: dict | None, provider_voice_id: str) -> bool:
    pid = _profile_id(profile)
    return bool(pid and str(pid) == str(provider_voice_id or "").strip())


def _safe_label(profile: dict | None, fallback: str = "") -> str:
    label = str((profile or {}).get("display_name") or fallback or "").strip()
    return re.sub(r"\s+", " ", label)[:120] or "Voice"


def friendly_voice_name(profile: dict | None, fallback: str = "Voice đã lưu") -> str:
    return _safe_label(profile, fallback)


def voice_vault_entry(profile: dict | None, *, source: str = "saved") -> VoiceVaultEntry:
    selected = dict(profile or {})
    profile_id = _profile_id(selected)
    provider_voice_id = normalize_voice_id(selected.get("provider_voice_id"))
    label = _safe_label(selected, "Voice đã gửi" if source == "uploaded" else "Voice đã lưu")
    if not validate_provider_voice_id(provider_voice_id) or _profile_voice_id_is_local_id(selected, provider_voice_id):
        return VoiceVaultEntry(
            ok=False,
            profile_id=profile_id,
            display_name=label,
            source=source,
            reason="missing_provider_voice_id",
            public_message=PUBLIC_SAFE_VOICE_NOT_READY,
        )
    return VoiceVaultEntry(
        ok=True,
        profile_id=profile_id,
        provider_voice_id=provider_voice_id,
        display_name=label,
        source=source,
    )


def list_friendly_voice_entries(profiles: list[dict] | tuple[dict, ...], *, source: str = "saved") -> list[VoiceVaultEntry]:
    entries = [voice_vault_entry(profile, source=source) for profile in list(profiles or [])]
    return [entry for entry in entries if entry.ok]


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
        if not validate_provider_voice_id(provider_voice_id) or _profile_voice_id_is_local_id(selected_profile, provider_voice_id):
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
        if not validate_provider_voice_id(provider_voice_id) or _profile_voice_id_is_local_id(selected_profile, provider_voice_id):
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


def voice_preview_policy(
    *,
    explicit: bool = False,
    no_charge: bool = True,
    max_seconds: int = 6,
) -> VoicePreviewPolicy:
    seconds = max(1, min(15, int(max_seconds or 6)))
    if not explicit:
        return VoicePreviewPolicy(
            allowed=False,
            explicit=False,
            short=True,
            no_charge=True,
            max_seconds=seconds,
            reason="preview_requires_explicit_confirm",
            public_message="Bản nghe thử chỉ tạo khi anh/chị xác nhận rõ và không trừ Xu âm thầm.",
        )
    if not no_charge:
        return VoicePreviewPolicy(
            allowed=False,
            explicit=True,
            short=True,
            no_charge=False,
            max_seconds=seconds,
            reason="preview_must_be_no_charge",
            public_message="Bản nghe thử phải là bước không trừ Xu.",
        )
    return VoicePreviewPolicy(
        allowed=True,
        explicit=True,
        short=True,
        no_charge=True,
        max_seconds=seconds,
        reason="preview_explicit_short_no_charge",
        public_message=f"TOAN AAS sẽ tạo bản nghe thử ngắn tối đa {seconds} giây và không trừ Xu.",
    )


def custom_voice_flow_state(*, ready: bool = False, locked_reason: str = "") -> CustomVoiceFlowState:
    if ready:
        return CustomVoiceFlowState(
            ready=True,
            locked=False,
            fallback_available=True,
            reason="custom_voice_ready",
            public_message="Voice riêng đã sẵn sàng để tạo audio sau khi xác nhận.",
        )
    reason = str(locked_reason or "custom_voice_locked").strip()
    return CustomVoiceFlowState(
        ready=False,
        locked=True,
        fallback_available=True,
        reason=reason,
        public_message=(
            "Tạo voice riêng đang tạm khóa để kiểm soát chất lượng. TOAN AAS chưa xử lý và chưa trừ Xu. "
            "Anh/chị có thể dùng giọng nữ/nam mặc định hoặc voice đã lưu."
        ),
    )


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


def _custom_voice_provider_id_from_result(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("provider_voice_id", "voice_id", "id", "custom_voice_id"):
            value = normalize_voice_id(result.get(key))
            if validate_provider_voice_id(value):
                return value
    for key in ("provider_voice_id", "voice_id", "id", "custom_voice_id"):
        value = normalize_voice_id(getattr(result, key, ""))
        if validate_provider_voice_id(value):
            return value
    return ""


def create_custom_voice_from_sample(
    sample_path: str | os.PathLike[str],
    display_name: str,
    user_id: str | int,
    idempotency_key: str,
    fake: bool = False,
    create_func: Callable[..., Any] | None = None,
) -> CustomVoiceCreateResult:
    label = re.sub(r"\s+", " ", str(display_name or "")).strip()[:120] or "Voice riêng"
    sample = Path(str(sample_path or "")).expanduser()
    if not sample.exists() or not sample.is_file():
        return CustomVoiceCreateResult(
            ok=False,
            display_name=label,
            error_code="sample_missing",
            public_message="TOAN AAS chưa nhận được file mẫu hợp lệ. Anh/chị gửi lại mẫu voice/audio rõ hơn.",
        )
    sample_size = int(sample.stat().st_size or 0)
    if sample_size <= 0:
        return CustomVoiceCreateResult(
            ok=False,
            display_name=label,
            error_code="sample_empty",
            public_message="File mẫu chưa có dữ liệu âm thanh hợp lệ. Anh/chị gửi lại mẫu voice/audio rõ hơn.",
        )
    stable_key = str(idempotency_key or f"{user_id}:{sample.name}:{sample_size}")
    if fake:
        digest = hashlib.sha256(
            "|".join([str(user_id or ""), label, stable_key, str(sample_size)]).encode("utf-8", errors="ignore")
        ).hexdigest()[:18]
        safe_user = re.sub(r"[^A-Za-z0-9]+", "-", str(user_id or "user")).strip("-")[:24] or "user"
        provider_voice_id = normalize_voice_id(f"toanaas-custom-{safe_user}-{digest}")
        if not validate_provider_voice_id(provider_voice_id):
            return CustomVoiceCreateResult(
                ok=False,
                display_name=label,
                error_code="provider_voice_id_invalid",
                public_message=PUBLIC_SAFE_VOICE_NOT_READY,
            )
        return CustomVoiceCreateResult(
            ok=True,
            provider_voice_id=provider_voice_id,
            display_name=label,
            metadata={
                "fake": True,
                "sample_size": sample_size,
                "idempotency_key": stable_key,
            },
        )
    if not callable(create_func):
        return CustomVoiceCreateResult(
            ok=False,
            display_name=label,
            error_code="provider_adapter_missing",
            public_message=(
                "Tạo voice riêng đang tạm khóa để kiểm soát chất lượng. "
                "Anh/chị có thể dùng giọng nam/nữ mặc định hoặc voice đã lưu."
            ),
        )
    try:
        result = create_func(
            sample_path=str(sample),
            display_name=label,
            user_id=user_id,
            idempotency_key=stable_key,
        )
        if inspect.isawaitable(result):
            return CustomVoiceCreateResult(
                ok=False,
                display_name=label,
                error_code="provider_adapter_async_not_supported",
                public_message=PUBLIC_SAFE_VOICE_NOT_READY,
            )
        provider_voice_id = _custom_voice_provider_id_from_result(result)
        if not provider_voice_id:
            return CustomVoiceCreateResult(
                ok=False,
                display_name=label,
                error_code="missing_provider_voice_id",
                public_message=PUBLIC_SAFE_VOICE_NOT_READY,
            )
        metadata = dict(result or {}) if isinstance(result, dict) else {}
        metadata.update({"sample_size": sample_size, "idempotency_key": stable_key})
        return CustomVoiceCreateResult(
            ok=True,
            provider_voice_id=provider_voice_id,
            display_name=label,
            metadata=metadata,
        )
    except Exception as exc:
        return CustomVoiceCreateResult(
            ok=False,
            display_name=label,
            error_code=type(exc).__name__,
            error_message=safe_public_error(str(exc)),
            public_message=safe_public_error(str(exc)),
        )


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
