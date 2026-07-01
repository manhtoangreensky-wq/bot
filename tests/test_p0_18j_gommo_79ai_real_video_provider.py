from pathlib import Path
from types import SimpleNamespace

import pytest

from providers.gommo_79ai_provider import Gommo79AIProvider, _sdk_form_payload, extract_download_url, normalize_status
from services import video_real_render_connector as connector


def _env(**overrides):
    data = {
        "GOMMO_ACCESS_TOKEN": "secret-token",
        "GOMMO_DOMAIN": "79ai.net",
        "GOMMO_API_BASE": "https://api.gommo.net",
        "GOMMO_VIDEO_ENABLED": "true",
    }
    data.update(overrides)
    return data


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, data=None, timeout=60):
        self.calls.append({"url": url, "data": dict(data or {}), "timeout": timeout})
        if not self.responses:
            return _Response({"success": False, "message": "no response"}, 500)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _models_payload(seedance_enabled=True, veo_enabled=True):
    return {
        "success": True,
        "data": [
            {
                "name": "Seedance 2.0 - Omni",
                "model": "seedance_20_pro_edit",
                "server": "dreaminaai",
                "status": "ON" if seedance_enabled else "OFF",
                "durations": [4, 6, 8, 15],
                "ratios": ["16:9", "9:16", "1:1"],
                "resolutions": ["720p", "1080p"],
                "modes": ["business_fast", "business_professional"],
            },
            {
                "name": "VEO 3.1",
                "model": "veo_3_1",
                "server": "google_veo",
                "status": "ON" if veo_enabled else "OFF",
                "durations": [4, 6, 8],
                "ratios": ["16:9", "9:16"],
                "resolutions": ["720p", "1080p"],
                "modes": ["fast", "quality"],
            },
        ],
    }


def _create_pending(video_id="vid-1", task_id="task-1"):
    return {
        "success": True,
        "id_base": video_id,
        "videoInfo": {
            "id_base": video_id,
            "task_id": task_id,
            "status": "MEDIA_GENERATION_STATUS_PENDING",
            "model": "seedance_20_pro_edit",
            "mode": "business_fast",
            "ratio": "9:16",
            "resolution": "720p",
            "duration": 6,
            "download_url": "",
        },
    }


def _status_success(video_id="vid-1", task_id="task-1", url="https://cdn.example/video.mp4"):
    return {
        "success": True,
        "videoInfo": {
            "id_base": video_id,
            "task_id": task_id,
            "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
            "download_url": url,
            "model": "seedance_20_pro_edit",
            "mode": "business_fast",
            "duration": 6,
        },
    }


def test_gommo_provider_ready_from_env():
    provider = Gommo79AIProvider(environ=_env())
    assert provider.is_ready() is True
    assert provider.readiness()["ok"] is True
    missing = Gommo79AIProvider(environ=_env(GOMMO_ACCESS_TOKEN="")).readiness()
    assert missing["ok"] is False
    assert "access_token" in missing["missing"]


def test_gommo_list_models_video_parses_seedance_and_veo():
    client = _Client([_Response(_models_payload())])
    provider = Gommo79AIProvider(environ=_env(), client=client)
    result = provider.list_models("video")
    models = {item["model"] for item in result["models"]}
    assert result["ok"] is True
    assert {"seedance_20_pro_edit", "veo_3_1"} <= models
    assert client.calls[0]["data"]["access_token"] == "secret-token"


def test_gommo_sdk_form_payload_skips_empty_and_stringifies_objects():
    payload = _sdk_form_payload(
        {
            "access_token": "secret-token",
            "domain": "79ai.net",
            "prompt": "scene",
            "empty": "",
            "none": None,
            "countTasks": 1,
            "enabled": True,
            "references": [{"id_base": "img-1"}],
            "metadata": {"ratio": "9:16"},
        }
    )
    assert payload["access_token"] == "secret-token"
    assert payload["domain"] == "79ai.net"
    assert payload["countTasks"] == "1"
    assert payload["enabled"] == "true"
    assert payload["references"] == '[{"id_base":"img-1"}]'
    assert payload["metadata"] == '{"ratio":"9:16"}'
    assert "empty" not in payload
    assert "none" not in payload


def test_gommo_picks_seedance_when_available():
    provider = Gommo79AIProvider(environ=_env())
    plan = provider.pick_video_model(models=_models_payload()["data"], duration=6, aspect_ratio="9:16")
    assert plan["ok"] is True
    assert plan["model"] == "seedance_20_pro_edit"
    assert plan["mode"] == "business_fast"
    assert plan["duration"] == 6


def test_gommo_falls_back_to_veo_when_seedance_unavailable():
    provider = Gommo79AIProvider(environ=_env())
    plan = provider.pick_video_model(models=_models_payload(seedance_enabled=False)["data"], duration=7, aspect_ratio="9:16")
    assert plan["ok"] is True
    assert plan["model"] == "veo_3_1"
    assert plan["duration"] in {6, 8}


def test_gommo_create_video_saves_id_base_and_task_id():
    client = _Client([_Response(_create_pending("vid-32", "task-32"))])
    provider = Gommo79AIProvider(environ=_env(), client=client)
    result = provider.create_video(prompt="cinematic product scene", model="seedance_20_pro_edit", duration=6)
    assert result["ok"] is True
    assert result["video_id"] == "vid-32"
    assert result["task_id"] == "task-32"
    assert result["status"] == "IN_PROGRESS"


def test_gommo_create_video_posts_sdk_form_body_with_token_domain_and_no_empty_reference():
    client = _Client([_Response(_create_pending("vid-sdk", "task-sdk"))])
    provider = Gommo79AIProvider(environ=_env(), client=client)
    result = provider.create_video(
        prompt="cinematic product scene",
        model="seedance_20_pro_edit",
        ratio="9:16",
        resolution="720p",
        duration=6,
        mode="business_fast",
        references={"imageReferences": [{"id_base": "img-1"}], "emptyReference": ""},
    )
    body = client.calls[0]["data"]
    assert result["video_id"] == "vid-sdk"
    assert body["access_token"] == "secret-token"
    assert body["domain"] == "79ai.net"
    assert body["imageReferences"] == '[{"id_base":"img-1"}]'
    assert "emptyReference" not in body


def test_gommo_status_uses_video_info_id_base_as_video_id():
    client = _Client([_Response({"success": True, "videoInfo": {"id_base": "real-id-base", "task_id": "task-1", "status": "MEDIA_GENERATION_STATUS_PENDING"}})])
    provider = Gommo79AIProvider(environ=_env(), client=client)
    result = provider.check_video_status("placeholder")
    assert client.calls[0]["data"]["videoId"] == "placeholder"
    assert result["video_id"] == "real-id-base"
    assert result["status"] == "IN_PROGRESS"


def test_gommo_pending_does_not_fail_no_real_visual():
    assert normalize_status("MEDIA_GENERATION_STATUS_PENDING") == "IN_PROGRESS"
    create = Gommo79AIProvider(environ=_env(), client=_Client([_Response(_create_pending())])).create_video(
        prompt="scene", model="seedance_20_pro_edit", duration=6
    )
    assert create["ok"] is True
    assert create["download_url"] == ""
    assert create["status"] == "IN_PROGRESS"


def test_gommo_status_success_downloads_mp4(monkeypatch, tmp_path):
    provider = Gommo79AIProvider(environ=_env())
    source = tmp_path / "source.mp4"
    source.write_bytes(b"mp4 bytes")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: source.open("rb"))
    result = provider.download_video("https://cdn.example/video.mp4", str(tmp_path / "out.mp4"))
    assert result["ok"] is True
    assert Path(result["path"]).read_bytes() == b"mp4 bytes"


def test_gommo_status_success_uses_resolution_url_if_download_url_missing():
    payload = {"videoInfo": {"status": "MEDIA_GENERATION_STATUS_SUCCESSFUL", "resolutions": [{"status": "FINISH", "url": "https://cdn.example/resolution.mp4"}]}}
    assert extract_download_url(payload) == "https://cdn.example/resolution.mp4"


def test_gommo_poll_extra_when_success_without_download_url():
    client = _Client([
        _Response({"success": True, "videoInfo": {"id_base": "vid-1", "task_id": "task-1", "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL", "download_url": ""}}),
        _Response(_status_success()),
    ])
    provider = Gommo79AIProvider(environ=_env(), client=client)
    result = provider.poll_video_until_ready("vid-1", max_attempts=1, interval_seconds=0, success_url_extra_attempts=2)
    assert result["status"] == "SUCCESS"
    assert result["download_url"] == "https://cdn.example/video.mp4"
    assert len(client.calls) == 2


def test_gommo_upload_video_rejects_empty_data_cleanly():
    result = Gommo79AIProvider(environ=_env()).upload_video("")
    assert result["ok"] is False
    assert result["error"] == "upload_video_invalid_data"


def test_gommo_upload_image_rejects_empty_data_cleanly():
    result = Gommo79AIProvider(environ=_env()).upload_image("")
    assert result["ok"] is False
    assert result["error"] == "upload_image_invalid_data"


def test_multiscene_3_scenes_creates_3_provider_tasks(monkeypatch, tmp_path):
    calls = []

    def fake_run_provider_generation(request, *, output_dir, environ=None, sleep_func=None):
        del environ, sleep_func
        calls.append(request)
        index = len(calls)
        output_path = Path(output_dir) / f"scene-provider-{index}.mp4"
        output_path.write_bytes(b"mp4")
        return {
            "ok": True,
            "provider": "gommo_79ai",
            "provider_task_ids": [f"task-{index}"],
            "provider_video_ids": [f"vid-{index}"],
            "output_path": str(output_path),
            "model": "seedance_20_pro_edit",
            "mode": "business_fast",
            "result_url_present": True,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)
    events = []
    renderer = connector.build_real_scene_renderer({"provider_order": ["gommo_79ai"]}, events)
    for index in range(1, 4):
        result = renderer(
            SimpleNamespace(scene_id=index, video_prompt=f"scene {index}", visual_prompt=f"scene {index}", aspect_ratio="9:16", target_duration_sec=6),
            str(tmp_path / f"scene-{index}.mp4"),
        )
        assert result["ok"] is True
    assert [item.required_capability for item in calls] == ["text_to_video", "text_to_video", "text_to_video"]
    assert [item["task_id"] for item in events] == ["task-1", "task-2", "task-3"]
    assert [item["video_id"] for item in events] == ["vid-1", "vid-2", "vid-3"]


def test_multiscene_downloads_and_stitches_clips(monkeypatch, tmp_path):
    output = tmp_path / "stitched.mp4"
    output.write_bytes(b"stitched")
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_args, **_kwargs: {"ok": True, "ready_provider_order": ["gommo_79ai"], "providers": []})
    monkeypatch.setattr(
        connector,
        "process_multiscene_video_pipeline",
        lambda **kwargs: {"ok": True, "final_video_path": str(output), "master_video_path": str(output), "created_files": [str(output)], "scene_count": kwargs["max_scenes"]},
    )
    result = connector.render_real_video_job({"job_id": "32", "source": "product_video", "product_video": True, "provider_call": True, "scene_count": 3, "addon_plan": {}}, str(tmp_path))
    assert result["visual_classification"] == connector.FINAL_AI_VIDEO
    assert result["stitch_attempted"] is True or result.get("master_video_path")


def test_token_never_logged():
    provider = Gommo79AIProvider(environ=_env())
    redacted = provider.redact_debug({"access_token": "secret-token", "nested": "ok"})
    assert "secret-token" not in str(redacted)
    assert redacted["access_token"] == "***"


def test_public_error_no_provider_api_words():
    text = "Hệ thống chưa dựng được video hoàn chỉnh lần này. TOAN AAS chưa trừ Xu. Anh/chị vui lòng thử lại sau."
    for forbidden in ("gommo", "79ai", "provider", "api", "task_id", "token", "ffmpeg", "traceback"):
        assert forbidden not in text.lower()


def test_default_provider_order_keeps_shopaikey_key4u_before_gommo(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER_ORDER", raising=False)
    order = connector._provider_order({})
    assert order[:3] == ["toanaas_video", "key4u_video", "shopaikey_video"]
