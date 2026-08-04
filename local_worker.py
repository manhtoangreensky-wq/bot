"""
TOAN AAS Local Worker Phase 1.

Runs on the local Windows machine and polls Railway bot internal worker endpoints.
Supports worker health checks plus guarded local FFmpeg jobs used by TOAN AAS.
ComfyUI is kept as planned/not_ready and is not called unless later phases
explicitly enable it.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import socket
import shutil
import tempfile
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from services.multiscene_video_pipeline import (
    SceneSpec,
    create_multiscene_workspace,
    ensure_video_output,
    process_multiscene_video_pipeline,
    safe_run_ffmpeg,
)
from services.video_real_render_connector import (
    REAL_VIDEO_RENDER_UNAVAILABLE,
    build_real_scene_renderer,
    original_prompt_from_job,
    product_video_logo_material,
    product_video_scene_duration_seconds,
    real_video_llm_func_from_job,
)
from services.video_local_editing import (
    LocalVideoEditError,
    available_ffmpeg_filters,
    default_manual_edit_plan,
    execute_manual_edit,
    execute_split_plan,
    manual_plan_assets_match,
    plan_has_effective_operation,
    split_plan_has_manual_conflict,
)
from services.video_local_validation import (
    MAX_UPLOAD_BYTES,
    LocalVideoValidationError,
    cleanup_job_workspace,
    create_job_workspace,
    delivery_file_allowed,
    enforce_workspace_limit,
    find_ffprobe,
    safe_display_filename,
    validate_extension,
    ALLOWED_LOGO_EXTENSIONS,
    ALLOWED_SOURCE_EXTENSIONS,
    ALLOWED_SUBTITLE_EXTENSIONS,
)
from services.video_smart_splitter import SplitRange
from services import (
    frame_video_commercial,
    frame_video_public_seam,
    frame_video_runtime,
    video_ai_edit_provider,
    video_ai_edit_status,
    video_ai_edit_validation,
    video_edit_long_media,
    video_edit_media_transport,
    video_editengine1,
    video_local_validation,
)


_TELEGRAM_DEFAULT_URLOPEN = urllib.request.urlopen
from services import product_video_public_seam


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
        print(f"[local_worker] .env load skipped: {type(exc).__name__}")


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


def telegram_api_root(environ=None) -> str:
    return frame_video_public_seam.frame_video_telegram_api_root(environ)


def telegram_api_method_url(method: str, *, token: str = "", environ=None) -> str:
    return frame_video_public_seam.frame_video_telegram_api_method_url(
        method,
        token=token or TELEGRAM_BOT_TOKEN,
        environ=environ,
    )


def telegram_api_proxy_headers(environ=None) -> dict[str, str]:
    return frame_video_public_seam.frame_video_telegram_api_proxy_headers(environ)


def telegram_file_download_url(file_path: str, *, token: str = "", environ=None) -> str:
    return frame_video_public_seam.frame_video_telegram_file_download_url(
        file_path,
        token=token or TELEGRAM_BOT_TOKEN,
        environ=environ,
    )


def frame_video_telegram_input_limit_bytes(environ=None) -> int:
    return frame_video_public_seam.frame_video_telegram_input_limit_bytes(environ)


def normalize_base_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if not value:
        return "http://127.0.0.1:8000"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return "https://" + value


BOT_BASE_URL = normalize_base_url(
    os.environ.get("LOCAL_WORKER_BOT_URL")
    or os.environ.get("TOAN_AAS_BOT_URL")
    or os.environ.get("BOT_BASE_URL")
    or os.environ.get("PUBLIC_BASE_URL")
    or "http://127.0.0.1:8000"
)
LOCAL_WORKER_TOKEN = str(os.environ.get("LOCAL_WORKER_TOKEN", "")).strip()
TELEGRAM_BOT_TOKEN = str(os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or "").strip()
LOCAL_WORKER_ID = str(os.environ.get("LOCAL_WORKER_ID", "toan-aas-local-windows")).strip()
LOCAL_WORKER_MAX_JOB_SECONDS = max(30, env_int("LOCAL_WORKER_MAX_JOB_SECONDS", 600))
LOCAL_FFMPEG_PATH = str(
    os.environ.get("LOCAL_FFMPEG_PATH", r"D:\TOANAAS\ffmpeg-8.1.1\bin\ffmpeg.exe")
).strip()
LOCAL_FFMPEG_FONT_PATH = str(os.environ.get("LOCAL_FFMPEG_FONT_PATH", r"C:\Windows\Fonts\arial.ttf")).strip()
LOCAL_COMFY_ENABLED = env_flag("LOCAL_COMFY_ENABLED", "false")
VIDEO_PROJECT_QUEUE_ENABLED = env_flag("VIDEO_PROJECT_QUEUE_ENABLED", "true")
LOCAL_VIDEO_FAKE_RENDERER_ENABLED = env_flag("LOCAL_VIDEO_FAKE_RENDERER_ENABLED", "false")
RENDER_MODE_REAL = "real"
RENDER_MODE_ADMIN_TEST_PATTERN = "admin_test_pattern"
REMOTE_WORKER_ADMIN_VIDEO_SOURCE = "admin_video_delivery"
VIDEO_EDIT_WORKER_OWNER = "local_video_edit"
VIDEO_EDIT_ENGINE_ROUTE = "local_worker_ffmpeg"
VIDEO_EDIT_CAPABILITIES = ("video_edit",)
FRAME_VIDEO_WORKER_CAPABILITY = "frame_video_render"
LOCAL_WORKER_CAPABILITIES = VIDEO_EDIT_CAPABILITIES + (FRAME_VIDEO_WORKER_CAPABILITY,)
LOCAL_WORKER_STARTED_AT_UTC = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
LOCAL_WORKER_INSTANCE_ID = f"{LOCAL_WORKER_ID}:{socket.gethostname()}:{os.getpid()}"
LOCAL_WORKER_LAST_ERROR = ""
VIDEO_EDIT_RECEIPT_PAYLOAD_LIMIT = 128 * 1024


def endpoint(path: str) -> str:
    return BOT_BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def auth_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + LOCAL_WORKER_TOKEN,
        "x-local-worker-token": LOCAL_WORKER_TOKEN,
        "x-worker-id": LOCAL_WORKER_ID,
    }


def http_json(
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: int = 20,
    *,
    total_deadline_seconds: float | None = None,
) -> dict:
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint(path), data=data, headers=auth_headers(), method=method.upper())

    if total_deadline_seconds is None:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body or "{}")

    if isinstance(total_deadline_seconds, bool) or not isinstance(total_deadline_seconds, (int, float)):
        raise ValueError("http_json_total_deadline_invalid")
    try:
        deadline_seconds = float(total_deadline_seconds)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("http_json_total_deadline_invalid") from None
    if not math.isfinite(deadline_seconds) or deadline_seconds <= 0:
        raise ValueError("http_json_total_deadline_invalid")
    absolute_deadline = time.monotonic() + deadline_seconds
    deadline_event = threading.Event()
    watchdog: threading.Timer | None = None

    try:
        remaining = absolute_deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("http_json_total_deadline")
        effective_timeout = min(float(timeout), remaining)
        if effective_timeout <= 0:
            raise TimeoutError("http_json_total_deadline")
        with urllib.request.urlopen(request, timeout=effective_timeout) as response:
            def expire_response() -> None:
                deadline_event.set()
                try:
                    response_socket = response.fp.raw._sock
                except Exception:
                    response_socket = None
                if response_socket is not None:
                    try:
                        response_socket.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                try:
                    response.close()
                except Exception:
                    pass

            remaining = absolute_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("http_json_total_deadline")
            watchdog = threading.Timer(remaining, expire_response)
            watchdog.daemon = True
            watchdog.start()
            body_parts: list[bytes] = []
            body_size = 0
            body_limit = 512 * 1024
            try:
                while True:
                    if deadline_event.is_set() or time.monotonic() >= absolute_deadline:
                        raise TimeoutError("http_json_total_deadline")
                    chunk = response.read(min(64 * 1024, body_limit - body_size + 1))
                    if deadline_event.is_set() or time.monotonic() >= absolute_deadline:
                        raise TimeoutError("http_json_total_deadline")
                    if not chunk:
                        break
                    body_size += len(chunk)
                    if body_size > body_limit:
                        raise ValueError("http_json_response_too_large")
                    body_parts.append(bytes(chunk))
            except Exception:
                if deadline_event.is_set() or time.monotonic() >= absolute_deadline:
                    raise TimeoutError("http_json_total_deadline") from None
                raise
            finally:
                watchdog.cancel()
                watchdog.join()
    except Exception:
        if deadline_event.is_set() or time.monotonic() >= absolute_deadline:
            raise TimeoutError("http_json_total_deadline") from None
        raise

    if deadline_event.is_set() or time.monotonic() >= absolute_deadline:
        raise TimeoutError("http_json_total_deadline")
    body = b"".join(body_parts).decode("utf-8", errors="replace")
    result = json.loads(body or "{}")
    if time.monotonic() >= absolute_deadline:
        raise TimeoutError("http_json_total_deadline")
    return result


def local_worker_heartbeat_payload(*, last_error: str = "", queue_depth: int = 0) -> dict:
    ffmpeg_path = local_ffmpeg_path()
    try:
        discovered_filters = available_ffmpeg_filters(ffmpeg_path, refresh=True)
        video_edit_filters_known = True
    except Exception:
        discovered_filters = ()
        video_edit_filters_known = False
    video_edit_filters = sorted(
        {
            str(name)
            for name in discovered_filters
            if 0 < len(str(name)) <= 64
            and str(name) == str(name).lower()
            and str(name).replace("_", "").isalnum()
        }
    )
    return {
        "heartbeat_contract_version": 1,
        "worker_id": LOCAL_WORKER_ID,
        "worker_sha": local_worker_runtime_sha(),
        "frame_video_engine_flags": frame_video_public_seam.frame_video_worker_flag_snapshot(os.environ),
        "worker_owner": VIDEO_EDIT_WORKER_OWNER,
        "engine_route": VIDEO_EDIT_ENGINE_ROUTE,
        # This worker executes both canonical local-edit and frame-video jobs.
        # Advertising both avoids admitting a queued job to a worker that cannot own it.
        "capabilities": list(LOCAL_WORKER_CAPABILITIES),
        "instance_id": LOCAL_WORKER_INSTANCE_ID,
        "process_id": int(os.getpid()),
        "started_at_utc": LOCAL_WORKER_STARTED_AT_UTC,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "queue_depth": max(0, int(queue_depth or 0)),
        "last_error": str(last_error or "")[:500],
        "ffmpeg_path": ffmpeg_path,
        "ffprobe_path": find_ffprobe(ffmpeg_path=ffmpeg_path),
        "video_edit_filters_known": video_edit_filters_known,
        "video_edit_filters": video_edit_filters,
        "video_edit_filter_worker_id": LOCAL_WORKER_ID,
        "video_edit_filter_ffmpeg_path": ffmpeg_path,
        "comfy_enabled": LOCAL_COMFY_ENABLED,
    }


def send_heartbeat() -> None:
    payload = local_worker_heartbeat_payload(last_error=LOCAL_WORKER_LAST_ERROR)
    http_json("POST", "/internal/worker/heartbeat", payload, timeout=15)


def run_heartbeat_loop(stop_event: threading.Event, interval_seconds: int = 30) -> None:
    """Publish immediately and keep readiness fresh while FFmpeg is busy."""

    global LOCAL_WORKER_LAST_ERROR
    interval = max(1, int(interval_seconds or 30))
    while not stop_event.is_set():
        try:
            send_heartbeat()
            LOCAL_WORKER_LAST_ERROR = ""
        except urllib.error.HTTPError as exc:
            LOCAL_WORKER_LAST_ERROR = f"heartbeat_http_{exc.code}"
            print(f"[local_worker] heartbeat HTTP {exc.code}")
        except urllib.error.URLError as exc:
            LOCAL_WORKER_LAST_ERROR = f"heartbeat_connection:{type(exc.reason).__name__}"
            print(f"[local_worker] heartbeat connection error: {type(exc.reason).__name__}")
        except Exception as exc:
            LOCAL_WORKER_LAST_ERROR = f"heartbeat_{type(exc).__name__}"
            print(f"[local_worker] heartbeat error: {type(exc).__name__}")
        stop_event.wait(interval)


def poll_job() -> dict | None:
    query = urllib.parse.urlencode({"worker_id": LOCAL_WORKER_ID})
    data = http_json("GET", f"/internal/worker/poll?{query}", timeout=25)
    return data.get("job") if data.get("ok") else None


def poll_video_render_job() -> dict | None:
    query = urllib.parse.urlencode({"worker_id": LOCAL_WORKER_ID, "lease_seconds": LOCAL_WORKER_MAX_JOB_SECONDS})
    data = http_json("GET", f"/internal/video_worker/poll?{query}", timeout=25)
    return data.get("job") if data.get("ok") else None


def update_job(
    job_id,
    status: str,
    error_short: str = "",
    output_url: str = "",
    output_file_id: str = "",
    detail_limit: int = 500,
    output_limit: int = 4000,
    *,
    stage: str | None = None,
    lease_seconds: int | None = None,
) -> None:
    safe_detail_limit = max(
        500,
        min(VIDEO_EDIT_RECEIPT_PAYLOAD_LIMIT, int(detail_limit or 500)),
    )
    safe_output_limit = max(
        1000,
        min(VIDEO_EDIT_RECEIPT_PAYLOAD_LIMIT, int(output_limit or 4000)),
    )
    payload = {
        "job_id": job_id,
        "status": status,
        "worker_id": LOCAL_WORKER_ID,
        "error_short": str(error_short or "")[:safe_detail_limit],
        "output_url": str(output_url or "")[:safe_output_limit],
        "output_file_id": str(output_file_id or "")[:500],
    }
    if stage is not None:
        if not isinstance(stage, str) or stage not in VIDEO_EDIT_WORKER_STAGES:
            raise LocalVideoEditError("video_local_edit_stage_invalid")
        payload["stage"] = stage
    if lease_seconds is not None:
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
            raise LocalVideoEditError("video_local_edit_lease_invalid")
        payload["lease_seconds"] = max(30, min(3600, lease_seconds))
    if stage is not None or lease_seconds is not None:
        http_json(
            "POST",
            "/internal/worker/job_update",
            payload,
            timeout=20,
            total_deadline_seconds=VIDEO_EDIT_LIVENESS_UPDATE_TIMEOUT_SECONDS,
        )
    else:
        http_json("POST", "/internal/worker/job_update", payload, timeout=20)


VIDEO_EDIT_WORKER_STAGES = frozenset({
    "inspecting_input",
    "preparing_plan",
    "processing_video",
    "validating_output",
    "delivering",
    "delivered",
    "failed_no_charge",
    "delivery_unknown",
})

# Liveness updates opt into an absolute HTTP deadline so stop can join any
# in-flight renewal to completion before cleanup and terminal persistence.
VIDEO_EDIT_LIVENESS_UPDATE_TIMEOUT_SECONDS = 20


class _VideoEditJobLiveness:
    def __init__(self, job_id: int | str, lease_seconds: int, interval_seconds: int) -> None:
        job_id_valid = (
            isinstance(job_id, int)
            and not isinstance(job_id, bool)
            and job_id > 0
        ) or (
            isinstance(job_id, str)
            and job_id.strip().isdigit()
            and int(job_id.strip()) > 0
        )
        if not job_id_valid:
            raise LocalVideoEditError("video_local_edit_worker_lease_lost")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
            raise LocalVideoEditError("video_local_edit_worker_lease_lost")
        if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int):
            raise LocalVideoEditError("video_local_edit_worker_lease_lost")
        if not 30 <= lease_seconds <= 3600 or not 1 <= interval_seconds <= 60:
            raise LocalVideoEditError("video_local_edit_worker_lease_lost")
        self._job_id = job_id
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds
        self._stage = "inspecting_input"
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._failure: LocalVideoEditError | None = None
        self._thread: threading.Thread | None = None
        self._closed = False
        self._started = False

    def _capture_failure(self) -> LocalVideoEditError:
        with self._lock:
            if self._failure is None:
                self._failure = LocalVideoEditError("video_local_edit_worker_lease_lost")
            return self._failure

    def _renew(self) -> bool:
        with self._lock:
            if self._closed:
                return False
            stage = self._stage
        try:
            update_job(
                self._job_id,
                "running",
                stage=stage,
                lease_seconds=self._lease_seconds,
            )
        except Exception:
            self._capture_failure()
            return False
        return True

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            if not self._renew():
                return

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise self._failure or LocalVideoEditError("video_local_edit_worker_lease_lost")
            if self._started:
                return
            if not self._renew():
                self._closed = True
                self._stop_event.set()
                raise self._capture_failure()
            try:
                candidate = threading.Thread(target=self._run, daemon=True)
                candidate.start()
            except Exception:
                self._closed = True
                self._stop_event.set()
                raise self._capture_failure() from None
            self._thread = candidate
            self._started = True

    def update_stage(self, stage: str) -> None:
        if not isinstance(stage, str) or stage not in VIDEO_EDIT_WORKER_STAGES:
            raise LocalVideoEditError("video_local_edit_worker_lease_lost")
        with self._lock:
            self._stage = stage

    def assert_healthy(self) -> None:
        with self._lock:
            failure = self._failure
        if failure is not None:
            raise failure

    def stop(self) -> None:
        with self._lock:
            self._closed = True
            self._stop_event.set()
            thread = self._thread if self._started else None
        if thread is not None and thread is not threading.current_thread():
            thread.join()


def video_edit_job_liveness(
    job_id: int | str,
    lease_seconds: int,
    interval_seconds: int,
) -> _VideoEditJobLiveness:
    return _VideoEditJobLiveness(job_id, lease_seconds, interval_seconds)


def update_video_render_job(
    job_id,
    status: str,
    error_short: str = "",
    final_video_path: str = "",
    final_video_file_id: str = "",
    result: dict | None = None,
) -> None:
    safe_result = dict(result or {})
    safe_result.update(local_worker_process_trace())
    payload = {
        "job_id": job_id,
        "status": status,
        "worker_id": LOCAL_WORKER_ID,
        "error_short": str(error_short or "")[:500],
        "final_video_path": str(final_video_path or "")[:1000],
        "final_video_file_id": str(final_video_file_id or "")[:500],
        "result": safe_result,
    }
    http_json("POST", "/internal/video_worker/job_update", payload, timeout=25)


def first_line(text: str) -> str:
    for line in str(text or "").splitlines():
        clean = line.strip()
        if clean:
            return clean[:300]
    return ""


def local_worker_process_trace() -> dict:
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = ""
    return {
        "actual_processor": "local_worker",
        "worker_id": LOCAL_WORKER_ID,
        "worker_service_mode": "local_video_worker",
        "claimed_by_service_mode": "local_video_worker",
        "worker_claim_route": "/internal/video_worker/poll",
        "worker_claim_status": "claimed",
        "worker_claim_reason": "",
        "process_hostname": str(hostname or "")[:160],
        "process_pid": int(os.getpid() or 0),
    }


def local_ffmpeg_path() -> str:
    if LOCAL_FFMPEG_PATH and os.path.exists(LOCAL_FFMPEG_PATH):
        return LOCAL_FFMPEG_PATH
    return shutil.which("ffmpeg") or LOCAL_FFMPEG_PATH


def local_worker_runtime_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        value = str(result.stdout or "").strip()
        if result.returncode == 0 and value:
            return value
    except Exception:
        pass
    for name in (
        "FRAME_VIDEO_WORKER_SHA",
        "RAILWAY_GIT_COMMIT_SHA",
        "GIT_COMMIT_SHA",
        "SOURCE_VERSION",
    ):
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    return "local"


def run_ffmpeg_health(job: dict) -> None:
    job_id = job.get("id")
    if not LOCAL_FFMPEG_PATH:
        update_job(job_id, "failed", "LOCAL_FFMPEG_PATH missing.")
        return
    try:
        result = subprocess.run(
            [LOCAL_FFMPEG_PATH, "-version"],
            capture_output=True,
            text=True,
            timeout=min(LOCAL_WORKER_MAX_JOB_SECONDS, 60),
            check=False,
        )
    except FileNotFoundError:
        update_job(job_id, "failed", "ffmpeg.exe not found at LOCAL_FFMPEG_PATH.")
        return
    except subprocess.TimeoutExpired:
        update_job(job_id, "failed", "ffmpeg health check timed out.")
        return
    except Exception as exc:
        update_job(job_id, "failed", f"ffmpeg health error: {type(exc).__name__}")
        return

    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    line = first_line(combined)
    if result.returncode == 0 and "ffmpeg version" in combined.lower():
        update_job(job_id, "succeeded", line or "ffmpeg version OK")
    else:
        update_job(job_id, "failed", line or f"ffmpeg returned code {result.returncode}")


def telegram_open_no_redirect(request, timeout):
    injected_urlopen = urllib.request.urlopen
    default_urlopen = globals().get("_TELEGRAM_DEFAULT_URLOPEN")
    if default_urlopen is not None and injected_urlopen is not default_urlopen:
        return injected_urlopen(request, timeout=timeout)

    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirectHandler())
    return opener.open(request, timeout=timeout)


_VIDEO_EDIT_TELEGRAM_JSON_MAX_BYTES = 256 * 1024


def _video_edit_telegram_media_config() -> video_edit_media_transport.TelegramMediaConfig:
    raw_media_path = str(
        os.environ.get("TELEGRAM_LOCAL_API_MEDIA_PATH") or "localfile"
    )
    local_media_path = (
        raw_media_path if raw_media_path.startswith("/") else f"/{raw_media_path}"
    )
    return video_edit_media_transport.TelegramMediaConfig(
        token=str(TELEGRAM_BOT_TOKEN or ""),
        api_root=str(
            os.environ.get("TELEGRAM_API_BASE_URL")
            or "https://api.telegram.org"
        ),
        proxy_secret_header=str(
            os.environ.get("TELEGRAM_API_PROXY_SECRET_HEADER")
            or "X-Toanaas-Proxy-Secret"
        ),
        proxy_secret=str(os.environ.get("TELEGRAM_API_PROXY_SECRET") or ""),
        local_file_root=str(
            os.environ.get("TELEGRAM_LOCAL_API_FILE_ROOT")
            or "/var/lib/telegram-bot-api"
        ).rstrip("/"),
        local_media_path=local_media_path,
    )


def _video_edit_bounded_json_response(response, *, reason: str) -> dict:
    try:
        body = response.read(_VIDEO_EDIT_TELEGRAM_JSON_MAX_BYTES + 1)
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError):
        raise RuntimeError(reason) from None
    if (
        not isinstance(body, bytes)
        or not body
        or len(body) > _VIDEO_EDIT_TELEGRAM_JSON_MAX_BYTES
    ):
        raise RuntimeError(reason)
    headers = getattr(response, "headers", None)
    declared_length = headers.get("Content-Length") if headers is not None else None
    if declared_length not in {None, ""}:
        try:
            if int(declared_length) != len(body):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise RuntimeError(reason) from None
    try:
        payload = json.loads(body.decode("utf-8", errors="strict"))
    except (UnicodeError, TypeError, ValueError):
        raise RuntimeError(reason) from None
    if not isinstance(payload, dict):
        raise RuntimeError(reason)
    return payload


def _video_edit_get_file_json(
    *,
    url: str,
    headers: dict,
    follow_redirects: bool,
    **request_fields,
) -> dict:
    if follow_redirects is not False or set(request_fields) != {"json"}:
        raise RuntimeError("telegram_get_file_request_invalid")
    try:
        body = json.dumps(
            request_fields["json"],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            str(url or ""),
            data=body,
            headers={"Content-Type": "application/json", **dict(headers or {})},
            method="POST",
        )
        with telegram_open_no_redirect(request, timeout=30) as response:
            return _video_edit_bounded_json_response(
                response,
                reason="telegram_get_file_response_invalid",
            )
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"telegram_get_file_http_{int(exc.code or 0)}") from None
    except RuntimeError:
        raise
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError, TypeError, ValueError):
        raise RuntimeError("telegram_get_file_network") from None


def _video_edit_stream_bytes(
    *,
    url: str,
    headers: dict,
    follow_redirects: bool,
    chunk_size: int,
):
    if (
        follow_redirects is not False
        or isinstance(chunk_size, bool)
        or not isinstance(chunk_size, int)
        or chunk_size < 1
    ):
        raise RuntimeError("telegram_download_request_invalid")
    bounded_chunk_size = min(
        chunk_size,
        video_edit_media_transport.STREAM_CHUNK_BYTES,
    )
    timeout = max(
        60,
        min(
            7200,
            env_int(
                "VIDEO_EDIT_TELEGRAM_DOWNLOAD_TIMEOUT_SECONDS",
                max(60, LOCAL_WORKER_MAX_JOB_SECONDS),
            ),
        ),
    )
    try:
        request = urllib.request.Request(
            str(url or ""),
            headers=dict(headers or {}),
            method="GET",
        )
        with telegram_open_no_redirect(request, timeout=timeout) as response:
            while True:
                chunk = response.read(bounded_chunk_size)
                if not chunk:
                    break
                if not isinstance(chunk, bytes) or len(chunk) > bounded_chunk_size:
                    raise RuntimeError("telegram_download_chunk_invalid")
                yield chunk
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"telegram_download_http_{int(exc.code or 0)}") from None
    except RuntimeError:
        raise
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError, TypeError, ValueError):
        raise RuntimeError("telegram_download_network") from None


def _video_edit_multipart_request(
    *,
    method_name: str,
    url: str,
    headers: dict,
    content_length: int,
    body,
    follow_redirects: bool,
) -> dict:
    if (
        follow_redirects is not False
        or method_name not in {"sendVideo", "sendDocument"}
        or isinstance(content_length, bool)
        or not isinstance(content_length, int)
        or content_length < 1
    ):
        raise RuntimeError("telegram_delivery_request_invalid")
    request_headers = dict(headers or {})
    if str(request_headers.get("Content-Length") or "") != str(content_length):
        raise RuntimeError("telegram_delivery_request_invalid")
    timeout = max(
        120,
        min(
            7200,
            env_int("VIDEO_EDIT_TELEGRAM_DELIVERY_TIMEOUT_SECONDS", 1800),
        ),
    )
    try:
        request = urllib.request.Request(
            str(url or ""),
            data=body,
            headers=request_headers,
            method="POST",
        )
        with telegram_open_no_redirect(request, timeout=timeout) as response:
            payload = _video_edit_bounded_json_response(
                response,
                reason="telegram_delivery_response_invalid",
            )
        payload["status_code"] = 200
        return payload
    except urllib.error.HTTPError as exc:
        try:
            payload = _video_edit_bounded_json_response(
                exc,
                reason="telegram_delivery_response_invalid",
            )
        finally:
            try:
                exc.close()
            except OSError:
                pass
        payload["status_code"] = int(exc.code or 0)
        if payload.get("ok") is not False:
            raise RuntimeError("telegram_delivery_outcome_uncertain")
        return payload
    except RuntimeError:
        raise
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError, TypeError, ValueError):
        raise RuntimeError("telegram_delivery_outcome_uncertain") from None


def telegram_json(method: str, payload: dict | None = None, timeout: int = 30) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    data = None
    headers = {
        "Content-Type": "application/json",
        **telegram_api_proxy_headers(),
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        telegram_api_method_url(method),
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with telegram_open_no_redirect(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"telegram_api_http_{int(exc.code or 0)}") from None
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError):
        raise RuntimeError("telegram_api_network") from None
    try:
        parsed = json.loads(body or "{}")
    except (TypeError, ValueError):
        raise RuntimeError("telegram_api_invalid_json") from None
    if not isinstance(parsed, dict):
        raise RuntimeError("telegram_api_invalid_json") from None
    return parsed


def telegram_download_file(
    file_id: str,
    destination: str,
    max_bytes: int = 20 * 1024 * 1024,
) -> None:
    data = telegram_json("getFile", {"file_id": file_id}, timeout=30)
    result = data.get("result") if isinstance(data, dict) else {}
    result = result if isinstance(result, dict) else {}
    file_path = str(result.get("file_path") or "").strip()
    if not isinstance(data, dict) or data.get("ok") is not True or not file_path:
        raise RuntimeError("telegram_get_file_failed")
    try:
        url = telegram_file_download_url(file_path)
    except ValueError as exc:
        raise RuntimeError("telegram_file_path_invalid") from exc
    limit = max(1, int(max_bytes or frame_video_telegram_input_limit_bytes()))
    downloaded = 0
    request = urllib.request.Request(url, headers=telegram_api_proxy_headers())
    timeout = max(60, min(7200, env_int("FRAME_VIDEO_TELEGRAM_DOWNLOAD_TIMEOUT_SECONDS", 1800)))

    def remove_partial() -> None:
        try:
            if os.path.exists(destination):
                os.remove(destination)
        except OSError:
            pass

    try:
        with telegram_open_no_redirect(request, timeout=timeout) as response, open(destination, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > limit:
                    raise RuntimeError("telegram_file_too_large")
                handle.write(chunk)
    except RuntimeError:
        remove_partial()
        raise
    except urllib.error.HTTPError as exc:
        remove_partial()
        raise RuntimeError(f"telegram_download_http_{int(exc.code or 0)}") from None
    except (TimeoutError, socket.timeout, urllib.error.URLError):
        remove_partial()
        raise RuntimeError("telegram_download_network") from None
    except OSError:
        remove_partial()
        raise RuntimeError("telegram_download_io") from None
    if downloaded <= 0:
        remove_partial()
        raise RuntimeError("telegram_download_empty")


def download_url_file(url: str, destination: str, max_bytes: int = 50 * 1024 * 1024) -> None:
    clean_url = str(url or "").strip()
    if not clean_url.startswith(("http://", "https://")):
        raise RuntimeError("preview_source_url_invalid")
    downloaded = 0
    request = urllib.request.Request(clean_url, headers={"User-Agent": "TOAN-AAS-Local-Worker/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, open(destination, "wb") as handle:
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            downloaded += len(chunk)
            if downloaded > max_bytes:
                raise RuntimeError("preview_source_too_large")
            handle.write(chunk)
    if downloaded <= 0:
        raise RuntimeError("preview_source_empty")


def ffmpeg_filter(width: int, height: int, seconds: float, effect: str) -> str:
    base = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    effect = str(effect or "fade").lower()
    if effect == "zoom":
        frames = max(45, int(float(seconds or 1.5) * 30))
        return f"{base},zoompan=z='min(zoom+0.0018,1.10)':d={frames}:s={width}x{height}:fps=30,format=yuv420p"
    if effect == "pan":
        return f"{base},crop={width}:{height}:'min(iw-{width},t*8)':0,format=yuv420p"
    return f"{base},format=yuv420p"


def concat_path(path: str) -> str:
    return str(path or "").replace("\\", "/").replace("'", "'\\''")


def run_frame_video_ffmpeg(image_paths: list[str], output_path: str, width: int, height: int, seconds: float, effect: str, timeout: int) -> None:
    if not LOCAL_FFMPEG_PATH or not os.path.exists(LOCAL_FFMPEG_PATH):
        raise RuntimeError("LOCAL_FFMPEG_PATH missing")
    if len(image_paths) < 1:
        raise RuntimeError("not_enough_images")
    clips: list[str] = []
    random_cycle = ["fade", "zoom", "pan", "slide"]
    directory = os.path.dirname(output_path) or tempfile.gettempdir()
    for idx, image_path in enumerate(image_paths, start=1):
        clip_effect = random_cycle[(idx - 1) % len(random_cycle)] if str(effect or "").lower() == "random" else str(effect or "fade").lower()
        if clip_effect == "slide":
            clip_effect = "pan"
        clip_path = os.path.join(directory, f"frame_video_clip_{idx}.mp4")
        cmd = [
            LOCAL_FFMPEG_PATH, "-y",
            "-loop", "1",
            "-t", f"{float(seconds or 1.5):.2f}",
            "-i", image_path,
            "-vf", ffmpeg_filter(width, height, seconds, clip_effect),
            "-r", "30",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            clip_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode != 0 or not os.path.exists(clip_path):
            raise RuntimeError(first_line(result.stderr or result.stdout) or f"ffmpeg_clip_{idx}_failed")
        clips.append(clip_path)
    concat_file = os.path.join(directory, "frame_video_concat.txt")
    with open(concat_file, "w", encoding="utf-8") as handle:
        for clip in clips:
            handle.write(f"file '{concat_path(clip)}'\n")
    result = subprocess.run(
        [LOCAL_FFMPEG_PATH, "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", "-movflags", "+faststart", output_path],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError(first_line(result.stderr or result.stdout) or "ffmpeg_concat_failed")


def telegram_send_video_receipt(
    chat_id: str,
    video_path: str,
    caption: str = "",
    reply_markup: dict | None = None,
    filename: str = "",
    max_bytes: int = 0,
    prefer_document: bool = False,
) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    if not os.path.isfile(video_path) or os.path.getsize(video_path) <= 0:
        raise RuntimeError("telegram_delivery_file_missing")
    video_size = os.path.getsize(video_path)
    output_limit = max(0, int(max_bytes or 0))
    if output_limit and video_size > output_limit:
        raise RuntimeError("telegram_delivery_resource_limit")
    safe_filename = safe_display_filename(filename or os.path.basename(video_path), "toan_aas_video.mp4")
    if not safe_filename.lower().endswith(".mp4"):
        safe_filename = "toan_aas_video.mp4"

    def send(method: str, file_field: str) -> dict:
        boundary = f"----TOANAASLocalWorkerBoundary{method}"
        fields = {"chat_id": str(chat_id or ""), "caption": str(caption or "")[:1000]}
        if reply_markup:
            fields["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        prefix = bytearray()
        for key, value in fields.items():
            prefix.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8"))
        prefix.extend(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
            f"filename=\"{safe_filename}\"\r\nContent-Type: video/mp4\r\n\r\n".encode("utf-8")
        )
        suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")

        def multipart_body_chunks():
            yield bytes(prefix)
            with open(video_path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    yield chunk
            yield suffix

        content_length = len(prefix) + video_size + len(suffix)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(content_length),
            **telegram_api_proxy_headers(),
        }
        request = urllib.request.Request(
            telegram_api_method_url(method),
            data=multipart_body_chunks(),
            headers=headers,
            method="POST",
        )
        timeout = max(
            120,
            min(
                7200,
                env_int("FRAME_VIDEO_TELEGRAM_DELIVERY_TIMEOUT_SECONDS", 1800),
            ),
        )
        try:
            with telegram_open_no_redirect(request, timeout=timeout) as response:
                body = response.read()
            data = json.loads(body.decode("utf-8", errors="replace") or "{}")
        except urllib.error.HTTPError:
            raise
        except (TimeoutError, socket.timeout, urllib.error.URLError, OSError, TypeError, ValueError):
            raise RuntimeError("telegram_delivery_outcome_uncertain") from None
        if not isinstance(data, dict):
            raise RuntimeError("telegram_delivery_outcome_uncertain") from None
        if not data.get("ok"):
            raise RuntimeError("telegram_delivery_rejected") from None
        result = data.get("result") or {}
        media = result.get(file_field) or {} if isinstance(result, dict) else {}
        message_id = str(result.get("message_id") or "") if isinstance(result, dict) else ""
        file_id = str(media.get("file_id") or "") if isinstance(media, dict) else ""
        if not message_id.isdigit() or int(message_id) <= 0 or not file_id:
            raise RuntimeError("telegram_delivery_outcome_uncertain") from None
        return {
            "sent": True,
            "file_id": file_id,
            "message_id": message_id,
            "delivery_method": method,
        }

    initial_method = "sendDocument" if prefer_document else "sendVideo"
    initial_field = "document" if prefer_document else "video"
    try:
        return send(initial_method, initial_field)
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        if not prefer_document and status in {400, 413, 422}:
            # Telegram rejected the video representation before accepting it.
            # A document fallback is therefore deterministic and non-duplicating.
            try:
                return send("sendDocument", "document")
            except urllib.error.HTTPError as fallback_exc:
                fallback_status = int(getattr(fallback_exc, "code", 0) or 0)
                if 400 <= fallback_status < 500:
                    raise RuntimeError("telegram_delivery_rejected") from None
                raise RuntimeError("telegram_delivery_outcome_uncertain") from None
            except (TimeoutError, socket.timeout, urllib.error.URLError, OSError):
                raise RuntimeError("telegram_delivery_outcome_uncertain") from None
        if 400 <= status < 500:
            raise RuntimeError("telegram_delivery_rejected") from None
        # A server-side failure can occur after Telegram accepted the upload.
        # Never issue a second send while delivery truth is uncertain.
        raise RuntimeError("telegram_delivery_outcome_uncertain") from None
    except (TimeoutError, socket.timeout, urllib.error.URLError, OSError):
        # Telegram may have accepted the upload before the connection timed out.
        # Do not issue a second send when delivery truth is uncertain.
        raise RuntimeError("telegram_delivery_outcome_uncertain") from None


def telegram_send_video(
    chat_id: str,
    video_path: str,
    caption: str = "",
    reply_markup: dict | None = None,
    filename: str = "",
) -> str:
    return str(
        telegram_send_video_receipt(
            chat_id,
            video_path,
            caption,
            reply_markup=reply_markup,
            filename=filename,
        ).get("file_id")
        or ""
    )


VIDEO_EDITOR_PRESET_FILTERS = {
    "video_clear": "eq=brightness=0.01:contrast=1.06:saturation=1.06,unsharp=5:5:0.55:5:5:0.0",
    "video_tiktok_pop": "eq=brightness=0.015:contrast=1.10:saturation=1.18,unsharp=5:5:0.65:5:5:0.0",
    "video_cinematic": "eq=brightness=-0.01:contrast=1.13:saturation=0.94:gamma=0.97,unsharp=5:5:0.40:5:5:0.0",
    "video_soft_clean": "eq=brightness=0.02:contrast=0.99:saturation=0.96,unsharp=5:5:0.25:5:5:0.0",
}
VIDEO_EDITOR_RATIO_SIZES = {"9:16": (720, 1280), "16:9": (1280, 720), "1:1": (1080, 1080), "4:5": (864, 1080)}


def ffmpeg_drawtext_escape(value: str) -> str:
    return (
        str(value or "")[:260]
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def video_editor_text_filter(text: str) -> str:
    clean = ffmpeg_drawtext_escape(text)
    if not clean:
        return ""
    font_part = ""
    if LOCAL_FFMPEG_FONT_PATH and os.path.exists(LOCAL_FFMPEG_FONT_PATH):
        font_path = LOCAL_FFMPEG_FONT_PATH.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        font_part = f"fontfile='{font_path}':"
    return (
        f"drawtext={font_part}text='{clean}':fontcolor=white:fontsize=h/22:"
        "borderw=2:bordercolor=black@0.75:box=1:boxcolor=black@0.35:boxborderw=18:"
        "x=(w-text_w)/2:y=h-text_h-h*0.06"
    )


def video_editor_filter(payload: dict) -> tuple[str, bool]:
    preset = str(payload.get("preset") or "video_clear")
    color_filter = VIDEO_EDITOR_PRESET_FILTERS.get(preset, VIDEO_EDITOR_PRESET_FILTERS["video_clear"])
    if payload.get("sharpen") and "unsharp" not in color_filter:
        color_filter += ",unsharp=5:5:0.65:5:5:0.0"
    ratio = str(payload.get("ratio") or "")
    method = str(payload.get("method") or "crop")
    width, height = VIDEO_EDITOR_RATIO_SIZES.get(ratio, (0, 0))
    text_filter = video_editor_text_filter(str(payload.get("overlay_text") or ""))
    tail = ",".join(part for part in [color_filter, text_filter, "format=yuv420p"] if part)
    if width and height and method == "blur":
        complex_filter = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma=28[bg2];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fg2];"
            f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1,{tail}[v]"
        )
        return complex_filter, True
    filters = []
    if width and height:
        filters.append(f"scale={width}:{height}:force_original_aspect_ratio=increase")
        filters.append(f"crop={width}:{height}")
        filters.append("setsar=1")
    filters.append(tail)
    return ",".join(part for part in filters if part), False


def _local1_progress(
    job_id,
    stage: str,
    *,
    processed: int = 0,
    total: int = 1,
    delivered: int = 0,
    detail: str = "",
    artifact_receipts: list[dict] | None = None,
) -> None:
    payload = {
        "local1": 1,
        "stage": str(stage or "processing_video")[:40],
        "processed": max(0, int(processed or 0)),
        "total": max(1, int(total or 1)),
        "delivered": max(0, int(delivered or 0)),
        "detail": first_line(detail)[:120],
        "charge": 0,
    }
    if artifact_receipts is not None:
        payload["artifact_receipts"] = list(artifact_receipts)
    update_job(
        job_id,
        "running",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        detail_limit=VIDEO_EDIT_RECEIPT_PAYLOAD_LIMIT,
    )


def _local1_download_asset(
    file_id: str,
    file_name: str,
    workspace: Path,
    allowed: set[str],
    stem: str,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> str:
    """Preserve the bounded legacy helper used by non-Video-Edit routes."""

    safe_name = validate_extension(file_name, allowed)
    suffix = Path(safe_name).suffix.lower()
    target = workspace / f"{stem}{suffix}"
    telegram_download_file(
        str(file_id or ""),
        str(target),
        max_bytes=max(1, int(max_bytes)),
    )
    enforce_workspace_limit(workspace)
    return str(target)


def _video_edit_download_asset(
    file_id: str,
    file_name: str,
    workspace: Path,
    allowed: set[str],
    stem: str,
    *,
    max_bytes: int | None = None,
    media_config: video_edit_media_transport.TelegramMediaConfig,
) -> str:
    safe_name = validate_extension(file_name, allowed)
    suffix = Path(safe_name).suffix.lower()
    target = workspace / f"{stem}{suffix}"
    config = media_config
    hard_max_bytes = max_bytes
    if hard_max_bytes is None and not config.is_local:
        hard_max_bytes = video_edit_media_transport.SHORT_MEDIA_MAX_BYTES
    try:
        receipt = video_edit_media_transport.download_file_to_path(
            config=config,
            file_id=str(file_id or ""),
            destination=target,
            get_file_json=_video_edit_get_file_json,
            stream_bytes=_video_edit_stream_bytes,
            hard_max_bytes=hard_max_bytes,
            workspace_reserve_bytes=(
                video_edit_long_media.DEFAULT_WORKSPACE_RESERVE_BYTES
            ),
            require_private_parent=True,
        )
    except video_edit_media_transport.MediaTransferError as exc:
        raise LocalVideoEditError(str(exc.reason or "stream_failed")) from exc
    return str(receipt.path)


def _legacy_local1_plan(payload: dict, source_path: str) -> dict:
    plan = default_manual_edit_plan(source_path)
    ratio = str(payload.get("ratio") or "").strip()
    if ratio in {"16:9", "9:16", "1:1", "4:5"}:
        plan["crop_or_fit"] = {"aspect_ratio": ratio, "mode": "fit" if str(payload.get("method") or "") == "blur" else "crop"}
    preset_map = {
        "video_clear": "bright_clear",
        "video_tiktok_pop": "high_contrast",
        "video_cinematic": "light_cinematic",
        "video_soft_clean": "keep",
    }
    plan["color_preset"] = preset_map.get(str(payload.get("preset") or ""), "keep")
    if str(payload.get("overlay_text") or "").strip():
        plan["text_overlay"] = {
            "content": str(payload.get("overlay_text") or "")[:260],
            "position": "bottom",
            "start_ms": 0,
            "end_ms": int(payload.get("source_duration_ms") or 0) or int(payload.get("source_duration") or 0) * 1000,
            "font_size": 42,
            "outline": 2,
            "font_path": LOCAL_FFMPEG_FONT_PATH,
        }
    return plan


def finalize_video_local_cleanup_state(
    *,
    terminal_status: str,
    terminal_detail: dict,
    delivery_receipts: list[dict],
    cleanup: dict,
) -> tuple[str, dict]:
    """Keep receipt ambiguity terminal when workspace cleanup also fails."""

    detail = dict(terminal_detail or {})
    if cleanup.get("ok"):
        return str(terminal_status or "failed"), detail
    reason = str(cleanup.get("reason") or "cleanup_failed")[:120]
    delivery_was_uncertain = str(detail.get("stage") or "").lower() == "delivery_unknown"
    if delivery_receipts or delivery_was_uncertain:
        # A partial or uncertain Telegram delivery must never be rewritten as
        # an ordinary failed job: the receipt cursor is the source of truth and
        # automatic retry would risk duplicate media.  A fully delivered job
        # keeps its delivered stage while recording cleanup failure separately.
        if str(detail.get("stage") or "").lower() != "delivered":
            detail["stage"] = "delivery_unknown"
        detail["cleanup"] = "failed"
        detail["cleanup_reason"] = reason
        return str(terminal_status or "failed"), detail
    return "failed", {
        "local1": 1,
        "stage": "failed_no_charge",
        "reason": reason,
        "charge": 0,
        "charged_xu": 0,
        "cleanup": "failed",
    }


def _video_local_delivery_is_uncertain(reason: str, receipts: list[dict]) -> bool:
    token = str(reason or "").lower()
    return bool(
        receipts
        or "telegram_delivery_outcome_uncertain" in token
        or "telegram_delivery_receipt_invalid" in token
    )


def _strict_video_edit_price(value) -> int:
    if isinstance(value, bool):
        raise LocalVideoEditError("video_local_edit_price_invalid")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        token = value.strip()
        digits = token[1:] if token[:1] in {"+", "-"} else token
        if not digits or not digits.isdigit():
            raise LocalVideoEditError("video_local_edit_price_invalid")
        try:
            parsed = int(token)
        except (TypeError, ValueError, OverflowError) as exc:
            raise LocalVideoEditError("video_local_edit_price_invalid") from exc
    else:
        raise LocalVideoEditError("video_local_edit_price_invalid")
    if parsed < 0:
        raise LocalVideoEditError("video_local_edit_price_invalid")
    return parsed


def run_video_local_edit(job: dict) -> None:
    job_id = job.get("id")
    workspace: Path | None = None
    liveness: _VideoEditJobLiveness | None = None
    terminal_status = "failed"
    terminal_detail = "failed_no_charge"
    output_file_ids: list[str] = []
    terminal_receipt: dict = {}
    delivery_receipts: list[dict] = []
    expected_output_total = 0
    source_video_path = ""
    source_sha256 = ""
    media_lane = ""
    try:
        payload = json.loads(str(job.get("input_file_id") or "") or "{}")
        if not isinstance(payload, dict):
            raise LocalVideoEditError("video_local_edit_contract_missing")
        contract = {
            "local1_contract": (
                isinstance(payload.get("local1_contract"), int)
                and not isinstance(payload.get("local1_contract"), bool)
                and payload.get("local1_contract") == 1
            ),
            "product_type": str(payload.get("product_type") or "") == video_editengine1.PRODUCT_TYPE,
            "engine_route": str(payload.get("engine_route") or "") == video_editengine1.ENGINE_ROUTE,
            "worker_owner": str(payload.get("worker_owner") or "") == video_editengine1.OUTBOX_OWNER,
            "worker_capability": str(payload.get("worker_capability") or "") == video_editengine1.WORKER_CAPABILITY,
        }
        failed_contract = next((name for name, accepted in contract.items() if not accepted), "")
        if failed_contract:
            raise LocalVideoEditError(f"video_local_edit_contract_{failed_contract}")
        source_file_id = str(payload.get("source_file_id") or "")
        chat_id = str(payload.get("chat_id") or "")
        if not source_file_id or not chat_id:
            raise LocalVideoEditError("video_local_edit_missing_input")
        persisted_media_lane = str(payload.get("media_lane") or "").strip()
        if persisted_media_lane in {"short_media", "large_media"}:
            media_lane = persisted_media_lane
        price_xu = _strict_video_edit_price(payload.get("price_xu", 0))
        quoted_price_xu = _strict_video_edit_price(
            payload.get("quoted_price_xu", 0)
        )
        free_edit = price_xu == 0
        requested_mode = str(payload.get("local1_mode") or "").strip().lower()
        if not requested_mode and not free_edit:
            if payload.get("split_ranges") or str(payload.get("split_mode") or "").strip():
                raise LocalVideoEditError("video_local_edit_mode_missing_with_split")
            requested_mode = "manual"
        if requested_mode not in {"manual", "split"}:
            raise LocalVideoEditError("video_local_edit_mode_invalid")
        mode = requested_mode
        submitted_manual_plan = payload.get("manual_edit_plan")
        if mode == "split" and not isinstance(submitted_manual_plan, dict):
            raise LocalVideoEditError("video_local_edit_split_plan_invalid")
        if requested_mode == "manual" and (
            not isinstance(submitted_manual_plan, dict) or not submitted_manual_plan
        ):
            raise LocalVideoEditError("video_local_edit_plan_missing")
        if free_edit:
            if (
                quoted_price_xu != 0
                or str(payload.get("quality_tier_id") or "") != "local-free"
                or str(payload.get("charge_policy") or "") != "free_local_tool"
                or payload.get("provider_call") is not False
            ):
                raise LocalVideoEditError("video_local_edit_free_contract_invalid")
            charge_status = "not_required_free"
            charge_policy = "free_local_tool"
        else:
            if (
                quoted_price_xu != price_xu
                or str(payload.get("quality_tier_id") or "") in {"", "local-free"}
                or str(payload.get("charge_policy") or "") != "after_valid_mp4_delivery"
                or payload.get("provider_call") is not False
            ):
                raise LocalVideoEditError("video_local_edit_paid_contract_invalid")
            charge_status = "pending_post_delivery"
            charge_policy = "after_valid_mp4_delivery"
        charged_xu = 0
        job_user_id = str(job.get("user_id") or "").strip()
        payload_user_id = str(payload.get("user_id") or "").strip()
        if free_edit and (
            not job_user_id
            or payload_user_id != job_user_id
            or not video_editengine1.valid_local_free_rights_confirmation(
                payload.get("rights_confirmation"),
                user_id=job_user_id,
                expected_review_revision=payload.get("state_revision"),
            )
        ):
            raise LocalVideoEditError(
                "video_local_edit_rights_confirmation_invalid"
            )
        if mode == "split":
            source_metadata = dict(payload.get("source_metadata") or {})
            try:
                duration_hint = int(
                    source_metadata.get("duration_ms")
                    or round(float(source_metadata.get("duration") or 0) * 1000)
                )
            except (TypeError, ValueError, OverflowError):
                duration_hint = 0
            if split_plan_has_manual_conflict(
                submitted_manual_plan,
                source_duration_ms=duration_hint,
                concat_sources=payload.get("concat_sources") or [],
                logo_source=payload.get("logo_source") or {},
                subtitle_source=payload.get("subtitle_source") or {},
            ):
                raise LocalVideoEditError(
                    "video_local_edit_split_manual_conflict"
                )
        if mode == "manual":
            if free_edit and "source" in submitted_manual_plan:
                raise LocalVideoEditError(
                    "video_local_edit_legacy_plan_invalid"
                )
            source_metadata = dict(payload.get("source_metadata") or {})
            try:
                duration_hint = int(
                    source_metadata.get("duration_ms")
                    or round(float(source_metadata.get("duration") or 0) * 1000)
                )
            except (TypeError, ValueError, OverflowError):
                duration_hint = 0
            preflight_concat_sources = payload.get("concat_sources") or []
            preflight_logo_source = payload.get("logo_source") or {}
            preflight_subtitle_source = payload.get("subtitle_source") or {}
            if (
                not isinstance(preflight_concat_sources, list)
                or any(
                    not isinstance(item, dict) or not str(item.get("file_id") or "").strip()
                    for item in preflight_concat_sources
                )
                or not isinstance(preflight_logo_source, dict)
                or not isinstance(preflight_subtitle_source, dict)
                or (preflight_logo_source and not str(preflight_logo_source.get("file_id") or "").strip())
                or (preflight_subtitle_source and not str(preflight_subtitle_source.get("file_id") or "").strip())
            ):
                raise LocalVideoEditError("video_local_edit_asset_contract_invalid")
            if free_edit and not manual_plan_assets_match(
                submitted_manual_plan,
                concat_sources=preflight_concat_sources,
                logo_source=preflight_logo_source,
                subtitle_source=preflight_subtitle_source,
            ):
                raise LocalVideoEditError("video_local_edit_asset_contract_invalid")
            asset_operation = bool(
                preflight_concat_sources
                or preflight_logo_source.get("file_id")
                or preflight_subtitle_source.get("file_id")
            )
            if (
                duration_hint > 0
                and not asset_operation
                and not plan_has_effective_operation(
                    submitted_manual_plan,
                    source_duration_ms=duration_hint,
                )
            ):
                raise LocalVideoEditError("video_local_edit_plan_missing")
        ffmpeg = local_ffmpeg_path()
        ffprobe = find_ffprobe(ffmpeg_path=ffmpeg)
        if not ffmpeg or not (os.path.exists(ffmpeg) or shutil.which(ffmpeg)):
            raise LocalVideoEditError("ffmpeg_missing")
        if not ffprobe:
            raise LocalVideoEditError("ffprobe_missing")
        workspace = create_job_workspace(f"job_{job_id}")
        try:
            media_config = _video_edit_telegram_media_config()
        except (TypeError, ValueError):
            raise LocalVideoEditError("invalid_media_transport_config") from None
        lease_seconds = max(30, min(3600, int(LOCAL_WORKER_MAX_JOB_SECONDS)))
        interval_seconds = min(30, max(5, lease_seconds // 3))
        liveness = video_edit_job_liveness(job_id, lease_seconds, interval_seconds)
        liveness.start()
        liveness.update_stage("inspecting_input")
        liveness.assert_healthy()

        def send_video_edit_artifact(
            artifact_path: str | Path,
            caption: str,
        ) -> dict:
            try:
                receipt = video_edit_media_transport.send_artifact_from_path(
                    config=media_config,
                    chat_id=chat_id,
                    artifact=artifact_path,
                    request=_video_edit_multipart_request,
                    caption=caption,
                )
            except video_edit_media_transport.MediaTransferError as exc:
                reason = str(exc.reason or "delivery_unknown")
                if reason == "delivery_unknown":
                    reason = "telegram_delivery_outcome_uncertain"
                elif reason == "delivery_rejected":
                    reason = "telegram_delivery_rejected"
                else:
                    reason = f"telegram_{reason}"
                raise LocalVideoEditError(reason) from exc
            if not isinstance(
                receipt,
                video_edit_media_transport.DeliveryReceipt,
            ):
                raise LocalVideoEditError("telegram_delivery_receipt_invalid")
            return {
                "sent": True,
                "message_id": receipt.message_id,
                "file_id": receipt.file_id,
                "delivery_method": receipt.delivery_method,
                "bytes_sent": receipt.bytes_sent,
                "sha256": receipt.sha256,
            }

        _local1_progress(job_id, "inspecting_input")
        source_path = _video_edit_download_asset(
            source_file_id,
            str(payload.get("source_file_name") or "video.mp4"),
            workspace,
            ALLOWED_SOURCE_EXTENSIONS,
            "source",
            media_config=media_config,
        )
        liveness.assert_healthy()
        downloaded_probe = video_local_validation.probe_video_file(
            source_path,
            ffprobe_path=ffprobe,
        )
        actual_source_size = os.path.getsize(source_path)
        try:
            actual_duration_seconds = float(
                downloaded_probe.get("duration") or 0.0
            )
        except (TypeError, ValueError, OverflowError):
            actual_duration_seconds = 0.0
        actual_media_lane = video_edit_media_transport.select_media_lane(
            duration_seconds=actual_duration_seconds,
            size_bytes=actual_source_size,
        )
        media_lane = (
            "large_media"
            if persisted_media_lane == "large_media"
            or actual_media_lane == "large_media"
            else "short_media"
        )
        downloaded_validation = video_local_validation.validate_source_metadata(
            downloaded_probe,
            file_size=actual_source_size,
            maximum_bytes=0,
            maximum_duration_seconds=0,
        )
        if not downloaded_validation.get("ok"):
            raise LocalVideoEditError(
                str(downloaded_validation.get("reason") or "invalid_video")
            )
        if mode == "split" and split_plan_has_manual_conflict(
            submitted_manual_plan,
            source_duration_ms=int(downloaded_validation.get("duration_ms") or 0),
            concat_sources=payload.get("concat_sources") or [],
            logo_source=payload.get("logo_source") or {},
            subtitle_source=payload.get("subtitle_source") or {},
        ):
            raise LocalVideoEditError(
                "video_local_edit_split_manual_conflict"
            )
        source_sha256 = video_ai_edit_validation.sha256_file(source_path)
        source_video_path = os.path.basename(source_path)
        timeout = min(LOCAL_WORKER_MAX_JOB_SECONDS, max(30, int(payload.get("max_render_seconds") or 600)))
        if mode == "split":
            submitted_ranges = payload.get("split_ranges")
            if not isinstance(submitted_ranges, list) or not submitted_ranges:
                raise LocalVideoEditError("split_plan_empty")
            coverage_required = payload.get("coverage_required", True)
            if not isinstance(coverage_required, bool):
                raise LocalVideoEditError("split_coverage_invalid")
            ranges: list[SplitRange] = []
            try:
                for index, item in enumerate(submitted_ranges, start=1):
                    if not isinstance(item, dict):
                        raise ValueError
                    raw_index = item.get("index", index)
                    raw_start = item.get("start_ms")
                    raw_end = item.get("end_ms")
                    if any(isinstance(value, bool) for value in (raw_index, raw_start, raw_end)):
                        raise ValueError
                    ranges.append(
                        SplitRange(
                            index=int(raw_index),
                            start_ms=int(raw_start),
                            end_ms=int(raw_end),
                        )
                    )
            except (TypeError, ValueError, OverflowError) as exc:
                raise LocalVideoEditError("split_range_invalid") from exc

            def on_split_progress(status: dict) -> None:
                _local1_progress(
                    job_id,
                    str(status.get("stage") or "processing_video"),
                    processed=int(status.get("processed") or 0),
                    total=int(status.get("total") or len(ranges) or 1),
                    delivered=0,
                )

            liveness.update_stage("processing_video")
            liveness.assert_healthy()
            result = execute_split_plan(
                source_path,
                ranges,
                workspace=workspace,
                coverage_required=coverage_required,
                ffmpeg_path=ffmpeg,
                ffprobe_path=ffprobe,
                timeout=timeout,
                progress=on_split_progress,
            )
            liveness.assert_healthy()
            outputs = list(result.get("outputs") or [])
            total = len(outputs)
            expected_output_total = total
            liveness.update_stage("delivering")
            for index, item in enumerate(outputs, start=1):
                output_path = str(item.get("path") or "")
                if not video_editengine1.valid_mp4_delivery_probe(item.get("validation")):
                    raise LocalVideoEditError("output_validation_failed")
                if not delivery_file_allowed(output_path, workspace=workspace):
                    raise LocalVideoEditError("forbidden_delivery_artifact")
                artifact_size = int(os.path.getsize(output_path))
                artifact_sha256 = video_ai_edit_validation.sha256_file(output_path)
                _local1_progress(job_id, "delivering", processed=total, total=total, delivered=index - 1)
                duration_seconds = max(0.0, float(item.get("duration_ms") or 0) / 1000)
                delivery_caption = (
                    f"✅ Phần {index}/{total} · {duration_seconds:.1f} giây · Miễn phí · 0 Xu"
                    if free_edit
                    else f"✅ Phần {index}/{total} · {duration_seconds:.1f} giây · chỉ ghi phí sau khi giao đủ kết quả"
                )
                liveness.assert_healthy()
                delivery = send_video_edit_artifact(
                    output_path,
                    delivery_caption,
                )
                message_id, file_id = video_editengine1.telegram_delivery_identity(delivery)
                if delivery.get("sent") is True and (not message_id or not file_id):
                    raise LocalVideoEditError("telegram_delivery_receipt_invalid")
                if not message_id or not file_id:
                    raise LocalVideoEditError("delivery_receipt_missing")
                output_file_ids.append(file_id)
                delivery_receipts.append({
                    "index": index,
                    "message_id": message_id,
                    "file_id": file_id,
                    "size": artifact_size,
                    "sha256": artifact_sha256,
                    "ffprobe": dict(item.get("validation") or {}),
                })
                _local1_progress(
                    job_id,
                    "delivering",
                    processed=total,
                    total=total,
                    delivered=index,
                    artifact_receipts=delivery_receipts,
                )
                liveness.assert_healthy()
            joined_hashes = "|".join(item["sha256"] for item in delivery_receipts)
            terminal_receipt = {
                "delivery_message_id": str(delivery_receipts[0]["message_id"] if delivery_receipts else ""),
                "delivery_file_id": str(delivery_receipts[0]["file_id"] if delivery_receipts else ""),
                "source_video_path": source_video_path,
                "source_sha256": source_sha256,
                "output_path": ",".join(os.path.basename(str(item.get("path") or "")) for item in outputs),
                "output_size_bytes": sum(int(item["size"]) for item in delivery_receipts),
                "output_sha256": hashlib.sha256(joined_hashes.encode("utf-8")).hexdigest(),
                "ffprobe": dict(delivery_receipts[0].get("ffprobe") or {}) if delivery_receipts else {},
                "output_count": len(delivery_receipts),
                "artifacts": delivery_receipts,
                "charge_policy": charge_policy,
                "charge_status": charge_status,
                "charged_xu": charged_xu,
            }
            terminal_detail = json.dumps({
                "local1": 1,
                "stage": "delivered",
                "operation": "split",
                "processed": total,
                "total": total,
                "delivered": total,
                "validation": "passed",
                "price_xu": price_xu,
                "charge_status": charge_status,
                "charged_xu": charged_xu,
                "cleanup": "done",
            }, ensure_ascii=False, separators=(",", ":"))
        else:
            raw_plan = dict(payload.get("manual_edit_plan") or {})
            if free_edit and "source" in raw_plan:
                raise LocalVideoEditError("video_local_edit_legacy_plan_invalid")
            if "source" in raw_plan:
                # Historic paid payloads carried a path-shaped alias that must
                # never override the freshly downloaded Telegram input.
                raw_plan.pop("source", None)
                if not raw_plan:
                    raise LocalVideoEditError("video_local_edit_plan_missing")
            plan = raw_plan or _legacy_local1_plan(payload, source_path)
            plan["input_video"] = source_path
            duration_hint = int(downloaded_validation.get("duration_ms") or 0)
            if (
                requested_mode == "manual"
                and not raw_plan.get("source")
                and not plan_has_effective_operation(
                    plan,
                    source_duration_ms=duration_hint,
                )
            ):
                raise LocalVideoEditError("video_local_edit_plan_missing")
            submitted_concat_sources = payload.get("concat_sources") or []
            if not isinstance(submitted_concat_sources, list):
                raise LocalVideoEditError("video_local_edit_asset_contract_invalid")
            concat_paths: list[str] = []
            for index, source in enumerate(submitted_concat_sources, start=1):
                if not isinstance(source, dict) or not source.get("file_id"):
                    raise LocalVideoEditError("video_local_edit_asset_contract_invalid")
                concat_paths.append(_video_edit_download_asset(
                    str(source.get("file_id") or ""),
                    str(source.get("file_name") or f"concat_{index}.mp4"),
                    workspace,
                    ALLOWED_SOURCE_EXTENSIONS,
                    f"concat_{index:03d}",
                    media_config=media_config,
                ))
            plan["concat_inputs"] = concat_paths
            if payload.get("logo_source") is not None and not isinstance(payload.get("logo_source"), dict):
                raise LocalVideoEditError("video_local_edit_asset_contract_invalid")
            logo_source = dict(payload.get("logo_source") or {})
            if logo_source and not logo_source.get("file_id"):
                raise LocalVideoEditError("video_local_edit_asset_contract_invalid")
            if logo_source.get("file_id"):
                logo_path = _video_edit_download_asset(
                    str(logo_source.get("file_id") or ""),
                    str(logo_source.get("file_name") or "logo.png"),
                    workspace,
                    ALLOWED_LOGO_EXTENSIONS,
                    "logo",
                    max_bytes=10 * 1024 * 1024,
                    media_config=media_config,
                )
                logo_config = dict(plan.get("logo_overlay") or {})
                logo_config["path"] = logo_path
                plan["logo_overlay"] = logo_config
            if payload.get("subtitle_source") is not None and not isinstance(payload.get("subtitle_source"), dict):
                raise LocalVideoEditError("video_local_edit_asset_contract_invalid")
            subtitle_source = dict(payload.get("subtitle_source") or {})
            if subtitle_source and not subtitle_source.get("file_id"):
                raise LocalVideoEditError("video_local_edit_asset_contract_invalid")
            if subtitle_source.get("file_id"):
                plan["subtitle_file"] = _video_edit_download_asset(
                    str(subtitle_source.get("file_id") or ""),
                    str(subtitle_source.get("file_name") or "subtitle.srt"),
                    workspace,
                    ALLOWED_SUBTITLE_EXTENSIONS,
                    "subtitle",
                    max_bytes=5 * 1024 * 1024,
                    media_config=media_config,
                )
            output_path = workspace / f"toan_aas_video_edit_{job_id}.mp4"

            def on_manual_progress(status: dict) -> None:
                _local1_progress(
                    job_id,
                    str(status.get("stage") or "processing_video"),
                    processed=int(status.get("processed") or 0),
                    total=int(status.get("total") or 1),
                )

            liveness.update_stage("processing_video")
            liveness.assert_healthy()
            result = execute_manual_edit(
                plan,
                output_path=str(output_path),
                workspace=workspace,
                ffmpeg_path=ffmpeg,
                ffprobe_path=ffprobe,
                timeout=timeout,
                progress=on_manual_progress,
            )
            liveness.assert_healthy()
            if not result.get("ok") or not delivery_file_allowed(output_path, workspace=workspace):
                raise LocalVideoEditError("output_validation_failed")
            validation = dict(result.get("validation") or {})
            if not video_editengine1.valid_mp4_delivery_probe(validation):
                raise LocalVideoEditError("output_validation_failed")
            output_size_bytes = int(os.path.getsize(output_path))
            output_sha256 = video_ai_edit_validation.sha256_file(output_path)
            expected_output_total = 1
            _local1_progress(job_id, "delivering", processed=1, total=1)
            liveness.update_stage("delivering")
            delivery_caption = (
                "✅ Video đã chỉnh sửa xong · Miễn phí · 0 Xu."
                if free_edit
                else "✅ Video đã chỉnh sửa xong. Hệ thống chỉ ghi phí sau khi giao file MP4 hợp lệ."
            )
            liveness.assert_healthy()
            delivery = send_video_edit_artifact(
                output_path,
                delivery_caption,
            )
            message_id, file_id = video_editengine1.telegram_delivery_identity(delivery)
            if delivery.get("sent") is True and (not message_id or not file_id):
                raise LocalVideoEditError("telegram_delivery_receipt_invalid")
            if not message_id or not file_id:
                raise LocalVideoEditError("delivery_receipt_missing")
            delivery_receipts.append({
                "index": 1,
                "message_id": message_id,
                "file_id": file_id,
                "size": output_size_bytes,
                "sha256": output_sha256,
                "ffprobe": validation,
            })
            output_file_ids.append(file_id)
            liveness.assert_healthy()
            terminal_receipt = {
                "delivery_message_id": message_id,
                "delivery_file_id": file_id,
                "source_video_path": source_video_path,
                "source_sha256": source_sha256,
                "output_path": output_path.name,
                "output_size_bytes": output_size_bytes,
                "output_sha256": output_sha256,
                "ffprobe": validation,
                "output_count": 1,
                "charge_policy": charge_policy,
                "charge_status": charge_status,
                "charged_xu": charged_xu,
            }
            terminal_detail = json.dumps({
                "local1": 1,
                "stage": "delivered",
                "operation": "manual",
                "processed": 1,
                "total": 1,
                "delivered": 1,
                "validation": "passed",
                "price_xu": price_xu,
                "charge_status": charge_status,
                "charged_xu": charged_xu,
                "cleanup": "done",
            }, ensure_ascii=False, separators=(",", ":"))
        liveness.stop()
        liveness.assert_healthy()
        terminal_status = "succeeded"
    except (LocalVideoEditError, LocalVideoValidationError) as exc:
        failure_reason = str(getattr(exc, "reason", str(exc)))[:160]
        if delivery_receipts:
            joined_hashes = "|".join(item["sha256"] for item in delivery_receipts)
            terminal_receipt = {
                "delivery_message_id": str(delivery_receipts[0]["message_id"]),
                "delivery_file_id": str(delivery_receipts[0]["file_id"]),
                "source_video_path": source_video_path,
                "source_sha256": source_sha256,
                "output_size_bytes": sum(int(item["size"]) for item in delivery_receipts),
                "output_sha256": hashlib.sha256(joined_hashes.encode("utf-8")).hexdigest(),
                "ffprobe": dict(delivery_receipts[0].get("ffprobe") or {}),
                "output_count": expected_output_total,
                "artifacts": delivery_receipts,
            }
            terminal_detail = json.dumps({
                "local1": 1,
                "stage": "delivery_unknown",
                "reason": failure_reason,
                "delivered": len(delivery_receipts),
                "total": expected_output_total,
                "charge": 0,
                "cleanup": "done",
            }, ensure_ascii=False, separators=(",", ":"))
        if _video_local_delivery_is_uncertain(failure_reason, delivery_receipts):
            terminal_detail = json.dumps({
                "local1": 1,
                "stage": "delivery_unknown",
                "reason": failure_reason,
                "delivered": len(delivery_receipts),
                "total": expected_output_total,
                "charge": 0,
                "cleanup": "done",
            }, ensure_ascii=False, separators=(",", ":"))
        else:
            terminal_detail = json.dumps({
                "local1": 1,
                "stage": "failed_no_charge",
                "reason": failure_reason,
                "charge": 0,
                "charged_xu": 0,
                "cleanup": "done",
            }, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        raw_failure_reason = first_line(str(exc))
        failure_reason = (
            raw_failure_reason
            if raw_failure_reason.startswith("telegram_delivery_")
            else f"{type(exc).__name__}:{raw_failure_reason}"
        )[:160]
        if delivery_receipts:
            joined_hashes = "|".join(item["sha256"] for item in delivery_receipts)
            terminal_receipt = {
                "delivery_message_id": str(delivery_receipts[0]["message_id"]),
                "delivery_file_id": str(delivery_receipts[0]["file_id"]),
                "source_video_path": source_video_path,
                "source_sha256": source_sha256,
                "output_size_bytes": sum(int(item["size"]) for item in delivery_receipts),
                "output_sha256": hashlib.sha256(joined_hashes.encode("utf-8")).hexdigest(),
                "ffprobe": dict(delivery_receipts[0].get("ffprobe") or {}),
                "output_count": expected_output_total,
                "artifacts": delivery_receipts,
            }
            terminal_detail = json.dumps({
                "local1": 1,
                "stage": "delivery_unknown",
                "reason": failure_reason,
                "delivered": len(delivery_receipts),
                "total": expected_output_total,
                "charge": 0,
                "cleanup": "done",
            }, ensure_ascii=False, separators=(",", ":"))
        if _video_local_delivery_is_uncertain(failure_reason, delivery_receipts):
            terminal_detail = json.dumps({
                "local1": 1,
                "stage": "delivery_unknown",
                "reason": failure_reason,
                "delivered": len(delivery_receipts),
                "total": expected_output_total,
                "charge": 0,
                "cleanup": "done",
            }, ensure_ascii=False, separators=(",", ":"))
        else:
            terminal_detail = json.dumps({
                "local1": 1,
                "stage": "failed_no_charge",
                "reason": failure_reason,
                "charge": 0,
                "charged_xu": 0,
                "cleanup": "done",
            }, ensure_ascii=False, separators=(",", ":"))
    finally:
        if liveness is not None:
            liveness.stop()
        cleanup = cleanup_job_workspace(workspace) if workspace else {"ok": True, "removed": False}
        try:
            detail_payload = json.loads(terminal_detail or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            detail_payload = {
                "local1": 1,
                "stage": "failed_no_charge",
                "charge": 0,
                "charged_xu": 0,
            }
        terminal_status, detail_payload = finalize_video_local_cleanup_state(
            terminal_status=terminal_status,
            terminal_detail=detail_payload,
            delivery_receipts=delivery_receipts,
            cleanup=cleanup,
        )
        if media_lane in {"short_media", "large_media"}:
            detail_payload["media_lane"] = media_lane
            if terminal_receipt:
                terminal_receipt["media_lane"] = media_lane
        terminal_detail = json.dumps(detail_payload, ensure_ascii=False, separators=(",", ":"))
        update_job(
            job_id,
            terminal_status,
            terminal_detail,
            output_file_id=next((item for item in output_file_ids if item), "")[:500],
            output_url=json.dumps(terminal_receipt, ensure_ascii=False, separators=(",", ":")) if terminal_receipt else "",
            detail_limit=4000,
            output_limit=VIDEO_EDIT_RECEIPT_PAYLOAD_LIMIT,
        )


def _aiedit_progress(job_id, stage: str, **fields) -> None:
    payload = {"aiedit1": 1, "stage": stage, **fields}
    update_job(
        job_id,
        "running",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        detail_limit=4000,
    )


def _aiedit_local_plan(payload: dict, source_path: str) -> dict:
    raw = dict(payload.get("local_preprocess_plan") or {})
    plan = default_manual_edit_plan(source_path)
    plan["input_video"] = source_path
    metadata = dict(payload.get("source_metadata") or {})
    plan["trim"] = {
        "start_ms": 0,
        "end_ms": int(metadata.get("duration_ms") or int(float(metadata.get("duration") or 0) * 1000)),
    }
    crop = dict(plan.get("crop_or_fit") or {})
    target_aspect = str(raw.get("crop_or_fit", {}).get("aspect_ratio") or payload.get("target_aspect_ratio") or "keep")
    crop.update({"aspect_ratio": target_aspect, "mode": str(raw.get("crop_or_fit", {}).get("mode") or "fit")})
    plan["crop_or_fit"] = crop
    plan["color_preset"] = str(raw.get("color_preset") or "keep")
    plan["quality_filters"] = {
        "sharpen": bool(raw.get("sharpen")),
        "denoise": bool(raw.get("denoise")),
    }
    plan["audio_normalization"] = "loudnorm" if bool(raw.get("audio_normalize")) else "off"
    return plan


def _aiedit_ready_provider_configs(payload: dict) -> list:
    requested = str(payload.get("provider_name") or "").strip()
    configs = [
        item
        for item in video_ai_edit_provider.configured_provider_chain(os.environ)
        if video_ai_edit_provider.validate_provider_config(item).get("ok")
    ]
    if requested:
        configs.sort(key=lambda item: 0 if item.provider_name == requested else 1)
    return configs


def _aiedit_submit_and_wait(job_id, payload: dict, config, source_path: str) -> dict:
    _aiedit_progress(job_id, "submitting_edit", provider_status="submitting", poll_count=0)
    submitted = video_ai_edit_provider.submit_video_edit(
        config,
        source_video_path=source_path,
        prompt=str(payload.get("professional_prompt") or ""),
        negative_prompt=str(payload.get("negative_prompt") or ""),
        aspect_ratio=str(payload.get("target_aspect_ratio") or "9:16"),
        duration_seconds=int(payload.get("target_duration_seconds") or 0),
        job_id=str(job_id),
        submit_source=str(payload.get("submit_source") or ""),
        public_user_confirmed=bool(payload.get("public_user_confirmed")),
    )
    task_id = str(submitted.get("provider_task_id") or "")
    if submitted.get("result_url_present"):
        return {**submitted, "poll_count": 0}

    def on_poll(status: dict) -> None:
        _aiedit_progress(
            job_id,
            "ai_processing",
            provider_task_id=task_id,
            provider_status=str(status.get("status") or "running"),
            poll_count=int(status.get("poll_count") or 0),
            result_url_present=bool(status.get("result_url_present")),
        )

    return video_ai_edit_provider.wait_for_result(
        config,
        task_id,
        progress=on_poll,
    )


def run_video_ai_edit(job: dict) -> None:
    """Execute one confirmed AI edit without touching Product Video workers."""
    job_id = job.get("id")
    workspace: Path | None = None
    terminal_status = "failed"
    terminal: dict = {
        "aiedit1": 1,
        "stage": "failed_no_charge",
        "reason": "ai_edit_worker_failed",
        "charge": 0,
        "charge_status": "not_charged",
        "cleanup": "pending",
    }
    output_file_id = ""
    result_url = ""
    try:
        payload = json.loads(str(job.get("input_file_id") or "") or "{}")
        if not isinstance(payload, dict) or not payload.get("aiedit1_contract"):
            raise video_ai_edit_validation.AiEditValidationError("ai_edit_contract_missing")
        lane = str(payload.get("execution_lane") or "local").strip().lower()
        policy = video_ai_edit_provider.submit_source_policy(
            str(payload.get("submit_source") or ""),
            public_user_confirmed=bool(payload.get("public_user_confirmed")),
            lane=lane,
            env=os.environ,
        )
        if not policy.get("allowed"):
            raise video_ai_edit_provider.AiEditProviderError(str(policy.get("reason") or "ai_edit_submit_blocked"))
        source_file_id = str(payload.get("source_file_id") or "")
        chat_id = str(payload.get("chat_id") or "")
        if not source_file_id or not chat_id:
            raise video_ai_edit_validation.AiEditValidationError("ai_edit_missing_input")
        ffmpeg = local_ffmpeg_path()
        ffprobe = find_ffprobe(ffmpeg_path=ffmpeg)
        if not ffmpeg or not (os.path.exists(ffmpeg) or shutil.which(ffmpeg)):
            raise video_ai_edit_validation.AiEditValidationError("ffmpeg_missing")
        if not ffprobe:
            raise video_ai_edit_validation.AiEditValidationError("ffprobe_missing")
        workspace = create_job_workspace(f"aiedit_{job_id}")
        _aiedit_progress(job_id, "inspecting_video", charge=0)
        source_path = _local1_download_asset(
            source_file_id,
            str(payload.get("source_file_name") or "source.mp4"),
            workspace,
            ALLOWED_SOURCE_EXTENSIONS,
            "source",
            max_bytes=video_ai_edit_validation.ai_edit_limits(os.environ)["upload_limit_bytes"],
        )
        source_probe = video_local_validation.probe_video_file(source_path, ffprobe_path=ffprobe)
        source_validation = video_ai_edit_validation.validate_input_metadata(
            source_probe,
            file_size=os.path.getsize(source_path),
            lane=lane,
            target_duration_seconds=int(payload.get("target_duration_seconds") or 0),
            env=os.environ,
        )
        if not source_validation.get("ok"):
            raise video_ai_edit_validation.AiEditValidationError(str(source_validation.get("reason") or "invalid_video"))
        _aiedit_progress(job_id, "preparing_style", charge=0)
        output_path = workspace / video_ai_edit_validation.safe_output_name(job_id)
        provider_name = "local_ffmpeg"
        model = "local_enhancement"
        poll_count = 0
        provider_task_id = ""
        fallback_count = 0
        if lane == "local":
            plan = _aiedit_local_plan(payload, source_path)
            result = execute_manual_edit(
                plan,
                output_path=str(output_path),
                workspace=workspace,
                ffmpeg_path=ffmpeg,
                ffprobe_path=ffprobe,
                timeout=min(LOCAL_WORKER_MAX_JOB_SECONDS, int(payload.get("max_render_seconds") or 600)),
                progress=lambda status: _aiedit_progress(
                    job_id,
                    "ai_processing",
                    provider_status="local_processing",
                    local_processed=int(status.get("processed") or 0),
                    local_total=max(1, int(status.get("total") or 1)),
                ),
            )
            if not result.get("ok"):
                raise video_ai_edit_validation.AiEditValidationError("local_enhancement_failed")
        else:
            ready = _aiedit_ready_provider_configs(payload)
            if not ready:
                raise video_ai_edit_provider.AiEditProviderError("ai_edit_video_to_video_provider_unavailable")
            preprocessed_path = workspace / "provider_input.mp4"
            video_ai_edit_validation.preprocess_source_video(
                source_path,
                str(preprocessed_path),
                workspace=workspace,
                ffmpeg_path=ffmpeg,
                ffprobe_path=ffprobe,
                target_duration_seconds=int(payload.get("target_duration_seconds") or 0),
                preserve_audio=bool(payload.get("preserve_source_audio", True)),
                env=os.environ,
                timeout=min(LOCAL_WORKER_MAX_JOB_SECONDS, int(payload.get("max_render_seconds") or 600)),
            )
            primary = ready[0]
            provider_name, model = primary.provider_name, primary.model
            try:
                provider_result = _aiedit_submit_and_wait(job_id, payload, primary, str(preprocessed_path))
            except video_ai_edit_provider.AiEditProviderError as primary_error:
                fallback = ready[1] if len(ready) > 1 else None
                decision = video_ai_edit_provider.controlled_fallback_decision(
                    public_confirm_provenance=bool(payload.get("public_user_confirmed")),
                    primary_status="failed" if primary_error.reason not in {"provider_poll_timeout"} else "timeout_waiting",
                    primary_task_alive=False,
                    fallback_count=0,
                    candidate=fallback,
                )
                if not decision.get("allowed"):
                    raise
                fallback_count = 1
                provider_name, model = fallback.provider_name, fallback.model
                provider_result = _aiedit_submit_and_wait(job_id, payload, fallback, str(preprocessed_path))
            provider_task_id = str(provider_result.get("provider_task_id") or "")
            poll_count = int(provider_result.get("poll_count") or 0)
            result_url = str(provider_result.get("result_url") or "")
            if not result_url:
                raise video_ai_edit_provider.AiEditProviderError("provider_result_url_missing")
            _aiedit_progress(
                job_id,
                "downloading_result",
                provider_task_id=provider_task_id,
                provider_status="completed",
                poll_count=poll_count,
                result_url_present=True,
            )
            video_ai_edit_provider.download_result(result_url, str(output_path))
        _aiedit_progress(
            job_id,
            "validating_result",
            provider_task_id=provider_task_id,
            provider_status="completed" if lane == "generative" else "local_completed",
            poll_count=poll_count,
            result_url_present=bool(result_url),
        )
        validation = video_ai_edit_validation.validate_final_edited_mp4(
            output_path,
            source_path=source_path,
            workspace=workspace,
            requested_duration_seconds=int(payload.get("target_duration_seconds") or 0),
            ffprobe_path=ffprobe,
        )
        if not validation.get("ok"):
            raise video_ai_edit_validation.AiEditValidationError(str(validation.get("reason") or "output_validation_failed"))
        _aiedit_progress(
            job_id,
            "delivering_result",
            provider_task_id=provider_task_id,
            provider_status="completed",
            poll_count=poll_count,
            result_url_present=bool(result_url),
            validation="passed",
        )
        receipt = telegram_send_video_receipt(
            chat_id,
            str(output_path),
            "✅ Video đã chỉnh sửa xong. Hệ thống chỉ ghi phí sau khi gửi kết quả hợp lệ.",
            filename=output_path.name,
        )
        if not receipt.get("sent") or not receipt.get("file_id") or not receipt.get("message_id"):
            raise video_ai_edit_validation.AiEditValidationError("delivery_failed")
        output_file_id = str(receipt.get("file_id") or "")
        terminal_status = "succeeded"
        terminal = {
            "aiedit1": 1,
            "stage": "delivered",
            "lane": lane,
            "provider": provider_name,
            "model": model,
            "provider_task_id": provider_task_id,
            "provider_status": "completed",
            "poll_count": poll_count,
            "fallback_count": fallback_count,
            "result_url_present": bool(result_url),
            "validation": "passed",
            "artifact_size": int(validation.get("artifact_size") or 0),
            "delivery": "sent",
            "delivery_message_id": str(receipt.get("message_id") or ""),
            "charge": 0,
            "charge_status": "pending_post_delivery" if int(payload.get("price_xu") or 0) > 0 else "free_local_tool",
            "cleanup": "pending",
        }
    except (video_ai_edit_provider.AiEditProviderError, video_ai_edit_validation.AiEditValidationError) as exc:
        terminal["reason"] = str(getattr(exc, "reason", str(exc)))[:160]
    except Exception as exc:
        terminal["reason"] = f"{type(exc).__name__}:{first_line(str(exc))}"[:160]
    finally:
        cleanup = cleanup_job_workspace(workspace) if workspace else {"ok": True, "removed": False}
        terminal["cleanup"] = "done" if cleanup.get("ok") else "failed"
        if not cleanup.get("ok") and terminal_status != "succeeded":
            terminal["reason"] = str(cleanup.get("reason") or terminal.get("reason") or "cleanup_failed")[:160]
        update_job(
            job_id,
            terminal_status,
            json.dumps(terminal, ensure_ascii=False, separators=(",", ":")),
            output_url=result_url,
            output_file_id=output_file_id,
            detail_limit=4000,
        )


def run_social_link_import(job: dict) -> None:
    job_id = job.get("id")
    try:
        from yt_dlp import YoutubeDL

        payload = json.loads(str(job.get("input_file_id") or "") or "{}")
        source_url = str(payload.get("source_url") or "").strip()
        chat_id = str(payload.get("chat_id") or "").strip()
        if not source_url.startswith(("http://", "https://")) or not chat_id:
            update_job(job_id, "failed", "social_link_import_invalid_input")
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, "toan_aas_social_%(id)s.%(ext)s")
            options = {
                "format": "bestvideo[filesize<45M]+bestaudio/best[filesize<45M]/best",
                "outtmpl": output_template,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 45,
                "retries": 2,
                "fragment_retries": 2,
                "max_filesize": 45 * 1024 * 1024,
                "merge_output_format": "mp4",
            }
            with YoutubeDL(options) as downloader:
                info = downloader.extract_info(source_url, download=True)
                if not info or info.get("is_live"):
                    raise RuntimeError("social_link_import_unsupported_live")
                duration = int(info.get("duration") or 0)
                if duration and duration > 60 * 30:
                    raise RuntimeError("social_link_import_duration_too_long")
                output_path = downloader.prepare_filename(info)
                merged_path = os.path.splitext(output_path)[0] + ".mp4"
                if os.path.exists(merged_path):
                    output_path = merged_path
            if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                raise RuntimeError("social_link_import_empty")
            if os.path.getsize(output_path) > 50 * 1024 * 1024:
                raise RuntimeError("social_link_import_too_large")
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "👁 Tạo phụ đề", "callback_data": "videodub|type|subtitle_create"},
                        {"text": "🌐 Dịch phụ đề", "callback_data": "videodub|type|subtitle_translate"},
                    ],
                    [
                        {"text": "🗣 Lồng tiếng tự động", "callback_data": "videodub|type|dub"},
                        {"text": "🎬 Dịch + lồng tiếng tự động", "callback_data": "videodub|type|subtitle_plus_dub"},
                    ],
                    [
                        {"text": "📂 Lưu vào Media", "callback_data": "videodub|source_media"},
                        {"text": "🏠 Menu chính", "callback_data": "menu|main"},
                    ],
                ]
            }
            output_file_id = telegram_send_video(
                chat_id,
                output_path,
                "✅ Đã tải video thành công.\nPhí tải link: 10 Xu.\n\nBạn muốn làm gì tiếp?",
                reply_markup=reply_markup,
            )
        update_job(job_id, "succeeded", "social link imported", output_file_id=output_file_id)
    except Exception as exc:
        update_job(job_id, "failed", f"social_link_import:{type(exc).__name__}:{first_line(str(exc))}")


def video_project_fake_scene_renderer(duration: float = 6.0):
    colors = ["0x1E88E5", "0x43A047", "0xF4511E", "0x8E24AA", "0xFDD835"]

    def _render(scene: SceneSpec, output_path: str) -> str:
        ffmpeg = local_ffmpeg_path()
        if not ffmpeg:
            raise RuntimeError("ffmpeg_missing")
        color = colors[(int(scene.scene_id) - 1) % len(colors)]
        command = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=540x960:r=30:d={float(duration):.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ]
        result = safe_run_ffmpeg(command, timeout=min(LOCAL_WORKER_MAX_JOB_SECONDS, 120))
        if result.returncode != 0:
            raise RuntimeError(first_line(result.stderr or result.stdout) or "fake_renderer_ffmpeg_failed")
        return ensure_video_output(output_path)

    return _render


def video_project_render_mode(job: dict | None = None) -> str:
    data = dict(job or {})
    project = dict(data.get("project") or {})
    asset_pack_json = project.get("asset_pack_json") or data.get("asset_pack_json") or ""
    try:
        asset_pack_from_json = json.loads(str(asset_pack_json or "{}"))
    except Exception:
        asset_pack_from_json = {}
    candidates = [
        data.get("render_mode"),
        (project.get("asset_pack") or {}).get("render_mode") if isinstance(project.get("asset_pack"), dict) else "",
        asset_pack_from_json.get("render_mode") if isinstance(asset_pack_from_json, dict) else "",
    ]
    for value in candidates:
        mode = str(value or "").strip().lower().replace("-", "_")
        if mode in {"admin_test_pattern", "test_pattern", "admin_test"}:
            return RENDER_MODE_ADMIN_TEST_PATTERN
    return RENDER_MODE_REAL


def local_admin_test_pattern_allowed(job: dict | None = None) -> bool:
    data = dict(job or {})
    project = dict(data.get("project") or {})
    asset_pack = {}
    invoice = {}
    for source_key, target in (("asset_pack_json", "asset"), ("invoice_json", "invoice")):
        try:
            parsed = json.loads(str(project.get(source_key) or data.get(source_key) or "{}"))
        except Exception:
            parsed = {}
        if isinstance(parsed, dict) and target == "asset":
            asset_pack = parsed
        elif isinstance(parsed, dict):
            invoice = parsed
    source = str(data.get("source") or asset_pack.get("source") or invoice.get("source") or "")
    return bool(
        source == REMOTE_WORKER_ADMIN_VIDEO_SOURCE
        and (data.get("admin_video_delivery") or asset_pack.get("admin_video_delivery") or invoice.get("admin_video_delivery"))
        and (data.get("admin_only") or asset_pack.get("admin_only") or invoice.get("admin_only"))
        and (data.get("no_charge") or asset_pack.get("no_charge") or invoice.get("no_charge"))
        and not (data.get("provider_call") or asset_pack.get("provider_call") or invoice.get("provider_call"))
        and not (data.get("public_user") or asset_pack.get("public_user") or invoice.get("public_user"))
    )


def video_project_addon_plan(job: dict | None = None) -> dict:
    data = dict(job or {})
    project = dict(data.get("project") or {})
    for candidate in (data.get("addon_plan"), data.get("addon_plan_json"), project.get("addon_plan_json")):
        if isinstance(candidate, dict):
            return dict(candidate)
        try:
            parsed = json.loads(str(candidate or "{}"))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def video_project_real_scene_renderer(job: dict | None = None):
    try:
        return build_real_scene_renderer(job or {})
    except Exception as exc:
        raise RuntimeError(f"{REAL_VIDEO_RENDER_UNAVAILABLE}:connector_failed:{type(exc).__name__}") from exc


def prepare_product_video_public_seam_job(
    job: dict | None = None,
    *,
    environ: dict | None = None,
) -> dict:
    data = dict(job or {})
    is_product_video = (
        product_video_public_seam.product_video_public_seam_applies_to_worker_job(
            data
        )
    )
    if not is_product_video or data.get("admin_video_delivery"):
        return data
    return product_video_public_seam.prepare_product_video_worker_job(
        data,
        environ=os.environ if environ is None else environ,
    )


def run_video_render_job(job: dict) -> None:
    job_id = job.get("id") or job.get("job_id")
    try:
        if not job_id:
            return
        try:
            job = prepare_product_video_public_seam_job(job)
        except RuntimeError as exc:
            update_video_render_job(job_id, "failed", str(exc))
            return
        project = job.get("project") or {}
        if not TELEGRAM_BOT_TOKEN:
            update_video_render_job(job_id, "failed", "telegram_token_missing_for_delivery")
            return
        user_id = str(project.get("user_id") or job.get("user_id") or "").strip()
        if not user_id:
            update_video_render_job(job_id, "failed", "video_render_missing_user")
            return
        scene_count = max(
            1,
            min(
                20,
                int(
                    job.get("scene_count")
                    or project.get("scene_count")
                    or len(job.get("scenes") or [])
                    or 1
                ),
            ),
        )
        duration = float(product_video_scene_duration_seconds({**job, "project": project}))
        prompt = original_prompt_from_job(job)[:4000]
        addon_plan = video_project_addon_plan(job)
        mode = video_project_render_mode(job)
        if mode == RENDER_MODE_ADMIN_TEST_PATTERN:
            if not local_admin_test_pattern_allowed(job):
                update_video_render_job(job_id, "failed", "unsafe_test_pattern_route")
                return
            if not LOCAL_VIDEO_FAKE_RENDERER_ENABLED:
                update_video_render_job(job_id, "failed", "admin_test_pattern_renderer_disabled")
                return
            render_func = video_project_fake_scene_renderer(duration)
            send_caption = "ADMIN TEST PATTERN — video test kỹ thuật, không phải video dựng thật."
            result_mode = RENDER_MODE_ADMIN_TEST_PATTERN
        else:
            try:
                render_func = video_project_real_scene_renderer(job)
            except RuntimeError as exc:
                update_video_render_job(job_id, "failed", str(exc) or REAL_VIDEO_RENDER_UNAVAILABLE)
                return
            send_caption = "✅ Video đã dựng xong. TOAN AAS gửi file kết quả cuối."
            result_mode = RENDER_MODE_REAL
        workspace = create_multiscene_workspace(f"video-project-{job_id}")
        logo_material = product_video_logo_material(job)
        logo_path = str(logo_material.get("logo_path") or "").strip()
        if logo_material.get("logo_enabled") and not logo_path and logo_material.get("logo_file_id"):
            logo_path = os.path.join(workspace, "product_logo.png")
            telegram_download_file(str(logo_material.get("logo_file_id") or ""), logo_path, max_bytes=10 * 1024 * 1024)
        watermark = {}
        asset_pack = project.get("asset_pack_json") or job.get("asset_pack") or "{}"
        try:
            parsed_asset_pack = json.loads(str(asset_pack or "{}"))
            if isinstance(parsed_asset_pack, dict):
                watermark = dict(parsed_asset_pack.get("watermark_config") or {})
        except Exception:
            watermark = {}
        logo_text = str(
            addon_plan.get("logo_text")
            or watermark.get("text")
            or ""
        ).strip()[:240]
        logo_position = str(
            logo_material.get("logo_position")
            or addon_plan.get("logo_position")
            or watermark.get("position")
            or "bottom_right"
        )
        logo_enabled = bool(logo_path or (addon_plan.get("logo_enabled") and logo_text) or watermark.get("enabled") and logo_text)
        def _execute_pipeline(prepared: dict, routed_scene_count: int):
            return process_multiscene_video_pipeline(
                user_id=user_id,
                job_id=str(job_id),
                user_prompt=prompt,
                workspace_dir=workspace,
                render_video_func=render_func,
                llm_func=real_video_llm_func_from_job(prepared),
                max_scenes=routed_scene_count,
                default_scene_duration=duration,
                aspect_ratio=str(project.get("ratio") or "9:16"),
                enable_voice=False,
                enable_subtitle=bool(addon_plan.get("subtitle_enabled", True)),
                logo_path=logo_path or None,
                enable_logo=logo_enabled,
                logo_text=logo_text,
                logo_position=logo_position,
            )

        result = product_video_public_seam.execute_product_video_worker_route(
            job,
            environ=os.environ,
            one_scene_executor=lambda prepared: _execute_pipeline(prepared, 1),
            multiscene_executor=lambda prepared: _execute_pipeline(
                prepared,
                scene_count,
            ),
            legacy_executor=lambda prepared: _execute_pipeline(
                prepared,
                scene_count,
            ),
        )
        final_path = str(result.get("final_video_path") or "")
        if not result.get("ok") or not final_path:
            raise RuntimeError(str(result.get("error") or result.get("status") or "video_render_failed"))
        result["render_mode"] = result_mode
        result["test_pattern"] = result_mode == RENDER_MODE_ADMIN_TEST_PATTERN
        delivery = telegram_send_video_receipt(
            user_id,
            final_path,
            send_caption,
            filename=os.path.basename(final_path) or "toan_aas_video.mp4",
        )
        if not delivery.get("sent") or not delivery.get("message_id") or not delivery.get("file_id"):
            raise RuntimeError("product_video_delivery_receipt_missing")
        result.update(
            {
                "delivery_succeeded": True,
                "delivery_message_id": str(delivery.get("message_id") or ""),
                "telegram_delivery_message_id": str(delivery.get("message_id") or ""),
                "delivery_file_id": str(delivery.get("file_id") or ""),
                "telegram_file_id": str(delivery.get("file_id") or ""),
                "final_video_file_id": str(delivery.get("file_id") or ""),
                "charge_policy": "after_valid_mp4_delivery",
            }
        )
        update_video_render_job(
            job_id,
            "completed",
            "video project sent",
            final_video_path=final_path,
            final_video_file_id=str(delivery.get("file_id") or ""),
            result=result,
        )
    except subprocess.TimeoutExpired:
        update_video_render_job(job_id, "failed", "video_render_timeout")
    except Exception as exc:
        update_video_render_job(job_id, "failed", f"video_render:{type(exc).__name__}:{first_line(str(exc))}")


def run_frame_video_render(job: dict) -> None:
    job_id = job.get("id")
    try:
        payload = json.loads(str(job.get("input_file_id") or "") or "{}")
        public_seam_job = frame_video_public_seam.frame_video_public_seam_applies_to_worker_job(
            payload
        )
        minimum_images = (
            frame_video_public_seam.frame_video_public_minimum_images()
            if public_seam_job
            else frame_video_runtime.FRAME_VIDEO_MIN_IMAGES
        )
        if payload.get("frame_video_contract") is not None:
            contract = {
                "version": int(payload.get("frame_video_contract") or 0) == 1,
                "worker_job_type": str(payload.get("worker_job_type") or "") == frame_video_commercial.WORKER_JOB_TYPE,
                "engine_route": str(payload.get("engine_route") or "") == frame_video_commercial.ENGINE_ROUTE,
                "worker_owner": str(payload.get("worker_owner") or "") == frame_video_commercial.WORKER_OWNER,
                "worker_capability": str(payload.get("worker_capability") or "") == frame_video_commercial.WORKER_CAPABILITY,
            }
            failed_contract = next((key for key, ok in contract.items() if not ok), "")
            if failed_contract:
                update_job(job_id, "failed", f"frame_video_contract_{failed_contract}")
                return
        photos = list(payload.get("photos") or [])
        if len(photos) < minimum_images:
            update_job(job_id, "failed", "not_enough_images")
            return
        state = dict(payload.get("state") or {})
        expected_image_count = int(state.get("image_count") or payload.get("image_count") or 0)
        framevideo3 = str(state.get("commercial_flow_version") or "") == "framevideo3"
        if (
            framevideo3
            and expected_image_count >= minimum_images
            and not payload.get("paid_preview")
            and len(photos) != expected_image_count
        ):
            update_job(job_id, "failed", "image_count_mismatch")
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            image_paths = []
            frame_input_limit = frame_video_telegram_input_limit_bytes()
            processing_input_limit = (
                frame_video_public_seam.frame_video_processing_input_limit_bytes()
            )
            downloaded_input_bytes = 0

            def download_frame_asset(file_id: str, path: str) -> None:
                nonlocal downloaded_input_bytes
                remaining_bytes = processing_input_limit - downloaded_input_bytes
                if remaining_bytes <= 0:
                    raise RuntimeError("frame_video_processing_capacity_exceeded")
                asset_limit = min(frame_input_limit, remaining_bytes)
                try:
                    telegram_download_file(file_id, path, max_bytes=asset_limit)
                except RuntimeError as exc:
                    if (
                        str(exc) == "telegram_file_too_large"
                        and asset_limit < frame_input_limit
                    ):
                        raise RuntimeError(
                            "frame_video_processing_capacity_exceeded"
                        ) from None
                    raise
                downloaded_input_bytes += os.path.getsize(path)
                if downloaded_input_bytes > processing_input_limit:
                    raise RuntimeError("frame_video_processing_capacity_exceeded")

            for idx, item in enumerate(photos, start=1):
                file_id = str((item or {}).get("file_id") or "")
                if not file_id:
                    continue
                path = os.path.join(tmpdir, f"frame_input_{idx}.jpg")
                download_frame_asset(file_id, path)
                image_paths.append(path)
            state["photos"] = photos
            logo_path = ""
            music_path = ""
            voice_path = ""
            for key, filename in (
                ("logo_file_id", "frame_logo.img"),
                ("music_file_id", "frame_music.audio"),
                ("voice_file_id", "frame_voice.audio"),
            ):
                file_id = str(state.get(key) or "")
                if not file_id:
                    continue
                path = os.path.join(tmpdir, filename)
                download_frame_asset(file_id, path)
                if key == "logo_file_id":
                    logo_path = path
                elif key == "music_file_id":
                    music_path = path
                else:
                    voice_path = path
            if (
                framevideo3
                and expected_image_count >= minimum_images
                and not payload.get("paid_preview")
                and len(image_paths) != expected_image_count
            ):
                update_job(job_id, "failed", "image_count_mismatch_downloaded")
                return
            output_path = os.path.join(tmpdir, "toan_aas_frame_video.mp4")
            actual_worker_sha = local_worker_runtime_sha()
            public_result = None
            if public_seam_job:
                frame_job_id = str(payload.get("frame_job_id") or "").strip()
                if not frame_job_id or not str(job_id or "").isdigit() or int(job_id) <= 0:
                    raise RuntimeError("frame_video_job_identity_missing")
                runtime_sha = str(
                    payload.get("frame_video_runtime_sha")
                    or payload.get("frame_video_expected_worker_sha")
                    or "local"
                ).strip()
                expected_worker_sha = str(
                    payload.get("frame_video_expected_worker_sha") or runtime_sha
                ).strip()
                worker_timeout_ceiling = max(
                    180,
                    env_int("FRAME_VIDEO_STAGE_TIMEOUT_MAX_SECONDS", 7200),
                )
                requested_timeout_ceiling = max(
                    180,
                    int(payload.get("max_render_seconds") or worker_timeout_ceiling),
                )
                stage_timeout = frame_video_public_seam.frame_video_stage_timeout_seconds(
                    frame_video_runtime.expected_duration_seconds(state),
                    input_bytes=downloaded_input_bytes,
                    large_media=(
                        str(payload.get("media_lane") or "") == "large_media"
                    ),
                    ceiling_seconds=min(
                        worker_timeout_ceiling,
                        requested_timeout_ceiling,
                    ),
                )
                public_result = frame_video_public_seam.render_frame_video_public(
                    state=state,
                    image_paths=image_paths,
                    output_path=output_path,
                    user_id=int(payload.get("user_id") or 0),
                    confirmation_id=str(payload.get("frame_job_id") or job_id),
                    language=str(payload.get("language") or "vi"),
                    runtime_sha=runtime_sha,
                    expected_worker_sha=expected_worker_sha,
                    worker_sha=actual_worker_sha,
                    worker_instance_id=LOCAL_WORKER_INSTANCE_ID,
                    ffmpeg_path=local_ffmpeg_path(),
                    ffprobe_path=find_ffprobe(ffmpeg_path=local_ffmpeg_path()),
                    music_path=music_path,
                    voice_path=voice_path,
                    logo_path=logo_path,
                    timeout_seconds=stage_timeout,
                    environ=os.environ,
                )
                if not public_result.get("enabled"):
                    raise RuntimeError("frame_video_public_seam_disabled")
                if not public_result.get("ok"):
                    raise RuntimeError(str(public_result.get("blocker") or "frame_video_public_seam_failed"))
                probe = dict(public_result.get("probe") or {})
                digest = str(public_result.get("output_sha256") or "")
            else:
                render = frame_video_runtime.build_ffmpeg_command(
                    image_paths,
                    output_path,
                    state,
                    ffmpeg_path=local_ffmpeg_path(),
                    music_path=music_path,
                    voice_path=voice_path,
                    logo_path=logo_path,
                )
                completed = subprocess.run(
                    render.command,
                    capture_output=True,
                    text=True,
                    timeout=min(LOCAL_WORKER_MAX_JOB_SECONDS, int(payload.get("max_render_seconds") or 180)),
                    check=False,
                )
                if completed.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                    raise RuntimeError(first_line(completed.stderr or completed.stdout) or "frame_video_ffmpeg_failed")
                probe = frame_video_runtime.probe_mp4(output_path, render.expected_duration, render.expects_audio)
                if not probe.get("ok"):
                    raise RuntimeError(f"frame_video_validate:{probe.get('reason')}")
                digest_obj = hashlib.sha256()
                with open(output_path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest_obj.update(chunk)
                digest = digest_obj.hexdigest()
            chat_id = str(payload.get("chat_id") or "").strip()
            if not chat_id:
                raise RuntimeError("frame_video_chat_id_missing")
            delivery_method = frame_video_public_seam.frame_video_telegram_delivery_method(
                os.path.getsize(output_path)
            )
            try:
                receipt = telegram_send_video_receipt(
                    chat_id,
                    output_path,
                    str(payload.get("caption") or ""),
                    filename="toan_aas_frame_video.mp4",
                    max_bytes=frame_video_public_seam.frame_video_telegram_output_limit_bytes(),
                    prefer_document=delivery_method == "document",
                )
                if not isinstance(receipt, dict):
                    raise RuntimeError("frame_video_delivery_receipt_missing")
                receipt_blocker = frame_video_public_seam.frame_video_delivery_receipt_blocker(
                    receipt.get("message_id"),
                    receipt.get("file_id"),
                )
                if receipt.get("sent") is not True or receipt_blocker:
                    raise RuntimeError("frame_video_delivery_receipt_missing")
            except Exception as exc:
                if frame_video_public_seam.frame_video_delivery_outcome_uncertain(exc):
                    update_job(
                        job_id,
                        "failed",
                        json.dumps(
                            {
                                "stage": "delivery_unknown",
                                "reason": "telegram_delivery_outcome_uncertain",
                                "charge": 0,
                            },
                            separators=(",", ":"),
                        ),
                    )
                    return
                raise
            terminal = frame_video_public_seam.build_frame_video_worker_terminal_receipt(
                frame_job_id=payload.get("frame_job_id"),
                local_worker_job_id=job_id,
                delivery_message_id=receipt.get("message_id"),
                delivery_file_id=receipt.get("file_id"),
                output_size_bytes=os.path.getsize(output_path),
                output_sha256=digest,
                worker_id=LOCAL_WORKER_ID,
                worker_sha=actual_worker_sha,
                probe=probe,
            )
        update_job(
            job_id,
            "succeeded",
            "frame video validated and sent",
            output_url=json.dumps(terminal, ensure_ascii=False, separators=(",", ":")),
            output_file_id=str(receipt.get("file_id") or ""),
            output_limit=16 * 1024,
        )
    except subprocess.TimeoutExpired:
        update_job(job_id, "failed", "frame_video_render_timeout")
    except Exception as exc:
        update_job(job_id, "failed", f"frame_video_render:{type(exc).__name__}:{first_line(str(exc))}")


def paid_video_preview_ffmpeg_command(payload: dict, source_path: str, output_path: str) -> list[str]:
    seconds = max(2, min(6, int(payload.get("preview_seconds") or 6)))
    width = max(240, min(640, int(payload.get("width") or 360)))
    height = max(240, min(960, int(payload.get("height") or 640)))
    source_kind = str(payload.get("source_kind") or "storyboard").strip().lower()
    command = [LOCAL_FFMPEG_PATH, "-y"]
    if source_path:
        if source_kind == "image":
            command.extend(["-loop", "1", "-i", source_path])
        else:
            command.extend(["-stream_loop", "-1", "-i", source_path])
    else:
        command.extend([
            "-f", "lavfi",
            "-i", f"color=c=#102a35:s={width}x{height}:r=24:d={seconds}",
        ])
    prompt = " ".join(str(payload.get("prompt_preview") or "").split())[:48]
    overlay = "TOAN AAS - BAN XEM THU" + (f" - {prompt}" if source_kind == "storyboard" and prompt else "")
    base_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
        "eq=brightness=-0.03:contrast=0.92:saturation=0.78"
    )
    text_filter = video_editor_text_filter(overlay)
    command.extend([
        "-t", str(seconds),
        "-vf", ",".join(part for part in (base_filter, text_filter, "format=yuv420p") if part),
        "-an",
        "-r", "24",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "32",
        "-movflags", "+faststart",
        output_path,
    ])
    return command


def run_paid_video_preview(job: dict) -> None:
    job_id = job.get("id")
    try:
        payload = json.loads(str(job.get("input_file_id") or "") or "{}")
        chat_id = str(payload.get("chat_id") or "")
        seconds = int(payload.get("preview_seconds") or 0)
        if not chat_id or seconds < 2 or seconds > 6:
            update_job(job_id, "failed", "paid_video_preview_invalid_input")
            return
        if not LOCAL_FFMPEG_PATH or not os.path.exists(LOCAL_FFMPEG_PATH):
            update_job(job_id, "failed", "LOCAL_FFMPEG_PATH missing")
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = ""
            source_file_id = str(payload.get("source_file_id") or "").strip()
            source_url = str(payload.get("source_url") or "").strip()
            if source_file_id:
                source_path = os.path.join(tmpdir, "paid_preview_source.bin")
                telegram_download_file(source_file_id, source_path, max_bytes=50 * 1024 * 1024)
            elif source_url:
                source_path = os.path.join(tmpdir, "paid_preview_source.bin")
                download_url_file(source_url, source_path, max_bytes=50 * 1024 * 1024)
            output_path = os.path.join(tmpdir, "toan_aas_paid_video_preview.mp4")
            command = paid_video_preview_ffmpeg_command(payload, source_path, output_path)
            timeout = min(LOCAL_WORKER_MAX_JOB_SECONDS, max(60, int(payload.get("max_render_seconds") or 120)))
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
            if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                raise RuntimeError(first_line(result.stderr or result.stdout) or "paid_video_preview_ffmpeg_failed")
            token = str(payload.get("confirm_token") or "")[:120]
            reply_markup = None
            if token:
                reply_markup = {
                    "inline_keyboard": [
                        [{"text": "✅ Xác nhận tạo bản đầy đủ", "callback_data": f"shopai|confirm|{token}"}],
                        [
                            {"text": "🔁 Đổi giọng/nhạc", "callback_data": "vfinal|music"},
                            {"text": "✏️ Sửa nội dung", "callback_data": "vfinal|menu"},
                        ],
                        [
                            {"text": "⬅️ Quay lại", "callback_data": "videoaddon|back"},
                            {"text": "🏠 Menu chính", "callback_data": "videoaddon|main"},
                        ],
                    ]
                }
            output_file_id = telegram_send_video(
                chat_id,
                output_path,
                str(payload.get("caption") or ""),
                reply_markup=reply_markup,
            )
        update_job(job_id, "succeeded", "paid video preview sent", output_file_id=output_file_id)
    except subprocess.TimeoutExpired:
        update_job(job_id, "failed", "paid_video_preview_timeout")
    except Exception as exc:
        update_job(job_id, "failed", f"paid_video_preview:{type(exc).__name__}:{first_line(str(exc))}")


def process_job(job: dict) -> None:
    job_id = job.get("id")
    job_type = str(job.get("job_type") or "").strip()
    if not job_id:
        return
    if job_type == "worker_ping":
        update_job(job_id, "succeeded", "Local worker ping OK.")
        return
    if job_type == "ffmpeg_health":
        run_ffmpeg_health(job)
        return
    if job_type == "frame_video_render":
        run_frame_video_render(job)
        return
    if job_type == "paid_video_preview":
        run_paid_video_preview(job)
        return
    if job_type == "video_local_edit":
        run_video_local_edit(job)
        return
    if job_type == "video_ai_edit":
        run_video_ai_edit(job)
        return
    if job_type == "social_link_import":
        run_social_link_import(job)
        return
    if job_type == "video_render":
        run_video_render_job(job)
        return
    if job_type.startswith("comfy_"):
        update_job(job_id, "failed", "ComfyUI Phase 1 planned/not_ready.")
        return
    update_job(job_id, "failed", "Job type chưa hỗ trợ ở Phase 1.")


def main() -> None:
    global LOCAL_WORKER_LAST_ERROR
    print("[local_worker] TOAN AAS Local Worker Phase 1 starting")
    print(f"[local_worker] base_url={BOT_BASE_URL}")
    print(f"[local_worker] worker_id={LOCAL_WORKER_ID}")
    print(f"[local_worker] token_configured={'yes' if bool(LOCAL_WORKER_TOKEN) else 'no'}")
    print(f"[local_worker] telegram_token_configured={'yes' if bool(TELEGRAM_BOT_TOKEN) else 'no'}")
    print(f"[local_worker] ffmpeg_path={LOCAL_FFMPEG_PATH}")
    print("[local_worker] ComfyUI render is planned/not_ready in Phase 1")
    heartbeat_stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=run_heartbeat_loop,
        args=(heartbeat_stop,),
        name="toan-aas-local-worker-heartbeat",
        daemon=True,
    )
    heartbeat_thread.start()
    try:
        while True:
            try:
                job = poll_job()
                if job:
                    print(f"[local_worker] job #{job.get('id')} {job.get('job_type')}")
                    process_job(job)
                elif VIDEO_PROJECT_QUEUE_ENABLED:
                    video_job = poll_video_render_job()
                    if video_job:
                        print(f"[local_worker] video_job #{video_job.get('id')} {video_job.get('job_type')}")
                        run_video_render_job(video_job)
                    else:
                        time.sleep(5)
                else:
                    time.sleep(5)
            except KeyboardInterrupt:
                print("[local_worker] stopped")
                return
            except urllib.error.HTTPError as exc:
                LOCAL_WORKER_LAST_ERROR = f"HTTP {exc.code}"
                print(f"[local_worker] HTTP {exc.code}; check LOCAL_WORKER_ENABLED/TOKEN/base URL")
                time.sleep(10)
            except urllib.error.URLError as exc:
                LOCAL_WORKER_LAST_ERROR = f"connection:{type(exc.reason).__name__}"
                print(f"[local_worker] connection error: {type(exc.reason).__name__}")
                time.sleep(10)
            except Exception as exc:
                LOCAL_WORKER_LAST_ERROR = type(exc).__name__
                print(f"[local_worker] loop error: {type(exc).__name__}")
                time.sleep(10)
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=2)


if __name__ == "__main__":
    main()
