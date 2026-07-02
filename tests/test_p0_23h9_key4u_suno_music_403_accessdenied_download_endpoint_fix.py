import asyncio
import inspect

import bot


AUDIO_BYTES = b"ID3-toan-aas-h9-real-music" * 320
JOB_ID = "MUSH9KEY4U01"
USER_ID = 230709
TASK_ID = "1279444349692403713"
BARE_CDN = "https://cdn1.suno.ai/song.mp3"
SIGNED_URL = "https://cdn1.suno.ai/song.mp3?token=abc&Expires=999"


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
        "status": "submitted",
        "pending_charge_xu": 300,
        "charged_xu": 0,
    }
    data.update(overrides)
    return data


class _FakeKey4U:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def suno_query(self, task_id):
        self.calls.append(task_id)
        if len(self.responses) > 1:
            return dict(self.responses.pop(0))
        return dict(self.responses[0])


def _completed(payload):
    return {
        "ok": True,
        "status": "SUCCESS",
        "http_status": 200,
        "output_url": BARE_CDN,
        "raw_provider_result": payload,
    }


def test_candidate_ranking_rejects_bare_music_output_url_over_signed_download_url():
    payload = {
        "data": {
            "music_output_url": BARE_CDN,
            "download_url": SIGNED_URL,
        }
    }
    candidates = bot.extract_shopaikey_suno_audio_candidates(payload, provider_name="key4u_suno")
    bare = next(item for item in candidates if item["field_path"] == "data.music_output_url")
    selected = bot.select_music_provider_audio_candidate(candidates)
    assert bare["rejected"] is True
    assert bare["reject_reason"] == "bare_suno_cdn_no_query"
    assert selected["field_path"] == "data.download_url"
    assert selected["selected_reason"] in {"signed_url_candidate", "query_url_candidate", "download_url_candidate"}


def test_signed_url_candidate_priority():
    payload = {
        "music_output_url": BARE_CDN,
        "signed_url": SIGNED_URL,
        "preview_url": "https://cdn1.suno.ai/preview.mp3?token=preview",
    }
    selected = bot.select_music_provider_audio_candidate(
        bot.extract_shopaikey_suno_audio_candidates(payload, provider_name="key4u_suno")
    )
    assert selected["field_path"] == "signed_url"
    assert selected["url"] == SIGNED_URL


def test_key4u_fetch_retries_when_only_bare_cdn_url(monkeypatch):
    provider = _FakeKey4U([
        _completed({"data": {"music_output_url": BARE_CDN}}),
        _completed({"data": {"music_output_url": BARE_CDN}}),
    ])
    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: provider)
    monkeypatch.setattr(bot, "record_music_provider_attempt", lambda **kwargs: None)

    result = asyncio.run(bot.poll_music_generation_job({"music_provider": "key4u_suno", "music_task_id": TASK_ID}, updated_by=USER_ID))

    assert provider.calls == [TASK_ID, TASK_ID]
    assert result["ok"] is False
    assert result["status"] == "COMPLETED_NO_DOWNLOADABLE_AUDIO"
    assert result["primary_blocker"] == "result_url_forbidden_access_denied"
    assert result["recovery_action"] == "need_key4u_signed_download_field_or_proxy"
    assert result["key4u_suno_fetch_retried"] is True
    assert "data.music_output_url" in result["key4u_suno_fetch_candidate_paths_text"]


def test_key4u_fetch_second_attempt_uses_download_url(monkeypatch):
    provider = _FakeKey4U([
        _completed({"data": {"music_output_url": BARE_CDN}}),
        _completed({"data": {"music_output_url": BARE_CDN, "download_url": SIGNED_URL}}),
    ])
    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: provider)
    monkeypatch.setattr(bot, "record_music_provider_attempt", lambda **kwargs: None)

    result = asyncio.run(bot.poll_music_generation_job({"music_provider": "key4u_suno", "music_task_id": TASK_ID}, updated_by=USER_ID))

    assert result["ok"] is True
    assert result["output_url"] == SIGNED_URL
    assert result["key4u_suno_fetch_retried"] is True
    assert result["selected_artifact_field_path"] == "data.download_url"


def test_completed_only_bare_cdn_sets_failed_no_charge(monkeypatch):
    store = {JOB_ID: _job()}
    provider = _FakeKey4U([
        _completed({"data": {"music_output_url": BARE_CDN}}),
        _completed({"data": {"music_output_url": BARE_CDN}}),
    ])

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or JOB_ID)] = current
        return dict(current)

    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: provider)
    monkeypatch.setattr(bot, "record_music_provider_attempt", lambda **kwargs: None)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda job_id: dict(store.get(job_id) or {}))
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)

    result = asyncio.run(bot.poll_music_suno_async_job(JOB_ID, updated_by=USER_ID))
    job = result["job"]

    assert result["status"] == "RESULT_URL_FORBIDDEN_ACCESS_DENIED"
    assert job["terminal_state"] == "failed_no_charge"
    assert job["primary_blocker"] == "result_url_forbidden_access_denied"
    assert job["charged_xu"] == 0
    assert job["progress_text"] == "Bài hát đã tạo xong nhưng hệ thống chưa lấy được file nhạc từ nhà cung cấp. Bot chưa trừ Xu."
    assert "cdn" not in job["progress_text"].lower()
    assert "api" not in job["progress_text"].lower()


def test_provider_download_endpoint_binary_audio(monkeypatch):
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

    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "https://api.key4u.shop/suno/download/{taskId}")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "key4u-secret")
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)

    audio, detail, status = asyncio.run(
        bot.music_provider_proxy_download_audio(provider_name="key4u_suno", provider_task_id=TASK_ID)
    )

    assert audio == AUDIO_BYTES
    assert status == 200
    assert calls[0][0].endswith(f"/{TASK_ID}")
    assert calls[0][1]["Authorization"].startswith("Bearer ")
    assert "provider_download_endpoint_attempted=yes" in detail


def test_provider_download_endpoint_json_signed_url(monkeypatch):
    download_calls = []

    class FakeResponse:
        status_code = 200
        content = b'{"data":{"signed_url":"https://cdn1.suno.ai/song.mp3?token=json"}}'
        headers = {"content-type": "application/json"}

        def json(self):
            return {"data": {"signed_url": "https://cdn1.suno.ai/song.mp3?token=json"}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return FakeResponse()

    async def fake_download(url, timeout_seconds=60.0, headers=None):
        download_calls.append(url)
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "KEY4U_SUNO_DOWNLOAD_URL", "https://api.key4u.shop/suno/download/{taskId}")
    monkeypatch.setattr(bot.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)

    audio, detail, status = asyncio.run(
        bot.music_provider_proxy_download_audio(provider_name="key4u_suno", provider_task_id=TASK_ID)
    )

    assert audio == AUDIO_BYTES
    assert status == 200
    assert download_calls == ["https://cdn1.suno.ai/song.mp3?token=json"]
    assert "provider_download_json_field=data.signed_url" in detail


def test_music_job_debug_lists_candidate_paths_safely(monkeypatch):
    signed = "https://cdn1.suno.ai/song.mp3?token=very-secret"
    job = _job(
        result_url=signed,
        key4u_suno_fetch_attempted=True,
        key4u_suno_fetch_http_status=200,
        key4u_suno_fetch_status_raw="SUCCESS",
        key4u_suno_fetch_candidate_paths_text="data.music_output_url|cdn1.suno.ai.mp3|cdn1.suno.ai|.mp3|no-query|bare_suno_cdn_no_query; data.download_url|cdn1.suno.ai.mp3|cdn1.suno.ai|.mp3|query|download_url_candidate",
        selected_artifact_field_path="data.download_url",
        selected_artifact_selected_reason="download_url_candidate",
        music_output_url_reject_reason="bare_suno_cdn_no_query",
        provider_download_endpoint_configured=True,
    )
    monkeypatch.setattr(
        bot,
        "get_engine_async_job_lookup",
        lambda _job_id: {"job": job, "lookup_found": True, "canonical_job_id": JOB_ID, "resolved_job_id": JOB_ID, "legacy_job_id": ""},
    )

    text = bot.music_job_debug_text(JOB_ID)

    assert "data.music_output_url" in text
    assert "bare_suno_cdn_no_query" in text
    assert "very-secret" not in text
    assert "key4u_suno_fetch_attempted" in text


def test_music_provider_audit_admin_only_and_shows_key4u_fetch_config(monkeypatch):
    source = inspect.getsource(bot.cmd_music_provider_audit)
    assert "is_admin_user" in source
    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda feature="", limit=1, active_only=False: [_job(
        key4u_suno_fetch_candidate_paths_text="data.music_output_url|cdn1.suno.ai.mp3|cdn1.suno.ai|.mp3|no-query|bare_suno_cdn_no_query",
        primary_blocker="result_url_forbidden_access_denied",
    )])
    text = bot.music_provider_audit_text()
    assert "submit URL configured" in text
    assert "fetch URL configured" in text
    assert "download endpoint configured" in text
    assert "data.music_output_url" in text
    assert "result_url_forbidden_access_denied" in text
