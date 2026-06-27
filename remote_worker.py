"""Remote VPS worker for TOAN AAS heavy local/video processing.

This process runs on the VPS and talks to the Railway bot only through the
authenticated /api/v1/worker/* bridge. It never opens the Railway SQLite DB and
does not need PayOS, wallet, or Telegram webhook authority.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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
LOCAL_VIDEO_FAKE_RENDERER_ENABLED = env_flag("LOCAL_VIDEO_FAKE_RENDERER_ENABLED", "false")


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


def claim_job() -> dict | None:
    payload = {
        "worker_id": WORKER_ID,
        "capabilities": ["ffmpeg", "video_postprocess"],
        "max_jobs": 1,
    }
    data = http_json("POST", "/api/v1/worker/claim", payload, timeout=30)
    return data.get("job") if data.get("ok") else None


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
    return http_json("POST", "/api/v1/worker/fail", payload, timeout=30)


def first_line(text: str) -> str:
    for line in str(text or "").splitlines():
        clean = line.strip()
        if clean:
            return clean[:300]
    return ""


def local_ffmpeg_path() -> str:
    if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
        return FFMPEG_PATH
    return shutil.which(FFMPEG_PATH) or shutil.which("ffmpeg") or FFMPEG_PATH


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


def process_claimed_job(job: dict) -> dict:
    job_id = str(job.get("job_id") or "")
    if not job_id:
        raise RuntimeError("job_id_missing")
    with tempfile.TemporaryDirectory(dir=WORKER_TMP_DIR if os.path.isdir(WORKER_TMP_DIR) else None) as work_dir:
        send_heartbeat(job_id, 5, "claimed")
        if not LOCAL_VIDEO_FAKE_RENDERER_ENABLED:
            raise RuntimeError("video_render_runner_missing")
        send_heartbeat(job_id, 35, "rendering fake admin test video")
        final_path = render_fake_video(job, work_dir)
        send_heartbeat(job_id, 90, "uploading result")
        result = {
            "ok": True,
            "renderer": "remote_worker_fake_admin_test",
            "final_video_name": os.path.basename(final_path),
            "bytes": os.path.getsize(final_path),
        }
        return complete_job(job_id, result, final_path)


def run_once() -> str:
    job = claim_job()
    if not job:
        return "idle"
    job_id = str(job.get("job_id") or "")
    try:
        process_claimed_job(job)
        return "completed"
    except Exception as exc:
        if job_id:
            fail_job(job_id, f"{type(exc).__name__}:{first_line(str(exc))}", retryable=True)
        return "failed"


def main() -> None:
    print("[remote_worker] TOAN AAS Remote Worker starting")
    print(f"[remote_worker] base_url={BOT_API_URL}")
    print(f"[remote_worker] worker_id={WORKER_ID}")
    print(f"[remote_worker] token_configured={'yes' if bool(LOCAL_WORKER_TOKEN) else 'no'}")
    print(f"[remote_worker] concurrency={WORKER_CONCURRENCY} ffmpeg_max={FFMPEG_MAX_CONCURRENT}")
    while True:
        try:
            status = run_once()
            if status == "idle":
                time.sleep(WORKER_POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("[remote_worker] stopped")
            return
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
    main()
