import asyncio
from pathlib import Path

import bot
import provider_router
import providers.key4u_provider as key4u_provider_module
from providers.key4u_provider import (
    Key4UConfig,
    Key4UProvider,
    is_placeholder_task_id,
    join_provider_url,
    mask_key,
    safe_join_url,
    should_try_model_fallback,
)


def repo_file(name: str) -> str:
    return Path(name).read_text(encoding="utf-8")


def source_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_key4u_status_masks_api_key():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            admin_smoke_enabled=True,
            api_key="sk-key4u-secret-123456789",
            usage_endpoint="/usage",
            balance_endpoint="/balance",
        )
    )
    status = provider.get_status()
    assert status["configured"] is True
    assert status["api_key"] == "sk-k***6789"
    assert status["usage_endpoint"] == "configured"
    assert status["balance_endpoint"] == "configured"
    assert "sk-key4u-secret-123456789" not in str(status)
    assert mask_key("") == "missing"


def test_key4u_url_join_keeps_v1_clean():
    assert safe_join_url("https://api.key4u.shop/v1", "/v1/chat/completions") == "https://api.key4u.shop/v1/chat/completions"
    assert safe_join_url("https://api.key4u.shop", "/v1/video/create") == "https://api.key4u.shop/v1/video/create"


def test_key4u_provider_url_join_avoids_scoped_duplicates():
    assert join_provider_url("https://api.key4u.shop/minimax", "/v1/t2a_v2") == "https://api.key4u.shop/minimax/v1/t2a_v2"
    assert join_provider_url("https://api.key4u.shop/minimax/v1", "/minimax/v1/t2a_v2") == "https://api.key4u.shop/minimax/v1/t2a_v2"
    assert join_provider_url("https://api.key4u.shop/suno", "/suno/submit/music") == "https://api.key4u.shop/suno/submit/music"
    assert join_provider_url("https://api.key4u.shop/suno/", "suno/fetch/task-1") == "https://api.key4u.shop/suno/fetch/task-1"


def test_key4u_provider_status_includes_final_audio_urls():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            admin_smoke_enabled=True,
            api_key="sk-test",
            minimax_base_url="https://api.key4u.shop/minimax",
            tts_endpoint="/v1/t2a_v2",
            minimax_upload_endpoint="/v1/files",
            minimax_clone_endpoint="/v1/voice_clone",
            suno_base_url="https://api.key4u.shop/suno",
            suno_create_endpoint="/submit/music",
            suno_query_endpoint="/fetch/{taskId}",
            suno_lyrics_endpoint="/submit/lyrics",
        )
    )
    status = provider.get_status()
    assert status["minimax_tts_final_url"] == "https://api.key4u.shop/minimax/v1/t2a_v2"
    assert status["minimax_clone_upload_final_url"] == "https://api.key4u.shop/minimax/v1/files"
    assert status["minimax_clone_final_url"] == "https://api.key4u.shop/minimax/v1/voice_clone"
    assert status["suno_submit_final_url"] == "https://api.key4u.shop/suno/submit/music"
    assert status["suno_fetch_final_url"] == "https://api.key4u.shop/suno/fetch/{taskId}"
    assert status["suno_lyrics_final_url"] == "https://api.key4u.shop/suno/submit/lyrics"


def test_key4u_voice_clone_id_uses_hyphen_not_underscore():
    source = Path(key4u_provider_module.__file__).read_text(encoding="utf-8")
    clone_block = source_between(source, "async def clone_voice(", "async def stt(")
    assert 'r"[^A-Za-z0-9-]+"' in clone_block
    assert 'replace("_"' not in clone_block


def test_key4u_default_models_are_not_empty():
    provider = Key4UProvider(Key4UConfig(enabled=True, admin_smoke_enabled=True, api_key="sk-test"))
    status = provider.get_status()
    assert status["chat_model"] == "qwen-plus"
    assert status["vision_model"] == "gemini-2.5-flash"
    assert bot.KEY4U_CHAT_MODEL == "qwen-plus"
    assert bot.KEY4U_VISION_MODEL == "gemini-2.5-flash"


def test_key4u_missing_config_no_network_no_crash():
    provider = Key4UProvider(Key4UConfig(enabled=False, api_key=""))
    result = asyncio.run(provider.chat_completion(model="dummy-model"))
    assert result["ok"] is False
    assert result["status"] == "NOT_CONFIGURED"
    assert result["provider"] == "key4u"


def test_key4u_usage_and_optional_capabilities_need_docs_without_endpoint():
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            admin_smoke_enabled=True,
            api_key="sk-test",
            tts_model="tts-model",
            stt_model="stt-model",
            suno_model="suno-model",
            rerank_model="rerank-model",
        )
    )
    usage = asyncio.run(provider.get_usage())
    balance = asyncio.run(provider.get_balance())
    tts = asyncio.run(provider.tts())
    stt = asyncio.run(provider.stt(audio_bytes=b"abc"))
    suno = asyncio.run(provider.suno_create())
    rerank = asyncio.run(provider.rerank("query", ["candidate"]))
    for result in (usage, balance):
        assert result["ok"] is False
        assert result["status"] == "NEED_ENDPOINT"
        assert result["provider"] == "key4u"
    for result in (tts, stt, suno, rerank):
        assert result["ok"] is False
        assert result["status"] == "NEED_DOCS"
        assert result["provider"] == "key4u"


def test_key4u_admin_smoke_commands_do_not_deduct_xu():
    source = repo_file("bot.py")
    command_blocks = [
        source_between(source, "async def cmd_tool_test_key4u_chat", "async def cmd_tool_test_key4u_vision"),
        source_between(source, "async def cmd_tool_test_key4u_vision", "async def cmd_tool_test_key4u_image"),
        source_between(source, "async def cmd_tool_test_key4u_image", "async def cmd_tool_test_key4u_image_edit"),
        source_between(source, "async def cmd_tool_test_key4u_image_edit", "async def cmd_tool_test_key4u_video"),
        source_between(source, "async def cmd_tool_test_key4u_video", "async def cmd_key4u_video_job"),
        source_between(source, "async def cmd_key4u_video_job", "async def cmd_tool_test_openrouter"),
    ]
    forbidden = [
        "spend_fixed_credit_info(",
        "deduct_dynamic_credit(",
        "add_credit(",
        "update_user_credits(",
    ]
    for block in command_blocks:
        assert "is_admin_user" in block
        assert "save_tool_test_result" in block
        assert "record_key4u_smoke_usage" in block
        for token in forbidden:
            assert token not in block


def test_key4u_admin_smoke_commands_have_model_fallbacks():
    source = repo_file("bot.py")
    chat_block = source_between(source, "async def cmd_tool_test_key4u_chat", "async def cmd_tool_test_key4u_vision")
    vision_block = source_between(source, "async def cmd_tool_test_key4u_vision", "async def cmd_tool_test_key4u_image")
    video_block = source_between(source, "async def cmd_tool_test_key4u_video", "async def cmd_key4u_video_job")
    assert "KEY4U_CHAT_MODEL_FALLBACKS" in chat_block
    assert "KEY4U_VISION_MODEL_FALLBACKS" in vision_block
    assert "KEY4U_VIDEO_FALLBACK_MODELS" in video_block
    assert "max_fallbacks=2" in chat_block
    assert "max_fallbacks=2" in vision_block
    assert "max_fallbacks=1" in video_block
    result_lines_block = source_between(source, "def key4u_result_lines", "def key4u_manual_balance_usd")
    assert "models_tried" in result_lines_block
    assert "KEY4U_VIDEO_NO_TASK_NOTE" in result_lines_block


def test_key4u_video_query_uses_get_with_id_and_rejects_placeholders():
    source = repo_file("providers/key4u_provider.py")
    poll_block = source_between(source, "async def poll_video_task", "async def tts")
    assert "is_placeholder_task_id(safe_task_id)" in poll_block
    assert 'params={"id": safe_task_id}' in poll_block
    assert "client.get(endpoint" in poll_block
    assert "client.post(endpoint" not in poll_block
    assert is_placeholder_task_id("<task_id>") is True
    assert is_placeholder_task_id("<task_id_thật>") is True
    assert is_placeholder_task_id("TASK_ID") is True
    assert is_placeholder_task_id("your_task_id") is True
    assert is_placeholder_task_id("abc") is True
    assert is_placeholder_task_id("abc123") is True
    assert is_placeholder_task_id("*") is True
    assert is_placeholder_task_id("abc12345") is False
    provider = Key4UProvider(Key4UConfig(enabled=True, admin_smoke_enabled=True, api_key="sk-test"))
    result = asyncio.run(provider.poll_video_task("<task_id>"))
    assert result["ok"] is False
    assert result["status"] == "NEED_TASK_ID"
    assert result["http_status"] == 0
    assert "task_id thật" in result["error_message_safe"]
    bot_block = source_between(source_between(repo_file("bot.py"), "async def cmd_key4u_video_job", "async def cmd_tool_test_key4u_tts"), "async def cmd_key4u_video_job", "result = await provider.poll_video_task")
    assert "is_placeholder_task_id(task_id)" in bot_block
    assert bot_block.index("is_placeholder_task_id(task_id)") < bot_block.index("key4u_provider_instance()")


def test_key4u_video_group_unavailable_can_fallback():
    result = {
        "status": "FAIL",
        "error_class": "FAIL_PROVIDER_GROUP_UNAVAILABLE",
        "error_message_safe": "No available channel for model veo3.1-fast under group cheap",
    }
    assert should_try_model_fallback(result) is True


def test_key4u_video_submit_payload_and_timeout_are_safe():
    source = repo_file("providers/key4u_provider.py")
    video_block = source_between(source, "async def video_generation", "async def poll_video_task")
    assert "timeout_seconds: float = 60.0" in video_block
    assert 'aspect_ratio: str = "16:9"' in video_block
    assert '"aspect_ratio": str(aspect_ratio or "16:9")[:20]' in video_block
    assert '"enhance_prompt": True' in video_block
    assert '"enable_upsample": False' in video_block
    assert '_timeout_result("video_generate"' in video_block


def test_key4u_commands_registered_and_documented():
    source = repo_file("bot.py")
    registry = repo_file("docs/COMMAND_REGISTRY.md")
    commands = [
        "key4u_status",
        "key4u_usage",
        "key4u_set_manual_balance",
        "tool_test_key4u_chat",
        "tool_test_key4u_vision",
        "tool_test_key4u_image",
        "tool_test_key4u_image_edit",
        "tool_test_key4u_video",
        "tool_test_key4u_video_model",
        "tool_test_key4u_video_all",
        "key4u_video_job",
        "tool_test_key4u_tts",
        "tool_test_key4u_stt",
        "tool_test_key4u_suno",
        "key4u_suno_job",
        "tool_test_key4u_rerank",
    ]
    for command in commands:
        assert f'CommandHandler("{command}"' in source
        assert f"/{command}" in registry


def test_provider_registry_includes_key4u_and_woku_parked(monkeypatch):
    monkeypatch.setattr(bot, "KEY4U_ENABLED", True)
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "sk-test-key4u")
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "KEY4U_ADMIN_SMOKE_ENABLED", True)
    monkeypatch.setattr(bot, "WOKU_REASON", "cost_high_parked")
    registry = bot.provider_registry()
    assert registry["key4u"]["configured"] is True
    assert registry["key4u"]["stage"] in {"admin_only", "ready_for_smoke_test", "live_pass"}
    assert registry["wokushop"]["configured"] is False
    assert registry["wokushop"]["health"]["status"] == "PARKED"
    matrix_text = "\n".join(bot.provider_matrix_lines())
    assert "Key4U" in matrix_text
    assert "parallel provider hub" in matrix_text
    assert "WokuShop" in matrix_text
    assert "cost_high" in matrix_text


def test_provider_router_excludes_woku_from_fallback_order(monkeypatch):
    monkeypatch.setenv("PROVIDER_FALLBACK_ORDER", "wokushop,key4u,shopaikey,woku")
    assert provider_router.provider_fallback_order() == ["key4u", "shopaikey"]
    payload = provider_router.provider_matrix_payload()
    assert payload["providers"]["wokushop"]["stage"] == "disabled"
    assert payload["providers"]["wokushop"]["reason"] == "cost_high_parked"


def test_env_example_key4u_public_off_and_woku_parked():
    env_text = repo_file(".env.example")
    assert "KEY4U_ENABLED=false" in env_text
    assert "KEY4U_SMART_ROUTING=true" in env_text
    assert "KEY4U_USAGE_ENDPOINT=" in env_text
    assert "KEY4U_BALANCE_ENDPOINT=" in env_text
    assert "KEY4U_DASHBOARD_BALANCE_USD=" in env_text
    assert "KEY4U_DEFAULT_CHAT_MODEL=qwen-plus" in env_text
    assert "KEY4U_CHAT_MODEL_FALLBACKS=qwen-plus,qwen-turbo,deepseek-chat,gemini-2.5-flash" in env_text
    assert "KEY4U_DEFAULT_VISION_MODEL=gemini-2.5-flash" in env_text
    assert "KEY4U_VISION_MODEL_FALLBACKS=gemini-2.5-flash,gemini-2.5-flash-all,gpt-4o-mini,qwen-vl-max" in env_text
    assert "KEY4U_VIDEO_FALLBACK_MODELS=veo3.1-fast,pixverse-video,viduq3,kling-video,minimax-video,doubao-seedance" in env_text
    assert "KEY4U_PUBLIC_ENABLED=false" in env_text
    assert "KEY4U_ADMIN_SMOKE_ENABLED=true" in env_text
    assert "PROVIDER_PRIMARY=shopaikey" in env_text
    assert "PROVIDER_PARALLEL_ENABLED=true" in env_text
    assert "PROVIDER_FALLBACK_ENABLED=false" in env_text
    assert "PROVIDER_FALLBACK_ORDER=shopaikey,key4u" in env_text
    assert "WOKU_ENABLED=false" in env_text
    assert "WOKU_REASON=cost_high_parked" in env_text


def test_video_200_beta_daily_limit_unchanged():
    assert bot.VIDEO_LOW_COST_XU == 200
    assert bot.VIDEO_BASIC_COST_XU == 300
    assert bot.VIDEO_COMMON_COST_XU == 400
    assert bot.VIDEO_BETA_200_MAX_USER_DAY == 3


def test_key4u_usage_schema_and_status_no_secret_leak():
    source = repo_file("bot.py")
    assert "CREATE TABLE IF NOT EXISTS provider_usage_events" in source
    assert "KEY4U_DASHBOARD_BALANCE_USD" in source
    usage_impl = source_between(source, "async def cmd_key4u_usage", "async def cmd_key4u_set_manual_balance")
    assert "key4u_usage_lines" in usage_impl
    assert "KEY4U_API_KEY" not in usage_impl
    assert "No API key, prompt, or raw provider response is shown." in source
