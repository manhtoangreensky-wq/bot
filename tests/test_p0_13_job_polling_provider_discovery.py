import asyncio
import inspect
from pathlib import Path

import pytest

import bot


def test_async_job_requires_provider_task_id_or_output():
    with pytest.raises(ValueError):
        bot.normalize_engine_async_job({
            "feature": "music_suno",
            "user_id": "1",
            "provider": "key4u_suno",
            "status": "processing",
        })


def test_async_job_allows_real_output_without_provider_task_id():
    job = bot.normalize_engine_async_job({
        "feature": "subtitle_dub",
        "user_id": "1",
        "provider": "subtitle_pipeline",
        "status": "completed",
        "output_bytes": 123,
    })
    assert job["internal_job_id"].startswith("DUB-")
    assert job["output_bytes"] == 123


def test_public_never_sees_provider_task_id():
    raw_task = "provider-task-secret-123456"
    text = bot.engine_async_status_text({
        "internal_job_id": "MUS-ABCD1234",
        "feature": "music_suno",
        "provider": "key4u_suno",
        "provider_task_id": raw_task,
        "status": "processing",
        "last_provider_status": f"processing {raw_task}",
        "poll_count": 2,
    }, admin=False)
    assert raw_task not in text
    assert "Provider task" not in text


def test_admin_status_shows_sanitized_provider_status():
    raw_task = "provider-task-secret-123456"
    text = bot.engine_async_status_text({
        "internal_job_id": "MUS-ABCD1234",
        "feature": "music_suno",
        "provider": "key4u_suno",
        "provider_task_id": raw_task,
        "status": "processing",
        "last_provider_status": f"processing {raw_task} https://example.test/file.mp3 token=abc123",
        "poll_count": 2,
    }, admin=True)
    assert raw_task not in text
    assert bot.mask_provider_task_id(raw_task) in text
    assert "token=abc123" not in text
    assert "https://example.test" not in text


def test_no_fake_processing_without_provider_task_id():
    source = inspect.getsource(bot.save_engine_async_job)
    assert "engine async job requires provider_task_id or output_bytes" in inspect.getsource(bot.normalize_engine_async_job)
    assert "normalize_engine_async_job(job)" in source


def test_music_accept_sends_check_status_button():
    keyboard = bot.engine_async_status_keyboard("MUS-ABCD1234", "music")
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any("Kiểm tra trạng thái" in button.text for button in buttons)
    assert any(button.callback_data == "enginejob|music|MUS-ABCD1234" for button in buttons)
    source = inspect.getsource(bot.cmd_music_suno_admin_test)
    assert "create_music_suno_async_job" in source
    assert "engine_async_waiting_text" in source


def test_key4u_suno_result_url_missing():
    assert bot.music_poll_status_is_success_without_url("SUCCESS")
    assert bot.music_poll_status_is_success_without_url("COMPLETED_NO_AUDIO")


def test_music_suno_no_fake_completed_without_audio(monkeypatch):
    job = {
        "internal_job_id": "MUS-UNIT0001",
        "feature": "music_suno",
        "user_id": "1",
        "provider": "key4u_suno",
        "provider_task_id": "task-real-123",
        "status": "submitted",
        "output_bytes": 0,
        "poll_count": 0,
    }
    saved = {}

    async def fake_poll(_state, updated_by=""):
        return {"ok": False, "status": "SUCCESS", "output_url": "", "detail": ""}

    def fake_get(_job_id):
        return dict(saved or job)

    def fake_save(payload):
        saved.clear()
        saved.update(payload)
        return payload

    monkeypatch.setattr(bot, "get_engine_async_job", fake_get)
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)

    result = asyncio.run(bot.poll_music_suno_async_job("MUS-UNIT0001", download=True))
    assert not result["ok"]
    assert saved["status"] == "failed"
    assert saved["error_category"] == "result_url_missing"
    assert saved["output_bytes"] == 0


def test_video_status_variants_no_v1_v1(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_BASE_URL", "https://api.shopaikey.com/v1")
    urls = bot.shopaikey_video_status_variant_urls("task-123")
    assert urls
    assert all("/v1/v1/" not in url for _name, url in urls)
    assert any("/video/generations/task-123" in url for _name, url in urls)


def test_video_status_variant_requires_existing_task():
    assert bot.shopaikey_video_status_variant_urls("") == []
    assert bot.shopaikey_video_status_variant_urls("bad task with spaces") == []


def test_multiscene_progress_lists_scene_states():
    text = bot.multiscene_job_status_text({
        "parent_task_id": "msv-1-unit",
        "status": "IN_PROGRESS",
        "scene_jobs": [
            {"scene_index": 1, "status": "SUBMITTED", "provider": "shopaikey", "provider_task_id": "scene-task-1", "poll_count": 1},
            {"scene_index": 2, "status": "COMPLETED", "provider": "key4u", "provider_task_id": "scene-task-2", "poll_count": 2, "output_url": "https://cdn.test/2.mp4"},
        ],
    })
    assert "Scene 1" in text
    assert "Scene 2" in text
    assert "scene-task-1" not in text
    assert bot.mask_provider_task_id("scene-task-1") in text


def test_multiscene_status_button_available():
    keyboard = bot.engine_async_status_keyboard("msv-1-unit", "multiscene")
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.callback_data == "enginejob|multiscene|msv-1-unit" for button in buttons)
    source = inspect.getsource(bot.cmd_tool_test_video_multiscene)
    assert '"basic": 300' in source
    assert "engine_async_status_keyboard" in source


def test_subtitle_admin_status_shows_srt_blocks():
    text = bot.subtitle_dub_job_status_text({
        "internal_job_id": "DUB-ABCD1234",
        "feature": "subtitle_dub",
        "provider": "Deepgram,MiniMax",
        "status": "completed",
        "output_bytes": 456,
        "srt_blocks": 3,
        "audio_bytes": 400,
        "video_bytes": 0,
        "mux_status": "disabled",
    })
    assert "SRT blocks" in text
    assert "<code>3</code>" in text
    assert "Audio bytes" in text
    assert "disabled" in text


def test_public_guard_copy_exact():
    expected = "Dịch vụ đang được kiểm tra. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."
    assert bot.music_ai_public_guard_text("vi") == expected
    assert bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT == expected


def test_p0_13_commands_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    required = [
        'CommandHandler("music_suno_jobs", cmd_music_suno_jobs)',
        'CommandHandler("music_suno_poll", cmd_music_suno_poll)',
        'CommandHandler("key4u_suno_route_status", cmd_key4u_suno_route_status)',
        'CommandHandler("video_jobs", cmd_video_jobs)',
        'CommandHandler("video_multiscene_job", cmd_video_multiscene_job)',
        'CommandHandler("video_multiscene_poll", cmd_video_multiscene_poll)',
        'CommandHandler("shopaikey_video_route_status", cmd_shopaikey_video_route_status)',
        'CommandHandler("shopaikey_video_job_status", cmd_shopaikey_video_status_job)',
        'CommandHandler("key4u_video_route_status", cmd_key4u_video_route_status)',
        'CommandHandler("key4u_video_job_status", cmd_key4u_video_status_job)',
        'CommandHandler("subtitle_jobs", cmd_subtitle_jobs)',
        'CommandHandler("dub_job", cmd_dub_job)',
        'CallbackQueryHandler(handle_engine_async_job_callback, pattern=r"^enginejob\\|")',
    ]
    for needle in required:
        assert needle in source
