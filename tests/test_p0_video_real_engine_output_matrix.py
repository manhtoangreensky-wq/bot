from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import pytest

import remote_worker
from services import video_final_output
from services import multiscene_video_pipeline
from services import video_real_render_connector
from services import video_project_queue
from services import remote_worker_api
from services import video_tail9
from providers import video_generic_http_provider
from services.video_provider_base import VideoGenerationRequest


ROOT = Path(__file__).resolve().parents[1]
QUEUE_SOURCE = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")
WORKER_SOURCE = (ROOT / "local_worker.py").read_text(encoding="utf-8")
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


PUBLIC_ENGINE_PRODUCTS = (
    "video_local_edit",
    "frame_video_local",
    "video_trend",
    "video_ai_real",
    "script_image_video",
    "storyboard_prompt",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
)


def _source_section(source: str, start: str, end: str) -> str:
    left = source.index(start)
    right = source.index(end, left)
    return source[left:right]


def test_each_public_product_has_a_distinct_engine_capability_contract() -> None:
    expected = {
        "video_local_edit": ("video_local_edit", "local_worker_ffmpeg", "video_to_video"),
        "frame_video_local": ("image_to_video", "frame_video_render", "local_ffmpeg"),
        "video_trend": ("video_trend", "trend_video", "text_to_video_or_scene_video"),
        "video_ai_real": ("video_ai_prompt", "video_ai_canonical", "text_to_video"),
        "script_image_video": ("script_to_video", "script_to_video", "text_to_video_or_scene_video"),
        "storyboard_prompt": ("storyboard_prompt", "storyboard_to_video", "image_to_video"),
        "self_shot_scene_change": ("self_shot_scene_change", "self_shot_scene_change", "video_to_video"),
        "self_shot_cinematic_transform": (
            "self_shot_cinematic_transform",
            "self_shot_cinematic_transform",
            "video_to_video",
        ),
    }
    for product, (executor, route, capability) in expected.items():
        contract = video_project_queue.product_video_engine_contract(product)
        assert contract["executor_product_type"] == executor
        assert contract["engine_route"] == route
        assert contract["required_capability"] == capability


def test_storyboard_route_requires_image_to_video_capability() -> None:
    route = video_final_output.route_for_product_type("storyboard_prompt")
    assert route["provider_capability"] == "image_to_video"
    assert route["engine_adapter"] == "storyboard_scene_image_video_engine"


def test_connector_resolves_capability_from_the_product_engine_contract() -> None:
    expected = {
        "video_trend": "text_to_video_or_scene_video",
        "video_ai_prompt": "text_to_video",
        "script_to_video": "text_to_video_or_scene_video",
        "storyboard_prompt": "image_to_video",
        "self_shot_scene_change": "video_to_video",
        "self_shot_cinematic_transform": "video_to_video",
    }
    for product_type, capability in expected.items():
        assert video_real_render_connector.product_video_required_capability(
            {"product_type": product_type}
        ) == capability


def test_storyboard_provider_payload_keeps_ordered_image_inputs() -> None:
    request = VideoGenerationRequest(
        job_id="storyboard-fixture",
        product_type="storyboard_prompt",
        video_flow_type="storyboard_prompt",
        prompt="Animate the approved storyboard frame.",
        storyboard=[{"scene_index": 1, "start_image_file_id": "telegram-image-1"}],
        image_paths=["C:/fixture/scene-1.png"],
        ratio="9:16",
        duration_seconds=8,
        required_capability="image_to_video",
        metadata={
            "product_video": True,
            "orchestration_mode": "per_scene_8s",
            "provider_orchestration_mode": "per_scene_8s",
        },
    )
    payload = video_generic_http_provider.build_shopaikey_video_payload(
        request,
        {"SHOPAIKEY_VIDEO_MODEL": ""},
    )
    assert payload["storyboard"] == request.storyboard
    assert payload["image_paths"] == request.image_paths


def test_storyboard_key4u_contract_keeps_image_inputs_after_model_resolution() -> None:
    request = VideoGenerationRequest(
        job_id="storyboard-key4u-fixture",
        product_type="storyboard_prompt",
        video_flow_type="storyboard_prompt",
        prompt="Animate the approved storyboard frame.",
        scenes=[{"scene_index": 1, "prompt": "single scene"}],
        storyboard=[{"scene_index": 1, "start_image_file_id": "telegram-image-1"}],
        image_paths=["C:/fixture/scene-1.png"],
        source_video_path="C:/fixture/irrelevant-source.mp4",
        ratio="9:16",
        duration_seconds=8,
        required_capability="image_to_video",
        metadata={
            "product_video": True,
            "scene_index": 1,
            "orchestration_mode": "per_scene_8s",
            "provider_model_map": {"key4u_video": "kling-3.0-turbo"},
        },
    )
    payload = video_generic_http_provider.build_key4u_video_payload(
        request,
        {
            "KEY4U_KLING_VIDEO_ENDPOINT": "https://provider.invalid/kling/image-to-video",
        },
    )
    assert payload["storyboard"] == request.storyboard
    assert payload["image_paths"] == request.image_paths
    assert "scenes" not in payload
    assert "source_video_path" not in payload


def test_selfshot_key4u_contract_keeps_source_video_after_model_resolution() -> None:
    request = VideoGenerationRequest(
        job_id="selfshot-key4u-fixture",
        product_type="self_shot_scene_change",
        video_flow_type="self_shot_scene_change",
        prompt="Transform the supplied source video while preserving the subject.",
        storyboard=[{"scene_index": 1}],
        image_paths=["C:/fixture/irrelevant-image.png"],
        source_video_path="C:/fixture/source.mp4",
        ratio="9:16",
        duration_seconds=8,
        required_capability="video_to_video",
        metadata={
            "product_video": True,
            "scene_index": 1,
            "provider_model_map": {"key4u_video": "kling-motion-control"},
        },
    )
    payload = video_generic_http_provider.build_key4u_video_payload(
        request,
        {
            "KEY4U_KLING_VIDEO_ENDPOINT": "https://provider.invalid/kling/video-to-video",
        },
    )
    assert payload["source_video_path"] == request.source_video_path
    assert "storyboard" not in payload
    assert "image_paths" not in payload


def test_storyboard_scene_request_uses_only_that_scenes_images(tmp_path) -> None:
    first = tmp_path / "scene-1.png"
    second = tmp_path / "scene-2.png"
    first.write_bytes(b"scene-one")
    second.write_bytes(b"scene-two")
    job = {
        "product_type": "storyboard_prompt",
        "scene_cards": [
            {"scene_index": 1, "start_image_path": str(first)},
            {"scene_index": 2, "start_image_path": str(second)},
        ],
    }
    assert video_real_render_connector.storyboard_scene_image_paths(job, 1) == [str(first)]
    assert video_real_render_connector.storyboard_scene_image_paths(job, 2) == [str(second)]


@pytest.mark.parametrize("product_type", ["storyboard_prompt", "video_ai_image", "image_to_video"])
def test_scene_image_products_use_only_the_current_scenes_materialized_image(
    tmp_path,
    product_type,
) -> None:
    first = tmp_path / f"{product_type}-scene-1.png"
    second = tmp_path / f"{product_type}-scene-2.png"
    first.write_bytes(b"scene-one")
    second.write_bytes(b"scene-two")
    job = {
        "product_type": product_type,
        "scene_cards": [
            {"scene_index": 1, "start_image_path": str(first)},
            {"scene_index": 2, "start_image_path": str(second)},
        ],
        "image_paths": [str(first), str(second)],
    }

    assert video_real_render_connector.product_video_scene_image_paths(job, 1) == [str(first)]
    assert video_real_render_connector.product_video_scene_image_paths(job, 2) == [str(second)]


@pytest.mark.parametrize("product_type", ["storyboard_prompt", "video_ai_image", "image_to_video"])
def test_remote_worker_materializes_one_required_image_per_scene(
    tmp_path,
    monkeypatch,
    product_type,
) -> None:
    class _Response:
        def __init__(self, payload: bytes):
            self.payload = payload
            self.offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size: int) -> bytes:
            chunk = self.payload[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    observed: list[str] = []

    def fake_urlopen(request, timeout):
        observed.append(request.full_url)
        scene_index = request.full_url.rstrip("/").split("/")[-2]
        return _Response(f"image-{scene_index}".encode())

    monkeypatch.setattr(remote_worker, "endpoint", lambda path: f"https://worker.invalid{path}")
    monkeypatch.setattr(remote_worker.urllib.request, "urlopen", fake_urlopen)
    job = {
        "job_id": "storyboard-job",
        "product_type": product_type,
        "scene_cards": [
            {"scene_index": 1, "start_image_file_id": "image-1"},
            {"scene_index": 2, "start_image_file_id": "image-2"},
        ],
    }
    paths = remote_worker.download_storyboard_scene_images(job, str(tmp_path))
    assert [Path(path).read_bytes() for path in paths] == [b"image-1", b"image-2"]
    assert job["storyboard_image_paths"] == paths
    assert [card["start_image_path"] for card in job["scene_cards"]] == paths
    assert observed == [
        "https://worker.invalid/api/v1/worker/jobs/storyboard-job/storyboard-image/1/start",
        "https://worker.invalid/api/v1/worker/jobs/storyboard-job/storyboard-image/2/start",
    ]


def test_bot_exposes_authenticated_storyboard_image_transfer() -> None:
    route = '@fastapi_app.get("/api/v1/worker/jobs/{job_id}/storyboard-image/{scene_index}/{slot}")'
    assert route in BOT_SOURCE
    section = _source_section(
        BOT_SOURCE,
        "async def api_worker_storyboard_scene_image",
        '@fastapi_app.get("/api/v1/worker/jobs/{job_id}/source-video")',
    )
    assert "verify_remote_worker_api_access(request)" in section
    assert "product_type not in PRODUCT_VIDEO_SCENE_IMAGE_INPUT_TYPES" in section
    assert "start_image_file_id" in section
    assert "end_image_file_id" in section
    assert "tg_app.bot.get_file(file_id)" in section


def test_remote_worker_materializes_product_video_logo(tmp_path, monkeypatch) -> None:
    class _Response:
        def __init__(self, payload: bytes):
            self.payload = payload
            self.offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size: int) -> bytes:
            chunk = self.payload[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    observed: list[str] = []

    def fake_urlopen(request, timeout):
        observed.append(request.full_url)
        return _Response(b"logo-image-bytes")

    monkeypatch.setattr(remote_worker, "endpoint", lambda path: f"https://worker.invalid{path}")
    monkeypatch.setattr(remote_worker.urllib.request, "urlopen", fake_urlopen)
    job = {
        "job_id": "logo-job",
        "product_type": "video_ai_prompt",
        "asset_pack": {
            "logo_material": {
                "logo_enabled": True,
                "logo_file_id": "telegram-logo",
                "logo_position": "bottom_left",
            },
        },
    }

    path = remote_worker.download_product_video_logo(job, str(tmp_path))
    material = job["asset_pack"]["logo_material"]

    assert Path(path).read_bytes() == b"logo-image-bytes"
    assert material["logo_path"] == path
    assert material["logo_file_id"] == "telegram-logo"
    assert observed == [
        "https://worker.invalid/api/v1/worker/jobs/logo-job/logo-material",
    ]


def test_bot_exposes_authenticated_product_video_logo_transfer() -> None:
    route = '@fastapi_app.get("/api/v1/worker/jobs/{job_id}/logo-material")'
    assert route in BOT_SOURCE
    section = _source_section(
        BOT_SOURCE,
        "async def api_worker_product_video_logo_material",
        '@fastapi_app.get("/api/v1/worker/jobs/{job_id}/source-video")',
    )
    assert "verify_remote_worker_api_access(request)" in section
    assert "logo_material" in section
    assert "tg_app.bot.get_file(file_id)" in section


def test_public_video_route_gate_is_open_except_long_video() -> None:
    namespace = {
        "VIDEO_AI_PUBLIC_ENABLED": False,
        "VIDEO_IMAGE_TO_VIDEO_ENABLED": False,
        "VIDEO_VIDEO_TO_VIDEO_ENABLED": False,
        "VIDEO_LONG_RENDER_ENABLED": False,
        "VIDEO_TREND_RENDER_ENABLED": False,
    }
    exec(
        _source_section(
            BOT_SOURCE,
            "def video_render_feature_enabled",
            "def developing_video_render_guard_text",
        ),
        namespace,
    )
    enabled = namespace["video_render_feature_enabled"]
    for flow in (
        "promptvideo",
        "imagevideo",
        "videoref",
        "selfscene",
        "trend",
        "storypack",
        "videoidea",
    ):
        assert enabled(flow) is True
    assert enabled("longvideo") is False


def test_storyboard_entry_owner_and_confirm_audit_see_the_real_handler() -> None:
    route_section = _source_section(
        BOT_SOURCE,
        '    "storyboard_prompt": {',
        '    "prompt_library": {',
    )
    assert '"entry_callback": "vid3|entry|storyboard_prompt"' in route_section
    assert '"legacy_entry_callback": "vproduct|open|storyboard_prompt"' in route_section
    assert '"handler": "handle_video_uiflow3_callback"' in route_section

    guard_section = _source_section(
        BOT_SOURCE,
        "def video_public_callback_failure_guard",
        "async def video_public_media_dedupe_guard",
    )
    assert "guarded.__wrapped__ = callback_handler" in guard_section
    handler_section = _source_section(
        BOT_SOURCE,
        "async def handle_video_product_callback",
        "async def task3d_reply_current_guided_step",
    )
    assert 'if action == "b14_confirm"' in handler_section


def test_confirm_kickoff_resolves_the_parent_product_capability(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_resolve(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "selected_provider": "fixture", "selected_model": "fixture", "supports_concat": True}

    monkeypatch.setattr(video_project_queue, "resolve_product_video_model", fake_resolve)
    project = {
        "project_id": 71,
        "profile_id": "storyboard_prompt",
        "scene_count": 2,
        "quality_tier": 300,
        "total_xu_estimated": 300,
        "asset_pack_json": json.dumps(
            {
                "source": "product_video",
                "render_mode": "real",
                "product_type": "storyboard_prompt",
                "provider_call": True,
                "public_user": True,
                "preconfirm_candidate_keys": ["fixture"],
            }
        ),
        "invoice_json": json.dumps(
            {
                "source": "product_video",
                "render_mode": "real",
                "product_type": "storyboard_prompt",
                "scene_count": 2,
                "scene_seconds": 5,
                "scene_duration_seconds": 5,
                "duration_seconds": 10,
                "total_xu": 300,
                "customer_charge_planned_xu": 300,
                "persisted_quoted_price_xu": 300,
                "user_visible_price_xu": 300,
            }
        ),
        "scene_cards_json": "[]",
    }
    job = {"id": 71, "result_json": "{}"}

    payload = video_project_queue.build_product_video_confirm_kickoff_payload(job, project, provider_chain=["fixture"])

    assert captured["required_capability"] == "image_to_video"
    assert payload["product_type"] == "storyboard_prompt"
    assert payload["required_capability"] == "image_to_video"
    assert payload["scene_duration_seconds"] == 5
    assert payload["duration_seconds"] == 10
    assert [item["scene_duration_seconds"] for item in payload["scene_tasks"]] == [5, 5]


def test_remote_worker_model_resolution_keeps_each_product_capability(monkeypatch) -> None:
    expected = {
        "video_trend": "text_to_video_or_scene_video",
        "video_ai_real": "text_to_video",
        "script_image_video": "text_to_video_or_scene_video",
        "storyboard_prompt": "image_to_video",
        "self_shot_scene_change": "video_to_video",
        "self_shot_cinematic_transform": "video_to_video",
    }
    captured: list[str] = []

    def fake_resolve(**kwargs):
        captured.append(str(kwargs.get("required_capability") or ""))
        return {
            "ok": True,
            "selected_provider": "fixture",
            "selected_model": "fixture-model",
            "selected_capabilities": [kwargs.get("required_capability")],
            "provider_model_map": {"fixture": "fixture-model"},
            "supports_concat": True,
        }

    monkeypatch.setattr(remote_worker_api, "resolve_product_video_model", fake_resolve)
    for index, (product_type, capability) in enumerate(expected.items(), start=1):
        contract = video_project_queue.product_video_engine_contract(product_type)
        asset_pack = {
            "source": "product_video",
            "render_mode": "real",
            "provider_call": True,
            "public_user": True,
            "product_type": product_type,
            "engine_adapter": contract["engine_adapter"],
            "provider_chain": ["fixture"],
            "preconfirm_candidate_keys": ["fixture"],
        }
        payload = remote_worker_api.build_worker_job_payload(
            {
                "id": index,
                "job_type": video_project_queue.VIDEO_RENDER_JOB_TYPE,
                "quality_tier": 300,
                "result_json": "{}",
                "project": {
                    "project_id": index,
                    "user_id": 42,
                    "profile_id": product_type,
                    "ratio": "9:16",
                    "scene_count": 2,
                    "quality_tier": 300,
                    "scene_cards_json": json.dumps(
                        [
                            {"scene_index": 1, "video_prompt": "scene one"},
                            {"scene_index": 2, "video_prompt": "scene two"},
                        ]
                    ),
                    "asset_pack_json": json.dumps(asset_pack),
                    "invoice_json": json.dumps({"product_type": product_type, "scene_count": 2}),
                    "addon_plan_json": "{}",
                },
            }
        )
        assert captured[-1] == capability
        assert payload["required_capability"] == capability
        assert payload["engine_route"] == contract["engine_route"]
        assert payload["engine_adapter"] == contract["engine_adapter"]
        assert payload["input_type"] == contract["input_type"]
        assert payload["worker_owner"] == contract["worker_owner"]


def test_runtime_admission_recheck_uses_the_same_product_capability_contract() -> None:
    source = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
    section = _source_section(
        source,
        "def _product_video_runtime_eligibility",
        "def claim_remote_worker_canary_job",
    )
    assert "video_project_queue.product_video_engine_contract" in section
    assert 'or "text_to_video_or_scene_video"' not in section


def test_local_product_video_worker_keeps_scene_count_duration_and_delivery_receipt() -> None:
    section = _source_section(WORKER_SOURCE, "def run_video_render_job", "def run_frame_video_render")
    assert "min(5" not in section
    assert "                20," in section
    assert "product_video_scene_duration_seconds" in section
    assert "telegram_send_video_receipt(" in section
    assert 'delivery_message_id' in section
    assert 'delivery_file_id' in section


def test_local_product_video_worker_materializes_and_passes_image_logo() -> None:
    section = _source_section(WORKER_SOURCE, "def run_video_render_job", "def run_frame_video_render")
    assert "product_video_logo_material" in section
    assert "telegram_download_file" in section
    assert "logo_path=logo_path" in section
    assert "enable_logo=logo_enabled" in section


def test_local_video_worker_update_persists_delivery_before_charge() -> None:
    endpoint = _source_section(BOT_SOURCE, "async def internal_video_worker_job_update", "@fastapi_app.post(\"/internal/worker/upload_result\")")
    assert "note_video_delivery_result" in endpoint
    assert "product_video_charge_after_final_delivery" in endpoint
    assert endpoint.index("note_video_delivery_result") < endpoint.index("product_video_charge_after_final_delivery")


def test_product_video_completion_uses_the_canonical_project_detector() -> None:
    section = _source_section(QUEUE_SOURCE, "def complete_video_job", "def note_video_delivery_result")
    assert "product_job = _is_product_video_project(project)" in section


def test_frame_video_payload_carries_an_explicit_local_engine_contract() -> None:
    frame_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    section = _source_section(frame_source, "def frame_video_worker_payload", "def frame_video_preview_worker_payload")
    for field in (
        '"frame_video_contract": 1',
        '"worker_job_type": frame_video_commercial.WORKER_JOB_TYPE',
        '"engine_route": frame_video_commercial.ENGINE_ROUTE',
        '"worker_owner": frame_video_commercial.WORKER_OWNER',
        '"worker_capability": frame_video_commercial.WORKER_CAPABILITY',
    ):
        assert field in section


def test_frame_video_commercial_exposes_one_worker_contract() -> None:
    from services import frame_video_commercial

    assert frame_video_commercial.WORKER_JOB_TYPE == "frame_video_render"
    assert frame_video_commercial.ENGINE_ROUTE == "frame_video_render"
    assert frame_video_commercial.WORKER_OWNER == "frame_video"
    assert frame_video_commercial.WORKER_CAPABILITY == "frame_video_render"


def test_product_video_logo_supports_all_nine_positions() -> None:
    for position in (
        "top_left", "top_center", "top_right",
        "center_left", "center", "center_right",
        "bottom_left", "bottom_center", "bottom_right",
    ):
        x, y = video_real_render_connector.product_video_logo_overlay_xy(position)
        assert x and y


def test_multiscene_logo_image_is_wired_into_the_final_ffmpeg_filter() -> None:
    source = (ROOT / "services" / "multiscene_video_pipeline.py").read_text(encoding="utf-8")
    section = _source_section(source, "def mux_final_multiscene_video", "def _upsert_scene_result")
    assert "scale2ref" in section
    assert "overlay=" in section
    assert "logo_path" in section


def test_multiscene_logo_overlay_ends_with_the_master_and_validates_mp4(tmp_path) -> None:
    first = tmp_path / "scene-1.png"
    second = tmp_path / "scene-2.png"
    logo = tmp_path / "logo.png"
    Image.new("RGB", (320, 180), (0, 128, 128)).save(first)
    Image.new("RGB", (320, 180), (30, 30, 30)).save(second)
    Image.new("RGBA", (96, 48), (255, 255, 255, 220)).save(logo)

    base = video_final_output.render_local_image_sequence_video(
        [str(first), str(second)],
        str(tmp_path / "base.mp4"),
        duration_per_image=0.5,
    )
    assert base["ok"] is True
    output = multiscene_video_pipeline.mux_final_multiscene_video(
        master_video_path=str(tmp_path / "base.mp4"),
        output_path=str(tmp_path / "logo.mp4"),
        logo_path=str(logo),
        logo_position="center",
    )
    validation = video_final_output.validate_final_video_output(
        path=output,
        result={"renderer": "provider_scene_video", "visual_classification": "final_ai_video"},
    )
    assert validation["ok"] is True


def test_long_video_remains_execution_locked() -> None:
    contract = video_tail9.commercial_contract("multi_scene_film")
    assert contract["execution_enabled"] is False
    assert contract["execution_blocker"] == "long_video_under_upgrade"
