"""Canonical Bot Core Realtime Translate & Dub Session Engine (RT-01 / RT-FIX1).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Session lifecycle FSM with fully idempotent termination (STOP_ONCE, STOP_TWICE_SAFE, ERROR_FINALIZE_SAFE).
2. Strict sequence idempotency and client reconnect ACK handshake.
3. Authority isolation: client can only request preference; Bot owns pricing and settlement.
4. Block settlement contract: settles exactly once, zero double-charging on reconnect or duplicate replay.
5. Owner-scoped subtitle export (SRT / VTT).
6. Process restart durability: declared as NOT_SUPPORTED for memory sessions.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

# Product & Pricing Authority Invariants
PRICING_STATE: str = "OWNER_DECISION_REQUIRED"
PRODUCTION_PAID_ADMISSION: str = "FAIL_CLOSED"
PROCESS_RESTART_DURABILITY: str = "NOT_SUPPORTED"
FALSE_ZERO_XU_SETTLEMENT: str = "REMOVED"


class RealtimeSessionState(str, enum.Enum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
    ERROR = "error"


class RealtimeTranslateMode(str, enum.Enum):
    CAPTION_ONLY = "CAPTION_ONLY"
    CAPTION_TRANSLATE = "CAPTION_TRANSLATE"
    LIVE_DUB = "LIVE_DUB"
    LIVE_DUB_BILINGUAL = "LIVE_DUB_BILINGUAL"


VALID_SESSION_TRANSITIONS: Dict[RealtimeSessionState, Set[RealtimeSessionState]] = {
    RealtimeSessionState.CREATED: {RealtimeSessionState.ACTIVE, RealtimeSessionState.ERROR, RealtimeSessionState.ENDED},
    RealtimeSessionState.ACTIVE: {RealtimeSessionState.PAUSED, RealtimeSessionState.ENDED, RealtimeSessionState.ERROR},
    RealtimeSessionState.PAUSED: {RealtimeSessionState.ACTIVE, RealtimeSessionState.ENDED, RealtimeSessionState.ERROR},
    RealtimeSessionState.ENDED: {RealtimeSessionState.ENDED},
    RealtimeSessionState.ERROR: {RealtimeSessionState.ERROR, RealtimeSessionState.ENDED},
}


@dataclass
class RealtimeSessionConfig:
    owner_id: str
    source_language: str = "auto"
    target_language: str = "vi"
    mode: RealtimeTranslateMode = RealtimeTranslateMode.LIVE_DUB_BILINGUAL
    voice_profile_id: Optional[str] = None
    gender_preference: Optional[str] = "male"
    client_device_id: Optional[str] = None
    metering_block_seconds: int = 60


@dataclass
class RealtimeTranscriptSegment:
    segment_id: str
    sequence: int
    start_ms: int
    end_ms: int
    source_text: str
    translated_text: str = ""
    is_final: bool = False
    speaker_id: Optional[str] = None
    tts_audio_base64: Optional[str] = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))


class RealtimeTranslateSession:
    """Core state machine and event coordinator for a live translate/dub session."""

    def __init__(self, session_id: str, config: RealtimeSessionConfig):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.config: RealtimeSessionConfig = config
        self.state: RealtimeSessionState = RealtimeSessionState.CREATED
        self.created_at: float = time.time()
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None

        self.last_client_seq: int = 0
        self.last_processed_seq: int = 0
        self.last_ack_seq: int = 0
        self.processed_seq_set: Set[int] = set()

        self.total_audio_ms: int = 0
        self.last_metered_seconds: int = 0
        self.consumed_blocks: int = 0
        self.settled_blocks: int = 0
        self.settled_xu: int = 0

        self.segments: List[RealtimeTranscriptSegment] = []
        self.error_message: Optional[str] = None

    def start(self) -> None:
        self._transition_to(RealtimeSessionState.ACTIVE)
        if self.started_at is None:
            self.started_at = time.time()

    def pause(self) -> None:
        self._transition_to(RealtimeSessionState.PAUSED)

    def resume(self) -> None:
        self._transition_to(RealtimeSessionState.ACTIVE)

    def end(self) -> None:
        """Idempotently finalizes the session. Safe to call multiple times or after error."""
        if self.state == RealtimeSessionState.ENDED:
            return
        self._transition_to(RealtimeSessionState.ENDED)
        if self.ended_at is None:
            self.ended_at = time.time()

    def fail(self, error_message: str) -> None:
        """Idempotently marks session as ERROR. Safe to call multiple times."""
        if self.state in (RealtimeSessionState.ENDED, RealtimeSessionState.ERROR):
            if not self.error_message:
                self.error_message = error_message
            return
        self.error_message = error_message
        self._transition_to(RealtimeSessionState.ERROR)
        if self.ended_at is None:
            self.ended_at = time.time()

    def _transition_to(self, new_state: RealtimeSessionState) -> None:
        if new_state not in VALID_SESSION_TRANSITIONS.get(self.state, set()):
            raise ValueError(f"Invalid session state transition: {self.state} -> {new_state}")
        self.state = new_state

    def accept_audio_sequence(self, seq: int, duration_ms: int) -> bool:
        """Enforces monotonic client sequence and deduplication.

        Returns True if accepted, False if duplicate or out of order.
        """
        if self.state not in (RealtimeSessionState.ACTIVE, RealtimeSessionState.CREATED):
            return False
        if seq <= 0:
            return False
        if seq in self.processed_seq_set:
            return False
        if seq <= self.last_processed_seq:
            return False

        self.processed_seq_set.add(seq)
        self.last_client_seq = max(self.last_client_seq, seq)
        self.total_audio_ms += max(0, duration_ms)
        return True

    def mark_sequence_processed(self, seq: int) -> int:
        """Records processed sequence and updates server ACK counter."""
        self.last_processed_seq = max(self.last_processed_seq, seq)
        self.last_ack_seq = self.last_processed_seq
        return self.last_ack_seq

    def handle_reconnect(self, client_last_ack_seq: int) -> Dict[str, Any]:
        """Handles client reconnection and reports server ACK authority."""
        return {
            "reconnected": True,
            "session_id": self.session_id,
            "server_last_ack_seq": self.last_processed_seq,
            "client_last_ack_seq": client_last_ack_seq,
            "state": self.state.value,
        }

    def compute_pending_metering_blocks(self) -> int:
        """Computes billable blocks (e.g. 60s) accrued since last settlement."""
        total_seconds = self.total_audio_ms // 1000
        block_sec = max(1, self.config.metering_block_seconds)
        current_blocks = total_seconds // block_sec
        new_blocks = current_blocks - self.consumed_blocks
        if new_blocks > 0:
            self.consumed_blocks = current_blocks
            self.last_metered_seconds = current_blocks * block_sec
            return new_blocks
        return 0

    def settle_blocks(self, block_count: int, xu_per_block: int = 0) -> Dict[str, Any]:
        """Settles accrued blocks exactly once and returns settlement truth.

        If PRICING_STATE is OWNER_DECISION_REQUIRED and xu_per_block is 0,
        it does NOT claim successful canonical settlement (FALSE_ZERO_XU_SETTLEMENT=REMOVED).
        """
        if block_count <= 0:
            return {
                "settled": False,
                "settled_blocks": self.settled_blocks,
                "xu_consumed": self.settled_xu,
            }
        if PRICING_STATE == "OWNER_DECISION_REQUIRED" and xu_per_block == 0:
            return {
                "settled": False,
                "blocks_pending": block_count,
                "pricing_state": PRICING_STATE,
                "xu_charged": 0,
                "total_xu_consumed": self.settled_xu,
                "reason": "PRICING_STATE=OWNER_DECISION_REQUIRED; zero xu settlement disallowed",
            }
        self.settled_blocks += block_count
        charge = block_count * max(0, xu_per_block)
        self.settled_xu += charge
        return {
            "settled": True,
            "blocks_settled": block_count,
            "total_settled_blocks": self.settled_blocks,
            "total_settled_seconds": self.settled_blocks * self.config.metering_block_seconds,
            "xu_charged": charge,
            "total_xu_consumed": self.settled_xu,
        }

    def get_telemetry_usage(self) -> Dict[str, Any]:
        """Returns telemetry usage update without claiming canonical Xu settlement."""
        total_seconds = self.total_audio_ms // 1000
        block_sec = max(1, self.config.metering_block_seconds)
        current_blocks = total_seconds // block_sec
        return {
            "type": "usage.updated",
            "audio_ms": self.total_audio_ms,
            "total_seconds": total_seconds,
            "pending_blocks": current_blocks - self.settled_blocks,
            "settled": False,
            "pricing_state": PRICING_STATE,
        }

    def add_segment(self, segment: RealtimeTranscriptSegment) -> None:
        self.segments.append(segment)

    def export_srt(self, requesting_owner_id: str) -> str:
        """Exports completed segments as standard SRT subtitle format.

        Enforces strict owner scoping.
        """
        if str(requesting_owner_id).strip() != str(self.config.owner_id).strip():
            raise PermissionError("Forbidden: requesting owner does not match session owner")

        lines = []
        idx = 1
        for seg in self.segments:
            if not seg.is_final:
                continue
            text = seg.translated_text if seg.translated_text else seg.source_text
            if not text.strip():
                continue
            start_str = self._format_srt_time(seg.start_ms)
            end_str = self._format_srt_time(seg.end_ms)
            lines.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
            idx += 1
        return "\n".join(lines)

    def export_vtt(self, requesting_owner_id: str) -> str:
        """Exports completed segments as standard WebVTT subtitle format.

        Enforces strict owner scoping.
        """
        if str(requesting_owner_id).strip() != str(self.config.owner_id).strip():
            raise PermissionError("Forbidden: requesting owner does not match session owner")

        lines = ["WEBVTT", ""]
        for seg in self.segments:
            if not seg.is_final:
                continue
            text = seg.translated_text if seg.translated_text else seg.source_text
            if not text.strip():
                continue
            start_str = self._format_vtt_time(seg.start_ms)
            end_str = self._format_vtt_time(seg.end_ms)
            lines.append(f"{start_str} --> {end_str}\n{text}\n")
        return "\n".join(lines)

    @staticmethod
    def _format_srt_time(ms: int) -> str:
        s, msec = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{msec:03d}"

    @staticmethod
    def _format_vtt_time(ms: int) -> str:
        s, msec = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{msec:03d}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "owner_id": self.config.owner_id,
            "state": self.state.value,
            "mode": self.config.mode.value,
            "source_language": self.config.source_language,
            "target_language": self.config.target_language,
            "voice_profile_id": self.config.voice_profile_id,
            "gender_preference": self.config.gender_preference,
            "total_audio_ms": self.total_audio_ms,
            "consumed_blocks": self.consumed_blocks,
            "settled_blocks": self.settled_blocks,
            "settled_xu": self.settled_xu,
            "last_processed_seq": self.last_processed_seq,
            "last_ack_seq": self.last_ack_seq,
            "segment_count": len([s for s in self.segments if s.is_final]),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error_message": self.error_message,
            "pricing_state": PRICING_STATE,
            "production_paid_admission": PRODUCTION_PAID_ADMISSION,
            "process_restart_durability": PROCESS_RESTART_DURABILITY,
        }
