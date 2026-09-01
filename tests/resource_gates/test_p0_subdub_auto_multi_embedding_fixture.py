from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from services import subdub_multi_speaker_embedding_onnx as service
from services import subdub_speaker_cast as speaker_cast


SOURCE_SHA256 = "83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e"
SOURCE_BYTES = 9_869_032
SOURCE_DURATION_SECONDS = 133.3754375
WORD_FIXTURE_SOURCE = "tiny_en_transcript.json sanitized word timeline"
WORD_FIXTURE_RAW_COUNT = 98
WORD_FIXTURE_KEPT_COUNT = 50
WORD_FIXTURE_DROPPED_ZERO_DURATION_COUNT = 48
WORD_FIXTURE_SHA256 = (
    "c061a165a03b8f1bba43fccdb808381e92fb61f861dde3baaf75e44f191b802f"
)
WORD_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "subdub_auto_multi_fixture_words.json"
)
ACOUSTIC_REGION_SOURCE = (
    "existing #B4CB6D5FE8 Deepgram sidecar sanitized to timing-only regions"
)
ACOUSTIC_REGION_SHA256 = (
    "5f16f84ed24ea33a30152a669c07a5cf454b050768a5cf5318562ab90971d95f"
)
ACOUSTIC_REGION_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "subdub_auto_multi_fixture_acoustic_regions.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _load_strict_words() -> list[dict]:
    assert _sha256(WORD_FIXTURE_PATH) == WORD_FIXTURE_SHA256
    words = json.loads(WORD_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert type(words) is list
    assert len(words) == WORD_FIXTURE_KEPT_COUNT
    assert WORD_FIXTURE_RAW_COUNT - len(words) == (
        WORD_FIXTURE_DROPPED_ZERO_DURATION_COUNT
    )
    assert all(
        type(item) is dict
        and set(item) == {"index", "word", "start", "end"}
        for item in words
    )
    validated = service.validate_word_timeline(
        words,
        duration_seconds=SOURCE_DURATION_SECONDS,
    )
    assert validated == words
    return validated


def _ffmpeg_path() -> str:
    configured = str(os.environ.get("SUBDUB_MULTI_FFMPEG_PATH") or "").strip()
    candidate = configured or str(shutil.which("ffmpeg") or "")
    if not candidate or not Path(candidate).is_file():
        pytest.fail("SUBDUB_MULTI_FFMPEG_PATH must identify a real FFmpeg binary")
    return candidate


def _load_acoustic_regions() -> list[dict]:
    assert _sha256(ACOUSTIC_REGION_PATH) == ACOUSTIC_REGION_SHA256
    regions = json.loads(ACOUSTIC_REGION_PATH.read_text(encoding="utf-8"))
    assert type(regions) is list and len(regions) == 32
    assert all(
        type(item) is dict
        and set(item) == {"index", "start", "end"}
        and item["index"] == index
        for index, item in enumerate(regions)
    )
    assert not any(
        key in item
        for item in regions
        for key in ("speaker", "speaker_id", "text", "provider", "confidence")
    )
    merged = []
    for item in regions:
        if merged and item["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(
                {
                    "index": len(merged),
                    "start": item["start"],
                    "end": item["end"],
                }
            )
    assert len(merged) == 18
    assert all(
        next_item["start"] >= current["end"]
        for current, next_item in zip(merged, merged[1:])
    )
    return merged


def test_exact_fixture_selects_five_stable_acoustic_speakers(tmp_path):
    source_value = str(os.environ.get("SUBDUB_MULTI_FIXTURE_PATH") or "").strip()
    if not source_value:
        pytest.fail("SUBDUB_MULTI_FIXTURE_PATH is mandatory for this resource gate")
    source = Path(source_value)
    assert source.is_file()
    assert source.stat().st_size == SOURCE_BYTES
    assert _sha256(source) == SOURCE_SHA256
    assert service.MODEL_PATH.stat().st_size == 26_534_127
    assert _sha256(service.MODEL_PATH) == service.MODEL_SHA256
    assert all(path.is_file() and path.stat().st_size > 0 for path in service.NOTICE_PATHS)
    words = _load_strict_words()
    regions = _load_acoustic_regions()

    pcm_path = tmp_path / "exact-fixture-mono-16000-s16le.pcm"
    command = [
        _ffmpeg_path(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        str(pcm_path),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8",
        errors="replace",
    )[:500]
    assert pcm_path.is_file()
    assert 0 < pcm_path.stat().st_size <= int(
        service.MAX_SOURCE_SECONDS
        * service.PCM_SAMPLE_RATE
        * service.PCM_BYTES_PER_SAMPLE
    )

    result = service.diarize_acoustic_regions(
        str(pcm_path),
        regions,
        duration_seconds=SOURCE_DURATION_SECONDS,
        deadline_monotonic=time.monotonic() + 300.0,
        stop_requested=lambda: False,
    )

    assert result["ok"] is True
    assert result["detected_speaker_count"] == 5
    assert result["stability_pass"] is True
    assert len(words) == WORD_FIXTURE_KEPT_COUNT
    assert result["region_count"] == len(regions) == 18
    assert result["run_count"] == 14
    assert result["window_count"] == 87
    assert result["embedding_window_count"] == 174
    assert len(result["region_labels"]) == len(regions)
    assert len(set(result["region_labels"])) == 5
    assert result["region_labels"] == [
        0,
        1,
        1,
        1,
        2,
        1,
        1,
        1,
        2,
        0,
        3,
        3,
        3,
        3,
        3,
        3,
        4,
        3,
    ]
    assert result["window_cluster_sizes"] == [17, 24, 13, 20, 13]
    assert result["region_cluster_sizes"] == [2, 6, 2, 7, 1]
    assert sum(result["window_cluster_sizes"]) == result["window_count"]
    assert sum(result["region_cluster_sizes"]) == result["region_count"]
    assert result["model_sha256"] == service.MODEL_SHA256
    assert result["algorithm_version"] == service.ALGORITHM_VERSION
    assert "embeddings" not in result
    assert "pcm_path" not in result
    assert WORD_FIXTURE_SOURCE.endswith("sanitized word timeline")
    assert ACOUSTIC_REGION_SOURCE.endswith("timing-only regions")


@pytest.mark.parametrize("mutation", ("model_byte", "missing_notice"))
def test_real_acoustic_assets_fail_before_inference(monkeypatch, tmp_path, mutation):
    model_copy = tmp_path / service.MODEL_PATH.name
    model_copy.write_bytes(service.MODEL_PATH.read_bytes())
    notice_copies = []
    for source in service.NOTICE_PATHS:
        target = tmp_path / source.name
        target.write_bytes(source.read_bytes())
        notice_copies.append(target)
    if mutation == "model_byte":
        payload = bytearray(model_copy.read_bytes())
        payload[len(payload) // 2] ^= 0x01
        model_copy.write_bytes(payload)
    else:
        notice_copies[0].unlink()
    monkeypatch.setattr(service, "MODEL_PATH", model_copy)
    monkeypatch.setattr(service, "NOTICE_PATHS", tuple(notice_copies))
    inference_calls = []

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.model_preflight(
            session_factory=lambda *_args, **_kwargs: inference_calls.append(True)
        )

    assert inference_calls == []
    assert _sha256(
        Path(__file__).resolve().parents[2]
        / "assets"
        / "models"
        / "subdub_auto_multi"
        / "voxceleb_resnet34.onnx"
    ) == service.MODEL_SHA256
