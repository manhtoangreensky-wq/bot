from fastapi.testclient import TestClient

import bot


LEGACY_PUBLIC_VERSION_MARKERS = (
    "V" + "15.2",
    "v" + "15.2",
    "TOAN AAS V" + "15.2",
    "TOAN AAS v" + "15.2",
)


def _assert_no_legacy_public_version(text: str) -> None:
    for marker in LEGACY_PUBLIC_VERSION_MARKERS:
        assert marker not in text


def _runtime_payload(monkeypatch):
    monkeypatch.setattr(bot, "OPERATOR_API_TOKEN", "runtime-test-token")
    monkeypatch.setattr(bot, "APP_BUILD", "abc1234")
    monkeypatch.setattr(bot, "APP_DEPLOY_ID", "deploy-test")
    client = TestClient(bot.fastapi_app)
    response = client.get("/runtime?token=runtime-test-token")
    assert response.status_code == 200
    return response.json()


def test_public_version_is_v1_beta():
    assert bot.PUBLIC_VERSION == "v1.0 Beta"
    assert bot.APP_VERSION == "TOAN AAS v1.0 Beta"
    assert bot.fastapi_app.title == "TOAN AAS v1.0 Beta"


def test_public_start_menu_does_not_show_v15_2(monkeypatch):
    monkeypatch.setattr(bot, "get_user", lambda *_args, **_kwargs: (0, 0, False))
    monkeypatch.setattr(bot, "is_admin_user", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(bot, "get_role_badge", lambda *_args, **_kwargs: "Newbie")
    text = "\n".join(
        [
            bot.build_start_message_text("customer-test"),
            bot.localized_start_menu_text("customer-test", "vi"),
            bot.localized_start_menu_text("customer-test", "en"),
            bot.localized_start_menu_text("customer-test", "zh"),
        ]
    )
    assert "TOAN AAS" in text
    _assert_no_legacy_public_version(text)


def test_public_menu_footer_does_not_show_v15_2():
    text = "\n".join(
        [
            bot.menu_text_main(False),
            bot.menu_text_main(True),
            bot.menu_text_system(),
        ]
    )
    assert "v1.0 Beta" in text
    _assert_no_legacy_public_version(text)


def test_runtime_keeps_internal_build_info(monkeypatch):
    payload = _runtime_payload(monkeypatch)
    assert payload["build"] == "abc1234"
    assert payload["deploy_id"] == "deploy-test"
    assert payload["app_version"] == "TOAN AAS v1.0 Beta"
    assert "telegram" in payload
    assert "telegram_update_mode" in payload
    assert "public_base_url_source" in payload


def test_runtime_shows_public_version_v1_beta(monkeypatch):
    payload = _runtime_payload(monkeypatch)
    assert payload["service"] == "TOAN AAS"
    assert payload["public_version"] == "v1.0 Beta"
    assert payload["app_version"] == "TOAN AAS v1.0 Beta"
    _assert_no_legacy_public_version(str(payload))
