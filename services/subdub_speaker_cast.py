"""Fail-closed speaker cue sidecars for SubDub automatic casting."""

from __future__ import annotations

from array import array
from collections.abc import Mapping
import hashlib
import hmac
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from services import subdub_canonical_cues


AUTO_CAST_UNAVAILABLE = "AUTO_CAST_UNAVAILABLE"
AUTO_CAST_MANUAL_REQUIRED = "AUTO_CAST_MANUAL_REQUIRED"
SIDECAR_VERSION = 1
MAX_SIDECAR_CUES = 20_000
MAX_SIDECAR_BYTES = 4 * 1024 * 1024
SIDECAR_FILENAME = "speaker_cast.sidecar.json"
MAX_SPEAKER_LABELS = 16

PCM_SAMPLE_RATE = 16_000
PCM_WINDOW_SAMPLES = 8_000
PCM_WINDOW_BYTES = PCM_WINDOW_SAMPLES * 2
MAX_AUTO_SPEAKER_LABELS = 16
MAX_SPEAKER_VOICED_SECONDS = 3.0
MAX_JOB_SAMPLE_SECONDS = 48.0
MAX_WORK_BUFFER_BYTES = 1_048_576
CLASSIFIER_WALL_TIMEOUT_SECONDS = 30.0
LOW_MAX_HZ = 155.0
HIGH_MIN_HZ = 185.0
MIN_REGISTER_CONFIDENCE = 0.75

_PCM_BYTES_PER_SAMPLE = 2
_PCM_WINDOW_SECONDS = PCM_WINDOW_SAMPLES / PCM_SAMPLE_RATE
_MIN_VOICED_SECONDS = 1.0
_MIN_WINDOW_RMS = 0.01
_MIN_AUTOCORRELATION = 0.82
_MIN_SPECTRAL_PURITY = 0.75
_MIN_PITCH_HZ = 70.0
_MAX_PITCH_HZ = 300.0
_AUTOCORRELATION_STRIDE = 4
_MAX_RELATIVE_PITCH_SPREAD = 0.08

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SPEAKER_ID_RE = re.compile(r"^chunk_(\d+):speaker_(\d+)$")
_VOICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SIDECAR_METADATA_FIELDS = (
    "speaker",
    "speaker_confidence",
    "speaker_id",
    "chunk_index",
    "voice_register",
    "tts_voice_id",
)


class AutoCastUnavailable(RuntimeError):
    """Raised when automatic casting cannot prove cue/sidecar identity."""

    def __init__(self, message: str = AUTO_CAST_UNAVAILABLE) -> None:
        super().__init__(str(message or AUTO_CAST_UNAVAILABLE))


class AutoCastManualRequired(RuntimeError):
    """Raised when bounded local evidence cannot support automatic casting."""

    def __init__(self) -> None:
        super().__init__(AUTO_CAST_MANUAL_REQUIRED)


def _validated_voice_pools(
    validated_pools: Mapping[str, object],
) -> dict[str, list[str]]:
    if not isinstance(validated_pools, Mapping):
        raise AutoCastManualRequired()
    if set(validated_pools) != {"low", "high"}:
        raise AutoCastManualRequired()

    normalized: dict[str, list[str]] = {}
    all_voice_ids: set[str] = set()
    for register in ("low", "high"):
        raw_pool = validated_pools.get(register)
        if not isinstance(raw_pool, (list, tuple)) or not raw_pool:
            raise AutoCastManualRequired()
        pool: list[str] = []
        for raw_voice_id in raw_pool:
            if type(raw_voice_id) is not str:
                raise AutoCastManualRequired()
            voice_id = raw_voice_id.strip()
            if voice_id != raw_voice_id or _VOICE_ID_RE.fullmatch(voice_id) is None:
                raise AutoCastManualRequired()
            if voice_id in all_voice_ids:
                raise AutoCastManualRequired()
            all_voice_ids.add(voice_id)
            pool.append(voice_id)
        normalized[register] = sorted(pool)
    return normalized


def assign_stable_voices(
    classifications: dict[str, dict],
    *,
    speaker_order: list[str],
    validated_pools: dict[str, list[str]],
    assignment_seed: str,
) -> dict[str, dict]:
    """Assign distinct provider-neutral voice IDs in canonical cue order."""

    if not isinstance(classifications, Mapping) or not classifications:
        raise AutoCastManualRequired()
    if not isinstance(speaker_order, (list, tuple)) or not speaker_order:
        raise AutoCastManualRequired()
    ordered_speakers = list(speaker_order)
    if (
        len(ordered_speakers) > MAX_AUTO_SPEAKER_LABELS
        or len(set(ordered_speakers)) != len(ordered_speakers)
        or set(ordered_speakers) != set(classifications)
    ):
        raise AutoCastManualRequired()
    seed = _normalized_sha256(assignment_seed)
    if not seed:
        raise AutoCastManualRequired()
    pools = _validated_voice_pools(validated_pools)

    register_counts = {"low": 0, "high": 0}
    normalized_classifications: dict[str, tuple[str, float]] = {}
    for speaker_id in ordered_speakers:
        try:
            validated_speaker_identity({"speaker_id": speaker_id})
        except AutoCastUnavailable as exc:
            raise AutoCastManualRequired() from exc
        item = classifications.get(speaker_id)
        if not isinstance(item, Mapping):
            raise AutoCastManualRequired()
        item_speaker_id = item.get("speaker_id")
        if item_speaker_id not in (None, speaker_id):
            raise AutoCastManualRequired()
        register = item.get("voice_register")
        confidence_value = item.get("confidence")
        if register not in register_counts or isinstance(confidence_value, bool):
            raise AutoCastManualRequired()
        try:
            confidence = float(confidence_value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AutoCastManualRequired() from exc
        if not math.isfinite(confidence) or confidence < MIN_REGISTER_CONFIDENCE:
            raise AutoCastManualRequired()
        normalized_classifications[speaker_id] = (str(register), confidence)
        register_counts[str(register)] += 1

    if any(register_counts[register] > len(pools[register]) for register in register_counts):
        raise AutoCastManualRequired()

    result: dict[str, dict] = {}
    used: dict[str, set[str]] = {"low": set(), "high": set()}
    for speaker_id in ordered_speakers:
        register, _confidence = normalized_classifications[speaker_id]
        available = [
            voice_id
            for voice_id in pools[register]
            if voice_id not in used[register]
        ]
        if not available:
            raise AutoCastManualRequired()
        digest = hashlib.sha256(
            f"{seed}:{speaker_id}:{register}".encode("utf-8", errors="strict")
        ).digest()
        voice_id = available[int.from_bytes(digest[:8], "big") % len(available)]
        used[register].add(voice_id)
        result[speaker_id] = {
            "speaker_id": speaker_id,
            "voice_register": register,
            "voice_id": voice_id,
        }
    return result


def pitch_register(median_hz: float, *, confidence: float) -> str:
    """Map a confident acoustic pitch estimate to the approved register labels."""

    try:
        normalized_hz = float(median_hz)
        normalized_confidence = float(confidence)
    except (TypeError, ValueError, OverflowError):
        return "unknown"
    if (
        not math.isfinite(normalized_hz)
        or not math.isfinite(normalized_confidence)
        or normalized_confidence < MIN_REGISTER_CONFIDENCE
    ):
        return "unknown"
    if normalized_hz <= LOW_MAX_HZ:
        return "low"
    if normalized_hz >= HIGH_MIN_HZ:
        return "high"
    return "unknown"


def valid_speaker_index(value: Any) -> bool:
    return type(value) is int and 0 <= value < MAX_SPEAKER_LABELS


def normalized_speaker_key(chunk_index: int, speaker: int) -> str:
    if type(chunk_index) is not int or chunk_index < 0:
        raise AutoCastUnavailable()
    if not valid_speaker_index(speaker):
        raise AutoCastUnavailable()
    try:
        speaker_id = f"chunk_{chunk_index:02d}:speaker_{speaker}"
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastUnavailable() from exc
    if len(speaker_id) > 128:
        raise AutoCastUnavailable()
    return speaker_id


def _normalized_sha256(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _bounded_text(value: Any, maximum: int) -> str:
    return str(value or "").strip()[: max(0, int(maximum))]


def _finite_confidence(value: Any) -> float:
    try:
        confidence = float(value or 0.0)
    except (TypeError, ValueError, OverflowError):
        confidence = 0.0
    if not math.isfinite(confidence):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def _optional_nonnegative_int(item: dict, field: str) -> int | None:
    if field not in item:
        return None
    value = item.get(field)
    if type(value) is not int or value < 0:
        raise AutoCastUnavailable()
    return value


def validated_speaker_identity(item: dict) -> tuple[int, int, str]:
    if not isinstance(item, dict):
        raise AutoCastUnavailable()
    speaker = _optional_nonnegative_int(item, "speaker")
    chunk_index = _optional_nonnegative_int(item, "chunk_index")
    speaker_id = str(item.get("speaker_id") or "").strip()
    match = _SPEAKER_ID_RE.fullmatch(speaker_id)
    if len(speaker_id) > 128 or match is None:
        raise AutoCastUnavailable()
    try:
        identity_chunk = int(match.group(1))
        identity_speaker = int(match.group(2))
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastUnavailable() from exc
    if (
        speaker_id != normalized_speaker_key(identity_chunk, identity_speaker)
        or (speaker is not None and speaker != identity_speaker)
        or (chunk_index is not None and chunk_index != identity_chunk)
    ):
        raise AutoCastUnavailable()
    return identity_chunk, identity_speaker, speaker_id


def _canonical_cues(cues: Iterable[dict]) -> list[dict]:
    source = [dict(item or {}) for item in (cues or [])]
    if len(source) > MAX_SIDECAR_CUES:
        raise AutoCastUnavailable()
    prepared: list[dict] = []
    for position, item in enumerate(source, start=1):
        current = dict(item)
        if current.get("source_start_ms") is None and current.get("start_ms") is not None:
            current["source_start_ms"] = current.get("start_ms")
        if current.get("source_end_ms") is None and current.get("end_ms") is not None:
            current["source_end_ms"] = current.get("end_ms")
        if not str(current.get("source_text") or current.get("text") or "").strip():
            current["text"] = f"__speaker_cue_{position:06d}__"
        prepared.append(current)
    try:
        canonical = subdub_canonical_cues.canonicalize_segments(
            prepared,
            extraction_source="speaker_sidecar",
            source_language="auto",
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastUnavailable() from exc
    if len(canonical) != len(source):
        raise AutoCastUnavailable()
    output: list[dict] = []
    for original, normalized in zip(source, canonical):
        output.append(
            {
                **original,
                "cue_id": str(normalized.get("cue_id") or "").strip(),
                "start_ms": int(normalized.get("source_start_ms") or 0),
                "end_ms": int(normalized.get("source_end_ms") or 0),
            }
        )
    return output


def _timeline_rows(cues: Iterable[dict]) -> list[tuple[str, int, int]]:
    canonical = _canonical_cues(cues)
    rows = [
        (
            str(item.get("cue_id") or "").strip(),
            int(item.get("start_ms") or 0),
            int(item.get("end_ms") or 0),
        )
        for item in canonical
    ]
    cue_ids = [row[0] for row in rows]
    if any(not cue_id for cue_id in cue_ids) or len(set(cue_ids)) != len(cue_ids):
        raise AutoCastUnavailable()
    return rows


def _signature_for_rows(rows: Iterable[tuple[str, int, int]]) -> str:
    serialized = "\n".join(f"{cue_id}:{start_ms}:{end_ms}" for cue_id, start_ms, end_ms in rows)
    return hashlib.sha256(serialized.encode("utf-8", errors="strict")).hexdigest()


def cue_timeline_signature(cues: list[dict]) -> str:
    return _signature_for_rows(_timeline_rows(cues))


def build_sidecar(
    cues: list[dict],
    *,
    media_sha256: str,
    subtitle_sha256: str,
) -> dict:
    media_hash = _normalized_sha256(media_sha256)
    subtitle_hash = _normalized_sha256(subtitle_sha256)
    if not media_hash or not subtitle_hash:
        raise ValueError("sidecar_sha256_invalid")
    canonical = _canonical_cues(cues)
    rows = _timeline_rows(canonical)
    entries: list[dict] = []
    for item, (cue_id, start_ms, end_ms) in zip(canonical, rows):
        identity_chunk, identity_speaker, speaker_id = validated_speaker_identity(item)
        speaker = identity_speaker if "speaker" in item else None
        chunk_index = identity_chunk if "chunk_index" in item else None
        entry: dict[str, Any] = {
            "cue_id": cue_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "speaker_id": speaker_id,
            "speaker_confidence": _finite_confidence(item.get("speaker_confidence")),
        }
        if speaker is not None:
            entry["speaker"] = speaker
        if chunk_index is not None:
            entry["chunk_index"] = chunk_index
        if "voice_register" in item:
            entry["voice_register"] = _bounded_text(item.get("voice_register"), 32)
        if "tts_voice_id" in item:
            entry["tts_voice_id"] = _bounded_text(item.get("tts_voice_id"), 256)
        entries.append(entry)
    return {
        "version": SIDECAR_VERSION,
        "media_sha256": media_hash,
        "subtitle_sha256": subtitle_hash,
        "timeline_signature": _signature_for_rows(rows),
        "cues": entries,
    }


def _sidecar_rows(sidecar: dict) -> list[tuple[str, int, int]]:
    entries = sidecar.get("cues")
    if not isinstance(entries, list) or len(entries) > MAX_SIDECAR_CUES:
        raise AutoCastUnavailable()
    rows: list[tuple[str, int, int]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise AutoCastUnavailable()
        cue_id = raw.get("cue_id")
        start_ms = raw.get("start_ms")
        end_ms = raw.get("end_ms")
        numeric_confidence = raw.get("speaker_confidence")
        if (
            type(cue_id) is not str
            or not cue_id
            or cue_id != cue_id.strip()
            or type(start_ms) is not int
            or type(end_ms) is not int
            or type(numeric_confidence) is not float
        ):
            raise AutoCastUnavailable()
        validated_speaker_identity(raw)
        if (
            start_ms < 0
            or end_ms <= start_ms
            or not math.isfinite(numeric_confidence)
            or not 0.0 <= numeric_confidence <= 1.0
        ):
            raise AutoCastUnavailable()
        rows.append((cue_id, start_ms, end_ms))
    cue_ids = [row[0] for row in rows]
    if len(cue_ids) != len(set(cue_ids)):
        raise AutoCastUnavailable()
    return rows


def sidecar_matches(
    sidecar: dict,
    cues: list[dict],
    *,
    media_sha256: str,
    subtitle_sha256: str,
) -> bool:
    try:
        if not isinstance(sidecar, dict):
            return False
        if type(sidecar.get("version")) is not int or sidecar.get("version") != SIDECAR_VERSION:
            return False
        media_hash = _normalized_sha256(media_sha256)
        subtitle_hash = _normalized_sha256(subtitle_sha256)
        if not media_hash or not subtitle_hash:
            return False
        if _normalized_sha256(sidecar.get("media_sha256")) != media_hash:
            return False
        if _normalized_sha256(sidecar.get("subtitle_sha256")) != subtitle_hash:
            return False
        expected_rows = _timeline_rows(cues)
        stored_rows = _sidecar_rows(sidecar)
        if stored_rows != expected_rows:
            return False
        signature = _signature_for_rows(expected_rows)
        return bool(
            _normalized_sha256(sidecar.get("timeline_signature")) == signature
            and len(stored_rows) == len(expected_rows)
        )
    except (AutoCastUnavailable, TypeError, ValueError, OverflowError):
        return False


def join_sidecar(sidecar: dict, cues: list[dict]) -> list[dict]:
    if (
        not isinstance(sidecar, dict)
        or type(sidecar.get("version")) is not int
        or sidecar.get("version") != SIDECAR_VERSION
    ):
        raise AutoCastUnavailable()
    source = _canonical_cues(cues)
    source_rows = _timeline_rows(source)
    stored_rows = _sidecar_rows(sidecar)
    if len(stored_rows) != len(source_rows):
        raise AutoCastUnavailable()
    entries = list(sidecar.get("cues") or [])
    by_cue_id = {str(item.get("cue_id")): dict(item) for item in entries}
    joined: list[dict] = []
    for cue, (cue_id, start_ms, end_ms) in zip(source, source_rows):
        entry = by_cue_id.get(cue_id)
        if (
            not entry
            or int(entry.get("start_ms")) != start_ms
            or int(entry.get("end_ms")) != end_ms
        ):
            raise AutoCastUnavailable()
        metadata = {
            key: entry[key]
            for key in _SIDECAR_METADATA_FIELDS
            if key in entry
        }
        joined.append({**cue, **metadata})
    return joined


def require_matching_sidecar(
    sidecar: dict,
    cues: list[dict],
    *,
    media_sha256: str,
    subtitle_sha256: str,
) -> list[dict]:
    if not sidecar_matches(
        sidecar,
        cues,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    ):
        raise AutoCastUnavailable()
    return join_sidecar(sidecar, cues)


def _workspace_file(workspace: str, path: str | os.PathLike[str]) -> Path:
    if not str(workspace or "").strip() or not str(path or "").strip():
        raise AutoCastUnavailable()
    root = Path(str(workspace or "")).expanduser().resolve(strict=False)
    target = Path(path).expanduser().resolve(strict=False)
    try:
        contained = os.path.commonpath((str(root), str(target))) == str(root)
    except ValueError as exc:
        raise AutoCastUnavailable() from exc
    if not root.is_dir() or not contained or target == root:
        raise AutoCastUnavailable()
    return target


def persist_sidecar(sidecar: dict, *, workspace: str) -> dict[str, str]:
    if not isinstance(sidecar, dict) or sidecar.get("version") != SIDECAR_VERSION:
        raise AutoCastUnavailable()
    entries = sidecar.get("cues")
    if not isinstance(entries, list) or len(entries) > MAX_SIDECAR_CUES:
        raise AutoCastUnavailable()
    if not str(workspace or "").strip():
        raise AutoCastUnavailable()
    root = Path(str(workspace or "")).expanduser().resolve(strict=False)
    target = _workspace_file(str(root), root / SIDECAR_FILENAME)
    try:
        payload = json.dumps(
            sidecar,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastUnavailable() from exc
    if len(payload) > MAX_SIDECAR_BYTES:
        raise AutoCastUnavailable()
    temporary = target.with_name(f"{target.name}.tmp")
    try:
        with open(temporary, "wb") as handle:
            handle.write(payload)
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise AutoCastUnavailable() from exc
    return {
        "path": str(target),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def load_sidecar(
    path: str,
    *,
    expected_sha256: str,
    workspace: str,
) -> dict:
    expected_hash = _normalized_sha256(expected_sha256)
    if not expected_hash:
        raise AutoCastUnavailable()
    target = _workspace_file(workspace, path)
    try:
        size = target.stat().st_size
        if size <= 0 or size > MAX_SIDECAR_BYTES:
            raise AutoCastUnavailable()
        with open(target, "rb") as handle:
            payload = handle.read(MAX_SIDECAR_BYTES + 1)
    except AutoCastUnavailable:
        raise
    except OSError as exc:
        raise AutoCastUnavailable() from exc
    if len(payload) != size or len(payload) > MAX_SIDECAR_BYTES:
        raise AutoCastUnavailable()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_hash, expected_hash):
        raise AutoCastUnavailable()
    try:
        sidecar = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise AutoCastUnavailable() from exc
    if (
        not isinstance(sidecar, dict)
        or sidecar.get("version") != SIDECAR_VERSION
        or not isinstance(sidecar.get("cues"), list)
        or len(sidecar.get("cues") or []) > MAX_SIDECAR_CUES
    ):
        raise AutoCastUnavailable()
    return sidecar


def ordered_auto_speaker_labels(cues: Iterable[dict]) -> list[str]:
    """Return distinct canonical labels in first-cue order, failing at label 17."""

    if isinstance(cues, (str, bytes, bytearray, dict)):
        raise AutoCastUnavailable()
    labels: list[str] = []
    seen: set[str] = set()
    for raw in cues or []:
        if not isinstance(raw, dict):
            raise AutoCastUnavailable()
        _chunk_index, _speaker, speaker_id = validated_speaker_identity(raw)
        if speaker_id in seen:
            continue
        if len(labels) >= MAX_AUTO_SPEAKER_LABELS:
            raise AutoCastManualRequired()
        seen.add(speaker_id)
        labels.append(speaker_id)
    return labels


def _ensure_classifier_active(
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> None:
    try:
        stopped = bool(stop_requested())
        expired = time.monotonic() >= deadline_monotonic
    except Exception as exc:
        raise AutoCastManualRequired() from exc
    if stopped or expired:
        raise AutoCastManualRequired()


def _bounded_median(values: list[float]) -> float:
    if not values:
        raise AutoCastManualRequired()
    ordered = sorted(float(value) for value in values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _speaker_window_offsets(
    ranges: object,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> list[int]:
    if not isinstance(ranges, (list, tuple)) or len(ranges) > MAX_SIDECAR_CUES:
        raise AutoCastManualRequired()
    offsets: list[int] = []
    remaining_seconds = MAX_SPEAKER_VOICED_SECONDS
    pending_start: float | None = None
    pending_end: float | None = None
    previous_start = -1.0

    def consume_interval(start: float, end: float) -> None:
        nonlocal remaining_seconds
        cursor = start
        while (
            remaining_seconds + 1e-12 >= _PCM_WINDOW_SECONDS
            and end - cursor + 1e-12 >= _PCM_WINDOW_SECONDS
        ):
            _ensure_classifier_active(deadline_monotonic, stop_requested)
            offsets.append(int(round(cursor * PCM_SAMPLE_RATE)) * _PCM_BYTES_PER_SAMPLE)
            cursor += _PCM_WINDOW_SECONDS
            remaining_seconds -= _PCM_WINDOW_SECONDS

    for position, raw_range in enumerate(ranges):
        if position % 64 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
            raise AutoCastManualRequired()
        try:
            start = float(raw_range[0])
            end = float(raw_range[1])
        except (TypeError, ValueError, OverflowError) as exc:
            raise AutoCastManualRequired() from exc
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0.0
            or end <= start
            or start < previous_start
        ):
            raise AutoCastManualRequired()
        previous_start = start
        if pending_start is None:
            pending_start, pending_end = start, end
            continue
        assert pending_end is not None
        if start <= pending_end + 1e-12:
            pending_end = max(pending_end, end)
            continue
        consume_interval(pending_start, pending_end)
        pending_start, pending_end = start, end

    if pending_start is not None and pending_end is not None:
        consume_interval(pending_start, pending_end)
    return offsets


def _estimate_window_pitch(
    raw: bytes,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> tuple[float, float] | None:
    _ensure_classifier_active(deadline_monotonic, stop_requested)
    if not isinstance(raw, bytes) or len(raw) != PCM_WINDOW_BYTES:
        return None

    samples = array("h")
    try:
        samples.frombytes(raw)
        if sys.byteorder != "little":
            samples.byteswap()
    except (MemoryError, OverflowError, ValueError) as exc:
        raise AutoCastManualRequired() from exc
    if len(samples) != PCM_WINDOW_SAMPLES:
        return None

    total = 0.0
    for index, sample in enumerate(samples):
        if index % 512 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        total += float(sample)
    mean = total / PCM_WINDOW_SAMPLES

    centered = array("f")
    energy = 0.0
    try:
        for index, sample in enumerate(samples):
            if index % 512 == 0:
                _ensure_classifier_active(deadline_monotonic, stop_requested)
            normalized = float(sample) - mean
            centered.append(normalized)
            energy += normalized * normalized
    except (MemoryError, OverflowError) as exc:
        raise AutoCastManualRequired() from exc
    rms = math.sqrt(energy / PCM_WINDOW_SAMPLES) / 32_768.0
    if not math.isfinite(rms) or rms < _MIN_WINDOW_RMS:
        return None

    minimum_lag = max(1, int(PCM_SAMPLE_RATE / _MAX_PITCH_HZ))
    maximum_lag = min(PCM_WINDOW_SAMPLES - 2, int(PCM_SAMPLE_RATE / _MIN_PITCH_HZ))
    correlation_count = maximum_lag - minimum_lag + 1
    transient_bytes = (
        len(raw)
        + len(samples) * samples.itemsize
        + len(centered) * centered.itemsize
        + correlation_count * 8
    )
    if transient_bytes > MAX_WORK_BUFFER_BYTES:
        raise AutoCastManualRequired()

    correlations = array("d")
    try:
        for lag in range(minimum_lag, maximum_lag + 1):
            _ensure_classifier_active(deadline_monotonic, stop_requested)
            cross = 0.0
            left_energy = 0.0
            right_energy = 0.0
            for step, index in enumerate(
                range(lag, PCM_WINDOW_SAMPLES, _AUTOCORRELATION_STRIDE)
            ):
                if step % 256 == 0:
                    _ensure_classifier_active(deadline_monotonic, stop_requested)
                left = float(centered[index])
                right = float(centered[index - lag])
                cross += left * right
                left_energy += left * left
                right_energy += right * right
            denominator = math.sqrt(left_energy * right_energy)
            correlations.append(cross / denominator if denominator > 0.0 else 0.0)
    except (MemoryError, OverflowError, ValueError) as exc:
        raise AutoCastManualRequired() from exc
    _ensure_classifier_active(deadline_monotonic, stop_requested)

    if len(correlations) != correlation_count:
        raise AutoCastManualRequired()
    maximum_score = max(correlations)
    if not math.isfinite(maximum_score) or maximum_score < _MIN_AUTOCORRELATION:
        return None

    candidate_indices = [
        index
        for index in range(1, len(correlations) - 1)
        if correlations[index] >= correlations[index - 1]
        and correlations[index] >= correlations[index + 1]
        and correlations[index] >= maximum_score - 0.015
    ]
    if candidate_indices:
        peak_index = candidate_indices[0]
    else:
        peak_index = max(range(len(correlations)), key=correlations.__getitem__)
    _ensure_classifier_active(deadline_monotonic, stop_requested)

    refined_offset = 0.0
    if 0 < peak_index < len(correlations) - 1:
        left = float(correlations[peak_index - 1])
        center = float(correlations[peak_index])
        right = float(correlations[peak_index + 1])
        curvature = left - (2.0 * center) + right
        if abs(curvature) > 1e-12:
            refined_offset = 0.5 * (left - right) / curvature
            refined_offset = max(-0.5, min(0.5, refined_offset))
    refined_lag = minimum_lag + peak_index + refined_offset
    if refined_lag <= 0.0:
        return None
    estimated_hz = PCM_SAMPLE_RATE / refined_lag
    if not math.isfinite(estimated_hz) or not _MIN_PITCH_HZ <= estimated_hz <= _MAX_PITCH_HZ:
        return None

    phase_step = 2.0 * math.pi * estimated_hz / PCM_SAMPLE_RATE
    phase_cos = 1.0
    phase_sin = 0.0
    step_cos = math.cos(phase_step)
    step_sin = math.sin(phase_step)
    projection_cos = 0.0
    projection_sin = 0.0
    for index, sample in enumerate(centered):
        if index % 512 == 0:
            _ensure_classifier_active(deadline_monotonic, stop_requested)
        value = float(sample)
        projection_cos += value * phase_cos
        projection_sin += value * phase_sin
        next_cos = (phase_cos * step_cos) - (phase_sin * step_sin)
        phase_sin = (phase_sin * step_cos) + (phase_cos * step_sin)
        phase_cos = next_cos
    spectral_purity = (
        2.0 * ((projection_cos * projection_cos) + (projection_sin * projection_sin))
        / (PCM_WINDOW_SAMPLES * energy)
        if energy > 0.0
        else 0.0
    )
    if not math.isfinite(spectral_purity) or spectral_purity < _MIN_SPECTRAL_PURITY:
        return None
    confidence = max(
        0.0,
        min(1.0, float(correlations[peak_index]), spectral_purity),
    )
    return estimated_hz, confidence


def classify_speaker_registers(
    pcm_path: str,
    ranges_by_speaker: dict[str, list[tuple[float, float]]],
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> dict[str, dict]:
    """Classify bounded speaker ranges from streaming mono 16 kHz s16le PCM."""

    if not isinstance(ranges_by_speaker, dict) or not ranges_by_speaker:
        raise AutoCastManualRequired()
    if not callable(stop_requested):
        raise AutoCastManualRequired()
    try:
        absolute_deadline = float(deadline_monotonic)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AutoCastManualRequired() from exc
    if not math.isfinite(absolute_deadline):
        raise AutoCastManualRequired()

    labels = ordered_auto_speaker_labels(
        {"speaker_id": speaker_id} for speaker_id in ranges_by_speaker
    )
    if not labels or len(labels) != len(ranges_by_speaker):
        raise AutoCastManualRequired()
    _ensure_classifier_active(absolute_deadline, stop_requested)

    sampled_job_seconds = 0.0
    results: dict[str, dict] = {}
    try:
        with open(str(pcm_path or ""), "rb") as handle:
            for speaker_id in labels:
                _ensure_classifier_active(absolute_deadline, stop_requested)
                offsets = _speaker_window_offsets(
                    ranges_by_speaker.get(speaker_id),
                    deadline_monotonic=absolute_deadline,
                    stop_requested=stop_requested,
                )
                speaker_seconds = len(offsets) * _PCM_WINDOW_SECONDS
                if (
                    speaker_seconds < _MIN_VOICED_SECONDS
                    or speaker_seconds > MAX_SPEAKER_VOICED_SECONDS + 1e-12
                    or sampled_job_seconds + speaker_seconds > MAX_JOB_SAMPLE_SECONDS + 1e-12
                ):
                    raise AutoCastManualRequired()

                frequencies: list[float] = []
                confidences: list[float] = []
                for offset in offsets:
                    _ensure_classifier_active(absolute_deadline, stop_requested)
                    handle.seek(offset)
                    _ensure_classifier_active(absolute_deadline, stop_requested)
                    _ensure_classifier_active(absolute_deadline, stop_requested)
                    raw = handle.read(PCM_WINDOW_BYTES)
                    _ensure_classifier_active(absolute_deadline, stop_requested)
                    estimate = _estimate_window_pitch(
                        raw,
                        deadline_monotonic=absolute_deadline,
                        stop_requested=stop_requested,
                    )
                    if estimate is None:
                        raise AutoCastManualRequired()
                    frequency, confidence = estimate
                    frequencies.append(frequency)
                    confidences.append(confidence)

                _ensure_classifier_active(absolute_deadline, stop_requested)
                median_hz = _bounded_median(frequencies)
                median_confidence = _bounded_median(confidences)
                relative_spread = 0.0
                for frequency in frequencies:
                    _ensure_classifier_active(absolute_deadline, stop_requested)
                    relative_spread = max(
                        relative_spread,
                        abs(frequency - median_hz) / median_hz,
                    )
                if (
                    not math.isfinite(relative_spread)
                    or relative_spread > _MAX_RELATIVE_PITCH_SPREAD
                ):
                    raise AutoCastManualRequired()
                stability_confidence = max(
                    0.0,
                    1.0 - (relative_spread / _MAX_RELATIVE_PITCH_SPREAD),
                )
                confidence = min(median_confidence, stability_confidence)
                register = pitch_register(median_hz, confidence=confidence)
                if register == "unknown":
                    raise AutoCastManualRequired()
                results[speaker_id] = {
                    "speaker_id": speaker_id,
                    "voice_register": register,
                    "confidence": round(float(confidence), 6),
                    "voiced_seconds": round(float(speaker_seconds), 3),
                    "sample_count": int(len(offsets) * PCM_WINDOW_SAMPLES),
                    "reason": "classified",
                }
                sampled_job_seconds += speaker_seconds
                _ensure_classifier_active(absolute_deadline, stop_requested)
    except AutoCastManualRequired:
        raise
    except (OSError, ValueError, TypeError, OverflowError, MemoryError) as exc:
        raise AutoCastManualRequired() from exc

    if not results or sampled_job_seconds > MAX_JOB_SAMPLE_SECONDS + 1e-12:
        raise AutoCastManualRequired()
    return results
