import argparse
import asyncio
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402


def clean_guard(subtitle_path: pathlib.Path, target: str, reason: str, *, no_charge: bool) -> dict:
    return {
        "ok": True,
        "status": "CLEAN_GUARD",
        "subtitle": str(subtitle_path),
        "target": str(target or ""),
        "reason": str(reason or "translation_provider_skipped"),
        "provider_called": False,
        "translated_srt_created": False,
        "translated_vtt_created": False,
        "translated_txt_created": False,
        "timestamps_preserved": False,
        "clean_guard": True,
        "no_charge": bool(no_charge),
    }


async def run_smoke(subtitle_path: pathlib.Path, target: str, no_charge: bool, confirm_paid: bool) -> dict:
    if not no_charge and not confirm_paid:
        raise RuntimeError("Refusing translation smoke without --no-charge or --confirm-paid")
    source = subtitle_path.read_text(encoding="utf-8")
    segments = bot.video_dubbing_segments_from_subtitle(source)
    if not segments:
        return {
            "ok": False,
            "status": "INVALID_SOURCE_SRT",
            "subtitle": str(subtitle_path),
            "target": target,
            "segments": 0,
        }
    if not bot.video_translation_provider_configured():
        return clean_guard(subtitle_path, target, "translation_adapter_missing", no_charge=no_charge)
    if not confirm_paid:
        return clean_guard(subtitle_path, target, "provider_call_skipped_requires_confirm_paid", no_charge=no_charge)

    flags = {"charge_called": False}

    def forbidden_charge(*_args, **_kwargs):
        flags["charge_called"] = True
        raise AssertionError("subtitle translate smoke must not charge Xu")

    bot.spend_fixed_credit_info = forbidden_charge
    translated = await bot.translate_subtitle_segments(segments, target, allow_admin=True, updated_by=17065011)
    translated_srt = str(translated.get("srt") or "").strip()
    items = bot.video_dubbing_subtitle_output_items(translated_srt, "all", bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    output_map = {item["output_type"]: bytes(item.get("bytes") or b"") for item in items}
    source_times = [(item["start"], item["end"]) for item in segments]
    translated_segments = bot.video_dubbing_segments_from_subtitle(translated_srt)
    translated_times = [(item["start"], item["end"]) for item in translated_segments]
    timestamps_preserved = bool(source_times and source_times == translated_times)
    return {
        "ok": bool(
            translated_srt
            and translated_segments
            and timestamps_preserved
            and b"-->" in output_map.get("srt", b"")
            and output_map.get("vtt", b"").startswith(b"WEBVTT")
            and output_map.get("txt", b"").strip()
            and not flags["charge_called"]
        ),
        "status": "PASS" if translated_srt and timestamps_preserved else "NO_VALID_TRANSLATED_OUTPUT",
        "subtitle": str(subtitle_path),
        "target": target,
        "provider": str(translated.get("provider") or ""),
        "segments": len(translated_segments),
        "translated_srt_created": b"-->" in output_map.get("srt", b""),
        "translated_vtt_created": output_map.get("vtt", b"").startswith(b"WEBVTT"),
        "translated_txt_created": bool(output_map.get("txt", b"").strip()),
        "timestamps_preserved": timestamps_preserved,
        "no_charge": not flags["charge_called"],
        "clean_guard": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Existing SRT -> translated SRT/VTT/TXT smoke; preserves timestamps and never fakes PASS.")
    parser.add_argument("--subtitle", required=True)
    parser.add_argument("--target", default="en")
    parser.add_argument("--no-charge", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    args = parser.parse_args()
    subtitle_path = pathlib.Path(args.subtitle).resolve()
    if not subtitle_path.exists():
        print(json.dumps({"ok": False, "status": "INPUT_MISSING", "subtitle": str(subtitle_path)}, ensure_ascii=False))
        return 2
    try:
        summary = asyncio.run(run_smoke(subtitle_path, args.target, bool(args.no_charge), bool(args.confirm_paid)))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "FAIL_SUBTITLE_TRANSLATE_SMOKE", "error": str(exc), "subtitle": str(subtitle_path)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
