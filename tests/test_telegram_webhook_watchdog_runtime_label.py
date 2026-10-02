import asyncio
import html
import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
EXPECTED_WEBHOOK = "https://tg.toanaas.vn/telegram/webhook"


def _load_watchdog(bot, sleep):
    match = re.search(
        r"(?ms)^async def telegram_webhook_watchdog\(\):.*?(?=^(?:async\s+)?def\s|^class\s|^#\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "Telegram webhook watchdog is missing"

    namespace = {
        "asyncio": SimpleNamespace(sleep=sleep, CancelledError=asyncio.CancelledError),
        "html": html,
        "logger": SimpleNamespace(warning=lambda *args: None),
        "tg_app": SimpleNamespace(bot=bot),
        "PUBLIC_BASE_URL": "https://tg.toanaas.vn",
        "TELEGRAM_TAKEOVER_INTERVAL_SECONDS": 1,
        "ADMIN_ID": 42,
        "ACTIVE_TELEGRAM_WEBHOOK_WATCHDOG": "",
        "ACTIVE_TELEGRAM_WEBHOOK_URL": "",
        "expected_telegram_webhook_url": lambda: EXPECTED_WEBHOOK,
        "serialize_telegram_webhook_info": lambda info, expected: {
            "url": info.url,
            "matches_expected": info.url == expected,
        },
        "set_telegram_webhook_takeover": lambda _bot, drop_pending_updates: _takeover_result(
            drop_pending_updates
        ),
    }
    exec(compile(match.group(0), "bot.py:telegram_webhook_watchdog", "exec"), namespace)
    return namespace["telegram_webhook_watchdog"]


async def _takeover_result(drop_pending_updates):
    assert drop_pending_updates is False
    return {"ok": True, "webhook_url": EXPECTED_WEBHOOK}


def test_mismatch_notice_reports_expected_webhook_without_wrong_host_claim():
    notices = []

    class FakeTelegramBot:
        async def get_webhook_info(self):
            return SimpleNamespace(url="https://old.example/webhook")

        async def send_message(self, **kwargs):
            notices.append(kwargs)

    sleep_count = 0

    async def one_watchdog_iteration(_seconds):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 1:
            raise asyncio.CancelledError

    watchdog = _load_watchdog(FakeTelegramBot(), one_watchdog_iteration)
    try:
        asyncio.run(watchdog())
    except asyncio.CancelledError:
        pass

    assert len(notices) == 1
    assert notices[0]["chat_id"] == 42
    assert EXPECTED_WEBHOOK in notices[0]["text"]
    assert "Railway" not in notices[0]["text"]
