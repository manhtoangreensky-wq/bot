from __future__ import annotations

import html
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_compact_debug_renderer():
    payload = (ROOT / "bot.py").read_bytes()
    start = payload.index(b"def subdub_job_debug_text(")
    end = payload.index(b"\ndef normalize_voice_tts_backend_choice(", start)
    source = payload[start:end].decode("utf-8")
    namespace = {
        "html": html,
        "subdub_merge_debug_job": lambda job: dict(job or {}),
        "subdub_debug_missing_payload": lambda *_args: {},
        "_safe_int": lambda value, default=0: int(value or default),
        "subdub_classify_bad_request": lambda *_args, **_kwargs: "",
    }
    exec(compile(source, str(ROOT / "bot.py"), "exec"), namespace)
    return namespace["subdub_job_debug_text"]


def test_auto_multi_job_debug_is_readable_and_exposes_only_safe_acoustic_failure():
    render = _load_compact_debug_renderer()

    text = render({
        "feature": "subtitle_dub",
        "internal_job_id": "auto-multi-failed-job",
        "public_code": "A5F1F9CB0A",
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "last_error_stage": "AUTO_CAST_MANUAL_REQUIRED",
        "multi_acoustic_failure_code": "fixed_vocal_speaker_count_unstable",
        "multi_acoustic_failure_word_count": 167,
        "multi_acoustic_failure_duration_ms": 174_000,
        "raw_transcript": "must-not-leak",
        "provider_payload": {"must": "not-leak"},
    }, "A5F1F9CB0A")

    assert "\\n" not in text
    assert "\n• public_code:" in text
    assert "last_error_stage: <code>AUTO_CAST_MANUAL_REQUIRED</code>" in text
    assert "multi_acoustic_failure_code: <code>fixed_vocal_speaker_count_unstable</code>" in text
    assert "multi_acoustic_failure_word_count: <code>167</code>" in text
    assert "multi_acoustic_failure_duration_ms: <code>174000</code>" in text
    assert "must-not-leak" not in text
    assert "provider_payload" not in text


def test_auto_multi_job_debug_escapes_safe_failure_code():
    render = _load_compact_debug_renderer()

    text = render({
        "internal_job_id": "auto-multi-failed-job",
        "multi_acoustic_failure_code": "bad<script>alert(1)</script>",
    })

    assert "<script>" not in text
    assert "bad&lt;script&gt;alert(1)&lt;/script&gt;" in text
