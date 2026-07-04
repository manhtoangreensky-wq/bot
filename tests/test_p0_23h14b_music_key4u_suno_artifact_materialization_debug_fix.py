import asyncio
import inspect
from types import SimpleNamespace

import bot


AUDIO_BYTES = b"ID3-toan-aas-h14b-real-music" * 320
JOB_ID = "MUSDEAD7C7D"
USER_ID = 230714
TASK_ID = "1279444349692403713"
WRONG_ITEM_ID = "wrongTrackIdABC123"
CLIP_ID = "clipIdLiveABC123"
BARE_CDN = f"https://cdn1.suno.ai/{CLIP_ID}.mp3"


def _provider_result(*items):
    return {"code": "SUCCESS", "data": {"data": list(items)}}


def _raw_provider_result():
    return _provider_result(
        {
            "id": WRONG_ITEM_ID,
            "clipId": CLIP_ID,
            "cld2AudioUrl": BARE_CDN,
            "progress": "100%",
            "prompt": "TOAN AAS test song",
        }
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
        "status": "completed",
        "provider_completed": True,
        "music_provider_completed": True,
        "provider_submit_called": True,
        "raw_provider_result_saved": True,
        "raw_provider_result_internal": _raw_provider_result(),
        "provider_result_candidates": _candidate_records(),
        "pending_charge_xu": 300,
        "charged_xu": 0,
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


def _patch_success_materialize(monkeypatch, tmp_path, *, duration=188):
    async def fake_duration(_audio, fallback=0):
        return duration

    def fake_upsert(*, audio_bytes, result=None, job=None, status="generated_unused", updated_by=""):
        path = tmp_path / "h14b-vault.mp3"
        path.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": "MV-H14B", "storage_ref": str(path)}

    def fake_write(_job, payload):
        path = tmp_path / "canonical-h14b.mp3"
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


class _JsonMissingAudioResponse:
    status_code = 200
    content = b'{"code":"success","data":{"status":"ready","message":"no file yet"},"message":""}'
    headers = {"content-type": "application/json"}

    def json(self):
        return {"code": "success", "data": {"status": "ready", "message": "no file yet"}, "message": ""}


class _AudioResponse:
    status_code = 200
    content = AUDIO_BYTES
    headers = {"content-type": "audio/mpeg"}


class _JsonInvalidAudioResponse:
    status_code = 200
    content = b'{"error":"AccessDenied"}'
    headers = {"content-type": "application/json"}

    def json(self):
        return {"error": "AccessDenied"}


class _CaptureMessage:
    def __init__(self):
        self.outputs = []
        self.chat_id = USER_ID

    async def reply_text(self, text, **kwargs):
        if len(str(text or "")) > 4096:
            raise RuntimeError("message is too long")
        self.outputs.append({"text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=len(self.outputs))


def test_music_job_debug_never_generic_fails_for_artifact_failed_job(monkeypatch):
    noisy_paths = "; ".join(f"data.data[{idx}].cld2AudioUrl|cdn1.suno.ai.mp3|no-query" for idx in range(160))
    job = _job(
        terminal_state="failed_no_charge",
        music_terminal_state="failed_no_charge",
        primary_blocker=bot.KEY4U_SUNO_WAV_JSON_OBJECT_BLOCKER,
        fail_stage="artifact",
        key4u_suno_fetch_candidate_paths_text=noisy_paths,
        candidate_paths_text=noisy_paths,
    )
    _patch_job_store(monkeypatch, job)
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)

    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=_CaptureMessage())
    asyncio.run(bot.cmd_music_job_debug(update, SimpleNamespace(args=[JOB_ID])))

    text = update.message.outputs[-1]["text"]
    assert len(text) <= 4096
    assert "Music job debug" in text
    assert bot.KEY4U_SUNO_WAV_JSON_OBJECT_BLOCKER in text
    assert "Có lỗi khi xử lý lệnh" not in text


def test_completed_key4u_result_selects_clip_id_from_data_item():
    candidates = bot.music_key4u_suno_clip_id_candidates_from_payload(_raw_provider_result(), provider_task_id=TASK_ID)
    assert candidates
    assert candidates[0]["clip_id"] == CLIP_ID
    assert candidates[0]["source_path"] == "data.data[0].clipId"


def test_selected_clip_id_source_path_recorded(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _JsonMissingAudioResponse()

    _patch_key4u_env(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    audio, detail, status = asyncio.run(
        bot.music_provider_proxy_download_audio(
            provider_name="key4u_suno",
            provider_task_id=TASK_ID,
            raw_url=BARE_CDN,
            raw_provider_result=_raw_provider_result(),
        )
    )
    fields = bot.music_key4u_suno_wav_detail_fields(detail)

    assert audio == b""
    assert status == 200
    assert fields["selected_clip_id_present"] is True
    assert fields["selected_clip_id_source_path"] == "data.data[0].clipId"
    assert fields["wav_request_clip_id_source"] == "data.data[0].clipId"


def test_wav_request_uses_selected_clip_id_not_provider_task_id_when_clip_exists(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            calls.append(url)
            return _AudioResponse()

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14b_clip"))
    job = result["job"]

    assert result["ok"] is True
    assert calls == [f"https://api.key4u.shop/suno/act/wav/{CLIP_ID}"]
    assert TASK_ID not in calls[0]
    assert WRONG_ITEM_ID not in calls[0]
    assert job["selected_clip_id_source_path"] == "data.data[0].clipId"
    assert job["wav_request_used_provider_task_id_fallback"] is False


def test_json_download_response_missing_audio_url_reports_safe_blocker(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _JsonMissingAudioResponse()

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14b_json_missing"))
    job = result["job"]

    assert result["ok"] is False
    assert job["terminal_state"] == "failed_no_charge"
    assert job["primary_blocker"] == bot.KEY4U_SUNO_WAV_JSON_OBJECT_BLOCKER
    assert job["wav_response_shape"] == "json_data_object"
    assert job["wav_json_audio_url_found"] is False
    assert job["wav_json_task_id_found"] is False
    assert job["selected_clip_id_source_path"] == "data.data[0].clipId"
    assert job["artifact_ready"] is False
    assert job["audio_validated"] is False


def test_bare_suno_cdn_mp3_not_rejected_before_validation(monkeypatch, tmp_path):
    calls = []

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
                return _AudioResponse()
            return _JsonMissingAudioResponse()

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14b_bare_cdn_valid"))
    job = result["job"]

    assert result["ok"] is True
    assert any("cdn1.suno.ai" in url for url in calls)
    assert job["artifact_ready"] is True
    assert job["audio_validated"] is True
    assert job["final_audio_download_status"] == "PASS"


def test_bare_suno_cdn_mp3_rejected_if_get_returns_json_or_invalid_audio(monkeypatch, tmp_path):
    calls = []

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
                return _JsonInvalidAudioResponse()
            return _JsonMissingAudioResponse()

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14b_bare_cdn_invalid"))
    job = result["job"]

    assert result["ok"] is False
    assert any("cdn1.suno.ai" in url for url in calls)
    assert job["artifact_ready"] is False
    assert job["audio_validated"] is False
    assert int(job["final_audio_bytes"] or 0) == 0
    assert job["primary_blocker"] in {bot.KEY4U_SUNO_WAV_JSON_OBJECT_BLOCKER, "artifact_invalid_content_type", "artifact_download_failed"}


def test_valid_audio_download_sets_artifact_ready_and_audio_validated(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _AudioResponse()

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14b_valid_audio"))
    job = result["job"]

    assert result["ok"] is True
    assert job["output_bytes"] == len(AUDIO_BYTES)
    assert job["artifact_ready"] is True
    assert job["audio_validated"] is True
    assert job["music_artifact_ready"] is True
    assert job["music_audio_validated"] is True


def test_recover_materializes_saved_completed_provider_result_without_new_job(monkeypatch, tmp_path):
    deliveries = []
    forbidden_calls = []
    store = _patch_job_store(monkeypatch, _job(provider_result_candidates=[]))

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _AudioResponse()

    async def fake_send_music(*args, **kwargs):
        deliveries.append(kwargs)
        updated = bot.record_music_job_full_send(
            kwargs.get("job"),
            SimpleNamespace(message_id=9001, audio=SimpleNamespace(file_id="file-h14b")),
            kwargs.get("audio_bytes"),
            result=kwargs.get("result"),
            updated_by=USER_ID,
        )
        store[JOB_ID] = updated
        return {"ok": True, "status": "SENT", "job": updated, "delivery_message_id": "9001"}

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot, "poll_music_generation_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not poll before saved raw materialization")))
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda *args, **kwargs: forbidden_calls.append("create"))
    monkeypatch.setattr(bot, "submit_music_generation_job", lambda *args, **kwargs: forbidden_calls.append("submit"))
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: forbidden_calls.append("execute"))
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda current: {})
    monkeypatch.setattr(bot, "send_music_product_audio_result", fake_send_music)

    result = asyncio.run(
        bot.deliver_music_ready_artifact_once(
            JOB_ID,
            context=SimpleNamespace(bot=SimpleNamespace()),
            user_id=USER_ID,
            source="h14b_recover",
        )
    )

    assert result["ok"] is True
    assert len(deliveries) == 1
    assert forbidden_calls == []
    assert store[JOB_ID]["audio_validated"] is True


def test_delivery_and_charge_only_after_validated_audio(monkeypatch, tmp_path):
    charge_calls = []
    send_calls = []
    _patch_job_store(monkeypatch, _job())

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return _JsonInvalidAudioResponse()

    def fake_charge(*args, **kwargs):
        charge_calls.append((args, kwargs))
        return {"ok": True}

    async def fake_send_music(*args, **kwargs):
        send_calls.append(kwargs)
        return {"ok": True, "status": "SENT"}

    _patch_key4u_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot, "poll_music_generation_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not resubmit or poll")))
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda current: {})
    monkeypatch.setattr(bot, "send_music_product_audio_result", fake_send_music)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", fake_charge)

    result = asyncio.run(
        bot.deliver_music_ready_artifact_once(
            JOB_ID,
            context=SimpleNamespace(bot=SimpleNamespace()),
            user_id=USER_ID,
            source="h14b_invalid_no_charge",
        )
    )

    assert result["ok"] is False
    assert send_calls == []
    assert charge_calls == []
    assert result["primary_blocker"] in {bot.KEY4U_SUNO_WAV_JSON_OBJECT_BLOCKER, "artifact_invalid_content_type", "artifact_download_failed"}


def test_no_product_video_subdub_payos_pricing_db_changes():
    source = "\n".join(
        inspect.getsource(obj)
        for obj in (
            bot.music_job_debug_text,
            bot.cmd_music_job_debug,
            bot.music_key4u_suno_clip_id_candidates_from_payload,
            bot.music_provider_proxy_download_audio,
            bot.music_download_artifact_candidate,
            bot.music_delivery_artifact_candidates,
            bot.materialize_music_artifact_for_job,
        )
    )
    forbidden = ("PayOS", "wallet", "VIDEO_", "SUBDUB", "VOICE_", "CANONICAL_PRICE", "CREATE TABLE", "ALTER TABLE")
    assert not any(term in source for term in forbidden)
