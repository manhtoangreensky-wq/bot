"""Tests for Bot Realtime Adapter __main__ Binding, Product Flags & 2x SubDub Settlement."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sqlite3
import sys
import time
from pathlib import Path
from types import ModuleType

import httpx
from fastapi import FastAPI

from services.copyfast_realtime_translate import internal_router
from services.customer_read_model_service import read_canonical_wallet
from services.realtime_asr_adapter import (
    RealtimeASRAdapter,
    get_canonical_asr_primitive,
    set_canonical_asr_primitive,
)
from services.realtime_audio_ingress import SpeechSegment
from services.realtime_translation_adapter import (
    RealtimeTranslationAdapter,
    get_canonical_translation_primitive,
    set_canonical_translation_primitive,
)
from services.realtime_tts_adapter import (
    get_canonical_tts_primitive,
    set_canonical_tts_primitive,
)


def _signed_headers(*, path: str, body: bytes, actor_id: str, token: str, secret: str) -> dict[str, str]:
    ts = str(int(time.time()))
    req_id = "req_test_rt_settle_001"
    digest = hashlib.sha256(body).hexdigest()
    msg = f"{ts}.{req_id}.POST.{path}.{digest}.{actor_id}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return {
        "Authorization": f"Bearer {token}",
        "X-TOAN-AAS-Signature": sig,
        "X-TOAN-AAS-Timestamp": ts,
        "X-TOAN-AAS-Request-ID": req_id,
        "X-TOAN-AAS-Actor-ID": actor_id,
        "Content-Type": "application/json",
    }


def test_adapters_bind_main_module_and_pass_product_flags(monkeypatch):
    captured = {}

    async def fake_asr(audio_bytes, content_type="audio/wav", language="auto", *, allow_subdub_public=False, allow_confirmed_product=False):
        captured["asr"] = (allow_subdub_public, allow_confirmed_product)
        return {"ok": True, "text": "hello world", "language": "en", "provider": "test"}

    async def fake_translate(text, target_lang="vi", allow_admin=False, updated_by="", allow_confirmed_product=False):
        captured["translate"] = (allow_confirmed_product, target_lang)
        return {"text": "xin chào thế giới", "provider": "test"}

    async def fake_tts(text, voice_id=""):
        return ("PASS", b"mp3bytes", "ok", 0)

    fake_main = ModuleType("__main__")
    fake_main.asr_transcribe_audio = fake_asr
    fake_main.translate_subtitle_text = fake_translate
    fake_main.tts_edge_bytes = fake_tts

    monkeypatch.setitem(sys.modules, "__main__", fake_main)
    monkeypatch.delitem(sys.modules, "bot", raising=False)
    set_canonical_asr_primitive(None)
    set_canonical_translation_primitive(None)
    set_canonical_tts_primitive(None)

    async def _run():
        assert get_canonical_asr_primitive() is fake_asr
        assert get_canonical_translation_primitive() is fake_translate
        assert get_canonical_tts_primitive() is fake_tts

        seg = SpeechSegment(
            segment_id="seg_flag",
            sequence_start=1,
            sequence_end=1,
            start_ms=0,
            end_ms=200,
            pcm_bytes=b"\x10\x00" * 320,
        )
        asr_res = await RealtimeASRAdapter().transcribe(seg, language="en")
        assert asr_res.ok is True
        assert captured["asr"] == (True, True)

        tr_res = await RealtimeTranslationAdapter(target_language="vi").translate("hello world")
        assert tr_res.ok is True
        assert captured["translate"] == (True, "vi")

    try:
        asyncio.run(_run())
    finally:
        set_canonical_asr_primitive(None)
        set_canonical_translation_primitive(None)
        set_canonical_tts_primitive(None)


def test_realtime_2x_settlement_reconciles_with_credit_events(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "rt_settle.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, credits INTEGER DEFAULT 0, total_spent INTEGER DEFAULT 0, is_vip INTEGER DEFAULT 0, join_date TEXT, username TEXT, total_paid_vnd INTEGER DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE credit_events (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, delta INTEGER, balance_after INTEGER, event_type TEXT, ref_id TEXT, note TEXT, created_at TEXT)"
    )
    conn.execute("INSERT INTO users (user_id, credits, total_spent) VALUES ('99001122', 100, 0)")
    conn.execute(
        "INSERT INTO credit_events (user_id, delta, balance_after, event_type, ref_id, note, created_at) VALUES ('99001122', 100, 100, 'topup', 'init', 'seed', '2026-11-27 00:00:00')"
    )
    conn.commit()
    conn.close()

    token = "test-bridge-token-123456"
    secret = "test-bridge-hmac-1234567890"
    monkeypatch.setenv("DB_FILE", str(db_file))
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", token)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", secret)

    app = FastAPI()
    app.include_router(internal_router)
    transport = httpx.ASGITransport(app=app)

    async def _run():
        async with httpx.AsyncClient(transport=transport, base_url="http://bot.internal") as client:
            payload = {
                "session_id": "rts_live_001",
                "actor_id": "99001122",
                "idempotency_key": "rt:rts_live_001:blk:1",
                "mode": "LIVE_DUB_BILINGUAL",
                "char_count": 100,
                "block_count": 1,
                "audio_seconds": 6.0,
            }
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            headers = _signed_headers(path="/internal/v1/realtime/settle", body=body, actor_id="99001122", token=token, secret=secret)
            r1 = await client.post("/internal/v1/realtime/settle", content=body, headers=headers)
            assert r1.status_code == 200
            d1 = r1.json()
            assert d1["ok"] is True
            assert d1["base_subdub_xu"] == 20
            assert d1["amount_xu"] == 40
            assert d1["balance_before"] == 100
            assert d1["balance_after"] == 60
            assert d1["duplicate"] is False

            r2 = await client.post("/internal/v1/realtime/settle", content=body, headers=headers)
            assert r2.status_code == 200
            d2 = r2.json()
            assert d2["duplicate"] is True
            assert d2["balance_after"] == 60

            ok_w, wallet_res, _ = read_canonical_wallet("99001122", str(db_file))
            assert ok_w is True
            assert wallet_res["data"]["balance_xu"] == 60
            assert wallet_res["data"]["total_spent_xu"] == 40

            payload_fail = {
                "session_id": "rts_live_001",
                "actor_id": "99001122",
                "idempotency_key": "rt:rts_live_001:blk:2",
                "mode": "LIVE_DUB_BILINGUAL",
                "char_count": 200,
                "block_count": 1,
            }
            body_fail = json.dumps(payload_fail, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            h_fail = _signed_headers(path="/internal/v1/realtime/settle", body=body_fail, actor_id="99001122", token=token, secret=secret)
            r3 = await client.post("/internal/v1/realtime/settle", content=body_fail, headers=h_fail)
            assert r3.status_code == 402
            assert r3.json()["error_code"] == "INSUFFICIENT_FUNDS"

    asyncio.run(_run())
