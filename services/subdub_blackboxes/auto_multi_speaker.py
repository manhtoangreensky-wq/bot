"""Multi-speaker acoustic profile adapter for the proven Auto SubDub lane."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from services import subdub_speaker_cast as speaker_cast

from . import auto_speaker


AUTO_MULTI_SPEAKER_LANE = "multi"
MULTI_PCM_AUDIO_FILTER = "highpass=f=70,lowpass=f=320,afftdn=nr=6:nf=-50"


def is_auto_multi_speaker_state(
    state: Mapping[str, object] | None,
) -> bool:
    current = state or {}
    return bool(
        auto_speaker.is_auto_speaker_state(current)
        and current.get("auto_speaker_lane") == AUTO_MULTI_SPEAKER_LANE
    )


def classify_multi_speaker_registers(
    pcm_path: str,
    ranges_by_speaker: dict[str, list[tuple[float, float]]],
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> dict[str, dict]:
    if (
        not isinstance(ranges_by_speaker, dict)
        or not 2 <= len(ranges_by_speaker) <= speaker_cast.MAX_AUTO_SPEAKER_LABELS
    ):
        raise speaker_cast.AutoCastManualRequired()
    return speaker_cast.classify_speaker_registers(
        pcm_path,
        ranges_by_speaker,
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
        allow_single_pitch_frame=True,
    )


async def run_auto_multi_speaker_blackbox(
    *,
    extract_pcm: Callable[..., Any],
    state: Mapping[str, object],
    **payload: Any,
) -> dict[str, Any]:
    current = state if isinstance(state, Mapping) else {}
    if not is_auto_multi_speaker_state(current) or not callable(extract_pcm):
        return {
            "ok": False,
            "status": speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
            "reason": speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
            "lane_mode": str(current.get("mode") or current.get("lane_mode") or ""),
            "public_copy_key": "voice_auto_manual_required",
        }

    async def extract_multi_pcm(
        prepared: dict,
        prepared_state: dict,
        **extract_kwargs: Any,
    ) -> Any:
        return await auto_speaker._maybe_await(
            extract_pcm(
                prepared,
                prepared_state,
                **extract_kwargs,
                audio_filter=MULTI_PCM_AUDIO_FILTER,
            )
        )

    return await auto_speaker.run_auto_speaker_blackbox(
        extract_pcm=extract_multi_pcm,
        classify_speakers=classify_multi_speaker_registers,
        state=current,
        **payload,
    )
