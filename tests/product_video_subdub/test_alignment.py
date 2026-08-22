from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

import pytest

from services import multiscene_video_pipeline
from services import product_video_addon_materialization, subdub_canonical_cues


ROOT = Path(__file__).resolve().parents[2]


def _srt_cues(path: Path) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((index for index, line in enumerate(lines) if "-->" in line), -1)
        assert timing_index >= 0, block
        start_text, end_text = [part.strip() for part in lines[timing_index].split("-->", 1)]

        def seconds(value: str) -> float:
            hours, minutes, remainder = value.replace(",", ".").split(":", 2)
            return (int(hours) * 3600) + (int(minutes) * 60) + float(remainder)

        cues.append(
            {
                "start": seconds(start_text),
                "end": seconds(end_text),
                "lines": lines[timing_index + 1 :],
            }
        )
    return cues


def test_product_video_subtitles_use_subdub_cues_without_crossing_scene_boundaries(
    tmp_path: Path,
) -> None:
    scene_one = (
        "Hạt cà phê được rang thủ công ở nhiệt độ ổn định để giữ hương thơm tự nhiên "
        "và tạo vị cân bằng cho từng mẻ rang mới."
    )
    scene_two = (
        "Barista rót chậm dòng cà phê vào ly trong suốt rồi hoàn thiện lớp bọt mịn "
        "để sản phẩm hiện lên rõ ràng và hấp dẫn."
    )
    result = product_video_addon_materialization.materialize_product_video_addons(
        {
            "addon_plan": {
                "contract_version": "product-video-addons-v1",
                "requested_addons": ["subtitle"],
                "subtitle": {
                    "enabled": True,
                    "target_language": "vi",
                    "script_text": f"{scene_one}\n{scene_two}",
                },
            }
        },
        workspace=str(tmp_path),
        scene_count=2,
        scene_duration=8.0,
    )

    assert result["ok"] is True
    assert Path(result["subtitle_path"]).suffix == ".ass"
    cues = _srt_cues(Path(result["subtitle_srt_path"]))
    assert len(cues) > 2
    assert cues[0]["start"] == 0.0
    assert cues[-1]["end"] == 16.0
    assert all(cue["start"] < cue["end"] for cue in cues)
    assert all(cue["end"] <= 8.0 for cue in cues if cue["start"] < 8.0)
    assert all(cue["start"] >= 8.0 for cue in cues if cue["end"] > 8.0)
    assert all(1 <= len(cue["lines"]) <= 2 for cue in cues)
    assert all(len(line) <= 42 for cue in cues for line in cue["lines"])
    assert result["subtitle_timeline_signature"] == subdub_canonical_cues.timeline_signature(
        result["subtitle_cues"]
    )
    assert result["subtitle_qc"]["renderer"] == "translation_v1_shared_autofit"
    assert result["subtitle_qc"]["frame_fit_pass"] is True
    ass_text = Path(result["subtitle_path"]).read_text(encoding="utf-8")
    dialogue = [line for line in ass_text.splitlines() if line.startswith("Dialogue: 0,")]
    assert len(dialogue) == len(cues)
    assert all(line.count(r"\N") <= 1 for line in dialogue)
    assert all(re.search(r"\{\\fs\d+\}", line) for line in dialogue)
    assert "Fontname, Fontsize" in ass_text
    assert "Alignment, MarginL, MarginR, MarginV" in ass_text


def test_product_video_subtitles_fall_back_to_persisted_scene_scripts(
    tmp_path: Path,
) -> None:
    result = product_video_addon_materialization.materialize_product_video_addons(
        {
            "scene_cards": [
                {"scene_index": 1, "script_text": "Rang hạt cà phê thủ công."},
                {"scene_index": 2, "script_text": "Barista rót cà phê vào ly."},
            ],
            "addon_plan": {
                "contract_version": "product-video-addons-v1",
                "requested_addons": ["subtitle", "transitions"],
                "subtitle": {
                    "enabled": True,
                    "source": "script",
                    "script_text": "",
                },
                "transition_plan": ["cut"],
            },
        },
        workspace=str(tmp_path),
        scene_count=2,
        scene_duration=8.0,
    )

    assert result["ok"] is True
    cues = _srt_cues(Path(result["subtitle_srt_path"]))
    assert cues[0]["start"] == 0.0
    assert all(cue["end"] <= 8.0 for cue in cues if cue["start"] < 8.0)
    assert all(8.0 <= cue["start"] < cue["end"] <= 16.0 for cue in cues if cue["start"] >= 8.0)
    assert any(cue["start"] < 8.0 for cue in cues)
    assert any(cue["start"] >= 8.0 for cue in cues)
    assert "Rang hạt cà phê thủ công." in Path(result["subtitle_srt_path"]).read_text(
        encoding="utf-8"
    )
    assert "Barista rót cà phê vào ly." in Path(result["subtitle_srt_path"]).read_text(
        encoding="utf-8"
    )


def test_translation_subdub_and_product_video_share_the_same_cue_fitter() -> None:
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    start = source.index("def video_dubbing_qc_segments(")
    end = source.index("\ndef subdub_retime_translated_segments_to_source(", start)

    assert "subdub_canonical_cues.fit_timed_subtitle_segments" in source[start:end]


def test_translation_subdub_and_product_video_share_the_same_production_frame_fitter() -> None:
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    fit_start = bot_source.index("def subdub_ass_fit_text_layout(")
    fit_end = bot_source.index("\ndef subdub_ass_wrap_text(", fit_start)
    materializer_source = (
        ROOT / "services" / "product_video_addon_materialization.py"
    ).read_text(encoding="utf-8")

    assert "subdub_ass_layout.fit_text_layout" in bot_source[fit_start:fit_end]
    assert "subdub_ass_layout.fit_text_layout" in materializer_source
    assert "services.subdub_v2" not in materializer_source


def test_shared_fitter_keeps_translation_legacy_timing_and_product_strict_boundary() -> None:
    source = [{"index": 1, "start": 2.0, "end": 2.5, "text": "Một cue ngắn."}]

    translation = subdub_canonical_cues.fit_timed_subtitle_segments(source)
    product = subdub_canonical_cues.fit_timed_subtitle_segments(
        source,
        strict_frame_fit=True,
    )

    assert translation == [
        {
            "index": 1,
            "start": 2.0,
            "end": 3.0,
            "text": "Một cue ngắn.",
            "confidence": None,
        }
    ]
    assert product[0]["start"] == 2.0
    assert product[0]["end"] == 2.5


def test_existing_timed_srt_is_preserved_and_rendered_through_subdub_ass(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.srt"
    source.write_text(
        "1\n00:00:01,250 --> 00:00:03,500\nPhụ đề có thời gian gốc.\n\n"
        "2\n00:00:04,000 --> 00:00:06,750\nCue thứ hai phải giữ nguyên.\n",
        encoding="utf-8",
    )
    result = product_video_addon_materialization.materialize_product_video_addons(
        {
            "output_width": 720,
            "output_height": 1280,
            "addon_plan": {
                "contract_version": "product-video-addons-v1",
                "requested_addons": ["subtitle"],
                "subtitle": {
                    "enabled": True,
                    "target_language": "vi",
                    "artifact_path": str(source),
                },
            },
        },
        workspace=str(tmp_path),
        scene_count=2,
        scene_duration=4.0,
    )

    assert result["ok"] is True
    assert Path(result["subtitle_path"]).suffix == ".ass"
    assert [(cue["start_ms"], cue["end_ms"]) for cue in result["subtitle_cues"]] == [
        (1250, 3500),
        (4000, 6750),
    ]


def _run_media(command: list[str]) -> bytes:
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="ignore")[-2000:]
    return completed.stdout


def _bright_x_positions(frame: bytes, width: int) -> list[int]:
    return [
        (index // 3) % width
        for index in range(0, len(frame), 3)
        if max(frame[index : index + 3]) >= 190
    ]


def test_product_video_subdub_burns_decodable_two_scene_mp4_inside_safe_frame(
    tmp_path: Path,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg unavailable for Product Video SubDub artifact proof")
    width, height = 360, 640
    source = tmp_path / "source.mp4"
    output = tmp_path / "product-video-subdub.mp4"
    _run_media(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:r=12:d=6",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ]
    )
    materials = product_video_addon_materialization.materialize_product_video_addons(
        {
            "output_width": width,
            "output_height": height,
            "addon_plan": {
                "contract_version": "product-video-addons-v1",
                "requested_addons": ["subtitle"],
                "subtitle": {
                    "enabled": True,
                    "target_language": "vi",
                    "script_text": (
                        "Hạt cà phê rang chậm giữ hương thơm, vị cân bằng và màu đẹp.\n"
                        "Barista rót chậm để ly cà phê hiện lên rõ nét và hấp dẫn."
                    ),
                },
            },
        },
        workspace=str(tmp_path),
        scene_count=2,
        scene_duration=3.0,
    )
    assert materials["ok"] is True

    rendered = multiscene_video_pipeline.mux_final_multiscene_video(
        master_video_path=str(source),
        output_path=str(output),
        subtitle_path=materials["subtitle_path"],
        burn_subtitles=True,
    )
    assert Path(rendered).stat().st_size > 0
    _run_media([ffmpeg, "-v", "error", "-i", rendered, "-f", "null", "-"])

    for at_seconds in (1.0, 4.0):
        frame = _run_media(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(at_seconds),
                "-i",
                rendered,
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ]
        )
        assert len(frame) == width * height * 3
        bright_x = _bright_x_positions(frame, width)
        assert bright_x
        edge_guard = max(2, int(round(width * 0.015)))
        assert min(bright_x) >= edge_guard
        assert max(bright_x) <= width - edge_guard - 1
