import ast
import asyncio
from pathlib import Path
import textwrap
import time
import uuid

import pytest

from services.subdub_blackboxes import auto_smart_multivoice as smart
from services import subdub_auto_word_pricing, subtitle_dub_product_pipeline
from test_p0_subdub_smart_standard_pipeline_orchestrator import SAMPLE_VALID_MP3


EXACT = {
    "auto_exact_receipt_version": "2026-08-15.auto-exact.1",
    "auto_exact_actual_billable_words": 2,
    "auto_exact_actual_auto_xu": 100,
    "auto_exact_actual_subtitle_xu": 23,
    "auto_exact_actual_total_xu": 123,
    "auto_exact_receipt_confirmed": True,
    "auto_exact_receipt": {"actual_total_xu": 123, "claim_state": "resuming"},
    "auto_exact_cache": {"version": "fixture"},
    "auto_exact_resume_state": {"mode": "subtitle_plus_dub"},
    "auto_exact_claim_token": "fixture-claim",
    "auto_exact_session_nonce": "fixture-session",
}


def actual_outer_exact_price_guard(state):
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8-sig")
    marker = source.index('"auto_exact_price_missing"')
    start = source.rindex('    if auto_pricing_active:', 0, marker)
    end = source.index('    charge_note = ', marker)
    tree = ast.parse("def guard():\n" + textwrap.indent(textwrap.dedent(source[start:end]), "    "))
    namespace = {
        "state": state, "auto_pricing_active": True,
        "mode": "subtitle_plus_dub", "lang": "vi",
        "subdub_mode_fail_text": lambda *_args: "fixture",
        "_failed_product_result": lambda *_args, **_kwargs: "auto_exact_price_missing",
    }
    exec(compile(tree, "production_exact_price_guard", "exec"), namespace)
    return namespace["guard"]()


def _production_gate_with_offline_storage():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8-sig")
    start = source.index("async def _subdub_auto_post_prepare_gate(")
    end = source.index("\ndef _subdub_auto_workspace_file", start)
    stored = []

    def persist(_key, **fields):
        stored.append(fields)
        return dict(fields)

    namespace = {
        "time": time, "uuid": uuid,
        "subdub_auto_speaker_route_enabled": lambda _state: True,
        "_subdub_auto_v2_restore_prepared_selection": lambda prepared, _state: dict(prepared),
        "subtitle_dub_product_pipeline": subtitle_dub_product_pipeline,
        "_subdub_auto_selected_text": lambda segments: " ".join(c["text"] for c in segments),
        "video_dubbing_segments_from_subtitle": lambda _text: [{}],
        "_subdub_auto_record_multi_diagnostics": lambda *_args, **_kwargs: None,
        "_subdub_auto_actual_components": lambda *_args: (2, 100, 23),
        "_workspace_truthy": bool,
        "subdub_auto_word_pricing": subdub_auto_word_pricing,
        "subdub_final_confirmed_state": lambda state: bool(state.get("subdub_final_confirmed")),
        "SUBDUB_AUTO_EXACT_RECEIPT_VERSION": "2026-08-15.auto-exact.1",
        "_subdub_auto_build_exact_receipt": lambda *_args, **_kwargs: {
            "ok": True, "receipt": {"actual_total_xu": 123}, "cache": {"fixture": True},
            "resume_state": {"fixture": True},
        },
        "update_subtitle_dub_pipeline_job": persist,
        "persist_subtitle_dub_pipeline_job_snapshot": lambda *_args, **_kwargs: True,
    }
    exec(compile(source[start:end], "production_quote_gate_offline_storage", "exec"), namespace)
    return namespace["_subdub_auto_post_prepare_gate"], stored


def _run_contract(tmp_path, mode, *, resumed=False):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"contract-source" * 100)
    cues = [{"cue_id": "c1", "speaker_id": "chunk_00:speaker_0",
             "start": 0.0, "end": 2.0, "text": "full sentence"}]
    events = []
    state = {
        "mode": "subtitle_plus_dub", "auto_speaker_lane": "auto_smart_multivoice",
        "voice_kind": "auto_speaker_gender", "voice_selection_mode": "auto_speaker",
        "input_duration": 3.0, "_pipeline_job_key": "fixture-only-not-db",
        "_pipeline_job_id": "fixture-gate", "auto_exact_resume": resumed,
        "auto_exact_actual_total_xu": 0,
        "auto_exact_receipt_confirmed": False,
    }
    if resumed:
        state.update(EXACT)
    if mode == "production_gate":
        state.update(_pipeline_is_admin=True, subdub_final_confirmed=True)
    prepared = {
        "source_file": str(source), "source_segments": cues, "output_segments": cues,
        "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nfull sentence\n",
        "state": {"auto_smart_generic_acoustic": True, "input_duration": 3.0,
                  "auto_exact_actual_total_xu": 0, "auto_exact_receipt_confirmed": False},
    }
    if mode == "stale_private":
        prepared["state"].update(_pipeline_job_key="old-job", _pipeline_job_id="old-id")

    async def prepare(*_args, **_kwargs):
        events.append("prepare")
        return prepared

    async def gate(prep, current):
        events.append("gate")
        assert current["_pipeline_job_key"] == "fixture-only-not-db"
        if mode == "production_gate":
            production_gate, stored = _production_gate_with_offline_storage()
            result = await production_gate(prep, current)
            assert len(stored) == 1
            assert stored[0]["auto_exact_actual_total_xu"] == 123
            assert stored[0]["charge_status"] == "not_charged"
            return result
        if mode == "pause":
            current["auto_exact_receipt"] = {"actual_total_xu": 123}
            return {"ok": False, "status": "AUTO_EXACT_CONFIRMATION_REQUIRED",
                    "resume_required": True, "receipt": current["auto_exact_receipt"]}
        if mode == "invalid":
            return {"ok": False, "status": "AUTO_EXACT_RECEIPT_INVALID"}
        if mode == "exception":
            raise RuntimeError("fixture-private-detail")
        if mode == "bad_result":
            return "unexpected"
        if mode == "empty_continue":
            return {"continue": True}
        if mode != "prepared_only":
            current.update(EXACT)
        if mode != "state_only":
            prep["state"].update(EXACT)
        if mode == "rebuilt":
            prep["output_segments"] = [{**cue, "text": "authorized sentence"} for cue in cues]
            prep["output_subtitle"] = "1\n00:00:00,000 --> 00:00:02,000\nauthorized sentence\n"
        return {"continue": True}

    async def synthesize(segments, **_kwargs):
        events.append("tts")
        if mode == "rebuilt":
            assert segments[0]["text"] == "authorized sentence"
        return {"provider": "offline_contract", "chunks": [
            {"cue_id": cue["cue_id"], "audio_bytes": SAMPLE_VALID_MP3,
             "audio_duration": 1.0} for cue in segments
        ]}

    async def timeline(*_args):
        events.append("timeline")
        return SAMPLE_VALID_MP3, "contract-only"

    async def render(*_args, **_kwargs):
        events.append("render")
        return b"contract-mp4" * 200, "contract-only"

    kwargs = dict(
        state=state, prepare_subtitles=prepare, synthesize_segments=synthesize,
        build_timeline_audio=timeline, render_video=render,
        validated_pools={"low": ["voice_low_1"], "high": ["voice_high_1"]},
        locked_speaker_voice_map={"chunk_00:speaker_0": "voice_low_1"},
        output_path=str(tmp_path / "result.mp4"), job_id="fixture-gate",
        checkpoint_workspace=str(tmp_path / "checkpoint"),
    )
    if mode != "missing":
        kwargs["post_prepare_gate"] = gate
    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(**kwargs))
    return result, events


@pytest.mark.parametrize("mode,status", [
    ("pause", "AUTO_EXACT_CONFIRMATION_REQUIRED"),
    ("invalid", "AUTO_EXACT_RECEIPT_INVALID"),
    ("missing", "AUTO_EXACT_GATE_UNAVAILABLE"),
    ("empty_continue", "AUTO_EXACT_PRICE_MISSING"),
    ("bad_result", "AUTO_EXACT_GATE_INVALID"),
    ("exception", "AUTO_EXACT_GATE_FAILED"),
])
def test_exact_gate_stops_before_tts_intent(tmp_path, mode, status):
    result, events = _run_contract(tmp_path, mode)
    assert result.get("status") == status, result
    assert result["ok"] is False
    assert events == (["prepare"] if mode == "missing" else ["prepare", "gate"])
    assert not (tmp_path / "checkpoint" / "subdub_tts_manifest.json").exists()
    assert not (tmp_path / "result.mp4").exists()
    assert "fixture-private-detail" not in str(result)


@pytest.mark.parametrize("mode", ["continue", "prepared_only", "state_only", "stale_private", "rebuilt"])
def test_authoritative_exact_fields_survive_generic_result(tmp_path, mode):
    result, events = _run_contract(tmp_path, mode)
    assert result["ok"], result
    assert events == ["prepare", "gate", "tts", "timeline", "render"]
    for key, expected in EXACT.items():
        assert result["state"][key] == expected
    assert result["state"]["_pipeline_job_key"] == "fixture-only-not-db"
    assert result["state"]["_pipeline_job_id"] == "fixture-gate"
    assert actual_outer_exact_price_guard(result["state"]) is None
    assert result["tts_expected_segments"] == result["tts_generated_segments"] == 1


def test_resumed_exact_receipt_is_verified_and_preserved(tmp_path):
    result, events = _run_contract(tmp_path, "continue", resumed=True)
    assert result["ok"], result
    assert events.count("gate") == 1
    assert actual_outer_exact_price_guard(result["state"]) is None
    assert result["state"]["auto_exact_claim_token"] == "fixture-claim"


def test_existing_production_gate_reaches_generic_guard_with_offline_storage(tmp_path):
    result, events = _run_contract(tmp_path, "production_gate")
    assert result["ok"], result
    assert events == ["prepare", "gate", "tts", "timeline", "render"]
    assert actual_outer_exact_price_guard(result["state"]) is None
    assert result["state"]["auto_exact_receipt"]["consumed"] is True
    assert result["state"]["auto_exact_receipt"]["claim_state"] == "resuming"
    assert result["state"]["auto_exact_claim_token"]


def test_real_price_guard_still_rejects_unconfirmed_or_zero():
    assert actual_outer_exact_price_guard({}) == "auto_exact_price_missing"
    assert actual_outer_exact_price_guard({"auto_exact_receipt_confirmed": True,
                                          "auto_exact_actual_total_xu": 0}) == "auto_exact_price_missing"


def test_v2_dispatch_keeps_its_existing_single_gate(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    cues = [{"cue_id": f"c{i}", "speaker_id": f"chunk_00:speaker_{i}",
             "start": float(i), "end": float(i+1), "text": "full sentence"} for i in range(3)]
    calls = []

    async def gate(_prep, state):
        calls.append("gate")
        state.update(EXACT)
        return {"continue": True}

    async def v2(**kwargs):
        await kwargs["post_prepare_gate"]({}, kwargs["state"])
        return {"ok": True, "state": kwargs["state"]}

    monkeypatch.setattr(smart.auto_multi_speaker, "acoustic_register_classifications",
                        lambda *_args: {c["speaker_id"]: {"voice_register": "low"} for c in cues})
    monkeypatch.setattr(smart.auto_multi_speaker_v2, "run_auto_multi_speaker_v2_blackbox", v2)
    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={"auto_speaker_lane": "auto_smart_multivoice"},
        prepare_subtitles=lambda *_args, **_kwargs: {"source_file": str(source), "output_segments": cues},
        post_prepare_gate=gate,
    ))
    assert result["ok"]
    assert calls == ["gate"]
    assert result["auto_smart_dispatch"] == "n3_plus_proven_v2"
