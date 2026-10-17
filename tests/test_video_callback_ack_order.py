"""Regression checks for the Video menu callback ACK fast path.

These checks intentionally inspect the production source instead of importing
the full Telegram bot.  They stay provider-free and make the UI contract
explicit: navigation callbacks acknowledge Telegram before synchronous
language/state work can delay the visible screen.
"""

from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    lines = SOURCE.splitlines(keepends=True)
    start = next(
        index
        for index, line in enumerate(lines)
        if line.startswith((f"def {name}(", f"async def {name}("))
    )
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith(("def ", "async def ", "class "))
            or (
                lines[index].strip()
                and not lines[index][0].isspace()
                and "=" in lines[index]
                and not lines[index].startswith("@")
            )
        ),
        len(lines),
    )
    return "".join(lines[start:end])


def _index_pair(text: str, first: str, second: str) -> tuple[int, int]:
    first_index = text.index(first)
    second_index = text.index(second)
    assert first_index < second_index, f"expected {first!r} before {second!r}"
    return first_index, second_index


def test_video_uiflow3_entry_ack_precedes_draft_creation():
    source = _function_source("handle_video_uiflow3_callback")
    _index_pair(source, "await query.answer()", "state = start_video_uiflow3_state(context, product)")
    _index_pair(source, "await query.answer()", "callback_answered = True")
    assert "if not callback_answered:\n            await query.answer(\"Đã nhận lựa chọn này.\")" in source


def test_video_uiflow3_back_ack_precedes_navigation_and_does_not_double_ack():
    source = _function_source("handle_video_uiflow3_callback")
    back_ack = source.index('if action == "back":')
    _index_pair(source[back_ack:], "await query.answer()", "save_video_uiflow3_state(context, state)")
    _index_pair(source[back_ack:], "await query.answer()", "elif action == \"mode\"")
    assert "if action == \"back\":\n        # All Back edges" in source
    assert "if not callback_answered:\n                        await query.answer()" in source


def test_product_video_entry_ack_precedes_language_lookup_and_avoids_storyboard_double_ack():
    source = _function_source("handle_video_product_callback")
    _index_pair(source, 'if action == "open" and value in {', "lang = get_user_language(uid) or \"vi\"")
    assert "if not callback_answered:" in source
    assert 'and not callback_answered:' in source


def test_prompt_library_entry_ack_precedes_language_lookup():
    source = _function_source("handle_video_prompt_library_callback")
    _index_pair(source, "await query.answer()", "lang = get_user_language(uid) or \"vi\"")


def test_video_editor_hub_ack_precedes_language_lookup():
    source = _function_source("handle_video_editor_callback")
    _index_pair(source, 'if raw_action == "hub"', "lang = get_user_language(uid) or \"vi\"")
    _index_pair(source, "await query.answer()", "lang = get_user_language(uid) or \"vi\"")


def test_video_planner_open_ack_precedes_lock_and_delivery_does_not_ack_twice():
    handler = _function_source("_handle_option_c_video_planning_callback")
    ack_marker = 'if verb in {"open", "back"} and not _transaction_locked:'
    ack_index = handler.index(ack_marker)
    lock_index = handler.index('if not _transaction_locked:', ack_index)
    assert "await _local_video_studio_ack_navigation(query)" in handler[ack_index:lock_index]
    assert ack_index < lock_index

    deliver = _function_source("_local_video_studio_public_deliver")
    _index_pair(
        deliver,
        "if _local_video_studio_callback_was_answered(query):",
        'responder = getattr(query, "answer", None)',
    )
    assert "query.answer(" not in handler


def test_video_product_navigation_allowlist_covers_visible_public_entries():
    source = _function_source("handle_video_product_callback")
    for value in (
        "video_trend",
        "script_image_video",
        "video_reference",
        "motion_prompt",
        "frame_video_local",
        "self_shot_scene_change",
        "storyboard_prompt",
    ):
        assert f'"{value}"' in source


def test_menu_video_root_ack_precedes_admin_lookup_and_shared_cleanup():
    source = _function_source("handle_menu_callback")
    fast_path = source.index('menu_fast_path = action in {"main", "main_video", "guide_video_ai"}')
    early_ack = source.index("await query.answer()", fast_path)
    admin_lookup = source.index("user_is_admin = is_admin_user(query.from_user.id)", fast_path)
    shared_cleanup = source.index("clear_media_creator_pending_states(", fast_path)
    assert early_ack < admin_lookup < shared_cleanup
    assert "if not menu_callback_answered:\n        menu_ack_start" in source


def test_ack_fast_path_is_navigation_only_and_does_not_add_provider_or_wallet_calls():
    fast_path = SOURCE[
        SOURCE.index("# A valid Video entry must acknowledge"):
        SOURCE.index("state = start_video_uiflow3_state(context, product)")
    ]
    fast_path = "\n".join(
        line for line in fast_path.splitlines() if not line.lstrip().startswith("#")
    )
    for forbidden in ("create_job(", "submit(", "charge(", "httpx", "requests"):
        assert forbidden not in fast_path.lower()
