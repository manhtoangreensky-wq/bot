"""Canonical Web App Realtime Gateway & WebSocket Router (RT-02 / RT-FIX1).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Account Authority: Strict authentication via require_account. No guest_user fallback.
2. Token Security: Fail-closed on missing REALTIME_STREAM_SECRET. Binds session_id, owner_id, device_id, expires_at, nonce.
3. Owner Isolation: Every REST route and WebSocket verifies session ownership (FOREIGN_OWNER_BLOCKED).
4. Full route family:
   - POST /api/v1/live-translate/sessions
   - GET  /api/v1/live-translate/sessions/{session_id}
   - POST /api/v1/live-translate/sessions/{session_id}/stop
   - GET  /api/v1/live-translate/sessions/{session_id}/export
   - WS   /api/v1/live-translate/sessions/{session_id}/stream
5. Monotonic sequence handling, server ACK, and reconnect support.
"""

from __future__ import annotations

import base64
import enum
import hashlib
import hmac
import io
import json
import logging
import math
import os
import struct
import time
import uuid
import wave
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    def Field(default=None, **kwargs):
        return default
    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.prefix = kwargs.get("prefix", "")
            self.tags = kwargs.get("tags", [])
            self.routes = []
        def post(self, path, *args, **kwargs):
            def decorator(f):
                self.routes.append(("POST", self.prefix + path, f))
                return f
            return decorator
        def get(self, path, *args, **kwargs):
            def decorator(f):
                self.routes.append(("GET", self.prefix + path, f))
                return f
            return decorator
        def websocket(self, path, *args, **kwargs):
            def decorator(f):
                self.routes.append(("WS", self.prefix + path, f))
                return f
            return decorator
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            super().__init__(f"{status_code}: {detail}")
            self.status_code = status_code
            self.detail = detail
    class WebSocketDisconnect(Exception):
        pass
    class Request: pass
    class WebSocket: pass
    def Query(default=None, **kwargs):
        return default
    def Depends(dependency=None):
        return dependency
    class _Status:
        HTTP_400_BAD_REQUEST = 400
        HTTP_401_UNAUTHORIZED = 401
        HTTP_403_FORBIDDEN = 403
        HTTP_404_NOT_FOUND = 404
        HTTP_500_INTERNAL_SERVER_ERROR = 500
    status = _Status()

try:
    from copyfast_auth import require_account
except Exception:
    def require_account(request: Request) -> dict:
        user_id = getattr(getattr(request, "state", None), "user_id", None)
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Yêu cầu đăng nhập tài khoản TOAN AAS")
        return {"id": user_id, "account_id": user_id, "role": "user"}

from services.realtime_asr_adapter import RealtimeASRAdapter
from services.realtime_audio_ingress import RealtimeAudioIngressBuffer, SpeechSegment
from services.realtime_translate_session import (
    PRICING_STATE,
    PRODUCTION_PAID_ADMISSION,
    PROCESS_RESTART_DURABILITY,
    RealtimeSessionConfig,
    RealtimeSessionState,
    RealtimeTranscriptSegment,
    RealtimeTranslateMode,
    RealtimeTranslateSession,
)
from services.realtime_translation_adapter import RealtimeTranslationAdapter
from services.realtime_tts_adapter import RealtimeTTSAdapter
from services.realtime_voice_resolution import RealtimeVoiceResolver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/live-translate", tags=["TOAN AAS Live Translate & Dub"])

# In-memory registry for active sessions
_ACTIVE_SESSIONS: Dict[str, RealtimeTranslateSession] = {}
_ACTIVE_INGRESS_BUFFERS: Dict[str, RealtimeAudioIngressBuffer] = {}

TOKEN_TTL_SECONDS: int = 300  # 5 minutes


def get_stream_secret() -> str:
    """Retrieves secret for signing stream tokens. FAILS CLOSED if not set."""
    secret = os.environ.get("REALTIME_STREAM_SECRET", "").strip()
    if not secret or len(secret) < 16:
        raise RuntimeError("REALTIME_STREAM_SECRET_NOT_CONFIGURED")
    return secret


def generate_stream_token(
    session_id: str,
    owner_id: str,
    device_id: str,
    expires_at: int,
    nonce: Optional[str] = None,
) -> str:
    secret = get_stream_secret()
    nonce_val = nonce or uuid.uuid4().hex[:8]
    payload = f"{session_id}:{owner_id}:{device_id}:{expires_at}:{nonce_val}"
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token_data = {
        "session_id": session_id,
        "owner_id": owner_id,
        "device_id": device_id,
        "exp": expires_at,
        "nonce": nonce_val,
        "sig": signature,
    }
    return base64.urlsafe_b64encode(json.dumps(token_data).encode("utf-8")).decode("ascii")


def verify_stream_token(token: str, session_id: str) -> Optional[Tuple[str, str]]:
    try:
        secret = get_stream_secret()
        token_clean = token.strip()
        trans = token_clean.replace("-", "+").replace("_", "/")
        raw_bytes = base64.b64decode(trans.encode("ascii"), validate=True)
        raw = raw_bytes.decode("utf-8")
        data = json.loads(raw)
        if data.get("session_id") != session_id:
            return None
        if time.time() > data.get("exp", 0):
            return None
        nonce_val = data.get("nonce", "")
        device_id = data.get("device_id", "")
        owner_id = data.get("owner_id", "")
        payload = f"{data['session_id']}:{owner_id}:{device_id}:{data['exp']}:{nonce_val}"
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(data.get("sig", ""), expected_sig):
            return str(owner_id), str(device_id)
    except Exception:
        return None
    return None


class CreateSessionRequest(BaseModel):
    source_language: str = Field(default="auto", description="Source audio language (e.g. en, zh, ja, auto)")
    target_language: str = Field(default="vi", description="Target translated language (e.g. vi)")
    mode: str = Field(default="LIVE_DUB_BILINGUAL", description="Mode: CAPTION_ONLY, CAPTION_TRANSLATE, LIVE_DUB, LIVE_DUB_BILINGUAL")
    voice_profile_id: Optional[str] = Field(default=None, description="Optional Voice Vault profile ID")
    gender_preference: Optional[str] = Field(default="male", description="male or female")
    device_id: Optional[str] = Field(default=None, description="Client device identifier")


class SessionResponse(BaseModel):
    ok: bool
    session_id: str
    stream_token: str
    websocket_url: str
    mode: str
    target_language: str


@router.post("/sessions", response_model=SessionResponse)
async def create_live_translate_session(
    req: CreateSessionRequest,
    request: Request,
    account: dict = Depends(require_account),
) -> SessionResponse:
    """Creates a new real-time translation session requiring authenticated account."""
    owner_id = str(account.get("id") or account.get("account_id") or "").strip()
    if not owner_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="CREATE_OWNER_AUTH: Invalid account identity")

    session_id = f"rts_{uuid.uuid4().hex[:12]}"
    device_id = req.device_id or f"dev_{uuid.uuid4().hex[:8]}"
    mode_enum = (
        RealtimeTranslateMode(req.mode)
        if req.mode in RealtimeTranslateMode._value2member_map_
        else RealtimeTranslateMode.LIVE_DUB_BILINGUAL
    )

    config = RealtimeSessionConfig(
        owner_id=owner_id,
        source_language=req.source_language,
        target_language=req.target_language,
        mode=mode_enum,
        voice_profile_id=req.voice_profile_id,
        gender_preference=req.gender_preference or "male",
        client_device_id=device_id,
    )

    session = RealtimeTranslateSession(session_id, config)
    _ACTIVE_SESSIONS[session_id] = session
    _ACTIVE_INGRESS_BUFFERS[session_id] = RealtimeAudioIngressBuffer()

    exp = int(time.time()) + TOKEN_TTL_SECONDS
    try:
        stream_token = generate_stream_token(session_id, owner_id, device_id, exp)
    except RuntimeError as e:
        logger.error(f"Failed to generate stream token (fail closed): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server stream security configuration missing")

    ws_url = f"/api/v1/live-translate/sessions/{session_id}/stream?token={stream_token}"

    return SessionResponse(
        ok=True,
        session_id=session_id,
        stream_token=stream_token,
        websocket_url=ws_url,
        mode=mode_enum.value,
        target_language=req.target_language,
    )


@router.get("/sessions/{session_id}")
async def get_session_status(
    session_id: str,
    account: dict = Depends(require_account),
) -> Dict[str, Any]:
    """Retrieves session metadata, enforcing owner isolation (STATUS_OWNER_AUTH)."""
    owner_id = str(account.get("id") or account.get("account_id") or "").strip()
    session = _ACTIVE_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if str(session.config.owner_id) != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: session belongs to another owner")
    return {"ok": True, **session.to_dict()}


@router.post("/sessions/{session_id}/stop")
async def stop_session(
    session_id: str,
    account: dict = Depends(require_account),
) -> Dict[str, Any]:
    """Idempotently stops a session, enforcing owner isolation (STOP_OWNER_AUTH)."""
    owner_id = str(account.get("id") or account.get("account_id") or "").strip()
    session = _ACTIVE_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if str(session.config.owner_id) != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: session belongs to another owner")

    session.end()
    _ACTIVE_INGRESS_BUFFERS.pop(session_id, None)
    return {"ok": True, "session_id": session_id, "state": session.state.value}


@router.get("/sessions/{session_id}/export")
async def export_session_subtitles(
    session_id: str,
    format: str = Query("srt", regex="^(srt|vtt)$"),
    account: dict = Depends(require_account),
) -> Dict[str, Any]:
    """Exports transcript as SRT or WebVTT subtitles, enforcing owner scope (EXPORT_OWNER_AUTH)."""
    owner_id = str(account.get("id") or account.get("account_id") or "").strip()
    session = _ACTIVE_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if str(session.config.owner_id) != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: session belongs to another owner")

    content = session.export_srt(owner_id) if format == "srt" else session.export_vtt(owner_id)
    return {"ok": True, "format": format, "content": content}


@router.websocket("/sessions/{session_id}/stream")
async def websocket_live_stream(websocket: WebSocket, session_id: str, token: str = Query(...)):
    """WebSocket bidirectional live streaming route for audio and subtitles.

    Enforces:
    1. WS_OWNER_AUTH: Valid stream token signature and expiration.
    2. TOKEN_OWNER_ID == SESSION_OWNER_ID verification.
    3. Monotonic sequence deduplication and server ACK.
    4. Client reconnect handling.
    """
    token_res = verify_stream_token(token, session_id)
    if not token_res:
        await websocket.close(code=4401, reason="Unauthorized or invalid stream token")
        return
    token_owner_id, token_device_id = token_res

    session = _ACTIVE_SESSIONS.get(session_id)
    ingress = _ACTIVE_INGRESS_BUFFERS.get(session_id)
    if not session or not ingress:
        await websocket.close(code=4404, reason="Session not found")
        return

    # Verify TOKEN_OWNER_ID == SESSION_OWNER_ID
    if str(token_owner_id) != str(session.config.owner_id):
        await websocket.close(code=4403, reason="Forbidden: token owner mismatch")
        return

    await websocket.accept()
    session.start()

    asr_adapter = RealtimeASRAdapter()
    translation_adapter = RealtimeTranslationAdapter(target_language=session.config.target_language)
    voice_resolver = RealtimeVoiceResolver()
    tts_adapter = RealtimeTTSAdapter()
    resolved_voice = voice_resolver.resolve(
        target_language=session.config.target_language,
        gender_preference=session.config.gender_preference,
        voice_profile_id=session.config.voice_profile_id,
        owner_id=session.config.owner_id,
    )

    try:
        await websocket.send_json({
            "type": "session.ready",
            "session_id": session_id,
            "mode": session.config.mode.value,
            "target_language": session.config.target_language,
            "last_ack_seq": session.last_ack_seq,
        })

        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                raw = message["bytes"]
                if len(raw) < 4:
                    continue

                seq = struct.unpack("<I", raw[:4])[0]
                pcm_bytes = raw[4:]
                chunk_dur_ms = int((len(pcm_bytes) / 32000) * 1000)

                if not session.accept_audio_sequence(seq, duration_ms=chunk_dur_ms):
                    await websocket.send_json({"type": "ack", "seq": seq, "status": "duplicate_ignored"})
                    continue

                completed_segments = ingress.push_chunk(seq=seq, pcm_bytes=pcm_bytes)

                for speech_seg in completed_segments:
                    asr_res = await asr_adapter.transcribe(speech_seg, language=session.config.source_language)
                    if not asr_res.ok or not asr_res.text.strip():
                        continue

                    await websocket.send_json({
                        "type": "stt.final",
                        "segment_id": speech_seg.segment_id,
                        "seq": seq,
                        "start_ms": speech_seg.start_ms,
                        "end_ms": speech_seg.end_ms,
                        "text": asr_res.text,
                    })

                    trans_text = ""
                    if session.config.mode != RealtimeTranslateMode.CAPTION_ONLY:
                        trans_res = await translation_adapter.translate(asr_res.text, target_language=session.config.target_language)
                        if trans_res.ok:
                            trans_text = trans_res.translated_text
                            await websocket.send_json({
                                "type": "translation.final",
                                "segment_id": speech_seg.segment_id,
                                "seq": seq,
                                "source_text": asr_res.text,
                                "translated_text": trans_text,
                                "start_ms": speech_seg.start_ms,
                                "end_ms": speech_seg.end_ms,
                            })

                    tts_b64 = None
                    if session.config.mode in (RealtimeTranslateMode.LIVE_DUB, RealtimeTranslateMode.LIVE_DUB_BILINGUAL) and trans_text:
                        tts_res = await tts_adapter.synthesize(trans_text, resolved_voice)
                        if tts_res.ok and tts_res.audio_base64:
                            tts_b64 = tts_res.audio_base64
                            await websocket.send_json({
                                "type": "tts.audio",
                                "segment_id": speech_seg.segment_id,
                                "seq": seq,
                                "format": tts_res.format,
                                "duration_ms": tts_res.duration_ms,
                                "audio_base64": tts_b64,
                            })

                    transcript_seg = RealtimeTranscriptSegment(
                        segment_id=speech_seg.segment_id,
                        sequence=seq,
                        start_ms=speech_seg.start_ms,
                        end_ms=speech_seg.end_ms,
                        source_text=asr_res.text,
                        translated_text=trans_text,
                        is_final=True,
                        tts_audio_base64=tts_b64,
                    )
                    session.add_segment(transcript_seg)

                ack_seq = session.mark_sequence_processed(seq)
                await websocket.send_json({"type": "ack", "seq": ack_seq})

                new_blocks = session.compute_pending_metering_blocks()
                if new_blocks > 0:
                    settlement = session.settle_blocks(new_blocks, xu_per_block=0)
                    await websocket.send_json({
                        "type": "usage.updated",
                        **settlement,
                    })

            elif "text" in message and message["text"]:
                try:
                    ctrl = json.loads(message["text"])
                    msg_type = ctrl.get("type", "")
                    if msg_type == "session.reconnect":
                        client_last_ack = int(ctrl.get("last_ack_seq", 0))
                        recon_info = session.handle_reconnect(client_last_ack)
                        await websocket.send_json({"type": "session.reconnected", **recon_info})
                    elif msg_type == "session.control":
                        action = ctrl.get("action", "").lower()
                        if action == "pause":
                            session.pause()
                            await websocket.send_json({"type": "session.state", "state": "paused"})
                        elif action == "resume":
                            session.resume()
                            await websocket.send_json({"type": "session.state", "state": "active"})
                        elif action == "stop":
                            session.end()
                            await websocket.send_json({"type": "session.state", "state": "ended"})
                            break
                except Exception as e:
                    logger.warning(f"Error handling control message: {e}")

    except WebSocketDisconnect:
        logger.info(f"Session {session_id} WebSocket disconnected.")
    except Exception as e:
        logger.error(f"Session {session_id} unexpected error: {e}")
        session.fail(str(e))
    finally:
        session.end()
        _ACTIVE_INGRESS_BUFFERS.pop(session_id, None)
