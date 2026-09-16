from __future__ import annotations

import hashlib
import os
import subprocess
from typing import Any, Callable, Mapping

from services import subdub_tts_checkpoint
from services.subdub_tts_checkpoint import SubdubTTSCheckpointManager, compute_tts_unit_key


# =====================================================================
# SPEC-06A LOCKED MANIFEST CONSTANTS (IMMUTABLE CANARY BINDINGS)
# =====================================================================
CANARY_JOB_ID: str = "c11830a5_canary_spec06b_three_voice"
LOCKED_PROVIDER: str = "key4u_minimax"
LOCKED_MODEL: str = "speech-02-hd"
LOCKED_TARGET_LANGUAGE: str = "vi"
APPROVED_BASE_SHA: str = "5e5f3bc5ec9435f43af00aac8e1c7eb7a5d7e397"

MAX_PAID_SUBMITS: int = 3
MAX_AUTO_SUBMITS_PER_UNIT: int = 1
MAX_PROVIDER_SPEND: float = 0.05
MAX_PROVIDER_SPEND_UNIT: str = "USD"
FAIL_FAST_ON_FIRST_AMBIGUOUS: bool = True

LOCKED_CANARY_UNITS: dict[str, dict[str, Any]] = {
    "unit_44f73b7d827cbb74507537ae": {
        "cue_id": "cue_001",
        "speaker_id": "chunk_00:speaker_0",
        "voice_id": "English_ConfidentWoman",
        "text": "Lời thoại phụ đề tiếng Việt thứ 1 chuẩn xác",
        "start": 0.0,
        "end": 2.0,
        "word_count": 10,
    },
    "unit_6ec0b605fa5f1ef983c33ed8": {
        "cue_id": "cue_002",
        "speaker_id": "chunk_00:speaker_1",
        "voice_id": "English_DecentYoungMan",
        "text": "Lời thoại phụ đề tiếng Việt thứ 2 chuẩn xác",
        "start": 2.5,
        "end": 4.5,
        "word_count": 10,
    },
    "unit_c6515b5f8a22fc4245e25266": {
        "cue_id": "cue_003",
        "speaker_id": "chunk_00:speaker_2",
        "voice_id": "English_PassionateWarrior",
        "text": "Lời thoại phụ đề tiếng Việt thứ 3 chuẩn xác",
        "start": 5.0,
        "end": 7.0,
        "word_count": 10,
    },
}


# =====================================================================
# CANARY GUARD EXCEPTIONS
# =====================================================================
class SubdubCanaryError(Exception):
    """Base exception for SubDub Canary execution harness."""


class CanaryUnauthorizedUnitError(SubdubCanaryError):
    """Raised when an unauthorized cue or unit key attempts execution."""


class CanarySubmitLimitExceededError(SubdubCanaryError):
    """Raised when total submissions or per-unit submissions exceed authorized limits."""


class CanarySpendLimitExceededError(SubdubCanaryError):
    """Raised when estimated or actual spend exceeds authorized spend ceiling."""


class CanaryAmbiguousAbortError(SubdubCanaryError):
    """Raised when an ambiguous result or execution error forces fail-fast abort."""


class CanaryProviderMismatchError(SubdubCanaryError):
    """Raised when provider or model deviates from locked key4u_minimax / speech-02-hd."""


class CanaryRuntimeSHAMismatchError(SubdubCanaryError):
    """Raised when the running code commit does not match the authorized runtime SHA."""


class CanaryPrestateError(SubdubCanaryError):
    """Raised when checkpoint state before execution is not clean NOT_STARTED."""


class CanaryContractDriftError(SubdubCanaryError):
    """Raised when cue fields drift from the locked SPEC-06A manifest."""


# =====================================================================
# CANARY EXECUTION HARNESS
# =====================================================================
class SubdubCanaryExecutionHarness:
    """
    Owner-governed, isolated execution harness for the SubDub SPEC-06B paid canary.

    Enforces:
    1. Exact allowlist of 3 locked units.
    2. Hard cap of MAX_PAID_SUBMITS=3 total provider boundary submissions.
    3. Max 1 automatic submission per unit (zero auto-resubmit).
    4. Fail-fast on first ambiguous result or corruption.
    5. Pinned provider key4u_minimax and model speech-02-hd.
    6. Runtime SHA binding.
    7. Clean prestate check (NOT_STARTED).
    8. Spend limit guard (0.05 USD).
    """

    def __init__(
        self,
        workspace: str,
        job_id: str = CANARY_JOB_ID,
        target_language: str = LOCKED_TARGET_LANGUAGE,
        runtime_sha: str = APPROVED_BASE_SHA,
        checkpoint_mgr: SubdubTTSCheckpointManager | None = None,
        fail_fast: bool = FAIL_FAST_ON_FIRST_AMBIGUOUS,
        max_submits: int = MAX_PAID_SUBMITS,
        max_spend: float = MAX_PROVIDER_SPEND,
    ) -> None:
        self.workspace = os.path.abspath(str(workspace or "."))
        self.job_id = str(job_id or CANARY_JOB_ID)
        if self.job_id != CANARY_JOB_ID:
            raise CanaryContractDriftError(
                f"job_id_mismatch: {self.job_id} != locked {CANARY_JOB_ID}"
            )
        self.target_language = str(target_language or LOCKED_TARGET_LANGUAGE)
        if self.target_language != LOCKED_TARGET_LANGUAGE:
            raise CanaryContractDriftError(
                f"target_language_mismatch: {self.target_language} != locked {LOCKED_TARGET_LANGUAGE}"
            )

        self.runtime_sha = str(runtime_sha or APPROVED_BASE_SHA)
        self.fail_fast = bool(fail_fast)
        self.max_submits = int(max_submits)
        self.max_spend = float(max_spend)

        self.checkpoint_mgr = checkpoint_mgr or SubdubTTSCheckpointManager(
            workspace=self.workspace,
            job_id=self.job_id,
            target_language=self.target_language,
        )

        self.total_submits: int = 0
        self.unit_submits: dict[str, int] = {k: 0 for k in LOCKED_CANARY_UNITS}
        self.accumulated_spend: float = 0.0
        self.aborted: bool = False
        self.abort_reason: str = ""
        self.executed_units: list[dict[str, Any]] = []

    def get_current_runtime_sha(self) -> str:
        """Resolve current runtime SHA via git rev-parse HEAD if available."""
        env_sha = os.getenv("RUNNING_COMMIT_SHA") or os.getenv("CANARY_RUNTIME_SHA")
        if env_sha:
            return env_sha.strip()
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            return res.stdout.strip()
        except Exception:
            return self.runtime_sha

    def verify_runtime_sha(self, current_sha: str | None = None) -> None:
        """Enforce that runtime commit matches authorized SHA."""
        resolved = (current_sha or self.get_current_runtime_sha()).strip()
        if resolved != self.runtime_sha:
            raise CanaryRuntimeSHAMismatchError(
                f"runtime_sha_drift: current={resolved} != approved={self.runtime_sha}"
            )

    def verify_checkpoint_prestate(self) -> None:
        """Enforce that all canary units start from clean NOT_STARTED state."""
        for unit_key, locked in LOCKED_CANARY_UNITS.items():
            entry = self.checkpoint_mgr.entries.get(unit_key)
            if entry is not None:
                state = entry.get("state")
                if state != subdub_tts_checkpoint.STATE_NOT_STARTED:
                    raise CanaryPrestateError(
                        f"dirty_canary_prestate: unit {unit_key} for cue {locked['cue_id']} "
                        f"already in state '{state}', expected '{subdub_tts_checkpoint.STATE_NOT_STARTED}'"
                    )

    def verify_cue_drift(self, cue: Mapping[str, Any], voice_id: str) -> str:
        """
        Validate cue against locked SPEC-06A manifest.
        Returns validated unit_key.
        """
        cid = str(cue.get("cue_id") or cue.get("id") or "")
        spk_id = str(cue.get("speaker_id") or "")
        text = str(cue.get("text") or "").strip()
        voice_id_str = str(voice_id or "").strip()

        unit_key = compute_tts_unit_key(
            job_id=self.job_id,
            cue_id=cid,
            speaker_id=spk_id,
            voice_id=voice_id_str,
            text=text,
            target_language=self.target_language,
        )

        if unit_key not in LOCKED_CANARY_UNITS:
            raise CanaryUnauthorizedUnitError(
                f"unauthorized_canary_unit: key={unit_key} cue_id={cid} speaker={spk_id} voice={voice_id_str} "
                f"is not in the locked 3-voice canary allowlist"
            )

        locked = LOCKED_CANARY_UNITS[unit_key]
        if cid != locked["cue_id"]:
            raise CanaryContractDriftError(
                f"cue_id drift for {unit_key}: {cid} != locked {locked['cue_id']}"
            )
        if spk_id != locked["speaker_id"]:
            raise CanaryContractDriftError(
                f"speaker_id drift for {unit_key}: {spk_id} != locked {locked['speaker_id']}"
            )
        if voice_id_str != locked["voice_id"]:
            raise CanaryContractDriftError(
                f"voice_id drift for {unit_key}: {voice_id_str} != locked {locked['voice_id']}"
            )
        if text != locked["text"]:
            raise CanaryContractDriftError(
                f"text drift for {unit_key}: '{text}' != locked '{locked['text']}'"
            )

        return unit_key

    def estimate_unit_cost(self, text: str) -> float:
        """Estimate provider spend in USD (conservative rate for MiniMax speech-02-hd)."""
        char_count = len(text)
        # Conservative rate: $0.00003 per character
        return max(0.0005, round(char_count * 0.00003, 6))

    def execute_unit(
        self,
        cue: Mapping[str, Any],
        voice_id: str,
        synthesize_fn: Callable[..., tuple[bytes, float, str]],
        provider: str = LOCKED_PROVIDER,
        model: str = LOCKED_MODEL,
    ) -> dict[str, Any]:
        """
        Execute synthesis for a single locked canary unit under strict gates.
        """
        # 1. Check fail-fast aborted state
        if self.aborted:
            raise CanaryAmbiguousAbortError(
                f"canary_harness_aborted: prior failure halted canary execution ({self.abort_reason})"
            )

        # 2. Pin provider and model
        if provider != LOCKED_PROVIDER:
            raise CanaryProviderMismatchError(
                f"unauthorized_provider: '{provider}' != locked '{LOCKED_PROVIDER}'"
            )
        if model != LOCKED_MODEL:
            raise CanaryProviderMismatchError(
                f"unauthorized_model: '{model}' != locked '{LOCKED_MODEL}'"
            )

        # 3. Verify cue drift & allowlist
        unit_key = self.verify_cue_drift(cue, voice_id)
        cid = str(cue.get("cue_id") or cue.get("id") or "")
        text = str(cue.get("text") or "").strip()

        # 4. Check spend guard
        est_cost = self.estimate_unit_cost(text)
        if self.accumulated_spend + est_cost > self.max_spend:
            self.aborted = True
            self.abort_reason = f"spend limit exceeded ({self.accumulated_spend + est_cost:.4f} > {self.max_spend})"
            raise CanarySpendLimitExceededError(
                f"spend_limit_exceeded: estimated {self.accumulated_spend + est_cost:.4f} USD > max {self.max_spend} USD"
            )

        # 5. Check submission limits
        if self.total_submits >= self.max_submits:
            self.aborted = True
            self.abort_reason = f"total submit limit reached ({self.total_submits} >= {self.max_submits})"
            raise CanarySubmitLimitExceededError(
                f"hard_max_submits_exceeded: total submits {self.total_submits} >= authorized max {self.max_submits}"
            )

        if self.unit_submits.get(unit_key, 0) >= MAX_AUTO_SUBMITS_PER_UNIT:
            self.aborted = True
            self.abort_reason = f"unit resubmit forbidden ({unit_key})"
            raise CanarySubmitLimitExceededError(
                f"unit_resubmit_forbidden: unit {unit_key} already submitted {self.unit_submits[unit_key]} time(s)"
            )

        # 6. Intent recording via checkpoint manager
        reused, artifact_path, audio_bytes, entry = self.checkpoint_mgr.prepare_cue_intent(cue, voice_id)
        if reused:
            # Already completed and validated
            res = {
                "unit_key": unit_key,
                "cue_id": cid,
                "reused": True,
                "artifact_path": artifact_path,
                "duration": entry.get("duration", 0.0),
                "sha256": entry.get("artifact_sha256", ""),
                "provider_request_id": entry.get("provider_request_id", ""),
                "state": entry.get("state"),
            }
            self.executed_units.append(res)
            return res

        # 7. Record submission attempt at provider boundary
        self.total_submits += 1
        self.unit_submits[unit_key] = self.unit_submits.get(unit_key, 0) + 1

        # 8. Call synthesis function with fail-fast catch
        try:
            audio_bytes, duration, provider_req_id = synthesize_fn(
                text=text,
                voice_id=voice_id,
                model=model,
                cue_id=cid,
                target_language=self.target_language,
            )
        except Exception as exc:
            self.aborted = True
            self.abort_reason = f"provider call exception on unit {unit_key}: {exc}"
            # Mark ambiguous in checkpoint
            cur_entry = self.checkpoint_mgr.entries.get(unit_key) or {}
            cur_entry.update({
                "state": subdub_tts_checkpoint.STATE_AMBIGUOUS,
                "error": str(exc),
                "fail_fast_aborted": True,
            })
            self.checkpoint_mgr.entries[unit_key] = cur_entry
            self.checkpoint_mgr._save_manifest_atomic()
            raise CanaryAmbiguousAbortError(
                f"canary_fail_fast_aborted: unit {unit_key} failed at provider boundary: {exc}"
            ) from exc

        # 9. Verify artifact container, decode, and duration via checkpoint manager
        try:
            success_entry = self.checkpoint_mgr.record_cue_success(
                cue=cue,
                voice_id=voice_id,
                audio_bytes=audio_bytes,
                duration=duration,
                provider_label=f"{provider}:{model}",
            )
        except Exception as exc:
            self.aborted = True
            self.abort_reason = f"artifact validation/recording failure on unit {unit_key}: {exc}"
            raise CanaryAmbiguousAbortError(
                f"canary_fail_fast_aborted: unit {unit_key} failed artifact validation: {exc}"
            ) from exc

        # 10. Record spend & update execution entry
        self.accumulated_spend += est_cost
        success_entry["provider_request_id"] = str(provider_req_id or "")
        success_entry["estimated_cost_usd"] = est_cost
        self.checkpoint_mgr.entries[unit_key] = success_entry
        self.checkpoint_mgr._save_manifest_atomic()

        res = {
            "unit_key": unit_key,
            "cue_id": cid,
            "reused": False,
            "artifact_path": success_entry.get("artifact_path"),
            "duration": success_entry.get("duration", 0.0),
            "sha256": success_entry.get("artifact_sha256", ""),
            "provider_request_id": provider_req_id,
            "estimated_cost_usd": est_cost,
            "state": success_entry.get("state"),
        }
        self.executed_units.append(res)
        return res

    def execute_batch(
        self,
        cues: list[Mapping[str, Any]],
        voice_map: Mapping[str, str],
        synthesize_fn: Callable[..., tuple[bytes, float, str]],
        provider: str = LOCKED_PROVIDER,
        model: str = LOCKED_MODEL,
        current_sha: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute entire canary batch under fail-fast contract.
        """
        self.verify_runtime_sha(current_sha)
        self.verify_checkpoint_prestate()

        batch_results = []
        for cue in cues:
            spk_id = str(cue.get("speaker_id") or "")
            voice_id = voice_map.get(spk_id) or ""
            res = self.execute_unit(
                cue=cue,
                voice_id=voice_id,
                synthesize_fn=synthesize_fn,
                provider=provider,
                model=model,
            )
            batch_results.append(res)

        return {
            "canary_job_id": self.job_id,
            "target_language": self.target_language,
            "provider": provider,
            "model": model,
            "runtime_sha": self.runtime_sha,
            "total_submits": self.total_submits,
            "units_completed": len(batch_results),
            "accumulated_spend_usd": self.accumulated_spend,
            "max_spend_usd": self.max_spend,
            "aborted": self.aborted,
            "results": batch_results,
        }
