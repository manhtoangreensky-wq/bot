"""Unit test verifying Vietnamese font encoding / UTF-8 mojibake repair and NFC normalization."""
import unicodedata
import pytest
from bot import _repair_mojibake_str, _normalize_telegram_payload, InlineKeyboardMarkup, InlineKeyboardButton


def test_repair_mojibake_vietnamese_strings():
    samples = [
        "Tiếng Việt",
        "Hướng dẫn nạp Xu và quản trị",
        "Bạn không có quyền dùng lệnh này.",
        "Thông báo số dư không đủ",
        "Yêu cầu được chấp nhận thành công",
    ]
    for orig in samples:
        # 1. Identity on clean NFC
        assert _repair_mojibake_str(orig) == orig
        # 2. Repair double-encoded UTF-8 in latin1
        mojibake = orig.encode("utf-8").decode("latin1")
        repaired = _repair_mojibake_str(mojibake)
        assert repaired == orig
        # 3. Canonical NFC check
        assert unicodedata.is_normalized("NFC", repaired)


def test_normalize_telegram_payload_recursive():
    payload = {
        "text": "Tiếng Việt".encode("utf-8").decode("latin1"),
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "Hướng dẫn".encode("utf-8").decode("latin1"), "callback_data": "guide_vi"}
                ]
            ]
        },
        "nested_list": ["Bạn không có quyền".encode("utf-8").decode("latin1")],
    }
    normalized = _normalize_telegram_payload(payload)
    assert normalized["text"] == "Tiếng Việt"
    assert normalized["reply_markup"]["inline_keyboard"][0][0]["text"] == "Hướng dẫn"
    assert normalized["nested_list"][0] == "Bạn không có quyền"


def test_inline_keyboard_markup_normalization():
    mojibake = "Tiếng Việt".encode("utf-8").decode("latin1")
    btn = InlineKeyboardButton(text=mojibake, callback_data="test_data")
    markup = InlineKeyboardMarkup([[btn]])
    assert markup.inline_keyboard[0][0].text == "Tiếng Việt"
