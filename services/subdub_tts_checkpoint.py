from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Mapping

from services import subdub_tts_artifact_validator


class SubdubTTSCheckpointError(Exception):
    """Base exception for TTS checkpoint errors."""


class SubdubTTSAmbiguousSubmissionError(SubdubTTSCheckpointError):
    """Raised when a cue was left in SUBMITTING/AMBIGUOUS state; automatic resubmission forbidden."""


class SubdubTTSArtifactCorruptionError(SubdubTTSCheckpointError):
    """Raised when a completed artifact file is missing, empty, or hash-mismatched."""


class SubdubTTSContractMismatchError(SubdubTTSCheckpointError):
    """Raised when text, voice, or speaker assignment changes across restart for the same cue."""


class SubdubTTSQuoteMismatchError(SubdubTTSCheckpointError):
    """Raised when the confirmed quote identity changes across restart."""


STATE_NOT_STARTED = "NOT_STARTED"
STATE_INTENT_PERSISTED = "INTENT_PERSISTED"
STATE_SUBMITTING = "SUBMITTING"
STATE_SUCCEEDED = "SUCCEEDED"
STATE_AMBIGUOUS = "AMBIGUOUS"
STATE_FAILED_PRE_SUBMIT = "FAILED_PRE_SUBMIT"
STATE_FAILED_TERMINAL = "FAILED_TERMINAL"


def compute_tts_unit_key(
    job_id: str,
    cue_id: str,
    speaker_id: str,
    voice_id: str,
    text: str,
    target_language: str = "vi",
) -> str:
    text_clean = str(text or "").strip()
    text_hash = hashlib.sha256(text_clean.encode("utf-8")).hexdigest()[:16]
    raw = (
        f"{str(job_id or '')}:"
        f"{str(cue_id or '')}:"
        f"{str(speaker_id or '')}:"
        f"{str(voice_id or '')}:"
        f"{text_hash}:"
        f"{str(target_language or '')}"
    )
    return f"unit_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


class SubdubTTSCheckpointManager:
    def __init__(
        self,
        workspace: str,
        job_id: str,
        target_language: str = "vi",
        quote_fingerprint: str = "",
    ) -> None:
        self.workspace = os.path.abspath(str(workspace or "."))
        self.job_id = str(job_id or "job_unspecified")
        self.target_language = str(target_language or "vi")
        self.quote_fingerprint = str(quote_fingerprint or "")
        self.manifest_path = os.path.join(self.workspace, "subdub_tts_manifest.json")
        self.artifacts_dir = os.path.join(self.workspace, "tts_artifacts")
        self.entries: dict[str, dict[str, Any]] = {}
        self.cue_id_to_unit_key: dict[str, str] = {}
        self._load_manifest()

    def _load_manifest(self) -> None:
        if not os.path.isfile(self.manifest_path):
            return
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            raise SubdubTTSCheckpointError(f"manifest_read_error: {exc}") from exc

        if not isinstance(data, dict):
            return

        manifest_quote = str(data.get("quote_fingerprint") or "")
        if (
            self.quote_fingerprint
            and manifest_quote
            and manifest_quote != self.quote_fingerprint
        ):
            raise SubdubTTSQuoteMismatchError(
                f"quote_fingerprint_mismatch: {manifest_quote} != {self.quote_fingerprint}"
            )

        manifest_job_id = str(data.get("job_id") or "")
        if self.job_id and manifest_job_id and manifest_job_id != self.job_id:
            raise SubdubTTSContractMismatchError(
                f"job_id_mismatch: {manifest_job_id} != {self.job_id}"
            )

        raw_entries = data.get("entries")
        if isinstance(raw_entries, dict):
            for k, v in raw_entries.items():
                if isinstance(v, dict):
                    self.entries[str(k)] = dict(v)
                    cid = str(v.get("cue_id") or "")
                    if cid:
                        self.cue_id_to_unit_key[cid] = str(k)

    def _save_manifest_atomic(self) -> None:
        os.makedirs(self.workspace, exist_ok=True)
        os.makedirs(self.artifacts_dir, exist_ok=True)
        payload = {
            "version": "1.0",
            "job_id": self.job_id,
            "target_language": self.target_language,
            "quote_fingerprint": self.quote_fingerprint,
            "updated_at": time.time(),
            "entries": self.entries,
        }
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        tmp_path = os.path.join(self.workspace, f"subdub_tts_manifest_{time.time_ns()}.tmp")
        try:
            with open(tmp_path, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.manifest_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def compute_key(self, cue: Mapping[str, Any], voice_id: str) -> str:
        cid = str(cue.get("cue_id") or cue.get("id") or "")
        spk_id = str(cue.get("speaker_id") or "")
        text = str(cue.get("text") or "").strip()
        return compute_tts_unit_key(
            self.job_id,
            cid,
            spk_id,
            voice_id,
            text,
            self.target_language,
        )

    def prepare_cue_intent(
        self,
        cue: Mapping[str, Any],
        voice_id: str,
    ) -> tuple[bool, str, bytes, dict[str, Any] | None]:
        cid = str(cue.get("cue_id") or cue.get("id") or "")
        spk_id = str(cue.get("speaker_id") or "")
        text = str(cue.get("text") or "").strip()
        if not text:
            raise SubdubTTSCheckpointError(f"empty_tts_text for cue {cid}")

        unit_key = self.compute_key(cue, voice_id)

        # Detect text, voice, or speaker drift on the same cue across restart
        prev_key = self.cue_id_to_unit_key.get(cid)
        if prev_key and prev_key != unit_key:
            prev_entry = self.entries.get(prev_key, {})
            raise SubdubTTSContractMismatchError(
                f"cue_contract_drift for {cid}: prev_voice={prev_entry.get('voice_id')} curr_voice={voice_id} prev_spk={prev_entry.get('speaker_id')} curr_spk={spk_id} prev_key={prev_key} curr_key={unit_key}"
            )

        entry = self.entries.get(unit_key)
        if entry:
            state = entry.get("state")
            if state == STATE_SUCCEEDED:
                path = str(entry.get("artifact_path") or "")
                expected_hash = str(entry.get("artifact_sha256") or "")
                if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
                    raise SubdubTTSArtifactCorruptionError(
                        f"artifact_missing_or_empty for cue {cid}: {path}"
                    )
                with open(path, "rb") as f:
                    data = f.read()
                actual_hash = hashlib.sha256(data).hexdigest()
                if actual_hash != expected_hash:
                    raise SubdubTTSArtifactCorruptionError(
                        f"artifact_hash_mismatch for cue {cid}: {actual_hash} != {expected_hash}"
                    )
                # Independent container/decode/duration validation on reuse
                validation_res = subdub_tts_artifact_validator.validate_tts_audio_artifact(path)
                if not validation_res.ok:
                    raise SubdubTTSArtifactCorruptionError(
                        f"reused_artifact_invalid for cue {cid}: status={validation_res.status} detail={validation_res.detail}"
                    )
                return True, path, data, dict(entry)

            if state in (STATE_SUBMITTING, STATE_AMBIGUOUS):
                raise SubdubTTSAmbiguousSubmissionError(
                    f"ambiguous_prior_submit for cue {cid} (state={state}); auto-resubmit forbidden"
                )

        # Record intent before submit
        self.entries[unit_key] = {
            "tts_unit_key": unit_key,
            "cue_id": cid,
            "speaker_id": spk_id,
            "voice_id": voice_id,
            "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "target_language": self.target_language,
            "state": STATE_SUBMITTING,
            "started_at": time.time(),
            "completed_at": None,
            "artifact_path": "",
            "artifact_sha256": "",
            "provider_request_id": "",
        }
        self.cue_id_to_unit_key[cid] = unit_key
        self._save_manifest_atomic()
        return False, "", b"", None

    def record_cue_success(
        self,
        cue: Mapping[str, Any],
        voice_id: str,
        audio_bytes: bytes,
        duration: float,
        provider_label: str = "",
        chunks_meta: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not audio_bytes or len(audio_bytes) == 0:
            raise SubdubTTSArtifactCorruptionError("empty_audio_bytes_on_success")

        unit_key = self.compute_key(cue, voice_id)
        cid = str(cue.get("cue_id") or cue.get("id") or "")
        os.makedirs(self.artifacts_dir, exist_ok=True)
        artifact_path = os.path.join(self.artifacts_dir, f"{unit_key}.mp3")
        tmp_artifact = artifact_path + f".{time.time_ns()}.tmp"
        with open(tmp_artifact, "wb") as f:
            f.write(audio_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_artifact, artifact_path)

        # Independent audio container, decode, and bitstream duration validation BEFORE SUCCEEDED
        validation_res = subdub_tts_artifact_validator.validate_tts_audio_artifact(artifact_path)
        if not validation_res.ok:
            # SUCCEEDED_BEFORE_DECODE = NO! State must NOT become SUCCEEDED.
            entry = self.entries.get(unit_key) or {
                "tts_unit_key": unit_key,
                "cue_id": cid,
                "speaker_id": str(cue.get("speaker_id") or ""),
                "voice_id": voice_id,
                "text_hash": hashlib.sha256(str(cue.get("text") or "").strip().encode("utf-8")).hexdigest(),
                "target_language": self.target_language,
            }
            entry.update({
                "state": STATE_AMBIGUOUS,
                "completed_at": None,
                "artifact_path": artifact_path,
                "artifact_sha256": hashlib.sha256(audio_bytes).hexdigest(),
                "validation_status": validation_res.status,
                "validation_detail": validation_res.detail,
            })
            self.entries[unit_key] = entry
            self.cue_id_to_unit_key[cid] = unit_key
            self._save_manifest_atomic()
            raise SubdubTTSArtifactCorruptionError(
                f"artifact_validation_failed for cue {cid}: status={validation_res.status} detail={validation_res.detail}"
            )

        artifact_sha256 = hashlib.sha256(audio_bytes).hexdigest()
        entry = self.entries.get(unit_key) or {
            "tts_unit_key": unit_key,
            "cue_id": cid,
            "speaker_id": str(cue.get("speaker_id") or ""),
            "voice_id": voice_id,
            "text_hash": hashlib.sha256(str(cue.get("text") or "").strip().encode("utf-8")).hexdigest(),
            "target_language": self.target_language,
        }
        clean_chunks_meta: list[dict[str, Any]] = []
        if chunks_meta:
            for item in chunks_meta:
                clean_item = {k: v for k, v in item.items() if k != "audio_bytes"}
                clean_chunks_meta.append(clean_item)
        canonical_duration = float(validation_res.duration if validation_res.duration > 0 else (duration or 0.0))
        entry.update({
            "state": STATE_SUCCEEDED,
            "completed_at": time.time(),
            "artifact_path": artifact_path,
            "artifact_sha256": artifact_sha256,
            "duration": canonical_duration,
            "provider_label": str(provider_label or ""),
            "chunks_meta": clean_chunks_meta,
            "validation_status": validation_res.status,
            "validation_container": validation_res.container,
            "validation_codec": validation_res.codec,
        })
        self.entries[unit_key] = entry
        self.cue_id_to_unit_key[cid] = unit_key
        self._save_manifest_atomic()
        return entry

    def reconstruct_chunks(
        self,
        cue: Mapping[str, Any],
        entry: Mapping[str, Any],
        audio_bytes: bytes,
    ) -> list[dict[str, Any]]:
        raw_meta = entry.get("chunks_meta")
        if isinstance(raw_meta, list) and raw_meta:
            reconstructed: list[dict[str, Any]] = []
            for item in raw_meta:
                if isinstance(item, Mapping):
                    chunk = dict(item)
                    chunk["audio_bytes"] = audio_bytes
                    reconstructed.append(chunk)
            if reconstructed:
                return reconstructed
        cid = str(cue.get("cue_id") or cue.get("id") or "")
        start = float(cue.get("start") or 0.0)
        end = float(cue.get("end") or 0.0)
        dur = float(entry.get("duration") or max(0.0, end - start))
        return [{
            "index": cue.get("index"),
            "cue_id": cid,
            "start": start,
            "end": end,
            "text": str(cue.get("text") or ""),
            "audio_bytes": audio_bytes,
            "audio_duration": dur,
            "raw_audio_duration": dur,
        }]

    def record_cue_ambiguous(
        self,
        cue: Mapping[str, Any],
        voice_id: str,
        error: Exception | str,
    ) -> None:
        unit_key = self.compute_key(cue, voice_id)
        entry = self.entries.get(unit_key)
        if entry:
            entry["state"] = STATE_AMBIGUOUS
            entry["error_detail"] = str(error)
            entry["failed_at"] = time.time()
            self._save_manifest_atomic()

    def record_cue_pre_submit_failure(
        self,
        cue: Mapping[str, Any],
        voice_id: str,
        error: Exception | str,
    ) -> None:
        unit_key = self.compute_key(cue, voice_id)
        entry = self.entries.get(unit_key)
        if entry:
            entry["state"] = STATE_FAILED_PRE_SUBMIT
            entry["error_detail"] = str(error)
            entry["failed_at"] = time.time()
            self._save_manifest_atomic()
