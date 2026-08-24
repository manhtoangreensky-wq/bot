from pathlib import Path

from services import video_uiflow3


BOT_SOURCE = Path(__file__).resolve().parents[1] / "bot.py"


def _block(source: str, start: str, end: str) -> str:
    return source[source.index(start):source.index(end, source.index(start))]


def test_scene_plan_auto_acknowledges_and_falls_back_after_bounded_gemini_wait() -> None:
    source = BOT_SOURCE.read_text(encoding="utf-8")

    sync_helper = _block(
        source,
        "def video_uiflow3_ai_enhance_scenes(state: dict) -> dict:",
        "async def video_uiflow3_ai_enhance_scenes_bounded",
    )
    assert "types.HttpOptions(" in sync_helper
    assert "timeout=VIDEO_UIFLOW3_SCENE_PLAN_AI_HTTP_TIMEOUT_MS" in sync_helper

    bounded_helper = _block(
        source,
        "async def video_uiflow3_ai_enhance_scenes_bounded(state: dict) -> dict:",
        "def video_film_fallback_script",
    )
    assert "asyncio.wait_for(" in bounded_helper
    assert "asyncio.to_thread(video_uiflow3_ai_enhance_scenes, state)" in bounded_helper
    assert "video_uiflow3.suggest_scene_plan_from_vault(state)" in bounded_helper
    assert "return fallback" in bounded_helper

    callback = _block(
        source,
        'elif action == "scene_plan_auto":',
        'elif action == "plan_scene" and values:',
    )
    acknowledgement = 'await query.answer("Đang phác thảo kế hoạch cảnh...")'
    bounded_call = "state = await video_uiflow3_ai_enhance_scenes_bounded(state)"
    assert acknowledgement in callback
    assert bounded_call in callback
    assert callback.index(acknowledgement) < callback.index(bounded_call)

    handler = _block(
        source,
        "async def handle_video_uiflow3_callback",
        "async def handle_video_uiflow3_pending_text",
    )
    assert "callback_answered = False" in handler
    assert (
        "if not callback_answered:\n"
        "        await video_uiflow3_ack_without_interrupting_flow(query)"
    ) in handler


def _video_ai_real_state() -> dict:
    state = video_uiflow3.new_state("video_ai_real", draft_id="scene-plan-context")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_scene_count_preference(state, 2)
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=12,
        seconds_per_scene=6,
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Mai rang hạt cà phê rồi rót thành phẩm trong hai cảnh.",
        profile_id="product_review",
        approved_brief={
            "title": "Cà phê thủ công cao cấp",
            "selected_context_prompt": "Xưởng rang gạch đỏ nối sang quầy cà phê sáng ấm.",
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state["source"]["assets"] = [{
        "asset_id": "source_01",
        "asset_type": "image",
        "role": "source",
        "metadata": {"caption": "Mai mặc tạp dề xanh ngọc"},
    }]
    state["bible"]["characters"] = [{
        "character_id": "char_01",
        "display_name": "Mai",
        "wardrobe": "tạp dề xanh ngọc",
        "voice_id": "voice_mai",
    }]
    state["audio"].update({
        "dialogue_segments": [{
            "scene_id": "scene_01",
            "speaker_id": "char_01",
            "text": "Hạt cà phê được rang vừa tới.",
        }],
        "music_scope": "whole_video",
        "music_plan": {"track_id": "acoustic-cafe"},
        "subtitle_mode": "auto",
    })
    state["creative_controls"] = {
        "visual_style": {"enabled": True, "value": "chân thật điện ảnh"},
        "camera_motion": {"enabled": True, "value": "dolly-in chậm"},
    }
    state["preservation_requirements"] = {
        "character_identity": {"enabled": True, "value": "giữ nguyên khuôn mặt Mai"},
    }
    return video_uiflow3.normalize_state(state)


def test_video_ai_real_scene_prompt_uses_short_duration_and_existing_media_context() -> None:
    state = _video_ai_real_state()

    prompt = video_uiflow3.build_scene_plan_ai_prompt(state, state["scenes"])

    assert "Mỗi cảnh dài đúng 6 giây" in prompt
    assert "chỉ một hành động" in prompt
    assert "không viết thành kịch bản dài" in prompt
    assert "Ảnh tham chiếu: 1" in prompt
    assert "Mai" in prompt
    assert "giọng đã gán" in prompt
    assert "Ngữ cảnh triển khai đã chọn" in prompt
    assert "Phong cách đã chọn" in prompt
    assert "Yêu cầu giữ nguyên" in prompt
    assert "Lời thoại/phụ đề" in prompt
    assert "Nhạc: whole_video" in prompt


def test_scene_prompt_distinguishes_trend_script_and_long_form_products() -> None:
    products = {
        "video_trend": "Bám dữ liệu trend đã phân tích",
        "script_image_video": "Bám sát kịch bản đã khóa",
        "multi_scene_film": "Giữ mạch liên tục của series và tập",
    }
    for product_id, expected in products.items():
        state = video_uiflow3.new_state(product_id, draft_id=f"prompt-{product_id}")
        state["content"]["original_intent"] = "Nội dung đầu vào đã được xác nhận."
        state["content"]["approved_brief"] = {"title": "Nội dung đã khóa"}
        state["series"]["goal"] = "Mạch phim xuyên suốt"
        state["episode"]["content"] = {
            "original_intent": "Nội dung tập hiện tại",
            "candidate_ready": True,
            "locked": True,
            "revision": 1,
        }
        prompt = video_uiflow3.build_scene_plan_ai_prompt(
            state,
            [{"scene_index": 1, "duration_target": 8}],
        )
        assert expected in prompt


def test_scene_plan_uses_local_prompt_vault_when_gemini_is_unavailable() -> None:
    state = _video_ai_real_state()
    full_intent = (
        "Cà phê thủ công cao cấp | giới thiệu quy trình trong 2 cảnh | "
        "Mai, cảnh 1 rang hạt trong xưởng gạch đỏ; "
        "cảnh 2 rót cà phê vào ly tại quầy sáng ấm"
    )
    state["content"]["original_intent"] = full_intent
    state["content"]["approved_brief"]["title"] = full_intent

    planned = video_uiflow3.suggest_scene_plan_from_vault(state)

    assert all(scene["planning_source"] == "local_prompt_vault" for scene in planned["scenes"])
    assert all("6 giây" in scene["main_action"] for scene in planned["scenes"])
    assert "rang hạt" in planned["scenes"][0]["main_action"].lower()
    assert "rót cà phê" in planned["scenes"][1]["main_action"].lower()
    assert all(full_intent not in scene["semantic_beat"] for scene in planned["scenes"])
    assert video_uiflow3.scene_plan_complete(planned) is True

    replanned = video_uiflow3.suggest_scene_plan_from_vault(planned)

    assert "rang hạt" in replanned["scenes"][0]["main_action"].lower()
    assert "rót cà phê" in replanned["scenes"][1]["main_action"].lower()
    assert all(full_intent not in scene["semantic_beat"] for scene in replanned["scenes"])


def test_local_prompt_vault_fallback_covers_trend_script_and_long_form() -> None:
    for product_id, count in (
        ("video_trend", 2),
        ("script_image_video", 5),
        ("multi_scene_film", 3),
    ):
        state = video_uiflow3.new_state(product_id, draft_id=f"vault-{product_id}")
        scene_actions = [f"Hành động riêng của cảnh {index}" for index in range(1, count + 1)]
        marked_content = "; ".join(
            f"Cảnh {index}: {action}"
            for index, action in enumerate(scene_actions, 1)
        )
        if product_id == "multi_scene_film":
            state = video_uiflow3.set_series_goal(state, "Mạch phim xuyên suốt")
            state = video_uiflow3.set_episode_content(state, marked_content)
            state = video_uiflow3.lock_episode_content(state)
        state = video_uiflow3.set_format(
            state,
            ratio="9:16",
            target_duration_seconds=count * int(state["format"]["seconds_per_scene"]),
        )
        state = video_uiflow3.set_content_candidate(
            state,
            source="manual",
            original_intent=marked_content,
            approved_brief={"title": marked_content},
        )
        state = video_uiflow3.lock_content(state)
        state = video_uiflow3.confirm_scene_count(state, count)

        planned = video_uiflow3.suggest_scene_plan_from_vault(state)

        assert all(scene["planning_source"] == "local_prompt_vault" for scene in planned["scenes"])
        assert all(
            action.lower() in scene["main_action"].lower()
            for action, scene in zip(scene_actions, planned["scenes"])
        )
        assert len({scene["semantic_beat"] for scene in planned["scenes"]}) == count
        assert video_uiflow3.scene_plan_complete(planned) is True


def test_script_local_vault_uses_the_existing_source_parser() -> None:
    script = (
        "Mai mở cửa xưởng rang. "
        "Cô cân từng mẻ hạt. "
        "Lửa rang đổi màu hạt. "
        "Mai kiểm tra mùi thơm. "
        "Cô rót cà phê và mời khách."
    )
    expected_actions = (
        "mở cửa xưởng rang",
        "cân từng mẻ hạt",
        "lửa rang đổi màu hạt",
        "kiểm tra mùi thơm",
        "rót cà phê và mời khách",
    )
    state = video_uiflow3.new_state("script_image_video", draft_id="vault-script-source")
    state = video_uiflow3.set_source_metadata(
        state,
        source_kind="approved_script",
        source_text=script,
    )
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=40)
    state = video_uiflow3.set_content_candidate(
        state,
        source="approved_script",
        original_intent="Kịch bản đã nhận",
        profile_id="storytelling_life",
        approved_brief={"title": "Một ngày ở xưởng cà phê"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.confirm_scene_count(state, 5)

    planned = video_uiflow3.suggest_scene_plan_from_vault(state)

    assert all(
        action in scene["main_action"].lower()
        for action, scene in zip(expected_actions, planned["scenes"])
    )
    assert len({scene["semantic_beat"] for scene in planned["scenes"]}) == 5


def test_local_vault_uses_distinct_profile_beats_for_every_video_product() -> None:
    profile_by_product = {
        "video_trend": "social_creator_trend",
        "video_ai_real": "product_review_demo",
        "script_image_video": "storytelling_life",
        "frame_video_local": "product_3d_showcase",
        "self_shot_scene_change": "affiliate_ugc",
        "storyboard_prompt": "short_film_trailer",
        "multi_scene_film": "short_film_trailer",
    }
    for product_id, profile_id in profile_by_product.items():
        state = video_uiflow3.new_state(product_id, draft_id=f"vault-profile-{product_id}")
        if product_id == "multi_scene_film":
            state = video_uiflow3.set_series_goal(state, "Hành trình xây dựng quán cà phê")
            state = video_uiflow3.set_episode_content(state, "Tập mở đầu giới thiệu Mai và xưởng rang.")
            state = video_uiflow3.lock_episode_content(state)
        state = video_uiflow3.set_format(
            state,
            ratio="9:16",
            target_duration_seconds=5 * int(state["format"]["seconds_per_scene"]),
        )
        state = video_uiflow3.set_content_candidate(
            state,
            source="manual",
            original_intent="Giới thiệu hành trình cà phê thủ công.",
            profile_id=profile_id,
            approved_brief={"title": "Hành trình cà phê"},
        )
        state = video_uiflow3.lock_content(state)
        state = video_uiflow3.confirm_scene_count(state, 5)

        planned = video_uiflow3.suggest_scene_plan_from_vault(state)

        assert all(scene["planning_source"] == "local_prompt_vault" for scene in planned["scenes"])
        assert len({scene["semantic_beat"] for scene in planned["scenes"]}) == 5
        assert video_uiflow3.scene_plan_complete(planned) is True


def test_scene_plan_screen_uses_real_newlines() -> None:
    source = BOT_SOURCE.read_text(encoding="utf-8")
    screen = _block(
        source,
        'if step == "scene_plan" and not view:',
        'if step == "branding" and view in {',
    )

    assert 'return "\\n".join(lines)' in screen
    assert 'return "\\\\n".join(lines)' not in screen
