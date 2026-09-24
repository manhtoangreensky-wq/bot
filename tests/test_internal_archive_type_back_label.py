from pathlib import Path


def test_type_picker_back_label_matches_preview_destination():
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
    start = source.index('def internal_archive_type_keyboard(')
    end = source.index('\ndef internal_archive_type_text(', start)
    block = source[start:end]
    assert 'InlineKeyboardButton("⬅️ Xem lại hồ sơ", callback_data="archive|back_department")' in block
