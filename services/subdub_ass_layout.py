"""Shared production SubDub ASS text fitting.

This is the frame-fit primitive used by both the Translation SubDub renderer
and Product Video subtitle materialization. It has no provider, wallet, UI, or
database side effects.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Callable

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - the deterministic width fallback remains available
    Image = ImageDraw = ImageFont = None


TextNormalizer = Callable[[str], str]
FontLoader = Callable[[int], Any]


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(re.sub(r"\s+", " ", line).strip() for line in text.splitlines()).strip()


def fit_text_layout(
    text: str,
    style: dict | None,
    max_lines: int = 2,
    *,
    normalize_text: TextNormalizer | None = None,
    font_loader: FontLoader | None = None,
) -> dict:
    """Fit all subtitle text inside the SubDub safe frame without dropping it."""

    current_style = dict(style or {})
    normalizer = normalize_text or _normalize_text
    normalized = normalizer(str(text or "")).replace("\\N", "\n")
    normalized = re.sub(r"[{}]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    play_res_x = max(1, int(current_style.get("play_res_x") or 1280))
    margin_l = max(
        0,
        int(current_style.get("subtitle_margin_l_after") or round(play_res_x * 0.04)),
    )
    margin_r = max(
        0,
        int(current_style.get("subtitle_margin_r_after") or round(play_res_x * 0.04)),
    )
    requested_size = max(
        6,
        int(current_style.get("render_size") or current_style.get("size") or 48),
    )
    line_limit = max(1, min(2, int(max_lines or 2)))
    if not normalized:
        return {
            "text": "",
            "font_size": requested_size,
            "line_count": 0,
            "max_line_width_px": 0,
            "available_width_px": max(1, play_res_x - margin_l - margin_r),
            "fits_width": True,
        }

    font_cache: dict[int, Any] = {}
    measurement_cache: dict[tuple[int, str], float] = {}
    measurement_draw = (
        ImageDraw.Draw(Image.new("L", (1, 1), 0))
        if Image is not None and ImageDraw is not None
        else None
    )

    def _font(size: int):
        if size in font_cache:
            return font_cache[size]
        if ImageFont is None:
            return None
        path = str(current_style.get("subtitle_font_path") or "").strip()
        try:
            if path and os.path.isfile(path):
                font_cache[size] = ImageFont.truetype(path, size)
            elif callable(font_loader):
                font_cache[size] = font_loader(size)
            else:
                font_cache[size] = None
        except Exception:
            font_cache[size] = None
        return font_cache[size]

    def _measure(value: str, size: int, font) -> float:
        cache_key = (size, value)
        if cache_key in measurement_cache:
            return measurement_cache[cache_key]
        if measurement_draw is not None and font is not None:
            try:
                box = measurement_draw.textbbox((0, 0), value, font=font)
                measurement_cache[cache_key] = float(max(0, box[2] - box[0]))
                return measurement_cache[cache_key]
            except Exception:
                pass
        units = 0.0
        for char in value:
            if char.isspace():
                units += 0.34
            elif unicodedata.east_asian_width(char) in {"W", "F"}:
                units += 1.0
            elif char.isupper():
                units += 0.68
            elif char.isalnum():
                units += 0.56
            else:
                units += 0.42
        measurement_cache[cache_key] = units * float(size)
        return measurement_cache[cache_key]

    last_layout = None
    for font_size in range(requested_size, 5, -1):
        font = _font(font_size)
        outline = max(0, int(current_style.get("outline") or 0))
        shadow = max(0, int(current_style.get("shadow") or 0))
        box_padding = int(round(font_size * 0.10)) if current_style.get("boxed_background") else 0
        available = max(
            1,
            play_res_x - margin_l - margin_r - (2 * (outline + shadow + box_padding)),
        )
        single_width = _measure(normalized, font_size, font)
        if single_width <= available:
            return {
                "text": normalized,
                "font_size": font_size,
                "line_count": 1,
                "max_line_width_px": single_width,
                "available_width_px": available,
                "fits_width": True,
            }
        if line_limit < 2:
            last_layout = (normalized, font_size, single_width, available)
            continue

        whitespace_splits = [index for index, char in enumerate(normalized) if char == " "]
        split_points = whitespace_splits or list(range(1, len(normalized)))
        best = None
        for split_at in split_points:
            if whitespace_splits:
                first = normalized[:split_at].rstrip()
                second = normalized[split_at + 1 :].lstrip()
            else:
                first = normalized[:split_at]
                second = normalized[split_at:]
            if not first or not second:
                continue
            first_width = _measure(first, font_size, font)
            second_width = _measure(second, font_size, font)
            score = (max(first_width, second_width), abs(first_width - second_width))
            if best is None or score < best[0]:
                best = (score, first, second, first_width, second_width)
        if best is None:
            last_layout = (normalized, font_size, single_width, available)
            continue
        max_width = max(best[3], best[4])
        layout_text = best[1] + r"\N" + best[2]
        last_layout = (layout_text, font_size, max_width, available)
        if max_width <= available:
            return {
                "text": layout_text,
                "font_size": font_size,
                "line_count": 2,
                "max_line_width_px": max_width,
                "available_width_px": available,
                "fits_width": True,
            }

    layout_text, font_size, max_width, available = last_layout or (
        normalized,
        6,
        0.0,
        play_res_x,
    )
    return {
        "text": layout_text,
        "font_size": font_size,
        "line_count": 1 + int(r"\N" in layout_text),
        "max_line_width_px": max_width,
        "available_width_px": available,
        "fits_width": bool(max_width <= available),
    }


__all__ = ["fit_text_layout"]
