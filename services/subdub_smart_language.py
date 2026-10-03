"""Optional, bounded local language hint. Never a render or provider gate."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import urllib.request

MODEL_DIR = Path(__file__).resolve().parents[1] / "assets/models/subdub_smart_language"
MODEL_REPO = "Systran/faster-whisper-small"
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
MODEL_FILES = {
    "config.json": ("b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828", 2370),
    "model.bin": ("3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671", 483546902),
    "tokenizer.json": ("fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab", 2203239),
    "vocabulary.txt": ("34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913", 459861),
}
SUPPORTED_LANGUAGES = frozenset(
    "bg ca cs da de el en es et fi fr hi hu id it ja ko lt lv ms nl no pl pt ro ru sk sv th tr uk vi zh".split()
)
_PROBE_LOCK = threading.Lock()


def _fallback(reason: str) -> dict:
    return {"language": "auto", "status": "auto_fallback", "reason": reason}


def select_language_hint(samples: list, *, duration_seconds: float) -> dict:
    confident = []
    for language, probability in samples:
        if type(probability) not in {int, float} or not math.isfinite(probability) or not .90 <= probability <= 1:
            continue
        if language not in SUPPORTED_LANGUAGES:
            return _fallback("unsupported_language")
        confident.append((language, float(probability)))
    if len({language for language, _ in confident}) > 1:
        return _fallback("conflicting_samples")
    single = len(samples) == 1 and duration_seconds >= 8 and confident and confident[0][1] >= .98
    if len(confident) < 2 and not single:
        return _fallback("insufficient_confidence")
    return {"language": confident[0][0], "status": "confident",
            "reason": "single_high_confidence" if single else "multi_sample_agreement",
            "confidence": min(p for _, p in confident), "sample_count": len(samples)}


def _file_verified(path: Path, expected: tuple[str, int]) -> bool:
    try:
        if not path.is_file() or path.stat().st_size != expected[1]:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest() == expected[0]
    except OSError:
        return False


def model_ready(directory: Path | None = None) -> bool:
    root = directory if directory is not None else MODEL_DIR
    return all(_file_verified(root / name, expected) for name, expected in MODEL_FILES.items())


def install_model(directory: Path) -> None:
    """Explicit release action only, never called by detect_smart_language."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in MODEL_FILES.items():
        target = directory / name
        if _file_verified(target, expected):
            continue
        partial = directory / (name + ".part")
        url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}"
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
        if not _file_verified(partial, expected):
            raise ValueError("model_download_hash_mismatch")
        partial.replace(target)
    if not model_ready(directory):
        raise ValueError("model_not_ready")


def _probe_file(source: Path, directory: Path, duration: float, ffmpeg: str) -> dict:
    if not model_ready(directory):
        return _fallback("model_not_ready")
    import numpy as np
    from faster_whisper import WhisperModel

    model = WhisperModel(str(directory), device="cpu", compute_type="int8",
                         cpu_threads=2, num_workers=1, local_files_only=True)
    last_start = max(0., duration - 30.)
    starts = sorted({0., last_start / 2., last_start})
    samples = []
    for start in starts:
        raw = subprocess.run([
            ffmpeg, "-v", "error", "-ss", str(start), "-i", str(source),
            "-t", "30", "-vn", "-ar", "16000", "-ac", "1", "-f", "f32le", "pipe:1",
        ], check=True, capture_output=True, timeout=15).stdout
        audio = np.frombuffer(raw, dtype="<f4")
        if len(audio) < 16000 or not np.isfinite(audio).all() or float(np.sqrt(np.mean(audio ** 2))) < .003:
            samples.append(("", 0.))
            continue
        language, probability, _ = model.detect_language(audio=audio, vad_filter=False)
        samples.append((language, float(probability)))
    result = select_language_hint(samples, duration_seconds=duration)
    result.update(model_revision=MODEL_REVISION,
                  samples=[{"language": language, "confidence": p, "start": start}
                           for start, (language, p) in zip(starts, samples)])
    return result


def _run_probe(audio: bytes, duration: float, ffmpeg: str) -> dict:
    if not _PROBE_LOCK.acquire(blocking=False):
        return _fallback("probe_busy")
    try:
        if not model_ready():
            return _fallback("model_not_ready")
        with tempfile.TemporaryDirectory(prefix="subdub_language_") as temp:
            source = Path(temp) / "source.audio"
            source.write_bytes(audio)
            process = subprocess.run([
                sys.executable, str(Path(__file__).resolve()), "--probe-audio", str(source),
                "--model-dir", str(MODEL_DIR), "--duration", str(duration), "--ffmpeg", ffmpeg,
            ], capture_output=True, text=True, timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if process.returncode != 0:
                return _fallback("probe_failed")
            result = json.loads(process.stdout)
            if not isinstance(result, dict) or result.get("language") not in SUPPORTED_LANGUAGES | {"auto"}:
                return _fallback("probe_invalid_result")
            return result
    except subprocess.TimeoutExpired:
        return _fallback("probe_timeout")
    except Exception:
        return _fallback("probe_failed")
    finally:
        _PROBE_LOCK.release()


async def detect_smart_language(audio: bytes, *, duration_seconds: float, ffmpeg_path: str) -> dict:
    if not audio or not ffmpeg_path or type(duration_seconds) not in {int, float} or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        return _fallback("invalid_probe_input")
    return await asyncio.to_thread(_run_probe, audio, float(duration_seconds), ffmpeg_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-model", action="store_true")
    parser.add_argument("--probe-audio", type=Path)
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    parser.add_argument("--duration", type=float, default=0.)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    if args.install_model:
        install_model(args.model_dir)
        print(json.dumps({"ready": True, "revision": MODEL_REVISION}))
    elif args.probe_audio:
        print(json.dumps(_probe_file(args.probe_audio, args.model_dir, args.duration, args.ffmpeg)))
    else:
        parser.error("Choose explicit --install-model or --probe-audio")
