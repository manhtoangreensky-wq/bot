from __future__ import annotations

from pathlib import Path

import pytest

import remote_worker
from services import video_ai_edit_provider
from services import video_final_output
from services import video_flow7
from services import video_real_render_connector
from services import video_selfshot3


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _source() -> dict:
    return {
        "file_id": "telegram-video-1",
        "file_unique_id": "source-unique-1",
        "file_name": "source.mp4",
        "file_size": 1024,
        "duration_seconds": 8,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "audio_streams": 1,
        "format": "video/mp4",
    }


def _person_analysis() -> dict:
    return video_selfshot3.analyze_source(
        _source(),
        detected_people=[{"subject_id": "person-1", "label": "áo trắng, giữa khung"}],
        detected_faces=[{"subject_id": "face-1", "label": "khuôn mặt người 1"}],
    )


def _ready_draft(*, custom_subject: bool = True) -> dict:
    draft = video_selfshot3.initial_draft()
    source = _source()
    analysis = video_selfshot3.analyze_source(source)
    if custom_subject:
        subject = video_selfshot3.select_subjects(
            analysis,
            "custom",
            description="Người áo trắng ở giữa khung hình",
        )
    else:
        analysis = _person_analysis()
        subject = video_selfshot3.select_subjects(analysis, "person")
    segment = video_selfshot3.segment_selection(analysis)
    preset = video_selfshot3.transformation_catalog()[0]["presets"][0]
    stages = video_selfshot3.build_timeline(
        segment=segment,
        stage_count=4,
        preset=preset,
        wardrobe="Fantasy thanh lịch",
        world="thiên nhiên fantasy",
        effects=["hạt sáng", "cánh hoa"],
    )
    draft.update(
        {
            "source_video": source,
            "source_analysis": analysis,
            "source_segment": segment,
            "subject_manifest": subject,
            "relationship_locks": [],
            "selected_group_id": "continuous_one_take",
            "selected_preset": dict(preset),
            "transformation_stage_count": 4,
            "transformation_content": "Từ căn phòng thật chuyển thành thế giới fantasy trong một cú máy",
            "transformation_stages": stages,
            "wardrobe": "Fantasy thanh lịch",
            "world": "thiên nhiên fantasy",
            "selected_effects": ["hạt sáng", "cánh hoa"],
        }
    )
    return draft


def _provider(name: str, model: str) -> video_ai_edit_provider.AiEditProviderConfig:
    return video_ai_edit_provider.AiEditProviderConfig(
        provider_name=name,
        enabled=True,
        submit_url=f"https://provider.invalid/{name}/submit",
        poll_url=f"https://provider.invalid/{name}/tasks/{{task_id}}",
        auth_header_name="Authorization",
        auth_header_value="Bearer configured-secret",
        model=model,
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )


def test_public_product_is_distinct_from_legacy_self_shot() -> None:
    assert video_selfshot3.PRODUCT_ID == "self_shot_cinematic_transform"
    assert video_selfshot3.JOB_TYPE == "self_shot_cinematic_transform"
    assert video_selfshot3.LEGACY_JOB_TYPE == "self_shot_scene_change"
    assert video_flow7.product_kind(video_selfshot3.PRODUCT_ID) == "self_shot_cinematic"
    assert video_flow7.execution_route(video_selfshot3.PRODUCT_ID)["provider_or_local_route"] == video_selfshot3.JOB_TYPE
    assert "🎥 Tự quay & biến đổi điện ảnh" in BOT_SOURCE


def test_source_video_precedes_every_transformation_step() -> None:
    sequence = video_flow7.product_sequence(video_selfshot3.PRODUCT_ID)
    assert sequence[:4] == ("source_video", "source_probe", "source_segment", "subject_selection")
    assert "scene_count" not in sequence[:4]
    rows = video_flow7.entry_rows(video_selfshot3.PRODUCT_ID)
    callbacks = [callback for row in rows for _label, callback in row]
    assert callbacks[0] == "vproduct|ss3|source"


def test_catalog_has_sixteen_groups_and_twenty_unique_presets_each() -> None:
    catalog = video_selfshot3.transformation_catalog()
    assert len(catalog) == 16
    assert len({group["group_id"] for group in catalog}) == 16
    for group in catalog:
        assert len(group["presets"]) == 20
        assert len({item["preset_id"] for item in group["presets"]}) == 20
        assert all(item["group_id"] == group["group_id"] for item in group["presets"])


def test_planning_draft_has_zero_side_effects() -> None:
    draft = video_selfshot3.initial_draft()
    assert draft["provider_called"] is False
    assert draft["job_created"] is False
    assert draft["outbox_created"] is False
    assert draft["generated_files"] == 0
    assert draft["wallet_mutations"] == 0
    assert draft["xu_charged"] == 0


def test_every_public_screen_has_valid_rows_unique_callbacks_and_exact_back() -> None:
    draft = _ready_draft()
    screens = list(video_selfshot3.SCREEN_PARENTS)
    for screen in screens:
        model = video_selfshot3.screen_model(screen, draft)
        parent = video_selfshot3.screen_parent(screen)
        expected_back = (
            "vproduct|selfshot_hub"
            if parent == "hub"
            else f"vproduct|ss3|show|{parent}"
        )
        validation = video_selfshot3.validate_rows(
            model["rows"], back_callback=expected_back
        )
        assert validation["ok"] is True, (screen, validation["errors"])
        assert len(validation["callbacks"]) == len(set(validation["callbacks"]))


def test_suggestion_row_is_exactly_one_row_of_five() -> None:
    draft = _ready_draft()
    draft["selected_group_id"] = "continuous_one_take"
    model = video_selfshot3.screen_model("presets", draft)
    assert [label for label, _callback in model["rows"][0]] == ["1", "2", "3", "4", "5"]


def test_callback_operations_have_one_canonical_owner_screen() -> None:
    assert video_selfshot3.callback_operation_allowed("types", "group_preview") is True
    assert video_selfshot3.callback_operation_allowed("groups", "group_preview") is False
    assert video_selfshot3.callback_operation_allowed("groups", "group") is True
    assert video_selfshot3.callback_operation_allowed("types", "group") is False
    assert video_selfshot3.callback_operation_allowed("volume", "volume_set") is True
    assert video_selfshot3.callback_operation_allowed("audio", "volume_set") is False


def test_metadata_only_analysis_does_not_claim_identity_tracking() -> None:
    report = video_selfshot3.analyze_source(_source())
    assert report["tracking_source"] == "metadata_only"
    assert report["tracking_ready"] is False
    manifest = video_selfshot3.select_subjects(report, "person")
    gate = video_selfshot3.subject_tracking_gate(report, manifest)
    assert gate["ok"] is False
    assert "subject_track_missing" in gate["blockers"]
    assert "face_identity_track_missing" in gate["blockers"]


def test_person_fixture_uses_real_supplied_tracks() -> None:
    report = _person_analysis()
    manifest = video_selfshot3.select_subjects(report, "person")
    gate = video_selfshot3.subject_tracking_gate(report, manifest)
    assert report["detector_results_supplied"] is True
    assert report["tracking_source"] == "supplied_local_detector"
    assert manifest["selected_ids"] == ["person-1"]
    assert gate["ok"] is True


def test_custom_subject_is_source_bound_without_fake_detector_claim() -> None:
    report = video_selfshot3.analyze_source(_source())
    manifest = video_selfshot3.select_subjects(
        report,
        "custom",
        description="Chiếc túi đỏ ở giữa khung",
    )
    gate = video_selfshot3.subject_tracking_gate(report, manifest)
    assert manifest["source_bound"] is True
    assert manifest["stable_ids"] is False
    assert gate["ok"] is True


def test_person_object_requires_and_preserves_interaction_lock() -> None:
    source = _source()
    source["interaction_graph"] = [
        {
            "person_id": "person-1",
            "object_id": "object-1",
            "relationship_type": "holding",
            "contact_points": ["right_hand", "handle"],
            "relative_position": "object in right hand",
        }
    ]
    report = video_selfshot3.analyze_source(
        source,
        detected_people=[{"subject_id": "person-1"}],
        detected_faces=[{"subject_id": "face-1"}],
        detected_objects=[{"subject_id": "object-1", "label": "túi đỏ"}],
    )
    manifest = video_selfshot3.select_subjects(report, "person_object")
    blocked = video_selfshot3.subject_tracking_gate(report, manifest)
    assert blocked["blocker"] == "interaction_lock_missing"
    locks = video_selfshot3.build_interaction_lock(manifest, report)
    assert locks == [
        {
            "person_id": "person-1",
            "object_id": "object-1",
            "relationship_type": "holding",
            "contact_points": ["right_hand", "handle"],
            "relative_position": "object in right hand",
            "interaction_lock": True,
        }
    ]
    assert video_selfshot3.subject_tracking_gate(report, manifest, locks)["ok"] is True


@pytest.mark.parametrize("layer", sorted(video_selfshot3.MANDATORY_PRESERVE_LAYERS))
def test_mandatory_continuity_layers_cannot_be_unlocked(layer: str) -> None:
    rules = video_selfshot3.update_layer_rule(
        video_selfshot3.default_layer_rules(), layer, "transform"
    )
    assert rules[layer] == "preserve"


@pytest.mark.parametrize("stage_count", (2, 3, 4, 5))
def test_one_take_timeline_has_exact_order_and_source_bounds(stage_count: int) -> None:
    segment = {"start_ms": 1200, "end_ms": 9200, "duration_ms": 8000}
    stages = video_selfshot3.build_timeline(
        segment=segment,
        stage_count=stage_count,
        preset={"title": "Sóng biến đổi"},
        wardrobe="Fantasy",
        world="cung điện",
        effects=["hạt sáng"],
    )
    assert len(stages) == stage_count
    assert stages[0]["start_ms"] == 1200
    assert stages[-1]["end_ms"] == 9200
    assert all(left["end_ms"] == right["start_ms"] for left, right in zip(stages, stages[1:]))
    assert all(stage["camera_policy"] == "preserve_source_camera" for stage in stages)
    assert all("no_abrupt_cut" in stage["negative_constraints"] for stage in stages)


def test_prompt_compiler_contains_identity_motion_relationship_and_negative_locks() -> None:
    draft = _ready_draft(custom_subject=False)
    bundle = video_selfshot3.compile_prompt(
        mode=video_selfshot3.MODE_ONE_TAKE,
        subject_manifest=draft["subject_manifest"],
        relationship_locks=[],
        layer_rules=draft["layer_rules"],
        segment=draft["source_segment"],
        stages=draft["transformation_stages"],
        wardrobe=draft["wardrobe"],
        world=draft["world"],
        effects=draft["selected_effects"],
        content=draft["transformation_content"],
    )
    assert bundle["identity_lock"] == ["person-1"]
    assert bundle["motion_lock"] == "preserve_source_motion"
    assert len(bundle["stage_prompts"]) == 4
    negative = bundle["negative_prompt"]
    for phrase in (
        "no face replacement",
        "no identity drift",
        "no duplicate person",
        "no extra limbs",
        "no hand deformation",
        "no object disappearance",
        "no logo distortion",
        "no abrupt background cut",
        "no temporal flicker",
    ):
        assert phrase in negative


@pytest.mark.parametrize(
    ("capabilities", "expected_route", "truthful_fallback"),
    (
        ({"direct_video_to_video"}, "direct_video_to_video", False),
        ({"performance_capture"}, "performance_capture", False),
        ({"regional_mask_transform"}, "masked_regional_transform", False),
        ({"person_identity_reference"}, "reference_assisted_video", False),
        ({"first_last_frame"}, "keyframe_image_to_video", True),
    ),
)
def test_engine_capability_routes_are_truthful(
    capabilities: set[str], expected_route: str, truthful_fallback: bool
) -> None:
    route = video_selfshot3.capability_route(
        capabilities,
        mode=video_selfshot3.MODE_ONE_TAKE,
    )
    assert route["ok"] is True
    assert route["route"] == expected_route
    assert route["truthful_fallback"] is truthful_fallback
    if truthful_fallback:
        assert "not_direct_video_to_video" in route["limitations"]


def test_preflight_passes_without_side_effects_when_every_gate_is_ready() -> None:
    report = video_selfshot3.preflight(
        _ready_draft(),
        capabilities={"direct_video_to_video"},
        owner_ready=True,
        package_available=True,
        delivery_ready=True,
    )
    assert report["ok"] is True
    assert report["job_type"] == video_selfshot3.JOB_TYPE
    assert set(report["side_effects"].values()) == {0}


def test_unavailable_engine_is_blocked_before_invoice() -> None:
    report = video_selfshot3.preflight(
        _ready_draft(),
        capabilities=set(),
        owner_ready=False,
        package_available=False,
        delivery_ready=False,
    )
    assert report["ok"] is False
    assert report["engine_route"]["ok"] is False
    assert report["engine_route"]["blocker"] in {
        "cinematic_transform_capability_missing",
        "regional_identity_capability_missing",
    }
    assert "execution_owner_unavailable" in report["blockers"]
    assert report["side_effects"]["invoice"] == 0
    assert report["side_effects"]["provider_calls"] == 0
    assert report["side_effects"]["xu_charged"] == 0


def test_delivery_requires_valid_mp4_continuity_and_real_telegram_message_id() -> None:
    good_scores = {
        "identity": 0.95,
        "body": 0.95,
        "motion": 0.95,
        "object": 0.95,
        "interaction": 0.95,
        "temporal": 0.95,
    }
    with pytest.raises(ValueError, match="valid_final_mp4_required"):
        video_selfshot3.record_delivery(
            {}, final_mp4_valid=False, message_id=99, receipt_key="job:99"
        )
    with pytest.raises(ValueError, match="valid_telegram_delivery_required"):
        video_selfshot3.record_delivery(
            {}, final_mp4_valid=True, message_id=0, receipt_key="job:99"
        )
    with pytest.raises(ValueError, match="continuity_validation_required"):
        video_selfshot3.record_delivery(
            {},
            final_mp4_valid=True,
            message_id=99,
            receipt_key="job:99",
            continuity={**good_scores, "identity": 0.2},
        )
    delivered = video_selfshot3.record_delivery(
        {},
        final_mp4_valid=True,
        message_id=99,
        receipt_key="job:99",
        continuity=good_scores,
    )
    assert video_selfshot3.charge_allowed(delivered) is True
    assert (
        video_selfshot3.record_delivery(
            delivered,
            final_mp4_valid=True,
            message_id=99,
            receipt_key="job:99",
            continuity=good_scores,
        )
        == delivered
    )


def test_selfshot_scene_duration_uses_full_selected_source_segment() -> None:
    job = {
        "product_type": video_selfshot3.JOB_TYPE,
        "asset_pack": {"source_segment": {"duration_ms": 17_000}},
    }
    assert video_real_render_connector.product_video_scene_duration_seconds(job) == 17


def test_engine_blocks_missing_source_before_provider_submit(tmp_path: Path) -> None:
    with pytest.raises(video_real_render_connector.RealVideoRenderError) as raised:
        video_real_render_connector._render_selfshot3_video_to_video(
            job={"job_id": "job-1"},
            asset_pack={"public_user_confirmed": True, "submit_source": "public_user_final_confirm"},
            raw_path=str(tmp_path / "output.mp4"),
            provider_order=["key4u"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
        )
    assert raised.value.diagnostics["provider_attempted"] is False
    assert raised.value.diagnostics["no_charge"] is True
    assert raised.value.diagnostics["blocker"] == "selfshot3_source_video_not_materialized"


def test_engine_blocks_hidden_or_unconfirmed_submit_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    provider_calls = []
    monkeypatch.setattr(
        video_ai_edit_provider,
        "submit_video_edit",
        lambda *args, **kwargs: provider_calls.append((args, kwargs)),
    )
    with pytest.raises(video_real_render_connector.RealVideoRenderError) as raised:
        video_real_render_connector._render_selfshot3_video_to_video(
            job={"job_id": "job-2", "source_video_local_path": str(source)},
            asset_pack={"public_user_confirmed": False, "submit_source": "debug"},
            raw_path=str(tmp_path / "output.mp4"),
            provider_order=["key4u"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
        )
    assert provider_calls == []
    assert raised.value.diagnostics["blocker"] == "selfshot3_public_confirm_required"


def test_engine_uses_one_mocked_direct_video_to_video_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    output = tmp_path / "result.mp4"
    config = _provider("key4u_video", "kling-motion-control")
    calls = []

    monkeypatch.setattr(
        video_real_render_connector,
        "_selfshot3_provider_configs",
        lambda provider_order, duration_seconds: [config],
    )

    def fake_submit(_config, **kwargs):
        calls.append(kwargs)
        return {
            "provider_task_id": "task-1",
            "result_url_present": True,
            "result_url": "https://provider.invalid/result.mp4",
        }

    def fake_download(_url: str, destination: str):
        Path(destination).write_bytes(b"mock-final-mp4")
        return {"ok": True, "path": destination, "bytes": 14}

    monkeypatch.setattr(video_ai_edit_provider, "submit_video_edit", fake_submit)
    monkeypatch.setattr(video_ai_edit_provider, "download_result", fake_download)

    result = video_real_render_connector._render_selfshot3_video_to_video(
        job={"job_id": "job-3", "source_video_local_path": str(source)},
        asset_pack={
            "public_user_confirmed": True,
            "submit_source": "public_user_final_confirm",
            "source_segment": {"start_ms": 0, "end_ms": 8000, "duration_ms": 8000},
            "transformation_stages": _ready_draft()["transformation_stages"],
        },
        raw_path=str(output),
        provider_order=["key4u"],
        fallback_prompt="one-take prompt",
        aspect_ratio="9:16",
    )
    assert len(calls) == 1
    assert calls[0]["source_video_path"] == str(source)
    assert calls[0]["submit_source"] == video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE
    assert calls[0]["public_user_confirmed"] is True
    assert result["engine_route"] == "direct_video_to_video"
    assert result["source_uploaded_multipart"] is True
    assert result["fallback_count"] == 0
    assert result["expected_duration_seconds"] == 8
    assert output.read_bytes() == b"mock-final-mp4"


def test_engine_uses_at_most_one_mocked_terminal_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    output = tmp_path / "result.mp4"
    primary = _provider("key4u_video", "kling-motion-control")
    fallback = _provider("key4u_video", "kling-video")
    calls = []

    monkeypatch.setattr(
        video_real_render_connector,
        "_selfshot3_provider_configs",
        lambda provider_order, duration_seconds: [primary, fallback],
    )

    def fake_submit(config, **kwargs):
        calls.append(config.model)
        if config.model == primary.model:
            raise video_ai_edit_provider.AiEditProviderError("provider_terminal_failure")
        return {
            "provider_task_id": "fallback-task",
            "result_url_present": True,
            "result_url": "https://provider.invalid/fallback.mp4",
        }

    def fake_download(_url: str, destination: str):
        Path(destination).write_bytes(b"fallback-final-mp4")
        return {"ok": True, "path": destination, "bytes": 18}

    monkeypatch.setattr(video_ai_edit_provider, "submit_video_edit", fake_submit)
    monkeypatch.setattr(video_ai_edit_provider, "download_result", fake_download)

    result = video_real_render_connector._render_selfshot3_video_to_video(
        job={"job_id": "job-4", "source_video_local_path": str(source)},
        asset_pack={
            "public_user_confirmed": True,
            "submit_source": "public_user_final_confirm",
            "source_segment": {"duration_ms": 8000},
        },
        raw_path=str(output),
        provider_order=["key4u"],
        fallback_prompt="prompt",
        aspect_ratio="9:16",
    )
    assert calls == [primary.model, fallback.model]
    assert result["fallback_used"] is True
    assert result["fallback_count"] == 1
    assert len(result["attempts"]) == 2


class _FakeDownloadResponse:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int) -> bytes:
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


def test_worker_materializes_source_only_inside_disposable_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    download_observations = []
    monkeypatch.setattr(remote_worker, "endpoint", lambda path: f"https://railway.invalid{path}")
    monkeypatch.setattr(remote_worker, "auth_headers", lambda _body: {"Authorization": "Bearer worker"})

    def fake_urlopen(request, timeout):
        download_observations.append((request.full_url, request.headers, timeout))
        return _FakeDownloadResponse(b"source-video-bytes")

    monkeypatch.setattr(remote_worker.urllib.request, "urlopen", fake_urlopen)
    job = {"job_id": "42", "product_type": video_selfshot3.JOB_TYPE}
    path = Path(remote_worker.download_selfshot3_source_video(job, str(tmp_path))).resolve()
    assert path.parent == tmp_path.resolve()
    assert path.read_bytes() == b"source-video-bytes"
    assert job["source_video_local_path"] == str(path)
    assert download_observations[0][0].endswith("/api/v1/worker/jobs/42/source-video")
    assert download_observations[0][2] == 120


def test_engine_registration_requires_source_and_video_to_video_capability() -> None:
    route = video_final_output.route_for_product_type(video_selfshot3.JOB_TYPE)
    assert route["engine_family"] == "reference_video"
    assert route["provider_capability"] == "video_to_video"
    assert "source_video" in route["input_requirements"]
    assert "transformation_stages" in route["input_requirements"]


def test_bot_has_one_selfshot3_owner_no_generic_x_and_authenticated_source_transfer() -> None:
    start = BOT_SOURCE.index('if action == "ss3":')
    end = BOT_SOURCE.index('if action == "scene3_mode":', start)
    callback_block = BOT_SOURCE[start:end]
    assert BOT_SOURCE.count('if action == "ss3":') == 1
    assert "Có lỗi khi xử lý lệnh" not in callback_block
    assert "callback_operation_allowed" in callback_block
    assert '@fastapi_app.get("/api/v1/worker/jobs/{job_id}/source-video")' in BOT_SOURCE
    assert "verify_remote_worker_api_access" in BOT_SOURCE[
        BOT_SOURCE.index("async def api_worker_selfshot3_source_video") :
        BOT_SOURCE.index("async def api_worker_selfshot3_source_video") + 5000
    ]
    assert '"in_progress"' in BOT_SOURCE[
        BOT_SOURCE.index("async def api_worker_selfshot3_source_video") :
        BOT_SOURCE.index("async def api_worker_selfshot3_source_video") + 5000
    ]


def test_no_real_provider_or_wallet_api_is_called_by_this_test_module() -> None:
    source = Path(__file__).read_text(encoding="utf-8").lower()
    assert "requests" + "." not in source
    assert "httpx" + "." not in source
    assert "shopai" + "key.com" not in source
    assert "key4u" + ".shop" not in source
    assert "wallet" + "_debit" not in source
