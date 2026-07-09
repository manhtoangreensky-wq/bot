from pathlib import Path
import re


BOT_SOURCE = Path("bot.py").read_text(encoding="utf-8")


def _block(start_marker: str, end_marker: str) -> str:
    start = BOT_SOURCE.index(start_marker)
    end = BOT_SOURCE.index(end_marker, start)
    return BOT_SOURCE[start:end]


def _command_registered(command: str, handler: str) -> bool:
    return bool(re.search(rf'CommandHandler\("{re.escape(command)}",\s*{handler}\)', BOT_SOURCE))


def test_public_botfather_alias_handlers_registered():
    expected = {
        "bot": "cmd_bot",
        "cskh": "cmd_cskh",
        "subdub": "cmd_subdub",
        "product_video": "cmd_product_video",
        "video": "cmd_video",
        "image": "cmd_image",
        "translate": "cmd_translate",
    }
    for command, handler in expected.items():
        assert _command_registered(command, handler)


def test_public_aliases_are_in_public_command_registry():
    registry = _block("PUBLIC_COMMAND_FUNCTIONS = {", "def public_command_exists")
    for command, handler in {
        "bot": "cmd_bot",
        "cskh": "cmd_cskh",
        "subdub": "cmd_subdub",
        "product_video": "cmd_product_video",
        "video": "cmd_video",
        "image": "cmd_image",
        "caption": "cmd_caption",
        "translate": "cmd_translate",
    }.items():
        assert f'"{command}": "{handler}"' in registry


def test_public_aliases_route_to_existing_menus_not_new_pipelines():
    alias_block = _block("async def reply_public_menu_alias", "def help_text_for_user")
    assert 'return await reply_public_menu_alias(update, "main_ai")' in alias_block
    assert "return await cmd_support(update, context)" in alias_block
    assert 'return await reply_public_menu_alias(update, "main_video")' in alias_block
    assert 'return await reply_public_menu_alias(update, "main_image")' in alias_block
    assert 'return await reply_public_menu_alias(update, "translation_video_factory")' in alias_block
    assert 'product_id = "video_ai_real"' in alias_block
    assert "task3d_product_intro_text(product_id, lang)" in alias_block
    assert "task3d_product_intro_keyboard(product_id, lang)" in alias_block


def test_product_video_alias_does_not_submit_or_charge():
    product_video_block = _block("async def cmd_product_video", "async def cmd_caption")
    assert "provider_called=False" in product_video_block
    assert "xu_charged=0" in product_video_block
    forbidden = [
        "call_ai_chat_with_fallback",
        "shopaikey_video_generate",
        "key4u_provider_instance().video_generation",
        "execute_engine(",
        "spend_fixed_credit_info",
        "charge_result",
        "render_real_video",
    ]
    for token in forbidden:
        assert token not in product_video_block


def test_caption_alias_is_menu_only_no_provider_call():
    caption_block = _block("async def cmd_caption", "def help_text_for_user")
    assert "main_ai_keyboard" in caption_block
    assert "call_ai_chat_with_fallback" not in caption_block
    assert "cmd_film(update, context)" not in caption_block
    assert "spend_fixed_credit_info" not in caption_block


def test_help_lists_public_command_groups():
    public_help = _block("def help_text_for_user", "if is_admin:")
    headings = [
        "Tài khoản & nạp Xu",
        "Bot AI/CSKH",
        "Nội dung/caption",
        "Ảnh AI",
        "Video AI/Product Video",
        "Phụ đề/Lồng tiếng",
        "Dịch ngôn ngữ/audio",
        "Nhạc/media",
    ]
    for heading in headings:
        assert heading in public_help
    for command in [
        "/bot",
        "/cskh",
        "/subdub",
        "/product_video",
        "/video",
        "/image",
        "/translate",
        "/caption",
        "/remove_bg",
        "/image_to_video_pack",
        "/music_library",
        "/translate_voice",
    ]:
        assert command in public_help


def test_public_help_does_not_expose_admin_debug_commands():
    public_help = _block("def help_text_for_user", "if is_admin:")
    forbidden = [
        "/runtime",
        "/providers",
        "/dashboard",
        "/pending",
        "/duyet",
        "/tuchoi",
        "/telegram_takeover",
        "/payos_test_plan",
        "/tool_audit",
    ]
    for command in forbidden:
        assert command not in public_help


def test_existing_public_commands_preserved():
    expected = {
        "start": "cmd_start",
        "help": "cmd_help",
        "profile": "cmd_profile",
        "pricing": "cmd_pricing",
        "naptien": "cmd_naptien",
        "thucong": "cmd_thanhtoan_thucong",
        "trial_status": "cmd_trial_status",
        "khuyenmai": "cmd_promo_guide",
        "promo": "cmd_promo",
        "ref": "cmd_ref",
        "gopy": "cmd_gopy",
        "caption": "cmd_caption",
        "remove_bg": "cmd_remove_bg_help",
        "image_to_video_pack": "cmd_image_to_video_pack",
        "music": "cmd_music_tools",
        "music_library": "cmd_music_library",
        "translate_voice": "cmd_translate_voice",
    }
    for command, handler in expected.items():
        assert _command_registered(command, handler)


def test_new_alias_wrappers_do_not_call_real_providers():
    alias_block = _block("async def reply_public_menu_alias", "def help_text_for_user")
    forbidden = [
        "call_ai_chat_with_fallback",
        "shopaikey",
        "key4u_provider",
        "submit",
        "poll_video_task",
        "run_subdub_pipeline",
        "spend_fixed_credit_info",
        "deduct",
    ]
    for token in forbidden:
        assert token not in alias_block
