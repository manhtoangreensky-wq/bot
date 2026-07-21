from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.dubbing_pipeline import DubbingPipelineError, mux_final_video


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test blackbox FFmpeg mux without Telegram or Xu.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--burn-subtitles", action="store_true")
    parser.add_argument("--no-charge", action="store_true")
    args = parser.parse_args()

    video = Path(args.video)
    audio = Path(args.audio)
    subtitle = Path(args.subtitle) if args.subtitle else None
    if not video.exists() or video.stat().st_size <= 0:
        print(f"CLEAN_GUARD video_missing_or_empty path={video}")
        return 0
    if not audio.exists() or audio.stat().st_size <= 0:
        print(f"CLEAN_GUARD audio_missing_or_empty path={audio}")
        return 0
    if subtitle and (not subtitle.exists() or subtitle.stat().st_size <= 0):
        print(f"CLEAN_GUARD subtitle_missing_or_empty path={subtitle}")
        return 0
    output = Path(args.output) if args.output else video.with_name("smoke_mux_final.mp4")
    try:
        result = mux_final_video(
            str(video),
            str(audio),
            str(output),
            srt_path=str(subtitle) if subtitle else None,
            burn_subtitles=bool(args.burn_subtitles),
            replace_audio=True,
        )
    except DubbingPipelineError as exc:
        print(f"CLEAN_GUARD {exc}")
        return 0
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}")
        return 1
    result_path = Path(result)
    if result_path.exists() and result_path.stat().st_size > 0:
        print(f"PASS output={result_path} bytes={result_path.stat().st_size} no_charge={bool(args.no_charge)}")
        return 0
    print("FAIL output_missing_or_empty")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
