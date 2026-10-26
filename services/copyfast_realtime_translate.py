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
        HTTP_402_PAYMENT_REQUIRED = 402
        HTTP_403_FORBIDDEN = 403
        HTTP_404_NOT_FOUND = 404
        HTTP_422_UNPROCESSABLE_ENTITY = 422
        HTTP_500_INTERNAL_SERVER_ERROR = 500
        HTTP_503_SERVICE_UNAVAILABLE = 503
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
    test_bypass_pricing: Optional[bool] = Field(default=False, description="Explicit test bypass for provider-free CI only")


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

    mode_enum = (
        RealtimeTranslateMode(req.mode)
        if req.mode in RealtimeTranslateMode._value2member_map_
        else RealtimeTranslateMode.LIVE_DUB_BILINGUAL
    )

    # PRICING ADMISSION CHECK (Owner decision unresolved -> fail closed on production)
    is_test_bypass = bool(
        getattr(req, "test_bypass_pricing", False)
        or os.environ.get("REALTIME_ALLOW_UNPRICED_TEST_SESSION") == "1"
    )
    if PRODUCTION_PAID_ADMISSION == "FAIL_CLOSED" and not is_test_bypass:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"PRICING_NOT_CONFIGURED: Production paid admission for mode '{mode_enum.value}' is blocked until Owner pricing decision.",
        )

    session_id = f"rts_{uuid.uuid4().hex[:12]}"
    device_id = req.device_id or f"dev_{uuid.uuid4().hex[:8]}"

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
    format: str = Query("srt", pattern="^(srt|vtt)$"),
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
                    await websocket.send_json(session.get_telemetry_usage())

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


# ==============================================================================
# INTERNAL REALTIME EXECUTION SURFACE (BOT-OWNED ASR, TRANSLATE, TTS, VAULT)
# ==============================================================================

internal_router = APIRouter(prefix="/internal/v1/realtime", tags=["Realtime Internal"])


def verify_internal_realtime_bridge_auth(
    authorization: str = "",
    signature: str = "",
    timestamp: str = "",
    request_id: str = "",
    method: str = "POST",
    path: str = "/internal/v1/realtime/process-chunk",
    body_bytes: bytes = b"",
    actor_id: str = "",
    token_override: Optional[str] = None,
    secret_override: Optional[str] = None,
    clock_skew_seconds: int = 300,
) -> Tuple[bool, str, int]:
    """Verifies incoming Web-to-Bot Core Bridge request credentials and HMAC signature."""
    bridge_token = (
        token_override
        if token_override is not None
        else (
            os.environ.get("CORE_BRIDGE_TOKEN", "").strip()
            or os.environ.get("INTERNAL_API_SECRET", "").strip()
            or os.environ.get("BOT_INTERNAL_SECRET", "").strip()
        )
    )
    hmac_secret = (
        secret_override
        if secret_override is not None
        else (
            os.environ.get("CORE_BRIDGE_HMAC_SECRET", "").strip()
            or os.environ.get("INTERNAL_API_SECRET", "").strip()
            or os.environ.get("BOT_INTERNAL_SECRET", "").strip()
        )
    )

    if not bridge_token:
        return False, "BRIDGE_NOT_CONFIGURED", 503

    raw_auth = str(authorization or "").strip()
    if not raw_auth:
        return False, "AUTH_MISSING", 401

    bearer = (
        raw_auth.replace("Bearer ", "", 1).strip()
        if raw_auth.lower().startswith("bearer ")
        else raw_auth
    )
    if not bearer or not hmac.compare_digest(bearer, bridge_token):
        return False, "AUTH_INVALID", 401

    clean_actor = str(actor_id or "").strip()
    if not clean_actor:
        return False, "ACTOR_ID_REQUIRED", 401

    if hmac_secret:
        clean_sig = str(signature or "").strip()
        clean_ts = str(timestamp or "").strip()
        clean_req_id = str(request_id or "").strip()

        if not clean_sig or not clean_ts or not clean_req_id:
            return False, "SIGNATURE_MISSING", 401

        try:
            ts_int = int(clean_ts)
            current_ts = int(time.time())
            if abs(current_ts - ts_int) > clock_skew_seconds:
                return False, "TIMESTAMP_OUT_OF_BOUNDS", 401
        except (ValueError, TypeError):
            return False, "INVALID_TIMESTAMP", 401

        digest = hashlib.sha256(body_bytes).hexdigest()
        msg = f"{clean_ts}.{clean_req_id}.{method.upper()}.{path}.{digest}.{clean_actor}".encode("utf-8")
        expected_sig = hmac.new(hmac_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(clean_sig, expected_sig):
            return False, "SIGNATURE_INVALID", 401

    return True, "OK", 200


class ProcessChunkRequest(BaseModel):
    session_id: str = Field(description="Realtime session ID")
    actor_id: str = Field(description="Authenticated owner/actor ID")
    sequence: int = Field(description="Audio chunk sequence number")
    segment_id: str = Field(description="Unique segment ID")
    pcm_bytes_b64: str = Field(default="", description="Base64-encoded PCM16 audio bytes")
    start_ms: int = Field(default=0, description="Segment start timestamp in ms")
    end_ms: int = Field(default=0, description="Segment end timestamp in ms")
    source_language: str = Field(default="auto", description="Source audio language")
    target_language: str = Field(default="vi", description="Target translated language")
    mode: str = Field(default="LIVE_DUB_BILINGUAL", description="Mode: CAPTION_ONLY, CAPTION_TRANSLATE, LIVE_DUB, LIVE_DUB_BILINGUAL")
    voice_profile_id: Optional[str] = Field(default=None, description="Optional Voice Vault profile ID")
    gender_preference: Optional[str] = Field(default="male", description="Preferred gender fallback")
    voice_vault_data: Optional[Dict[str, Any]] = Field(default=None, description="Optional test profile data")


@internal_router.post("/process-chunk")
async def internal_process_realtime_chunk(
    req: ProcessChunkRequest,
    request: Request,
) -> Dict[str, Any]:
    """Production internal execution endpoint for processing a realtime audio chunk.

    Requires Core Bridge Bearer token and HMAC signature with actor_id.
    Executes canonical Bot STT, Translation, TTS, and owner-scoped Voice Vault resolution.
    Returns canonical Bot-shaped events: stt.final, translation.final, tts.audio.
    """
    raw_body = b""
    try:
        if hasattr(request, "body"):
            body_res = request.body()
            if asyncio.iscoroutine(body_res):
                raw_body = await body_res
            else:
                raw_body = body_res or b""
    except Exception:
        raw_body = b""

    if not raw_body:
        payload_dict = {
            "session_id": req.session_id,
            "actor_id": req.actor_id,
            "sequence": req.sequence,
            "segment_id": req.segment_id,
            "pcm_bytes_b64": req.pcm_bytes_b64,
            "start_ms": req.start_ms,
            "end_ms": req.end_ms,
            "source_language": req.source_language,
            "target_language": req.target_language,
            "mode": req.mode,
            "voice_profile_id": req.voice_profile_id,
            "gender_preference": req.gender_preference,
        }
        raw_body = json.dumps(payload_dict, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    req_headers = getattr(request, "headers", {})
    auth_header = req_headers.get("authorization", "")
    sig_header = req_headers.get("x-toan-aas-signature", "")
    ts_header = req_headers.get("x-toan-aas-timestamp", "")
    req_id_header = req_headers.get("x-toan-aas-request-id", "")
    actor_header = str(req_headers.get("x-toan-aas-actor-id") or req.actor_id or "").strip()

    auth_ok, auth_err, auth_status = verify_internal_realtime_bridge_auth(
        authorization=auth_header,
        signature=sig_header,
        timestamp=ts_header,
        request_id=req_id_header,
        method="POST",
        path="/internal/v1/realtime/process-chunk",
        body_bytes=raw_body,
        actor_id=actor_header,
    )
    if not auth_ok:
        raise HTTPException(
            status_code=auth_status,
            detail=f"Bridge auth failed: {auth_err}",
        )

    # Actor match
    if str(req.actor_id).strip() != actor_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Actor ID mismatch between body and header",
        )

    # Decode PCM
    pcm_bytes = b""
    if req.pcm_bytes_b64:
        try:
            pcm_bytes = base64.b64decode(req.pcm_bytes_b64)
        except Exception:
            pcm_bytes = b""

    # Voice Resolution
    resolver = RealtimeVoiceResolver()
    resolved_voice = resolver.resolve(
        target_language=req.target_language,
        gender_preference=req.gender_preference or "male",
        voice_profile_id=req.voice_profile_id,
        owner_id=req.actor_id,
        voice_vault_data=req.voice_vault_data,
    )

    if req.voice_profile_id and resolved_voice.validation_status != "valid":
        status_code = status.HTTP_403_FORBIDDEN if resolved_voice.error_code == "FOREIGN_PROFILE_BLOCKED" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(
            status_code=status_code,
            detail=f"Voice profile validation failed: {resolved_voice.error_code}",
        )

    speech_seg = SpeechSegment(
        segment_id=req.segment_id,
        sequence_start=req.sequence,
        sequence_end=req.sequence,
        start_ms=req.start_ms,
        end_ms=req.end_ms,
        pcm_bytes=pcm_bytes,
        is_silence=False,
    )

    # 1. Canonical ASR
    asr_adapter = RealtimeASRAdapter()
    asr_res = await asr_adapter.transcribe(speech_seg, language=req.source_language)
    source_text = asr_res.text if asr_res.ok else ""

    events: List[Dict[str, Any]] = [
        {
            "type": "stt.final",
            "segment_id": req.segment_id,
            "sequence": req.sequence,
            "source_text": source_text,
            "language": asr_res.language,
        }
    ]

    # 2. Canonical Translation
    mode_str = req.mode.upper() if req.mode else "LIVE_DUB_BILINGUAL"
    translated_text = ""
    if mode_str in ("CAPTION_TRANSLATE", "LIVE_DUB", "LIVE_DUB_BILINGUAL"):
        trans_adapter = RealtimeTranslationAdapter(target_language=req.target_language)
        trans_res = await trans_adapter.translate(source_text, target_language=req.target_language)
        translated_text = trans_res.translated_text if trans_res.ok else source_text
        events.append({
            "type": "translation.final",
            "segment_id": req.segment_id,
            "sequence": req.sequence,
            "source_text": source_text,
            "translated_text": translated_text,
            "target_language": req.target_language,
        })

    # 3. Canonical TTS
    if mode_str in ("LIVE_DUB", "LIVE_DUB_BILINGUAL"):
        tts_adapter = RealtimeTTSAdapter()
        tts_res = await tts_adapter.synthesize(translated_text, voice=resolved_voice)
        events.append({
            "type": "tts.audio",
            "segment_id": req.segment_id,
            "sequence": req.sequence,
            "audio_b64": tts_res.audio_base64 or "",
            "format": tts_res.format,
            "sample_rate": getattr(tts_res, "sample_rate", 24000),
        })

    return {
        "ok": True,
        "session_id": req.session_id,
        "sequence": req.sequence,
        "segment_id": req.segment_id,
        "events": events,
    }
