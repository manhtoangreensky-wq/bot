import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class FakeMessage:
    chat_id = 918200
    message_id = 1

    def __init__(self, text=""):
        self.text = text
        self.sent = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P018B")
        self.data = data
        self.message = FakeMessage()
        self.answered = False
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _press(user_id: int, data: str):
    query = FakeQuery(user_id, data)
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query, bot.get_video_session(user_id)


def _seed(user_id: int, topic="câu chuyện đạo lý về lòng tin"):
    bot.clear_video_session(user_id)
    session = bot.task3d_session_step(user_id, "profile_select", product_id="multi_scene_film", return_to="menu|main_video")
    session = bot.video_b14_set_profile(user_id, session, "philosophy_quotes")
    session = bot.task3d_session_step(user_id, "b14_creative_controls", topic=topic, provider_called=False, xu_charged=0)
    return session


def test_p0_18b_audit_report_exists():
    report = Path("docs/reports/P0_18B_LIVE_VIDEO_UX_CALLBACK_AUDIT.md")
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "Callback Matrix" in text
    assert "Backstack Matrix" in text
    assert "videodub|language|..." in text
    assert "Not touched: PayOS" in text


def test_creative_color_and_emotion_are_distinct():
    user_id = 918201
    session = _seed(user_id)
    session = bot.video_b14_set_creative_controls(
        user_id,
        session,
        color_palette=bot.video_b14_creative_choice_value("color_palette", "teal_white"),
    )
    session = bot.video_b14_set_creative_controls(
        user_id,
        session,
        emotion_tone=bot.video_b14_creative_choice_value("emotion_tone", "trust"),
    )
    controls = bot.video_b14_creative_controls_from_session(session)
    assert controls["color_palette"] != controls["emotion_tone"]
    assert "xanh ngọc" in controls["color_palette"]
    assert "tin tưởng" in controls["emotion_tone"]
    bot.clear_video_session(user_id)


def test_emotion_does_not_write_color_palette():
    user_id = 918202
    session = _seed(user_id)
    before = bot.video_b14_creative_controls_from_session(session)["color_palette"]
    session = bot.video_b14_set_creative_controls(user_id, session, emotion_tone=bot.video_b14_creative_choice_value("emotion_tone", "curious"))
    controls = bot.video_b14_creative_controls_from_session(session)
    assert controls["color_palette"] == before
    assert "tò mò" in controls["emotion_tone"]
    bot.clear_video_session(user_id)


def test_color_does_not_write_emotion_tone():
    user_id = 918203
    session = _seed(user_id)
    before = bot.video_b14_creative_controls_from_session(session)["emotion_tone"]
    session = bot.video_b14_set_creative_controls(user_id, session, color_palette=bot.video_b14_creative_choice_value("color_palette", "warm_wood"))
    controls = bot.video_b14_creative_controls_from_session(session)
    assert controls["emotion_tone"] == before
    assert "vàng ấm" in controls["color_palette"]
    bot.clear_video_session(user_id)


def test_emotion_output_vietnamese_friendly():
    user_id = 918204
    session = _seed(user_id)
    text = bot.video_b14_creative_controls_text(session, user_id, "vi")
    assert "Cảm xúc là cảm giác người xem nhận được" in text
    assert "Deep, slow, reflective" not in text
    bot.clear_video_session(user_id)


def test_fast_style_does_not_duplicate_color_emotion():
    user_id = 918205
    session = _seed(user_id)
    session = bot.video_b14_set_creative_controls(user_id, session, color_palette="tự nhiên sáng", emotion_tone="tin tưởng")
    session = bot.video_b14_set_creative_controls(user_id, session, visual_style=bot.video_b14_creative_choice_value("visual_style", "cinematic"))
    controls = bot.video_b14_creative_controls_from_session(session)
    assert controls["color_palette"] == "tự nhiên sáng"
    assert controls["emotion_tone"] == "tin tưởng"
    assert controls["visual_style"] not in {controls["color_palette"], controls["emotion_tone"]}
    bot.clear_video_session(user_id)


def test_storyboard_prompt_from_creative_no_error():
    user_id = 918206
    _seed(user_id)
    query, session = _press(user_id, "vproduct|b14_creative_done")
    assert "Có lỗi khi xử lý lệnh" not in query.edits[-1]["text"]
    assert "Storyboard + prompt" in query.edits[-1]["text"]
    assert session["current_step"] == "storyboard_preview"
    bot.clear_video_session(user_id)


def test_storyboard_builds_if_missing():
    user_id = 918207
    _seed(user_id)
    query, session = _press(user_id, "vproduct|b14_prompt_video_text")
    assert "Prompt video" in query.edits[-1]["text"]
    assert (session.get("draft") or {}).get("b14_storyboard_plan")
    bot.clear_video_session(user_id)


def test_storyboard_missing_session_recover():
    user_id = 918208
    bot.clear_video_session(user_id)
    query, _session = _press(user_id, "vproduct|b14_creative_done")
    assert "Phiên tạo video bị thiếu dữ liệu" in query.edits[-1]["text"]
    assert "Có lỗi khi xử lý lệnh" not in query.edits[-1]["text"]


def test_storyboard_buttons_have_handlers_and_back_returns_creative():
    callbacks = set(_callbacks(bot.video_b14_storyboard_keyboard("vi")))
    assert {
        "vproduct|storyboard_confirm",
        "vproduct|b14_prompt_image_text",
        "vproduct|b14_prompt_video_text",
        "vproduct|b14_export_pack",
        "vproduct|b14_creative_screen",
        "vproduct|b14_addons",
        "vproduct|asset_intro",
    }.issubset(callbacks)


def test_addons_back_to_storyboard():
    user_id = 918209
    _seed(user_id)
    _press(user_id, "vproduct|b14_creative_done")
    query, session = _press(user_id, "vproduct|storyboard_confirm")
    assert session["current_step"] == "b14_scene_mode"
    assert "Chọn cách dựng video" in query.edits[-1]["text"]
    query, session = _press(user_id, "vproduct|b14_scene_mode|multi")
    assert session["current_step"] == "b14_addons"
    assert "Voice / nhạc / phụ đề / logo" in query.edits[-1]["text"]
    assert "vproduct|b14_scene_mode_screen" in _callbacks(query.edits[-1]["reply_markup"])
    query, session = _press(user_id, "vproduct|b14_scene_mode_screen")
    assert session["current_step"] == "b14_scene_mode"
    assert "Chọn cách dựng video" in query.edits[-1]["text"]
    bot.clear_video_session(user_id)


def test_voice_music_subtitle_dub_logo_sfx_back_to_addons():
    user_id = 918210
    _seed(user_id, "review máy lọc nước")
    _press(user_id, "vproduct|b14_creative_done")
    _press(user_id, "vproduct|storyboard_confirm")
    for data in (
        "vproduct|b14_addon_voice",
        "vproduct|b14_addon_music",
        "vproduct|b14_addon_subtitle",
        "vproduct|b14_addon_dub",
        "vproduct|b14_addon_logo",
        "vproduct|b14_addon_sfx",
    ):
        query, _session = _press(user_id, data)
        assert "vproduct|b14_addons" in _callbacks(query.edits[-1]["reply_markup"])
        query, session = _press(user_id, "vproduct|b14_addons")
        assert session["current_step"] == "b14_addons"
        assert "Voice / nhạc / phụ đề / logo" in query.edits[-1]["text"]
    bot.clear_video_session(user_id)


def test_video_voice_default_female_applies_and_returns():
    user_id = 918211
    _seed(user_id, "video review son môi")
    _press(user_id, "vproduct|b14_creative_done")
    _press(user_id, "vproduct|storyboard_confirm")
    query, session = _press(user_id, "vproduct|b14_voice_source|default_female")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert session["current_step"] == "b14_voice"
    assert plan["voice_enabled"] is True
    assert plan["voice_source"] == "default_female"
    assert "Giọng đọc cho video" in query.edits[-1]["text"]
    bot.clear_video_session(user_id)


def test_video_voice_default_male_applies_and_returns():
    user_id = 918212
    _seed(user_id, "video review tai nghe")
    _press(user_id, "vproduct|b14_creative_done")
    _press(user_id, "vproduct|storyboard_confirm")
    query, session = _press(user_id, "vproduct|b14_voice_source|default_male")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert session["current_step"] == "b14_voice"
    assert plan["voice_enabled"] is True
    assert plan["voice_source"] == "default_male"
    assert "Giọng đọc cho video" in query.edits[-1]["text"]
    bot.clear_video_session(user_id)


def test_video_voice_custom_not_ready_has_fallback():
    user_id = 918213
    _seed(user_id)
    _press(user_id, "vproduct|b14_creative_done")
    _press(user_id, "vproduct|storyboard_confirm")
    query, _session = _press(user_id, "vproduct|b14_voice_source|custom")
    text = query.edits[-1]["text"]
    labels = _labels(query.edits[-1]["reply_markup"])
    assert "tạm khóa để kiểm soát chất lượng" in text
    assert "👩 Giọng nữ mặc định" in labels
    assert "👨 Giọng nam mặc định" in labels
    bot.clear_video_session(user_id)


def test_video_music_default_applies_and_returns():
    user_id = 918214
    _seed(user_id)
    _press(user_id, "vproduct|b14_creative_done")
    _press(user_id, "vproduct|storyboard_confirm")
    query, session = _press(user_id, "vproduct|b14_music_source|default")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert session["current_step"] == "b14_music"
    assert plan["music_enabled"] is True
    assert plan["music_source"] == "default"
    assert "Nhạc nền" in query.edits[-1]["text"]
    bot.clear_video_session(user_id)


def test_video_subtitle_translate_language_applies():
    user_id = 918215
    _seed(user_id)
    _press(user_id, "vproduct|b14_creative_done")
    _press(user_id, "vproduct|storyboard_confirm")
    query, session = _press(user_id, "vproduct|b14_subtitle_translate")
    assert session["current_step"] == "b14_subtitle_language"
    assert "Chọn ngôn ngữ dịch phụ đề" in query.edits[-1]["text"]
    query, session = _press(user_id, "vproduct|b14_subtitle_lang|English")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert session["current_step"] == "b14_subtitle"
    assert plan["subtitle_enabled"] is True
    assert plan["subtitle_source"] == "translated"
    assert plan["subtitle_target_language"] == "English"
    assert "đã ghi nhận yêu cầu dịch phụ đề" in query.edits[-1]["text"]
    bot.clear_video_session(user_id)


def test_dub_language_applies_to_addon_plan():
    user_id = 918216
    _seed(user_id)
    _press(user_id, "vproduct|b14_creative_done")
    _press(user_id, "vproduct|storyboard_confirm")
    query, session = _press(user_id, "vproduct|b14_dub_lang|English")
    plan = bot.video_b14_addon_plan_from_session(session)
    assert session["current_step"] == "b14_dub"
    assert plan["dub_enabled"] is True
    assert plan["dub_target_language"] == "English"
    assert "Lồng tiếng cho video" in query.edits[-1]["text"]
    bot.clear_video_session(user_id)


def test_uploaded_video_subtitle_language_no_false_ready(monkeypatch):
    calls = {"translate": 0}

    async def fail_translate(*_args, **_kwargs):
        calls["translate"] += 1
        raise AssertionError("language callback must not translate before final confirm")

    async def fake_edit(query, text, reply_markup=None, parse_mode="HTML"):
        return SimpleNamespace(text=str(text), reply_markup=reply_markup, parse_mode=parse_mode)

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    monkeypatch.setattr(bot, "video_dubbing_translate_current_subtitle_to_output", fail_translate)

    uid = 918217
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "language",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_file_id="tg-video",
        video_file_id="tg-video",
    )
    query = FakeQuery(uid, "videodub|language|English")
    result = asyncio.run(bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert calls["translate"] == 0
    assert state["step"] == "confirm"
    assert state["target_language"] == "English"
    assert "Dịch phụ đề video" in result.text
    assert "✅ Xác nhận dịch" in _labels(result.reply_markup)
    bot.clear_video_dubbing_pending(uid)


def test_tool_test_live_video_ux_regression_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=918218), message=message)
    asyncio.run(bot.cmd_tool_test_live_video_ux_regression(update, SimpleNamespace(args=["--no-charge"])))
    assert message.sent
    assert "TOAN AAS" in message.sent[-1]["text"]


def test_tool_test_live_video_ux_regression_no_charge(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=918219), message=message)
    asyncio.run(bot.cmd_tool_test_live_video_ux_regression(update, SimpleNamespace(args=["--no-charge"])))
    text = message.sent[-1]["text"]
    assert "PASS" in text
    assert "no_xu_charge" in text
    assert "No provider call. No Xu charge." in text


def test_tool_test_live_video_ux_regression_covers_backstack():
    report = bot.video_b14_live_ux_regression_report(918220)
    assert report["ok"] is True
    assert report["checks"]["addons_backstack"] is True
    assert report["checks"]["no_provider_call"] is True
    assert report["checks"]["no_xu_charge"] is True
    bot.clear_video_session(918220)
