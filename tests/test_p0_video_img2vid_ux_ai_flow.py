import re
from pathlib import Path

import video_image_to_video_flow as ivf


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _top_level_function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(index for index in starts if index >= 0)
    next_markers = []
    for marker in ("\ndef ", "\nasync def "):
        index = BOT_SOURCE.find(marker, start + 1)
        if index >= 0:
            next_markers.append(index + 1)
    end = min(next_markers) if next_markers else len(BOT_SOURCE)
    return BOT_SOURCE[start:end].rstrip()


def test_img2vid_hub_keeps_two_clear_paths_and_stable_rows():
    markup = ivf.frame_video_unified_menu_keyboard("vi")
    assert [len(row) for row in markup.inline_keyboard] == [2, 2]
    assert _labels(markup)[:2] == ["📤 Dùng ảnh có sẵn", "✨ Tạo ảnh AI nhanh rồi ghép"]
    assert _callbacks(markup) == [
        "framevideo|start",
        "framevideo|ai_first",
        "menu|main_video",
        "framevideo|main",
    ]


def test_ai_first_starts_with_idea_or_custom_prompt_not_a_text_dead_end():
    markup = ivf.frame_video_ai_first_keyboard("vi")
    assert [len(row) for row in markup.inline_keyboard] == [2, 2]
    assert _labels(markup) == [
        "💡 Chọn gợi ý",
        "✍️ Tự nhập prompt",
        "⬅️ Ghép ảnh thành video",
        "🏠 Menu chính",
    ]
    assert "framevideo|layout" not in _callbacks(markup)
    assert "framevideo|start" not in _callbacks(markup)


def test_ai_suggestions_are_five_number_buttons_on_one_row():
    markup = ivf.frame_video_ai_suggestions_keyboard("vi")
    assert [button.text for button in markup.inline_keyboard[0]] == ["1", "2", "3", "4", "5"]
    assert [button.callback_data for button in markup.inline_keyboard[0]] == [
        "framevideo|ai_pick|1",
        "framevideo|ai_pick|2",
        "framevideo|ai_pick|3",
        "framevideo|ai_pick|4",
        "framevideo|ai_pick|5",
    ]
    assert all(len(callback.encode("utf-8")) <= 64 for callback in _callbacks(markup))


def test_prompt_review_is_a_real_step_before_image_count():
    markup = ivf.frame_video_ai_prompt_keyboard("vi", suggestion_source=True)
    callbacks = _callbacks(markup)
    assert callbacks == [
        "framevideo|ai_count_menu",
        "framevideo|ai_prompt",
        "framevideo|ai_suggest",
        "framevideo|main",
    ]
    assert "giữ cùng chủ thể" in ivf.frame_video_ai_prompt_text("Bộ ảnh sản phẩm", "vi")


def test_back_routes_return_to_the_screen_that_opened_them():
    prompt_callbacks = _callbacks(ivf.frame_video_ai_custom_prompt_keyboard("vi"))
    suggestion_callbacks = _callbacks(ivf.frame_video_ai_suggestions_keyboard("vi"))
    collect_source = _top_level_function_source("frame_video_collect_keyboard")
    assert "framevideo|ai_first" in prompt_callbacks
    assert "framevideo|ai_first" in suggestion_callbacks
    assert 'callback_data="framevideo|hub"' in collect_source
    assert 'callback_data="menu|main_video"' not in collect_source


def test_handler_has_complete_ai_idea_prompt_count_sequence():
    source = _top_level_function_source("handle_img2vid_lock1_callback")
    for required in (
        'action in {"ai_suggest", "ai_refresh"}',
        'action == "ai_pick"',
        'state["step"] = "ai_prepared"',
        'action == "ai_prepared"',
        'action == "ai_count_menu"',
        'ivf.frame_video_ai_prompt_text',
        'ivf.frame_video_ai_suggestions_keyboard',
    ):
        assert required in source
    assert source.index('action == "ai_pick"') < source.index('action == "ai_count_menu"')


def test_ai_first_state_no_longer_skips_directly_to_prompt_input():
    source = _top_level_function_source("handle_frame_video_callback")
    block = source[source.index('if action == "ai_first"'):source.index('text = ivf.frame_video_layout_helper_text')]
    assert '"step": "ai_entry"' in block
    assert '"step": "ai_prompt"' not in block
    assert '"ai_suggestion_offset": 0' in block


def test_custom_prompt_returns_to_review_before_image_count():
    source = _top_level_function_source("handle_frame_video_pending_text")
    prompt_block = source[source.index('if step == "ai_prompt"'):source.index('if step == "ai_count_custom"')]
    assert 'state["step"] = "ai_prepared"' in prompt_block
    assert 'state["ai_prompt_source"] = "custom"' in prompt_block
    assert "frame_video_ai_prompt_text" in prompt_block
    assert "img2vid_ai_count_keyboard" not in prompt_block


def test_changed_functions_compile_in_isolation():
    names = (
        "img2vid_ai_count_keyboard",
        "img2vid_ai_suggestions",
        "img2vid_ai_prompt_from_topic",
        "frame_video_collect_keyboard",
        "handle_frame_video_pending_text",
        "handle_img2vid_lock1_callback",
        "handle_frame_video_callback",
    )
    for name in names:
        compile("from __future__ import annotations\n" + _top_level_function_source(name), f"<img2vid:{name}>", "exec")


def test_img2vid_ui_changes_do_not_call_ai_video_provider_or_charge_early():
    callback_source = _top_level_function_source("handle_img2vid_lock1_callback")
    ai_preparation = callback_source[:callback_source.index('if action == "ai_generate_confirm"')]
    assert "shopaikey_image_generate" not in ai_preparation
    assert "spend_fixed_credit_info" not in ai_preparation
    assert "shopaikey_video_create" not in callback_source
    assert "key4u_video" not in callback_source
    assert not re.search(r"create_(?:product_)?video_job", ai_preparation)
