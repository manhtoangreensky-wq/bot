"""Film Series and Multi-Episode Long Video Planning Engine.

Provides structured multi-episode decomposition, character bible continuity,
scene graph compilation, and integration with the RouteEngine Multiscene Pipeline.
Zero transport dependencies, zero provider side-effects during planning.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from services.video_semantic_scene_planner import (
    canonical_scene_count,
    SCENE_SECONDS,
)
from services.video_scene_continuity import (
    build_continuity_contract,
    inherit_previous_completion,
    validate_continuity,
)
from services.video_scene_transition_planner import plan_transitions, apply_transitions


MIN_EPISODES = 1
MAX_EPISODES = 5
DEFAULT_SCENES_PER_EPISODE = 4
MIN_SCENES_PER_EPISODE = 2
MAX_SCENES_PER_EPISODE = 8


def _clean_str(value: Any, max_len: int = 1000) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    return cleaned[:max_len]


def _canonical_json_str(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _sha256_hash(data: Any) -> str:
    return hashlib.sha256(_canonical_json_str(data).encode("utf-8")).hexdigest()


def canonical_episode_count(value: Any) -> int:
    try:
        val = int(value)
        return max(MIN_EPISODES, min(MAX_EPISODES, val))
    except (TypeError, ValueError):
        return 1


def canonical_scenes_per_episode(value: Any) -> int:
    try:
        val = int(value)
        return max(MIN_SCENES_PER_EPISODE, min(MAX_SCENES_PER_EPISODE, val))
    except (TypeError, ValueError):
        return DEFAULT_SCENES_PER_EPISODE


def generate_default_character_bible(
    concept: str,
    *,
    genre: str = "drama",
) -> list[dict[str, Any]]:
    """Generate default character bible for a series concept if not provided."""
    clean_concept = _clean_str(concept, 200)
    return [
        {
            "character_id": "protagonist_01",
            "name": "Nhân vật chính",
            "role": "protagonist",
            "archetype": "hero",
            "visual_description": f"Gương mặt sáng, trang phục đặc trưng phù hợp bối cảnh {clean_concept}, phong thái tự tin, ánh mắt kiên định",
            "costume_lock": "trang phục nhất quán xuyên suốt các tập",
            "personality_traits": ["quyết đoán", "thấu cảm", "kiên trì"],
        },
        {
            "character_id": "supporting_01",
            "name": "Nhân vật đồng hành",
            "role": "supporting",
            "archetype": "mentor_or_ally",
            "visual_description": f"Trang phục tương phản nhẹ với nhân vật chính, phong cách điềm tĩnh, hỗ trợ mạch truyện",
            "costume_lock": "trang phục đồng bộ theo bối cảnh",
            "personality_traits": ["trầm tĩnh", "thấu hiểu"],
        },
    ]


def plan_film_series(
    *,
    title: str,
    concept: str,
    episodes_count: int = 1,
    scenes_per_episode: int = DEFAULT_SCENES_PER_EPISODE,
    genre: str = "drama",
    visual_style: str = "cinematic 4k, realistic lighting, highly detailed",
    aspect_ratio: str = "9:16",
    character_bible: list[dict[str, Any]] | None = None,
    language: str = "vi",
) -> dict[str, Any]:
    """Create a fully compiled Film Series Plan across N episodes.
    
    Guarantees deterministic scene graph decomposition, character bible continuity,
    audio/voiceover arcs, and zero provider side effects.
    """
    clean_title = _clean_str(title, 200) or "AI Film Series"
    clean_concept = _clean_str(concept, 2000) or "Một câu chuyện lôi cuốn được kể qua nhiều tập phim"
    ep_count = canonical_episode_count(episodes_count)
    scenes_per_ep = canonical_scenes_per_episode(scenes_per_episode)
    ratio = _clean_str(aspect_ratio, 20) or "9:16"
    style = _clean_str(visual_style, 400) or "cinematic, consistent lighting, 4k"

    characters = [
        dict(item) for item in (character_bible or generate_default_character_bible(clean_concept, genre=genre))
        if isinstance(item, Mapping)
    ]
    if not characters:
        characters = generate_default_character_bible(clean_concept, genre=genre)

    # Build overarching continuity contract
    char_desc_list = [f"{c.get('name')}: {c.get('visual_description')}" for c in characters]
    continuity = build_continuity_contract(
        subject=clean_title,
        profile_id=genre,
        requirements={
            "visual_style": style,
            "character_bible": characters,
            "preserve_constraints": [
                *char_desc_list,
                f"Phong cách hình ảnh: {style}",
                f"Tỷ lệ khung hình: {ratio}",
            ],
        },
        assets={"characters": characters},
    )

    episodes: list[dict[str, Any]] = []
    all_scenes_flat: list[dict[str, Any]] = []
    global_scene_idx = 1

    episode_arc_roles = [
        ("Mở đầu & Xung đột", "Giới thiệu bối cảnh, nhân vật và khởi đầu biến cố chính"),
        ("Phát triển & Thử thách", "Nhân vật đối mặt khó khăn, mâu thuẫn leo thang"),
        ("Bước ngoặt & Cao trào", "Mâu thuẫn lên đỉnh điểm, nhân vật buộc phải lựa chọn"),
        ("Hồi kết & Lắng đọng", "Giải quyết xung đột, bài học và mở ra tương lai"),
        ("Tập đặc biệt / Vĩ thanh", "Góc nhìn sâu hơn về số phận các nhân vật"),
    ]

    for ep_idx in range(1, ep_count + 1):
        arc_title, arc_desc = episode_arc_roles[min(ep_idx - 1, len(episode_arc_roles) - 1)]
        ep_title = f"{clean_title} - Tập {ep_idx}: {arc_title}" if ep_count > 1 else clean_title
        ep_synopsis = f"{arc_desc} trong mạch truyện '{clean_concept}'"

        ep_scenes: list[dict[str, Any]] = []
        previous_scene: dict[str, Any] | None = all_scenes_flat[-1] if all_scenes_flat else None

        for sc_idx in range(1, scenes_per_ep + 1):
            scene_id = f"ep{ep_idx}_sc{sc_idx}"
            
            # Determine dramatic phase within episode
            if sc_idx == 1:
                phase_role = "hook_opening"
                phase_desc = f"Mở đầu tập {ep_idx}: Thu hút sự chú ý, thiết lập bối cảnh cho {clean_title}"
            elif sc_idx == scenes_per_ep:
                phase_role = "cliffhanger_or_resolution"
                phase_desc = f"Kết thúc tập {ep_idx}: Điểm nhấn đọng lại hoặc nút thắt chuyển tiếp"
            elif sc_idx == 2:
                phase_role = "conflict_introduction"
                phase_desc = f"Phát triển tình huống tập {ep_idx}: Xuất hiện thử thách đối với nhân vật chính"
            else:
                phase_role = f"escalation_beat_{sc_idx}"
                phase_desc = f"Diễn biến tập {ep_idx}: Mạch truyện tăng tiến, nhân vật hành động"

            # Primary character for this scene
            acting_char = characters[(sc_idx - 1) % len(characters)]
            char_name = acting_char.get("name", "Nhân vật")
            char_visual = acting_char.get("visual_description", "")

            start_state = (
                previous_scene.get("completion_state")
                if previous_scene
                else f"{char_name} xuất hiện trong bối cảnh ban đầu của {clean_concept}"
            )
            action = f"{char_name} thực hiện hành động: {phase_desc}"
            completion = f"Hành động của {char_name} tại cảnh {sc_idx} tập {ep_idx} hoàn thành ổn định"

            prompt_parts = [
                f"Scene {global_scene_idx} (Episode {ep_idx}, Scene {sc_idx}): {clean_title}",
                f"Style: {style}",
                f"Subject: {char_name} ({char_visual})",
                f"Action: {action}",
                f"Atmosphere: cinematic mood, consistent lighting, high quality, no watermark",
            ]
            provider_prompt = " | ".join(prompt_parts)

            image_prompt_parts = [
                f"Keyframe Episode {ep_idx} Scene {sc_idx}",
                f"Style: {style}, aspect ratio {ratio}",
                f"Subject: {char_name} ({char_visual})",
                f"Framing: cinematic medium shot, detailed facial expression, clear background",
            ]
            image_prompt = " | ".join(image_prompt_parts)

            voice_text = (
                f"Tập {ep_idx}, cảnh {sc_idx}: {char_name} tiếp tục hành trình trong {clean_title}."
                if language == "vi"
                else f"Episode {ep_idx}, Scene {sc_idx}: The story unfolds in {clean_title}."
            )

            scene_dict = {
                "scene_id": scene_id,
                "global_scene_index": global_scene_idx,
                "episode_index": ep_idx,
                "scene_index": sc_idx,
                "scene_role": phase_role,
                "main_idea": phase_desc,
                "subject": char_name,
                "characters": [acting_char],
                "start_state": start_state,
                "primary_action": action,
                "completion_state": completion,
                "provider_prompt": provider_prompt,
                "image_prompt": image_prompt,
                "voice_text": voice_text,
                "duration_seconds": SCENE_SECONDS,
                "aspect_ratio": ratio,
                "visual_style": style,
                "transition_in": "dissolve" if sc_idx > 1 else "fade_in",
                "transition_out": "dissolve" if sc_idx < scenes_per_ep else ("fade_out" if ep_idx == ep_count else "cut"),
                "preserve_constraints": [
                    char_visual,
                    f"Phong cách: {style}",
                ],
                "semantic_complete": True,
            }

            if previous_scene:
                scene_dict = inherit_previous_completion(scene_dict, previous_scene)

            ep_scenes.append(scene_dict)
            all_scenes_flat.append(scene_dict)
            previous_scene = scene_dict
            global_scene_idx += 1

        # Plan transitions for episode scenes
        transitions = plan_transitions(ep_scenes, profile_id=genre, preferred_style="dissolve")
        apply_transitions(ep_scenes, transitions)

        episodes.append({
            "episode_index": ep_idx,
            "episode_title": ep_title,
            "synopsis": ep_synopsis,
            "scene_count": len(ep_scenes),
            "duration_seconds": len(ep_scenes) * SCENE_SECONDS,
            "scenes": ep_scenes,
            "transitions": transitions,
        })

    total_scenes = len(all_scenes_flat)
    total_duration = total_scenes * SCENE_SECONDS

    # Validate overall continuity
    continuity_report = validate_continuity(all_scenes_flat, continuity)

    # Calculate commercial quote
    base_unit_xu = 150
    estimated_xu = total_scenes * base_unit_xu

    manifest = {
        "series_title": clean_title,
        "concept": clean_concept,
        "genre": genre,
        "visual_style": style,
        "aspect_ratio": ratio,
        "episodes_count": ep_count,
        "scenes_per_episode": scenes_per_ep,
        "total_scenes": total_scenes,
        "total_duration_seconds": total_duration,
        "character_bible": characters,
        "continuity_contract": continuity,
        "continuity_validation": continuity_report,
        "episodes": episodes,
        "all_scenes": all_scenes_flat,
        "quote": {
            "total_scenes": total_scenes,
            "seconds_per_scene": SCENE_SECONDS,
            "total_duration_seconds": total_duration,
            "unit_price_xu": base_unit_xu,
            "estimated_xu": estimated_xu,
            "final_charge_xu": estimated_xu,
        },
        "side_effects": {
            "provider_calls": 0,
            "wallet_mutations": 0,
            "jobs_created": 0,
        },
    }
    manifest["series_hash"] = _sha256_hash(manifest)
    return manifest


def convert_series_to_scene_specs(
    series_manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Convert compiled series scenes into format expected by multiscene pipeline."""
    all_scenes = list(series_manifest.get("all_scenes") or [])
    specs: list[dict[str, Any]] = []
    for sc in all_scenes:
        specs.append({
            "scene_id": str(sc.get("scene_id") or f"scene_{sc.get('global_scene_index', 1)}"),
            "prompt": str(sc.get("provider_prompt") or sc.get("main_idea") or ""),
            "duration": float(sc.get("duration_seconds") or SCENE_SECONDS),
            "voiceover_text": str(sc.get("voice_text") or ""),
            "transition": str(sc.get("transition_out") or "dissolve"),
            "aspect_ratio": str(sc.get("aspect_ratio") or "9:16"),
            "order": int(sc.get("global_scene_index") or 1),
            "characters": list(sc.get("characters") or []),
            "visual_style": str(sc.get("visual_style") or ""),
        })
    return specs


from services.multiscene_video_pipeline import SceneSpec, MultisceneManifest, plan_multiscene_video


def build_multiscene_manifest_for_series(
    series_manifest: Mapping[str, Any],
    *,
    job_id: str,
    user_id: str = "user_0",
    workspace_dir: str = "",
    output_profile: str = "9:16",
    music_path: str = "",
    logo_path: str = "",
    watermark_text: str = "",
    voice_audio_path: str = "",
) -> MultisceneManifest:
    """Bridge compiled series plan into MultisceneManifest for execution."""
    all_scenes = list(series_manifest.get("all_scenes") or [])
    scene_specs = [
        {
            "scene_id": int(sc.get("global_scene_index") or idx),
            "title": f"Episode {sc.get('episode_index', 1)} Scene {sc.get('scene_index', 1)}",
            "visual_prompt": str(sc.get("image_prompt") or sc.get("main_idea") or ""),
            "video_prompt": str(sc.get("provider_prompt") or sc.get("main_idea") or ""),
            "narration_text": str(sc.get("voice_text") or ""),
            "target_duration_sec": float(sc.get("duration_seconds") or SCENE_SECONDS),
            "aspect_ratio": str(sc.get("aspect_ratio") or output_profile or "9:16"),
            "transition": str(sc.get("transition_out") or "dissolve"),
        }
        for idx, sc in enumerate(all_scenes, start=1)
    ]
    scene_order = [int(sc["scene_id"]) for sc in scene_specs]
    total_dur = sum(float(sc["target_duration_sec"]) for sc in scene_specs)

    return MultisceneManifest(
        job_id=str(job_id),
        user_id=str(user_id),
        workspace_dir=str(workspace_dir or f"/tmp/series_{job_id}"),
        scene_specs=scene_specs,
        scene_order=scene_order,
        required_scene_indexes=list(range(1, len(scene_specs) + 1)),
        expected_duration_sec=total_dur,
        transition_plan=[str(sc.get("transition") or "dissolve") for sc in scene_specs],
        bgm_audio_path=music_path or None,
        logo_path=logo_path or None,
        voice_audio_path=voice_audio_path or None,
    )
