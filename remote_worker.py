"""Remote VPS worker for TOAN AAS heavy local/video processing.

This process runs on the VPS and talks to the Railway bot only through the
authenticated /api/v1/worker/* bridge. It never opens the Railway SQLite DB and
does not need PayOS, wallet, or Telegram webhook authority.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path


def load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as exc:
        print(f"[remote_worker] .env load skipped: {type(exc).__name__}")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
load_dotenv(os.path.join(os.getcwd(), ".env"))


def env_flag(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, str(default)) or str(default)).strip())
    except Exception:
        return int(default)


def normalize_base_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if not value:
        return "http://127.0.0.1:8000"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return "https://" + value


BOT_API_URL = normalize_base_url(
    os.environ.get("BOT_API_URL")
    or os.environ.get("LOCAL_WORKER_BOT_URL")
    or os.environ.get("TOAN_AAS_BOT_URL")
    or os.environ.get("PUBLIC_BASE_URL")
    or "https://bot-production-2dd7.up.railway.app"
)
LOCAL_WORKER_TOKEN = str(os.environ.get("LOCAL_WORKER_TOKEN", "")).strip()
WORKER_ID = str(os.environ.get("WORKER_ID") or os.environ.get("LOCAL_WORKER_ID") or "vps-1").strip()
WORKER_POLL_INTERVAL_SECONDS = max(1, env_int("WORKER_POLL_INTERVAL_SECONDS", 5))
WORKER_CONCURRENCY = max(1, env_int("WORKER_CONCURRENCY", 1))
WORKER_TMP_DIR = str(os.environ.get("WORKER_TMP_DIR") or tempfile.gettempdir()).strip()
FFMPEG_MAX_CONCURRENT = max(1, env_int("FFMPEG_MAX_CONCURRENT", 1))
FFMPEG_PATH = str(os.environ.get("LOCAL_FFMPEG_PATH") or os.environ.get("FFMPEG_PATH") or "ffmpeg").strip()
LAST_CLAIM_RESPONSE: dict = {}
LAST_IDLE_REASON = ""
LAST_REAL_VIDEO_RENDER_RESULT: dict = {}
LOCAL_VIDEO_FAKE_RENDERER_ENABLED = env_flag("LOCAL_VIDEO_FAKE_RENDERER_ENABLED", "false")
REAL_VIDEO_RENDER_UNAVAILABLE = "real_video_renderer_unavailable"
RENDER_MODE_REAL = "real"
RENDER_MODE_ADMIN_TEST_PATTERN = "admin_test_pattern"
RENDER_MODE_UNAVAILABLE = "unavailable"
REMOTE_WORKER_ADMIN_VIDEO_SOURCE = "admin_video_delivery"
REMOTE_WORKER_PRODUCT_VIDEO_SOURCE = "product_video"


def mask_secret(value: str) -> str:
    secret = str(value or "").strip()
    if not secret:
        return "no"
    if len(secret) <= 8:
        return f"<configured len={len(secret)}>"
    return f"{secret[:4]}...{secret[-4:]} len={len(secret)}"


def remote_worker_config() -> dict:
    return {
        "bot_api_url": BOT_API_URL,
        "worker_id": WORKER_ID,
        "poll_interval_seconds": WORKER_POLL_INTERVAL_SECONDS,
        "worker_concurrency": WORKER_CONCURRENCY,
        "worker_tmp_dir": WORKER_TMP_DIR,
        "ffmpeg_max_concurrent": FFMPEG_MAX_CONCURRENT,
        "local_worker_token_configured": bool(LOCAL_WORKER_TOKEN),
        "direct_sqlite_required": False,
    }


def endpoint(path: str) -> str:
    return BOT_API_URL.rstrip("/") + "/" + path.lstrip("/")


def auth_headers(content_type: str = "application/json") -> dict[str, str]:
    headers = {"Authorization": "Bearer " + LOCAL_WORKER_TOKEN, "User-Agent": f"toan-aas-remote-worker/{WORKER_ID}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint(path), data=data, headers=auth_headers(), method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return json.loads(body or "{}")


def _multipart_body(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = "----toanaasworker" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, (filename, content, content_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def http_multipart(path: str, fields: dict[str, str], files: dict[str, tuple[str, bytes, str]], timeout: int = 120) -> dict:
    body, content_type = _multipart_body(fields, files)
    request = urllib.request.Request(endpoint(path), data=body, headers=auth_headers(content_type), method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw or "{}")


def claim_job(
    canary_only: bool = False,
    admin_canary_only: bool = False,
    admin_video_only: bool = False,
    product_video_only: bool = False,
    owner_product_video_only: bool = False,
) -> dict | None:
    global LAST_CLAIM_RESPONSE
    if product_video_only or owner_product_video_only:
        capabilities = ["product_video", "owner_product_video", "ffmpeg", "video_postprocess"]
    elif admin_video_only:
        capabilities = ["admin_video", "ffmpeg"]
    elif admin_canary_only:
        capabilities = ["admin_canary", "ffmpeg"]
    elif canary_only:
        capabilities = ["canary", "ffmpeg"]
    else:
        capabilities = ["ffmpeg", "video_postprocess"]
    payload = {
        "worker_id": WORKER_ID,
        "capabilities": capabilities,
        "max_jobs": 1,
    }
    if canary_only:
        payload["canary_only"] = True
    if admin_canary_only:
        payload["admin_canary_only"] = True
    if admin_video_only:
        payload["admin_video_only"] = True
    if product_video_only:
        payload["product_video_only"] = True
    if owner_product_video_only:
        payload["owner_product_video_only"] = True
    global LAST_CLAIM_RESPONSE
    try:
        data = http_json("POST", "/api/v1/worker/claim", payload, timeout=30)
    except Exception as exc:
        LAST_CLAIM_RESPONSE = {"ok": False, "reason": type(exc).__name__}
        raise
    LAST_CLAIM_RESPONSE = data if isinstance(data, dict) else {}
    return data.get("job") if isinstance(data, dict) and data.get("ok") else None


def claim_idle_reason(
    *,
    canary_only: bool = False,
    admin_canary_only: bool = False,
    admin_video_only: bool = False,
    product_video_only: bool = False,
    owner_product_video_only: bool = False,
) -> str:
    response = LAST_CLAIM_RESPONSE if isinstance(LAST_CLAIM_RESPONSE, dict) else {}
    reason = str(response.get("reason") or "").strip()
    if reason:
        return reason
    if admin_canary_only:
        return "no_matching_jobs_or_job_already_failed_or_filter_mismatch_or_api_no_job"
    if owner_product_video_only:
        return "no_matching_owner_product_jobs_or_public_gate_mismatch_or_api_no_job"
    if product_video_only:
        return "no_matching_product_jobs_or_public_gate_mismatch_or_api_no_job"
    if admin_video_only:
        return "no_matching_admin_video_jobs_or_job_already_failed_or_filter_mismatch_or_api_no_job"
    if canary_only:
        return "no_matching_canary_jobs_or_job_already_failed_or_filter_mismatch_or_api_no_job"
    return "api_no_job"


def claim_debug_lines() -> list[str]:
    response = LAST_CLAIM_RESPONSE if isinstance(LAST_CLAIM_RESPONSE, dict) else {}
    debug = response.get("debug") if isinstance(response.get("debug"), dict) else {}
    if not debug:
        return []
    lines: list[str] = []
    claim_route = str(debug.get("claim_route") or "").strip()
    if claim_route:
        lines.append(f"[remote_worker] once claim_route={claim_route}")
    if "public_worker_enabled" in debug:
        lines.append(f"[remote_worker] once public_worker_enabled={'yes' if debug.get('public_worker_enabled') else 'no'}")
    counts = debug.get("lane_counts") if isinstance(debug.get("lane_counts"), dict) else {}
    if counts:
        ordered = ["admin_canary", "owner_product_video", "admin_video", "public_product_video", "public_gate_blocked"]
        parts = []
        for key in ordered:
            if key in counts:
                parts.append(f"{key}={counts.get(key)}")
        for key in sorted(k for k in counts if k not in ordered):
            parts.append(f"{key}={counts.get(key)}")
        lines.append(f"[remote_worker] once lane_counts {' '.join(parts)}")
    reason = str(debug.get("not_claimable_reason") or "").strip()
    if reason:
        lines.append(f"[remote_worker] once not_claimable_reason={reason}")
    return lines


def ping_server(
    canary: bool = False,
    admin_canary: bool = False,
    admin_video: bool = False,
    product_video: bool = False,
    owner_product_video: bool = False,
) -> dict:
    if product_video or owner_product_video:
        capabilities = ["product_video", "owner_product_video", "ffmpeg", "video_postprocess"]
    elif admin_video:
        capabilities = ["admin_video", "ffmpeg"]
    elif admin_canary:
        capabilities = ["admin_canary", "ffmpeg"]
    elif canary:
        capabilities = ["canary", "ffmpeg"]
    else:
        capabilities = ["ffmpeg", "video_postprocess"]
    payload = {
        "worker_id": WORKER_ID,
        "capabilities": capabilities,
        "dry_run": True,
    }
    if canary:
        payload["canary_only"] = True
    if admin_canary:
        payload["admin_canary_only"] = True
    if admin_video:
        payload["admin_video_only"] = True
    if product_video:
        payload["product_video_only"] = True
    if owner_product_video:
        payload["owner_product_video_only"] = True
    return http_json("POST", "/api/v1/worker/ping", payload, timeout=20)


def send_heartbeat(job_id: str, progress_percent: int = 0, message: str = "") -> None:
    payload = {
        "worker_id": WORKER_ID,
        "job_id": str(job_id),
        "progress_percent": int(progress_percent or 0),
        "message": str(message or "")[:500],
    }
    http_json("POST", "/api/v1/worker/heartbeat", payload, timeout=20)


def complete_job(job_id: str, result: dict, final_video_path: str = "") -> dict:
    metadata = {
        "worker_id": WORKER_ID,
        "job_id": str(job_id),
        "result": result or {},
    }
    if final_video_path and os.path.exists(final_video_path) and os.path.getsize(final_video_path) > 0:
        with open(final_video_path, "rb") as handle:
            content = handle.read()
        return http_multipart(
            "/api/v1/worker/complete",
            {"metadata": json.dumps(metadata, ensure_ascii=False)},
            {"file": (os.path.basename(final_video_path) or "result.mp4", content, "video/mp4")},
            timeout=180,
        )
    return http_json("POST", "/api/v1/worker/complete", metadata, timeout=60)


def fail_job(job_id: str, safe_error: str, retryable: bool = True, partial_artifacts: list | None = None) -> dict:
    payload = {
        "worker_id": WORKER_ID,
        "job_id": str(job_id),
        "safe_error": str(safe_error or "remote_worker_failed")[:500],
        "retryable": bool(retryable),
        "partial_artifacts": partial_artifacts or [],
    }
    if LAST_REAL_VIDEO_RENDER_RESULT:
        payload["diagnostics"] = dict(LAST_REAL_VIDEO_RENDER_RESULT or {})
    return http_json("POST", "/api/v1/worker/fail", payload, timeout=30)


def first_line(text: str) -> str:
    for line in str(text or "").splitlines():
        clean = line.strip()
        if clean:
            return clean[:300]
    return ""


def normalize_render_mode(job: dict | None = None) -> str:
    data = dict(job or {})
    mode = str(data.get("render_mode") or "").strip().lower().replace("-", "_")
    if mode in {"test_pattern", "admin_test", "admin_test_pattern"}:
        return RENDER_MODE_ADMIN_TEST_PATTERN
    if mode == RENDER_MODE_UNAVAILABLE:
        return RENDER_MODE_UNAVAILABLE
    return RENDER_MODE_REAL


def admin_test_pattern_allowed(job: dict | None = None) -> bool:
    data = dict(job or {})
    if normalize_render_mode(data) != RENDER_MODE_ADMIN_TEST_PATTERN:
        return False
    return bool(
        data.get("admin_video_delivery")
        and str(data.get("source") or "") == REMOTE_WORKER_ADMIN_VIDEO_SOURCE
        and data.get("admin_only")
        and data.get("no_charge")
        and not data.get("provider_call")
        and not data.get("public_user")
    )


def product_video_job_allowed(job: dict | None = None) -> bool:
    data = dict(job or {})
    return bool(
        str(data.get("job_type") or "") == "video_render"
        and str(data.get("source") or "") == REMOTE_WORKER_PRODUCT_VIDEO_SOURCE
        and normalize_render_mode(data) == RENDER_MODE_REAL
        and not data.get("test_pattern")
        and not data.get("admin_video_delivery")
        and not data.get("canary")
        and not data.get("worker_admin_canary")
        and (data.get("provider_call") or data.get("claim_only_diagnostic"))
    )


def local_ffmpeg_path() -> str:
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        return FFMPEG_PATH
    return shutil.which(FFMPEG_PATH) or shutil.which("ffmpeg") or FFMPEG_PATH


def ffmpeg_available() -> bool:
    candidate = local_ffmpeg_path()
    return bool(candidate and (os.path.exists(candidate) or shutil.which(candidate)))


def local_doctor_lines() -> tuple[list[str], bool]:
    token_ok = bool(LOCAL_WORKER_TOKEN)
    ffmpeg_ok = ffmpeg_available()
    tmp_ok = bool(WORKER_TMP_DIR)
    lines = [
        "[remote_worker] doctor",
        f"Worker ID: {WORKER_ID}",
        f"BOT_API_URL: {BOT_API_URL}",
        f"token configured: {'yes' if token_ok else 'no'} ({mask_secret(LOCAL_WORKER_TOKEN)})",
        f"ffmpeg found: {'yes' if ffmpeg_ok else 'no'}",
        f"tmp dir configured: {'yes' if tmp_ok else 'no'}",
    ]
    return lines, bool(token_ok and ffmpeg_ok and tmp_ok)


def run_doctor() -> int:
    lines, ok = local_doctor_lines()
    for line in lines:
        print(line)
    print(f"doctor: {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


def render_fake_video(job: dict, work_dir: str) -> str:
    output_path = os.path.join(work_dir, f"remote_worker_job_{job.get('job_id') or 'test'}.mp4")
    ffmpeg = local_ffmpeg_path()
    if ffmpeg and shutil.which(ffmpeg) or (ffmpeg and os.path.exists(ffmpeg)):
        command = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1E88E5:s=540x960:r=24:d=2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        raise RuntimeError(first_line(result.stderr or result.stdout) or "fake_renderer_ffmpeg_failed")
    Path(output_path).write_bytes(b"TOAN_AAS_REMOTE_WORKER_FAKE_MP4")
    return output_path


def render_canary_video(job: dict, work_dir: str) -> str:
    output_path = os.path.join(work_dir, f"remote_worker_canary_{job.get('job_id') or 'test'}.mp4")
    ffmpeg = local_ffmpeg_path()
    ffmpeg_ok = bool(ffmpeg and (os.path.exists(ffmpeg) or shutil.which(ffmpeg)))
    if not ffmpeg_ok:
        raise RuntimeError("ffmpeg_missing")
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x180:rate=24",
        "-t",
        "2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise RuntimeError(first_line(result.stderr or result.stdout) or "canary_ffmpeg_failed")
    if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("canary_output_empty")
    return output_path


def render_admin_canary_video(job: dict, work_dir: str) -> str:
    output_path = os.path.join(work_dir, f"remote_worker_admin_canary_{job.get('job_id') or 'test'}.mp4")
    ffmpeg = local_ffmpeg_path()
    ffmpeg_ok = bool(ffmpeg and (os.path.exists(ffmpeg) or shutil.which(ffmpeg)))
    if not ffmpeg_ok:
        raise RuntimeError("ffmpeg_missing")
    duration = max(1, min(10, int(job.get("expected_duration_seconds") or 3)))
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x180:rate=24",
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        raise RuntimeError(first_line(result.stderr or result.stdout) or "admin_canary_ffmpeg_failed")
    if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("admin_canary_output_empty")
    return output_path


def render_admin_video_delivery(job: dict, work_dir: str) -> str:
    output_path = os.path.join(work_dir, f"remote_worker_admin_video_{job.get('job_id') or 'test'}.mp4")
    ffmpeg = local_ffmpeg_path()
    ffmpeg_ok = bool(ffmpeg and (os.path.exists(ffmpeg) or shutil.which(ffmpeg)))
    if not ffmpeg_ok:
        raise RuntimeError("ffmpeg_missing")
    duration = max(1, min(30, int(job.get("expected_duration_seconds") or 6)))
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=540x960:rate=24",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:sample_rate=44100",
        "-t",
        str(duration),
        "-shortest",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode != 0:
        raise RuntimeError(first_line(result.stderr or result.stdout) or "admin_video_ffmpeg_failed")
    if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("admin_video_output_empty")
    return output_path


def render_real_video(job: dict, work_dir: str) -> str:
    """Render a normal product video through the real provider connector."""
    global LAST_REAL_VIDEO_RENDER_RESULT
    LAST_REAL_VIDEO_RENDER_RESULT = {}
    try:
        from services.video_real_render_connector import LAST_RENDER_DIAGNOSTICS, RealVideoRenderError, render_real_video_job
    except Exception as exc:
        raise RuntimeError(f"{REAL_VIDEO_RENDER_UNAVAILABLE}:connector_import_failed:{type(exc).__name__}") from exc
    try:
        result = render_real_video_job(job, work_dir)
        LAST_REAL_VIDEO_RENDER_RESULT = dict(result or {})
    except RealVideoRenderError as exc:
        LAST_REAL_VIDEO_RENDER_RESULT = dict(getattr(exc, "diagnostics", {}) or LAST_RENDER_DIAGNOSTICS or {})
        raise RuntimeError(str(exc) or REAL_VIDEO_RENDER_UNAVAILABLE) from exc
    final_path = str(result.get("final_video_path") or "")
    if not final_path or not os.path.exists(final_path) or os.path.getsize(final_path) <= 0:
        raise RuntimeError(REAL_VIDEO_RENDER_UNAVAILABLE)
    return final_path


def process_claimed_job(job: dict) -> dict:
    job_id = str(job.get("job_id") or "")
    if not job_id:
        raise RuntimeError("job_id_missing")
    if job.get("claim_only_diagnostic"):
        if str(job.get("source") or "") != REMOTE_WORKER_PRODUCT_VIDEO_SOURCE:
            raise RuntimeError("claim_only_product_video_required")
        if job.get("test_pattern") or job.get("admin_video_delivery") or job.get("provider_call") or job.get("public_user"):
            raise RuntimeError("unsafe_claim_only_diagnostic_metadata")
        send_heartbeat(job_id, 20, "product diagnostic claimed")
        result = {
            "ok": True,
            "claim_only_diagnostic": True,
            "diagnostic_claim_only": True,
            "renderer": "remote_worker_claim_only",
            "render_mode": RENDER_MODE_REAL,
            "test_pattern": False,
            "admin_video_delivery": False,
            "bytes": 0,
            "admin_only": True,
            "no_charge": True,
            "provider_call": False,
            "public_user": False,
            "source": REMOTE_WORKER_PRODUCT_VIDEO_SOURCE,
        }
        send_heartbeat(job_id, 100, "product diagnostic claim pass")
        return complete_job(job_id, result)
    with tempfile.TemporaryDirectory(dir=WORKER_TMP_DIR if os.path.isdir(WORKER_TMP_DIR) else None) as work_dir:
        send_heartbeat(job_id, 5, "claimed")
        mode = normalize_render_mode(job)
        if mode == RENDER_MODE_ADMIN_TEST_PATTERN:
            if not admin_test_pattern_allowed(job):
                raise RuntimeError("unsafe_test_pattern_route")
            if not LOCAL_VIDEO_FAKE_RENDERER_ENABLED:
                raise RuntimeError("admin_test_pattern_renderer_disabled")
            send_heartbeat(job_id, 35, "rendering ADMIN TEST PATTERN")
            final_path = render_fake_video(job, work_dir)
            result = {
                "ok": True,
                "render_mode": RENDER_MODE_ADMIN_TEST_PATTERN,
                "test_pattern": True,
                "renderer": "remote_worker_fake_admin_test",
                "final_video_name": os.path.basename(final_path),
                "bytes": os.path.getsize(final_path),
                "admin_only": True,
                "no_charge": True,
                "provider_call": False,
                "public_user": False,
                "warning": "ADMIN TEST PATTERN - not real rendered video",
            }
            send_heartbeat(job_id, 90, "uploading ADMIN TEST PATTERN")
            return complete_job(job_id, result, final_path)
        send_heartbeat(job_id, 20, "preparing product video")
        final_path = render_real_video(job, work_dir)
        send_heartbeat(job_id, 80, "product video rendered")
        send_heartbeat(job_id, 95, "uploading result")
        connector_result = dict(LAST_REAL_VIDEO_RENDER_RESULT or {})
        visual_classification = str(connector_result.get("visual_classification") or connector_result.get("final_classification") or "")
        force_no_charge = bool(visual_classification and visual_classification != "final_ai_video")
        result = {
            "ok": True,
            "render_mode": RENDER_MODE_REAL,
            "renderer": "remote_worker_real_render_route",
            "final_video_name": os.path.basename(final_path),
            "bytes": os.path.getsize(final_path),
            "source": REMOTE_WORKER_PRODUCT_VIDEO_SOURCE,
            "product_video": True,
            "test_pattern": False,
            "admin_video_delivery": False,
            "provider_call": bool(job.get("provider_call")),
            "public_user": bool(job.get("public_user")),
            "admin_only": bool(job.get("admin_only")),
            "no_charge": bool(job.get("no_charge")) or force_no_charge,
            "connector_renderer": str(connector_result.get("renderer") or ""),
            "provider_attempted": bool(connector_result.get("provider_attempted")),
            "provider_route_selected": bool(connector_result.get("provider_route_selected")),
            "provider_events": connector_result.get("provider_events") or [],
            "provider_task_ids": connector_result.get("provider_task_ids") or [],
            "provider_video_ids": connector_result.get("provider_video_ids") or [],
            "provider_models": connector_result.get("provider_models") or [],
            "provider_modes": connector_result.get("provider_modes") or [],
            "provider_status": str(connector_result.get("provider_status") or ""),
            "provider_error": str(connector_result.get("provider_error") or ""),
            "chunk_count": connector_result.get("chunk_count") or 0,
            "downloaded_clip_paths": connector_result.get("downloaded_clip_paths") or [],
            "stitch_attempted": bool(connector_result.get("stitch_attempted")),
            "fallback_used": bool(connector_result.get("fallback_used")),
            "fallback_reason": str(connector_result.get("fallback_reason") or ""),
            "visual_source": str(connector_result.get("visual_source") or ""),
            "visual_classification": visual_classification,
            "final_classification": visual_classification,
            "placeholder_detected": bool(connector_result.get("placeholder_detected") or connector_result.get("placeholder_visual")),
            "raw_prompt_burned_into_frame": bool(connector_result.get("raw_prompt_burned_into_frame")),
            "partial_addons": bool(connector_result.get("partial_addons")),
            "addon_degrade_notes": connector_result.get("addon_degrade_notes") or [],
        }
        return complete_job(job_id, result, final_path)


def process_admin_video_job(job: dict) -> dict:
    job_id = str(job.get("job_id") or "")
    if not job_id:
        raise RuntimeError("job_id_missing")
    if str(job.get("job_type") or "") != "video_render" or not job.get("admin_video_delivery"):
        raise RuntimeError("admin_video_job_required")
    if str(job.get("source") or "") != REMOTE_WORKER_ADMIN_VIDEO_SOURCE:
        raise RuntimeError("admin_video_route_source_required")
    if not job.get("admin_only") or not job.get("no_charge") or job.get("provider_call") or job.get("public_user"):
        raise RuntimeError("unsafe_admin_video_metadata")
    with tempfile.TemporaryDirectory(dir=WORKER_TMP_DIR if os.path.isdir(WORKER_TMP_DIR) else None) as work_dir:
        send_heartbeat(job_id, 10, "admin video claimed")
        mode = normalize_render_mode(job)
        if mode == RENDER_MODE_ADMIN_TEST_PATTERN:
            if not admin_test_pattern_allowed(job):
                raise RuntimeError("unsafe_test_pattern_route")
            send_heartbeat(job_id, 35, "rendering ADMIN TEST PATTERN")
            final_path = render_admin_video_delivery(job, work_dir)
            renderer = "remote_worker_admin_test_pattern_ffmpeg"
            test_pattern = True
            queue_label = "OWNER/ADMIN TEST PATTERN - video delivery only, no Xu"
        else:
            send_heartbeat(job_id, 35, "admin video real rendering")
            final_path = render_real_video(job, work_dir)
            renderer = "remote_worker_real_render_route"
            test_pattern = False
            queue_label = "OWNER/ADMIN VIDEO REAL RENDER - no Xu"
        send_heartbeat(job_id, 85, "admin video uploading")
        result = {
            "ok": True,
            "admin_video_delivery": True,
            "render_mode": RENDER_MODE_ADMIN_TEST_PATTERN if test_pattern else RENDER_MODE_REAL,
            "test_pattern": bool(test_pattern),
            "renderer": renderer,
            "final_video_name": os.path.basename(final_path),
            "bytes": os.path.getsize(final_path),
            "admin_only": True,
            "no_charge": True,
            "provider_call": False,
            "public_user": False,
            "queue_label": queue_label,
        }
        send_heartbeat(job_id, 100, "admin test pattern completed" if test_pattern else "admin real video completed")
        return complete_job(job_id, result, final_path)


def process_admin_canary_job(job: dict) -> dict:
    job_id = str(job.get("job_id") or "")
    if not job_id:
        raise RuntimeError("job_id_missing")
    if str(job.get("job_type") or "") != "video_render" or not job.get("worker_admin_canary"):
        raise RuntimeError("admin_canary_job_required")
    if not job.get("admin_only") or not job.get("no_charge") or job.get("provider_call") or job.get("public_user"):
        raise RuntimeError("unsafe_admin_canary_metadata")
    with tempfile.TemporaryDirectory(dir=WORKER_TMP_DIR if os.path.isdir(WORKER_TMP_DIR) else None) as work_dir:
        send_heartbeat(job_id, 10, "admin canary claimed")
        send_heartbeat(job_id, 30, "admin canary preparing")
        final_path = render_admin_canary_video(job, work_dir)
        send_heartbeat(job_id, 60, "admin canary rendering")
        send_heartbeat(job_id, 85, "admin canary uploading")
        result = {
            "ok": True,
            "admin_canary": True,
            "worker_admin_canary": True,
            "renderer": "remote_worker_admin_canary_ffmpeg",
            "final_video_name": os.path.basename(final_path),
            "bytes": os.path.getsize(final_path),
            "admin_only": True,
            "no_charge": True,
            "provider_call": False,
            "public_user": False,
            "queue_label": "OWNER/ADMIN WORKER CANARY - no Xu",
        }
        send_heartbeat(job_id, 100, "admin canary completed")
        return complete_job(job_id, result, final_path)


def process_canary_job(job: dict) -> dict:
    job_id = str(job.get("job_id") or "")
    if not job_id:
        raise RuntimeError("job_id_missing")
    if str(job.get("job_type") or "") != "remote_worker_canary" or not job.get("canary"):
        raise RuntimeError("canary_job_required")
    if not job.get("admin_only") or not job.get("no_charge") or job.get("provider_call") or job.get("public_user"):
        raise RuntimeError("unsafe_canary_metadata")
    with tempfile.TemporaryDirectory(dir=WORKER_TMP_DIR if os.path.isdir(WORKER_TMP_DIR) else None) as work_dir:
        send_heartbeat(job_id, 10, "canary claimed")
        final_path = render_canary_video(job, work_dir)
        send_heartbeat(job_id, 70, "canary uploading")
        result = {
            "ok": True,
            "canary": True,
            "renderer": "remote_worker_canary_ffmpeg",
            "final_video_name": os.path.basename(final_path),
            "bytes": os.path.getsize(final_path),
            "admin_only": True,
            "no_charge": True,
            "provider_call": False,
            "public_user": False,
        }
        return complete_job(job_id, result, final_path)


def claim_mode_label(
    *,
    canary_only: bool = False,
    admin_canary_only: bool = False,
    admin_video_only: bool = False,
    product_video_only: bool = False,
    owner_product_video_only: bool = False,
) -> str:
    if owner_product_video_only:
        return "owner_product_video"
    if product_video_only:
        return "product_video"
    if admin_video_only:
        return "admin_video"
    if admin_canary_only:
        return "admin_canary"
    if canary_only:
        return "canary"
    return "default_video"


def last_claim_reason() -> str:
    response = LAST_CLAIM_RESPONSE if isinstance(LAST_CLAIM_RESPONSE, dict) else {}
    reason = str(response.get("reason") or "").strip()
    if reason:
        return first_line(reason)[:160]
    if response.get("ok") is False:
        return "claim_api_not_ok"
    if response:
        return "api_returned_no_job"
    return "no_claim_response"


def run_once(
    canary_only: bool = False,
    admin_canary_only: bool = False,
    admin_video_only: bool = False,
    product_video_only: bool = False,
    owner_product_video_only: bool = False,
) -> str:
    global LAST_CLAIM_RESPONSE, LAST_IDLE_REASON
    LAST_CLAIM_RESPONSE = {}
    LAST_IDLE_REASON = ""
    if product_video_only or owner_product_video_only:
        job = claim_job(product_video_only=product_video_only, owner_product_video_only=owner_product_video_only)
    elif admin_video_only:
        job = claim_job(admin_video_only=True)
    elif admin_canary_only:
        job = claim_job(admin_canary_only=True)
    elif canary_only:
        job = claim_job(canary_only=True)
    else:
        job = claim_job()
    if not job:
        LAST_IDLE_REASON = claim_idle_reason(
            canary_only=canary_only,
            admin_canary_only=admin_canary_only,
            admin_video_only=admin_video_only,
            product_video_only=product_video_only,
            owner_product_video_only=owner_product_video_only,
        )
        print(
            "[remote_worker] claim idle "
            f"mode={claim_mode_label(canary_only=canary_only, admin_canary_only=admin_canary_only, admin_video_only=admin_video_only, product_video_only=product_video_only, owner_product_video_only=owner_product_video_only)} "
            "route=/api/v1/worker/claim "
            "status=idle "
            f"reason={LAST_IDLE_REASON}"
        )
        return "idle"
    job_id = str(job.get("job_id") or "")
    try:
        if admin_canary_only or job.get("worker_admin_canary"):
            process_admin_canary_job(job)
        elif admin_video_only or job.get("admin_video_delivery"):
            process_admin_video_job(job)
        elif product_video_only or owner_product_video_only:
            if not product_video_job_allowed(job):
                raise RuntimeError("product_video_job_required")
            process_claimed_job(job)
        elif canary_only or job.get("canary"):
            process_canary_job(job)
        else:
            process_claimed_job(job)
        return "completed"
    except Exception as exc:
        if job_id:
            message = first_line(str(exc))
            unavailable = REAL_VIDEO_RENDER_UNAVAILABLE in message
            fail_job(
                job_id,
                f"{type(exc).__name__}:{message}",
                retryable=not bool(
                    unavailable
                    or canary_only
                    or admin_canary_only
                    or admin_video_only
                    or product_video_only
                    or owner_product_video_only
                    or job.get("canary")
                    or job.get("worker_admin_canary")
                    or job.get("admin_video_delivery")
                    or job.get("product_video")
                ),
            )
        return "failed"


def run_ping_mode(
    *,
    dry_run: bool = False,
    canary: bool = False,
    admin_canary: bool = False,
    admin_video: bool = False,
    product_video: bool = False,
    owner_product_video: bool = False,
) -> int:
    lines, local_ok = local_doctor_lines()
    for line in lines:
        print(line)
    if not LOCAL_WORKER_TOKEN:
        print("ping: FAIL (LOCAL_WORKER_TOKEN missing)")
        if dry_run:
            print("claim skipped because dry-run: yes")
        return 1
    try:
        if product_video or owner_product_video:
            payload = ping_server(product_video=product_video, owner_product_video=owner_product_video)
        elif admin_video:
            payload = ping_server(admin_video=True)
        elif admin_canary:
            payload = ping_server(admin_canary=True)
        elif canary:
            payload = ping_server(canary=True)
        else:
            payload = ping_server()
    except urllib.error.HTTPError as exc:
        print(f"ping: FAIL (HTTP {exc.code})")
        if dry_run:
            print("claim skipped because dry-run: yes")
        return 1
    except urllib.error.URLError as exc:
        print(f"ping: FAIL ({type(exc.reason).__name__})")
        if dry_run:
            print("claim skipped because dry-run: yes")
        return 1
    except Exception as exc:
        print(f"ping: FAIL ({type(exc).__name__})")
        if dry_run:
            print("claim skipped because dry-run: yes")
        return 1
    ping_ok = bool(payload.get("ok") and payload.get("dry_run") and payload.get("can_claim_jobs") is False)
    print(f"ping: {'OK' if ping_ok else 'FAIL'}")
    print(f"server build: {payload.get('build') or '-'}")
    print(f"remote mode supported: {'yes' if payload.get('remote_worker_mode_supported') else 'no'}")
    if dry_run:
        print("claim skipped because dry-run: yes")
    return 0 if (local_ok and ping_ok) else 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TOAN AAS remote VPS worker")
    parser.add_argument("--doctor", action="store_true", help="run local environment checks and exit")
    parser.add_argument("--ping", action="store_true", help="ping Railway worker API and exit")
    parser.add_argument("--once", action="store_true", help="run one polling cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="ping only; never claim or complete real jobs")
    parser.add_argument("--canary", action="store_true", help="claim only safe remote_worker_canary jobs")
    parser.add_argument("--admin-canary", action="store_true", help="claim only admin production canary video_render jobs")
    parser.add_argument("--admin-video", action="store_true", help="claim only owner/admin no-charge video_render delivery jobs")
    parser.add_argument("--product-video", action="store_true", help="claim product video real-render jobs")
    parser.add_argument("--owner-product-video", action="store_true", help="claim only owner/admin no-charge product video real-render jobs")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    special_modes = [bool(args.canary), bool(args.admin_canary), bool(args.admin_video), bool(args.product_video), bool(args.owner_product_video)]
    if sum(1 for item in special_modes if item) > 1:
        print("[remote_worker] choose only one of --canary, --admin-canary, --admin-video, --product-video, or --owner-product-video")
        return 2
    if args.doctor:
        return run_doctor()
    if args.ping:
        return run_ping_mode(
            dry_run=args.dry_run,
            canary=args.canary,
            admin_canary=args.admin_canary,
            admin_video=args.admin_video,
            product_video=args.product_video,
            owner_product_video=args.owner_product_video,
        )
    if args.dry_run:
        return run_ping_mode(
            dry_run=True,
            canary=args.canary,
            admin_canary=args.admin_canary,
            admin_video=args.admin_video,
            product_video=args.product_video,
            owner_product_video=args.owner_product_video,
        )
    if args.once:
        status = run_once(
            canary_only=args.canary,
            admin_canary_only=args.admin_canary,
            admin_video_only=args.admin_video,
            product_video_only=args.product_video,
            owner_product_video_only=args.owner_product_video,
        )
        print(
            f"[remote_worker] once status={status} "
            f"canary_only={'yes' if args.canary else 'no'} "
            f"admin_canary_only={'yes' if args.admin_canary else 'no'} "
            f"admin_video_only={'yes' if args.admin_video else 'no'} "
            f"product_video_only={'yes' if args.product_video else 'no'} "
            f"owner_product_video_only={'yes' if args.owner_product_video else 'no'}"
        )
        if status == "idle":
            print(f"[remote_worker] once idle_reason={LAST_IDLE_REASON or 'api_no_job'}")
            for line in claim_debug_lines():
                print(line)
        return 1 if status == "failed" else 0

    print("[remote_worker] TOAN AAS Remote Worker starting")
    print(f"[remote_worker] base_url={BOT_API_URL}")
    print(f"[remote_worker] worker_id={WORKER_ID}")
    print(f"[remote_worker] token_configured={'yes' if bool(LOCAL_WORKER_TOKEN) else 'no'}")
    print(f"[remote_worker] concurrency={WORKER_CONCURRENCY} ffmpeg_max={FFMPEG_MAX_CONCURRENT}")
    print(f"[remote_worker] canary_only={'yes' if args.canary else 'no'}")
    print(f"[remote_worker] admin_canary_only={'yes' if args.admin_canary else 'no'}")
    print(f"[remote_worker] admin_video_only={'yes' if args.admin_video else 'no'}")
    print(f"[remote_worker] product_video_only={'yes' if args.product_video else 'no'}")
    print(f"[remote_worker] owner_product_video_only={'yes' if args.owner_product_video else 'no'}")
    while True:
        try:
            status = run_once(
                canary_only=args.canary,
                admin_canary_only=args.admin_canary,
                admin_video_only=args.admin_video,
                product_video_only=args.product_video,
                owner_product_video_only=args.owner_product_video,
            )
            if status == "idle":
                time.sleep(WORKER_POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("[remote_worker] stopped")
            return 0
        except urllib.error.HTTPError as exc:
            print(f"[remote_worker] HTTP {exc.code}; check BOT_API_URL/LOCAL_WORKER_TOKEN")
            time.sleep(WORKER_POLL_INTERVAL_SECONDS)
        except urllib.error.URLError as exc:
            print(f"[remote_worker] connection error: {type(exc.reason).__name__}")
            time.sleep(WORKER_POLL_INTERVAL_SECONDS)
        except Exception as exc:
            print(f"[remote_worker] loop error: {type(exc).__name__}")
            time.sleep(WORKER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
