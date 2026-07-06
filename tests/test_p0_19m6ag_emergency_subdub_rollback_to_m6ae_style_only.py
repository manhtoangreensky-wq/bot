import asyncio
import inspect
import re
import subprocess

import bot


VALID_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:03,000\n"
    "Day la dong phu de dai can hien thi gon va khong che mat noi dung video goc.\n"
)


class _Sent:
    def __init__(self, message_id: int):
        self.message_id = message_id


class _Message:
    def __init__(self):
        self.videos = []
        self.documents = []
        self.texts = []

    async def reply_video(self, **kwargs):
        self.videos.append(kwargs)
        return _Sent(701)

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)
        return _Sent(702)

    async def reply_text(self, text, **kwargs):
        self.texts.append({"text": text, **kwargs})
        return _Sent(703)


def _diff_files_from_main() -> set[str]:
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def _ass_style_line(ass_text: str) -> str:
    for line in ass_text.splitlines():
        if line.startswith("Style: Default,"):
            return line
    raise AssertionError("ASS style line missing")


def test_m6ag_keeps_subdub_pipeline_runtime_unchanged_from_current_main():
    changed = _diff_files_from_main()

    assert "services/subtitle_dub_product_pipeline.py" not in changed
    assert "services/product_progress_status.py" not in changed


def test_m6ag_subtitle_only_restored_to_m6ae_mp4_success():
    message = _Message()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow="subtitle_translate",
            subtitle_items=[{
                "output_type": "srt",
                "filename": "toan_aas_subtitle_translate.srt",
                "bytes": VALID_SRT.encode("utf-8"),
            }],
            srt_text=VALID_SRT,
            video_bytes=b"valid-mp4-bytes",
            lang="vi",
        )
    )

    assert sent["final_mp4_delivered"] is True
    assert len(message.videos) == 1


def test_m6ag_subtitle_only_no_translate_failure_for_valid_short_video():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "target_language": "Tiếng Việt", "video_duration": 21},
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "video_delivery_message_id": "701", "charged": 0},
        "vi",
    )

    assert "Đã tạo video phụ đề thành công" in text
    assert "chưa dịch được phụ đề" not in text
    assert "chưa tạo được video hoàn chỉnh" not in text


def test_m6ag_subtitle_only_srt_artifact_still_created():
    labels = [
        button.text
        for row in bot.video_dubbing_receipt_keyboard(
            "vi",
            "translation",
            {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "active_flow": "subtitle_translate"},
        ).inline_keyboard
        for button in row
    ]

    assert "📄 Tải SRT dịch" in labels


def test_m6ag_subtitle_only_no_auto_srt_after_mp4():
    message = _Message()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow="subtitle_translate",
            subtitle_items=[{
                "output_type": "srt",
                "filename": "toan_aas_subtitle_translate.srt",
                "bytes": VALID_SRT.encode("utf-8"),
            }],
            srt_text=VALID_SRT,
            video_bytes=b"valid-mp4-bytes",
            lang="vi",
        )
    )

    assert sent["srt_auto_send_suppressed"] is True
    assert len(message.documents) == 0


def test_m6ag_subtitle_only_receipt_success_no_late_fail():
    key = "m6ag-subtitle-delivered"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    acquired, _job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=196606,
        chat_id=196606,
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    )
    assert acquired is True

    ok = bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="701",
        terminal_artifact_type="video",
        video_delivery_message_id="701",
    )
    message = _Message()
    duplicate = asyncio.run(
        bot.send_subdub_fail_once(
            message,
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            reason="late_fail_after_success",
            lang="vi",
        )
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert ok is True
    assert duplicate["suppressed"] is True
    assert message.texts == []
    assert stored["terminal_state"] == "delivered"
    assert stored["progress_percent"] == 100


def test_m6ag_style_font_is_smaller_but_keeps_m4restore_render_formula():
    style_720 = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 1280,
        "video_height": 720,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    })
    style_1080 = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 1920,
        "video_height": 1080,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    })

    assert style_720["render_size"] == bot.subdub_render_subtitle_size(style_720, style_720)
    assert style_1080["render_size"] == bot.subdub_render_subtitle_size(style_1080, style_1080)
    assert style_720["render_size"] <= 38
    assert style_1080["render_size"] <= 46
    assert style_720["subtitle_style_source"] == "m6ag_style_only"
    assert style_720["subtitle_font_size_before"] > style_720["subtitle_font_size_after"]
    assert style_720["subtitle_style_only_change"] == "yes"


def test_m6ag_translated_subtitles_sit_near_bottom_not_middle_screen():
    ass = bot.subdub_generate_ass_from_srt(
        VALID_SRT,
        {
            "subtitle_style_preset": "cover_original",
            "video_width": 1280,
            "video_height": 720,
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        },
    )
    style_line = _ass_style_line(ass)
    fields = style_line.split(",")
    alignment = int(fields[-5])
    margin_v = int(fields[-2])

    assert alignment == 2
    assert 4 <= margin_v <= 8
    assert "PlayResY: 720" in ass


def test_m6ag_debug_fields_expose_style_before_after_values():
    style = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 1280,
        "video_height": 720,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    })

    assert style["subtitle_alignment"] == "bottom_center"
    assert style["subtitle_max_lines"] == 2
    assert style["subtitle_font_size_before"] > style["subtitle_font_size_after"]
    assert style["subtitle_margin_v_before"] > style["subtitle_margin_v_after"]
    assert 4 <= style["subtitle_margin_v_after"] <= 8


def test_m6ag_subtitle_wrap_is_limited_to_two_lines():
    ass = bot.subdub_generate_ass_from_srt(
        "1\n00:00:00,000 --> 00:00:04,000\n"
        "mot hai ba bon nam sau bay tam chin muoi muoi mot muoi hai muoi ba muoi bon muoi lam\n",
        {
            "subtitle_style_preset": "cover_original",
            "video_width": 1280,
            "video_height": 720,
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        },
    )
    dialogue = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))

    assert dialogue.count("\\N") <= 1


def test_m6ag_renderer_style_failure_falls_back_to_basic_filter_not_pipeline_failure():
    source = inspect.getsource(bot.video_dubbing_render_video)

    assert 'return b"", str(style.get("subtitle_font_blocker")' not in source
    assert 'return b"", "subtitle_ass_generation_failed"' not in source
    assert "subtitle_style_fallback_basic" in source
    assert "fallback_subtitle_filter or subtitle_filter" in source


def test_m6ag_no_forbidden_runtime_areas_touched():
    changed = _diff_files_from_main()
    forbidden_patterns = [
        r"(^|/)providers/(key4u_provider|video_|music|suno)",
        r"(^|/)services/(video_provider|video_real|music|payos|wallet|storage|artifact)",
        r"(^|/)tests/test_p0_23",
        r"(^|/)tests/test_p0_18v",
        r"(^|/)tests/test_p0_17c",
    ]

    forbidden = [
        path
        for path in changed
        if any(re.search(pattern, path) for pattern in forbidden_patterns)
    ]
    assert forbidden == []
