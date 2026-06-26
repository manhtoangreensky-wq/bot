import argparse
import asyncio
import json
import mimetypes
import pathlib
import sys
from types import SimpleNamespace


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402


class SmokeTelegramFile:
    def __init__(self, data: bytes):
        self.data = data
        self.downloaded = False

    async def download_as_bytearray(self):
        self.downloaded = True
        return bytearray(self.data)


class SmokeTelegramBot:
    def __init__(self, tg_file: SmokeTelegramFile):
        self.tg_file = tg_file
        self.file_id = ""

    async def get_file(self, file_id):
        self.file_id = str(file_id or "")
        return self.tg_file


def clean_guard(input_path: pathlib.Path, reason: str, readiness: dict, *, no_charge: bool) -> dict:
    return {
        "ok": True,
        "status": "CLEAN_GUARD",
        "input": str(input_path),
        "reason": str(reason or readiness.get("reason") or "provider_call_skipped"),
        "provider_ready": bool(readiness.get("configured")),
        "asr_called": False,
        "segments": 0,
        "srt_created": False,
        "vtt_created": False,
        "txt_created": False,
        "clean_guard": True,
        "no_charge": bool(no_charge),
        "provider": str(readiness.get("adapter") or readiness.get("provider") or ""),
    }


async def run_smoke(input_path: pathlib.Path, no_charge: bool, confirm_paid: bool) -> dict:
    if not no_charge and not confirm_paid:
        raise RuntimeError("Refusing provider smoke without --no-charge or --confirm-paid")
    readiness = bot.get_asr_adapter_readiness(public=False)
    if not readiness.get("configured"):
        return clean_guard(input_path, str(readiness.get("reason") or "asr_adapter_missing"), readiness, no_charge=no_charge)
    if not confirm_paid:
        return clean_guard(input_path, "provider_call_skipped_requires_confirm_paid", readiness, no_charge=no_charge)

    data = input_path.read_bytes()
    flags = {
        "telegram_downloaded": False,
        "asr_called": False,
        "charge_called": False,
    }

    def forbidden_charge(*_args, **_kwargs):
        flags["charge_called"] = True
        raise AssertionError("smoke must not charge Xu")

    original_transcribe = bot.video_dubbing_transcribe_bytes

    async def audited_transcribe(*args, **kwargs):
        flags["asr_called"] = True
        return await original_transcribe(*args, **kwargs)

    bot.video_dubbing_transcribe_bytes = audited_transcribe
    bot.spend_fixed_credit_info = forbidden_charge

    tg_file = SmokeTelegramFile(data)
    context = SimpleNamespace(bot=SmokeTelegramBot(tg_file))
    suffix = input_path.suffix.lower()
    content_type = str(mimetypes.guess_type(str(input_path))[0] or "video/mp4").lower()
    media_kind = "video" if suffix in {".mp4", ".mov", ".mkv", ".webm"} or content_type.startswith("video/") else "audio"
    user_id = 17065001
    bot.clear_video_dubbing_pending(user_id)
    state = bot.set_video_dubbing_pending(
        user_id,
        "creating_original_subtitle",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        source_file_id="smoke-telegram-file",
        video_file_id="smoke-telegram-file",
        source_file_name=input_path.name,
        source_mime_type=content_type,
        source_content_type=content_type,
        media_kind=media_kind,
        source_media_type=media_kind,
        source_duration=6,
        video_duration=6,
        source_file_size=len(data),
        video_file_size=len(data),
    )
    prepared = await bot.video_dubbing_prepare_subtitles(context, state, user_id, allow_admin=True)
    flags["telegram_downloaded"] = tg_file.downloaded
    srt = str(prepared.get("source_subtitle") or "")
    outputs = bot.video_dubbing_subtitle_output_items(srt, "all", bot.VIDEO_SUBTITLE_MODE_CREATE)
    output_map = {item["output_type"]: bytes(item["bytes"] or b"") for item in outputs}
    segments = list(prepared.get("source_segments") or [])
    return {
        "ok": bool(
            flags["telegram_downloaded"]
            and flags["asr_called"]
            and segments
            and b"-->" in output_map.get("srt", b"")
            and output_map.get("vtt", b"").startswith(b"WEBVTT")
            and output_map.get("txt", b"").strip()
            and not flags["charge_called"]
        ),
        "status": "PASS" if segments else "NO_SEGMENTS",
        "input": str(input_path),
        "telegram_downloaded": flags["telegram_downloaded"],
        "asr_called": flags["asr_called"],
        "segments": len(segments),
        "srt_created": b"-->" in output_map.get("srt", b""),
        "vtt_created": output_map.get("vtt", b"").startswith(b"WEBVTT"),
        "txt_created": bool(output_map.get("txt", b"").strip()),
        "no_charge": not flags["charge_called"],
        "asr_provider": str(prepared.get("asr_provider") or ""),
        "clean_guard": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Real media -> ASR -> subtitle smoke, with honest clean guard when provider calls are not allowed.")
    parser.add_argument("--input", required=True, help="Path to a small video/audio fixture")
    parser.add_argument("--no-charge", action="store_true", help="Assert no Xu charge; does not fake ASR")
    parser.add_argument("--confirm-paid", action="store_true", help="Allow the configured ASR provider to be called")
    args = parser.parse_args()
    input_path = pathlib.Path(args.input).resolve()
    if not input_path.exists():
        print(json.dumps({"ok": False, "status": "INPUT_MISSING", "input": str(input_path)}, ensure_ascii=False))
        return 2
    try:
        summary = asyncio.run(run_smoke(input_path, bool(args.no_charge), bool(args.confirm_paid)))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "FAIL_REAL_PIPELINE", "error": str(exc), "input": str(input_path)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
