import asyncio
import inspect
from types import SimpleNamespace

import bot


AUDIO_BYTES = b"ID3-toan-aas-h14c-real-music" * 360
JOB_ID = "MUS269F99CB"
USER_ID = 230714
TASK_ID = "1279444349692403713"
CLIP_ID = "clipLiveH14C123"
BARE_CDN = f"https://cdn1.suno.ai/{CLIP_ID}.mp3"


def _provider_result(*items):
    return {"code": "SUCCESS", "data": {"data": list(items)}}


def _raw_provider_result():
    return _provider_result(
        {
            "clipId": CLIP_ID,
            "cld2AudioUrl": BARE_CDN,
            "progress": "100%",
            "prompt": "TOAN AAS live recovery test",
        },
        {
            "clipId": "clipSecondH14C",
            "cld2AudioUrl": "https://cdn1.suno.ai/clipSecondH14C.mp3",
            "progress": "100%",
        },
    )


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
    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_URL", "https://api.key4u.shop/suno/act/wav/{clip_id}")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_RESULT_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_FETCH_URL", "")
    monkeypatch.setattr(bot, "KEY4U_MUSIC_FETCH_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_QUERY_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "key4u-secret")
    monkeypatch.setattr(bot, "MUSIC_ARTIFACT_WAIT_MAX_ATTEMPTS", 3)


def _patch_success_materialize(monkeypatch, tmp_path, *, duration=188):
    async def fake_duration(_audio, fallback=0):
        return duration

    def fake_upsert(*, audio_bytes, result=None, job=None, status="generated_unused", updated_by=""):
        path = tmp_path / "h14c-vault.mp3"
        path.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": "MV-H14C", "storage_ref": str(path)}

    def fake_write(_job, payload):
        path = tmp_path / "canonical-h14c.mp3"
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


class _WavPendingResponse:
    status_code = 200
    content = b'{"code":1102,"message":"Please wait for the creation to finish before downloading."}'
    headers = {"content-type": "application/json"}

    def json(self):
        return {"code": 1102, "message": "Please wait for the creation to finish before downloading."}


class _JsonNoAudioResponse:
    status_code = 200
    content = b'{"code":"success","message":"","data":null}'
    headers = {"content-type": "application/json"}

    def json(self):
        return {"code": "success", "message": "", "data": None}


class _JsonInvalidAudioResponse:
    status_code = 200
    content = b'{"error":"AccessDenied"}'
    headers = {"content-type": "application/json"}

    def json(self):
        return {"error": "AccessDenied"}


class _AudioResponse:
    status_code = 200
    content = AUDIO_BYTES
    headers = {"content-type": "audio/mpeg"}


def _client(monkeypatch, calls, *, cdn_response, endpoint_response=None):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            calls.append(url)
            if "cdn1.suno.ai" in url:
                return cdn_response
            return endpoint_response or _WavPendingResponse()

    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)


def test_wav_1102_wait_message_treated_as_artifact_pending_not_failed(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonInvalidAudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14c_1102"))
    job = result["job"]

    assert result["status"] == "ARTIFACT_WAITING"
    assert job["terminal_state"] == ""
    assert job["artifact_waiting"] is True
    assert job["wav_1102_treated_as_pending"] is True
    assert job["primary_blocker"] == "artifact_not_ready"
    assert job["charged_xu"] == 0


def test_artifact_wait_loop_keeps_job_processing_no_charge(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonInvalidAudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14c_wait"))
    job = result["job"]

    assert result["ok"] is False
    assert job["status"] == "processing"
    assert job["materialization_status"] == "waiting"
    assert job["artifact_wait_attempt_count"] == 1
    assert job["artifact_wait_max_attempts"] == 3
    assert job["next_artifact_retry_at"]
    assert job["terminal_after_wait_exhausted"] is False
    assert job["charge_status"] == "pending_no_charge"


def test_artifact_wait_exhaustion_terminal_failed_no_charge(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonInvalidAudioResponse())

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(artifact_wait_attempt_count=2, artifact_materialization_wait_attempt_count=2),
            updated_by=USER_ID,
            source="h14c_wait_exhausted",
        )
    )
    job = result["job"]

    assert result["ok"] is False
    assert job["terminal_state"] == "failed_no_charge"
    assert job["primary_blocker"] == "artifact_not_ready"
    assert job["terminal_after_wait_exhausted"] is True
    assert job["charged_xu"] == 0


def test_bare_cdn_mp3_candidate_not_rejected_before_validation(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14c_cdn_valid"))
    job = result["job"]

    assert result["ok"] is True
    assert any("cdn1.suno.ai" in url for url in calls)
    assert job["candidate_attempted"] is True
    assert job["candidate_bare_url_allowed_for_validation"] is True
    assert job["candidate_validation_passed"] is True
    assert job["candidate_field_path"] == "data.data[0].cld2AudioUrl"


def test_bare_cdn_mp3_valid_audio_materializes_artifact(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14c_valid"))
    job = result["job"]

    assert result["ok"] is True
    assert job["artifact_ready"] is True
    assert job["audio_validated"] is True
    assert job["output_bytes"] == len(AUDIO_BYTES)
    assert job["selected_artifact_field_path"] == "data.data[0].cld2AudioUrl"


def test_bare_cdn_mp3_json_response_rejected_after_validation_attempt(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonInvalidAudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14c_json_cdn"))
    job = result["job"]

    assert result["ok"] is False
    assert any("cdn1.suno.ai" in url for url in calls)
    assert job["candidate_attempted"] is True
    assert job["candidate_validation_passed"] is False
    assert job["artifact_ready"] is False
    assert job["audio_validated"] is False


def test_provider_download_json_no_audio_does_not_override_cld2_audio_candidate(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse(), endpoint_response=_JsonNoAudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14c_json_endpoint"))
    job = result["job"]

    assert result["ok"] is True
    assert not any("api.key4u.shop" in url for url in calls)
    assert any("cdn1.suno.ai" in url for url in calls)
    assert job["selected_artifact_field_path"] == "data.data[0].cld2AudioUrl"
    assert job["artifact_ready"] is True


def test_candidate_order_prefers_valid_audio_over_json_endpoint(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse(), endpoint_response=_JsonNoAudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14c_order"))
    job = result["job"]

    assert result["ok"] is True
    assert job["candidate_order"] >= 1
    assert job["candidate_validation_passed"] is True
    assert job["selected_artifact_selected_reason"] == "cld2_audio_url_candidate"
    assert job["candidate_field_path"] == "data.data[0].cld2AudioUrl"


def test_recover_uses_saved_raw_provider_result_and_direct_cdn_candidate(monkeypatch, tmp_path):
    calls = []
    deliveries = []
    store = _patch_job_store(monkeypatch, _job(provider_result_candidates=[]))

    async def fake_send_music(*args, **kwargs):
        deliveries.append(kwargs)
        updated = bot.record_music_job_full_send(
            kwargs.get("job"),
            SimpleNamespace(message_id=9001, audio=SimpleNamespace(file_id="file-h14c")),
            kwargs.get("audio_bytes"),
            result=kwargs.get("result"),
            updated_by=USER_ID,
        )
        store[JOB_ID] = updated
        return {"ok": True, "status": "SENT", "job": updated, "delivery_message_id": "9001"}

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda current: {})
    monkeypatch.setattr(bot, "send_music_product_audio_result", fake_send_music)

    result = asyncio.run(
        bot.deliver_music_ready_artifact_once(
            JOB_ID,
            context=SimpleNamespace(bot=SimpleNamespace()),
            user_id=USER_ID,
            source="h14c_recover",
        )
    )

    assert result["ok"] is True
    assert len(deliveries) == 1
    assert any("cdn1.suno.ai" in url for url in calls)
    assert store[JOB_ID]["audio_validated"] is True


def test_recover_does_not_create_new_job(monkeypatch, tmp_path):
    calls = []
    forbidden = []
    _patch_job_store(monkeypatch, _job())

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _client(monkeypatch, calls, cdn_response=_JsonInvalidAudioResponse())
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda *args, **kwargs: forbidden.append("create"))
    monkeypatch.setattr(bot, "submit_music_generation_job", lambda *args, **kwargs: forbidden.append("submit"))
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: forbidden.append("execute"))
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda current: {})

    result = asyncio.run(
        bot.deliver_music_ready_artifact_once(
            JOB_ID,
            context=SimpleNamespace(bot=SimpleNamespace()),
            user_id=USER_ID,
            source="h14c_recover_wait",
        )
    )

    assert result["status"] == "ARTIFACT_WAITING"
    assert forbidden == []


def test_delivery_and_charge_only_after_validated_audio(monkeypatch, tmp_path):
    calls = []
    send_calls = []
    charge_calls = []
    _patch_job_store(monkeypatch, _job())

    async def fake_send_music(*args, **kwargs):
        send_calls.append(kwargs)
        return {"ok": True, "status": "SENT"}

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _client(monkeypatch, calls, cdn_response=_JsonInvalidAudioResponse())
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda current: {})
    monkeypatch.setattr(bot, "send_music_product_audio_result", fake_send_music)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: charge_calls.append((args, kwargs)))

    result = asyncio.run(
        bot.deliver_music_ready_artifact_once(
            JOB_ID,
            context=SimpleNamespace(bot=SimpleNamespace()),
            user_id=USER_ID,
            source="h14c_invalid_no_charge",
        )
    )

    assert result["ok"] is False
    assert result["status"] == "ARTIFACT_WAITING"
    assert send_calls == []
    assert charge_calls == []


def test_public_progress_not_stuck_5_when_provider_completed_artifact_waiting(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_JsonInvalidAudioResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(progress_percent=5), updated_by=USER_ID, source="h14c_progress"))
    job = result["job"]

    assert result["status"] == "ARTIFACT_WAITING"
    assert int(job["progress_percent"]) > 5
    assert "đang chuẩn bị file nhạc" in job["progress_text"]
    assert job["terminal_state"] == ""


def test_old_working_download_path_restored_contract(monkeypatch):
    _patch_key4u_env(monkeypatch)
    candidates = bot.music_delivery_artifact_candidates({}, _job(provider_result_candidates=[]), None)
    direct = next(item for item in candidates if item.get("field_path") == "data.data[0].cld2AudioUrl")
    endpoint = next(item for item in candidates if item.get("provider_download_endpoint_candidate"))

    assert direct["url"] == BARE_CDN
    assert direct["rank"] > endpoint["rank"]
    assert direct["selected_reason"] == "cld2_audio_url_candidate"
    assert endpoint["raw_result_url"] == BARE_CDN
    assert endpoint["raw_result_field_path"] == "data.data[0].cld2AudioUrl"
    assert bot.music_url_is_bare_suno_cdn(endpoint["raw_result_url"]) is True


def test_no_product_video_subdub_payos_pricing_db_changes():
    source = "\n".join(
        inspect.getsource(obj)
        for obj in (
            bot.music_artifact_materialization_pending,
            bot.mark_music_artifact_materialization_waiting,
            bot.music_download_artifact_candidate,
            bot.music_delivery_artifact_candidates,
            bot.materialize_music_artifact_for_job,
        )
    )
    forbidden = ("PayOS", "wallet", "VIDEO_", "SUBDUB", "VOICE_", "CANONICAL_PRICE", "CREATE TABLE", "ALTER TABLE")
    assert not any(term in source for term in forbidden)
