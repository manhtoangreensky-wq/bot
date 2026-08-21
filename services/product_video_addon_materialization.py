"""Strict Product Video Add-on materialization shared by workers.

The UI/queue contract names the requested materials. This module resolves
those names to real local artifacts before a renderer or provider is touched.
It deliberately has no Telegram, billing, or provider side effects; callers
inject the optional download callbacks used by their worker boundary.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from services.multiscene_video_pipeline import SceneSpec, build_scene_subtitle
from services.video_local_validation import (
    ALLOWED_AUDIO_EXTENSIONS,
    find_ffprobe,
    validate_static_image_file,
)


CONTRACT_VERSION = "product-video-addons-v1"
STOCK_AUDIO_HOSTS = frozenset(
    {
        "freesound.org",
        "cdn.freesound.org",
        "jamendo.com",
        "storage.jamendo.com",
        "prod-1.storage.jamendo.com",
    }
)
EDGE_VOICES = {
    "vi": ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"),
    "en": ("en-US-JennyNeural", "en-US-GuyNeural"),
    "zh": ("zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural"),
    "es": ("es-ES-ElviraNeural", "es-ES-AlvaroNeural"),
    "pt": ("pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"),
    "fr": ("fr-FR-DeniseNeural", "fr-FR-HenriNeural"),
    "de": ("de-DE-KatjaNeural", "de-DE-ConradNeural"),
    "ja": ("ja-JP-NanamiNeural", "ja-JP-KeitaNeural"),
    "ko": ("ko-KR-SunHiNeural", "ko-KR-InJoonNeural"),
    "hi": ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural"),
    "ar": ("ar-SA-ZariyahNeural", "ar-SA-HamedNeural"),
    "ru": ("ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural"),
    "tr": ("tr-TR-EmelNeural", "tr-TR-AhmetNeural"),
    "th": ("th-TH-PremwadeeNeural", "th-TH-NiwatNeural"),
    "fil": ("fil-PH-BlessicaNeural", "fil-PH-AngeloNeural"),
    "it": ("it-IT-ElsaNeural", "it-IT-DiegoNeural"),
    "id": ("id-ID-GadisNeural", "id-ID-ArdiNeural"),
}


def addon_plan(job: dict | None = None) -> dict:
    data = dict(job or {})
    project = dict(data.get("project") or {})
    candidates = (
        data.get("addon_plan"),
        data.get("addon_plan_json"),
        project.get("addon_plan_json"),
    )
    for candidate in candidates:
        if isinstance(candidate, dict):
            return dict(candidate)
        try:
            parsed = json.loads(str(candidate or "{}"))
        except (TypeError, ValueError):
            parsed = {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _addon_file(value: Any) -> str:
    path = str(value or "").strip()
    try:
        return os.path.abspath(path) if path and os.path.isfile(path) and os.path.getsize(path) > 0 else ""
    except OSError:
        return ""


def _ffmpeg_path(explicit: str = "") -> str:
    selected = str(explicit or os.getenv("FFMPEG_PATH") or os.getenv("LOCAL_FFMPEG_PATH") or "").strip()
    if selected and (os.path.isfile(selected) or shutil.which(selected)):
        return selected
    return shutil.which("ffmpeg") or ""


def _audio_valid(path: str, *, ffmpeg_path: str = "") -> bool:
    source = _addon_file(path)
    if not source or Path(source).suffix.lower() not in ALLOWED_AUDIO_EXTENSIONS:
        return False
    probe = find_ffprobe(ffmpeg_path=_ffmpeg_path(ffmpeg_path))
    if not probe:
        return False
    try:
        completed = subprocess.run(
            [
                probe,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                source,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and "audio" in str(completed.stdout or "").lower()


def _stock_url_allowed(value: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(str(value or "").strip())
    except ValueError:
        return False
    host = str(parsed.hostname or "").strip().lower().rstrip(".")
    return bool(
        parsed.scheme.lower() == "https"
        and host
        and any(host == allowed or host.endswith("." + allowed) for allowed in STOCK_AUDIO_HOSTS)
    )


def _download_url(url: str, destination: str, max_bytes: int = 50 * 1024 * 1024) -> None:
    request = urllib.request.Request(str(url), headers={"User-Agent": "TOAN-AAS-product-video/1"})
    target = Path(destination)
    partial = target.with_suffix(target.suffix + ".partial")
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            with partial.open("wb") as handle:
                while True:
                    chunk = response.read(min(1024 * 1024, max_bytes - received + 1))
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > max_bytes:
                        raise RuntimeError("addon_audio_too_large")
                    handle.write(chunk)
        if received <= 0:
            raise RuntimeError("addon_audio_empty")
        partial.replace(target)
    except Exception:
        try:
            partial.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _materialize_stock_audio(
    material: dict,
    *,
    workspace: str,
    filename: str,
    download_url: Callable[[str, str, int], None] | None,
    ffmpeg_path: str,
) -> str:
    existing = _addon_file(material.get("artifact_path") or material.get("local_path"))
    if existing:
        return existing if _audio_valid(existing, ffmpeg_path=ffmpeg_path) else ""
    source_url = str(
        material.get("source_url")
        or material.get("download_url")
        or material.get("preview_url")
        or ""
    ).strip()
    if not source_url or not _stock_url_allowed(source_url):
        return ""
    suffix = Path(urllib.parse.urlsplit(source_url).path).suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        suffix = ".mp3"
    target = os.path.join(workspace, f"{filename}{suffix}")
    try:
        (download_url or _download_url)(source_url, target, 50 * 1024 * 1024)
    except Exception:
        return ""
    return os.path.abspath(target) if _audio_valid(target, ffmpeg_path=ffmpeg_path) else ""


def _subtitle_scenes(script_text: str, scene_count: int, duration: float) -> list[SceneSpec]:
    lines = [line.strip() for line in str(script_text or "").splitlines() if line.strip()]
    if not lines:
        return []
    count = max(1, int(scene_count or 1))
    if len(lines) < count:
        lines.extend([lines[-1]] * (count - len(lines)))
    return [
        SceneSpec(
            scene_id=index,
            title=f"Scene {index}",
            visual_prompt="",
            video_prompt="",
            narration_text=lines[index - 1],
            target_duration_sec=max(0.5, float(duration or 1.0)),
        )
        for index in range(1, count + 1)
    ]


def _materialize_subtitle(material: dict, *, workspace: str, scene_count: int, scene_duration: float) -> str:
    existing = _addon_file(material.get("artifact_path"))
    if existing and Path(existing).suffix.lower() == ".srt":
        return existing
    scenes = _subtitle_scenes(
        str(material.get("script_text") or material.get("text") or ""),
        scene_count,
        scene_duration,
    )
    if not scenes:
        return ""
    output = os.path.join(workspace, "product_video_subtitles.srt")
    try:
        return build_scene_subtitle(
            scenes,
            [max(0.5, float(scene_duration or 1.0))] * len(scenes),
            output,
        )
    except Exception:
        return ""


def _edge_voice(material: dict) -> str:
    language = str(material.get("target_language") or "vi").strip().lower().split("-", 1)[0]
    female, male = EDGE_VOICES.get(language, EDGE_VOICES["vi"])
    choice = str(material.get("voice_choice") or material.get("voice_kind") or "default_female").strip().lower()
    return male if "male" in choice and "female" not in choice else female


def _materialize_dubbing(material: dict, *, workspace: str, ffmpeg_path: str) -> str:
    existing = _addon_file(material.get("artifact_path") or material.get("audio_path"))
    if existing:
        return existing if _audio_valid(existing, ffmpeg_path=ffmpeg_path) else ""
    script = " ".join(str(material.get("script_text") or "").split())
    choice = str(material.get("voice_choice") or "default_female").strip().lower()
    if not script or choice not in {"default_female", "default_male", "female", "male"}:
        return ""
    try:
        import edge_tts
    except Exception:
        return ""
    target = os.path.join(workspace, "product_video_dubbing.mp3")

    async def _save() -> None:
        communicator = edge_tts.Communicate(script, _edge_voice(material))
        await communicator.save(target)

    try:
        asyncio.run(_save())
    except Exception:
        return ""
    return os.path.abspath(target) if _audio_valid(target, ffmpeg_path=ffmpeg_path) else ""


def materialize_product_video_addons(
    job: dict | None,
    *,
    workspace: str,
    scene_count: int,
    scene_duration: float,
    download_url: Callable[[str, str, int], None] | None = None,
    telegram_download: Callable[..., Any] | None = None,
    logo_fallback_path: str = "",
    ffmpeg_path: str = "",
) -> dict:
    plan = addon_plan(job)
    if str(plan.get("contract_version") or "") != CONTRACT_VERSION:
        return {"ok": True, "strict": False, "requested_addons": []}
    requested = [
        str(item or "").strip()
        for item in plan.get("requested_addons") or []
        if str(item or "").strip()
    ]
    result = {
        "ok": False,
        "strict": True,
        "requested_addons": requested,
        "subtitle_path": "",
        "voice_audio_path": "",
        "bgm_audio_path": "",
        "sfx_audio_paths": [],
        "logo_path": "",
        "logo_position": "top_left",
        "watermark_text": "",
        "watermark_position": "bottom_right",
        "watermark_opacity_percent": 45,
        "text_overlays": [],
        "transition_plan": [],
        "voice_volume_percent": 100,
        "music_volume_percent": 20,
        "sfx_volume_percent": 35,
        "provider_submit_allowed": False,
    }

    def block(name: str) -> dict:
        return {**result, "blocker": f"addon_material_missing:{name}"}

    selected_ffmpeg = _ffmpeg_path(ffmpeg_path)
    if "subtitle" in requested:
        path = _materialize_subtitle(
            dict(plan.get("subtitle") or {}),
            workspace=workspace,
            scene_count=scene_count,
            scene_duration=scene_duration,
        )
        if not path:
            return block("subtitle")
        result["subtitle_path"] = path
    if "dubbing" in requested:
        dubbing = dict(plan.get("dubbing") or {})
        result["voice_audio_path"] = _materialize_dubbing(
            dubbing,
            workspace=workspace,
            ffmpeg_path=selected_ffmpeg,
        )
        result["voice_volume_percent"] = max(0, min(200, int(dubbing.get("volume_percent") or 100)))
        if not result["voice_audio_path"]:
            return block("dubbing")
    if "music" in requested:
        music = dict(plan.get("music") or {})
        if not str(music.get("asset_id") or "").strip():
            return block("music")
        result["bgm_audio_path"] = _materialize_stock_audio(
            music,
            workspace=workspace,
            filename="product_video_music",
            download_url=download_url,
            ffmpeg_path=selected_ffmpeg,
        )
        result["music_volume_percent"] = max(0, min(200, int(music.get("volume_percent") or 20)))
        if not result["bgm_audio_path"]:
            return block("music")
    if "sfx" in requested:
        sfx = dict(plan.get("sfx") or {})
        assets = [dict(item) for item in sfx.get("assets") or [] if isinstance(item, dict)]
        if not assets:
            return block("sfx")
        for index, asset in enumerate(assets, start=1):
            if not str(asset.get("asset_id") or "").strip():
                return block("sfx")
            path = _materialize_stock_audio(
                asset,
                workspace=workspace,
                filename=f"product_video_sfx_{index:02d}",
                download_url=download_url,
                ffmpeg_path=selected_ffmpeg,
            )
            if not path:
                return block("sfx")
            result["sfx_audio_paths"].append(path)
        result["sfx_assets"] = assets
        result["sfx_volume_percent"] = max(0, min(200, int(sfx.get("volume_percent") or 35)))
    if "logo" in requested:
        logo = dict(plan.get("logo") or {})
        logo_path = _addon_file(logo.get("artifact_path")) or _addon_file(logo_fallback_path)
        if not logo_path and str(logo.get("telegram_file_id") or "").strip() and telegram_download:
            logo_path = os.path.join(workspace, "product_video_logo.png")
            try:
                telegram_download(
                    str(logo.get("telegram_file_id") or ""),
                    logo_path,
                    max_bytes=10 * 1024 * 1024,
                )
            except Exception:
                logo_path = ""
        validation = validate_static_image_file(logo_path) if logo_path else {"ok": False}
        if not validation.get("ok"):
            return block("logo")
        result["logo_path"] = os.path.abspath(logo_path)
        result["logo_position"] = str(logo.get("position") or "top_left")
    if "watermark" in requested:
        watermark = dict(plan.get("watermark") or {})
        result["watermark_text"] = str(watermark.get("text") or "").strip()[:240]
        result["watermark_position"] = str(watermark.get("position") or "bottom_right")
        result["watermark_opacity_percent"] = max(0, min(100, int(watermark.get("opacity_percent") or 45)))
        if not result["watermark_text"]:
            return block("watermark")
    if "text" in requested:
        result["text_overlays"] = [
            dict(item)
            for item in plan.get("text_overlays") or []
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
        if not result["text_overlays"]:
            return block("text")
    if "transitions" in requested:
        result["transition_plan"] = [
            str(item or "cut").strip() or "cut"
            for item in plan.get("transition_plan") or []
        ]
        if scene_count > 1 and len(result["transition_plan"]) != scene_count - 1:
            return block("transitions")
    result.update(
        {
            "ok": True,
            "blocker": "",
            "provider_submit_allowed": True,
            "materialized_addons": list(requested),
        }
    )
    return result
