from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import remote_worker
from services import video_flow7
from services import video_real_render_connector
from services import video_selfshot2


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _source(**updates) -> dict:
    source = {
        "file_id": "telegram-source-video",
        "file_unique_id": "source-video-unique",
        "file_name": "source.mp4",
        "file_size": 4096,
        "duration_seconds": 16,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "audio_streams": 1,
        "format": "video/mp4",
        "main_actions": ["nguoi cam chai san pham va buoc ve phia truoc"],
        "person_candidates": [
            {
                "subject_id": "person-1",
                "description": "Nguoi ao den ben trai",
                "confidence": 0.98,
            }
        ],
        "object_candidates": [
            {
                "subject_id": "object-1",
                "description": "Chai san pham mau xanh trong tay phai",
                "confidence": 0.97,
            }
        ],
        "interaction_graph": [
            {
                "person_id": "person-1",
                "object_id": "object-1",
                "relationship_type": "holding",
            }
        ],
    }
    source.update(updates)
    return source


def _ready_draft(*, mode: str = "person_object", scene_count: int = 2) -> dict:
    draft = video_selfshot2.initial_draft()
    source = _source()
    analysis = video_selfshot2.analyze_source(source)
    manifest = video_selfshot2.select_subjects(analysis, mode)
    constraints = video_selfshot2.default_preserve_constraints(manifest)
    content = video_selfshot2.suggestion_catalog(
        analysis,
        manifest,
        scene_count=scene_count,
        aspect_ratio="9:16",
    )[0]
    direction = video_selfshot2.direction_contract("environment")
    plan = video_selfshot2.build_scene_plan(
        analysis=analysis,
        subject_manifest=manifest,
        constraints=constraints,
        scene_count=scene_count,
        content=content,
        direction=direction,
    )
    prompts = video_selfshot2.compile_scene_prompts(
        plan,
        subject_manifest=manifest,
        content=content,
        direction=direction,
    )
    draft.update(
        {
            "source_video": source,
            "source_analysis": analysis,
            "subject_manifest": manifest,
            "preserve_constraints": constraints,
            "scene_count": scene_count,
            "aspect_ratio": "9:16",
            "content_source": "suggestions",
            "selected_content": content,
            "content_return_screen": "suggestions",
            "selected_direction": "environment",
            "direction_contract": direction,
            "scene_plan": plan,
            "video_prompts": prompts,
        }
    )
    return draft


def _callbacks(model: dict) -> list[str]:
    return [callback for row in model["rows"] for _label, callback in row]


def _back_callback(screen: str, draft: dict) -> str:
    parent = video_selfshot2.screen_parent(screen, draft)
    return (
        "vproduct|selfshot_hub"
        if parent == "hub"
        else f"vproduct|ss2|show|{parent}"
    )


def test_public_entry_requires_real_source_before_planning() -> None:
    draft = video_selfshot2.initial_draft()
    model = video_selfshot2.screen_model("intro", draft)
    callbacks = _callbacks(model)
    assert callbacks[0] == "vproduct|ss2|source"
    assert all(token not in " ".join(callbacks) for token in ("scene_count", "ratio", "profile", "suggestion"))
    assert video_selfshot2.source_gate({}, {})["blocker"] == "source_video_missing"
    assert draft["provider_called"] is False
    assert draft["job_created"] is False
    assert draft["outbox_created"] is False
    assert draft["generated_files"] == 0
    assert draft["wallet_mutations"] == 0
    assert draft["xu_charged"] == 0


def test_flow7_keeps_source_analysis_subjects_and_constraints_first() -> None:
    sequence = video_flow7.product_sequence(video_selfshot2.PRODUCT_ID)
    assert sequence[:6] == (
        "source_video",
        "source_analysis",
        "subject_selection",
        "preserve_constraints",
        "scene_count",
        "aspect_ratio",
    )
    assert video_flow7.execution_route(video_selfshot2.PRODUCT_ID)["provider_or_local_route"] == video_selfshot2.JOB_TYPE


def test_source_analysis_persists_stable_person_object_and_interaction_truth() -> None:
    analysis = video_selfshot2.analyze_source(_source())
    assert analysis["source_video_id"] == "telegram-source-video"
    assert analysis["source_hash"]
    assert analysis["person_tracks"][0]["subject_id"] == "person-1"
    assert analysis["object_tracks"][0]["subject_id"] == "object-1"
    assert analysis["interaction_graph"][0]["relationship_type"] == "holding"
    assert analysis["audio_manifest"]["stream_count"] == 1
    assert analysis["analysis_truth"] == "metadata_and_available_local_tracks_only"


@pytest.mark.parametrize(
    ("source_updates", "expected_ratio", "expected_rate_mode", "expected_audio_streams"),
    (
        ({"width": 1080, "height": 1920, "frame_rate_mode": "CFR", "audio_streams": 1}, "9:16", "cfr", 1),
        ({"width": 1920, "height": 1080, "is_vfr": True, "audio_streams": 0}, "16:9", "vfr", 0),
        ({"width": 1080, "height": 1080, "fps_mode": "unknown", "audio_streams": 2}, "1:1", "unknown", 2),
    ),
)
def test_source_analysis_preserves_orientation_frame_rate_and_audio_truth(
    source_updates: dict,
    expected_ratio: str,
    expected_rate_mode: str,
    expected_audio_streams: int,
) -> None:
    analysis = video_selfshot2.analyze_source(_source(**source_updates))
    assert analysis["aspect_ratio"] == expected_ratio
    assert analysis["frame_rate_mode"] == expected_rate_mode
    assert analysis["audio_manifest"]["stream_count"] == expected_audio_streams


@pytest.mark.parametrize(
    ("mode", "person_ids", "object_ids", "motion_only"),
    (
        ("person", ["person-1"], [], False),
        ("object", [], ["object-1"], False),
        ("person_object", ["person-1"], ["object-1"], False),
        ("motion_only", [], [], True),
    ),
)
def test_subject_modes_select_only_the_requested_source_tracks(
    mode: str,
    person_ids: list[str],
    object_ids: list[str],
    motion_only: bool,
) -> None:
    manifest = video_selfshot2.select_subjects(video_selfshot2.analyze_source(_source()), mode)
    assert manifest["person_subject_ids"] == person_ids
    assert manifest["object_subject_ids"] == object_ids
    assert manifest["motion_only"] is motion_only


@pytest.mark.parametrize("relationship_type", ("holding", "driving", "playing"))
def test_selected_person_object_relationship_is_carried_into_every_scene_prompt(relationship_type: str) -> None:
    source = _source(
        interaction_graph=[
            {
                "person_id": "person-1",
                "object_id": "object-1",
                "relationship_type": relationship_type,
            }
        ]
    )
    analysis = video_selfshot2.analyze_source(source)
    manifest = video_selfshot2.select_subjects(analysis, "person_object")
    content = video_selfshot2.suggestion_catalog(analysis, manifest, scene_count=2, aspect_ratio="9:16")[0]
    direction = video_selfshot2.direction_contract("environment")
    plan = video_selfshot2.build_scene_plan(
        analysis=analysis,
        subject_manifest=manifest,
        constraints=video_selfshot2.default_preserve_constraints(manifest),
        scene_count=2,
        content=content,
        direction=direction,
    )
    prompts = video_selfshot2.compile_scene_prompts(
        plan,
        subject_manifest=manifest,
        content=content,
        direction=direction,
    )
    assert manifest["interaction_graph"][0]["relationship_type"] == relationship_type
    assert all(scene["person_object_interactions"][0]["relationship_type"] == relationship_type for scene in plan)
    assert all(f"person-1 {relationship_type} object-1" in item["prompt"] for item in prompts)


def test_multiple_subjects_require_explicit_stable_ids() -> None:
    analysis = video_selfshot2.analyze_source(
        _source(
            person_candidates=[
                {"subject_id": "person-1", "description": "Nguoi ben trai"},
                {"subject_id": "person-2", "description": "Nguoi o giua"},
            ],
            object_candidates=[
                {"subject_id": "object-1", "description": "Chai xanh"},
                {"subject_id": "object-2", "description": "Chiec xe phia sau"},
            ],
        )
    )
    with pytest.raises(ValueError, match="person_subject_choice_required"):
        video_selfshot2.select_subjects(analysis, "person")
    with pytest.raises(ValueError, match="person_object_subject_choice_required"):
        video_selfshot2.select_subjects(analysis, "person_object")
    manifest = video_selfshot2.select_subjects(
        analysis,
        "person_object",
        selected_ids=["person-2", "object-1"],
    )
    assert manifest["subject_ids"] == ["person-2", "object-1"]


def test_required_identity_and_relationship_locks_cannot_pass_when_disabled() -> None:
    draft = _ready_draft()
    constraints = dict(draft["preserve_constraints"])
    for key, blocker in (
        ("person_identity", "person_identity_lock_missing"),
        ("object_identity", "object_identity_lock_missing"),
        ("person_object_relation", "person_object_relationship_lock_missing"),
        ("action_expression", "source_action_lock_missing"),
    ):
        changed = {**constraints, key: False}
        assert blocker in video_selfshot2.preserve_gate(draft["subject_manifest"], changed)["blockers"]


def test_every_public_screen_has_two_button_rows_unique_callbacks_and_exact_back() -> None:
    draft = _ready_draft()
    for screen in video_selfshot2.SCREEN_PARENTS:
        model = video_selfshot2.screen_model(screen, draft)
        validation = video_selfshot2.validate_rows(
            model["rows"],
            back_callback=_back_callback(screen, draft),
        )
        assert validation["ok"] is True, (screen, validation["errors"])
        for row in model["rows"]:
            assert len(row) <= 2 or (
                len(row) == 5 and [label for label, _callback in row] == ["1", "2", "3", "4", "5"]
            )


@pytest.mark.parametrize(
    ("screen", "return_to"),
    (
        ("analysis", "scene_count"),
        ("detected", "analysis"),
        ("preserve", "review"),
        ("scene_plan", "review"),
        ("prompts", "review"),
        ("audio", "review"),
        ("direction", "review"),
        ("addons", "review"),
    ),
)
def test_dynamic_subscreens_render_the_exact_calling_screen_as_back(
    screen: str,
    return_to: str,
) -> None:
    draft = _ready_draft()
    draft["screen_return_overrides"] = {screen: return_to}
    model = video_selfshot2.screen_model(screen, draft)
    expected = f"vproduct|ss2|show|{return_to}"
    assert model["rows"][-1][0][1] == expected


def test_review_enters_one_shared_addon_and_returns_to_prompts() -> None:
    draft = _ready_draft()
    model = video_selfshot2.screen_model("review", draft)
    callbacks = {callback for row in model["rows"] for _label, callback in row}
    assert "vproduct|ss2|finish" in callbacks
    assert "vproduct|ss2|review_addons" not in callbacks
    draft["screen_return_overrides"] = {"addons": "review"}
    assert video_selfshot2.screen_parent("addons", draft) == "review"
    assert video_selfshot2.validate_rows(
        model["rows"],
        back_callback="vproduct|ss2|show|prompts",
    )["ok"] is True


def test_direct_suggestions_clear_a_stale_profile_parent() -> None:
    draft = _ready_draft()
    draft.update({"selfshot2_screen": "content_source", "suggestions_parent": "profiles"})
    result = video_selfshot2.apply_action(draft, "content_source", "suggestions")
    assert result["screen"] == "suggestions"
    assert video_selfshot2.screen_parent("suggestions", result["state"]) == "content_source"


def test_all_rendered_selfshot_callbacks_have_a_known_single_owner_contract() -> None:
    draft = _ready_draft()
    service_operations = {
        "subject", "subject_id", "confirm_subject_ids", "clear_subject_ids",
        "preserve", "preserve_done", "preserve_default", "scene_count", "ratio",
        "content_source", "profile_page", "suggestion_page", "idea_page", "profile",
        "suggestion", "idea", "direction", "plan_view", "rebuild_plan",
        "compile_prompts", "prompt", "audio_review", "audio", "volume", "volume_set",
        "addon", "addon_position", "addon_position_set",
    }
    bot_operations = {"show", "source", "resume_segment", "reset", "finish", "quality", "review_addons"}
    for screen in video_selfshot2.SCREEN_PARENTS:
        model = video_selfshot2.screen_model(screen, draft)
        for callback in _callbacks(model):
            assert video_selfshot2.callback_allowed(screen, callback, draft) is True
            if callback in {"vproduct|selfshot_hub", "menu|main_video"}:
                continue
            parts = callback.split("|")
            assert parts[:2] == ["vproduct", "ss2"]
            assert parts[2] in service_operations | bot_operations


def test_stale_callback_check_is_read_only() -> None:
    draft = _ready_draft()
    before = deepcopy(draft)
    assert video_selfshot2.callback_allowed(
        "ratio", "vproduct|ss2|audio|music", draft
    ) is False
    assert draft == before


def test_five_suggestions_are_source_aware_and_one_horizontal_row() -> None:
    draft = _ready_draft()
    model = video_selfshot2.screen_model("suggestions", draft)
    assert [label for label, _callback in model["rows"][0]] == ["1", "2", "3", "4", "5"]
    text = model["text"]
    assert "Nguoi ao den ben trai" in text
    assert "Chai san pham mau xanh" in text
    assert "nguoi cam chai san pham" in text


def test_scene_plan_and_prompts_lock_person_object_relationship_per_scene() -> None:
    draft = _ready_draft(scene_count=3)
    assert len(draft["scene_plan"]) == 3
    assert len(draft["video_prompts"]) == 3
    assert draft["scene_plan"][0]["source_segment_start"] == 0
    assert draft["scene_plan"][-1]["source_segment_end"] == 16
    for scene, prompt in zip(draft["scene_plan"], draft["video_prompts"]):
        assert scene["person_subject_ids"] == ["person-1"]
        assert scene["object_subject_ids"] == ["object-1"]
        assert "person-object contact points" in prompt["prompt"]
        assert "no face drift" in prompt["negative_prompt"]
        assert "no product shape drift" in prompt["negative_prompt"]
        assert "no lost held object" in prompt["negative_prompt"]


def test_audio_toggle_volume_and_visual_addons_are_planning_only() -> None:
    draft = _ready_draft()
    draft["selfshot2_screen"] = "audio"
    toggled = video_selfshot2.apply_action(draft, "audio", "music")["state"]
    assert toggled["audio_plan"]["music"]["enabled"] is True
    toggled["selfshot2_screen"] = "audio"
    toggled = video_selfshot2.apply_action(toggled, "audio", "music")["state"]
    assert toggled["audio_plan"]["music"]["enabled"] is False
    toggled["audio_volume_target"] = "voice"
    toggled["selfshot2_screen"] = "volume"
    changed = video_selfshot2.apply_action(toggled, "volume_set", "200")["state"]
    assert changed["audio_plan"]["voice"]["volume"] == 200
    changed["selfshot2_screen"] = "addons"
    positioned = video_selfshot2.apply_action(
        changed, "addon_position_set", "watermark.bottom_left"
    )["state"]
    assert positioned["visual_addons"]["watermark"]["position"] == "bottom_left"
    assert positioned["provider_called"] is False
    assert positioned["job_created"] is False
    assert positioned["xu_charged"] == 0


@pytest.mark.parametrize(
    ("capabilities", "keyframes", "expected_route", "ok"),
    (
        (
            {"video_to_video", "environment_replacement", "person_identity_preservation", "object_reference", "person_object_relationship"},
            False,
            "direct_video_to_video",
            True,
        ),
        (
            {"performance_capture", "video_reference", "person_identity_preservation", "object_reference", "person_object_relationship"},
            False,
            "performance_capture_reference",
            True,
        ),
        ({"image_to_video"}, True, "controlled_keyframe_image_to_video", True),
        (set(), False, "", False),
    ),
)
def test_engine_routes_are_truthful_before_invoice(
    capabilities: set[str],
    keyframes: bool,
    expected_route: str,
    ok: bool,
) -> None:
    draft = _ready_draft()
    route = video_selfshot2.capability_route(
        capabilities=capabilities,
        subject_manifest=draft["subject_manifest"],
        direction=draft["direction_contract"],
        reference_keyframes_ready=keyframes,
    )
    assert route["ok"] is ok
    assert route["route"] == expected_route
    if expected_route == "controlled_keyframe_image_to_video":
        assert route["truth"] == "image_to_video_fallback_not_direct_v2v"


@pytest.mark.parametrize(
    ("mode", "metrics", "expected"),
    (
        ("person", {"final_mp4_valid": True, "scene_coverage_complete": True, "person_identity": True}, True),
        ("person", {"final_mp4_valid": True, "scene_coverage_complete": True}, False),
        ("object", {"final_mp4_valid": True, "scene_coverage_complete": True, "object_identity": True}, True),
        (
            "person_object",
            {
                "final_mp4_valid": True,
                "scene_coverage_complete": True,
                "person_identity": True,
                "object_identity": True,
                "person_object_relationship": True,
            },
            True,
        ),
        (
            "person_object",
            {
                "final_mp4_valid": True,
                "scene_coverage_complete": True,
                "person_identity": True,
                "object_identity": True,
            },
            False,
        ),
        ("motion_only", {"final_mp4_valid": True, "scene_coverage_complete": True}, True),
    ),
)
def test_service_continuity_is_conditional_on_selected_subjects(
    mode: str,
    metrics: dict,
    expected: bool,
) -> None:
    draft = _ready_draft(mode=mode)
    report = video_selfshot2.continuity_validation(metrics, draft["subject_manifest"])
    assert report["ok"] is expected


def _connector_job(draft: dict) -> dict:
    return {
        "product_type": video_selfshot2.JOB_TYPE,
        "scene_count": draft["scene_count"],
        "asset_pack": {
            "product_type": video_selfshot2.JOB_TYPE,
            "scene_count": draft["scene_count"],
            "subject_manifest": draft["subject_manifest"],
        },
    }


def _connector_result(path: Path, *, scene_count: int) -> dict:
    path.write_bytes(b"mock-final-mp4")
    return {
        "final_video_path": str(path),
        "output_bytes": path.stat().st_size,
        "has_video": True,
        "validation_status": "candidate_mp4_valid_full",
        "concat_ready": scene_count > 1,
    }


def test_connector_requires_downloaded_scene_clips_and_explicit_continuity_evidence(
    tmp_path: Path,
) -> None:
    draft = _ready_draft(scene_count=2)
    job = _connector_job(draft)
    output = _connector_result(tmp_path / "final.mp4", scene_count=2)
    transport_only = video_real_render_connector.selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[
            {"scene_index": 1, "status": "success", "result_url_valid": True},
            {"scene_index": 2, "status": "completed", "result_url_valid": True},
        ],
        debug_results=[
            {"scene_index": 1, "provider_task_id": "task-1", "result_url_present": True},
            {"scene_index": 2, "provider_task_id": "task-2", "result_url_present": True},
        ],
    )
    assert transport_only["ok"] is False
    assert transport_only["blocker"] == "selfshot2_scene_coverage_incomplete"

    passed = video_real_render_connector.selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[
            {"scene_index": 1, "status": "downloaded", "clip_valid": True},
            {"scene_index": 2, "status": "downloaded", "clip_valid": True},
        ],
        debug_results=[
            {
                "scene_index": 1,
                "continuity_evidence": {
                    "person_identity_preserved": True,
                    "object_identity_preserved": True,
                    "person_object_relationship_preserved": True,
                },
            },
            {
                "scene_index": 2,
                "continuity_evidence": {
                    "person_identity_preserved": "passed",
                    "object_identity_preserved": "preserved",
                    "person_object_relationship_preserved": "valid",
                },
            },
        ],
    )
    assert passed["ok"] is True
    assert passed["continuity_evidence_scene_indexes"] == [1, 2]


def test_delivery_and_charge_require_valid_mp4_continuity_and_real_message_id() -> None:
    draft = _ready_draft()
    artifact = {
        "final_mp4_valid": True,
        "bytes": 4096,
        "duration_seconds": 16,
        "mime_type": "video/mp4",
    }
    continuity = {
        "final_mp4_valid": True,
        "scene_coverage_complete": True,
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }
    with pytest.raises(ValueError, match="valid_delivery_receipt_required"):
        video_selfshot2.record_delivery(
            draft,
            message_id=0,
            receipt_key="job:1",
            artifact=artifact,
            continuity_metrics=continuity,
        )
    with pytest.raises(ValueError, match="person_object_relationship"):
        video_selfshot2.record_delivery(
            draft,
            message_id=99,
            receipt_key="job:1",
            artifact=artifact,
            continuity_metrics={**continuity, "person_object_relationship": False},
        )
    delivered = video_selfshot2.record_delivery(
        draft,
        message_id=99,
        receipt_key="job:1",
        artifact=artifact,
        continuity_metrics=continuity,
    )
    assert video_selfshot2.charge_allowed(delivered) is True
    assert video_selfshot2.record_delivery(
        delivered,
        message_id=99,
        receipt_key="job:1",
        artifact=artifact,
        continuity_metrics=continuity,
    ) == delivered


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


def test_worker_materializes_selfshot2_source_inside_disposable_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = []
    monkeypatch.setattr(remote_worker, "endpoint", lambda path: f"https://railway.invalid{path}")
    monkeypatch.setattr(remote_worker, "auth_headers", lambda _body: {"Authorization": "Bearer worker"})

    def fake_urlopen(request, timeout):
        observations.append((request.full_url, timeout))
        return _FakeDownloadResponse(b"source-video-bytes")

    monkeypatch.setattr(remote_worker.urllib.request, "urlopen", fake_urlopen)
    job = {"job_id": "42", "product_type": video_selfshot2.JOB_TYPE}
    path = Path(remote_worker.download_selfshot2_source_video(job, str(tmp_path))).resolve()
    assert path.parent == tmp_path.resolve()
    assert path.read_bytes() == b"source-video-bytes"
    assert job["source_video_local_path"] == str(path)
    assert observations == [("https://railway.invalid/api/v1/worker/jobs/42/source-video", 120)]


def test_bot_has_one_selfshot2_owner_no_generic_x_and_delivery_gate() -> None:
    start = BOT_SOURCE.index('if action == "ss2":')
    end = BOT_SOURCE.index('if action == "ss3":', start)
    block = BOT_SOURCE[start:end]
    assert BOT_SOURCE.count('if action == "ss2":') == 1
    assert "Có lỗi khi xử lý lệnh" not in block
    assert "callback_allowed" in block
    assert "return await video_selfshot2_render(query, uid, current_screen" in block
    finish = block[block.index('if operation == "finish":'):]
    assert 'return await video_tail9_render(query, uid, context, "addon")' in finish
    assert "selfshot2_continuity_validation_required" in BOT_SOURCE
    assert "continuity_validation_passed" in BOT_SOURCE
    assert '@fastapi_app.get("/api/v1/worker/jobs/{job_id}/source-video")' in BOT_SOURCE


def test_no_real_provider_or_wallet_api_is_called_by_this_test_module() -> None:
    source = Path(__file__).read_text(encoding="utf-8").lower()
    assert "requests" + "." not in source
    assert "httpx" + "." not in source
    assert "shopai" + "key.com" not in source
    assert "key4u" + ".shop" not in source
    assert "wallet" + "_debit" not in source
