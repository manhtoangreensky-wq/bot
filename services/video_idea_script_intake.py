"""Provider-free script intake helpers for the dynamic Video Ideas flow."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable, Mapping


MAX_SCENES = 20
SCENE_SECONDS = 8
HEADING_RE = re.compile(
    r"(?im)^\s*(?:cảnh|scene)\s*(\d{1,2})\s*[:.\-)–—]?\s*"
)
NUMBERED_RE = re.compile(r"(?m)^\s*(\d{1,2})\s*[.)\-–—:]\s+")
SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ỹ0-9])")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split()).strip()


def _segments_from_markers(text: str, pattern: re.Pattern[str]) -> list[str]:
    matches = list(pattern.finditer(text))
    if not matches:
        return []
    rows: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = _clean(text[start:end])
        if value:
            rows.append(value)
    return rows


def split_manual_script(raw_text: str, *, max_scenes: int = MAX_SCENES) -> dict[str, Any]:
    """Split a customer script using explicit structure before punctuation.

    The function never silently truncates. More than ``max_scenes`` returns a
    validation error so the customer can shorten or select the desired part.
    """

    source = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not source:
        return {"ok": False, "reason": "empty_script", "scenes": [], "method": "none"}

    scenes = _segments_from_markers(source, HEADING_RE)
    method = "scene_heading"
    if not scenes:
        scenes = _segments_from_markers(source, NUMBERED_RE)
        method = "numbered_heading"
    if not scenes:
        paragraphs = [_clean(item) for item in re.split(r"\n\s*\n+", source) if _clean(item)]
        if len(paragraphs) > 1:
            scenes = paragraphs
            method = "paragraph"
    if not scenes:
        lines = [_clean(item) for item in source.split("\n") if _clean(item)]
        if len(lines) > 1:
            scenes = lines
            method = "line"
    if not scenes:
        sentences = [_clean(item) for item in SENTENCE_RE.split(_clean(source)) if _clean(item)]
        scenes = sentences if len(sentences) > 1 else [_clean(source)]
        method = "sentence" if len(sentences) > 1 else "single_block"

    if len(scenes) > int(max_scenes):
        return {
            "ok": False,
            "reason": "too_many_scenes",
            "scene_count": len(scenes),
            "max_scenes": int(max_scenes),
            "scenes": scenes,
            "method": method,
        }
    return {
        "ok": True,
        "reason": "",
        "scene_count": len(scenes),
        "estimated_duration_seconds": len(scenes) * SCENE_SECONDS,
        "scenes": scenes,
        "method": method,
        "diagnostics": [scene_diagnostic(item) for item in scenes],
    }


def scene_diagnostic(text: str) -> dict[str, Any]:
    value = _clean(text)
    word_count = len(value.split())
    action_markers = (
        "đi", "đến", "mở", "đóng", "chọn", "dùng", "thử", "nói", "nhìn",
        "giới thiệu", "thực hiện", "chuyển", "đặt", "tạo", "cho thấy", "kết",
    )
    has_action = any(marker in value.lower() for marker in action_markers)
    return {
        "word_count": word_count,
        "too_long": word_count > 45,
        "very_short": word_count < 4,
        "has_action": has_action,
        "needs_action": bool(value and not has_action),
    }


def deterministic_scene_drafts(
    preset: Mapping[str, Any],
    *,
    scene_count: int,
    topic: str = "",
    customer_brief: str = "",
    semantic_beats: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Create an editable local draft without claiming that an AI ran."""

    count = max(1, min(MAX_SCENES, int(scene_count or 1)))
    title = _clean(topic) or _clean(preset.get("title")) or "ý tưởng video"
    brief = _clean(customer_brief)
    beats = [dict(item) for item in semantic_beats if isinstance(item, Mapping)]
    rows: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        beat = beats[index - 1] if index <= len(beats) else {}
        main_idea = _clean(beat.get("main_idea")) or f"Phát triển ý {index} của {title}"
        action = _clean(beat.get("action")) or f"Thể hiện một hành động hoàn chỉnh liên quan trực tiếp đến {title}."
        completion = _clean(beat.get("completion")) or "Khép hành động tự nhiên và để lại trạng thái rõ cho cảnh sau."
        rows.append({
            "scene_index": index,
            "role": _clean(beat.get("role")) or ("customer_conclusion" if index == count else f"customer_scene_{index:02d}"),
            "goal": main_idea,
            "content": action + (f" Yêu cầu riêng: {brief}." if brief else ""),
            "start_state": "Mở bằng trạng thái dễ hiểu, chủ thể và bối cảnh đã ổn định.",
            "development": _clean(beat.get("development")) or action,
            "end_state": completion,
            "image_prompt": (
                f"Cảnh {index}/{count} về {title}: {main_idea}. "
                f"{_clean(preset.get('image_prompt_seed'))} Giữ nhận diện và bố cục liên tục."
            ).strip(),
            "video_prompt": (
                f"Cảnh {index}/{count}: {action} {completion} "
                f"{_clean(preset.get('video_prompt_seed'))} Không cắt giữa hành động hoặc chuyển động camera."
            ).strip(),
            "transition": "Nối từ trạng thái cuối cảnh này sang trạng thái đầu cảnh kế tiếp.",
            "voice_plan": _clean(preset.get("voice_plan")),
            "music_plan": _clean(preset.get("music_plan")),
            "audio_plan": _clean(preset.get("audio_plan")),
            "visual_plan": _clean(preset.get("visual_plan")),
        })
    return rows


def manual_scene_drafts(scenes: Iterable[str], preset: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = [_clean(item) for item in scenes if _clean(item)]
    if len(values) > MAX_SCENES:
        raise ValueError("scene_limit_exceeded")
    total = len(values)
    rows: list[dict[str, Any]] = []
    for index, content in enumerate(values, 1):
        rows.append({
            "scene_index": index,
            "goal": content,
            "content": content,
            "start_state": "Bắt đầu khi chủ thể và bối cảnh của đoạn này đã rõ.",
            "development": "Thể hiện trọn nội dung khách đã viết bằng một hành động hoặc diễn biến dễ hiểu.",
            "end_state": "Kết thúc câu và hành động tự nhiên trước khi chuyển cảnh.",
            "image_prompt": f"Cảnh {index}/{total}: {content}. {_clean(preset.get('image_prompt_seed'))}".strip(),
            "video_prompt": f"Cảnh {index}/{total}: {content}. {_clean(preset.get('video_prompt_seed'))}".strip(),
            "transition": "Nối mạch nội dung sang cảnh kế tiếp mà không cắt giữa câu hoặc hành động.",
            "voice_plan": _clean(preset.get("voice_plan")),
            "music_plan": _clean(preset.get("music_plan")),
            "audio_plan": _clean(preset.get("audio_plan")),
            "visual_plan": _clean(preset.get("visual_plan")),
            "diagnostic": scene_diagnostic(content),
        })
    return rows


def renumber_scene_drafts(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        item = deepcopy(dict(row))
        item["scene_index"] = index
        result.append(item)
    if len(result) > MAX_SCENES:
        raise ValueError("scene_limit_exceeded")
    return result


def edit_scene(rows: Iterable[Mapping[str, Any]], scene_index: int, content: str) -> list[dict[str, Any]]:
    result = renumber_scene_drafts(rows)
    index = int(scene_index) - 1
    if not 0 <= index < len(result):
        raise ValueError("scene_not_found")
    value = _clean(content)
    if not value:
        raise ValueError("empty_scene")
    result[index].update({"goal": value, "content": value, "diagnostic": scene_diagnostic(value)})
    return result


def add_scene(rows: Iterable[Mapping[str, Any]], content: str, *, after_index: int | None = None) -> list[dict[str, Any]]:
    result = renumber_scene_drafts(rows)
    if len(result) >= MAX_SCENES:
        raise ValueError("scene_limit_reached")
    value = _clean(content)
    if not value:
        raise ValueError("empty_scene")
    item = {"goal": value, "content": value, "diagnostic": scene_diagnostic(value)}
    position = len(result) if after_index is None else max(0, min(len(result), int(after_index)))
    result.insert(position, item)
    return renumber_scene_drafts(result)


def delete_scene(rows: Iterable[Mapping[str, Any]], scene_index: int) -> list[dict[str, Any]]:
    result = renumber_scene_drafts(rows)
    if len(result) <= 1:
        raise ValueError("at_least_one_scene_required")
    index = int(scene_index) - 1
    if not 0 <= index < len(result):
        raise ValueError("scene_not_found")
    result.pop(index)
    return renumber_scene_drafts(result)


def merge_scenes(rows: Iterable[Mapping[str, Any]], first_index: int) -> list[dict[str, Any]]:
    result = renumber_scene_drafts(rows)
    index = int(first_index) - 1
    if not 0 <= index < len(result) - 1:
        raise ValueError("adjacent_scene_not_found")
    merged = _clean(f"{result[index].get('content')} {result[index + 1].get('content')}")
    result[index].update({"goal": merged, "content": merged, "diagnostic": scene_diagnostic(merged)})
    result.pop(index + 1)
    return renumber_scene_drafts(result)


def split_scene(rows: Iterable[Mapping[str, Any]], scene_index: int, first: str, second: str) -> list[dict[str, Any]]:
    result = renumber_scene_drafts(rows)
    if len(result) >= MAX_SCENES:
        raise ValueError("scene_limit_reached")
    index = int(scene_index) - 1
    if not 0 <= index < len(result):
        raise ValueError("scene_not_found")
    left, right = _clean(first), _clean(second)
    if not left or not right:
        raise ValueError("split_requires_two_parts")
    result[index].update({"goal": left, "content": left, "diagnostic": scene_diagnostic(left)})
    result.insert(index + 1, {"goal": right, "content": right, "diagnostic": scene_diagnostic(right)})
    return renumber_scene_drafts(result)


def move_scene(rows: Iterable[Mapping[str, Any]], scene_index: int, target_index: int) -> list[dict[str, Any]]:
    result = renumber_scene_drafts(rows)
    source = int(scene_index) - 1
    target = int(target_index) - 1
    if not 0 <= source < len(result) or not 0 <= target < len(result):
        raise ValueError("scene_not_found")
    item = result.pop(source)
    result.insert(target, item)
    return renumber_scene_drafts(result)


def semantic_beats_from_drafts(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    beats: list[dict[str, Any]] = []
    numbered = renumber_scene_drafts(rows)
    total = len(numbered)
    for row in numbered:
        content = _clean(row.get("content") or row.get("goal"))
        scene_index = int(row["scene_index"])
        beats.append({
            "role": _clean(row.get("role") or row.get("scene_role"))
            or ("customer_conclusion" if scene_index == total else f"customer_scene_{scene_index:02d}"),
            "main_idea": content,
            "action": _clean(row.get("development")) or content,
            "development": _clean(row.get("development")) or content,
            "completion": _clean(row.get("end_state")) or "Hoàn tất ý và hành động trước khi chuyển cảnh.",
        })
    return beats
