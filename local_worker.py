"""
TOAN AAS Local Worker Phase 1.

Runs on the local Windows machine and polls Railway bot internal worker endpoints.
Phase 1 only supports worker ping and local ffmpeg health checks. ComfyUI is kept
as planned/not_ready and is not called unless later phases explicitly enable it.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


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
LOCAL_WORKER_ID = str(os.environ.get("LOCAL_WORKER_ID", "toan-aas-local-windows")).strip()
LOCAL_WORKER_MAX_JOB_SECONDS = max(30, env_int("LOCAL_WORKER_MAX_JOB_SECONDS", 600))
LOCAL_FFMPEG_PATH = str(
    os.environ.get("LOCAL_FFMPEG_PATH", r"D:\TOANAAS\ffmpeg-8.1.1\bin\ffmpeg.exe")
).strip()
LOCAL_COMFY_ENABLED = env_flag("LOCAL_COMFY_ENABLED", "false")


def endpoint(path: str) -> str:
    return BOT_BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def auth_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + LOCAL_WORKER_TOKEN,
        "x-local-worker-token": LOCAL_WORKER_TOKEN,
        "x-worker-id": LOCAL_WORKER_ID,
    }


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = 20) -> dict:
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint(path), data=data, headers=auth_headers(), method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return json.loads(body or "{}")


def send_heartbeat() -> None:
    payload = {
        "worker_id": LOCAL_WORKER_ID,
        "ffmpeg_path": LOCAL_FFMPEG_PATH,
        "comfy_enabled": LOCAL_COMFY_ENABLED,
    }
    http_json("POST", "/internal/worker/heartbeat", payload, timeout=15)


def poll_job() -> dict | None:
    query = urllib.parse.urlencode({"worker_id": LOCAL_WORKER_ID})
    data = http_json("GET", f"/internal/worker/poll?{query}", timeout=25)
    return data.get("job") if data.get("ok") else None


def update_job(job_id, status: str, error_short: str = "", output_url: str = "") -> None:
    payload = {
        "job_id": job_id,
        "status": status,
        "worker_id": LOCAL_WORKER_ID,
        "error_short": str(error_short or "")[:500],
        "output_url": str(output_url or "")[:1000],
    }
    http_json("POST", "/internal/worker/job_update", payload, timeout=20)


def first_line(text: str) -> str:
    for line in str(text or "").splitlines():
        clean = line.strip()
        if clean:
            return clean[:300]
    return ""


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
    if job_type.startswith("comfy_"):
        update_job(job_id, "failed", "ComfyUI Phase 1 planned/not_ready.")
        return
    update_job(job_id, "failed", "Job type chưa hỗ trợ ở Phase 1.")


def main() -> None:
    print("[local_worker] TOAN AAS Local Worker Phase 1 starting")
    print(f"[local_worker] base_url={BOT_BASE_URL}")
    print(f"[local_worker] worker_id={LOCAL_WORKER_ID}")
    print(f"[local_worker] token_configured={'yes' if bool(LOCAL_WORKER_TOKEN) else 'no'}")
    print(f"[local_worker] ffmpeg_path={LOCAL_FFMPEG_PATH}")
    print("[local_worker] ComfyUI render is planned/not_ready in Phase 1")
    last_heartbeat = 0.0
    while True:
        try:
            now = time.time()
            if now - last_heartbeat >= 30:
                send_heartbeat()
                last_heartbeat = now
            job = poll_job()
            if job:
                print(f"[local_worker] job #{job.get('id')} {job.get('job_type')}")
                process_job(job)
            else:
                time.sleep(5)
        except KeyboardInterrupt:
            print("[local_worker] stopped")
            return
        except urllib.error.HTTPError as exc:
            print(f"[local_worker] HTTP {exc.code}; check LOCAL_WORKER_ENABLED/TOKEN/base URL")
            time.sleep(10)
        except urllib.error.URLError as exc:
            print(f"[local_worker] connection error: {type(exc.reason).__name__}")
            time.sleep(10)
        except Exception as exc:
            print(f"[local_worker] loop error: {type(exc).__name__}")
            time.sleep(10)


if __name__ == "__main__":
    main()
