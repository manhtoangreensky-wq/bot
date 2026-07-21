from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.dubbing_pipeline import cleanup_workspace, process_dubbing_pipeline


def _parse_srt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    segments: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r", "").strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        time_line = next((line for line in lines if "-->" in line), "")
        if not time_line:
            continue
        body = " ".join(line for line in lines if "-->" not in line and not line.isdigit()).strip()
        if body:
            segments.append({"start": 0, "end": 2 + len(segments) * 2, "text": body})
    return segments


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test blackbox dubbing pipeline without Telegram or Xu.")
    parser.add_argument("--video", default="")
    parser.add_argument("--subtitle", required=True)
    parser.add_argument("--voice", default="default_female")
    parser.add_argument("--audio", default="tests/fixtures/sample_audio.mp3")
    parser.add_argument("--workspace", default="")
    parser.add_argument("--no-charge", action="store_true")
    args = parser.parse_args()

    subtitle = Path(args.subtitle)
    if not subtitle.exists() or subtitle.stat().st_size <= 0:
        print(f"CLEAN_GUARD subtitle_missing_or_empty path={subtitle}")
        return 0
    audio = Path(args.audio)
    if not audio.exists() or audio.stat().st_size <= 0:
        print(f"CLEAN_GUARD tts_audio_fixture_missing path={audio}")
        return 0
    video = Path(args.video) if args.video else None
    if video and (not video.exists() or video.stat().st_size <= 0):
        print(f"CLEAN_GUARD video_missing_or_empty path={video}")
        return 0
    segments = _parse_srt(subtitle)
    if not segments:
        print("CLEAN_GUARD subtitle_segments_empty")
        return 0
    workspace = Path(args.workspace) if args.workspace else Path(tempfile.mkdtemp(prefix="toanaas_blackbox_smoke_"))
    workspace.mkdir(parents=True, exist_ok=True)

    def fixture_tts(_segments, voice_id="", workspace_dir=""):
        return audio.read_bytes()

    try:
        result = process_dubbing_pipeline(
            source_video_path=str(video) if video else None,
            subtitle_segments=segments,
            voice_id=args.voice,
            workspace_dir=str(workspace),
            tts_func=fixture_tts,
            burn_subtitles=False,
            final_only=True,
        )
        output_path = Path(result.get("video_path") or result.get("audio_path") or "")
        if result.get("ok") and output_path.exists() and output_path.stat().st_size > 0:
            print(
                f"PASS result_type={result.get('result_type')} output={output_path} "
                f"bytes={output_path.stat().st_size} mux_attempted={result.get('mux_attempted')} no_charge={bool(args.no_charge)}"
            )
            return 0
        print(f"CLEAN_GUARD {result.get('fallback_reason') or result.get('result_type') or 'no_output'}")
        return 0
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}")
        return 1
    finally:
        if not args.workspace:
            cleanup_workspace(str(workspace))
        elif workspace.exists():
            shutil.rmtree(workspace / "__empty_cleanup_marker__", ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
