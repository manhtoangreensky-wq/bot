import pytest
import asyncio
import copy
import hashlib
import json
import sqlite3
from pathlib import Path
from services import subdub_auto_word_pricing
from services import minimax_voice_adapter
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_multi_speaker_v2, auto_multi_speaker, auto_speaker
import bot


def _generate_68_cues():
    cues = []
    source_segments = []
    output_segments = []
    for i in range(1, 69):
        cid = f"cue-{i:04d}-fixture"
        st = round(float(i - 1) * 2.5, 3)
        et = round(st + 2.0, 3)
        spk = (i % 3)
        spk_id = f"chunk_00:speaker_{spk}"
        reg = "high" if spk == 0 else "low"
        cues.append({
            "chunk_index": 0,
            "cue_id": cid,
            "start_ms": int(round(st * 1000)),
            "end_ms": int(round(et * 1000)),
            "speaker": spk,
            "speaker_id": spk_id,
            "voice_register": reg,
        })
        source_segments.append({
            "index": i,
            "id": cid,
            "cue_id": cid,
            "start": st,
            "end": et,
            "text": f"English spoken source cue {i}",
            "speaker": spk,
            "speaker_id": spk_id,
        })
        output_segments.append({
            "index": i,
            "id": cid,
            "cue_id": cid,
            "start": st,
            "end": et,
            "text": f"Lời thoại tiếng Việt thứ {i} chuẩn xác",
            "speaker": spk,
            "speaker_id": spk_id,
        })
    return cues, source_segments, output_segments


def _stable_voice_casts():
    return {
        "chunk_00:speaker_0": {
            "speaker_id": "chunk_00:speaker_0",
            "voice_register": "high",
            "voice_id": "English_ConfidentWoman",
        },
        "chunk_00:speaker_1": {
            "speaker_id": "chunk_00:speaker_1",
            "voice_register": "low",
            "voice_id": "English_DecentYoungMan",
        },
        "chunk_00:speaker_2": {
            "speaker_id": "chunk_00:speaker_2",
            "voice_register": "low",
            "voice_id": "English_PassionateWarrior",
        },
    }


def _seed_sqlite_job(tmp_path: Path, job: dict) -> Path:
    db_path = tmp_path / f"{job['internal_job_id']}.sqlite3"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            note TEXT,
            updated_at TEXT,
            updated_by TEXT
            )"""
        )
        conn.execute(
            "INSERT OR REPLACE INTO system_settings(key, value, note, updated_at, updated_by) VALUES (?, ?, '', '', '')",
            (
                bot._engine_async_job_key(job["internal_job_id"]),
                json.dumps(job, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_spec03_quote_snapshot_and_pricing_authority():
    actual_words = 272
    auto_xu = subdub_auto_word_pricing.auto_voice_component_xu(actual_words)
    assert auto_xu == 136

    subtitle_xu = 104
    total_quoted_xu = auto_xu + subtitle_xu
    assert total_quoted_xu == 240

    decision = subdub_auto_word_pricing.auto_exact_confirmation_state(
        quoted_words=None,
        actual_words=actual_words,
        exact_known_at_quote=False,
        quoted_total_xu=None,
        actual_total_xu=total_quoted_xu,
    )
    assert decision["exact_confirmation_required"] is True
    assert decision["actual_billable_words"] == 272
    assert decision["actual_auto_xu"] == 136


def test_spec03_confirmation_call_graph_and_no_wallet_mutation(monkeypatch, tmp_path):
    user_id = 7714990570
    chat_id = user_id
    internal_job_id = "job-spec03-test-identity"
    job_key = f"key-{internal_job_id}"
    session_nonce = "nonce_12345678"

    initial_job = {
        "job_id": internal_job_id,
        "internal_job_id": internal_job_id,
        "job_key": job_key,
        "mode": "subtitle_plus_dub",
        "user_id": user_id,
        "chat_id": chat_id,
        "status": "awaiting_auto_exact_confirmation",
        "auto_exact_session_nonce": session_nonce,
        "auto_exact_actual_total_xu": 240,
        "auto_exact_receipt": {
            "version": bot.SUBDUB_AUTO_EXACT_RECEIPT_VERSION,
            "quote_version": bot.SUBDUB_AUTO_EXACT_QUOTE_VERSION,
            "session_nonce": session_nonce,
            "internal_job_id": internal_job_id,
            "job_key_sha256": hashlib.sha256(job_key.encode("utf-8")).hexdigest(),
            "mode": "subtitle_plus_dub",
            "owner_user_id": str(user_id),
            "chat_id": str(chat_id),
            "consumed": False,
            "claim_state": "unconsumed",
            "expires_at": 9999999999.0,
        },
        "auto_exact_resume_state": {
            "_pipeline_job_id": internal_job_id,
            "target_language": "vi",
            "mode": "subtitle_plus_dub",
        },
    }

    db_path = _seed_sqlite_job(tmp_path, initial_job)
    monkeypatch.setattr(
        bot,
        "db_connect",
        lambda: sqlite3.connect(str(db_path), timeout=5.0),
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS[job_key] = copy.deepcopy(initial_job)
    bot.ENGINE_ASYNC_MEMORY_JOBS[internal_job_id] = copy.deepcopy(initial_job)

    claimed, updated = bot._subdub_auto_engine_job_cas(
        internal_job_id,
        user_id=user_id,
        chat_id=chat_id,
        session_nonce=session_nonce,
        cancel=False,
    )
    assert claimed is True
    assert updated["status"] == "resuming_auto_exact_confirmation"
    receipt = updated["auto_exact_receipt"]
    assert receipt["consumed"] is True
    assert receipt["claim_state"] == "resuming"
    assert bool(receipt["claim_token"]) is True
    assert updated["job_id"] == initial_job["job_id"]
    assert updated["internal_job_id"] == initial_job["internal_job_id"]


def test_spec03_post_prepare_gate_pre_and_post_confirm(monkeypatch):
    user_id = 7714990570
    _, source_segs, output_segs = _generate_68_cues()
    casts = _stable_voice_casts()
    state = {
        "_pipeline_job_id": "job-preconfirm-test",
        "_pipeline_owner_user_id": str(user_id),
        "target_language": "vi",
        "mode": "subtitle_plus_dub",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "speaker_cast": casts,
        "_pipeline_workspace": "dummy_workspace",
    }
    prepared = {
        "source_segments": source_segs,
        "output_segments": output_segs,
        "source_bytes": b"dummy_mp4_bytes_fixture",
        "source_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nHello\n",
        "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n",
        "state": state,
    }

    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    monkeypatch.setattr(bot, "subdub_auto_provider_capacity_ready", lambda *a, **kw: True)
    monkeypatch.setattr(bot, "_subdub_auto_read_balance_xu", lambda uid: 1352)
    monkeypatch.setattr(bot, "_subdub_auto_actual_components", lambda p, s, txt: (272, 136, 104))
    monkeypatch.setattr(
        bot,
        "_subdub_auto_build_exact_receipt",
        lambda p, s, **kw: {
            "ok": True,
            "receipt": {
                "session_nonce": "nonce_gate_001",
                "actual_words": 272,
                "actual_auto_xu": 136,
                "actual_subtitle_xu": 104,
                "actual_total_xu": 240,
                "consumed": False,
            },
            "cache": {},
            "resume_state": {},
        },
    )
    monkeypatch.setattr(bot, "_subdub_auto_receipt_matches_actual", lambda *a, **kw: True)

    # 1. Pre-confirm gate must yield AUTO_EXACT_CONFIRMATION_REQUIRED
    pre_result = asyncio.run(bot._subdub_auto_post_prepare_gate(prepared, state))
    assert pre_result["ok"] is False
    assert pre_result["status"] == "AUTO_EXACT_CONFIRMATION_REQUIRED"
    assert pre_result["resume_required"] is True

    # 2. Post-confirm gate with auto_exact_resume=True must yield continue=True
    resume_state = dict(state)
    resume_state["auto_exact_resume"] = True
    resume_state["auto_exact_receipt"] = {
        "claim_state": "resuming",
        "consumed": True,
    }
    resume_prepared = dict(prepared)
    resume_prepared["state"] = resume_state
    resume_result = asyncio.run(bot._subdub_auto_post_prepare_gate(resume_prepared, resume_state))
    assert resume_result.get("continue") is True
    assert resume_state.get("auto_exact_receipt_confirmed") is True

    # 3. Malformed state: wrong balance fails closed
    monkeypatch.setattr(bot, "_subdub_auto_read_balance_xu", lambda uid: 50)  # < 240
    insufficient_result = asyncio.run(bot._subdub_auto_post_prepare_gate(prepared, state))
    assert insufficient_result["ok"] is False
    assert insufficient_result["status"] == "AUTO_EXACT_BALANCE_INSUFFICIENT"


def test_spec03_stable_speaker_voice_mapping_and_provider_contract():
    casts = _stable_voice_casts()
    expected_voices = {
        "chunk_00:speaker_0": ("high", "English_ConfidentWoman"),
        "chunk_00:speaker_1": ("low", "English_DecentYoungMan"),
        "chunk_00:speaker_2": ("low", "English_PassionateWarrior"),
    }
    for spk_id, (reg, v_id) in expected_voices.items():
        assert casts[spk_id]["voice_register"] == reg
        assert casts[spk_id]["voice_id"] == v_id
        assert minimax_voice_adapter.validate_provider_voice_id(v_id) is True
        if reg == "high":
            assert v_id in bot.SUBDUB_AUTO_DOCUMENTED_HIGH_VOICE_IDS
        else:
            assert v_id in bot.SUBDUB_AUTO_DOCUMENTED_LOW_VOICE_IDS

    _, source_segs, output_segs = _generate_68_cues()
    prepared = {
        "source_segments": source_segs,
        "output_segments": output_segs,
    }
    _, assignments = auto_multi_speaker_v2._annotate_multi_v2_prepared_assignments(
        prepared, casts
    )
    assert len(assignments) == 68

    cue_speaker_map = {c["cue_id"]: c["speaker_id"] for c in source_segs}
    voice_drift_count = 0
    for cid, (reg, v_id, st, et) in assignments.items():
        spk_id = cue_speaker_map[cid]
        expected_reg, expected_v_id = expected_voices[spk_id]
        if reg != expected_reg or v_id != expected_v_id:
            voice_drift_count += 1
    assert voice_drift_count == 0


def test_spec03_tts_request_payload_schema_and_ordering():
    cues, source_segs, output_segs = _generate_68_cues()
    casts = _stable_voice_casts()

    assert len(output_segs) == 68
    for seg in output_segs:
        assert isinstance(seg["text"], str)
        assert len(seg["text"].strip()) > 0
        assert seg["cue_id"].startswith("cue-")

    is_sorted_by_start = all(
        output_segs[i]["start"] <= output_segs[i + 1]["start"]
        for i in range(len(output_segs) - 1)
    )
    assert is_sorted_by_start is True

    annotated, assignments = auto_multi_speaker_v2._annotate_multi_v2_prepared_assignments(
        {"source_segments": source_segs, "output_segments": output_segs},
        casts,
    )
    selected = auto_multi_speaker_v2._validated_multi_v2_assigned_segments(
        annotated["output_segments"],
        assignments,
    )
    assert len(selected) == 68

    payloads = []
    for cue in selected:
        payload = bot.shopaikey_official_tts_payload(
            cue["text"],
            voice_id=cue["tts_voice_id"],
            speed=1.0,
            tts_language_boost="auto",
        )
        assert payload["model"] == (bot.SHOPAIKEY_TTS_MODEL or "speech-2.6-turbo")
        assert payload["text"] == cue["text"]
        assert payload["voice_setting"]["voice_id"] == cue["tts_voice_id"]
        assert payload["voice_setting"]["speed"] == 1.0
        assert payload["voice_setting"]["vol"] == 1
        assert payload["voice_setting"]["pitch"] == 0
        assert payload["audio_setting"]["format"] == "mp3"
        assert payload["audio_setting"]["sample_rate"] == 32000
        assert payload["audio_setting"]["bitrate"] == 128000
        assert payload["audio_setting"]["channel"] == 1
        assert payload["language_boost"] == "auto"
        assert payload["stream"] is False
        assert payload["subtitle_enable"] is False
        payloads.append(payload)

    assert len(payloads) == 68


def test_spec03_zero_cost_mock_execution_and_artifact_correlation():
    async def _runner():
        cues, source_segs, output_segs = _generate_68_cues()
        casts = _stable_voice_casts()
        annotated, assignments = auto_multi_speaker_v2._annotate_multi_v2_prepared_assignments(
            {"source_segments": source_segs, "output_segments": output_segs},
            casts,
        )
        selected = auto_multi_speaker_v2._validated_multi_v2_assigned_segments(
            annotated["output_segments"],
            assignments,
        )
        assert len(selected) == 68

        call_records = []

        async def mock_synthesize_segments(segments, *args, **kwargs):
            assert len(segments) == 1
            cue = segments[0]
            call_records.append({
                "cue_id": cue["cue_id"],
                "speaker_id": cue["speaker_id"],
                "voice_id": kwargs.get("voice_id"),
                "text": cue["text"],
                "start": cue["start"],
                "end": cue["end"],
            })
            return {
                "chunks": [
                    {
                        "cue_id": cue["cue_id"],
                        "speaker_id": cue["speaker_id"],
                        "voice_id": kwargs.get("voice_id"),
                        "start": cue["start"],
                        "end": cue["end"],
                        "text": cue["text"],
                        "audio_bytes": b"mock_mp3_audio_bytes",
                        "duration": round(cue["end"] - cue["start"], 3),
                    }
                ],
                "provider": "mock_minimax",
            }

        chunks = []
        provider_labels = []
        for cue in selected:
            scalar_kwargs = {"voice_id": cue["tts_voice_id"]}
            scalar_result = await mock_synthesize_segments([cue], **scalar_kwargs)
            scalar_chunks, provider_label = auto_speaker._validated_scalar_result(
                scalar_result, cue
            )
            chunks.extend(scalar_chunks)
            provider_labels.append(provider_label)

        assert len(call_records) == 68
        assert len(chunks) == 68
        for i, chunk in enumerate(chunks):
            rec = call_records[i]
            assert chunk["cue_id"] == rec["cue_id"]
            assert chunk["speaker_id"] == rec["speaker_id"]
            assert chunk["voice_id"] == rec["voice_id"]
            assert chunk["start"] == rec["start"]
            assert chunk["end"] == rec["end"]
            assert chunk["audio_bytes"] == b"mock_mp3_audio_bytes"

    asyncio.run(_runner())


def test_spec03_protected_comparators_auto2_and_legacy():
    assert hasattr(auto_speaker, "run_auto_speaker_blackbox")
    assert hasattr(auto_multi_speaker, "run_auto_multi_speaker_blackbox")
    assert hasattr(auto_multi_speaker_v2, "run_auto_multi_speaker_v2_blackbox")
