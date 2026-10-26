"""Canonical Web App Realtime Gateway & WebSocket Router (RT-02).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Authenticated session creation: issues HMAC-signed stream token (5 min TTL).
2. WebSocket gateway: accepts 16kHz PCM chunks, dispatches to Bot Core Session Engine.
3. Downstream event broadcasting: stt.partial, stt.final, translation.final, tts.audio.
4. Server-side sequence idempotency and block metering.
5. Export endpoints for SRT and VTT subtitle tracks.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
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
            pass
        def post(self, *args, **kwargs):
            return lambda f: f
        def get(self, *args, **kwargs):
            return lambda f: f
        def websocket(self, *args, **kwargs):
            return lambda f: f
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail
    class WebSocketDisconnect(Exception):
        pass
    class Request: pass
    class WebSocket: pass
    def Query(default=None, **kwargs):
        return default

from services.realtime_asr_adapter import RealtimeASRAdapter
from services.realtime_audio_ingress import RealtimeAudioIngressBuffer
from services.realtime_translate_session import (
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

STREAM_TOKEN_SECRET = os.environ.get("REALTIME_STREAM_SECRET", "toanaas-live-stream-secret-key-32b")
TOKEN_TTL_SECONDS = 300  # 5 minutes


class CreateSessionRequest(BaseModel):
    source_language: str = Field(default="auto", description="Source audio language (e.g. en, zh, ja, auto)")
    target_language: str = Field(default="vi", description="Target translated language (e.g. vi)")
    mode: str = Field(default="LIVE_DUB_BILINGUAL", description="Mode: CAPTION_ONLY, CAPTION_TRANSLATE, LIVE_DUB, LIVE_DUB_BILINGUAL")
    voice_profile_id: Optional[str] = Field(default=None, description="Optional Voice Vault profile ID")
    gender_preference: Optional[str] = Field(default="male", description="male or female")


class SessionResponse(BaseModel):
    ok: bool
    session_id: str
    stream_token: str
    websocket_url: str
    mode: str
    target_language: str


def generate_stream_token(session_id: str, owner_id: str, expires_at: int) -> str:
    """Generates an HMAC-SHA256 signature for authenticating WebSocket connection."""
    payload = f"{session_id}:{owner_id}:{expires_at}"
    signature = hmac.new(
        STREAM_TOKEN_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token_data = {"session_id": session_id, "owner_id": owner_id, "exp": expires_at, "sig": signature}
    return base64.urlsafe_b64encode(json.dumps(token_data).encode("utf-8")).decode("ascii")


def verify_stream_token(token: str, session_id: str) -> Optional[str]:
    """Verifies stream token and returns owner_id if valid, or None."""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        if data.get("session_id") != session_id:
            return None
        if time.time() > data.get("exp", 0):
            return None
        payload = f"{data['session_id']}:{data['owner_id']}:{data['exp']}"
        expected_sig = hmac.new(
            STREAM_TOKEN_SECRET.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(data.get("sig", ""), expected_sig):
            return str(data["owner_id"])
    except Exception:
        return None
    return None


@router.post("/sessions", response_model=SessionResponse)
async def create_live_translate_session(req: CreateSessionRequest, request: Request) -> SessionResponse:
    """Creates a new real-time translation session and returns signed stream token."""
    # Resolve owner id (mock or from auth middleware if present)
    owner_id = getattr(request.state, "user_id", "guest_user")

    session_id = f"rts_{uuid.uuid4().hex[:12]}"
    mode_enum = RealtimeTranslateMode(req.mode) if req.mode in RealtimeTranslateMode._value2member_map_ else RealtimeTranslateMode.LIVE_DUB_BILINGUAL

    config = RealtimeSessionConfig(
        owner_id=owner_id,
        source_language=req.source_language,
        target_language=req.target_language,
        mode=mode_enum,
        voice_profile_id=req.voice_profile_id,
    )

    session = RealtimeTranslateSession(session_id, config)
    _ACTIVE_SESSIONS[session_id] = session
    _ACTIVE_INGRESS_BUFFERS[session_id] = RealtimeAudioIngressBuffer()

    exp = int(time.time()) + TOKEN_TTL_SECONDS
    stream_token = generate_stream_token(session_id, owner_id, exp)
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
async def get_session_status(session_id: str) -> Dict[str, Any]:
    """Retrieves session metadata, status, and segment count."""
    session = _ACTIVE_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True, **session.to_dict()}


@router.get("/sessions/{session_id}/export")
async def export_session_subtitles(session_id: str, format: str = Query("srt", regex="^(srt|vtt)$")) -> Dict[str, Any]:
    """Exports transcript as SRT or WebVTT subtitles."""
    session = _ACTIVE_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    content = session.export_srt() if format == "srt" else session.export_vtt()
    return {"ok": True, "format": format, "content": content}


@router.websocket("/sessions/{session_id}/stream")
async def websocket_live_stream(websocket: WebSocket, session_id: str, token: str = Query(...)):
    """WebSocket bidirectional live streaming route for audio and subtitles."""
    owner_id = verify_stream_token(token, session_id)
    if not owner_id:
        await websocket.close(code=4401, reason="Unauthorized or expired stream token")
        return

    session = _ACTIVE_SESSIONS.get(session_id)
    ingress = _ACTIVE_INGRESS_BUFFERS.get(session_id)
    if not session or not ingress:
        await websocket.close(code=4404, reason="Session not found")
        return

    await websocket.accept()
    session.start()

    asr_adapter = RealtimeASRAdapter()
    translation_adapter = RealtimeTranslationAdapter(target_language=session.config.target_language)
    voice_resolver = RealtimeVoiceResolver()
    tts_adapter = RealtimeTTSAdapter()
    resolved_voice = voice_resolver.resolve(
        target_language=session.config.target_language,
        voice_profile_id=session.config.voice_profile_id,
    )

    try:
        # Send initial handshake ACK
        await websocket.send_json({
            "type": "session.ready",
            "session_id": session_id,
            "mode": session.config.mode.value,
            "target_language": session.config.target_language,
        })

        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                # Binary audio chunk received (PCM 16kHz s16le)
                pcm_bytes = message["bytes"]
                session.last_received_seq += 1
                seq = session.last_received_seq

                chunk_dur_ms = int((len(pcm_bytes) / 32000) * 1000)
                if not session.accept_audio_sequence(seq, duration_ms=chunk_dur_ms):
                    continue

                # Process through ingress buffer & VAD
                completed_segments = ingress.push_chunk(seq=seq, pcm_bytes=pcm_bytes)

                for speech_seg in completed_segments:
                    # 1. ASR
                    asr_res = await asr_adapter.transcribe(speech_seg, language=session.config.source_language)
                    if not asr_res.ok or not asr_res.text.strip():
                        continue

                    # Emit original caption
                    await websocket.send_json({
                        "type": "stt.final",
                        "segment_id": speech_seg.segment_id,
                        "start_ms": speech_seg.start_ms,
                        "end_ms": speech_seg.end_ms,
                        "text": asr_res.text,
                    })

                    # 2. Translation (if mode requires translation)
                    trans_text = ""
                    if session.config.mode != RealtimeTranslateMode.CAPTION_ONLY:
                        trans_res = await translation_adapter.translate(asr_res.text, target_language=session.config.target_language)
                        if trans_res.ok:
                            trans_text = trans_res.translated_text
                            await websocket.send_json({
                                "type": "translation.final",
                                "segment_id": speech_seg.segment_id,
                                "source_text": asr_res.text,
                                "translated_text": trans_text,
                                "start_ms": speech_seg.start_ms,
                                "end_ms": speech_seg.end_ms,
                            })

                    # 3. TTS (if live dubbing mode enabled)
                    tts_b64 = None
                    if session.config.mode in (RealtimeTranslateMode.LIVE_DUB, RealtimeTranslateMode.LIVE_DUB_BILINGUAL) and trans_text:
                        tts_res = await tts_adapter.synthesize(trans_text, resolved_voice)
                        if tts_res.ok and tts_res.audio_base64:
                            tts_b64 = tts_res.audio_base64
                            await websocket.send_json({
                                "type": "tts.audio",
                                "segment_id": speech_seg.segment_id,
                                "format": tts_res.format,
                                "duration_ms": tts_res.duration_ms,
                                "audio_base64": tts_b64,
                            })

                    # Record completed segment in session
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
                    session.mark_sequence_processed(seq)

                # Check block metering
                new_blocks = session.compute_pending_metering_blocks()
                if new_blocks > 0:
                    await websocket.send_json({
                        "type": "usage.updated",
                        "consumed_blocks": session.consumed_blocks,
                        "total_audio_ms": session.total_audio_ms,
                    })

            elif "text" in message and message["text"]:
                # JSON control message
                try:
                    ctrl = json.loads(message["text"])
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
        # Clean up ingress buffer
        _ACTIVE_INGRESS_BUFFERS.pop(session_id, None)
