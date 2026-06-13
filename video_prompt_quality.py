import re
from dataclasses import asdict, dataclass, field


@dataclass
class VideoPromptSpec:
    user_idea: str = ""
    target_platform: str = "custom"
    duration_seconds: int = 15
    language: str = "en"
    genre: str = "product_ad"
    style_pack: str = "corporate_tech_commercial"
    action_pack: str = "product_showcase"
    subject_type: str = "main subject"
    subject_description: str = ""
    product_description: str = ""
    scene_context: str = ""
    transformation_type: str = ""
    camera_style: str = ""
    lighting_style: str = ""
    vfx_style: str = ""
    audio_style: str = "modern_electronic"
    shot_count: int = 0
    shot_breakdown: list[dict] = field(default_factory=list)
    continuity_locks: list[str] = field(default_factory=list)
    negative_constraints: list[str] = field(default_factory=list)
    provider_notes: str = ""
    prompt_strength: str = "director"
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


# Backward-compatible name used by older callers.
VideoIntentSpec = VideoPromptSpec


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

STYLE_PACK_ROWS = (
    ("dark_angel_gothic", "Dark Angel / Gothic Transformation", "ominous transformation", "low-key moonlight and sharp rim light", "slow push-in, low angle and controlled orbit", "deliberate supernatural motion", "tension riser and bass impact", "smoke, feathers and restrained shadow particles", "gothic cinematic realism", "avoid horror gore, unstable wings and identity drift"),
    ("mafia_boss_luxury", "Mafia Boss Luxury", "controlled power and status", "warm practical lights with black-gold contrast", "low-angle dolly and slow orbit", "measured confident movement", "luxury bass and subtle room ambience", "light haze and polished reflections", "premium crime-drama composition", "avoid weapons unless requested and avoid caricature"),
    ("cyberpunk_hacker", "Cyberpunk Hacker", "focused future-tech tension", "cyan-magenta screen glow", "handheld inserts and smooth push-in", "precise hand and screen interaction", "electronic pulse and interface clicks", "restrained holographic overlays", "cyberpunk realism", "avoid unreadable UI text and excessive neon"),
    ("future_ai_office", "Future AI Office", "calm efficient automation", "clean white light with turquoise accents", "dolly through connected workstations", "natural staff and dashboard activity", "modern electronic ambience", "subtle data trails and interface glow", "clean corporate futurism", "avoid fantasy machinery and fake readable dashboards"),
    ("product_luxury_reveal", "Product Luxury Reveal", "premium desire and precision", "controlled studio key light and rim highlights", "macro detail, orbit and hero push-in", "stable product turntable motion", "luxury bass with tactile clicks", "light sweep and restrained particles", "high-end commercial photography", "never alter product shape, color, logo or packaging"),
    ("tiktok_viral_product_demo", "TikTok Viral Product Demo", "fast useful proof", "bright practical social lighting", "snap zoom, handheld detail and quick cuts", "clear hands-on demonstration", "upbeat beat, whoosh and click SFX", "minimal callout motion", "credible short-form UGC", "avoid exaggerated claims and unstable hands"),
    ("beauty_fashion_glowup", "Beauty / Fashion Glow-up", "confident transformation", "soft beauty key and flattering rim light", "mirror match cut and smooth orbit", "natural pose and outfit movement", "fashion bass and fabric ASMR", "sparkle accents and clean match cuts", "editorial fashion realism", "preserve face, skin texture and garment details"),
    ("superhero_transformation", "Superhero Transformation", "earned power reveal", "dramatic backlight and volumetric beams", "low-angle push-in and orbit", "grounded transformation pose", "cinematic rise and impact hit", "energy ribbons and controlled light burst", "realistic superhero cinema", "avoid copied protected costumes and anatomy distortion"),
    ("samurai_warrior_reveal", "Samurai / Warrior Reveal", "discipline and resolve", "dawn side light with atmospheric haze", "wide establish, detail inserts and slow push-in", "measured stance and fabric motion", "taiko-inspired pulse and wind ambience", "dust and restrained ember particles", "historical cinematic realism", "avoid gore, unsafe weapon focus and cultural caricature"),
    ("scifi_portal_transition", "Sci-fi Portal Transition", "discovery and transition", "cool portal glow with consistent scene exposure", "walk-through tracking shot", "natural approach and crossing action", "electronic riser and portal whoosh", "stable portal edge and light refraction", "grounded science-fiction", "avoid subject duplication and environment flicker"),
    ("documentary_premium", "Documentary Premium", "credible observation", "natural available light", "stable handheld, wide context and detail inserts", "authentic unscripted movement", "location ambience and restrained score", "no decorative VFX", "premium documentary realism", "avoid staged reactions and artificial skin"),
    ("corporate_tech_commercial", "Corporate Tech Commercial", "clarity, trust and capability", "clean neutral lighting with brand accents", "smooth dolly, screen detail and team wide shot", "natural work interactions", "modern corporate pulse and soft clicks", "subtle line animation and data glow", "polished corporate commercial", "avoid unreadable screen text and generic stock-video behavior"),
    ("real_estate_cinematic", "Real Estate Cinematic", "space, comfort and aspiration", "balanced window exposure and warm interiors", "gimbal walk-through, wide reveal and detail pan", "minimal natural lifestyle movement", "ambient luxury and room tone", "gentle speed ramps only", "architectural cinematic realism", "keep room geometry stable and avoid impossible spaces"),
    ("food_commercial", "Food Commercial", "freshness and appetite appeal", "soft directional food lighting", "macro push-in, overhead detail and slow motion", "realistic pour, steam and texture movement", "crisp kitchen ASMR and subtle music", "steam, condensation and ingredient motion", "photoreal food advertising", "avoid synthetic texture and impossible liquid physics"),
    ("fitness_motivation", "Fitness Motivation", "discipline and momentum", "high-contrast gym light", "tracking, detail close-up and controlled handheld", "anatomically correct exercise motion", "rhythmic percussion and breath SFX", "subtle sweat and dust highlights", "athletic commercial realism", "avoid unsafe form and body distortion"),
    ("comedy_fast_cut", "Comedy Fast Cut", "relatable surprise", "bright natural lighting", "locked reaction shots and quick punch-in", "clear readable physical comedy", "comic pops and short beat stops", "minimal graphic accents", "clean social comedy", "avoid chaotic motion and offensive stereotypes"),
    ("horror_suspense", "Horror Suspense", "uncertainty without gore", "motivated darkness and narrow practical light", "slow creep, static hold and restrained handheld", "small tense movements", "room tone, low rumble and isolated impacts", "shadow movement and light flicker used sparingly", "psychological suspense", "avoid gore, flashing hazards and unreadable darkness"),
    ("emotional_storytelling", "Emotional Storytelling", "human memory and connection", "soft natural golden light", "slow push-in, close detail and gentle handheld", "subtle authentic gestures", "soft piano, room tone and intimate voiceover", "natural transitions with no heavy VFX", "cinematic human realism", "avoid melodrama and artificial tears"),
    ("before_after_transformation", "Before/After Transformation", "clear visible progress", "matched lighting across states", "locked composition and match-cut reveal", "controlled repeated action", "riser, snap and result hit", "wipe or match-cut transition", "credible comparison commercial", "keep angle, identity and product consistent"),
    ("ugc_review_style", "UGC Review Style", "honest first-person proof", "natural window or phone light", "stable handheld and close product inserts", "casual demonstration and reaction", "voice-first audio with light room ambience", "no heavy VFX", "authentic creator video", "avoid over-polished stock appearance and false claims"),
    ("affiliate_product_ad", "Affiliate Product Ad", "problem, proof and soft conversion", "bright practical light", "hook close-up, demo inserts and result shot", "clear product usage", "upbeat bed, whoosh and click SFX", "simple benefit callouts without generated text", "conversion-focused social ad", "avoid unsupported promises and altered product details"),
    ("app_saas_explainer", "App / SaaS Explainer", "simple understanding and utility", "clean office light and screen-safe exposure", "over-shoulder, device macro and smooth push-in", "natural tap and workflow motion", "light electronic pulse and UI clicks", "subtle interface highlight only", "modern SaaS commercial", "avoid fabricated readable UI and impossible interactions"),
    ("camera_elv_installation_demo", "Camera / ELV Installation Demo", "technical confidence and safety", "clear practical work light", "wide setup, tool detail and result pan", "accurate installation steps", "clean voiceover and tool SFX", "simple diagram-like transitions", "credible technical demonstration", "avoid unsafe wiring or fake certifications"),
    ("ai_automation_system_promo", "AI Automation System Promo", "connected workflow and measurable efficiency", "white-to-turquoise technology lighting", "workflow dolly, dashboard close-up and team reveal", "coordinated bot, content and media actions", "future electronic pulse and confirmation clicks", "subtle connected data paths", "premium AI automation commercial", "avoid fantasy robots, fake claims and unreadable dashboards"),
)

STYLE_PACKS = {
    key: {
        "name": name,
        "mood": mood,
        "lighting": lighting,
        "camera": camera,
        "motion": motion,
        "audio": audio,
        "common_vfx": vfx,
        "prompt_modifiers": modifiers,
        "negative_constraints": negatives,
    }
    for key, name, mood, lighting, camera, motion, audio, vfx, modifiers, negatives in STYLE_PACK_ROWS
}

ACTION_PACK_ROWS = (
    ("finger_snap_transformation", "Finger snap transformation", "a crisp finger snap triggers the change", "close-up to medium reveal", "snap match cut", "small light pulse", "sharp snap and bass hit"),
    ("match_cut_outfit_change", "Match cut outfit change", "repeat the same pose while the outfit changes", "locked framing", "match cut", "brief light sweep", "fabric rustle and whoosh"),
    ("smoke_burst_reveal", "Smoke burst reveal", "a controlled smoke burst reveals the subject", "slow push-in", "smoke wipe", "restrained smoke volume", "smoke burst and low impact"),
    ("feather_particle_reveal", "Feather / particle reveal", "particles gather and reveal the subject", "gentle orbit", "particle dissolve", "controlled particles", "soft flutter and riser"),
    ("product_spin_reveal", "Product spin reveal", "the product rotates slowly into a hero angle", "macro orbit", "clean cut", "light sweep", "tactile click and bass accent"),
    ("before_after_wipe", "Before / after wipe", "show the same composition before and after", "locked camera", "split wipe", "minimal edge glow", "snap and result chime"),
    ("phone_screen_transition", "Phone screen transition", "camera moves through a clean phone screen into the next scene", "push toward device", "screen portal cut", "subtle screen glow", "tap and digital whoosh"),
    ("door_opening_transition", "Door opening transition", "opening a door reveals the new environment", "tracking follow", "motivated doorway cut", "natural exposure shift", "door latch and room ambience"),
    ("walk_through_reveal", "Walk-through reveal", "the subject walks through foreground cover into the reveal", "gimbal tracking", "foreground wipe", "light haze", "footsteps and soft riser"),
    ("slow_push_in", "Slow push-in", "hold natural action while tension builds", "slow push-in", "clean cut", "none", "subtle room tone"),
    ("orbit_camera", "Orbit camera", "keep the subject stable while the camera orbits", "controlled orbit", "clean cut", "parallax depth", "soft cinematic pulse"),
    ("bullet_time_freeze", "Bullet-time freeze", "freeze one decisive moment while the camera moves", "bullet-time arc", "speed ramp", "restrained motion trails", "time-stop hit"),
    ("explosion_of_light", "Explosion of light", "a controlled light burst reveals the final state", "low-angle reveal", "flash match cut", "volumetric light", "riser and impact"),
    ("fabric_ribbon_transition", "Fabric / ribbon transition", "fabric crosses the lens and reveals the next state", "close tracking", "fabric wipe", "natural cloth simulation", "fabric ASMR and whoosh"),
    ("object_morph", "Object morph", "one object transforms while preserving silhouette and purpose", "locked macro", "shape match cut", "controlled morph", "tonal rise and click"),
    ("hand_gesture_trigger", "Hand gesture trigger", "a clear hand gesture triggers the scene change", "medium close-up", "gesture match cut", "small light trace", "gesture swish"),
    ("logo_product_hero_shot", "Logo / product hero shot", "finish with a stable product or legitimate logo hero frame", "slow final push-in", "clean settle", "light sweep", "brand sting"),
    ("cinematic_final_stare", "Cinematic final stare", "the character holds a calm final look", "subtle push-in", "hold", "none", "music resolve and room tone"),
    ("cta_end_frame", "CTA end frame", "reserve a clean final composition for externally added CTA", "locked frame", "soft fade", "none", "short resolve"),
    ("voiceover_driven_demo", "Voiceover-driven demo", "each action directly illustrates one voiceover point", "clear inserts", "motivated cuts", "minimal", "voice-first mix and practical SFX"),
    ("split_screen_comparison", "Split-screen comparison", "compare two states with matched framing", "locked dual framing", "split transition", "clean divider", "comparison clicks"),
    ("timeline_growth_animation", "Timeline growth animation", "show progress through distinct visual milestones", "steady lateral move", "milestone cuts", "subtle path glow", "progress pulses"),
    ("ai_dashboard_reveal", "AI dashboard reveal", "reveal a clean automation workflow without fabricated readable data", "over-shoulder push-in", "screen-to-world cut", "subtle data glow", "UI clicks and confirmation tone"),
    ("customer_pain_to_solution", "Customer pain → solution", "show a credible pain point, practical solution and result", "problem close-up to wide relief", "motivated match cut", "minimal", "tension-to-relief sound arc"),
)

ACTION_PACKS = {
    key: {
        "name": name,
        "action": action,
        "camera": camera,
        "transition": transition,
        "vfx": vfx,
        "audio": audio,
    }
    for key, name, action, camera, transition, vfx, audio in ACTION_PACK_ROWS
}

GENRE_TEMPLATES = {
    "product_ad": ["hook", "pain point", "product reveal", "practical demo", "benefit proof", "soft CTA"],
    "cinematic_story": ["character setup", "conflict", "turning point", "transformation", "power moment", "final emotion"],
    "trend_video": ["trend hook", "recognizable pattern", "subject adaptation", "surprise moment", "proof", "loop ending"],
    "storyboard_video": ["scene establish", "subject action", "visual proof", "transition bridge", "result", "next-scene handoff"],
    "scene_change": ["input lock", "original scene establish", "transition trigger", "new scene reveal", "identity proof", "final hold"],
    "realistic_human": ["identity establish", "natural action", "environment interaction", "controlled camera", "authentic reaction", "final hold"],
    "long_form": ["chapter hook", "context", "development", "evidence", "resolution", "chapter handoff"],
}

AUDIO_MODES = {
    "asmr_only": "No background music. Use crisp practical ASMR and location SFX.",
    "cinematic_light": "Light cinematic score with a restrained rise and clean final resolve.",
    "modern_electronic": "Modern electronic bed with a soft riser and clean transition whooshes.",
    "tension_riser": "Low tension riser, sparse impacts and controlled silence before the reveal.",
    "luxury_fashion_bass": "Minimal luxury bass, fabric detail and a refined reveal impact.",
    "product_click_pop": "Tactile product clicks, pops and clean practical demonstration SFX.",
    "whoosh_transition": "Short clean whooshes aligned with motivated transitions.",
    "nature_ambience": "Natural location ambience with restrained music.",
    "office_ambience": "Clean office room tone, subtle keyboard/click sounds and low music.",
    "voiceover_first": "Voiceover-first mix; music stays low and every action supports the narration.",
    "voiceover_vi": "Vietnamese voiceover-first mix with natural pacing and clear consonants.",
    "voiceover_en": "English voiceover-first mix with neutral commercial delivery.",
    "voiceover_zh": "Chinese voiceover-first mix with natural pacing and clear pronunciation.",
    "bass_reveal": "Build to one controlled bass hit on the main reveal.",
    "emotional_piano": "Soft emotional piano, intimate room tone and gentle final resolve.",
}

PROMPT_STRENGTH_LEVELS = {
    "quick": {"label": "⚡ Nhanh gọn", "detail": "compact direction with essential stability constraints"},
    "director": {"label": "🎬 Đạo diễn phim", "detail": "global vision, timed shots, camera, audio and continuity"},
    "viral": {"label": "🔥 Viral nâng cao", "detail": "strong hook, pattern interrupt, fast proof, SFX and CTA hold"},
    "provider_safe": {"label": "🧪 Provider-safe", "detail": "simpler motion, fewer VFX and maximum subject stability"},
    "premium": {"label": "👑 Cao cấp", "detail": "cinematic lensing, detailed movement, VFX, audio and polished final hold"},
}

PROMPT_EXAMPLE_SPECS = {
    "dark_angel_transformation": ("a man in a white shirt transforms into an original dark angel", "cinematic_story", "dark_angel_gothic", "finger_snap_transformation", "tension_riser"),
    "luxury_product_reveal": ("luxury perfume hero reveal", "product_ad", "product_luxury_reveal", "product_spin_reveal", "luxury_fashion_bass"),
    "tiktok_affiliate_demo": ("TikTok affiliate demo for a mini blender", "product_ad", "affiliate_product_ad", "customer_pain_to_solution", "voiceover_vi"),
    "ai_automation_office": ("TOAN AAS automates business operations", "product_ad", "ai_automation_system_promo", "ai_dashboard_reveal", "modern_electronic"),
    "cyberpunk_hacker_glowup": ("original cyberpunk hacker glow-up", "cinematic_story", "cyberpunk_hacker", "match_cut_outfit_change", "modern_electronic"),
    "beauty_fashion_transition": ("beauty fashion glow-up", "trend_video", "beauty_fashion_glowup", "fabric_ribbon_transition", "luxury_fashion_bass"),
    "home_cleaning_before_after": ("home cleaning before and after", "product_ad", "before_after_transformation", "before_after_wipe", "product_click_pop"),
    "food_commercial_macro": ("fresh food commercial macro sequence", "product_ad", "food_commercial", "product_spin_reveal", "asmr_only"),
    "real_estate_tour": ("modern apartment cinematic tour", "product_ad", "real_estate_cinematic", "walk_through_reveal", "cinematic_light"),
    "camera_installation": ("security camera installation demo", "product_ad", "camera_elv_installation_demo", "voiceover_driven_demo", "voiceover_vi"),
    "support_bot_demo": ("customer support bot resolves a request", "product_ad", "app_saas_explainer", "ai_dashboard_reveal", "office_ambience"),
    "content_factory_promo": ("AI content factory workflow", "product_ad", "corporate_tech_commercial", "timeline_growth_animation", "modern_electronic"),
    "dubbing_demo": ("multilingual voice dubbing workflow", "product_ad", "app_saas_explainer", "voiceover_driven_demo", "voiceover_first"),
    "music_generation_promo": ("AI music generation promo", "trend_video", "corporate_tech_commercial", "timeline_growth_animation", "modern_electronic"),
    "business_growth_transformation": ("small business growth transformation", "cinematic_story", "emotional_storytelling", "customer_pain_to_solution", "emotional_piano"),
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


def _duration_seconds(text: str, previous: dict) -> int:
    explicit = previous.get("duration_seconds")
    try:
        if explicit:
            return max(3, min(3600, int(explicit)))
    except (TypeError, ValueError):
        pass
    source = f"{_clean(text)} {_clean(previous.get('duration'), 80)}".lower()
    minute_match = re.search(r"\b(\d{1,3})\s*(?:phút|minutes?|mins?)\b", source)
    if minute_match:
        return max(60, min(3600, int(minute_match.group(1)) * 60))
    second_match = re.search(r"\b(\d{1,4})\s*(?:giây|seconds?|secs?|s)\b", source)
    if second_match:
        return max(3, min(3600, int(second_match.group(1))))
    return 15


def _infer_genre(text: str, task_type: str, previous: dict) -> str:
    selected = _clean(previous.get("genre") or previous.get("prompt_kind"), 80).lower()
    aliases = {
        "ad": "product_ad",
        "cinema": "cinematic_story",
        "viral": "trend_video",
        "storyboard": "storyboard_video",
    }
    if selected:
        return aliases.get(selected, selected if selected in GENRE_TEMPLATES else "")
    lowered = _clean(text).lower()
    if task_type == "trend_video" or any(word in lowered for word in ("trend", "viral", "tiktok", "reels")):
        return "trend_video"
    if task_type == "storyboard_video":
        return "storyboard_video"
    if task_type == "change_scene":
        return "scene_change"
    if task_type == "long_script" or any(word in lowered for word in ("video dài", "long-form", "long form")):
        return "long_form"
    if any(word in lowered for word in ("điện ảnh", "cinematic", "câu chuyện", "story", "dark angel", "mafia", "samurai", "horror")):
        return "cinematic_story"
    if any(word in lowered for word in ("người thật", "real human", "chân thật", "realistic human")):
        return "realistic_human"
    return "product_ad"


def _infer_style_pack(text: str, genre: str, previous: dict) -> str:
    selected = _clean(previous.get("style_pack"), 80).lower()
    if selected in STYLE_PACKS:
        return selected
    lowered = _clean(text).lower()
    rules = (
        ("dark_angel_gothic", ("dark angel", "thiên thần bóng tối", "gothic")),
        ("mafia_boss_luxury", ("mafia", "ông trùm")),
        ("cyberpunk_hacker", ("cyberpunk", "hacker")),
        ("ai_automation_system_promo", ("toan aas", "ai automation system", "tự động hóa ai")),
        ("future_ai_office", ("future ai office", "văn phòng tương lai")),
        ("food_commercial", ("đồ ăn", "món ăn", "food", "cà phê", "coffee")),
        ("real_estate_cinematic", ("bất động sản", "căn hộ", "real estate", "homestay")),
        ("camera_elv_installation_demo", ("camera", "elv", "installation", "lắp đặt")),
        ("app_saas_explainer", ("app", "saas", "phần mềm", "software")),
        ("beauty_fashion_glowup", ("beauty", "fashion", "thời trang", "makeup", "glow-up", "glow up")),
        ("fitness_motivation", ("fitness", "gym", "workout", "tập luyện")),
        ("before_after_transformation", ("before/after", "before after", "trước/sau")),
        ("ugc_review_style", ("ugc", "review", "đời thường")),
        ("affiliate_product_ad", ("affiliate", "tiktok shop")),
        ("documentary_premium", ("documentary", "tài liệu")),
        ("horror_suspense", ("horror", "kinh dị", "suspense")),
        ("comedy_fast_cut", ("comedy", "hài")),
        ("emotional_storytelling", ("cảm xúc", "ký ức", "gia đình", "emotional")),
        ("corporate_tech_commercial", ("doanh nghiệp", "corporate", "công nghệ", "technology")),
        ("product_luxury_reveal", ("luxury", "sang trọng", "cao cấp", "nước hoa", "perfume")),
    )
    for style_key, keywords in rules:
        if any(keyword in lowered for keyword in keywords):
            return style_key
    if genre == "trend_video":
        return "tiktok_viral_product_demo"
    if genre == "cinematic_story":
        return "emotional_storytelling"
    if genre == "realistic_human":
        return "documentary_premium"
    return "corporate_tech_commercial"


def _infer_action_pack(text: str, genre: str, previous: dict) -> str:
    selected = _clean(previous.get("action_pack"), 80).lower()
    if selected in ACTION_PACKS:
        return selected
    lowered = _clean(text).lower()
    rules = (
        ("finger_snap_transformation", ("finger snap", "búng tay")),
        ("match_cut_outfit_change", ("đổi trang phục", "outfit change")),
        ("smoke_burst_reveal", ("smoke", "khói")),
        ("feather_particle_reveal", ("feather", "lông vũ", "particle")),
        ("product_spin_reveal", ("xoay 360", "product spin", "sản phẩm xoay")),
        ("before_after_wipe", ("before/after", "before after", "trước/sau")),
        ("phone_screen_transition", ("phone screen", "màn hình điện thoại")),
        ("door_opening_transition", ("mở cửa", "door opening")),
        ("walk_through_reveal", ("walk through", "bước qua", "đi xuyên")),
        ("orbit_camera", ("orbit", "quay quanh", "xoay quanh")),
        ("bullet_time_freeze", ("bullet time", "đóng băng")),
        ("fabric_ribbon_transition", ("fabric", "ribbon", "dải lụa", "vải")),
        ("object_morph", ("morph", "biến hình vật thể")),
        ("hand_gesture_trigger", ("hand gesture", "cử chỉ tay")),
        ("split_screen_comparison", ("split screen", "chia đôi màn hình")),
        ("timeline_growth_animation", ("timeline", "tăng trưởng")),
        ("ai_dashboard_reveal", ("dashboard", "workflow", "tự động hóa")),
        ("customer_pain_to_solution", ("pain point", "vấn đề", "giải pháp")),
    )
    for action_key, keywords in rules:
        if any(keyword in lowered for keyword in keywords):
            return action_key
    if genre == "trend_video":
        return "before_after_wipe"
    if genre == "cinematic_story":
        return "cinematic_final_stare"
    if genre == "product_ad":
        return "product_showcase" if "product_showcase" in ACTION_PACKS else "logo_product_hero_shot"
    return "slow_push_in"


def _infer_audio_style(text: str, style_pack: str, previous: dict) -> str:
    selected = _clean(previous.get("audio_style"), 80).lower()
    if selected in AUDIO_MODES:
        return selected
    music = _clean(previous.get("selected_music") or previous.get("music_voice"), 180).lower()
    combined = f"{_clean(text).lower()} {music}"
    rules = (
        ("asmr_only", ("không nhạc", "no music", "asmr")),
        ("voiceover_vi", ("voice tiếng việt", "vietnamese voice", "giọng việt")),
        ("voiceover_en", ("english voice", "giọng anh")),
        ("voiceover_zh", ("chinese voice", "giọng trung")),
        ("emotional_piano", ("piano", "cảm xúc", "emotional")),
        ("luxury_fashion_bass", ("luxury", "fashion", "sang trọng")),
        ("tension_riser", ("tension", "căng thẳng", "suspense")),
        ("office_ambience", ("office", "văn phòng", "corporate")),
        ("nature_ambience", ("nature", "thiên nhiên")),
        ("bass_reveal", ("bass hit", "impact")),
        ("voiceover_first", ("voiceover", "lời đọc", "thuyết minh")),
    )
    for audio_key, keywords in rules:
        if any(keyword in combined for keyword in keywords):
            return audio_key
    style_audio = STYLE_PACKS.get(style_pack, {}).get("audio", "")
    if "piano" in style_audio:
        return "emotional_piano"
    if "luxury" in style_audio or "bass" in style_audio:
        return "luxury_fashion_bass"
    return "modern_electronic"


def _infer_prompt_strength(text: str, previous: dict) -> str:
    selected = _clean(previous.get("prompt_strength"), 40).lower().replace("-", "_")
    aliases = {"fast": "quick", "safe": "provider_safe", "cao_cap": "premium"}
    selected = aliases.get(selected, selected)
    if selected in PROMPT_STRENGTH_LEVELS:
        return selected
    lowered = _clean(text).lower()
    if any(word in lowered for word in ("provider-safe", "provider safe", "ổn định", "dễ render")):
        return "provider_safe"
    if any(word in lowered for word in ("viral", "tiktok", "reels")):
        return "viral"
    if any(word in lowered for word in ("premium", "cao cấp", "đạo diễn", "cinematic")):
        return "premium"
    return "director"


def _shot_count_for_duration(duration_seconds: int) -> int:
    if duration_seconds <= 6:
        return 3
    if duration_seconds <= 8:
        return 4
    if duration_seconds <= 10:
        return 5
    if duration_seconds <= 15:
        return 7
    if duration_seconds <= 30:
        return 6
    if duration_seconds <= 60:
        return 8
    return max(6, min(10, round(duration_seconds / 30)))


def _build_shot_breakdown(spec: dict) -> list[dict]:
    duration = max(3, int(spec.get("duration_seconds") or 15))
    count = max(1, int(spec.get("shot_count") or _shot_count_for_duration(duration)))
    genre = spec.get("genre") if spec.get("genre") in GENRE_TEMPLATES else "product_ad"
    phases = GENRE_TEMPLATES[genre]
    style = STYLE_PACKS.get(spec.get("style_pack"), STYLE_PACKS["corporate_tech_commercial"])
    action = ACTION_PACKS.get(spec.get("action_pack"), ACTION_PACKS["slow_push_in"])
    topic = _clean(spec.get("product_or_topic") or spec.get("user_idea"), 360) or "the main subject"
    if duration >= 60:
        segment_length = duration / count
        return [
            {
                "index": idx + 1,
                "start": round(idx * segment_length, 1),
                "end": round(min(duration, (idx + 1) * segment_length), 1),
                "beat": f"chapter {idx + 1}: {phases[idx % len(phases)]}",
                "visual": f"{topic}; maintain the same subject/product lock across this chapter",
                "action": action["action"],
                "camera": style["camera"],
                "transition": action["transition"],
                "audio": AUDIO_MODES.get(spec.get("audio_style"), AUDIO_MODES["modern_electronic"]),
            }
            for idx in range(count)
        ]
    shot_length = duration / count
    shots = []
    for idx in range(count):
        start = round(idx * shot_length, 1)
        end = round(duration if idx == count - 1 else (idx + 1) * shot_length, 1)
        beat = phases[min(len(phases) - 1, round(idx * (len(phases) - 1) / max(1, count - 1)))]
        shots.append(
            {
                "index": idx + 1,
                "start": start,
                "end": end,
                "beat": beat,
                "visual": f"{topic}; {style['mood']}",
                "action": action["action"],
                "camera": action["camera"] if idx in {1, count - 2} else style["camera"],
                "transition": "final hold" if idx == count - 1 else action["transition"],
                "audio": action["audio"] if idx in {0, count - 1} else AUDIO_MODES.get(spec.get("audio_style"), AUDIO_MODES["modern_electronic"]),
            }
        )
    return shots


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
    duration_seconds = _duration_seconds(text, previous)
    duration = f"{duration_seconds} seconds"
    background = _clean(previous.get("selected_context") or previous.get("background"), 240)
    if "nền" in text.lower() or "background" in text.lower() or "bối cảnh" in text.lower():
        background = text
    lighting = "luxury controlled lighting" if any(item in text.lower() for item in ("luxury", "sang trọng")) else _clean(previous.get("lighting"), 160)
    music = _clean(previous.get("selected_music") or previous.get("music_voice"), 180)
    try:
        scene_count = max(0, int(previous.get("scene_count") or 0))
    except (TypeError, ValueError):
        scene_count = 0
    genre = _infer_genre(text, task_type, previous)
    style_pack = _infer_style_pack(text, genre, previous)
    action_pack = _infer_action_pack(text, genre, previous)
    audio_style = _infer_audio_style(text, style_pack, previous)
    prompt_strength = _infer_prompt_strength(text, previous)
    subject_type = _subject_type(text)
    continuity_locks = _unique(
        [
            "keep the same face and identity from the source when a person is present",
            "keep product shape, color, packaging and legitimate logo consistent",
            "keep hands, fingers, eyes and mouth anatomically stable",
            "keep camera motion smooth and scene lighting consistent",
            "do not generate unreadable text overlays",
            *must_keep,
        ]
    )
    negative_constraints = _unique([*must_avoid, *[item.strip() for item in DEFAULT_NEGATIVE.split(",")]])
    style_data = STYLE_PACKS.get(style_pack, STYLE_PACKS["corporate_tech_commercial"])
    action_data = ACTION_PACKS.get(action_pack, ACTION_PACKS["slow_push_in"])
    shot_count = scene_count or _shot_count_for_duration(duration_seconds)
    spec = VideoPromptSpec(
        user_idea=text or _clean(previous.get("selected_topic"), 700),
        target_platform=platform,
        duration_seconds=duration_seconds,
        language=_clean(previous.get("prompt_language") or previous.get("language"), 20) or "en",
        genre=genre,
        style_pack=style_pack,
        action_pack=action_pack,
        subject_type=subject_type,
        subject_description=_clean(previous.get("subject_description"), 500) or text,
        product_description=_clean(previous.get("product_description"), 500) or (text if subject_type in {"physical product", "software or app", "food or drink"} else ""),
        scene_context=background,
        transformation_type=action_data.get("name", ""),
        camera_style=motion["camera_motion"] or style_data.get("camera", ""),
        lighting_style=lighting or style_data.get("lighting", ""),
        vfx_style=style_data.get("common_vfx", ""),
        audio_style=audio_style,
        shot_count=shot_count,
        continuity_locks=continuity_locks,
        negative_constraints=negative_constraints,
        provider_notes=_clean(previous.get("provider_notes"), 300),
        prompt_strength=prompt_strength,
        source_type=source_type,
        task_type=task_type,
        user_goal=goal,
        target_subject=subject_type,
        product_or_topic=text or _clean(previous.get("selected_topic"), 700),
        audience=_clean(previous.get("audience"), 160),
        platform=platform,
        ratio=ratio,
        duration=duration,
        style=style,
        scene_count=shot_count,
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
    payload = asdict(spec)
    payload["shot_breakdown"] = _build_shot_breakdown(payload)
    return payload


def _list_text(values, fallback: str) -> str:
    items = _unique(values or [])
    return "; ".join(items) if items else fallback


def _clean_multiline(value, limit: int = 12000) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line)[:limit]


def _task_vision(spec: dict, topic: str) -> str:
    task = _clean(spec.get("task_type"), 80) or "prompt_to_video"
    genre = _clean(spec.get("genre"), 80)
    if task == "image_to_video":
        return (
            "Use the uploaded image as the visual reference. Preserve the main subject, face or product identity, "
            "legitimate logo, color palette and composition. Animate only the requested camera and subject movement."
        )
    if task == "video_reference_to_video":
        return (
            "Analyze the reference video structure and create an original concept inspired only by pacing, camera rhythm "
            "and scene structure. Do not copy the original video exactly or reuse protected identity, branding, faces or voices."
        )
    if task == "trend_video":
        return (
            f"Create a trend-style short video for {topic}. The opening 1-3 seconds must hook the viewer, "
            "then show recognizable pattern, useful proof, a surprise beat and a soft CTA or loop ending."
        )
    if task == "storyboard_video":
        return (
            f"Create a scene-specific video direction for the storyboard subject {topic}. "
            "Keep each scene independently editable while maintaining continuity across the sequence."
        )
    if task == "change_scene":
        return (
            "Keep the original person or product identity stable. Change only the requested background or style. "
            "Preserve face, body proportions, product geometry, legitimate logo and natural motion."
        )
    if task == "long_script":
        return (
            f"Build a long-form video plan for {topic}. Do not render one long video directly; "
            "split the story into reviewable chapters with separate prompts and a shared continuity summary."
        )
    if genre == "trend_video":
        return (
            f"Create a trend-style short video for {topic}. The opening 1-3 seconds must hook the viewer, "
            "then show recognizable pattern, useful proof, a surprise beat and a soft CTA or loop ending."
        )
    if genre == "cinematic_story":
        return (
            f"Create an original cinematic story for {topic}: establish the character or subject, introduce conflict, "
            "build a motivated transformation and finish on a clear emotional image."
        )
    if genre == "product_ad":
        return (
            f"Create a credible product or service advertisement for {topic}: hook, pain point, product reveal, "
            "practical demonstration, visible benefit and a soft CTA."
        )
    return f"Create an original AI-generated video for this request: {topic}."


def build_video_prompt(intent: VideoPromptSpec | dict) -> dict:
    spec = asdict(intent) if isinstance(intent, VideoIntentSpec) else dict(intent or {})
    task = _clean(spec.get("task_type"), 80) or "prompt_to_video"
    topic = _clean(spec.get("product_or_topic"), 900) or "the requested subject"
    ratio = _clean(spec.get("ratio"), 20) or "9:16"
    platform = _clean(spec.get("platform"), 40) or "custom"
    camera = _clean(spec.get("camera_motion"), 300) or "stable camera with subtle natural movement"
    subject_motion = _clean(spec.get("subject_motion"), 300) or "natural restrained subject motion"
    transition = _clean(spec.get("transition"), 240) or "clean smooth transition"
    must_keep = _list_text(
        spec.get("continuity_locks") or spec.get("must_keep"),
        "the requested subject, colors and recognizable details",
    )
    must_avoid = _list_text(
        spec.get("negative_constraints") or spec.get("must_avoid"),
        DEFAULT_NEGATIVE,
    )
    tier = _clean(spec.get("quality_tier"), 40).lower() or "basic"
    quality = TIER_QUALITY.get(tier, TIER_QUALITY["basic"])
    if task == "frame_video":
        prompt = (
            "Local frame-video plan only. Use the uploaded images in their selected order. Do not call a generative video provider. "
            f"Ratio: {ratio}. Camera simulation/effect: {camera}. Transition: {transition}. "
            f"Music/voice plan: {_clean(spec.get('music_voice'), 180) or 'none selected'}."
        )
        return {
            "intent": spec,
            "prompt": _clean(prompt, 3600),
            "negative_prompt": _clean(f"{must_avoid}; {DEFAULT_NEGATIVE}", 1200),
            "caution": "",
            "provider_video_allowed": False,
        }

    genre = _clean(spec.get("genre"), 80) or "product_ad"
    style_key = _clean(spec.get("style_pack"), 80) or "corporate_tech_commercial"
    action_key = _clean(spec.get("action_pack"), 80) or "slow_push_in"
    strength = _clean(spec.get("prompt_strength"), 40) or "director"
    style_pack = STYLE_PACKS.get(style_key, STYLE_PACKS["corporate_tech_commercial"])
    action_pack = ACTION_PACKS.get(action_key, ACTION_PACKS["slow_push_in"])
    audio_key = _clean(spec.get("audio_style"), 80) or "modern_electronic"
    audio = AUDIO_MODES.get(audio_key, AUDIO_MODES["modern_electronic"])
    duration_seconds = max(3, int(spec.get("duration_seconds") or 15))
    shots = list(spec.get("shot_breakdown") or _build_shot_breakdown(spec))
    if strength == "quick":
        shots = shots[: min(3, len(shots))]
    if strength == "provider_safe":
        vfx = "Minimal provider-safe effects; prefer clean cuts, stable geometry and one controlled motion per shot."
        camera_direction = "Use one slow, stable camera move per shot. Avoid bullet-time, heavy morphing and simultaneous complex actions."
    else:
        vfx = f"{style_pack['common_vfx']}; primary transition: {action_pack['transition']}; {action_pack['vfx']}."
        camera_direction = (
            f"{camera}. Style-pack camera: {style_pack['camera']}. Action camera: {action_pack['camera']}. "
            "Use motivated movement, readable blocking and smooth acceleration/deceleration."
        )
    if strength == "viral":
        vfx += " Add one clear pattern interrupt in the first 1-3 seconds and preserve a loopable final composition."
    if strength == "premium":
        vfx += " Use premium cinematic depth, physically plausible particles/reflections and polished match cuts without visual overload."

    shot_lines = []
    for shot in shots:
        label = "Segment" if duration_seconds >= 60 else "Shot"
        shot_lines.append(
            f"{shot.get('index')}. [{shot.get('start'):.1f}-{shot.get('end'):.1f}s] "
            f"{label} goal: {shot.get('beat')}. Visual: {shot.get('visual')}. "
            f"Action: {shot.get('action')}. Camera: {shot.get('camera')}. "
            f"Transition: {shot.get('transition')}. Audio cue: {shot.get('audio')}"
        )
    long_form_note = ""
    if duration_seconds >= 60:
        long_form_note = (
            "\n[Segment Outline]\n"
            "Render and review each segment separately. Reuse the exact Subject / Product Lock and continuity summary "
            "for every segment; archive completed segment prompts according to the job retention policy."
        )
    final_hold = (
        "Hold the final composition for 0.5-1.0 seconds with stable subject geometry and clean negative space. "
        "Do not generate readable CTA text; add verified text in post-production."
    )
    prompt = f"""
[Global Vision & Tone]
{_task_vision(spec, topic)}
Goal: {_clean(spec.get('user_goal'), 180) or 'clear visual communication'}. Genre: {genre}. Style pack: {style_pack['name']}.
Mood: {style_pack['mood']}. Platform: {platform}. aspect ratio {ratio}. Duration: {duration_seconds} seconds.

[Subject / Product Lock]
Main subject: {topic}. Subject type: {_clean(spec.get('subject_type') or spec.get('target_subject'), 100) or 'main subject'}.
Background/context: {_clean(spec.get('scene_context') or spec.get('background'), 260) or 'a relevant clean environment'}.
Must keep: {must_keep}.
If a phone, laptop or screen appears, keep the screen clean or slightly blurred with no readable UI text.

[Shot Breakdown]
{chr(10).join(shot_lines)}
{long_form_note}

[Camera Direction]
{camera_direction}

[VFX / Motion]
Subject movement: {subject_motion}. Primary action: {action_pack['action']}. Transition logic: {transition}. {vfx}

[Audio / SFX]
{audio} Style-pack cue: {style_pack['audio']}. Action cue: {action_pack['audio']}.

[Quality / Style]
{quality}. {style_pack['prompt_modifiers']}. Lighting: {_clean(spec.get('lighting_style') or spec.get('lighting'), 220) or style_pack['lighting']}.
Color: {_clean(spec.get('color_palette'), 160) or 'coherent brand-safe colors'}.

[Continuity Locks]
{must_keep}.

[Final Hold]
{final_hold}

[Negative Constraints]
{must_avoid}; {style_pack['negative_constraints']}; {DEFAULT_NEGATIVE}.
"""
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
        "prompt": _clean_multiline(prompt, 12000),
        "negative_prompt": _clean(f"{must_avoid}; {DEFAULT_NEGATIVE}", 1200),
        "caution": caution,
        "provider_video_allowed": True,
    }


def build_video_prompt_example(example_key: str) -> dict:
    example = PROMPT_EXAMPLE_SPECS.get(str(example_key or "").strip().lower())
    if not example:
        raise KeyError(f"Unknown video prompt example: {example_key}")
    idea, genre, style_pack, action_pack, audio_style = example
    intent = parse_video_user_intent(
        f"{idea} 15 seconds",
        "trend" if genre == "trend_video" else "promptvideo",
        {
            "genre": genre,
            "style_pack": style_pack,
            "action_pack": action_pack,
            "audio_style": audio_style,
            "prompt_strength": "director",
            "duration_seconds": 15,
        },
    )
    return build_video_prompt(intent)


def video_prompt_library_summary() -> dict:
    return {
        "style_pack_count": len(STYLE_PACKS),
        "action_pack_count": len(ACTION_PACKS),
        "audio_mode_count": len(AUDIO_MODES),
        "genre_template_count": len(GENRE_TEMPLATES),
        "prompt_strength_count": len(PROMPT_STRENGTH_LEVELS),
        "example_count": len(PROMPT_EXAMPLE_SPECS),
    }


def validate_video_prompt_against_user_request(user_request: str, generated_prompt: str, intent: dict | None = None) -> dict:
    spec = dict(intent or parse_video_user_intent(user_request))
    prompt = _clean(generated_prompt, 12000).lower()
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
        result["prompt"] = _clean_multiline(
            f"{result['prompt']} Validation guard: preserve requested ratio, camera motion, subject motion, must-keep and avoid constraints.",
            12000,
        )
    return result["prompt"]
