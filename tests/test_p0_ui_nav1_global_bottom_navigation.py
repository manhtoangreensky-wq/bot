from __future__ import annotations

from pathlib import Path

from services import ui_navigation


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


class Button:
    def __init__(self, text: str, *, callback_data: str):
        self.text = text
        self.callback_data = callback_data


def labels(rows):
    return [[button.text for button in row] for row in rows]


def callbacks(rows):
    return [[button.callback_data for button in row] for row in rows]


def test_canonical_bottom_nav_requires_and_preserves_exact_parent_callback():
    row = ui_navigation.canonical_bottom_nav(
        "vprofile|audio_plan",
        button_factory=Button,
    )
    assert labels([row]) == [["⬅️ Quay lại", "🏠 Menu chính"]]
    assert callbacks([row]) == [["vprofile|audio_plan", "menu|main"]]


def test_existing_back_and_main_are_deduped_and_moved_to_the_last_row():
    rows = [
        [Button("⬅️ Quay lại", callback_data="video|parent")],
        [Button("Sửa", callback_data="video|edit"), Button("Xem", callback_data="video|view")],
        [Button("🏠 Menu chính", callback_data="menu|main")],
        [Button("Tiếp tục", callback_data="video|next")],
    ]
    result = ui_navigation.canonicalize_bottom_navigation(rows, button_factory=Button)
    assert labels(result) == [
        ["Sửa", "Xem"],
        ["Tiếp tục"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]
    assert callbacks(result[-1:]) == [["video|parent", "menu|main"]]
    assert ui_navigation.navigation_audit(result)["bottom_row_ok"] is True


def test_numeric_suggestion_row_is_the_only_five_button_exception():
    rows = [
        [Button(str(index), callback_data=f"pick|{index}") for index in range(1, 6)],
        [Button("Tự nhập", callback_data="custom")],
        [Button("Quay lại", callback_data="field|back"), Button("Menu", callback_data="menu|main")],
    ]
    result = ui_navigation.canonicalize_bottom_navigation(rows, button_factory=Button)
    assert len(result[0]) == 5
    assert all(len(row) <= 2 for row in result[1:])
    assert labels(result[-1:]) == [["⬅️ Quay lại", "🏠 Menu chính"]]


def test_keyboard_without_both_navigation_buttons_is_not_rewritten():
    rows = [[Button("🏠 Menu chính", callback_data="menu|main")]]
    result = ui_navigation.canonicalize_bottom_navigation(rows, button_factory=Button)
    assert result == rows


def test_parent_label_is_canonicalized_but_pagination_button_is_preserved():
    rows = [
        [Button("⬅️ Trang trước", callback_data="items|page|0")],
        [Button("⬅️ Hỗ trợ", callback_data="support|start")],
        [Button("🏠 Menu chính", callback_data="menu|main")],
    ]
    result = ui_navigation.canonicalize_bottom_navigation(rows, button_factory=Button)
    assert labels(result) == [
        ["⬅️ Trang trước"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]
    assert callbacks(result[-1:]) == [["support|start", "menu|main"]]


def test_bot_uses_global_navigation_constructor_without_inventing_back_routes():
    assert "_TelegramInlineKeyboardMarkup = InlineKeyboardMarkup" in BOT_SOURCE
    assert "ui_navigation.canonicalize_bottom_navigation(" in BOT_SOURCE
    assert "button_factory=InlineKeyboardButton" in BOT_SOURCE
    assert "back_callback is required" in (ROOT / "services" / "ui_navigation.py").read_text(encoding="utf-8")

    class RawMarkup:
        def __init__(self, rows, *args, **kwargs):
            self.inline_keyboard = rows

    start = BOT_SOURCE.index("class InlineKeyboardMarkup(")
    end = BOT_SOURCE.index("\n\n# ─── LOGGING", start)
    scope = {
        "_TelegramInlineKeyboardMarkup": RawMarkup,
        "InlineKeyboardButton": Button,
        "ui_navigation": ui_navigation,
    }
    exec(BOT_SOURCE[start:end], scope)
    markup = scope["InlineKeyboardMarkup"]([
        [Button("Menu chính", callback_data="menu|main")],
        [Button("Quay lại", callback_data="video|parent")],
    ])
    assert labels(markup.inline_keyboard) == [["⬅️ Quay lại", "🏠 Menu chính"]]


def test_stale_callbacks_are_not_mutated_by_navigation_normalization():
    stale_callback = "legacy_video|old_parent"
    rows = [[
        Button("Quay lại", callback_data=stale_callback),
        Button("Menu chính", callback_data="menu|main"),
    ]]
    result = ui_navigation.canonicalize_bottom_navigation(rows, button_factory=Button)
    assert callbacks(result) == [[stale_callback, "menu|main"]]


def test_non_vietnamese_navigation_labels_survive_global_normalization():
    """The wrapper may reorder navigation, but must never translate it for us."""
    cases = (
        ("⬅️ Back", "🏠 Main menu"),
        ("⬅️ 戻る", "🏠 メインメニュー"),
        ("⬅️ 뒤로", "🏠 메인 메뉴"),
        ("⬅️ رجوع", "🏠 القائمة الرئيسية"),
        ("⬅️ Volver", "🏠 Menú principal"),
    )

    for back_text, main_text in cases:
        rows = [
            [Button("Continue", callback_data="flow|next")],
            [
                Button(back_text, callback_data="flow|back"),
                Button(main_text, callback_data="menu|main"),
            ],
        ]
        result = ui_navigation.canonicalize_bottom_navigation(rows, button_factory=Button)
        assert labels(result[-1:]) == [[back_text, main_text]]
        assert callbacks(result[-1:]) == [["flow|back", "menu|main"]]
        assert ui_navigation.navigation_audit(result)["bottom_row_ok"] is True


def test_noncanonical_vietnamese_parent_label_survives_normalization():
    rows = [[
        Button("⬅️ Về menu ảnh", callback_data="image|parent"),
        Button("🏠 Menu chính", callback_data="menu|main"),
    ]]
    result = ui_navigation.canonicalize_bottom_navigation(rows, button_factory=Button)
    assert labels(result) == [["⬅️ Về menu ảnh", "🏠 Menu chính"]]
