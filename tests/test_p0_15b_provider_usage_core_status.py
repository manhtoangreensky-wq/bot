from pathlib import Path

import bot


def _source():
    return Path(bot.__file__).read_text(encoding="utf-8")


def _patch_settings(monkeypatch):
    store = {}

    def get_setting(key, default=""):
        return store.get(key, default)

    def set_setting(key, value, note="", updated_by=""):
        store[str(key)] = str(value or "")

    monkeypatch.setattr(bot, "get_system_setting", get_setting)
    monkeypatch.setattr(bot, "set_system_setting", set_setting)
    return store


def _patch_provider_usage(monkeypatch, estimated_cost_usd=0.0):
    monkeypatch.setattr(
        bot,
        "provider_usage_summary",
        lambda *_args, **_kwargs: {
            "total_calls": 0,
            "success_count": 0,
            "fail_count": 0,
            "estimated_cost_usd": estimated_cost_usd,
            "last_event_at": "",
            "by_capability": {},
        },
    )


def _patch_core_4(monkeypatch):
    monkeypatch.setattr(
        bot,
        "get_minimax_voice_clone_readiness",
        lambda: {
            "public_enabled": False,
            "provider_permission_blocker": "clone_permission_forbidden",
            "reason": "permission/fallback not ready",
        },
    )
    monkeypatch.setattr(
        bot,
        "load_provider_attempt",
        lambda kind: {
            "voice_clone": {"status": "BLOCKED", "error": "clone_permission_forbidden"},
            "music": {"fetch_status": "PROCESSING", "download_status": "NO_AUDIO", "error": "processing/no audio download"},
        }.get(kind, {}),
    )
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {"full_result_ready": False, "public_enabled": False, "reason": "processing/no audio download"},
    )
    monkeypatch.setattr(bot, "music_ai_admin_blockers", lambda: ["processing/no audio download"])
    monkeypatch.setattr(
        bot,
        "video_multiscene_status_payload",
        lambda: {
            "admin_multiscene_smoke_ready": False,
            "exact_missing_components": ["upstream_overloaded"],
            "last_result": "upstream overloaded",
            "public_enabled": False,
        },
    )
    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        bot,
        "get_subtitle_dub_readiness",
        lambda: {"ready": False, "public_enabled": False, "reason": "not public-ready"},
    )
    monkeypatch.setattr(
        bot,
        "video_dubbing_capability",
        lambda *_args, **_kwargs: {"ok": False, "missing": ["subtitle_dub_public_guard"], "reason": "not public-ready"},
    )
    monkeypatch.setattr(bot, "provider_status_payload", lambda: {"media_factory": {"auto_publish": False}})


def test_provider_usage_command_supported():
    source = _source()
    assert 'CommandHandler("provider_usage", cmd_provider_usage)' in source
    assert "async def cmd_provider_usage" in source


def test_provider_usage_shows_shopaikey_key4u(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_provider_usage(monkeypatch, estimated_cost_usd=0.101)
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "")
    monkeypatch.setattr(
        bot,
        "shopaikey_last_usage_snapshot",
        lambda: {
            "remaining": "9.9",
            "total": "20",
            "remaining_percent": "49.5",
            "group_name": "cheap",
            "last_at": "2026-06-24 01:00:00",
        },
    )
    bot.set_key4u_manual_balance_usd(bot.key4u_parse_usage_amount("14.101"), "1")

    text = bot.admin_provider_usage_text_v2()

    assert "<b>ShopAIKey</b>" in text
    assert "<b>Key4U</b>" in text
    assert "14.101 USD" in text
    assert "/shopaikey_usage" in text
    assert "/key4u_usage_refresh" in text
    assert "/key4u_usage_set_manual &lt;amount&gt;" in text
    assert "/key4u_usage_status" in text


def test_provider_usage_no_secret(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_provider_usage(monkeypatch)
    monkeypatch.setattr(bot, "shopaikey_last_usage_snapshot", lambda: {})
    text = bot.admin_provider_usage_text_v2().lower()

    for forbidden in ("api_key", "token", "secret", "authorization", "bearer"):
        assert forbidden not in text


def test_core_4_status_command_supported():
    source = _source()
    assert 'CommandHandler("core_4_status", cmd_core_4_status)' in source
    assert 'CommandHandler("core_blockers", cmd_core_4_status)' in source


def test_core_4_status_no_provider_call(monkeypatch):
    _patch_core_4(monkeypatch)

    def fail_provider_call():
        raise AssertionError("core_4_status must not call providers")

    monkeypatch.setattr(bot, "key4u_provider_instance", fail_provider_call)

    text = bot.core_4_status_text()

    assert "P0 Core Blockers" in text
    assert "Voice clone" in text
    assert "Suno/music" in text
    assert "Video multiscene" in text
    assert "Subtitle/dub" in text
    assert "Board này chỉ đọc trạng thái local/settings; không gọi provider." in text


def test_marketing_auto_stays_admin_only_disabled(monkeypatch):
    _patch_core_4(monkeypatch)
    source = _source()
    text = bot.core_4_status_text()

    assert 'ENABLE_AUTO_PUBLISH = env_flag("ENABLE_AUTO_PUBLISH", "0")' in source
    assert 'CommandHandler("publisher_auto", admin_internal_command(cmd_publisher_auto))' in source
    assert "Marketing tự động sẽ xử lý sau khi 4 lỗi lõi ổn định." in text
    assert "no social API call" in text
    assert "no auto publish" in text
    assert "không trừ Xu" in text


def test_providers_compact_and_detail_supported():
    source = _source()
    assert 'CommandHandler("providers_compact", cmd_providers_compact)' in source
    assert 'CommandHandler("provider_detail", cmd_provider_detail)' in source
