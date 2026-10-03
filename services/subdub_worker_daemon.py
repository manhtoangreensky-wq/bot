"""Canonical Bot Core SubDub Dedicated Worker Daemon (BOT-SUBDUB-WORKER-R1).

Governed by owner-governed-codex, locked-focus-engineering,
toanaas-system-design-and-open-apis.

Invariants:
1. SubDub-Only Scope: Only claims and processes jobs from canonical `subdub_worker_jobs` queue.
   Never touches product video, video editing, or admin canary queues.
2. Atomic Fencing Token: Strictly requires and passes `claim_token` to complete_subdub_job / fail_subdub_job.
3. Max Attempts Bound: Preserves `max_attempts` (strictly 1 for Web R7 dispatch). No auto provider retry, no provider fallback.
4. Upload Authority: Resolves `upload_id` strictly via canonical owner-bound upload authority.
   Rejects raw filesystem paths, remote URLs, and cross-owner uploads.
5. VTT Delivery Truth: For mode=subtitle_create, produces valid non-zero VTT artifact (starting with 'WEBVTT').
6. Non-Fake Completion: Never completes a job without verified non-zero artifact and safe delivery URL.
7. Safe Heartbeat: Periodically heartbeats active jobs; aborts if fencing token is invalidated.
8. Zero Secret Leakage: Never logs provider keys, HMAC secrets, or authorization tokens.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import signal
import sqlite3
import sys
import threading
import time
from typing import Any, Callable

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.subdub_worker_claim import (
    claim_next_subdub_job,
    heartbeat_subdub_job,
    complete_subdub_job,
    fail_subdub_job,
    get_subdub_worker_job,
    ensure_subdub_worker_queue_schema,
)
from services.subdub_upload_staging import get_staged_upload

logger = logging.getLogger("subdub_worker_daemon")

DEFAULT_WORKER_ID = "vps-subdub-worker"
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_LEASE_SECONDS = 600
DEFAULT_HEARTBEAT_INTERVAL = 30.0
DEFAULT_PUBLIC_BASE_URL = "https://tg.toanaas.vn/artifacts/subdub"
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "data" / "artifacts" / "subdub"

SUPPORTED_MODES = frozenset({
    "subtitle_create",
    "subtitle_translate",
    "dub",
    "subtitle_plus_dub",
})

SAFE_HOSTNAME_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
FORBIDDEN_OUTPUT_URL_SCHEMES = frozenset({"javascript:", "vbscript:", "data:", "file:", "blob:", "about:"})


def is_safe_subdub_output_url(url: Any) -> bool:
    """Validate that a candidate SubDub output URL is safe to deliver."""
    if not isinstance(url, str):
        return False
    trimmed = url.strip()
    if not trimmed or len(trimmed) > 2048 or trimmed != url:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in trimmed):
        return False
    if "\\" in trimmed:
        return False
    lowered = trimmed.lower()
    if ".." in lowered or "%2e" in lowered:
        return False
    if any(lowered.startswith(s) or s in lowered for s in FORBIDDEN_OUTPUT_URL_SCHEMES):
        return False
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(trimmed)
    except Exception:
        return False
    if parsed.scheme.lower() != "https":
        return False
    if not parsed.netloc:
        return False
    if parsed.username or parsed.password or "@" in parsed.netloc:
        return False
    hostname = (parsed.hostname or "").lower()
    if not hostname or not SAFE_HOSTNAME_PATTERN.fullmatch(hostname):
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in (None, 443):
        return False
    return True


def format_srt_timestamp(seconds: float) -> str:
    """Format floating seconds into SRT timestamp HH:MM:SS,mmm."""
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_vtt_text(cues: list[dict[str, Any]] | str) -> str:
    """Convert cues or raw text into canonical VTT format."""
    if isinstance(cues, str):
        body = cues.replace("\r", "").strip()
        if not body:
            return "WEBVTT\n"
        # Convert SRT timestamps (comma) to VTT (dot)
        body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", body)
        if body.startswith("WEBVTT"):
            return body + ("\n" if not body.endswith("\n") else "")
        return f"WEBVTT\n\n{body}\n"

    blocks = []
    for idx, item in enumerate(cues or [], start=1):
        text = str((item or {}).get("text") or "").strip()
        if not text:
            continue
        start = float((item or {}).get("start") or 0.0)
        end = float((item or {}).get("end") or 0.0)
        if end <= start:
            end = start + 1.0
        start_ts = format_srt_timestamp(start).replace(",", ".")
        end_ts = format_srt_timestamp(end).replace(",", ".")
        blocks.append(f"{idx}\n{start_ts} --> {end_ts}\n{text}")

    if not blocks:
        return "WEBVTT\n"
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"


def is_provider_calls_enabled() -> bool:
    """Check if paid external provider API calls are explicitly allowed."""
    raw = os.getenv("WEBAPP_PROVIDER_CALLS_ENABLED") or os.getenv("PROVIDER_CALLS_ENABLED") or "false"
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class SubDubWorkerDaemon:
    """Single-lane canonical worker daemon for SubDub queue consumption."""

    def __init__(
        self,
        *,
        worker_id: str = DEFAULT_WORKER_ID,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
        public_base_url: str = DEFAULT_PUBLIC_BASE_URL,
        artifact_dir: Path | str | None = None,
        db_conn: sqlite3.Connection | None = None,
        transcriber_fn: Callable[..., Any] | None = None,
        translator_fn: Callable[..., Any] | None = None,
        voice_resolver_fn: Callable[..., Any] | None = None,
        tts_fn: Callable[..., Any] | None = None,
        muxer_fn: Callable[..., Any] | None = None,
        probe_fn: Callable[..., Any] | None = None,
    ):
        self.worker_id = str(worker_id or DEFAULT_WORKER_ID).strip()[:80]
        self.poll_interval = max(0.1, float(poll_interval))
        self.lease_seconds = max(10, int(lease_seconds))
        self.heartbeat_interval = max(1.0, float(heartbeat_interval))
        self.public_base_url = str(public_base_url or DEFAULT_PUBLIC_BASE_URL).rstrip("/")
        self.artifact_dir = Path(artifact_dir or os.getenv("SUBDUB_ARTIFACT_DIR") or DEFAULT_ARTIFACT_DIR).resolve()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.db_conn = db_conn
        self.transcriber_fn = transcriber_fn
        self.translator_fn = translator_fn
        self.voice_resolver_fn = voice_resolver_fn
        self.tts_fn = tts_fn
        self.muxer_fn = muxer_fn
        self.probe_fn = probe_fn
        self._running = False
        self._stop_event = threading.Event()


    def stop(self) -> None:
        """Signal daemon to stop gracefully."""
        self._running = False
        self._stop_event.set()

    def _resolve_upload(self, upload_id: str, owner_id: str) -> tuple[bool, str, int, dict[str, Any]]:
        """Resolve staged upload metadata with actor ownership enforcement."""
        if self.db_conn is not None:
            clean_id = str(upload_id or "").strip()
            if not clean_id or not re.fullmatch(r"^[A-Za-z0-9_-]{1,80}$", clean_id):
                return False, "INVALID_UPLOAD_ID", 400, {}
            try:
                cur = self.db_conn.execute("SELECT value FROM system_settings WHERE key = ?", (f"subdub_upload:{clean_id}",))
                row = cur.fetchone()
                if not row:
                    return False, "UPLOAD_NOT_FOUND", 404, {}
                record = json.loads(row[0] if isinstance(row, (tuple, list)) else row["value"])
            except Exception:
                return False, "UPLOAD_NOT_FOUND", 404, {}

            if not isinstance(record, dict) or record.get("upload_id") != clean_id:
                return False, "UPLOAD_NOT_FOUND", 404, {}

            local_path = str(record.get("local_path") or "").strip()
            if not local_path or not Path(local_path).is_file():
                return False, "STAGED_FILE_MISSING", 404, {}

            record_owner = str(record.get("owner_id") or "").strip()
            clean_actor = str(owner_id or "").strip()
            if clean_actor.startswith("telegram-"):
                clean_actor = clean_actor[len("telegram-"):]
            if record_owner and clean_actor and record_owner != clean_actor:
                return False, "FORBIDDEN_CROSS_OWNER", 403, {}

            return True, "OK", 200, record

        return get_staged_upload(upload_id, actor_id=owner_id)

    def process_one_job(self) -> bool:
        """Claim and process at most one job from the queue. Return True if job was claimed."""
        job = claim_next_subdub_job(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            conn=self.db_conn,
        )
        if not job:
            return False

        job_id = str(job.get("job_id") or "")
        worker_id = str(job.get("worker_id") or self.worker_id)
        claim_token = str(job.get("claim_token") or "")
        owner_id = str(job.get("owner_id") or "")
        mode = str(job.get("mode") or "").strip().lower()
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        attempts = int(job.get("attempts") or 1)
        max_attempts = int(job.get("max_attempts") or 1)

        logger.info(f"Claimed SubDub job {job_id} (mode={mode}, attempts={attempts}/{max_attempts})")

        # 1. Attempt Bound Invariant (Fail-Closed)
        if attempts > max_attempts:
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="MAX_ATTEMPTS_EXCEEDED",
                message=f"Job exceeded max_attempts bound ({attempts} > {max_attempts})",
                conn=self.db_conn,
            )
            return True

        # 2. Mode Support Gate
        if mode not in SUPPORTED_MODES:
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="UNSUPPORTED_MODE",
                message=f"SubDub mode '{mode}' is not supported by worker",
                conn=self.db_conn,
            )
            return True

        # 3. Upload Authority Intake Resolution (Phase F)
        upload_id = str(payload.get("upload_id") or "").strip()
        if not upload_id:
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="MISSING_UPLOAD_ID",
                message="upload_id is required in job payload",
                conn=self.db_conn,
            )
            return True

        # Check for forbidden raw authority paths passed directly in payload
        for forbidden in ("local_path", "file_path", "path", "url", "remote_url"):
            if forbidden in payload and payload[forbidden]:
                fail_subdub_job(
                    job_id,
                    worker_id,
                    claim_token,
                    error_code="RAW_PATH_OR_URL_REJECTED",
                    message="Direct path or remote URL rejected as input authority",
                    conn=self.db_conn,
                )
                return True

        upload_ok, upload_reason, upload_code, upload_record = self._resolve_upload(upload_id, owner_id)
        if not upload_ok:
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code=upload_reason or "UPLOAD_RESOLUTION_FAILED",
                message=f"Failed to resolve upload {upload_id} (http={upload_code}): {upload_reason}",
                conn=self.db_conn,
            )
            return True

        media_path = str(upload_record.get("local_path") or "").strip()
        if not media_path or not Path(media_path).is_file() or Path(media_path).stat().st_size == 0:
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="STAGED_FILE_MISSING",
                message=f"Staged upload media file is missing or zero bytes",
                conn=self.db_conn,
            )
            return True

        # 4. Heartbeat Monitor during processing
        heartbeat_abort = threading.Event()

        def _heartbeat_loop():
            while not heartbeat_abort.wait(timeout=self.heartbeat_interval):
                try:
                    hb_ok, hb_reason, _ = heartbeat_subdub_job(
                        job_id,
                        worker_id,
                        claim_token,
                        lease_seconds=self.lease_seconds,
                        conn=self.db_conn,
                    )
                    if not hb_ok:
                        logger.warning(f"Heartbeat failed for {job_id}: {hb_reason}")
                        heartbeat_abort.set()
                        break
                except Exception as exc:
                    logger.warning(f"Heartbeat exception for {job_id}: {exc}")

        hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        hb_thread.start()

        # 5. Pipeline Execution
        try:
            if mode == "subtitle_create":
                self._execute_subtitle_create(
                    job_id=job_id,
                    worker_id=worker_id,
                    claim_token=claim_token,
                    owner_id=owner_id,
                    media_path=media_path,
                    payload=payload,
                    heartbeat_abort=heartbeat_abort,
                )
            elif mode == "subtitle_translate":
                self._execute_subtitle_translate(
                    job_id=job_id,
                    worker_id=worker_id,
                    claim_token=claim_token,
                    owner_id=owner_id,
                    media_path=media_path,
                    payload=payload,
                    heartbeat_abort=heartbeat_abort,
                )
            elif mode == "dub":
                self._execute_dub(
                    job_id=job_id,
                    worker_id=worker_id,
                    claim_token=claim_token,
                    owner_id=owner_id,
                    media_path=media_path,
                    payload=payload,
                    heartbeat_abort=heartbeat_abort,
                )
            elif mode == "subtitle_plus_dub":
                self._execute_subtitle_plus_dub(
                    job_id=job_id,
                    worker_id=worker_id,
                    claim_token=claim_token,
                    owner_id=owner_id,
                    media_path=media_path,
                    payload=payload,
                    heartbeat_abort=heartbeat_abort,
                )
            else:
                fail_subdub_job(
                    job_id,
                    worker_id,
                    claim_token,
                    error_code="UNSUPPORTED_MODE",
                    message=f"SubDub mode '{mode}' is not supported by worker",
                    conn=self.db_conn,
                )

        except Exception as exc:
            logger.error(f"Execution error on job {job_id}: {exc}")
            # Ensure failure is registered fail-closed
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="PIPELINE_EXECUTION_EXCEPTION",
                message=f"{type(exc).__name__}: {str(exc)[:180]}",
                conn=self.db_conn,
            )
        finally:
            heartbeat_abort.set()
            hb_thread.join(timeout=1.0)

        return True

    def _execute_subtitle_create(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        owner_id: str,
        media_path: str,
        payload: dict[str, Any],
        heartbeat_abort: threading.Event,
    ) -> None:
        """Execute mode=subtitle_create and produce truthful VTT artifact."""
        if heartbeat_abort.is_set():
            logger.warning(f"Aborting execution for {job_id} due to fencing token mismatch")
            return

        output_format = str(payload.get("output_format") or "vtt").strip().lower()
        if output_format not in {"vtt", "srt"}:
            output_format = "vtt"

        # Check injected transcriber or provider availability
        vtt_content = ""
        cues_count = 0
        duration_seconds = 0.0

        if self.transcriber_fn is not None:
            # Custom / test injected runner
            try:
                transcribe_result = self.transcriber_fn(media_path, payload)
                if isinstance(transcribe_result, list):
                    raw_cues = transcribe_result
                    vtt_content = format_vtt_text(raw_cues)
                    cues_count = len([c for c in raw_cues if isinstance(c, dict) and (c.get("text") or "").strip()])
                    duration_seconds = max((float((c or {}).get("end") or 0.0) for c in raw_cues if isinstance(c, dict)), default=0.0)
                elif isinstance(transcribe_result, dict):
                    raw_cues = transcribe_result.get("cues") or transcribe_result.get("segments") or []
                    duration_seconds = float(transcribe_result.get("duration") or 0.0)
                    vtt_content = format_vtt_text(raw_cues)
                    cues_count = len(raw_cues) if isinstance(raw_cues, list) else 1
                elif isinstance(transcribe_result, str):
                    vtt_content = format_vtt_text(transcribe_result)
                    cues_count = vtt_content.count("-->")
                else:
                    fail_subdub_job(
                        job_id,
                        worker_id,
                        claim_token,
                        error_code="TRANSCRIBER_RETURN_INVALID",
                        message="Transcriber returned invalid data",
                        conn=self.db_conn,
                    )
                    return
            except Exception as exc:
                fail_subdub_job(
                    job_id,
                    worker_id,
                    claim_token,
                    error_code="TRANSCRIBER_FAILED",
                    message=f"Transcriber error: {type(exc).__name__}",
                    conn=self.db_conn,
                )
                return
        else:
            # Production pipeline path
            if not is_provider_calls_enabled():
                fail_subdub_job(
                    job_id,
                    worker_id,
                    claim_token,
                    error_code="PROVIDER_CALLS_DISABLED",
                    message="Provider calls are disabled by environment gate (PROVIDER_CALLS=0)",
                    conn=self.db_conn,
                )
                return

            try:
                import bot
                import asyncio

                media_bytes = Path(media_path).read_bytes()
                content_type = str(payload.get("source_mime_type") or "audio/mpeg")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    res = loop.run_until_complete(
                        bot.transcribe_media_to_segments(
                            {"bytes": media_bytes, "content_type": content_type, "duration_seconds": 0},
                            allow_subdub_public=True,
                        )
                    )
                finally:
                    loop.close()

                segments = res.get("segments") or []
                cues_count = len(segments)
                duration_seconds = float(res.get("duration_seconds") or 0.0)
                srt_text = bot.video_dubbing_srt_from_segments(segments)
                vtt_content = bot.video_dubbing_srt_to_vtt_text(srt_text)
            except Exception as exc:
                fail_subdub_job(
                    job_id,
                    worker_id,
                    claim_token,
                    error_code="CANONICAL_ASR_FAILED",
                    message=f"ASR execution error: {type(exc).__name__}",
                    conn=self.db_conn,
                )
                return

        # Phase G Verification: Truthful VTT Artifact
        if not vtt_content or not vtt_content.startswith("WEBVTT"):
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="INVALID_VTT_HEADER",
                message="Produced subtitle output lacks valid WEBVTT header",
                conn=self.db_conn,
            )
            return

        if cues_count <= 0 or vtt_content.strip() == "WEBVTT":
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="EMPTY_SUBTITLE_OUTPUT",
                message="Produced subtitle output has no cues or content",
                conn=self.db_conn,
            )
            return

        vtt_bytes = vtt_content.encode("utf-8")
        if len(vtt_bytes) == 0:
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="ZERO_BYTE_OUTPUT",
                message="Produced subtitle artifact is 0 bytes",
                conn=self.db_conn,
            )
            return

        # Write artifact to disk
        artifact_filename = f"{job_id}.vtt"
        artifact_file = self.artifact_dir / artifact_filename
        artifact_file.write_bytes(vtt_bytes)

        file_size = artifact_file.stat().st_size
        file_sha256 = hashlib.sha256(vtt_bytes).hexdigest()

        delivery_url = f"{self.public_base_url}/{artifact_filename}"
        if not is_safe_subdub_output_url(delivery_url):
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="UNSAFE_DELIVERY_URL",
                message="Constructed delivery URL violates safety invariants",
                conn=self.db_conn,
            )
            return

        # Phase H Completion Truth
        result_payload = {
            "output_url": delivery_url,
            "download_url": delivery_url,
            "url": delivery_url,
            "format": "vtt",
            "output_format": "vtt",
            "content_type": "text/vtt",
            "size_bytes": file_size,
            "sha256": file_sha256,
            "duration_seconds": round(duration_seconds, 2),
            "cues_count": cues_count,
            "mode": "subtitle_create",
            "artifact_path": str(artifact_file),
        }

        ok, reason, _ = complete_subdub_job(
            job_id,
            worker_id,
            claim_token,
            result=result_payload,
            conn=self.db_conn,
        )
        if not ok:
            logger.error(f"Failed to complete job {job_id}: {reason}")

    def _execute_subtitle_translate(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        owner_id: str,
        media_path: str,
        payload: dict[str, Any],
        heartbeat_abort: threading.Event,
    ) -> None:
        """Execute mode=subtitle_translate and produce truthful translated subtitle artifact."""
        if heartbeat_abort.is_set():
            logger.warning(f"Aborting execution for {job_id} due to fencing token mismatch")
            return

        target_lang = str(payload.get("target_language") or "").strip().lower()
        if not target_lang:
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="MISSING_TARGET_LANGUAGE",
                message="target_language is required for subtitle_translate",
                conn=self.db_conn,
            )
            return

        # 1. Transcribe source media
        source_segments = []
        duration_seconds = 0.0
        if self.transcriber_fn is not None:
            try:
                res = self.transcriber_fn(media_path, payload)
                if isinstance(res, list):
                    source_segments = res
                    duration_seconds = max((float((c or {}).get("end") or 0.0) for c in res if isinstance(c, dict)), default=0.0)
                elif isinstance(res, dict):
                    source_segments = res.get("segments") or res.get("cues") or []
                    duration_seconds = float(res.get("duration") or res.get("duration_seconds") or 0.0)
                elif isinstance(res, str):
                    source_segments = [{"text": res, "start": 0.0, "end": 2.0}]
                    duration_seconds = 2.0
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "TRANSCRIBER_FAILED", f"Transcriber error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                media_bytes = Path(media_path).read_bytes()
                content_type = str(payload.get("source_mime_type") or "audio/mpeg")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    res = loop.run_until_complete(
                        bot.transcribe_media_to_segments(
                            {"bytes": media_bytes, "content_type": content_type, "duration_seconds": 0},
                            allow_subdub_public=True,
                        )
                    )
                finally:
                    loop.close()
                source_segments = res.get("segments") or []
                duration_seconds = float(res.get("duration_seconds") or 0.0)
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_ASR_FAILED", f"ASR execution error: {type(exc).__name__}", conn=self.db_conn)
                return

        if not source_segments:
            fail_subdub_job(job_id, worker_id, claim_token, "EMPTY_SOURCE_TRANSCRIPT", "Source media yielded zero subtitle segments", conn=self.db_conn)
            return

        # 2. Translate segments to target language
        translated_segments = []
        if self.translator_fn is not None:
            try:
                t_res = self.translator_fn(source_segments, target_lang, payload)
                if isinstance(t_res, list):
                    translated_segments = t_res
                elif isinstance(t_res, dict):
                    translated_segments = t_res.get("segments") or []
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "TRANSLATION_FAILED", f"Translator error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    t_out = loop.run_until_complete(
                        bot.translate_subtitle_segments(
                            source_segments,
                            target_lang,
                            allow_confirmed_product=True,
                        )
                    )
                finally:
                    loop.close()
                translated_segments = t_out.get("segments") or t_out if isinstance(t_out, list) else []
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_TRANSLATION_FAILED", f"Translation error: {type(exc).__name__}", conn=self.db_conn)
                return

        if not translated_segments:
            fail_subdub_job(job_id, worker_id, claim_token, "EMPTY_TRANSLATION_OUTPUT", "Translation yielded zero segments", conn=self.db_conn)
            return

        vtt_content = format_vtt_text(translated_segments)
        cues_count = len([c for c in translated_segments if isinstance(c, dict) and (c.get("text") or "").strip()])
        char_count = sum(len(str((c or {}).get("text") or "")) for c in translated_segments if isinstance(c, dict))

        if cues_count <= 0 or not vtt_content.startswith("WEBVTT"):
            fail_subdub_job(job_id, worker_id, claim_token, "INVALID_VTT_HEADER", "Produced translated subtitle lacks valid WEBVTT header or content", conn=self.db_conn)
            return

        vtt_bytes = vtt_content.encode("utf-8")
        if len(vtt_bytes) == 0:
            fail_subdub_job(job_id, worker_id, claim_token, "ZERO_BYTE_OUTPUT", "Produced subtitle artifact is 0 bytes", conn=self.db_conn)
            return

        artifact_filename = f"{job_id}.vtt"
        artifact_file = self.artifact_dir / artifact_filename
        artifact_file.write_bytes(vtt_bytes)
        file_size = artifact_file.stat().st_size
        file_sha256 = hashlib.sha256(vtt_bytes).hexdigest()

        delivery_url = f"{self.public_base_url}/{artifact_filename}"
        if not is_safe_subdub_output_url(delivery_url):
            fail_subdub_job(job_id, worker_id, claim_token, "UNSAFE_DELIVERY_URL", "Constructed delivery URL violates safety invariants", conn=self.db_conn)
            return

        result_payload = {
            "output_url": delivery_url,
            "download_url": delivery_url,
            "url": delivery_url,
            "format": "vtt",
            "output_format": "vtt",
            "content_type": "text/vtt",
            "size_bytes": file_size,
            "sha256": file_sha256,
            "duration_seconds": round(duration_seconds, 2),
            "cues_count": cues_count,
            "char_count": char_count,
            "target_language": target_lang,
            "mode": "subtitle_translate",
            "artifact_path": str(artifact_file),
        }
        complete_subdub_job(job_id, worker_id, claim_token, result=result_payload, conn=self.db_conn)

    def _execute_dub(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        owner_id: str,
        media_path: str,
        payload: dict[str, Any],
        heartbeat_abort: threading.Event,
    ) -> None:
        """Execute mode=dub and produce truthful dubbed media artifact."""
        if heartbeat_abort.is_set():
            logger.warning(f"Aborting execution for {job_id} due to fencing token mismatch")
            return

        target_lang = str(payload.get("target_language") or "").strip().lower()
        if not target_lang:
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="MISSING_TARGET_LANGUAGE",
                message="target_language is required for dub",
                conn=self.db_conn,
            )
            return

        # 1. Voice profile resolution (server authority)
        if self.voice_resolver_fn is not None:
            try:
                vr_ok, vr_reason, vr_code, vr_data = self.voice_resolver_fn(owner_id, payload)
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "VOICE_RESOLUTION_FAILED", f"Voice resolver error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            from services.subdub_voice_resolution import resolve_subdub_voice_authority
            vr_ok, vr_reason, vr_code, vr_data = resolve_subdub_voice_authority(owner_id, payload)

        if not vr_ok:
            fail_subdub_job(job_id, worker_id, claim_token, vr_reason or "VOICE_RESOLUTION_FAILED", f"Voice resolution failed: {vr_reason}", conn=self.db_conn)
            return

        # 2. ASR Transcribe
        source_segments = []
        duration_seconds = 0.0
        if self.transcriber_fn is not None:
            try:
                res = self.transcriber_fn(media_path, payload)
                if isinstance(res, list):
                    source_segments = res
                    duration_seconds = max((float((c or {}).get("end") or 0.0) for c in res if isinstance(c, dict)), default=0.0)
                elif isinstance(res, dict):
                    source_segments = res.get("segments") or res.get("cues") or []
                    duration_seconds = float(res.get("duration") or res.get("duration_seconds") or 0.0)
                elif isinstance(res, str):
                    source_segments = [{"text": res, "start": 0.0, "end": 2.0}]
                    duration_seconds = 2.0
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "TRANSCRIBER_FAILED", f"Transcriber error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                media_bytes = Path(media_path).read_bytes()
                content_type = str(payload.get("source_mime_type") or "audio/mpeg")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    res = loop.run_until_complete(
                        bot.transcribe_media_to_segments(
                            {"bytes": media_bytes, "content_type": content_type, "duration_seconds": 0},
                            allow_subdub_public=True,
                        )
                    )
                finally:
                    loop.close()
                source_segments = res.get("segments") or []
                duration_seconds = float(res.get("duration_seconds") or 0.0)
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_ASR_FAILED", f"ASR execution error: {type(exc).__name__}", conn=self.db_conn)
                return

        if not source_segments:
            fail_subdub_job(job_id, worker_id, claim_token, "EMPTY_SOURCE_TRANSCRIPT", "Source media yielded zero subtitle segments", conn=self.db_conn)
            return

        # 3. Translation (if needed)
        source_lang = str(payload.get("source_language") or "auto").strip().lower()
        if source_lang == target_lang and self.translator_fn is None:
            translated_segments = source_segments
        elif self.translator_fn is not None:
            try:
                t_res = self.translator_fn(source_segments, target_lang, payload)
                translated_segments = t_res if isinstance(t_res, list) else t_res.get("segments", [])
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "TRANSLATION_FAILED", f"Translator error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    t_out = loop.run_until_complete(
                        bot.translate_subtitle_segments(source_segments, target_lang, allow_confirmed_product=True)
                    )
                finally:
                    loop.close()
                translated_segments = t_out.get("segments") or t_out if isinstance(t_out, list) else []
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_TRANSLATION_FAILED", f"Translation error: {type(exc).__name__}", conn=self.db_conn)
                return

        char_count = sum(len(str((c or {}).get("text") or "")) for c in translated_segments if isinstance(c, dict))

        # 4. TTS Synthesis
        dub_audio_bytes = b""
        if self.tts_fn is not None:
            try:
                dub_audio_bytes = self.tts_fn(translated_segments, vr_data, payload)
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "TTS_FAILED", f"TTS error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    synth_res = loop.run_until_complete(
                        bot.synthesize_dub_segment_chunks(
                            translated_segments,
                            voice_style=vr_data.get("_internal_provider_voice_id"),
                            voice_speed=vr_data.get("voice_speed", 1.0),
                            target_language=target_lang,
                        )
                    )
                finally:
                    loop.close()
                dub_audio_bytes = synth_res.get("audio_bytes") if isinstance(synth_res, dict) else (synth_res or b"")
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_TTS_FAILED", f"TTS error: {type(exc).__name__}", conn=self.db_conn)
                return

        if not dub_audio_bytes or len(dub_audio_bytes) == 0:
            fail_subdub_job(job_id, worker_id, claim_token, "TTS_SYNTHESIS_FAILED", "TTS synthesis produced zero bytes", conn=self.db_conn)
            return

        # 5. Mux / Render
        is_video = str(payload.get("source_media_type") or "").lower() == "video" or bool(payload.get("is_video_source")) or Path(media_path).suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")
        output_format = "video" if is_video else "audio"
        ext = "mp4" if is_video else "mp3"
        content_type = "video/mp4" if is_video else "audio/mpeg"

        final_media_bytes = b""
        if self.muxer_fn is not None:
            try:
                final_media_bytes, ext = self.muxer_fn(media_path, dub_audio_bytes, None, payload)
                content_type = "video/mp4" if ext == "mp4" else "audio/mpeg"
                output_format = "video" if ext == "mp4" else "audio"
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "MUX_FAILED", f"Muxer error: {type(exc).__name__}", conn=self.db_conn)
                return
        elif not is_video:
            final_media_bytes = dub_audio_bytes
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    render_res = loop.run_until_complete(
                        bot.video_dubbing_render_video(
                            video_path=media_path,
                            audio_bytes=dub_audio_bytes,
                            mode="dub",
                        )
                    )
                finally:
                    loop.close()
                final_media_bytes = render_res.get("video_bytes") if isinstance(render_res, dict) else (render_res or b"")
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_MUX_FAILED", f"Mux error: {type(exc).__name__}", conn=self.db_conn)
                return

        if not final_media_bytes or len(final_media_bytes) == 0:
            fail_subdub_job(job_id, worker_id, claim_token, "EMPTY_MUX_OUTPUT", "Mux/render produced zero bytes", conn=self.db_conn)
            return

        artifact_filename = f"{job_id}.{ext}"
        artifact_file = self.artifact_dir / artifact_filename
        artifact_file.write_bytes(final_media_bytes)
        file_size = artifact_file.stat().st_size
        file_sha256 = hashlib.sha256(final_media_bytes).hexdigest()

        # 6. Final Media Probe
        if self.probe_fn is not None:
            try:
                probe_ok, probe_info = self.probe_fn(str(artifact_file))
                if not probe_ok:
                    fail_subdub_job(job_id, worker_id, claim_token, "ARTIFACT_PROBE_FAILED", f"Probe error: {probe_info.get('reason', 'invalid media')}", conn=self.db_conn)
                    return
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "ARTIFACT_PROBE_FAILED", f"Probe exception: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if file_size <= 0:
                fail_subdub_job(job_id, worker_id, claim_token, "ARTIFACT_PROBE_FAILED", "Generated artifact has zero size", conn=self.db_conn)
                return

        delivery_url = f"{self.public_base_url}/{artifact_filename}"
        if not is_safe_subdub_output_url(delivery_url):
            fail_subdub_job(job_id, worker_id, claim_token, "UNSAFE_DELIVERY_URL", "Constructed delivery URL violates safety invariants", conn=self.db_conn)
            return

        result_payload = {
            "output_url": delivery_url,
            "download_url": delivery_url,
            "url": delivery_url,
            "format": ext,
            "output_format": output_format,
            "content_type": content_type,
            "size_bytes": file_size,
            "sha256": file_sha256,
            "duration_seconds": round(duration_seconds, 2),
            "char_count": char_count,
            "target_language": target_lang,
            "voice_profile_id": payload.get("voice_profile_id"),
            "mode": "dub",
            "artifact_path": str(artifact_file),
        }
        complete_subdub_job(job_id, worker_id, claim_token, result=result_payload, conn=self.db_conn)

    def _execute_subtitle_plus_dub(
        self,
        *,
        job_id: str,
        worker_id: str,
        claim_token: str,
        owner_id: str,
        media_path: str,
        payload: dict[str, Any],
        heartbeat_abort: threading.Event,
    ) -> None:
        """Execute mode=subtitle_plus_dub and produce truthful combo media artifact."""
        if heartbeat_abort.is_set():
            logger.warning(f"Aborting execution for {job_id} due to fencing token mismatch")
            return

        target_lang = str(payload.get("target_language") or "").strip().lower()
        if not target_lang:
            fail_subdub_job(
                job_id,
                worker_id,
                claim_token,
                error_code="MISSING_TARGET_LANGUAGE",
                message="target_language is required for subtitle_plus_dub",
                conn=self.db_conn,
            )
            return

        # 1. Voice profile resolution
        if self.voice_resolver_fn is not None:
            try:
                vr_ok, vr_reason, vr_code, vr_data = self.voice_resolver_fn(owner_id, payload)
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "VOICE_RESOLUTION_FAILED", f"Voice resolver error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            from services.subdub_voice_resolution import resolve_subdub_voice_authority
            vr_ok, vr_reason, vr_code, vr_data = resolve_subdub_voice_authority(owner_id, payload)

        if not vr_ok:
            fail_subdub_job(job_id, worker_id, claim_token, vr_reason or "VOICE_RESOLUTION_FAILED", f"Voice resolution failed: {vr_reason}", conn=self.db_conn)
            return

        # 2. ASR Transcribe
        source_segments = []
        duration_seconds = 0.0
        if self.transcriber_fn is not None:
            try:
                res = self.transcriber_fn(media_path, payload)
                if isinstance(res, list):
                    source_segments = res
                    duration_seconds = max((float((c or {}).get("end") or 0.0) for c in res if isinstance(c, dict)), default=0.0)
                elif isinstance(res, dict):
                    source_segments = res.get("segments") or res.get("cues") or []
                    duration_seconds = float(res.get("duration") or res.get("duration_seconds") or 0.0)
                elif isinstance(res, str):
                    source_segments = [{"text": res, "start": 0.0, "end": 2.0}]
                    duration_seconds = 2.0
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "TRANSCRIBER_FAILED", f"Transcriber error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                media_bytes = Path(media_path).read_bytes()
                content_type = str(payload.get("source_mime_type") or "audio/mpeg")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    res = loop.run_until_complete(
                        bot.transcribe_media_to_segments(
                            {"bytes": media_bytes, "content_type": content_type, "duration_seconds": 0},
                            allow_subdub_public=True,
                        )
                    )
                finally:
                    loop.close()
                source_segments = res.get("segments") or []
                duration_seconds = float(res.get("duration_seconds") or 0.0)
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_ASR_FAILED", f"ASR execution error: {type(exc).__name__}", conn=self.db_conn)
                return

        if not source_segments:
            fail_subdub_job(job_id, worker_id, claim_token, "EMPTY_SOURCE_TRANSCRIPT", "Source media yielded zero subtitle segments", conn=self.db_conn)
            return

        # 3. Translate segments
        if self.translator_fn is not None:
            try:
                t_res = self.translator_fn(source_segments, target_lang, payload)
                translated_segments = t_res if isinstance(t_res, list) else t_res.get("segments", [])
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "TRANSLATION_FAILED", f"Translator error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    t_out = loop.run_until_complete(
                        bot.translate_subtitle_segments(source_segments, target_lang, allow_confirmed_product=True)
                    )
                finally:
                    loop.close()
                translated_segments = t_out.get("segments") or t_out if isinstance(t_out, list) else []
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_TRANSLATION_FAILED", f"Translation error: {type(exc).__name__}", conn=self.db_conn)
                return

        char_count = sum(len(str((c or {}).get("text") or "")) for c in translated_segments if isinstance(c, dict))

        # Write subtitle artifact
        vtt_content = format_vtt_text(translated_segments)
        vtt_bytes = vtt_content.encode("utf-8")
        if not vtt_bytes or not vtt_content.startswith("WEBVTT"):
            fail_subdub_job(job_id, worker_id, claim_token, "INVALID_VTT_HEADER", "Combo subtitle generation failed", conn=self.db_conn)
            return
        subtitle_file = self.artifact_dir / f"{job_id}.vtt"
        subtitle_file.write_bytes(vtt_bytes)

        # 4. TTS Synthesis
        dub_audio_bytes = b""
        if self.tts_fn is not None:
            try:
                dub_audio_bytes = self.tts_fn(translated_segments, vr_data, payload)
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "TTS_FAILED", f"TTS error: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    synth_res = loop.run_until_complete(
                        bot.synthesize_dub_segment_chunks(
                            translated_segments,
                            voice_style=vr_data.get("_internal_provider_voice_id"),
                            voice_speed=vr_data.get("voice_speed", 1.0),
                            target_language=target_lang,
                        )
                    )
                finally:
                    loop.close()
                dub_audio_bytes = synth_res.get("audio_bytes") if isinstance(synth_res, dict) else (synth_res or b"")
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_TTS_FAILED", f"TTS error: {type(exc).__name__}", conn=self.db_conn)
                return

        if not dub_audio_bytes or len(dub_audio_bytes) == 0:
            fail_subdub_job(job_id, worker_id, claim_token, "TTS_SYNTHESIS_FAILED", "TTS synthesis produced zero bytes", conn=self.db_conn)
            return

        # 5. Mux / Render combo (both video subtitle + audio)
        is_video = str(payload.get("source_media_type") or "").lower() == "video" or bool(payload.get("is_video_source")) or Path(media_path).suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")
        output_format = "video_subtitle" if is_video else "audio"
        ext = "mp4" if is_video else "mp3"
        content_type = "video/mp4" if is_video else "audio/mpeg"

        final_media_bytes = b""
        if self.muxer_fn is not None:
            try:
                final_media_bytes, ext = self.muxer_fn(media_path, dub_audio_bytes, str(subtitle_file), payload)
                content_type = "video/mp4" if ext == "mp4" else "audio/mpeg"
                output_format = "video_subtitle" if ext == "mp4" else "audio"
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "MUX_FAILED", f"Muxer error: {type(exc).__name__}", conn=self.db_conn)
                return
        elif not is_video:
            final_media_bytes = dub_audio_bytes
        else:
            if not is_provider_calls_enabled():
                fail_subdub_job(job_id, worker_id, claim_token, "PROVIDER_CALLS_DISABLED", "Provider calls are disabled by environment gate (PROVIDER_CALLS=0)", conn=self.db_conn)
                return
            try:
                import bot
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    render_res = loop.run_until_complete(
                        bot.video_dubbing_render_video(
                            video_path=media_path,
                            audio_bytes=dub_audio_bytes,
                            mode="subtitle_plus_dub",
                            subtitle_file=str(subtitle_file),
                        )
                    )
                finally:
                    loop.close()
                final_media_bytes = render_res.get("video_bytes") if isinstance(render_res, dict) else (render_res or b"")
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "CANONICAL_MUX_FAILED", f"Mux error: {type(exc).__name__}", conn=self.db_conn)
                return

        if not final_media_bytes or len(final_media_bytes) == 0:
            fail_subdub_job(job_id, worker_id, claim_token, "EMPTY_MUX_OUTPUT", "Combo render produced zero bytes", conn=self.db_conn)
            return

        artifact_filename = f"{job_id}.{ext}"
        artifact_file = self.artifact_dir / artifact_filename
        artifact_file.write_bytes(final_media_bytes)
        file_size = artifact_file.stat().st_size
        file_sha256 = hashlib.sha256(final_media_bytes).hexdigest()

        # 6. Final Media Probe
        if self.probe_fn is not None:
            try:
                probe_ok, probe_info = self.probe_fn(str(artifact_file))
                if not probe_ok:
                    fail_subdub_job(job_id, worker_id, claim_token, "ARTIFACT_PROBE_FAILED", f"Probe error: {probe_info.get('reason', 'invalid media')}", conn=self.db_conn)
                    return
            except Exception as exc:
                fail_subdub_job(job_id, worker_id, claim_token, "ARTIFACT_PROBE_FAILED", f"Probe exception: {type(exc).__name__}", conn=self.db_conn)
                return
        else:
            if file_size <= 0:
                fail_subdub_job(job_id, worker_id, claim_token, "ARTIFACT_PROBE_FAILED", "Generated combo artifact has zero size", conn=self.db_conn)
                return

        delivery_url = f"{self.public_base_url}/{artifact_filename}"
        sub_delivery_url = f"{self.public_base_url}/{job_id}.vtt"
        if not is_safe_subdub_output_url(delivery_url) or not is_safe_subdub_output_url(sub_delivery_url):
            fail_subdub_job(job_id, worker_id, claim_token, "UNSAFE_DELIVERY_URL", "Constructed delivery URL violates safety invariants", conn=self.db_conn)
            return

        result_payload = {
            "output_url": delivery_url,
            "download_url": delivery_url,
            "url": delivery_url,
            "subtitle_url": sub_delivery_url,
            "format": ext,
            "output_format": output_format,
            "content_type": content_type,
            "size_bytes": file_size,
            "sha256": file_sha256,
            "duration_seconds": round(duration_seconds, 2),
            "char_count": char_count,
            "target_language": target_lang,
            "voice_profile_id": payload.get("voice_profile_id"),
            "mode": "subtitle_plus_dub",
            "artifact_path": str(artifact_file),
            "subtitle_path": str(subtitle_file),
        }
        complete_subdub_job(job_id, worker_id, claim_token, result=result_payload, conn=self.db_conn)


    def run(self, *, run_once: bool = False, max_jobs: int | None = None) -> int:
        """Main worker loop. Returns total number of jobs processed."""
        self._running = True
        self._stop_event.clear()
        jobs_processed = 0

        logger.info(
            f"SubDub worker daemon started (id={self.worker_id}, poll={self.poll_interval}s, "
            f"lease={self.lease_seconds}s, run_once={run_once}, max_jobs={max_jobs})"
        )

        while self._running and not self._stop_event.is_set():
            if max_jobs is not None and jobs_processed >= max_jobs:
                break

            try:
                claimed = self.process_one_job()
                if claimed:
                    jobs_processed += 1
                else:
                    if run_once:
                        break
                    self._stop_event.wait(timeout=self.poll_interval)
            except Exception as exc:
                logger.error(f"Unexpected error in worker loop: {exc}")
                if run_once:
                    break
                self._stop_event.wait(timeout=self.poll_interval)

        logger.info(f"SubDub worker daemon stopped. Processed {jobs_processed} jobs.")
        return jobs_processed


def run_doctor(db_conn: sqlite3.Connection | None = None) -> bool:
    """Run pre-start doctor/health check without calling any external providers."""
    import bot
    owned = db_conn is None
    db = db_conn or bot.db_connect()
    try:
        ensure_subdub_worker_queue_schema(db)
        # Verify schema
        row = db.execute("SELECT COUNT(*) FROM subdub_worker_jobs").fetchone()
        count = row[0] if row else 0
        print(f"DOCTOR_OK: subdub_worker_jobs accessible, row_count={count}")
        return True
    except Exception as exc:
        print(f"DOCTOR_FAILED: {exc}")
        return False
    finally:
        if owned:
            db.close()


def main():
    parser = argparse.ArgumentParser(description="TOAN AAS SubDub Dedicated Worker Daemon")
    parser.add_argument("--worker-id", default=os.getenv("SUBDUB_WORKER_ID", DEFAULT_WORKER_ID), help="Worker identifier")
    parser.add_argument("--poll-interval", type=float, default=float(os.getenv("SUBDUB_WORKER_POLL_INTERVAL", DEFAULT_POLL_INTERVAL)), help="Poll interval in seconds")
    parser.add_argument("--lease-seconds", type=int, default=int(os.getenv("SUBDUB_WORKER_LEASE_SECONDS", DEFAULT_LEASE_SECONDS)), help="Job claim lease duration")
    parser.add_argument("--heartbeat-interval", type=float, default=float(os.getenv("SUBDUB_WORKER_HEARTBEAT_INTERVAL", DEFAULT_HEARTBEAT_INTERVAL)), help="Heartbeat interval in seconds")
    parser.add_argument("--run-once", action="store_true", help="Process at most one job or exit if empty")
    parser.add_argument("--max-jobs", type=int, default=None, help="Process at most N jobs then exit")
    parser.add_argument("--dry-run", action="store_true", help="Run doctor check then exit")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"), help="Logging level")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] [subdub_worker] %(message)s",
    )

    if args.dry_run:
        ok = run_doctor()
        sys.exit(0 if ok else 1)

    daemon = SubDubWorkerDaemon(
        worker_id=args.worker_id,
        poll_interval=args.poll_interval,
        lease_seconds=args.lease_seconds,
        heartbeat_interval=args.heartbeat_interval,
    )

    def handle_signal(sig, frame):
        logger.info(f"Received signal {sig}, stopping daemon...")
        daemon.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    daemon.run(run_once=args.run_once, max_jobs=args.max_jobs)


if __name__ == "__main__":
    main()
