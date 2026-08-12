"""Canonical Script-to-Video planning helpers.

This module is provider-free.  It owns exact script preservation, deterministic
content choices, and the prompt contract used by the public AI-script route.
Rendering, billing, Telegram I/O, and provider calls remain with their existing
owners in ``bot.py``.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from typing import Any, Iterable, Mapping
import xml.etree.ElementTree as ET
import zipfile

from services import video_profile_catalog


MIN_SCENES = 5
MAX_SCENES = 20
PROFILE_PAGE_SIZE = 8
PROFILE_PAGE_COUNT = 4

GOALS = {
    "sales": ("🛍", "Bán hàng / chuyển đổi"),
    "introduce": ("✨", "Giới thiệu sản phẩm / thương hiệu"),
    "educate": ("🎓", "Hướng dẫn / chia sẻ kiến thức"),
    "story": ("📖", "Kể chuyện / tạo cảm xúc"),
    "engage": ("🔥", "Tăng tương tác / giữ người xem"),
}

AUDIENCES = {
    "prospects": "Khách hàng tiềm năng",
    "beginners": "Người mới tìm hiểu",
    "community": "Cộng đồng / người theo dõi",
    "professionals": "Người có chuyên môn",
    "families": "Gia đình / người dùng phổ thông",
}

PLATFORMS = {
    "tiktok_reels": "TikTok / Reels",
    "youtube_shorts": "YouTube Shorts",
    "facebook": "Facebook",
    "ads_landing": "Quảng cáo / website",
    "multi": "Nhiều nền tảng",
}

STYLES = {
    "realistic": "Chân thật, tự nhiên",
    "cinematic": "Điện ảnh, giàu cảm xúc",
    "sales_clear": "Bán hàng rõ lợi ích",
    "storytelling": "Kể chuyện có cao trào",
    "educational": "Kiến thức dễ hiểu",
}

RATIOS = {
    "9x16": "9:16",
    "16x9": "16:9",
    "1x1": "1:1",
    "4x5": "4:5",
}

DURATION_SECONDS_PER_SCENE = (8, 12, 15)

_SCENE_HEADING_RE = re.compile(
    r"(?im)^\s*(?:cảnh|scene)\s*\d{1,2}\s*[:.\-)–—]?\s*"
)
_NUMBERED_HEADING_RE = re.compile(r"(?m)^\s*\d{1,2}\s*[.)\-–—:]\s+")
_PARAGRAPH_BREAK_RE = re.compile(r"\n[ \t]*\n+")
_LINE_BREAK_RE = re.compile(r"\n")
_SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?…])[ \t\n]+(?=\S)")
_WORD_BREAK_RE = re.compile(r"\s+")

_WORDPROCESSING_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_DOCX_TEXT_TAGS = {
    f"{{{_WORDPROCESSING_NS}}}t",
    f"{{{_DRAWING_NS}}}t",
}
_DOCX_TAB_TAG = f"{{{_WORDPROCESSING_NS}}}tab"
_DOCX_BREAK_TAGS = {
    f"{{{_WORDPROCESSING_NS}}}br",
    f"{{{_WORDPROCESSING_NS}}}cr",
}
_DOCX_PARAGRAPH_TAG = f"{{{_WORDPROCESSING_NS}}}p"
_DOCX_CELL_TAG = f"{{{_WORDPROCESSING_NS}}}tc"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split()).strip()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _docx_part_text(xml_bytes: bytes) -> str:
    output: list[str] = []
    try:
        events = ET.iterparse(io.BytesIO(xml_bytes), events=("end",))
        for _event, element in events:
            if element.tag in _DOCX_TEXT_TAGS:
                output.append(str(element.text or ""))
            elif element.tag == _DOCX_TAB_TAG:
                output.append("\t")
            elif element.tag in _DOCX_BREAK_TAGS:
                output.append("\n")
            elif element.tag == _DOCX_CELL_TAG:
                output.append("\t")
            elif element.tag == _DOCX_PARAGRAPH_TAG:
                output.append("\n")
            element.clear()
    except ET.ParseError as exc:
        raise ValueError("docx_xml_invalid") from exc
    return "".join(output).replace("\t\n", "\n").strip("\n\t")


def extract_docx_text(data: bytes) -> str:
    """Read all customer-visible Word XML without silently dropping tables or text boxes."""

    try:
        with zipfile.ZipFile(io.BytesIO(bytes(data or b""))) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                raise ValueError("docx_document_xml_missing")
            headers = sorted(name for name in names if re.fullmatch(r"word/header\d+\.xml", name))
            footers = sorted(name for name in names if re.fullmatch(r"word/footer\d+\.xml", name))
            supporting = [
                name
                for name in ("word/footnotes.xml", "word/endnotes.xml", "word/comments.xml")
                if name in names
            ]
            ordered_parts = [*headers, "word/document.xml", *footers, *supporting]
            parts = [_docx_part_text(archive.read(name)) for name in ordered_parts]
    except (zipfile.BadZipFile, OSError, KeyError) as exc:
        raise ValueError("docx_invalid") from exc
    return "\n\n".join(part for part in parts if part).strip()


def goal_label(value: str) -> str:
    icon, label = GOALS.get(str(value or ""), ("🎯", _clean(value) or "Chưa chọn"))
    return f"{icon} {label}"


def profile_page(page: int) -> list[dict[str, Any]]:
    page_number = max(1, min(PROFILE_PAGE_COUNT, int(page or 1)))
    profiles = [dict(item) for item in video_profile_catalog.PROFILE_SEEDS if bool(item.get("is_active", 1))]
    start = (page_number - 1) * PROFILE_PAGE_SIZE
    return profiles[start:start + PROFILE_PAGE_SIZE]


def profile_record(profile_key: str) -> dict[str, Any]:
    return dict(video_profile_catalog.PROFILE_BY_KEY.get(str(profile_key or "")) or {})


def profile_content_suggestions(
    profile_key: str,
    *,
    goal: str = "",
    revision: int = 0,
) -> list[dict[str, Any]]:
    profile = profile_record(profile_key)
    public_name = _clean(profile.get("public_name")) or "Nội dung video"
    description = _clean(profile.get("description"))
    pattern = [_clean(item) for item in profile.get("default_scene_pattern") or [] if _clean(item)]
    if not pattern:
        pattern = ["Mở đầu", "Diễn biến", "Cao trào", "Kết"]
    structure = " → ".join(pattern)
    goal_text = goal_label(goal)
    first = pattern[0]
    second = pattern[1] if len(pattern) > 1 else pattern[0]
    climax = pattern[-2] if len(pattern) > 1 else pattern[0]
    ending = pattern[-1]
    angles = (
        (
            f"{first} làm điểm mở",
            f"Mở đúng bằng “{first}”, phát triển qua “{second}” và kết trọn ở “{ending}”.",
        ),
        (
            f"{second} làm trọng tâm",
            f"Đưa “{second}” lên thành chi tiết giữ người xem, rồi lần lượt hoàn thành mạch {structure}.",
        ),
        (
            f"Cao trào tại {climax}",
            f"Dồn các cảnh trước về “{climax}”, sau đó khép lại bằng “{ending}” thay vì kết đột ngột.",
        ),
        (
            f"Mở từ kết quả {ending}",
            f"Cho người xem thấy “{ending}” trước, quay lại “{first}” và kể đủ nguyên nhân theo cấu trúc {structure}.",
        ),
        (
            f"Trọn mạch {first} đến {ending}",
            f"Giữ nguyên thứ tự đặc trưng {structure}; mỗi phần thành một nhịp rõ và không lặp ý.",
        ),
    )
    offset = max(0, int(revision or 0)) % len(angles)
    rotated = angles[offset:] + angles[:offset]
    return [
        {
            "id": f"{profile_key}:{index}:{revision}",
            "title": f"{title} · {public_name}",
            "brief": (
                f"{detail} Loại nội dung: {public_name}. {description} "
                f"Mục tiêu: {goal_text}."
            ).strip(),
            "hook": f"Mở ngay bằng “{title}” và cho người xem thấy điều đáng quan tâm của {public_name.lower()}.",
            "structure": structure,
            "profile_key": str(profile_key or ""),
        }
        for index, (title, detail) in enumerate(rotated, 1)
    ]


def idea_library_suggestions(*, goal: str = "", revision: int = 0) -> list[dict[str, Any]]:
    offsets = {"sales": 0, "introduce": 4, "educate": 12, "story": 10, "engage": 5}
    profiles = [dict(item) for item in video_profile_catalog.PROFILE_SEEDS]
    start = (offsets.get(str(goal or ""), 0) + max(0, int(revision or 0)) * 5) % len(profiles)
    selected = [profiles[(start + index) % len(profiles)] for index in range(5)]
    rows: list[dict[str, Any]] = []
    for index, profile in enumerate(selected, 1):
        suggestion = profile_content_suggestions(
            str(profile.get("profile_key") or ""),
            goal=goal,
            revision=revision + index - 1,
        )[0]
        rows.append({**suggestion, "id": f"idea:{index}:{revision}"})
    return rows


def estimated_scene_count(duration_seconds: int) -> int:
    duration = max(1, int(duration_seconds or 0))
    return max(MIN_SCENES, min(MAX_SCENES, round(duration / 8)))


def duration_options(scene_count: int) -> tuple[int, int, int]:
    """Return short, balanced and long script durations for the chosen scenes."""

    count = max(MIN_SCENES, min(MAX_SCENES, safe_count(scene_count) or MIN_SCENES))
    return tuple(count * seconds for seconds in DURATION_SECONDS_PER_SCENE)


def duration_bounds(scene_count: int) -> tuple[int, int]:
    options = duration_options(scene_count)
    return options[0], options[-1]


def _candidate_boundaries(source: str) -> list[int]:
    for pattern in (_SCENE_HEADING_RE, _NUMBERED_HEADING_RE):
        matches = list(pattern.finditer(source))
        if len(matches) >= MIN_SCENES:
            starts = [match.start() for match in matches]
            if starts[0] > 0:
                starts[0] = 0
            return sorted(set(starts))
    paragraph_ends = [match.end() for match in _PARAGRAPH_BREAK_RE.finditer(source)]
    if paragraph_ends:
        return [0, *paragraph_ends]
    line_ends = [match.end() for match in _LINE_BREAK_RE.finditer(source)]
    if line_ends:
        return [0, *line_ends]
    sentence_ends = [match.end() for match in _SENTENCE_BREAK_RE.finditer(source)]
    if sentence_ends:
        return [0, *sentence_ends]
    return [0]


def _nearest_split(
    source: str,
    target: int,
    minimum: int,
    maximum: int,
    *,
    previous: int,
    remaining_scenes: int,
    nonspace_prefix: list[int],
) -> int:
    def valid(position: int) -> bool:
        current_content = nonspace_prefix[position] - nonspace_prefix[previous]
        remaining_content = nonspace_prefix[len(source)] - nonspace_prefix[position]
        return current_content > 0 and remaining_content >= remaining_scenes

    word_boundaries = [
        match.end()
        for match in _WORD_BREAK_RE.finditer(source, minimum, maximum)
        if minimum <= match.end() <= maximum
    ]
    candidates = sorted(
        {max(minimum, min(maximum, target)), *word_boundaries},
        key=lambda value: (abs(value - target), value),
    )
    for position in candidates:
        if valid(position):
            return position
    for distance in range(1, max(target - minimum, maximum - target) + 1):
        for position in (target - distance, target + distance):
            if minimum <= position <= maximum and valid(position):
                return position
    raise ValueError("script_partition_failed")


def exact_partition(source_text: str, scene_count: int) -> dict[str, Any]:
    source = str(source_text or "")
    if not source.strip():
        return {"ok": False, "reason": "empty_script", "source_text": source, "scenes": []}
    count = max(MIN_SCENES, min(MAX_SCENES, int(scene_count or MIN_SCENES)))
    nonspace_prefix = [0]
    for character in source:
        nonspace_prefix.append(nonspace_prefix[-1] + (0 if character.isspace() else 1))
    if nonspace_prefix[-1] < count:
        return {
            "ok": False,
            "reason": "script_too_short_for_scene_count",
            "source_text": source,
            "scene_count": count,
            "scenes": [],
        }
    boundaries = [0]
    for index in range(1, count):
        target = round(len(source) * index / count)
        minimum = boundaries[-1] + 1
        maximum = len(source) - (count - index)
        try:
            boundary = _nearest_split(
                source,
                target,
                minimum,
                maximum,
                previous=boundaries[-1],
                remaining_scenes=count - index,
                nonspace_prefix=nonspace_prefix,
            )
        except ValueError:
            return {
                "ok": False,
                "reason": "script_partition_failed",
                "source_text": source,
                "scene_count": count,
                "scenes": [],
            }
        boundaries.append(boundary)
    boundaries.append(len(source))
    scenes = [source[boundaries[index]:boundaries[index + 1]] for index in range(count)]
    if any(not item.strip() for item in scenes) or "".join(scenes) != source:
        return {"ok": False, "reason": "script_partition_failed", "source_text": source, "scenes": []}
    ranges = [
        {"scene_index": index + 1, "start": boundaries[index], "end": boundaries[index + 1]}
        for index in range(count)
    ]
    joined = "".join(scenes)
    return {
        "ok": True,
        "reason": "",
        "source_text": source,
        "scene_count": count,
        "scenes": scenes,
        "ranges": ranges,
        "coverage": {
            "no_truncation": True,
            "source_length": len(source),
            "covered_length": len(joined),
            "coverage_percent": 100,
            "source_sha256": _digest(source),
            "joined_sha256": _digest(joined),
            "exact_match": joined == source,
        },
    }


def parse_script(source_text: str) -> dict[str, Any]:
    source = str(source_text or "")
    if not source.strip():
        return {
            "source_text": source,
            "proposed_scenes": [],
            "proposed_scene_count": 0,
            "scene_ranges": [],
            "scene_count_confirmed": False,
            "coverage": {"no_truncation": True, "exact_match": True, "coverage_percent": 100},
        }
    starts = [value for value in _candidate_boundaries(source) if 0 <= value < len(source)]
    starts = sorted(set([0, *starts]))
    scenes = [source[starts[index]:starts[index + 1]] for index in range(len(starts) - 1)]
    scenes.append(source[starts[-1]:])
    scenes = [item for item in scenes if item]
    if len(scenes) < MIN_SCENES or any(not item.strip() for item in scenes):
        meaningful_count = sum(1 for item in scenes if item.strip())
        partition = exact_partition(
            source,
            max(MIN_SCENES, min(MAX_SCENES, meaningful_count)),
        )
        if not partition.get("ok"):
            return {
                "source_text": source,
                "proposed_scenes": [],
                "proposed_scene_count": 0,
                "scene_ranges": [],
                "scene_count_confirmed": False,
                "error": str(partition.get("reason") or "script_partition_failed"),
                "coverage": {"no_truncation": True, "exact_match": False, "coverage_percent": 0},
            }
        scenes = list(partition["scenes"])
    if len(scenes) > MAX_SCENES:
        partition = exact_partition(source, MAX_SCENES)
        if not partition.get("ok"):
            return {
                "source_text": source,
                "proposed_scenes": [],
                "proposed_scene_count": 0,
                "scene_ranges": [],
                "scene_count_confirmed": False,
                "error": str(partition.get("reason") or "script_partition_failed"),
                "coverage": {"no_truncation": True, "exact_match": False, "coverage_percent": 0},
            }
        scenes = list(partition["scenes"])
    cursor = 0
    ranges = []
    for index, scene in enumerate(scenes, 1):
        ranges.append({"scene_index": index, "start": cursor, "end": cursor + len(scene)})
        cursor += len(scene)
    joined = "".join(scenes)
    return {
        "source_text": source,
        "proposed_scenes": scenes,
        "proposed_scene_count": len(scenes),
        "scene_ranges": ranges,
        "scene_count_confirmed": False,
        "coverage": {
            "no_truncation": True,
            "source_length": len(source),
            "covered_length": len(joined),
            "coverage_percent": 100 if joined == source else 0,
            "source_sha256": _digest(source),
            "joined_sha256": _digest(joined),
            "exact_match": joined == source,
        },
    }


def semantic_beats(source_text: str, scene_count: int) -> dict[str, Any]:
    requested = max(MIN_SCENES, min(MAX_SCENES, int(scene_count or MIN_SCENES)))
    parsed = parse_script(source_text)
    if (
        safe_count(parsed.get("proposed_scene_count")) == requested
        and (parsed.get("coverage") or {}).get("exact_match")
    ):
        partition = {
            "ok": True,
            "reason": "",
            "source_text": str(parsed.get("source_text") or ""),
            "scene_count": requested,
            "scenes": list(parsed.get("proposed_scenes") or []),
            "ranges": list(parsed.get("scene_ranges") or []),
            "coverage": dict(parsed.get("coverage") or {}),
        }
    else:
        partition = exact_partition(source_text, requested)
    if not partition.get("ok"):
        return partition
    beats = []
    total = int(partition["scene_count"])
    for index, (content, source_range) in enumerate(
        zip(partition["scenes"], partition["ranges"]),
        1,
    ):
        clean = _clean(content)
        beats.append({
            "role": "customer_conclusion" if index == total else f"customer_scene_{index:02d}",
            "main_idea": clean,
            "action": clean,
            "development": clean,
            "completion": "Hoàn tất trọn phần kịch bản này trước khi nối sang cảnh kế tiếp.",
            "source_text_exact": content,
            "source_start": int(source_range["start"]),
            "source_end": int(source_range["end"]),
        })
    return {**partition, "semantic_beats": beats}


def state_contract(state: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep the approved full script in UI/session state without execution data."""

    current = dict(state or {})
    source = str(current.get("manual_script_raw") or current.get("script_text") or "")
    scenes = [str(item) for item in current.get("parsed_script_scenes") or []]
    ranges = [
        dict(item)
        for item in current.get("parsed_script_ranges") or []
        if isinstance(item, Mapping)
    ]
    coverage = dict(current.get("script_coverage") or {})
    count = safe_count(current.get("scene_count"))
    cursor = 0
    exact = bool(
        source.strip()
        and current.get("scene_count_confirmed")
        and MIN_SCENES <= count <= MAX_SCENES
        and len(scenes) == count
        and len(ranges) == count
    )
    if exact:
        for index, item in enumerate(ranges, 1):
            start = safe_count(item.get("start"))
            end = safe_count(item.get("end"))
            if (
                safe_count(item.get("scene_index")) != index
                or start != cursor
                or end < start
                or source[start:end] != scenes[index - 1]
            ):
                exact = False
                break
            cursor = end
    joined = "".join(scenes)
    digest = _digest(source)
    exact = bool(
        exact
        and cursor == len(source)
        and joined == source
        and coverage.get("no_truncation")
        and coverage.get("exact_match")
        and safe_count(coverage.get("coverage_percent")) == 100
        and str(coverage.get("source_sha256") or "").lower() == digest
        and str(coverage.get("joined_sha256") or "").lower() == digest
    )
    if not exact:
        raise ValueError("script_coverage_incomplete")
    return {
        "script_text": source,
        "manual_script_raw": source,
        "parsed_script_scenes": scenes,
        "parsed_script_ranges": ranges,
        "script_coverage": {
            **coverage,
            "no_truncation": True,
            "source_length": len(source),
            "covered_length": len(source),
            "coverage_percent": 100,
            "source_sha256": digest,
            "joined_sha256": digest,
            "exact_match": True,
        },
        "scene_count_confirmed": True,
        "script_source": str(current.get("script_source") or "customer"),
        "script_metadata": dict(current.get("script_metadata") or {}),
        "script_sha256": digest,
        "script_exact_match": True,
    }


def safe_count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def build_ai_prompt(state: Mapping[str, Any]) -> str:
    draft = dict(state or {})
    scene_count = max(
        MIN_SCENES,
        min(
            MAX_SCENES,
            safe_count(draft.get("script_entry_scene_count")) or MIN_SCENES,
        ),
    )
    minimum_duration, maximum_duration = duration_bounds(scene_count)
    duration = safe_count(draft.get("script_duration_seconds")) or duration_options(scene_count)[1]
    duration = max(minimum_duration, min(maximum_duration, duration))
    profile = profile_record(str(draft.get("script_profile_key") or ""))
    content = _clean(draft.get("script_content_brief") or draft.get("script_topic"))
    if not content:
        raise ValueError("script_content_required")
    revision = max(1, int(draft.get("script_ai_revision") or 1))
    selected_goal = _clean(draft.get("script_goal_label"))
    if not selected_goal:
        selected_goal = goal_label(str(draft.get("script_goal") or ""))
    return (
        "Bạn là biên kịch Video AI của TOAN AAS. Hãy tạo MỘT KỊCH BẢN HOÀN CHỈNH bằng tiếng Việt, "
        "không tạo video, không tóm tắt đầu vào, không bỏ chi tiết và không dùng tên model/provider. "
        "Đây là kịch bản dài nhiều cảnh, KHÔNG phải một prompt video một cảnh và KHÔNG phải tập hợp các prompt rời.\n\n"
        f"Lần tạo: {revision}\n"
        f"Mục tiêu: {selected_goal}\n"
        f"Nội dung/chủ đề/sản phẩm: {content}\n"
        f"Loại nội dung: {_clean(profile.get('public_name')) or 'Tự nhập'}\n"
        f"Cấu trúc gợi ý: {' → '.join(str(item) for item in profile.get('default_scene_pattern') or []) or 'Mở → phát triển → cao trào → kết'}\n"
        f"Đối tượng xem: {_clean(draft.get('script_audience_label')) or 'Người xem phù hợp nội dung'}\n"
        f"Nền tảng: {_clean(draft.get('script_platform_label')) or 'Video ngắn'}\n"
        f"Phong cách: {_clean(draft.get('script_style_label')) or 'Chân thật, rõ ràng'}\n"
        f"Tỉ lệ: {_clean(draft.get('script_ratio')) or '9:16'}\n"
        f"Thời lượng mục tiêu: {duration} giây\n"
        f"Số cảnh mục tiêu: {scene_count} cảnh, tối thiểu {MIN_SCENES} cảnh\n\n"
        "Kịch bản phải hiển thị đầy đủ nguyên văn cho khách sửa trực tiếp và PHẢI có đúng các phần sau:\n"
        "1. TÊN KỊCH BẢN\n"
        "2. CONCEPT\n"
        "3. HOOK\n"
        "4. MỞ BÀI\n"
        "5. DIỄN BIẾN\n"
        "6. CAO TRÀO\n"
        "7. KẾT\n"
        "8. CTA\n"
        "9. NGƯỜI DẪN / NARRATOR: ghi toàn bộ lời dẫn\n"
        "10. NHÂN VẬT VÀ TOÀN BỘ LỜI THOẠI CỦA TỪNG NHÂN VẬT\n"
        f"11. ĐÚNG {scene_count} CẢNH, đánh dấu CẢNH 1 đến CẢNH {scene_count}. Trong MỖI cảnh ghi đủ:\n"
        "- semantic beat / mục tiêu cảnh\n"
        "- hành động và diễn biến trọn vẹn\n"
        "- bối cảnh\n"
        "- nhân vật xuất hiện\n"
        "- lời narrator\n"
        "- lời thoại từng nhân vật\n"
        "- ý đồ máy quay, cỡ cảnh và chuyển động camera\n"
        "- prompt video chi tiết cho riêng cảnh đó, đủ bối cảnh, chủ thể, hành động, ánh sáng, camera và cảm xúc\n"
        "- ý đồ chuyển cảnh sang cảnh kế tiếp\n"
        "- trạng thái kết cảnh; không cắt giữa câu nói hoặc hành động\n\n"
        "Toàn bộ các cảnh phải giữ một mạch ngữ cảnh xuyên suốt: nhất quán nhân vật, nhận diện, sản phẩm, "
        "không gian, đạo cụ, thời gian, nguyên nhân-kết quả và trạng thái nối tiếp. Mỗi cảnh phải có chiều sâu hơn "
        "Prompt → Video một cảnh nhưng vẫn phục vụ cùng concept, cao trào và kết thúc của kịch bản.\n\n"
        "Chỉ trả về toàn bộ kịch bản hoàn chỉnh. Không thêm lời giải thích trước hoặc sau kịch bản."
    )


def public_choice_label(mapping: Mapping[str, str], value: str, fallback: str = "") -> str:
    return str(mapping.get(str(value or "")) or fallback or _clean(value))


def public_profile_label(profile_key: str) -> str:
    profile = profile_record(profile_key)
    return f"{profile.get('icon') or '📝'} {_clean(profile.get('public_name')) or 'Tự nhập'}".strip()


def compact_suggestions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in rows][:5]
