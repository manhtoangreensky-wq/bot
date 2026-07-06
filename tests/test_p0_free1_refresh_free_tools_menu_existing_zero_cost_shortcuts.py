import asyncio
import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
from free_tools_hub import prompt_library_counts


ROOT = Path(bot.__file__).resolve().parent


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def _labels(markup):
    return [button.text for button in _buttons(markup)]


def _callbacks(markup):
    return [button.callback_data for button in _buttons(markup) if button.callback_data]


def _free_menu():
    return bot.free_hub_main_keyboard("vi")


def _free_handler_source():
    return inspect.getsource(bot.handle_free_hub_callback)


def _git_status_paths():
    result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("git status unavailable for scope guard")
    paths = []
    for line in result.stdout.splitlines():
        path = line[3:].strip()
        if path.startswith((".pytest_cache/", "__pycache__/")) or "/__pycache__/" in path:
            continue
        paths.append(path.replace("\\", "/"))
    return paths


def _git_diff_bot():
    result = subprocess.run(
        ["git", "diff", "--", "bot.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("git diff unavailable for scope guard")
    return result.stdout


def _git_branch_name() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return (result.stdout or "").strip().lower()


def _is_subdub_branch() -> bool:
    branch = _git_branch_name()
    return any(token in branch for token in ("p0-19m", "subdub", "subtitle-dub", "subtitle_dub"))


def test_free_tools_menu_title_updated():
    assert "🆓 <b>Công cụ miễn phí TOAN AAS</b>" in bot.free_hub_main_text("vi")


def test_free_tools_menu_copy_explains_zero_xu_helpers_and_paid_confirmation():
    text = bot.free_hub_main_text("vi")
    assert "0 Xu/miễn phí" in text
    assert "chuẩn bị nội dung" in text
    assert "báo giá và hỏi xác nhận riêng trước khi trừ Xu" in text
    for forbidden in ("provider", "api", "debug", "endpoint", "token", "webhook"):
        assert forbidden not in text.lower()


def test_old_free_tools_buttons_still_present_if_valid():
    labels = _labels(_free_menu())
    for label in [
        "🤖 Prompt Meta AI",
        "✍️ Caption/Hashtag",
        "🧠 Ý tưởng content",
        "🖼 Prompt ảnh/video",
        "📦 Gói đăng bài",
        "📚 Kho prompt mẫu",
        "📝 Ghi chú / Tài liệu",
        "📥 Lưu media tạm",
    ]:
        assert label in labels


def test_current_existing_free_music_helper_shortcut_included_if_verified():
    labels = _labels(_free_menu())
    callbacks = _callbacks(_free_menu())
    assert "🎵 Ý tưởng nhạc/SFX" in labels
    assert "freehub|lib_music" in callbacks
    assert bot.FREE_HUB_LIBRARY_CATEGORIES["music"][0] == "music_sfx"
    assert prompt_library_counts(bot.FREE_PROMPT_LIBRARY)["music_sfx"] > 0


def test_current_existing_voice_and_subtitle_subdub_helper_shortcut_included_if_verified():
    labels = _labels(_free_menu())
    callbacks = _callbacks(_free_menu())
    assert "🎙 Script voice/SubDub" in labels
    assert "freehub|hook" in callbacks
    assert '"hook": "hook_script"' in _free_handler_source()


def test_current_existing_image_video_prompt_helper_shortcut_included_if_verified():
    labels = _labels(_free_menu())
    callbacks = _callbacks(_free_menu())
    assert "🖼 Prompt ảnh/video" in labels
    assert "freehub|prompts" in callbacks


def test_notes_media_and_support_free_shortcuts_included():
    labels = _labels(_free_menu())
    callbacks = _callbacks(_free_menu())
    assert "📝 Ghi chú / Tài liệu" in labels
    assert "📥 Lưu media tạm" in labels
    assert "🧑‍💼 Hỗ trợ" in labels
    assert "💬 Góp ý / Báo lỗi" in labels
    assert {"menu|main_memory", "freehub|upload", "support|start", "feedback|start"}.issubset(set(callbacks))


def test_every_new_button_callback_resolves_to_existing_handler_or_safe_screen():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    handler = _free_handler_source()
    for callback in _callbacks(_free_menu()):
        if callback in {"menu|main", "menu|main_memory"}:
            assert 'CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|")' in source
            continue
        if callback == "support|start":
            assert 'CallbackQueryHandler(handle_human_support_callback, pattern=r"^support\\|")' in source
            continue
        if callback == "feedback|start":
            assert 'CallbackQueryHandler(handle_feedback_callback, pattern=r"^feedback\\|")' in source
            continue
        assert callback.startswith("freehub|")
        action = callback.split("|", 1)[1]
        if action.startswith("lib_"):
            assert action.replace("lib_", "", 1) in bot.FREE_HUB_LIBRARY_CATEGORIES
        else:
            assert f'"{action}"' in handler


def test_no_dead_buttons_and_layout_max_two_columns():
    markup = _free_menu()
    callbacks = _callbacks(markup)
    assert callbacks
    assert all(callback for callback in callbacks)
    assert len(callbacks) == len(set(callbacks))
    assert all(len(row) <= 2 for row in markup.inline_keyboard)
    assert _labels(markup).count("🏠 Menu chính") == 1


def test_free_tools_shortcuts_do_not_charge_wallet():
    source = _free_handler_source()
    for forbidden in (
        "spend_fixed_credit_info(",
        "spend_fixed_credit(",
        "deduct_dynamic_credit(",
        "deduct_package_item_for_job(",
        "confirm_video_project_invoice(",
    ):
        assert forbidden not in source


def test_free_tools_shortcuts_do_not_submit_provider_jobs():
    source = _free_handler_source()
    for forbidden in (
        "create_shopaikey_job(",
        "submit_public_video_with_key4u_fallback(",
        "execute_video_dubbing_pipeline(",
        "send_standalone_tts_result(",
        "music_ai_confirm",
    ):
        assert forbidden not in source


def test_free_tools_shortcuts_do_not_start_paid_music_generation():
    callbacks = _callbacks(_free_menu())
    assert not any(callback.startswith("music_quick|") for callback in callbacks)
    assert "music_ai_confirm" not in _free_handler_source()


def test_free_tools_shortcuts_do_not_start_paid_video_generation():
    callbacks = _callbacks(_free_menu())
    assert not any(callback.startswith(("vproduct|", "vfinal|", "videoaddon|", "job|", "prov|")) for callback in callbacks)
    assert "submit_public_video_with_key4u_fallback(" not in _free_handler_source()


def test_free_tools_shortcuts_do_not_start_paid_subdub_processing():
    callbacks = _callbacks(_free_menu())
    assert not any(callback.startswith(("videodub|", "tr_target|", "tr_pick|")) for callback in callbacks)
    assert "execute_video_dubbing_pipeline(" not in _free_handler_source()


def test_free_tools_shortcuts_do_not_start_paid_tts():
    callbacks = _callbacks(_free_menu())
    assert not any("voice_default" in callback or "voice_tts" in callback for callback in callbacks)
    assert "send_standalone_tts_result(" not in _free_handler_source()


def test_back_button_returns_exactly_free_tools_menu_and_main_returns_main_menu():
    direct_subpages = [
        bot.free_hub_input_keyboard("vi"),
        bot.free_hub_prompts_keyboard("vi"),
        bot.free_hub_library_keyboard("vi"),
        bot.free_hub_library_suggestions_keyboard("vi"),
        bot.free_hub_library_item_keyboard("vi"),
        bot.free_hub_notes_keyboard("vi"),
        bot.free_hub_docs_keyboard("vi"),
    ]
    for markup in direct_subpages:
        callbacks = _callbacks(markup)
        assert "freehub|main" in callbacks
        assert "menu|main" in callbacks
    assert _callbacks(_free_menu())[-1] == "menu|main"


def test_normal_user_can_open_menu(monkeypatch):
    monkeypatch.setattr(bot, "FREE_HUB_ENABLED", True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")

    class FakeQuery:
        data = "freehub|main"
        from_user = SimpleNamespace(id=44001, username="normal", first_name="Normal")
        message = SimpleNamespace(chat_id=44001)

        def __init__(self):
            self.edited = {}

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
            self.edited = {"text": text, "parse_mode": parse_mode, "reply_markup": reply_markup}
            return self.edited

    query = FakeQuery()
    asyncio.run(bot.handle_free_hub_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert "Công cụ miễn phí TOAN AAS" in query.edited["text"]
    assert "freehub|meta" in _callbacks(query.edited["reply_markup"])
    assert "menu|main" in _callbacks(query.edited["reply_markup"])


def test_free_tools_refresh_does_not_touch_music_runtime():
    diff = _git_diff_bot()
    for marker in ('if action == "music_ai_confirm":', "async def handle_music_quick_callback", "def music_ai_preview_text"):
        assert marker not in diff


def test_free_tools_refresh_does_not_touch_product_video_runtime():
    diff = _git_diff_bot()
    for marker in ("async def handle_video_product_callback", "submit_public_video_with_key4u_fallback", "run_multiscene_video_job"):
        assert marker not in diff


def test_free_tools_refresh_does_not_touch_subdub_runtime():
    if _is_subdub_branch():
        pytest.skip("SubDub task is allowed to touch SubDub runtime without weakening Free Tools guard.")
    diff = _git_diff_bot()
    for marker in ("async def handle_video_dubbing_callback", "execute_video_dubbing_pipeline", "_execute_video_dubbing_pipeline_core"):
        assert marker not in diff


def test_free_tools_refresh_does_not_touch_voice_runtime():
    diff = _git_diff_bot()
    for marker in ("send_standalone_tts_result", "create_minimax_voice_profile_preview", "voice_clone"):
        assert marker not in diff


def test_free_tools_refresh_does_not_touch_payos_pricing_db_webhook():
    changed_paths = _git_status_paths()
    forbidden_paths = ("providers/", "services/product_progress_status.py", "remote_worker.py", "local_worker.py")
    assert not any(path.startswith(forbidden_paths) for path in changed_paths)
    diff = _git_diff_bot()
    for marker in ("payos", "payment webhook", "pricing", "db_connect", "webhook"):
        assert marker not in diff.lower()
