import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

import bot
from aiedit1_scope_guard import aiedit1_local_worker_allowed


USER_ID = 232714


def _current_branch_name() -> str:
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    except Exception:
        return ""


def _is_music_scope_branch(branch: str) -> bool:
    lowered = str(branch or "").lower()
    return any(token in lowered for token in ("p0-20", "p0-23", "music", "suno"))


class CaptureMessage:
    def __init__(self, text="", chat_id=USER_ID):
        self.text = text
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": str(text or ""), **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))


class CaptureQuery:
    def __init__(self, data, user_id=USER_ID):
        self.data = data
        self.message = CaptureMessage(chat_id=user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _update(data, user_id=USER_ID):
    return SimpleNamespace(callback_query=CaptureQuery(data, user_id), effective_user=SimpleNamespace(id=user_id))


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _prepare_song_after_tier(user_id=USER_ID, vocal="female"):
    bot.save_music_guided_result(user_id, {
        "music_product_flow": "p0_20a_3_tier",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "song_vocal": vocal,
        "vocal_mode": vocal,
    })


def _select_voice_to_idea(user_id=USER_ID, vocal="female"):
    _prepare_song_after_tier(user_id, vocal="")
    update = _update(f"music_quick|showroom|music_vocal:{vocal}", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    return update


def test_custom_lyrics_button_visible_on_music_idea_screen_after_voice_selection():
    _reset()
    update = _select_voice_to_idea(vocal="female")
    output = update.callback_query.message.outputs[-1]
    assert "Ý tưởng bài hát" in output["text"]
    assert "nhập lời có sẵn" in output["text"]
    assert "✍️ Nhập lời" in _labels(output["reply_markup"])


def test_custom_lyrics_button_reuses_existing_lyrics_input_flow():
    markup = bot.music_product_idea_keyboard("song", "vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    assert "music_quick|showroom|music_product_manual" in _callbacks(markup)


def test_custom_lyrics_button_preserves_female_voice_state():
    _reset()
    _select_voice_to_idea(vocal="female")
    update = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    state = bot.get_music_guided_result(USER_ID)
    assert state["song_vocal"] == "female"
    assert "Giọng hát: <b>Nữ</b>" in update.callback_query.message.outputs[-1]["text"]
    assert "Style nhạc" in update.callback_query.message.outputs[-1]["text"]


def test_custom_lyrics_button_preserves_male_voice_state():
    _reset()
    _select_voice_to_idea(vocal="male")
    update = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    state = bot.get_music_guided_result(USER_ID)
    assert state["song_vocal"] == "male"
    assert "Giọng hát: <b>Nam</b>" in update.callback_query.message.outputs[-1]["text"]


def test_custom_lyrics_button_preserves_duet_voice_state():
    _reset()
    _select_voice_to_idea(vocal="duet")
    update = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    state = bot.get_music_guided_result(USER_ID)
    assert state["song_vocal"] == "duet"
    assert "Giọng hát: <b>Song ca</b>" in update.callback_query.message.outputs[-1]["text"]


def test_custom_lyrics_button_does_not_create_music_job(monkeypatch):
    _reset()
    _select_voice_to_idea(vocal="female")
    monkeypatch.setattr(bot, "create_music_pending_submit_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("job created before confirm")))
    update = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert "Style nhạc" in update.callback_query.message.outputs[-1]["text"]


def test_custom_lyrics_button_does_not_charge(monkeypatch):
    _reset()
    _select_voice_to_idea(vocal="female")
    charges = []
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: charges.append(args) or {"ok": False})
    update = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert charges == []


def test_back_from_lyrics_input_returns_to_idea_screen():
    _reset()
    _select_voice_to_idea(vocal="duet")
    manual = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(manual, SimpleNamespace()))
    callbacks = _callbacks(manual.callback_query.message.outputs[-1]["reply_markup"])
    assert "music_quick|showroom|music_product_back_idea" in callbacks
    back = _update("music_quick|showroom|music_product_back_idea")
    asyncio.run(bot.handle_music_quick_callback(back, SimpleNamespace()))
    state = bot.get_music_guided_result(USER_ID)
    assert state["song_vocal"] == "duet"
    assert "Ý tưởng bài hát" in back.callback_query.message.outputs[-1]["text"]


def test_style_then_lyrics_flow_preserves_female_voice_state():
    _reset()
    _select_voice_to_idea(vocal="female")
    manual = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(manual, SimpleNamespace()))
    assert "Style nhạc" in manual.callback_query.message.outputs[-1]["text"]

    style_message = CaptureMessage(
        text="Upbeat Tropical Pop, Female vocal, bright acoustic guitar, bouncy bass, healing vibes, 120 BPM",
        chat_id=USER_ID,
    )
    style_update = SimpleNamespace(message=style_message, effective_user=SimpleNamespace(id=USER_ID))
    asyncio.run(bot.handle_music_guided_pending_text(style_update, SimpleNamespace()))
    assert "Lời hát" in style_message.outputs[-1]["text"]
    state = bot.get_music_guided_result(USER_ID)
    assert state["selected_vocal_mode"] == "female"
    assert state["music_product_pending_lyrics"] is True

    lyrics_message = CaptureMessage(
        text="[Intro]\n(Ooh...)\n[Verse]\nTOAN AAS sang ngay\n[Chorus]\nCung nhau vuon xa",
        chat_id=USER_ID,
    )
    lyrics_update = SimpleNamespace(message=lyrics_message, effective_user=SimpleNamespace(id=USER_ID))
    asyncio.run(bot.handle_music_guided_pending_text(lyrics_update, SimpleNamespace()))
    result = bot.get_music_guided_result(USER_ID)
    assert result["selected_vocal_mode"] == "female"
    assert "Female vocal" in result["provider_style_prompt"]
    assert result["provider_lyrics"].startswith("[Intro]")
    assert "Xác nhận tạo bài hát" in lyrics_message.outputs[-1]["text"]


def test_back_from_idea_screen_returns_to_voice_selection():
    _reset()
    update = _select_voice_to_idea(vocal="male")
    callbacks = _callbacks(update.callback_query.message.outputs[-1]["reply_markup"])
    assert "music_quick|showroom|music_product_change_vocal" in callbacks
    back = _update("music_quick|showroom|music_product_change_vocal")
    asyncio.run(bot.handle_music_quick_callback(back, SimpleNamespace()))
    assert "Chọn giọng hát" in back.callback_query.message.outputs[-1]["text"]


def test_existing_suggestion_flow_still_works():
    _reset()
    _select_voice_to_idea(vocal="female")
    sample = _update("music_quick|showroom|music_product_sample_idea")
    asyncio.run(bot.handle_music_quick_callback(sample, SimpleNamespace()))
    state = bot.get_music_guided_result(USER_ID)
    assert len(state["music_suggestions"]) == 3
    assert state["song_vocal"] == "female"
    assert "TOAN AAS đã chuẩn bị 3 gợi ý bài hát" in sample.callback_query.message.outputs[-1]["text"]


def test_no_music_provider_engine_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    assert "providers/key4u_provider.py" not in changed
    assert (
        "local_worker.py" not in changed
        or _local_worker_change_is_img2vid_only()
        or aiedit1_local_worker_allowed(changed)
    )
    assert "remote_worker.py" not in changed


def _local_worker_change_is_img2vid_only() -> bool:
    diff = subprocess.check_output(
        ["git", "diff", "--unified=0", "origin/main", "--", "local_worker.py"],
        text=True,
        encoding="utf-8",
    ).lower()
    changed_lines = "\n".join(
        line for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    )
    forbidden = ("music", "suno", "subdub", "subtitle", "dub", "payos", "wallet", "provider", "video_provider")
    return (
        "run_frame_video_render" in diff
        and "len(photos) < 2" in diff
        and "len(photos) < 1" in diff
        and not any(marker in changed_lines for marker in forbidden)
    )


def test_no_product_video_subdub_payos_pricing_db_changes():
    if not _is_music_scope_branch(_current_branch_name()):
        pytest.skip("Music H14G scope guard is not active for this branch")
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    forbidden_prefixes = (
        "providers/video",
        "services/video",
        "services/subdub",
        "services/payos",
        "services/wallet",
        "services/payment",
        "config/pricing",
        "migrations/",
    )
    forbidden_exact = {"local_worker.py", "remote_worker.py", "providers/key4u_provider.py"}
    assert not [path for path in changed if path in forbidden_exact or path.startswith(forbidden_prefixes)]
