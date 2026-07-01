"""Optional VoxCPM2 local TTS adapter.

The bot must be able to start without VoxCPM2 dependencies or model files.
Heavy modules are imported only inside the lazy model loader after the
adapter is enabled and called.
"""

from __future__ import annotations

import concurrent.futures
import importlib
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from services.tts_provider_base import (
    PUBLIC_TTS_UNAVAILABLE,
    OutputFormat,
    TTSResult,
    validate_tts_audio_file,
)


PROVIDER_NAME = "voxcpm2_local"


def _env_bool(env: dict[str, str], key: str, default: bool = False) -> bool:
    value = str(env.get(key, "")).strip().lower()
    if not value:
        return bool(default)
    return value in {"1", "true", "yes", "on", "y"}


def _env_int(env: dict[str, str], key: str, default: int) -> int:
    try:
        return int(float(str(env.get(key, "")).strip() or default))
    except Exception:
        return int(default)


def _clean_gender(value: str | None) -> str:
    lowered = str(value or "").strip().lower()
    if lowered in {"female", "nu", "nữ", "woman", "girl"}:
        return "female"
    if lowered in {"male", "nam", "man", "boy"}:
        return "male"
    return "neutral" if lowered in {"neutral", "auto", ""} else lowered[:40]


@dataclass(frozen=True)
class VoxCPM2Config:
    enabled: bool = False
    device: str = "auto"
    model_path: str = ""
    cache_dir: str = "/data/models/voxcpm2"
    max_text_chars: int = 2000
    timeout_seconds: int = 180
    output_format: OutputFormat = "wav"
    allow_cpu: bool = True
    admin_only: bool = True
    artifact_dir: str = field(default_factory=lambda: str(Path(tempfile.gettempdir()) / "toanaas_voxcpm2"))
    supported_languages: tuple[str, ...] = ("vi", "en")
    supported_genders: tuple[str, ...] = ("female", "male", "neutral")


def config_from_env(env: dict[str, str] | None = None) -> VoxCPM2Config:
    env = dict(os.environ if env is None else env)
    output_format = str(env.get("VOXCPM2_OUTPUT_FORMAT") or "wav").strip().lower()
    if output_format not in {"wav", "mp3"}:
        output_format = "wav"
    languages = tuple(item.strip().lower() for item in str(env.get("VOXCPM2_SUPPORTED_LANGUAGES") or "vi,en").split(",") if item.strip())
    genders = tuple(_clean_gender(item) for item in str(env.get("VOXCPM2_SUPPORTED_GENDERS") or "female,male,neutral").split(",") if item.strip())
    return VoxCPM2Config(
        enabled=_env_bool(env, "VOXCPM2_ENABLED", False),
        device=str(env.get("VOXCPM2_DEVICE") or "auto").strip() or "auto",
        model_path=str(env.get("VOXCPM2_MODEL_PATH") or "").strip(),
        cache_dir=str(env.get("VOXCPM2_CACHE_DIR") or "/data/models/voxcpm2").strip(),
        max_text_chars=max(1, _env_int(env, "VOXCPM2_MAX_TEXT_CHARS", 2000)),
        timeout_seconds=max(1, _env_int(env, "VOXCPM2_TIMEOUT_SECONDS", 180)),
        output_format=output_format,  # type: ignore[arg-type]
        allow_cpu=_env_bool(env, "VOXCPM2_ALLOW_CPU", True),
        admin_only=_env_bool(env, "VOXCPM2_ADMIN_ONLY", True),
        artifact_dir=str(env.get("VOXCPM2_ARTIFACT_DIR") or Path(tempfile.gettempdir()) / "toanaas_voxcpm2"),
        supported_languages=languages or ("vi", "en"),
        supported_genders=tuple(dict.fromkeys(genders or ("female", "male", "neutral"))),
    )


class VoxCPM2TTSProvider:
    provider_name = PROVIDER_NAME

    def __init__(
        self,
        config: VoxCPM2Config | None = None,
        *,
        model_loader: Callable[[VoxCPM2Config], Any] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or config_from_env()
        self._model_loader = model_loader
        self._clock = clock or time.time
        self._model: Any = None
        self._lazy_loaded = False
        self._loading = False
        self._last_error = ""
        self._lock = threading.RLock()

    @property
    def lazy_loaded(self) -> bool:
        return bool(self._lazy_loaded)

    @property
    def last_error(self) -> str:
        return self._last_error

    def status(self) -> dict[str, Any]:
        model_path = Path(self.config.model_path).expanduser() if self.config.model_path else None
        cache_dir = Path(self.config.cache_dir).expanduser() if self.config.cache_dir else None
        return {
            "enabled": bool(self.config.enabled),
            "model_available": bool(model_path and model_path.exists()),
            "lazy_loaded": bool(self._lazy_loaded),
            "device": self.config.device,
            "cache_dir_exists": bool(cache_dir and cache_dir.exists()),
            "last_error": self._last_error,
            "supported_languages": list(self.config.supported_languages),
            "admin_only": bool(self.config.admin_only),
            "queue_active": bool(self._loading),
        }

    def _clean_unavailable(self, code: str, requested_gender: str = "", fallback_reason: str = "") -> TTSResult:
        self._last_error = code
        return TTSResult(
            ok=False,
            provider_name=PROVIDER_NAME,
            requested_gender=requested_gender,
            fallback_reason=fallback_reason,
            error_code=code,
            public_message=PUBLIC_TTS_UNAVAILABLE,
        )

    def _model_available(self) -> bool:
        return bool(self.config.model_path and Path(self.config.model_path).expanduser().exists())

    def _load_model(self) -> Any:
        if callable(self._model_loader):
            return self._model_loader(self.config)
        module = importlib.import_module("voxcpm")
        if hasattr(module, "load_model"):
            return module.load_model(self.config.model_path, device=self.config.device, cache_dir=self.config.cache_dir)
        if hasattr(module, "VoxCPM2"):
            return module.VoxCPM2(model_path=self.config.model_path, device=self.config.device, cache_dir=self.config.cache_dir)
        raise RuntimeError("voxcpm2_loader_missing")

    def _get_model(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            self._loading = True
            try:
                self._model = self._load_model()
                self._lazy_loaded = True
                self._last_error = ""
                return self._model
            except Exception as exc:
                self._last_error = type(exc).__name__
                raise
            finally:
                self._loading = False

    def _resolve_gender(self, requested_gender: str) -> tuple[bool, str, bool, str]:
        requested = _clean_gender(requested_gender)
        supported = set(self.config.supported_genders or ())
        if requested in supported:
            return True, requested, False, ""
        if requested in {"female", "male"}:
            return False, "", False, f"{requested}_voice_unavailable"
        if "neutral" in supported:
            return True, "neutral", bool(requested and requested != "neutral"), "gender_defaulted_neutral" if requested else ""
        return False, "", False, "gender_unavailable"

    def _artifact_path(self, output_format: str) -> Path:
        artifact_dir = Path(self.config.artifact_dir).expanduser()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".wav" if output_format == "wav" else ".mp3"
        return artifact_dir / f"voxcpm2_{int(self._clock() * 1000)}_{threading.get_ident()}{suffix}"

    def _write_result_to_path(self, result: Any, output_path: Path) -> None:
        if isinstance(result, (bytes, bytearray)):
            output_path.write_bytes(bytes(result))
            return
        if isinstance(result, dict):
            for key in ("audio_bytes", "bytes", "data", "audio"):
                value = result.get(key)
                if isinstance(value, (bytes, bytearray)):
                    output_path.write_bytes(bytes(value))
                    return
            source_path = str(result.get("audio_path") or result.get("path") or "").strip()
            if source_path and Path(source_path).exists():
                output_path.write_bytes(Path(source_path).read_bytes())
                return
        source_path = str(getattr(result, "audio_path", "") or getattr(result, "path", "") or "").strip()
        if source_path and Path(source_path).exists():
            output_path.write_bytes(Path(source_path).read_bytes())

    def _run_model(
        self,
        model: Any,
        *,
        text: str,
        language: str,
        gender: str,
        voice_id: str,
        reference_audio_path: str,
        speed: float,
        emotion: str,
        output_path: Path,
    ) -> None:
        kwargs = {
            "text": text,
            "language": language,
            "gender": gender,
            "voice_id": voice_id or None,
            "reference_audio_path": reference_audio_path or None,
            "speed": speed,
            "emotion": emotion or None,
            "output_path": str(output_path),
        }
        if hasattr(model, "synthesize_to_file"):
            result = model.synthesize_to_file(**kwargs)
            if result is not None:
                self._write_result_to_path(result, output_path)
            return
        if hasattr(model, "synthesize"):
            result = model.synthesize(**kwargs)
            self._write_result_to_path(result, output_path)
            return
        if callable(model):
            result = model(**kwargs)
            self._write_result_to_path(result, output_path)
            return
        raise RuntimeError("voxcpm2_model_synthesize_missing")

    def synthesize(
        self,
        text: str,
        language: str = "vi",
        gender: str | None = None,
        voice_id: str | None = None,
        reference_audio_path: str | None = None,
        speed: float | None = None,
        emotion: str | None = None,
        output_format: OutputFormat | None = None,
        output_path: str | None = None,
        *,
        admin: bool = False,
    ) -> TTSResult:
        requested_gender = _clean_gender(gender)
        if not self.config.enabled:
            return self._clean_unavailable("adapter_disabled", requested_gender)
        if self.config.admin_only and not admin:
            return self._clean_unavailable("admin_only", requested_gender)
        clean_text = " ".join(str(text or "").split())
        if not clean_text:
            return self._clean_unavailable("text_missing", requested_gender)
        if len(clean_text) > int(self.config.max_text_chars or 2000):
            return self._clean_unavailable("text_too_long", requested_gender)
        if not self._model_available() and not callable(self._model_loader):
            return self._clean_unavailable("adapter_unavailable", requested_gender)
        ok_gender, resolved_gender, fallback_used, fallback_reason = self._resolve_gender(requested_gender)
        if not ok_gender:
            return self._clean_unavailable("gender_unavailable", requested_gender, fallback_reason)

        fmt = str(output_format or self.config.output_format or "wav").lower()
        if fmt not in {"wav", "mp3"}:
            fmt = "wav"
        artifact_path = Path(output_path).expanduser() if output_path else self._artifact_path(fmt)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            model = self._get_model()
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            timed_out = False
            try:
                future = pool.submit(
                    self._run_model,
                    model,
                    text=clean_text,
                    language=str(language or "vi"),
                    gender=resolved_gender,
                    voice_id=str(voice_id or ""),
                    reference_audio_path=str(reference_audio_path or ""),
                    speed=float(speed or 1.0),
                    emotion=str(emotion or ""),
                    output_path=artifact_path,
                )
                future.result(timeout=max(1, int(self.config.timeout_seconds or 180)))
            except concurrent.futures.TimeoutError:
                timed_out = True
                raise
            finally:
                pool.shutdown(wait=not timed_out, cancel_futures=timed_out)
        except concurrent.futures.TimeoutError:
            return self._clean_unavailable("timeout", requested_gender, fallback_reason)
        except Exception as exc:
            return self._clean_unavailable(type(exc).__name__ or "synthesize_failed", requested_gender, fallback_reason)

        validation = validate_tts_audio_file(artifact_path, require_duration=(fmt == "wav"))
        if not validation.ok:
            self._last_error = validation.error_code
            return TTSResult(
                ok=False,
                audio_path=validation.audio_path,
                duration=validation.duration,
                bytes=validation.bytes,
                sample_rate=validation.sample_rate,
                provider_name=PROVIDER_NAME,
                requested_gender=requested_gender,
                resolved_gender=resolved_gender,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                error_code=validation.error_code,
                public_message=PUBLIC_TTS_UNAVAILABLE,
            )
        return TTSResult(
            ok=True,
            audio_path=validation.audio_path,
            duration=validation.duration,
            bytes=validation.bytes,
            sample_rate=validation.sample_rate,
            provider_name=PROVIDER_NAME,
            requested_gender=requested_gender,
            resolved_gender=resolved_gender,
            resolved_voice_id=str(voice_id or resolved_gender or "voxcpm2"),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )


def provider_from_env() -> VoxCPM2TTSProvider:
    return VoxCPM2TTSProvider(config_from_env())


def status_from_env() -> dict[str, Any]:
    return provider_from_env().status()


def synthesize_to_bytes(**kwargs: Any) -> tuple[TTSResult, bytes]:
    provider = kwargs.pop("provider", None) or provider_from_env()
    result = provider.synthesize(**kwargs)
    audio = b""
    if result.ok and result.audio_path and Path(result.audio_path).exists():
        audio = Path(result.audio_path).read_bytes()
    return result, audio
