import argparse
import asyncio
import json
import pathlib
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402


def clean_guard(reason: str, readiness: dict, *, no_charge: bool, segments: int) -> dict:
    return {
        "ok": True,
        "status": "CLEAN_GUARD",
        "reason": str(reason or readiness.get("reason") or "subtitle_dub_tts_not_ready"),
        "provider_ready": bool(readiness.get("configured")),
        "provider": str(readiness.get("provider") or ""),
        "model": str(readiness.get("model") or ""),
        "segments": int(segments or 0),
        "output_audio_exists": False,
        "output_audio_bytes": 0,
        "clean_guard": True,
        "no_charge": bool(no_charge),
    }


def preview_segments(segments: list[dict]) -> list[dict]:
    if not segments:
        return []
    selected = []
    first_start = float(segments[0].get("start") or 0)
    for item in segments:
        if len(selected) >= 3:
            break
        item_end = float(item.get("end") or 0)
        if selected and item_end - first_start > 15:
            break
        selected.append(dict(item))
    shifted = []
    for item in selected or [dict(segments[0])]:
        start = max(0.0, float(item.get("start") or 0) - first_start)
        end = max(start + 0.5, float(item.get("end") or 0) - first_start)
        shifted.append({**item, "start": start, "end": min(15.0, end)})
    return shifted


async def run_smoke(subtitle_path: pathlib.Path, voice: str, preview: bool, no_charge: bool, confirm_paid: bool) -> dict:
    if not no_charge and not confirm_paid:
        raise RuntimeError("Refusing provider smoke without --no-charge or --confirm-paid")
    subtitle_text = subtitle_path.read_text(encoding="utf-8-sig", errors="replace")
    segments = bot.video_dubbing_segments_from_subtitle(subtitle_text)
    if not segments:
        raise RuntimeError("subtitle_segments_empty")
    selected = preview_segments(segments) if preview else segments
    readiness = bot.get_tts_provider_readiness(public=False)
    if not readiness.get("configured"):
        return clean_guard(str(readiness.get("reason") or "tts_provider_missing"), readiness, no_charge=no_charge, segments=len(segments))

    original_provider = bot.TTS_PROVIDER
    if no_charge and not confirm_paid:
        if not bot.edge_tts:
            return clean_guard("edge_tts_missing_for_no_charge_smoke", readiness, no_charge=no_charge, segments=len(segments))
        bot.TTS_PROVIDER = "edge"
    flags = {"charge_called": False}

    def forbidden_charge(*_args, **_kwargs):
        flags["charge_called"] = True
        raise AssertionError("smoke must not charge Xu")

    bot.spend_fixed_credit_info = forbidden_charge
    try:
        voice_id = voice
        if bot.TTS_PROVIDER == "edge" and voice in {"default_female", "female"}:
            voice_id = bot.default_edge_tts_voice_id("female")
        elif bot.TTS_PROVIDER == "edge" and voice in {"default_male", "male"}:
            voice_id = bot.default_edge_tts_voice_id("male")
        tts_result = await bot.synthesize_dub_segment_chunks(
            selected,
            voice_style=voice,
            voice_id=voice_id,
            base_speed=1.0,
            max_speed=1.35,
            allow_admin=bool(confirm_paid),
        )
        chunks = list(tts_result.get("chunks") or [])
        duration = max(float(item.get("end") or 0) for item in selected)
        raw_audio, timeline_detail = await bot.build_dub_timeline_audio(chunks, max(1.0, duration))
        if not raw_audio:
            return clean_guard(f"dub_timeline_failed:{timeline_detail}", readiness, no_charge=no_charge, segments=len(segments))
        audio_bytes, normalization_detail = await bot.normalize_dub_audio_bytes(raw_audio)
        if not audio_bytes:
            return clean_guard(f"dub_normalization_failed:{normalization_detail}", readiness, no_charge=no_charge, segments=len(segments))
        if preview:
            audio_bytes, _cap_detail = await bot.cap_voice_preview_audio_bytes(audio_bytes, 15)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", prefix="toanaas_subtitle_dub_smoke_") as handle:
            handle.write(audio_bytes)
            output_path = handle.name
        return {
            "ok": bool(audio_bytes and pathlib.Path(output_path).exists() and not flags["charge_called"]),
            "status": "PASS",
            "subtitle": str(subtitle_path),
            "segments": len(segments),
            "preview_segments": len(selected),
            "provider": str(tts_result.get("provider") or readiness.get("provider") or ""),
            "voice": voice,
            "preview": bool(preview),
            "output_audio_exists": pathlib.Path(output_path).exists(),
            "output_audio_bytes": len(audio_bytes or b""),
            "output_path": output_path,
            "no_charge": not flags["charge_called"],
            "clean_guard": False,
        }
    except Exception as exc:
        return clean_guard(str(exc), readiness, no_charge=no_charge, segments=len(segments))
    finally:
        bot.TTS_PROVIDER = original_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Real subtitle-file -> segment TTS -> timeline audio smoke.")
    parser.add_argument("--subtitle", required=True)
    parser.add_argument("--voice", default="default_female")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--no-charge", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    args = parser.parse_args()
    subtitle_path = pathlib.Path(args.subtitle).resolve()
    if not subtitle_path.exists():
        print(json.dumps({"ok": False, "status": "SUBTITLE_MISSING", "subtitle": str(subtitle_path)}, ensure_ascii=False))
        return 2
    try:
        summary = asyncio.run(run_smoke(subtitle_path, args.voice, bool(args.preview), bool(args.no_charge), bool(args.confirm_paid)))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "FAIL_SUBTITLE_DUB_SMOKE", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
