import argparse
import asyncio
import json
import pathlib
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402


def clean_guard(reason: str, *, no_charge: bool) -> dict:
    return {
        "ok": True,
        "status": "CLEAN_GUARD",
        "reason": str(reason or "default_voice_output_unavailable"),
        "provider_hint": "default_free",
        "forced_preview": False,
        "output_audio_exists": False,
        "output_audio_bytes": 0,
        "clean_guard": True,
        "no_charge": bool(no_charge),
    }


async def run_smoke(text: str, voice: str, no_charge: bool) -> dict:
    clean_text = " ".join(str(text or "").split())
    if not clean_text:
        raise RuntimeError("empty_text")
    if not no_charge:
        raise RuntimeError("Default voice smoke must be run with --no-charge")

    flags = {"charge_called": False, "preview_cap_called": False}

    def forbidden_charge(*_args, **_kwargs):
        flags["charge_called"] = True
        raise AssertionError("default voice smoke must not charge Xu")

    async def forbidden_preview_cap(*_args, **_kwargs):
        flags["preview_cap_called"] = True
        raise AssertionError("default voice flow must not force 6-second preview")

    bot.spend_fixed_credit_info = forbidden_charge
    bot.cap_voice_preview_audio_bytes = forbidden_preview_cap
    tmpdir_path = pathlib.Path(tempfile.mkdtemp(prefix="toanaas_default_voice_db_"))
    bot.DB_FILE = str(tmpdir_path / "smoke.db")
    bot.DB_BACKUP_DIR = str(tmpdir_path / "backups")
    bot.init_db()
    result = await bot.execute_engine(
        "voice_tts",
        {
            "text": clean_text,
            "voice_id": voice,
            "voice_style": voice,
            "speed": "normal",
            "provider_hint": "default_free",
        },
        {
            "user_id": 17065010,
            "entry_source": bot.ENGINE_ENTRY_SOURCE_PRODUCT,
            "confirm_paid": True,
            "admin_interactive_confirm": False,
            "is_paid_job": False,
            "allow_admin": False,
        },
    )
    audio_bytes = bytes(result.get("output_bytes") or b"")
    if not result.get("ok") or not audio_bytes:
        return clean_guard(str(result.get("detail") or result.get("status") or "no_output_bytes"), no_charge=no_charge)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", prefix="toanaas_default_voice_") as handle:
        handle.write(audio_bytes)
        output_path = handle.name
    return {
        "ok": bool(pathlib.Path(output_path).exists() and audio_bytes and not flags["charge_called"] and not flags["preview_cap_called"]),
        "status": "PASS",
        "provider_hint": "default_free",
        "voice": voice,
        "forced_preview": False,
        "output_audio_exists": pathlib.Path(output_path).exists(),
        "output_audio_bytes": len(audio_bytes),
        "output_path": output_path,
        "no_charge": not flags["charge_called"],
        "clean_guard": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Default free voice smoke; locked against charge and forced 6-second preview.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", default="default_female")
    parser.add_argument("--no-charge", action="store_true")
    args = parser.parse_args()
    try:
        summary = asyncio.run(run_smoke(args.text, args.voice, bool(args.no_charge)))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "FAIL_DEFAULT_VOICE_SMOKE", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
