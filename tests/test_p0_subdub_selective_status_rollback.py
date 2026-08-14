"""Focused comparator for the selective SubDub status rollback.

This test executes only the real status helper source so it stays fast and
cannot start Telegram, provider, payment, or wallet code.
"""

from __future__ import annotations

import html
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _load_status_helpers():
    start_marker = "def subdub_progress_bar("
    end_marker = "def subdub_progress_keyboard("
    assert start_marker in BOT_SOURCE, "missing focused SubDub progress bar helper"
    start = BOT_SOURCE.index(start_marker)
    end = BOT_SOURCE.index(end_marker, start)
    namespace = {
        "html": html,
        "normalize_user_language": lambda lang: str(lang or "vi").lower(),
        "public_subdub_deep_copy": lambda lang: {
            "progress": "⏳ Processing" if lang != "vi" else "⏳ Đang xử lý",
            "success": "✅ Completed" if lang != "vi" else "✅ Đã hoàn tất",
            "job": "Task status" if lang != "vi" else "Trạng thái tác vụ",
        },
        "subdub_progress_stage_payload": lambda stage: {
            "stage": stage,
            "percent": 100 if stage == "delivered" else 65,
        },
        "product_progress_status_text": lambda *args, **kwargs: (
            "🎬 TOAN AAS đang xử lý video\n\n"
            "Trạng thái: Đang tạo giọng lồng tiếng\n"
            f"Tiến độ: {kwargs.get('percent', args[3] if len(args) > 3 else 0)}%\n"
            "Mã xử lý: #ABC123\n\n"
            "Các bước:\n✅ Nhận video\n⏳ Tạo giọng lồng tiếng\n⬜ Gửi kết quả\n\n"
            "Vui lòng không bấm lại nhiều lần."
        ),
    }
    exec(BOT_SOURCE[start:end], namespace)
    return namespace["subdub_progress_bar"], namespace["subdub_progress_text"]


def test_vi_restores_full_panel_and_horizontal_progress_bar():
    progress_bar, progress_text = _load_status_helpers()
    text = progress_text("generating_voice", "abc123", "vi")

    assert text.startswith("🎬 TOAN AAS đang xử lý video")
    assert "Trạng thái:" in text
    assert "Tiến độ: 65%" in text
    assert "Các bước:" in text
    assert progress_bar(65) in text
    assert progress_bar(65) == "0% 🟩🟩🟩🟩🟩🟩🟨⬜⬜⬜ 100%"
    assert progress_bar(0) == "0% ⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 100%"
    assert progress_bar(10) == "0% 🟩⬜⬜⬜⬜⬜⬜⬜⬜⬜ 100%"
    assert progress_bar(-5) == progress_bar(0)
    assert progress_bar(105) == progress_bar(100)
    assert progress_bar("invalid") == progress_bar(0)


def test_delivered_panel_is_full_green_and_keeps_receipt_handoff():
    progress_bar, progress_text = _load_status_helpers()
    text = progress_text("delivered", "abc123", "vi")

    assert text.startswith("✅ TOAN AAS đã hoàn tất video")
    assert progress_bar(100) == "0% 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 100%"
    assert progress_bar(100) in text
    assert "SUBDUB_POSTDELIVERY_VIDEO_EDIT_CONTEXT" in BOT_SOURCE
    assert 'callback_data=f"videodub|edit|{token}"' in BOT_SOURCE
    assert 'callback_data=f"videodub|branding|{token}"' in BOT_SOURCE


def test_non_vi_keeps_native_compact_copy_without_vietnamese_panel_leak():
    progress_bar, progress_text = _load_status_helpers()
    text = progress_text("generating_voice", "abc123", "en")

    assert text.startswith("⏳ Processing · 65%")
    assert progress_bar(65) in text
    assert "Các bước:" not in text
    assert "Trạng thái tác vụ" not in text


if __name__ == "__main__":
    test_vi_restores_full_panel_and_horizontal_progress_bar()
    test_delivered_panel_is_full_green_and_keeps_receipt_handoff()
    test_non_vi_keeps_native_compact_copy_without_vietnamese_panel_leak()
    print("3 focused SubDub status comparators passed")
