"""
TOAN AAS Local Worker Phase 1.

Runs on the local Windows machine and polls Railway bot internal worker endpoints.
Phase 1 only supports worker ping and local ffmpeg health checks. ComfyUI is kept
as planned/not_ready and is not called unless later phases explicitly enable it.
"""

from __future__ import annotations

import json
import os
import tempfile
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
TELEGRAM_BOT_TOKEN = str(os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or "").strip()
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


def update_job(job_id, status: str, error_short: str = "", output_url: str = "", output_file_id: str = "") -> None:
    payload = {
        "job_id": job_id,
        "status": status,
        "worker_id": LOCAL_WORKER_ID,
        "error_short": str(error_short or "")[:500],
        "output_url": str(output_url or "")[:1000],
        "output_file_id": str(output_file_id or "")[:500],
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


def telegram_json(method: str, payload: dict | None = None, timeout: int = 30) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}", data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return json.loads(body or "{}")


def telegram_download_file(file_id: str, destination: str, max_bytes: int = 20 * 1024 * 1024) -> None:
    data = telegram_json("getFile", {"file_id": file_id}, timeout=30)
    file_path = ((data.get("result") or {}).get("file_path") or "").strip()
    if not data.get("ok") or not file_path:
        raise RuntimeError("telegram_get_file_failed")
    url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    downloaded = 0
    with urllib.request.urlopen(url, timeout=60) as response, open(destination, "wb") as handle:
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            downloaded += len(chunk)
            if downloaded > max_bytes:
                raise RuntimeError("telegram_file_too_large")
            handle.write(chunk)
    if downloaded <= 0:
        raise RuntimeError("telegram_download_empty")


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
    if len(image_paths) < 2:
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


def telegram_send_video(chat_id: str, video_path: str, caption: str = "") -> str:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    boundary = "----TOANAASLocalWorkerBoundary"
    with open(video_path, "rb") as handle:
        video_bytes = handle.read()
    fields = {
        "chat_id": str(chat_id or ""),
        "caption": str(caption or "")[:1000],
    }
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8"))
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"toan_aas_frame_video.mp4\"\r\nContent-Type: video/mp4\r\n\r\n".encode("utf-8"))
    body.extend(video_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    if not data.get("ok"):
        raise RuntimeError("telegram_send_video_failed")
    videos = (data.get("result") or {}).get("video") or {}
    return str(videos.get("file_id") or "")


def run_frame_video_render(job: dict) -> None:
    job_id = job.get("id")
    try:
        payload = json.loads(str(job.get("input_file_id") or "") or "{}")
        photos = list(payload.get("photos") or [])
        if len(photos) < 2:
            update_job(job_id, "failed", "not_enough_images")
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            image_paths = []
            for idx, item in enumerate(photos, start=1):
                file_id = str((item or {}).get("file_id") or "")
                if not file_id:
                    continue
                path = os.path.join(tmpdir, f"frame_input_{idx}.jpg")
                telegram_download_file(file_id, path)
                image_paths.append(path)
            output_path = os.path.join(tmpdir, "toan_aas_frame_video.mp4")
            run_frame_video_ffmpeg(
                image_paths,
                output_path,
                int(payload.get("width") or 720),
                int(payload.get("height") or 1280),
                float(payload.get("seconds_per_image") or 1.5),
                str(payload.get("effect") or "fade"),
                min(LOCAL_WORKER_MAX_JOB_SECONDS, int(payload.get("max_render_seconds") or 180)),
            )
            output_file_id = telegram_send_video(str(payload.get("chat_id") or ""), output_path, str(payload.get("caption") or ""))
        update_job(job_id, "succeeded", "frame video sent", output_file_id=output_file_id)
    except subprocess.TimeoutExpired:
        update_job(job_id, "failed", "frame_video_render_timeout")
    except Exception as exc:
        update_job(job_id, "failed", f"frame_video_render:{type(exc).__name__}:{first_line(str(exc))}")


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
    if job_type.startswith("comfy_"):
        update_job(job_id, "failed", "ComfyUI Phase 1 planned/not_ready.")
        return
    update_job(job_id, "failed", "Job type chưa hỗ trợ ở Phase 1.")


def main() -> None:
    print("[local_worker] TOAN AAS Local Worker Phase 1 starting")
    print(f"[local_worker] base_url={BOT_BASE_URL}")
    print(f"[local_worker] worker_id={LOCAL_WORKER_ID}")
    print(f"[local_worker] token_configured={'yes' if bool(LOCAL_WORKER_TOKEN) else 'no'}")
    print(f"[local_worker] telegram_token_configured={'yes' if bool(TELEGRAM_BOT_TOKEN) else 'no'}")
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
