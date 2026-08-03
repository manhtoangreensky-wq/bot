"""Provider-free public Frame Video seam for ROUTEENGINE29O."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import shutil
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, urlsplit

from services import (
    frame_video_engine,
    frame_video_runtime,
    telegram_transport,
    video_engine_contract,
)


FRAME_VIDEO_PUBLIC_SEAM_FLAG = "FRAME_VIDEO_DURABLE_PUBLIC_SEAM_ENABLED"
FRAME_VIDEO_WORKER_FLAG_KEYS = (
    FRAME_VIDEO_PUBLIC_SEAM_FLAG,
    "FRAME_VIDEO_ENGINE_ENABLED",
    "FRAME_VIDEO_PUBLIC_ALLOWED",
    "FRAME_VIDEO_AUTO_RETRY",
    "FRAME_VIDEO_AUTO_FALLBACK",
)
FRAME_VIDEO_TELEGRAM_CLOUD_API_ROOT = "https://api.telegram.org"
FRAME_VIDEO_TELEGRAM_CLOUD_INPUT_LIMIT_MB = 20
FRAME_VIDEO_TELEGRAM_CLOUD_OUTPUT_LIMIT_MB = 49
FRAME_VIDEO_TELEGRAM_LOCAL_LIMIT_MAX_MB = 2000
FRAME_VIDEO_SHORT_MEDIA_MAX_BYTES = 20 * 1024 * 1024
FRAME_VIDEO_SHORT_MEDIA_MAX_SECONDS = 60.0


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes", "on"}


def sanitize_frame_video_worker_sha(value: Any) -> str:
    """Keep only a bounded revision token suitable for an admission record."""

    token = _clean(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", token):
        return ""
    return token.lower()


def _sanitize_worker_id(value: Any) -> str:
    token = _clean(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,119}", token):
        return ""
    return token


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return parsed if parsed > 0 else 0


def _positive_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return parsed if math.isfinite(parsed) and parsed > 0 else 0.0


def frame_video_stage_timeout_seconds(
    expected_duration_seconds: Any,
    *,
    input_bytes: Any = 0,
    large_media: bool = False,
    ceiling_seconds: Any = 7200,
) -> int:
    """Scale a bounded stage timeout from measured duration and input size."""

    ceiling = _positive_int(ceiling_seconds) or 7200
    ceiling = min(7200, max(180, ceiling))
    duration = _positive_float(expected_duration_seconds)
    size_mib = _positive_int(input_bytes) / float(1024 * 1024)
    duration_estimate = duration * 4.0 + 120.0 if duration else 180.0
    size_estimate = size_mib * 3.0 + 120.0 if size_mib else 180.0
    estimated = math.ceil(max(duration_estimate, size_estimate))
    if large_media:
        estimated = max(1800, estimated)
    return min(ceiling, max(180, estimated))


def frame_video_telegram_api_root(
    environ: Mapping[str, Any] | None = None,
) -> str:
    source = os.environ if environ is None else environ
    configured = _clean(source.get("TELEGRAM_API_BASE_URL"))
    return (
        telegram_transport.normalize_api_root(configured)
        if configured
        else FRAME_VIDEO_TELEGRAM_CLOUD_API_ROOT
    )


def _frame_video_telegram_local_api_enabled(
    environ: Mapping[str, Any] | None = None,
) -> bool:
    return frame_video_telegram_api_root(environ) != FRAME_VIDEO_TELEGRAM_CLOUD_API_ROOT


def frame_video_telegram_api_proxy_headers(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    source = os.environ if environ is None else environ
    if not _frame_video_telegram_local_api_enabled(source):
        return {}
    raw_secret = str(source.get("TELEGRAM_API_PROXY_SECRET") or "")
    if "\r" in raw_secret or "\n" in raw_secret:
        raise ValueError("telegram_proxy_secret_invalid")
    secret = _clean(raw_secret)
    if not secret:
        hostname = _clean(urlsplit(frame_video_telegram_api_root(source)).hostname).lower()
        if hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("telegram_proxy_secret_missing")
        return {}
    header = _clean(source.get("TELEGRAM_API_PROXY_SECRET_HEADER")) or (
        "X-Toanaas-Proxy-Secret"
    )
    if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", header):
        raise ValueError("telegram_proxy_header_invalid")
    return {header: secret}


def _frame_video_telegram_token(value: Any) -> str:
    token = _clean(value)
    if not re.fullmatch(r"[A-Za-z0-9:_-]{1,256}", token):
        raise ValueError("telegram_token_invalid")
    return token


def frame_video_telegram_api_method_url(
    method: Any,
    *,
    token: Any,
    environ: Mapping[str, Any] | None = None,
) -> str:
    method_name = _clean(method)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", method_name):
        raise ValueError("telegram_method_invalid")
    url = (
        f"{frame_video_telegram_api_root(environ)}/"
        f"bot{_frame_video_telegram_token(token)}/{method_name}"
    )
    return telegram_transport.validate_api_url(url)


def frame_video_telegram_file_download_url(
    file_path: Any,
    *,
    token: Any,
    environ: Mapping[str, Any] | None = None,
) -> str:
    source = os.environ if environ is None else environ
    raw = _clean(file_path)
    if not raw:
        raise ValueError("telegram_file_path_missing")
    root = frame_video_telegram_api_root(source)
    if _frame_video_telegram_local_api_enabled(source):
        file_root = (
            _clean(source.get("TELEGRAM_LOCAL_API_FILE_ROOT"))
            or "/var/lib/telegram-bot-api"
        ).rstrip("/")
        current_token = _frame_video_telegram_token(token)
        required_prefix = f"{file_root}/{current_token}/"
        if "\\" in raw or not raw.startswith(required_prefix):
            raise ValueError("telegram_file_path_invalid")
        relative = raw[len(file_root) :].lstrip("/")
        if not relative or ".." in relative.split("/"):
            raise ValueError("telegram_file_path_invalid")
        media_path = "/" + (
            _clean(source.get("TELEGRAM_LOCAL_API_MEDIA_PATH")) or "localfile"
        ).strip("/")
        url = f"{root}{media_path}/{quote(relative, safe='/@._:-')}"
        return telegram_transport.validate_api_url(url)
    relative = raw.lstrip("/")
    if not relative or ".." in relative.split("/"):
        raise ValueError("telegram_file_path_invalid")
    url = (
        f"{root}/file/bot{_frame_video_telegram_token(token)}/"
        f"{quote(relative, safe='/@._:-')}"
    )
    return telegram_transport.validate_api_url(url)


def _frame_video_telegram_limit_bytes(
    environ: Mapping[str, Any] | None,
    *,
    name: str,
    cloud_mb: int,
    local_default_mb: int,
) -> int:
    source = os.environ if environ is None else environ
    if not _frame_video_telegram_local_api_enabled(source):
        return int(cloud_mb) * 1024 * 1024
    configured = _positive_int(source.get(name)) or int(local_default_mb)
    return min(FRAME_VIDEO_TELEGRAM_LOCAL_LIMIT_MAX_MB, configured) * 1024 * 1024


def frame_video_telegram_input_limit_bytes(
    environ: Mapping[str, Any] | None = None,
) -> int:
    return _frame_video_telegram_limit_bytes(
        environ,
        name="FRAME_VIDEO_TELEGRAM_MAX_INPUT_MB",
        cloud_mb=FRAME_VIDEO_TELEGRAM_CLOUD_INPUT_LIMIT_MB,
        local_default_mb=500,
    )


def frame_video_telegram_output_limit_bytes(
    environ: Mapping[str, Any] | None = None,
) -> int:
    return _frame_video_telegram_limit_bytes(
        environ,
        name="FRAME_VIDEO_TELEGRAM_MAX_OUTPUT_MB",
        cloud_mb=FRAME_VIDEO_TELEGRAM_CLOUD_OUTPUT_LIMIT_MB,
        local_default_mb=500,
    )


def frame_video_processing_input_limit_bytes(
    environ: Mapping[str, Any] | None = None,
) -> int:
    source = os.environ if environ is None else environ
    configured = _positive_int(
        source.get("FRAME_VIDEO_PROCESSING_MAX_INPUT_MB", 1000)
    )
    return max(1, configured) * 1024 * 1024


def frame_video_media_lane(
    state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(state or {})
    photos = [dict(item or {}) for item in list(payload.get("photos") or [])]
    declared_sizes = [_positive_int(item.get("file_size")) for item in photos]
    optional_sizes: list[int] = []
    optional_unknown = False
    for prefix in ("logo", "music", "voice"):
        if not _clean(payload.get(f"{prefix}_file_id")):
            continue
        size = _positive_int(payload.get(f"{prefix}_file_size"))
        optional_sizes.append(size)
        optional_unknown = optional_unknown or size <= 0
    size_known = bool(photos) and all(value > 0 for value in declared_sizes)
    size_known = size_known and not optional_unknown
    total_bytes = sum(declared_sizes) + sum(optional_sizes)
    duration_seconds = _positive_float(
        frame_video_runtime.expected_duration_seconds(payload)
    )
    duration_known = duration_seconds > 0
    short = bool(
        size_known
        and duration_known
        and total_bytes <= FRAME_VIDEO_SHORT_MEDIA_MAX_BYTES
        and duration_seconds <= FRAME_VIDEO_SHORT_MEDIA_MAX_SECONDS
    )
    if not size_known or not duration_known:
        reason = "metadata_unknown"
    elif total_bytes > FRAME_VIDEO_SHORT_MEDIA_MAX_BYTES:
        reason = "declared_size_over_short_threshold"
    elif duration_seconds > FRAME_VIDEO_SHORT_MEDIA_MAX_SECONDS:
        reason = "duration_over_short_threshold"
    else:
        reason = "within_short_thresholds"
    return {
        "lane": "short_media" if short else "large_media",
        "reason": reason,
        "size_known": size_known,
        "duration_known": duration_known,
        "declared_input_bytes": total_bytes,
        "duration_seconds": duration_seconds,
    }


def frame_video_input_capacity_blocker(
    paths: list[str] | tuple[str, ...],
    environ: Mapping[str, Any] | None = None,
) -> str:
    limit = frame_video_processing_input_limit_bytes(environ)
    total = 0
    for raw_path in paths:
        candidate = Path(_clean(raw_path)).expanduser()
        if not candidate.is_file():
            continue
        total += max(0, int(candidate.stat().st_size))
        if total > limit:
            return "frame_video_processing_capacity_exceeded"
    return ""


def frame_video_telegram_delivery_method(output_bytes: Any) -> str:
    return (
        "document"
        if _positive_int(output_bytes) > FRAME_VIDEO_SHORT_MEDIA_MAX_BYTES
        else "video"
    )


def frame_video_delivery_outcome_uncertain(error: BaseException) -> bool:
    reason = _clean(error).lower()
    error_types = {
        item.__name__.lower()
        for item in type(error).__mro__
    }
    if reason in {
        "telegram_delivery_outcome_uncertain",
        "telegram_delivery_receipt_missing",
        "frame_video_delivery_receipt_missing",
    }:
        return True
    if reason == "telegram_delivery_rejected":
        return False
    return bool(
        isinstance(error, (TimeoutError, OSError))
        or any(
            marker in error_type
            for error_type in error_types
            for marker in ("timeout", "timedout", "network", "connection")
        )
        or any(
            marker in reason
            for marker in (
                "timed out",
                "timeout",
                "connection reset",
                "connection aborted",
                "network error",
                "response stream reset",
            )
        )
    )


def frame_video_delivery_receipt_blocker(
    delivery_message_id: Any,
    delivery_file_id: Any,
) -> str:
    message_id = _clean(delivery_message_id)
    if not re.fullmatch(r"[1-9][0-9]{0,19}", message_id):
        return "delivery_message_id_invalid"
    if not _clean(delivery_file_id):
        return "delivery_file_id_missing"
    return ""


def _compact_probe_reason(value: Any) -> str:
    reason = _clean(value)
    if not reason:
        return ""
    if "/" in reason or "\\" in reason or re.match(r"^[A-Za-z]:", reason):
        return "probe_failed"
    token = re.sub(r"[^A-Za-z0-9_.:-]+", "_", reason).strip("_.:-")
    return (token or "probe_failed")[:80]


def frame_video_worker_flag_snapshot(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    engine_flags = frame_video_engine.frame_video_engine_flags(source)
    return {
        FRAME_VIDEO_PUBLIC_SEAM_FLAG: frame_video_public_seam_enabled(source),
        **{
            key: bool(engine_flags[key])
            for key in FRAME_VIDEO_WORKER_FLAG_KEYS
            if key != FRAME_VIDEO_PUBLIC_SEAM_FLAG
        },
    }


def normalize_frame_video_worker_flags(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    if set(value) != set(FRAME_VIDEO_WORKER_FLAG_KEYS):
        return {}
    normalized: dict[str, bool] = {}
    for key in FRAME_VIDEO_WORKER_FLAG_KEYS:
        item = value.get(key)
        if not isinstance(item, bool):
            return {}
        normalized[key] = item
    return normalized


def frame_video_worker_queue_admission(
    worker: Mapping[str, Any] | None,
    *,
    expected_worker_sha: Any,
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Require an exact worker revision and Frame flag handshake before queueing."""

    actual_sha = sanitize_frame_video_worker_sha(dict(worker or {}).get("worker_sha"))
    expected_sha = sanitize_frame_video_worker_sha(expected_worker_sha)
    if not expected_sha:
        return {"ok": False, "blocker": "worker_expected_sha_missing"}
    if not actual_sha:
        return {"ok": False, "blocker": "worker_sha_missing"}
    if not hmac.compare_digest(actual_sha, expected_sha):
        return {
            "ok": False,
            "blocker": "worker_sha_mismatch",
            "worker_sha": actual_sha,
            "expected_worker_sha": expected_sha,
        }
    worker_flags = normalize_frame_video_worker_flags(
        dict(worker or {}).get("frame_video_engine_flags")
    )
    if not worker_flags:
        return {"ok": False, "blocker": "worker_engine_flags_missing"}
    expected_flags = frame_video_worker_flag_snapshot(environ)
    if worker_flags != expected_flags:
        return {
            "ok": False,
            "blocker": "worker_engine_flags_mismatch",
            "worker_flags": worker_flags,
            "expected_worker_flags": expected_flags,
        }
    return {
        "ok": True,
        "blocker": "",
        "worker_sha": actual_sha,
        "expected_worker_sha": expected_sha,
        "frame_video_engine_flags": worker_flags,
    }


def frame_video_worker_transition_blocker(
    previous_job: Mapping[str, Any] | None,
    requested_status: Any,
    reported_worker_id: Any,
) -> str:
    job = dict(previous_job or {})
    if _clean(job.get("job_type")) != "frame_video_render":
        return ""
    current = _clean(job.get("status")).lower()
    requested = _clean(requested_status).lower()
    allowed = {
        "queued": {"running", "failed", "cancelled"},
        "running": {"running", "succeeded", "failed", "cancelled"},
        "succeeded": {"succeeded"},
        "failed": {"failed"},
        "cancelled": {"cancelled"},
    }
    if requested not in allowed.get(current, set()):
        return "frame_worker_transition_invalid"
    admitted_worker = _sanitize_worker_id(job.get("worker_id"))
    reported_worker = _sanitize_worker_id(reported_worker_id)
    if requested in {"running", "succeeded", "failed"} and (
        not admitted_worker or not reported_worker
    ):
        return "frame_worker_identity_missing"
    if admitted_worker and reported_worker and not hmac.compare_digest(
        admitted_worker, reported_worker
    ):
        return "frame_worker_identity_mismatch"
    return ""


def frame_video_terminal_receipt_replay_blocker(
    previous_job: Mapping[str, Any] | None,
    requested_status: Any,
    *,
    output_url: Any = "",
    output_file_id: Any = "",
) -> str:
    """Keep a succeeded Frame receipt immutable across idempotent worker replays."""

    job = dict(previous_job or {})
    if _clean(job.get("job_type")) != "frame_video_render":
        return ""
    current = _clean(job.get("status")).lower()
    requested = _clean(requested_status).lower()
    if current != "succeeded" or requested != current:
        return ""

    stored_raw = _clean(job.get("output_url"))
    replay_raw = _clean(output_url) or stored_raw
    try:
        stored_receipt = json.loads(stored_raw)
        replay_receipt = json.loads(replay_raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return "frame_terminal_receipt_conflict"
    if (
        not isinstance(stored_receipt, dict)
        or not stored_receipt
        or not isinstance(replay_receipt, dict)
        or stored_receipt != replay_receipt
    ):
        return "frame_terminal_receipt_conflict"

    stored_file_id = _clean(job.get("output_file_id"))
    replay_file_id = _clean(output_file_id) or stored_file_id
    if not stored_file_id or not hmac.compare_digest(stored_file_id, replay_file_id):
        return "frame_terminal_receipt_conflict"
    return ""


def _compact_frame_probe(probe: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(probe or {})
    duration_delta = _positive_float(source.get("duration_delta_seconds"))
    try:
        audio_stream_count = max(0, int(source.get("audio_stream_count") or 0))
    except (TypeError, ValueError, OverflowError):
        audio_stream_count = 0
    compact: dict[str, Any] = {
        "ok": source.get("ok") is True,
        "full_decode": source.get("full_decode") is True,
        "reason": _compact_probe_reason(source.get("reason")),
        "duration_seconds": round(_positive_float(source.get("duration_seconds")), 3),
        "expected_duration_seconds": round(
            _positive_float(source.get("expected_duration_seconds")), 3
        ),
        "duration_delta_seconds": round(duration_delta, 3),
        "size_bytes": _positive_int(source.get("size_bytes")),
        "video_stream_count": _positive_int(source.get("video_stream_count")),
        "audio_stream_count": audio_stream_count,
        "video_codec": _clean(source.get("video_codec"))[:40],
        "width": _positive_int(source.get("width")),
        "height": _positive_int(source.get("height")),
    }
    for key in ("artifact_sha256", "plan_sha256", "frame_order_sha256"):
        digest = _clean(source.get(key)).lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            compact[key] = digest
    return compact


def compact_frame_video_probe(
    probe: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return only bounded, path-free validation evidence for durable storage."""

    return _compact_frame_probe(probe)


def build_frame_video_worker_terminal_receipt(
    *,
    frame_job_id: Any,
    local_worker_job_id: Any,
    delivery_message_id: Any,
    delivery_file_id: Any,
    output_size_bytes: Any,
    output_sha256: Any,
    worker_id: Any,
    worker_sha: Any,
    probe: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "terminal_contract_version": 1,
        "frame_job_id": _clean(frame_job_id)[:120],
        "local_worker_job_id": str(_positive_int(local_worker_job_id) or ""),
        "delivery_message_id": _clean(delivery_message_id)[:80],
        "delivery_file_id": _clean(delivery_file_id)[:240],
        "output_size_bytes": _positive_int(output_size_bytes),
        "output_sha256": _clean(output_sha256).lower()[:64],
        "worker_id": _sanitize_worker_id(worker_id),
        "worker_sha": sanitize_frame_video_worker_sha(worker_sha),
        "ffprobe": _compact_frame_probe(probe),
        "charge_policy": "post_delivery",
        "wallet_charge_amount_xu": 0,
    }


def validate_frame_video_worker_terminal(
    payload: Mapping[str, Any] | None,
    receipt: Mapping[str, Any] | None,
    *,
    admitted_worker_id: Any,
    reported_worker_id: Any,
    expected_local_worker_job_id: Any,
) -> dict[str, Any]:
    job_payload = dict(payload or {})
    terminal = dict(receipt or {})
    admitted = _sanitize_worker_id(admitted_worker_id)
    reported = _sanitize_worker_id(reported_worker_id)
    terminal_worker = _sanitize_worker_id(terminal.get("worker_id"))
    if not admitted or not reported or not terminal_worker:
        return {"ok": False, "blocker": "frame_worker_identity_missing"}
    if not (
        hmac.compare_digest(admitted, reported)
        and hmac.compare_digest(admitted, terminal_worker)
    ):
        return {"ok": False, "blocker": "frame_worker_identity_mismatch"}

    expected_sha = sanitize_frame_video_worker_sha(
        job_payload.get("frame_video_expected_worker_sha")
        or job_payload.get("frame_video_runtime_sha")
    )
    actual_sha = sanitize_frame_video_worker_sha(terminal.get("worker_sha"))
    if not expected_sha or not actual_sha:
        return {"ok": False, "blocker": "worker_sha_missing"}
    if not hmac.compare_digest(expected_sha, actual_sha):
        return {"ok": False, "blocker": "worker_sha_mismatch"}

    expected_frame_job_id = _clean(job_payload.get("frame_job_id"))
    terminal_frame_job_id = _clean(terminal.get("frame_job_id"))
    if not expected_frame_job_id or not hmac.compare_digest(
        expected_frame_job_id,
        terminal_frame_job_id,
    ):
        return {"ok": False, "blocker": "frame_job_id_mismatch"}
    expected_queue_job_id = _positive_int(expected_local_worker_job_id)
    terminal_queue_job_id = _positive_int(terminal.get("local_worker_job_id"))
    if not expected_queue_job_id or terminal_queue_job_id != expected_queue_job_id:
        return {"ok": False, "blocker": "local_worker_job_id_mismatch"}

    message_id = _clean(terminal.get("delivery_message_id"))
    delivery_file_id = _clean(terminal.get("delivery_file_id"))
    receipt_blocker = frame_video_delivery_receipt_blocker(
        message_id,
        delivery_file_id,
    )
    if receipt_blocker:
        return {"ok": False, "blocker": receipt_blocker}
    output_size = _positive_int(terminal.get("output_size_bytes"))
    if not output_size:
        return {"ok": False, "blocker": "frame_output_size_invalid"}
    output_sha = _clean(terminal.get("output_sha256")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", output_sha):
        return {"ok": False, "blocker": "frame_output_digest_invalid"}

    raw_probe = terminal.get("ffprobe")
    probe = _compact_frame_probe(raw_probe if isinstance(raw_probe, Mapping) else {})
    if not probe.get("ok"):
        return {"ok": False, "blocker": "frame_probe_not_ok"}
    if not probe.get("full_decode"):
        return {"ok": False, "blocker": "frame_full_decode_missing"}
    if probe.get("video_stream_count", 0) < 1:
        return {"ok": False, "blocker": "frame_video_stream_missing"}
    if not probe.get("video_codec") or not probe.get("width") or not probe.get("height"):
        return {"ok": False, "blocker": "frame_video_metrics_invalid"}
    if not probe.get("duration_seconds"):
        return {"ok": False, "blocker": "frame_duration_invalid"}
    if probe.get("size_bytes") != output_size:
        return {"ok": False, "blocker": "frame_output_size_mismatch"}
    probe_sha = _clean(probe.get("artifact_sha256")).lower()
    if not probe_sha or not hmac.compare_digest(probe_sha, output_sha):
        return {"ok": False, "blocker": "frame_output_digest_mismatch"}

    compact = build_frame_video_worker_terminal_receipt(
        frame_job_id=expected_frame_job_id,
        local_worker_job_id=expected_queue_job_id,
        delivery_message_id=message_id,
        delivery_file_id=delivery_file_id,
        output_size_bytes=output_size,
        output_sha256=output_sha,
        worker_id=terminal_worker,
        worker_sha=actual_sha,
        probe=probe,
    )
    return {"ok": True, "blocker": "", "receipt": compact}


def frame_video_public_seam_enabled(
    environ: Mapping[str, Any] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    return _flag(source.get(FRAME_VIDEO_PUBLIC_SEAM_FLAG, False))


def frame_video_public_minimum_images() -> int:
    """The durable engine supports one-frame motion and multi-frame composition."""

    return 1


def frame_video_public_seam_blocker(
    environ: Mapping[str, Any] | None = None,
) -> str:
    if not frame_video_public_seam_enabled(environ):
        return ""
    flags = frame_video_engine.frame_video_engine_flags(environ)
    if not flags["FRAME_VIDEO_ENGINE_ENABLED"]:
        return "frame_video_engine_disabled"
    if not flags["FRAME_VIDEO_PUBLIC_ALLOWED"]:
        return "frame_video_public_disabled"
    if flags["FRAME_VIDEO_AUTO_RETRY"]:
        return "automatic_retry_forbidden"
    if flags["FRAME_VIDEO_AUTO_FALLBACK"]:
        return "automatic_fallback_forbidden"
    return ""


def frame_video_public_seam_applies_to_worker_job(
    job: Mapping[str, Any] | None,
) -> bool:
    payload = dict(job or {})
    if _flag(payload.get("paid_preview")):
        return False
    return _flag(payload.get("frame_video_durable_public_seam"))


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _asset_component(kind: str, path: str, state: Mapping[str, Any]) -> dict[str, Any]:
    candidate = Path(_clean(path)).expanduser()
    if not candidate.is_file() or candidate.stat().st_size <= 0:
        raise ValueError(f"{kind}_asset_missing")
    volume = state.get(f"{kind}_volume_percent")
    fade = state.get(f"{kind}_fade_seconds")
    raw_volume = (35 if kind == "music" else 100) if volume in (None, "") else volume
    raw_fade = 0.35 if fade in (None, "") else fade
    if isinstance(raw_volume, bool):
        raise ValueError(f"{kind}_volume_invalid")
    if isinstance(raw_fade, bool):
        raise ValueError(f"{kind}_fade_invalid")
    try:
        parsed_volume = float(raw_volume)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{kind}_volume_invalid") from exc
    try:
        parsed_fade = float(raw_fade)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{kind}_fade_invalid") from exc
    if (
        not math.isfinite(parsed_volume)
        or not parsed_volume.is_integer()
        or not 0 <= parsed_volume <= 200
    ):
        raise ValueError(f"{kind}_volume_invalid")
    if not math.isfinite(parsed_fade) or not 0 <= parsed_fade <= 2:
        raise ValueError(f"{kind}_fade_invalid")
    return {
        "kind": kind,
        "asset_id": f"frame_{kind}_asset",
        "sha256": _sha256_file(candidate),
        "bytes": candidate.stat().st_size,
        "volume_percent": int(parsed_volume),
        "fade_seconds": parsed_fade,
    }


def build_frame_video_public_plan(
    state: Mapping[str, Any] | None,
    image_paths: list[str] | tuple[str, ...],
    *,
    music_path: str = "",
    voice_path: str = "",
    logo_path: str = "",
) -> frame_video_engine.FrameVideoPlan:
    clean_state = dict(state or {})
    validation = frame_video_runtime.validate_plan(
        clean_state,
        min_images=frame_video_public_minimum_images(),
    )
    manifest = list(validation.get("manifest") or [])
    if not validation.get("ok"):
        raise ValueError(str((validation.get("errors") or ["frame_plan_invalid"])[0]))
    paths = [str(item or "").strip() for item in image_paths]
    if len(paths) != len(manifest):
        raise ValueError("image_manifest_path_mismatch")
    config = dict(validation.get("config") or {})
    durations = frame_video_runtime.image_duration_map({**clean_state, "photos": manifest})
    motions = dict(clean_state.get("image_motions") or {})
    frames = [
        {
            "frame_index": index,
            "asset_id": str(item.get("image_id") or ""),
            "source_path": path,
            "duration_seconds": durations.get(str(item.get("image_id") or ""), config.get("seconds_per_image", 3.0)),
            "motion": motions.get(str(item.get("image_id") or ""), config.get("motion", "none")),
        }
        for index, (item, path) in enumerate(zip(manifest, paths), start=1)
    ]
    components = []
    if _flag(clean_state.get("music_enabled")) and not music_path:
        raise ValueError("music_asset_missing")
    if _flag(clean_state.get("voice_enabled")) and not voice_path:
        raise ValueError("voice_asset_missing")
    if music_path:
        components.append(_asset_component("music", music_path, clean_state))
    if voice_path:
        components.append(_asset_component("voice", voice_path, clean_state))
    audio_policy: dict[str, Any] = {
        "promised": bool(components),
        "asset_id": "frame_audio_mix" if components else "",
        "sha256": _sha256_json(components) if components else "",
        "components": components,
    }
    logo_sha = ""
    if _flag(clean_state.get("logo_enabled")) and not logo_path:
        raise ValueError("logo_asset_missing")
    if logo_path:
        candidate = Path(logo_path).expanduser()
        if not candidate.is_file() or candidate.stat().st_size <= 0:
            raise ValueError("logo_asset_missing")
        logo_sha = _sha256_file(candidate)
    runtime_contract = {
        "kind": "frame_public_runtime_contract",
        "fit_mode": config.get("fit_mode", "contain"),
        "background_color": config.get("background_color", "#111111"),
        "quality": dict(config.get("quality") or {}),
        "watermark_text": str(clean_state.get("watermark_text") or ""),
        "watermark_position": str(clean_state.get("watermark_position") or "top_right"),
        "logo_sha256": logo_sha,
        "logo_promised": bool(logo_sha),
        "logo_position": str(clean_state.get("logo_position") or "top_right"),
    }
    overlays = [item for item in list(clean_state.get("text_overlays") or []) if isinstance(item, Mapping)]
    overlays.append(runtime_contract)
    mode = "single_scene" if len(frames) == 1 else "multi_scene"
    return frame_video_engine.compile_frame_video_plan(
        frames=frames,
        mode=mode,
        aspect_ratio=str(clean_state.get("ratio") or "9x16"),
        custom_width=config.get("custom_width", 0),
        custom_height=config.get("custom_height", 0),
        transition=str(config.get("transition") or "fade"),
        transition_seconds=float(config.get("transition_seconds") or 0.1),
        text_overlays=overlays,
        audio_policy=audio_policy,
        voice_policy={},
    )


def render_frame_video_public(
    *,
    state: Mapping[str, Any] | None,
    image_paths: list[str] | tuple[str, ...],
    output_path: str,
    user_id: int,
    confirmation_id: str,
    language: str,
    runtime_sha: str,
    expected_worker_sha: str,
    environ: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    if not frame_video_public_seam_enabled(environ):
        return {
            "enabled": False,
            "legacy_passthrough": True,
            "ok": False,
            "engine_jobs": 0,
            "provider_calls": 0,
            "wallet_mutations": 0,
        }
    capacity_blocker = frame_video_input_capacity_blocker(
        tuple(image_paths)
        + tuple(
            str(kwargs.get(name) or "")
            for name in ("music_path", "voice_path", "logo_path")
        ),
        environ,
    )
    if capacity_blocker:
        return {
            "enabled": True,
            "legacy_passthrough": False,
            "ok": False,
            "blocker": capacity_blocker,
            "reason": capacity_blocker,
            "engine_jobs": 0,
            "provider_calls": 0,
            "wallet_mutations": 0,
        }
    try:
        plan = build_frame_video_public_plan(
            state,
            image_paths,
            music_path=str(kwargs.get("music_path") or ""),
            voice_path=str(kwargs.get("voice_path") or ""),
            logo_path=str(kwargs.get("logo_path") or ""),
        )
    except (OSError, TypeError, ValueError) as exc:
        blocker = _clean(str(exc)) or "frame_plan_invalid"
        return {
            "enabled": True,
            "legacy_passthrough": False,
            "ok": False,
            "blocker": blocker,
            "reason": blocker,
            "engine_jobs": 0,
            "provider_calls": 0,
            "wallet_mutations": 0,
        }
    worker_sha = _clean(kwargs.get("worker_sha") or expected_worker_sha)
    worker_instance_id = _clean(kwargs.get("worker_instance_id") or "frame-public-seam")
    ffmpeg_path = _clean(kwargs.get("ffmpeg_path") or shutil.which("ffmpeg") or "ffmpeg")
    manifest = video_engine_contract.build_worker_manifest(
        worker_sha=worker_sha,
        worker_instance_id=worker_instance_id,
        supported_products=[video_engine_contract.VideoProduct.FRAME_VIDEO],
        supported_modes=[plan.mode],
        renderer_name="frame-video-public-seam",
        renderer_version="29o",
        ffmpeg_version=Path(ffmpeg_path).name or "ffmpeg",
        provider_enabled=False,
        local_enabled=True,
        queue_ready=True,
        worker_connected=True,
        heartbeat_fresh=True,
        health_ok=True,
        worker_status="healthy",
        capabilities=[frame_video_engine.CANONICAL_WORKER_CAPABILITY],
        local_capabilities={frame_video_engine.CANONICAL_WORKER_CAPABILITY: True},
        provider_availability={},
    )
    manifest.update(
        {
            "engine_adapters": [frame_video_engine.ENGINE_ADAPTER],
            "artifact_ready": True,
        }
    )
    request = frame_video_engine.build_frame_video_request(
        user_id=int(user_id),
        confirmation_id=str(confirmation_id),
        language=str(language or "vi"),
        plan=plan,
        explicit_confirmation_receipt={"confirmation_id": str(confirmation_id), "source": "framevideo_confirm"},
        runtime_sha=str(runtime_sha),
        expected_worker_sha=str(expected_worker_sha),
        admin_no_charge=bool(kwargs.get("admin_no_charge", False)),
        charge_plan=kwargs.get("charge_plan") if isinstance(kwargs.get("charge_plan"), Mapping) else {},
    )
    ledger = kwargs.get("ledger")
    if not isinstance(ledger, frame_video_engine.FrameVideoEngineLedger):
        ledger = frame_video_engine.FrameVideoEngineLedger()
    music_path = _clean(kwargs.get("music_path"))
    voice_path = _clean(kwargs.get("voice_path"))
    logo_path = _clean(kwargs.get("logo_path"))
    source = os.environ if environ is None else environ
    timeout_ceiling = (
        _positive_int(kwargs.get("timeout_seconds"))
        or _positive_int(source.get("FRAME_VIDEO_STAGE_TIMEOUT_MAX_SECONDS"))
        or _positive_int(source.get("FRAME_VIDEO_MAX_RENDER_SECONDS"))
        or 7200
    )
    actual_input_bytes = sum(
        max(0, int(Path(path).stat().st_size))
        for path in tuple(image_paths) + (music_path, voice_path, logo_path)
        if path and Path(path).is_file()
    )
    media_lane = frame_video_media_lane(state)
    stage_timeout = frame_video_stage_timeout_seconds(
        plan.expected_duration_seconds,
        input_bytes=actual_input_bytes,
        large_media=str(media_lane.get("lane") or "") == "large_media",
        ceiling_seconds=timeout_ceiling,
    )
    execution = frame_video_engine.execute_frame_video_local(
        request,
        plan=plan,
        manifest=manifest,
        runtime_sha=str(runtime_sha),
        ledger=ledger,
        output_root=Path(str(output_path or "")).parent,
        output_path=output_path,
        asset_paths={frame.asset_id: frame.source_path for frame in plan.frames},
        audio_paths={"music": music_path, "voice": voice_path},
        logo_path=logo_path,
        render_state=dict(state or {}),
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=_clean(
            kwargs.get("ffprobe_path") or shutil.which("ffprobe") or "ffprobe"
        ),
        timeout_seconds=stage_timeout,
        environ=environ,
        public_request=True,
    )
    validation = dict(execution.get("validation") or {})
    blocker = _clean(execution.get("blocker"))
    return {
        **execution,
        "enabled": True,
        "legacy_passthrough": False,
        "engine_jobs": int(execution.get("job_count") or 0),
        "output_size_bytes": int(execution.get("output_bytes") or 0),
        "output_sha256": _clean(
            execution.get("output_sha256") or validation.get("artifact_sha256")
        ),
        "probe": validation,
        "plan": plan,
        "ledger": ledger,
        "worker_sha": worker_sha,
        "reason": blocker,
    }
