"""Owner-approved source audio for individually unfit/untranslated Smart cues."""
from __future__ import annotations

import io
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave


def replace_unfit_smart_cues(
    chunks: list[dict], *, source_file: str = "", source_bytes: bytes = b"",
    missing_translation_cue_ids: list[str] | tuple[str, ...] = (),
) -> dict:
    missing = set(missing_translation_cue_ids)
    replacements = []
    for item in chunks:
        if not item.get("duration_aware_timing"):
            continue
        cid = str(item.get("cue_id") or "")
        start, end = float(item.get("start") or 0), float(item.get("end") or 0)
        duration = float(item.get("fit_audio_duration") or item.get("audio_duration") or item.get("raw_audio_duration") or 0)
        if cid not in missing and duration <= end - start + .001:
            continue
        if not cid or not all(math.isfinite(v) for v in (start, end, duration)) or start < 0 or end <= start:
            raise RuntimeError("smart_source_audio_invalid_window")
        try:
            source_end = float(item.get("smart_source_end", end))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("smart_source_audio_invalid_window") from exc
        if not math.isfinite(source_end) or not start < source_end <= end:
            raise RuntimeError("smart_source_audio_invalid_window")
        reason = "translation_missing" if cid in missing else "natural_audio_exceeds_window"
        # Borrowed silence belongs to TTS fitting, not the original source speech.
        replacements.append((item, cid, start, source_end, reason))
    evidence = {"smart_source_audio_cue_ids": [], "smart_source_audio_reasons": {},
                "smart_source_audio_cue_count": 0, "smart_dubbed_voice_count": len({
                    str(c.get("tts_voice_id") or c.get("voice_id") or "") for c in chunks
                    if c.get("tts_voice_id") or c.get("voice_id")})}
    if not replacements:
        return evidence
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("smart_source_audio_ffmpeg_missing")
    decoded = []
    with tempfile.TemporaryDirectory(prefix="smart_source_cue_") as folder:
        source = Path(source_file) if source_file else Path(folder) / "source.media"
        if (not source.is_file()
                or source.suffix.lower() in {".srt", ".vtt", ".ass", ".ssa", ".sub", ".txt", ".json"}):
            if not source_bytes:
                raise RuntimeError("smart_source_audio_source_missing")
            source = Path(folder) / "source.media"
            source.write_bytes(source_bytes)
        for item, cid, start, end, reason in replacements:
            try:
                process = subprocess.run([
                    ffmpeg, "-v", "error", "-ss", f"{start:.6f}", "-i", str(source),
                    "-t", f"{end-start:.6f}", "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "44100",
                    "-c:a", "pcm_s16le", "-f", "wav", "pipe:1",
                ], capture_output=True, timeout=30, check=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                data = process.stdout
                with wave.open(io.BytesIO(data), "rb") as wav:
                    frames = wav.readframes(int(round((end-start)*44100)))
                    actual = len(frames) / (wav.getsampwidth() * wav.getnchannels() * wav.getframerate())
                if abs(actual-(end-start)) > .002 or actual <= 0:
                    raise ValueError("source_window_incomplete")
            except Exception as exc:
                raise RuntimeError("smart_source_audio_decode_failed") from exc
            decoded.append((item, cid, end-start, data, reason))
    for item, cid, duration, data, reason in decoded:
        item.update(audio=data, audio_bytes=data, audio_duration=duration, fit_audio_duration=duration,
                    raw_audio_duration=duration, generated_audio_seconds=duration, trim_start=0.,
                    trim_end=duration, fit_ratio=1., smart_audio_source="source", recovery_eligible=False,
                    duration_aware_timing=False)
        evidence["smart_source_audio_cue_ids"].append(cid)
        evidence["smart_source_audio_reasons"][cid] = reason
    evidence["smart_source_audio_cue_count"] = len(decoded)
    replaced = set(evidence["smart_source_audio_cue_ids"])
    evidence["smart_dubbed_voice_count"] = len({str(c.get("tts_voice_id") or c.get("voice_id") or "")
        for c in chunks if str(c.get("cue_id") or "") not in replaced and (c.get("tts_voice_id") or c.get("voice_id"))})
    return evidence
