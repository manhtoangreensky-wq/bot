"""Provider-agnostic multi-scene planning and local stitching helpers.

This module has no billing, Telegram, or provider credentials.  The bot adapter
owns confirmation, provider submission/polling, persistence, and result delivery.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


VAULT_FILES = {
    "video_styles": "video_styles.json",
    "scene_templates": "scene_templates.json",
    "camera_moves": "camera_moves.json",
    "product_contexts": "product_contexts.json",
    "audience_pain_points": "audience_pain_points.json",
    "cta_templates": "cta_templates.json",
    "brand_voice": "brand_voice.json",
    "negative_prompt_rules": "negative_prompt_rules.json",
    "platform_rules": "platform_rules.json",
    "localization_rules": "localization_rules.json",
}

REQUIRED_VAULT_FIELDS = {
    "id", "label_vi", "tags", "use_cases", "prompt_template",
    "scene_guidance", "negative_prompt", "platform_hint", "safety_note",
}

DEFAULT_IDS = {
    "video_styles": "style_social_realistic",
    "scene_templates": "scene_problem_solution",
    "camera_moves": "camera_short_form",
    "product_contexts": "context_default_short_ad",
    "audience_pain_points": "pain_default_attention",
    "cta_templates": "cta_soft_action",
    "brand_voice": "voice_vi_clear_warm",
    "negative_prompt_rules": "negative_default_quality",
    "platform_rules": "platform_short_vertical",
    "localization_rules": "locale_vi",
}

SECRET_KEY_PATTERN = re.compile(r"(?i)(api[_-]?key|secret|token|password|authorization|bearer)")


def prompt_vault_dir(base_dir: str | os.PathLike[str] | None = None) -> Path:
    if base_dir:
        return Path(base_dir)
    return Path(__file__).resolve().parent / "data" / "prompt_vault"


def load_prompt_vault(base_dir: str | os.PathLike[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    root = prompt_vault_dir(base_dir)
    vault: dict[str, list[dict[str, Any]]] = {}
    for category, filename in VAULT_FILES.items():
        path = root / filename
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError(f"Prompt vault file {filename} must contain an items list")
        normalized: list[dict[str, Any]] = []
        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError(f"Prompt vault item in {filename} must be an object")
            item = dict(raw)
            item.setdefault("label_en", "")
            missing = REQUIRED_VAULT_FIELDS.difference(item)
            if missing:
                raise ValueError(f"Prompt vault item {item.get('id') or '?'} missing: {sorted(missing)}")
            if SECRET_KEY_PATTERN.search(" ".join(str(key) for key in item)):
                raise ValueError(f"Prompt vault item {item.get('id') or '?'} contains a secret-like field")
            item["tags"] = [str(tag).strip().lower() for tag in item.get("tags", []) if str(tag).strip()]
            item["use_cases"] = [str(use).strip().lower() for use in item.get("use_cases", []) if str(use).strip()]
            normalized.append(item)
        vault[category] = normalized
    return vault


def prompt_vault_has_no_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return all(not SECRET_KEY_PATTERN.search(str(key)) and prompt_vault_has_no_secret(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(prompt_vault_has_no_secret(item) for item in value)
    text = str(value or "")
    return not re.search(r"(?i)(sk-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._-]{12,})", text)


def prompt_vault_status(base_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    vault = load_prompt_vault(base_dir)
    ids = {item.get("id") for items in vault.values() for item in items}
    return {
        "counts": {category: len(items) for category, items in vault.items()},
        "default_fallback_available": all(default_id in ids for default_id in DEFAULT_IDS.values()),
        "no_secrets": prompt_vault_has_no_secret(vault),
    }


def _session_sources(session: dict[str, Any] | None) -> list[dict[str, Any]]:
    root = dict(session or {})
    sources = [root]
    for key in (
        "pending_payload", "source_payload", "session_context", "video_project",
        "video_order", "draft", "project", "product", "context",
    ):
        value = root.get(key)
        if isinstance(value, dict):
            sources.append(value)
    draft = root.get("draft") if isinstance(root.get("draft"), dict) else {}
    for key in ("prompt_bundle", "project", "context"):
        value = draft.get(key)
        if isinstance(value, dict):
            sources.append(value)
    return sources


def _first_value(sources: list[dict[str, Any]], keys: tuple[str, ...], default: Any = "") -> Any:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return value
    return default


def normalize_plan_language(value: Any, prompt: str = "") -> str:
    raw = str(value or "").strip().lower().replace("_", "-")
    if raw.startswith("zh") or raw in {"cn", "chinese", "中文", "中文简体"}:
        return "zh"
    if raw.startswith("en") or raw in {"english", "tiếng anh"}:
        return "en"
    if raw.startswith("vi") or raw in {"vn", "vietnamese", "tiếng việt"}:
        return "vi"
    text = str(prompt or "")
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[ăâđêôơưĂÂĐÊÔƠƯ]|[àáạảãèéẹẻẽìíịỉĩòóọỏõùúụủũỳýỵỷỹ]", text, re.I):
        return "vi"
    return "en" if text and re.fullmatch(r"[\x00-\x7f\s\W]+", text) else "vi"


def _context_tags(text: str) -> set[str]:
    normalized = str(text or "").lower()
    groups = {
        "affiliate": ("affiliate", "tiktok shop", "hoa hồng", "tiếp thị liên kết"),
        "service": ("dịch vụ", "service", "doanh nghiệp", "business", "công ty"),
        "education": ("giáo dục", "hướng dẫn", "tutorial", "explainer", "bài học", "education"),
        "storytelling": ("câu chuyện", "story", "phim ngắn", "nhân vật"),
        "trend": ("trend", "viral", "xu hướng", "pov"),
        "testimonial": ("testimonial", "review", "đánh giá", "kết quả khách hàng", "ugc"),
        "before_after": ("before/after", "before after", "trước và sau", "lột xác"),
        "problem_solution": ("vấn đề", "giải pháp", "problem", "solution", "nỗi đau"),
        "animation": ("pixar", "3d", "hoạt hình", "animation", "cartoon"),
        "documentary": ("documentary", "tài liệu", "phóng sự"),
        "cinematic": ("cinematic", "điện ảnh", "film look"),
        "product": ("sản phẩm", "product", "quảng cáo", "bán hàng", "shop"),
        "social_short": ("tiktok", "reels", "shorts", "video ngắn", "short form"),
    }
    tags = {tag for tag, words in groups.items() if any(word in normalized for word in words)}
    return tags or {"product", "social_short", "problem_solution"}


def _select_item(items: list[dict[str, Any]], tags: set[str], default_id: str, language: str = "") -> dict[str, Any]:
    best: dict[str, Any] | None = None
    best_score = -1
    for item in items:
        item_tags = set(item.get("tags") or []) | set(item.get("use_cases") or [])
        score = len(tags.intersection(item_tags)) * 10
        if item.get("id") == default_id:
            score += 1
        if language and language in item_tags:
            score += 8
        if score > best_score:
            best = item
            best_score = score
    return dict(best or {})


def select_video_context_bundle(
    session: dict[str, Any] | None,
    vault: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    sources = _session_sources(session)
    prompt = str(_first_value(sources, ("user_prompt", "prompt", "video_prompt", "storyboard", "script", "topic", "story"), ""))
    product_type = str(_first_value(sources, ("product_type", "product_name", "product_id", "niche", "topic"), ""))
    platform_hint = str(_first_value(sources, ("platform_hint", "platform", "target_platform"), ""))
    language = normalize_plan_language(_first_value(sources, ("language", "lang", "ui_lang"), ""), prompt)
    text = " ".join((prompt, product_type, platform_hint))
    tags = _context_tags(text)
    platform_lower = platform_hint.lower()
    if any(name in (platform_lower + " " + text.lower()) for name in ("tiktok", "reels", "shorts")):
        tags.add("social_short")
        platform = "TikTok/Reels/Shorts"
    elif "youtube" in platform_lower:
        tags.add("youtube")
        platform = "YouTube"
    else:
        tags.add("social_short")
        platform = "TikTok/Reels/Shorts"
    loaded = vault or load_prompt_vault()

    def choose(category: str, *, lang: str = "") -> dict[str, Any]:
        return _select_item(loaded.get(category, []), tags, DEFAULT_IDS[category], lang)

    bundle = {
        "style_pack": choose("video_styles"),
        "scene_template": choose("scene_templates"),
        "camera_move_pack": choose("camera_moves"),
        "product_context": choose("product_contexts"),
        "audience_pain_points": choose("audience_pain_points"),
        "cta_pack": choose("cta_templates"),
        "brand_voice": choose("brand_voice", lang=language),
        "negative_prompt_rules": choose("negative_prompt_rules"),
        "platform_rules": choose("platform_rules"),
        "localization_rules": choose("localization_rules", lang=language),
        "language": language,
        "platform": platform,
        "tags": sorted(tags),
    }
    if not prompt_vault_has_no_secret(bundle):
        raise ValueError("Selected prompt context contains secret-like data")
    return bundle


def context_bundle_debug_summary(bundle: dict[str, Any] | None) -> dict[str, Any]:
    bundle = dict(bundle or {})
    keys = (
        "style_pack", "scene_template", "camera_move_pack", "product_context",
        "audience_pain_points", "cta_pack", "brand_voice", "negative_prompt_rules",
        "platform_rules", "localization_rules",
    )
    return {
        "selected_ids": {key: str((bundle.get(key) or {}).get("id") or "") for key in keys},
        "tags": list(bundle.get("tags") or []),
        "language": str(bundle.get("language") or "vi"),
        "platform": str(bundle.get("platform") or "TikTok/Reels/Shorts"),
    }


def _clean_text(value: Any, limit: int = 900) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _scene_purpose(index: int, count: int, language: str) -> str:
    if language == "en":
        if index == 1:
            return "hook and establish the main subject"
        if index == count:
            return "resolve the story and give a soft call to action"
        phases = ["show the audience pain", "introduce the solution", "demonstrate the key benefit", "provide believable proof", "show the transformation", "reinforce trust"]
        return f"{phases[(index - 2) % len(phases)]} — beat {index}"
    if language == "zh":
        if index == 1:
            return "吸引注意并建立主要主体"
        if index == count:
            return "完成故事并给出自然行动提示"
        phases = ["展示受众痛点", "引出解决方案", "演示核心优势", "提供可信证据", "展示变化结果", "强化信任"]
        return f"{phases[(index - 2) % len(phases)]}（第{index}段）"
    if index == 1:
        return "hook và thiết lập chủ thể chính"
    if index == count:
        return "khép lại câu chuyện và CTA nhẹ"
    phases = ["nêu nỗi đau người xem", "đưa giải pháp vào tự nhiên", "demo lợi ích chính", "cung cấp bằng chứng đáng tin", "thể hiện chuyển biến", "củng cố niềm tin"]
    return f"{phases[(index - 2) % len(phases)]} — nhịp {index}"


def _localized_scene_copy(language: str, index: int, count: int, subject: str, purpose: str) -> tuple[str, str]:
    if language == "en":
        return (
            f"Scene {index}/{count}: {purpose}. Keep {subject} visually identical to the consistency bible.",
            f"Use one clear action that advances beat {index}; end on a frame that motivates the next scene.",
        )
    if language == "zh":
        return (
            f"场景 {index}/{count}：{purpose}。{subject} 的外观必须与一致性设定完全相同。",
            f"只安排一个明确动作推动第 {index} 段，并以适合衔接下一场的画面结束。",
        )
    return (
        f"Cảnh {index}/{count}: {purpose}. Giữ {subject} đồng nhất tuyệt đối theo consistency bible.",
        f"Chỉ dùng một hành động rõ để đẩy nhịp {index} tiến lên; kết ở khung hình thuận cho cảnh kế tiếp.",
    )


def build_detailed_multiscene_prompt_plan(
    session: dict[str, Any] | None,
    context_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sources = _session_sources(session)
    bundle = context_bundle or select_video_context_bundle(session)
    language = normalize_plan_language(bundle.get("language") or _first_value(sources, ("language", "lang"), "vi"))
    scene_count = max(1, min(20, int(_first_value(sources, ("selected_scene_count", "scene_count"), 1) or 1)))
    estimated_scene_seconds = max(1, int(_first_value(sources, ("estimated_scene_seconds", "scene_duration_seconds"), 6) or 6))
    provider_scene_seconds_raw = _first_value(sources, ("provider_scene_seconds",), 0)
    provider_scene_seconds = max(0, int(provider_scene_seconds_raw or 0))
    aspect_ratio = _clean_text(_first_value(sources, ("selected_video_aspect_ratio", "aspect_ratio"), "9:16"), 12) or "9:16"
    platform = _clean_text(bundle.get("platform") or _first_value(sources, ("platform", "platform_hint"), "TikTok/Reels/Shorts"), 80)
    package = _clean_text(_first_value(sources, ("task3d_package_id", "package_id", "selected_video_tier", "video_tier", "package"), ""), 80)
    prompt = _clean_text(_first_value(sources, ("user_prompt", "original_prompt", "prompt", "video_prompt", "storyboard", "script", "topic", "story"), ""), 1200)
    product = _clean_text(_first_value(sources, ("product_name", "product", "product_type", "topic"), ""), 240)
    character = _clean_text(_first_value(sources, ("character_description", "character", "main_character", "target_audience"), ""), 260)
    location = _clean_text(_first_value(sources, ("location", "setting", "scene_location"), ""), 240)
    logo = _clean_text(_first_value(sources, ("logo_watermark", "watermark", "logo", "logo_file_id", "watermark_text"), ""), 260)
    selected_tools = _first_value(sources, ("selected_tools", "selected_addons", "addons", "tools"), [])
    if isinstance(selected_tools, dict):
        selected_tools = [key for key, value in selected_tools.items() if value]
    elif not isinstance(selected_tools, (list, tuple, set)):
        selected_tools = [str(selected_tools)] if selected_tools else []

    style = bundle.get("style_pack") or {}
    template = bundle.get("scene_template") or {}
    camera = bundle.get("camera_move_pack") or {}
    product_context = bundle.get("product_context") or {}
    cta = bundle.get("cta_pack") or {}
    negative_rules = bundle.get("negative_prompt_rules") or {}
    brand_voice = bundle.get("brand_voice") or {}
    subject = product or character or prompt[:160] or ("chủ thể chính" if language == "vi" else "main subject")
    visual_style = _clean_text(style.get("label_vi") if language == "vi" else style.get("label_en"), 180) or _clean_text(style.get("label_vi"), 180)
    tone = _clean_text(brand_voice.get("scene_guidance") or brand_voice.get("label_vi"), 220)
    lighting = "ánh sáng nhất quán, hướng sáng và độ tương phản không đổi" if language == "vi" else ("一致的光线方向与对比度" if language == "zh" else "consistent lighting direction and contrast")
    palette = "bảng màu thương hiệu nhất quán, không đổi nhiệt độ màu giữa các cảnh" if language == "vi" else ("统一品牌色板，场景之间不改变色温" if language == "zh" else "consistent brand palette and color temperature across scenes")
    camera_style = _clean_text(camera.get("scene_guidance") or camera.get("prompt_template"), 300)
    negative_prompt = ", ".join(filter(None, {
        _clean_text(style.get("negative_prompt"), 260),
        _clean_text(template.get("negative_prompt"), 260),
        _clean_text(negative_rules.get("negative_prompt"), 360),
    }))
    logo_rule = "" if not logo else (
        f"Giữ logo/watermark '{logo}' đúng chính tả, đúng tỷ lệ và vị trí đã chọn; không tự thêm logo khác."
        if language == "vi" else
        (f"保持品牌标志/水印“{logo}”拼写、比例和位置准确，不添加其他标志。" if language == "zh" else f"Keep logo/watermark '{logo}' exact in spelling, proportion, and selected placement; add no other logo.")
    )
    do_not_change = [subject, visual_style, lighting, palette]
    if product:
        do_not_change.append(product)
    if character:
        do_not_change.append(character)
    if logo_rule:
        do_not_change.append(logo_rule)

    if language == "en":
        context_guidance = "Show the product or idea in a credible real-use context with one visible benefit."
        final_cta = "If this is useful to you, view more details or take the next step provided by the brand."
        motions = ["slow push-in", "gentle lateral tracking", "controlled orbit", "steady reveal", "subtle pull-back", "locked hero frame"]
        shots = ["close-up", "medium shot", "detail insert", "wide establishing shot", "over-the-shoulder shot", "hero shot"]
        labels = ("Visual style", "Shot", "Story context", "Context guidance", "Continuity", "Negative prompt")
    elif language == "zh":
        context_guidance = "在可信的真实使用场景中展示产品或主题，并呈现一个可见优势。"
        final_cta = "如果内容适合你，请查看品牌提供的更多信息或下一步。"
        motions = ["缓慢推进", "轻柔横向跟拍", "受控环绕", "稳定揭示", "轻微拉远", "固定主画面"]
        shots = ["特写", "中景", "细节插入", "广角建立镜头", "越肩镜头", "主视觉镜头"]
        labels = ("视觉风格", "镜头", "故事背景", "场景指引", "一致性", "负面提示")
    else:
        context_guidance = _clean_text(product_context.get("scene_guidance"), 360)
        final_cta = _clean_text(cta.get("prompt_template"), 360)
        motions = ["tiến máy chậm", "theo ngang nhẹ", "xoay quanh có kiểm soát", "reveal ổn định", "lùi máy nhẹ", "giữ hero frame"]
        shots = ["cận cảnh", "trung cảnh", "cận chi tiết", "toàn cảnh thiết lập", "qua vai", "hero shot"]
        labels = ("Phong cách hình ảnh", "Góc máy", "Bối cảnh câu chuyện", "Hướng dẫn ngữ cảnh", "Tính nhất quán", "Negative prompt")

    scenes: list[dict[str, Any]] = []
    provider_prompts: list[str] = []
    for index in range(1, scene_count + 1):
        purpose = _scene_purpose(index, scene_count, language)
        visual_line, action_line = _localized_scene_copy(language, index, scene_count, subject, purpose)
        motion = motions[(index - 1) % len(motions)]
        shot = shots[(index - 1) % len(shots)]
        transition = "match cut theo hướng chuyển động" if language == "vi" else ("按运动方向匹配剪辑" if language == "zh" else "match cut on movement direction")
        if index == scene_count:
            transition = "giữ hero frame sạch để kết video" if language == "vi" else ("保持干净主画面结束视频" if language == "zh" else "hold a clean hero frame to end the video")
        caption_hint = _clean_text(final_cta if index == scene_count else brand_voice.get("prompt_template"), 320)
        provider_prompt = " ".join(filter(None, [
            visual_line,
            action_line,
            f"{labels[0]}: {visual_style}.",
            f"{labels[1]}: {shot}; {motion}; {aspect_ratio}; {provider_scene_seconds or estimated_scene_seconds}s.",
            f"{labels[2]}: {prompt}.",
            f"{labels[3]}: {context_guidance}.",
            f"{labels[4]}: {lighting}; {palette}; {logo_rule}",
            f"{labels[5]}: {negative_prompt}.",
        ]))
        provider_prompts.append(provider_prompt)
        scenes.append({
            "scene_index": index,
            "duration_seconds": estimated_scene_seconds,
            "provider_scene_seconds": provider_scene_seconds or None,
            "purpose": purpose,
            "shot_type": shot,
            "camera_motion": motion,
            "visual_prompt": visual_line,
            "action_prompt": action_line,
            "negative_prompt": negative_prompt,
            "transition_to_next": transition,
            "voice_or_caption_hint": caption_hint,
            "provider_prompt": provider_prompt,
        })

    return {
        "project": {
            "language": language,
            "aspect_ratio": aspect_ratio,
            "platform": platform,
            "scene_count": scene_count,
            "selected_scene_count": scene_count,
            "estimated_scene_seconds": estimated_scene_seconds,
            "estimated_total_seconds": scene_count * estimated_scene_seconds,
            "provider_scene_seconds": provider_scene_seconds or None,
            "duration_mode": "scene_based",
            "visual_style": visual_style,
            "tone": tone,
            "package": package,
            "selected_tools": [str(item) for item in selected_tools if str(item).strip()],
            "logo_watermark": logo,
        },
        "consistency_bible": {
            "main_subject": subject,
            "character": character,
            "product": product,
            "location": location or ("bối cảnh phù hợp nội dung" if language == "vi" else ("符合故事的场景" if language == "zh" else "a setting appropriate to the story")),
            "lighting": lighting,
            "color_palette": palette,
            "camera_style": camera_style,
            "do_not_change": do_not_change,
        },
        "scenes": scenes,
        "final_prompt_pack": {
            "provider_prompt_per_scene": provider_prompts,
            "stitching_notes": "Ghép đúng thứ tự cảnh; chuẩn hóa tỷ lệ, độ phân giải và nhịp; không lặp cảnh." if language == "vi" else ("按场景顺序拼接，统一比例、分辨率和节奏，不重复片段。" if language == "zh" else "Stitch in scene order; normalize ratio, resolution, and pacing; do not duplicate clips."),
            "thumbnail_hint": f"Khung hero rõ chủ thể {subject}, ít chữ, tương phản tốt." if language == "vi" else (f"以{subject}为清晰主视觉，少量文字并保持高对比。" if language == "zh" else f"Clear hero frame of {subject}, minimal text, strong contrast."),
            "caption_hint": final_cta,
        },
        "context_selection": context_bundle_debug_summary(bundle),
    }


def _ffprobe_has_audio(path: Path, ffmpeg_path: str) -> bool:
    ffmpeg = Path(ffmpeg_path)
    probe_name = "ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe"
    probe = ffmpeg.with_name(probe_name)
    probe_path = str(probe) if probe.exists() else shutil.which("ffprobe")
    if not probe_path:
        return False
    result = subprocess.run(
        [probe_path, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode == 0 and bool((result.stdout or "").strip())


def stitch_scene_videos(
    scene_files: list[str | os.PathLike[str]],
    output_path: str | os.PathLike[str],
    aspect_ratio: str = "9:16",
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    files = [Path(path).resolve() for path in scene_files]
    if not files or any(not path.is_file() for path in files):
        return {"status": "FAILED", "error": "SCENE_FILE_MISSING", "output_path": ""}
    ffmpeg = str(settings.get("ffmpeg_path") or os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg") or "").strip()
    if not ffmpeg or not Path(ffmpeg).exists():
        return {"status": "STITCHING_UNAVAILABLE", "error": "FFMPEG_NOT_FOUND", "output_path": ""}
    sizes = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
    width, height = sizes.get(str(aspect_ratio or "9:16"), sizes["9:16"])
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    timeout = max(60, int(settings.get("timeout_seconds") or 900))
    preserve_audio = bool(settings.get("preserve_audio", True)) and all(_ffprobe_has_audio(path, ffmpeg) for path in files)
    filter_text = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
    try:
        with tempfile.TemporaryDirectory(prefix="toanaas_multiscene_") as temp_dir:
            temp = Path(temp_dir)
            normalized: list[Path] = []
            for index, source in enumerate(files, start=1):
                target = temp / f"scene_{index:02d}.mp4"
                command = [str(ffmpeg), "-y", "-i", str(source), "-map", "0:v:0"]
                if preserve_audio:
                    command += ["-map", "0:a:0"]
                command += ["-vf", filter_text, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
                if preserve_audio:
                    command += ["-c:a", "aac", "-ar", "48000", "-ac", "2"]
                else:
                    command += ["-an"]
                command += ["-movflags", "+faststart", str(target)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
                if result.returncode != 0 or not target.is_file():
                    return {"status": "FAILED", "error": f"NORMALIZE_SCENE_{index}_FAILED", "output_path": ""}
                normalized.append(target)
            concat_file = temp / "concat.txt"
            concat_file.write_text("".join(f"file '{str(path).replace(chr(92), '/')}'\n" for path in normalized), encoding="utf-8")
            result = subprocess.run(
                [str(ffmpeg), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", "-movflags", "+faststart", str(output)],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
                return {"status": "FAILED", "error": "FFMPEG_CONCAT_FAILED", "output_path": ""}
    except subprocess.TimeoutExpired:
        return {"status": "FAILED", "error": "FFMPEG_TIMEOUT", "output_path": ""}
    except Exception as exc:
        return {"status": "FAILED", "error": f"STITCH_EXCEPTION_{type(exc).__name__}", "output_path": ""}
    return {
        "status": "COMPLETED",
        "output_path": str(output),
        "scene_count": len(files),
        "aspect_ratio": aspect_ratio,
        "audio_preserved": preserve_audio,
    }
