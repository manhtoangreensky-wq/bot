import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest

import bot
from services import product_progress_status


AUDIO_BYTES = b"ID3-toan-aas-h14i-pr173-real-music" * 360
JOB_ID = "MUSH14IPR173"
USER_ID = 232914
TASK_ID = "1279444349692403713"
CLIP_ID = "clipLiveH14I173"
BARE_CDN = f"https://cdn1.suno.ai/{CLIP_ID}.mp3"
PROVIDER_ENDPOINT = "https://api.key4u.shop/suno/act/wav/{clip_id}"


def _current_branch_name() -> str:
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    except Exception:
        return ""


def _is_music_scope_branch(branch: str) -> bool:
    lowered = str(branch or "").lower()
    return any(token in lowered for token in ("p0-20", "p0-23", "music", "suno"))


def _raw_provider_result():
    return {
        "code": "SUCCESS",
        "data": {
            "data": [
                {
                    "clipId": CLIP_ID,
                    "cld2AudioUrl": BARE_CDN,
                    "progress": "100%",
                    "prompt": "TOAN AAS PR173 restore",
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
        "music_output_url": BARE_CDN,
        "output_url": BARE_CDN,
        "result_url": BARE_CDN,
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
        path = tmp_path / "h14i-vault.mp3"
        path.write_bytes(bytes(audio_bytes or b""))
        return {"vault_id": "MV-H14I", "storage_ref": str(path)}

    def fake_write(_job, payload):
        path = tmp_path / "canonical-h14i.mp3"
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
    return store


class _AudioResponse:
    status_code = 200
    content = AUDIO_BYTES
    headers = {"content-type": "audio/mpeg"}
    text = ""

    def json(self):
        raise ValueError("not json")


class _Json83Response:
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


def _song_result(vocal="female"):
    return bot.music_product_result_from_input({
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "song_vocal": vocal,
        "vocal_mode": vocal,
        "requested_vocal_mode": vocal,
        "selected_vocal_mode": vocal,
        "theme": "Bai hat thuong hieu TOAN AAS",
        "lyrics": "[Verse]\nTOAN AAS sang ngay\n[Chorus]\nCung nhau vuon xa",
        "style_prompt": "Vietnamese pop, bright chorus",
    })


def _materialize_voice(monkeypatch, tmp_path, vocal):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse(), endpoint_response=_Json83Response())
    result = asyncio.run(bot.materialize_music_artifact_for_job(
        _job(selected_vocal_mode=vocal, requested_vocal_mode=vocal, song_vocal=vocal),
        updated_by=USER_ID,
        source=f"h14i_{vocal}",
    ))
    return result, calls


def test_pr173_artifact_engine_restored_contract(monkeypatch):
    calls = []
    _patch_key4u_env(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse(), endpoint_response=_Json83Response())

    result = asyncio.run(bot.music_download_artifact_candidate(_candidate_records()[0], _job()))

    assert result["ok"] is True
    assert result["pr173_artifact_engine_restored"] is True
    assert result["direct_audio_url_get_attempted"] is True
    assert result["provider_download_endpoint_bypassed_for_raw_audio"] is True
    assert result["download_strategy_used"] == "direct_cdn"
    assert calls == [BARE_CDN]


def test_raw_audio_url_downloaded_directly_not_provider_endpoint(monkeypatch):
    calls = []
    _patch_key4u_env(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse(), endpoint_response=_Json83Response())

    result = asyncio.run(bot.music_download_artifact_candidate(_candidate_records()[0], _job()))

    assert result["ok"] is True
    assert not result["provider_download_endpoint_attempted"]
    assert not any("api.key4u.shop" in item for item in calls)


def test_provider_download_json_83_bytes_does_not_override_raw_audio(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse(), endpoint_response=_Json83Response())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14i_direct"))
    job = result["job"]

    assert result["ok"] is True
    assert calls == [BARE_CDN]
    assert job["provider_download_endpoint_attempted"] is False
    assert job["download_strategy_used"] == "direct_cdn"
    assert job["artifact_ready"] is True


def test_male_voice_uses_restored_pr173_engine_and_delivers(monkeypatch, tmp_path):
    result, calls = _materialize_voice(monkeypatch, tmp_path, "male")
    assert result["ok"] is True
    assert result["job"]["selected_vocal_mode"] == "male"
    assert result["job"]["pr173_artifact_engine_restored"] is True
    assert calls == [BARE_CDN]


def test_female_voice_uses_restored_pr173_engine_and_delivers(monkeypatch, tmp_path):
    result, calls = _materialize_voice(monkeypatch, tmp_path, "female")
    assert result["ok"] is True
    assert result["job"]["selected_vocal_mode"] == "female"
    assert result["job"]["pr173_artifact_engine_restored"] is True
    assert calls == [BARE_CDN]


def test_duet_uses_restored_pr173_engine_and_delivers(monkeypatch, tmp_path):
    result, calls = _materialize_voice(monkeypatch, tmp_path, "duet")
    assert result["ok"] is True
    assert result["job"]["selected_vocal_mode"] == "duet"
    assert result["job"]["pr173_artifact_engine_restored"] is True
    assert calls == [BARE_CDN]


def test_artifact_not_ready_does_not_terminal_fail_immediately(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_Json83Response(), endpoint_response=_WavPendingResponse())

    result = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14i_wait"))
    job = result["job"]

    assert result["status"] == "ARTIFACT_WAITING"
    assert job["terminal_state"] == ""
    assert job["primary_blocker"] == "artifact_not_ready"
    assert job["charged_xu"] == 0


def test_artifact_waiting_progress_stays_85_not_5(monkeypatch, tmp_path):
    calls = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_Json83Response(), endpoint_response=_WavPendingResponse())

    job = asyncio.run(bot.materialize_music_artifact_for_job(_job(progress_percent=5), updated_by=USER_ID, source="h14i_progress"))["job"]
    state = product_progress_status.product_progress_stage_from_job("music_song", job)

    assert job["progress_percent"] >= 85
    assert state["percent"] >= 85
    assert state["terminal_state"] == ""
    assert state["current_stage"] == "validating_audio"


def test_delivery_sends_one_audio_file(monkeypatch):
    sent = []
    store = _patch_job_store(monkeypatch, _job(output_bytes=len(AUDIO_BYTES), audio_validated=True))
    monkeypatch.setattr(bot, "save_music_guided_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "music_product_charge_after_delivery", lambda *args, **kwargs: {"ok": True, "charged_xu": 0})
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV-H14I", "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: None)

    class FakeBot:
        async def send_audio(self, **kwargs):
            sent.append(kwargs)
            return SimpleNamespace(message_id=len(sent), audio=SimpleNamespace(file_id=f"file-{len(sent)}"))

    message = SimpleNamespace(chat_id=USER_ID)
    context = SimpleNamespace(bot=FakeBot())
    result = asyncio.run(bot.deliver_music_result_once(
        message,
        context,
        user_id=USER_ID,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result={"music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC, "music_product_mode": "song"},
        audio_bytes=AUDIO_BYTES,
        job=store[JOB_ID],
        updated_by=USER_ID,
        source="h14i_delivery",
    ))

    assert result["ok"] is True
    assert len(sent) == 1
    assert result["job"]["terminal_state"] == "delivered"


def test_no_red_x_after_success():
    text = bot.product_progress_status_from_job_text("music_song", {
        "internal_job_id": "MUS-H14I-SUCCESS",
        "terminal_state": "delivered",
        "delivery_succeeded": True,
        "output_bytes": len(AUDIO_BYTES),
        "audio_validated": True,
    }, "MUS-H14I-SUCCESS", "vi")
    assert "100%" in text
    assert "❌" not in text


def test_charge_only_after_delivery_or_explicit_no_charge_reason(monkeypatch, tmp_path):
    calls = []
    charges = []
    _patch_key4u_env(monkeypatch)
    _patch_materialize_success(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch)
    _client(monkeypatch, calls, cdn_response=_AudioResponse())
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: charges.append(args) or {"ok": True, "final_cost": 300})

    job = asyncio.run(bot.materialize_music_artifact_for_job(_job(), updated_by=USER_ID, source="h14i_no_charge"))["job"]

    assert job["audio_validated"] is True
    assert job["charged_xu"] == 0
    assert job["charge_status"] == "pending_no_charge"
    assert charges == []


def test_current_compact_idea_ui_still_works():
    labels = [[button.text for button in row] for row in bot.music_product_idea_keyboard("song", "vi", bot.PRODUCT_CONTEXT_SHOWROOM).inline_keyboard]
    assert labels[0] == ["✨ Gợi ý mẫu", "✍️ Nhập lời"]


def test_no_product_video_subdub_payos_pricing_db_changes():
    if not _is_music_scope_branch(_current_branch_name()):
        pytest.skip("Music H14I scope guard is not active for this branch")
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
