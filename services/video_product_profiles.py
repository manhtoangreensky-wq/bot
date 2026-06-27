"""Product profile brain for TOAN AAS generated video flows.

This module is intentionally provider-free and Telegram-free. It describes the
creative contract used before any render engine is called.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PROTECTED_STYLE_TERMS = (
    "ghibli",
    "pixar",
    "disney",
    "dreamworks",
    "makoto shinkai",
    "hayao miyazaki",
    "marvel",
    "dc comics",
    "star wars",
)


@dataclass(frozen=True)
class VideoProductProfile:
    profile_id: str
    menu_label: str
    product_goal: str
    script_formula: str
    system_prompt: str
    required_inputs: tuple[str, ...]
    optional_assets: tuple[str, ...]
    scene_templates_3: tuple[dict[str, str], ...]
    scene_templates_5: tuple[dict[str, str], ...]
    image_style: str
    camera_style: str
    motion_style: str
    transition_style: str
    voice_style: str
    music_style: str
    subtitle_style: str
    logo_policy: str
    pacing_policy: str
    postprocess_defaults: dict[str, Any] = field(default_factory=dict)
    public_enabled: bool = True
    admin_enabled: bool = True
    fact_policy: str = ""
    sfx_policy: str = ""
    overlay_policy: str = ""
    postprocess_policy: str = ""
    character_consistency: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


def _template(items: list[tuple[str, str, str]]) -> tuple[dict[str, str], ...]:
    return tuple({"role": role, "title": title, "purpose": purpose} for role, title, purpose in items)


DEFAULT_POSTPROCESS = {
    "burn_subtitles": True,
    "logo_position": "bottom_right",
    "logo_opacity": 0.82,
    "voice_volume": 1.0,
    "music_volume": 0.18,
    "keep_original_audio": False,
    "replace_original_audio": True,
    "target_loudness": -16,
}


VIDEO_PRODUCT_PROFILES: dict[str, VideoProductProfile] = {
    "storytelling": VideoProductProfile(
        profile_id="storytelling",
        menu_label="Video kể chuyện",
        product_goal="Continuous character/story flow with emotional retention.",
        script_formula="3-act structure: Hook -> rising action/conflict -> twist/resolution/open ending",
        system_prompt=(
            "Build a continuous story with one main character, clear emotional state, "
            "location logic, and transitions that make each scene feel connected."
        ),
        required_inputs=("idea_or_story",),
        optional_assets=("character_reference", "scene_background", "style_reference", "voice_audio", "music_audio", "logo"),
        scene_templates_3=_template([
            ("hook", "Character situation", "Open on the main character and a clear problem or emotion."),
            ("conflict", "Emotional turn", "Escalate the situation with one visible change."),
            ("ending", "Resolution or twist", "Resolve, twist, or leave an open emotional ending."),
        ]),
        scene_templates_5=_template([
            ("hook", "Establishing hook", "Introduce character, mood, and visual promise."),
            ("setup", "Character goal", "Show what the character wants."),
            ("conflict", "Conflict", "Create one obstacle or emotional pressure."),
            ("proof", "Climax", "Show the decisive visual/emotional turn."),
            ("ending", "Emotional ending", "Resolve or invite the viewer to continue."),
        ]),
        image_style="cinematic lighting, highly detailed, warm dramatic tone, consistent character and outfit",
        camera_style="gentle push-in, over-shoulder, medium close-up, stable framing",
        motion_style="natural movement, emotional pauses, one action per shot",
        transition_style="crossfade, match cut, gentle camera continuity",
        voice_style="warm emotional storyteller, slower pacing",
        music_style="soft beginning, more intense at climax, soft ending",
        subtitle_style="readable bottom captions with emotional emphasis",
        logo_policy="logo only at ending or subtle corner watermark",
        pacing_policy="let character emotion breathe; avoid random fast cuts",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.14},
    ),
    "product_review": VideoProductProfile(
        profile_id="product_review",
        menu_label="Video review sản phẩm / affiliate",
        product_goal="Sell a product quickly with clear benefits and high retention.",
        script_formula="AIDA/PAS: Attention -> Interest/Problem -> Desire/Solution -> Action/CTA",
        system_prompt=(
            "Create a sharp product review or affiliate video. Open with a pain point, "
            "show the product clearly, prove one benefit, and end with a CTA."
        ),
        required_inputs=("product_or_offer",),
        optional_assets=("product_reference", "object_reference", "logo", "brand_color", "music_audio", "voice_audio"),
        scene_templates_3=_template([
            ("hook", "Pain point", "Name the problem or attention hook in one visual beat."),
            ("product_reveal", "Product reveal", "Show the product and one key feature."),
            ("CTA", "Benefit and CTA", "Make the benefit concrete and invite action."),
        ]),
        scene_templates_5=_template([
            ("hook", "Hook", "Stop the scroll with a problem or bold result."),
            ("problem", "Problem", "Show why the viewer cares."),
            ("product_reveal", "Product reveal", "Reveal product/object with clean macro detail."),
            ("proof", "Proof or comparison", "Show feature, use-case, or before/after."),
            ("CTA", "Call to action", "Close with clear benefit and next action."),
        ]),
        image_style="studio product photography, macro close-up, clean background, high detail",
        camera_style="macro close-up, top-down, clean hero shot, quick cutaway",
        motion_style="fast cuts, clear hand/product movement, benefit demonstration",
        transition_style="snappy cut, match cut, product close-up transition",
        voice_style="high energy reviewer, clear CTA",
        music_style="trending upbeat beat under the voice",
        subtitle_style="large bottom captions, punchy keywords, popup emphasis if supported",
        logo_policy="brand logo at ending; subtle watermark if provided",
        pacing_policy="2-3 seconds per shot for short ads",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.2},
    ),
    "news": VideoProductProfile(
        profile_id="news",
        menu_label="Video tin tức",
        product_goal="Professional, neutral, factual summary.",
        script_formula="5W1H: Who, What, Where, When, Why, How",
        system_prompt=(
            "Summarize facts neutrally. Do not invent missing facts. If facts are uncertain, "
            "mark them as 'chua du du lieu' in the planning output."
        ),
        required_inputs=("news_text_or_topic",),
        optional_assets=("article_text", "scene_background", "style_reference", "logo"),
        scene_templates_3=_template([
            ("hook", "Main headline", "State the main event without exaggeration."),
            ("setup", "Key facts", "Cover the most important 5W1H facts."),
            ("ending", "Impact", "Explain what changes or what to watch next."),
        ]),
        scene_templates_5=_template([
            ("hook", "Headline", "Open with the verified headline."),
            ("setup", "Who and what", "Name the people/groups and event."),
            ("proof", "Where and when", "Show place/time context if available."),
            ("lesson", "Why and how", "Explain cause or mechanism carefully."),
            ("ending", "Impact or next step", "Close with consequence or follow-up."),
        ]),
        image_style="realistic photojournalism, sharp focus, natural newsroom lighting",
        camera_style="news package framing, lower-third friendly composition",
        motion_style="controlled camera movement, clean cutaway, no dramatized chaos",
        transition_style="clean news cut, subtle lower-third change",
        voice_style="news anchor, clear and neutral",
        music_style="light news intro/background",
        subtitle_style="clean lower-third, professional, concise",
        logo_policy="network or brand logo only if provided",
        pacing_policy="factual rhythm; avoid emotional exaggeration",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.1},
        fact_policy="Do not invent dates, names, locations, quotes, or causes. Mark uncertain facts as chua du du lieu.",
    ),
    "philosophy_quotes": VideoProductProfile(
        profile_id="philosophy_quotes",
        menu_label="Video triết lý / đạo lý / quotes",
        product_goal="Deep, slow, reflective short-form video.",
        script_formula="quote hook -> silence/pause -> short explanation -> emotional ending",
        system_prompt=(
            "Create a reflective video with pauses that matter. Use narration pause markers "
            "like [pause 0.8s] in the plan, but keep provider prompts plain if SSML is unsupported."
        ),
        required_inputs=("quote_or_core_message",),
        optional_assets=("scene_background", "style_reference", "voice_audio", "music_audio", "logo"),
        scene_templates_3=_template([
            ("hook", "Quote hook", "Open with a short thought or question."),
            ("setup", "Pause and reflection", "Let the visual breathe and explain simply."),
            ("ending", "Meaning", "End with one emotional line."),
        ]),
        scene_templates_5=_template([
            ("hook", "Visual hook", "Open with a quiet striking image."),
            ("setup", "Quote", "Deliver the quote with space."),
            ("lesson", "Pause/reflection", "Hold a beat and deepen meaning."),
            ("proof", "Explanation", "Connect the idea to daily life."),
            ("ending", "Emotional ending", "Leave a memorable final line."),
        ]),
        image_style="minimalist zen nature, peaceful fog, mountain, rain, dark cinematic background",
        camera_style="slow push, locked-off wide shot, gentle parallax",
        motion_style="slow motion, soft natural motion, visible pause beats",
        transition_style="slow dissolve, fade through darkness, calm match cut",
        voice_style="deep slow reflective voice with pause markers in narration plan",
        music_style="lofi, meditation, rain, wind, or nature ambience",
        subtitle_style="elegant large readable text, slow reveal",
        logo_policy="avoid logo unless brand requested; if used, keep subtle",
        pacing_policy="few scenes, slow movement, pauses matter",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.12},
    ),
    "educational": VideoProductProfile(
        profile_id="educational",
        menu_label="Video kiến thức",
        product_goal="Explain clearly and visually.",
        script_formula="ELI5: simple hook -> step 1 -> step 2 -> step 3 -> summary",
        system_prompt="Teach one idea clearly. Each new concept should become a new visual scene.",
        required_inputs=("topic_or_question",),
        optional_assets=("style_reference", "scene_background", "logo", "voice_audio", "music_audio"),
        scene_templates_3=_template([
            ("hook", "Concept hook", "Ask or state the simple question."),
            ("setup", "Step-by-step explanation", "Show the process in simple visuals."),
            ("lesson", "Summary", "Close with the practical lesson."),
        ]),
        scene_templates_5=_template([
            ("hook", "Hook/question", "Ask what the viewer will learn."),
            ("setup", "Definition", "Define the concept simply."),
            ("proof", "Example", "Show a concrete example."),
            ("solution", "Process", "Explain steps or mechanism."),
            ("lesson", "Summary", "Recap the key point."),
        ]),
        image_style="clean 3D illustration, infographic style, simple background, isometric diagram",
        camera_style="diagram-friendly framing, centered elements, clean labels reserved for postprocess",
        motion_style="step-by-step reveal, pointer-like movement, no clutter",
        transition_style="wipe between concepts, clean scene change",
        voice_style="bright trustworthy teacher/expert",
        music_style="low-volume lofi or corporate inspiration",
        subtitle_style="clear bullet-style captions",
        logo_policy="small educational brand watermark if provided",
        pacing_policy="new scene when a new concept starts",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.1},
    ),
    "history": VideoProductProfile(
        profile_id="history",
        menu_label="Video lịch sử",
        product_goal="Viral historical storytelling while avoiding fake facts.",
        script_formula="historian mode: context -> event -> turning point -> consequence -> lesson",
        system_prompt=(
            "Tell history carefully. Do not invent dates, names, or events. If input lacks facts, "
            "mark it as dramatized and do not present fiction as fact."
        ),
        required_inputs=("historical_topic_or_facts",),
        optional_assets=("scene_background", "style_reference", "logo", "voice_audio", "music_audio"),
        scene_templates_3=_template([
            ("setup", "Context", "Set time/place only if provided or safely generic."),
            ("conflict", "Turning point", "Show the main event or decisive change."),
            ("lesson", "Consequence", "Close with consequence or lesson."),
        ]),
        scene_templates_5=_template([
            ("setup", "Historical context", "Set the world around the event."),
            ("hook", "Main figure/event", "Name the figure or event if provided."),
            ("conflict", "Turning point", "Show conflict or decisive moment."),
            ("proof", "Result", "Explain what changed."),
            ("lesson", "Consequence/lesson", "Close with historical meaning."),
        ]),
        image_style="vintage photography, sepia tone, classic oil painting, cinematic historical recreation",
        camera_style="epic wide shot, archival framing, careful close-up",
        motion_style="slow dramatic movement, film grain optional, no fake labels",
        transition_style="fade, archival cut, map-like transition if supported",
        voice_style="epic strong narration, slight reverb if supported",
        music_style="epic orchestral, drums, solemn ambience",
        subtitle_style="classic yellow or white lower-third",
        logo_policy="brand logo only at ending if provided",
        pacing_policy="give context before action; never outrun facts",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.16},
        fact_policy="Do not invent dates, names, events, or quotes. Mark insufficient factual input as dramatized.",
    ),
    "ugc_affiliate": VideoProductProfile(
        profile_id="ugc_affiliate",
        menu_label="Video Affiliate / UGC bán hàng",
        product_goal="Create raw, realistic, user-generated-style TikTok/Reels sales video that feels like a normal user sharing a real experience.",
        script_formula="Problem -> Solution -> Personal experience -> CTA",
        system_prompt=(
            "Write a short, natural, conversational sales script. Use everyday words, light slang, "
            "emotional reactions, and authentic UGC tone. Avoid corporate ad language."
        ),
        required_inputs=("product_info_or_product_image",),
        optional_assets=("product_reference", "character_reference", "existing_video", "logo", "music_audio"),
        scene_templates_3=_template([
            ("hook", "Pain point / relatable hook", "Show a familiar pain point in a casual first-person way."),
            ("solution", "Product as solution", "Use the product naturally and show the personal experience."),
            ("CTA", "Result and CTA", "Show the result and close with a simple action."),
        ]),
        scene_templates_5=_template([
            ("hook", "Relatable hook", "Start like a real user talking to camera."),
            ("problem", "Problem", "Show the pain point quickly."),
            ("product_reveal", "Product reveal", "Bring in the product as the practical solution."),
            ("proof", "Personal proof", "Show a result, reaction, or use moment."),
            ("CTA", "CTA", "Ask the viewer to try, click, or save."),
        ]),
        image_style="smartphone footage, vertical video, eye-level angle, selfie style, casual lighting, realistic raw aesthetic",
        camera_style="handheld smartphone, eye-level, selfie angle, quick casual movement",
        motion_style="natural handheld, quick cuts, casual demonstration",
        transition_style="hard cut, fast cut, pop or swoosh transition if SFX exists",
        voice_style="natural excited UGC voice, slightly fast, energetic, speed 1.1x to 1.2x if supported",
        music_style="viral TikTok/Reels upbeat background at very low volume",
        subtitle_style="large popup captions, high contrast yellow/black or white/red, punchy keywords",
        logo_policy="logo only at CTA or subtle watermark if user provided it",
        pacing_policy="fast, 2-3 seconds per shot, hook in first 2 seconds",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.08},
        sfx_policy="use short pop, swoosh, ting, click sounds at transitions if SFX assets exist; otherwise text cue only",
    ),
    "real_estate_fpv": VideoProductProfile(
        profile_id="real_estate_fpv",
        menu_label="Video bất động sản / địa điểm / FPV tour",
        product_goal="Create smooth property, location, travel, hotel, restaurant, or showroom tour.",
        script_formula="Location -> key specs -> experience -> value -> contact/CTA",
        system_prompt=(
            "Write concise narration for a premium property or location tour. Use fewer words and leave space "
            "for viewers to enjoy the visuals."
        ),
        required_inputs=("property_or_location_description",),
        optional_assets=("scene_background", "property_images", "map_location_note", "logo", "music_audio"),
        scene_templates_3=_template([
            ("hook", "Exterior/location establishing", "Show the exterior or surrounding location."),
            ("proof", "Interior/highlight walkthrough", "Move through the best room or highlight."),
            ("CTA", "Value/contact CTA", "Close with value, contact, or booking cue."),
        ]),
        scene_templates_5=_template([
            ("hook", "Location intro", "Show where the property/place is."),
            ("setup", "Exterior/front view", "Establish frontage, entrance, or context."),
            ("proof", "Main interior", "Walk through the most important interior."),
            ("solution", "Amenities/highlights", "Show amenities or standout details."),
            ("CTA", "Price/value/contact CTA", "Close with key value and action."),
        ]),
        image_style="architectural photography, ultra-wide angle, bright sunlight, luxurious interior, clean realistic composition",
        camera_style="FPV drone motion, smooth fly-through, pan, dolly forward, wide establishing shot",
        motion_style="smooth fly-through, drone fly-forward, pan left/right, slow reveal",
        transition_style="fade in, fade out, smooth crossfade",
        voice_style="calm premium real estate narrator, mature, confident, slow",
        music_style="luxury lounge, soft house, premium ambient background",
        subtitle_style="minimal lower-third/title block, not huge center captions",
        logo_policy="subtle real estate or venue logo at ending",
        pacing_policy="slow premium movement; give rooms time to breathe",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.16},
        overlay_policy="use title blocks at corner for area, location, price, or highlight specs if supported",
    ),
    "fashion_lookbook": VideoProductProfile(
        profile_id="fashion_lookbook",
        menu_label="Video thời trang / lookbook",
        product_goal="Create stylish, aesthetic, beat-driven fashion showcase.",
        script_formula="Minimal keywords: Hook keyword -> collection/style keyword -> highlight -> CTA",
        system_prompt="Create a visual-first fashion video plan with short stylish keywords instead of long narration.",
        required_inputs=("fashion_item_or_style_idea",),
        optional_assets=("character_reference", "product_reference", "style_reference", "music_audio", "logo"),
        scene_templates_3=_template([
            ("hook", "Outfit hook", "Open with the strongest outfit pose."),
            ("proof", "Detail/fabric/style close-up", "Show texture, accessory, or styling detail."),
            ("CTA", "Full look and CTA", "Reveal the full look and close with keyword/CTA."),
        ]),
        scene_templates_5=_template([
            ("hook", "Brand/style hook", "Set the collection mood."),
            ("setup", "Look 1", "Show the first full look."),
            ("proof", "Detail close-up", "Show fabric, accessory, or cut."),
            ("solution", "Look 2 / pose change", "Show a second pose or style variation."),
            ("CTA", "CTA / sale keyword", "End with brand/sale keyword or final pose."),
        ]),
        image_style="editorial fashion photography, dynamic pose, aesthetic lighting, clean composition, high-fashion mood",
        camera_style="quick fashion cuts, close-up fabric details, full-body pose, runway-like movement",
        motion_style="short 1-2 second clips, pose change, fabric movement, walk-in, turn-around",
        transition_style="beat cut, flash cut, glitch text if supported",
        voice_style="usually no voice, or one very short hook only",
        music_style="strong beat, EDM, tech, phonk, fashion runway music",
        subtitle_style="short keyword flashes, not full sentence captions",
        logo_policy="brand logo at final pose or corner watermark",
        pacing_policy="cut to music beat; very fast aesthetic shots",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "voice_volume": 0.0, "music_volume": 0.24},
        postprocess_policy="beat-sync captions and quick keyword flashes; no long narration unless requested",
    ),
    "food_asmr": VideoProductProfile(
        profile_id="food_asmr",
        menu_label="Video ẩm thực / ASMR",
        product_goal="Create appetizing food and beverage video focused on texture, taste, macro visuals, and sound cues.",
        script_formula="Sensory hook -> ingredient/texture -> taste moment -> craving/CTA",
        system_prompt="Write a short food/ASMR video plan using sensory words: crispy, juicy, creamy, smoky, fresh, sizzling, crunchy.",
        required_inputs=("dish_drink_name_or_food_image",),
        optional_assets=("product_reference", "object_reference", "logo", "music_audio", "sfx_audio"),
        scene_templates_3=_template([
            ("hook", "Food beauty hook", "Show the most appetizing macro hero shot."),
            ("proof", "Texture/action close-up", "Show pour, cut, sizzle, crunch, or steam."),
            ("CTA", "Taste reaction / CTA", "Create craving and close with action."),
        ]),
        scene_templates_5=_template([
            ("hook", "Ingredient/food hook", "Introduce the food with appetite appeal."),
            ("setup", "Preparation action", "Show prep movement."),
            ("proof", "Sizzle/pour/macro texture", "Focus on texture and sound cue."),
            ("solution", "Bite/taste moment", "Show taste or reaction moment."),
            ("CTA", "Craving/CTA", "Close with craving phrase and action."),
        ]),
        image_style="macro shot, extreme close-up, steam rising, shallow depth of field, vibrant 4k food photography",
        camera_style="macro close-up, slow push-in, top-down preparation shot, side close-up",
        motion_style="slow motion pour, cheese pull, steam, cutting, sizzling, bite moment",
        transition_style="sharp cut synced with chop/click/sizzle cue",
        voice_style="ASMR whisper or fun food reviewer voice",
        music_style="very low-volume cozy beat or no music if ASMR SFX dominates",
        subtitle_style="short tasty words, popup but not too crowded",
        logo_policy="restaurant/product logo at ending if provided",
        pacing_policy="texture-first pacing, give macro actions time to land",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.08},
        sfx_policy="sizzle, crunch, chop, pour, pop, bite sound cues if SFX assets exist; otherwise write SFX cue into scene card only",
    ),
    "lofi_audio_visualizer": VideoProductProfile(
        profile_id="lofi_audio_visualizer",
        menu_label="Video nhạc chill / lofi / audio visualizer",
        product_goal="Create loopable chill music visualizer, lyrics video, or ambient long-form background.",
        script_formula="Mood -> optional lyric lines -> repeating chorus/hook; or visual loop + music mood only",
        system_prompt="Create a calm loopable visual concept for lofi/chill music. Keep motion subtle and seamless.",
        required_inputs=("mood_music_idea_or_lyrics_audio",),
        optional_assets=("music_audio", "lyrics_text", "style_reference", "character_reference", "scene_background"),
        scene_templates_3=_template([
            ("hook", "Establish mood visual", "Create the main cozy loop mood."),
            ("setup", "Loop variation / lyric hook", "Add one subtle visual or lyric variation."),
            ("ending", "Return to seamless loop", "Resolve back to the initial loop state."),
        ]),
        scene_templates_5=_template([
            ("hook", "Intro atmosphere", "Establish room/weather/mood."),
            ("setup", "Verse visual", "Subtle visual movement for verse."),
            ("proof", "Hook/chorus visual", "Slightly richer movement for hook."),
            ("lesson", "Bridge ambience", "Calm bridge with ambience detail."),
            ("ending", "Seamless return loop", "Return to loop start state."),
        ]),
        image_style="looping animation, cozy room, rainy window, night city, soft neon, warm lamp, calm atmosphere",
        camera_style="static or very slow camera, gentle parallax, minimal movement",
        motion_style="seamless loop, rain, blinking lights, slow smoke, gentle character idle animation",
        transition_style="no hard transitions, loop/crossfade",
        voice_style="usually no voice unless narration/lyrics requested",
        music_style="lofi, chillhop, soft piano, ambient, rainy mood",
        subtitle_style="karaoke lyrics style if lyrics exist; otherwise minimal title",
        logo_policy="small title/logo only; keep visual calm",
        pacing_policy="can reuse short 6-second loop for longer output if supported by local FFmpeg",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "voice_volume": 0.0, "music_volume": 0.28},
        postprocess_policy="support loop extension by FFmpeg when source clip is short; do not invoke renderer repeatedly unless required",
    ),
    "cinematic_trailer": VideoProductProfile(
        profile_id="cinematic_trailer",
        menu_label="Phim ngắn AI / cinematic trailer",
        product_goal="Create premium cinematic short film or trailer with strong atmosphere and consistent characters.",
        script_formula="Setup -> incident -> escalation -> climax glimpse -> title/CTA",
        system_prompt=(
            "Write a cinematic trailer storyboard with professional scene beats. Each scene must have strong visual stakes, "
            "consistent characters, dramatic lighting, and clear transitions."
        ),
        required_inputs=("film_idea_or_story_prompt",),
        optional_assets=("character_reference", "scene_background", "style_reference", "voice_audio", "music_audio", "logo"),
        scene_templates_3=_template([
            ("setup", "World/setup", "Establish the world and mood."),
            ("conflict", "Conflict/escalation", "Show the incident or rising stakes."),
            ("ending", "Climax glimpse/title CTA", "End with title-card energy or CTA."),
        ]),
        scene_templates_5=_template([
            ("setup", "Establishing world", "Set the world and atmosphere."),
            ("hook", "Main character/objective", "Show the character or object of desire."),
            ("conflict", "Incident/conflict", "Trigger the dramatic problem."),
            ("proof", "Escalation/climax glimpse", "Show a powerful visual glimpse."),
            ("CTA", "Title/ending CTA", "Close with trailer title or action."),
        ]),
        image_style="cinematic movie still, anamorphic look, dramatic shadows, volumetric lighting, high-detail realistic scene, teal-orange color tone",
        camera_style="wide establishing shot, dramatic close-up, slow dolly, handheld tension, low angle hero shot",
        motion_style="slow cinematic movement, tension build, action glimpse, atmospheric particles",
        transition_style="fade to black, hard impact cut, cinematic crossfade",
        voice_style="deep trailer narrator or expressive voice acting",
        music_style="epic orchestral, dark cinematic trailer, drums, riser, impact hits",
        subtitle_style="minimal cinematic subtitle lower third; optional title card",
        logo_policy="title card or logo only at ending",
        pacing_policy="dramatic pacing with impact beats and short powerful narration",
        postprocess_defaults={**DEFAULT_POSTPROCESS, "music_volume": 0.18},
        postprocess_policy="optional letterbox 21:9 look, cinematic color grading, impact SFX cues if available",
        character_consistency="strongly prefer reference image/image-to-video if available; otherwise enforce detailed character description in StoryBible",
    ),
}


VIDEO_MENU_PROFILE_MAP = {
    "video_trend": "auto",
    "video_idea": "auto",
    "storyboard_prompt": "storytelling",
    "prompt_library": "storytelling",
    "video_ai_real": "auto",
    "script_image_video": "auto",
    "frame_video_local": "auto",
    "self_shot_scene_change": "ugc_affiliate",
    "multi_scene_film": "cinematic_trailer",
    "video_reference": "storytelling",
}


def list_video_profiles(public_only: bool = True) -> list[VideoProductProfile]:
    items = list(VIDEO_PRODUCT_PROFILES.values())
    if public_only:
        return [profile for profile in items if profile.public_enabled]
    return items


def get_video_profile(profile_id: str) -> VideoProductProfile:
    key = str(profile_id or "").strip().lower()
    if key in {"", "auto"}:
        key = "storytelling"
    if key not in VIDEO_PRODUCT_PROFILES:
        raise KeyError(f"unknown_video_profile:{profile_id}")
    return VIDEO_PRODUCT_PROFILES[key]


def recommend_profile_id(user_text: str = "", *, product_id: str = "", assets: Any = None) -> str:
    text = f"{product_id} {user_text}".lower()
    if any(word in text for word in ("ugc", "selfie", "người dùng", "nguoi dung", "affiliate", "tiktok shop", "chốt đơn")):
        return "ugc_affiliate"
    if any(word in text for word in ("bất động sản", "bat dong san", "real estate", "nhà phố", "can ho", "căn hộ", "fpv", "tour", "khách sạn", "hotel", "showroom", "restaurant")):
        return "real_estate_fpv"
    if any(word in text for word in ("fashion", "lookbook", "thời trang", "tho trang", "outfit", "runway", "váy", "vay", "áo", "ao")):
        return "fashion_lookbook"
    if any(word in text for word in ("food", "asmr", "ẩm thực", "am thuc", "món ăn", "mon an", "đồ uống", "do uong", "sizzle", "crunch", "restaurant")):
        return "food_asmr"
    if any(word in text for word in ("lofi", "chill", "visualizer", "lyrics", "karaoke", "rainy", "nhạc chill", "nhac chill")):
        return "lofi_audio_visualizer"
    if any(word in text for word in ("trailer", "phim ngắn", "phim ngan", "cinematic", "movie", "teaser")):
        return "cinematic_trailer"
    if any(word in text for word in ("review", "san pham", "sản phẩm", "cta", "ban hang", "bán hàng")):
        return "product_review"
    if any(word in text for word in ("tin tuc", "tin tức", "news", "5w1h")):
        return "news"
    if any(word in text for word in ("quote", "triet ly", "triết lý", "dao ly", "đạo lý")):
        return "philosophy_quotes"
    if any(word in text for word in ("hoc", "học", "kien thuc", "kiến thức", "eli5", "tutorial")):
        return "educational"
    if any(word in text for word in ("lich su", "lịch sử", "history", "historical")):
        return "history"
    if assets is not None:
        summary = str(assets).lower()
        if "music" in summary:
            return "lofi_audio_visualizer"
        if "product" in summary:
            return "product_review"
    return "storytelling"


def recommend_video_profile(user_text: str = "", assets: Any = None) -> VideoProductProfile:
    return get_video_profile(recommend_profile_id(user_text, assets=assets))


def resolve_profile_for_menu_product(product_id: str, *, user_text: str = "") -> VideoProductProfile:
    mapped = VIDEO_MENU_PROFILE_MAP.get(str(product_id or "").strip(), "auto")
    if mapped == "auto":
        mapped = recommend_profile_id(user_text, product_id=product_id)
    return get_video_profile(mapped)


def profile_template(profile: VideoProductProfile | str, scene_count: int) -> tuple[dict[str, str], ...]:
    item = get_video_profile(profile) if isinstance(profile, str) else profile
    return item.scene_templates_5 if int(scene_count or 3) >= 5 else item.scene_templates_3


def get_scene_template(profile_id: str, scene_count: int) -> tuple[dict[str, str], ...]:
    return profile_template(profile_id, scene_count)


def build_profile_prompt_context(profile_id: str) -> str:
    profile = get_video_profile(profile_id)
    return "\n".join([
        f"Profile: {profile.profile_id}",
        f"Goal: {profile.product_goal}",
        f"Formula: {profile.script_formula}",
        f"System: {profile.system_prompt}",
        f"Image style: {profile.image_style}",
        f"Camera: {profile.camera_style}",
        f"Motion: {profile.motion_style}",
        f"Transition: {profile.transition_style}",
        f"Voice: {profile.voice_style}",
        f"Music: {profile.music_style}",
        f"Subtitle: {profile.subtitle_style}",
        f"Logo: {profile.logo_policy}",
        f"Pacing: {profile.pacing_policy}",
        f"SFX: {profile.sfx_policy or 'text cue only when no SFX asset exists'}",
        f"Overlay: {profile.overlay_policy or 'postprocess overlay only when available'}",
        f"Postprocess: {profile.postprocess_policy or 'standard FFmpeg final MP4 add-ons'}",
    ])


def profile_contains_protected_style_names(profile: VideoProductProfile) -> list[str]:
    haystack = " ".join(str(value) for value in asdict(profile).values()).lower()
    return [term for term in PROTECTED_STYLE_TERMS if term in haystack]


def validate_profile_style_safety() -> dict[str, list[str]]:
    return {
        profile.profile_id: profile_contains_protected_style_names(profile)
        for profile in list_video_profiles()
        if profile_contains_protected_style_names(profile)
    }


def profiles_summary() -> str:
    lines = ["Video product profiles"]
    for profile in list_video_profiles():
        lines.append(f"- {profile.profile_id}: {profile.menu_label} | {profile.script_formula}")
    return "\n".join(lines)
