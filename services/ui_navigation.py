from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


CANONICAL_BACK_TEXT = "⬅️ Quay lại"
CANONICAL_MAIN_TEXT = "🏠 Menu chính"
CANONICAL_MAIN_CALLBACK = "menu|main"


def _button_text(button: Any) -> str:
    return str(getattr(button, "text", "") or "").strip()


def _button_callback(button: Any) -> str:
    return str(getattr(button, "callback_data", "") or "").strip()


def is_main_menu_button(button: Any) -> bool:
    return _button_callback(button) == CANONICAL_MAIN_CALLBACK


def is_position_choice_button(button: Any) -> bool:
    callback = _button_callback(button)
    parts = callback.split("|")
    return callback.startswith("video_tail|logo|setpos|") or (
        len(parts) >= 3
        and parts[1] in {
            "content_position_set",
            "post_position_set",
            "logo_position_set",
        }
    )


def is_back_button(button: Any) -> bool:
    text = _button_text(button).casefold()
    callback = _button_callback(button).casefold()
    if is_main_menu_button(button) or is_position_choice_button(button):
        return False
    pagination_terms = (
        "trang trước",
        "cảnh trước",
        "tệp trước",
        "mục trước",
        "bản trước",
        "previous page",
        "previous scene",
        "上一页",
    )
    arrow_back = text.startswith(("⬅", "🔙", "↩")) and not any(
        term in text for term in pagination_terms
    )
    return (
        arrow_back
        or "quay lại" in text
        or text.startswith("⬅️ back")
        or text.startswith("🔙 back")
        or callback.endswith("|back")
        or callback.endswith(":back")
        or callback.endswith("_back")
    )


def is_numeric_suggestion_row(row: Sequence[Any]) -> bool:
    if len(row) != 5:
        return False
    labels = [_button_text(button).replace("️⃣", "").strip() for button in row]
    return labels == ["1", "2", "3", "4", "5"]


def is_position_grid_row(row: Sequence[Any]) -> bool:
    return len(row) == 3 and all(is_position_choice_button(button) for button in row)


def canonical_bottom_nav(
    back_callback: str,
    *,
    button_factory,
    menu_callback: str = CANONICAL_MAIN_CALLBACK,
    back_text: str = CANONICAL_BACK_TEXT,
    menu_text: str = CANONICAL_MAIN_TEXT,
) -> list[Any]:
    """Build the one canonical bottom row without guessing its parent route."""
    safe_back = str(back_callback or "").strip()
    if not safe_back:
        raise ValueError("back_callback is required")
    return [
        button_factory(back_text, callback_data=safe_back),
        button_factory(menu_text, callback_data=menu_callback),
    ]


def canonicalize_bottom_navigation(
    rows: Iterable[Sequence[Any]],
    *,
    button_factory,
) -> list[list[Any]]:
    """Move an existing Back/Main pair to the final row and preserve its route.

    The function never invents a parent callback. Keyboards without both buttons
    are returned unchanged. This keeps business actions intact while making the
    navigation contract uniform.
    """
    normalized = [list(row) for row in rows]
    back_buttons = [button for row in normalized for button in row if is_back_button(button)]
    main_buttons = [button for row in normalized for button in row if is_main_menu_button(button)]
    if not back_buttons or not main_buttons:
        return normalized

    back = back_buttons[-1]
    kept_rows: list[list[Any]] = []
    for row in normalized:
        kept = [
            button
            for button in row
            if not is_main_menu_button(button) and not is_back_button(button)
        ]
        if kept:
            if is_numeric_suggestion_row(kept) or is_position_grid_row(kept):
                kept_rows.append(kept)
            else:
                kept_rows.extend(kept[index:index + 2] for index in range(0, len(kept), 2))

    kept_rows.append(
        canonical_bottom_nav(
            _button_callback(back),
            button_factory=button_factory,
        )
    )
    return kept_rows


def navigation_audit(rows: Iterable[Sequence[Any]]) -> dict[str, Any]:
    normalized = [list(row) for row in rows]
    back = [button for row in normalized for button in row if is_back_button(button)]
    main = [button for row in normalized for button in row if is_main_menu_button(button)]
    expected = bool(back and main)
    bottom_ok = not expected or (
        len(normalized[-1]) == 2
        and _button_text(normalized[-1][0]) == CANONICAL_BACK_TEXT
        and _button_text(normalized[-1][1]) == CANONICAL_MAIN_TEXT
        and _button_callback(normalized[-1][0]) == _button_callback(back[-1])
        and _button_callback(normalized[-1][1]) == CANONICAL_MAIN_CALLBACK
    )
    return {
        "has_back": bool(back),
        "has_main": bool(main),
        "bottom_row_required": expected,
        "bottom_row_ok": bottom_ok,
        "back_callback": _button_callback(back[-1]) if back else "",
        "buttons_after_bottom_nav": 0 if bottom_ok else None,
    }
