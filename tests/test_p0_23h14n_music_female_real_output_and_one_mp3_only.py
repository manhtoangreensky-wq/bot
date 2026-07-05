import asyncio
import re
import subprocess
from types import SimpleNamespace

import bot


USER_ID = 231615
JOB_ID = "MUSH14NFEMALE"
AUDIO_BYTES = b"ID3-toan-aas-h14n-final-audio" * 260


class DictTelegramBot:
    def __init__(self):
        self.audio = []
        self.sent = []

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        return {
            "message_id": f"audio-message-{len(self.audio)}",
            "audio": {"file_id": f"audio-file-{len(self.audio)}"},
            "status": "SUCCESS",
        }

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"message_id": f"success-message-{len(self.sent)}", "status": "SUCCESS"}


class ReentrantTelegramBot(DictTelegramBot):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.reentrant_result = None

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        if len(self.audio) == 1:
            self.reentrant_result = await bot.deliver_music_result_once(
                CaptureMessage(),
                _ctx(self),
                user_id=USER_ID,
                lang="vi",
                product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
                result=_result(),
                audio_bytes=AUDIO_BYTES,
                job=self.state["job"],
                updated_by=USER_ID,
                send_success_message=True,
                source="manual_refresh",
            )
        return {
            "message_id": f"audio-message-{len(self.audio)}",
            "audio": {"file_id": f"audio-file-{len(self.audio)}"},
            "status": "SUCCESS",
        }


class CaptureMessage:
    def __init__(self, chat_id=USER_ID):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_audio(self, **kwargs):
        self.outputs.append({"kind": "audio", **kwargs})
        return {"message_id": f"reply-audio-{len(self.outputs)}", "audio": {"file_id": f"reply-file-{len(self.outputs)}"}}

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": str(text or ""), **kwargs})
        return {"message_id": f"reply-text-{len(self.outputs)}"}


def _ctx(fake=None):
    return SimpleNamespace(bot=fake or DictTelegramBot())


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _result(vocal="female", tier=None):
    tier = tier or bot.MUSIC_PRODUCT_TIER_BASIC
    return bot.music_product_result_from_input({
        "user_id": USER_ID,
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "song",
        "music_product_tier": tier,
        "description": "Upbeat pop, Male vocal, bright acoustic guitar",
        "style_prompt": "Upbeat pop, Male vocal, bright acoustic guitar",
        "lyrics": "[Verse]\nTOAN AAS sang ngay\n[Chorus]\nCung nhau vuon xa",
        "song_vocal": vocal,
        "vocal_mode": vocal,
        "selected_vocal_mode": vocal,
        "requested_vocal_mode": vocal,
        "music_task_id": "provider-task-h14n",
        "music_internal_job_id": JOB_ID,
        "music_job_id": JOB_ID,
    })


def _job(job_id=JOB_ID):
    return {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "music_product_price_xu": 200,
        "song_vocal": "female",
        "selected_vocal_mode": "female",
        "requested_vocal_mode": "female",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-h14n",
        "provider_job_id": "provider-task-h14n",
        "status": "completed",
        "progress_percent": 90,
        "output_bytes": len(AUDIO_BYTES),
        "artifact_duration_seconds": 190,
        "music_result_duration_seconds": 190,
        "output_sha256": bot.music_audio_sha256(AUDIO_BYTES),
        "audio_validated": True,
        "artifact_ready": True,
        "music_audio_validated": True,
        "music_artifact_ready": True,
        "pending_charge_xu": 200,
        "charged_xu": 0,
    }


def _patch_store(monkeypatch, job=None, *, admin=True):
    state = {"job": dict(job or _job()), "guided": {}, "charges": []}

    async def fake_duration(*_args, **_kwargs):
        return 190

    def fake_save(payload):
        state["job"] = dict(payload)
        return dict(payload)

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(state["job"]) if _job_id == state["job"].get("internal_job_id") else {})
    monkeypatch.setattr(
        bot,
        "get_engine_async_job_lookup",
        lambda _job_id: {
            "job": dict(state["job"]),
            "resolved_job_id": state["job"].get("internal_job_id"),
            "canonical_job_id": state["job"].get("internal_job_id"),
            "lookup_found": True,
        } if _job_id == state["job"].get("internal_job_id") else {"job": {}, "resolved_job_id": "", "canonical_job_id": "", "lookup_found": False},
    )
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_music_guided_result", lambda _user_id: dict(state["guided"]))
    monkeypatch.setattr(bot, "save_music_guided_result", lambda _user_id, payload: state["guided"].update(dict(payload)) or dict(payload))
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-H14N", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-H14N"})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: state["charges"].append(args) or {"ok": True, "final_cost": 200, "status": "ok"})
    return state


def _submit_payload_for(result):
    vocal = bot.music_product_canonical_vocal_mode(result)
    return bot.shopaikey_suno_submit_payload(
        result["provider_style_prompt"],
        title=result.get("provider_title") or "TOAN AAS Music",
        tags=result.get("provider_tags") or "original",
        instrumental=False,
        model="chirp-v4",
        lyrics=result["provider_lyrics"],
        vocal_mode=vocal,
    )


def _assert_female_payload(payload):
    combined = f"{payload.get('gpt_description_prompt')}\n{payload.get('prompt')}"
    assert bot.music_product_prompt_contains_vocal_hint(combined, "female") is True
    assert bot.music_product_prompt_contains_vocal_hint(combined, "male") is False
    assert payload["prompt"].startswith("[Female vocal]")
    assert not re.search(r"\bMale\s+vocal\b", combined)


def test_h14n_female_suggestion_provider_payload_is_locked_to_female():
    state = {
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "song_vocal": "female",
        "vocal_mode": "female",
        "selected_vocal_mode": "female",
        "requested_vocal_mode": "female",
    }
    prepared = bot.music_product_prepare_suggestions_result(state, idea="bai hat thuong hieu nang luong", offset=0, lang="vi")
    selected = bot.music_product_result_from_suggestion(prepared, prepared["music_suggestions"][0])

    assert selected["selected_vocal_mode"] == "female"
    _assert_female_payload(_submit_payload_for(selected))


def test_h14n_female_custom_lyrics_provider_payload_is_locked_to_female():
    result = _result("female")

    assert result["selected_vocal_mode"] == "female"
    _assert_female_payload(_submit_payload_for(result))


def test_h14n_female_payload_removes_stale_male_hint():
    result = bot.music_product_result_from_input({
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "song_vocal": "female",
        "vocal_mode": "female",
        "selected_vocal_mode": "male",
        "requested_vocal_mode": "female",
        "style_prompt": "Male vocal, acoustic pop, warm chorus",
        "lyrics": "[Male vocal]\n[Verse]\nTOAN AAS sang ngay",
    })
    payload = _submit_payload_for(result)

    _assert_female_payload(payload)
    assert "[Male vocal]" not in payload["prompt"]


def test_h14n_male_and_duet_payloads_keep_correct_vocal_tags():
    male = _submit_payload_for(_result("male"))
    duet = _submit_payload_for(_result("duet"))

    assert bot.music_product_prompt_contains_vocal_hint(f"{male['gpt_description_prompt']}\n{male['prompt']}", "male") is True
    assert male["prompt"].startswith("[Male vocal]")
    assert "Male and female duet vocal" in f"{duet['gpt_description_prompt']}\n{duet['prompt']}"


def test_h14n_lyrics_250_300_use_same_female_lock_as_200():
    for tier in (bot.MUSIC_PRODUCT_TIER_STANDARD, bot.MUSIC_PRODUCT_TIER_PREMIUM):
        result = _result("female", tier=tier)
        payload = _submit_payload_for(result)
        _assert_female_payload(payload)


def test_h14n_delivery_in_progress_suppresses_second_mp3(monkeypatch):
    _reset()
    prelocked = _job()
    prelocked.update({
        "music_delivery_lock": "sending",
        "music_result_delivery_lock": "sending",
        "delivery_in_progress": True,
        "music_delivery_in_progress": True,
        "delivery_lock_run_id": "auto_tick:other",
        "delivery_attempt_count": 1,
        "selected_artifact_hash": bot.music_audio_sha256(AUDIO_BYTES),
    })
    state = _patch_store(monkeypatch, prelocked)
    fake = DictTelegramBot()

    duplicate = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        _ctx(fake),
        user_id=USER_ID,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=AUDIO_BYTES,
        job=state["job"],
        updated_by=USER_ID,
        send_success_message=True,
        source="manual_refresh",
    ))

    assert duplicate["duplicate"] is True
    assert fake.audio == []
    assert duplicate["job"]["duplicate_send_suppressed"] is True
    assert duplicate["job"]["duplicate_send_suppressed_reason"] == "delivery_in_progress"
    assert int(duplicate["job"]["delivery_attempt_count"]) == 1


def test_h14n_auto_tick_and_manual_refresh_race_sends_exactly_one_mp3(monkeypatch):
    _reset()
    state = _patch_store(monkeypatch)
    fake = ReentrantTelegramBot(state)

    delivered = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        _ctx(fake),
        user_id=USER_ID,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=AUDIO_BYTES,
        job=state["job"],
        updated_by=USER_ID,
        send_success_message=True,
        source="auto_tick",
    ))

    assert delivered["ok"] is True
    assert len(fake.audio) == 1
    assert fake.reentrant_result["duplicate"] is True
    assert fake.reentrant_result["job"]["duplicate_send_suppressed_reason"] == "delivery_in_progress"


def test_h14n_debug_fields_present_for_female_and_delivery(monkeypatch):
    _reset()
    state = _patch_store(monkeypatch)
    fake = DictTelegramBot()
    delivered = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        _ctx(fake),
        user_id=USER_ID,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=AUDIO_BYTES,
        job=state["job"],
        updated_by=USER_ID,
        send_success_message=True,
        source="auto_tick",
    ))
    job = dict(delivered["job"])
    job.update(bot.music_provider_vocal_submit_fields(job.get("provider_style_prompt") or "Female vocal", job.get("provider_lyrics") or "[Verse]\nTOAN", "female"))
    state["job"] = job

    text = bot.music_job_debug_text(JOB_ID)
    assert "final_provider_vocal_mode" in text
    assert "female_vocal_payload_lock" in text
    assert "delivery_lock_acquired" in text
    assert "duplicate_send_suppressed" in text


def test_h14n_no_price1_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    assert "tests/test_p0_23h_price1_music_all_tiers_price_ui_behavior_sync.py" not in changed


def test_h14n_no_artifact_download_changes():
    diff = subprocess.check_output(["git", "diff", "-U0", "origin/main", "--", "bot.py"], text=True)
    forbidden = ("artifact_download", "provider_download_endpoint", "wav_", "download_strategy_used")
    changed_lines = "\n".join(line for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
    assert not any(token in changed_lines for token in forbidden)


def test_h14n_no_product_video_subdub_voice_payos_db_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    forbidden_prefixes = (
        "providers/video",
        "services/video",
        "services/subdub",
        "services/payos",
        "services/wallet",
        "services/voice",
        "migrations/",
    )
    forbidden_exact = {"local_worker.py", "remote_worker.py", "providers/key4u_provider.py"}
    assert not any(path in forbidden_exact or path.startswith(forbidden_prefixes) for path in changed)
