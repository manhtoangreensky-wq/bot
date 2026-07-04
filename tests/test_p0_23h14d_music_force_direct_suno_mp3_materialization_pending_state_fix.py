import asyncio
import subprocess
from types import SimpleNamespace

import bot
from services import product_progress_status


AUDIO_BYTES = b"ID3-toan-aas-h14d-real-music" * 360
JOB_ID = "MUSE98BEAD8"
USER_ID = 231414
TASK_ID = "1279444349692403713"
CLIP_ID = "clipLiveH14D123"
BARE_CDN = f"https://cdn1.suno.ai/{CLIP_ID}.mp3"
PROVIDER_ENDPOINT = "https://api.key4u.shop/suno/act/wav/{clip_id}"


def _raw_provider_result():
    return {
        "code": "SUCCESS",
        "data": {
            "data": [
                {
                    "clipId": CLIP_ID,
                    "cld2AudioUrl": BARE_CDN,
                    "progress": "100%",
                    "prompt": "TOAN AAS live direct CDN recovery",
                }
            ]
        },
    }


def _candidate_records(payload=None):
    return bot.music_provider_audio_candidate_records(
        bot.extract_shopaikey_suno_audio_candidates(payload or _raw_provider_result(), provider_name="key4u_suno")
    )


def _job(**overrides):
    data = {
        "internal_job_id": JOB_ID,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_name_internal": "key4u_suno",
        "provider_task_id": TASK_ID,
        "provider_job_id": TASK_ID,
        "provider_submit_called": True,
        "provider_completed": True,
        "music_provider_completed": True,
        "provider_status": "completed",
        "provider_status_raw": "SUCCESS",
        "status": "completed",
        "progress_percent": 5,
        "raw_provider_result_saved": True,
        "raw_provider_result_internal": _raw_provider_result(),
        "provider_result_candidates": _candidate_records(),
        "pending_charge_xu": 300,
        "charged_xu": 0,
        "charge_status": "pending_no_charge",
    }
    data.update(overrides)
    return data


def _patch_key4u_env(monkeypatch):
    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", PROVIDER_ENDPOINT)
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_URL", PROVIDER_ENDPOINT)
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_RESULT_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_FETCH_URL", "")
    monkeypatch.setattr(bot, "KEY4U_MUSIC_FETCH_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_QUERY_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "key4u-secret")
    monkeypatch.setattr(bot, "MUSIC_RESULT_DOWNLOAD_MAX_RETRIES", 1)
    monkeypatch.setattr(bot, "MUSIC_ARTIFACT_WAIT_MAX_ATTEMPTS", 8)


def _patch_materialize_success(monkeypatch, tmp_path, *, duration=188):
    async def fake_duration(_audio, fallback=0):
        return duration

    def fake_upsert(*, audio_bytes, result=None, job=None, status="generated_unused", updated_by=""):
        path = tmp_path / "h14d-vault.mp3"
        path.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": "MV-H14D", "storage_ref": str(path)}

    def fake_write(_job, payload):
        path = tmp_path / "canonical-h14d.mp3"
        path.write_bytes(bytes(payload or b""))
        return str(path)

    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", fake_upsert)
    monkeypatch.setattr(bot, "write_music_canonical_artifact", fake_write)
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: None)


def _patch_job_store(monkeypatch, initial=None):
    store = {JOB_ID: dict(initial or _job())}

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or JOB_ID)] = current
        return dict(current)

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(store.get(str(job_id)) or {}))
    monkeypatch.setattr(
        bot,
        "get_engine_async_job_lookup",
        lambda _job_id: {
            "job": dict(store.get(JOB_ID) or {}),
            "lookup_found": True,
            "canonical_job_id": JOB_ID,
            "resolved_job_id": JOB_ID,
            "legacy_job_id": "",
        },
    )
    return store


class _AudioResponse:
    status_code = 200
    content = AUDIO_BYTES
    headers = {"content-type": "audio/mpeg"}
    text = ""

    def json(self):
        raise ValueError("not json")


class _JsonNoAudioResponse:
    status_code = 200
    content = b'{"code":"success","message":"","data":null}'
    headers = {"content-type": "application/json"}
    text = '{"code":"success","message":"","data":null}'

    def json(self):
        return {"code": "success", "message": "", "data": None}


class _WavPendingResponse:
    status_code = 200
    content = b'{"code":1102,"message":"Please wait for the creation to finish before downloading."}'
    headers = {"content-type": "application/json"}
    text = '{"code":1102,"message":"Please wait for the creation to finish before downloading."}'

    def json(self):
        return {"code": 1102, "message": "Please wait for the creation to finish before downloading."}


def _client(monkeypatch, calls, *, cdn_response, endpoint_response=None):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            calls.append(str(url))
            if "cdn1.suno.ai" in str(url):
                return cdn_response
            return endpoint_response or _WavPendingResponse()

    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)


class CaptureMessage:
    def __init__(self, text="", user_id=USER_ID):
        self.text = text
        self.chat_id = user_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": str(text or ""), **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))


def _message_update(message, user_id=USER_ID):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def test_selected_cld2_audio_url_is_downloaded_directly_not_provider_auth(monkeypatch):
    calls = []
    _patch_key4u_env(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())

    candidate = _candidate_records()[0]
    result = asyncio.run(bot.music_download_artifact_candidate(candidate, _job()))

    assert result["ok"] is True
    assert result["download_strategy_used"] == "direct_cdn"
    assert result["provider_auth_header_used"] is False
    assert result["provider_download_endpoint_attempted"] is False
    assert calls == [BARE_CDN]


def test_provider_auth_bypassed_for_direct_cdn_candidate(monkeypatch):
    calls = []
    _patch_key4u_env(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())

    result = asyncio.run(bot.music_download_artifact_candidate(_candidate_records()[0], _job()))

    assert result["provider_auth_bypassed_for_direct_cdn"] is True
    assert result["provider_auth_bypassed_for_direct_suno_cdn"] is True
    assert result["direct_cdn_download_attempted"] is True
    assert not any("api.key4u.shop" in item for item in calls)


def test_provider_endpoint_json_no_audio_does_not_override_direct_candidate(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonNoAudioResponse(), endpoint_response=_WavPendingResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14d_pending"))
    job = result["job"]

    assert calls[0] == BARE_CDN
    assert result["status"] == "ARTIFACT_WAITING"
    assert job["terminal_state"] == ""
    assert job["primary_blocker"] == "artifact_not_ready"
    assert job["direct_cdn_download_attempted"] is True
    assert job["provider_download_endpoint_attempted"] is True


def test_direct_cdn_mp3_validates_and_sets_artifact_ready(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14d_direct"))
    job = result["job"]

    assert result["ok"] is True
    assert calls == [BARE_CDN]
    assert job["artifact_ready"] is True
    assert job["audio_validated"] is True
    assert job["output_bytes"] == len(AUDIO_BYTES)
    assert job["download_strategy_used"] == "direct_cdn"
    assert job["provider_download_endpoint_attempted"] is False


def test_direct_cdn_json_response_rejected_after_get_attempt(monkeypatch):
    calls = []
    _patch_key4u_env(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonNoAudioResponse())

    result = asyncio.run(bot.music_download_artifact_candidate(_candidate_records()[0], _job()))

    assert result["ok"] is False
    assert result["direct_cdn_download_attempted"] is True
    assert result["direct_cdn_validation_passed"] is False
    assert result["provider_download_endpoint_attempted"] is False
    assert calls == [BARE_CDN]


def test_final_audio_pending_does_not_set_failed_no_charge(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonNoAudioResponse(), endpoint_response=_WavPendingResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14d_pending"))
    job = result["job"]

    assert result["status"] == "ARTIFACT_WAITING"
    assert job["terminal_state"] == ""
    assert bot.music_job_terminal_failed(job) is False
    assert job["charged_xu"] == 0


def test_artifact_waiting_registers_scheduler_retry(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonNoAudioResponse(), endpoint_response=_WavPendingResponse())

    job = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14d_wait"))["job"]

    assert job["artifact_waiting"] is True
    assert job["artifact_wait_scheduler_registered"] is True
    assert job["scheduler_status"] in {"waiting", "running", "scheduled", "not_started"}
    assert job["next_artifact_retry_at"]
    assert job["recovery_action"] == "artifact_waiting_retry_later"


def test_provider_completed_artifact_waiting_progress_not_stuck_at_5(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonNoAudioResponse(), endpoint_response=_WavPendingResponse())

    job = asyncio.run(bot.materialize_music_artifact_for_job(_job(progress_percent=5), updated_by=USER_ID, source="h14d_progress"))["job"]
    state = product_progress_status.product_progress_stage_from_job("music_song", job)

    assert state["current_stage"] == "validating_audio"
    assert state["terminal_state"] == ""
    assert state["percent"] >= 80
    assert "file nhạc" in state["status_text"]


def test_recover_materializes_saved_cld2_audio_url_without_new_job(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    job = _job(raw_provider_result_internal={}, provider_result_candidates=[], music_output_url=BARE_CDN)
    _patch_job_store(monkeypatch, job)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(job, updated_by=USER_ID, source="h14d_saved_url"))

    assert result["ok"] is True
    assert calls == [BARE_CDN]
    assert result["job"]["selected_artifact_field_path"] == "music_output_url"
    assert result["job"]["provider_task_id"] == TASK_ID


def test_recover_does_not_mark_delivery_attempted_until_telegram_send(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())

    job = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14d_materialize_only"))["job"]

    assert job.get("delivery_state", "") != "delivered"
    assert int(job.get("delivery_attempt_count") or 0) == 0
    assert int(job.get("send_attempt_count") or 0) == 0


def test_charge_only_after_validated_audio_delivery(monkeypatch, tmp_path):
    calls = []
    charges = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: charges.append(args) or {"ok": True, "final_cost": 300})

    job = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14d_charge"))["job"]

    assert job["audio_validated"] is True
    assert job["charged_xu"] == 0
    assert job["charge_status"] == "pending_no_charge"
    assert charges == []


def test_song_manual_style_then_lyrics_preserves_both_lines(monkeypatch):
    user_id = 231415
    bot.USER_PENDING.pop(bot.music_guided_pending_key(user_id), None)
    bot.USER_PENDING.pop(bot.music_guided_result_key(user_id), None)
    bot.save_music_guided_result(
        user_id,
        {
            "music_product_flow": "p0_20a_3_tier",
            "music_product_mode": "song",
            "music_product_tier": "music_tier_basic",
            "song_vocal": "female",
            "vocal_mode": "female",
        },
    )
    bot.set_music_guided_pending(user_id, "music_product_song_details", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)

    style_message = CaptureMessage(
        "Upbeat Indie pop, tropical house elements, bright synth, bouncy bassline, clear warm vocals.",
        user_id,
    )
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(style_message, user_id), SimpleNamespace()))
    assert handled is True
    assert "Lời hát" in style_message.outputs[-1]["text"]

    lyrics_message = CaptureMessage("(Verse)\nWake up to the morning light\nLeave the shadows in the night\n\n(Chorus)\nDance it out, let it go", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(lyrics_message, user_id), SimpleNamespace()))
    result = bot.get_music_guided_result(user_id)

    assert handled is True
    assert "Xác nhận tạo bài hát" in lyrics_message.outputs[-1]["text"]
    assert "Upbeat Indie pop" in result["provider_style_prompt"]
    assert "Wake up to the morning light" in result["provider_lyrics"]


def test_no_product_video_subdub_payos_pricing_db_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    forbidden_prefixes = (
        "providers/video",
        "services/video",
        "services/subdub",
        "services/payos",
        "services/wallet",
        "services/pricing",
        "migrations/",
        "web/",
    )
    forbidden_exact = {
        "local_worker.py",
        "remote_worker.py",
        "providers/key4u_provider.py",
    }
    offenders = [
        path for path in changed
        if path in forbidden_exact or path.startswith(forbidden_prefixes)
    ]
    assert offenders == []
