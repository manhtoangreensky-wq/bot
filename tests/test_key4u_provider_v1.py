import asyncio
from pathlib import Path

import bot
import provider_router
from providers.key4u_provider import Key4UConfig, Key4UProvider, mask_key, safe_join_url


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
        )
    )
    status = provider.get_status()
    assert status["configured"] is True
    assert status["api_key"] == "sk-k***6789"
    assert "sk-key4u-secret-123456789" not in str(status)
    assert mask_key("") == "missing"


def test_key4u_url_join_keeps_v1_clean():
    assert safe_join_url("https://api.key4u.shop/v1", "/v1/chat/completions") == "https://api.key4u.shop/v1/chat/completions"
    assert safe_join_url("https://api.key4u.shop", "/v1/video/create") == "https://api.key4u.shop/v1/video/create"


def test_key4u_missing_config_no_network_no_crash():
    provider = Key4UProvider(Key4UConfig(enabled=False, api_key=""))
    result = asyncio.run(provider.chat_completion(model="dummy-model"))
    assert result["ok"] is False
    assert result["status"] == "NOT_CONFIGURED"
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
        for token in forbidden:
            assert token not in block


def test_key4u_commands_registered_and_documented():
    source = repo_file("bot.py")
    registry = repo_file("docs/COMMAND_REGISTRY.md")
    commands = [
        "key4u_status",
        "tool_test_key4u_chat",
        "tool_test_key4u_vision",
        "tool_test_key4u_image",
        "tool_test_key4u_image_edit",
        "tool_test_key4u_video",
        "key4u_video_job",
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
    assert "KEY4U_PUBLIC_ENABLED=false" in env_text
    assert "KEY4U_ADMIN_SMOKE_ENABLED=true" in env_text
    assert "PROVIDER_FALLBACK_ENABLED=false" in env_text
    assert "PROVIDER_FALLBACK_ORDER=shopaikey,key4u" in env_text
    assert "WOKU_ENABLED=false" in env_text
    assert "WOKU_REASON=cost_high_parked" in env_text


def test_video_200_beta_daily_limit_unchanged():
    assert bot.VIDEO_LOW_COST_XU == 200
    assert bot.VIDEO_BASIC_COST_XU == 300
    assert bot.VIDEO_COMMON_COST_XU == 400
    assert bot.VIDEO_BETA_200_MAX_USER_DAY == 3
