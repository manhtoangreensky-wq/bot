import asyncio

import bot


AUDIO_BYTES = b"RIFF-toan-aas-h13-real-wav" * 320
JOB_ID = "MUSH13CLIP01"
USER_ID = 230713
TASK_ID = "1279444349692403713"
CDN_STEM = "cdnStemNotClip123"
TRACK_ID = "trackClipABC123"
TRACK_ID_2 = "trackClipXYZ789"
BARE_CDN = f"https://cdn1.suno.ai/{CDN_STEM}.mp3"


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


def _provider_result(*items):
    return {"code": "SUCCESS", "data": {"data": list(items)}}


def _patch_key4u_wav_env(monkeypatch):
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
        path = tmp_path / "h13-vault.wav"
        path.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": "MV-H13", "storage_ref": str(path)}

    def fake_write(_job, payload):
        path = tmp_path / "canonical-h13.wav"
        path.write_bytes(bytes(payload or b""))
        return str(path)

    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", fake_upsert)
    monkeypatch.setattr(bot, "write_music_canonical_artifact", fake_write)
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: None)


def _patch_job_save(monkeypatch):
    def fake_save(payload):
        return dict(payload)

    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)


def _audio_response():
    class AudioResponse:
        status_code = 200
        content = AUDIO_BYTES
        headers = {"content-type": "audio/wav"}

    return AudioResponse()


def _clip_rejected_response(message="no found clipId"):
    class JsonResponse:
        status_code = 200
        content = b'{"code":1010,"data":{"tn":0},"msg":"no found clipId"}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"code": 1010, "data": {"tn": 0}, "msg": message}

    return JsonResponse()


def test_fetch_result_data_data_id_used_for_wav_not_provider_task(monkeypatch, tmp_path):
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
            assert TASK_ID not in url
            assert CDN_STEM not in url
            assert TRACK_ID in url
            return _audio_response()

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_save(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(
                provider_result_candidates=[_bare_candidate()],
                raw_provider_result_internal=_provider_result({"id": TRACK_ID, "cld2AudioUrl": BARE_CDN, "title": "safe"}),
            ),
            updated_by=USER_ID,
            source="h13_data_data_id",
        )
    )
    job = result["job"]

    assert result["ok"] is True
    assert calls == [f"https://api.key4u.shop/suno/act/wav/{TRACK_ID}"]
    assert job["selected_clip_id_source_path"] == "data.data[0].id"
    assert job["wav_request_clip_id_source"] == "data.data[0].id"
    assert job["selected_clip_id_present"] is True
    assert job["wav_request_used_provider_task_id_fallback"] is False
    assert job["provider_result_item_count"] == 1
    assert job["final_audio_bytes"] == len(AUDIO_BYTES)
    assert job["audio_validated"] is True


def test_fetch_result_data_data_clipid_used_for_wav(monkeypatch, tmp_path):
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
            return _audio_response()

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_save(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(
                provider_result_candidates=[_bare_candidate()],
                raw_provider_result_internal=_provider_result({"clipId": TRACK_ID, "cld2AudioUrl": BARE_CDN}),
            ),
            updated_by=USER_ID,
            source="h13_data_data_clipid",
        )
    )
    job = result["job"]

    assert result["ok"] is True
    assert calls == [f"https://api.key4u.shop/suno/act/wav/{TRACK_ID}"]
    assert job["selected_clip_id_source_path"] == "data.data[0].clipId"
    assert job["clip_id_candidates_found"] == 1


def test_first_clip_candidate_rejected_second_candidate_succeeds(monkeypatch, tmp_path):
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
            if TRACK_ID in url:
                return _clip_rejected_response()
            if TRACK_ID_2 in url:
                return _audio_response()
            raise AssertionError(f"unexpected URL {url}")

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_save(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(
                provider_result_candidates=[_bare_candidate()],
                raw_provider_result_internal=_provider_result(
                    {"id": TRACK_ID, "cld2AudioUrl": BARE_CDN},
                    {"id": TRACK_ID_2, "cld2AudioUrl": f"https://cdn1.suno.ai/{TRACK_ID_2}.mp3"},
                ),
            ),
            updated_by=USER_ID,
            source="h13_retry_clip_candidates",
        )
    )
    job = result["job"]

    assert result["ok"] is True
    assert calls == [
        f"https://api.key4u.shop/suno/act/wav/{TRACK_ID}",
        f"https://api.key4u.shop/suno/act/wav/{TRACK_ID_2}",
    ]
    assert job["selected_clip_id_source_path"] == "data.data[1].id"
    assert job["clip_id_candidates_found"] == 2
    assert "data.data[0].id|http=200|shape=json_data_object|status=1010" in job["clip_id_candidate_statuses"]
    assert "data.data[1].id|http=200|shape=audio_bytes" in job["clip_id_candidate_statuses"]
    assert job["final_audio_download_status"] == "PASS"


def test_no_clip_id_in_provider_result_sets_missing_blocker(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            raise AssertionError("WAV endpoint must not be called without clip id")

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_save(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(
                provider_result_candidates=[_bare_candidate()],
                raw_provider_result_internal=_provider_result({"cld2AudioUrl": BARE_CDN, "title": "safe"}),
            ),
            updated_by=USER_ID,
            source="h13_missing_clip_id",
        )
    )
    job = result["job"]

    assert result["ok"] is False
    assert job["terminal_state"] == "failed_no_charge"
    assert job["primary_blocker"] == bot.KEY4U_SUNO_CLIP_ID_MISSING_BLOCKER
    assert job["provider_result_item_count"] == 1
    assert job["provider_result_item0_keys"] == "cld2AudioUrl,title"
    assert job["clip_id_candidates_found"] == 0
    assert job["selected_clip_id_present"] is False
    assert job["final_audio_bytes"] == 0
    assert job["artifact_ready"] is False


def test_all_clip_id_candidates_rejected_sets_rejected_blocker(monkeypatch, tmp_path):
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
            return _clip_rejected_response()

    _patch_key4u_wav_env(monkeypatch)
    _patch_success_materialize(monkeypatch, tmp_path)
    _patch_job_save(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        bot.materialize_music_artifact_for_job(
            _job(
                provider_result_candidates=[_bare_candidate()],
                raw_provider_result_internal=_provider_result(
                    {"id": TRACK_ID, "cld2AudioUrl": BARE_CDN},
                    {"id": TRACK_ID_2, "cld2AudioUrl": f"https://cdn1.suno.ai/{TRACK_ID_2}.mp3"},
                ),
            ),
            updated_by=USER_ID,
            source="h13_all_clip_ids_rejected",
        )
    )
    job = result["job"]

    assert result["ok"] is False
    assert calls == [
        f"https://api.key4u.shop/suno/act/wav/{TRACK_ID}",
        f"https://api.key4u.shop/suno/act/wav/{TRACK_ID_2}",
    ]
    assert job["primary_blocker"] == bot.KEY4U_SUNO_WAV_CLIP_ID_REJECTED_BLOCKER
    assert job["clip_id_candidates_found"] == 2
    assert "status=1010" in job["clip_id_candidate_statuses"]
    assert job["final_audio_bytes"] == 0
    assert job["audio_validated"] is False
