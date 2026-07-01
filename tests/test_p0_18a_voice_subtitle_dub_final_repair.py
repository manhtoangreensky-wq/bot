import inspect
from pathlib import Path

import bot
from services import minimax_voice_adapter as voice_adapter
from services import provider_gate
from services import subtitle_dub_pipeline as subtitle_pipeline


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _storyboard():
    return {
        "scene_cards": [
            {"scene_index": 1, "narration_line": "Mở đầu giới thiệu sản phẩm.", "start": 0, "end": 6},
            {"scene_index": 2, "narration_line": "Nêu lợi ích chính dễ hiểu.", "start": 6, "end": 12},
            {"scene_index": 3, "narration_line": "Chốt thông điệp và kêu gọi hành động.", "start": 12, "end": 18},
        ]
    }


def _fake_tts(text, voice_id="", output_path="", **_kwargs):
    payload = f"FAKE-AUDIO:{voice_id}:{text}".encode("utf-8")
    if output_path:
        Path(output_path).write_bytes(payload)
    return payload


def _fake_mux(video_path, audio_path, output_path, subtitle_path=""):
    del subtitle_path
    Path(output_path).write_bytes(b"FAKE-MP4" + Path(video_path).read_bytes() + Path(audio_path).read_bytes()[:32])
    return output_path


def _fake_mux_fail(*_args, **_kwargs):
    raise RuntimeError("fake mux failed")


def test_p0_18a_audit_report_exists_and_lists_compatible_callbacks():
    report = Path("docs/reports/P0_18A_VOICE_SUBTITLE_DUB_AUDIT.md")
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "vproduct|b14_voice_source|default_male" in text
    assert "videodub|type|subtitle_plus_dub" in text
    assert "services/dubbing_pipeline.py" in text
    assert "PayOS/wallet/payment" in text


def test_provider_gate_blocks_public_interactive_voice_call():
    decision = provider_gate.evaluate_provider_gate(context=provider_gate.INTERACTIVE_UI, configured=True)
    assert decision.allowed is False
    assert decision.reason == "interactive_plan_only"
    assert "chưa trừ Xu" in decision.public_message


def test_provider_gate_allows_worker_confirmed_job():
    decision = provider_gate.evaluate_provider_gate(
        context=provider_gate.WORKER_CONFIRMED_JOB,
        configured=True,
        final_confirmed=True,
    )
    assert decision.allowed is True
    assert decision.may_charge is True


def test_provider_gate_allows_admin_test_no_charge():
    decision = provider_gate.evaluate_provider_gate(
        context=provider_gate.ADMIN_TEST,
        is_admin=True,
        configured=True,
        fake_mode=True,
    )
    assert decision.allowed is True
    assert decision.no_charge is True
    assert "không trừ Xu" in decision.public_message


def test_provider_gate_no_provider_name_public():
    decision = provider_gate.evaluate_provider_gate(
        context=provider_gate.INTERACTIVE_UI,
        configured=True,
        provider_name="MiniMax",
    )
    assert not provider_gate.public_copy_has_technical_terms(decision.public_message)
    assert "MiniMax" not in decision.public_message


def test_minimax_adapter_rejects_missing_provider_voice_id():
    result = voice_adapter.resolve_provider_voice_id(voice_source="saved", profile={"id": 7, "display_name": "Giọng A", "provider_voice_id": ""})
    assert result.ok is False
    assert result.reason == "missing_provider_voice_id"
    assert "Voice này chưa sẵn sàng" in result.public_message


def test_minimax_adapter_uses_provider_voice_id_not_local_id():
    profile = {"id": 55, "display_name": "Giọng bán hàng", "provider_voice_id": "real-provider-voice-55"}
    result = voice_adapter.resolve_provider_voice_id(voice_source="saved", profile=profile)
    assert result.ok is True
    assert result.provider_voice_id == "real-provider-voice-55"
    assert result.provider_voice_id != str(profile["id"])


def test_minimax_adapter_validates_nonzero_audio(tmp_path):
    output = tmp_path / "voice.mp3"
    artifact = voice_adapter.synthesize_text_to_audio(
        text="Xin chào",
        provider_voice_id="voice-ready-1",
        output_path=output,
        tts_func=_fake_tts,
    )
    assert artifact.ok is True
    assert artifact.size_bytes > 0
    assert voice_adapter.validate_audio_artifact(output).ok is True


def test_minimax_adapter_safe_error_no_raw_provider(tmp_path):
    def bad_tts(*_args, **_kwargs):
        raise RuntimeError("provider API endpoint token leaked")

    artifact = voice_adapter.synthesize_text_to_audio(
        text="Xin chào",
        provider_voice_id="voice-ready-1",
        output_path=tmp_path / "bad.mp3",
        tts_func=bad_tts,
    )
    assert artifact.ok is False
    assert not provider_gate.public_copy_has_technical_terms(artifact.public_message)


def test_video_voice_default_male_provider_id_ready():
    result = bot.video_b14_voice_resolution("default_male")
    assert result.ok is True
    assert result.provider_voice_id
    assert result.provider_voice_id != "default_male"


def test_video_voice_default_female_provider_id_ready():
    result = bot.video_b14_voice_resolution("default_female")
    assert result.ok is True
    assert result.provider_voice_id
    assert result.provider_voice_id != "default_female"


def test_saved_voice_lists_friendly_names(monkeypatch):
    monkeypatch.setattr(bot, "user_voice_profile_rows", lambda *_args, **_kwargs: [
        {"id": 11, "display_name": "Voice bán hàng", "provider_voice_id": "voice-11", "status": "active"},
    ])
    monkeypatch.setattr(bot, "voice_profile_can_generate_tts", lambda profile: bool(profile.get("provider_voice_id")))
    labels = _labels(bot.video_b14_voice_select_keyboard(123, "vi"))
    callbacks = _callbacks(bot.video_b14_voice_select_keyboard(123, "vi"))
    assert any("Voice bán hàng" in label for label in labels)
    assert "vproduct|b14_voice_saved_pick|11" in callbacks


def test_uploaded_voice_missing_provider_id_safe_message():
    result = voice_adapter.resolve_provider_voice_id(voice_source="uploaded", uploaded_profile={"id": 9, "provider_voice_id": ""})
    assert result.ok is False
    assert "Voice này chưa sẵn sàng" in result.public_message


def test_voice_done_returns_addons():
    callbacks = _callbacks(bot.video_b14_voice_keyboard("vi"))
    assert "vproduct|b14_voice_done" in callbacks
    assert "vproduct|b14_addons" in callbacks


def test_voice_uses_manual_narration_first():
    session = {"draft": {"b14_addon_plan": {"narration_text": "Cảnh 1: đọc thủ công."}, "b14_storyboard_plan": _storyboard()}}
    result = bot.video_b14_narration_source(session)
    assert result["source"] == "manual"
    assert "đọc thủ công" in result["text"]


def test_voice_uses_storyboard_narration_if_no_manual():
    session = {"draft": {"b14_storyboard_plan": _storyboard()}}
    result = bot.video_b14_narration_source(session)
    assert result["source"] == "storyboard"
    assert result["text"].count("Cảnh") == 3


def test_voice_blocks_empty_narration(tmp_path):
    artifact = voice_adapter.synthesize_text_to_audio(
        text="",
        provider_voice_id="voice-ready-1",
        output_path=tmp_path / "empty.mp3",
        tts_func=_fake_tts,
    )
    assert artifact.ok is False
    assert "lời đọc" in artifact.public_message


def test_multiscene_narration_has_scene_lines():
    session = {"draft": {"b14_storyboard_plan": _storyboard()}}
    text = bot.video_b14_narration_from_storyboard(session)
    assert "Cảnh 1:" in text
    assert "Cảnh 2:" in text
    assert "Cảnh 3:" in text


def test_public_voice_preview_no_silent_charge():
    decision = provider_gate.evaluate_provider_gate(
        context=provider_gate.PREVIEW_CONFIRMED,
        configured=True,
        public_ready=True,
        preview_confirmed=False,
        preview_no_charge=False,
    )
    assert decision.allowed is False
    assert "không trừ Xu âm thầm" in decision.public_message


def test_public_voice_preview_limited_duration():
    source = inspect.getsource(bot.execute_subtitle_plus_dub_voice_preview)
    assert "15" in source
    assert "cap_voice_preview_audio_bytes" in source


def test_admin_voice_preview_no_charge():
    decision = provider_gate.evaluate_provider_gate(
        context=provider_gate.PREVIEW_CONFIRMED,
        is_admin=True,
        configured=True,
    )
    assert decision.allowed is True
    assert decision.no_charge is True


def test_preview_missing_provider_safe_message():
    decision = provider_gate.evaluate_provider_gate(
        context=provider_gate.PREVIEW_CONFIRMED,
        configured=False,
        public_ready=False,
    )
    assert decision.allowed is False
    assert not provider_gate.public_copy_has_technical_terms(decision.public_message)


def test_subtitle_from_storyboard_generates_valid_srt():
    transcript = subtitle_pipeline.build_transcript_from_storyboard(_storyboard(), scene_duration=6)
    srt = subtitle_pipeline.generate_srt_from_transcript(transcript)
    assert len(transcript) == 3
    assert subtitle_pipeline.validate_srt(srt)


def test_subtitle_from_narration_generates_valid_srt():
    transcript = subtitle_pipeline.build_transcript_from_storyboard({}, narration_text="Dòng một\nDòng hai", scene_duration=5)
    srt = subtitle_pipeline.generate_srt_from_transcript(transcript)
    assert subtitle_pipeline.validate_srt(srt)
    assert "00:00:05,000" in srt


def test_uploaded_video_asr_transcript_to_srt():
    transcript = [{"start": 0, "end": 2, "text": "Lời thoại từ ASR"}, {"start": 2, "end": 4, "text": "Dòng tiếp theo"}]
    srt = subtitle_pipeline.generate_srt_from_transcript(transcript)
    assert subtitle_pipeline.validate_srt(srt)
    assert "Lời thoại từ ASR" in srt


def test_invalid_srt_rejected():
    assert subtitle_pipeline.validate_srt("1\nbad timestamp\nhello") is False


def test_subtitle_no_fake_success():
    srt = subtitle_pipeline.generate_srt_from_transcript([])
    assert srt == ""
    assert subtitle_pipeline.validate_srt(srt) is False


def test_translate_srt_preserves_timestamps():
    srt = subtitle_pipeline.generate_srt_from_transcript([{"start": 0, "end": 3, "text": "Xin chào"}])
    translated = subtitle_pipeline.translate_srt(srt, "English", translate_func=lambda text, lang: f"{lang}: {text}")
    assert "00:00:00,000 --> 00:00:03,000" in translated
    assert "English: Xin chào" in translated


def test_translate_subtitle_target_language_saved():
    session = {"draft": {"b14_profile_id": "product_review"}}
    updated = bot.video_b14_set_addon_plan(991801, session, subtitle_enabled=True, subtitle_source="translated", subtitle_target_language="English")
    plan = bot.video_b14_addon_plan_from_session(updated)
    assert plan["subtitle_target_language"] == "English"
    bot.clear_video_session(991801)


def test_translate_provider_error_safe_public():
    message = provider_gate.safe_public_error("provider API endpoint failed")
    assert not provider_gate.public_copy_has_technical_terms(message)


def test_dub_pipeline_creates_audio_artifact(tmp_path):
    transcript = subtitle_pipeline.build_transcript_from_storyboard(_storyboard())
    result = subtitle_pipeline.run_dub_pipeline(
        workspace_dir=str(tmp_path),
        transcript=transcript,
        provider_voice_id="voice-ready-1",
        tts_func=_fake_tts,
    )
    assert result.ok is True
    assert result.audio_path and Path(result.audio_path).stat().st_size > 0


def test_dub_pipeline_mux_success_returns_mp4(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"FAKE-SOURCE")
    transcript = subtitle_pipeline.build_transcript_from_storyboard(_storyboard())
    result = subtitle_pipeline.run_dub_pipeline(
        workspace_dir=str(tmp_path / "out"),
        source_video_path=str(video),
        transcript=transcript,
        provider_voice_id="voice-ready-1",
        tts_func=_fake_tts,
        mux_func=_fake_mux,
    )
    assert result.ok is True
    assert result.result_type == "mp4"
    assert Path(result.video_path).stat().st_size > 0


def test_dub_pipeline_mux_failure_returns_partial(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"FAKE-SOURCE")
    transcript = subtitle_pipeline.build_transcript_from_storyboard(_storyboard())
    result = subtitle_pipeline.run_dub_pipeline(
        workspace_dir=str(tmp_path / "out"),
        source_video_path=str(video),
        transcript=transcript,
        provider_voice_id="voice-ready-1",
        tts_func=_fake_tts,
        mux_func=_fake_mux_fail,
    )
    assert result.ok is True
    assert result.result_type == "partial"
    assert result.audio_path
    assert result.subtitle_path
    assert "Video chưa ghép được tự động" in result.public_message


def test_dub_pipeline_no_fake_mp4_success(tmp_path):
    transcript = subtitle_pipeline.build_transcript_from_storyboard(_storyboard())
    result = subtitle_pipeline.run_dub_pipeline(
        workspace_dir=str(tmp_path),
        source_video_path="",
        transcript=transcript,
        provider_voice_id="voice-ready-1",
        tts_func=_fake_tts,
    )
    assert result.ok is True
    assert result.result_type != "mp4"
    assert not result.video_path


def test_addon_plan_contains_voice_subtitle_dub():
    session = {"draft": {"b14_profile_id": "product_review"}}
    plan = bot.video_b14_addon_plan_from_session(session)
    for key in ("voice_provider_voice_id", "subtitle_target_language", "dub_enabled", "dub_source", "dub_target_language"):
        assert key in plan


def test_invoice_shows_voice_subtitle_dub_addons(monkeypatch):
    monkeypatch.setattr(bot, "get_user", lambda _uid: (9999, None, None))
    session = {
        "product_id": "multi_scene_film",
        "topic": "review sản phẩm",
        "draft": {
            "b14_profile_id": "product_review",
            "b14_quality_xu": 300,
            "b14_scene_count": 3,
            "b14_addon_plan": {
                **bot.video_b14_default_addon_plan("product_review"),
                "voice_enabled": True,
                "voice_source": "default_male",
                "voice_label": "Nam mặc định",
                "subtitle_enabled": True,
                "subtitle_source": "translated",
                "subtitle_target_language": "English",
                "dub_enabled": True,
                "dub_target_language": "English",
            },
        },
    }
    text = bot.video_b14_invoice_text(session, 991802, "vi")
    assert "Voice:" in text
    assert "Phụ đề:" in text
    assert "Lồng tiếng:" in text
    assert "English" in text


def test_final_confirm_calls_voice_subtitle_only_in_worker():
    source = inspect.getsource(bot.handle_video_product_callback)
    before_confirm = source.split('if action == "b14_confirm":', 1)[0]
    assert "synthesize_text_to_audio(" not in before_confirm
    assert "video_dubbing_tts_bytes(" not in before_confirm
    assert "confirm_video_project_invoice" in source.split('if action == "b14_confirm":', 1)[1]


def test_status_shows_voice_subtitle_stage():
    text = bot.video_b14_queue_status_text({
        "draft": {
            "b14_queue_job": {"id": 9},
            "b14_invoice": {"scene_count": 3, "duration_seconds": 18},
            "b14_addon_plan": {"voice_enabled": True, "subtitle_enabled": True, "dub_enabled": True},
        }
    }, None, 0, "vi")
    assert "Voice, lồng tiếng" in text
    assert "phụ đề" in text


def test_public_voice_studio_no_video_only_buttons():
    labels = _labels(bot.voice_vault_keyboard(0, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "Không voice" not in " ".join(labels)


def test_public_voice_studio_default_voice_asks_text():
    text = bot.video_voice_script_prompt_text({"duration_seconds": 12}, "Nam mặc định", "vi")
    assert "gửi nội dung/kịch bản cần đọc" in text
    assert "chưa render voice và chưa trừ Xu" in text


def test_public_voice_studio_saved_voice_routes():
    callbacks = _callbacks(bot.voice_tts_choice_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "music_quick|showroom|voice_profiles" in callbacks
    assert "send_paid_saved_voice_tts_result" in source


def test_tool_test_voice_gate_admin_only():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("tool_test_voice_gate", cmd_tool_test_voice_gate)' in source
    assert "p0_18a_admin_guard(update, \"p0_18a_voice_gate\")" in source


def test_tool_test_minimax_adapter_fake_no_provider():
    source = inspect.getsource(bot.cmd_tool_test_minimax_adapter)
    assert "--fake" in source
    assert "p0_18a_fake_tts" in source
    assert "Provider call: <code>NO</code>" in source


def test_tool_test_subtitle_dub_fake_files_no_provider():
    source = inspect.getsource(bot.cmd_tool_test_subtitle_dub_pipeline)
    assert "--fake-files" in source
    assert "p0_18a_fake_mux_success" in source
    assert "Provider call: <code>NO</code>" in source


def test_public_blocked_from_voice_subtitle_admin_tests():
    source = inspect.getsource(bot.p0_18a_admin_guard)
    assert "admin_only" in source
    assert "chưa xử lý file và chưa trừ Xu" in source


def test_voice_subtitle_public_copy_no_technical_terms():
    session = {
        "product_id": "multi_scene_film",
        "topic": "review sản phẩm",
        "draft": {
            "b14_profile_id": "product_review",
            "b14_storyboard_plan": _storyboard(),
            "b14_addon_plan": bot.video_b14_default_addon_plan("product_review"),
        },
    }
    public_text = "\n".join([
        provider_gate.PUBLIC_SAFE_BLOCK_MESSAGE,
        provider_gate.PUBLIC_SAFE_PREVIEW_MESSAGE,
        voice_adapter.PUBLIC_SAFE_VOICE_NOT_READY,
        subtitle_pipeline.PUBLIC_PARTIAL_MESSAGE,
        bot.video_b14_addon_text(session, "vi"),
        bot.video_b14_subtitle_text(session, "vi"),
        bot.video_b14_dub_text(session, "vi"),
    ])
    assert not provider_gate.public_copy_has_technical_terms(public_text)
