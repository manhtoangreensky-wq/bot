import asyncio
from types import SimpleNamespace

import bot


AUDIO_BYTES = b"ID3-toan-aas-h10-real-music" * 320
JOB_ID = "MUSH10KEY4U01"
USER_ID = 230710
TASK_ID = "1279444349692403713"
BARE_CDN = "https://cdn1.suno.ai/song.mp3"


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
        path = tmp_path / "h10.mp3"
        path.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": "MV-H10", "storage_ref": str(path)}

    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", fake_upsert)
    monkeypatch.setattr(bot, "write_music_canonical_artifact", lambda job, payload: str(tmp_path / "canonical-h10.mp3"))
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))


def test_cld2_audio_url_bare_cdn_selected_for_direct_validation():
    payload = {"data": {"data": [{"cld2AudioUrl": BARE_CDN}]}}
    candidates = bot.extract_shopaikey_suno_audio_candidates(payload, provider_name="key4u_suno")

    assert candidates
    assert candidates[0]["field_path"] == "data.data[0].cld2AudioUrl"
    assert candidates[0]["rejected"] is False
    assert candidates[0]["selected_reason"] == "cld2_audio_url_candidate"
    selected = bot.select_music_provider_audio_candidate(candidates)
    assert selected["url"] == BARE_CDN
    assert "cld2_audio_url_candidate" in bot.music_provider_candidate_paths_text(candidates)


def test_no_download_endpoint_attempts_direct_bare_cdn_before_clean_no_charge(monkeypatch):
    class FakeProvider:
        async def suno_query(self, task_id):
            return {
                "ok": True,
                "status": "SUCCESS",
                "http_status": 200,
                "raw_provider_result": {"data": {"data": [{"cld2AudioUrl": BARE_CDN}]}},
            }

    store = {JOB_ID: _job(status="submitted", provider_completed=False, music_provider_completed=False)}

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or JOB_ID)] = current
        return dict(current)

    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_ENDPOINT", "")
    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: FakeProvider())
    monkeypatch.setattr(bot, "record_music_provider_attempt", lambda **kwargs: None)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(store.get(str(job_id)) or {}))
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)

    result = asyncio.run(bot.poll_music_suno_async_job(JOB_ID, updated_by=USER_ID))
    job = result["job"]

    assert result["status"] == "RESULT_URL_DOWNLOAD_FAILED"
    assert job["terminal_state"] == "failed_no_charge"
    assert job["primary_blocker"] in {
        "artifact_download_failed",
        "result_url_expired",
        "artifact_invalid_content_type",
        "result_url_forbidden_access_denied",
    }
    assert job["candidate_attempted"] is True
    assert job["candidate_bare_url_allowed_for_validation"] is True
    assert job["charged_xu"] == 0


def test_download_endpoint_with_task_and_url_materializes(monkeypatch, tmp_path):
    calls = []

    class FakeResponse:
        status_code = 200
        content = AUDIO_BYTES
        headers = {"content-type": "audio/mpeg"}

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

    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "https://api.key4u.shop/suno/download/{taskId}?source={url}")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "key4u-secret")
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(provider_result_candidates=[_bare_candidate()]),
            updated_by=USER_ID,
            source="h10",
        )
    )
    job = result["job"]

    assert result["ok"] is True
    assert calls and f"/{TASK_ID}" in calls[0][0]
    assert "https%3A%2F%2Fcdn1.suno.ai%2Fsong.mp3" in calls[0][0]
    assert calls[0][1]["Authorization"].startswith("Bearer ")
    assert job["provider_download_endpoint_attempted"] is True
    assert job["provider_download_http_status"] == 200
    assert job["provider_download_bytes"] == len(AUDIO_BYTES)
    assert job["audio_validated"] is True


def test_download_endpoint_bad_http_failed_no_charge_safe_debug(monkeypatch, tmp_path):
    class FakeResponse:
        status_code = 500
        content = b'{"error":"provider busy","token":"secret-token"}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"error": "provider busy", "token": "secret-token"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return FakeResponse()

    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "https://api.key4u.shop/suno/download/{taskId}?token=secret-token")
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(provider_result_candidates=[_bare_candidate()]),
            updated_by=USER_ID,
            source="h10",
        )
    )
    job = result["job"]

    assert result["ok"] is False
    assert job["terminal_state"] == "failed_no_charge"
    assert job["provider_download_endpoint_attempted"] is True
    assert job["provider_download_http_status"] == 500
    assert job["provider_download_content_type"] == "application/json"
    assert "secret-token" not in bot.music_job_debug_text(JOB_ID)


def test_recovery_refetches_provider_result_delivers_once_and_does_not_resubmit(monkeypatch, tmp_path):
    deliveries = []
    poll_calls = []
    submit_calls = []
    store = {JOB_ID: _job(status="completed", provider_completed=True, music_provider_completed=True)}

    class FakeResponse:
        status_code = 200
        content = AUDIO_BYTES
        headers = {"content-type": "audio/mpeg"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return FakeResponse()

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or JOB_ID)] = current
        return dict(current)

    async def fake_poll(state, updated_by=""):
        poll_calls.append(dict(state))
        return {
            "ok": False,
            "status": "COMPLETED_NO_DOWNLOADABLE_AUDIO",
            "output_url": "",
            "raw_provider_result": {"data": {"data": [{"cld2AudioUrl": BARE_CDN}]}},
            "provider_result_candidates": bot.music_provider_audio_candidate_records([
                bot.extract_shopaikey_suno_audio_candidates({"data": {"data": [{"cld2AudioUrl": BARE_CDN}]}}, provider_name="key4u_suno")[0]
            ]),
        }

    async def fail_submit(*args, **kwargs):
        submit_calls.append(True)
        raise AssertionError("must not resubmit")

    async def fake_send_music(*args, **kwargs):
        deliveries.append(kwargs)
        updated = bot.record_music_job_full_send(
            kwargs.get("job"),
            SimpleNamespace(message_id=1001, audio=SimpleNamespace(file_id="file-h10")),
            kwargs.get("audio_bytes"),
            result=kwargs.get("result"),
            updated_by=USER_ID,
        )
        return {"ok": True, "status": "SENT", "job": updated, "delivery_message_id": "1001"}

    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "https://api.key4u.shop/suno/download/{taskId}?source={url}")
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(store.get(str(job_id)) or {}))
    monkeypatch.setattr(
        bot,
        "get_engine_async_job_lookup",
        lambda _job_id: {"job": dict(store.get(JOB_ID) or {}), "lookup_found": True, "canonical_job_id": JOB_ID, "resolved_job_id": JOB_ID, "legacy_job_id": ""},
    )
    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    monkeypatch.setattr(bot, "submit_music_generation_job", fail_submit)
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda current: {})
    monkeypatch.setattr(bot, "send_music_product_audio_result", fake_send_music)

    ctx = SimpleNamespace(bot=SimpleNamespace())
    first = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=ctx, user_id=USER_ID, source="admin_recover"))
    second = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=ctx, user_id=USER_ID, source="admin_recover"))

    assert first["ok"] is True
    assert second["ok"] is True
    assert len(deliveries) == 1
    assert poll_calls
    assert submit_calls == []


def test_music_provider_audit_shows_setup_required_without_endpoint(monkeypatch):
    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_URL", "")
    monkeypatch.setattr(bot, "KEY4U_SUNO_WAV_ENDPOINT", "")
    monkeypatch.setattr(
        bot,
        "list_engine_async_jobs",
        lambda feature="", limit=1, active_only=False: [_job(
            primary_blocker=bot.KEY4U_SUNO_BARE_CDN_SETUP_BLOCKER,
            setup_required=bot.KEY4U_SUNO_DOWNLOAD_SETUP_REQUIRED,
            rejected_candidate_reasons=["data.data[0].cld2AudioUrl:rejected_bare_suno_cdn_no_query:cdn1.suno.ai.mp3"],
        )],
    )

    text = bot.music_provider_audit_text()

    assert "download endpoint configured: <code>no</code>" in text
    assert bot.KEY4U_SUNO_DOWNLOAD_SETUP_REQUIRED in text
    assert "data.data[0].cld2AudioUrl" in text
    assert "token=" not in text
