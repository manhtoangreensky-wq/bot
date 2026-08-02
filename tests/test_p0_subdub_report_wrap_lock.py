import asyncio
import re
import subprocess

import pytest

import bot
from services import video_local_validation as media_validation


REPORT_FIELDS_VI = [
    "Mã xử lý",
    "Kết quả",
    "Ngôn ngữ dịch",
    "Loại dịch vụ",
    "Thời lượng",
    "Giá",
    "Đã trừ",
    "Tài khoản còn",
    "Trạng thái",
]


def test_subdub_receipt_financial_snapshot_reads_balance_after_existing_charge(monkeypatch):
    calls = []

    def fake_get_user(user_id):
        calls.append(user_id)
        return 944, "newbie", ""

    monkeypatch.setattr(bot, "get_user", fake_get_user)

    snapshot = bot.subdub_receipt_financial_snapshot(
        "customer-1",
        price_xu=56,
        charged_xu=52,
    )

    assert snapshot == {
        "final_price_xu": 56,
        "charged_xu": 52,
        "account_balance_xu": 944,
    }
    assert calls == ["customer-1"]


@pytest.mark.parametrize(
    ("mode", "result_label", "service_label", "target_language", "price_xu"),
    [
        (bot.VIDEO_SUBTITLE_MODE_CREATE, "Video phụ đề", "Phụ đề", "", 0),
        (bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "Video phụ đề dịch", "Phụ đề dịch", "Tiếng Việt", 24),
        (bot.VIDEO_SUBTITLE_MODE_DUB, "Video lồng tiếng", "Lồng tiếng", "Tiếng Việt", 32),
        (
            bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "Video combo phụ đề - lồng tiếng",
            "Combo phụ đề - lồng tiếng",
            "Tiếng Việt",
            56,
        ),
    ],
)
def test_subdub_success_report_contains_only_owner_requested_fields(
    mode,
    result_label,
    service_label,
    target_language,
    price_xu,
):
    state = {
        "mode": mode,
        "requested_mode": mode,
        "terminal_state": "delivered",
        "target_language": target_language,
        "source_duration": 143.616,
    }
    result = {
        **state,
        "terminal_public_outcome_type": "success",
        "final_mp4_delivered": True,
        "video_delivered": True,
        "video_delivery_message_id": "receipt-video-1",
        "canonical_final_artifact_duration": 143.616,
        "duration_coverage_ok": True,
        "public_job_id": "REPORT-WRAP-1",
        "final_price_xu": price_xu,
        "charged_xu": max(0, price_xu - 4),
        "account_balance_xu": 944,
        "original_cue_count": 55,
        "translated_cue_count": 55,
        "tts_expected_segments": 55,
        "tts_generated_segments": 55,
        "tts_mixed_segments": 55,
        "audio_active_duration": 141.2,
        "artifact_validation_result": "ok",
    }

    text = bot.video_dubbing_receipt_text(state, result, "vi")
    bullet_lines = [line for line in text.splitlines() if line.startswith("• ")]
    labels = [re.sub(r"^•\s*([^:]+):.*$", r"\1", line) for line in bullet_lines]

    assert labels == REPORT_FIELDS_VI
    assert f"Kết quả: <b>{result_label}</b>" in text
    assert f"Loại dịch vụ: <b>{service_label}</b>" in text
    expected_language = target_language or "Không dịch"
    assert f"Ngôn ngữ dịch: <b>{expected_language}</b>" in text
    assert "Thời lượng: <b>2 phút 23 giây</b>" in text
    assert f"Giá: <b>{price_xu} Xu</b>" in text
    assert f"Đã trừ: <b>{max(0, price_xu - 4)} Xu</b>" in text
    assert "Tài khoản còn: <b>944 Xu</b>" in text
    assert "Trạng thái: <b>Đã gửi video</b>" in text
    for forbidden in (
        "Ngôn ngữ nguồn:",
        "Thời lượng nguồn:",
        "Thời lượng kết quả:",
        "Số câu phụ đề:",
        "TTS dự kiến/tạo/ghép/bỏ:",
        "Âm thanh hoạt động:",
        "Kiểm tra file:",
        "Giọng:",
    ):
        assert forbidden not in text


def test_subdub_international_report_has_the_same_nine_fields():
    text = bot.video_dubbing_receipt_text(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "terminal_state": "delivered",
            "target_language": "English",
        },
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "terminal_state": "delivered",
            "terminal_public_outcome_type": "success",
            "final_mp4_delivered": True,
            "video_delivered": True,
            "video_delivery_message_id": "receipt-video-en",
            "canonical_final_artifact_duration": 61.8,
            "duration_coverage_ok": True,
            "public_job_id": "REPORT-WRAP-EN",
            "final_price_xu": 40,
            "charged_xu": 36,
            "account_balance_xu": 964,
        },
        "en",
    )
    bullet_lines = [line for line in text.splitlines() if line.startswith("• ")]

    assert len(bullet_lines) == 9
    for label in (
        "Support code:",
        "Result:",
        "Translation language:",
        "Service type:",
        "Duration:",
        "Price:",
        "Charged:",
        "Account balance:",
        "Status:",
    ):
        assert sum(label in line for line in bullet_lines) == 1
    assert "Duration: <b>1 min 1 sec</b>" in text


LONG_EDGE_TEXT = (
    "This thing is going absolutely viral across platforms, and here it is "
    "for everyone watching the complete explanation on every platform today"
)


@pytest.mark.parametrize(
    "width,height",
    [(1280, 720), (720, 1280), (640, 360), (360, 640)],
)
def test_subdub_ass_autofit_keeps_two_lines_inside_safe_width(width, height):
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "output_type": "burn",
        "video_width": width,
        "video_height": height,
        "subtitle_style_preset": "cover_original",
    }
    style = bot.subdub_normalize_style(state)
    layout = bot.subdub_ass_fit_text_layout(LONG_EDGE_TEXT, style, 2)

    assert style["play_res_x"] == width
    assert style["play_res_y"] == height
    assert 0.02 <= style["subtitle_margin_l_after"] / width <= 0.05
    assert 0.02 <= style["subtitle_margin_r_after"] / width <= 0.05
    assert layout["fits_width"] is True
    assert layout["line_count"] <= 2
    assert layout["max_line_width_px"] <= layout["available_width_px"]
    assert 6 <= layout["font_size"] <= style["render_size"]
    assert layout["text"].replace(r"\N", " ") == LONG_EDGE_TEXT

    ass = bot.subdub_generate_ass_from_srt(
        f"1\n00:00:00,000 --> 00:00:04,000\n{LONG_EDGE_TEXT}\n",
        state,
    )
    dialogue = next(line for line in ass.splitlines() if line.startswith("Dialogue: 0,"))
    style_line = next(line for line in ass.splitlines() if line.startswith("Style: Default,"))
    fields = style_line.split(",")

    assert int(fields[19]) == style["subtitle_margin_l_after"]
    assert int(fields[20]) == style["subtitle_margin_r_after"]
    assert dialogue.count(r"\N") <= 1
    assert rf"{{\fs{layout['font_size']}}}" in dialogue


def test_subdub_ass_autofit_splits_unbroken_token_without_losing_text():
    token = "SUPERCALIFRAGILISTICEXPIALIDOCIOUS" * 2
    style = bot.subdub_normalize_style(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "output_type": "burn",
            "video_width": 720,
            "video_height": 1280,
            "subtitle_style_preset": "cover_original",
        }
    )

    layout = bot.subdub_ass_fit_text_layout(token, style, 2)

    assert layout["fits_width"] is True
    assert layout["line_count"] == 2
    assert layout["text"].replace(r"\N", "") == token
    assert layout["max_line_width_px"] <= layout["available_width_px"]


def _run_media(command, *, timeout=90):
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="ignore")[-2000:]
    return completed.stdout


@pytest.mark.parametrize("width,height", [(640, 360), (360, 640)])
def test_subdub_real_render_has_no_bright_subtitle_pixels_at_frame_edges(tmp_path, width, height):
    ffmpeg = media_validation.find_ffmpeg()
    if not ffmpeg:
        pytest.skip("FFmpeg unavailable for SubDub subtitle edge proof")
    source_path = tmp_path / f"source-{width}x{height}.mp4"
    output_path = tmp_path / f"output-{width}x{height}.mp4"
    _run_media(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:r=10:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:sample_rate=16000:duration=2",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            "2",
            str(source_path),
        ]
    )
    rendered, detail = asyncio.run(
        bot.video_dubbing_render_video(
            source_path.read_bytes(),
            subtitle_bytes=(
                f"1\n00:00:00,000 --> 00:00:02,000\n{LONG_EDGE_TEXT}\n"
            ).encode("utf-8"),
            subtitle_style={
                "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "output_type": "burn",
                "video_width": width,
                "video_height": height,
                "subtitle_style_preset": "cover_original",
            },
            require_audio=True,
        )
    )
    assert rendered, detail
    output_path.write_bytes(rendered)

    frame = _run_media(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "1",
            "-i",
            str(output_path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]
    )
    assert len(frame) == width * height * 3
    bright_x = []
    for index in range(0, len(frame), 3):
        if max(frame[index : index + 3]) >= 210:
            bright_x.append((index // 3) % width)

    assert bright_x
    edge_guard = max(2, int(round(width * 0.015)))
    assert min(bright_x) >= edge_guard
    assert max(bright_x) <= width - edge_guard - 1
