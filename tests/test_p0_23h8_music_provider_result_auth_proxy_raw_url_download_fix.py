import asyncio
from types import SimpleNamespace

import bot


AUDIO_BYTES = b"ID3-toan-aas-h8-real-music" * 320
JOB_ID = "MUSH8RAW01"
USER_ID = 230708


def _job(**overrides):
    data = {
        "internal_job_id": JOB_ID,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": "provider-h8-task",
        "provider_job_id": "provider-h8-task",
        "status": "completed",
        "provider_completed": True,
        "music_provider_completed": True,
        "pending_charge_xu": 0,
        "charged_xu": 0,
    }
    data.update(overrides)
    return data


def _patch_success_materialize(monkeypatch, tmp_path, *, duration=188):
    async def fake_duration(_audio, fallback=0):
        return duration

    def fake_upsert(*, audio_bytes, result=None, job=None, status="generated_unused", updated_by=""):
        path = tmp_path / "h8.mp3"
        path.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": "MV-H8", "storage_ref": str(path)}

    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", fake_upsert)
    monkeypatch.setattr(bot, "write_music_canonical_artifact", lambda job, payload: str(tmp_path / "canonical.mp3"))
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: dict(payload))


def test_download_uses_raw_url_not_safe_label(monkeypatch):
    raw = "https://cdn1.suno.ai/song.mp3?token=secret&Expires=999"
    calls = []

    async def fake_download(url, timeout_seconds=60.0):
        calls.append(url)
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    async def fake_duration(_audio, fallback=0):
        return 180

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    result = asyncio.run(bot.select_music_delivery_artifact({}, _job(result_url=raw)))
    assert result["ok"] is True
    assert calls == [raw]
    assert result["selected_artifact_url"] == "https://cdn1.suno.ai/song.mp3"


def test_signed_query_preserved_for_download(monkeypatch):
    raw = "https://cdn1.suno.ai/song.mp3?X-Amz-Signature=abc&X-Amz-Expires=60"
    seen = []

    async def fake_download(url, timeout_seconds=60.0):
        seen.append(url)
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    async def fake_duration(_audio, fallback=0):
        return 180

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    asyncio.run(bot.select_music_delivery_artifact({}, _job(output_url=raw)))
    assert seen[0].endswith("?X-Amz-Signature=abc&X-Amz-Expires=60")


def test_debug_masks_signed_query(monkeypatch):
    raw = "https://cdn1.suno.ai/song.mp3?token=very-secret-token"
    job = _job(result_url=raw, result_url_query_present=True, result_url_signature_param_present=True)
    monkeypatch.setattr(bot, "get_engine_async_job_lookup", lambda _job_id: {"job": job, "lookup_found": True, "canonical_job_id": JOB_ID, "resolved_job_id": JOB_ID, "legacy_job_id": ""})
    text = bot.music_job_debug_text(JOB_ID)
    assert "very-secret-token" not in text
    assert "cdn1.suno.ai.mp3" in text
    assert "signature_param_present" in text


def test_signature_param_loss_sets_signature_invalid_blocker():
    detail = "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=SignatureDoesNotMatch"
    assert bot.music_download_error_category(detail, 403) == "result_url_signature_lost_or_invalid"


def test_extracts_multiple_provider_audio_candidates():
    payload = {"data": [{"download_url": "https://cdn/a.mp3"}, {"audio_url": "https://cdn/b.mp3?token=1"}]}
    candidates = bot.extract_shopaikey_suno_audio_candidates(payload, provider_name="shopaikey_music")
    assert len([item for item in candidates if not item["rejected"]]) == 2


def test_prefers_download_url_over_preview_url():
    payload = {"preview_url": "https://cdn/preview.mp3", "download_url": "https://cdn/full.mp3"}
    selected = bot.select_music_provider_audio_candidate(bot.extract_shopaikey_suno_audio_candidates(payload))
    assert selected["field_path"] == "download_url"


def test_prefers_query_signed_audio_url():
    payload = {"audio_url": "https://cdn/full.mp3?token=abc", "cdn_url": "https://cdn/full.mp3"}
    selected = bot.select_music_provider_audio_candidate(bot.extract_shopaikey_suno_audio_candidates(payload))
    assert selected["url"].endswith("?token=abc")
    assert selected["signature_param_present"] is True


def test_rejects_thumbnail_url():
    payload = {"thumbnail_url": "https://cdn/cover.jpg", "audio_url": "https://cdn/song.mp3"}
    candidates = bot.extract_shopaikey_suno_audio_candidates(payload)
    assert all(item["field_path"] != "thumbnail_url" or item["rejected"] for item in candidates)


def test_rejects_json_metadata_as_audio():
    payload = {"audio_url": "https://cdn/song.json"}
    candidates = bot.extract_shopaikey_suno_audio_candidates(payload)
    assert candidates and candidates[0]["rejected"] is True


def test_selected_artifact_field_path_saved(monkeypatch, tmp_path):
    raw = "https://cdn/song.mp3?token=abc"
    _patch_success_materialize(monkeypatch, tmp_path)

    async def fake_download(url, timeout_seconds=60.0):
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    job = _job(provider_result_candidates=[{"field_path": "data[0].download_url", "source": "data[0].download_url", "url": raw, "role": "provider_result_metadata", "rank": 1200, "has_query": True}])
    result = asyncio.run(bot.materialize_music_artifact_for_job(job, updated_by=USER_ID, source="provider_poll_completed"))
    assert result["job"]["selected_artifact_field_path"] == "data[0].download_url"


def test_403_access_denied_xml_classified_forbidden():
    detail = "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=AccessDenied"
    assert bot.music_download_error_category(detail, 403) == "result_url_forbidden"


def test_403_expired_token_xml_classified_expired():
    detail = "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=ExpiredToken"
    assert bot.music_download_error_category(detail, 403) == "result_url_expired"


def test_403_signature_mismatch_classified_signature_invalid():
    detail = "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=SignatureDoesNotMatch"
    assert bot.music_download_error_category(detail, 403) == "result_url_signature_lost_or_invalid"


def test_403_short_age_not_blindly_expired():
    detail = "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=AccessDenied; result_url_age_seconds=61"
    assert bot.music_download_error_category(detail, 403) != "result_url_expired"


def test_401_classified_auth_required():
    assert bot.music_download_error_category("http=401; downloaded_bytes=0", 401) == "provider_auth_required"


def test_direct_raw_signed_url_download_success(monkeypatch):
    raw = "https://cdn/song.mp3?token=abc"

    async def fake_download(url, timeout_seconds=60.0):
        assert url == raw
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    result = asyncio.run(bot.music_download_artifact_candidate({"url": raw}, _job(result_url=raw)))
    assert result["ok"] is True
    assert result["download_strategy_used"] == "direct_raw_url"


def test_provider_auth_header_download_success(monkeypatch):
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "key4u-secret")
    calls = []

    async def fake_download(url, timeout_seconds=60.0, headers=None):
        calls.append(headers or {})
        if headers and headers.get("Authorization"):
            return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200
        return b"", "http=401; downloaded_bytes=0; content_type=application/json", 401

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    result = asyncio.run(bot.music_download_artifact_candidate({"url": "https://api.key4u.shop/suno/file.mp3", "requires_auth": True, "provider_name": "key4u_suno"}, _job()))
    assert result["ok"] is True
    assert result["download_strategy_used"] == "provider_auth"
    assert any(call.get("Authorization") for call in calls)


def test_provider_proxy_download_success(monkeypatch):
    async def fake_download(url, timeout_seconds=60.0):
        return b"", "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=AccessDenied", 403

    async def fake_proxy(**kwargs):
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_provider_proxy_download_audio", fake_proxy)
    result = asyncio.run(bot.music_download_artifact_candidate({"url": "https://cdn/song.mp3", "provider_name": "shopaikey_music"}, _job(provider="shopaikey_music")))
    assert result["ok"] is True
    assert result["download_strategy_used"] == "provider_proxy"


def test_provider_repoll_fresh_url_success(monkeypatch, tmp_path):
    old = "https://cdn/old.mp3?token=old"
    fresh = "https://cdn/fresh.mp3?token=fresh"
    _patch_success_materialize(monkeypatch, tmp_path)
    saved = {}
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: saved.setdefault("job", dict(payload)) or dict(payload))

    async def fake_poll(state, updated_by=""):
        return {"ok": True, "status": "COMPLETED", "output_url": fresh, "raw_provider_result": {"download_url": fresh}}

    async def fake_download(url, timeout_seconds=60.0):
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    result = asyncio.run(bot.refresh_music_expired_result_url_for_job(_job(result_url=old), updated_by=USER_ID))
    assert result["ok"] is True
    assert result["job"]["refreshed_result_url"] is True


def test_repoll_same_url_then_proxy_attempted(monkeypatch, tmp_path):
    old = "https://cdn/same.mp3?token=old"
    _patch_success_materialize(monkeypatch, tmp_path)

    async def fake_poll(state, updated_by=""):
        return {"ok": True, "status": "COMPLETED", "output_url": old, "raw_provider_result": {"download_url": old}}

    async def fake_download(url, timeout_seconds=60.0):
        return b"", "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=AccessDenied", 403

    async def fake_proxy(**kwargs):
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_provider_proxy_download_audio", fake_proxy)
    result = asyncio.run(bot.refresh_music_expired_result_url_for_job(_job(result_url=old), updated_by=USER_ID))
    assert result["ok"] is True
    assert result["job"]["provider_proxy_attempted"] is True


def test_all_strategies_fail_clean_blocker(monkeypatch, tmp_path):
    _patch_success_materialize(monkeypatch, tmp_path)

    async def fake_download(url, timeout_seconds=60.0):
        return b"", "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=AccessDenied", 403

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(result_url="https://cdn/fail.mp3"), updated_by=USER_ID, source="h8"))
    assert result["ok"] is False
    assert result["job"]["primary_blocker"] == "result_url_forbidden"
    assert result["job"]["terminal_state"] == "failed_no_charge"


def test_provider_completed_materializes_with_provider_poll_completed_source(monkeypatch, tmp_path):
    _patch_success_materialize(monkeypatch, tmp_path)

    async def fake_download(url, timeout_seconds=60.0):
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(result_url="https://cdn/song.mp3"), updated_by=USER_ID, source="provider_poll_completed"))
    assert result["ok"] is True
    assert result["job"]["artifact_materialized_source"] == "provider_poll_completed"


def test_successful_materialization_sets_local_artifact_and_validates(monkeypatch, tmp_path):
    _patch_success_materialize(monkeypatch, tmp_path)

    async def fake_download(url, timeout_seconds=60.0):
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(result_url="https://cdn/song.mp3"), updated_by=USER_ID, source="h8"))
    assert result["job"]["local_artifact_path"]
    assert result["job"]["audio_validated"] is True


def test_successful_materialization_delivers_once(monkeypatch, tmp_path):
    deliveries = []
    job = _job(result_url="https://cdn/song.mp3")
    store = {JOB_ID: dict(job)}

    def fake_save(payload):
        current = dict(payload)
        store[str(current.get("internal_job_id") or JOB_ID)] = current
        return dict(current)

    _patch_success_materialize(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_engine_async_job_lookup", lambda _job_id: {"job": dict(store.get(JOB_ID) or {}), "lookup_found": True, "canonical_job_id": JOB_ID, "resolved_job_id": JOB_ID, "legacy_job_id": ""})
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(store.get(str(_job_id or JOB_ID)) or store.get(JOB_ID) or {}))
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda current: {})

    async def fake_download(url, timeout_seconds=60.0):
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    async def fake_send_music(*args, **kwargs):
        deliveries.append(kwargs)
        updated = bot.record_music_job_full_send(
            kwargs.get("job"),
            SimpleNamespace(message_id=1001, audio=SimpleNamespace(file_id="file-h8")),
            kwargs.get("audio_bytes"),
            result=kwargs.get("result"),
            updated_by=USER_ID,
        )
        return {"ok": True, "status": "SENT", "job": updated, "delivery_message_id": "1001"}

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "send_music_product_audio_result", fake_send_music)
    ctx = SimpleNamespace(bot=SimpleNamespace())
    first = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=ctx, user_id=USER_ID, source="h8"))
    second = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=ctx, user_id=USER_ID, source="h8"))
    assert first["ok"] is True
    assert second["ok"] is True
    assert len(deliveries) == 1


def test_failed_materialization_no_generic_error(monkeypatch, tmp_path):
    _patch_success_materialize(monkeypatch, tmp_path)

    async def fake_download(url, timeout_seconds=60.0):
        return b"", "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=AccessDenied", 403

    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(result_url="https://cdn/fail.mp3"), updated_by=USER_ID, source="h8"))
    assert result["job"]["progress_text"] != "Có lỗi khi xử lý lệnh."
    assert result["job"]["terminal_state"] == "failed_no_charge"


def test_admin_recover_retries_candidate_strategies_without_resubmit(monkeypatch, tmp_path):
    _patch_success_materialize(monkeypatch, tmp_path)
    submitted = []

    async def fail_submit(*args, **kwargs):
        submitted.append(True)
        raise AssertionError("must not resubmit")

    async def fake_download(url, timeout_seconds=60.0):
        return b"", "http=403; downloaded_bytes=111; content_type=application/xml; error_body_class=AccessDenied", 403

    async def fake_proxy(**kwargs):
        return AUDIO_BYTES, "http=200; bytes=8192; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "submit_music_generation_job", fail_submit)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_provider_proxy_download_audio", fake_proxy)
    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(result_url="https://cdn/recover.mp3"), updated_by=USER_ID, source="admin_recover"))
    assert result["ok"] is True
    assert submitted == []
