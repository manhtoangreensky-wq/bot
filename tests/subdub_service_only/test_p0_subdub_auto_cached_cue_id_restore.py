import hashlib

import pytest

from services import subdub_speaker_cast as speaker_cast


def _sidecar_fixture():
    media_sha256 = hashlib.sha256(b"normalized-media").hexdigest()
    subtitle_sha256 = hashlib.sha256(b"cached-source-srt").hexdigest()
    original = [
        {
            "cue_id": "cue-0001-sidecar-stable",
            "start_ms": 320,
            "end_ms": 3440,
            "text": "hello",
            "speaker": 0,
            "speaker_id": "chunk_00:speaker_0",
            "speaker_confidence": 0.99,
        }
    ]
    sidecar = speaker_cast.build_sidecar(
        original,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    )
    cached = [
        {
            **original[0],
            "cue_id": "cue-0001-regenerated-after-srt-parse",
        }
    ]
    return sidecar, cached, media_sha256, subtitle_sha256


def test_cached_srt_restores_sidecar_cue_id_only_after_exact_timeline_match():
    sidecar, cached, media_sha256, subtitle_sha256 = _sidecar_fixture()

    restored = speaker_cast.restore_cached_cue_ids_from_sidecar(
        sidecar,
        cached,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    )
    joined = speaker_cast.require_matching_sidecar(
        sidecar,
        restored,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    )

    assert restored[0]["cue_id"] == "cue-0001-sidecar-stable"
    assert joined[0]["speaker_id"] == "chunk_00:speaker_0"


@pytest.mark.parametrize("mismatch", ("media", "subtitle", "timestamp", "count"))
def test_cached_srt_cue_id_restore_fails_closed_on_identity_mismatch(mismatch):
    sidecar, cached, media_sha256, subtitle_sha256 = _sidecar_fixture()
    if mismatch == "media":
        media_sha256 = "a" * 64
    elif mismatch == "subtitle":
        subtitle_sha256 = "b" * 64
    elif mismatch == "timestamp":
        cached[0]["end_ms"] += 1
    else:
        cached.append({**cached[0], "cue_id": "cue-extra"})

    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.restore_cached_cue_ids_from_sidecar(
            sidecar,
            cached,
            media_sha256=media_sha256,
            subtitle_sha256=subtitle_sha256,
        )
