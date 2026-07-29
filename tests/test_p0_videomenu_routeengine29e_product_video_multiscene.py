from __future__ import annotations

import hashlib
import inspect
import json
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from services import product_video_multiscene_engine as multiscene
from services import product_video_one_scene_engine as one_scene
from services import product_video_poll_recovery as poll_recovery
from services import video_engine_contract
from services import multiscene_video_pipeline as pipeline


RUNTIME_SHA = "3344ce1228cc04769d8a9bbbd92b3899081f69c6"
NOW = 1_785_340_000.0


def _flags(**overrides: str) -> dict[str, str]:
    values = {
        "PRODUCT_VIDEO_MULTISCENE_ENGINE_ENABLED": "1",
        "PRODUCT_VIDEO_MULTISCENE_PUBLIC_ALLOWED": "0",
        "PRODUCT_VIDEO_MULTISCENE_REAL_PROVIDER_ENABLED": "0",
        "PRODUCT_VIDEO_MULTISCENE_AUTO_RESUBMIT": "0",
        "PRODUCT_VIDEO_MULTISCENE_AUTO_FALLBACK": "0",
    }
    values.update(overrides)
    return values


def _manifest(**overrides) -> dict:
    values = video_engine_contract.build_worker_manifest(
        worker_sha=RUNTIME_SHA,
        worker_instance_id="fixture-worker-29e",
        supported_products=["product_video"],
        supported_modes=["multi_scene"],
        renderer_name="fixture-multiscene-real-mp4",
        renderer_version="1",
        ffmpeg_version="6.1",
        provider_enabled=True,
        local_enabled=False,
        queue_ready=True,
        worker_connected=True,
        heartbeat_fresh=True,
        health_ok=True,
        worker_status="healthy",
        capabilities=list(multiscene.REQUIRED_WORKER_CAPABILITIES),
        provider_availability={"fake_provider": True, "paid_provider": True},
    )
    values.update(
        {
            "artifact_ready": True,
            "engine_adapters": [multiscene.ENGINE_ADAPTER],
            "provider_routes": ["fake_provider", "paid_provider"],
            "offline_fixture": True,
        }
    )
    values.update(overrides)
    return values


def _scene_inputs(
    count: int,
    *,
    required_audio_scene: int = 0,
    transitions: tuple[str, ...] | None = None,
) -> list[dict]:
    return [
        {
            "scene_id": f"scene_{index:03d}",
            "scene_index": index,
            "scene_specification": f"Canh {index}: quay san pham Aurora dung thu tu.",
            "original_user_prompt": f"Prompt goc canh {index}, khong duoc thay doi chi tiet.",
            "product_name": "Aurora",
            "required_visual_attributes": (
                "chai thuy tinh trong",
                f"nhan canh {index}",
            ),
            "forbidden_claims": ("khong tuyen bo chua benh",),
            "duration_seconds": 2,
            "aspect_ratio": "9:16",
            "input_assets": (f"fixture-product-reference-{index}",),
            "audio_requirement": {
                "required": index == required_audio_scene,
                "artifact_path": "",
            },
            "voice_requirement": {"required": False, "artifact_path": ""},
            "provider": "fake_provider",
            "model": "fixture-model-v1",
            "transition": (
                transitions[index - 1]
                if transitions is not None and index - 1 < len(transitions)
                else "cut"
            ),
        }
        for index in range(1, count + 1)
    ]


def _graph(
    count: int,
    *,
    required_audio_scene: int = 0,
    transitions: tuple[str, ...] | None = None,
):
    return multiscene.compile_product_video_scene_graph(
        scenes=_scene_inputs(
            count,
            required_audio_scene=required_audio_scene,
            transitions=transitions,
        ),
        user_id=172203,
        confirmation_id="confirm-29e",
        language="vi",
    )


def _request(
    count: int,
    *,
    graph=None,
    admin_no_charge: bool = True,
    charge_plan: dict | None = None,
    audio_policy: dict | None = None,
    voice_policy: dict | None = None,
    final_assets: dict | None = None,
):
    selected_graph = graph or _graph(count)
    return multiscene.build_product_video_multiscene_request(
        user_id=172203,
        confirmation_id="confirm-29e",
        language="vi",
        scene_graph=selected_graph,
        input_assets=("fixture-product-reference-parent",),
        aspect_ratio="9:16",
        audio_policy=audio_policy or {"enabled": False, "promised": False},
        voice_policy=voice_policy or {"enabled": False, "promised": False},
        final_assets=final_assets
        or {
            "enable_subtitle": False,
            "voice_audio_path": "",
            "bgm_audio_path": "",
            "logo_path": "",
            "logo_text": "",
            "logo_position": "bottom_right",
        },
        provider_selection="fake_provider",
        explicit_confirmation_receipt={"confirmation_id": "confirm-29e"},
        runtime_sha=RUNTIME_SHA,
        expected_worker_sha=RUNTIME_SHA,
        admin_no_charge=admin_no_charge,
        charge_plan=charge_plan,
    )


def _store(tmp_path: Path) -> poll_recovery.ProductVideoPollRecoveryStore:
    return poll_recovery.ProductVideoPollRecoveryStore(tmp_path / "durable-29e")


def _unexpected(name: str):
    def fail(*_args, **_kwargs):
        raise AssertionError(f"unexpected side effect: {name}")

    return fail


def _effects(calls: list[str]) -> dict:
    def deliver(payload: dict) -> dict:
        calls.append("delivery")
        assert payload["production"] is False
        return {"accepted": True, "message_id": "fixture-message-29e", "production": False}

    def receipt(_payload: dict) -> dict:
        calls.append("receipt")
        return {"persisted": True, "receipt_id": "fixture-receipt-29e"}

    def charge(payload: dict) -> dict:
        calls.append("charge")
        assert payload["amount_xu"] == 0
        assert payload["admin_no_charge"] is True
        return {"ok": True, "wallet_mutated": False, "tx_id": "admin-zero-29e"}

    def report(_payload: dict) -> dict:
        calls.append("report")
        return {"emitted": True, "report_id": "fixture-report-29e"}

    return {
        "deliverer": deliver,
        "receipt_persister": receipt,
        "charger": charge,
        "terminal_reporter": report,
    }


def _dispatch(
    tmp_path: Path,
    *,
    count: int = 2,
    graph=None,
    request=None,
    scene_submitter=None,
    ledger=None,
    environ=None,
    manifest=None,
) -> tuple[dict, poll_recovery.ProductVideoPollRecoveryStore]:
    selected_graph = graph or _graph(count)
    selected_request = request or _request(count, graph=selected_graph)
    store = _store(tmp_path)
    result = multiscene.dispatch_product_video_multiscene(
        selected_request,
        scene_graph=selected_graph,
        manifest=manifest or _manifest(),
        runtime_sha=RUNTIME_SHA,
        environ=_flags() if environ is None else environ,
        store=store,
        ledger=ledger or multiscene.ProductVideoMultisceneLedger(),
        scene_submitter=scene_submitter or _unexpected("scene_submit"),
        now_epoch=NOW,
    )
    return result, store


def _recover(
    store: poll_recovery.ProductVideoPollRecoveryStore,
    job_id: str,
    *,
    status_getter=None,
    artifact_fetcher=None,
    scene_validator=None,
    final_validator=None,
    compositor=None,
    effects=None,
    now_epoch: float = NOW,
    **overrides,
) -> dict:
    calls: list[str] = []
    kwargs = {
        "store": store,
        "job_id": job_id,
        "lease_owner": "worker-29e-a",
        "actual_worker_sha": RUNTIME_SHA,
        "status_getter": status_getter or _unexpected("provider_status_get"),
        "artifact_fetcher": artifact_fetcher or _unexpected("artifact_fetch"),
        "scene_validator": scene_validator or one_scene.validate_product_video_one_scene_artifact,
        "final_validator": final_validator or one_scene.validate_product_video_one_scene_artifact,
        "environ": _flags(),
        "now_epoch": now_epoch,
        **(effects or _effects(calls)),
    }
    if compositor is not None:
        kwargs["compositor"] = compositor
    kwargs.update(overrides)
    return multiscene.recover_product_video_multiscene(**kwargs)


def _render_scene_mp4(path: Path, *, scene_index: int, duration: int = 2) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required for the zero-cost 29E rehearsal")
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=96x160:rate=8:duration={duration}",
        "-vf",
        f"hue=h={scene_index * 35}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert completed.returncode == 0, completed.stderr
    assert path.stat().st_size >= one_scene.MINIMUM_ARTIFACT_BYTES
    return path


def _render_variant_scene_mp4(
    path: Path,
    *,
    size: str,
    rate: int,
    duration: float,
    hue: int,
    rotation: int = 0,
    with_audio: bool = False,
) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required for the zero-cost 29E media fixture")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded_path = path if not rotation else path.with_name(f"{path.stem}.encoded.mp4")
    command = [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={size}:rate={rate}:duration={duration:.3f}",
    ]
    if with_audio:
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:sample_rate=44100:duration={duration:.3f}",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
            ]
        )
    command.extend(
        [
            "-vf",
            f"hue=h={hue}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if with_audio:
        command.extend(["-c:a", "aac", "-ar", "44100", "-ac", "1", "-shortest"])
    else:
        command.append("-an")
    command.extend(["-movflags", "+faststart", str(encoded_path)])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert completed.returncode == 0, completed.stderr
    if rotation:
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-display_rotation",
                str(rotation),
                "-i",
                str(encoded_path),
                "-c",
                "copy",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert completed.returncode == 0, completed.stderr
    assert path.stat().st_size >= one_scene.MINIMUM_ARTIFACT_BYTES
    return path


def _probe_streams(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        pytest.skip("ffprobe is required for the zero-cost 29E media fixture")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration:"
                "stream=index,codec_type,codec_name,width,height,pix_fmt,"
                "sample_aspect_ratio,r_frame_rate,time_base,sample_rate,channels,channel_layout:"
                "stream_side_data=rotation"
            ),
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_29e_normalize_scene_media_locks_geometry_rotation_timebase_and_audio(
    tmp_path: Path,
) -> None:
    source = _render_variant_scene_mp4(
        tmp_path / "rotated-source.mp4",
        size="320x180",
        rate=24,
        duration=1.5,
        hue=45,
        rotation=90,
        with_audio=True,
    )
    normalized = pipeline.normalize_scene_duration(
        str(source),
        str(tmp_path / "normalized.mp4"),
        1.5,
        target_width=360,
        target_height=640,
        target_fps=30,
        preserve_audio=True,
        audio_sample_rate=48000,
        audio_channels=2,
    )
    details = _probe_streams(Path(normalized))
    video = next(item for item in details["streams"] if item["codec_type"] == "video")
    audio = next(item for item in details["streams"] if item["codec_type"] == "audio")
    rotations = [
        int(item.get("rotation") or 0)
        for item in video.get("side_data_list") or []
    ]
    assert (video["width"], video["height"]) == (360, 640)
    assert video["sample_aspect_ratio"] == "1:1"
    assert video["pix_fmt"] == "yuv420p"
    assert video["r_frame_rate"] == "30/1"
    assert video["time_base"] == "1/90000"
    assert not rotations or rotations == [0]
    assert audio["sample_rate"] == "48000"
    assert audio["channels"] == 2


def test_29e_stitch_scenes_renders_requested_video_and_audio_crossfade(
    tmp_path: Path,
) -> None:
    normalized_paths: list[str] = []
    for index, hue in enumerate((20, 180), start=1):
        source = _render_variant_scene_mp4(
            tmp_path / f"source-{index}.mp4",
            size="240x426" if index == 1 else "360x640",
            rate=24 if index == 1 else 25,
            duration=1.5,
            hue=hue,
            with_audio=True,
        )
        normalized_paths.append(
            pipeline.normalize_scene_duration(
                str(source),
                str(tmp_path / f"normalized-{index}.mp4"),
                1.5,
                target_width=360,
                target_height=640,
                target_fps=30,
                preserve_audio=True,
                audio_sample_rate=48000,
                audio_channels=2,
            )
        )
    output = pipeline.stitch_scenes(
        normalized_paths,
        str(tmp_path / "crossfaded.mp4"),
        transition="dissolve",
        transition_duration_sec=0.25,
        include_audio=True,
    )
    details = _probe_streams(Path(output))
    duration = float(details["format"]["duration"])
    stream_types = [item["codec_type"] for item in details["streams"]]
    assert 2.65 <= duration <= 2.90
    assert stream_types.count("video") == 1
    assert stream_types.count("audio") == 1


def test_29e_final_mux_keeps_selected_source_voice_and_music_tracks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master = tmp_path / "master.mp4"
    voice = tmp_path / "voice.m4a"
    music = tmp_path / "music.m4a"
    output = tmp_path / "mixed.mp4"
    for path in (master, voice, music):
        path.write_bytes(b"fixture-media")
    captured: list[str] = []

    def fake_run(command: list[str], *, timeout: int = 180):
        del timeout
        captured.extend(command)
        output.write_bytes(b"fixture-output")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(pipeline, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(pipeline, "safe_run_ffmpeg", fake_run)
    result = pipeline.mux_final_multiscene_video(
        master_video_path=str(master),
        output_path=str(output),
        voice_audio_path=str(voice),
        bgm_audio_path=str(music),
        preserve_master_audio=True,
        audio_sample_rate=48000,
        audio_channels=2,
    )
    command = " ".join(captured)
    assert result == str(output)
    assert "[0:a:0]volume=1.0[amaster]" in command
    assert "[1:a:0]volume=1.0[avoice]" in command
    assert "[2:a:0]volume=0.10[abgm]" in command
    assert "[amaster][avoice][abgm]amix=inputs=3" in command
    assert "apad[aout]" in command
    assert "-ar 48000" in command
    assert "-ac 2" in command


def test_29e_final_mux_pads_a_single_selected_audio_track(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master = tmp_path / "master.mp4"
    voice = tmp_path / "voice.m4a"
    output = tmp_path / "voice-only.mp4"
    for path in (master, voice):
        path.write_bytes(b"fixture-media")
    captured: list[str] = []

    def fake_run(command: list[str], *, timeout: int = 180):
        del timeout
        captured.extend(command)
        output.write_bytes(b"fixture-output")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(pipeline, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(pipeline, "safe_run_ffmpeg", fake_run)
    result = pipeline.mux_final_multiscene_video(
        master_video_path=str(master),
        output_path=str(output),
        voice_audio_path=str(voice),
        audio_sample_rate=48000,
        audio_channels=2,
    )
    command = " ".join(captured)
    assert result == str(output)
    assert "[1:a:0]volume=1.0[avoice]" in command
    assert "[avoice]aresample=48000:async=1:first_pts=0,apad[aout]" in command
    assert "-map [aout] -shortest" in command


def test_29e_finalizer_applies_scene_transition_plan_after_normalization(
    tmp_path: Path,
) -> None:
    sources = {
        1: str(
            _render_variant_scene_mp4(
                tmp_path / "scene-1-rotated.mp4",
                size="320x180",
                rate=24,
                duration=1.5,
                hue=25,
                rotation=90,
            )
        ),
        2: str(
            _render_variant_scene_mp4(
                tmp_path / "scene-2.mp4",
                size="360x640",
                rate=25,
                duration=1.5,
                hue=210,
            )
        ),
    }
    scenes = [
        pipeline.SceneSpec(
            scene_id=1,
            title="Scene 1",
            visual_prompt="Aurora start",
            video_prompt="Aurora start",
            target_duration_sec=1.5,
            aspect_ratio="9:16",
            transition="fade",
        ),
        pipeline.SceneSpec(
            scene_id=2,
            title="Scene 2",
            visual_prompt="Aurora finish",
            video_prompt="Aurora finish",
            target_duration_sec=1.5,
            aspect_ratio="9:16",
        ),
    ]
    result = pipeline.finalize_multiscene_scene_clips(
        user_id="fixture-user",
        job_id="fixture-transition-plan",
        workspace_dir=str(tmp_path / "workspace"),
        scenes=scenes,
        scene_clip_paths=sources,
        output_width=360,
        output_height=640,
        output_fps=30,
        transition_duration_sec=0.25,
    )
    assert result["ok"] is True
    assert result["transition_plan"] == ["fade"]
    assert result["transition_duration_seconds"] == 0.25
    assert result["normalization_profile"] == {
        "width": 360,
        "height": 640,
        "fps": 30,
        "pixel_format": "yuv420p",
        "sample_aspect_ratio": "1:1",
        "video_time_base": "1/90000",
    }
    details = _probe_streams(Path(result["final_video_path"]))
    video = next(item for item in details["streams"] if item["codec_type"] == "video")
    assert (video["width"], video["height"]) == (360, 640)
    assert 2.65 <= float(details["format"]["duration"]) <= 2.90


def test_29e_flags_default_off_and_route_stays_profile_only() -> None:
    assert multiscene.product_video_multiscene_flags({}) == {
        name: False for name in multiscene.MULTISCENE_FLAG_DEFAULTS
    }
    route = video_engine_contract.product_route_contract(
        "product_video",
        mode="multi_scene",
        environ={},
    )
    assert route["state"] == "PROFILE_ONLY"
    assert route["connected"] is False


def test_29e_mode_specific_route_preserves_29c_single_scene_contract() -> None:
    environ = {
        **_flags(),
        "PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED": "1",
        "PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED": "0",
        "PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED": "0",
        "PRODUCT_VIDEO_ONE_SCENE_AUTO_RETRY": "0",
        "PRODUCT_VIDEO_ONE_SCENE_AUTO_FALLBACK": "0",
    }
    single = video_engine_contract.product_route_contract(
        "product_video", mode="single_scene", environ=environ
    )
    multi = video_engine_contract.product_route_contract(
        "product_video", mode="multi_scene", environ=environ
    )
    assert single == one_scene.shared_product_video_one_scene_route()
    assert multi == multiscene.shared_product_video_multiscene_route()
    assert single["engine_route"] != multi["engine_route"]
    assert multi["supported_modes"] == ("multi_scene",)


def test_29e_contract_declares_ordered_scene_truth_and_no_replacement() -> None:
    contract = multiscene.product_video_multiscene_contract({})
    assert contract["scene_count"]["minimum"] == 2
    assert contract["scene_count"]["maximum"] == multiscene.MAX_MULTISCENE_SCENES
    assert contract["scene_required_fields"] == (
        "scene_id",
        "scene_index",
        "scene_specification",
        "duration_seconds",
        "aspect_ratio",
        "transition",
        "input_assets",
        "audio_requirement",
        "voice_requirement",
        "provider",
        "model",
        "idempotency_key",
        "status",
        "artifact_fingerprint",
    )
    assert contract["automatic_resubmit"] is False
    assert contract["automatic_fallback"] is False
    assert contract["final_delivery_count"] == 1
    assert contract["final_compose_count"] == 1


def test_29e_scene_graph_preserves_exact_prompt_order_assets_and_hashes() -> None:
    graph = _graph(3)
    assert [scene.scene_index for scene in graph] == [1, 2, 3]
    assert [scene.scene_id for scene in graph] == ["scene_001", "scene_002", "scene_003"]
    assert graph[1].original_user_prompt == "Prompt goc canh 2, khong duoc thay doi chi tiet."
    assert graph[1].scene_specification == "Canh 2: quay san pham Aurora dung thu tu."
    assert graph[1].input_assets == ("fixture-product-reference-2",)
    assert graph[1].provider == "fake_provider"
    assert graph[1].model == "fixture-model-v1"
    assert graph[1].original_prompt_sha256 == hashlib.sha256(
        graph[1].original_user_prompt.encode("utf-8")
    ).hexdigest()
    assert len({scene.idempotency_key for scene in graph}) == 3


def test_29e_scalar_scene_input_asset_is_one_asset_not_characters() -> None:
    scenes = _scene_inputs(2)
    scenes[0]["input_assets"] = "fixture-scene-asset"
    graph = multiscene.compile_product_video_scene_graph(
        scenes=scenes,
        user_id=172203,
        confirmation_id="confirm-29e",
        language="vi",
    )
    assert graph[0].input_assets == ("fixture-scene-asset",)


@pytest.mark.parametrize(
    ("mutate_graph", "error"),
    (
        (lambda graph: (replace(graph[0], model=""), graph[1]), "scene_model_required"),
        (
            lambda graph: (
                replace(graph[0], original_prompt_sha256="0" * 64),
                graph[1],
            ),
            "original_prompt_hash_mismatch",
        ),
        (
            lambda graph: (
                graph[0],
                replace(graph[1], idempotency_key=graph[0].idempotency_key),
            ),
            "multiscene_scene_idempotency_invalid",
        ),
    ),
)
def test_29e_request_rejects_noncanonical_external_scene_contract(
    mutate_graph,
    error: str,
) -> None:
    graph = mutate_graph(_graph(2))
    with pytest.raises(ValueError, match=error):
        _request(2, graph=graph)


@pytest.mark.parametrize("count", (1, multiscene.MAX_MULTISCENE_SCENES + 1))
def test_29e_rejects_invalid_scene_count(count: int) -> None:
    with pytest.raises(ValueError, match="multiscene_scene_count"):
        _graph(count)


@pytest.mark.parametrize(
    "mutator",
    (
        lambda scenes: scenes.__setitem__(1, {**scenes[1], "scene_index": 1}),
        lambda scenes: scenes.__setitem__(1, {**scenes[1], "scene_id": "scene_001"}),
        lambda scenes: scenes.__setitem__(1, {**scenes[1], "aspect_ratio": "16:9"}),
        lambda scenes: scenes.__setitem__(1, {**scenes[1], "provider": "auto_provider"}),
    ),
)
def test_29e_rejects_duplicate_unordered_or_cross_route_scene(mutator) -> None:
    scenes = _scene_inputs(2)
    mutator(scenes)
    with pytest.raises(ValueError):
        multiscene.compile_product_video_scene_graph(
            scenes=scenes,
            user_id=172203,
            confirmation_id="confirm-29e",
            language="vi",
        )


def test_29e_request_uses_shared_contract_and_exact_scene_graph() -> None:
    graph = _graph(2)
    request = _request(2, graph=graph)
    assert request.product_type.value == "product_video"
    assert request.mode.value == "multi_scene"
    assert request.approved_plan["scene_count"] == 2
    assert request.approved_plan["scene_order"] == [1, 2]
    assert request.approved_plan["scenes"][0]["original_user_prompt"] == graph[0].original_user_prompt
    assert request.payload["scene_graph_sha256"] == multiscene.scene_graph_sha256(graph)
    assert request.payload["admin_no_charge"] is True


def test_29e_transition_is_part_of_scene_contract_payload_and_idempotency(
    tmp_path: Path,
) -> None:
    graph = _graph(2, transitions=("dissolve", "cut"))
    cut_graph = _graph(2, transitions=("cut", "cut"))
    assert graph[0].transition == "dissolve"
    assert graph[1].transition == "cut"
    assert graph[0].idempotency_key != cut_graph[0].idempotency_key

    request = _request(2, graph=graph)
    assert request.approved_plan["transition_plan"] == ["dissolve"]
    assert request.payload["transition_plan"] == ["dissolve"]
    submitted: list[dict] = []

    def submit(payload: dict) -> dict:
        submitted.append(payload)
        return {
            "state": "ACCEPTED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-transition-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "paid": False,
        }

    _dispatch(tmp_path, graph=graph, request=request, scene_submitter=submit)
    assert [item["transition"] for item in submitted] == ["dissolve", "cut"]


def test_29e_default_compositor_passes_approved_profile_transition_and_audio_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _graph(2, transitions=("fade", "cut"))
    request = _request(
        2,
        graph=graph,
        audio_policy={
            "enabled": True,
            "promised": True,
            "source_audio": True,
        },
        final_assets={
            "enable_subtitle": False,
            "voice_audio_path": "",
            "bgm_audio_path": "",
            "logo_path": "",
            "logo_text": "",
            "logo_position": "bottom_right",
            "output_profile": {
                "width": 360,
                "height": 640,
                "fps": 25,
                "audio_sample_rate": 44100,
                "audio_channels": 1,
            },
            "transition_duration_seconds": 0.2,
        },
    )
    captured: dict = {}
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"fixture-final")

    def fake_finalize(**kwargs) -> dict:
        captured.update(kwargs)
        return {
            "ok": True,
            "final_video_path": str(final_path),
            "master_video_path": str(final_path),
            "scene_count": 2,
            "scene_order": [1, 2],
            "target_duration_sec": 3.8,
        }

    monkeypatch.setattr(
        multiscene.pipeline,
        "finalize_multiscene_scene_clips",
        fake_finalize,
    )
    checkpoint = {
        "job_id": "fixture-compositor-29e",
        "request": {
            "user_id": request.user_id,
            "payload": request.payload,
            "audio_policy": request.audio_policy,
            "voice_policy": request.voice_policy,
        },
        "scenes": [multiscene._json_safe(item) for item in graph],
    }
    result = multiscene._default_compositor(
        store=_store(tmp_path),
        checkpoint=checkpoint,
        scene_clip_paths={1: "scene-1.mp4", 2: "scene-2.mp4"},
    )
    assert result["ok"] is True
    assert [item.transition for item in captured["scenes"]] == ["fade", "cut"]
    assert captured["output_width"] == 360
    assert captured["output_height"] == 640
    assert captured["output_fps"] == 25
    assert captured["preserve_scene_audio"] is True
    assert captured["audio_sample_rate"] == 44100
    assert captured["audio_channels"] == 1
    assert captured["transition_duration_sec"] == 0.2


def test_29e_recovery_validates_composed_duration_after_transition_overlap(
    tmp_path: Path,
) -> None:
    graph = _graph(2, transitions=("dissolve", "cut"))

    def submit(payload: dict) -> dict:
        scene_path = tmp_path / f"scene-{payload['scene_index']}.mp4"
        scene_path.write_bytes(f"scene-{payload['scene_index']}".encode() * 1000)
        return {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-duration-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "artifact_path": str(scene_path),
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, graph=graph, scene_submitter=submit)
    final_path = tmp_path / "composed-duration.mp4"
    expected_duration_calls: list[float] = []

    def compositor(**_kwargs) -> dict:
        final_path.write_bytes(b"composed-duration" * 1000)
        return {
            "ok": True,
            "final_video_path": str(final_path),
            "scene_count": 2,
            "scene_order": [1, 2],
            "target_duration_sec": 3.65,
        }

    def final_validator(path: str, **kwargs) -> dict:
        expected_duration_calls.append(float(kwargs["expected_duration_seconds"]))
        return {"ok": True, "bytes": Path(path).stat().st_size}

    result = _recover(
        store,
        dispatched["job_id"],
        scene_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        final_validator=final_validator,
        compositor=compositor,
    )
    assert result["outcome"] == "final_delivered"
    assert expected_duration_calls == [3.65]


def test_29e_default_off_dispatch_has_zero_side_effects(tmp_path: Path) -> None:
    calls: list[str] = []
    result, _store_value = _dispatch(
        tmp_path,
        environ={},
        scene_submitter=lambda _payload: calls.append("provider"),
    )
    assert result["submitted"] is False
    assert result["blocker"] == "product_video_multiscene_disabled"
    assert result["job_count"] == 0
    assert result["scene_submit_intents"] == 0
    assert calls == []


@pytest.mark.parametrize(
    ("manifest_override", "blocker"),
    (
        ({"worker_sha": "wrong-sha"}, "worker_sha_mismatch"),
        ({"supported_modes": ("single_scene",)}, "worker_mode_unsupported"),
        ({"artifact_ready": False}, "worker_artifact_not_ready"),
    ),
)
def test_29e_readiness_fails_before_scene_submit(
    tmp_path: Path,
    manifest_override: dict,
    blocker: str,
) -> None:
    calls: list[str] = []
    result, _store_value = _dispatch(
        tmp_path,
        manifest=_manifest(**manifest_override),
        scene_submitter=lambda _payload: calls.append("provider"),
    )
    assert result["blocker"] == blocker
    assert result["scene_submit_intents"] == 0
    assert calls == []


def test_29e_required_scene_audio_missing_blocks_before_submit(tmp_path: Path) -> None:
    graph = _graph(2, required_audio_scene=2)
    result, _store_value = _dispatch(
        tmp_path,
        graph=graph,
        request=_request(2, graph=graph),
    )
    assert result["blocker"] == "scene_audio_artifact_missing"
    assert result["scene_submit_intents"] == 0


def test_29e_restart_reuses_parent_job_and_never_resubmits_accepted_scenes(
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def submit(payload: dict) -> dict:
        calls.append(payload["scene_index"])
        return {
            "state": "ACCEPTED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "paid": False,
        }

    first, store = _dispatch(tmp_path, count=3, scene_submitter=submit)
    second = multiscene.dispatch_product_video_multiscene(
        _request(3),
        scene_graph=_graph(3),
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        environ=_flags(),
        store=store,
        ledger=multiscene.ProductVideoMultisceneLedger(),
        scene_submitter=_unexpected("replacement_submit"),
        now_epoch=NOW,
    )
    assert first["job_id"] == second["job_id"]
    assert first["submitted_scene_count"] == 3
    assert second["submitted_scene_count"] == 0
    assert second["idempotent_replay"] is True
    assert calls == [1, 2, 3]
    assert second["scene_submit_intents"] == 3
    assert second["production_provider_submits"] == 0


def test_29e_concurrent_dispatch_claim_submits_each_scene_at_most_once(
    tmp_path: Path,
) -> None:
    graph = _graph(2)
    request = _request(2, graph=graph)
    store = _store(tmp_path)
    original_load = store.load
    initial_load_barrier = threading.Barrier(2)
    initial_load_count = 0
    initial_load_lock = threading.Lock()

    def racing_initial_load(job_id: str) -> dict:
        nonlocal initial_load_count
        try:
            return original_load(job_id)
        except poll_recovery.RecoveryCheckpointNotFound:
            with initial_load_lock:
                initial_load_count += 1
                should_wait = initial_load_count <= 2
            if should_wait:
                initial_load_barrier.wait(timeout=10)
            raise

    store.load = racing_initial_load  # type: ignore[method-assign]
    calls: list[int] = []
    calls_lock = threading.Lock()

    def submit(payload: dict) -> dict:
        with calls_lock:
            calls.append(payload["scene_index"])
        return {
            "state": "ACCEPTED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "paid": False,
        }

    def dispatch() -> dict:
        return multiscene.dispatch_product_video_multiscene(
            request,
            scene_graph=graph,
            manifest=_manifest(),
            runtime_sha=RUNTIME_SHA,
            environ=_flags(),
            store=store,
            ledger=multiscene.ProductVideoMultisceneLedger(),
            scene_submitter=submit,
            now_epoch=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result(timeout=20) for future in (executor.submit(dispatch), executor.submit(dispatch))]

    assert sorted(calls) == [1, 2]
    assert sum(result["submitted_scene_count"] for result in results) == 2
    assert sum(result["fixture_provider_submit_calls"] for result in results) >= 2
    assert all(result["production_provider_submits"] == 0 for result in results)


def test_29e_recovery_fence_survives_lease_expiry_without_duplicate_finalization(
    tmp_path: Path,
) -> None:
    def submit(payload: dict) -> dict:
        path = tmp_path / "lease-expiry" / f"scene-{payload['scene_index']}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"scene-{payload['scene_index']}".encode() * 1000)
        return {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "artifact_path": str(path),
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, scene_submitter=submit)
    original_load = store.load
    first_thread_id: list[int | None] = [None]
    first_load_count = 0
    first_load_lock = threading.Lock()
    first_holds_expired_lease = threading.Event()
    release_first = threading.Event()

    def controlled_load(job_id: str) -> dict:
        nonlocal first_load_count
        loaded = original_load(job_id)
        if threading.get_ident() == first_thread_id[0]:
            with first_load_lock:
                first_load_count += 1
                should_pause = first_load_count == 2
            if should_pause:
                first_holds_expired_lease.set()
                assert release_first.wait(timeout=20)
        return loaded

    store.load = controlled_load  # type: ignore[method-assign]
    stage_calls: list[str] = []
    stage_lock = threading.Lock()
    final_path = tmp_path / "lease-expiry" / "final.mp4"

    def record(name: str) -> None:
        with stage_lock:
            stage_calls.append(name)

    def compositor(**_kwargs) -> dict:
        record("compose")
        final_path.write_bytes(b"valid-final" * 1000)
        return {
            "ok": True,
            "final_video_path": str(final_path),
            "scene_count": 2,
            "scene_order": [1, 2],
        }

    effects = {
        "deliverer": lambda _payload: (
            record("delivery")
            or {
                "accepted": True,
                "message_id": "fixture-message-29e",
                "production": False,
            }
        ),
        "receipt_persister": lambda _payload: (
            record("receipt")
            or {"persisted": True, "receipt_id": "fixture-receipt-29e"}
        ),
        "charger": lambda _payload: (
            record("charge") or {"ok": True, "wallet_mutated": False}
        ),
        "terminal_reporter": lambda _payload: (
            record("report") or {"emitted": True, "report_id": "fixture-report-29e"}
        ),
    }
    common = {
        "scene_validator": lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        "final_validator": lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        "compositor": compositor,
        "effects": effects,
        "lease_seconds": 1,
    }

    def first_recovery() -> dict:
        first_thread_id[0] = threading.get_ident()
        return _recover(
            store,
            dispatched["job_id"],
            now_epoch=NOW,
            lease_owner="worker-first",
            **common,
        )

    def second_recovery() -> dict:
        return _recover(
            store,
            dispatched["job_id"],
            now_epoch=NOW + 2,
            lease_owner="worker-second",
            **common,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(first_recovery)
        assert first_holds_expired_lease.wait(timeout=20)
        second_future = executor.submit(second_recovery)
        try:
            second = second_future.result(timeout=20)
        finally:
            release_first.set()
        first = first_future.result(timeout=20)

    assert sorted((first["outcome"], second["outcome"])) == ["blocked", "final_delivered"]
    blocked = first if first["outcome"] == "blocked" else second
    assert blocked["blocker"] == "recovery_fence_active"
    assert stage_calls.count("compose") == 1
    assert stage_calls.count("delivery") == 1
    assert stage_calls.count("receipt") == 1
    assert stage_calls.count("charge") == 1
    assert stage_calls.count("report") == 1


def test_29e_existing_ledger_without_checkpoint_never_resubmits(
    tmp_path: Path,
) -> None:
    ledger = multiscene.ProductVideoMultisceneLedger()
    calls: list[int] = []

    def submit(payload: dict) -> dict:
        calls.append(payload["scene_index"])
        return {
            "state": "ACCEPTED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "paid": False,
        }

    first, _first_store = _dispatch(
        tmp_path / "first-store",
        ledger=ledger,
        scene_submitter=submit,
    )
    empty_store = _store(tmp_path / "empty-store")
    second = multiscene.dispatch_product_video_multiscene(
        _request(2),
        scene_graph=_graph(2),
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        environ=_flags(),
        store=empty_store,
        ledger=ledger,
        scene_submitter=submit,
        now_epoch=NOW,
    )
    assert first["submitted_scene_count"] == 2
    assert second["submitted_scene_count"] == 0
    assert second["idempotent_replay"] is True
    assert second["outcome"] == "waiting_review"
    assert second["blocker"] == "multiscene_checkpoint_missing_for_existing_job"
    assert calls == [1, 2]


def test_29e_acceptance_unknown_never_resubmits_or_polls(tmp_path: Path) -> None:
    calls: list[int] = []

    def ambiguous(payload: dict):
        calls.append(payload["scene_index"])
        raise one_scene.ProviderAcceptanceUnknown("timeout after submit")

    first, store = _dispatch(tmp_path, scene_submitter=ambiguous)
    second = multiscene.dispatch_product_video_multiscene(
        _request(2),
        scene_graph=_graph(2),
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        environ={},
        store=store,
        ledger=multiscene.ProductVideoMultisceneLedger(),
        scene_submitter=_unexpected("replacement_submit"),
        now_epoch=NOW,
    )
    recovered = _recover(
        store,
        first["job_id"],
        status_getter=_unexpected("ambiguous_poll"),
    )
    assert first["blocker"] == "scene_provider_acceptance_unknown"
    assert second["blocker"] == "scene_provider_acceptance_unknown"
    assert second["outcome"] == "waiting_review"
    assert second["ok"] is False
    assert recovered["outcome"] == "waiting_review"
    assert recovered["blocker"] == "scene_provider_acceptance_unknown"
    assert calls == [1]
    assert recovered["provider_status_get_calls"] == 0


def test_29e_default_off_still_recovers_already_accepted_scene_tasks(
    tmp_path: Path,
) -> None:
    dispatched, store = _dispatch(
        tmp_path,
        scene_submitter=lambda payload: {
            "state": "ACCEPTED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "paid": False,
        },
    )
    polled: list[int] = []

    def status(payload: dict) -> dict:
        polled.append(payload["scene_index"])
        return {
            "state": "RUNNING",
            "provider": payload["provider"],
            "provider_task_id": payload["provider_task_id"],
            "scene_index": payload["scene_index"],
        }

    result = _recover(
        store,
        dispatched["job_id"],
        status_getter=status,
        environ={},
    )
    assert result["outcome"] == "waiting_provider"
    assert result["blocker"] == ""
    assert result["provider_status_get_calls"] == 2
    assert result["production_provider_submits"] == 0
    assert polled == [1, 2]


def test_29e_required_scene_voice_is_enforced_during_artifact_validation(
    tmp_path: Path,
) -> None:
    scene_inputs = _scene_inputs(2)
    scene_inputs[0]["voice_requirement"] = {
        "required": True,
        "artifact_path": "fixture-voice.wav",
    }
    graph = multiscene.compile_product_video_scene_graph(
        scenes=scene_inputs,
        user_id=172203,
        confirmation_id="confirm-29e",
        language="vi",
    )
    scene_one = tmp_path / "provider" / "voice-scene.mp4"
    scene_one.parent.mkdir(parents=True)
    scene_one.write_bytes(b"voice-required-scene" * 400)

    dispatched, store = _dispatch(
        tmp_path,
        graph=graph,
        request=_request(2, graph=graph),
        scene_submitter=lambda payload: {
            "state": "COMPLETED" if payload["scene_index"] == 1 else "RUNNING",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "artifact_path": str(scene_one) if payload["scene_index"] == 1 else "",
            "paid": False,
        },
    )
    promised_values: list[bool] = []

    def validate(path: str, **kwargs) -> dict:
        promised_values.append(bool(kwargs["audio_promised"]))
        return {"ok": True, "bytes": Path(path).stat().st_size}

    result = _recover(
        store,
        dispatched["job_id"],
        status_getter=lambda payload: {
            "state": "RUNNING",
            "provider": payload["provider"],
            "provider_task_id": payload["provider_task_id"],
            "scene_index": payload["scene_index"],
        },
        scene_validator=validate,
        final_validator=_unexpected("final_validation"),
        compositor=_unexpected("composition"),
    )
    assert result["outcome"] == "waiting_provider"
    assert promised_values == [True]


def test_29e_completed_scene_is_reused_while_only_running_scene_is_polled(
    tmp_path: Path,
) -> None:
    scene_one = tmp_path / "provider" / "scene-1.mp4"
    scene_one.parent.mkdir(parents=True)
    scene_one.write_bytes(b"validated-scene-one" * 400)

    def submit(payload: dict) -> dict:
        index = payload["scene_index"]
        return {
            "state": "COMPLETED" if index == 1 else "ACCEPTED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{index}",
            "scene_index": index,
            "artifact_path": str(scene_one) if index == 1 else "",
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, scene_submitter=submit)
    polls: list[int] = []

    def status(payload: dict) -> dict:
        polls.append(payload["scene_index"])
        return {
            "state": "RUNNING",
            "provider": "fake_provider",
            "provider_task_id": "fixture-task-29e-2",
            "scene_index": 2,
        }

    result = _recover(
        store,
        dispatched["job_id"],
        status_getter=status,
        scene_validator=lambda *_args, **_kwargs: {"ok": True, "bytes": scene_one.stat().st_size},
        final_validator=_unexpected("final_validation"),
        compositor=_unexpected("composition"),
    )
    assert result["outcome"] == "waiting_provider"
    assert result["completed_scene_count"] == 1
    assert result["completed_scenes_reused"] == 0
    assert polls == [2]
    assert result["compose_count"] == 0
    assert result["delivery_count"] == 0

    second = _recover(
        store,
        dispatched["job_id"],
        status_getter=lambda payload: {
            "state": "RUNNING",
            "provider": "fake_provider",
            "provider_task_id": payload["provider_task_id"],
            "scene_index": payload["scene_index"],
        },
        now_epoch=NOW + multiscene.DEFAULT_SCENE_POLL_INTERVAL_SECONDS + 1,
        scene_validator=_unexpected("revalidate_completed_scene"),
        final_validator=_unexpected("final_validation"),
        compositor=_unexpected("composition"),
    )
    assert second["completed_scenes_reused"] == 1
    assert second["completed_scene_count"] == 1


def test_29e_missing_durable_scene_artifact_is_not_counted_or_composed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "provider" / "scene-1.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"validated-scene-one" * 400)

    def submit(payload: dict) -> dict:
        index = payload["scene_index"]
        return {
            "state": "COMPLETED" if index == 1 else "RUNNING",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{index}",
            "scene_index": index,
            "artifact_path": str(source) if index == 1 else "",
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, scene_submitter=submit)
    first = _recover(
        store,
        dispatched["job_id"],
        status_getter=lambda payload: {
            "state": "RUNNING",
            "provider": payload["provider"],
            "provider_task_id": payload["provider_task_id"],
            "scene_index": payload["scene_index"],
        },
        scene_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        final_validator=_unexpected("final_validation"),
        compositor=_unexpected("composition"),
    )
    assert first["completed_scene_count"] == 1
    checkpoint = store.load(dispatched["job_id"])
    durable_path = Path(checkpoint["scenes"][0]["artifact_path"])
    assert durable_path.is_file()
    durable_path.unlink()

    second = _recover(
        store,
        dispatched["job_id"],
        status_getter=_unexpected("poll_before_due"),
        artifact_fetcher=_unexpected("fetch_without_durable_source"),
        scene_validator=_unexpected("validate_missing_durable_scene"),
        final_validator=_unexpected("final_validation"),
        compositor=_unexpected("composition"),
    )
    assert second["ok"] is False
    assert second["outcome"] == "waiting_review"
    assert second["blocker"] == "scene_durable_artifact_missing"
    assert second["completed_scene_count"] == 0
    assert second["completed_scenes_reused"] == 0
    assert second["compose_count"] == 0
    assert second["delivery_count"] == 0


def test_29e_tampered_durable_scene_is_rematerialized_from_same_task(
    tmp_path: Path,
) -> None:
    original_bytes = b"original-scene-one" * 400
    source = tmp_path / "provider" / "scene-1.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(original_bytes)

    def submit(payload: dict) -> dict:
        index = payload["scene_index"]
        return {
            "state": "COMPLETED" if index == 1 else "RUNNING",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{index}",
            "scene_index": index,
            "artifact_path": str(source) if index == 1 else "",
            "artifact_url": "fixture://same-task/scene-1" if index == 1 else "",
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, scene_submitter=submit)
    first = _recover(
        store,
        dispatched["job_id"],
        status_getter=lambda payload: {
            "state": "RUNNING",
            "provider": payload["provider"],
            "provider_task_id": payload["provider_task_id"],
            "scene_index": payload["scene_index"],
        },
        scene_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        final_validator=_unexpected("final_validation"),
        compositor=_unexpected("composition"),
    )
    assert first["completed_scene_count"] == 1
    checkpoint = store.load(dispatched["job_id"])
    durable_path = Path(checkpoint["scenes"][0]["artifact_path"])
    durable_path.write_bytes(b"tampered-scene" * 400)
    fetched_task_ids: list[str] = []

    def fetch(payload: dict) -> dict:
        fetched_task_ids.append(payload["provider_task_id"])
        destination = Path(payload["destination_path"])
        destination.write_bytes(original_bytes)
        return {"ok": True, "artifact_path": str(destination)}

    second = _recover(
        store,
        dispatched["job_id"],
        status_getter=_unexpected("poll_before_due"),
        artifact_fetcher=fetch,
        scene_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        final_validator=_unexpected("final_validation"),
        compositor=_unexpected("composition"),
    )
    assert second["outcome"] == "waiting_provider"
    assert second["blocker"] == ""
    assert second["completed_scene_count"] == 1
    assert second["artifact_fetch_calls"] == 1
    assert second["production_provider_submits"] == 0
    assert fetched_task_ids == ["fixture-task-29e-1"]
    assert durable_path.read_bytes() == original_bytes


def test_29e_status_response_cannot_replace_scene_task(tmp_path: Path) -> None:
    dispatched, store = _dispatch(
        tmp_path,
        scene_submitter=lambda payload: {
            "state": "ACCEPTED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "paid": False,
        },
    )
    result = _recover(
        store,
        dispatched["job_id"],
        status_getter=lambda payload: {
            "state": "RUNNING",
            "provider": payload["provider"],
            "provider_task_id": f"replacement-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
        },
    )
    assert result["blocker"] == "scene_provider_task_identity_mismatch"
    assert result["outcome"] == "waiting_review"
    assert result["production_provider_submits"] == 0


def test_29e_required_scene_failure_never_composes_delivers_or_charges(tmp_path: Path) -> None:
    dispatched, store = _dispatch(
        tmp_path,
        scene_submitter=lambda payload: {
            "state": "FAILED" if payload["scene_index"] == 2 else "ACCEPTED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "paid": False,
        },
    )
    result = _recover(
        store,
        dispatched["job_id"],
        status_getter=_unexpected("poll_after_required_failure"),
        compositor=_unexpected("composition"),
    )
    assert result["ok"] is False
    assert result["outcome"] == "failed_no_charge"
    assert result["blocker"] == "required_scene_failed"
    assert result["compose_count"] == 0
    assert result["delivery_count"] == 0
    assert result["charge_count"] == 0
    assert result["wallet_mutations"] == 0

    replay = multiscene.dispatch_product_video_multiscene(
        _request(2),
        scene_graph=_graph(2),
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        environ=_flags(),
        store=store,
        ledger=multiscene.ProductVideoMultisceneLedger(),
        scene_submitter=_unexpected("replacement_submit_after_terminal_failure"),
        now_epoch=NOW,
    )
    assert replay["ok"] is False
    assert replay["outcome"] == "failed_no_charge"
    assert replay["blocker"] == "required_scene_failed"
    assert replay["idempotent_replay"] is True


def test_29e_invalid_final_mp4_never_delivers_or_charges(tmp_path: Path) -> None:
    artifacts = {}

    def submit(payload: dict) -> dict:
        index = payload["scene_index"]
        path = tmp_path / "provider" / f"scene-{index}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"scene-{index}".encode() * 1000)
        artifacts[index] = path
        return {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{index}",
            "scene_index": index,
            "artifact_path": str(path),
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, scene_submitter=submit)
    invalid_final = tmp_path / "invalid-final.mp4"
    invalid_final.write_bytes(b"not a final mp4")
    result = _recover(
        store,
        dispatched["job_id"],
        scene_validator=lambda path, **_kwargs: {"ok": True, "bytes": Path(path).stat().st_size},
        compositor=lambda **_kwargs: {
            "ok": True,
            "final_video_path": str(invalid_final),
            "scene_count": 2,
            "scene_order": [1, 2],
        },
        final_validator=lambda *_args, **_kwargs: {"ok": False, "reason": "final_output_invalid"},
    )
    assert result["blocker"] == "final_output_invalid"
    assert result["terminal_state"] == "failed_no_charge"
    assert result["compose_count"] == 1
    assert result["delivery_count"] == 0
    assert result["charge_count"] == 0

    replay = _recover(
        store,
        dispatched["job_id"],
        status_getter=_unexpected("terminal_failure_poll"),
        scene_validator=_unexpected("terminal_failure_scene_validation"),
        final_validator=_unexpected("terminal_failure_final_validation"),
        compositor=_unexpected("terminal_failure_composition"),
        effects={
            "deliverer": _unexpected("terminal_failure_delivery"),
            "receipt_persister": _unexpected("terminal_failure_receipt"),
            "charger": _unexpected("terminal_failure_charge"),
            "terminal_reporter": _unexpected("terminal_failure_report"),
        },
    )
    assert replay["terminal_state"] == "failed_no_charge"
    assert replay["blocker"] == "final_output_invalid"
    assert replay["idempotent_replay"] is True


def test_29e_missing_completed_final_artifact_blocks_before_delivery(
    tmp_path: Path,
) -> None:
    dispatched, store = _dispatch(
        tmp_path,
        scene_submitter=lambda payload: {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "artifact_path": "",
            "paid": False,
        },
    )
    checkpoint = store.load(dispatched["job_id"])
    for scene in checkpoint["scenes"]:
        path = tmp_path / "durable-scenes" / f"scene-{scene['scene_index']}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"scene-{scene['scene_index']}".encode() * 1000)
        scene["artifact_path"] = str(path)
        scene["artifact_fingerprint"] = hashlib.sha256(path.read_bytes()).hexdigest()
        scene["validation"] = {"ok": True, "bytes": path.stat().st_size}

    final_path = tmp_path / "completed-final.mp4"
    final_path.write_bytes(b"valid-final-before-loss" * 1000)
    checkpoint["final_artifact_path"] = str(final_path)
    checkpoint["final_artifact_fingerprint"] = hashlib.sha256(
        final_path.read_bytes()
    ).hexdigest()
    checkpoint["final_validation"] = {"ok": True, "bytes": final_path.stat().st_size}
    checkpoint["compose"] = {"state": "COMPLETED", "completed": True}
    store.save(checkpoint)
    final_path.unlink()

    result = _recover(
        store,
        dispatched["job_id"],
        status_getter=_unexpected("poll_completed_scenes"),
        artifact_fetcher=_unexpected("fetch_completed_scenes"),
        scene_validator=_unexpected("revalidate_completed_scenes"),
        final_validator=_unexpected("revalidate_missing_final"),
        compositor=_unexpected("recompose_completed_final"),
        effects={
            "deliverer": _unexpected("delivery_with_missing_final"),
            "receipt_persister": _unexpected("receipt_with_missing_final"),
            "charger": _unexpected("charge_with_missing_final"),
            "terminal_reporter": _unexpected("report_with_missing_final"),
        },
    )
    assert result["ok"] is False
    assert result["outcome"] == "waiting_review"
    assert result["blocker"] == "final_artifact_missing"
    assert result["delivery_count"] == 0
    assert result["receipt_count"] == 0
    assert result["charge_count"] == 0
    assert result["terminal_report_count"] == 0


@pytest.mark.parametrize(
    ("composition_metadata", "blocker"),
    (
        ({"scene_count": 1, "scene_order": [1, 2]}, "final_scene_count_mismatch"),
        ({"scene_count": 2, "scene_order": [2, 1]}, "final_scene_order_mismatch"),
    ),
)
def test_29e_composition_must_report_exact_scene_coverage_and_order(
    tmp_path: Path,
    composition_metadata: dict,
    blocker: str,
) -> None:
    def submit(payload: dict) -> dict:
        path = tmp_path / "provider" / f"scene-{payload['scene_index']}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"scene-{payload['scene_index']}".encode() * 1000)
        return {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "artifact_path": str(path),
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, scene_submitter=submit)
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"valid-final" * 1000)
    result = _recover(
        store,
        dispatched["job_id"],
        scene_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        final_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        compositor=lambda **_kwargs: {
            "ok": True,
            "final_video_path": str(final_path),
            **composition_metadata,
        },
        effects={
            "deliverer": _unexpected("delivery_after_bad_scene_manifest"),
            "receipt_persister": _unexpected("receipt_after_bad_scene_manifest"),
            "charger": _unexpected("charge_after_bad_scene_manifest"),
            "terminal_reporter": _unexpected("report_after_bad_scene_manifest"),
        },
    )
    assert result["ok"] is False
    assert result["outcome"] == "failed_no_charge"
    assert result["blocker"] == blocker
    assert result["delivery_count"] == 0
    assert result["charge_count"] == 0


@pytest.mark.parametrize(
    ("invalid_stage", "blocker"),
    (
        ("delivery", "delivery_not_accepted"),
        ("receipt", "delivery_receipt_not_persisted"),
        ("report", "terminal_report_not_emitted"),
    ),
)
def test_29e_finalization_requires_auditable_stage_identities(
    tmp_path: Path,
    invalid_stage: str,
    blocker: str,
) -> None:
    def submit(payload: dict) -> dict:
        path = tmp_path / invalid_stage / f"scene-{payload['scene_index']}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"scene-{payload['scene_index']}".encode() * 1000)
        return {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "artifact_path": str(path),
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, scene_submitter=submit)
    final_path = tmp_path / invalid_stage / "final.mp4"
    final_path.write_bytes(b"valid-final" * 1000)
    calls: list[str] = []

    def deliver(_payload: dict) -> dict:
        calls.append("delivery")
        result = {"accepted": True, "production": False}
        if invalid_stage != "delivery":
            result["message_id"] = "fixture-message-29e"
        return result

    def receipt(_payload: dict) -> dict:
        calls.append("receipt")
        result = {"persisted": True}
        if invalid_stage != "receipt":
            result["receipt_id"] = "fixture-receipt-29e"
        return result

    def charge(_payload: dict) -> dict:
        calls.append("charge")
        return {"ok": True, "wallet_mutated": False}

    def report(_payload: dict) -> dict:
        calls.append("report")
        result = {"emitted": True}
        if invalid_stage != "report":
            result["report_id"] = "fixture-report-29e"
        return result

    result = _recover(
        store,
        dispatched["job_id"],
        scene_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        final_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        compositor=lambda **_kwargs: {
            "ok": True,
            "final_video_path": str(final_path),
            "scene_count": 2,
            "scene_order": [1, 2],
        },
        effects={
            "deliverer": deliver,
            "receipt_persister": receipt,
            "charger": charge,
            "terminal_reporter": report,
        },
    )
    assert result["ok"] is False
    assert result["outcome"] == "waiting_review"
    assert result["blocker"] == blocker
    expected_calls = {
        "delivery": ["delivery"],
        "receipt": ["delivery", "receipt"],
        "report": ["delivery", "receipt", "charge", "report"],
    }
    assert calls == expected_calls[invalid_stage]
    assert result["production_telegram_deliveries"] == 0
    assert result["wallet_mutations"] == 0


def test_29e_stage_responses_cannot_overwrite_authoritative_evidence(
    tmp_path: Path,
) -> None:
    def submit(payload: dict) -> dict:
        path = tmp_path / "authoritative" / f"scene-{payload['scene_index']}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"scene-{payload['scene_index']}".encode() * 1000)
        return {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "artifact_path": str(path),
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, scene_submitter=submit)
    final_path = tmp_path / "authoritative" / "final.mp4"
    final_path.write_bytes(b"valid-final" * 1000)
    result = _recover(
        store,
        dispatched["job_id"],
        scene_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        final_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        compositor=lambda **_kwargs: {
            "ok": True,
            "final_video_path": str(final_path),
            "scene_count": 2,
            "scene_order": [1, 2],
        },
        effects={
            "deliverer": lambda _payload: {
                "accepted": True,
                "message_id": "fixture-message-29e",
                "production": False,
                "idempotency_key": "forged-delivery-key",
                "output_sha256": "0" * 64,
                "output_bytes": 1,
            },
            "receipt_persister": lambda _payload: {
                "persisted": True,
                "receipt_id": "fixture-receipt-29e",
                "job_id": "forged-job",
                "delivery_idempotency_key": "forged-delivery-key",
                "delivery_message_id": "forged-message",
                "output_sha256": "0" * 64,
                "output_bytes": 1,
                "delivered_at": "forged-time",
            },
            "charger": lambda _payload: {
                "ok": True,
                "wallet_mutated": False,
                "amount_xu": 999,
                "idempotency_key": "forged-charge-key",
            },
            "terminal_reporter": lambda _payload: {
                "emitted": True,
                "report_id": "fixture-report-29e",
                "idempotency_key": "forged-report-key",
            },
        },
    )
    assert result["outcome"] == "final_delivered"
    checkpoint = store.load(dispatched["job_id"])
    final_sha = hashlib.sha256(final_path.read_bytes()).hexdigest()
    delivery_key = f"delivery:{dispatched['job_id']}:{final_sha}"
    assert checkpoint["delivery"]["idempotency_key"] == delivery_key
    assert checkpoint["delivery"]["output_sha256"] == final_sha
    assert checkpoint["delivery"]["output_bytes"] == final_path.stat().st_size
    assert checkpoint["receipt"]["job_id"] == dispatched["job_id"]
    assert checkpoint["receipt"]["delivery_idempotency_key"] == delivery_key
    assert checkpoint["receipt"]["delivery_message_id"] == "fixture-message-29e"
    assert checkpoint["receipt"]["output_sha256"] == final_sha
    assert checkpoint["receipt"]["output_bytes"] == final_path.stat().st_size
    assert checkpoint["receipt"]["delivered_at"] != "forged-time"
    assert checkpoint["charge"]["amount_xu"] == 0
    assert checkpoint["charge"]["idempotency_key"] == (
        f"charge:{dispatched['job_id']}:0"
    )
    assert checkpoint["terminal_report"]["idempotency_key"] == (
        f"terminal-report:{dispatched['job_id']}"
    )


def test_29e_non_admin_without_positive_charge_plan_blocks_before_charger(
    tmp_path: Path,
) -> None:
    def submit(payload: dict) -> dict:
        path = tmp_path / "charge-plan" / f"scene-{payload['scene_index']}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"scene-{payload['scene_index']}".encode() * 1000)
        return {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{payload['scene_index']}",
            "scene_index": payload["scene_index"],
            "artifact_path": str(path),
            "paid": False,
        }

    graph = _graph(2)
    dispatched, store = _dispatch(
        tmp_path,
        graph=graph,
        request=_request(2, graph=graph, admin_no_charge=False),
        scene_submitter=submit,
    )
    final_path = tmp_path / "charge-plan" / "final.mp4"
    final_path.write_bytes(b"valid-final" * 1000)
    calls: list[str] = []
    result = _recover(
        store,
        dispatched["job_id"],
        scene_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        final_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        compositor=lambda **_kwargs: {
            "ok": True,
            "final_video_path": str(final_path),
            "scene_count": 2,
            "scene_order": [1, 2],
        },
        effects={
            "deliverer": lambda _payload: {
                "accepted": True,
                "message_id": "fixture-message-29e",
                "production": False,
            },
            "receipt_persister": lambda _payload: {
                "persisted": True,
                "receipt_id": "fixture-receipt-29e",
            },
            "charger": _unexpected("zero_xu_non_admin_charge"),
            "terminal_reporter": lambda _payload: calls.append("report"),
        },
    )
    assert result["ok"] is False
    assert result["outcome"] == "waiting_review"
    assert result["blocker"] == "charge_plan_missing"
    assert result["charge_count"] == 0
    assert result["wallet_mutations"] == 0
    assert calls == []


@pytest.mark.parametrize(
    "unknown_stage",
    ("delivery", "receipt", "charge", "report"),
)
def test_29e_terminal_acceptance_unknown_never_replays_external_stage(
    tmp_path: Path,
    unknown_stage: str,
) -> None:
    artifacts: dict[int, Path] = {}

    def submit(payload: dict) -> dict:
        index = payload["scene_index"]
        artifact = tmp_path / unknown_stage / f"scene-{index}.mp4"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(f"scene-{index}".encode() * 1000)
        artifacts[index] = artifact
        return {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{unknown_stage}-{index}",
            "scene_index": index,
            "artifact_path": str(artifact),
            "paid": False,
        }

    dispatched, store = _dispatch(tmp_path, scene_submitter=submit)
    final_path = tmp_path / unknown_stage / "final.mp4"
    final_path.write_bytes(b"valid-final-fixture" * 1000)
    calls: list[str] = []

    def stage(name: str, success: dict):
        def execute(_payload: dict) -> dict:
            calls.append(name)
            if name == unknown_stage:
                raise TimeoutError(f"{name} acceptance unknown")
            return success

        return execute

    first = _recover(
        store,
        dispatched["job_id"],
        scene_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        final_validator=lambda path, **_kwargs: {
            "ok": True,
            "bytes": Path(path).stat().st_size,
        },
        compositor=lambda **_kwargs: {
            "ok": True,
            "final_video_path": str(final_path),
            "scene_count": 2,
            "scene_order": [1, 2],
        },
        effects={
            "deliverer": stage(
                "delivery",
                {"accepted": True, "message_id": "fixture-message", "production": False},
            ),
            "receipt_persister": stage(
                "receipt",
                {"persisted": True, "receipt_id": "fixture-receipt"},
            ),
            "charger": stage(
                "charge",
                {"ok": True, "wallet_mutated": False, "tx_id": "fixture-charge"},
            ),
            "terminal_reporter": stage(
                "report",
                {"emitted": True, "report_id": "fixture-report"},
            ),
        },
    )
    expected_blocker = f"{unknown_stage}_acceptance_unknown"
    assert first["outcome"] == "waiting_review"
    assert first["blocker"] == expected_blocker

    replay = _recover(
        store,
        dispatched["job_id"],
        status_getter=_unexpected("unknown_stage_poll"),
        scene_validator=_unexpected("unknown_stage_scene_validation"),
        final_validator=_unexpected("unknown_stage_final_validation"),
        compositor=_unexpected("unknown_stage_composition"),
        effects={
            "deliverer": _unexpected("duplicate_delivery"),
            "receipt_persister": _unexpected("duplicate_receipt"),
            "charger": _unexpected("duplicate_charge"),
            "terminal_reporter": _unexpected("duplicate_report"),
        },
    )
    assert replay["outcome"] == "waiting_review"
    assert replay["blocker"] == expected_blocker
    assert replay["idempotent_replay"] is True


@pytest.mark.parametrize(
    ("scene_count", "transition"),
    ((2, "cut"), (2, "dissolve"), (3, "cut"), (3, "dissolve")),
)
def test_29e_zero_cost_rehearsal_composes_valid_mp4_and_finalizes_once(
    tmp_path: Path,
    scene_count: int,
    transition: str,
) -> None:
    provider_calls: list[int] = []

    def submit(payload: dict) -> dict:
        index = payload["scene_index"]
        provider_calls.append(index)
        artifact = _render_scene_mp4(
            tmp_path / "provider" / f"scene-{index}.mp4",
            scene_index=index,
        )
        return {
            "state": "COMPLETED",
            "provider": "fake_provider",
            "provider_task_id": f"fixture-task-29e-{scene_count}-{index}",
            "scene_index": index,
            "artifact_path": str(artifact),
            "paid": False,
        }

    transitions = tuple([transition] * (scene_count - 1) + ["cut"])
    graph = _graph(scene_count, transitions=transitions)
    request = _request(scene_count, graph=graph)
    dispatched, store = _dispatch(
        tmp_path,
        count=scene_count,
        graph=graph,
        request=request,
        scene_submitter=submit,
    )
    side_effects: list[str] = []
    first = _recover(
        store,
        dispatched["job_id"],
        effects=_effects(side_effects),
    )
    second = _recover(
        store,
        dispatched["job_id"],
        status_getter=_unexpected("terminal_poll"),
        scene_validator=_unexpected("terminal_scene_validation"),
        final_validator=_unexpected("terminal_final_validation"),
        compositor=_unexpected("terminal_composition"),
        effects={
            "deliverer": _unexpected("duplicate_delivery"),
            "receipt_persister": _unexpected("duplicate_receipt"),
            "charger": _unexpected("duplicate_charge"),
            "terminal_reporter": _unexpected("duplicate_report"),
        },
    )
    assert first["ok"] is True
    assert second["ok"] is True
    assert second["idempotent_replay"] is True
    assert provider_calls == list(range(1, scene_count + 1))
    assert first["scene_count"] == scene_count
    assert first["scene_order"] == list(range(1, scene_count + 1))
    assert first["completed_scene_count"] == scene_count
    assert first["compose_count"] == 1
    assert first["delivery_count"] == 1
    assert first["receipt_count"] == 1
    assert first["charge_count"] == 1
    assert first["terminal_report_count"] == 1
    assert side_effects == ["delivery", "receipt", "charge", "report"]
    assert first["fixture_provider_submit_calls"] == scene_count
    assert first["production_provider_submits"] == 0
    assert first["real_provider_calls"] == 0
    assert first["paid_provider_calls"] == 0
    assert first["wallet_mutations"] == 0
    assert first["production_telegram_deliveries"] == 0
    final_path = Path(first["final_artifact_path"])
    assert final_path.is_file()
    assert first["final_validation"]["ok"] is True
    expected_duration = float(request.duration_profile["target_duration_seconds"])
    assert abs(pipeline.probe_duration(str(final_path)) - expected_duration) <= 0.5

    dispatch_replay = multiscene.dispatch_product_video_multiscene(
        request,
        scene_graph=graph,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        environ={},
        store=store,
        ledger=multiscene.ProductVideoMultisceneLedger(),
        scene_submitter=_unexpected("replacement_submit_after_final_delivery"),
        now_epoch=NOW,
    )
    assert dispatch_replay["ok"] is True
    assert dispatch_replay["outcome"] == "final_delivered"
    assert dispatch_replay["blocker"] == ""
    assert dispatch_replay["idempotent_replay"] is True


def test_29e_scope_is_transport_free_and_reuses_29d_store() -> None:
    source = inspect.getsource(multiscene)
    lowered = source.casefold()
    assert "product_video_poll_recovery" in source
    assert "ProductVideoPollRecoveryStore" in source
    assert "requests." not in lowered
    assert "httpx" not in lowered
    assert "telegram.ext" not in lowered
    assert "send_video(" not in lowered
    assert "bot.py" not in lowered
    assert "remote_worker.py" not in lowered
    assert "deduct_xu" not in lowered
    assert "wallet." not in lowered
    assert "fallback_provider" not in lowered
    assert '"automatic_fallback": False' in source
