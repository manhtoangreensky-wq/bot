import inspect
import json

import bot
import video_image_to_video_flow as ivf


def test_img2vid_path_a_existing_images_menu_exists():
    markup = ivf.frame_video_unified_menu_keyboard("vi")
    buttons = [button for row in markup.inline_keyboard for button in row]
    labels = [button.text for button in buttons]
    callbacks = [button.callback_data for button in buttons]
    assert "📤 Dùng ảnh có sẵn" in labels
    assert "✨ Tạo ảnh AI nhanh rồi ghép" in labels
    assert "framevideo|start" in callbacks
    assert "framevideo|ai_first" in callbacks
    assert all("storyboard" not in str(callback).lower() for callback in callbacks)
    assert all("vproduct|open" not in str(callback).lower() for callback in callbacks)


def test_img2vid_path_a_calculates_total_duration():
    state = {"img2vid_lock1": True, "photos": [{}, {}, {}, {}], "seconds_per_image": 2}
    price = bot.img2vid_slideshow_price_for_state(state)
    assert price["total_seconds"] == 8
    assert price["duration_seconds"] == 8


def test_img2vid_path_a_free_under_3_images_6s():
    assert bot.img2vid_slideshow_price_breakdown(3, 2)["total"] == 0


def test_img2vid_path_a_price_8s_20xu():
    assert bot.img2vid_slideshow_price_breakdown(4, 2)["total"] == 20


def test_img2vid_path_a_price_12s_56xu():
    assert bot.img2vid_slideshow_price_breakdown(6, 2)["total"] == 56


def test_img2vid_path_a_price_25s_150xu():
    assert bot.img2vid_slideshow_price_breakdown(5, 5)["total"] == 150


def test_img2vid_path_a_uses_local_slideshow_not_ai_video_provider():
    state = {
        "img2vid_lock1": True,
        "mode": "existing_images",
        "photos": [{"file_id": "a"}, {"file_id": "b"}],
        "seconds_per_image": 2,
        "ratio": "9x16",
        "effect": "fade",
    }
    payload = json.loads(bot.frame_video_worker_payload("fv-test", 1, 2, state, 20))
    assert payload["seconds_per_image"] == 2
    assert payload["img2vid_lock1"] is True
    assert payload["ai_video_provider_called"] is False
    assert payload["storyboard_route_called"] is False
    assert "Local Worker" not in payload["caption"]


def test_img2vid_path_b_ai_image_menu_exists():
    markup = ivf.frame_video_ai_first_keyboard("vi")
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "framevideo|ai_prompt" in callbacks
    assert "menu|main_image" not in callbacks
    assert "vproduct|open|storyboard_prompt" not in callbacks


def test_img2vid_path_b_generated_prompts_are_related_to_base_prompt():
    prompts = bot.img2vid_image_prompt_variants("xay sinh tố xoài", 4)
    assert len(prompts) == 4
    assert all("xay sinh tố xoài" in prompt for prompt in prompts)
    assert len(set(prompts)) == 4


def test_img2vid_path_b_image_price_confirm_before_generation():
    text = bot.img2vid_ai_confirm_text({"ai_prompt": "nấu ăn", "ai_image_count": 3})
    assert "Số ảnh" in text
    assert "Giá ảnh" in text
    assert "Tổng Xu" in text
    assert "Prompt" in text


def test_img2vid_path_b_shows_button_to_stitch_generated_images():
    markup = bot.img2vid_generated_images_keyboard()
    labels = [button.text for row in markup.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "🎞 Ghép các ảnh này thành video" in labels
    assert "framevideo|ai_stitch_generated" in callbacks


def test_img2vid_path_b_video_price_confirm_after_images():
    text = bot.img2vid_slideshow_confirm_text(
        {"img2vid_lock1": True, "photos": [{}, {}, {}, {}], "seconds_per_image": 2},
        1,
    )
    assert "Số ảnh" in text
    assert "Giây mỗi ảnh" in text
    assert "Tổng thời lượng" in text
    assert "Giá video" in text
    assert "Không dùng AI dựng cảnh" in text


def test_img2vid_lock_not_storyboard_or_product_video_ai():
    source = inspect.getsource(bot.handle_frame_video_callback)
    assert "vproduct|open|storyboard_prompt" not in source
    assert "menu|main_image" not in source
    assert "shopaikey_video" not in source.lower()
    assert "key4u_video" not in source.lower()


def test_img2vid_lock_frame_video_local_opens_two_path_menu():
    text_source = inspect.getsource(bot.task3d_product_intro_text)
    keyboard_source = inspect.getsource(bot.task3d_product_intro_keyboard)
    assert '"frame_video_local"' in text_source
    assert "frame_video_unified_menu_text" in text_source
    assert "frame_video_unified_menu_keyboard" in keyboard_source


def test_img2vid_lock_back_button_to_video_menu():
    markup = ivf.frame_video_unified_menu_keyboard("vi")
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "menu|main_video" in callbacks
    assert "framevideo|main" in callbacks


def test_img2vid_debug_registered():
    source = inspect.getsource(bot)
    assert 'CommandHandler("img2vid_debug", cmd_img2vid_debug)' in source
    assert "def cmd_img2vid_debug" in source


def test_img2vid_no_music_runtime_changes():
    source = inspect.getsource(bot.handle_frame_video_callback)
    assert "music_provider" not in source
    assert "suno" not in source.lower()
