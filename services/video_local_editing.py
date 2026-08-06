"""Local-only manual video editing and split execution.

The module builds argument arrays and invokes FFmpeg without a shell.  It has
no provider, Telegram, database, or wallet dependency.
"""

from __future__ import annotations

import os
import re
import subprocess
import math
import threading
import time
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Iterable

from services import ffmpeg_text

from services.video_local_validation import (
    FFMPEG_TIMEOUT_SECONDS,
    LocalVideoValidationError,
    enforce_workspace_limit,
    find_ffmpeg,
    find_ffprobe,
    path_is_within,
    probe_video_file,
    require_path_within,
    validate_mp4_output,
    validate_srt_file,
)
from services.video_smart_splitter import (
    MAX_SPLIT_PARTS,
    MIN_SEGMENT_MS,
    SplitRange,
    split_output_name,
    validate_exact_coverage,
)


ASPECT_RATIOS = {"keep", "16:9", "9:16", "1:1", "4:5"}
RESOLUTION_PRESETS = {"keep", "720p", "1080p"}
ROTATIONS = {0, 90, 180, 270}
FLIP_MODES = {"none", "horizontal", "vertical"}
SPEED_PRESETS = {0.5, 0.75, 1.0, 1.25, 1.5, 2.0}
VOLUME_PRESETS = {0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5, 2.0}
COLOR_PRESETS = {
    "keep": "",
    "bright_clear": "eq=brightness=0.025:contrast=1.06:saturation=1.06,unsharp=5:5:0.45:5:5:0.0",
    "light_cinematic": "eq=brightness=-0.01:contrast=1.12:saturation=0.93:gamma=0.98",
    "warm": "colorbalance=rs=0.06:gs=0.015:bs=-0.04:rm=0.06:gm=0.015:bm=-0.04:rh=0.06:gh=0.015:bh=-0.04",
    "cool": "colorbalance=rs=-0.04:gs=0.01:bs=0.06:rm=-0.04:gm=0.01:bm=0.06:rh=-0.04:gh=0.01:bh=0.06",
    "high_contrast": "eq=contrast=1.25:saturation=1.05",
    "black_white": "hue=s=0,eq=contrast=1.08",
    "soft_clean": "hqdn3d=1.0:1.0:3.0:3.0,eq=brightness=0.01:contrast=1.03:saturation=0.98,unsharp=5:5:0.18:5:5:0.0",
}
OVERLAY_POSITIONS = {
    "top_left", "top_center", "top_right",
    "center_left", "center", "center_right",
    "bottom_left", "bottom_center", "bottom_right",
}
# Earlier edit plans used three vertical-only text labels. Keep those plans
# valid, then normalize them to the same 3x3 placement contract as logos.
TEXT_POSITIONS = OVERLAY_POSITIONS | {"top", "bottom"}
LOGO_POSITIONS = set(OVERLAY_POSITIONS)
AUDIO_NORMALIZATION_MODES = {"off", "loudnorm"}
QUALITY_FILTER_KEYS = {"sharpen", "denoise"}
LOCAL_EFFECT_KEYS = {"fade_in_ms", "fade_out_ms", "vignette", "slow_zoom"}


class LocalVideoEditError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def normalize_callback_plan_choice(kind: Any, value: Any) -> tuple[str, Any]:
    """Validate one public ``videoedit|set`` value before state mutation."""
    key = str(kind or "").strip().lower()
    token = str(value or "").strip().lower()
    try:
        if key == "aspect":
            normalized = token.replace("x", ":")
            if normalized not in ASPECT_RATIOS:
                raise ValueError
            return key, normalized
        if key == "aspect_mode":
            if token not in {"crop", "fit"}:
                raise ValueError
            return key, token
        if key == "resolution":
            if token not in RESOLUTION_PRESETS:
                raise ValueError
            return key, token
        if key == "rotation":
            if not re.fullmatch(r"\d{1,3}", token):
                raise ValueError
            rotation = int(token)
            if rotation not in ROTATIONS:
                raise ValueError
            return key, rotation
        if key == "flip":
            if token not in FLIP_MODES:
                raise ValueError
            return key, token
        if key in {"speed", "volume", "logo_opacity"}:
            number = float(token)
            if not math.isfinite(number):
                raise ValueError
            if key == "speed" and number not in SPEED_PRESETS:
                raise ValueError
            if key == "volume" and number not in VOLUME_PRESETS:
                raise ValueError
            if key == "logo_opacity" and not 0.1 <= number <= 1.0:
                raise ValueError
            return key, number
        if key == "color_preset":
            if token not in COLOR_PRESETS:
                raise ValueError
            return key, token
        if key == "logo_position":
            if token not in LOGO_POSITIONS:
                raise ValueError
            return key, token
    except (TypeError, ValueError, OverflowError) as exc:
        raise LocalVideoEditError("callback_choice_invalid") from exc
    raise LocalVideoEditError("callback_choice_invalid")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _strict_number(value: Any, *, reason: str) -> float:
    if isinstance(value, bool):
        raise LocalVideoEditError(reason)
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LocalVideoEditError(reason) from exc
    if not math.isfinite(parsed):
        raise LocalVideoEditError(reason)
    return parsed


def _strict_integer(value: Any, *, reason: str) -> int:
    if isinstance(value, bool):
        raise LocalVideoEditError(reason)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise LocalVideoEditError(reason)
        return int(value)
    token = str(value or "").strip()
    if not re.fullmatch(r"[+-]?\d+", token):
        raise LocalVideoEditError(reason)
    try:
        return int(token)
    except (TypeError, ValueError, OverflowError) as exc:
        raise LocalVideoEditError(reason) from exc


def _safe_text(value: Any, maximum: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:maximum]


def _canonical_overlay_position(value: Any, default: str) -> str:
    token = str(value or default).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "top": "top_center",
        "bottom": "bottom_center",
        "middle": "center",
        "middle_left": "center_left",
        "middle_right": "center_right",
    }
    token = aliases.get(token, token)
    return token if token in OVERLAY_POSITIONS else default


def _overlay_xy(
    position: Any,
    *,
    frame_width: str,
    frame_height: str,
    overlay_width: str,
    overlay_height: str,
    margin_x: str,
    margin_y: str,
    default: str,
) -> tuple[str, str]:
    """Return FFmpeg expressions for a canonical 3x3 overlay position."""
    token = _canonical_overlay_position(position, default)
    x = f"({frame_width}-{overlay_width})/2"
    y = f"({frame_height}-{overlay_height})/2"
    if token.endswith("_left"):
        x = margin_x
    elif token.endswith("_right"):
        x = f"{frame_width}-{overlay_width}-{margin_x}"
    if token.startswith("top_"):
        y = margin_y
    elif token.startswith("bottom_"):
        y = f"{frame_height}-{overlay_height}-{margin_y}"
    return x, y


def default_manual_edit_plan(input_video: str = "") -> dict[str, Any]:
    return {
        "input_video": str(input_video or ""),
        "concat_inputs": [],
        "trim": {"start_ms": 0, "end_ms": 0},
        "crop_or_fit": {"aspect_ratio": "keep", "mode": "fit"},
        "resolution": "keep",
        "rotation": 0,
        "flip": "none",
        "speed": 1.0,
        "volume": 1.0,
        "brightness_percent": 100,
        "text_overlay": {},
        "logo_overlay": {},
        "subtitle_file": "",
        "color_preset": "keep",
        "audio_normalization": "off",
        "quality_filters": {"sharpen": False, "denoise": False},
        "local_effects": {
            "fade_in_ms": 0,
            "fade_out_ms": 0,
            "vignette": False,
            "slow_zoom": False,
        },
        "remove_middle": {},
        "output_format": "mp4",
    }


def neutral_split_manual_plan() -> dict[str, Any]:
    """Return the one duration-independent manual-plan identity for Split."""

    return default_manual_edit_plan("")


def _is_neutral_plan_subset(value: Any, neutral: Any) -> bool:
    """Accept sparse JSON representations only when every value is neutral."""

    if isinstance(neutral, dict):
        if not isinstance(value, dict) or not set(value).issubset(neutral):
            return False
        return all(
            _is_neutral_plan_subset(item, neutral[key])
            for key, item in value.items()
        )
    if isinstance(neutral, list):
        return isinstance(value, list) and value == neutral
    if isinstance(neutral, bool):
        return isinstance(value, bool) and value is neutral
    if isinstance(neutral, (int, float)) and isinstance(value, bool):
        return False
    return value == neutral


_MANUAL_PLAN_NESTED_FIELDS: dict[str, frozenset[str]] = {
    "trim": frozenset({"start_ms", "end_ms"}),
    "crop_or_fit": frozenset({"aspect_ratio", "mode"}),
    "quality_filters": frozenset(QUALITY_FILTER_KEYS),
    "local_effects": frozenset(LOCAL_EFFECT_KEYS),
    "remove_middle": frozenset({"start_ms", "end_ms"}),
    "text_overlay": frozenset(
        {"content", "position", "start_ms", "end_ms", "font_size", "outline", "font_path"}
    ),
    "logo_overlay": frozenset({"path", "position", "scale", "opacity"}),
}


def _manual_plan_has_unknown_nested_fields(plan: dict[str, Any]) -> bool:
    """Fail closed when a destructive transition sees an unknown nested field."""

    for field, allowed in _MANUAL_PLAN_NESTED_FIELDS.items():
        value = plan.get(field)
        if value in (None, {}):
            continue
        if not isinstance(value, dict) or set(value) - set(allowed):
            return True
    return False


def _collection_has_any_item(value: Any) -> bool:
    """Treat every supplied item, including ``None``, as an occupied asset slot."""

    if value is None:
        return False
    if isinstance(value, (str, bytes, bytearray, dict)):
        return bool(value)
    try:
        return bool(tuple(value))
    except TypeError:
        return bool(value)


def manual_plan_requires_split_reset(
    plan: dict[str, Any] | None,
    *,
    source_duration_ms: int = 0,
    concat_sources: Iterable[Any] | None = None,
    logo_source: Any = None,
    subtitle_source: Any = None,
) -> bool:
    """Return whether entering Split would discard real manual work."""

    if not isinstance(plan, dict):
        return True
    if set(plan) - set(default_manual_edit_plan()):
        return True
    if _manual_plan_has_unknown_nested_fields(plan):
        return True
    has_concat = _collection_has_any_item(concat_sources)
    return bool(
        plan_has_effective_operation(
            plan,
            source_duration_ms=max(0, int(source_duration_ms or 0)),
        )
        or has_concat
        or bool(logo_source)
        or bool(subtitle_source)
    )


def manual_plan_assets_match(
    plan: dict[str, Any] | None,
    *,
    concat_sources: Any,
    logo_source: Any,
    subtitle_source: Any,
) -> bool:
    """Bind every manual asset operation to exactly one Telegram asset record."""

    if not isinstance(plan, dict) or not isinstance(concat_sources, list):
        return False
    if not isinstance(logo_source, dict) or not isinstance(subtitle_source, dict):
        return False
    concat_inputs = plan.get("concat_inputs") or []
    if not isinstance(concat_inputs, list):
        return False
    if any(not isinstance(item, str) or not item.strip() for item in concat_inputs):
        return False
    if len(concat_inputs) != len(concat_sources):
        return False
    logo_plan = plan.get("logo_overlay") or {}
    if not isinstance(logo_plan, dict):
        return False
    if bool(logo_plan) != bool(str(logo_source.get("file_id") or "").strip()):
        return False
    subtitle_plan = plan.get("subtitle_file") or ""
    if not isinstance(subtitle_plan, str):
        return False
    if bool(subtitle_plan.strip()) != bool(
        str(subtitle_source.get("file_id") or "").strip()
    ):
        return False
    return True


def plan_has_effective_operation(
    plan: dict[str, Any] | None,
    *,
    source_duration_ms: int = 0,
    split_ranges: Iterable[Any] | None = None,
) -> bool:
    """Return whether a plan requests an observable local edit.

    A syntactically valid default plan is not an edit.  Keeping this check in
    the local contract prevents a canonical job from entering FFmpeg as a
    no-op while still allowing the conversational editor to collect fields
    incrementally.
    """

    try:
        current = dict(plan or {})
    except (TypeError, ValueError):
        return False
    ranges = [item for item in (split_ranges or ()) if item is not None]
    if ranges:
        if len(ranges) == 1 and int(source_duration_ms or 0) > 0:
            item = ranges[0]
            start = item.get("start_ms") if isinstance(item, dict) else getattr(item, "start_ms", None)
            end = item.get("end_ms") if isinstance(item, dict) else getattr(item, "end_ms", None)
            try:
                if int(start) == 0 and int(end) == int(source_duration_ms):
                    return False
            except (TypeError, ValueError, OverflowError):
                return False
        return True
    trim = current.get("trim") if isinstance(current.get("trim"), dict) else {}
    start_ms = _integer(trim.get("start_ms"), 0)
    end_ms = _integer(trim.get("end_ms"), 0)
    duration = max(0, int(source_duration_ms or 0))
    if start_ms > 0 or (end_ms > 0 and (duration <= 0 or end_ms < duration)):
        return True
    remove_middle = current.get("remove_middle") if isinstance(current.get("remove_middle"), dict) else {}
    if remove_middle.get("start_ms") is not None and remove_middle.get("end_ms") is not None:
        return True
    if current.get("concat_inputs"):
        return True
    crop = current.get("crop_or_fit") if isinstance(current.get("crop_or_fit"), dict) else {}
    if str(crop.get("aspect_ratio") or "keep") != "keep":
        return True
    if str(current.get("resolution") or "keep") != "keep":
        return True
    if _integer(current.get("rotation"), 0) or str(current.get("flip") or "none") != "none":
        return True
    if _number(current.get("speed"), 1.0) != 1.0:
        return True
    if _number(current.get("volume"), 1.0) != 1.0:
        return True
    if _integer(current.get("brightness_percent"), 100) != 100:
        return True
    if str(current.get("color_preset") or "keep") != "keep":
        return True
    if str(current.get("audio_normalization") or "off") != "off":
        return True
    quality = current.get("quality_filters") if isinstance(current.get("quality_filters"), dict) else {}
    if any(bool(quality.get(key)) for key in QUALITY_FILTER_KEYS):
        return True
    effects = current.get("local_effects") if isinstance(current.get("local_effects"), dict) else {}
    if any(bool(effects.get(key)) or _integer(effects.get(key), 0) > 0 for key in LOCAL_EFFECT_KEYS):
        return True
    if current.get("text_overlay") or current.get("logo_overlay") or current.get("subtitle_file"):
        return True
    return False


def manual_plan_has_effect(
    plan: dict[str, Any] | None,
    *,
    source_duration_ms: int = 0,
    split_ranges: Iterable[Any] | None = None,
) -> bool:
    """Backward-compatible public name for the no-op guard."""

    return plan_has_effective_operation(
        plan,
        source_duration_ms=source_duration_ms,
        split_ranges=split_ranges,
    )


def split_plan_has_manual_conflict(
    plan: dict[str, Any] | None,
    *,
    source_duration_ms: int = 0,
    concat_sources: Iterable[Any] | None = None,
    logo_source: Any = None,
    subtitle_source: Any = None,
) -> bool:
    """Reject a Split payload that also carries an independent manual edit.

    Split is a separate execution plan: it keeps source audio and only emits
    the selected ranges.  Manual operations/assets must be explicitly reset
    before entering that plan so neither the bot nor a forged worker payload
    can silently combine two different products.
    """

    del source_duration_ms  # Split neutrality must never depend on probe rounding.
    has_concat = _collection_has_any_item(concat_sources)
    return bool(
        not _is_neutral_plan_subset(plan, neutral_split_manual_plan())
        or has_concat
        or bool(logo_source)
        or bool(subtitle_source)
    )


def normalize_manual_edit_plan(
    plan: dict[str, Any] | None,
    *,
    source_duration_ms: int,
    workspace: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    source_duration_ms = max(0, int(source_duration_ms or 0))
    if source_duration_ms <= 0:
        raise LocalVideoEditError("source_duration_invalid")
    try:
        requested = dict(plan or {})
    except (TypeError, ValueError) as exc:
        raise LocalVideoEditError("edit_plan_invalid") from exc
    allowed_fields = set(default_manual_edit_plan())
    unknown_fields = sorted(set(requested) - allowed_fields)
    if unknown_fields:
        raise LocalVideoEditError(f"unknown_edit_plan_field:{unknown_fields[0]}")
    raw = {**default_manual_edit_plan(), **requested}
    source = str(raw.get("input_video") or "").strip()
    if not source:
        raise LocalVideoEditError("input_video_missing")
    if workspace is not None:
        try:
            require_path_within(source, workspace)
        except LocalVideoValidationError as exc:
            raise LocalVideoEditError(exc.reason) from exc
    concat_inputs = [str(item or "").strip() for item in raw.get("concat_inputs") or [] if str(item or "").strip()]
    if len(concat_inputs) > 9:
        raise LocalVideoEditError("concat_input_limit")
    if workspace is not None:
        for item in concat_inputs:
            try:
                require_path_within(item, workspace)
            except LocalVideoValidationError as exc:
                raise LocalVideoEditError(exc.reason) from exc
    try:
        trim = dict(raw.get("trim") or {})
    except (TypeError, ValueError) as exc:
        raise LocalVideoEditError("trim_range_invalid") from exc
    if set(trim) - {"start_ms", "end_ms"}:
        raise LocalVideoEditError("trim_range_invalid")
    start_ms = _strict_integer(trim.get("start_ms", 0), reason="trim_range_invalid")
    end_ms = _strict_integer(trim.get("end_ms", 0), reason="trim_range_invalid") or source_duration_ms
    if start_ms < 0:
        raise LocalVideoEditError("trim_range_invalid")
    if start_ms >= end_ms or end_ms > source_duration_ms:
        raise LocalVideoEditError("trim_range_invalid")
    try:
        crop = dict(raw.get("crop_or_fit") or {})
    except (TypeError, ValueError) as exc:
        raise LocalVideoEditError("crop_mode_invalid") from exc
    if set(crop) - {"aspect_ratio", "mode"}:
        raise LocalVideoEditError("crop_mode_invalid")
    aspect = str(crop.get("aspect_ratio") or "keep").strip().lower()
    mode = str(crop.get("mode") or "fit").strip().lower()
    if aspect not in ASPECT_RATIOS:
        raise LocalVideoEditError("aspect_ratio_invalid")
    if mode not in {"crop", "fit"}:
        raise LocalVideoEditError("crop_mode_invalid")
    resolution = str(raw.get("resolution") or "keep").strip().lower()
    if resolution not in RESOLUTION_PRESETS:
        raise LocalVideoEditError("resolution_invalid")
    rotation = _strict_integer(raw.get("rotation"), reason="rotation_invalid")
    if rotation not in ROTATIONS:
        raise LocalVideoEditError("rotation_invalid")
    flip = str(raw.get("flip") or "none").strip().lower()
    if flip not in FLIP_MODES:
        raise LocalVideoEditError("flip_invalid")
    speed = _strict_number(raw.get("speed"), reason="speed_invalid")
    if speed not in SPEED_PRESETS:
        raise LocalVideoEditError("speed_invalid")
    volume = _strict_number(raw.get("volume"), reason="volume_invalid")
    if not 0.0 <= volume <= 2.0:
        raise LocalVideoEditError("volume_invalid")
    brightness_percent = _strict_integer(raw.get("brightness_percent"), reason="brightness_invalid")
    if not 20 <= brightness_percent <= 200:
        raise LocalVideoEditError("brightness_invalid")
    color = str(raw.get("color_preset") or "keep").strip().lower()
    if color not in COLOR_PRESETS:
        raise LocalVideoEditError("color_preset_invalid")
    audio_normalization = str(raw.get("audio_normalization") or "off").strip().lower()
    if audio_normalization not in AUDIO_NORMALIZATION_MODES:
        raise LocalVideoEditError("audio_normalization_invalid")
    try:
        quality = dict(raw.get("quality_filters") or {})
    except (TypeError, ValueError) as exc:
        raise LocalVideoEditError("quality_filter_invalid") from exc
    if set(quality) - QUALITY_FILTER_KEYS or any(type(quality.get(key, False)) is not bool for key in QUALITY_FILTER_KEYS):
        raise LocalVideoEditError("quality_filter_invalid")
    quality = {key: bool(quality.get(key, False)) for key in ("sharpen", "denoise")}
    try:
        effects = dict(raw.get("local_effects") or {})
    except (TypeError, ValueError) as exc:
        raise LocalVideoEditError("local_effect_invalid") from exc
    if set(effects) - LOCAL_EFFECT_KEYS:
        raise LocalVideoEditError("local_effect_invalid")
    if any(type(effects.get(key, False)) is not bool for key in ("vignette", "slow_zoom")):
        raise LocalVideoEditError("local_effect_invalid")
    fade_in_ms = _strict_integer(effects.get("fade_in_ms", 0), reason="local_effect_duration_invalid")
    fade_out_ms = _strict_integer(effects.get("fade_out_ms", 0), reason="local_effect_duration_invalid")
    if fade_in_ms < 0 or fade_out_ms < 0:
        raise LocalVideoEditError("local_effect_duration_invalid")
    remove_middle_raw = raw.get("remove_middle") or {}
    try:
        remove_middle = dict(remove_middle_raw)
    except (TypeError, ValueError) as exc:
        raise LocalVideoEditError("remove_middle_invalid") from exc
    if remove_middle:
        if set(remove_middle) != {"start_ms", "end_ms"}:
            raise LocalVideoEditError("remove_middle_invalid")
        remove_start_ms = _strict_integer(
            remove_middle.get("start_ms"), reason="remove_middle_invalid"
        )
        remove_end_ms = _strict_integer(
            remove_middle.get("end_ms"), reason="remove_middle_invalid"
        )
        if not (start_ms < remove_start_ms < remove_end_ms < end_ms):
            raise LocalVideoEditError("remove_middle_invalid")
        remove_middle = {"start_ms": remove_start_ms, "end_ms": remove_end_ms}
    selected_after_removal_ms = end_ms - start_ms
    if remove_middle:
        selected_after_removal_ms -= int(remove_middle["end_ms"]) - int(remove_middle["start_ms"])
    post_speed_duration_ms = max(1, int(round(selected_after_removal_ms / speed)))
    if not concat_inputs and (
        fade_in_ms >= post_speed_duration_ms
        or fade_out_ms >= post_speed_duration_ms
        or fade_in_ms + fade_out_ms > post_speed_duration_ms
    ):
        raise LocalVideoEditError("local_effect_duration_invalid")
    effects = {
        "fade_in_ms": fade_in_ms,
        "fade_out_ms": fade_out_ms,
        "vignette": bool(effects.get("vignette", False)),
        "slow_zoom": bool(effects.get("slow_zoom", False)),
    }
    try:
        text = dict(raw.get("text_overlay") or {})
    except (TypeError, ValueError) as exc:
        raise LocalVideoEditError("text_overlay_invalid") from exc
    if text:
        content = _safe_text(text.get("content"), 260)
        requested_position = str(text.get("position") or "bottom").strip().lower()
        position = _canonical_overlay_position(requested_position, "bottom_center")
        start = _strict_integer(
            text.get("start_ms", 0), reason="text_overlay_invalid"
        )
        end = _strict_integer(
            text.get("end_ms", 0), reason="text_overlay_invalid"
        ) or end_ms - start_ms
        font_size = _strict_integer(
            text.get("font_size", 42), reason="text_overlay_invalid"
        )
        outline = _strict_integer(
            text.get("outline", 2), reason="text_overlay_invalid"
        )
        if (
            not content
            or requested_position not in TEXT_POSITIONS
            or start < 0
            or start >= end
            or not 16 <= font_size <= 120
            or not 1 <= outline <= 6
        ):
            raise LocalVideoEditError("text_overlay_invalid")
        text = {
            "content": content,
            "position": position,
            "start_ms": start,
            "end_ms": end,
            "font_size": font_size,
            "outline": outline,
            "font_path": str(text.get("font_path") or "").strip(),
        }
        if not concat_inputs and not (
            max(0, start) < min(post_speed_duration_ms, end)
        ):
            raise LocalVideoEditError("text_overlay_outside_output")
    logo = dict(raw.get("logo_overlay") or {})
    if logo:
        logo_path = str(logo.get("path") or "").strip()
        requested_position = str(logo.get("position") or "top_right").strip().lower()
        position = _canonical_overlay_position(requested_position, "top_right")
        scale = _strict_number(logo.get("scale", 0.12), reason="logo_overlay_invalid")
        opacity = _strict_number(logo.get("opacity", 1.0), reason="logo_overlay_invalid")
        if (
            not logo_path
            or requested_position not in LOGO_POSITIONS
            or not 0.02 <= scale <= 0.18
            or not 0.1 <= opacity <= 1.0
        ):
            raise LocalVideoEditError("logo_overlay_invalid")
        if workspace is not None:
            try:
                require_path_within(logo_path, workspace)
            except LocalVideoValidationError as exc:
                raise LocalVideoEditError(exc.reason) from exc
        logo = {"path": logo_path, "position": position, "scale": scale, "opacity": opacity}
    subtitle_file = str(raw.get("subtitle_file") or "").strip()
    if subtitle_file:
        validation = validate_srt_file(subtitle_file, workspace=workspace)
        if not validation.get("ok"):
            raise LocalVideoEditError(str(validation.get("reason") or "subtitle_invalid"))
        if not concat_inputs and not any(
            max(0, int(cue.get("start_ms") or 0))
            < min(post_speed_duration_ms, int(cue.get("end_ms") or 0))
            for cue in list(validation.get("cue_windows") or [])
            if isinstance(cue, dict)
        ):
            raise LocalVideoEditError("subtitle_outside_output")
    if str(raw.get("output_format") or "mp4").lower() != "mp4":
        raise LocalVideoEditError("output_format_invalid")
    return {
        "input_video": source,
        "concat_inputs": concat_inputs,
        "trim": {"start_ms": start_ms, "end_ms": end_ms},
        "crop_or_fit": {"aspect_ratio": aspect, "mode": mode},
        "resolution": resolution,
        "rotation": rotation,
        "flip": flip,
        "speed": speed,
        "volume": volume,
        "brightness_percent": brightness_percent,
        "text_overlay": text,
        "logo_overlay": logo,
        "subtitle_file": subtitle_file,
        "color_preset": color,
        "audio_normalization": audio_normalization,
        "quality_filters": quality,
        "local_effects": effects,
        "remove_middle": remove_middle,
        "output_format": "mp4",
    }


def expected_final_timeline_duration_ms(
    plan: dict[str, Any] | None,
    *,
    concat_sources: Iterable[Any] | None = None,
    source_duration_ms: int = 0,
) -> int:
    """Return the final post-trim/remove/concat/speed timeline duration.

    Telegram stores appended clips as metadata records while the worker later
    replaces them with bounded local paths.  Keeping this duration calculation
    in one pure helper makes the intake UI and the FFmpeg contract agree before
    any job is written.
    """

    current = dict(plan or {})
    trim = current.get("trim") if isinstance(current.get("trim"), dict) else {}
    start_ms = max(0, _integer(trim.get("start_ms"), 0))
    end_ms = _integer(trim.get("end_ms"), 0)
    if end_ms <= 0:
        end_ms = max(start_ms, _integer(source_duration_ms, 0))
    selected_ms = max(0, end_ms - start_ms)

    remove_middle = (
        current.get("remove_middle")
        if isinstance(current.get("remove_middle"), dict)
        else {}
    )
    if remove_middle:
        remove_start_ms = _integer(remove_middle.get("start_ms"), 0)
        remove_end_ms = _integer(remove_middle.get("end_ms"), 0)
        overlap_ms = max(
            0,
            min(end_ms, remove_end_ms) - max(start_ms, remove_start_ms),
        )
        selected_ms = max(0, selected_ms - overlap_ms)

    appended_ms = 0
    try:
        items = list(concat_sources or [])
    except TypeError:
        items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = (
            item.get("metadata")
            if isinstance(item.get("metadata"), dict)
            else item.get("source_metadata")
            if isinstance(item.get("source_metadata"), dict)
            else {}
        )
        duration_ms = _integer(
            metadata.get("duration_ms") or item.get("duration_ms"),
            0,
        )
        if duration_ms <= 0:
            duration_seconds = _number(
                metadata.get("duration_seconds")
                or metadata.get("duration")
                or item.get("duration_seconds")
                or item.get("duration"),
                0.0,
            )
            if not math.isfinite(duration_seconds) or duration_seconds <= 0:
                duration_seconds = 0.0
            duration_ms = int(
                round(duration_seconds * 1000)
            )
        appended_ms += max(0, duration_ms)

    speed = _number(current.get("speed"), 1.0)
    if not math.isfinite(speed) or speed <= 0:
        speed = 1.0
    return max(0, int(round((selected_ms + appended_ms) / speed)))


def expected_manual_duration_ms(
    plan: dict[str, Any],
    *,
    concat_sources: Iterable[dict[str, Any]] | None = None,
    source_duration_ms: int = 0,
) -> int:
    """Compatibility name for the authoritative final manual timeline."""

    return expected_final_timeline_duration_ms(
        plan,
        concat_sources=concat_sources,
        source_duration_ms=source_duration_ms,
    )


def required_optional_filters(
    plan: dict[str, Any],
    *,
    has_audio: bool,
    source_width: int = 0,
    source_height: int = 0,
) -> set[str]:
    """Return every FFmpeg filter required by a normalized local plan.

    The name is retained for adapter compatibility, but the contract is now
    complete: core geometry, timeline, overlay and audio filters are included
    alongside quality/effect filters.  Admission can therefore compare the
    plan against the exact worker snapshot before invoking FFmpeg.
    """
    required: set[str] = set()
    # ``build_manual_ffmpeg_command`` always emits a YUV420P format stage.
    required.add("format")
    crop = dict(plan.get("crop_or_fit") or {})
    aspect = str(crop.get("aspect_ratio") or "keep")
    resolution = str(plan.get("resolution") or "keep")
    if (
        aspect != "keep"
        or resolution != "keep"
        or int(source_width or 0) > 1920
        or int(source_height or 0) > 1920
    ):
        required.update({"scale", "setsar"})
        required.add("crop" if str(crop.get("mode") or "fit") == "crop" else "pad")
    rotation = int(plan.get("rotation") or 0)
    if rotation in {90, 270}:
        required.add("transpose")
    elif rotation == 180:
        required.update({"hflip", "vflip"})
    flip = str(plan.get("flip") or "none")
    if flip == "horizontal":
        required.add("hflip")
    elif flip == "vertical":
        required.add("vflip")
    speed = float(plan.get("speed") or 1.0)
    if speed != 1.0:
        required.add("setpts")
        if has_audio and float(plan.get("volume") or 0.0) > 0:
            required.add("atempo")
    color = COLOR_PRESETS.get(str(plan.get("color_preset") or "keep"), "")
    if color:
        for token in ("eq", "unsharp", "hqdn3d", "colorbalance", "hue"):
            if token in color:
                required.add(token)
    if int(plan.get("brightness_percent") or 100) != 100:
        required.add("eq")
    quality = dict(plan.get("quality_filters") or {})
    effects = dict(plan.get("local_effects") or {})
    audible = bool(has_audio and float(plan.get("volume") or 0) > 0)
    if quality.get("sharpen"):
        required.add("unsharp")
    if quality.get("denoise"):
        required.add("hqdn3d")
    if str(plan.get("audio_normalization") or "off") == "loudnorm":
        if not audible:
            raise LocalVideoEditError("audio_stream_required_for_loudnorm")
        required.add("loudnorm")
    if int(effects.get("fade_in_ms") or 0) or int(effects.get("fade_out_ms") or 0):
        required.add("fade")
        if audible:
            required.add("afade")
    if effects.get("vignette"):
        required.add("vignette")
    if effects.get("slow_zoom"):
        required.add("zoompan")
    text = dict(plan.get("text_overlay") or {})
    if text:
        required.add("drawtext")
    if str(plan.get("subtitle_file") or ""):
        required.add("subtitles")
    logo = dict(plan.get("logo_overlay") or {})
    if logo:
        required.update({"colorchannelmixer", "scale", "overlay"})
    if audible and float(plan.get("volume") or 0.0) != 1.0:
        required.add("volume")
    if plan.get("concat_inputs"):
        # Each concat input is normalized to the primary stream contract.
        # The primary clip can require a trim before append, and any appended
        # clip can require synthetic silence before stream normalization.
        required.update({
            "scale", "pad", "setsar", "fps", "anullsrc",
            "trim", "setpts", "atrim", "asetpts",
        })
    if plan.get("remove_middle"):
        required.update({"trim", "setpts"})
        if audible:
            required.update({"atrim", "asetpts"})
        required.add("concat")
    return required


def validate_required_optional_filters(
    plan: dict[str, Any],
    *,
    available_filters: set[str],
    has_audio: bool,
    source_width: int = 0,
    source_height: int = 0,
) -> None:
    missing = sorted(
        required_optional_filters(
            plan,
            has_audio=has_audio,
            source_width=int(source_width or 0),
            source_height=int(source_height or 0),
        )
        - set(available_filters or set())
    )
    if missing:
        raise LocalVideoEditError(f"ffmpeg_filter_unavailable:{missing[0]}")


def validate_manual_edit_plan_contract(
    plan: dict[str, Any] | None,
    *,
    source_duration_ms: int,
    has_audio: bool,
    allow_empty: bool = False,
    source_width: int = 0,
    source_height: int = 0,
    logo_source_present: bool = False,
    concat_sources_present: bool = False,
) -> dict[str, Any]:
    """Validate plan shape before a Telegram job is written.

    Telegram state contains file IDs rather than worker-local paths.  The
    normalizer is still authoritative for all fields; placeholder paths are
    used only for shape validation and are replaced by the worker later.
    """

    try:
        candidate = deepcopy(dict(plan or {}))
    except (TypeError, ValueError):
        return {
            "ok": False,
            "reason": "edit_plan_invalid",
            "required_filters": [],
            "plan": {},
        }
    legacy_source_alias = bool(candidate.get("source"))
    # Legacy worker payloads used ``source``; keep that compatibility alias
    # while still rejecting every other unknown top-level operation.
    if not candidate.get("input_video") and candidate.get("source"):
        candidate["input_video"] = str(candidate.get("source") or "")
        candidate.pop("source", None)
    candidate["input_video"] = str(candidate.get("input_video") or "source.mp4")
    if concat_sources_present and not candidate.get("concat_inputs"):
        # Telegram admission stores appended media as file-id records.  One
        # path-shaped placeholder preserves the pending-concat timeline rule;
        # the worker replaces it with its bounded downloaded paths.
        candidate["concat_inputs"] = ["concat-source.mp4"]
    # The worker downloads and validates the SRT inside its bounded workspace.
    # Do not require that worker-local path to exist during admission.
    subtitle_requested = bool(candidate.get("subtitle_file"))
    if candidate.get("subtitle_file"):
        candidate["subtitle_file"] = ""
    logo_candidate = candidate.get("logo_overlay")
    if isinstance(logo_candidate, dict) and logo_candidate and not logo_candidate.get("path") and logo_source_present:
        candidate["logo_overlay"] = {**logo_candidate, "path": "logo.png"}
    try:
        normalized = normalize_manual_edit_plan(
            candidate,
            source_duration_ms=int(source_duration_ms or 0),
            workspace=None,
        )
        if (
            not allow_empty
            and not legacy_source_alias
            and not subtitle_requested
            and not plan_has_effective_operation(
                normalized,
                source_duration_ms=int(source_duration_ms or 0),
            )
        ):
            raise LocalVideoEditError("edit_operation_missing")
        required = required_optional_filters(
            normalized,
            has_audio=bool(has_audio),
            source_width=int(source_width or 0),
            source_height=int(source_height or 0),
        )
        if subtitle_requested:
            required.add("subtitles")
    except LocalVideoEditError as exc:
        return {
            "ok": False,
            "reason": str(exc.reason or "edit_plan_invalid"),
            "required_filters": [],
            "plan": {},
        }
    return {
        "ok": True,
        "reason": "ok",
        "required_filters": sorted(required),
        "plan": normalized,
    }


_FFMPEG_FILTER_CACHE: dict[str, tuple[tuple[Any, ...], frozenset[str]]] = {}
_FFMPEG_DIAGNOSTIC_TAIL_BYTES = 256 * 1024
# `ffmpeg -filters` is normally a small textual listing.  This leaves generous
# headroom for supported builds while refusing a hostile or unexpectedly noisy
# binary before its output can consume unbounded memory.
_FFMPEG_FILTER_OUTPUT_BYTES = 4 * 1024 * 1024
_FFMPEG_PIPE_READ_BYTES = 64 * 1024
_FFMPEG_PIPE_JOIN_SECONDS = 1.0


def _ffmpeg_binary_fingerprint(ffmpeg_path: str) -> tuple[Any, ...]:
    path = Path(str(ffmpeg_path or "")).resolve(strict=False)
    try:
        stat = path.stat()
    except OSError:
        return (str(path).lower(), "unstatable")
    return (
        str(path).lower(),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(getattr(stat, "st_ino", 0) or 0),
    )


def available_ffmpeg_filters(
    ffmpeg_path: str,
    *,
    refresh: bool = False,
    deadline_monotonic: float | None = None,
) -> frozenset[str]:
    """Discover filters from the exact FFmpeg binary used by the worker."""
    cache_key = str(Path(str(ffmpeg_path or "")).resolve(strict=False)).lower()
    fingerprint = _ffmpeg_binary_fingerprint(ffmpeg_path)
    cached = _FFMPEG_FILTER_CACHE.get(cache_key)
    if not refresh and cached and cached[0] == fingerprint:
        return cached[1]
    try:
        subprocess_timeout = _remaining_ffmpeg_timeout(20, deadline_monotonic)
        result, stdout_overflow, _stderr_overflow = _capture_bounded_subprocess(
            [str(ffmpeg_path), "-hide_banner", "-filters"],
            timeout=subprocess_timeout,
            deadline_monotonic=deadline_monotonic,
            stdout_limit=_FFMPEG_FILTER_OUTPUT_BYTES,
            stderr_limit=_FFMPEG_DIAGNOSTIC_TAIL_BYTES,
        )
    except subprocess.TimeoutExpired as exc:
        raise LocalVideoEditError("ffmpeg_timeout") from exc
    except OSError as exc:
        raise LocalVideoEditError("ffmpeg_filter_discovery_failed") from exc
    if stdout_overflow or result.returncode != 0:
        raise LocalVideoEditError("ffmpeg_filter_discovery_failed")
    discovered: set[str] = set()
    for line in str(result.stdout or "").splitlines():
        # FFmpeg 8 prints two flag columns (for example ``TS``/``..``),
        # while older builds commonly print three.  Parse the capability
        # token by shape instead of pinning the worker to one FFmpeg release.
        match = re.match(r"^\s*[A-Z\.]{2,4}\s+([A-Za-z0-9_]+)\s", line)
        if match:
            discovered.add(match.group(1))
    if not discovered:
        raise LocalVideoEditError("ffmpeg_filter_discovery_empty")
    result = frozenset(discovered)
    _FFMPEG_FILTER_CACHE[cache_key] = (fingerprint, result)
    return result


def _target_size(aspect: str, resolution: str, source_width: int, source_height: int) -> tuple[int, int]:
    aspect = aspect if aspect in ASPECT_RATIOS else "keep"
    resolution = resolution if resolution in RESOLUTION_PRESETS else "keep"
    source_width = max(2, int(source_width or 2))
    source_height = max(2, int(source_height or 2))
    source_scale = min(1.0, 1920 / source_width, 1920 / source_height)
    bounded_width = max(2, int(source_width * source_scale) // 2 * 2)
    bounded_height = max(2, int(source_height * source_scale) // 2 * 2)
    if aspect == "keep":
        if resolution == "keep":
            return bounded_width, bounded_height
        landscape = source_width >= source_height
        if resolution == "720p":
            return (1280, 720) if landscape else (720, 1280)
        return (1920, 1080) if landscape else (1080, 1920)
    sizes = {
        "720p": {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (720, 720), "4:5": (720, 900)},
        "1080p": {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)},
    }
    if resolution == "keep":
        numerator, denominator = (int(item) for item in aspect.split(":", 1))
        target_ratio = numerator / denominator
        if bounded_width / bounded_height >= target_ratio:
            height = bounded_height
            width = max(2, int(round((height * target_ratio) / 2.0)) * 2)
        else:
            width = bounded_width
            height = max(2, int(round((width / target_ratio) / 2.0)) * 2)
        return width, height
    selected = resolution
    return sizes[selected][aspect]


def _escape_filter_text(value: str) -> str:
    # Single definition lives in services/ffmpeg_text: a quote cannot be
    # escaped inside a quoted filtergraph value, so it has to be replaced.
    return ffmpeg_text.escape_filter_text(value)


def _escape_filter_path(path: str) -> str:
    return ffmpeg_text.escape_filter_path(path)


def resolve_vietnamese_font_path(explicit: str = "") -> str:
    candidates = (
        explicit,
        os.getenv("LOCAL_FFMPEG_FONT_PATH", ""),
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    )
    for candidate in candidates:
        clean = str(candidate or "").strip()
        if clean and Path(clean).is_file():
            return clean
    return ""


def _text_filter(config: dict[str, Any]) -> str:
    if not config:
        return ""
    x, y = _overlay_xy(
        config.get("position"),
        frame_width="w",
        frame_height="h",
        overlay_width="text_w",
        overlay_height="text_h",
        margin_x="w*0.04",
        margin_y="h*0.06",
        default="bottom_center",
    )
    font_path = resolve_vietnamese_font_path(str(config.get("font_path") or ""))
    font = f"fontfile='{_escape_filter_path(font_path)}':" if font_path else ""
    start = int(config.get("start_ms") or 0) / 1000
    end = int(config.get("end_ms") or 0) / 1000
    return (
        f"drawtext={font}text='{_escape_filter_text(str(config.get('content') or ''))}':{ffmpeg_text.DRAWTEXT_NO_EXPANSION}:"
        f"fontcolor=white:fontsize={int(config.get('font_size') or 42)}:"
        f"borderw={int(config.get('outline') or 2)}:bordercolor=black@0.9:"
        f"x={x}:y={y}:enable='between(t,{start:.3f},{end:.3f})'"
    )


def build_manual_ffmpeg_command(
    plan: dict[str, Any],
    *,
    output_path: str,
    source_probe: dict[str, Any],
    ffmpeg_path: str,
) -> list[str]:
    if plan.get("remove_middle"):
        raise LocalVideoEditError("remove_middle_requires_timeline_preparation")
    source = str(plan.get("input_video") or "")
    trim = dict(plan.get("trim") or {})
    start_seconds = int(trim.get("start_ms") or 0) / 1000
    selected_seconds = (int(trim.get("end_ms") or 0) - int(trim.get("start_ms") or 0)) / 1000
    command = [ffmpeg_path, "-y", "-ss", f"{start_seconds:.3f}", "-i", source]
    logo = dict(plan.get("logo_overlay") or {})
    if logo:
        command.extend(["-i", str(logo.get("path") or "")])
    filters: list[str] = []
    aspect = str((plan.get("crop_or_fit") or {}).get("aspect_ratio") or "keep")
    mode = str((plan.get("crop_or_fit") or {}).get("mode") or "fit")
    width, height = _target_size(
        aspect,
        str(plan.get("resolution") or "keep"),
        int(source_probe.get("width") or 1280),
        int(source_probe.get("height") or 720),
    )
    needs_geometry_filter = bool(
        aspect != "keep"
        or str(plan.get("resolution") or "keep") != "keep"
        or int(source_probe.get("width") or 0) > 1920
        or int(source_probe.get("height") or 0) > 1920
    )
    if needs_geometry_filter:
        if mode == "crop":
            filters.extend([
                f"scale={width}:{height}:force_original_aspect_ratio=increase",
                f"crop={width}:{height}",
            ])
        else:
            filters.extend([
                f"scale={width}:{height}:force_original_aspect_ratio=decrease",
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            ])
        filters.append("setsar=1")
    rotation = int(plan.get("rotation") or 0)
    if rotation == 90:
        filters.append("transpose=1")
    elif rotation == 180:
        filters.extend(["hflip", "vflip"])
    elif rotation == 270:
        filters.append("transpose=2")
    output_width, output_height = (
        (height, width) if rotation in {90, 270} else (width, height)
    )
    if plan.get("flip") == "horizontal":
        filters.append("hflip")
    elif plan.get("flip") == "vertical":
        filters.append("vflip")
    speed = float(plan.get("speed") or 1.0)
    expected_output_seconds = selected_seconds / max(0.01, speed)
    color = COLOR_PRESETS.get(str(plan.get("color_preset") or "keep"), "")
    if color:
        filters.append(color)
    brightness_percent = int(plan.get("brightness_percent") or 100)
    if brightness_percent != 100:
        filters.append(f"eq=brightness={(brightness_percent - 100) / 200:.3f}")
    quality = dict(plan.get("quality_filters") or {})
    if quality.get("denoise"):
        filters.append("hqdn3d=6:4:8:6")
    if quality.get("sharpen"):
        filters.append("unsharp=5:5:0.8:5:5:0.0")
    effects = dict(plan.get("local_effects") or {})
    if effects.get("slow_zoom"):
        fps = max(1.0, min(60.0, float(source_probe.get("fps") or 30.0)))
        filters.append(
            "zoompan=z='min(max(zoom,pzoom)+0.0005,1.08)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={output_width}x{output_height}:fps={fps:g}"
        )
    # ``zoompan`` regenerates frame timestamps.  Apply the requested speed
    # afterwards so slow zoom cannot silently cancel or distort the timeline.
    # Timed filters (fade, text and subtitles) must remain after this stage.
    if speed != 1.0:
        filters.append(f"setpts=PTS/{speed:g}")
    if effects.get("vignette"):
        filters.append("vignette=PI/5")
    fade_in_seconds = int(effects.get("fade_in_ms") or 0) / 1000
    fade_out_seconds = int(effects.get("fade_out_ms") or 0) / 1000
    if fade_in_seconds > 0:
        filters.append(f"fade=t=in:st=0:d={fade_in_seconds:.3f}")
    if fade_out_seconds > 0:
        fade_out_start = max(0.0, expected_output_seconds - fade_out_seconds)
        filters.append(f"fade=t=out:st={fade_out_start:.3f}:d={fade_out_seconds:.3f}")
    text = _text_filter(dict(plan.get("text_overlay") or {}))
    if text:
        filters.append(text)
    subtitle = str(plan.get("subtitle_file") or "")
    if subtitle:
        subtitle_font = resolve_vietnamese_font_path()
        subtitle_style = "DejaVu Sans" if "dejavu" in subtitle_font.lower() else "Noto Sans"
        filters.append(
            f"subtitles='{_escape_filter_path(subtitle)}':"
            f"force_style='FontName={subtitle_style},FontSize=22,Outline=2,Shadow=0,MarginV=42,Alignment=2'"
        )
    filters.append("format=yuv420p")
    base_filter = ",".join(item for item in filters if item)
    if logo:
        logo_frame_width = output_width
        logo_width = max(
            2,
            int(round(logo_frame_width * float(logo.get("scale") or 0.12))) // 2 * 2,
        )
        x, y = _overlay_xy(
            logo.get("position"),
            frame_width="main_w",
            frame_height="main_h",
            overlay_width="overlay_w",
            overlay_height="overlay_h",
            margin_x="main_w*0.04",
            margin_y="main_h*0.035",
            default="top_right",
        )
        complex_filter = (
            f"[0:v]{base_filter}[base];"
            f"[1:v]format=rgba,colorchannelmixer=aa={float(logo.get('opacity') or 1.0):.3f}[logo0];"
            f"[logo0]scale=w={logo_width}:h=-2[logo];"
            f"[base][logo]overlay={x}:{y}[v]"
        )
        command.extend(["-filter_complex", complex_filter, "-map", "[v]"])
    else:
        command.extend(["-vf", base_filter, "-map", "0:v:0"])
    has_audio = bool(source_probe.get("has_audio"))
    volume = float(plan.get("volume") or 0.0)
    if has_audio and volume > 0:
        command.extend(["-map", "0:a:0?"])
        audio_filters = []
        if speed != 1.0:
            audio_filters.append(f"atempo={speed:g}")
        if volume != 1.0:
            audio_filters.append(f"volume={volume:g}")
        if str(plan.get("audio_normalization") or "off") == "loudnorm":
            audio_filters.append("loudnorm=I=-16:LRA=11:TP=-1.5")
        if fade_in_seconds > 0:
            audio_filters.append(f"afade=t=in:st=0:d={fade_in_seconds:.3f}")
        if fade_out_seconds > 0:
            fade_out_start = max(0.0, expected_output_seconds - fade_out_seconds)
            audio_filters.append(f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_seconds:.3f}")
        if audio_filters:
            command.extend(["-af", ",".join(audio_filters)])
        command.extend(["-c:a", "aac", "-b:a", "160k", "-ar", "48000"])
    else:
        command.append("-an")
    command.extend([
        "-t", f"{expected_output_seconds:.3f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-maxrate", "8M",
        "-bufsize", "16M",
        "-movflags", "+faststart",
        "-max_muxing_queue_size", "2048",
        str(output_path),
    ])
    return command


def build_split_ffmpeg_command(
    source_path: str,
    item: SplitRange,
    output_path: str,
    *,
    ffmpeg_path: str,
    has_audio: bool,
) -> list[str]:
    command = [
        ffmpeg_path, "-y",
        "-ss", f"{item.start_ms / 1000:.3f}",
        "-i", str(source_path),
        "-t", f"{item.duration_ms / 1000:.3f}",
        "-map", "0:v:0",
        "-vf", "scale=w='min(iw,1920)':h='min(ih,1920)':force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,format=yuv420p",
    ]
    if has_audio:
        command.extend(["-map", "0:a:0?", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"])
    else:
        command.append("-an")
    command.extend([
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-max_muxing_queue_size", "2048", str(output_path),
    ])
    return command


def validate_split_ranges(
    ranges: Iterable[SplitRange],
    *,
    source_duration_ms: int,
    coverage_required: bool,
) -> list[SplitRange]:
    """Validate the worker split contract before any FFmpeg invocation."""

    items = list(ranges or [])
    duration = int(source_duration_ms or 0)
    if duration <= 0:
        raise LocalVideoEditError("source_duration_invalid")
    if not items:
        raise LocalVideoEditError("split_plan_empty")
    if (
        len(items) == 1
        and isinstance(items[0], SplitRange)
        and int(items[0].start_ms) == 0
        and int(items[0].end_ms) == duration
    ):
        raise LocalVideoEditError("split_part_count_invalid")
    if len(items) > int(MAX_SPLIT_PARTS):
        raise LocalVideoEditError("split_part_count_invalid")
    previous_end: int | None = None
    for position, item in enumerate(items, start=1):
        if not isinstance(item, SplitRange):
            raise LocalVideoEditError("split_range_invalid")
        if int(item.index) != position:
            raise LocalVideoEditError("split_index_invalid")
        start_ms = int(item.start_ms)
        end_ms = int(item.end_ms)
        if start_ms < 0 or start_ms >= end_ms or end_ms > duration:
            raise LocalVideoEditError("split_range_invalid")
        if end_ms - start_ms < int(MIN_SEGMENT_MS):
            raise LocalVideoEditError("split_part_too_short")
        if previous_end is not None and start_ms < previous_end:
            raise LocalVideoEditError("split_range_overlap")
        if bool(coverage_required) and previous_end is not None and start_ms != previous_end:
            raise LocalVideoEditError("split_coverage_invalid")
        previous_end = end_ms
    if bool(coverage_required) and (items[0].start_ms != 0 or items[-1].end_ms != duration):
        raise LocalVideoEditError("split_coverage_invalid")
    return items


def _remaining_ffmpeg_timeout(timeout: int, deadline_monotonic: float | None) -> float:
    per_call_timeout = float(max(1, int(timeout)))
    if deadline_monotonic is None:
        return per_call_timeout
    remaining = float(deadline_monotonic) - time.monotonic()
    if remaining <= 0:
        raise LocalVideoEditError("ffmpeg_timeout")
    return min(per_call_timeout, remaining)


def _enforce_workspace_budget(
    workspace: str | os.PathLike[str],
    workspace_budget_bytes: int | None,
) -> int:
    if workspace_budget_bytes is None:
        return enforce_workspace_limit(workspace)
    return enforce_workspace_limit(
        workspace,
        maximum_bytes=int(workspace_budget_bytes),
    )


class _BoundedByteTail:
    """Retain only the final ``limit`` bytes while a pipe is drained."""

    def __init__(self, limit: int) -> None:
        self.limit = int(limit)
        self._chunks: deque[bytes] = deque()
        self._size = 0
        self.overflowed = False

    def append(self, chunk: bytes) -> None:
        if not chunk:
            return
        chunk = bytes(chunk)
        if len(chunk) >= self.limit:
            self.overflowed = (
                self.overflowed
                or len(chunk) > self.limit
                or self._size > 0
            )
            self._chunks.clear()
            retained = chunk[-self.limit :]
            self._chunks.append(retained)
            self._size = len(retained)
            return
        self._chunks.append(chunk)
        self._size += len(chunk)
        if self._size > self.limit:
            self.overflowed = True
        while self._size > self.limit and self._chunks:
            overflow = self._size - self.limit
            oldest = self._chunks[0]
            if len(oldest) <= overflow:
                self._chunks.popleft()
                self._size -= len(oldest)
                continue
            self._chunks[0] = oldest[overflow:]
            self._size -= overflow

    def text(self) -> str:
        return b"".join(self._chunks).decode("utf-8", errors="replace")


def _reap_bounded_process(
    process: Any,
    *,
    deadline_monotonic: float | None = None,
) -> None:
    """Stop and reap an unsuccessful capture without an unbounded wait."""

    def cleanup_timeout() -> float:
        if deadline_monotonic is None:
            return 0.5
        return max(
            0.0,
            min(0.5, float(deadline_monotonic) - time.monotonic()),
        )

    try:
        running = process.poll() is None
    except OSError:
        running = True
    if running:
        terminate_failed = False
        try:
            process.terminate()
        except OSError:
            terminate_failed = True
        if not terminate_failed:
            try:
                process.wait(timeout=cleanup_timeout())
                running = False
            except (subprocess.TimeoutExpired, OSError):
                pass
        if running:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=cleanup_timeout())
            except (subprocess.TimeoutExpired, OSError):
                pass


def _cancel_windows_reader_io(reader: threading.Thread) -> bool:
    """Cancel a synchronous Windows pipe read owned by ``reader``."""
    if os.name != "nt" or not reader.is_alive():
        return False
    native_id = getattr(reader, "native_id", None)
    if not isinstance(native_id, int) or native_id <= 0:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenThread.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        )
        kernel32.OpenThread.restype = wintypes.HANDLE
        kernel32.CancelSynchronousIo.argtypes = (wintypes.HANDLE,)
        kernel32.CancelSynchronousIo.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenThread(0x0001, False, native_id)
        if not handle:
            return False
        try:
            return bool(kernel32.CancelSynchronousIo(handle))
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _capture_bounded_subprocess(
    command: list[str],
    *,
    timeout: float,
    deadline_monotonic: float | None = None,
    stdout_limit: int,
    stderr_limit: int,
) -> tuple[subprocess.CompletedProcess[str], bool, bool]:
    """Run a process with concurrently drained, fixed-size diagnostic tails."""
    timeout_value = float(timeout)
    started_monotonic = time.monotonic()
    capture_deadline = started_monotonic + timeout_value
    if deadline_monotonic is not None:
        capture_deadline = min(capture_deadline, float(deadline_monotonic))

    def remaining_capture_timeout() -> float:
        remaining = capture_deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout_value)
        return remaining

    remaining_capture_timeout()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_tail = _BoundedByteTail(stdout_limit)
    stderr_tail = _BoundedByteTail(stderr_limit)
    reader_errors: list[BaseException] = []

    def drain(pipe: Any, tail: _BoundedByteTail) -> None:
        try:
            while True:
                chunk = pipe.read(_FFMPEG_PIPE_READ_BYTES)
                if not chunk:
                    return
                tail.append(chunk)
        except BaseException as exc:  # Pipe reads can surface platform-specific I/O errors.
            reader_errors.append(exc)
            # A failed reader can otherwise leave a chatty child blocked on
            # its other pipe.  End it promptly; the owner reaps it below.
            try:
                if process.poll() is None:
                    process.terminate()
            except OSError:
                pass
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    readers: list[threading.Thread] = []
    started_readers: list[threading.Thread] = []

    def join_readers() -> bool:
        if not started_readers:
            return True
        remaining = max(0.0, capture_deadline - time.monotonic())
        join_budget = min(float(_FFMPEG_PIPE_JOIN_SECONDS), remaining)
        per_reader_timeout = max(
            0.0,
            join_budget / len(started_readers),
        )
        for reader in started_readers:
            reader.join(timeout=per_reader_timeout)
        return not any(reader.is_alive() for reader in started_readers)

    try:
        readers.extend(
            (
                threading.Thread(
                    target=drain,
                    args=(process.stdout, stdout_tail),
                    daemon=True,
                ),
                threading.Thread(
                    target=drain,
                    args=(process.stderr, stderr_tail),
                    daemon=True,
                ),
            )
        )
        for reader in readers:
            reader.start()
            started_readers.append(reader)
        returncode = process.wait(timeout=remaining_capture_timeout())
        if not join_readers():
            alive_readers = [
                reader for reader in started_readers if reader.is_alive()
            ]
            for reader in alive_readers:
                _cancel_windows_reader_io(reader)
            join_readers()
            raise OSError("ffmpeg_pipe_read_timeout")
        if reader_errors:
            raise OSError("ffmpeg_pipe_read_failed") from reader_errors[0]
        return (
            subprocess.CompletedProcess(process.args, returncode, stdout_tail.text(), stderr_tail.text()),
            stdout_tail.overflowed,
            stderr_tail.overflowed,
        )
    except BaseException:
        _reap_bounded_process(
            process,
            deadline_monotonic=capture_deadline,
        )
        alive_readers = [
            reader for reader in started_readers if reader.is_alive()
        ]
        for reader in alive_readers:
            _cancel_windows_reader_io(reader)
        join_readers()
        raise
    finally:
        for reader, pipe in zip(readers, (process.stdout, process.stderr)):
            if reader not in started_readers or not reader.is_alive():
                if pipe is not None:
                    try:
                        pipe.close()
                    except OSError:
                        pass


def _run(
    command: list[str],
    *,
    timeout: int,
    deadline_monotonic: float | None = None,
) -> subprocess.CompletedProcess[str]:
    if not command or "ffmpeg" not in Path(str(command[0])).name.lower():
        raise LocalVideoEditError("ffmpeg_command_required")
    try:
        subprocess_timeout = _remaining_ffmpeg_timeout(timeout, deadline_monotonic)
        result, _stdout_overflow, _stderr_overflow = _capture_bounded_subprocess(
            command,
            timeout=subprocess_timeout,
            deadline_monotonic=deadline_monotonic,
            stdout_limit=_FFMPEG_DIAGNOSTIC_TAIL_BYTES,
            stderr_limit=_FFMPEG_DIAGNOSTIC_TAIL_BYTES,
        )
        return result
    except subprocess.TimeoutExpired as exc:
        raise LocalVideoEditError("ffmpeg_timeout") from exc
    except OSError as exc:
        raise LocalVideoEditError(f"ffmpeg_exec_failed:{type(exc).__name__}") from exc


def _run_checked(
    command: list[str],
    *,
    timeout: int,
    deadline_monotonic: float | None = None,
) -> None:
    result = _run(command, timeout=timeout, deadline_monotonic=deadline_monotonic)
    if result.returncode != 0:
        lines = [line.strip() for line in str(result.stderr or result.stdout or "").splitlines() if line.strip()]
        diagnostics = [
            line for line in lines
            if not line.startswith("[Parsed_")
            and any(token in line.lower() for token in ("error", "invalid", "failed", "unable", "not found"))
        ]
        detail = " | ".join((diagnostics or lines)[-2:])
        raise LocalVideoEditError(f"ffmpeg_failed:{detail[:300] or result.returncode}")


def _ffconcat_manifest_entry(path: str | Path) -> str:
    normalized_path = str(path).replace("\\", "/")
    escaped_path = normalized_path.replace("'", "'\\''")
    return f"file '{escaped_path}'\n"


def _normalize_concat_inputs(
    sources: list[str],
    *,
    workspace: Path,
    ffmpeg_path: str,
    ffprobe_path: str,
    timeout: int,
    deadline_monotonic: float | None = None,
    workspace_budget_bytes: int | None = None,
) -> tuple[str, dict[str, Any]]:
    normalized: list[Path] = []
    target_width = 0
    target_height = 0
    for index, source in enumerate(sources, start=1):
        probe = probe_video_file(source, ffprobe_path=ffprobe_path)
        if not probe.get("ok"):
            raise LocalVideoEditError(str(probe.get("reason") or "concat_probe_failed"))
        if not target_width or not target_height:
            # Normalize every append input to the primary source geometry,
            # capped at the existing local 1920px safety boundary.  ``keep``
            # must never silently become a fixed 720p export.
            target_width, target_height = _target_size(
                "keep",
                "keep",
                int(probe.get("width") or 2),
                int(probe.get("height") or 2),
            )
        target = workspace / f"concat_normalized_{index:03d}.mp4"
        command = [ffmpeg_path, "-y", "-i", source]
        if not probe.get("has_audio"):
            command.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        duration = max(0.001, float(probe.get("duration") or 0.0))
        command.extend([
            "-map", "0:v:0", "-map", "0:a:0?" if probe.get("has_audio") else "1:a:0",
            "-vf", (
                f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                "setsar=1,fps=30,format=yuv420p"
            ),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
            "-t", f"{duration:.3f}", "-movflags", "+faststart", str(target),
        ])
        _run_checked(command, timeout=timeout, deadline_monotonic=deadline_monotonic)
        _enforce_workspace_budget(workspace, workspace_budget_bytes)
        normalized.append(target)
    manifest = workspace / "concat_inputs.txt"
    manifest.write_text(
        "".join(_ffconcat_manifest_entry(item) for item in normalized),
        encoding="utf-8",
    )
    concat_output = workspace / "concat_source.mp4"
    _run_checked(
        [ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(concat_output)],
        timeout=timeout,
        deadline_monotonic=deadline_monotonic,
    )
    _enforce_workspace_budget(workspace, workspace_budget_bytes)
    probe = probe_video_file(concat_output, ffprobe_path=ffprobe_path)
    if not probe.get("ok"):
        raise LocalVideoEditError(str(probe.get("reason") or "concat_output_invalid"))
    return str(concat_output), probe


def _prepare_primary_timeline(
    plan: dict[str, Any],
    *,
    source_probe: dict[str, Any],
    workspace: Path,
    ffmpeg_path: str,
    ffprobe_path: str,
    timeout: int,
    deadline_monotonic: float | None = None,
    workspace_budget_bytes: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Apply primary trim/remove-middle before any append operation."""
    source = str(plan.get("input_video") or "")
    trim = dict(plan.get("trim") or {})
    remove_middle = dict(plan.get("remove_middle") or {})
    start_ms = int(trim.get("start_ms") or 0)
    end_ms = int(trim.get("end_ms") or 0)
    source_duration_ms = int(source_probe.get("duration_ms") or 0)
    needs_trim = start_ms > 0 or end_ms < source_duration_ms
    if not needs_trim and not remove_middle:
        return source, source_probe

    start_seconds = start_ms / 1000
    end_seconds = end_ms / 1000
    has_audio = bool(source_probe.get("has_audio"))
    video_parts: list[str] = []
    audio_parts: list[str] = []
    concat_inputs: list[str] = []
    if remove_middle:
        remove_start_seconds = int(remove_middle["start_ms"]) / 1000
        remove_end_seconds = int(remove_middle["end_ms"]) / 1000
        spans = ((start_seconds, remove_start_seconds), (remove_end_seconds, end_seconds))
    else:
        spans = ((start_seconds, end_seconds),)
    for index, (span_start, span_end) in enumerate(spans):
        video_parts.append(
            f"[0:v]trim=start={span_start:.3f}:end={span_end:.3f},"
            f"setpts=PTS-STARTPTS[v{index}]"
        )
        concat_inputs.append(f"[v{index}]")
        if has_audio:
            audio_parts.append(
                f"[0:a]atrim=start={span_start:.3f}:end={span_end:.3f},"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )
            concat_inputs.append(f"[a{index}]")
    if len(spans) == 1:
        video_out = "[v0]"
        audio_out = "[a0]" if has_audio else ""
        filter_graph = ";".join([*video_parts, *audio_parts])
    else:
        video_out = "[v]"
        audio_out = "[a]" if has_audio else ""
        filter_graph = ";".join(
            [
                *video_parts,
                *audio_parts,
                "".join(concat_inputs)
                + f"concat=n={len(spans)}:v=1:a={1 if has_audio else 0}[v]"
                + ("[a]" if has_audio else ""),
            ]
        )
    target = workspace / f"primary_timeline_{os.getpid()}.mp4"
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        source,
        "-filter_complex",
        filter_graph,
        "-map",
        video_out,
    ]
    if has_audio:
        command.extend(["-map", audio_out, "-c:a", "aac", "-b:a", "160k", "-ar", "48000"])
    else:
        command.append("-an")
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-max_muxing_queue_size",
            "2048",
            str(target),
        ]
    )
    try:
        if target.exists():
            target.unlink()
        _run_checked(command, timeout=timeout, deadline_monotonic=deadline_monotonic)
        _enforce_workspace_budget(workspace, workspace_budget_bytes)
        expected_duration_ms = end_ms - start_ms
        if remove_middle:
            expected_duration_ms -= int(remove_middle["end_ms"]) - int(remove_middle["start_ms"])
        validation = validate_mp4_output(
            target,
            expected_duration_ms=expected_duration_ms,
            require_audio=has_audio,
            ffprobe_path=ffprobe_path,
        )
        if not validation.get("ok"):
            raise LocalVideoEditError(str(validation.get("reason") or "primary_timeline_invalid"))
        prepared_probe = probe_video_file(target, ffprobe_path=ffprobe_path)
        if not prepared_probe.get("ok"):
            raise LocalVideoEditError(str(prepared_probe.get("reason") or "primary_timeline_probe_failed"))
        return str(target), prepared_probe
    except Exception:
        if target.exists():
            target.unlink()
        raise


def execute_manual_edit(
    plan: dict[str, Any],
    *,
    output_path: str,
    workspace: str | os.PathLike[str],
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    timeout: int = FFMPEG_TIMEOUT_SECONDS,
    progress: Callable[[dict[str, Any]], None] | None = None,
    deadline_monotonic: float | None = None,
    workspace_budget_bytes: int | None = None,
) -> dict[str, Any]:
    workspace_path = Path(workspace).resolve(strict=False)
    admitted_workspace_budget = (
        None if workspace_budget_bytes is None else int(workspace_budget_bytes)
    )
    output = require_path_within(output_path, workspace_path)
    staging = output.with_name(f".{output.stem}.{os.getpid()}.partial{output.suffix}")
    staging = require_path_within(staging, workspace_path)
    ffmpeg = find_ffmpeg(ffmpeg_path)
    probe_bin = find_ffprobe(ffprobe_path, ffmpeg_path=ffmpeg)
    if not ffmpeg:
        raise LocalVideoEditError("ffmpeg_missing")
    if not probe_bin:
        raise LocalVideoEditError("ffprobe_missing")
    source_probe = probe_video_file(str(plan.get("input_video") or ""), ffprobe_path=probe_bin)
    if not source_probe.get("ok"):
        raise LocalVideoEditError(str(source_probe.get("reason") or "input_probe_failed"))
    normalized = normalize_manual_edit_plan(plan, source_duration_ms=int(source_probe.get("duration_ms") or 0), workspace=workspace_path)
    required_filters = required_optional_filters(
        normalized,
        has_audio=bool(source_probe.get("has_audio")),
        source_width=int(source_probe.get("width") or 0),
        source_height=int(source_probe.get("height") or 0),
    )
    if required_filters:
        filter_discovery_kwargs: dict[str, Any] = {"refresh": True}
        if deadline_monotonic is not None:
            filter_discovery_kwargs["deadline_monotonic"] = deadline_monotonic
        validate_required_optional_filters(
            normalized,
            available_filters=set(available_ffmpeg_filters(ffmpeg, **filter_discovery_kwargs)),
            has_audio=bool(source_probe.get("has_audio")),
            source_width=int(source_probe.get("width") or 0),
            source_height=int(source_probe.get("height") or 0),
        )
    if progress:
        progress({"stage": "preparing_plan", "processed": 0, "total": 1})
    prepared_primary: Path | None = None
    primary_trim = dict(normalized.get("trim") or {})
    primary_needs_preparation = bool(
        normalized.get("remove_middle")
        or (
            normalized.get("concat_inputs")
            and (
                int(primary_trim.get("start_ms") or 0) > 0
                or int(primary_trim.get("end_ms") or 0) < int(source_probe.get("duration_ms") or 0)
            )
        )
    )
    if primary_needs_preparation:
        source, source_probe = _prepare_primary_timeline(
            normalized,
            source_probe=source_probe,
            workspace=workspace_path,
            ffmpeg_path=ffmpeg,
            ffprobe_path=probe_bin,
            timeout=timeout,
            deadline_monotonic=deadline_monotonic,
            workspace_budget_bytes=admitted_workspace_budget,
        )
        prepared_primary = Path(source)
        normalized["input_video"] = source
        normalized["trim"] = {"start_ms": 0, "end_ms": int(source_probe.get("duration_ms") or 0)}
        normalized["remove_middle"] = {}
    concat_sources = [normalized["input_video"], *normalized.get("concat_inputs", [])]
    if len(concat_sources) > 1:
        try:
            source, source_probe = _normalize_concat_inputs(
                concat_sources,
                workspace=workspace_path,
                ffmpeg_path=ffmpeg,
                ffprobe_path=probe_bin,
                timeout=timeout,
                deadline_monotonic=deadline_monotonic,
                workspace_budget_bytes=admitted_workspace_budget,
            )
            normalized["input_video"] = source
            normalized["concat_inputs"] = []
            normalized["trim"] = {
                "start_ms": 0,
                "end_ms": int(source_probe.get("duration_ms") or 0),
            }
            normalized = normalize_manual_edit_plan(
                normalized,
                source_duration_ms=int(source_probe.get("duration_ms") or 0),
                workspace=workspace_path,
            )
        except Exception:
            if prepared_primary is not None and prepared_primary.exists():
                prepared_primary.unlink()
                prepared_primary = None
            raise
    if progress:
        progress({"stage": "processing_video", "processed": 0, "total": 1})
    try:
        if staging.exists():
            staging.unlink()
        command = build_manual_ffmpeg_command(
            normalized,
            output_path=str(staging),
            source_probe=source_probe,
            ffmpeg_path=ffmpeg,
        )
        _run_checked(command, timeout=timeout, deadline_monotonic=deadline_monotonic)
        _enforce_workspace_budget(workspace_path, admitted_workspace_budget)
        if progress:
            progress({"stage": "validating_output", "processed": 1, "total": 1})
        expected = expected_manual_duration_ms(normalized)
        validation = validate_mp4_output(
            staging,
            expected_duration_ms=expected,
            require_audio=bool(source_probe.get("has_audio") and float(normalized.get("volume") or 0) > 0),
            ffprobe_path=probe_bin,
        )
        if not validation.get("ok"):
            raise LocalVideoEditError(str(validation.get("reason") or "output_validation_failed"))
        os.replace(staging, output)
        validation = validate_mp4_output(
            output,
            expected_duration_ms=expected,
            require_audio=bool(source_probe.get("has_audio") and float(normalized.get("volume") or 0) > 0),
            ffprobe_path=probe_bin,
        )
        if not validation.get("ok"):
            if output.exists():
                output.unlink()
            raise LocalVideoEditError(str(validation.get("reason") or "output_finalize_validation_failed"))
        return {
            "ok": True,
            "output_path": str(output),
            "validation": validation,
            "expected_duration_ms": expected,
            "audio_preserved": bool(validation.get("has_audio")) if source_probe.get("has_audio") else False,
            "provider_called": False,
            "xu_charged": 0,
        }
    finally:
        if staging.exists():
            staging.unlink()
        if prepared_primary is not None and prepared_primary.exists():
            prepared_primary.unlink()


def execute_split_plan(
    source_path: str,
    ranges: Iterable[SplitRange],
    *,
    workspace: str | os.PathLike[str],
    coverage_required: bool,
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    timeout: int = FFMPEG_TIMEOUT_SECONDS,
    progress: Callable[[dict[str, Any]], None] | None = None,
    deadline_monotonic: float | None = None,
    workspace_budget_bytes: int | None = None,
) -> dict[str, Any]:
    workspace_path = Path(workspace).resolve(strict=False)
    admitted_workspace_budget = (
        None if workspace_budget_bytes is None else int(workspace_budget_bytes)
    )
    source = require_path_within(source_path, workspace_path)
    items = list(ranges or [])
    if not items:
        raise LocalVideoEditError("split_plan_empty")
    ffmpeg = find_ffmpeg(ffmpeg_path)
    probe_bin = find_ffprobe(ffprobe_path, ffmpeg_path=ffmpeg)
    if not ffmpeg:
        raise LocalVideoEditError("ffmpeg_missing")
    if not probe_bin:
        raise LocalVideoEditError("ffprobe_missing")
    filter_discovery_kwargs: dict[str, Any] = {"refresh": True}
    if deadline_monotonic is not None:
        filter_discovery_kwargs["deadline_monotonic"] = deadline_monotonic
    available_filters = set(available_ffmpeg_filters(ffmpeg, **filter_discovery_kwargs))
    for required_filter in ("format", "scale", "setsar"):
        if required_filter not in available_filters:
            raise LocalVideoEditError(
                f"ffmpeg_filter_unavailable:{required_filter}"
            )
    source_probe = probe_video_file(source, ffprobe_path=probe_bin)
    if not source_probe.get("ok"):
        raise LocalVideoEditError(str(source_probe.get("reason") or "input_probe_failed"))
    source_duration_ms = int(source_probe.get("duration_ms") or 0)
    validate_split_ranges(
        items,
        source_duration_ms=source_duration_ms,
        coverage_required=bool(coverage_required),
    )
    coverage = validate_exact_coverage(items, source_duration_ms)
    outputs: list[dict[str, Any]] = []
    total = len(items)
    for item in items:
        if progress:
            progress({"stage": "processing_video", "processed": item.index - 1, "total": total, "current_part": item.index})
        target = workspace_path / split_output_name(item.index, total)
        command = build_split_ffmpeg_command(
            str(source), item, str(target), ffmpeg_path=ffmpeg, has_audio=bool(source_probe.get("has_audio"))
        )
        _run_checked(command, timeout=timeout, deadline_monotonic=deadline_monotonic)
        validation = validate_mp4_output(
            target,
            expected_duration_ms=item.duration_ms,
            require_audio=bool(source_probe.get("has_audio")),
            ffprobe_path=probe_bin,
        )
        if not validation.get("ok"):
            raise LocalVideoEditError(f"split_part_invalid:{item.index}:{validation.get('reason')}")
        outputs.append({"index": item.index, "path": str(target), "duration_ms": item.duration_ms, "validation": validation})
        _enforce_workspace_budget(workspace_path, admitted_workspace_budget)
        if progress:
            progress({"stage": "validating_output", "processed": item.index, "total": total, "current_part": item.index})
    actual_total = sum(int(item["validation"].get("duration_ms") or 0) for item in outputs)
    expected_total = sum(item.duration_ms for item in items)
    tolerance = max(1_000, 750 * len(items))
    if abs(actual_total - expected_total) > tolerance:
        raise LocalVideoEditError("split_total_duration_mismatch")
    return {
        "ok": True,
        "outputs": outputs,
        "part_count": total,
        "coverage": coverage,
        "source_duration_ms": source_duration_ms,
        "actual_total_duration_ms": actual_total,
        "expected_total_duration_ms": expected_total,
        "audio_preserved": bool(source_probe.get("has_audio")),
        "provider_called": False,
        "xu_charged": 0,
    }


def public_plan_summary(
    plan: dict[str, Any],
    *,
    source_duration_ms: int = 0,
) -> list[str]:
    lines: list[str] = []
    trim = dict(plan.get("trim") or {})
    trim_start = int(trim.get("start_ms") or 0)
    trim_end = int(trim.get("end_ms") or 0)
    source_duration = max(0, int(source_duration_ms or 0))
    explicit_trim = bool(
        trim_start > 0
        or (
            trim_end > 0
            and (source_duration <= 0 or trim_end < source_duration)
        )
    )
    if explicit_trim:
        lines.append("Cắt theo khoảng đã chọn")
    aspect = str((plan.get("crop_or_fit") or {}).get("aspect_ratio") or "keep")
    if aspect != "keep":
        mode = str((plan.get("crop_or_fit") or {}).get("mode") or "fit")
        mode_label = "Cắt vừa khung" if mode == "crop" else "Giữ toàn cảnh có viền"
        lines.append(f"Tỉ lệ {aspect} · {mode_label}")
    if str(plan.get("resolution") or "keep") != "keep":
        lines.append(f"Độ phân giải {plan['resolution']}")
    if int(plan.get("rotation") or 0):
        lines.append(f"Xoay {int(plan['rotation'])}°")
    if str(plan.get("flip") or "none") != "none":
        lines.append("Lật ngang" if plan["flip"] == "horizontal" else "Lật dọc")
    if float(plan.get("speed") or 1.0) != 1.0:
        lines.append(f"Tốc độ {float(plan['speed']):g}x")
    volume_value = plan.get("volume")
    volume = 1.0 if volume_value is None else float(volume_value)
    if volume != 1.0:
        lines.append("Tắt tiếng" if volume == 0 else f"Âm lượng {volume * 100:g}%")
    if int(plan.get("brightness_percent") or 100) != 100:
        lines.append(f"Độ sáng {int(plan['brightness_percent'])}%")
    if plan.get("text_overlay"):
        lines.append("Chèn chữ")
    if plan.get("logo_overlay"):
        logo = dict(plan.get("logo_overlay") or {})
        position_labels = {
            "top_left": "Trên trái",
            "top_center": "Trên giữa",
            "top_right": "Trên phải",
            "center_left": "Giữa trái",
            "center": "Chính giữa",
            "center_right": "Giữa phải",
            "bottom_left": "Dưới trái",
            "bottom_center": "Dưới giữa",
            "bottom_right": "Dưới phải",
        }
        position = position_labels.get(
            str(logo.get("position") or "top_right"),
            "Trên phải",
        )
        try:
            opacity = float(logo.get("opacity", 1.0))
        except (TypeError, ValueError, OverflowError):
            opacity = 1.0
        if not math.isfinite(opacity):
            opacity = 1.0
        opacity_percent = int(round(max(0.0, min(1.0, opacity)) * 100))
        lines.append(f"Logo / watermark · {position} · {opacity_percent}%")
    if plan.get("subtitle_file"):
        lines.append("Chèn phụ đề SRT")
    if str(plan.get("color_preset") or "keep") != "keep":
        color_labels = {
            "bright_clear": "Sáng rõ",
            "light_cinematic": "Điện ảnh nhẹ",
            "warm": "Tông ấm",
            "cool": "Tông lạnh",
            "high_contrast": "Tương phản cao",
            "black_white": "Đen trắng",
        }
        lines.append("Màu: " + color_labels.get(str(plan.get("color_preset")), "Cấu hình màu cục bộ"))
    if plan.get("remove_middle"):
        lines.append("Bỏ đoạn giữa và nối lại thành một MP4")
    quality = dict(plan.get("quality_filters") or {})
    if quality.get("sharpen"):
        lines.append("Làm rõ nhẹ")
    if quality.get("denoise"):
        lines.append("Giảm nhiễu nhẹ")
    if str(plan.get("audio_normalization") or "off") == "loudnorm":
        lines.append("Cân bằng âm lượng tự động")
    effects = dict(plan.get("local_effects") or {})
    if int(effects.get("fade_in_ms") or 0) or int(effects.get("fade_out_ms") or 0):
        lines.append("Mờ vào / mờ ra")
    if effects.get("vignette"):
        lines.append("Viền tối nhẹ")
    if effects.get("slow_zoom"):
        lines.append("Phóng chậm nhẹ")
    if plan.get("concat_inputs"):
        lines.append(f"Ghép {len(plan['concat_inputs']) + 1} video")
    return lines or ["Giữ nguyên hình và âm thanh"]
