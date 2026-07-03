import asyncio

import bot


AUDIO_BYTES = b"RIFF-toan-aas-h12-real-wav" * 320
JOB_ID = "MUSH12WAV01"
USER_ID = 230712
TASK_ID = "1279444349692403713"
CLIP_ID = "clipABC123"
WAV_TASK_ID = "wavTaskOBJ999"
BARE_CDN = f"https://cdn1.suno.ai/{CLIP_ID}.mp3"
SECRET_AUDIO_URL = "https://api.key4u.shop/suno/download/final.mp3?token=secret-token"


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
        path = tmp_path / "h12-vault.wav"
        path.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": "MV-H12", "storage_ref": str(path)}

    def fake_write(_job, payload):
        path = tmp_path / "canonical-h12.wav"
        path.write_bytes(bytes(payload or b""))
        return str(path)

    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", fake_upsert)
    monkeypatch.setattr(bot, "write_music_canonical_artifact", fake_write)
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: None)


def _patch_key4u_wav_env(monkeypatch, *, result_url="", fetch_url=True):
    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_URL", "https://api.key4u.shop/suno/act/wav/{clip_id}")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_RESULT_URL", result_url)
    monkeypatch.setattr(bot, "KEY4U_SUNO_FETCH_URL", "https://api.key4u.shop/suno/fetch/{taskId}" if fetch_url else "")
    monkeypatch.setattr(bot, "KEY4U_MUSIC_FETCH_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_QUERY_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "key4u-secret")


def _patch_job_save(monkeypatch):
    store = {}

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or JOB_ID)] = current
        return dict(current)

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    return store


def test_wav_json_data_object_task_id_followup_materializes(monkeypatch, tmp_path):
    calls = []

    class JsonResponse:
        status_code = 200
        content = b'{"code":"success","data":{"task_id":"wavTaskOBJ999","status":"ready"},"message":""}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"code": "success", "data": {"task_id": WAV_TASK_ID, "status": "ready"}, "message": ""}

    class AudioResponse:
        status_code = 200
        content = AUDIO_BYTES
        headers = {"content-type": "audio/wav"}

    class FakeClient:
        def __init__(self, *args, headers=None, **kwargs):
            self.headers = dict(headers or {})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            calls.append((url, dict(headers or self.headers or {})))
            if "/act/wav/" in url:
                return JsonResponse()
            return AudioResponse()

    _patch_key4u_wav_env(monkeypatch, result_url="https://api.key4u.shop/suno/wav-result/{id}", fetch_url=False)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_save(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(provider_result_candidates=[_bare_candidate()]),
            updated_by=USER_ID,
            source="h12_json_object_task_id",
        )
    )
    job = result["job"]

    assert result["ok"] is True
    assert any(f"/act/wav/{CLIP_ID}" in url for url, _headers in calls)
    assert any(f"/wav-result/{WAV_TASK_ID}" in url for url, _headers in calls)
    assert not any(f"/wav-result/{CLIP_ID}" in url for url, _headers in calls)
    assert job["wav_response_shape"] == "json_data_object"
    assert job["wav_json_task_id_found"] is True
    assert job["wav_json_task_id_field_path"] == "data.task_id"
    assert job["wav_followup_attempted"] is True
    assert job["wav_followup_http_status"] == 200
    assert job["final_audio_download_status"] == "PASS"
    assert job["final_audio_bytes"] == len(AUDIO_BYTES)
    assert job["audio_validated"] is True


def test_wav_json_data_object_audio_url_downloads_final_audio(monkeypatch, tmp_path):
    calls = []

    class JsonResponse:
        status_code = 200
        content = b'{"code":"success","data":{"downloadUrl":"https://api.key4u.shop/suno/download/final.mp3?token=secret-token"}}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"code": "success", "data": {"downloadUrl": SECRET_AUDIO_URL}}

    class AudioResponse:
        status_code = 200
        content = AUDIO_BYTES
        headers = {"content-type": "audio/mpeg"}

    class FakeClient:
        def __init__(self, *args, headers=None, **kwargs):
            self.headers = dict(headers or {})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            current_headers = dict(headers or self.headers or {})
            calls.append((url, current_headers))
            if "/act/wav/" in url:
                return JsonResponse()
            if "/download/final.mp3" in url:
                return AudioResponse()
            raise AssertionError(f"unexpected URL {url}")

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_save(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(provider_result_candidates=[_bare_candidate()]),
            updated_by=USER_ID,
            source="h12_json_object_audio_url",
        )
    )
    job = result["job"]

    assert result["ok"] is True
    assert any("/download/final.mp3?token=secret-token" in url for url, _headers in calls)
    final_headers = [headers for url, headers in calls if "/download/final.mp3" in url][0]
    assert final_headers["Authorization"].startswith("Bearer ")
    assert job["wav_response_shape"] == "json_data_object"
    assert job["wav_json_audio_url_found"] is True
    assert job["wav_json_audio_url_field_path"] == "data.downloadUrl"
    assert job["wav_json_task_id_found"] is False
    assert job["final_audio_download_status"] == "PASS"
    assert job["final_audio_content_type"] == "audio/mpeg"
    assert job["final_audio_bytes"] == len(AUDIO_BYTES)
    assert job["audio_validated"] is True

    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *args, **kwargs: [job])
    monkeypatch.setattr(bot, "load_provider_attempt", lambda *_args, **_kwargs: {})
    audit = bot.music_provider_audit_text()
    recover = bot.music_delivery_recover_report_text(JOB_ID, {"job": job, "lookup_found": True, "canonical_job_id": JOB_ID, "resolved_job_id": JOB_ID})
    assert "secret-token" not in repr(job)
    assert "secret-token" not in audit
    assert "secret-token" not in recover
    assert SECRET_AUDIO_URL not in audit
    assert SECRET_AUDIO_URL not in recover


def test_wav_json_status_message_only_sets_specific_no_charge_blocker(monkeypatch, tmp_path):
    class JsonResponse:
        status_code = 200
        content = b'{"code":"success","data":{"status":"ready","message":"no file yet"}}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"code": "success", "data": {"status": "ready", "message": "no file yet"}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return JsonResponse()

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_save(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(provider_result_candidates=[_bare_candidate()]),
            updated_by=USER_ID,
            source="h12_json_object_missing_audio",
        )
    )
    job = result["job"]

    assert result["ok"] is False
    assert job["terminal_state"] == "failed_no_charge"
    assert job["primary_blocker"] == bot.KEY4U_SUNO_WAV_JSON_OBJECT_BLOCKER
    assert job["artifact_ready"] is False
    assert job["audio_validated"] is False
    assert job["wav_response_shape"] == "json_data_object"
    assert job["wav_json_audio_url_found"] is False
    assert job["wav_json_task_id_found"] is False
    assert job["wav_followup_attempted"] is False
    assert job["final_audio_download_status"] == "FAIL"
    assert job["final_audio_bytes"] == 0
    assert job["wav_response_top_level_keys"] == "code,data"
    assert job["wav_response_data_keys"] == "message,status"
    assert job["wav_response_message_safe"] == "no file yet"
    assert job["progress_text"] == bot.KEY4U_SUNO_DOWNLOAD_PUBLIC_NO_CHARGE


def test_provider_download_url_json_object_not_accepted_without_audio_bytes(monkeypatch, tmp_path):
    class JsonResponse:
        status_code = 200
        content = b'{"code":"success","data":{"status":"ready","message":"still preparing"}}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"code": "success", "data": {"status": "ready", "message": "still preparing"}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            assert "api.key4u.shop" in url
            return JsonResponse()

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_save(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(provider_result_candidates=[_bare_candidate()]),
            updated_by=USER_ID,
            source="h12_provider_download_url_no_audio",
        )
    )
    job = result["job"]

    assert result["ok"] is False
    assert job["selected_artifact_field_path"] == "provider_download_url"
    assert job["selected_artifact_url_label"] == "api.key4u.shop"
    assert job["primary_blocker"] == bot.KEY4U_SUNO_WAV_JSON_OBJECT_BLOCKER
    assert job["provider_download_http_status"] == 200
    assert job["provider_download_content_type"] == "application/json"
    assert job["provider_download_bytes"] == len(JsonResponse.content)
    assert job["final_audio_bytes"] == 0
    assert job["artifact_ready"] is False
    assert job["audio_validated"] is False
