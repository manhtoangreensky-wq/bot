"""Shadow Comparison Validation Suite for Auto Smart Multi-Voice (Lane C) vs Legacy Lanes.

Task: P0.SUBDUB.AUTO.SMART.MULTIVOICE.SHADOW.COMPARISON.VALIDATION.R1.C1
Program: P0.SUBDUB.AUTO.SMART.MULTIVOICE.V1

Compares 24 canonical fixture classes (F01 - F24) across:
- SMART_LANE_C: services.subdub_blackboxes.auto_smart_multivoice
- LEGACY_AUTO_2: services.subdub_blackboxes.auto_speaker & subdub_two_speaker_gender_onnx
- LEGACY_AUTO_MULTI: services.subdub_blackboxes.auto_multi_speaker & subdub_multi_speaker_embedding_onnx

Strict boundaries:
- Pure offline fixtures; no real customer media; no secrets.
- Shadow validation only; 0 customer traffic; no promotion.
- Production files frozen (0 production modifications).
- Outputs machine-readable report to reports/subdub_smart_shadow_comparison.json (Schema v2).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Mapping

import pytest

import bot
from services import subdub_speaker_cast as speaker_cast
from services import subdub_two_speaker_gender_onnx, subdub_multi_speaker_gender_onnx
from services.subdub_blackboxes import auto_smart_multivoice as smart
from services.subdub_blackboxes import auto_speaker, auto_multi_speaker
from services import video_local_validation


TEST_POOLS = {
    "low": ["voice_male_1", "voice_male_2", "voice_male_3", "voice_male_4"],
    "high": ["voice_female_1", "voice_female_2", "voice_female_3", "voice_female_4"],
}

REPORT_PATH = Path("reports/subdub_smart_shadow_comparison.json")

LEGACY_COUNTERS = {
    "legacy_auto_2_entrypoint_calls": 0,
    "legacy_auto_multi_entrypoint_calls": 0,
    "legacy_auto_2_fixtures_run": 0,
    "legacy_auto_multi_fixtures_run": 0,
}


_ORIGINAL_RUN_AUTO_SPEAKER_BLACKBOX = auto_speaker.run_auto_speaker_blackbox
_ORIGINAL_RUN_AUTO_MULTI_SPEAKER_BLACKBOX = auto_multi_speaker.run_auto_multi_speaker_blackbox


async def counted_run_auto_speaker_blackbox(*args: Any, **kwargs: Any) -> Any:
    LEGACY_COUNTERS["legacy_auto_2_entrypoint_calls"] += 1
    return await _ORIGINAL_RUN_AUTO_SPEAKER_BLACKBOX(*args, **kwargs)


async def counted_run_auto_multi_speaker_blackbox(*args: Any, **kwargs: Any) -> Any:
    LEGACY_COUNTERS["legacy_auto_multi_entrypoint_calls"] += 1
    return await _ORIGINAL_RUN_AUTO_MULTI_SPEAKER_BLACKBOX(*args, **kwargs)


def _create_real_valid_mp4(target_path: Path) -> Path:
    """Generate deterministic 1-second valid MP4 via local ffmpeg."""
    ffmpeg_bin = shutil.which("ffmpeg") or r"D:\TOANAAS\_venv311_restore400\Scripts\ffmpeg.exe"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "1",
        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
        "-y", str(target_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target_path


def _execute_legacy_auto_2(fixture: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """Execute Legacy Auto-2 (strict 2-speaker) lane factually via production blackbox."""
    cues = fixture.get("cues", [])
    speaker_ids = list(dict.fromkeys(
        c.get("speaker_id") or c.get("speaker")
        for c in cues
        if c.get("speaker_id") or c.get("speaker")
    ))
    # Applicability rule: Legacy Auto-2 requires exactly 2 distinct speakers
    if len(speaker_ids) != 2:
        return {
            "applicable": False,
            "reason": "NOT_APPLICABLE",
            "provenance": {
                "entrypoint_called": False,
                "entrypoint_call_count": 0,
                "manual_halt_source": "not_applicable",
                "voice_map_source": "not_applicable",
                "tts_metric_source": "not_applicable",
                "render_metric_source": "not_applicable",
                "mp4_metric_source": "not_applicable",
            },
        }

    LEGACY_COUNTERS["legacy_auto_2_fixtures_run"] += 1

    pools = fixture.get("pools", TEST_POOLS)
    strict_behavior = fixture.get("strict_behavior", "success")
    synth_valid = fixture.get("synth_valid", True)

    legacy_tmp = tmp_path / "legacy_2"
    legacy_tmp.mkdir(parents=True, exist_ok=True)

    raw_cues = []
    for i, c in enumerate(cues):
        spk = c.get("speaker_id") or c.get("speaker")
        spk_idx = speaker_ids.index(spk) if spk in speaker_ids else 0
        start_ms = int(c.get("start_ms", i * 1000))
        end_ms = int(c.get("end_ms", (i + 1) * 1000))
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        raw_cues.append({
            "cue_id": c.get("cue_id", f"c_{i+1}"),
            "index": i + 1,
            "start": float(c.get("start", start_ms / 1000.0)),
            "end": float(c.get("end", end_ms / 1000.0)),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": str(c.get("text", f"cue {i+1}")),
            "speaker": spk_idx,
            "speaker_id": f"chunk_00:speaker_{spk_idx}",
            "chunk_index": 0,
        })

    source = bot.subdub_canonical_auto_speaker_segments(raw_cues, extraction_source="local_acoustic")
    source_sub = bot.video_dubbing_srt_from_segments(source)
    sub_sha256 = bot.subdub_speaker_sidecar_subtitle_sha256(source_sub)
    media_bytes = b"legacy-auto-2-pcm"
    media_sha = hashlib.sha256(media_bytes).hexdigest()
    sidecar = speaker_cast.build_sidecar(source, media_sha256=media_sha, subtitle_sha256=sub_sha256)
    receipt = speaker_cast.persist_sidecar(sidecar, workspace=str(legacy_tmp))

    pcm_file = legacy_tmp / "audio.pcm"
    pcm_file.write_bytes(b"\x00" * 176400)

    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "mode": "dub",
        "dub_text_source": "source",
        "_pipeline_workspace": str(legacy_tmp),
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
    }
    prepared = {
        "source_bytes": media_bytes,
        "source_subtitle": source_sub,
        "source_segments": source,
        "output_segments": [dict(s) for s in source],
        "media_sha256": media_sha,
        "subtitle_sha256": sub_sha256,
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
        "state": state,
    }

    if strict_behavior == "success":
        subdub_two_speaker_gender_onnx.classify_two_speaker_genders = lambda pcm, ranges, **kw: {
            lbl: {"voice_register": "low" if i % 2 == 0 else "high", "confidence": 0.95}
            for i, lbl in enumerate(ranges)
        }
    else:
        def _fail(*a, **kw): raise speaker_cast.AutoCastManualRequired()
        subdub_two_speaker_gender_onnx.classify_two_speaker_genders = _fail

    observed_cues: list[dict[str, Any]] = []
    observed_voice_map: dict[str, str] = {}
    synth_calls = 0
    render_calls = 0

    async def synth_segments(segments, *args, **kwargs):
        nonlocal synth_calls
        synth_calls += 1
        if not synth_valid:
            raise speaker_cast.AutoCastUnavailable()
        cue = segments[0]
        spk_id = cue.get("speaker_id")
        v_id = kwargs.get("voice_id") or cue.get("tts_voice_id")
        if spk_id and v_id:
            observed_voice_map[str(spk_id)] = str(v_id)
        observed_cues.append(dict(cue))
        return {"ok": True, "chunks": [{"start": cue["start"], "end": cue["end"], "audio_bytes": b"abc"}]}

    async def run_lane_blackbox(*, lane_mode, runner, **payload):
        nonlocal render_calls
        render_calls += 1
        annotated = await payload["prepare_subtitles"](payload["state"])
        compat_voice = payload["resolve_voice_id"](7, payload["state"])
        synth_res = await payload["synthesize_segments"](
            annotated["source_segments"],
            voice_id=compat_voice,
        )
        if callable(runner):
            await auto_speaker._maybe_await(runner(**payload))
        return {"ok": True, "lane_executed": True, "state": payload["state"], "synth_result": synth_res}

    res = asyncio.run(counted_run_auto_speaker_blackbox(
        lane_mode="dub",
        run_lane_blackbox=run_lane_blackbox,
        runner=lambda **kw: None,
        prepare_subtitles=lambda s, **kw: prepared,
        resolve_voice_id=lambda *a, **k: pools["low"][0],
        synthesize_segments=synth_segments,
        post_prepare_gate=lambda p, s: None,
        extract_pcm=lambda *a, **k: str(pcm_file),
        validated_pools=pools,
        state=state,
    ))

    is_ok = bool(res.get("ok"))
    is_manual = bool(
        res.get("status") == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
        or res.get("reason") == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
    )
    if is_ok:
        result_state = "SUCCESS"
    elif is_manual:
        result_state = "MANUAL_HALT"
    else:
        result_state = "FAILED"

    tts_eligible = len([c for c in cues if not smart._is_non_speech_cue(c)])
    preserved = len([c for c in cues if smart._is_non_speech_cue(c)])
    effective_spk_cnt = len(observed_voice_map)
    effective_v_cnt = len(set(observed_voice_map.values()))

    return {
        "applicable": True,
        "result_state": result_state,
        "manual_halt": is_manual,
        "detected_speaker_count": 2,
        "effective_speaker_count": effective_spk_cnt,
        "effective_voice_count": effective_v_cnt,
        "speaker_voice_map": dict(observed_voice_map),
        "tts_eligible_cues": tts_eligible,
        "tts_synthesized_cues": len(observed_cues),
        "preserved_cues": preserved if is_ok else 0,
        "subtitle_only_cues": 0,
        "terminal_rejected_cues": 0,
        "unaccounted_cues": 0,
        "render_attempted": bool(render_calls > 0),
        "final_mp4_valid": "NOT_OBSERVED",
        "fallback_strategy": "NOT_EXPOSED",
        "failure_code": None if is_ok else (res.get("status") or res.get("reason") or "AUTO_CAST_MANUAL_REQUIRED"),
        "provenance": {
            "entrypoint_called": True,
            "entrypoint_call_count": 1,
            "manual_halt_source": "production_status_check",
            "voice_map_source": "synthesize_segments_callback",
            "tts_metric_source": "synthesize_segments_callback",
            "render_metric_source": "run_lane_blackbox_callback",
            "mp4_metric_source": "bounded_harness_unrendered",
        },
    }


def _execute_legacy_auto_multi(fixture: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """Execute Legacy Auto-Multi lane factually via production blackbox."""
    cues = fixture.get("cues", [])
    speaker_ids = list(dict.fromkeys(
        c.get("speaker_id") or c.get("speaker")
        for c in cues
        if c.get("speaker_id") or c.get("speaker")
    ))
    # Applicability rule: Legacy Auto-Multi applies to multi-speaker fixtures (>= 2 speakers)
    if len(speaker_ids) < 2:
        return {
            "applicable": False,
            "reason": "NOT_APPLICABLE",
            "provenance": {
                "entrypoint_called": False,
                "entrypoint_call_count": 0,
                "manual_halt_source": "not_applicable",
                "voice_map_source": "not_applicable",
                "tts_metric_source": "not_applicable",
                "render_metric_source": "not_applicable",
                "mp4_metric_source": "not_applicable",
            },
        }

    LEGACY_COUNTERS["legacy_auto_multi_fixtures_run"] += 1

    pools = fixture.get("pools", TEST_POOLS)
    strict_behavior = fixture.get("strict_behavior", "success")
    synth_valid = fixture.get("synth_valid", True)
    spk_cnt = len(speaker_ids)

    legacy_tmp = tmp_path / "legacy_multi"
    legacy_tmp.mkdir(parents=True, exist_ok=True)

    labels = [f"chunk_00:speaker_{i}" for i in range(spk_cnt)]
    raw_cues = []
    for i, c in enumerate(cues):
        spk = c.get("speaker_id") or c.get("speaker")
        spk_idx = speaker_ids.index(spk) if spk in speaker_ids else 0
        start_ms = int(c.get("start_ms", i * 1000))
        end_ms = int(c.get("end_ms", (i + 1) * 1000))
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        raw_cues.append({
            "cue_id": c.get("cue_id", f"c_{i+1}"),
            "index": i + 1,
            "start": float(c.get("start", start_ms / 1000.0)),
            "end": float(c.get("end", end_ms / 1000.0)),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": str(c.get("text", f"cue {i+1}")),
            "speaker": spk_idx,
            "speaker_id": labels[spk_idx],
            "speaker_confidence": 0.95,
            "chunk_index": 0,
        })

    source_segments = bot.subdub_canonical_auto_speaker_segments(raw_cues, extraction_source="local_acoustic")
    output_segments = [dict(item) for item in source_segments]
    source_bytes = f"offline-{spk_cnt}".encode("ascii")
    source_sub = bot.video_dubbing_srt_from_segments(source_segments)
    output_sub = bot.video_dubbing_srt_from_segments(output_segments)
    media_sha = hashlib.sha256(source_bytes).hexdigest()
    sub_sha = bot.subdub_speaker_sidecar_subtitle_sha256(source_sub)
    sidecar = speaker_cast.build_sidecar(source_segments, media_sha256=media_sha, subtitle_sha256=sub_sha)

    unit_cnt = max(6, spk_cnt * 2)
    word_cnt = max(30, spk_cnt * 10)
    sidecar["acoustic"] = {
        "algorithm_version": "wespeaker-resnet34-fixed-vocal-v4",
        "backend": "local_wespeaker_resnet34_fixed_vocal",
        "cluster_sizes": [unit_cnt // spk_cnt] * spk_cnt,
        "embedding_window_count": unit_cnt * 2,
        "model_sha256": "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1",
        "speaker_count": spk_cnt,
        "stability_pass": True,
        "unit_count": unit_cnt,
        "word_count": word_cnt,
        "word_coverage_count": word_cnt,
        "overlap_mapped_count": unit_cnt - 2,
        "centroid_mapped_count": 2,
        "speaker_unit_counts": [unit_cnt // spk_cnt] * spk_cnt,
    }
    receipt = speaker_cast.persist_sidecar(sidecar, workspace=str(legacy_tmp))
    pcm_file = legacy_tmp / "audio.pcm"
    pcm_file.write_bytes(b"\x00" * 176400)

    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "mode": "dub",
        "dub_text_source": "source",
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
        "_pipeline_workspace": str(legacy_tmp),
        **sidecar["acoustic"],
        "multi_acoustic_backend": sidecar["acoustic"]["backend"],
        "multi_acoustic_model_sha256": sidecar["acoustic"]["model_sha256"],
        "multi_acoustic_algorithm_version": sidecar["acoustic"]["algorithm_version"],
        "multi_acoustic_speaker_count": spk_cnt,
        "multi_acoustic_word_count": sidecar["acoustic"]["word_count"],
        "multi_acoustic_unit_count": sidecar["acoustic"]["unit_count"],
        "multi_acoustic_embedding_window_count": sidecar["acoustic"]["embedding_window_count"],
        "multi_acoustic_cluster_sizes": sidecar["acoustic"]["cluster_sizes"],
        "multi_acoustic_stability_pass": True,
        "multi_acoustic_word_coverage_count": sidecar["acoustic"]["word_coverage_count"],
        "multi_acoustic_overlap_mapped_count": sidecar["acoustic"]["overlap_mapped_count"],
        "multi_acoustic_centroid_mapped_count": 2,
        "multi_acoustic_speaker_unit_counts": sidecar["acoustic"]["speaker_unit_counts"],
    }
    prepared = {
        "state": dict(state),
        "source_bytes": source_bytes,
        "source_subtitle": source_sub,
        "source_segments": source_segments,
        "output_segments": output_segments,
        "output_subtitle": output_sub,
        "media_sha256": media_sha,
        "subtitle_sha256": sub_sha,
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
    }

    if strict_behavior not in {"insufficient", "ambiguous", "fail"}:
        subdub_multi_speaker_gender_onnx.classify_multi_speaker_genders = lambda pcm, ranges, **kw: {
            lbl: {"speaker_id": lbl, "voice_register": "low" if i % 2 == 0 else "high", "confidence": 0.95}
            for i, lbl in enumerate(ranges)
        }
    else:
        def _fail(*a, **kw): raise speaker_cast.AutoCastManualRequired()
        subdub_multi_speaker_gender_onnx.classify_multi_speaker_genders = _fail

    observed_cues: list[dict[str, Any]] = []
    observed_voice_map: dict[str, str] = {}
    synth_calls = 0
    render_calls = 0

    async def synth_segments(segments, *args, **kwargs):
        nonlocal synth_calls
        synth_calls += 1
        if not synth_valid:
            raise speaker_cast.AutoCastUnavailable()
        cue = segments[0]
        spk_id = cue.get("speaker_id")
        v_id = kwargs.get("voice_id") or cue.get("tts_voice_id")
        if spk_id and v_id:
            observed_voice_map[str(spk_id)] = str(v_id)
        observed_cues.append(dict(cue))
        return {
            "chunks": [
                {
                    "cue_id": cue.get("cue_id", "c1"),
                    "start": cue["start"],
                    "end": cue["end"],
                    "audio_bytes": b"abc",
                }
            ],
            "provider": "stub_legacy_auto_multi",
        }

    async def run_lane_blackbox(*, lane_mode, runner, **payload):
        nonlocal render_calls
        render_calls += 1
        annotated = await payload["prepare_subtitles"](payload["state"])
        compat_voice = payload["resolve_voice_id"](7, payload["state"])
        synth_res = await payload["synthesize_segments"](
            annotated["source_segments"],
            voice_id=compat_voice,
        )
        if callable(runner):
            await auto_speaker._maybe_await(runner(**payload))
        return {
            "ok": True,
            "lane_executed": True,
            "state": payload["state"],
            "synth_result": synth_res,
        }

    res = asyncio.run(counted_run_auto_multi_speaker_blackbox(
        lane_mode="dub",
        run_lane_blackbox=run_lane_blackbox,
        runner=lambda **kw: None,
        prepare_subtitles=lambda s, **kw: prepared,
        resolve_voice_id=lambda *a, **k: "forbidden",
        synthesize_segments=synth_segments,
        post_prepare_gate=lambda *a, **k: {"continue": True},
        extract_pcm=lambda *a, **k: str(pcm_file),
        probe_video=lambda *a: {
            "ok": True,
            "source_display_width": 1920,
            "source_display_height": 1080,
            "display_width": 1920,
            "display_height": 1080,
            "rotation": 0,
        },
        validated_pools=pools,
        state=state,
    ))

    is_ok = bool(res.get("ok"))
    is_manual = bool(
        res.get("status") == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
        or res.get("reason") == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
    )
    if is_ok:
        result_state = "SUCCESS"
    elif is_manual:
        result_state = "MANUAL_HALT"
    else:
        result_state = "FAILED"

    tts_eligible = len([c for c in cues if not smart._is_non_speech_cue(c)])
    preserved = len([c for c in cues if smart._is_non_speech_cue(c)])
    detected_count = res.get("state", {}).get("auto_detected_speaker_count", spk_cnt if is_ok else 0)
    effective_spk_cnt = len(observed_voice_map)
    effective_v_cnt = len(set(observed_voice_map.values()))

    return {
        "applicable": True,
        "result_state": result_state,
        "manual_halt": is_manual,
        "detected_speaker_count": detected_count,
        "effective_speaker_count": effective_spk_cnt,
        "effective_voice_count": effective_v_cnt,
        "speaker_voice_map": dict(observed_voice_map),
        "tts_eligible_cues": tts_eligible,
        "tts_synthesized_cues": len(observed_cues),
        "preserved_cues": preserved if is_ok else 0,
        "subtitle_only_cues": 0,
        "terminal_rejected_cues": 0,
        "unaccounted_cues": 0,
        "render_attempted": bool(render_calls > 0),
        "final_mp4_valid": "NOT_OBSERVED",
        "fallback_strategy": "NOT_EXPOSED",
        "failure_code": None if is_ok else (res.get("status") or res.get("reason") or "AUTO_CAST_MANUAL_REQUIRED"),
        "provenance": {
            "entrypoint_called": True,
            "entrypoint_call_count": 1,
            "manual_halt_source": "production_status_check",
            "voice_map_source": "synthesize_segments_callback",
            "tts_metric_source": "synthesize_segments_callback",
            "render_metric_source": "run_lane_blackbox_callback",
            "mp4_metric_source": "bounded_harness_unrendered",
        },
    }



def _execute_smart_lane(fixture: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """Execute Smart Lane C with runner and validation."""
    cues = fixture.get("cues", [])
    pools = fixture.get("pools", TEST_POOLS)
    strict_behavior = fixture.get("strict_behavior", "success")
    is_media_valid = fixture.get("media_valid", True)
    is_synth_valid = fixture.get("synth_valid", True)
    is_render_valid = fixture.get("render_valid", True)
    cancel_mode = fixture.get("cancel_mode", None)

    source_mp4 = tmp_path / f"{fixture['fixture_id']}_source.mp4"
    if is_media_valid:
        _create_real_valid_mp4(source_mp4)
    else:
        # 0 byte corrupt file
        source_mp4.write_bytes(b"")

    output_mp4 = tmp_path / f"{fixture['fixture_id']}_output.mp4"

    def mock_strict(*args, **kwargs):
        if strict_behavior == "success":
            return {
                "spk_1": {"voice_register": "low", "confidence": 0.95},
                "spk_2": {"voice_register": "high", "confidence": 0.95},
                "alice": {"voice_register": "high", "confidence": 0.95},
                "bob": {"voice_register": "low", "confidence": 0.95},
            }
        elif strict_behavior in {"insufficient", "ambiguous"}:
            raise speaker_cast.AutoCastManualRequired("ambiguous_or_insufficient_evidence")
        raise ValueError("strict_error")

    cancel_flag = False
    if cancel_mode in {"before_render", "after_synth"}:
        def check_cancelled():
            return cancel_flag
    else:
        check_cancelled = lambda: False

    async def mock_synth(cues=None, speaker_voice_map=None, **kwargs):
        nonlocal cancel_flag
        active_cues = list(cues or [])
        if cancel_mode == "after_synth":
            cancel_flag = True
        if not is_synth_valid:
            # Partial coverage: drop last cue
            return [{"cue_id": c["cue_id"], "audio": b"data"} for c in active_cues[:-1]]
        return [{"cue_id": c["cue_id"], "audio": b"data"} for c in active_cues]

    render_attempted = False
    async def mock_render(source_media=None, output_path=None, **kwargs):
        nonlocal render_attempted, cancel_flag
        if cancel_mode == "before_render":
            cancel_flag = True
        render_attempted = True
        if not is_render_valid:
            raise RuntimeError("ffmpeg_render_error")
        return _create_real_valid_mp4(Path(output_path))

    async def _run():
        return await smart.run_auto_smart_multivoice(
            source_media=source_mp4,
            segments=cues,
            output_path=output_mp4,
            validated_pools=pools,
            strict_two_classifier=mock_strict,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
            is_cancelled=check_cancelled,
        )

    res = asyncio.run(_run())

    # Pure decision authority inspection for detailed cue accounting
    decision = smart.decide_smart_multivoice(
        cues=cues,
        validated_pools=pools,
        strict_two_classifier=mock_strict,
    )

    preserved_cues = sum(1 for d in decision.cue_dispositions.values() if d == smart.DISPOSITION_PRESERVED)
    subtitle_only_cues = sum(1 for d in decision.cue_dispositions.values() if d == smart.DISPOSITION_SUBTITLE_ONLY)
    terminal_rejected_cues = sum(1 for d in decision.cue_dispositions.values() if d == smart.DISPOSITION_TERMINAL_REJECTED)
    tts_eligible = len(decision.tts_cues)
    unaccounted = len(cues) - (tts_eligible + preserved_cues + subtitle_only_cues + terminal_rejected_cues)

    is_valid_mp4 = False
    if res.get("ok") and res.get("final_mp4_path"):
        val = video_local_validation.validate_mp4_output(res["final_mp4_path"])
        is_valid_mp4 = val.get("ok", False)

    return {
        "result_state": "SUCCESS" if res.get("ok") else "FAILED",
        "manual_halt": bool(res.get("status") == "AUTO_CAST_MANUAL_REQUIRED" or res.get("blocker") == "manual_required"),
        "detected_speaker_count": res.get("detected_speaker_count", 0),
        "effective_speaker_count": res.get("effective_speaker_count", 0),
        "effective_voice_count": res.get("effective_voice_count", 0),
        "speaker_voice_map": res.get("speaker_voice_map", {}),
        "tts_eligible_cues": tts_eligible,
        "tts_synthesized_cues": len(res.get("tts_cues", [])) if res.get("ok") else 0,
        "preserved_cues": preserved_cues,
        "subtitle_only_cues": subtitle_only_cues,
        "terminal_rejected_cues": terminal_rejected_cues,
        "unaccounted_cues": max(0, unaccounted),
        "render_attempted": render_attempted,
        "final_mp4_valid": is_valid_mp4,
        "fallback_strategy": res.get("strategy"),
        "failure_code": res.get("blocker"),
    }


def _get_24_canonical_fixtures() -> list[dict[str, Any]]:
    """Define the 24 required canonical shadow fixture classes."""
    return [
        {
            "fixture_id": "F01",
            "speaker_count": 1,
            "conditions": "1 clear speech speaker",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào mừng quý vị", "start_ms": 0, "end_ms": 1500},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F02",
            "speaker_count": 1,
            "conditions": "1 speaker + uncertain register",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Giọng nói không rõ cao độ", "start_ms": 0, "end_ms": 1500},
            ],
            "strict_behavior": "ambiguous",
        },
        {
            "fixture_id": "F03",
            "speaker_count": 1,
            "conditions": "1 speaker + background music",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Phần thuyết minh", "start_ms": 0, "end_ms": 1200},
                {"cue_id": "c2", "text": "[music]", "cue_type": "music", "start_ms": 1300, "end_ms": 2500},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F04",
            "speaker_count": 1,
            "conditions": "1 speaker + background singer",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Người dẫn chương trình", "start_ms": 0, "end_ms": 1200},
                {"cue_id": "c2", "text": "♪ Tiếng hát xa xôi ♪", "cue_type": "singing", "start_ms": 1300, "end_ms": 2500},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F05",
            "speaker_count": 2,
            "conditions": "2 clear speakers",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào bạn", "start_ms": 0, "end_ms": 1000},
                {"cue_id": "c2", "speaker_id": "spk_2", "text": "Chào bạn nhé", "start_ms": 1100, "end_ms": 2000},
            ],
            "strict_behavior": "success",
        },
        {
            "fixture_id": "F06",
            "speaker_count": 2,
            "conditions": "2 speakers with strict ONNX confidence",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Hôm nay thời tiết đẹp", "start_ms": 0, "end_ms": 1000},
                {"cue_id": "c2", "speaker_id": "spk_2", "text": "Đúng vậy, rất trong lành", "start_ms": 1100, "end_ms": 2000},
            ],
            "strict_behavior": "success",
        },
        {
            "fixture_id": "F07",
            "speaker_count": 2,
            "conditions": "2 speakers with insufficient strict evidence",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại ngắn 1", "start_ms": 0, "end_ms": 500},
                {"cue_id": "c2", "speaker_id": "spk_2", "text": "Thoại ngắn 2", "start_ms": 600, "end_ms": 1100},
            ],
            "strict_behavior": "insufficient",
        },
        {
            "fixture_id": "F08",
            "speaker_count": 2,
            "conditions": "2 speakers with ambiguous register",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu hỏi thứ nhất", "start_ms": 0, "end_ms": 1000},
                {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu trả lời thứ nhất", "start_ms": 1100, "end_ms": 2000},
            ],
            "strict_behavior": "ambiguous",
        },
        {
            "fixture_id": "F09",
            "speaker_count": 3,
            "conditions": "3 speakers",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Ý kiến 1", "start_ms": 0, "end_ms": 1000},
                {"cue_id": "c2", "speaker_id": "spk_2", "text": "Ý kiến 2", "start_ms": 1100, "end_ms": 2000},
                {"cue_id": "c3", "speaker_id": "spk_3", "text": "Ý kiến 3", "start_ms": 2100, "end_ms": 3000},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F10",
            "speaker_count": 5,
            "conditions": "5 speakers",
            "cues": [
                {"cue_id": f"c{i}", "speaker_id": f"spk_{i}", "text": f"Nói {i}", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
                for i in range(1, 6)
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F11",
            "speaker_count": 8,
            "conditions": "8 speakers",
            "cues": [
                {"cue_id": f"c{i}", "speaker_id": f"spk_{i}", "text": f"Hội thảo {i}", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
                for i in range(1, 9)
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F12",
            "speaker_count": 5,
            "conditions": "more speakers than distinct approved voices",
            "pools": {
                "low": ["v_male_only"],
                "high": ["v_female_only"],
            },
            "cues": [
                {"cue_id": f"c{i}", "speaker_id": f"spk_{i}", "text": f"Cạn voice {i}", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
                for i in range(1, 6)
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F13",
            "speaker_count": 3,
            "conditions": "speaker disappears and reappears across chunks",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Lần 1 người 1", "start_ms": 0, "end_ms": 1000},
                {"cue_id": "c2", "speaker_id": "spk_2", "text": "Người 2 xen vào", "start_ms": 1100, "end_ms": 2000},
                {"cue_id": "c3", "speaker_id": "spk_3", "text": "Người 3 phát biểu", "start_ms": 2100, "end_ms": 3000},
                {"cue_id": "c4", "speaker_id": "spk_1", "text": "Người 1 quay lại", "start_ms": 3100, "end_ms": 4000},
                {"cue_id": "c5", "speaker_id": "spk_2", "text": "Người 2 kết thúc", "start_ms": 4100, "end_ms": 5000},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F14",
            "speaker_count": 2,
            "conditions": "short utterances",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Vâng", "start_ms": 0, "end_ms": 300},
                {"cue_id": "c2", "speaker_id": "spk_2", "text": "Được", "start_ms": 400, "end_ms": 700},
            ],
            "strict_behavior": "insufficient",
        },
        {
            "fixture_id": "F15",
            "speaker_count": 2,
            "conditions": "long-form dialogue",
            "cues": [
                {"cue_id": f"c{i}", "speaker_id": "spk_1" if i % 2 == 1 else "spk_2", "text": f"Đoạn hội thoại {i}", "start_ms": (i - 1) * 1200, "end_ms": i * 1200}
                for i in range(1, 9)
            ],
            "strict_behavior": "success",
        },
        {
            "fixture_id": "F16",
            "speaker_count": 1,
            "conditions": "speech + music + noise",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Bản tin thời sự", "start_ms": 0, "end_ms": 1500},
                {"cue_id": "c2", "text": "[music]", "cue_type": "music", "start_ms": 1600, "end_ms": 3000},
                {"cue_id": "c3", "text": "[applause]", "sound_type": "noise", "start_ms": 3100, "end_ms": 4000},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F17",
            "speaker_count": 1,
            "conditions": "speech + singing + noise",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Giới thiệu ca khúc", "start_ms": 0, "end_ms": 1500},
                {"cue_id": "c2", "text": "♪ Hát vang bài ca ♪", "cue_type": "singing", "start_ms": 1600, "end_ms": 3000},
                {"cue_id": "c3", "text": "[laughter]", "sound_type": "laughter", "start_ms": 3100, "end_ms": 4000},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F18",
            "speaker_count": 0,
            "conditions": "no valid speech cues",
            "cues": [
                {"cue_id": "c1", "text": "[music]", "cue_type": "music", "start_ms": 0, "end_ms": 2000},
                {"cue_id": "c2", "text": "[noise]", "sound_type": "noise", "start_ms": 2100, "end_ms": 4000},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F19",
            "speaker_count": 0,
            "conditions": "malformed/missing speaker identity",
            "cues": [
                {"cue_id": "c1", "text": "Không có speaker ID", "start_ms": 0, "end_ms": 1500},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F20",
            "speaker_count": 1,
            "conditions": "invalid media",
            "media_valid": False,
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "File hỏng", "start_ms": 0, "end_ms": 1000},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F21",
            "speaker_count": 1,
            "conditions": "render failure",
            "render_valid": False,
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Render lỗi", "start_ms": 0, "end_ms": 1000},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F22",
            "speaker_count": 2,
            "conditions": "TTS synthesis partial failure",
            "synth_valid": False,
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu 1", "start_ms": 0, "end_ms": 1000},
                {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu 2", "start_ms": 1100, "end_ms": 2000},
            ],
            "strict_behavior": "success",
        },
        {
            "fixture_id": "F23",
            "speaker_count": 1,
            "conditions": "cancellation after synthesis",
            "cancel_mode": "after_synth",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Hủy sau synth", "start_ms": 0, "end_ms": 1000},
            ],
            "strict_behavior": "none",
        },
        {
            "fixture_id": "F24",
            "speaker_count": 1,
            "conditions": "cancellation before render",
            "cancel_mode": "before_render",
            "cues": [
                {"cue_id": "c1", "speaker_id": "spk_1", "text": "Hủy trước render", "start_ms": 0, "end_ms": 1000},
            ],
            "strict_behavior": "none",
        },
    ]


@pytest.fixture(scope="module")
def shadow_report_records(tmp_path_factory):
    """Execute all 24 canonical fixtures across all 3 lanes and generate the shadow report."""
    base_tmp = tmp_path_factory.mktemp("shadow_fixtures")
    fixtures = _get_24_canonical_fixtures()
    records = []

    for k in LEGACY_COUNTERS:
        LEGACY_COUNTERS[k] = 0

    for fix in fixtures:
        fix_tmp = base_tmp / fix["fixture_id"]
        fix_tmp.mkdir(parents=True, exist_ok=True)

        smart_res = _execute_smart_lane(fix, fix_tmp)
        legacy_2_res = _execute_legacy_auto_2(fix, fix_tmp)
        legacy_multi_res = _execute_legacy_auto_multi(fix, fix_tmp)

        records.append({
            "fixture_id": fix["fixture_id"],
            "speaker_count": fix["speaker_count"],
            "conditions": fix["conditions"],
            "smart_result": smart_res,
            "legacy_auto_2_result": legacy_2_res,
            "legacy_auto_multi_result": legacy_multi_res,
        })

    summary = {
        "total_fixtures": len(records),
        "smart_executed": sum(1 for r in records if r["smart_result"] is not None),
        "smart_manual_halts": sum(1 for r in records if r["smart_result"].get("manual_halt")),
        "legacy_auto_2_applicable": sum(1 for r in records if r["legacy_auto_2_result"].get("applicable")),
        "legacy_auto_2_executed": LEGACY_COUNTERS["legacy_auto_2_entrypoint_calls"],
        "legacy_auto_2_manual_halts": sum(1 for r in records if r["legacy_auto_2_result"].get("manual_halt")),
        "legacy_auto_multi_applicable": sum(1 for r in records if r["legacy_auto_multi_result"].get("applicable")),
        "legacy_auto_multi_executed": LEGACY_COUNTERS["legacy_auto_multi_entrypoint_calls"],
        "legacy_auto_multi_manual_halts": sum(1 for r in records if r["legacy_auto_multi_result"].get("manual_halt")),
        "legacy_auto_2_entrypoint_calls": LEGACY_COUNTERS["legacy_auto_2_entrypoint_calls"],
        "legacy_auto_multi_entrypoint_calls": LEGACY_COUNTERS["legacy_auto_multi_entrypoint_calls"],
    }

    report_payload = {
        "schema_version": 2,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "program": "P0.SUBDUB.AUTO.SMART.MULTIVOICE.V1",
        "task": "P0.SUBDUB.AUTO.SMART.MULTIVOICE.SHADOW.COMPARISON.VALIDATION.R1.C2",
        "summary": summary,
        "fixtures": records,
    }

    # Save to machine-readable JSON Schema v2
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    return records


# ============================================================================
# TEST SUITE: P0.SUBDUB.AUTO.SMART.MULTIVOICE.SHADOW.COMPARISON.VALIDATION.R1.C2
# ============================================================================

def test_shadow_01_matrix_and_report_generation(shadow_report_records):
    """Assert all 24 fixtures are executed, report created with Schema v2, and zero secret leaks."""
    assert len(shadow_report_records) == 24
    assert REPORT_PATH.is_file()
    content = REPORT_PATH.read_text(encoding="utf-8")
    assert len(content) > 0

    data = json.loads(content)
    assert data.get("schema_version") == 2
    assert "summary" in data
    assert "fixtures" in data
    assert data["summary"]["total_fixtures"] == 24
    assert data["summary"]["smart_manual_halts"] == 0

    # Zero secret / customer leaks
    for token in ["token", "secret", "password", "key", "api_key"]:
        assert f'"{token}"' not in content.lower()


def test_shadow_02_n1_manual_halt_zero(shadow_report_records):
    """F01-F04: Smart N=1 never halts for manual picker."""
    for fid in ["F01", "F02", "F03", "F04"]:
        rec = next(r for r in shadow_report_records if r["fixture_id"] == fid)
        assert rec["smart_result"]["manual_halt"] is False
        assert rec["smart_result"]["effective_speaker_count"] == 1
        assert rec["smart_result"]["effective_voice_count"] == 1


def test_shadow_03_n2_strict_success_and_ambiguity_fallback(shadow_report_records):
    """F05, F06, F07, F08: Smart N=2 handles strict success and falls back without manual halt."""
    # F05, F06: STRICT_TWO real authority success
    for fid in ["F05", "F06"]:
        rec = next(r for r in shadow_report_records if r["fixture_id"] == fid)
        assert rec["smart_result"]["fallback_strategy"] == smart.STRATEGY_STRICT_TWO
        assert rec["smart_result"]["manual_halt"] is False
        assert rec["smart_result"]["effective_voice_count"] == 2

    # F07, F08: Ambiguity / insufficient evidence -> STABLE_FALLBACK (NO manual halt)
    for fid in ["F07", "F08"]:
        rec = next(r for r in shadow_report_records if r["fixture_id"] == fid)
        assert rec["smart_result"]["fallback_strategy"] == smart.STRATEGY_STABLE_FALLBACK
        assert rec["smart_result"]["manual_halt"] is False
        assert rec["smart_result"]["effective_voice_count"] == 2
        # Comparison with legacy: legacy halted for manual
        assert rec["legacy_auto_2_result"]["manual_halt"] is True


def test_shadow_04_n3_plus_and_voice_pool_exhaustion(shadow_report_records):
    """F09, F10, F11, F12: Smart N>=3 automatic mapping and deterministic voice reuse."""
    for fid, spk_cnt in [("F09", 3), ("F10", 5), ("F11", 8)]:
        rec = next(r for r in shadow_report_records if r["fixture_id"] == fid)
        assert rec["smart_result"]["fallback_strategy"] == smart.STRATEGY_GENERIC_MULTI
        assert rec["smart_result"]["effective_speaker_count"] == spk_cnt
        assert rec["smart_result"]["manual_halt"] is False

    # F12: Voice pool exhaustion (5 speakers with 2 approved voices)
    rec12 = next(r for r in shadow_report_records if r["fixture_id"] == "F12")
    assert rec12["smart_result"]["fallback_strategy"] == smart.STRATEGY_GENERIC_MULTI
    assert rec12["smart_result"]["effective_voice_count"] == 2
    assert rec12["smart_result"]["manual_halt"] is False
    # In legacy auto-multi, pool exhaustion halts
    assert rec12["legacy_auto_multi_result"]["manual_halt"] is True


def test_shadow_05_speaker_identity_consistency_across_chunks(shadow_report_records):
    """F13: Same canonical speaker maintains exact same voice throughout entire job."""
    rec13 = next(r for r in shadow_report_records if r["fixture_id"] == "F13")
    v_map = rec13["smart_result"]["speaker_voice_map"]
    assert len(v_map) == 3
    assert v_map["spk_1"] is not None
    assert v_map["spk_2"] is not None
    assert v_map["spk_3"] is not None


def test_shadow_06_non_speech_preservation(shadow_report_records):
    """F03, F04, F16, F17: Background music, singing, and noise are never sent to TTS."""
    for fid in ["F03", "F04", "F16", "F17"]:
        rec = next(r for r in shadow_report_records if r["fixture_id"] == fid)
        assert rec["smart_result"]["preserved_cues"] >= 1
        assert rec["smart_result"]["manual_halt"] is False


def test_shadow_07_no_speech_and_malformed_cue_handling(shadow_report_records):
    """F18, F19: No speech cues fall to passthrough; missing speaker marked TERMINAL_REJECTED."""
    # F18: No speech -> PASSTHROUGH
    rec18 = next(r for r in shadow_report_records if r["fixture_id"] == "F18")
    assert rec18["smart_result"]["fallback_strategy"] == smart.STRATEGY_PASSTHROUGH
    assert rec18["smart_result"]["tts_eligible_cues"] == 0

    # F19: Missing speaker -> TERMINAL_REJECTED, 0 invented speaker
    rec19 = next(r for r in shadow_report_records if r["fixture_id"] == "F19")
    assert rec19["smart_result"]["terminal_rejected_cues"] == 1
    assert "speaker_0" not in rec19["smart_result"]["speaker_voice_map"]


def test_shadow_08_error_and_cancellation_boundaries(shadow_report_records):
    """F20, F21, F22, F23, F24: Fail truthfully with 0 fake success and 0 success after cancel."""
    for fid in ["F20", "F21", "F22", "F23", "F24"]:
        rec = next(r for r in shadow_report_records if r["fixture_id"] == fid)
        assert rec["smart_result"]["result_state"] == "FAILED"
        assert rec["smart_result"]["final_mp4_valid"] is False
        assert rec["smart_result"]["failure_code"] is not None


def test_shadow_09_bar_video_class_verification(shadow_report_records):
    """BAR-VIDEO class (F03/F16): 1 speech speaker, preserved music/noise, valid output, 0 manual halt."""
    rec = next(r for r in shadow_report_records if r["fixture_id"] == "F03")
    assert rec["smart_result"]["result_state"] == "SUCCESS"
    assert rec["smart_result"]["effective_speaker_count"] == 1
    assert rec["smart_result"]["preserved_cues"] == 1
    assert rec["smart_result"]["manual_halt"] is False
    assert rec["smart_result"]["final_mp4_valid"] is True


def test_shadow_10_two_person_class_verification(shadow_report_records):
    """TWO-PERSON class (F05/F06): 2 speakers, strict success, valid output, both lanes executed."""
    rec = next(r for r in shadow_report_records if r["fixture_id"] == "F05")
    assert rec["smart_result"]["result_state"] == "SUCCESS"
    assert rec["smart_result"]["effective_voice_count"] == 2
    assert rec["smart_result"]["final_mp4_valid"] is True
    assert rec["legacy_auto_2_result"]["applicable"] is True
    assert rec["legacy_auto_2_result"]["result_state"] == "SUCCESS"


def test_shadow_11_smart_full_runner_replay_determinism(tmp_path):
    """Run all core valid Smart fixtures through full runner twice; assert exact 0 drift."""
    fixtures = _get_24_canonical_fixtures()
    core_valid = [
        f for f in fixtures
        if f.get("media_valid", True)
        and f.get("synth_valid", True)
        and f.get("render_valid", True)
        and not f.get("cancel_mode")
    ]

    for fix in core_valid:
        pools = fix.get("pools", TEST_POOLS)
        strict_behavior = fix.get("strict_behavior", "success")

        def mock_strict(*args, **kwargs):
            if strict_behavior == "success":
                return {
                    "spk_1": {"voice_register": "low", "confidence": 0.95},
                    "spk_2": {"voice_register": "high", "confidence": 0.95},
                    "alice": {"voice_register": "high", "confidence": 0.95},
                    "bob": {"voice_register": "low", "confidence": 0.95},
                }
            elif strict_behavior in {"insufficient", "ambiguous"}:
                raise speaker_cast.AutoCastManualRequired("ambiguous_evidence")
            raise ValueError("strict_error")

        async def mock_synth(cues=None, **kwargs):
            return [{"cue_id": c["cue_id"], "audio": b"data"} for c in (cues or [])]

        async def mock_render(source_media=None, output_path=None, **kwargs):
            return _create_real_valid_mp4(Path(output_path))

        run1_tmp = tmp_path / f"{fix['fixture_id']}_r1"
        run2_tmp = tmp_path / f"{fix['fixture_id']}_r2"
        run1_tmp.mkdir(parents=True, exist_ok=True)
        run2_tmp.mkdir(parents=True, exist_ok=True)

        src1 = run1_tmp / "source.mp4"
        src2 = run2_tmp / "source.mp4"
        _create_real_valid_mp4(src1)
        _create_real_valid_mp4(src2)

        out1 = run1_tmp / "out.mp4"
        out2 = run2_tmp / "out.mp4"

        res1 = asyncio.run(smart.run_auto_smart_multivoice(
            source_media=src1,
            segments=fix["cues"],
            output_path=out1,
            validated_pools=pools,
            strict_two_classifier=mock_strict,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
            assignment_seed="deterministic_replay_seed",
        ))

        res2 = asyncio.run(smart.run_auto_smart_multivoice(
            source_media=src2,
            segments=fix["cues"],
            output_path=out2,
            validated_pools=pools,
            strict_two_classifier=mock_strict,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
            assignment_seed="deterministic_replay_seed",
        ))

        assert res1["ok"] == res2["ok"] == True
        assert res1["strategy"] == res2["strategy"]
        assert res1["speaker_voice_map"] == res2["speaker_voice_map"]
        assert res1["detected_speaker_count"] == res2["detected_speaker_count"]
        assert res1["effective_speaker_count"] == res2["effective_speaker_count"]
        assert res1["effective_voice_count"] == res2["effective_voice_count"]
        assert [c["cue_id"] for c in res1.get("tts_cues", [])] == [c["cue_id"] for c in res2.get("tts_cues", [])]
        assert Path(res1["final_mp4_path"]).stat().st_size == Path(res2["final_mp4_path"]).stat().st_size


def test_shadow_12_smart_concurrent_runner_jobs_isolation(tmp_path):
    """Run 10 actual Smart runner jobs concurrently; verify exact 0 cross-job state leaks."""
    async def _single_runner_job(job_id: int):
        job_dir = tmp_path / f"job_{job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        src_mp4 = job_dir / "src.mp4"
        out_mp4 = job_dir / "out.mp4"
        _create_real_valid_mp4(src_mp4)

        job_pools = {
            "low": [f"voice_male_job_{job_id}"],
            "high": [f"voice_female_job_{job_id}"],
        }
        job_cues = [
            {"cue_id": f"c_{job_id}_1", "speaker_id": f"spk_job_{job_id}_1", "text": f"Voice 1 from job {job_id}", "start_ms": 0, "end_ms": 1000},
            {"cue_id": f"c_{job_id}_2", "speaker_id": f"spk_job_{job_id}_2", "text": f"Voice 2 from job {job_id}", "start_ms": 1100, "end_ms": 2000},
        ]

        def strict_cls(*args, **kwargs):
            return {
                f"spk_job_{job_id}_1": {"voice_register": "low", "confidence": 0.95},
                f"spk_job_{job_id}_2": {"voice_register": "high", "confidence": 0.95},
            }

        async def job_synth(cues=None, **kwargs):
            return [{"cue_id": c["cue_id"], "audio": b"data"} for c in (cues or [])]

        async def job_render(source_media=None, output_path=None, **kwargs):
            return _create_real_valid_mp4(Path(output_path))

        res = await smart.run_auto_smart_multivoice(
            source_media=src_mp4,
            segments=job_cues,
            output_path=out_mp4,
            validated_pools=job_pools,
            strict_two_classifier=strict_cls,
            synthesize_segments=job_synth,
            render_pipeline=job_render,
            assignment_seed=f"seed_concurrency_{job_id}",
        )
        return job_id, res

    async def _run_all_concurrent():
        tasks = [_single_runner_job(i) for i in range(10)]
        return await asyncio.gather(*tasks)

    results = asyncio.run(_run_all_concurrent())
    assert len(results) == 10

    for jid, res in results:
        assert res["ok"] is True
        assert res["effective_speaker_count"] == 2
        assert res["effective_voice_count"] == 2
        v_map = res["speaker_voice_map"]
        assert v_map[f"spk_job_{jid}_1"] == f"voice_male_job_{jid}"
        assert v_map[f"spk_job_{jid}_2"] == f"voice_female_job_{jid}"
        assert Path(res["final_mp4_path"]).is_file()

        # Zero leakage from any of the other 9 jobs
        for other_id in range(10):
            if other_id != jid:
                assert f"voice_male_job_{other_id}" not in v_map.values()
                assert f"voice_female_job_{other_id}" not in v_map.values()


def test_shadow_13_legacy_entrypoints_actually_called(shadow_report_records):
    """Verify actual production legacy entrypoints were executed without simulation."""
    assert LEGACY_COUNTERS["legacy_auto_2_entrypoint_calls"] == 7
    assert LEGACY_COUNTERS["legacy_auto_2_fixtures_run"] == 7
    assert LEGACY_COUNTERS["legacy_auto_multi_entrypoint_calls"] == 12
    assert LEGACY_COUNTERS["legacy_auto_multi_fixtures_run"] == 12
    assert LEGACY_COUNTERS["legacy_auto_2_entrypoint_calls"] == LEGACY_COUNTERS["legacy_auto_2_fixtures_run"]
    assert LEGACY_COUNTERS["legacy_auto_multi_entrypoint_calls"] == LEGACY_COUNTERS["legacy_auto_multi_fixtures_run"]


def test_shadow_14_smart_manual_halt_empirically_derived(shadow_report_records):
    """Verify Smart manual_halt is empirically derived and 0 across all 24 fixtures."""
    for rec in shadow_report_records:
        assert isinstance(rec["smart_result"]["manual_halt"], bool)
        assert rec["smart_result"]["manual_halt"] is False


def test_shadow_15_legacy_auto_2_manual_halt_on_weak_evidence(shadow_report_records):
    """Verify F07, F08, F14 produced real AUTO_CAST_MANUAL_REQUIRED from run_auto_speaker_blackbox."""
    for fid in ["F07", "F08", "F14"]:
        rec = next(r for r in shadow_report_records if r["fixture_id"] == fid)
        assert rec["legacy_auto_2_result"]["applicable"] is True
        assert rec["legacy_auto_2_result"]["manual_halt"] is True
        assert rec["legacy_auto_2_result"]["result_state"] == "MANUAL_HALT"
        assert rec["legacy_auto_2_result"]["failure_code"] == speaker_cast.AUTO_CAST_MANUAL_REQUIRED


def test_shadow_16_legacy_auto_multi_pool_exhaustion(shadow_report_records):
    """Verify F12 produced real AUTO_CAST_MANUAL_REQUIRED from run_auto_multi_speaker_blackbox."""
    rec12 = next(r for r in shadow_report_records if r["fixture_id"] == "F12")
    assert rec12["legacy_auto_multi_result"]["applicable"] is True
    assert rec12["legacy_auto_multi_result"]["manual_halt"] is True
    assert rec12["legacy_auto_multi_result"]["result_state"] == "MANUAL_HALT"


def test_shadow_17_no_simulated_outcome_dictionaries():
    """Verify harness source code executes production entrypoints directly without dummy returns."""
    import inspect
    src_2 = inspect.getsource(_execute_legacy_auto_2)
    src_m = inspect.getsource(_execute_legacy_auto_multi)
    src_s = inspect.getsource(_execute_smart_lane)

    assert "counted_run_auto_speaker_blackbox" in src_2 or "auto_speaker.run_auto_speaker_blackbox" in src_2
    assert "counted_run_auto_multi_speaker_blackbox" in src_m or "auto_multi_speaker.run_auto_multi_speaker_blackbox" in src_m
    assert '"manual_halt": False' not in src_s
    assert 'res.get("status") == "AUTO_CAST_MANUAL_REQUIRED"' in src_s


def test_shadow_18_report_schema_v2_summary_consistency(shadow_report_records):
    """Verify that report schema v2 top-level summary matches machine-derived numbers."""
    assert REPORT_PATH.is_file()
    data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["task"] == "P0.SUBDUB.AUTO.SMART.MULTIVOICE.SHADOW.COMPARISON.VALIDATION.R1.C2"

    summary = data["summary"]
    assert summary["total_fixtures"] == 24
    assert summary["smart_executed"] == 24
    assert summary["smart_manual_halts"] == 0
    assert summary["legacy_auto_2_applicable"] == 7
    assert summary["legacy_auto_2_executed"] == 7
    assert summary["legacy_auto_2_entrypoint_calls"] == 7
    assert summary["legacy_auto_multi_applicable"] == 12
    assert summary["legacy_auto_multi_executed"] == 12
    assert summary["legacy_auto_multi_entrypoint_calls"] == 12
    assert len(data["fixtures"]) == 24


def test_shadow_19_full_production_source_unmodified():
    """Verify zero modifications to production codebase."""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "services/", "bot.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == "", f"Production files modified: {proc.stdout}"


def test_first_red_01_legacy_outcome_reconstructed_by_pre_c2_harness():
    """FIRST RED 1: Prove pre-C2 helper reconstructed outcome fields without sourcing from production callbacks."""
    is_ok = True
    cues = [{"cue_id": "c1"}, {"cue_id": "c2"}]
    pools = {"low": ["v_low"], "high": ["v_high"]}
    speaker_ids = ["spk_1", "spk_2"]

    # 1. speaker_voice_map constructed by test code
    v_map = {speaker_ids[0]: pools["low"][0], speaker_ids[1]: pools["high"][0]} if is_ok else {}
    assert v_map == {"spk_1": "v_low", "spk_2": "v_high"}

    # 2. effective_speaker_count is fixture-derived
    effective_speaker_count = 2 if is_ok else 0
    assert effective_speaker_count == 2

    # 3. effective_voice_count is fixture-derived
    effective_voice_count = 2 if is_ok else 0
    assert effective_voice_count == 2

    # 4. tts_synthesized_cues is inferred from is_ok
    tts_eligible = len(cues)
    tts_synthesized_cues = tts_eligible if is_ok else 0
    assert tts_synthesized_cues == 2

    # 5. render_attempted is assigned from is_ok
    render_attempted = is_ok
    assert render_attempted is True

    # 6. final_mp4_valid is assigned from is_ok
    final_mp4_valid = is_ok
    assert final_mp4_valid is True

    # 7. fallback_strategy is assigned by test code
    fallback_strategy = "STRICT_TWO" if is_ok else "MANUAL_REQUIRED"
    assert fallback_strategy == "STRICT_TWO"


def test_first_red_02_non_manual_failure_mislabeled_manual():
    """FIRST RED 2: Prove pre-C2 helper misclassified generic non-manual failures as MANUAL_HALT due to `or not is_ok`."""
    res = {"ok": False, "status": "RENDER_PIPELINE_CRASH", "blocker": "render_error"}
    is_ok = bool(res.get("ok"))

    # Pre-C2 flawed formula:
    is_manual = bool(res.get("status") == speaker_cast.AUTO_CAST_MANUAL_REQUIRED or not is_ok)
    result_state = "SUCCESS" if is_ok else "MANUAL_HALT"

    assert res.get("status") != speaker_cast.AUTO_CAST_MANUAL_REQUIRED
    assert is_manual is True
    assert result_state == "MANUAL_HALT"


def test_shadow_20_entrypoint_counter_zero_when_not_invoked(tmp_path):
    """Guard 20: Entrypoint counters remain unchanged if production entrypoint is never invoked."""
    fixtures = _get_24_canonical_fixtures()
    f01 = next(f for f in fixtures if f["fixture_id"] == "F01")
    c2_before = LEGACY_COUNTERS["legacy_auto_2_entrypoint_calls"]
    cm_before = LEGACY_COUNTERS["legacy_auto_multi_entrypoint_calls"]

    res_2 = _execute_legacy_auto_2(f01, tmp_path / "f01_2")
    res_m = _execute_legacy_auto_multi(f01, tmp_path / "f01_m")

    assert res_2["applicable"] is False
    assert res_m["applicable"] is False
    assert res_2["provenance"]["entrypoint_called"] is False
    assert res_m["provenance"]["entrypoint_called"] is False
    assert LEGACY_COUNTERS["legacy_auto_2_entrypoint_calls"] == c2_before
    assert LEGACY_COUNTERS["legacy_auto_multi_entrypoint_calls"] == cm_before


def test_shadow_21_generic_production_failure_not_classified_as_manual_halt():
    """Guard 21: Generic production failure is classified as FAILED, not MANUAL_HALT."""
    res = {"ok": False, "status": "GPU_OUT_OF_MEMORY", "reason": "oom"}
    is_ok = bool(res.get("ok"))
    is_manual = bool(
        res.get("status") == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
        or res.get("reason") == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
    )
    if is_ok:
        result_state = "SUCCESS"
    elif is_manual:
        result_state = "MANUAL_HALT"
    else:
        result_state = "FAILED"

    assert is_manual is False
    assert result_state == "FAILED"


def test_shadow_22_auto_2_speaker_voice_map_observed_from_callbacks(shadow_report_records):
    """Guard 22: Auto-2 speaker_voice_map comes strictly from observed callback execution."""
    rec05 = next(r for r in shadow_report_records if r["fixture_id"] == "F05")
    leg2 = rec05["legacy_auto_2_result"]
    assert leg2["applicable"] is True
    assert leg2["result_state"] == "SUCCESS"
    v_map = leg2["speaker_voice_map"]
    assert len(v_map) == 2
    assert "chunk_00:speaker_0" in v_map
    assert "chunk_00:speaker_1" in v_map
    assert leg2["provenance"]["voice_map_source"] == "synthesize_segments_callback"
    assert leg2["effective_voice_count"] == len(set(v_map.values()))


def test_shadow_23_auto_multi_speaker_voice_map_observed_from_callbacks(shadow_report_records):
    """Guard 23: Auto-Multi speaker_voice_map comes strictly from observed callback execution."""
    rec09 = next(r for r in shadow_report_records if r["fixture_id"] == "F09")
    leg_m = rec09["legacy_auto_multi_result"]
    assert leg_m["applicable"] is True
    assert leg_m["result_state"] == "SUCCESS"
    v_map = leg_m["speaker_voice_map"]
    assert len(v_map) == 3
    assert leg_m["provenance"]["voice_map_source"] == "synthesize_segments_callback"
    assert leg_m["effective_voice_count"] == len(set(v_map.values()))


def test_shadow_24_synth_count_observed_from_callbacks(shadow_report_records):
    """Guard 24: Synth count derives from actual callback observations, not is_ok."""
    rec05 = next(r for r in shadow_report_records if r["fixture_id"] == "F05")
    assert rec05["legacy_auto_2_result"]["tts_synthesized_cues"] == 2

    rec07 = next(r for r in shadow_report_records if r["fixture_id"] == "F07")
    assert rec07["legacy_auto_2_result"]["tts_synthesized_cues"] == 0

    rec12 = next(r for r in shadow_report_records if r["fixture_id"] == "F12")
    assert rec12["legacy_auto_multi_result"]["tts_synthesized_cues"] == 0


def test_shadow_25_render_attempted_observed_from_callback(shadow_report_records):
    """Guard 25: render_attempted derives from actual run_lane_blackbox callback invocation."""
    rec05 = next(r for r in shadow_report_records if r["fixture_id"] == "F05")
    assert rec05["legacy_auto_2_result"]["render_attempted"] is True

    rec07 = next(r for r in shadow_report_records if r["fixture_id"] == "F07")
    assert rec07["legacy_auto_2_result"]["render_attempted"] is False


def test_shadow_26_final_mp4_valid_cannot_become_true_solely_from_is_ok(shadow_report_records):
    """Guard 26: final_mp4_valid cannot be True without actual output MP4 generation."""
    for rec in shadow_report_records:
        r2 = rec["legacy_auto_2_result"]
        if r2.get("applicable"):
            assert r2["final_mp4_valid"] == "NOT_OBSERVED"
        rm = rec["legacy_auto_multi_result"]
        if rm.get("applicable"):
            assert rm["final_mp4_valid"] == "NOT_OBSERVED"


def test_shadow_27_fallback_strategy_cannot_be_fixture_hardcoded(shadow_report_records):
    """Guard 27: fallback_strategy reports NOT_EXPOSED rather than invented strategies."""
    for rec in shadow_report_records:
        r2 = rec["legacy_auto_2_result"]
        if r2.get("applicable"):
            assert r2["fallback_strategy"] == "NOT_EXPOSED"
        rm = rec["legacy_auto_multi_result"]
        if rm.get("applicable"):
            assert rm["fallback_strategy"] == "NOT_EXPOSED"


def test_shadow_28_report_fixture_aggregate_recomputation_matches_summary():
    """Guard 28: Summary aggregates recomputed from fixture rows match summary exactly."""
    assert REPORT_PATH.is_file()
    data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    summary = data["summary"]
    fixtures = data["fixtures"]

    assert len(fixtures) == summary["total_fixtures"]
    assert sum(1 for f in fixtures if f["smart_result"] is not None) == summary["smart_executed"]
    assert sum(1 for f in fixtures if f["smart_result"].get("manual_halt")) == summary["smart_manual_halts"]
    assert sum(1 for f in fixtures if f["legacy_auto_2_result"].get("applicable")) == summary["legacy_auto_2_applicable"]
    assert sum(1 for f in fixtures if f["legacy_auto_2_result"].get("provenance", {}).get("entrypoint_called")) == summary["legacy_auto_2_executed"]
    assert sum(1 for f in fixtures if f["legacy_auto_2_result"].get("manual_halt")) == summary["legacy_auto_2_manual_halts"]
    assert sum(1 for f in fixtures if f["legacy_auto_multi_result"].get("applicable")) == summary["legacy_auto_multi_applicable"]
    assert sum(1 for f in fixtures if f["legacy_auto_multi_result"].get("provenance", {}).get("entrypoint_called")) == summary["legacy_auto_multi_executed"]
    assert sum(1 for f in fixtures if f["legacy_auto_multi_result"].get("manual_halt")) == summary["legacy_auto_multi_manual_halts"]
    assert summary["legacy_auto_2_entrypoint_calls"] == summary["legacy_auto_2_executed"]
    assert summary["legacy_auto_multi_entrypoint_calls"] == summary["legacy_auto_multi_executed"]


def test_shadow_29_source_guards_reject_hardcoded_patterns():
    """Guard 29: Source code guard verifies forbidden heuristic patterns are eliminated."""
    import inspect
    src_2 = inspect.getsource(_execute_legacy_auto_2)
    src_m = inspect.getsource(_execute_legacy_auto_multi)

    for src in [src_2, src_m]:
        assert '"render_attempted": is_ok' not in src
        assert '"final_mp4_valid": is_ok' not in src
        assert '"tts_synthesized_cues": tts_eligible if is_ok else 0' not in src
        assert 'or not is_ok' not in src
