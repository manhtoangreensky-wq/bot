from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.multiscene_video_pipeline import (  # noqa: E402
    SceneSpec,
    create_multiscene_workspace,
    ensure_video_output,
    probe_duration,
    process_multiscene_video_pipeline,
    safe_run_ffmpeg,
)


def ffmpeg_path() -> str:
    configured = os.getenv("FFMPEG_PATH", "").strip()
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which("ffmpeg") or ""


def fake_scene_renderer(duration: float, *, frame_size: str = "540x960"):
    colors = ["0x1E88E5", "0x43A047", "0xF4511E", "0x8E24AA", "0xFDD835"]

    def _render(scene: SceneSpec, output_path: str) -> str:
        ffmpeg = ffmpeg_path()
        if not ffmpeg:
            raise RuntimeError("ffmpeg_missing")
        color = colors[(int(scene.scene_id) - 1) % len(colors)]
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={frame_size}:r=30:d={float(duration):.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ]
        result = safe_run_ffmpeg(cmd, timeout=90)
        if result.returncode != 0:
            raise RuntimeError("fake_renderer_ffmpeg_failed")
        return ensure_video_output(output_path)

    return _render


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke the TOAN AAS multiscene blackbox with a local fake renderer.")
    parser.add_argument("--scenes", type=int, default=3)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--fake-renderer", action="store_true")
    parser.add_argument("--no-charge", action="store_true")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--matrix-r18s4", action="store_true", help="Run the offline 2x8, 4x8, and 8x8 matrix.")
    args = parser.parse_args()

    if not args.fake_renderer:
        print("FAIL fake renderer is required for this smoke")
        return 2
    if not args.no_charge:
        print("FAIL --no-charge is required")
        return 2
    if not args.matrix_r18s4 and (args.scenes != 3 or abs(float(args.duration) - 6.0) > 0.001):
        print("FAIL first smoke target must be 3 scenes x 6s")
        return 2

    if args.output_dir:
        os.environ["MULTISCENE_VIDEO_TEMP_ROOT"] = os.path.abspath(args.output_dir)
    matrix = [(2, 8.0), (4, 8.0), (8, 8.0)] if args.matrix_r18s4 else [(int(args.scenes), float(args.duration))]
    for scene_count, scene_duration in matrix:
        job_id = f"smoke-{scene_count}x{int(scene_duration)}-{uuid.uuid4().hex[:10]}"
        workspace = create_multiscene_workspace(job_id)
        result = process_multiscene_video_pipeline(
            user_id="smoke",
            job_id=job_id,
            user_prompt="Scene one opens with a product reveal. Scene two shows the benefit. Scene three proves the value. Scene four closes cleanly.",
            workspace_dir=workspace,
            render_video_func=fake_scene_renderer(0.16 if args.matrix_r18s4 else scene_duration, frame_size="96x160" if args.matrix_r18s4 else "540x960"),
            max_scenes=scene_count,
            default_scene_duration=scene_duration,
            aspect_ratio="9:16",
            enable_voice=False,
            enable_subtitle=not args.matrix_r18s4,
            enable_logo=False,
        )
        final_path = str(result.get("final_video_path") or "")
        if not result.get("ok") or not final_path:
            print(f"FAIL {scene_count}x{scene_duration:g} {result.get('error') or result.get('status')}")
            print(f"manifest={result.get('manifest_path')}")
            return 1
        ensure_video_output(final_path)
        actual_duration = probe_duration(final_path)
        target_duration = scene_count * scene_duration
        if abs(actual_duration - target_duration) > max(1.0, scene_count * 0.2):
            print(f"FAIL {scene_count}x{scene_duration:g} duration={actual_duration:.3f} target={target_duration:.3f}")
            return 1
        print(f"PASS multiscene blackbox {scene_count}x{scene_duration:g}")
        print(f"workspace={workspace}")
        print(f"final_video_path={final_path}")
        print(f"duration_sec={actual_duration:.3f}")
        print(f"manifest_path={result.get('manifest_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
