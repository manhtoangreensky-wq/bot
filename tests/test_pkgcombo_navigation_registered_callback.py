"""Exercise a customer package Back route through its registered handler."""
import re
from pathlib import Path
from types import SimpleNamespace

import unittest


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
EXPECTED_DETAIL_ORIGIN_CODES = {
    "pricing_main_profile": "a", "pricing_catalog": "b",
    "pricing_total_catalog": "d", "pricing_total_profile": "e",
}


class _Button:
    def __init__(self, text, callback_data=None, **_kwargs):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, username=None, first_name=None)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _source_function(name):
    match = re.search(
        rf"(?ms)^(?:async )?def {re.escape(name)}\(.*?(?=^(?:async )?def |\Z)",
        BOT_SOURCE,
    )
    if not match:
        raise AssertionError(f"missing source function: {name}")
    return match.group(0)


def _runtime(lang="vi"):
    scope = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "public_pricing_locale": lambda lang: lang,
        "pricing_copy_language": lambda lang: lang,
        "public_hub_copy": lambda _lang: {
            "monthly_plans": "Monthly plans",
            "finished_combos": "Finished combos",
            "my_packages": "My packages",
            "large_order": "Custom order",
            "notes": "Notes",
            "main_menu": "Main menu",
            "packages_label": "Packages",
        },
        "public_page_title": lambda _page, _lang: "Pricing",
        "pkgcombo_normalize_group": lambda group: group,
        "public_task_package_entries": lambda group: [
            ("image_mini_monthly" if group == "image" else f"{group}_fixture", {"label": group, "group": group})
        ],
        "package_i18n_button_label": lambda entry, code, _kind, _lang: f"{entry['label']} {code}",
        "package_catalog_entry": lambda code, package_type: (
            {"group": "image", "manual": True}
            if package_type == "monthly" and code == "image_mini_monthly"
            else {"group": "combo", "manual": True, "label": "Fixture combo"}
            if package_type == "combo" and code == "combo_ad_video_588k"
            else None
        ),
        "package_purchase_detail_lines": lambda *_args: ["Package detail fixture"],
        "package_entry_auto_checkout_enabled": lambda _entry: False,
        "PACKAGE_TASK_GROUP_ORDER": (
            "image",
            "video",
            "music",
            "voice",
            "subtitle_dub",
            "prompt_workflow",
            "mixed",
        ),
        "pricing_packages_lines": lambda _lang: ["Packages screen"],
        "pricing_task_package_group_lines": lambda group, _lang: [f"{group} packages"],
        "public_video_combo_pricing_payload": lambda: [
            {"code": "combo_ad_video_588k", "label": "Fixture combo", "group": "combo"}
        ],
        "get_user_language": lambda _uid: lang,
        "user_package_summary_text": lambda user_id, lang: f"My packages fixture {user_id} ({lang})",
    }
    for name in (
        "pkgcombo_group_callback",
        "pkgcombo_large_order_callback",
        "pkgcombo_large_order_origin_token",
        "pkgcombo_large_order_back_callback",
        "pkgcombo_large_order_lines",
        "pkgcombo_large_order_keyboard",
        "render_pkgcombo_large_order",
        "package_group_for_code",
        "package_detail_back_callback",
        "pricing_packages_keyboard",
        "pricing_pkgcombo_notes_lines",
        "pricing_pkgcombo_notes_keyboard",
        "pricing_task_package_group_keyboard",
        "pricing_combo_keyboard",
        "my_packages_keyboard",
        "package_purchase_manual_keyboard",
        "package_purchase_confirm_keyboard",
        "render_pkgcombo_detail",
        "handle_pkgcombo_callback",
        "handle_package_purchase_callback",
    ):
        exec(compile("from __future__ import annotations\n" + _source_function(name), f"bot.py:{name}", "exec"), scope)

    cleared = []
    scope["clear_media_creator_pending_states"] = lambda uid: cleared.append(uid)
    scope["create_package_order_request"] = lambda *_args, **_kwargs: {"request_id": 0}
    async def render(query, lines, markup):
        query.edits.append(("\n".join(lines), markup))
    scope["edit_or_send_pricing_lines"] = render
    async def safe_render(query, text, **kwargs):
        query.edits.append((text, kwargs.get("reply_markup")))
    scope["safe_edit_or_send"] = safe_render
    scope["pricing_combo_lines"] = lambda _lang: ["Combo packages"]

    routes = []
    scope.update(
        tg_app=SimpleNamespace(add_handler=routes.append),
        CallbackQueryHandler=lambda handler, pattern: (handler, re.compile(pattern)),
    )
    registration = next(
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_pkgcombo_callback," in line
    )
    exec(registration, scope)
    if len(routes) != 1:
        raise AssertionError("expected exactly one registered package-combo callback")
    return scope, routes[0], cleared


def _click(route, user_id, callback_data):
    return _click_immediate(route, user_id, callback_data)


def _click_immediate(route, user_id, callback_data):
    handler, pattern = route
    if not pattern.search(callback_data):
        raise AssertionError(f"registered route does not accept {callback_data!r}")
    query = _Query(user_id, callback_data)
    coroutine = handler(SimpleNamespace(callback_query=query), SimpleNamespace())
    try:
        coroutine.send(None)
    except StopIteration:
        pass
    else:
        coroutine.close()
        raise AssertionError("fixture callback unexpectedly yielded asynchronous I/O")
    if query.answers != [((), {})]:
        raise AssertionError(f"callback acknowledgement mismatch: {query.answers!r}")
    return query


class PackageComboNavigationTests(unittest.TestCase):
    def test_account_package_origin_callbacks_fit_telegram_limit(self):
        scope, route, _ = _runtime()
        def assert_callbacks_fit(screen):
            for row in screen.edits[0][1].inline_keyboard:
                for button in row:
                    self.assertLessEqual(
                        len(button.callback_data.encode("utf-8")), 64,
                        msg=f"callback exceeds Telegram limit: {button.callback_data!r}",
                    )

        origins = (
            "pricing_main_profile", "pricing_catalog", "pricing_catalog_profile",
            "pricing_total_catalog", "pricing_total_profile", "pricing_image",
            "pricing_image_profile", "pricing_video", "pricing_video_profile",
        )
        for origin in origins:
            packages = _click_immediate(route, 90735, f"pkgcombo:home:{origin}")
            assert_callbacks_fit(packages)
            for task_group in ("image", "video", "music", "voice", "subtitle_dub", "prompt_workflow", "combo"):
                with self.subTest(origin=origin, group=task_group):
                    group_entry = next(
                        button for row in packages.edits[0][1].inline_keyboard for button in row
                        if button.callback_data.startswith(f"pkgcombo:group:{task_group}:")
                    )
                    package_group = _click_immediate(route, 90735, group_entry.callback_data)
                    assert_callbacks_fit(package_group)
                    large_order_entry = next(
                        button for row in package_group.edits[0][1].inline_keyboard for button in row
                        if button.text.startswith("📩")
                    )
                    order_back_callback = scope["pkgcombo_large_order_back_callback"](
                        large_order_entry.callback_data.split(":")[2:]
                    )
                    order_back = scope["pkgcombo_large_order_keyboard"](order_back_callback).inline_keyboard[0][0]
                    self.assertLessEqual(len(order_back.callback_data.encode("utf-8")), 64)
                    returned_group = _click_immediate(route, 90735, order_back.callback_data)
                    self.assertEqual(
                        [button.callback_data for row in package_group.edits[0][1].inline_keyboard for button in row],
                        [button.callback_data for row in returned_group.edits[0][1].inline_keyboard for button in row],
                    )
            for group, detail_prefix in (
                ("image", "pkgcombo:detail:"),
                ("combo", "pkgcombo:combo_detail:"),
            ):
                with self.subTest(origin=origin, group=group):
                    packages = _click_immediate(route, 90735, f"pkgcombo:home:{origin}")
                    group_entry = next(
                        button for row in packages.edits[0][1].inline_keyboard for button in row
                        if button.callback_data.startswith(f"pkgcombo:group:{group}:")
                    )
                    package_group = _click_immediate(route, 90735, group_entry.callback_data)
                    detail_entry = next(
                        button for row in package_group.edits[0][1].inline_keyboard for button in row
                        if button.callback_data.startswith(detail_prefix)
                    )
                    package_detail = _click_immediate(route, 90735, detail_entry.callback_data)
                    for screen in (packages, package_group, package_detail):
                        assert_callbacks_fit(screen)
                    detail_back = next(
                        button for row in package_detail.edits[0][1].inline_keyboard for button in row
                        if button.callback_data.startswith(f"pkgcombo:group:{group}:")
                    )
                    self.assertEqual(f"pkgcombo:group:{group}:{origin}", detail_back.callback_data)
                    returned_group = _click_immediate(route, 90735, detail_back.callback_data)
                    self.assertEqual(
                        [button.callback_data for row in package_group.edits[0][1].inline_keyboard for button in row],
                        [button.callback_data for row in returned_group.edits[0][1].inline_keyboard for button in row],
                    )
                    large_order_entry = next(
                        button for row in package_detail.edits[0][1].inline_keyboard for button in row
                        if button.text.startswith("📩")
                    )
                    order_back_callback = scope["pkgcombo_large_order_back_callback"](
                        large_order_entry.callback_data.split(":")[2:]
                    )
                    order_screen = scope["pkgcombo_large_order_keyboard"](order_back_callback)
                    order_back = order_screen.inline_keyboard[0][0]
                    self.assertLessEqual(len(order_back.callback_data.encode("utf-8")), 64)
                    returned_detail = _click_immediate(route, 90735, order_back.callback_data)
                    self.assertEqual(
                        [button.callback_data for row in package_detail.edits[0][1].inline_keyboard for button in row],
                        [button.callback_data for row in returned_detail.edits[0][1].inline_keyboard for button in row],
                    )
        self.assertEqual(
            "pkgcombo:combo_detail:a",
            scope["pkgcombo_large_order_back_callback"](["combo_detail", "a"]),
        )
        self.assertEqual(
            "pkgcombo:detail:a",
            scope["pkgcombo_large_order_back_callback"](["detail", "a"]),
        )

    def test_emitted_package_confirmation_dispatches_to_inert_purchase_seam(self):
        user_id = 90736
        scope, package_route, _ = _runtime("vi")
        scope["package_catalog_entry"] = lambda code, package_type: (
            {"group": "image", "manual": False, "label": "Image Mini", "default_days": 30}
            if package_type == "monthly" and code == "image_mini_monthly"
            else None
        )
        scope["package_entry_auto_checkout_enabled"] = lambda entry: bool(
            entry and not entry.get("manual")
        )

        image_group = scope["pricing_task_package_group_keyboard"]("image", "vi")
        detail_button = next(
            button
            for row in image_group.inline_keyboard
            for button in row
            if button.callback_data.startswith("pkgcombo:detail:")
        )
        detail = _click_immediate(package_route, user_id, detail_button.callback_data)
        confirm_button = next(
            button
            for row in detail.edits[0][1].inline_keyboard
            for button in row
            if button.callback_data.startswith("pkgbuy|confirm|")
        )
        self.assertEqual("✅ Xác nhận thanh toán", confirm_button.text)
        self.assertLessEqual(len(confirm_button.callback_data.encode("utf-8")), 64)

        back_button = next(
            button
            for row in detail.edits[0][1].inline_keyboard
            for button in row
            if button.text == "⬅️ Hủy"
        )
        self.assertEqual("pkgcombo:group:image", back_button.callback_data)
        returned_group = _click_immediate(package_route, user_id, back_button.callback_data)
        self.assertEqual("image packages", returned_group.edits[0][0])

        purchase_routes = []
        scope["tg_app"] = SimpleNamespace(add_handler=purchase_routes.append)
        purchase_registration = next(
            line.strip()
            for line in BOT_SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_package_purchase_callback," in line
        )
        exec(purchase_registration, scope)
        self.assertEqual(1, len(purchase_routes))
        purchase_handler, purchase_pattern = purchase_routes[0]
        self.assertEqual("handle_package_purchase_callback", purchase_handler.__name__)
        self.assertIsNotNone(purchase_pattern.search(confirm_button.callback_data))

        start_calls = []

        async def inert_start_purchase(update, context, package_type, code, message=None):
            start_calls.append((update.callback_query.from_user.id, package_type, code, message))
            return "inert-checkout"

        scope["start_package_purchase"] = inert_start_purchase
        query = _Query(user_id, confirm_button.callback_data)
        query.message = object()
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace()
        callback_coro = purchase_handler(update, context)
        try:
            result = callback_coro.send(None)
        except StopIteration as completed:
            result = completed.value
        else:
            callback_coro.close()
            self.fail("inert package-confirm callback unexpectedly yielded I/O")

        self.assertEqual("inert-checkout", result)
        self.assertEqual([((), {})], query.answers)
        self.assertEqual(
            [(user_id, "monthly", "image_mini_monthly", query.message)],
            start_calls,
        )

    def test_pricing_catalog_packages_back_returns_to_catalog(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        user_id = 90730
        _, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, cleared = _runtime()
        catalog = pricing_fixture.fixture._dispatch(pricing_route, "pricing|catalog")
        catalog_markup = catalog.edits[0][1]["reply_markup"]
        catalog_controls = [button for row in catalog_markup.inline_keyboard for button in row]
        packages_entry = next(button for button in catalog_controls if button.text == "🎁 Gói/Combo")
        self.assertEqual("pkgcombo:home:pricing_catalog", packages_entry.callback_data)

        packages = _click(package_route, user_id, packages_entry.callback_data)
        self.assertEqual("Packages screen", packages.edits[0][0])
        back = next(button for row in packages.edits[0][1].inline_keyboard for button in row
                    if button.text.startswith("⬅"))
        self.assertEqual("pricing|catalog", back.callback_data)

        returned_catalog = pricing_fixture.fixture._dispatch(pricing_route, back.callback_data)
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in catalog_controls],
            [button.callback_data for row in returned_catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row],
        )
        self.assertEqual([((), {})], returned_catalog.answers)
        self.assertEqual([user_id], cleared)

    def test_account_catalog_packages_back_preserves_account_catalog_origin(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        user_id = 90729
        _, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, _ = _runtime()
        account_hub = pricing_fixture.fixture._dispatch(pricing_route, "pricing|main|profile")
        catalog = pricing_fixture.fixture._dispatch(pricing_route, pricing_fixture._callback(account_hub, "catalog"))
        catalog_controls = [button for row in catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row]
        packages_entry = next(button for button in catalog_controls if button.text == "🎁 Gói/Combo")
        self.assertEqual("pkgcombo:home:pricing_catalog_profile", packages_entry.callback_data)

        packages = _click(package_route, user_id, packages_entry.callback_data)
        back = next(button for row in packages.edits[0][1].inline_keyboard for button in row
                    if button.text.startswith("⬅"))
        self.assertEqual("pricing|catalog|profile", back.callback_data)
        returned_catalog = pricing_fixture.fixture._dispatch(pricing_route, back.callback_data)
        self.assertEqual(catalog.edits[0][0], returned_catalog.edits[0][0])
        self.assertEqual(
            [button.callback_data for button in catalog_controls],
            [button.callback_data for row in returned_catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row],
        )

    def test_catalog_origin_survives_package_group_back_to_home(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        user_id = 90728
        _, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, _ = _runtime()
        catalog = pricing_fixture.fixture._dispatch(pricing_route, "pricing|catalog")
        catalog_controls = [button for row in catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row]
        packages_entry = next(button for button in catalog_controls if button.text == "🎁 Gói/Combo")
        packages = _click(package_route, user_id, packages_entry.callback_data)
        package_controls = [button for row in packages.edits[0][1].inline_keyboard for button in row]
        group_entry = next(button for button in package_controls if button.callback_data.startswith("pkgcombo:group:image"))
        self.assertEqual("pkgcombo:group:image:pricing_catalog", group_entry.callback_data)

        group = _click(package_route, user_id, group_entry.callback_data)
        group_controls = [button for row in group.edits[0][1].inline_keyboard for button in row]
        back_home = next(button for button in group_controls if button.text.startswith("⬅"))
        self.assertEqual("pkgcombo:home:pricing_catalog", back_home.callback_data)
        returned_home = _click(package_route, user_id, back_home.callback_data)
        returned_controls = [button for row in returned_home.edits[0][1].inline_keyboard for button in row]
        self.assertEqual([button.callback_data for button in package_controls],
                         [button.callback_data for button in returned_controls])
        back_catalog = next(button for button in returned_controls if button.text.startswith("⬅"))
        self.assertEqual("pricing|catalog", back_catalog.callback_data)
        returned_catalog = pricing_fixture.fixture._dispatch(pricing_route, back_catalog.callback_data)
        self.assertEqual([button.callback_data for button in catalog_controls],
                         [button.callback_data for row in returned_catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row])

    def test_image_and_video_pricing_packages_back_return_to_source_screen(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        _, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, _ = _runtime()
        for index, action in enumerate(("image", "video"), start=1):
            with self.subTest(action=action):
                parent = pricing_fixture.fixture._dispatch(pricing_route, f"pricing|{action}")
                parent_controls = [button for row in parent.edits[0][1]["reply_markup"].inline_keyboard for button in row]
                packages_entry = next(button for button in parent_controls
                                      if button.text in {"🎁 Gói / Combo", "🎁 Gói/Combo"})
                packages = _click(package_route, 90720 + index, packages_entry.callback_data)
                back = next(button for row in packages.edits[0][1].inline_keyboard for button in row
                            if button.text.startswith("⬅"))
                self.assertEqual(f"pricing|{action}", back.callback_data)
                returned = pricing_fixture.fixture._dispatch(pricing_route, back.callback_data)
                self.assertEqual(parent.edits[0][0], returned.edits[0][0])
                self.assertEqual(
                    [button.callback_data for button in parent_controls],
                    [button.callback_data for row in returned.edits[0][1]["reply_markup"].inline_keyboard for button in row],
                )

        account_image = pricing_fixture.fixture._dispatch(pricing_route, "pricing|image|profile")
        account_controls = [button for row in account_image.edits[0][1]["reply_markup"].inline_keyboard for button in row]
        account_entry = next(button for button in account_controls if button.text == "🎁 Gói / Combo")
        self.assertEqual("pkgcombo:home:pricing_image_profile", account_entry.callback_data)
        account_packages = _click(package_route, 90723, account_entry.callback_data)
        account_back = next(button for row in account_packages.edits[0][1].inline_keyboard for button in row
                            if button.text.startswith("⬅"))
        self.assertEqual("pricing|image|profile", account_back.callback_data)
        returned_account_image = pricing_fixture.fixture._dispatch(pricing_route, account_back.callback_data)
        self.assertEqual(
            [button.callback_data for button in account_controls],
            [button.callback_data for row in returned_account_image.edits[0][1]["reply_markup"].inline_keyboard for button in row],
        )

    def test_catalog_origin_survives_package_detail_back_to_group_and_catalog(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        user_id = 90724
        _, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, _ = _runtime()
        catalog = pricing_fixture.fixture._dispatch(pricing_route, "pricing|catalog")
        catalog_controls = [button for row in catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row]
        packages_entry = next(button for button in catalog_controls if button.text == "🎁 Gói/Combo")
        packages = _click(package_route, user_id, packages_entry.callback_data)
        package_controls = [button for row in packages.edits[0][1].inline_keyboard for button in row]
        group_entry = next(button for button in package_controls if button.callback_data.startswith("pkgcombo:group:image"))
        group = _click(package_route, user_id, group_entry.callback_data)
        group_controls = [button for row in group.edits[0][1].inline_keyboard for button in row]
        detail_entry = next(button for button in group_controls if button.callback_data.startswith("pkgcombo:detail:"))
        self.assertEqual("pkgcombo:detail:image_mini_monthly:b", detail_entry.callback_data)

        detail = _click(package_route, user_id, detail_entry.callback_data)
        self.assertEqual("Package detail fixture", detail.edits[0][0])
        detail_back = next(button for row in detail.edits[0][1].inline_keyboard for button in row
                           if button.text.startswith(("⬅", "🔙", "←")))
        self.assertEqual("pkgcombo:group:image:pricing_catalog", detail_back.callback_data)
        returned_group = _click(package_route, user_id, detail_back.callback_data)
        self.assertEqual([button.callback_data for button in group_controls],
                         [button.callback_data for row in returned_group.edits[0][1].inline_keyboard for button in row])
        group_back = next(button for row in returned_group.edits[0][1].inline_keyboard for button in row
                          if button.text.startswith("⬅"))
        self.assertEqual("pkgcombo:home:pricing_catalog", group_back.callback_data)
        returned_home = _click(package_route, user_id, group_back.callback_data)
        home_back = next(button for row in returned_home.edits[0][1].inline_keyboard for button in row
                         if button.text.startswith("⬅"))
        self.assertEqual("pricing|catalog", home_back.callback_data)
        returned_catalog = pricing_fixture.fixture._dispatch(pricing_route, home_back.callback_data)
        self.assertEqual([button.callback_data for button in catalog_controls],
                         [button.callback_data for row in returned_catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row])

    def test_catalog_origin_survives_package_notes_and_my_packages_back(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        _, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, _ = _runtime()
        catalog = pricing_fixture.fixture._dispatch(pricing_route, "pricing|catalog")
        catalog_controls = [button for row in catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row]
        packages_entry = next(button for button in catalog_controls if button.text == "🎁 Gói/Combo")

        for index, action in enumerate(("notes", "my"), start=1):
            with self.subTest(action=action):
                packages = _click(package_route, 90725 + index, packages_entry.callback_data)
                package_controls = [button for row in packages.edits[0][1].inline_keyboard for button in row]
                child_entry = next(button for button in package_controls
                                   if button.callback_data.startswith(f"pkgcombo:{action}"))
                self.assertEqual(f"pkgcombo:{action}:pricing_catalog", child_entry.callback_data)
                child = _click(package_route, 90725 + index, child_entry.callback_data)
                child_controls = [button for row in child.edits[0][1].inline_keyboard for button in row]
                back_home = next(button for button in child_controls
                                 if button.text.startswith(("⬅", "🔙", "←")))
                self.assertEqual("pkgcombo:home:pricing_catalog", back_home.callback_data)
                returned_home = _click(package_route, 90725 + index, back_home.callback_data)
                home_back = next(button for row in returned_home.edits[0][1].inline_keyboard for button in row
                                 if button.text.startswith(("⬅", "🔙", "←")))
                self.assertEqual("pricing|catalog", home_back.callback_data)
                returned_catalog = pricing_fixture.fixture._dispatch(pricing_route, home_back.callback_data)
                self.assertEqual([button.callback_data for button in catalog_controls],
                                 [button.callback_data for row in returned_catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row])

    def test_account_pricing_hub_packages_back_returns_to_account_hub(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        _, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, _ = _runtime()
        hub = pricing_fixture.fixture._dispatch(pricing_route, "pricing|main|profile")
        hub_controls = [button for row in hub.edits[0][1]["reply_markup"].inline_keyboard for button in row]
        packages_entry = next(button for button in hub_controls if button.callback_data.startswith("pkgcombo:home"))
        self.assertEqual("pkgcombo:home:pricing_main_profile", packages_entry.callback_data)
        packages = _click(package_route, 90727, packages_entry.callback_data)
        back = next(button for row in packages.edits[0][1].inline_keyboard for button in row
                    if button.text.startswith("⬅"))
        self.assertEqual("pricing|main|profile", back.callback_data)
        returned_hub = pricing_fixture.fixture._dispatch(pricing_route, back.callback_data)
        self.assertEqual([button.callback_data for button in hub_controls],
                         [button.callback_data for row in returned_hub.edits[0][1]["reply_markup"].inline_keyboard for button in row])

    def test_account_pricing_package_group_and_detail_back_preserve_full_origin(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        ns, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, _ = _runtime()
        account_menu = ns["main_profile_keyboard"]("vi")
        account_pricing_entry = next(button for row in account_menu.inline_keyboard for button in row
                                     if button.callback_data.split("|")[:2] == ["pricing", "main"])
        account_hub = pricing_fixture.fixture._dispatch(pricing_route, account_pricing_entry.callback_data)

        scenarios = (
            ("pricing_main_profile", account_hub, "pricing|main|profile"),
            ("pricing_total_profile", pricing_fixture.fixture._dispatch(
                pricing_route,
                pricing_fixture._callback(
                    pricing_fixture.fixture._dispatch(
                        pricing_route,
                        pricing_fixture._callback(account_hub, "catalog"),
                    ),
                    "total",
                ),
            ), "pricing|total|profile"),
            ("pricing_total_catalog", pricing_fixture.fixture._dispatch(
                pricing_route,
                pricing_fixture._callback(
                    pricing_fixture.fixture._dispatch(
                        pricing_route,
                        pricing_fixture._callback(
                            pricing_fixture.fixture._dispatch(pricing_route, "pricing|main"),
                            "catalog",
                        ),
                    ),
                    "total",
                ),
            ), "pricing|total|catalog"),
        )
        for index, (origin, parent, expected_parent) in enumerate(scenarios):
            with self.subTest(origin=origin):
                user_id = 90729 + index
                parent_controls = [button for row in parent.edits[0][1]["reply_markup"].inline_keyboard for button in row]
                packages_entry = next(button for button in parent_controls
                                      if button.callback_data.startswith("pkgcombo:home"))
                self.assertEqual(f"pkgcombo:home:{origin}", packages_entry.callback_data)
                package_home = _click(package_route, user_id, packages_entry.callback_data)
                package_controls = [button for row in package_home.edits[0][1].inline_keyboard for button in row]
                group_entry = next(button for row in package_home.edits[0][1].inline_keyboard for button in row
                                   if button.callback_data.startswith("pkgcombo:group:image"))
                self.assertEqual(f"pkgcombo:group:image:{origin}", group_entry.callback_data)

                group = _click(package_route, user_id, group_entry.callback_data)
                group_controls = [button for row in group.edits[0][1].inline_keyboard for button in row]
                detail_entry = next(button for row in group.edits[0][1].inline_keyboard for button in row
                                    if button.callback_data.startswith("pkgcombo:detail:"))
                self.assertEqual(f"pkgcombo:detail:image_mini_monthly:{EXPECTED_DETAIL_ORIGIN_CODES[origin]}", detail_entry.callback_data)
                detail = _click(package_route, user_id, detail_entry.callback_data)
                detail_back = next(button for row in detail.edits[0][1].inline_keyboard for button in row
                                   if button.text.startswith(("⬅", "🔙", "←")))
                self.assertEqual(f"pkgcombo:group:image:{origin}", detail_back.callback_data)

                returned_group = _click(package_route, user_id, detail_back.callback_data)
                self.assertEqual([button.callback_data for button in group_controls],
                                 [button.callback_data for row in returned_group.edits[0][1].inline_keyboard for button in row])
                group_back = next(button for row in returned_group.edits[0][1].inline_keyboard for button in row
                                  if button.text.startswith(("⬅", "🔙", "←")))
                package_home_again = _click(package_route, user_id, group_back.callback_data)
                self.assertEqual([button.callback_data for button in package_controls],
                                 [button.callback_data for row in package_home_again.edits[0][1].inline_keyboard for button in row])
                package_back = next(button for row in package_home_again.edits[0][1].inline_keyboard for button in row
                                    if button.text.startswith(("⬅", "🔙", "←")))
                self.assertEqual(expected_parent, package_back.callback_data)
                returned_parent = pricing_fixture.fixture._dispatch(pricing_route, package_back.callback_data)
                self.assertEqual([button.callback_data for button in parent_controls],
                                 [button.callback_data for row in returned_parent.edits[0][1]["reply_markup"].inline_keyboard for button in row])

    def test_total_price_packages_back_returns_to_total_then_catalog(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        _, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, _ = _runtime()
        catalog = pricing_fixture.fixture._dispatch(pricing_route, "pricing|catalog")
        total_entry = next(button for row in catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row
                           if button.callback_data == "pricing|total|catalog")
        total = pricing_fixture.fixture._dispatch(pricing_route, total_entry.callback_data)
        total_controls = [button for row in total.edits[0][1]["reply_markup"].inline_keyboard for button in row]
        packages_entry = next(button for button in total_controls if button.callback_data.startswith("pkgcombo:home"))
        self.assertEqual("pkgcombo:home:pricing_total_catalog", packages_entry.callback_data)
        packages = _click(package_route, 90726, packages_entry.callback_data)
        back = next(button for row in packages.edits[0][1].inline_keyboard for button in row
                    if button.text.startswith("⬅"))
        self.assertEqual("pricing|total|catalog", back.callback_data)
        returned_total = pricing_fixture.fixture._dispatch(pricing_route, back.callback_data)
        self.assertEqual([button.callback_data for button in total_controls],
                         [button.callback_data for row in returned_total.edits[0][1]["reply_markup"].inline_keyboard for button in row])
        catalog_back = next(button for row in returned_total.edits[0][1]["reply_markup"].inline_keyboard for button in row
                            if button.callback_data == "pricing|catalog")
        returned_catalog = pricing_fixture.fixture._dispatch(pricing_route, catalog_back.callback_data)
        self.assertEqual([button.callback_data for row in catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row],
                         [button.callback_data for row in returned_catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row])

    def test_account_total_packages_back_preserves_account_pricing_chain(self):
        from tests import test_profile_pricing_back_origin as pricing_fixture

        _, pricing_route, _, _, _ = pricing_fixture._runtime("vi")
        _, package_route, _ = _runtime()
        account_hub = pricing_fixture.fixture._dispatch(pricing_route, "pricing|main|profile")
        catalog_entry = pricing_fixture._callback(account_hub, "catalog")
        catalog = pricing_fixture.fixture._dispatch(pricing_route, catalog_entry)
        total_entry = pricing_fixture._callback(catalog, "total")
        total = pricing_fixture.fixture._dispatch(pricing_route, total_entry)
        total_controls = [button for row in total.edits[0][1]["reply_markup"].inline_keyboard for button in row]
        packages_entry = next(button for button in total_controls if button.callback_data.startswith("pkgcombo:home"))
        self.assertEqual("pkgcombo:home:pricing_total_profile", packages_entry.callback_data)

        packages = _click(package_route, 90728, packages_entry.callback_data)
        back = next(button for row in packages.edits[0][1].inline_keyboard for button in row
                    if button.text.startswith("⬅"))
        self.assertEqual("pricing|total|profile", back.callback_data)

        returned_total = pricing_fixture.fixture._dispatch(pricing_route, back.callback_data)
        self.assertEqual(
            [button.callback_data for button in total_controls],
            [button.callback_data for row in returned_total.edits[0][1]["reply_markup"].inline_keyboard for button in row],
        )
        returned_catalog_back = next(button for row in returned_total.edits[0][1]["reply_markup"].inline_keyboard for button in row
                                     if button.callback_data == "pricing|catalog|profile")
        returned_catalog = pricing_fixture.fixture._dispatch(pricing_route, returned_catalog_back.callback_data)
        account_back = next(button for row in returned_catalog.edits[0][1]["reply_markup"].inline_keyboard for button in row
                            if button.callback_data == "pricing|main|profile")
        returned_account_hub = pricing_fixture.fixture._dispatch(pricing_route, account_back.callback_data)
        self.assertEqual(
            [button.callback_data for row in account_hub.edits[0][1]["reply_markup"].inline_keyboard for button in row],
            [button.callback_data for row in returned_account_hub.edits[0][1]["reply_markup"].inline_keyboard for button in row],
        )

    def test_emitted_image_group_back_returns_to_packages_via_registered_handler(self):
        user_id = 90731
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        menu_buttons = [button for row in package_menu.inline_keyboard for button in row]
        group_entry = next(button for button in menu_buttons if button.callback_data == "pkgcombo:group:image")
        self.assertEqual("🖼 Gói Ảnh", group_entry.text)

        group_screen = _click(route, user_id, group_entry.callback_data)
        self.assertEqual("image packages", group_screen.edits[0][0])
        group_markup = group_screen.edits[0][1]
        back = next(button for row in group_markup.inline_keyboard for button in row if button.text.startswith("⬅"))
        self.assertEqual("pkgcombo:home", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("Packages screen", returned.edits[0][0])
        returned_callbacks = [
            button.callback_data
            for row in returned.edits[0][1].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for button in menu_buttons],
            returned_callbacks,
        )
        self.assertIn("pricing|main", returned_callbacks)
        self.assertIn("menu|main", returned_callbacks)
        self.assertEqual([user_id, user_id], cleared)

    def test_emitted_package_detail_back_returns_to_origin_group_via_registered_handler(self):
        user_id = 90732
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        group_entry = next(
            button
            for row in package_menu.inline_keyboard
            for button in row
            if button.callback_data == "pkgcombo:group:image"
        )

        group_screen = _click(route, user_id, group_entry.callback_data)
        detail_entry = next(
            button
            for row in group_screen.edits[0][1].inline_keyboard
            for button in row
            if button.callback_data.startswith("pkgcombo:detail:")
        )
        self.assertEqual("pkgcombo:detail:image_mini_monthly", detail_entry.callback_data)

        detail_screen = _click(route, user_id, detail_entry.callback_data)
        self.assertEqual("Package detail fixture", detail_screen.edits[0][0])
        detail_buttons = [button for row in detail_screen.edits[0][1].inline_keyboard for button in row]
        back = next(button for button in detail_buttons if button.text.startswith("🔙"))
        self.assertEqual("pkgcombo:group:image", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("image packages", returned.edits[0][0])
        returned_callbacks = [
            button.callback_data
            for row in returned.edits[0][1].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for row in group_screen.edits[0][1].inline_keyboard for button in row],
            returned_callbacks,
        )
        self.assertEqual([user_id, user_id, user_id], cleared)
        self.assertFalse(
            any(
                callback.startswith(("pkgbuy|", "pkgcombo:pay", "pkgcombo:combo_pay"))
                for callback in returned_callbacks
            )
        )

    def test_emitted_combo_detail_back_returns_to_combo_group_via_registered_handler(self):
        user_id = 90733
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        combo_entry = next(
            button
            for row in package_menu.inline_keyboard
            for button in row
            if button.callback_data == "pkgcombo:group:combo"
        )

        combo_group = _click(route, user_id, combo_entry.callback_data)
        self.assertEqual("Combo packages", combo_group.edits[0][0])
        detail_entry = next(
            button
            for row in combo_group.edits[0][1].inline_keyboard
            for button in row
            if button.callback_data.startswith("pkgcombo:combo_detail:")
        )
        self.assertEqual("pkgcombo:combo_detail:combo_ad_video_588k", detail_entry.callback_data)

        detail_screen = _click(route, user_id, detail_entry.callback_data)
        self.assertEqual("Package detail fixture", detail_screen.edits[0][0])
        detail_buttons = [button for row in detail_screen.edits[0][1].inline_keyboard for button in row]
        back = next(button for button in detail_buttons if button.text.startswith("🔙"))
        self.assertEqual("pkgcombo:group:combo", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("Combo packages", returned.edits[0][0])
        returned_callbacks = [
            button.callback_data
            for row in returned.edits[0][1].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for row in combo_group.edits[0][1].inline_keyboard for button in row],
            returned_callbacks,
        )
        self.assertEqual([user_id, user_id, user_id], cleared)

    def test_emitted_package_notes_back_returns_to_same_package_home(self):
        user_id = 90734
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        package_callbacks = [
            button.callback_data
            for row in package_menu.inline_keyboard
            for button in row
        ]
        notes_entry = next(
            button
            for row in package_menu.inline_keyboard
            for button in row
            if button.callback_data == "pkgcombo:notes"
        )

        notes_screen = _click(route, user_id, notes_entry.callback_data)
        self.assertIn("ℹ️ <b>Lưu ý Gói / Combo</b>", notes_screen.edits[0][0])
        back = next(
            button
            for row in notes_screen.edits[0][1].inline_keyboard
            for button in row
            if button.text.startswith("⬅️")
        )
        self.assertEqual("pkgcombo:home", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("Packages screen", returned.edits[0][0])
        self.assertEqual(
            package_callbacks,
            [
                button.callback_data
                for row in returned.edits[0][1].inline_keyboard
                for button in row
            ],
        )
        self.assertEqual([user_id, user_id], cleared)

    def test_emitted_my_packages_back_returns_to_same_package_home(self):
        user_id = 90735
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        package_callbacks = [
            button.callback_data
            for row in package_menu.inline_keyboard
            for button in row
        ]
        my_packages_entry = next(
            button
            for row in package_menu.inline_keyboard
            for button in row
            if button.callback_data == "pkgcombo:my"
        )

        my_packages = _click(route, user_id, my_packages_entry.callback_data)
        self.assertEqual(f"My packages fixture {user_id} (vi)", my_packages.edits[0][0])
        back = next(
            button
            for row in my_packages.edits[0][1].inline_keyboard
            for button in row
            if button.text.startswith("⬅️")
        )
        self.assertEqual("pkgcombo:home", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("Packages screen", returned.edits[0][0])
        self.assertEqual(
            package_callbacks,
            [
                button.callback_data
                for row in returned.edits[0][1].inline_keyboard
                for button in row
            ],
        )
        self.assertEqual([user_id, user_id], cleared)

    def test_account_package_large_order_back_preserves_account_origin(self):
        scenarios = tuple(
            (origin, entry_point, expected_back, parent_back)
            for origin, parent_back in (
                ("pricing_main_profile", "pricing|main|profile"),
                ("pricing_catalog", "pricing|catalog"),
            )
            for entry_point, expected_back in (
                ("home", f"pkgcombo:home:{origin}"),
                ("notes", f"pkgcombo:notes:{origin}"),
                ("my", f"pkgcombo:my:{origin}"),
                ("group", f"pkgcombo:group:image:{origin}"),
                ("combo_group", f"pkgcombo:group:combo:{origin}"),
                ("detail", f"pkgcombo:detail:image_mini_monthly:{EXPECTED_DETAIL_ORIGIN_CODES[origin]}"),
                ("combo_detail", f"pkgcombo:combo_detail:combo_ad_video_588k:{EXPECTED_DETAIL_ORIGIN_CODES[origin]}"),
            )
        )
        for index, (origin, entry_point, expected_back, parent_back) in enumerate(scenarios):
            with self.subTest(origin=origin, entry_point=entry_point):
                user_id = 90736 + index
                _, package_route, _ = _runtime()
                package_home = _click_immediate(package_route, user_id, f"pkgcombo:home:{origin}")
                package_markup = package_home.edits[0][1]
                parent_screen = package_home

                if entry_point == "notes":
                    notes_entry = next(
                        button for row in package_markup.inline_keyboard for button in row
                        if button.callback_data.startswith("pkgcombo:notes:")
                    )
                    parent_screen = _click_immediate(package_route, user_id, notes_entry.callback_data)
                elif entry_point == "my":
                    my_entry = next(
                        button for row in package_markup.inline_keyboard for button in row
                        if button.callback_data.startswith("pkgcombo:my:")
                    )
                    parent_screen = _click_immediate(package_route, user_id, my_entry.callback_data)
                elif entry_point in {"group", "detail"}:
                    group_entry = next(
                        button for row in package_markup.inline_keyboard for button in row
                        if button.callback_data.startswith("pkgcombo:group:image:")
                    )
                    parent_screen = _click_immediate(package_route, user_id, group_entry.callback_data)
                elif entry_point in {"combo_group", "combo_detail"}:
                    group_entry = next(
                        button for row in package_markup.inline_keyboard for button in row
                        if button.callback_data.startswith("pkgcombo:group:combo:")
                    )
                    parent_screen = _click_immediate(package_route, user_id, group_entry.callback_data)

                if entry_point == "detail":
                    detail_entry = next(
                        button for row in parent_screen.edits[0][1].inline_keyboard for button in row
                        if button.callback_data.startswith("pkgcombo:detail:")
                    )
                    parent_screen = _click_immediate(package_route, user_id, detail_entry.callback_data)
                elif entry_point == "combo_detail":
                    detail_entry = next(
                        button for row in parent_screen.edits[0][1].inline_keyboard for button in row
                        if button.callback_data.startswith("pkgcombo:combo_detail:")
                    )
                    parent_screen = _click_immediate(package_route, user_id, detail_entry.callback_data)

                large_order_entry = next(
                    button for row in parent_screen.edits[0][1].inline_keyboard for button in row
                    if button.text.startswith("📩")
                )
                large_order = _click_immediate(package_route, user_id, large_order_entry.callback_data)
                back = next(
                    button for row in large_order.edits[0][1].inline_keyboard for button in row
                    if button.text.startswith("⬅")
                )
                self.assertEqual(expected_back, back.callback_data)

                returned_parent = _click_immediate(package_route, user_id, back.callback_data)
                self.assertEqual(
                    [button.callback_data for row in parent_screen.edits[0][1].inline_keyboard for button in row],
                    [button.callback_data for row in returned_parent.edits[0][1].inline_keyboard for button in row],
                )
                if entry_point == "home":
                    account_back = next(
                        button for row in returned_parent.edits[0][1].inline_keyboard for button in row
                        if button.text.startswith("⬅")
                    )
                    self.assertEqual(parent_back, account_back.callback_data)

    def test_package_home_large_order_back_preserves_origin_for_all_locales(self):
        for index, lang in enumerate(("en", "zh", "fr")):
            with self.subTest(lang=lang):
                _, route, _ = _runtime(lang)
                user_id = 90800 + index
                initial = _click_immediate(route, user_id, "pkgcombo:home:pricing_main_profile")
                initial_controls = [button for row in initial.edits[0][1].inline_keyboard for button in row]
                large_order_entry = next(
                    button for button in initial_controls
                    if str(button.callback_data).startswith("pkgcombo:large_order:home")
                )
                large_order = _click_immediate(route, user_id, large_order_entry.callback_data)
                back = next(
                    button for row in large_order.edits[0][1].inline_keyboard for button in row
                    if button.text.startswith("⬅")
                )
                self.assertEqual("pkgcombo:home:pricing_main_profile", back.callback_data)

                returned = _click_immediate(route, user_id, back.callback_data)
                returned_controls = [button for row in returned.edits[0][1].inline_keyboard for button in row]
                self.assertEqual(
                    [button.callback_data for button in initial_controls],
                    [button.callback_data for button in returned_controls],
                )


if __name__ == "__main__":
    unittest.main()
