"""P0.SUBDUB.GOLIVE ADDENDUM 2 — lane-open integrity, always-terminal smokes,
restored runtime names, well-formed gate reasons, permanent F821 guard.

Covers:
- Section C/D: resolve_translate_target restored (PR400 ancestry f257e1d),
  sanitize_public_copy call site reconnected to sanitize_log_text (d21d651),
  single subdub_missing_origin_back_callback definition.
- Section D3: an exception injected right after the provider seam returns must
  propagate (no swallowed success), record a FAIL attempt, never a PASS state,
  and never a second provider submit.
- Section F: a lane-level readiness probe (empty state) can never skip the ASR
  chain; missing / failed / stale-SHA / provider-changed smokes keep the lane
  closed.
- Section G: paid video smokes always answer with a terminal PASS/FAIL/BLOCKED
  line even when the engine gate blocks or the wrapper crashes.
- Section I: gate reason is never the contradictory "blocked_*:ready"; the
  debug view identifies which job it shows.
- Section C6: permanent F821 guard on the SubDub surface.

Zero provider calls (all provider seams are monkeypatched), zero Telegram
sends (fake update), zero wallet mutations.
"""

import asyncio
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot

NOT_TESTED = {"status": "NOT_TESTED", "tested_at": "", "detail": ""}


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(str(text))
        return SimpleNamespace(message_id=len(self.replies))


def _fake_update(user_id=22):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=FakeMessage(),
    )


def _patch_settings_store(monkeypatch):
    store = {}

    def get_system_setting(key, default=""):
        return store.get(str(key), default)

    def set_system_setting(key, value, note="", updated_by=""):
        store[str(key)] = str(value)

    monkeypatch.setattr(bot, "get_system_setting", get_system_setting)
    monkeypatch.setattr(bot, "set_system_setting", set_system_setting)
    return store


def _patch_ready_runtime(monkeypatch, smoke_overrides=None):
    """Production-like runtime: explicit providers, configured, smokes PASS on
    the current runtime SHA. Individual tests then degrade one link at a time."""
    monkeypatch.setattr(bot, "APP_BUILD_SHA", "addendum2-runtime-sha")
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", False)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", True)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setattr(bot, "TTS_PROVIDER", "direct_minimax")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "MINIMAX_API_KEY", "configured")
    monkeypatch.setattr(bot, "MINIMAX_GROUP_ID", "configured")
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 22)
    monkeypatch.setattr(
        bot,
        "subdub_runtime_status_payload",
        lambda: {
            "media_preprocessing_ready": True,
            "subtitle_rendering_ready": True,
            "ffmpeg_ready": True,
            "ffprobe_ready": True,
        },
    )
    smoke = {
        "asr:deepgram": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=addendum2-runtime-sha"},
        "translation:deepl": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=addendum2-runtime-sha"},
        "tts:direct_minimax": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=addendum2-runtime-sha"},
    }
    if smoke_overrides is not None:
        smoke.clear()
        smoke.update(smoke_overrides)
    monkeypatch.setattr(
        bot,
        "get_tool_test_result",
        lambda name: dict(smoke.get(name) or dict(NOT_TESTED)),
    )
    return smoke


# ---------------------------------------------------------------------------
# Section C/D — restored names (static NameError fixes stay fixed)
# ---------------------------------------------------------------------------

def test_resolve_translate_target_restored_from_pr400_ancestry():
    assert bot.resolve_translate_target("vi") == "vi"
    assert bot.resolve_translate_target("en") == "en"
    assert bot.resolve_translate_target("") == "vi"
    assert bot.resolve_translate_target("   ") == "vi"
    assert bot.resolve_translate_target("", default="en") == "en"


def test_missing_origin_back_callback_single_definition_and_behaviour():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert source.count("def subdub_missing_origin_back_callback") == 1
    assert bot.subdub_missing_origin_back_callback() == "videodub|back_type"
    assert bot.subdub_missing_origin_back_callback({}) == "videodub|back_type"
    assert bot.subdub_missing_origin_back_callback({"origin": "video_addon"}) == "videodub|return_origin"


def test_failed_job_public_status_renders_safe_copy_without_nameerror():
    job = {"status": "failed", "last_error_safe": "Video chưa xử lý được, chưa trừ Xu."}
    text = bot.subdub_job_public_status_text(job, "vi")
    assert "Video chưa xử lý được, chưa trừ Xu." in text


def test_failed_job_public_status_falls_back_to_clean_failure_text():
    job = {"status": "failed_pipeline", "terminal_state": "failed"}
    text = bot.subdub_job_public_status_text(job, "vi")
    assert text == bot.subdub_clean_failure_text("vi")


# ---------------------------------------------------------------------------
# Section D — translate route: no NameError, post-provider ordering
# ---------------------------------------------------------------------------

def _patch_translate_deepl(monkeypatch, provider_calls):
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")

    async def fake_deepl(text, target):
        provider_calls.append((str(text)[:50], target))
        return "bản dịch thật từ provider"

    monkeypatch.setattr(bot, "translate_with_deepl", fake_deepl)


def test_translate_subtitle_text_shared_route_has_no_nameerror(monkeypatch):
    provider_calls = []
    _patch_translate_deepl(monkeypatch, provider_calls)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *a, **k: None)
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *a, **k: None)
    result = asyncio.run(bot.translate_subtitle_text("hello world", "vi", allow_admin=True))
    assert result["provider"] == "deepl"
    assert result["target"] == "vi"
    assert result["text"] == "bản dịch thật từ provider"
    assert len(provider_calls) == 1


def test_translate_crash_after_provider_seam_propagates_and_records_fail(monkeypatch):
    """Section D3: an exception right after the provider seam returns must
    (a) propagate — never be relabelled success, (b) record a FAIL attempt,
    (c) never trigger a second provider submit inside the same call."""
    provider_calls = []
    _patch_translate_deepl(monkeypatch, provider_calls)

    def crash_after_provider(name, status, detail="", updated_by=""):
        raise RuntimeError("injected_after_provider_return")

    monkeypatch.setattr(bot, "save_tool_test_result", crash_after_provider)
    attempts = []
    monkeypatch.setattr(
        bot,
        "save_provider_attempt",
        lambda name, payload, updated_by="": attempts.append((str(name), dict(payload))),
    )
    with pytest.raises(RuntimeError, match="injected_after_provider_return"):
        asyncio.run(bot.translate_subtitle_text("hello world", "vi", allow_admin=True))
    assert len(provider_calls) == 1, "crash after the seam must not re-submit to the provider"
    assert attempts, "the failed attempt must be persisted"
    assert attempts[-1][0] == "translation_text"
    assert attempts[-1][1].get("status") == "FAIL"


def test_translate_provider_auto_resolves_deterministically_no_paid_fallback(monkeypatch):
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "auto")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    assert bot.subdub_translation_provider_name() == "deepl"
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "")
    assert bot.subdub_translation_provider_name() == ""


def test_asr_auto_blocks_at_execution_time_with_zero_provider_routes(monkeypatch):
    """`auto` for ASR maps to an EMPTY provider order at execution time —
    it can never silently pick (and pay) a vendor. REAL PROVIDER COST LOCK."""
    monkeypatch.setattr(bot, "ASR_PROVIDER", "auto")
    attempts = []
    monkeypatch.setattr(
        bot,
        "save_provider_attempt",
        lambda name, payload, updated_by="": attempts.append(dict(payload)),
    )
    result = asyncio.run(bot.asr_transcribe_audio(b"fake-bytes", "audio/mpeg", allow_admin=True))
    assert result["ok"] is False
    assert result["status"] == "asr_unavailable"
    assert attempts and attempts[-1]["called"] is False


# ---------------------------------------------------------------------------
# Section F — lane-open integrity: empty probe can never skip the ASR chain
# ---------------------------------------------------------------------------

def test_lane_probe_with_empty_state_cannot_skip_asr_chain(monkeypatch):
    _patch_settings_store(monkeypatch)
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "auto")
    readiness = bot.get_subdub_lane_readiness(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, public=True)
    assert "asr_provider_policy_required" in readiness["blockers"]
    assert readiness["effective_ready"] is False


def test_exact_auto_speaker_route_uses_deepgram_when_global_asr_is_auto(monkeypatch):
    _patch_settings_store(monkeypatch)
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "auto")
    monkeypatch.setattr(bot, "subdub_auto_provider_capacity_ready", lambda provider=None: True)
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "media_kind": "video",
        "translate_requested": "1",
        "target_language": "en",
    }

    readiness = bot.get_subdub_lane_readiness(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state,
        public=True,
        confirmed_product=True,
    )

    assert readiness["asr_required"] is True
    assert readiness["asr_provider"] == "deepgram"
    assert "asr_provider_policy_required" not in readiness["blockers"]
    assert readiness["effective_ready"] is True


def test_job_state_with_subtitle_file_still_skips_asr(monkeypatch):
    _patch_settings_store(monkeypatch)
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "auto")
    state = {"source_file_name": "phu_de_khach_gui.srt"}
    readiness = bot.get_subdub_lane_readiness(bot.VIDEO_SUBTITLE_MODE_CREATE, state, public=True)
    assert "asr_provider_policy_required" not in readiness["blockers"]
    assert "asr_smoke_not_pass" not in readiness["blockers"]


def _subtitle_lane_env_state(monkeypatch, smoke_overrides):
    store = _patch_settings_store(monkeypatch)
    _patch_ready_runtime(monkeypatch, smoke_overrides=smoke_overrides)
    return store


def test_lane_cannot_open_when_asr_smoke_missing(monkeypatch):
    _subtitle_lane_env_state(
        monkeypatch,
        {
            "translation:deepl": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=addendum2-runtime-sha"},
            "tts:direct_minimax": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=addendum2-runtime-sha"},
        },
    )
    readiness = bot.get_subdub_lane_readiness(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, public=True)
    assert "asr_smoke_not_pass" in readiness["blockers"]
    assert readiness["effective_ready"] is False


def test_lane_cannot_open_when_asr_smoke_failed(monkeypatch):
    _subtitle_lane_env_state(
        monkeypatch,
        {
            "asr:deepgram": {"status": "FAIL", "tested_at": "now", "detail": "runtime_sha=addendum2-runtime-sha"},
        },
    )
    readiness = bot.get_subdub_lane_readiness(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, public=True)
    assert "asr_smoke_not_pass" in readiness["blockers"]
    assert readiness["effective_ready"] is False


def test_lane_cannot_open_when_asr_smoke_bound_to_older_sha(monkeypatch):
    _subtitle_lane_env_state(
        monkeypatch,
        {
            "asr:deepgram": {"status": "PASS", "tested_at": "old", "detail": "runtime_sha=older-deploy-sha"},
        },
    )
    smoke = bot.subdub_provider_smoke_result("asr", "deepgram")
    assert smoke["status"] == "STALE"
    readiness = bot.get_subdub_lane_readiness(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, public=True)
    assert "asr_smoke_not_pass" in readiness["blockers"]
    assert readiness["effective_ready"] is False


def test_lane_cannot_open_when_provider_changed_after_smoke(monkeypatch):
    _subtitle_lane_env_state(
        monkeypatch,
        {
            "asr:deepgram": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=addendum2-runtime-sha"},
        },
    )
    monkeypatch.setattr(bot, "ASR_PROVIDER", "key4u")
    monkeypatch.setattr(bot, "key4u_asr_configured", lambda: True)
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", True)
    readiness = bot.get_subdub_lane_readiness(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, public=True)
    assert "asr_smoke_not_pass" in readiness["blockers"], readiness["blockers"]
    assert readiness["effective_ready"] is False


def test_open_safe_keeps_subtitle_lane_closed_without_asr_smoke(monkeypatch):
    _subtitle_lane_env_state(
        monkeypatch,
        {
            "translation:deepl": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=addendum2-runtime-sha"},
            "tts:direct_minimax": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=addendum2-runtime-sha"},
        },
    )
    update = _fake_update()
    asyncio.run(bot.cmd_subdub_public_open_safe(update, SimpleNamespace()))
    body = "\n".join(update.message.replies)
    assert "VIDEO_SUBTITLE_PUBLIC_ENABLED=OPEN" not in body
    assert "asr_smoke_not_pass" in body


# ---------------------------------------------------------------------------
# Section G — always-terminal smoke replies
# ---------------------------------------------------------------------------

def test_video_smoke_replies_terminal_blocked_when_gate_blocks(monkeypatch):
    async def fake_execute_engine(feature, params=None, context=None):
        return {
            "ok": False,
            "status": "GATE_BLOCKED",
            "detail": "asr,tts",
            "gate": {"status": "blocked_admin_missing_provider_config", "reason": "asr,tts"},
        }

    monkeypatch.setattr(bot, "execute_engine", fake_execute_engine)
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 22)
    saved = []
    monkeypatch.setattr(
        bot,
        "save_tool_test_result",
        lambda name, status, detail="", updated_by="": saved.append((str(name), str(status), str(detail))),
    )
    update = _fake_update()
    context = SimpleNamespace(args=["--confirm-paid"])
    asyncio.run(bot.run_admin_video_pipeline_smoke(update, context, bot.VIDEO_SUBTITLE_MODE_CREATE))
    body = "\n".join(update.message.replies)
    assert "Status: BLOCKED" in body
    assert "Provider calls: 0" in body
    assert "Xu charged: 0" in body
    assert "asr,tts" in body
    assert any(rec[1] == "BLOCKED" for rec in saved)


def test_video_smoke_replies_terminal_fail_on_unexpected_exception(monkeypatch):
    async def boom(feature, params=None, context=None):
        raise RuntimeError("engine_exploded_unexpectedly")

    monkeypatch.setattr(bot, "execute_engine", boom)
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 22)
    saved = []
    monkeypatch.setattr(
        bot,
        "save_tool_test_result",
        lambda name, status, detail="", updated_by="": saved.append((str(name), str(status), str(detail))),
    )
    update = _fake_update()
    context = SimpleNamespace(args=["--confirm-paid"])
    asyncio.run(bot.run_admin_video_pipeline_smoke(update, context, bot.VIDEO_SUBTITLE_MODE_DUB))
    body = "\n".join(update.message.replies)
    assert "Status: FAIL" in body
    assert "Error class: RuntimeError" in body
    assert any(rec[1] == "FAIL" for rec in saved)


def test_video_smoke_passthrough_keeps_runner_result(monkeypatch):
    async def ok_engine(feature, params=None, context=None):
        return {"ok": True, "status": "PASS", "runner_result": {"ok": True, "marker": "ran"}}

    monkeypatch.setattr(bot, "execute_engine", ok_engine)
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 22)
    update = _fake_update()
    context = SimpleNamespace(args=["--confirm-paid"])
    result = asyncio.run(bot.run_admin_video_pipeline_smoke(update, context, bot.VIDEO_SUBTITLE_MODE_CREATE))
    assert result == {"ok": True, "marker": "ran"}


# ---------------------------------------------------------------------------
# Section I — well-formed gate reasons + job identification in debug view
# ---------------------------------------------------------------------------

def test_gate_matrix_reason_is_never_blocked_colon_ready(monkeypatch):
    _patch_settings_store(monkeypatch)
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "auto")
    access = {"status": "blocked_admin_missing_provider_config", "reason": "ready"}
    matrix = bot.video_dubbing_product_gate_matrix(
        22, bot.VIDEO_SUBTITLE_MODE_CREATE, {}, access=access, input_save={}
    )
    reason = str(matrix.get("provider_gate_reason") or "")
    assert reason.startswith("blocked_admin_missing_provider_config:")
    assert not reason.endswith(":ready")


def test_engine_access_block_reason_lists_missing_not_ready(monkeypatch):
    _patch_settings_store(monkeypatch)
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "auto")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    decision = bot.can_user_access_product_engine(
        22,
        bot.engine_feature_product_area("subtitle_asr"),
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        is_provider_call=True,
        is_paid_job=True,
        confirm_paid=True,
        state={},
    )
    if decision.get("status") == "blocked_admin_missing_provider_config":
        assert str(decision.get("reason") or "") not in {"", "ready"}


def test_debug_text_identifies_job_and_timestamps():
    job = {
        "internal_job_id": "abc123deadbeef",
        "job_id": "abc123deadbeef",
        "created_at": "2026-07-27T01:37:00+07:00",
        "updated_at": "2026-07-27T01:40:00+07:00",
        "status": "failed",
    }
    text = bot.subtitle_dub_debug_text(job)
    assert "abc123deadbeef" in text
    assert "job created at" in text
    assert "2026-07-27T01:37:00+07:00" in text
    assert "job updated at" in text


# ---------------------------------------------------------------------------
# Section C6 — permanent F821 guard on the SubDub surface
# ---------------------------------------------------------------------------

KNOWN_OUT_OF_SCOPE_F821 = {
    # Documented follow-up findings OUTSIDE SubDub scope (task list flagged to
    # the owner). A new symbol anywhere, or ANY hit inside a SubDub-surface
    # function, fails this guard.
    "context",
    "BASE_DIR",
    "member_profile",
    "scene_seconds",
    "invoice",
    "count",
    "duration",
}

SUBDUB_SURFACE_PATTERN = re.compile(
    r"subdub|video_dub|subtitle|translate|tool_test|smoke|dubbing", re.IGNORECASE
)


def test_no_f821_on_subdub_surface_permanent_guard():
    """RESTORE400 died on `_SUBDUB_BASE_RUN_FFMPEG_COMMAND`; the live smokes
    died on `resolve_translate_target` / `sanitize_public_copy`. Same disease.
    This guard makes the class of bug impossible to reintroduce silently:
    any F821 inside a SubDub-surface function — or any NEW undefined symbol
    anywhere in bot.py — fails the suite. TIMEOUT is reported as failure,
    never as clean."""
    ruff = shutil.which("ruff")
    if not ruff:
        for candidate_name in ("ruff.exe", "ruff"):
            candidate = Path(sys.executable).with_name(candidate_name)
            if candidate.exists():
                ruff = str(candidate)
                break
    if not ruff:
        pytest.skip("ruff not available (PATH or venv Scripts) — install ruff to enforce the F821 guard")
    bot_path = Path(bot.__file__)
    try:
        proc = subprocess.run(
            [ruff, "check", "--select", "F821", "--output-format", "concise", str(bot_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("ruff F821 sweep TIMEOUT after 300s — TIMEOUT is not CLEAN")
    source_lines = bot_path.read_text(encoding="utf-8").splitlines()
    top_level_defs = [
        (index + 1, line.strip())
        for index, line in enumerate(source_lines)
        if line.startswith("def ") or line.startswith("async def ")
    ]
    offenders = []
    for line in proc.stdout.splitlines():
        match = re.search(r":(\d+):\d+:\s+F821 Undefined name `([^`]+)`", line)
        if not match:
            continue
        lineno = int(match.group(1))
        symbol = match.group(2)
        containing = ""
        for def_line, def_text in top_level_defs:
            if def_line <= lineno:
                containing = def_text
            else:
                break
        on_subdub_surface = bool(SUBDUB_SURFACE_PATTERN.search(containing))
        if on_subdub_surface or symbol not in KNOWN_OUT_OF_SCOPE_F821:
            offenders.append((lineno, symbol, containing[:90]))
    assert not offenders, (
        "Undefined names on the SubDub surface (or new F821 findings) — "
        f"fix before merge: {offenders}"
    )
