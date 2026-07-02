import asyncio
from types import SimpleNamespace

import bot


AUDIO_BYTES = b"RIFF-toan-aas-h11-real-wav" * 320
JOB_ID = "MUSH11WAV01"
USER_ID = 230711
TASK_ID = "1279444349692403713"
CLIP_ID = "clipABC123"
WAV_TASK_ID = "wavTaskABC999"
BARE_CDN = f"https://cdn1.suno.ai/{CLIP_ID}.mp3"


def _job(**overrides):
    data = {
        "internal_job_id": JOB_ID,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": TASK_ID,
        "provider_job_id": TASK_ID,
        "status": "completed",
        "provider_completed": True,
        "music_provider_completed": True,
        "pending_charge_xu": 300,
        "charged_xu": 0,
    }
    data.update(overrides)
    return data


def _bare_candidate():
    return {
        "field_path": "data.data[0].cld2AudioUrl",
        "source": "data.data[0].cld2AudioUrl",
        "role": "provider_result_metadata",
        "url": BARE_CDN,
        "url_label": "cdn1.suno.ai.mp3",
        "safe_label": "cdn1.suno.ai.mp3",
        "provider_name": "key4u_suno",
        "rejected": True,
        "reject_reason": "bare_suno_cdn_no_query",
        "rejected_reason": "bare_suno_cdn_no_query",
        "rank": -10000,
    }


def _patch_success_materialize(monkeypatch, tmp_path, *, duration=188):
    async def fake_duration(_audio, fallback=0):
        return duration

    def fake_upsert(*, audio_bytes, result=None, job=None, status="generated_unused", updated_by=""):
        path = tmp_path / "h11.wav"
        path.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": "MV-H11", "storage_ref": str(path)}

    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", fake_upsert)
    monkeypatch.setattr(bot, "write_music_canonical_artifact", lambda job, payload: str(tmp_path / "canonical-h11.wav"))
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: None)


def _patch_key4u_wav_env(monkeypatch, *, fetch_url=True):
    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_URL", "https://api.key4u.shop/suno/act/wav/{clip_id}")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_RESULT_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_FETCH_URL", "https://api.key4u.shop/suno/fetch/{taskId}" if fetch_url else "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_QUERY_ENDPOINT", "" if not fetch_url else "/fetch/{taskId}")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "key4u-secret")


def test_get_wav_direct_audio_bytes_materializes(monkeypatch, tmp_path):
    calls = []

    class FakeResponse:
        status_code = 200
        content = AUDIO_BYTES
        headers = {"content-type": "audio/wav"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            calls.append((url, headers or {}))
            return FakeResponse()

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(provider_result_candidates=[_bare_candidate()]),
            updated_by=USER_ID,
            source="h11_direct_wav",
        )
    )
    job = result["job"]

    assert result["ok"] is True
    assert calls and f"/act/wav/{CLIP_ID}" in calls[0][0]
    assert calls[0][1]["Authorization"].startswith("Bearer ")
    assert job["wav_endpoint_configured"] is True
    assert job["wav_request_http_status"] == 200
    assert job["wav_response_shape"] == "audio_bytes"
    assert job["final_audio_download_status"] == "PASS"
    assert job["audio_validated"] is True


def test_get_wav_json_uuid_second_step_fetch_materializes(monkeypatch, tmp_path):
    calls = []

    class JsonResponse:
        status_code = 200
        content = b'{"code":"success","data":"wavTaskABC999","message":""}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"code": "success", "data": WAV_TASK_ID, "message": ""}

    class AudioResponse:
        status_code = 200
        content = AUDIO_BYTES
        headers = {"content-type": "audio/wav"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            calls.append(url)
            if "/act/wav/" in url:
                return JsonResponse()
            return AudioResponse()

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(provider_result_candidates=[_bare_candidate()]),
            updated_by=USER_ID,
            source="h11_two_step",
        )
    )
    job = result["job"]

    assert result["ok"] is True
    assert any(f"/act/wav/{CLIP_ID}" in url for url in calls)
    assert any(f"/fetch/{WAV_TASK_ID}" in url for url in calls)
    assert job["wav_response_shape"] == "json_data_uuid"
    assert job["wav_task_id_present"] is True
    assert job["final_audio_download_status"] == "PASS"
    assert job["provider_download_bytes"] == len(AUDIO_BYTES)


def test_get_wav_json_uuid_without_followup_url_sets_setup_required(monkeypatch, tmp_path):
    class JsonResponse:
        status_code = 200
        content = b'{"code":"success","data":"wavTaskABC999","message":""}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"code": "success", "data": WAV_TASK_ID, "message": ""}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return JsonResponse()

    _patch_key4u_wav_env(monkeypatch, fetch_url=False)
    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(provider_result_candidates=[_bare_candidate()]),
            updated_by=USER_ID,
            source="h11_missing_followup",
        )
    )
    job = result["job"]

    assert result["ok"] is False
    assert job["terminal_state"] == "failed_no_charge"
    assert job["primary_blocker"] == bot.KEY4U_SUNO_WAV_RESULT_BLOCKER
    assert job["setup_required"] == bot.KEY4U_SUNO_WAV_SETUP_REQUIRED
    assert job["wav_response_shape"] == "json_data_uuid"
    assert job["wav_task_id_present"] is True
    assert job["final_audio_download_status"] == "SETUP_REQUIRED"
    assert job["artifact_ready"] is False


def test_bare_cdn_no_query_remains_rejected():
    candidates = bot.extract_shopaikey_suno_audio_candidates(
        {"data": {"data": [{"cld2AudioUrl": BARE_CDN}]}},
        provider_name="key4u_suno",
    )

    assert candidates[0]["rejected"] is True
    assert candidates[0]["reject_reason"] == "bare_suno_cdn_no_query"
    assert bot.select_music_provider_audio_candidate(candidates) == {}


def test_no_charge_before_telegram_delivery(monkeypatch, tmp_path):
    store = {JOB_ID: _job(provider_result_candidates=[_bare_candidate()])}
    charge_calls = []

    class FakeResponse:
        status_code = 200
        content = AUDIO_BYTES
        headers = {"content-type": "audio/wav"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return FakeResponse()

    class FailingBot:
        async def send_audio(self, *args, **kwargs):
            raise RuntimeError("telegram send failed")

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or JOB_ID)] = current
        return dict(current)

    async def fake_poll(state, updated_by=""):
        return {
            "ok": False,
            "status": "COMPLETED_NO_DOWNLOADABLE_AUDIO",
            "output_url": "",
            "raw_provider_result": {"data": {"data": [{"id": CLIP_ID, "cld2AudioUrl": BARE_CDN}]}},
        }

    def fake_spend(*args, **kwargs):
        charge_calls.append((args, kwargs))
        return {"ok": True, "final_cost": 300}

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(store.get(str(job_id)) or {}))
    monkeypatch.setattr(
        bot,
        "get_engine_async_job_lookup",
        lambda _job_id: {"job": dict(store.get(JOB_ID) or {}), "lookup_found": True, "canonical_job_id": JOB_ID, "resolved_job_id": JOB_ID, "legacy_job_id": ""},
    )
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda current: {})
    monkeypatch.setattr(bot, "save_music_guided_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", fake_spend)

    result = asyncio.run(
        bot.deliver_music_ready_artifact_once(
            JOB_ID,
            context=SimpleNamespace(bot=FailingBot()),
            user_id=USER_ID,
            source="h11_no_charge_before_send",
        )
    )

    assert result["ok"] is False
    assert result["status"] == "SEND_FAILED"
    assert charge_calls == []
