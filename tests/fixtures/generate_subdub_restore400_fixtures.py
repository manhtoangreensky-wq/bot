"""Generate SubDub RESTORE400 media fixtures at test time.

No binary fixtures are committed to the repository; tests call this script
(or its ``generate_fixture`` function) to build the inputs with ffmpeg.

Variant A (soft-sub): 11 s portrait MP4, H.264 (yuv420p) video + AAC audio,
plus an embedded, extractable Chinese subtitle track (mov_text).

Variant B (hardsub-only): same base video/audio but NO extractable subtitle
track, reproducing the live failing input whose Chinese subtitles are burned
into the frames. Burning visible glyphs requires a CJK font which CI runners
may not have, and the SubDub routing decision only depends on the absence of
an extractable subtitle stream, so glyph burn-in is intentionally skipped.

Both variants: ~11 s, portrait 720x1280, under 20 MB, Telegram-compatible
(H.264 yuv420p + AAC, +faststart).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile

DURATION_SECONDS = 11
CHINESE_SRT = (
    "1\n00:00:00,200 --> 00:00:03,000\n你好，世界\n\n"
    "2\n00:00:03,200 --> 00:00:07,000\n这是测试字幕\n\n"
    "3\n00:00:07,200 --> 00:00:10,800\n谢谢观看\n"
)


def _base_input_args() -> list[str]:
    return [
        "-f", "lavfi", "-i", f"color=c=0x203040:s=720x1280:d={DURATION_SECONDS}:r=30",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={DURATION_SECONDS}",
    ]


def _base_output_args() -> list[str]:
    return [
        "-t", str(DURATION_SECONDS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
    ]


def generate_fixture(variant: str, output_path: str, ffmpeg: str = "ffmpeg") -> str:
    variant = str(variant or "").strip().lower()
    if variant not in {"a", "b"}:
        raise ValueError("variant must be 'a' (soft-sub) or 'b' (hardsub-only)")
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    if variant == "a":
        srt_file = tempfile.NamedTemporaryFile(
            "w", suffix=".srt", delete=False, encoding="utf-8"
        )
        try:
            srt_file.write(CHINESE_SRT)
            srt_file.close()
            cmd += _base_input_args()
            cmd += ["-i", srt_file.name]
            cmd += _base_output_args()
            cmd += [
                "-c:s", "mov_text",
                "-metadata:s:s:0", "language=chi",
                "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
                output_path,
            ]
            subprocess.run(cmd, check=True, timeout=180)
        finally:
            try:
                os.unlink(srt_file.name)
            except OSError:
                pass
    else:
        cmd += _base_input_args()
        cmd += _base_output_args()
        cmd += ["-map", "0:v:0", "-map", "1:a:0", output_path]
        subprocess.run(cmd, check=True, timeout=180)
    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError(f"fixture generation produced no file: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True, choices=["a", "b"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    path = generate_fixture(args.variant, args.output, ffmpeg=args.ffmpeg)
    print(path)


if __name__ == "__main__":
    main()
