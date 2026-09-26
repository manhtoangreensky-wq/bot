"""Runtime registration contract for the Admin Marketing callback."""

import asyncio
from types import SimpleNamespace

import bot
from telegram import CallbackQuery, Update, User


class _StopBeforeTelegramNetwork(RuntimeError):
    pass


class _FakeTelegramApplication:
    def __init__(self):
        self.handlers = []
        self.error_handlers = []

    def add_handler(self, handler, group=0):
        self.handlers.append((group, handler))

    def add_error_handler(self, handler):
        self.error_handlers.append(handler)

    async def initialize(self):
        raise _StopBeforeTelegramNetwork()


def _registration_handlers():
    fake_app = _FakeTelegramApplication()
    originals = {}

    for name in (
        "tg_app",
        "tg_polling_task",
        "tg_webhook_watchdog_task",
        "tg_auto_backup_task",
        "tg_memory_reminder_task",
        "tg_shopaikey_usage_task",
        "tg_payos_expiry_task",
        "tg_broadcast_lite_worker_task",
        "tg_product_video_watchdog_task",
        "tg_frame_video_watchdog_task",
        "tg_video_trend_catalog_task",
        "ACTIVE_TELEGRAM_UPDATE_MODE",
        "ACTIVE_TELEGRAM_WEBHOOK_URL",
        "TELEGRAM_STARTUP_ERROR",
        "TELEGRAM_HANDLERS_REGISTERED",
        "PRODUCT_VIDEO_CONFIRM_HANDLER_DIAGNOSTICS",
    ):
        originals[name] = getattr(bot, name)

    def replace(name, value):
        originals[name] = getattr(bot, name)
        setattr(bot, name, value)

    replace("init_db", lambda: None)
    replace("run_storage_cleanup_auto_once", lambda: None)
    replace("telegram_token_runtime_summary", lambda: {"configured": True, "len": 0, "masked": ""})
    replace("runtime_db_status", lambda: {"status": "PASS"})
    replace("data_persistence_status_payload", lambda **_kwargs: {"mode": "test", "db_path": "", "db_exists": True, "data_loss_risk": False, "backup_last_status": ""})
    replace("subdub_runtime_status_payload", lambda: {"ffmpeg_version_probe_ok": True, "ffprobe_version_probe_ok": True, "ass_filter_ready": True, "unicode_font_ready": True, "media_preprocessing_ready": True})
    replace("build_telegram_application", lambda: fake_app)
    replace("audit_product_video_confirm_handler_registration", lambda _app: {})
    replace("telegram_handler_count", lambda _app: len(fake_app.handlers))
    originals["TELEGRAM_TOKEN"] = bot.TELEGRAM_TOKEN
    originals["SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED"] = bot.SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED
    bot.TELEGRAM_TOKEN = "123456:registration-contract-only"
    bot.SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED = False

    async def run():
        async with bot.lifespan(SimpleNamespace()):
            return list(fake_app.handlers)

    try:
        return asyncio.run(run())
    finally:
        for name, value in originals.items():
            setattr(bot, name, value)


def test_admin_growth_callback_is_registered_by_lifespan():
    handlers = _registration_handlers()
    routed = [
        handler
        for _group, handler in handlers
        if getattr(handler, "callback", None) is bot.handle_admin_growth_callback
    ]

    assert len(routed) == 1
    update = Update(
        update_id=1,
        callback_query=CallbackQuery(
            id="registration-contract",
            from_user=User(id=1, is_bot=False, first_name="test"),
            chat_instance="registration-contract",
            data="admin_growth|main",
        ),
    )
    assert routed[0].check_update(update)
