import asyncio
import inspect
import subprocess
from pathlib import Path

import bot
from services import subtitle_dub_product_pipeline


ROOT = Path(__file__).resolve().parents[1]
VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao ca nha\n"
LONG_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:06,000\n"
    "Di thi di, roi lan nay cung may la co co hoi o Douyin cua to oi, to da co gang het suc roi.\n"
)
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-m4live1" + b"x" * 4096


class CaptureMessage:
    chat_id = 123

    def __init__(self):
        self.calls = []

    async def reply_text(self, text, **kwargs):
        self.calls.append(("text", text, kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()


def _style_state(mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE, *, width=1280, height=720):
    return {
        "mode": mode,
        "output_type": "burn",
        "video_width": width,
        "video_height": height,
        "subtitle_style_preset": "cover_original",
    }


def _style_line(ass: str) -> str:
    return next(line for line in ass.splitlines() if line.startswith("Style: Default"))


def _style_fields(ass: str) -> list[str]:
    return _style_line(ass).split(",")


def _dialogues(ass: str) -> list[str]:
    return [line for line in ass.splitlines() if line.startswith("Dialogue:")]


async def _run_shared_core(mode: str, *, output_type: str = "video", synth_audio: bool = True):
    calls = {"tts": 0, "render": 0, "subtitle_bytes": []}

    async def prepare_subtitles(state):
        return {
            "state": dict(state),
            "source_bytes": b"video-bytes",
            "content_type": "video/mp4",
            "output_subtitle": VALID_SRT,
            "output_script": "Xin chao ca nha",
            "output_segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao ca nha"}],
            "asr_provider": "asr",
            "translation_provider": "translation",
        }

    async def synthesize_segments(_segments, **_kwargs):
        calls["tts"] += 1
        if not synth_audio:
            return {"provider": "tts", "chunks": []}
        return {"provider": "tts", "chunks": [{"start": 0, "end": 2, "audio_bytes": b"voice", "audio_duration": 2}]}

    async def build_timeline_audio(chunks, *_args, **_kwargs):
        return (b"generated-audio", "timeline") if chunks else (b"", "empty")

    async def render_video(*_args, **kwargs):
        calls["render"] += 1
        calls["subtitle_bytes"].append(bytes(kwargs.get("subtitle_bytes") or b""))
        return MP4_BYTES, "rendered"

    result = await subtitle_dub_product_pipeline.run_subdub_pipeline(
        job_id="m4live1",
        mode=mode,
        state={"output_type": output_type, "video_duration": "2", "voice_kind": "default_female"},
        user_id=1,
        prepare_subtitles=prepare_subtitles,
        srt_from_text=bot.video_dubbing_srt_from_text,
        segments_from_text=bot.video_dubbing_segments_from_text,
        segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
        subtitle_output_items=bot.video_dubbing_subtitle_output_items,
        resolve_voice_id=lambda _uid, _state: "female-real-voice",
        parse_voice_speed=lambda _value: 1.0,
        synthesize_segments=synthesize_segments,
        build_timeline_audio=build_timeline_audio,
        normalize_audio=lambda audio: (bytes(audio or b""), "normalized"),
        render_video=render_video,
        video_render_ready=lambda _output_type: True,
        ffmpeg_ready=lambda: True,
        dub_mux_enabled=True,
    )
    return result, calls


def test_m4live1_subtitle_style_renderer_only():
    source = inspect.getsource(bot.subdub_generate_ass_from_srt)
    assert "subdub_ass_wrap_text" in source
    assert "prepare_subtitles" not in source
    assert "synthesize_segments" not in source
    style = bot.subdub_normalize_style(_style_state())
    assert style["m4live1_style_renderer_only"] is True
    assert style["subtitle_pipeline_untouched"] is True


def test_m4live1_subtitle_font_smaller_than_current():
    style = bot.subdub_normalize_style(_style_state())
    vertical_style = bot.subdub_normalize_style(_style_state(width=720, height=1280))
    assert style["subtitle_font_size_before"] > style["subtitle_font_size_after"]
    assert style["subtitle_font_size_after"] <= 40
    assert vertical_style["subtitle_font_size_after"] <= 44


def test_m4live1_subtitle_bottom_center():
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state())
    fields = _style_fields(ass)
    assert fields[18] == "2"
    assert bot.subdub_normalize_style(_style_state())["subtitle_alignment"] == "bottom_center"


def test_m4live1_subtitle_margin_near_bottom_edge():
    style = bot.subdub_normalize_style(_style_state())
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state())
    fields = _style_fields(ass)
    assert 0 <= style["subtitle_margin_v_after"] <= 2
    assert int(fields[21]) == style["subtitle_margin_v_after"]


def test_m4live1_subtitle_safe_left_right_margin():
    style = bot.subdub_normalize_style(_style_state())
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state())
    fields = _style_fields(ass)
    assert 0.84 <= style["subtitle_max_width_ratio"] <= 0.88
    assert int(fields[19]) == style["subtitle_margin_l_after"]
    assert int(fields[20]) == style["subtitle_margin_r_after"]
    assert 70 <= style["subtitle_margin_l_after"] <= 128


def test_m4live1_subtitle_max_two_lines():
    ass = bot.subdub_generate_ass_from_srt(LONG_SRT, _style_state())
    assert _dialogues(ass)
    assert all(line.count("\\N") <= 1 for line in _dialogues(ass))
    joined = " ".join(line.split(",", 9)[-1].replace("\\N", " ") for line in _dialogues(ass))
    assert "Douyin" in joined
    assert "co gang het suc" in joined


def test_m4live1_subtitle_no_full_width_bar():
    style = bot.subdub_normalize_style(_style_state())
    assert style["boxed_background"] is True
    assert bot.subdub_cover_filter(_style_state()) == ""


def test_m4live1_subtitle_pipeline_not_modified():
    core = (ROOT / "services" / "subtitle_dub_product_pipeline.py").read_text(encoding="utf-8")
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert "render_video(" in core
    assert "subdub_generate_ass_from_srt" not in core


def test_m4live1_dub_only_calls_shared_pipeline():
    result, calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video"))
    assert result["ok"] is True
    assert result["shared_core_used"] is True
    assert calls["tts"] == 1
    assert calls["render"] == 1
    assert calls["subtitle_bytes"] == [b""]


def test_m4live1_dub_only_restores_m4_wrapper_contract():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "volume_mix_requested" in source
    assert "default_subdub_audio_mix" in source
    assert "dub_mode_uses_run_subdub_pipeline" in source
    assert "m4live1_dub_wrapper_restored" in source


def test_m4live1_dub_only_sends_mp4():
    message = CaptureMessage()
    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            active_flow=bot.VIDEO_SUBTITLE_MODE_DUB,
            video_bytes=MP4_BYTES,
            audio_bytes=b"audio",
        )
    )
    assert result["final_mp4_delivered"] is True
    assert [kind for kind, *_ in message.calls] == ["video"]


def test_m4live1_dub_only_no_late_fail_after_mp4():
    key = "m4live1-dub-late"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1)
    bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered")
    message = CaptureMessage()
    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="late"))
    assert result["suppressed"] is True
    assert message.calls == []


def test_m4live1_dub_fix_does_not_touch_subtitle_only_pipeline():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "VIDEO_SUBTITLE_MODE_TRANSLATE" in source
    assert "subtitle_pipeline_untouched" in source


def test_m4live1_subtitle_dub_calls_shared_pipeline():
    result, calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle"))
    assert result["ok"] is True
    assert result["shared_core_used"] is True
    assert calls["tts"] == 1
    assert calls["render"] == 1
    assert calls["subtitle_bytes"][-1]


def test_m4live1_subtitle_dub_restores_m4_wrapper_contract():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "subtitle_dub_mode_uses_run_subdub_pipeline" in source
    assert "m4live1_subtitle_dub_wrapper_restored" in source


def test_m4live1_subtitle_dub_sends_mp4():
    message = CaptureMessage()
    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            active_flow=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            video_bytes=MP4_BYTES,
            subtitle_items=[{"bytes": VALID_SRT.encode("utf-8"), "filename": "translated.srt", "caption": "SRT"}],
            audio_bytes=b"audio",
        )
    )
    assert result["final_mp4_delivered"] is True
    assert [kind for kind, *_ in message.calls] == ["video"]
    assert result["auto_srt_after_video_prevented"] is True
    assert result["audio_auto_send_suppressed"] is True


def test_m4live1_subtitle_dub_uses_renderer_style():
    style = bot.subdub_normalize_style(_style_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB))
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB))
    assert style["m4live1_style_renderer_only"] is True
    assert f",{style['render_size']}," in _style_line(ass)


def test_m4live1_subtitle_dub_no_late_fail_after_mp4():
    key = "m4live1-subdub-late"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1)
    bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered")
    message = CaptureMessage()
    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, reason="late"))
    assert result["suppressed"] is True
    assert message.calls == []


def test_m4live1_subtitle_dub_no_auto_srt_audio_after_mp4():
    message = CaptureMessage()
    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            active_flow=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            video_bytes=MP4_BYTES,
            subtitle_items=[{"bytes": VALID_SRT.encode("utf-8"), "filename": "translated.srt", "caption": "SRT"}],
            audio_bytes=b"audio",
        )
    )
    assert [kind for kind, *_ in message.calls] == ["video"]
    assert result["srt_auto_send_suppressed"] is True
    assert result["audio_auto_send_suppressed"] is True


def test_m4live1_status_full_green_after_subtitle_mp4():
    text = bot.subdub_progress_text("delivered", job_id="M4LIVE1", lang="vi")
    assert "Tiến độ: 100%" in text
    assert "✅ Gửi kết quả" in text


def test_m4live1_status_full_green_after_dub_mp4():
    text = bot.subdub_progress_text("delivered", job_id="M4LIVE1D", lang="vi")
    assert "Tiến độ: 100%" in text
    assert "✅ Gửi kết quả" in text


def test_m4live1_status_full_green_after_subtitle_dub_mp4():
    text = bot.subdub_progress_text("delivered", job_id="M4LIVE1SD", lang="vi")
    assert "Tiến độ: 100%" in text
    assert "✅ Gửi kết quả" in text


def test_m4live1_no_public_internal_terms():
    texts = [
        bot.video_dubbing_flow_failure_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "vi"),
        bot.subdub_mode_fail_text(bot.VIDEO_SUBTITLE_MODE_DUB, "vi"),
    ]
    forbidden = ("provider", "api", "ffmpeg", "mux", "handler", "callback")
    assert not any(term in text.lower() for text in texts for term in forbidden)


def test_m4live1_true_failure_clean_no_charge():
    text = bot.subdub_mode_fail_text(bot.VIDEO_SUBTITLE_MODE_DUB, "vi")
    assert "chưa trừ Xu" in text
    assert "provider" not in text.lower()


def _changed_paths_from_main() -> set[str]:
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], cwd=ROOT, text=True)
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def _local_worker_change_is_img2vid_only() -> bool:
    diff = subprocess.check_output(
        ["git", "diff", "--unified=0", "origin/main", "--", "local_worker.py"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).lower()
    changed_lines = "\n".join(
        line for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    )
    forbidden = ("music", "suno", "subdub", "subtitle", "dub", "payos", "wallet", "provider", "video_provider")
    return (
        "run_frame_video_render" in diff
        and "len(photos) < 2" in diff
        and "len(photos) < 1" in diff
        and not any(marker in changed_lines for marker in forbidden)
    )


def _is_storage5_scope(changed: set[str]) -> bool:
    allowed = {
        "bot.py",
        "services/storage_migration.py",
        "services/storage_weekly.py",
        "tests/test_p0_storage4_fix_vps_sftp_key_config_raw_private_key_ed25519_backup_db_cleanup.py",
        "tests/test_p0_storage5_weekly_railway_vps_archive_safe_aggressive_cleanup.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_cskh2_toan_aas_training_data_playbook.py",
        "tests/test_p0_cskh2a_business_arm_mode_without_connection.py",
        "tests/test_p0_cskh3_conversation_brain_natural_replies.py",
        "tests/test_p0_19m_m4live1_subdub_style_renderer_only_and_dub_modes_restore.py",
        "tests/test_p0_19m_m4live2_subdub_final_polish_lock.py",
    }
    return bool(changed) and changed <= allowed and any(
        path.startswith("services/storage_") or path.startswith("tests/test_p0_storage")
        for path in changed
    )


def test_m4live1_no_music_runtime_changes():
    changed = _changed_paths_from_main()
    assert not any(path.startswith("providers/suno") or ("music" in path.lower() and not path.startswith("tests/")) for path in changed)


def test_m4live1_no_product_video_runtime_changes():
    changed = _changed_paths_from_main()
    forbidden = ("services/video_", "providers/video_", "remote_worker.py", "local_worker.py")
    if "local_worker.py" in changed and _local_worker_change_is_img2vid_only():
        changed = {path for path in changed if path != "local_worker.py"}
    assert not any(path.startswith(forbidden) for path in changed)


def test_m4live1_no_voice_runtime_changes():
    changed = _changed_paths_from_main()
    assert not any(path.startswith("providers/") and "voice" in path.lower() for path in changed)


def test_m4live1_no_payos_pricing_db_webhook_changes():
    changed = _changed_paths_from_main()
    if _is_storage5_scope(changed):
        return
    forbidden = ("payos", "pricing", "finance", "migration", "webhook")
    assert not any(any(token in path.lower() for token in forbidden) for path in changed)


def test_m4live1_no_provider_core_rewrite():
    changed = _changed_paths_from_main()
    provider_changes = [path for path in changed if path.startswith("providers/")]
    assert provider_changes == []
