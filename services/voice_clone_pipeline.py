from __future__ import annotations

import asyncio
import hashlib
import inspect
import re
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from services import audio_postprocess, minimax_voice_adapter


PUBLIC_CUSTOM_VOICE_NOT_READY = (
    "Tạo voice riêng đang tạm khóa để kiểm soát chất lượng. TOAN AAS chưa xử lý và chưa trừ Xu. "
    "Anh/chị có thể dùng giọng nam/nữ mặc định hoặc voice đã lưu."
)
PUBLIC_CUSTOM_VOICE_FAILED = (
    "TOAN AAS chưa tạo được voice hợp lệ từ mẫu này. Anh/chị thử mẫu rõ hơn hoặc dùng giọng nam/nữ mặc định. "
    "TOAN AAS chưa trừ Xu."
)
PUBLIC_CUSTOM_VOICE_SAMPLE_TOO_SHORT = (
    "Mẫu giọng hơi ngắn. Anh/chị gửi mẫu dài hơn một chút, khoảng 10-30 giây, một người nói và ít tạp âm. "
    "TOAN AAS chưa trừ Xu."
)
PUBLIC_CUSTOM_VOICE_UNSUPPORTED_AUDIO = (
    "TOAN AAS chỉ nhận mẫu giọng mp3, m4a hoặc wav. Anh/chị gửi lại mẫu phù hợp. TOAN AAS chưa trừ Xu."
)
PUBLIC_CUSTOM_VOICE_SAMPLE_TOO_LARGE = (
    "Mẫu giọng đang lớn hơn giới hạn 20MB. Anh/chị gửi mẫu ngắn hơn, khoảng 10-30 giây. TOAN AAS chưa trừ Xu."
)
CUSTOM_VOICE_ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".wav"}
CUSTOM_VOICE_MAX_SAMPLE_BYTES = 20 * 1024 * 1024
CUSTOM_VOICE_MIN_DETECTABLE_SECONDS = 10.0


@dataclass
class CustomVoiceCreateResult:
    ok: bool
    status: str
    profile_id: int | None = None
    provider: str | None = None
    provider_voice_id: str | None = None
    provider_file_id: str | None = None
    preview_audio_path: str | None = None
    preview_audio_bytes: int = 0
    charged_xu: int = 0
    provider_called: bool = False
    created_files: list[str] = field(default_factory=list)
    error_code: str | None = None
    safe_public_message: str | None = None
    admin_debug_summary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VoiceResolution:
    ok: bool
    provider_voice_id: str = ""
    voice_source: str = ""
    profile_id: int = 0
    safe_public_message: str = ""
    admin_debug_summary: str = ""


@dataclass
class VoiceTTSResult:
    ok: bool
    audio_path: str = ""
    audio_bytes: int = 0
    provider_voice_id_used: str = ""
    voice_source: str = ""
    provider_called: bool = False
    charged_xu: int = 0
    safe_public_message: str = ""
    admin_debug_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _safe_text(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"(sk-|Bearer\s+|token=|api[_-]?key=|key=)[^\s;]+", r"\1***", text, flags=re.I)
    return text[:limit]


def _is_pass(status: Any) -> bool:
    return str(status or "").strip().upper() == "PASS"


def _route_error(
    adapter: str,
    operation: str,
    route: str,
    status: Any,
    detail: Any,
    *,
    http_status: int = 0,
    output_bytes: int = 0,
    payload_fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "adapter": _safe_text(adapter, 80),
        "operation": _safe_text(operation, 40),
        "route": _safe_text(route, 120),
        "http_status": int(http_status or 0),
        "provider_status": _safe_text(status, 80),
        "error_code": _safe_text(status, 80),
        "error_message": _safe_text(detail, 220),
        "output_bytes": int(output_bytes or 0),
        "payload_fields": [str(item)[:60] for item in (payload_fields or [])][:16],
    }


def _route_error_summary(item: dict[str, Any] | str, limit: int = 260) -> str:
    if not isinstance(item, dict):
        return _safe_text(item, limit)
    fields = ",".join(str(value) for value in (item.get("payload_fields") or [])) or "-"
    return _safe_text(
        "adapter={adapter}; operation={operation}; route={route}; http_status={http}; "
        "provider_status={status}; error_code={code}; error_message={message}; output_bytes={bytes}; "
        "payload_fields={fields}".format(
            adapter=item.get("adapter") or "-",
            operation=item.get("operation") or "-",
            route=item.get("route") or "-",
            http=int(item.get("http_status") or 0),
            status=item.get("provider_status") or "-",
            code=item.get("error_code") or "-",
            message=item.get("error_message") or "-",
            bytes=int(item.get("output_bytes") or 0),
            fields=fields,
        ),
        limit,
    )


def _permission_error(value: Any) -> bool:
    marker = str(value or "").lower()
    return bool("clone_permission_forbidden" in marker or "voice clone user forbidden" in marker or "forbidden" in marker)


def _not_ready_status(route_errors: list[dict[str, Any] | str] | None = None, error: Any = "") -> str:
    marker = " ".join([str(error or ""), *[_route_error_summary(item, 220) for item in (route_errors or [])]]).lower()
    if _permission_error(marker):
        return "CLONE_PERMISSION_FORBIDDEN"
    if "adapter_missing" in marker or "missing" in marker:
        return "CLONE_ADAPTER_MISSING"
    return "CLONE_NOT_READY"


def _extract_provider_voice_id(payload: Any) -> str:
    candidates: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key or "").strip().lower()
                if lowered in {"provider_voice_id", "voice_id", "voiceid", "custom_voice_id"} and str(child or "").strip():
                    candidates.append(str(child).strip())
                elif isinstance(child, (dict, list, tuple)):
                    visit(child)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(payload)
    for candidate in candidates:
        normalized = minimax_voice_adapter.normalize_voice_id(candidate)
        if minimax_voice_adapter.validate_provider_voice_id(normalized):
            return normalized
    return ""


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _preview_output_path(output_dir: str | None, user_id: Any, profile_id: int) -> Path:
    base = Path(str(output_dir or "") or tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{user_id}:{profile_id}".encode("utf-8", errors="ignore")).hexdigest()[:14]
    return base / f"toan_aas_voice_preview_{profile_id}_{digest}.mp3"


def _write_boosted_voice_output(raw_bytes: bytes, target_path: Path, metadata: dict[str, Any]) -> tuple[str, int, list[str]]:
    payload = bytes(raw_bytes or b"")
    if not payload:
        return "", 0, []
    target_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = target_path.with_name(f"{target_path.stem}_raw{target_path.suffix or '.mp3'}")
    boosted_path = audio_postprocess.boosted_output_path(target_path)
    raw_path.write_bytes(payload)
    boost = audio_postprocess.boost_voice_audio(str(raw_path), str(boosted_path), volume_factor=2.0, limiter=True)
    final_path = Path(boost.output_path) if boost.ok and boost.output_path and Path(boost.output_path).exists() else raw_path
    final_bytes = int(final_path.stat().st_size if final_path.exists() else len(payload))
    metadata.update({
        "voice_volume_boosted": bool(boost.boosted),
        "voice_volume_factor": float(boost.factor or 2.0),
        "voice_volume_fallback_original": bool(boost.fallback_original),
        "voice_volume_boost_detail": _safe_text(boost.detail, 120),
        "voice_volume_output_bytes": final_bytes,
    })
    return str(final_path), final_bytes, [str(raw_path), str(final_path)]


def _fake_provider_voice_id(user_id: Any, profile_id: int, display_name: str = "") -> str:
    digest = hashlib.sha256(f"{user_id}:{profile_id}:{display_name}".encode("utf-8", errors="ignore")).hexdigest()[:18]
    uid = re.sub(r"[^A-Za-z0-9]+", "-", str(user_id or "user")).strip("-")[:24] or "user"
    return minimax_voice_adapter.normalize_voice_id(f"toanaas-custom-{uid}-{digest}")


def _detect_sample_duration_seconds(path: Path) -> float:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        try:
            with wave.open(str(path), "rb") as wav_file:
                frame_rate = float(wav_file.getframerate() or 0)
                if frame_rate > 0:
                    return float(wav_file.getnframes() or 0) / frame_rate
        except Exception:
            return 0.0
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return float(str(completed.stdout or "").strip() or 0)
    except Exception:
        return 0.0


def _sample_validation_error(sample: Path) -> tuple[str, str] | None:
    if sample.suffix.lower() not in CUSTOM_VOICE_ALLOWED_EXTENSIONS:
        return "unsupported_audio_extension", PUBLIC_CUSTOM_VOICE_UNSUPPORTED_AUDIO
    size_bytes = int(sample.stat().st_size or 0)
    if size_bytes <= 0:
        return "sample_missing_or_empty", PUBLIC_CUSTOM_VOICE_FAILED
    if size_bytes > CUSTOM_VOICE_MAX_SAMPLE_BYTES:
        return "sample_too_large", PUBLIC_CUSTOM_VOICE_SAMPLE_TOO_LARGE
    duration_seconds = _detect_sample_duration_seconds(sample)
    if 0 < duration_seconds < CUSTOM_VOICE_MIN_DETECTABLE_SECONDS:
        return "sample_duration_too_short", PUBLIC_CUSTOM_VOICE_SAMPLE_TOO_SHORT
    return None


async def preflight_custom_voice_create(
    *,
    user_id,
    profile_id: int | None = None,
    admin_mode: bool = False,
    readiness: dict | None = None,
    route_attempts_func: Callable[..., Any] | None = None,
    access_allowed_func: Callable[..., Any] | None = None,
    ready_for_processing_func: Callable[..., Any] | None = None,
) -> CustomVoiceCreateResult:
    pid = int(profile_id or 0)
    readiness = dict(readiness or {})
    route_attempts = []
    if callable(route_attempts_func):
        route_attempts = list(await _maybe_await(route_attempts_func(readiness, admin_access=bool(admin_mode))) or [])
    access_allowed = True
    if callable(access_allowed_func):
        access_allowed = bool(await _maybe_await(access_allowed_func(user_id, readiness, route_attempts, admin_access=bool(admin_mode))))
    ready_for_processing = bool(readiness.get("ready"))
    if callable(ready_for_processing_func):
        ready_for_processing = bool(await _maybe_await(ready_for_processing_func(readiness, route_attempts, admin_access=bool(admin_mode))))
    if access_allowed and ready_for_processing and route_attempts:
        return CustomVoiceCreateResult(True, "PREFLIGHT_PASS", profile_id=pid, metadata={"route_count": len(route_attempts)})
    error_code = "CLONE_PERMISSION_FORBIDDEN" if readiness.get("provider_permission_blocked") else "provider_not_ready"
    return CustomVoiceCreateResult(
        False,
        "BLOCKED",
        profile_id=pid,
        error_code=error_code,
        safe_public_message=PUBLIC_CUSTOM_VOICE_NOT_READY,
        admin_debug_summary=_safe_text(f"ready={readiness.get('ready')}; routes={len(route_attempts)}; admin={admin_mode}", 260),
    )


async def process_custom_voice_create(
    *,
    user_id,
    sample_path,
    display_name,
    product_context,
    profile_id: int | None = None,
    admin_mode: bool = False,
    no_charge: bool = False,
    fake: bool = False,
    preview_text: str | None = None,
    readiness: dict | None = None,
    output_dir: str | None = None,
    metadata_updates: dict[str, Any] | None = None,
    route_attempts_func: Callable[..., Any] | None = None,
    access_allowed_func: Callable[..., Any] | None = None,
    ready_for_processing_func: Callable[..., Any] | None = None,
    make_provider_voice_id_func: Callable[..., str] | None = None,
    execute_engine_func: Callable[..., Any] | None = None,
    audio_reference_to_bytes_func: Callable[..., Any] | None = None,
    cap_preview_audio_func: Callable[..., Any] | None = None,
    record_attempt_func: Callable[..., Any] | None = None,
    finalize_profile_func: Callable[..., Any] | None = None,
    max_preview_seconds: int = 6,
) -> CustomVoiceCreateResult:
    del product_context, no_charge
    pid = int(profile_id or 0)
    label = re.sub(r"\s+", " ", str(display_name or "")).strip()[:120]
    metadata: dict[str, Any] = {"source_type": "custom_clone"}
    metadata.update(dict(metadata_updates or {}))
    if not pid:
        return CustomVoiceCreateResult(False, "FAIL", profile_id=pid, error_code="missing_profile_id", safe_public_message=PUBLIC_CUSTOM_VOICE_FAILED)
    if len(label) < 2:
        return CustomVoiceCreateResult(False, "FAIL", profile_id=pid, error_code="display_name_invalid", safe_public_message=PUBLIC_CUSTOM_VOICE_FAILED)
    sample = Path(str(sample_path or "")).expanduser()
    if not sample.exists() or not sample.is_file():
        return CustomVoiceCreateResult(False, "FAIL", profile_id=pid, error_code="sample_missing_or_empty", safe_public_message=PUBLIC_CUSTOM_VOICE_FAILED)
    sample_error = _sample_validation_error(sample)
    if sample_error:
        error_code, public_message = sample_error
        return CustomVoiceCreateResult(False, "FAIL", profile_id=pid, error_code=error_code, safe_public_message=public_message, metadata={**metadata, "sample_validation": error_code})
    audio_bytes = sample.read_bytes()
    if fake:
        provider_voice_id = _fake_provider_voice_id(user_id, pid, label)
        if not minimax_voice_adapter.validate_provider_voice_id(provider_voice_id):
            return CustomVoiceCreateResult(False, "FAIL", profile_id=pid, error_code="missing_provider_voice_id", safe_public_message=PUBLIC_CUSTOM_VOICE_FAILED)
        finalize = {}
        if callable(finalize_profile_func):
            finalize = await _maybe_await(finalize_profile_func(provider="minimax_fake", provider_voice_id=provider_voice_id, provider_file_id="", preview_audio_ref="", metadata_updates=metadata))
        if finalize and not finalize.get("ok"):
            return CustomVoiceCreateResult(False, "FAIL", profile_id=pid, provider_voice_id=provider_voice_id, error_code=str(finalize.get("reason") or "finalize_failed"), safe_public_message=str(finalize.get("public_message") or PUBLIC_CUSTOM_VOICE_FAILED), metadata=metadata)
        return CustomVoiceCreateResult(True, "PASS", profile_id=pid, provider="minimax_fake", provider_voice_id=provider_voice_id, charged_xu=int((finalize or {}).get("charged_xu") or 0), metadata=metadata)

    readiness = dict(readiness or {})
    route_attempts = []
    if callable(route_attempts_func):
        route_attempts = list(await _maybe_await(route_attempts_func(readiness, admin_access=bool(admin_mode))) or [])
    access_allowed = True
    if callable(access_allowed_func):
        access_allowed = bool(await _maybe_await(access_allowed_func(user_id, readiness, route_attempts, admin_access=bool(admin_mode))))
    ready_for_processing = bool(readiness.get("ready"))
    if callable(ready_for_processing_func):
        ready_for_processing = bool(await _maybe_await(ready_for_processing_func(readiness, route_attempts, admin_access=bool(admin_mode))))
    if not access_allowed or not ready_for_processing or not route_attempts:
        error_code = "CLONE_PERMISSION_FORBIDDEN" if readiness.get("provider_permission_blocked") else "provider_not_ready"
        return CustomVoiceCreateResult(
            False,
            "BLOCKED",
            profile_id=pid,
            error_code=error_code,
            safe_public_message=PUBLIC_CUSTOM_VOICE_NOT_READY,
            admin_debug_summary=_safe_text(f"ready={readiness.get('ready')}; routes={len(route_attempts)}; admin={admin_mode}", 260),
            metadata=metadata,
        )
    provider_voice_id_seed = (
        str(make_provider_voice_id_func(user_id, profile_id=pid) if callable(make_provider_voice_id_func) else "")
        or _fake_provider_voice_id(user_id, pid, label)
    )
    provider_voice_id_seed = minimax_voice_adapter.normalize_voice_id(provider_voice_id_seed)
    if not minimax_voice_adapter.validate_provider_voice_id(provider_voice_id_seed) or str(provider_voice_id_seed) == str(pid):
        return CustomVoiceCreateResult(
            False,
            "FAIL",
            profile_id=pid,
            error_code="missing_provider_voice_id",
            safe_public_message=PUBLIC_CUSTOM_VOICE_FAILED,
            metadata={**metadata, "provider_voice_id_seed_invalid": True},
        )
    if callable(execute_engine_func):
        async def _gate_runner():
            return {"ok": True, "status": "GATE_ONLY"}

        gate = await _maybe_await(
            execute_engine_func(
                "voice_clone",
                {"runner": _gate_runner, "state": {"profile_id": pid}, "sample_path": str(sample)},
                {"user_id": user_id, "entry_source": "interactive_product", "confirm_paid": True, "admin_interactive_confirm": True, "is_paid_job": bool(admin_mode)},
            )
        )
        if isinstance(gate, dict) and not gate.get("ok"):
            return CustomVoiceCreateResult(False, "BLOCKED", profile_id=pid, error_code=str(gate.get("status") or "engine_gate_blocked"), safe_public_message=PUBLIC_CUSTOM_VOICE_NOT_READY, admin_debug_summary=_safe_text(gate.get("detail") or gate.get("status"), 260), metadata=metadata)
    route_errors: list[dict[str, Any] | str] = []
    provider_name = ""
    provider_file_id = ""
    provider_voice_id = ""
    preview_audio_path = ""
    preview_audio_bytes = 0
    provider_called = False
    created_files: list[str] = []
    try:
        for route_name, upload_call, clone_call, tts_call in route_attempts:
            status, candidate_file_id, detail, http_status = await upload_call(audio_bytes)
            provider_called = True
            if not _is_pass(status) or not candidate_file_id:
                route_errors.append(_route_error(route_name, "upload", f"{route_name}/upload", status, detail, http_status=http_status, payload_fields=["file", "purpose"]))
                if callable(record_attempt_func):
                    await _maybe_await(record_attempt_func(status=status, provider=route_name, route=f"{route_name}/upload", upload_status=status, error=detail, updated_by=user_id))
                continue
            status, clone_payload, detail, http_status = await clone_call(candidate_file_id, provider_voice_id_seed)
            if not _is_pass(status):
                route_errors.append(_route_error(route_name, "clone", f"{route_name}/clone", status, detail, http_status=http_status, payload_fields=["file_id", "voice_id", "model", "text"]))
                if callable(record_attempt_func):
                    await _maybe_await(record_attempt_func(status=status, provider=route_name, route=f"{route_name}/clone", upload_status="PASS", clone_status=status, error=detail, updated_by=user_id))
                continue
            candidate_voice_id = _extract_provider_voice_id(clone_payload)
            if not candidate_voice_id and str(route_name) == "shopaikey_minimax":
                candidate_voice_id = provider_voice_id_seed
            candidate_voice_id = minimax_voice_adapter.normalize_voice_id(candidate_voice_id)
            if not candidate_voice_id or str(candidate_voice_id).strip() == str(pid):
                route_errors.append(_route_error(route_name, "clone", f"{route_name}/clone", "FAIL", "missing_provider_voice_id", http_status=http_status, payload_fields=["voice_id"]))
                if callable(record_attempt_func):
                    await _maybe_await(record_attempt_func(status="FAIL", provider=route_name, route=f"{route_name}/clone", upload_status="PASS", clone_status="PASS", error="missing_provider_voice_id", updated_by=user_id))
                continue
            provider_name = str(route_name)
            provider_file_id = str(candidate_file_id)
            provider_voice_id = candidate_voice_id
            clone_payload_dict = clone_payload if isinstance(clone_payload, dict) else {}
            demo_audio_ref = str((clone_payload_dict or {}).get("demo_audio") or "")
            preview_bytes = b""
            demo_detail = ""
            if demo_audio_ref and callable(audio_reference_to_bytes_func):
                preview_bytes, demo_detail = await audio_reference_to_bytes_func(demo_audio_ref)
            if not preview_bytes and callable(tts_call):
                status, preview_bytes, detail, http_status = await tts_call(str(preview_text or ""), voice_id=provider_voice_id)
                if not _is_pass(status) or not preview_bytes:
                    route_errors.append(_route_error(route_name, "tts", f"{route_name}/tts", status, f"{str(detail)[:120]}; demo={str(demo_detail)[:80]}", http_status=http_status, output_bytes=len(preview_bytes or b""), payload_fields=["text", "voice_id", "voice_style"]))
                    preview_bytes = b""
            if preview_bytes and callable(cap_preview_audio_func):
                capped_bytes, cap_detail = await cap_preview_audio_func(bytes(preview_bytes), int(max_preview_seconds or 6))
                if capped_bytes:
                    preview_path = _preview_output_path(output_dir, user_id, pid)
                    preview_audio_path, preview_audio_bytes, boost_files = _write_boosted_voice_output(bytes(capped_bytes), preview_path, metadata)
                    created_files.extend(boost_files)
                else:
                    metadata["preview_unavailable_reason"] = _safe_text(f"voice_preview_cap:{cap_detail}", 160)
            elif preview_bytes:
                preview_path = _preview_output_path(output_dir, user_id, pid)
                preview_audio_path, preview_audio_bytes, boost_files = _write_boosted_voice_output(bytes(preview_bytes), preview_path, metadata)
                created_files.extend(boost_files)
            else:
                metadata["preview_unavailable_reason"] = "provider_clone_succeeded_preview_unavailable"
            if callable(record_attempt_func):
                await _maybe_await(record_attempt_func(status="PASS", provider=route_name, route=f"{route_name}/upload_clone" + ("_tts" if preview_audio_bytes else ""), upload_status="PASS", clone_status="PASS", tts_status="PASS" if preview_audio_bytes else "SKIPPED", provider_voice_id=provider_voice_id, demo_audio=demo_audio_ref, error="-", updated_by=user_id))
            break
        if not provider_name or not minimax_voice_adapter.validate_provider_voice_id(provider_voice_id):
            status = _not_ready_status(route_errors, "voice_routes_failed")
            return CustomVoiceCreateResult(False, status, profile_id=pid, provider=provider_name or None, provider_called=provider_called, error_code=status, safe_public_message=PUBLIC_CUSTOM_VOICE_NOT_READY if status == "CLONE_PERMISSION_FORBIDDEN" else PUBLIC_CUSTOM_VOICE_FAILED, admin_debug_summary=" | ".join(_route_error_summary(item, 160) for item in route_errors[:4]), metadata={**metadata, "route_errors": route_errors})
        metadata.update({
            "provider_file_id": provider_file_id,
            "provider_route": provider_name,
            "provider_voice_id": provider_voice_id,
            "requested_provider_voice_id": provider_voice_id_seed,
            "preview_output_bytes": preview_audio_bytes,
        })
        finalize = {}
        if callable(finalize_profile_func):
            finalize = await _maybe_await(
                finalize_profile_func(
                    provider=provider_name,
                    provider_voice_id=provider_voice_id,
                    provider_file_id=provider_file_id,
                    preview_audio_ref=preview_audio_path,
                    metadata_updates=metadata,
                )
            )
            if finalize and not finalize.get("ok"):
                return CustomVoiceCreateResult(False, "FAIL", profile_id=pid, provider=provider_name, provider_voice_id=provider_voice_id, provider_file_id=provider_file_id, preview_audio_path=preview_audio_path or None, preview_audio_bytes=preview_audio_bytes, provider_called=provider_called, created_files=created_files, error_code=str(finalize.get("reason") or "finalize_failed"), safe_public_message=str(finalize.get("public_message") or PUBLIC_CUSTOM_VOICE_FAILED), admin_debug_summary=_safe_text(finalize.get("reason") or "", 220), metadata=metadata)
        return CustomVoiceCreateResult(True, "PASS", profile_id=pid, provider=provider_name, provider_voice_id=provider_voice_id, provider_file_id=provider_file_id, preview_audio_path=preview_audio_path or None, preview_audio_bytes=preview_audio_bytes, charged_xu=int((finalize or {}).get("charged_xu") or 0), provider_called=provider_called, created_files=created_files, metadata=metadata)
    except Exception as exc:
        status = _not_ready_status(route_errors, exc)
        return CustomVoiceCreateResult(False, status, profile_id=pid, provider=provider_name or None, provider_voice_id=provider_voice_id or None, provider_file_id=provider_file_id or None, provider_called=provider_called, created_files=created_files, error_code=status, safe_public_message=PUBLIC_CUSTOM_VOICE_NOT_READY if _permission_error(exc) else PUBLIC_CUSTOM_VOICE_FAILED, admin_debug_summary=_safe_text(f"{type(exc).__name__}: {exc}", 260), metadata={**metadata, "route_errors": route_errors})


def resolve_user_voice_for_tts(
    user_id,
    selected_voice_option,
    db=None,
    *,
    get_profile_func: Callable[..., dict] | None = None,
    get_default_voice_id_func: Callable[[str], str] | None = None,
) -> VoiceResolution:
    del db
    option = selected_voice_option
    profile = option if isinstance(option, dict) else {}
    source = str((profile or {}).get("voice_source") or option or "").strip().lower()
    if isinstance(option, int) or (isinstance(option, str) and option.isdigit()):
        profile_id = int(option or 0)
        profile = get_profile_func(user_id, profile_id) if callable(get_profile_func) else {}
        source = "saved"
    if isinstance(option, str) and option.startswith(("default_", "male", "female")):
        gender = "male" if "male" in option else ("female" if "female" in option else "neutral")
        voice_id = get_default_voice_id_func(gender) if callable(get_default_voice_id_func) else ""
        resolved = minimax_voice_adapter.resolve_provider_voice_id(voice_source=f"default_{gender}", default_male_voice_id=voice_id if gender == "male" else "", default_female_voice_id=voice_id if gender != "male" else "")
    else:
        resolved = minimax_voice_adapter.resolve_provider_voice_id(voice_source=source or "saved", profile=profile)
    if not resolved.ok:
        return VoiceResolution(False, voice_source=source or "saved", profile_id=int((profile or {}).get("id") or 0), safe_public_message=resolved.public_message or minimax_voice_adapter.PUBLIC_SAFE_VOICE_NOT_READY, admin_debug_summary=resolved.reason)
    return VoiceResolution(True, provider_voice_id=resolved.provider_voice_id, voice_source=source or "saved", profile_id=resolved.profile_id)


async def process_voice_tts(
    *,
    user_id,
    text,
    selected_voice_option,
    product_context,
    admin_mode: bool = False,
    fake: bool = False,
    output_path: str | None = None,
    get_profile_func: Callable[..., dict] | None = None,
    get_default_voice_id_func: Callable[[str], str] | None = None,
    execute_tts_func: Callable[..., Any] | None = None,
) -> VoiceTTSResult:
    del product_context
    clean_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean_text:
        return VoiceTTSResult(False, safe_public_message="TOAN AAS cần lời đọc trước khi tạo giọng.", admin_debug_summary="text_missing")
    resolution = resolve_user_voice_for_tts(user_id, selected_voice_option, get_profile_func=get_profile_func, get_default_voice_id_func=get_default_voice_id_func)
    if not resolution.ok:
        return VoiceTTSResult(False, voice_source=resolution.voice_source, safe_public_message=resolution.safe_public_message, admin_debug_summary=resolution.admin_debug_summary)
    if fake:
        payload = f"VOICE:{resolution.provider_voice_id}:{clean_text}".encode("utf-8")
    elif callable(execute_tts_func):
        result = await _maybe_await(execute_tts_func(clean_text, provider_voice_id=resolution.provider_voice_id, voice_source=resolution.voice_source, admin_mode=admin_mode))
        if isinstance(result, dict):
            payload = bytes(result.get("output_bytes") or result.get("audio_bytes") or b"")
        elif isinstance(result, (bytes, bytearray)):
            payload = bytes(result)
        elif isinstance(result, (tuple, list)) and len(result) > 1:
            payload = bytes(result[1] or b"")
        else:
            payload = b""
    else:
        return VoiceTTSResult(False, provider_voice_id_used=resolution.provider_voice_id, voice_source=resolution.voice_source, safe_public_message=minimax_voice_adapter.PUBLIC_SAFE_TTS_ERROR, admin_debug_summary="tts_executor_missing")
    if not payload:
        return VoiceTTSResult(False, provider_voice_id_used=resolution.provider_voice_id, voice_source=resolution.voice_source, provider_called=not fake, safe_public_message=minimax_voice_adapter.PUBLIC_SAFE_TTS_ERROR, admin_debug_summary="audio_empty")
    path = ""
    metadata: dict[str, Any] = {}
    if output_path:
        target = Path(str(output_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        path, output_bytes, _boost_files = _write_boosted_voice_output(payload, target, metadata)
        payload_size = output_bytes or len(payload)
    else:
        payload_size = len(payload)
    return VoiceTTSResult(True, audio_path=path, audio_bytes=payload_size, provider_voice_id_used=resolution.provider_voice_id, voice_source=resolution.voice_source, provider_called=not fake, charged_xu=0, metadata=metadata)
