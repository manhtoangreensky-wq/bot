from pathlib import Path
import os
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_PY = REPO_ROOT / "bot.py"


def test_bot_main_uses_configurable_bind_address_and_port():
    text = BOT_PY.read_text(encoding="utf-8")
    assert 'host="0.0.0.0"' not in text
    assert "host=BOT_BIND_ADDRESS" in text
    assert "port=BOT_PORT" in text


def test_binding_defaults_via_subprocess():
    code = (
        "import bot;"
        "print(f'{bot.BOT_BIND_ADDRESS}|{bot.BOT_PORT}|{bot.PORT}')"
    )
    env = dict(os.environ)
    env.pop("BOT_BIND_ADDRESS", None)
    env.pop("BOT_PORT", None)
    env.pop("PORT", None)

    res = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout.strip().splitlines()[-1]
    bind, bot_port, port = out.split("|")
    assert bind == "127.0.0.1"
    assert bot_port == "8000"
    assert port == "8000"


def test_binding_env_overrides_via_subprocess():
    code = (
        "import bot;"
        "print(f'{bot.BOT_BIND_ADDRESS}|{bot.BOT_PORT}')"
    )
    env = dict(os.environ)
    env["BOT_BIND_ADDRESS"] = "127.0.0.2"
    env["BOT_PORT"] = "9999"

    res = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout.strip().splitlines()[-1]
    bind, bot_port = out.split("|")
    assert bind == "127.0.0.2"
    assert bot_port == "9999"
