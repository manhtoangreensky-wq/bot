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


def _git_branch_paths():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _git_diff_file(path):
    result = subprocess.run(
        ["git", "diff", "origin/main...HEAD", "--", path],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout:
        result = subprocess.run(
            ["git", "diff", "--", path],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    if result.returncode != 0:
        pytest.skip(f"git diff unavailable for {path}")
    return result.stdout


def _local_worker_change_is_img2vid_only():
    diff = _git_diff_file("local_worker.py")
    if not diff:
        return True
    forbidden_markers = (
        "music",
        "suno",
        "subdub",
        "subtitle",
        "dub",
        "payos",
        "wallet",
        "provider",
        "video_provider",
        "remote_worker",
    )
    added_removed = "\n".join(
        line for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    )
    return (
        "run_frame_video_render" in diff
        and "len(photos) < 2" in diff
        and "len(photos) < 1" in diff
        and not any(marker in added_removed.lower() for marker in forbidden_markers)
    )


def _local_worker_change_is_video_local1_only():
    diff = _git_diff_file("local_worker.py")
    if not diff:
        return True
    changed_paths = set(_git_status_paths()) | set(_git_branch_paths())
    if "tests/test_p0_video_local1_manual_editing_smart_splitter.py" not in changed_paths:
        return False
    added_removed = "\n".join(
        line for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    ).lower()
    required = ("run_video_local_edit", "execute_manual_edit", "execute_split_plan", "create_job_workspace")
    forbidden = ("music", "suno", "subdub", "payos", "wallet", "remote_worker", "video_provider_router")
    return all(marker in diff for marker in required) and not any(marker in added_removed for marker in forbidden)


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


def _bot_change_is_img2vid_copy_only(diff: str) -> bool:
    if not diff:
        return True
    added_removed = "\n".join(
        line for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    )
    required = ("frame_video_ai_first_guard_text", "Tạo ảnh AI trước", "Create AI images first")
    forbidden = (
        "submit_public_video_with_key4u_fallback",
        "run_multiscene_video_job",
        "provider_router",
        "video_provider",
        "music",
        "suno",
        "subdub",
        "payos",
        "wallet",
    )
    return all(marker in diff for marker in required) and not any(marker in added_removed for marker in forbidden)


def _bot_change_is_video_uiflow1_only(diff: str) -> bool:
    if not diff:
        return True
    added_removed = "\n".join(
        line for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    ).lower()
    required = (
        "VIDEO_UIFLOW1_CANONICAL_SEQUENCE",
        "VIDEO_UIFLOW1_CANONICAL_PROFILE_PRODUCTS",
        "video_uiflow1_canonical_flow_map",
        '"storyboard_preview": "b14_creative_controls"',
    )
    forbidden = (
        "submit_public_video_with_key4u_fallback",
        "run_multiscene_video_job",
        "provider_router",
        "video_provider",
        "music",
        "suno",
        "subdub",
        "payos",
        "wallet",
    )
    return all(marker in diff for marker in required) and not any(marker in added_removed for marker in forbidden)


def _bot_change_is_video_local1_only(diff: str) -> bool:
    if not diff:
        return True
    changed_paths = set(_git_status_paths()) | set(_git_branch_paths())
    if "tests/test_p0_video_local1_manual_editing_smart_splitter.py" not in changed_paths:
        return False
    added_removed = "\n".join(
        line for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    ).lower()
    required = (
        "handle_video_editor_callback",
        "submit_local_video_editor_job",
        "video_local_status_payload",
        'job_type="video_local_edit"',
    )
    forbidden = (
        "payos",
        "payment webhook",
        "pricing",
        "wallet",
        "submit_public_video_with_key4u_fallback",
        "video_provider_router",
        "music_ai_confirm",
        "execute_video_dubbing_pipeline",
        "send_standalone_tts_result",
    )
    return all(marker in diff for marker in required) and not any(marker in added_removed for marker in forbidden)


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
        if marker == "async def handle_video_product_callback" and (
            _bot_change_is_img2vid_copy_only(diff) or _bot_change_is_video_uiflow1_only(diff)
        ):
            continue
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
    changed_paths = set(_git_status_paths()) | set(_git_branch_paths())
    forbidden_paths = ("providers/", "services/product_progress_status.py", "remote_worker.py")
    assert not any(path.startswith(forbidden_paths) for path in changed_paths)
    if "local_worker.py" in changed_paths:
        assert _local_worker_change_is_img2vid_only() or _local_worker_change_is_video_local1_only()
    diff = _git_diff_bot()
    if _bot_change_is_video_local1_only(diff):
        added_removed = "\n".join(
            line for line in diff.splitlines()
            if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
        ).lower()
        for marker in ("payos", "payment webhook", "pricing", "wallet", "webhook"):
            assert marker not in added_removed
        return
    for marker in ("payos", "payment webhook", "pricing", "db_connect", "webhook"):
        assert marker not in diff.lower()
