from __future__ import annotations

import bot
from services import video_scene3_flow, video_tail9, video_uiflow3


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _tail(product: str = "video_ai_real") -> dict:
    state = video_tail9.new_state(product_type=product, session_id=f"ui-{product}")
    state["scene_content"] = [
        {
            "scene_index": 1,
            "dialogue_or_voiceover": "Xin chào, đây là nội dung tiếng Việt của cảnh đầu tiên.",
        },
        {
            "scene_index": 2,
            "dialogue_or_voiceover": "Cảnh tiếp theo giữ nguyên mạch kể và nhân vật.",
        },
    ]
    return video_tail9.normalize_state(state)


def test_tail9_subtitle_and_dubbing_store_language_source_and_editable_script() -> None:
    state = bot.video_tail9_set_addon_option(_tail(), "subtitles", "auto")
    subtitle = bot.video_tail9_addon_value(state, "subtitles")
    assert state["audio_config"]["subtitles"] is True
    assert subtitle["source"] == "auto"
    assert subtitle["target_language"] == ""
    assert bot.video_tail9_addon_script_info(state, "subtitles")["detected_language"] == "vi"

    state = bot.video_tail9_set_addon_language(state, "subtitles", "en")
    subtitle = bot.video_tail9_addon_value(state, "subtitles")
    assert subtitle["source"] == "translated"
    assert subtitle["translation"] is True
    assert subtitle["target_language"] == "en"

    state = bot.video_tail9_set_dubbing_script_source(state, "subtitles")
    dubbing = bot.video_tail9_addon_value(state, "dubbing")
    assert state["audio_config"]["dubbing"] is True
    assert dubbing["script_source"] == "subtitles"
    assert bot.video_tail9_addon_script_info(state, "dubbing")["source"] == "subtitles"

    state = bot.video_tail9_set_addon_language(state, "dubbing", "ja")
    state = bot.video_tail9_set_addon_script_text(
        state,
        "dubbing",
        "Nội dung lồng tiếng do người dùng sửa và giữ nguyên văn.",
    )
    dubbing = bot.video_tail9_addon_value(state, "dubbing")
    assert dubbing["target_language"] == "ja"
    assert dubbing["script_source"] == "manual"
    assert dubbing["dialogue_text"].startswith("Nội dung lồng tiếng")
    assert "Nội dung lồng tiếng đã sửa" in bot.video_tail9_addon_detail_text(state, "dubbing")


def test_tail9_subtitle_dubbing_buttons_have_exact_local_back_stack() -> None:
    state = _tail()
    subtitle_callbacks = _callbacks(bot.video_tail9_addon_detail_keyboard(state, "subtitles"))
    dubbing_callbacks = _callbacks(bot.video_tail9_addon_detail_keyboard(state, "dubbing"))

    assert "video_tail|addon|language|subtitles" in subtitle_callbacks
    assert "video_tail|addon|script|subtitles" in subtitle_callbacks
    assert "video_tail|addon|edit_script|subtitles" in subtitle_callbacks
    assert "video_tail|addon|source|dubbing|subtitles" in dubbing_callbacks
    assert "video_tail|addon|source|dubbing|script" in dubbing_callbacks
    assert "video_tail|addon|language|dubbing" in dubbing_callbacks

    for key in ("subtitles", "dubbing"):
        language_callbacks = _callbacks(bot.video_tail9_addon_language_keyboard(key))
        preview_callbacks = _callbacks(bot.video_tail9_addon_script_preview_keyboard(key))
        input_callbacks = _callbacks(bot.video_tail9_addon_input_keyboard(key))
        expected_back = f"video_tail|addon|item|{key}"
        assert expected_back in language_callbacks
        assert expected_back in preview_callbacks
        assert expected_back in input_callbacks
        assert all(len(callback.encode("utf-8")) <= 64 for callback in [
            *language_callbacks,
            *preview_callbacks,
            *input_callbacks,
        ])


def test_tail9_reuses_public_subdub_language_and_default_voice_choices() -> None:
    public_language_labels = [
        button.text
        for row in bot.subtitle_plus_dub_translation_language_keyboard("vi").inline_keyboard
        for button in row
        if str(button.callback_data or "").startswith("videodub|language|")
        or str(button.callback_data or "") == "videodub|language_custom"
    ]
    tail_language_labels = [label for _code, label in bot.video_tail9_subdub_language_options()]
    assert tail_language_labels == public_language_labels

    public_voice_labels = [
        button.text
        for row in bot.subtitle_plus_dub_voice_keyboard("vi", {}).inline_keyboard
        for button in row
        if str(button.callback_data or "") in {
            "videodub|voice|default_female",
            "videodub|voice|default_male",
        }
    ]
    tail_voice_labels = [label for _option, label in bot.video_tail9_subdub_default_voice_options()]
    assert tail_voice_labels == public_voice_labels


def test_shared_scene3_auto_suggestions_only_target_remaining_products(monkeypatch) -> None:
    monkeypatch.setattr(bot.random, "choice", lambda choices: choices[-1])
    for product in (
        "script_image_video",
        "video_trend",
        bot.video_selfshot2.PRODUCT_ID,
    ):
        state = video_scene3_flow.default_state(
            product_type=product,
            subject="Nội dung mẫu cho gợi ý nhanh",
            aspect_ratio="9:16",
        )
        state["source_product_id"] = product
        state["scene_count"] = 3
        assert bot.video_scene3_shared_auto_suggest_enabled(state) is True
        creative_keyboard = bot.video_scene3_creative_keyboard(state)
        requirements_keyboard = bot.video_scene3_requirements_keyboard(state)
        assert "vprofile|creative_auto" in _callbacks(creative_keyboard)
        assert "vprofile|creative_auto_clear" in _callbacks(creative_keyboard)
        assert "vprofile|req_auto" in _callbacks(requirements_keyboard)
        assert all(len(row) == 2 for row in creative_keyboard.inline_keyboard)
        assert all(len(row) == 2 for row in requirements_keyboard.inline_keyboard)

        suggested = bot.video_scene3_apply_auto_suggestions(
            state,
            group="creative_controls",
            fields=tuple(video_scene3_flow.CREATIVE_CONTROLS),
            selection_key="creative_auto_selection",
            revision_key="creative_auto_revision",
        )
        assert suggested["creative_auto_selection"] == 5
        assert suggested["creative_auto_revision"] == 1
        assert all(
            entry.get("enabled") and str(entry.get("value") or "").strip()
            for entry in suggested["creative_controls"].values()
        )
        assert suggested["provider_called"] is False
        assert suggested["job_created"] is False
        assert suggested["wallet_mutations"] == 0

    for protected in ("video_ai_real", "storyboard_prompt"):
        state = video_scene3_flow.default_state(product_type=protected, subject="Khóa", aspect_ratio="9:16")
        state["source_product_id"] = protected
        assert bot.video_scene3_shared_auto_suggest_enabled(state) is False
        assert "vprofile|creative_auto" not in _callbacks(bot.video_scene3_creative_keyboard(state))
        assert "vprofile|creative_auto_clear" not in _callbacks(bot.video_scene3_creative_keyboard(state))
        assert "vprofile|req_auto" not in _callbacks(bot.video_scene3_requirements_keyboard(state))


def test_long_video_uses_quick_suggestions_without_changing_realistic_labels() -> None:
    long_state = video_uiflow3.new_state("multi_scene_film", draft_id="long-style-ui")
    long_state["parent_product"] = "multi_scene_film"
    _text, long_creative = bot.video_ai_real_pilot_creative_payload(long_state)
    _text, long_requirements = bot.video_ai_real_pilot_requirements_payload(long_state)
    assert "✨ Tự động gợi ý nhanh" in _labels(long_creative)
    assert "✨ Tự động gợi ý nhanh" in _labels(long_requirements)
    assert "vid3|quick_build" not in _callbacks(long_creative)

    realistic = video_uiflow3.new_state("video_ai_real", draft_id="realistic-lock")
    realistic["parent_product"] = "video_ai_real"
    _text, realistic_creative = bot.video_ai_real_pilot_creative_payload(realistic)
    assert "✨ Tự động gợi ý nhanh" in _labels(realistic_creative)
    assert "vid3|pilot_creative_auto" in _callbacks(realistic_creative)
    assert "vid3|quick_build" not in _callbacks(realistic_creative)
