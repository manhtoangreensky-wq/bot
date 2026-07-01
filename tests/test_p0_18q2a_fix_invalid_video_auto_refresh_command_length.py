import inspect
import re

import bot


COMMAND_PATTERN = re.compile(r"^[a-z0-9_]{1,32}$")


async def _dummy_handler(update, context):
    return None


def _registered_command_names():
    source = inspect.getsource(bot)
    return re.findall(r'CommandHandler\("([^"]+)"', source)


def test_video_auto_status_command_registered():
    source = inspect.getsource(bot.lifespan)
    assert 'CommandHandler("video_auto_status", cmd_video_progress_auto_refresh_status)' in source


def test_long_video_progress_auto_refresh_status_not_registered():
    source = inspect.getsource(bot.lifespan)
    assert 'CommandHandler("video_progress_auto_refresh_status"' not in source
    assert "/video_progress_auto_refresh_status" not in inspect.getsource(bot.video_ui_audit_payload)


def test_all_registered_bot_commands_are_valid_telegram_commands():
    commands = _registered_command_names()
    assert "video_auto_status" in commands
    invalid = [command for command in commands if not COMMAND_PATTERN.fullmatch(command)]
    assert invalid == []


def test_bot_startup_does_not_raise_commandhandler_valueerror():
    errors = {}
    for command in _registered_command_names():
        try:
            bot.CommandHandler(command, _dummy_handler)
        except ValueError as exc:
            errors[command] = str(exc)
    assert errors == {}


def test_video_auto_status_calls_same_debug_handler():
    source = inspect.getsource(bot.lifespan)
    assert 'CommandHandler("video_auto_status", cmd_video_progress_auto_refresh_status)' in source
    assert "async def cmd_video_progress_auto_refresh_status" in inspect.getsource(bot)


def test_video_ui_audit_mentions_video_auto_status():
    payload = bot.video_ui_audit_payload()
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["video_auto_refresh_debug_command"]["ok"] is True
    assert checks["video_auto_refresh_debug_command"]["command"] == "/video_auto_status"
