"""One translation master to separate subtitle and dubbing copies."""

from __future__ import annotations

from typing import Any

from .duration_fit import build_dub_script
from .subtitle_adapter import build_subtitle_copy


def build_translated_copies(source_master: dict[str, Any], translation_master: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "subtitle_copy": build_subtitle_copy(source_master, translation_master),
        "dub_script": build_dub_script(source_master, translation_master),
    }


__all__ = ["build_dub_script", "build_subtitle_copy", "build_translated_copies"]
