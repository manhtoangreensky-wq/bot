import re
from dataclasses import asdict, dataclass, field


@dataclass
class VideoIntentSpec:
    source_type: str = "prompt"
    task_type: str = "prompt_to_video"
    user_goal: str = ""
    target_subject: str = ""
    product_or_topic: str = ""
    audience: str = ""
    platform: str = "custom"
    ratio: str = "9:16"
    duration: str = ""
    style: str = ""
    scene_count: int = 0
    camera_motion: str = ""
    subject_motion: str = ""
    transition: str = ""
    background: str = ""
    lighting: str = ""
    color_palette: str = ""
    music_voice: str = ""
    caption_cta: str = ""
    must_keep: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    quality_tier: str = ""
    provider_target: str = ""
    needs_clarification: bool = False


FLOW_MAP = {
    "promptvideo": ("prompt", "prompt_to_video"),
    "prompt_to_video": ("prompt", "prompt_to_video"),
    "imagevideo": ("image", "image_to_video"),
    "image_to_video": ("image", "image_to_video"),
    "videoref": ("video_reference", "video_reference_to_video"),
    "reference_video_plan": ("video_reference", "video_reference_to_video"),
    "trend": ("trend", "trend_video"),
    "trendvideo": ("trend", "trend_video"),
    "storyboard": ("storyboard", "storyboard_video"),
    "framevideo": ("storyboard", "frame_video"),
    "selfscene": ("self_record", "change_scene"),
    "longvideo": ("script", "long_script"),
    "videoidea": ("script", "ad_concept"),
}

CAMERA_MOTION_RULES = (
    (("zoom nhẹ", "zoom nhe", "camera zoom nhẹ", "slow push-in", "pushin", "push-in"), "slow push-in"),
    (("zoom ra", "pull out", "pull-out"), "slow pull-out"),
    (("pan trái", "lia trái", "pan left"), "smooth pan left"),
    (("pan phải", "lia phải", "pan right"), "smooth pan right"),
    (("orbit", "quay quanh", "xoay quanh"), "gentle orbit shot around the subject"),
    (("handheld", "rung nhẹ", "cầm tay"), "subtle natural handheld motion"),
    (("từ trên xuống", "top-down", "top down"), "top-down to front transition"),
    (("cận cảnh", "close-up", "close up", "macro"), "close-up detail shot"),
    (("toàn cảnh", "wide shot", "wide establishing"), "wide establishing shot"),
    (("dolly in", "dolly-in", "dolly"), "smooth dolly-in"),
    (("parallax",), "subtle parallax motion"),
)

SUBJECT_MOTION_RULES = (
    (("sản phẩm xoay", "xoay sản phẩm", "product rotates", "rotation 360", "xoay 360"), "product rotates slowly with stable geometry"),
    (("quay đầu", "turns head", "turn head"), "subject gently turns their head"),
    (("đi bộ", "bước đi", "walks", "walking"), "subject walks naturally"),
    (("cười nhẹ", "smiles gently", "gentle smile"), "subject smiles gently"),
    (("nâng sản phẩm", "holds up", "lift product"), "subject naturally lifts and presents the product"),
    (("mở hộp", "unbox", "unboxing"), "hands naturally unbox the product"),
    (("rót nước", "pour water", "pouring"), "liquid is poured naturally with realistic physics"),
    (("chạm màn hình", "tap screen", "touch screen"), "subject naturally taps the screen"),
    (("ánh sáng chạy qua", "light sweep"), "a soft controlled light sweep passes over the subject"),
    (("logo nổi lên", "logo reveal"), "a clean restrained logo reveal animation"),
    (("chuyển động nhẹ", "motion nhẹ", "subtle motion", "làm mượt hơn"), "subtle natural motion with no excessive deformation"),
)

TRANSITION_RULES = (
    (("chuyển cảnh mượt", "smooth transition"), "smooth cinematic transition"),
    (("match cut",), "match cut transition"),
    (("before/after", "before after", "trước/sau"), "before-after split or wipe transition"),
    (("flash transition", "chuyển flash"), "quick flash transition"),
    (("theo nhạc", "cut on beat", "theo beat"), "cut on beat"),
)

KEEP_RULES = (
    (("giữ logo", "keep logo"), "logo and legitimate brand identity"),
    (("giữ mặt", "keep face", "giữ người", "keep person"), "original face and person identity"),
    (("giữ sản phẩm", "keep product"), "product identity, shape and packaging"),
    (("không đổi màu", "keep color", "giữ màu"), "original color palette"),
    (("không đổi bối cảnh", "keep background"), "original background"),
    (("giữ đúng bố cục", "keep composition"), "original composition"),
    (("giữ đúng thương hiệu", "keep brand"), "brand identity and product details"),
)

AVOID_RULES = (
    (("không méo chữ", "no broken text"), "misspelled or distorted text"),
    (("không méo mặt", "no distorted face"), "distorted face or identity change"),
    (("không thêm người", "no extra people"), "extra people"),
    (("không thêm chữ", "no text", "không chữ"), "random or readable generated text"),
    (("không đổi bối cảnh",), "unrequested background changes"),
    (("không đổi màu",), "unrequested color changes"),
)

TIER_QUALITY = {
    "low": "simple short video, basic motion, fast test",
    "basic": "clear subject, simple camera motion, stable composition",
    "common": "smooth camera motion, better visual detail, commercial-ready result",
    "standard": "cinematic motion, controlled lighting, stronger realism, clean transitions",
    "high": "premium cinematic quality, realistic motion, high detail, polished commercial look, stable identity",
    "premium": "admin-reviewed prompt, provider selection and manual quality review when available",
}

DEFAULT_NEGATIVE = (
    "distorted face, identity change, warped product, broken logo, misspelled text, random text, no text, no caption, "
    "extra limbs, extra people, unstable geometry, flicker, morphing, no watermark, unrelated objects"
)

VAGUE_REQUESTS = {
    "làm video đẹp", "tao video dep", "tạo video đẹp", "làm video bán hàng", "tạo video bán hàng",
    "video sản phẩm", "video ai", "làm clip quảng cáo", "beautiful video", "sales video", "product video",
}

SENSITIVE_IDENTITY_TERMS = (
    "mặt", "face", "người thật", "person", "logo", "thương hiệu", "brand", "bao bì", "packaging",
    "sản phẩm", "product", "chữ", "text", "slogan", "tên thương hiệu",
)


def _clean(value, limit: int = 1800) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _unique(items) -> list[str]:
    seen = set()
    output = []
    for item in items:
        clean = _clean(item, 240)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            output.append(clean)
    return output


def _matches(text: str, rules) -> list[str]:
    lowered = f" {_clean(text).lower()} "
    return _unique(output for keywords, output in rules if any(keyword in lowered for keyword in keywords))


def normalize_video_motion(user_motion_text: str) -> dict:
    text = _clean(user_motion_text)
    camera = _matches(text, CAMERA_MOTION_RULES)
    subject = _matches(text, SUBJECT_MOTION_RULES)
    transitions = _matches(text, TRANSITION_RULES)
    return {
        "camera_motion": "; ".join(camera) or "stable camera with subtle natural movement",
        "subject_motion": "; ".join(subject) or "natural restrained subject motion",
        "transition": "; ".join(transitions) or "clean smooth transition",
        "complex_motion": len(camera) + len(subject) + len(transitions) > 3,
    }


def video_request_is_vague(user_text: str) -> bool:
    text = _clean(user_text).lower().strip(" .,!?:;")
    if text in VAGUE_REQUESTS:
        return True
    words = [part for part in re.split(r"\W+", text, flags=re.UNICODE) if len(part) > 1]
    return len(words) < 4


def _platform_ratio(text: str, previous: dict) -> tuple[str, str]:
    lowered = _clean(text).lower()
    explicit_ratio = re.search(r"(?<!\d)(9:16|16:9|1:1|4:5)(?!\d)", lowered)
    if explicit_ratio:
        ratio = explicit_ratio.group(1)
    else:
        ratio = _clean(previous.get("ratio") or previous.get("aspect_ratio"), 20)
    if any(item in lowered for item in ("tiktok", "reels", "shorts")):
        return ("tiktok" if "tiktok" in lowered else ("reels" if "reels" in lowered else "shorts"), ratio or "9:16")
    if "youtube" in lowered or "video ngang" in lowered or "banner" in lowered:
        return "youtube", ratio or "16:9"
    if "facebook" in lowered or "instagram" in lowered or "feed" in lowered:
        return "facebook", ratio or "4:5"
    return _clean(previous.get("platform"), 40) or "custom", ratio or "9:16"


def _goal_style(text: str, previous: dict) -> tuple[str, str]:
    lowered = _clean(text).lower()
    if any(item in lowered for item in ("hướng dẫn", "tutorial", "how to", "mẹo")):
        goal = "tutorial"
    elif any(item in lowered for item in ("trend", "viral", "tiktok")):
        goal = "social trend"
    elif any(item in lowered for item in ("cinematic", "điện ảnh", "cảm xúc", "brand film")):
        goal = "cinematic brand story"
    elif any(item in lowered for item in ("quảng cáo", "bán hàng", "ad", "product")):
        goal = "commercial advertising"
    else:
        goal = _clean(previous.get("user_goal") or previous.get("goal") or previous.get("prompt_kind"), 120) or "clear short-form communication"
    if any(item in lowered for item in ("luxury", "sang trọng", "cao cấp")):
        style = "luxury commercial"
    elif any(item in lowered for item in ("ugc", "đời thường", "handheld")):
        style = "natural UGC"
    elif any(item in lowered for item in ("cinematic", "điện ảnh")):
        style = "cinematic"
    elif any(item in lowered for item in ("viral", "tiktok")):
        style = "fast social video"
    else:
        style = _clean(previous.get("style") or previous.get("selected_style"), 180) or "professional and visually coherent"
    return goal, style


def _subject_type(text: str) -> str:
    lowered = _clean(text).lower()
    rules = (
        ("person", ("người", "nhân vật", "face", "person", "model", "người mẫu")),
        ("software or app", ("app", "phần mềm", "software", "màn hình")),
        ("physical product", ("sản phẩm", "product", "chai", "hộp", "máy", "nước hoa")),
        ("logo", ("logo", "brand mark")),
        ("food or drink", ("món ăn", "đồ ăn", "food", "cà phê", "coffee", "nước")),
        ("real estate", ("bất động sản", "căn hộ", "nhà", "interior", "real estate")),
        ("fashion", ("thời trang", "fashion", "quần áo", "outfit")),
    )
    for label, keywords in rules:
        if any(keyword in lowered for keyword in keywords):
            return label
    return "main subject"


def parse_video_user_intent(user_text: str, current_flow: str = "promptvideo", previous_state: dict | None = None) -> dict:
    previous = dict(previous_state or {})
    text = _clean(user_text)
    flow = _clean(current_flow, 80).lower()
    source_type, task_type = FLOW_MAP.get(flow, ("prompt", "prompt_to_video"))
    platform, ratio = _platform_ratio(text, previous)
    goal, style = _goal_style(text, previous)
    selected_motion = _clean(previous.get("selected_motion") or previous.get("camera_motion"), 260)
    motion = normalize_video_motion(f"{text} {selected_motion}")
    must_keep = _matches(text, KEEP_RULES)
    must_avoid = _matches(text, AVOID_RULES)
    if source_type in {"image", "video_reference", "self_record"}:
        must_keep.extend(["original subject identity", "original composition and recognizable details"])
    if task_type == "image_to_video":
        must_avoid.extend(["warped source image", "product or face identity changes"])
    if task_type == "video_reference_to_video":
        must_avoid.extend(["copying the reference video exactly", "protected logos, faces, voices or brand elements"])
    if task_type == "change_scene":
        must_keep.extend(["original person or product identity", "natural face and body proportions"])
    duration_match = re.search(r"\b(\d{1,3})\s*(?:giây|seconds?|s)\b", text.lower())
    duration = f"{duration_match.group(1)} seconds" if duration_match else _clean(previous.get("duration"), 60)
    background = _clean(previous.get("selected_context") or previous.get("background"), 240)
    if "nền" in text.lower() or "background" in text.lower() or "bối cảnh" in text.lower():
        background = text
    lighting = "luxury controlled lighting" if any(item in text.lower() for item in ("luxury", "sang trọng")) else _clean(previous.get("lighting"), 160)
    music = _clean(previous.get("selected_music") or previous.get("music_voice"), 180)
    try:
        scene_count = max(0, int(previous.get("scene_count") or 0))
    except (TypeError, ValueError):
        scene_count = 0
    spec = VideoIntentSpec(
        source_type=source_type,
        task_type=task_type,
        user_goal=goal,
        target_subject=_subject_type(text),
        product_or_topic=text or _clean(previous.get("selected_topic"), 700),
        audience=_clean(previous.get("audience"), 160),
        platform=platform,
        ratio=ratio,
        duration=duration,
        style=style,
        scene_count=scene_count,
        camera_motion=motion["camera_motion"],
        subject_motion=motion["subject_motion"],
        transition=motion["transition"],
        background=background,
        lighting=lighting or "controlled professional lighting",
        color_palette=_clean(previous.get("color_palette"), 160),
        music_voice=music,
        caption_cta=_clean(previous.get("caption_cta"), 220),
        must_keep=_unique(must_keep),
        must_avoid=_unique(must_avoid),
        quality_tier=_clean(previous.get("quality_tier") or previous.get("video_tier"), 40),
        provider_target=_clean(previous.get("provider_target"), 80),
        needs_clarification=video_request_is_vague(text),
    )
    return asdict(spec)


def _list_text(values, fallback: str) -> str:
    items = _unique(values or [])
    return "; ".join(items) if items else fallback


def build_video_prompt(intent: VideoIntentSpec | dict) -> dict:
    spec = asdict(intent) if isinstance(intent, VideoIntentSpec) else dict(intent or {})
    task = _clean(spec.get("task_type"), 80) or "prompt_to_video"
    topic = _clean(spec.get("product_or_topic"), 900) or "the requested subject"
    ratio = _clean(spec.get("ratio"), 20) or "9:16"
    platform = _clean(spec.get("platform"), 40) or "custom"
    camera = _clean(spec.get("camera_motion"), 300) or "stable camera with subtle natural movement"
    subject_motion = _clean(spec.get("subject_motion"), 300) or "natural restrained subject motion"
    transition = _clean(spec.get("transition"), 240) or "clean smooth transition"
    must_keep = _list_text(spec.get("must_keep"), "the requested subject, colors and recognizable details")
    must_avoid = _list_text(spec.get("must_avoid"), DEFAULT_NEGATIVE)
    tier = _clean(spec.get("quality_tier"), 40).lower() or "basic"
    quality = TIER_QUALITY.get(tier, TIER_QUALITY["basic"])
    common = (
        f"Goal: {_clean(spec.get('user_goal'), 180) or 'clear short-form communication'}. "
        f"Main subject: {topic}. Background/context: {_clean(spec.get('background'), 260) or 'a relevant clean environment'}. "
        f"Style: {_clean(spec.get('style'), 180) or 'professional and visually coherent'}. "
        f"Platform: {platform}. aspect ratio {ratio}. Camera movement: {camera}. Subject movement: {subject_motion}. "
        f"Transition: {transition}. Lighting/color: {_clean(spec.get('lighting'), 180) or 'controlled professional lighting'}; "
        f"{_clean(spec.get('color_palette'), 160) or 'coherent brand-safe colors'}. Quality: {quality}. "
        f"Must keep: {must_keep}. Avoid: {must_avoid}; {DEFAULT_NEGATIVE}. "
        "If a phone, laptop or screen appears, keep the screen clean or slightly blurred with no readable UI text."
    )
    if task == "image_to_video":
        prompt = (
            "Use the uploaded image as the visual reference. Preserve the main subject, face or product identity, "
            "legitimate logo, color palette and composition. Animate only the requested camera and subject movement. "
            f"{common} Use subtle natural motion and smooth cinematic movement with no excessive deformation."
        )
    elif task == "video_reference_to_video":
        prompt = (
            "Analyze the reference video structure and create a new concept inspired only by its pacing, camera rhythm, "
            "scene structure and visual style. Do not copy the original video exactly or reuse protected identity, branding, faces or voices. "
            f"New topic/product: {topic}. Use a new opening hook, original scene progression and a distinct ending. {common}"
        )
    elif task == "trend_video":
        prompt = (
            f"Create a trend-style short video for {topic}. The opening 1-3 seconds must hook the viewer. "
            "Use clear visual focus, social-media-friendly pacing, a concise main benefit, result/proof and a soft CTA. "
            f"{common}"
        )
    elif task == "storyboard_video":
        prompt = (
            f"Create a scene-specific video prompt for the storyboard subject {topic}. Keep this scene independent and editable. "
            f"Include scene duration, camera, subject action and a clean transition to the next scene. {common}"
        )
    elif task == "frame_video":
        prompt = (
            "Local frame-video plan only. Use the uploaded images in their selected order. Do not call a generative video provider. "
            f"Ratio: {ratio}. Camera simulation/effect: {camera}. Transition: {transition}. "
            f"Music/voice plan: {_clean(spec.get('music_voice'), 180) or 'none selected'}."
        )
    elif task == "change_scene":
        prompt = (
            "Keep the original person or product identity stable. Change only the requested background or style. "
            "Preserve face, body proportions, product geometry, legitimate logo and natural motion. "
            f"{common}"
        )
    elif task == "long_script":
        prompt = (
            f"Long-form planning only for {topic}. Create an outline, script, chapter list and separate short scene prompts. "
            "Do not render one long video directly; split later rendering into small reviewable scene jobs. "
            f"{common}"
        )
    else:
        prompt = f"Create a short AI-generated video based on this request. {common}"
    caution = ""
    lowered = topic.lower()
    if any(term in lowered for term in SENSITIVE_IDENTITY_TERMS) or spec.get("must_keep"):
        caution = (
            "Video AI may slightly distort faces, text, logos, packaging or product details. "
            "The prompt protects identity and geometry, but the result still requires review."
        )
    if spec.get("needs_clarification"):
        caution = (caution + " " if caution else "") + "The request is brief; clarify goal, platform, subject and motion before paid rendering."
    return {
        "intent": spec,
        "prompt": _clean(prompt, 3600),
        "negative_prompt": _clean(f"{must_avoid}; {DEFAULT_NEGATIVE}", 1200),
        "caution": caution,
        "provider_video_allowed": task != "frame_video",
    }


def validate_video_prompt_against_user_request(user_request: str, generated_prompt: str, intent: dict | None = None) -> dict:
    spec = dict(intent or parse_video_user_intent(user_request))
    prompt = _clean(generated_prompt).lower()
    missing = []
    ratio = _clean(spec.get("ratio"), 20)
    if ratio and ratio.lower() not in prompt:
        missing.append("ratio")
    for field in ("camera_motion", "subject_motion"):
        value = _clean(spec.get(field), 240).lower()
        key_terms = [part.strip() for part in re.split(r"[;,]", value) if len(part.strip()) > 3]
        if key_terms and not any(term in prompt for term in key_terms):
            missing.append(field)
    if spec.get("must_keep") and "must keep" not in prompt and "preserve" not in prompt:
        missing.append("must_keep")
    if spec.get("must_avoid") and "avoid" not in prompt and "negative" not in prompt:
        missing.append("must_avoid")
    task = _clean(spec.get("task_type"), 80)
    required_task_text = {
        "image_to_video": "uploaded image",
        "video_reference_to_video": "reference video",
        "trend_video": "opening 1-3 seconds",
        "frame_video": "do not call a generative video provider",
        "change_scene": "keep the original",
        "long_script": "do not render one long video directly",
    }.get(task)
    if required_task_text and required_task_text not in prompt:
        missing.append("task_template")
    return {"ok": not missing, "missing": missing, "task_type": task}


def enhance_video_prompt_for_generation(
    user_request: str,
    tier: str = "",
    ratio: str = "",
    current_flow: str = "promptvideo",
    previous_state: dict | None = None,
) -> str:
    previous = dict(previous_state or {})
    previous["quality_tier"] = tier
    if ratio:
        previous["ratio"] = ratio
    intent = parse_video_user_intent(user_request, current_flow, previous)
    result = build_video_prompt(intent)
    validation = validate_video_prompt_against_user_request(user_request, result["prompt"], intent)
    if not validation["ok"]:
        result["prompt"] = _clean(
            f"{result['prompt']} Validation guard: preserve requested ratio, camera motion, subject motion, must-keep and avoid constraints.",
            3800,
        )
    return result["prompt"]
