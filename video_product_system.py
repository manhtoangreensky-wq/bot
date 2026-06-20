"""Task 3D video product registry, prompt engine, package policy and prompt vault.

This module is deliberately provider-agnostic.  Free planning calls never submit
jobs or mutate a wallet; paid execution remains behind bot.py's final-confirm
adapter and provider readiness gates.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRODUCT_FIELDS = (
    "product_id",
    "public_label",
    "purpose",
    "user_input_type",
    "output_type",
    "free_or_paid",
    "allowed_packages",
    "provider_required",
    "local_worker_required",
    "default_duration",
    "max_duration",
    "allowed_aspect_ratios",
    "prompt_template_id",
    "next_steps",
    "back_steps",
    "parent_menu_callback",
    "public_guard_message",
    "admin_status_fields",
)


def _product(
    product_id: str,
    label: str,
    purpose: str,
    input_type: str,
    output_type: str,
    boundary: str,
    packages: tuple[str, ...],
    *,
    provider: bool = False,
    worker: bool = False,
    duration: int = 6,
    max_duration: int = 60,
    ratios: tuple[str, ...] = ("9:16", "16:9", "1:1"),
    template: str = "video_general",
    next_steps: tuple[str, ...] = ("generate_prompt", "export_prompt_pack"),
    back_steps: tuple[str, ...] = ("style", "platform", "input", "intro"),
    guard: str = "Tính năng render chưa sẵn sàng. Bạn vẫn có thể xuất prompt pack miễn phí.",
) -> dict[str, Any]:
    return {
        "product_id": product_id,
        "public_label": label,
        "purpose": purpose,
        "user_input_type": input_type,
        "output_type": output_type,
        "free_or_paid": boundary,
        "allowed_packages": list(packages),
        "provider_required": provider,
        "local_worker_required": worker,
        "default_duration": duration,
        "max_duration": max_duration,
        "allowed_aspect_ratios": list(ratios),
        "prompt_template_id": template,
        "next_steps": list(next_steps),
        "back_steps": list(back_steps),
        # All 13 products are launched from the video menu. Internal Back is
        # one step at a time; the product root always returns to its parent.
        "parent_menu_callback": "menu|main_video",
        "public_guard_message": guard,
        "admin_status_fields": ["enabled", "provider_route", "cost_gate", "last_job_id", "last_error_safe"],
    }


VIDEO_PRODUCT_REGISTRY: dict[str, dict[str, Any]] = {
    "video_trend": _product(
        "video_trend", "🔥 Video theo trend",
        "Tạo trend angle, hook, kịch bản, caption và storyboard prompt từ chủ đề.",
        "topic|product|niche", "plan|script|prompt_pack", "free_planning", (),
        template="tiktok_hook", next_steps=("generate_plan", "export_prompt_pack", "render_video"),
    ),
    "video_idea": _product(
        "video_idea", "🧠 Ý tưởng video",
        "Tạo 5–10 ý tưởng, hook và format theo chủ đề, sản phẩm và nền tảng.",
        "topic|product|platform", "idea_pack", "free_planning", (),
        template="youtube_short_script", next_steps=("generate_ideas", "export_prompt_pack", "render_video"),
    ),
    "storyboard_prompt": _product(
        "storyboard_prompt", "🎞 Storyboard + Prompt",
        "Tạo storyboard 6/9/12/16 panel, prompt ảnh/video từng shot và batch multishot 2 shot.",
        "topic|story|product|reference", "storyboard_table|image_prompts|video_prompts|prompt_pack", "free_planning_paid_render",
        ("package_200", "package_300", "package_400"), template="seedance_multishot", max_duration=96,
        next_steps=("image_prompts", "video_prompts", "render_one_shot", "export_prompt_pack"),
    ),
    "script_image_video": _product(
        "script_image_video", "🧩 Kịch bản → Ảnh → Video",
        "Tạo kịch bản, shot list, prompt ảnh rồi prompt chuyển động/video từng cảnh.",
        "topic|script|product", "script|shot_list|image_prompts|video_prompts", "free_planning_paid_render",
        ("package_200", "package_300", "package_400"), template="product_ad", max_duration=60,
        next_steps=("export_prompt_pack", "create_scene_image", "render_scene", "assemble_multiscene"),
    ),
    "video_ai_real": _product(
        "video_ai_real", "🎬 Video AI chân thật",
        "Biến prompt hoặc ảnh tham chiếu thành một video AI ngắn, chân thật.",
        "text_prompt|optional_reference_image", "rendered_video", "paid_after_final_confirm",
        ("package_200", "package_300", "package_400"), provider=True, template="realistic_video", max_duration=12,
        next_steps=("improve_prompt", "choose_package", "final_confirm", "provider_job"),
    ),
    "image_to_video": _product(
        "image_to_video", "🖼 Ảnh → Video",
        "Tạo motion prompt miễn phí hoặc render video từ 1–4 ảnh.",
        "1_to_4_images|scene_description", "motion_prompt|rendered_video", "free_prompt_paid_render",
        ("package_200", "package_300", "package_400"), provider=True, template="image_to_video_motion", max_duration=12,
        next_steps=("motion_prompt", "choose_package", "final_confirm", "provider_job"),
    ),
    "frame_video_local": _product(
        "frame_video_local", "🎞 Ghép ảnh thành video",
        "Ghép ảnh thành MP4 bằng Local Worker/FFmpeg, không gọi AI video provider.",
        "images", "local_mp4", "local_render_policy", (), worker=True, template="local_slideshow", max_duration=120,
        next_steps=("collect_images", "choose_local_settings", "local_confirm", "local_job"),
    ),
    "self_shot_scene_change": _product(
        "self_shot_scene_change", "🎥 Tự quay & đổi cảnh AI",
        "Giữ chủ thể/hướng chuyển động từ video hoặc ảnh nguồn rồi đổi bối cảnh, ánh sáng và phong cách.",
        "user_video|user_image", "video_to_video_plan|edited_video", "free_plan_paid_guarded_render",
        ("package_300", "package_400"), provider=True, template="transformation_video", max_duration=12,
        next_steps=("collect_source", "preserve_subject", "scene_plan", "choose_package"),
    ),
    "multi_scene_film": _product(
        "multi_scene_film", "🎬 Phim AI nhiều cảnh",
        "Lập kế hoạch phim/quảng cáo nhiều cảnh và render theo từng scene khi gói phù hợp.",
        "story|product|script", "scene_plan|prompt_pack|optional_scene_renders", "free_planning_paid_higher_tier_render",
        ("package_300", "package_400"), provider=True, template="cinematic_story", max_duration=120,
        next_steps=("scene_plan", "export_prompt_pack", "render_scene_batches"),
        guard="Gói 200 chỉ render một shot ngắn, không render phim nhiều cảnh.",
    ),
    "motion_prompt": _product(
        "motion_prompt", "🎥 Prompt / Chuyển động",
        "Tạo prompt camera, chuyển động chủ thể và chuyển cảnh chuyên nghiệp.",
        "image|scene_description", "camera_motion_prompt", "free_planning", (), template="image_to_video_motion",
        next_steps=("generate_motion_prompt", "export_prompt_pack", "render_video"),
    ),
    "video_reference": _product(
        "video_reference", "📥 Video mẫu / Kênh mẫu",
        "Phân tích nhịp, bố cục và ngôn ngữ hình ảnh để tạo style brief mới, không sao chép nội dung có bản quyền.",
        "video|link|manual_style", "style_brief|reusable_prompt_style", "free_guarded_analysis", (), template="reference_style",
        next_steps=("save_reference", "style_brief", "create_original_prompt"),
    ),
    "audio_addons": _product(
        "audio_addons", "🎵 Nhạc / Voice / SFX",
        "Chọn audio plan cho phiên video hiện tại và chuyển sang trạng thái sẵn sàng của Task 1.",
        "existing_video_session", "audio_plan", "free_default_optional_paid", ("package_300", "package_400"), template="audio_plan",
        next_steps=("task1_readiness", "select_default_audio", "return_video_session"),
    ),
    "video_local_edit": _product(
        "video_local_edit", "🛠 Chỉnh sửa video local",
        "Trim, crop, resize, compress hoặc merge video bằng Local Worker/FFmpeg.",
        "video", "local_mp4", "local_render_policy", (), worker=True, template="local_edit", max_duration=600,
        next_steps=("collect_video", "choose_edit", "local_confirm", "local_job"),
    ),
}


VIDEO_MENU_ROWS: tuple[tuple[str, ...], ...] = (
    ("video_trend", "video_idea"),
    ("storyboard_prompt", "motion_prompt"),
    ("video_ai_real", "script_image_video"),
    ("image_to_video", "frame_video_local"),
    ("self_shot_scene_change", "multi_scene_film"),
    ("video_reference", "audio_addons"),
    ("video_local_edit", "main_menu"),
)


VIDEO_PACKAGE_REGISTRY: dict[str, dict[str, Any]] = {
    "package_200": {
        "package_id": "package_200", "price_xu": 200, "duration_seconds": 6,
        "max_scenes": 1, "max_shots": 1, "aspect_ratios": ["9:16", "16:9", "1:1"],
        "provider_quality": "basic_short_default", "allowed_products": ["video_ai_real", "image_to_video", "storyboard_prompt", "script_image_video"],
        "allowed_addons": ["none", "default_no_audio", "stock_music_free"], "preview_policy": "not_required",
        "public_enabled": True, "cost_gate": "intentional_starter_boundary",
    },
    "package_300": {
        "package_id": "package_300", "price_xu": 300, "duration_seconds": 8,
        "max_scenes": 2, "max_shots": 2, "aspect_ratios": ["9:16", "16:9", "1:1"],
        "provider_quality": "standard_short", "allowed_products": ["video_ai_real", "image_to_video", "storyboard_prompt", "script_image_video", "self_shot_scene_change", "multi_scene_film"],
        "allowed_addons": ["none", "default_no_audio", "stock_music_free", "subtitle_from_script"], "preview_policy": "optional",
        "public_enabled": True, "cost_gate": "provider_cost_must_be_known_safe",
    },
    "package_400": {
        "package_id": "package_400", "price_xu": 400, "duration_seconds": 12,
        "max_scenes": 4, "max_shots": 4, "aspect_ratios": ["9:16", "16:9", "1:1"],
        "provider_quality": "enhanced_short", "allowed_products": ["video_ai_real", "image_to_video", "storyboard_prompt", "script_image_video", "self_shot_scene_change", "multi_scene_film"],
        "allowed_addons": ["none", "default_no_audio", "stock_music_free", "subtitle_from_script", "default_voice_if_cost_safe"], "preview_policy": "optional",
        "public_enabled": True, "cost_gate": "provider_cost_must_be_known_safe",
    },
    "package_600_off": {
        "package_id": "package_600_off", "price_xu": 600, "duration_seconds": 0, "max_scenes": 0, "max_shots": 0,
        "aspect_ratios": [], "provider_quality": "off", "allowed_products": [], "allowed_addons": [],
        "preview_policy": "off", "public_enabled": False, "cost_gate": "hidden_until_task3e",
    },
    "package_premium_off": {
        "package_id": "package_premium_off", "price_xu": 0, "duration_seconds": 0, "max_scenes": 0, "max_shots": 0,
        "aspect_ratios": [], "provider_quality": "off", "allowed_products": [], "allowed_addons": [],
        "preview_policy": "off", "public_enabled": False, "cost_gate": "unknown_provider_cost",
    },
}


LEGACY_TIER_TO_PACKAGE = {"low": "package_200", "basic": "package_300", "common": "package_400"}


def package_for_tier(tier: str) -> dict[str, Any]:
    package_id = LEGACY_TIER_TO_PACKAGE.get(str(tier or "").strip().lower(), str(tier or ""))
    return dict(VIDEO_PACKAGE_REGISTRY.get(package_id) or {})


def validate_package_selection(product_id: str, package_id: str, selected_addons: list[str] | None = None) -> dict[str, Any]:
    product = VIDEO_PRODUCT_REGISTRY.get(str(product_id or ""))
    package = VIDEO_PACKAGE_REGISTRY.get(str(package_id or ""))
    if not product or not package:
        return {"ok": False, "reason": "unknown_product_or_package"}
    if not package.get("public_enabled"):
        return {"ok": False, "reason": "package_hidden"}
    if package_id not in product.get("allowed_packages", []):
        return {"ok": False, "reason": "package_not_allowed_for_product"}
    addons = [str(item or "none") for item in (selected_addons or ["none"])]
    blocked = [item for item in addons if item not in set(package.get("allowed_addons") or [])]
    if blocked:
        return {"ok": False, "reason": "paid_addon_not_allowed", "blocked_addons": blocked}
    return {"ok": True, "reason": "ready", "product": product, "package": package}


@dataclass
class VideoPromptRequest:
    product_id: str
    user_topic: str
    platform: str = "TikTok/Reels"
    aspect_ratio: str = "9:16"
    duration: int = 6
    package_id: str = ""
    target_audience: str = "general audience"
    objective: str = "engagement"
    style: str = "realistic cinematic"
    tone: str = "clear and natural"
    language: str = "vi"
    character_description: str = ""
    product_description: str = ""
    scene_count: int = 6
    shot_count: int = 6
    reference_style: str = ""
    source_media_ref: str = ""
    user_constraints: list[str] = field(default_factory=list)
    provider_target: str = "generic_video_provider"
    safety_flags: list[str] = field(default_factory=list)


@dataclass
class VideoPromptBundle:
    title: str
    short_summary: str
    hook: str
    script: str
    scene_table: list[dict[str, Any]]
    shot_table: list[dict[str, Any]]
    storyboard_panels: list[dict[str, Any]]
    image_prompts: list[str]
    video_prompts: list[str]
    motion_prompts: list[str]
    negative_prompt: str
    audio_suggestion: str
    subtitle_suggestion: str
    provider_payload: dict[str, Any]
    quality_checklist: dict[str, bool]
    render_plan: dict[str, Any]
    package_fit: dict[str, Any]
    warnings: list[str]
    bundle_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


NEGATIVE_PROMPT = (
    "no watermark, no random logo, no unreadable text, no duplicate subject, no identity drift, "
    "no warped hands or face, no flicker, no jumpy camera, no object morphing, no copyrighted character, "
    "no living-artist imitation"
)


class VideoPromptEngine:
    """Deterministic provider-ready prompt compiler; it never calls a provider."""

    @staticmethod
    def _shot_count(request: VideoPromptRequest) -> int:
        if request.product_id in {"video_ai_real", "image_to_video", "motion_prompt"}:
            return 1
        requested = int(request.shot_count or request.scene_count or 6)
        return max(1, min(16, requested))

    def build(self, request: VideoPromptRequest | dict[str, Any]) -> VideoPromptBundle:
        if isinstance(request, dict):
            request = VideoPromptRequest(**request)
        if request.product_id not in VIDEO_PRODUCT_REGISTRY:
            raise ValueError("unknown video product")
        topic = re.sub(r"\s+", " ", str(request.user_topic or "").strip())[:600]
        if not topic:
            raise ValueError("user_topic is required")
        count = self._shot_count(request)
        duration_total = max(count, int(request.duration or 6))
        per_shot = max(2, min(8, round(duration_total / count)))
        phases = (
            ("Hook", "establish the subject immediately", "close-up", "slow push-in", "hard cut"),
            ("Context", "show the real setting and audience problem", "wide establishing shot", "controlled pan", "cut on action"),
            ("Reveal", "reveal the product or main character clearly", "medium hero shot", "smooth dolly-in", "match cut"),
            ("Action", "demonstrate one concrete action or benefit", "over-the-shoulder", "short tracking move", "motivated cut"),
            ("Proof", "show a credible result and reaction", "medium close-up", "subtle orbit", "match cut"),
            ("Close", "finish on a clean memorable hero frame", "hero composition", "gentle pull-out", "hold"),
        )
        shots: list[dict[str, Any]] = []
        for index in range(1, count + 1):
            phase, purpose, angle, movement, transition = phases[(index - 1) % len(phases)]
            continuity = (
                f"Keep the same subject identity, proportions, wardrobe/product geometry, color palette and screen direction "
                f"from shot {max(1, index - 1)} to shot {index}."
            )
            environment = f"authentic setting relevant to {topic}, uncluttered production design"
            lighting = "soft motivated key light, realistic shadows, stable color temperature"
            image_prompt = (
                f"Storyboard keyframe {index}/{count}: {topic}. {phase}: {purpose}. Subject is clearly visible, "
                f"{environment}; {angle}; 35mm cinematic lens; {lighting}; {request.style}; {request.aspect_ratio}; "
                f"balanced foreground, midground and background. {continuity} {NEGATIVE_PROMPT}."
            )
            video_prompt = (
                f"Shot {index}/{count}, {per_shot} seconds, {request.aspect_ratio}, {request.style}. Subject: {topic}. "
                f"Action: {purpose}. Environment: {environment}. Camera: {angle}, {movement}, 35mm lens, stable horizon. "
                f"Lighting: {lighting}. Mood: {request.tone}. Composition: clear focal subject with natural depth. "
                f"Motion must be physically plausible and continuous; transition: {transition}. {continuity} "
                f"Do not imitate copyrighted characters or living artists. {NEGATIVE_PROMPT}."
            )
            shots.append({
                "shot_number": index,
                "scene_purpose": purpose,
                "subject": topic,
                "action": purpose,
                "environment": environment,
                "camera_angle": angle,
                "camera_movement": movement,
                "lens": "35mm cinematic lens",
                "lighting": lighting,
                "mood": request.tone,
                "composition": "clear focal subject, balanced foreground/midground/background",
                "continuity_notes": continuity,
                "duration_seconds": per_shot,
                "transition": transition,
                "audio_sfx": "subtle room tone and one motivated transition SFX",
                "on_screen_text": "none by default; add only user-approved copy in post",
                "image_prompt": image_prompt,
                "video_prompt": video_prompt,
                "negative_prompt": NEGATIVE_PROMPT,
            })
        batches = [
            {"batch_number": i // 2 + 1, "shot_numbers": [shot["shot_number"] for shot in shots[i:i + 2]]}
            for i in range(0, len(shots), 2)
        ]
        script_lines = [f"{shot['shot_number']}. {shot['scene_purpose'].capitalize()}: {shot['action']}." for shot in shots]
        package_fit = self._package_fit(request, len(shots))
        bundle = VideoPromptBundle(
            title=f"{VIDEO_PRODUCT_REGISTRY[request.product_id]['public_label']} — {topic[:80]}",
            short_summary=f"Kế hoạch {len(shots)} shot cho {request.platform}, tỉ lệ {request.aspect_ratio}, phong cách {request.style}.",
            hook=f"Mở ngay bằng một chi tiết rõ nhất của {topic} trong 2 giây đầu.",
            script="\n".join(script_lines),
            scene_table=[{"scene_number": shot["shot_number"], "purpose": shot["scene_purpose"], "duration_seconds": shot["duration_seconds"], "transition": shot["transition"]} for shot in shots],
            shot_table=shots,
            storyboard_panels=[{"panel": shot["shot_number"], "caption_vi": shot["scene_purpose"], "image_prompt_en": shot["image_prompt"]} for shot in shots],
            image_prompts=[shot["image_prompt"] for shot in shots],
            video_prompts=[shot["video_prompt"] for shot in shots],
            motion_prompts=[f"Shot {shot['shot_number']}: {shot['camera_movement']}; {shot['transition']}; {shot['duration_seconds']}s." for shot in shots],
            negative_prompt=NEGATIVE_PROMPT,
            audio_suggestion="Default: no generated music. Optional low-volume licensed stock bed with scene-motivated SFX.",
            subtitle_suggestion="Create subtitles from the approved script in post; keep safe margins for the selected platform.",
            provider_payload={
                "model": "<configured-provider-model>",
                "prompt": shots[0]["video_prompt"] if shots else "",
                "aspect_ratio": request.aspect_ratio,
                "duration_seconds": per_shot,
                "source_media_ref": request.source_media_ref,
                "provider_target": request.provider_target,
            },
            quality_checklist={},
            render_plan={
                "mode": "single_shot" if len(shots) == 1 else "multishot_batches",
                "batches": batches,
                "provider_call_required": False,
                "requires_final_confirmation_for_render": True,
                "free_planning_only": True,
            },
            package_fit=package_fit,
            warnings=[
                "Prompt pack is free and does not submit a provider job.",
                "Only render after package selection and final confirmation.",
                "Use references for general style traits only; do not duplicate copyrighted footage or characters.",
            ],
        )
        validation = validate_video_prompt_bundle(bundle)
        bundle.quality_checklist = validation["checks"]
        if not validation["valid"]:
            bundle.warnings.extend(validation["missing"])
        return bundle

    @staticmethod
    def _package_fit(request: VideoPromptRequest, shot_count: int) -> dict[str, Any]:
        if not request.package_id:
            return {"selected": "", "fits": True, "reason": "planning_only_no_package_selected"}
        package = VIDEO_PACKAGE_REGISTRY.get(request.package_id)
        if not package:
            return {"selected": request.package_id, "fits": False, "reason": "unknown_package"}
        allowed = request.product_id in set(package.get("allowed_products") or [])
        fits_shots = shot_count <= int(package.get("max_shots") or 0)
        return {
            "selected": request.package_id,
            "fits": bool(package.get("public_enabled") and allowed and fits_shots),
            "reason": "ready" if package.get("public_enabled") and allowed and fits_shots else "product_or_shot_limit",
            "max_shots": int(package.get("max_shots") or 0),
        }


def validate_video_prompt_bundle(bundle: VideoPromptBundle | dict[str, Any]) -> dict[str, Any]:
    data = bundle.to_dict() if isinstance(bundle, VideoPromptBundle) else dict(bundle or {})
    shots = list(data.get("shot_table") or [])
    required = (
        "subject", "action", "environment", "camera_movement", "lighting", "mood",
        "duration_seconds", "continuity_notes", "video_prompt", "negative_prompt",
    )
    missing: list[str] = []
    for index, shot in enumerate(shots, start=1):
        for key in required:
            if not shot.get(key):
                missing.append(f"shot_{index}.{key}")
    joined_prompts = " ".join(str(shot.get("video_prompt") or "") for shot in shots).lower()
    checks = {
        "has_subject": bool(shots and all(shot.get("subject") for shot in shots)),
        "has_action": bool(shots and all(shot.get("action") for shot in shots)),
        "has_setting": bool(shots and all(shot.get("environment") for shot in shots)),
        "has_camera_movement": bool(shots and all(shot.get("camera_movement") for shot in shots)),
        "has_lighting": bool(shots and all(shot.get("lighting") for shot in shots)),
        "has_style": any(token in joined_prompts for token in ("style", "cinematic", "realistic", "ugc", "anime", "cartoon")),
        "has_duration": bool(shots and all(int(shot.get("duration_seconds") or 0) > 0 for shot in shots)),
        "has_aspect_ratio": any(ratio in joined_prompts for ratio in ("9:16", "16:9", "1:1", "4:5")),
        "has_negative_prompt": bool(shots and all(shot.get("negative_prompt") for shot in shots)),
        "has_continuity": bool(shots and all(shot.get("continuity_notes") for shot in shots)),
        "no_unsupported_parameters": not any(token in joined_prompts for token in ("--ar ", "--stylize", "cfg_scale=")),
        "rights_safe": "living-artist imitation" in joined_prompts and "copyrighted character" in joined_prompts,
    }
    if not shots:
        missing.append("shot_table")
    missing.extend(key for key, ok in checks.items() if not ok)
    return {"valid": not missing, "missing": list(dict.fromkeys(missing)), "checks": checks}


def bundle_to_markdown(bundle: VideoPromptBundle | dict[str, Any]) -> str:
    data = bundle.to_dict() if isinstance(bundle, VideoPromptBundle) else dict(bundle or {})
    lines = [f"# {data.get('title') or 'TOAN AAS Video Prompt Pack'}", "", str(data.get("short_summary") or ""), "", "## Storyboard"]
    for shot in data.get("shot_table") or []:
        lines.extend([
            "",
            f"### Shot {shot.get('shot_number')}",
            f"- Purpose: {shot.get('scene_purpose')}",
            f"- Duration: {shot.get('duration_seconds')}s",
            f"- Camera: {shot.get('camera_angle')} / {shot.get('camera_movement')} / {shot.get('lens')}",
            f"- Continuity: {shot.get('continuity_notes')}",
            f"- Image prompt: {shot.get('image_prompt')}",
            f"- Video prompt: {shot.get('video_prompt')}",
            f"- Negative prompt: {shot.get('negative_prompt')}",
        ])
    lines.extend(["", "## Render batches", "", json.dumps((data.get("render_plan") or {}).get("batches") or [], ensure_ascii=False, indent=2)])
    return "\n".join(lines).strip() + "\n"


class PromptVault:
    REQUIRED_FIELDS = (
        "prompt_id", "category", "product_id", "platform", "style", "language", "prompt_text",
        "negative_prompt", "variables", "source", "license_note", "quality_score", "enabled",
    )

    def __init__(self, seed_path: str | Path):
        self.seed_path = Path(seed_path)

    def _load(self) -> dict[str, Any]:
        if not self.seed_path.exists():
            return {"schema_version": "task3d-v1", "prompts": []}
        data = json.loads(self.seed_path.read_text(encoding="utf-8"))
        prompts = data.get("prompts") if isinstance(data, dict) else []
        return {"schema_version": data.get("schema_version", "task3d-v1"), "prompts": list(prompts or [])}

    def status(self) -> dict[str, Any]:
        data = self._load()
        prompts = data["prompts"]
        invalid = [item.get("prompt_id", "<missing>") for item in prompts if any(field not in item for field in self.REQUIRED_FIELDS)]
        return {
            "path": str(self.seed_path), "exists": self.seed_path.exists(), "count": len(prompts),
            "enabled_count": sum(1 for item in prompts if item.get("enabled")), "invalid": invalid,
            "schema_version": data["schema_version"],
        }

    def search(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        needle = str(keyword or "").strip().lower()
        if not needle:
            return []
        matches = []
        for item in self._load()["prompts"]:
            if not item.get("enabled"):
                continue
            haystack = " ".join(str(item.get(key) or "") for key in ("prompt_id", "category", "product_id", "platform", "style", "prompt_text")).lower()
            if needle in haystack:
                matches.append(dict(item))
        return sorted(matches, key=lambda row: float(row.get("quality_score") or 0), reverse=True)[:max(1, min(50, int(limit or 10)))]

    def add(self, item: dict[str, Any]) -> dict[str, Any]:
        missing = [field for field in self.REQUIRED_FIELDS if field not in item]
        if missing:
            return {"ok": False, "reason": "missing_fields", "missing": missing}
        data = self._load()
        prompt_id = str(item.get("prompt_id") or "").strip()
        if any(str(existing.get("prompt_id") or "") == prompt_id for existing in data["prompts"]):
            return {"ok": False, "reason": "duplicate_prompt_id"}
        data["prompts"].append(dict(item))
        try:
            self.seed_path.parent.mkdir(parents=True, exist_ok=True)
            self.seed_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            return {"ok": False, "reason": "vault_storage_read_only"}
        return {"ok": True, "prompt_id": prompt_id}

    def export(self) -> str:
        return json.dumps(self._load(), ensure_ascii=False, indent=2) + "\n"

    def refresh(self) -> dict[str, Any]:
        # Local refresh only. Remote imports require an explicit URL/license and are
        # intentionally not scraped or fetched by this runtime command.
        return {"ok": True, "source": "local_seed", **self.status(), "refreshed_at": datetime.now(timezone.utc).isoformat()}


def provider_curl_examples(status: dict[str, Any]) -> str:
    provider = str(status.get("selected_provider") or "missing")
    submit = str(status.get("final_submit_url") or "")
    fetch = str(status.get("final_fetch_url") or "")
    if not submit:
        return f"# {provider}: missing endpoint"
    lines = [
        f"# {provider} submit (token masked)",
        f"curl -X POST '{submit}' -H 'Authorization: Bearer ***MASKED***' -H 'Content-Type: application/json' --data '{{\"model\":\"<configured-model>\",\"prompt\":\"<provider-ready prompt>\",\"aspect_ratio\":\"9:16\"}}'",
    ]
    if fetch:
        lines.extend(["", f"# {provider} fetch", f"curl -X GET '{fetch}' -H 'Authorization: Bearer ***MASKED***'"])
    else:
        lines.extend(["", "# missing fetch/status endpoint"])
    return "\n".join(lines)


def registry_audit() -> dict[str, Any]:
    missing = {product_id: [field for field in PRODUCT_FIELDS if field not in product] for product_id, product in VIDEO_PRODUCT_REGISTRY.items()}
    missing = {key: value for key, value in missing.items() if value}
    menu_ids = [item for row in VIDEO_MENU_ROWS for item in row if item != "main_menu"]
    return {
        "valid": (
            not missing
            and set(menu_ids) == set(VIDEO_PRODUCT_REGISTRY)
            and all(item.get("parent_menu_callback") == "menu|main_video" for item in VIDEO_PRODUCT_REGISTRY.values())
        ),
        "missing_fields": missing,
        "missing_menu_products": sorted(set(VIDEO_PRODUCT_REGISTRY) - set(menu_ids)),
        "unknown_menu_products": sorted(set(menu_ids) - set(VIDEO_PRODUCT_REGISTRY)),
        "wrong_parent_routes": sorted(
            product_id
            for product_id, item in VIDEO_PRODUCT_REGISTRY.items()
            if item.get("parent_menu_callback") != "menu|main_video"
        ),
        "product_count": len(VIDEO_PRODUCT_REGISTRY),
    }
