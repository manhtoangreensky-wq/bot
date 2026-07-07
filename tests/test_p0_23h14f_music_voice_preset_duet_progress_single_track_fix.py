import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

import bot


USER_ID = 232614
JOB_ID = "MUS14FVOICE"
AUDIO_BYTES = b"ID3-toan-aas-h14f-final-audio" * 260


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


class FakeBot:
    def __init__(self):
        self.audio = []
        self.sent = []

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        return SimpleNamespace(message_id=8100 + len(self.audio), audio=SimpleNamespace(file_id=f"audio-{len(self.audio)}"))

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=7100 + len(self.sent))


class CaptureMessage:
    def __init__(self, text="", chat_id=USER_ID):
        self.text = text
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": str(text or ""), **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))

    async def reply_audio(self, audio=None, filename="", caption="", **kwargs):
        self.outputs.append({"kind": "audio", "audio": audio, "filename": filename, "caption": caption, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs), audio=SimpleNamespace(file_id=f"reply-audio-{len(self.outputs)}"))


class CaptureQuery:
    def __init__(self, data, user_id=USER_ID):
        self.data = data
        self.message = CaptureMessage(chat_id=user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _ctx(fake=None):
    return SimpleNamespace(bot=fake or FakeBot())


def _update_with_query(data, user_id=USER_ID):
    return SimpleNamespace(callback_query=CaptureQuery(data, user_id), effective_user=SimpleNamespace(id=user_id))


def _message_update(message, user_id=USER_ID):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _song_state(user_id=USER_ID, tier=bot.MUSIC_PRODUCT_TIER_BASIC, vocal="female", idea="Bai hat thuong hieu TOAN AAS vui tuoi"):
    state = {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "song",
        "music_product_tier": tier,
        "song_vocal": vocal,
        "vocal_mode": vocal,
        "requested_vocal_mode": vocal,
        "selected_vocal_mode": vocal,
        "music_user_idea": idea,
    }
    prepared = bot.music_product_prepare_suggestions_result(state, idea=idea, offset=0, lang="vi")
    bot.save_music_guided_result(user_id, prepared)
    return prepared


def _result(vocal="female"):
    return {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "music_product_price_xu": 200,
        "provider_style_prompt": f"Vietnamese pop, bright chorus, {vocal} vocal",
        "provider_lyrics": "[Verse]\nTOAN AAS sang ngay\n[Chorus]\nCung nhau vuon xa",
        "song_vocal": vocal,
        "vocal_mode": vocal,
        "music_task_id": "provider-task-h14f",
        "music_internal_job_id": JOB_ID,
    }


def _job(vocal="female", job_id=JOB_ID):
    return {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "music_product_price_xu": 200,
        "song_vocal": vocal,
        "requested_vocal_mode": vocal,
        "selected_vocal_mode": vocal,
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-h14f",
        "provider_job_id": "provider-task-h14f",
        "status": "completed",
        "progress_percent": 90,
        "output_bytes": len(AUDIO_BYTES),
        "artifact_duration_seconds": 118,
        "music_result_duration_seconds": 118,
        "output_sha256": bot.music_audio_sha256(AUDIO_BYTES),
        "audio_validated": True,
        "artifact_ready": True,
        "music_audio_validated": True,
        "music_artifact_ready": True,
        "pending_charge_xu": 200,
        "charged_xu": 0,
    }


def _patch_store(monkeypatch, job=None, *, admin=True, charge_ok=True, charged=200):
    state = {"job": dict(job or _job()), "charges": []}

    async def fake_duration(*_args, **_kwargs):
        return 118

    def fake_save(payload):
        state["job"] = dict(payload)
        return dict(payload)

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(state["job"]) if _job_id == state["job"].get("internal_job_id") else {})
    monkeypatch.setattr(bot, "get_engine_async_job_lookup", lambda _job_id: {"job": dict(state["job"]), "resolved_job_id": state["job"].get("internal_job_id"), "lookup_found": True} if _job_id == state["job"].get("internal_job_id") else {"job": {}, "resolved_job_id": "", "lookup_found": False})
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-H14F", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-H14F"})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))

    def fake_spend(*args, **_kwargs):
        state["charges"].append(args)
        return {"ok": bool(charge_ok), "final_cost": charged if charge_ok else 0, "status": "ok" if charge_ok else "fail"}

    monkeypatch.setattr(bot, "spend_fixed_credit_info", fake_spend)
    return state


def _deliver(monkeypatch, fake=None, result=None, job=None, *, admin=True, source="auto_tick", send_success=True):
    state = _patch_store(monkeypatch, job or _job(), admin=admin)
    fake = fake or FakeBot()
    delivered = asyncio.run(
        bot.deliver_music_result_once(
            CaptureMessage(chat_id=USER_ID),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=result or _result(),
            audio_bytes=AUDIO_BYTES,
            job=state["job"],
            updated_by=USER_ID,
            send_success_message=send_success,
            source=source,
        )
    )
    return delivered, fake, state


def test_female_voice_survives_suggested_prompt_change():
    _reset()
    _song_state(vocal="female")
    update = _update_with_query("music_quick|showroom|music_product_regenerate_suggestions")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    state = bot.get_music_guided_result(USER_ID)
    selected = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    assert state["song_vocal"] == "female"
    assert selected["selected_vocal_mode"] == "female"
    assert selected["provider_prompt_contains_voice_hint"] is True
    assert "female" in selected["provider_style_prompt"].lower()


def test_male_voice_survives_suggested_prompt_change():
    _reset()
    _song_state(vocal="male")
    update = _update_with_query("music_quick|showroom|music_product_regenerate_suggestions")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    state = bot.get_music_guided_result(USER_ID)
    selected = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    assert state["song_vocal"] == "male"
    assert selected["selected_vocal_mode"] == "male"
    assert "male" in selected["provider_style_prompt"].lower()
    assert "female vocal" not in selected["provider_style_prompt"].lower()


def test_voice_mode_survives_lyrics_edit():
    _reset()
    _song_state(vocal="male")
    bot.set_music_guided_pending(USER_ID, "music_product_song_details", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    style = CaptureMessage("Upbeat pop, acoustic guitar, clear warm vocal.", USER_ID)
    asyncio.run(bot.handle_music_guided_pending_text(_message_update(style), SimpleNamespace()))
    lyrics = CaptureMessage("(Verse)\nWake up to the morning light\n(Chorus)\nDance it out, let it go", USER_ID)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(lyrics), SimpleNamespace()))
    result = bot.get_music_guided_result(USER_ID)
    assert handled is True
    assert "Xác nhận tạo bài hát" in lyrics.outputs[-1]["text"]
    assert result["selected_vocal_mode"] == "male"
    assert "male" in result["provider_style_prompt"].lower()


def test_provider_prompt_contains_female_vocal_hint():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "vocal_mode": "female", "description": "male vocal pop", "lyrics": "x"})
    assert bot.music_product_prompt_contains_vocal_hint(built["provider_style_prompt"], "female") is True


def test_provider_prompt_contains_male_vocal_hint():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "vocal_mode": "male", "description": "female vocal pop", "lyrics": "x"})
    assert bot.music_product_prompt_contains_vocal_hint(built["provider_style_prompt"], "male") is True


def test_duet_option_routes_to_generation():
    _reset()
    bot.save_music_guided_result(USER_ID, {"music_product_mode": "song", "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC})
    update = _update_with_query("music_quick|showroom|music_vocal:duet")
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert bot.get_music_guided_result(USER_ID)["song_vocal"] == "duet"
    msg = CaptureMessage("Bai hat thuong hieu song ca nam nu", USER_ID)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(msg), SimpleNamespace()))
    assert handled is True
    state = bot.get_music_guided_result(USER_ID)
    assert len(state["music_suggestions"]) == 3
    assert state["selected_vocal_mode"] == "duet"


def test_duet_prompt_contains_male_female_instruction():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "vocal_mode": "duet", "lyrics": "Cau 1\nCau 2\nDiep khuc"})
    assert "male and female duet" in built["provider_style_prompt"].lower()
    assert bot.music_product_prompt_contains_vocal_hint(built["provider_style_prompt"], "duet") is True


def test_duet_with_user_lyrics_does_not_loop():
    _reset()
    _song_state(vocal="duet")
    bot.set_music_guided_pending(USER_ID, "music_product_song_details", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    details = CaptureMessage("Tieu de: Song Ca TOAN AAS\nChu de: niem tin AI\nThe loai: pop\nLoi hat:\n[Male]\nTa cung di len\n[Female]\nSang trong niem tin\n[Duet]\nTOAN AAS vuon xa", USER_ID)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(details), SimpleNamespace()))
    result = bot.get_music_guided_result(USER_ID)
    assert handled is True
    assert "Xác nhận tạo bài hát" in details.outputs[-1]["text"]
    assert result["selected_vocal_mode"] == "duet"
    assert result["duet_prompt_applied"] is True
    assert not result.get("music_product_pending_lyrics")


def test_duet_generated_lyrics_has_valid_structure():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "vocal_mode": "duet", "lyrics": "Cau mot\nCau hai\nCau ba\nCau bon"})
    assert "[Male Verse]" in built["provider_lyrics"]
    assert "[Female Verse]" in built["provider_lyrics"]
    assert "[Duet Chorus]" in built["provider_lyrics"]
    assert bot.music_product_duet_lyrics_structure(built["provider_lyrics"]) == "tagged"


def test_duet_failure_clean_no_charge(monkeypatch):
    _reset()
    state = _patch_store(monkeypatch, job=_job(vocal="duet"), admin=False)
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_result_once(CaptureMessage(chat_id=USER_ID), _ctx(fake), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result("duet"), audio_bytes=b"", job=state["job"], send_success_message=True, source="empty_duet_audio"))
    assert result["ok"] is False
    assert state["charges"] == []
    assert fake.audio == []


def test_generic_error_after_audio_delivery_suppressed(monkeypatch):
    _reset()
    delivered, _fake, _state = _deliver(monkeypatch)
    recorded = bot.record_music_runtime_error_suppressed(delivered["job"], reason="RuntimeError", callback_data="progress|status|music_song|MUS14FVOICE", status_panel=False)
    assert recorded["late_error_suppressed"] is True
    assert recorded["generic_error_after_delivery_prevented"] is True
    assert recorded["terminal_public_outcome_type"] == "success"


def test_status_panel_edit_failure_after_delivery_not_public_error(monkeypatch):
    _reset()
    delivered, _fake, _state = _deliver(monkeypatch)
    recorded = bot.record_music_runtime_error_suppressed(delivered["job"], reason="BadRequest", callback_data="progress|status|music_song|MUS14FVOICE", status_panel=True)
    assert recorded["status_panel_edit_failed_nonterminal"] is True
    assert recorded["public_panel_update_failed_nonterminal"] is True
    assert recorded["generic_error_after_delivery_prevented"] is True


def test_success_panel_after_audio_no_red_x(monkeypatch):
    _reset()
    delivered, fake, _state = _deliver(monkeypatch)
    bot.record_music_runtime_error_suppressed(delivered["job"], reason="late_panel_error", callback_data="music_quick|showroom|music_ai_status")
    assert len(fake.audio) == 1
    assert len(fake.sent) == 1
    assert "Có lỗi khi xử lý lệnh" not in fake.sent[0]["text"]


def test_actual_delivery_failure_still_clean_failed_no_charge(monkeypatch):
    _reset()
    state = _patch_store(monkeypatch, admin=False)
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_result_once(CaptureMessage(chat_id=USER_ID), _ctx(fake), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"", job=state["job"], send_success_message=True, source="empty_audio"))
    assert result["ok"] is False
    assert state["charges"] == []
    assert len(fake.audio) == 0


def test_music_progress_does_not_mark_file_check_green_before_audio_validated():
    state = bot.product_progress_state_from_job("music_song", {"internal_job_id": "MUS-PROG1", "status": "completed", "provider_task_id": "task-1", "provider_style_prompt": "pop", "provider_lyrics": "lyrics"})
    assert "validating_audio" not in state["completed_steps"]
    assert "delivering" not in state["completed_steps"]


def test_music_progress_does_not_mark_delivery_green_before_delivery_succeeded():
    state = bot.product_progress_state_from_job("music_song", {"internal_job_id": "MUS-PROG2", "status": "completed", "provider_task_id": "task-2", "provider_style_prompt": "pop", "provider_lyrics": "lyrics", "output_bytes": 1024, "artifact_duration_seconds": 120, "audio_validated": True})
    assert "validating_audio" in state["completed_steps"]
    assert "delivering" not in state["completed_steps"]


def test_music_progress_all_green_after_delivery():
    state = bot.product_progress_state_from_job("music_song", {"internal_job_id": "MUS-PROG3", "terminal_state": "delivered", "delivery_succeeded": True, "provider_style_prompt": "pop", "provider_lyrics": "lyrics"})
    assert state["terminal_state"] == "delivered"
    assert state["percent"] == 100
    assert {"received_request", "preparing_lyrics", "preparing_style", "generating_song", "validating_audio", "delivering"}.issubset(set(state["completed_steps"]))


def test_music_panel_finalizes_100_after_delivery():
    text = bot.product_progress_status_from_job_text("music_song", {"internal_job_id": "MUS-PROG4", "terminal_state": "delivered", "delivery_succeeded": True, "provider_style_prompt": "pop", "provider_lyrics": "lyrics"}, "MUS-PROG4", "vi")
    assert "Tiến độ: 100%" in text
    assert "✅ Gửi kết quả" in text


def test_music_delivers_one_track_only(monkeypatch):
    _reset()
    delivered, fake, _state = _deliver(monkeypatch)
    assert delivered["ok"] is True
    assert len(fake.audio) == 1
    assert delivered["result"]["delivered_track_count"] == 1
    assert delivered["result"]["multi_track_concat_attempted"] is False


def test_multiple_provider_items_selects_one_candidate_not_concat(monkeypatch):
    _reset()
    async def fake_duration(_payload, fallback=0):
        return 121

    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(
        bot,
        "music_delivery_artifact_candidates",
        lambda *_args, **_kwargs: [
            {"audio_bytes": b"ID3-first" * 120, "source": "provider_result_0", "role": "provider_result_metadata"},
            {"audio_bytes": b"ID3-second" * 120, "source": "provider_result_1", "role": "provider_result_metadata"},
        ],
    )
    artifact = asyncio.run(bot.select_music_delivery_artifact(_result(), _job(), None))
    assert artifact["ok"] is True
    assert artifact["selected_track_index"] == 1
    assert artifact["delivered_track_count"] == 1
    assert artifact["multi_track_concat_attempted"] is False


def test_delivered_track_count_one(monkeypatch):
    _reset()
    delivered, _fake, _state = _deliver(monkeypatch)
    assert delivered["job"]["delivered_track_count"] == 1


def test_success_duration_matches_delivered_audio(monkeypatch):
    _reset()
    delivered, _fake, _state = _deliver(monkeypatch)
    assert delivered["result"]["music_result_duration_seconds"] == delivered["result"]["delivered_duration_seconds"]
    assert delivered["job"]["music_result_duration_seconds"] == delivered["job"]["delivered_duration_seconds"]


def test_basic_package_duration_display_not_fake(monkeypatch):
    _reset()
    delivered, _fake, _state = _deliver(monkeypatch)
    success = bot.music_product_success_text(delivered["result"], delivered["charged_xu"], "vi")
    assert "1:58" in success
    assert "245 giây" not in success


def test_success_panel_charge_zero_has_reason(monkeypatch):
    _reset()
    delivered, fake, _state = _deliver(monkeypatch, admin=True)
    assert delivered["charged_xu"] == 0
    assert "Đã trừ: 0 Xu" in fake.sent[0]["text"]


def test_success_panel_paid_charge_after_delivery(monkeypatch):
    _reset()
    delivered, fake, state = _deliver(monkeypatch, admin=False)
    assert delivered["charged_xu"] == 200
    assert state["charges"]
    assert "Đã trừ: 200 Xu" in fake.sent[0]["text"]


def test_no_duplicate_charge(monkeypatch):
    _reset()
    first, fake, state = _deliver(monkeypatch, admin=False)
    second = asyncio.run(bot.deliver_music_result_once(CaptureMessage(chat_id=USER_ID), _ctx(fake), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=AUDIO_BYTES, job=first["job"], send_success_message=True, source="recover"))
    assert second["duplicate"] is True
    assert len(state["charges"]) == 1
    assert len(fake.audio) == 1


def test_no_product_video_subdub_payos_pricing_db_changes():
    if not _is_music_scope_branch(_current_branch_name()):
        pytest.skip("Music H14F scope guard is not active for this branch")
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


def test_current_download_engine_not_rewritten():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    assert "providers/key4u_provider.py" not in changed
    assert "local_worker.py" not in changed or _local_worker_change_is_img2vid_only()
    assert "remote_worker.py" not in changed
