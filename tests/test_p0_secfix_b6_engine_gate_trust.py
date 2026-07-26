"""SECFIX B6: the engine stops believing a caller that says it checked.

execute_engine skipped its own product gate whenever the caller put
`"gate_prechecked": True` in the context dict. A comment said "caller already
passed product export guard" — a convention, not something the engine could
verify. A public callback set that flag along with confirm_paid,
admin_interactive_confirm and is_paid_job, so the gate never ran on that path
and nothing in the engine could tell a genuine decision from a claim.

The flag is now replaced by a decision object carrying a token that only
bot.py can produce. A dict cannot forge it, so any caller that merely asserts
it checked gets the gate evaluated instead of skipped. Callers that legitimately
own the decision hand over a real object, and their behaviour is unchanged.
"""

import asyncio
from types import SimpleNamespace

import pytest

import bot


def _params():
    return {"action": "export", "state": {}}


def _run(coro):
    return asyncio.run(coro)


def test_a_forged_flag_no_longer_skips_the_gate(monkeypatch):
    evaluated = []

    def _gate(feature, params=None, context=None):
        evaluated.append(feature)
        return {"allowed": False, "status": "blocked_test", "reason": "gate ran", "message": ""}

    monkeypatch.setattr(bot, "evaluate_engine_gate", _gate)

    result = _run(
        bot.execute_engine(
            "video_single",
            _params(),
            {"user_id": 4242, "gate_prechecked": True, "confirm_paid": True, "is_paid_job": True},
        )
    )
    assert evaluated, "the bare flag must no longer skip evaluate_engine_gate"
    assert result.get("ok") is False
    assert result.get("status") == "GATE_BLOCKED"


def test_a_hand_built_lookalike_object_is_rejected(monkeypatch):
    evaluated = []

    def _gate(feature, params=None, context=None):
        evaluated.append(feature)
        return {"allowed": False, "status": "blocked_test", "reason": "gate ran", "message": ""}

    monkeypatch.setattr(bot, "evaluate_engine_gate", _gate)

    # Everything the real object has, except a token it cannot obtain.
    forged = {
        "allowed": True,
        "status": "allowed_prechecked",
        "reason": "trust me",
        "_precheck_token": "not-the-real-token",
    }
    result = _run(
        bot.execute_engine(
            "video_single", _params(), {"user_id": 4242, "gate_precheck_result": forged}
        )
    )
    assert evaluated, "a lookalike object must not be accepted"
    assert result.get("ok") is False


def test_a_real_precheck_object_is_honoured_and_skips_re_evaluation(monkeypatch):
    calls = []

    def _gate(feature, params=None, context=None):
        calls.append(feature)
        return {"allowed": True, "status": "allowed", "reason": "", "message": ""}

    monkeypatch.setattr(bot, "evaluate_engine_gate", _gate)
    monkeypatch.setattr(bot, "_product_engine_readiness", lambda *a, **k: {"ready": True})

    decision = bot.engine_gate_precheck_allow("video_single", _params(), {"user_id": 7})
    assert decision["allowed"] is True
    calls.clear()

    ran = {"runner": False}

    async def _runner():
        ran["runner"] = True
        return {"ok": True}

    result = _run(
        bot.execute_engine(
            "video_single",
            {"runner": _runner, "action": "export", "state": {}},
            {"user_id": 7, "gate_precheck_result": decision},
        )
    )
    assert calls == [], "a real decision object should not be re-evaluated"
    assert ran["runner"] is True
    assert result.get("ok") is True


def test_the_token_never_leaks_into_the_returned_gate(monkeypatch):
    monkeypatch.setattr(bot, "_product_engine_readiness", lambda *a, **k: {"ready": True})

    async def _runner():
        return {"ok": True}

    decision = bot.engine_gate_precheck_allow("video_single", _params(), {"user_id": 7})
    result = _run(
        bot.execute_engine(
            "video_single",
            {"runner": _runner, "action": "export", "state": {}},
            {"user_id": 7, "gate_precheck_result": decision},
        )
    )
    assert "_precheck_token" not in (result.get("gate") or {})


def test_subdub_features_are_still_never_prechecked(monkeypatch):
    calls = []

    def _gate(feature, params=None, context=None):
        calls.append(feature)
        return {"allowed": True, "status": "allowed", "reason": "", "message": ""}

    monkeypatch.setattr(bot, "evaluate_engine_gate", _gate)
    monkeypatch.setattr(bot, "_product_engine_readiness", lambda *a, **k: {"ready": True})

    async def _runner():
        return {"ok": True}

    decision = bot.engine_gate_precheck_allow("video_dub", _params(), {"user_id": 7})
    _run(
        bot.execute_engine(
            "video_dub",
            {"runner": _runner, "action": "export", "state": {}},
            {"user_id": 7, "gate_precheck_result": decision},
        )
    )
    assert calls, "SubDub must always evaluate its own gate, token or not"


def test_precheck_helper_runs_the_real_gate_and_carries_its_verdict(monkeypatch):
    monkeypatch.setattr(
        bot,
        "evaluate_engine_gate",
        lambda feature, params=None, context=None: {
            "allowed": False,
            "status": "blocked_upstream",
            "reason": "no",
            "message": "",
        },
    )
    decision = bot.engine_gate_precheck("video_single", _params(), {"user_id": 7})
    assert decision["allowed"] is False, "the helper must not invent an allow"
    assert bot.engine_gate_precheck_result({"gate_precheck_result": decision}) is decision


def test_public_export_handler_hands_over_a_real_object():
    from pathlib import Path

    source = Path(bot.__file__).read_text(encoding="utf-8", errors="replace")
    handler = source.split("async def handle_video_export_confirm(", 1)[1].split("\nasync def ", 1)[0]
    assert "engine_gate_precheck_allow(" in handler
    assert '"gate_prechecked": True' not in handler
