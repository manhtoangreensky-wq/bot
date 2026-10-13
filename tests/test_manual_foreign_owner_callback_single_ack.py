import re
from pathlib import Path
from types import SimpleNamespace
import unittest


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Button:
    def __init__(self, text, callback_data=None, url=None, **_kwargs):
        self.text = text
        self.callback_data = callback_data
        self.url = url


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.message = SimpleNamespace()

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _source_function(name):
    starts = (
        BOT_SOURCE.find(f"\nasync def {name}(") + 1,
        BOT_SOURCE.find(f"\ndef {name}(") + 1,
    )
    start = next((position for position in starts if position > 0), -1)
    assert start >= 0, f"production function {name} is missing"
    lines = BOT_SOURCE[start:].splitlines(keepends=True)
    body = [lines[0]]
    for line in lines[1:]:
        if line.startswith(("async def ", "def ", "class ")):
            break
        body.append(line)
    return "".join(body)


def _run_no_io(awaitable):
    try:
        awaitable.send(None)
    except StopIteration:
        return
    awaitable.close()
    raise AssertionError("foreign-owner callback unexpectedly yielded I/O")


def _registered_manual_route():
    forbidden = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("foreign-owner callback reached a state, DB, payment, or provider seam")
    )
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "SimpleNamespace": SimpleNamespace,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "public_hub_copy": lambda _lang: {
            "manual_topup": "Nạp thủ công",
            "package_details": "Chi tiết gói",
            "topup_label": "Nạp Xu",
            "common_main_menu": "Menu chính",
            "main_menu": "Menu chính",
            "profile_packages": "Gói của tôi",
            "common_failed": "Không thực hiện được.",
            "common_back": "Quay lại",
        },
        "public_account_flow_copy": lambda _lang: {
            "manual_topup_rules": "Hướng dẫn nạp thủ công",
            "select_topup": "Chọn gói nạp",
            "quick_stats": "Lịch sử",
        },
        "normalize_user_language": lambda _lang: "vi",
        "public_copy_locale": lambda _lang: "vi",
        "get_user_language": lambda _uid: "vi",
        "MANUAL_FOREIGN_TOPUP_ENABLED": False,
        "MANUAL_BANK_ENABLED": True,
        "MANUAL_ZALOPAY_PERSONAL_ENABLED": False,
        "MANUAL_ZALOPAY_MERCHANT_ENABLED": False,
        "MANUAL_MOMO_TUITHANTAI_ENABLED": False,
        "SUPPORTED_MANUAL_CURRENCIES": {"USD"},
        "PAYMENT_PACKAGES": {
            "10k": {"amount": 10000},
            "20k": {"amount": 20000},
            "50k": {"amount": 50000},
            "100k": {"amount": 100000},
            "200k": {"amount": 200000},
            "500k": {"amount": 500000},
        },
        "format_foreign_amount": lambda value: str(value),
        "manual_payment_method_label": lambda method, _lang: method,
        "is_admin_user": lambda _uid: False,
        "db_connect": forbidden,
        "get_active_manual_bill_state": forbidden,
        "set_manual_bill_state": forbidden,
        "update_manual_bill_state": forbidden,
        "manual_vnd_topup_preview": forbidden,
        "foreign_topup_preview": forbidden,
        "manual_method_enabled": forbidden,
        "send_manual_payment_qr": forbidden,
        "set_manual_approval_state": forbidden,
        "cmd_duyet": forbidden,
        "cmd_tuchoi": forbidden,
    }
    for name in (
        "payos_package_callback_data",
        "manual_package_callback_data",
        "payos_unavailable_keyboard",
        "manual_payment_menu_keyboard",
        "manual_domestic_amount_keyboard",
        "manual_domestic_method_keyboard",
        "manual_foreign_amount_keyboard",
        "manual_foreign_preview_keyboard",
        "manual_method_keyboard",
        "handle_manual_package_choice",
    ):
        exec(compile(_source_function(name), f"bot.py:{name}", "exec"), namespace)

    registrations = []
    namespace.update(
        tg_app=SimpleNamespace(add_handler=registrations.append),
        CallbackQueryHandler=lambda callback, pattern: SimpleNamespace(
            callback=callback,
            pattern=re.compile(pattern),
        ),
    )
    registration = next(
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_manual_package_choice," in line
    )
    exec(registration, namespace)
    route = registrations[0]

    def emitted(keyboard, callback_data):
        button = next(
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data == callback_data
        )
        assert route.pattern.match(button.callback_data)
        return button.callback_data

    menu = namespace["manual_payment_menu_keyboard"](123)
    unavailable = namespace["payos_unavailable_keyboard"]("10k", 123)
    domestic = namespace["manual_domestic_amount_keyboard"](123)
    domestic_method = namespace["manual_domestic_method_keyboard"](123)
    foreign = namespace["manual_foreign_amount_keyboard"]("USD", 123)
    foreign_preview = namespace["manual_foreign_preview_keyboard"](
        {"currency": "USD", "original_amount": 10}, 123
    )
    namespace["get_active_manual_bill_state"] = lambda _uid: {
        "pkg_key": "10k",
        "foreign_manual": False,
    }
    payment_method = namespace["manual_method_keyboard"](123)
    namespace["get_active_manual_bill_state"] = forbidden
    callbacks = (
        emitted(menu, "manual|currency|VND|123"),
        emitted(domestic, "manual|vndamount|10k|123"),
        emitted(foreign, "manual|fxamount|USD|10|123"),
        emitted(foreign, "manual|fxcustom|USD|123"),
        emitted(foreign_preview, "manual|fxmethod|USD|10|usdt_trc20|123"),
        emitted(menu, "manual|history|123"),
        emitted(domestic_method, "manual|method|bank_acb|123"),
        emitted(domestic, "manual|menu|123"),
        emitted(payment_method, "manual|await_bill|123"),
        emitted(unavailable, "manual|start|10k|123"),
    )
    return route, callbacks


class ManualForeignOwnerCallbackSingleAckTests(unittest.TestCase):
    def test_emitted_owner_bound_customer_actions_deny_with_one_alert_ack(self):
        route, callbacks = _registered_manual_route()
        expected = (("⚠️ Không thực hiện được.",), {"show_alert": True})

        for callback_data in callbacks:
            with self.subTest(callback_data=callback_data):
                query = _Query(456, callback_data)
                _run_no_io(
                    route.callback(
                        SimpleNamespace(callback_query=query),
                        SimpleNamespace(args=[]),
                    )
                )
                self.assertEqual(query.answers, [expected])


if __name__ == "__main__":
    unittest.main()
