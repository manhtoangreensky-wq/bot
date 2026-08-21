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

    planned = video_uiflow3.suggest_scene_plan_from_vault(state)

    assert all(scene["planning_source"] == "local_prompt_vault" for scene in planned["scenes"])
    assert all("6 giây" in scene["main_action"] for scene in planned["scenes"])
    assert video_uiflow3.scene_plan_complete(planned) is True


def test_local_prompt_vault_fallback_covers_trend_script_and_long_form() -> None:
    for product_id, count in (
        ("video_trend", 2),
        ("script_image_video", 5),
        ("multi_scene_film", 3),
    ):
        state = video_uiflow3.new_state(product_id, draft_id=f"vault-{product_id}")
        if product_id == "multi_scene_film":
            state = video_uiflow3.set_series_goal(state, "Mạch phim xuyên suốt")
        state = video_uiflow3.set_format(
            state,
            ratio="9:16",
            target_duration_seconds=count * int(state["format"]["seconds_per_scene"]),
        )
        state = video_uiflow3.set_content_candidate(
            state,
            source="manual",
            original_intent="Nội dung sản phẩm đã khóa.",
            approved_brief={"title": "Nội dung sản phẩm đã khóa"},
        )
        state = video_uiflow3.lock_content(state)
        state = video_uiflow3.confirm_scene_count(state, count)

        planned = video_uiflow3.suggest_scene_plan_from_vault(state)

        assert all(scene["planning_source"] == "local_prompt_vault" for scene in planned["scenes"])
        assert all("nội dung đã khóa" in scene["main_action"].lower() for scene in planned["scenes"])
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
