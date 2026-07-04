import asyncio
import re
import subprocess
from types import SimpleNamespace

import bot


USER_ID = 232814


class CaptureMessage:
    def __init__(self, chat_id=USER_ID):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text or ""), **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))


class CaptureQuery:
    def __init__(self, data, user_id=USER_ID):
        self.data = data
        self.message = CaptureMessage(chat_id=user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _update(data, user_id=USER_ID):
    return SimpleNamespace(callback_query=CaptureQuery(data, user_id), effective_user=SimpleNamespace(id=user_id))


def _labels(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _callbacks(markup):
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


def _flat_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _select_voice(vocal="female", user_id=USER_ID):
    bot.save_music_guided_result(user_id, {
        "music_product_flow": "p0_20a_3_tier",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
    })
    update = _update(f"music_quick|showroom|music_vocal:{vocal}", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    return update


def _prepared_state(vocal="female", user_id=USER_ID):
    state = {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "song_vocal": vocal,
        "vocal_mode": vocal,
        "requested_vocal_mode": vocal,
        "selected_vocal_mode": vocal,
        "music_user_idea": "Bai hat thuong hieu TOAN AAS vui tuoi",
    }
    prepared = bot.music_product_prepare_suggestions_result(state, idea=state["music_user_idea"], offset=0, lang="vi")
    bot.save_music_guided_result(user_id, prepared)
    return prepared


def _song_result(vocal="female", **extra):
    data = {
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "song_vocal": vocal,
        "vocal_mode": vocal,
        "requested_vocal_mode": vocal,
        "selected_vocal_mode": vocal,
        "theme": "Bai hat thuong hieu TOAN AAS",
        "lyrics": "[Verse]\nTOAN AAS sang ngay\n[Chorus]\nCung nhau vuon xa",
        "style_prompt": "Vietnamese pop, bright chorus",
    }
    data.update(extra)
    return bot.music_product_result_from_input(data)


def test_female_voice_uses_same_generation_path_as_male(monkeypatch):
    saved = []
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: saved.append(dict(payload)) or dict(payload))
    female = bot.create_music_pending_submit_job(user_id=USER_ID, chat_id=USER_ID, result=_song_result("female"))
    male = bot.create_music_pending_submit_job(user_id=USER_ID + 1, chat_id=USER_ID + 1, result=_song_result("male"))
    assert female["feature"] == male["feature"] == "music_suno"
    assert female["confirm_handler_name"] == male["confirm_handler_name"]
    assert female["product_type"] == male["product_type"] == "music_song"
    assert female["selected_vocal_mode"] == "female"
    assert male["selected_vocal_mode"] == "male"


def test_female_voice_state_survives_idea_screen():
    _reset()
    update = _select_voice("female")
    state = bot.get_music_guided_result(USER_ID)
    assert state["requested_vocal_mode"] == "female"
    assert state["selected_vocal_mode"] == "female"
    assert state["vocal_mode_source"] == "user_selection"
    assert "Ý tưởng bài hát" in update.callback_query.message.outputs[-1]["text"]


def test_female_voice_state_survives_suggestion_selection():
    state = _prepared_state("female")
    selected = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    assert selected["selected_vocal_mode"] == "female"
    assert selected["requested_vocal_mode"] == "female"
    assert bot.music_product_prompt_contains_vocal_hint(selected["provider_style_prompt"], "female")


def test_female_voice_state_survives_custom_lyrics():
    result = _song_result("female", vocal_mode="male", selected_vocal_mode="female", requested_vocal_mode="female")
    assert result["selected_vocal_mode"] == "female"
    assert result["song_vocal"] == "female"
    assert "female" in result["provider_style_prompt"].lower()
    assert not re.search(r"\bmale\s+(lead\s+)?vocal\b", result["provider_style_prompt"], flags=re.I)


def test_female_voice_prompt_contains_female_vocal_hint():
    result = _song_result("female")
    assert result["prompt_contains_female_vocal_hint"] is True
    assert result["provider_prompt_contains_voice_hint"] is True


def test_female_voice_provider_payload_valid(monkeypatch):
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))
    job = bot.create_music_pending_submit_job(user_id=USER_ID, chat_id=USER_ID, result=_song_result("female"))
    assert job["provider_payload_valid"] is True
    assert job["lyrics_present"] is True
    assert job["style_prompt_present"] is True
    assert job["female_flow_source"] == "restored_pr173/current_shared_path"


def test_female_voice_does_not_jump_80_then_fail_without_artifact_reason(monkeypatch):
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))
    job = bot.create_music_pending_submit_job(user_id=USER_ID, chat_id=USER_ID, result=_song_result("female"))
    assert job["progress_percent"] == 5
    assert job["last_provider_status"] == "provider_submit_not_called"
    assert job["provider_payload_valid"] is True
    assert job["female_regression_fixed"] == "yes"


def test_female_voice_progress_matches_male_lifecycle():
    female_state = bot.product_progress_state_from_job("music_song", {
        "internal_job_id": "MUS-FEMALE",
        "status": "completed",
        "provider_task_id": "task-f",
        "provider_style_prompt": "female vocal pop",
        "provider_lyrics": "lyrics",
        "output_bytes": 2048,
        "audio_validated": True,
        "delivery_succeeded": True,
        "terminal_state": "delivered",
    })
    male_state = bot.product_progress_state_from_job("music_song", {
        "internal_job_id": "MUS-MALE",
        "status": "completed",
        "provider_task_id": "task-m",
        "provider_style_prompt": "male vocal pop",
        "provider_lyrics": "lyrics",
        "output_bytes": 2048,
        "audio_validated": True,
        "delivery_succeeded": True,
        "terminal_state": "delivered",
    })
    assert female_state["percent"] == male_state["percent"] == 100
    assert female_state["current_stage"] == male_state["current_stage"]


def test_male_voice_still_generates_single_audio():
    result = _song_result("male")
    assert result["selected_vocal_mode"] == "male"
    assert result["provider_payload_valid"] is True
    assert result["provider_style_prompt"].lower().count("male") >= 1


def test_male_voice_no_duplicate_delivery():
    job = {
        "internal_job_id": "MUS-MALE-LOCK",
        "terminal_state": "delivered",
        "delivery_succeeded": True,
        "music_result_delivered_once": True,
        "send_attempt_count": 1,
    }
    assert bot.music_job_delivered(job) is True
    assert int(job["send_attempt_count"]) == 1


def test_male_voice_success_panel_charge_copy_clean():
    text = bot.product_progress_status_from_job_text("music_song", {
        "internal_job_id": "MUS-MALE-PANEL",
        "terminal_state": "delivered",
        "delivery_succeeded": True,
        "provider_style_prompt": "male vocal pop",
        "provider_lyrics": "lyrics",
        "charged_xu": 200,
    }, "MUS-MALE-PANEL", "vi")
    assert "100%" in text
    assert "provider_voice_id" not in text
    assert "traceback" not in text.lower()


def test_duet_voice_state_survives_idea_screen():
    _reset()
    _select_voice("duet")
    state = bot.get_music_guided_result(USER_ID)
    assert state["selected_vocal_mode"] == "duet"
    assert state["duet_enabled"] is not False


def test_duet_voice_state_survives_custom_lyrics():
    result = _song_result("duet")
    assert result["selected_vocal_mode"] == "duet"
    assert "[Male Verse]" in result["provider_lyrics"]
    assert "[Female Verse]" in result["provider_lyrics"]


def test_duet_prompt_contains_male_female_duet_hint():
    result = _song_result("duet")
    assert "male and female duet" in result["provider_style_prompt"].lower()
    assert result["prompt_contains_duet_vocal_hint"] is True


def test_duet_routes_to_generation_without_prompt_loop(monkeypatch):
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))
    job = bot.create_music_pending_submit_job(user_id=USER_ID, chat_id=USER_ID, result=_song_result("duet"))
    assert job["feature"] == "music_suno"
    assert job["selected_vocal_mode"] == "duet"
    assert job["provider_payload_valid"] is True


def test_music_idea_screen_has_two_buttons_first_row():
    markup = bot.music_product_idea_keyboard("song", "vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    assert _labels(markup)[0] == ["✨ Gợi ý mẫu", "✍️ Nhập lời"]


def test_music_idea_screen_short_labels():
    labels = [label for row in _labels(bot.music_product_idea_keyboard("song", "vi", bot.PRODUCT_CONTEXT_SHOWROOM)) for label in row]
    assert "✨ Dùng ý tưởng mẫu TOAN AAS" not in labels
    assert "✍️ Tự nhập lời bài hát" not in labels
    assert all(len(label) <= 14 or label in {"🏠 Menu chính"} for label in labels)


def test_idea_screen_suggestion_button_still_works():
    callbacks = _flat_callbacks(bot.music_product_idea_keyboard("song", "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "music_quick|showroom|music_product_sample_idea" in callbacks


def test_idea_screen_manual_lyrics_button_still_works():
    callbacks = _flat_callbacks(bot.music_product_idea_keyboard("song", "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "music_quick|showroom|music_product_manual" in callbacks


def test_compact_idea_screen_preserves_female_voice():
    _reset()
    _select_voice("female")
    update = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert bot.get_music_guided_result(USER_ID)["selected_vocal_mode"] == "female"


def test_compact_idea_screen_preserves_male_voice():
    _reset()
    _select_voice("male")
    update = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert bot.get_music_guided_result(USER_ID)["selected_vocal_mode"] == "male"


def test_compact_idea_screen_preserves_duet_voice():
    _reset()
    _select_voice("duet")
    update = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert bot.get_music_guided_result(USER_ID)["selected_vocal_mode"] == "duet"


def test_compact_idea_screen_does_not_create_job_or_charge(monkeypatch):
    _reset()
    _select_voice("female")
    created = []
    charged = []
    monkeypatch.setattr(bot, "create_music_pending_submit_job", lambda *args, **kwargs: created.append((args, kwargs)) or {})
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: charged.append((args, kwargs)) or {"ok": False})
    update = _update("music_quick|showroom|music_product_manual")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert created == []
    assert charged == []


def test_current_download_engine_not_rewritten():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    assert "providers/key4u_provider.py" not in changed
    assert "local_worker.py" not in changed
    assert "remote_worker.py" not in changed


def test_no_product_video_subdub_payos_pricing_db_changes():
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
