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

import asyncio
import base64
import enum
import hashlib
import hmac
import inspect
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


_TEST_PRICING_ADMISSION_OVERRIDE: Optional[Callable[[RealtimeTranslateMode], bool]] = None


def set_test_pricing_admission_override(override: Optional[Callable[[RealtimeTranslateMode], bool]]) -> None:
    """Sets a server-side test authority for pricing admission in provider-free tests."""
    global _TEST_PRICING_ADMISSION_OVERRIDE
    _TEST_PRICING_ADMISSION_OVERRIDE = override


def is_pricing_admission_allowed(mode: RealtimeTranslateMode) -> bool:
    """Determines whether realtime session admission is allowed.

    Fails closed on production paid modes until Owner approves prices.
    Never allows environment or client bypass in production environment.
    """
    if PRODUCTION_PAID_ADMISSION != "FAIL_CLOSED":
        return True

    env_name = (
        os.environ.get("ENV")
        or os.environ.get("ENVIRONMENT")
        or os.environ.get("TOAN_AAS_ENV")
        or ""
    ).lower()
    is_production = env_name in ("production", "prod", "live")
    if is_production:
        return False

    if _TEST_PRICING_ADMISSION_OVERRIDE is not None:
        return bool(_TEST_PRICING_ADMISSION_OVERRIDE(mode))

    is_test_env = (
        os.environ.get("ENV") == "test"
        or os.environ.get("TESTING") == "1"
        or os.environ.get("CI") == "true"
        or os.environ.get("PYTEST_CURRENT_TEST") is not None
    )
    if is_test_env and os.environ.get("REALTIME_ALLOW_UNPRICED_TEST_SESSION") == "1":
        return True

    return False


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

    mode_enum = (
        RealtimeTranslateMode(req.mode)
        if req.mode in RealtimeTranslateMode._value2member_map_
        else RealtimeTranslateMode.LIVE_DUB_BILINGUAL
    )

    # PRICING ADMISSION CHECK (Owner decision unresolved -> fail closed on production)
    if not is_pricing_admission_allowed(mode_enum):
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
    clock_skew_seconds: Optional[int] = None,
) -> Tuple[bool, str, int]:
    """Verifies incoming Web-to-Bot Core Bridge request credentials and HMAC signature."""
    max_skew = (
        clock_skew_seconds
        if clock_skew_seconds is not None
        else int(os.environ.get("CORE_BRIDGE_CLOCK_SKEW", "300"))
    )
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

    if not hmac_secret:
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

    clean_sig = str(signature or "").strip()
    clean_ts = str(timestamp or "").strip()
    clean_req_id = str(request_id or "").strip()

    if not clean_sig or not clean_ts or not clean_req_id:
        return False, "SIGNATURE_MISSING", 401

    try:
        ts_int = int(clean_ts)
        current_ts = int(time.time())
        if abs(current_ts - ts_int) > max_skew:
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
            if inspect.isawaitable(body_res):
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
            detail="ACTOR_BODY_HEADER_MISMATCH",
        )

    # Decode PCM
    pcm_bytes = b""
    if req.pcm_bytes_b64:
        try:
            pcm_bytes = base64.b64decode(req.pcm_bytes_b64)
        except Exception:
            pcm_bytes = b""

    # Voice Resolution
    clean_voice_id = str(req.voice_profile_id or "").strip() or None
    resolver = RealtimeVoiceResolver()
    resolved_voice = resolver.resolve(
        target_language=req.target_language,
        gender_preference=req.gender_preference or "male",
        voice_profile_id=clean_voice_id,
        owner_id=req.actor_id,
    )

    if clean_voice_id and resolved_voice.validation_status != "valid":
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
        tts_ev: Dict[str, Any] = {
            "type": "tts.audio",
            "segment_id": req.segment_id,
            "sequence": req.sequence,
            "audio_b64": tts_res.audio_base64 or "",
            "format": tts_res.format,
            "sample_rate": getattr(tts_res, "sample_rate", 24000),
        }
        if not tts_res.ok and tts_res.error:
            tts_ev["error"] = str(tts_res.error)[:240]
        events.append(tts_ev)

    return {
        "ok": True,
        "session_id": req.session_id,
        "sequence": req.sequence,
        "segment_id": req.segment_id,
        "events": events,
    }


class RealtimeSettleRequest(BaseModel):
    session_id: str = Field(description="Realtime session ID")
    actor_id: str = Field(description="Authenticated canonical owner/actor ID")
    idempotency_key: str = Field(description="Unique deterministic idempotency key for this charge unit")
    mode: str = Field(default="LIVE_DUB_BILINGUAL", description="Realtime mode")
    char_count: int = Field(default=0, ge=0, description="Translated/spoken characters in this billable slice")
    block_count: int = Field(default=0, ge=0, description="Billable time blocks in this slice")
    audio_seconds: float = Field(default=0.0, ge=0.0, description="Processed audio seconds")
    voice_profile_id: Optional[str] = Field(default=None, description="Optional custom voice profile ID")
    is_final: bool = Field(default=False, description="Whether this is final stop settlement")


def _resolve_bot_db_path() -> str:
    import sys
    bot_mod = sys.modules.get("bot") or sys.modules.get("__main__")
    bot_db = getattr(bot_mod, "DB_FILE", None) if bot_mod is not None else None
    return (
        os.environ.get("DB_FILE", "").strip()
        or os.environ.get("DB_PATH", "").strip()
        or (str(bot_db).strip() if bot_db else "")
        or "toandaas_system.db"
    )


def _now_bot_text() -> str:
    import sys
    from datetime import datetime, timezone
    bot_mod = sys.modules.get("bot") or sys.modules.get("__main__")
    now_fn = getattr(bot_mod, "now_text", None) if bot_mod is not None else None
    if callable(now_fn):
        try:
            return str(now_fn())
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _calculate_realtime_2x_subdub_charge(
    *,
    mode: str,
    char_count: int,
    block_count: int,
    voice_profile_id: Optional[str] = None,
) -> Tuple[int, int, str]:
    """Calculates canonical 2x SubDub fee from Bot authority without cold module re-imports.

    Returns (amount_xu, base_subdub_xu, mapped_subdub_mode).
    """
    import sys
    from services.web_subdub_settlement_service import (
        DEFAULT_DUB_CUSTOM_RATE_XU,
        DEFAULT_DUB_PRESET_RATE_XU,
        DEFAULT_SUBTITLE_TRANSLATE_RATE_XU,
        calculate_subdub_char_price,
    )

    clean_mode = str(mode or "LIVE_DUB_BILINGUAL").strip().upper()
    subdub_mode_map = {
        "CAPTION_ONLY": "subtitle_translate",
        "CAPTION_TRANSLATE": "subtitle_translate",
        "LIVE_DUB": "dub",
        "LIVE_DUB_BILINGUAL": "subtitle_plus_dub",
    }
    mapped_mode = subdub_mode_map.get(clean_mode, "subtitle_plus_dub")
    clean_chars = max(0, int(char_count or 0))
    clean_blocks = max(0, int(block_count or 0))
    clean_voice = str(voice_profile_id or "").strip() or None

    if clean_chars == 0 and clean_blocks == 0:
        return 0, 0, mapped_mode

    if clean_chars > 0:
        translate_rate = DEFAULT_SUBTITLE_TRANSLATE_RATE_XU
        dub_preset_rate = DEFAULT_DUB_PRESET_RATE_XU
        dub_custom_rate = DEFAULT_DUB_CUSTOM_RATE_XU
        bot_mod = sys.modules.get("bot") or sys.modules.get("__main__")
        if bot_mod is not None and callable(getattr(bot_mod, "canonical_price_xu", None)):
            try:
                t_rate = bot_mod.canonical_price_xu("subtitle_translate_video")
                if t_rate:
                    translate_rate = float(t_rate)
                d_rate = bot_mod.canonical_price_xu("dub_video")
                if d_rate:
                    dub_preset_rate = float(d_rate)
                c_rate = bot_mod.canonical_price_xu("voice_clone_custom")
                if c_rate:
                    dub_custom_rate = float(c_rate)
            except Exception:
                pass
        effective_dub_rate = dub_custom_rate if clean_voice else dub_preset_rate
        if mapped_mode == "subtitle_translate":
            base_xu = max(1, int(calculate_subdub_char_price(clean_chars, translate_rate)["total_xu"]))
        elif mapped_mode == "dub":
            base_xu = max(1, int(calculate_subdub_char_price(clean_chars, effective_dub_rate)["total_xu"]))
        else:
            t_xu = int(calculate_subdub_char_price(clean_chars, translate_rate)["total_xu"])
            d_xu = int(calculate_subdub_char_price(clean_chars, effective_dub_rate)["total_xu"])
            base_xu = max(1, t_xu + d_xu)
        return base_xu * 2, base_xu, mapped_mode

    # Duration/block fallback when block elapsed before char reporting: 2 Xu / block (2x base)
    base_xu = max(1, clean_blocks)
    return base_xu * 2, base_xu, mapped_mode


@internal_router.post("/settle")
async def internal_settle_realtime_usage(
    req: RealtimeSettleRequest,
    request: Request,
) -> Dict[str, Any]:
    """Atomic, idempotent 2x-SubDub settlement in canonical Bot SQLite ledger."""
    import sqlite3
    from fastapi.responses import JSONResponse
    from services.customer_read_model_service import normalize_target_user_id
    from services.web_subdub_settlement_service import is_admin_or_owner_user

    raw_body = b""
    try:
        if hasattr(request, "body"):
            body_res = request.body()
            raw_body = await body_res if inspect.isawaitable(body_res) else (body_res or b"")
    except Exception:
        raw_body = b""

    if not raw_body:
        raw_body = json.dumps(
            {
                "session_id": req.session_id,
                "actor_id": req.actor_id,
                "idempotency_key": req.idempotency_key,
                "mode": req.mode,
                "char_count": req.char_count,
                "block_count": req.block_count,
                "audio_seconds": req.audio_seconds,
                "voice_profile_id": req.voice_profile_id,
                "is_final": req.is_final,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    req_headers = getattr(request, "headers", {})
    actor_header = str(req_headers.get("x-toan-aas-actor-id") or req.actor_id or "").strip()
    auth_ok, auth_err, auth_status = verify_internal_realtime_bridge_auth(
        authorization=req_headers.get("authorization", ""),
        signature=req_headers.get("x-toan-aas-signature", ""),
        timestamp=req_headers.get("x-toan-aas-timestamp", ""),
        request_id=req_headers.get("x-toan-aas-request-id", ""),
        method="POST",
        path="/internal/v1/realtime/settle",
        body_bytes=raw_body,
        actor_id=actor_header,
    )
    if not auth_ok:
        raise HTTPException(status_code=auth_status, detail=f"Bridge auth failed: {auth_err}")

    if str(req.actor_id).strip() != actor_header:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ACTOR_BODY_HEADER_MISMATCH")

    clean_uid = normalize_target_user_id(req.actor_id)
    if not clean_uid:
        return JSONResponse(status_code=400, content={"ok": False, "error_code": "INVALID_USER_ID", "message": "Thiếu ID tài khoản canonical."})

    amount_xu, base_subdub_xu, mapped_mode = _calculate_realtime_2x_subdub_charge(
        mode=req.mode,
        char_count=req.char_count,
        block_count=req.block_count,
        voice_profile_id=req.voice_profile_id,
    )
    clean_idemp = str(req.idempotency_key or "").strip()
    if not clean_idemp:
        return JSONResponse(status_code=400, content={"ok": False, "error_code": "IDEMPOTENCY_KEY_REQUIRED", "message": "Thiếu mã idempotency thanh toán realtime."})

    db_path = _resolve_bot_db_path()
    conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_realtime_settlements (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE NOT NULL,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                subdub_mode TEXT NOT NULL,
                char_count INTEGER NOT NULL,
                block_count INTEGER NOT NULL,
                base_subdub_xu INTEGER NOT NULL,
                amount_xu INTEGER NOT NULL,
                balance_before INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                status TEXT NOT NULL,
                settled_at TEXT NOT NULL
            )
            """
        )

        existing = conn.execute(
            """
            SELECT id, user_id, mode, char_count, block_count, base_subdub_xu, amount_xu,
                   balance_before, balance_after, status, settled_at
            FROM web_realtime_settlements
            WHERE idempotency_key = ?
            """,
            (clean_idemp,),
        ).fetchone()
        if existing:
            conn.execute("COMMIT")
            return {
                "ok": True,
                "duplicate": True,
                "settlement_id": existing[0],
                "canonical_user_id": existing[1],
                "mode": existing[2],
                "char_count": existing[3],
                "block_count": existing[4],
                "base_subdub_xu": existing[5],
                "amount_xu": existing[6],
                "balance_before": existing[7],
                "balance_after": existing[8],
                "status": existing[9],
                "settled_at": existing[10],
            }

        user_row = conn.execute(
            "SELECT credits, COALESCE(total_spent, 0) FROM users WHERE user_id = ?",
            (clean_uid,),
        ).fetchone()
        if not user_row:
            conn.execute("ROLLBACK")
            return JSONResponse(
                status_code=404,
                content={
                    "ok": False,
                    "error_code": "BOT_USER_NOT_INITIALIZED",
                    "message": "Tài khoản chưa kích hoạt ví trên Bot canonical.",
                },
            )

        current_balance = int(user_row[0] or 0)
        current_spent = int(user_row[1] or 0)
        now_str = _now_bot_text()
        settlement_id = f"rts_{uuid.uuid4().hex[:16]}"

        if amount_xu <= 0:
            conn.execute(
                """
                INSERT INTO web_realtime_settlements (
                    id, idempotency_key, session_id, user_id, mode, subdub_mode,
                    char_count, block_count, base_subdub_xu, amount_xu,
                    balance_before, balance_after, status, settled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'no_billable_usage', ?)
                """,
                (
                    settlement_id, clean_idemp, req.session_id, clean_uid,
                    str(req.mode), mapped_mode, int(req.char_count), int(req.block_count),
                    base_subdub_xu, current_balance, current_balance, now_str,
                ),
            )
            conn.execute("COMMIT")
            return {
                "ok": True,
                "duplicate": False,
                "status": "no_billable_usage",
                "settlement_id": settlement_id,
                "canonical_user_id": clean_uid,
                "amount_xu": 0,
                "base_subdub_xu": base_subdub_xu,
                "balance_before": current_balance,
                "balance_after": current_balance,
            }

        if is_admin_or_owner_user(clean_uid):
            conn.execute(
                """
                INSERT INTO web_realtime_settlements (
                    id, idempotency_key, session_id, user_id, mode, subdub_mode,
                    char_count, block_count, base_subdub_xu, amount_xu,
                    balance_before, balance_after, status, settled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'exempt', ?)
                """,
                (
                    settlement_id, clean_idemp, req.session_id, clean_uid,
                    str(req.mode), mapped_mode, int(req.char_count), int(req.block_count),
                    base_subdub_xu, current_balance, current_balance, now_str,
                ),
            )
            conn.execute("COMMIT")
            return {
                "ok": True,
                "duplicate": False,
                "exempt": True,
                "status": "exempt",
                "settlement_id": settlement_id,
                "canonical_user_id": clean_uid,
                "amount_xu": 0,
                "quoted_2x_xu": amount_xu,
                "base_subdub_xu": base_subdub_xu,
                "balance_before": current_balance,
                "balance_after": current_balance,
            }

        if current_balance < amount_xu:
            conn.execute("ROLLBACK")
            return JSONResponse(
                status_code=402,
                content={
                    "ok": False,
                    "error_code": "INSUFFICIENT_FUNDS",
                    "message": f"Số dư ({current_balance} Xu) không đủ thanh toán {amount_xu} Xu cho phiên Dịch trực tiếp (cước 2x SubDub).",
                    "balance_xu": current_balance,
                    "required_xu": amount_xu,
                },
            )

        new_balance = current_balance - amount_xu
        new_spent = current_spent + amount_xu
        conn.execute(
            "UPDATE users SET credits = ?, total_spent = ? WHERE user_id = ?",
            (new_balance, new_spent, clean_uid),
        )
        conn.execute(
            """
            INSERT INTO credit_events (
                user_id, delta, balance_after, event_type, ref_id, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_uid,
                -amount_xu,
                new_balance,
                "realtime_translate_dub",
                req.session_id,
                f"Live Translate ({req.mode}, 2x SubDub, chars={req.char_count}, blocks={req.block_count}, key={clean_idemp})",
                now_str,
            ),
        )
        conn.execute(
            """
            INSERT INTO web_realtime_settlements (
                id, idempotency_key, session_id, user_id, mode, subdub_mode,
                char_count, block_count, base_subdub_xu, amount_xu,
                balance_before, balance_after, status, settled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'settled', ?)
            """,
            (
                settlement_id, clean_idemp, req.session_id, clean_uid,
                str(req.mode), mapped_mode, int(req.char_count), int(req.block_count),
                base_subdub_xu, amount_xu, current_balance, new_balance, now_str,
            ),
        )
        conn.execute("COMMIT")
        return {
            "ok": True,
            "duplicate": False,
            "exempt": False,
            "status": "settled",
            "settlement_id": settlement_id,
            "canonical_user_id": clean_uid,
            "mode": str(req.mode),
            "char_count": int(req.char_count),
            "block_count": int(req.block_count),
            "base_subdub_xu": base_subdub_xu,
            "amount_xu": amount_xu,
            "balance_before": current_balance,
            "balance_after": new_balance,
            "settled_at": now_str,
        }
    except Exception as exc:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        logger.exception("Realtime settlement failed cleanly: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error_code": "SETTLEMENT_FAILED", "message": "Lỗi đối soát giao dịch realtime."})
    finally:
        conn.close()
