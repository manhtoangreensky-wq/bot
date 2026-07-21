from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Iterable


FRAME_VIDEO_MIN_IMAGES = 2
FRAME_VIDEO_MAX_IMAGES = 20

RATIOS: dict[str, tuple[int, int]] = {
    "9x16": (720, 1280),
    "16x9": (1280, 720),
    "1x1": (720, 720),
    "4x5": (720, 900),
}

FIT_MODES = {"contain", "crop", "blur", "color"}
TRANSITIONS = {"none", "fade", "dissolve", "slide", "zoom"}
MOTIONS = {"none", "zoom_in", "zoom_out", "pan_horizontal", "pan_vertical", "ken_burns"}

QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "label": "Nhanh",
        "long_edge": 1280,
        "fps": 24,
        "codec": "libx264",
        "crf": 28,
        "preset": "veryfast",
        "strength": "Xuất nhanh, file gọn",
        "limit": "Chi tiết chuyển động vừa phải",
    },
    "balanced": {
        "label": "Cân bằng",
        "long_edge": 1280,
        "fps": 30,
        "codec": "libx264",
        "crf": 23,
        "preset": "medium",
        "strength": "Cân bằng độ nét và thời gian dựng",
        "limit": "File lớn hơn chế độ Nhanh",
    },
    "beautiful": {
        "label": "Đẹp",
        "long_edge": 1920,
        "fps": 30,
        "codec": "libx264",
        "crf": 19,
        "preset": "slow",
        "strength": "Ưu tiên chi tiết, chữ và logo rõ",
        "limit": "Dựng lâu hơn và file lớn hơn",
    },
}

XFADE_TRANSITIONS = {
    "fade": "fade",
    "dissolve": "dissolve",
    "slide": "slideleft",
    "zoom": "zoomin",
}


def _clean_token(value: Any, fallback: str = "") -> str:
    value = str(value or "").strip().lower().replace(":", "x").replace("-", "_")
    return value or fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _stable_image_id(item: dict[str, Any], ordinal: int, salt: str = "") -> str:
    source = str(
        item.get("image_id")
        or item.get("file_unique_id")
        or item.get("file_id")
        or item.get("image_url")
        or item.get("url")
        or f"image-{ordinal}"
    )
    if str(item.get("image_id") or "").startswith("fvimg_") and not salt:
        return str(item["image_id"])
    digest = hashlib.sha256(f"{source}:{salt}".encode("utf-8")).hexdigest()[:14]
    return f"fvimg_{digest}"


def canonical_image_manifest(items: Iterable[Any], max_images: int = FRAME_VIDEO_MAX_IMAGES) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for ordinal, raw in enumerate(list(items or [])[: max(1, int(max_images or FRAME_VIDEO_MAX_IMAGES))], start=1):
        item = dict(raw) if isinstance(raw, dict) else {"file_id": str(raw or "")}
        if not any(str(item.get(key) or "").strip() for key in ("file_id", "image_url", "url")):
            continue
        image_id = _stable_image_id(item, ordinal)
        if image_id in used_ids:
            image_id = _stable_image_id(item, ordinal, salt=f"duplicate-{ordinal}")
        used_ids.add(image_id)
        manifest.append(
            {
                "image_id": image_id,
                "file_id": str(item.get("file_id") or "")[:500],
                "file_unique_id": str(item.get("file_unique_id") or "")[:200],
                "image_url": str(item.get("image_url") or item.get("url") or "")[:1500],
                "file_name": str(item.get("file_name") or "")[:240],
                "mime_type": str(item.get("mime_type") or "image/jpeg")[:120],
                "file_size": max(0, _safe_int(item.get("file_size"), 0)),
                "source": str(item.get("source") or "telegram")[:80],
                "caption": str(item.get("caption") or "")[:1000],
                "prompt": str(item.get("prompt") or "")[:4000],
                "model": str(item.get("model") or "")[:200],
                "tier": str(item.get("tier") or "")[:80],
                "ratio": str(item.get("ratio") or "")[:40],
                "image_job_id": max(0, _safe_int(item.get("image_job_id"), 0)),
                "delivery_message_id": max(0, _safe_int(item.get("delivery_message_id"), 0)),
                "receipt_key": str(item.get("receipt_key") or "")[:200],
                "ordinal": len(manifest) + 1,
                "is_cover": bool(item.get("is_cover")),
            }
        )
    if manifest and not any(item.get("is_cover") for item in manifest):
        manifest[0]["is_cover"] = True
    return manifest


def manifest_add(items: Iterable[Any], item: dict[str, Any], max_images: int = FRAME_VIDEO_MAX_IMAGES) -> list[dict[str, Any]]:
    manifest = canonical_image_manifest(items, max_images=max_images)
    if len(manifest) >= int(max_images or FRAME_VIDEO_MAX_IMAGES):
        raise ValueError("too_many_images")
    unique = str(item.get("file_unique_id") or item.get("file_id") or item.get("image_url") or "")
    if unique and any(unique in {str(row.get("file_unique_id") or ""), str(row.get("file_id") or ""), str(row.get("image_url") or "")} for row in manifest):
        return manifest
    return canonical_image_manifest([*manifest, item], max_images=max_images)


def manifest_delete(items: Iterable[Any], image_id: str) -> list[dict[str, Any]]:
    return canonical_image_manifest([row for row in canonical_image_manifest(items) if row.get("image_id") != image_id])


def manifest_replace(items: Iterable[Any], image_id: str, replacement: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = canonical_image_manifest(items)
    found = False
    updated: list[dict[str, Any]] = []
    for row in manifest:
        if row.get("image_id") != image_id:
            updated.append(row)
            continue
        found = True
        next_row = dict(replacement or {})
        next_row["image_id"] = image_id
        next_row["is_cover"] = bool(row.get("is_cover"))
        next_row["caption"] = str(row.get("caption") or "")
        updated.append(next_row)
    if not found:
        raise ValueError("image_not_found")
    return canonical_image_manifest(updated)


def manifest_duplicate(items: Iterable[Any], image_id: str) -> list[dict[str, Any]]:
    manifest = canonical_image_manifest(items)
    if len(manifest) >= FRAME_VIDEO_MAX_IMAGES:
        raise ValueError("too_many_images")
    source = next((dict(row) for row in manifest if row.get("image_id") == image_id), None)
    if not source:
        raise ValueError("image_not_found")
    source["image_id"] = _stable_image_id(source, len(manifest) + 1, salt=f"copy-{len(manifest) + 1}")
    source["is_cover"] = False
    return canonical_image_manifest([*manifest, source])


def manifest_move(items: Iterable[Any], image_id: str, direction: str) -> list[dict[str, Any]]:
    manifest = canonical_image_manifest(items)
    index = next((idx for idx, row in enumerate(manifest) if row.get("image_id") == image_id), -1)
    if index < 0:
        raise ValueError("image_not_found")
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(manifest):
        manifest[index], manifest[target] = manifest[target], manifest[index]
    return canonical_image_manifest(manifest)


def manifest_set_cover(items: Iterable[Any], image_id: str) -> list[dict[str, Any]]:
    manifest = canonical_image_manifest(items)
    if not any(row.get("image_id") == image_id for row in manifest):
        raise ValueError("image_not_found")
    for row in manifest:
        row["is_cover"] = row.get("image_id") == image_id
    return canonical_image_manifest(manifest)


def image_duration_map(state: dict[str, Any]) -> dict[str, float]:
    default = max(0.5, min(30.0, _safe_float(state.get("seconds_per_image"), 3.0)))
    raw = dict(state.get("image_durations") or {})
    return {
        row["image_id"]: max(0.5, min(30.0, _safe_float(raw.get(row["image_id"]), default)))
        for row in canonical_image_manifest(state.get("photos") or [])
    }


def transition_overlap_seconds(state: dict[str, Any]) -> float:
    transition = _clean_token(state.get("transition") or state.get("effect"), "fade")
    if transition in {"none", "cut", "natural"}:
        return 0.0
    durations = list(image_duration_map(state).values()) or [3.0]
    requested = max(0.1, min(1.5, _safe_float(state.get("transition_seconds"), 0.35)))
    return round(min(requested, max(0.1, min(durations) / 2.0)), 3)


def expected_duration_seconds(state: dict[str, Any]) -> float:
    durations = list(image_duration_map(state).values())
    if not durations:
        return 0.0
    overlap = transition_overlap_seconds(state)
    return round(sum(durations) - overlap * max(0, len(durations) - 1), 3)


def _ratio_dimensions(
    ratio: str,
    custom_width: Any = 0,
    custom_height: Any = 0,
) -> tuple[int, int]:
    token = _clean_token(ratio, "9x16")
    if token != "custom":
        return RATIOS.get(token, RATIOS["9x16"])
    try:
        width = max(100, min(4096, int(custom_width or 0)))
        height = max(100, min(4096, int(custom_height or 0)))
    except (TypeError, ValueError):
        return RATIOS["9x16"]
    width -= width % 2
    height -= height % 2
    if width < 100 or height < 100:
        return RATIOS["9x16"]
    return width, height


def quality_payload(
    token: str,
    ratio: str = "9x16",
    custom_width: Any = 0,
    custom_height: Any = 0,
) -> dict[str, Any]:
    quality = _clean_token(token, "balanced")
    if quality not in QUALITY_PRESETS:
        quality = "balanced"
    config = dict(QUALITY_PRESETS[quality])
    base_width, base_height = _ratio_dimensions(ratio, custom_width, custom_height)
    long_edge = int(config["long_edge"])
    scale = long_edge / max(base_width, base_height)
    width = max(2, int(round(base_width * scale / 2.0) * 2))
    height = max(2, int(round(base_height * scale / 2.0) * 2))
    config.update({"token": quality, "width": width, "height": height})
    return config


def canonical_config(state: dict[str, Any]) -> dict[str, Any]:
    ratio = _clean_token(state.get("ratio"), "9x16")
    if ratio not in {*RATIOS, "custom"}:
        ratio = "9x16"
    fit_mode = _clean_token(state.get("fit_mode"), "contain")
    if fit_mode not in FIT_MODES:
        fit_mode = "contain"
    transition = _clean_token(state.get("transition") or state.get("effect"), "fade")
    aliases = {"cut": "none", "natural": "none", "default": "fade"}
    transition = aliases.get(transition, transition)
    if transition not in TRANSITIONS:
        transition = "fade"
    motion = _clean_token(state.get("motion"), "none")
    if motion not in MOTIONS:
        motion = "none"
    quality = quality_payload(
        str(state.get("quality") or "balanced"),
        ratio,
        state.get("custom_width"),
        state.get("custom_height"),
    )
    config = {
        "ratio": ratio,
        "custom_width": _safe_int(state.get("custom_width"), 0),
        "custom_height": _safe_int(state.get("custom_height"), 0),
        "fit_mode": fit_mode,
        "background_color": _background_color(state.get("background_color")),
        "seconds_per_image": max(0.5, min(30.0, _safe_float(state.get("seconds_per_image"), 3.0))),
        "transition": transition,
        "transition_seconds": transition_overlap_seconds({**state, "transition": transition}),
        "motion": motion,
        "quality": quality,
    }
    config["duration_seconds"] = expected_duration_seconds({**state, **config})
    manifest = canonical_image_manifest(state.get("photos") or [])
    config["transition_manifest"] = [
        {
            "transition_id": f"fvtr_{left['image_id'][-8:]}_{right['image_id'][-8:]}",
            "from_image_id": left["image_id"],
            "to_image_id": right["image_id"],
            "type": transition,
            "duration_seconds": config["transition_seconds"],
        }
        for left, right in zip(manifest, manifest[1:])
    ]
    return config


def validate_plan(state: dict[str, Any]) -> dict[str, Any]:
    manifest = canonical_image_manifest(state.get("photos") or [])
    config = canonical_config({**state, "photos": manifest})
    errors: list[str] = []
    expected_image_count = max(0, _safe_int(state.get("image_count"), 0))
    if len(manifest) < FRAME_VIDEO_MIN_IMAGES:
        errors.append("not_enough_images")
    if len(manifest) > FRAME_VIDEO_MAX_IMAGES:
        errors.append("too_many_images")
    if (
        str(state.get("commercial_flow_version") or "") == "framevideo3"
        and expected_image_count >= FRAME_VIDEO_MIN_IMAGES
        and len(manifest) != expected_image_count
    ):
        errors.append("image_count_mismatch")
    if config["duration_seconds"] <= 0:
        errors.append("invalid_duration")
    return {
        "ok": not errors,
        "errors": errors,
        "manifest": manifest,
        "config": config,
        "expected_image_count": expected_image_count,
        "received_image_count": len(manifest),
    }


def _escape_drawtext(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "").strip())[:500]
    return value.replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'").replace("%", r"\%")


def _position_xy(position: str, margin: int = 36) -> tuple[str, str]:
    token = _clean_token(position, "bottom_center")
    horizontal = "(w-text_w)/2"
    vertical = "(h-text_h)/2"
    if token.endswith("left"):
        horizontal = str(margin)
    elif token.endswith("right"):
        horizontal = f"w-text_w-{margin}"
    if token.startswith("top"):
        vertical = str(margin)
    elif token.startswith("bottom"):
        vertical = f"h-text_h-{margin}"
    return horizontal, vertical


def _drawtext_color(value: Any, fallback: str) -> str:
    token = str(value or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}(?:@[0-9.]+)?", token):
        return token
    if re.fullmatch(r"[a-z]{3,16}(?:@[0-9.]+)?", token):
        return token
    return fallback


def _background_color(value: Any, fallback: str = "#111111") -> str:
    token = str(value or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", token):
        return token
    if re.fullmatch(r"[a-z]{3,16}", token):
        return token
    return fallback


def _fit_filter(input_label: str, output_label: str, width: int, height: int, fit_mode: str, color: str, fps: int) -> list[str]:
    if fit_mode == "crop":
        return [
            f"{input_label}scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps}{output_label}"
        ]
    if fit_mode == "blur":
        suffix = output_label.strip("[]")
        return [
            f"{input_label}split=2[bg_{suffix}][fg_{suffix}]",
            f"[bg_{suffix}]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=24:8[blur_{suffix}]",
            f"[fg_{suffix}]scale={width}:{height}:force_original_aspect_ratio=decrease[fit_{suffix}]",
            f"[blur_{suffix}][fit_{suffix}]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={fps}{output_label}",
        ]
    return [
        f"{input_label}scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={color},setsar=1,fps={fps}{output_label}"
    ]


def _motion_filter(input_label: str, output_label: str, width: int, height: int, fps: int, motion: str, duration: float) -> str:
    frames = max(1, int(math.ceil(duration * fps)))
    if motion == "zoom_in":
        expr = "z='min(zoom+0.0015,1.10)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
    elif motion == "zoom_out":
        expr = "z='if(eq(on,1),1.10,max(1.0,zoom-0.0015))':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
    elif motion == "pan_horizontal":
        expr = f"z=1.08:x='(iw-iw/zoom)*on/{max(1, frames - 1)}':y='ih/2-ih/zoom/2'"
    elif motion == "pan_vertical":
        expr = f"z=1.08:x='iw/2-iw/zoom/2':y='(ih-ih/zoom)*on/{max(1, frames - 1)}'"
    elif motion == "ken_burns":
        expr = f"z='min(zoom+0.0012,1.10)':x='(iw-iw/zoom)*on/{max(1, frames - 1)}':y='ih/2-ih/zoom/2'"
    else:
        return f"{input_label}trim=duration={duration:.3f},setpts=PTS-STARTPTS{output_label}"
    return (
        f"{input_label}zoompan={expr}:d=1:s={width}x{height}:fps={fps},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS{output_label}"
    )


@dataclass(frozen=True)
class FrameVideoCommand:
    command: list[str]
    expected_duration: float
    expects_audio: bool


def build_ffmpeg_command(
    image_paths: list[str],
    output_path: str,
    state: dict[str, Any],
    *,
    ffmpeg_path: str = "",
    music_path: str = "",
    voice_path: str = "",
    logo_path: str = "",
) -> FrameVideoCommand:
    plan = validate_plan({**state, "photos": state.get("photos") or [{"file_id": path} for path in image_paths]})
    if len(image_paths) != len(plan["manifest"]):
        raise ValueError("image_manifest_path_mismatch")
    if not plan["ok"]:
        raise ValueError(",".join(plan["errors"]))
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
    config = plan["config"]
    quality = config["quality"]
    width, height, fps = int(quality["width"]), int(quality["height"]), int(quality["fps"])
    durations_by_id = image_duration_map({**state, "photos": plan["manifest"]})
    durations = [durations_by_id[row["image_id"]] for row in plan["manifest"]]
    command = [ffmpeg, "-y"]
    for duration, path in zip(durations, image_paths):
        command.extend(["-loop", "1", "-t", f"{duration:.3f}", "-i", path])
    logo_index = None
    if logo_path:
        logo_index = len(image_paths)
        command.extend(["-loop", "1", "-i", logo_path])
    audio_indices: list[tuple[str, int]] = []
    if music_path:
        audio_indices.append(("music", len(image_paths) + (1 if logo_path else 0) + len(audio_indices)))
        command.extend(["-stream_loop", "-1", "-i", music_path])
    if voice_path:
        audio_indices.append(("voice", len(image_paths) + (1 if logo_path else 0) + len(audio_indices)))
        command.extend(["-i", voice_path])

    filters: list[str] = []
    for idx, duration in enumerate(durations):
        fit_label = f"[fit{idx}]"
        filters.extend(_fit_filter(f"[{idx}:v]", fit_label, width, height, config["fit_mode"], config["background_color"], fps))
        filters.append(_motion_filter(fit_label, f"[v{idx}]", width, height, fps, config["motion"], duration))

    overlap = float(config["transition_seconds"])
    if len(image_paths) == 1:
        video_label = "[v0]"
    elif config["transition"] == "none" or overlap <= 0:
        filters.append("".join(f"[v{idx}]" for idx in range(len(image_paths))) + f"concat=n={len(image_paths)}:v=1:a=0[vcat]")
        video_label = "[vcat]"
    else:
        transition = XFADE_TRANSITIONS[config["transition"]]
        previous = "[v0]"
        cumulative = durations[0]
        for idx in range(1, len(image_paths)):
            output = f"[vx{idx}]"
            offset = max(0.0, cumulative - overlap * idx)
            filters.append(f"{previous}[v{idx}]xfade=transition={transition}:duration={overlap:.3f}:offset={offset:.3f}{output}")
            previous = output
            cumulative += durations[idx]
        video_label = previous

    text_filters: list[str] = []
    for item in list(state.get("text_overlays") or [])[:30]:
        content = _escape_drawtext(str((item or {}).get("content") or ""))
        if not content:
            continue
        start = max(0.0, _safe_float((item or {}).get("start_seconds"), 0.0))
        end = min(
            _safe_float(config.get("duration_seconds"), 0.0),
            max(
                start + 0.1,
                _safe_float((item or {}).get("end_seconds"), _safe_float(config.get("duration_seconds"), 0.0)),
            ),
        )
        x, y = _position_xy(str((item or {}).get("position") or "bottom_center"))
        size = max(18, min(84, _safe_int((item or {}).get("font_size"), max(22, width // 28))))
        font_color = _drawtext_color((item or {}).get("font_color"), "white")
        box_color = _drawtext_color((item or {}).get("box_color"), "black@0.28")
        animation = _clean_token((item or {}).get("animation"), "none")
        alpha = "1"
        if animation == "fade":
            alpha = f"if(lt(t,{start + 0.25:.3f}),(t-{start:.3f})/0.25,if(gt(t,{end - 0.25:.3f}),({end:.3f}-t)/0.25,1))"
        elif animation == "slide":
            x = f"if(lt(t,{start + 0.35:.3f}),w-(w-({x}))*(t-{start:.3f})/0.35,{x})"
        text_filters.append(
            "drawtext="
            f"text='{content}':fontcolor={font_color}:fontsize={size}:borderw=2:bordercolor=black@0.8:"
            f"box=1:boxcolor={box_color}:boxborderw=12:x={x}:y={y}:alpha='{alpha}':enable='between(t,{start:.3f},{end:.3f})'"
        )
    watermark = _escape_drawtext(str(state.get("watermark_text") or ""))
    if watermark:
        x, y = _position_xy(str(state.get("watermark_position") or "top_right"), margin=28)
        text_filters.append(
            f"drawtext=text='{watermark}':fontcolor=white@0.68:fontsize={max(18, width // 34)}:borderw=1:bordercolor=black@0.45:x={x}:y={y}"
        )
    if text_filters:
        filters.append(f"{video_label}{','.join(text_filters)}[vtext]")
        video_label = "[vtext]"

    if logo_index is not None:
        logo_width = max(48, int(width * max(0.04, min(0.18, _safe_float(state.get("logo_width_ratio"), 0.12)))))
        filters.append(f"[{logo_index}:v]scale={logo_width}:-1[logo]")
        position = str(state.get("logo_position") or "top_right")
        x, y = _position_xy(position, margin=max(16, int(width * 0.03)))
        x = x.replace("text_w", "overlay_w").replace("w-", "W-")
        y = y.replace("text_h", "overlay_h").replace("h-", "H-")
        filters.append(f"{video_label}[logo]overlay=x={x}:y={y}:format=auto[vlogo]")
        video_label = "[vlogo]"

    filters.append(f"{video_label}format=yuv420p[vout]")
    expected_duration = float(config["duration_seconds"])
    audio_labels: list[str] = []
    for kind, index in audio_indices:
        volume = max(
            0,
            min(200, _safe_int(state.get(f"{kind}_volume_percent"), 35 if kind == "music" else 100)),
        ) / 100.0
        fade = max(0.0, min(2.0, _safe_float(state.get(f"{kind}_fade_seconds"), 0.35)))
        label = f"[a_{kind}]"
        filters.append(
            f"[{index}:a]volume={volume:.2f},atrim=0:{expected_duration:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade:.3f},afade=t=out:st={max(0.0, expected_duration - fade):.3f}:d={fade:.3f}{label}"
        )
        audio_labels.append(label)
    if len(audio_labels) > 1:
        filters.append("".join(audio_labels) + f"amix=inputs={len(audio_labels)}:duration=longest:dropout_transition=0,alimiter=limit=0.95,atrim=0:{expected_duration:.3f}[aout]")
    elif audio_labels:
        filters.append(f"{audio_labels[0]}alimiter=limit=0.95,atrim=0:{expected_duration:.3f}[aout]")

    command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])
    if audio_labels:
        command.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    else:
        command.append("-an")
    command.extend(
        [
            "-r",
            str(fps),
            "-c:v",
            str(quality["codec"]),
            "-preset",
            str(quality["preset"]),
            "-crf",
            str(quality["crf"]),
            "-pix_fmt",
            "yuv420p",
            "-t",
            f"{expected_duration:.3f}",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )
    return FrameVideoCommand(command=command, expected_duration=expected_duration, expects_audio=bool(audio_labels))


def probe_mp4(path: str, expected_duration: float, expects_audio: bool = False, ffprobe_path: str = "") -> dict[str, Any]:
    ffprobe = ffprobe_path or shutil.which("ffprobe") or "ffprobe"
    if not path or not os.path.exists(path) or os.path.getsize(path) <= 0:
        return {"ok": False, "reason": "artifact_missing", "path": str(path or "")}
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=index,codec_type,codec_name,width,height",
        "-of",
        "json",
        path,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except Exception as exc:
        return {"ok": False, "reason": f"ffprobe_{type(exc).__name__}"}
    if completed.returncode != 0:
        return {"ok": False, "reason": "ffprobe_failed", "detail": (completed.stderr or completed.stdout or "")[-500:]}
    try:
        payload = json.loads(completed.stdout or "{}")
    except Exception:
        return {"ok": False, "reason": "ffprobe_invalid_json"}
    streams = list(payload.get("streams") or [])
    video_streams = [row for row in streams if row.get("codec_type") == "video"]
    audio_streams = [row for row in streams if row.get("codec_type") == "audio"]
    duration = _safe_float((payload.get("format") or {}).get("duration"), 0.0)
    expected = _safe_float(expected_duration, 0.0)
    delta = abs(duration - expected)
    reason = "ok"
    if not video_streams:
        reason = "video_stream_missing"
    elif expects_audio and not audio_streams:
        reason = "audio_stream_missing"
    elif expected > 0 and delta > 0.35:
        reason = "duration_mismatch"
    return {
        "ok": reason == "ok",
        "reason": reason,
        "duration_seconds": round(duration, 3),
        "expected_duration_seconds": round(expected, 3),
        "duration_delta_seconds": round(delta, 3),
        "size_bytes": int((payload.get("format") or {}).get("size") or os.path.getsize(path)),
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "video_codec": str((video_streams[0] if video_streams else {}).get("codec_name") or ""),
        "width": int((video_streams[0] if video_streams else {}).get("width") or 0),
        "height": int((video_streams[0] if video_streams else {}).get("height") or 0),
        "ffprobe_command": command,
    }
