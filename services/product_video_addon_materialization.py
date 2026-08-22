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

from services import subdub_ass_layout, subdub_canonical_cues
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


def _persisted_scene_subtitle_script(job: dict | None = None) -> str:
    data = dict(job or {})
    project = dict(data.get("project") or {})
    cards: list[dict] = []
    for candidate in (
        data.get("scene_cards"),
        data.get("scenes"),
        project.get("scene_cards_json"),
    ):
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except (TypeError, ValueError):
                candidate = []
        if isinstance(candidate, list):
            cards = [dict(item) for item in candidate if isinstance(item, dict)]
            if cards:
                break
    fields = (
        "subtitle_line",
        "narration_line",
        "script_text",
        "dialogue_or_voiceover",
        "dialogue",
        "voiceover",
        "narration",
        "main_idea",
        "content",
    )
    lines: list[str] = []
    for card in cards:
        line = next(
            (
                " ".join(str(card.get(field) or "").split())
                for field in fields
                if str(card.get(field) or "").strip()
            ),
            "",
        )
        if line:
            lines.append(line)
    return "\n".join(lines)[:8000]


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


def _subtitle_scene_segments(script_text: str, scene_count: int, duration: float) -> list[dict]:
    lines = [line.strip() for line in str(script_text or "").splitlines() if line.strip()]
    if not lines:
        return []
    count = max(1, int(scene_count or 1))
    if len(lines) < count:
        lines.extend([lines[-1]] * (count - len(lines)))
    scene_duration = max(0.5, float(duration or 1.0))
    return [
        {
            "index": index,
            "scene_index": index,
            "start": round((index - 1) * scene_duration, 3),
            "end": round(index * scene_duration, 3),
            "text": lines[index - 1],
        }
        for index in range(1, count + 1)
    ]


def _subtitle_profile_name(language: str) -> str:
    code = str(language or "vi").strip().lower().replace("_", "-").split("-", 1)[0]
    if code in {"zh", "ja", "ko"}:
        return f"{code}_telegram_general_v1"
    if code in {"th", "vi", "en"}:
        return f"{code}_telegram_general_v1"
    return "en_telegram_general_v1"


def _subtitle_timestamp(milliseconds: int) -> str:
    milliseconds = max(0, int(milliseconds or 0))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _subtitle_ass_timestamp(milliseconds: int) -> str:
    centiseconds = max(0, int(round(int(milliseconds or 0) / 10.0)))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _render_subdub_srt(cues: list[dict]) -> str:
    blocks = []
    for cue in cues or []:
        text = str(cue.get("source_text") or cue.get("text") or "").strip()
        start_ms = int(cue.get("source_start_ms") or cue.get("start_ms") or 0)
        end_ms = int(cue.get("source_end_ms") or cue.get("end_ms") or 0)
        if not text or end_ms <= start_ms:
            return ""
        blocks.append(
            f"{len(blocks) + 1}\n"
            f"{_subtitle_timestamp(start_ms)} --> {_subtitle_timestamp(end_ms)}\n"
            f"{text}"
        )
    return ("\n\n".join(blocks) + "\n") if blocks else ""


def _subtitle_design_size(width: int, height: int) -> int:
    vertical = bool(height >= width * 1.15)
    if height <= 720:
        return 40 if vertical else 38
    if height <= 1080:
        return 42 if vertical else 40
    return 44 if vertical else 42


def _render_subdub_ass(
    cues: list[dict],
    *,
    width: int,
    height: int,
    language: str,
) -> tuple[str, list[dict]]:
    width = max(160, min(3840, int(width or 720)))
    height = max(160, min(3840, int(height or 1280)))
    code = str(language or "vi").strip().lower().replace("_", "-").split("-", 1)[0]
    profile_name = _subtitle_profile_name(code)
    font_name = "Noto Sans CJK SC" if code in {"zh", "ja", "ko"} else "Noto Sans"
    design_size = _subtitle_design_size(width, height)
    margin_l = max(2, min(max(2, int(width * 0.05)), int(round(width * 0.04))))
    margin_r = margin_l
    margin_v = max(6, min(14, int(round(height * 0.008))))
    style = {
        "play_res_x": width,
        "play_res_y": height,
        "render_size": design_size,
        "size": design_size,
        "subtitle_margin_l_after": margin_l,
        "subtitle_margin_r_after": margin_r,
        "outline": 4,
        "shadow": 1,
        "boxed_background": True,
    }
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "; subdub_renderer: translation_v1_shared_autofit",
        f"; canonical_subdub_profile: {profile_name}",
        "; subtitle_max_lines: 2",
        "; subtitle_cue_timestamps_mutated: no",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        (
            f"Style: Default,{font_name},{design_size},&H00FFFFFF,&H00FFFFFF,"
            f"&H00000000,&HB2000000,-1,0,0,0,100,100,0,0,3,4,1,2,"
            f"{margin_l},{margin_r},{margin_v},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events = []
    layouts = []
    for cue in cues or []:
        text = str(cue.get("source_text") or cue.get("text") or "").strip()
        start_ms = int(cue.get("source_start_ms") or cue.get("start_ms") or 0)
        end_ms = int(cue.get("source_end_ms") or cue.get("end_ms") or 0)
        if not text or end_ms <= start_ms:
            return "", []
        layout = subdub_ass_layout.fit_text_layout(text, style, 2)
        fitted = str(layout.get("text") or "")
        if (
            not fitted
            or not layout.get("fits_width")
            or int(layout.get("line_count") or 0) > 2
        ):
            return "", []
        escaped = r"\N".join(
            line.replace("\\", r"\\")
            for line in fitted.split(r"\N")
        )
        events.append(
            "Dialogue: 0,"
            f"{_subtitle_ass_timestamp(start_ms)},"
            f"{_subtitle_ass_timestamp(end_ms)},"
            f"Default,,0,0,0,,{{\\fs{int(layout.get('font_size') or design_size)}}}{escaped}"
        )
        layouts.append(dict(layout))
    return "\n".join([*header, *events]) + ("\n" if events else ""), layouts


def _materialize_subtitle(
    material: dict,
    *,
    workspace: str,
    scene_count: int,
    scene_duration: float,
    output_width: int,
    output_height: int,
) -> dict:
    existing = _addon_file(material.get("artifact_path"))
    timed_source = False
    if existing and Path(existing).suffix.lower() == ".srt":
        try:
            scene_segments = subdub_canonical_cues.parse_srt_segments(
                Path(existing).read_text(encoding="utf-8")
            )
        except OSError:
            return {}
        timed_source = True
    else:
        scene_segments = _subtitle_scene_segments(
            str(material.get("script_text") or material.get("text") or ""),
            scene_count,
            scene_duration,
        )
    if not scene_segments:
        return {}
    language = str(material.get("target_language") or material.get("language") or "vi").strip().lower()
    fitted = subdub_canonical_cues.fit_timed_subtitle_segments(
        scene_segments,
        preserve_timestamps=timed_source,
        max_chars_per_line=42,
        max_lines=2,
        metadata_fields=("scene_index",),
        strict_frame_fit=True,
    )
    canonical = subdub_canonical_cues.canonicalize_segments(
        fitted,
        extraction_source=(
            "user_timed_subtitle"
            if timed_source
            else "product_video_scene_timeline"
        ),
        source_language=language,
    )
    if not canonical:
        return {}
    srt_text = _render_subdub_srt(canonical)
    if not srt_text.strip():
        return {}
    ass_text, layouts = _render_subdub_ass(
        canonical,
        width=output_width,
        height=output_height,
        language=language,
    )
    if not ass_text.strip() or len(layouts) != len(canonical):
        return {}
    srt_output = os.path.join(workspace, "product_video_subtitles.srt")
    ass_output = os.path.join(workspace, "product_video_subtitles.ass")
    try:
        Path(srt_output).write_text(srt_text.rstrip() + "\n", encoding="utf-8")
        Path(ass_output).write_text(ass_text.rstrip() + "\n", encoding="utf-8")
    except OSError:
        return {}
    output_cues = list(canonical)
    profile_name = _subtitle_profile_name(language)
    return {
        "path": os.path.abspath(ass_output),
        "srt_path": os.path.abspath(srt_output),
        "cues": output_cues,
        "timeline_signature": subdub_canonical_cues.timeline_signature(output_cues),
        "profile": profile_name,
        "qc": {
            "status": "PASS",
            "renderer": "translation_v1_shared_autofit",
            "timeline_equal_to_source": True,
            "max_lines_pass": all(int(item.get("line_count") or 0) <= 2 for item in layouts),
            "frame_fit_pass": all(bool(item.get("fits_width")) for item in layouts),
            "blocking_failures": [],
        },
    }


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
        "subtitle_srt_path": "",
        "subtitle_cues": [],
        "subtitle_timeline_signature": [],
        "subtitle_profile": "",
        "subtitle_qc": {},
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
        data = dict(job or {})
        project = dict(data.get("project") or {})
        raw_asset_pack = data.get("asset_pack") or data.get("asset_pack_json") or project.get("asset_pack_json") or {}
        if isinstance(raw_asset_pack, str):
            try:
                raw_asset_pack = json.loads(raw_asset_pack)
            except (TypeError, ValueError):
                raw_asset_pack = {}
        asset_pack = dict(raw_asset_pack) if isinstance(raw_asset_pack, dict) else {}
        geometry = dict(asset_pack.get("output_geometry") or {})
        output_width = int(geometry.get("width") or data.get("output_width") or project.get("output_width") or 720)
        output_height = int(geometry.get("height") or data.get("output_height") or project.get("output_height") or 1280)
        subtitle_material = dict(plan.get("subtitle") or {})
        if not any(
            str(subtitle_material.get(key) or "").strip()
            for key in ("script_text", "text", "artifact_path")
        ):
            subtitle_material["script_text"] = _persisted_scene_subtitle_script(job)
        subtitle = _materialize_subtitle(
            subtitle_material,
            workspace=workspace,
            scene_count=scene_count,
            scene_duration=scene_duration,
            output_width=output_width,
            output_height=output_height,
        )
        if not subtitle.get("path"):
            return block("subtitle")
        result["subtitle_path"] = str(subtitle["path"])
        result["subtitle_srt_path"] = str(subtitle.get("srt_path") or "")
        result["subtitle_cues"] = list(subtitle.get("cues") or [])
        result["subtitle_timeline_signature"] = list(subtitle.get("timeline_signature") or [])
        result["subtitle_profile"] = str(subtitle.get("profile") or "")
        result["subtitle_qc"] = dict(subtitle.get("qc") or {})
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
