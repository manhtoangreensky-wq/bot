from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
from pathlib import Path
import time

import pytest

import bot
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_speaker


EXACT_AUTO_STATE = {
    "voice_kind": "auto_speaker_gender",
    "voice_selection_mode": "auto_speaker",
}


def _multi_module():
    spec = importlib.util.find_spec(
        "services.subdub_blackboxes.auto_multi_speaker"
    )
    assert spec is not None, "multi-speaker blackbox module is missing"
    return importlib.import_module(
        "services.subdub_blackboxes.auto_multi_speaker"
    )


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def _patch_one_frame_evidence(monkeypatch) -> None:
    frame_estimates = iter(((220.0, 0.74), None, None, None))
    monkeypatch.setattr(
        speaker_cast,
        "_estimate_frame_pitch_yin",
        lambda *_args, **_kwargs: next(frame_estimates),
    )
    monkeypatch.setattr(
        speaker_cast,
        "_frame_competing_pitch",
        lambda *_args, **_kwargs: (0.0, 0.0),
    )
    monkeypatch.setattr(
        speaker_cast,
        "_refine_full_rate_pitch",
        lambda _samples, estimated_hz, **_kwargs: estimated_hz,
    )
    monkeypatch.setattr(
        speaker_cast,
        "_pitch_spectrum_metrics",
        lambda *_args, **_kwargs: (1.0, 1.0),
    )


def test_auto_choices_set_and_clear_only_the_multi_marker(monkeypatch):
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )

    old = bot.subdub_apply_voice_choice(
        {},
        "auto_speaker_gender",
        activation_enabled=True,
    )
    multi = bot.subdub_apply_voice_choice(
        {},
        "auto_multi_speaker",
        activation_enabled=True,
    )
    manual = bot.subdub_apply_voice_choice(
        multi,
        "default_female",
        activation_enabled=True,
    )

    assert old == EXACT_AUTO_STATE
    assert multi["voice_kind"] == old["voice_kind"]
    assert multi["voice_selection_mode"] == old["voice_selection_mode"]
    assert multi["auto_speaker_lane"] == "multi"
    assert "auto_speaker_lane" not in manual
    assert "voice_selection_mode" not in manual


@pytest.mark.parametrize(
    "state",
    (
        {"mode": "dub"},
        {
            "mode": "subtitle_plus_dub",
            "active_flow": "subtitle_plus_dub",
            "requested_mode": "subtitle_plus_dub",
        },
    ),
)
def test_voice_menus_expose_one_old_and_one_multi_choice(
    monkeypatch,
    state,
):
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )

    callbacks = _callbacks(bot.video_dubbing_voice_keyboard("vi", state))

    assert callbacks.count("videodub|voice|auto_speaker_gender") == 1
    assert callbacks.count("videodub|voice|auto_multi_speaker") == 1


def test_old_and_multi_states_select_different_blackboxes(monkeypatch):
    multi_module = _multi_module()
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )
    selector = getattr(bot, "subdub_auto_blackbox_runner", None)
    multi_route = getattr(
        bot,
        "subdub_auto_multi_speaker_route_enabled",
        None,
    )

    assert callable(selector)
    assert callable(multi_route)
    assert selector(EXACT_AUTO_STATE) is auto_speaker.run_auto_speaker_blackbox
    assert selector(
        {**EXACT_AUTO_STATE, "auto_speaker_lane": "multi"}
    ) is multi_module.run_auto_multi_speaker_blackbox
    assert multi_route(EXACT_AUTO_STATE) is False
    assert multi_route(
        {**EXACT_AUTO_STATE, "auto_speaker_lane": "multi"}
    ) is True


def test_old_and_multi_jobs_have_separate_retry_leases(monkeypatch):
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )
    base = {
        "source_file_unique_id": "same-source",
        "mode": "dub",
        "active_flow": "dub_audio",
    }

    old_key = bot.subtitle_dub_pipeline_job_key(
        7,
        8,
        {**base, **EXACT_AUTO_STATE},
    )
    multi_key = bot.subtitle_dub_pipeline_job_key(
        7,
        8,
        {
            **base,
            **EXACT_AUTO_STATE,
            "auto_speaker_lane": "multi",
        },
    )

    assert old_key.endswith("|auto_speaker")
    assert multi_key.endswith("|auto_multi_speaker")
    assert old_key != multi_key


def test_multi_marker_does_not_change_auto_pricing(monkeypatch):
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )
    priced = {
        "mode": "dub",
        "billing_chars": 120,
        "auto_quote_billable_words": 24,
        "auto_quote_exact_known": True,
    }
    old = {**priced, **EXACT_AUTO_STATE}
    multi = {
        **priced,
        **EXACT_AUTO_STATE,
        "auto_speaker_lane": "multi",
    }

    assert auto_speaker.is_auto_speaker_state(old)
    assert auto_speaker.is_auto_speaker_state(multi)
    assert bot.video_dubbing_invoice_breakdown(old) == (
        bot.video_dubbing_invoice_breakdown(multi)
    )


def test_default_classifier_rejects_but_multi_profile_accepts_one_frame(
    monkeypatch,
):
    raw = b"\0" * speaker_cast.PCM_WINDOW_BYTES
    _patch_one_frame_evidence(monkeypatch)
    default_result = speaker_cast._estimate_window_pitch(
        raw,
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
    )

    assert default_result is None

    _patch_one_frame_evidence(monkeypatch)
    multi_result = speaker_cast._estimate_window_pitch(
        raw,
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
        allow_single_pitch_frame=True,
    )

    assert multi_result is not None
    assert multi_result[0] >= speaker_cast.HIGH_MIN_HZ
    assert multi_result[1] >= speaker_cast.MIN_REGISTER_CONFIDENCE


def test_multi_classifier_preserves_three_provider_labels_without_invention(
    monkeypatch,
):
    multi_module = _multi_module()
    labels = [f"chunk_00:speaker_{index}" for index in range(3)]
    ranges = {
        label: [(float(index), float(index + 1))]
        for index, label in enumerate(labels)
    }
    captured = {}

    def fake_classifier(
        pcm_path,
        ranges_by_speaker,
        *,
        deadline_monotonic,
        stop_requested,
        allow_single_pitch_frame,
    ):
        captured.update(
            {
                "pcm_path": pcm_path,
                "labels": list(ranges_by_speaker),
                "deadline": deadline_monotonic,
                "stopped": stop_requested(),
                "single_frame": allow_single_pitch_frame,
            }
        )
        return {
            label: {
                "speaker_id": label,
                "voice_register": "low" if index < 2 else "high",
                "confidence": 0.9,
            }
            for index, label in enumerate(ranges_by_speaker)
        }

    monkeypatch.setattr(
        speaker_cast,
        "classify_speaker_registers",
        fake_classifier,
    )
    result = multi_module.classify_multi_speaker_registers(
        "fixture.pcm",
        ranges,
        deadline_monotonic=123.0,
        stop_requested=lambda: False,
    )

    assert list(result) == labels
    assert captured == {
        "pcm_path": "fixture.pcm",
        "labels": labels,
        "deadline": 123.0,
        "stopped": False,
        "single_frame": True,
    }
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_module.classify_multi_speaker_registers(
            "fixture.pcm",
            {labels[0]: ranges[labels[0]]},
            deadline_monotonic=123.0,
            stop_requested=lambda: False,
        )
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_module.classify_multi_speaker_registers(
            "fixture.pcm",
            {
                f"chunk_00:speaker_{index}": [(0.0, 1.0)]
                for index in range(17)
            },
            deadline_monotonic=123.0,
            stop_requested=lambda: False,
        )


def test_three_provider_labels_keep_distinct_validated_voices():
    labels = [f"chunk_00:speaker_{index}" for index in range(3)]
    classifications = {
        labels[0]: {
            "speaker_id": labels[0],
            "voice_register": "low",
            "confidence": 0.91,
        },
        labels[1]: {
            "speaker_id": labels[1],
            "voice_register": "low",
            "confidence": 0.92,
        },
        labels[2]: {
            "speaker_id": labels[2],
            "voice_register": "high",
            "confidence": 0.93,
        },
    }
    casts = speaker_cast.assign_stable_voices(
        classifications,
        speaker_order=labels,
        validated_pools={
            "low": ["low-a", "low-b", "low-c"],
            "high": ["high-a", "high-b", "high-c"],
        },
        assignment_seed="a" * 64,
    )

    assert list(casts) == labels
    assert {item["speaker_id"] for item in casts.values()} == set(labels)
    assert len({item["voice_id"] for item in casts.values()}) == 3


def test_multi_adapter_injects_only_classifier_and_pcm_filter(monkeypatch):
    multi_module = _multi_module()
    captured = {"delegate": 0, "extract": 0}

    async def base_extract(
        prepared,
        state,
        *,
        channels,
        sample_rate,
        sample_format,
        audio_filter="",
    ):
        del prepared, state, channels, sample_rate, sample_format
        captured["extract"] += 1
        captured["audio_filter"] = audio_filter
        return "fixture.pcm"

    async def fake_old_blackbox(**kwargs):
        captured["delegate"] += 1
        captured["classifier"] = kwargs.get("classify_speakers")
        extracted = kwargs["extract_pcm"](
            {},
            kwargs["state"],
            channels=1,
            sample_rate=speaker_cast.PCM_SAMPLE_RATE,
            sample_format="s16le",
        )
        if inspect.isawaitable(extracted):
            extracted = await extracted
        captured["pcm"] = extracted
        return {"ok": True, "status": "fixture"}

    monkeypatch.setattr(
        auto_speaker,
        "run_auto_speaker_blackbox",
        fake_old_blackbox,
    )
    result = asyncio.run(
        multi_module.run_auto_multi_speaker_blackbox(
            lane_mode="dub",
            extract_pcm=base_extract,
            state={
                **EXACT_AUTO_STATE,
                "auto_speaker_lane": "multi",
            },
        )
    )

    assert result == {"ok": True, "status": "fixture"}
    assert captured == {
        "delegate": 1,
        "extract": 1,
        "audio_filter": multi_module.MULTI_PCM_AUDIO_FILTER,
        "classifier": multi_module.classify_multi_speaker_registers,
        "pcm": "fixture.pcm",
    }


def test_multi_filter_is_opt_in_to_the_shared_bounded_extractor(
    tmp_path,
    monkeypatch,
):
    multi_module = _multi_module()
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"source")
    calls = []

    monkeypatch.setattr(
        bot,
        "subtitle_dub_workspace_path_safety",
        lambda _workspace: {"allowed": True},
    )
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(
        bot.subdub_media_preflight,
        "timeout_for_stage",
        lambda *_args, **_kwargs: 77.0,
    )

    async def fake_run(command, timeout):
        calls.append((list(command), timeout))
        Path(command[-1]).write_bytes(b"\0\0" * 8_000)
        return True, "ok"

    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run)
    result = asyncio.run(
        bot._extract_subdub_auto_pcm(
            {
                "state": {
                    "_pipeline_workspace": str(tmp_path),
                    "_pipeline_saved_source_path": str(source_path),
                },
                "duration_seconds": 12,
            },
            {},
            channels=1,
            sample_rate=16_000,
            sample_format="s16le",
            audio_filter=multi_module.MULTI_PCM_AUDIO_FILTER,
        )
    )

    assert result == str(tmp_path / "auto_speaker_16000_mono_s16le.pcm")
    assert calls == [
        (
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source_path),
                "-t",
                "12",
                "-vn",
                "-ac",
                "1",
                "-af",
                multi_module.MULTI_PCM_AUDIO_FILTER,
                "-ar",
                "16000",
                "-f",
                "s16le",
                str(tmp_path / "auto_speaker_16000_mono_s16le.pcm"),
            ],
            77.0,
        )
    ]
