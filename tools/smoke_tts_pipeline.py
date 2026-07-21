import argparse
import asyncio
import json
import pathlib
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402


def clean_guard(reason: str, readiness: dict, *, no_charge: bool) -> dict:
    return {
        "ok": True,
        "status": "CLEAN_GUARD",
        "reason": str(reason or readiness.get("reason") or "tts_not_ready"),
        "provider_ready": bool(readiness.get("configured")),
        "provider": str(readiness.get("provider") or ""),
        "model": str(readiness.get("model") or ""),
        "output_audio_exists": False,
        "output_audio_bytes": 0,
        "clean_guard": True,
        "no_charge": bool(no_charge),
    }


async def run_smoke(text: str, voice: str, preview: bool, no_charge: bool, confirm_paid: bool) -> dict:
    clean_text = " ".join(str(text or "").split())
    if not clean_text:
        raise RuntimeError("empty_text")
    if not no_charge and not confirm_paid:
        raise RuntimeError("Refusing provider smoke without --no-charge or --confirm-paid")
    readiness = bot.get_tts_provider_readiness(public=False)
    if not readiness.get("configured"):
        return clean_guard(str(readiness.get("reason") or "tts_provider_missing"), readiness, no_charge=no_charge)

    flags = {"charge_called": False}

    def forbidden_charge(*_args, **_kwargs):
        flags["charge_called"] = True
        raise AssertionError("smoke must not charge Xu")

    bot.spend_fixed_credit_info = forbidden_charge
    provider_hint = "default_free" if no_charge and not confirm_paid and voice in {"default_female", "default_male", "female", "male"} else ""
    result = await bot.execute_engine(
        "voice_tts",
        {
            "text": clean_text,
            "voice_id": voice,
            "voice_style": voice,
            "speed": "normal",
            "provider_hint": provider_hint,
        },
        {
            "user_id": 17065002,
            "entry_source": bot.ENGINE_ENTRY_SOURCE_PRODUCT,
            "confirm_paid": bool(confirm_paid or no_charge),
            "admin_interactive_confirm": bool(confirm_paid),
            "is_paid_job": bool(confirm_paid and not no_charge),
            "allow_admin": bool(confirm_paid),
        },
    )
    audio_bytes = bytes(result.get("output_bytes") or b"")
    if not result.get("ok") or not audio_bytes:
        return clean_guard(str(result.get("detail") or result.get("status") or "no_output_bytes"), readiness, no_charge=no_charge)
    final_bytes = audio_bytes
    if preview:
        final_bytes, _detail = await bot.cap_voice_preview_audio_bytes(audio_bytes, bot.voice_preview_seconds())
        final_bytes = final_bytes or audio_bytes
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", prefix="toanaas_tts_smoke_") as handle:
        handle.write(final_bytes)
        output_path = handle.name
    return {
        "ok": bool(final_bytes and pathlib.Path(output_path).exists() and not flags["charge_called"]),
        "status": "PASS",
        "provider": str(readiness.get("provider") or ""),
        "model": str(readiness.get("model") or ""),
        "voice": voice,
        "preview": bool(preview),
        "output_audio_exists": pathlib.Path(output_path).exists(),
        "output_audio_bytes": len(final_bytes or b""),
        "output_path": output_path,
        "no_charge": not flags["charge_called"],
        "clean_guard": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Real Voice/TTS smoke; returns clean guard instead of fake pass when provider output is unavailable.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", default="default_female")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--no-charge", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    args = parser.parse_args()
    try:
        summary = asyncio.run(run_smoke(args.text, args.voice, bool(args.preview), bool(args.no_charge), bool(args.confirm_paid)))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "FAIL_TTS_SMOKE", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
