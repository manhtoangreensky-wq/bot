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


async def run_smoke(input_path: pathlib.Path, no_charge: bool) -> dict:
    if not no_charge:
        raise RuntimeError("Refusing to run paid/provider smoke without --no-charge")
    data = input_path.read_bytes()
    flags = {
        "telegram_downloaded": False,
        "audio_extracted": False,
        "asr_called": False,
        "charge_called": False,
    }

    async def fake_embedded_subtitle(*_args, **_kwargs):
        return "", "smoke_no_embedded_subtitle"

    async def fake_extract_audio(source_bytes, content_type, max_seconds=0):
        flags["audio_extracted"] = True
        if not source_bytes:
            raise RuntimeError("smoke_empty_source")
        return b"smoke-audio-bytes", "audio/mpeg", "smoke_fake_ffmpeg_extract"

    async def fake_transcribe(audio_bytes, context, audio_content_type, **_kwargs):
        flags["asr_called"] = True
        if not audio_bytes:
            raise RuntimeError("smoke_empty_audio")
        return "smoke_unit_asr", "xin chao tu smoke subtitle pipeline", "smoke_no_charge"

    def fake_charge(*_args, **_kwargs):
        flags["charge_called"] = True
        raise AssertionError("smoke must not charge Xu")

    bot.video_dubbing_extract_embedded_subtitle = fake_embedded_subtitle
    bot.video_dubbing_audio_extract_ready = lambda: True
    bot.video_dubbing_extract_audio = fake_extract_audio
    bot.video_dubbing_transcribe_bytes = fake_transcribe
    bot.spend_fixed_credit_info = fake_charge

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
    summary = {
        "ok": bool(
            flags["telegram_downloaded"]
            and flags["asr_called"]
            and prepared.get("source_segments")
            and b"-->" in output_map.get("srt", b"")
            and output_map.get("vtt", b"").startswith(b"WEBVTT")
            and output_map.get("txt", b"").strip()
            and not flags["charge_called"]
        ),
        "input": str(input_path),
        "telegram_downloaded": flags["telegram_downloaded"],
        "audio_extracted": flags["audio_extracted"],
        "asr_called": flags["asr_called"],
        "segments": len(prepared.get("source_segments") or []),
        "srt_created": b"-->" in output_map.get("srt", b""),
        "vtt_created": output_map.get("vtt", b"").startswith(b"WEBVTT"),
        "txt_created": bool(output_map.get("txt", b"").strip()),
        "no_charge": not flags["charge_called"],
        "asr_provider": str(prepared.get("asr_provider") or ""),
    }
    if media_kind == "video" and not flags["audio_extracted"]:
        summary["ok"] = False
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Local no-charge smoke for media -> ASR -> subtitle pipeline.")
    parser.add_argument("--input", required=True, help="Path to a small video/audio fixture")
    parser.add_argument("--no-charge", action="store_true", help="Use local stubs and assert no Xu charge")
    args = parser.parse_args()
    input_path = pathlib.Path(args.input).resolve()
    if not input_path.exists():
        print(json.dumps({"ok": False, "error": "input_missing", "input": str(input_path)}, ensure_ascii=False))
        return 2
    try:
        summary = asyncio.run(run_smoke(input_path, bool(args.no_charge)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "input": str(input_path)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
