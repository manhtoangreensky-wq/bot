"""
TOAN AAS Local Worker Phase 1.

Runs on the local Windows machine and polls Railway bot internal worker endpoints.
Supports worker health checks plus guarded local FFmpeg jobs used by TOAN AAS.
ComfyUI is kept as planned/not_ready and is not called unless later phases
explicitly enable it.
"""

from __future__ import annotations

import json
import os
import socket
import shutil
import tempfile
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

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
    real_video_llm_func_from_job,
)


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
LOCAL_FFMPEG_FONT_PATH = str(os.environ.get("LOCAL_FFMPEG_FONT_PATH", r"C:\Windows\Fonts\arial.ttf")).strip()
LOCAL_COMFY_ENABLED = env_flag("LOCAL_COMFY_ENABLED", "false")
VIDEO_PROJECT_QUEUE_ENABLED = env_flag("VIDEO_PROJECT_QUEUE_ENABLED", "true")
LOCAL_VIDEO_FAKE_RENDERER_ENABLED = env_flag("LOCAL_VIDEO_FAKE_RENDERER_ENABLED", "false")
RENDER_MODE_REAL = "real"
RENDER_MODE_ADMIN_TEST_PATTERN = "admin_test_pattern"
REMOTE_WORKER_ADMIN_VIDEO_SOURCE = "admin_video_delivery"


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


def poll_video_render_job() -> dict | None:
    query = urllib.parse.urlencode({"worker_id": LOCAL_WORKER_ID, "lease_seconds": LOCAL_WORKER_MAX_JOB_SECONDS})
    data = http_json("GET", f"/internal/video_worker/poll?{query}", timeout=25)
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


def telegram_send_video(chat_id: str, video_path: str, caption: str = "", reply_markup: dict | None = None) -> str:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    boundary = "----TOANAASLocalWorkerBoundary"
    with open(video_path, "rb") as handle:
        video_bytes = handle.read()
    fields = {
        "chat_id": str(chat_id or ""),
        "caption": str(caption or "")[:1000],
    }
    if reply_markup:
        fields["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
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


def run_video_local_edit(job: dict) -> None:
    job_id = job.get("id")
    try:
        payload = json.loads(str(job.get("input_file_id") or "") or "{}")
        source_file_id = str(payload.get("source_file_id") or "")
        chat_id = str(payload.get("chat_id") or "")
        if not source_file_id or not chat_id:
            update_job(job_id, "failed", "video_local_edit_missing_input")
            return
        if not LOCAL_FFMPEG_PATH or not os.path.exists(LOCAL_FFMPEG_PATH):
            update_job(job_id, "failed", "LOCAL_FFMPEG_PATH missing")
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "video_editor_input.mp4")
            output_path = os.path.join(tmpdir, "toan_aas_video_editor.mp4")
            telegram_download_file(source_file_id, input_path, max_bytes=50 * 1024 * 1024)
            filter_value, is_complex = video_editor_filter(payload)
            command = [LOCAL_FFMPEG_PATH, "-y", "-i", input_path]
            if is_complex:
                command.extend(["-filter_complex", filter_value, "-map", "[v]", "-map", "0:a?"])
            else:
                command.extend(["-vf", filter_value, "-map", "0:v:0", "-map", "0:a?"])
            command.extend([
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                "-max_muxing_queue_size", "2048", output_path,
            ])
            timeout = min(LOCAL_WORKER_MAX_JOB_SECONDS, max(60, int(payload.get("max_render_seconds") or 300)))
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
            if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                raise RuntimeError(first_line(result.stderr or result.stdout) or "video_local_edit_ffmpeg_failed")
            output_file_id = telegram_send_video(chat_id, output_path, str(payload.get("caption") or ""))
        update_job(job_id, "succeeded", "local video edit sent", output_file_id=output_file_id)
    except subprocess.TimeoutExpired:
        update_job(job_id, "failed", "video_local_edit_timeout")
    except Exception as exc:
        update_job(job_id, "failed", f"video_local_edit:{type(exc).__name__}:{first_line(str(exc))}")


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


def run_video_render_job(job: dict) -> None:
    job_id = job.get("id") or job.get("job_id")
    project = job.get("project") or {}
    try:
        if not job_id:
            return
        if not TELEGRAM_BOT_TOKEN:
            update_video_render_job(job_id, "failed", "telegram_token_missing_for_delivery")
            return
        user_id = str(project.get("user_id") or job.get("user_id") or "").strip()
        if not user_id:
            update_video_render_job(job_id, "failed", "video_render_missing_user")
            return
        scene_count = max(1, min(5, int(project.get("scene_count") or len(job.get("scenes") or []) or 3)))
        duration = 6.0
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
        result = process_multiscene_video_pipeline(
            user_id=user_id,
            job_id=str(job_id),
            user_prompt=prompt,
            workspace_dir=workspace,
            render_video_func=render_func,
            llm_func=real_video_llm_func_from_job(job),
            max_scenes=scene_count,
            default_scene_duration=duration,
            aspect_ratio=str(project.get("ratio") or "9:16"),
            enable_voice=False,
            enable_subtitle=bool(addon_plan.get("subtitle_enabled", True)),
            enable_logo=bool(addon_plan.get("logo_enabled") and addon_plan.get("logo_text")),
            logo_text=str(addon_plan.get("logo_text") or ""),
            logo_position=str(addon_plan.get("logo_position") or "bottom_right"),
        )
        final_path = str(result.get("final_video_path") or "")
        if not result.get("ok") or not final_path:
            raise RuntimeError(str(result.get("error") or result.get("status") or "video_render_failed"))
        result["render_mode"] = result_mode
        result["test_pattern"] = result_mode == RENDER_MODE_ADMIN_TEST_PATTERN
        output_file_id = telegram_send_video(
            user_id,
            final_path,
            send_caption,
        )
        update_video_render_job(job_id, "completed", "video project sent", final_video_path=final_path, final_video_file_id=output_file_id, result=result)
    except subprocess.TimeoutExpired:
        update_video_render_job(job_id, "failed", "video_render_timeout")
    except Exception as exc:
        update_video_render_job(job_id, "failed", f"video_render:{type(exc).__name__}:{first_line(str(exc))}")


def run_frame_video_render(job: dict) -> None:
    job_id = job.get("id")
    try:
        payload = json.loads(str(job.get("input_file_id") or "") or "{}")
        photos = list(payload.get("photos") or [])
        if len(photos) < 1:
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
