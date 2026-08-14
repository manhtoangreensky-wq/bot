from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot as bot_runtime
from services import video_idea_catalog, video_profile_catalog, video_selfshotflow4, video_tail9


def _state(flow: str) -> dict:
    return {
        video_selfshotflow4.FLOW_FLAGS[flow]: True,
        video_selfshotflow4.FLOW_SCREEN_KEYS[flow]: "segment",
        "owner": f"selfshot{flow[-1]}",
        "session_id": f"{flow}-session",
        "revision": 3,
        "source_revision": 1,
        "source_asset": {
            "file_id": f"{flow}-video",
            "file_unique_id": f"{flow}-unique",
            "duration_seconds": 18,
            "width": 1080,
            "height": 1920,
            "audio_streams": 1,
        },
        "source_video_id": f"{flow}-video",
        "source_video_hash": f"{flow}-hash",
        "source_analysis": {
            "analysis_status": "ready",
            "analysis_revision": 1,
            "source_hash": f"{flow}-hash",
            "duration_seconds": 18,
            "width": 1080,
            "height": 1920,
            "audio_manifest": {"stream_count": 1},
            "person_tracks": [
                {
                    "subject_id": "person-1",
                    "subject_type": "person",
                    "label": "Người 1",
                    "description": "Người 1",
                    "appearance_start_seconds": 0,
                    "appearance_end_seconds": 18,
                    "confidence": 0.94,
                }
            ],
            "object_tracks": [
                {
                    "subject_id": "object-1",
                    "subject_type": "object",
                    "label": "Vật thể 1",
                    "description": "Vật thể 1",
                    "appearance_start_seconds": 1,
                    "appearance_end_seconds": 18,
                    "confidence": 0.82,
                }
            ],
            "pet_tracks": [
                {
                    "subject_id": "pet-1",
                    "subject_type": "pet",
                    "label": "Thú cưng 1",
                    "description": "Thú cưng 1",
                    "appearance_start_seconds": 2,
                    "appearance_end_seconds": 17,
                    "confidence": 0.86,
                }
            ],
            "product_tracks": [],
            "interaction_graph": [
                {
                    "person_id": "person-1",
                    "object_id": "object-1",
                    "relationship_type": "holding",
                }
            ],
            "motion_summary": "Chủ thể di chuyển từ trái sang phải",
            "camera_summary": "Camera cầm tay ổn định",
            "source_reference_frames": [
                {"timestamp_seconds": 0, "frame_index": 0},
                {"timestamp_seconds": 9, "frame_index": 270},
            ],
            "main_actions": ["đi bộ và cầm sản phẩm"],
        },
        "source_ratio": "9:16",
    }


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_segment_persists_exact_seconds_revision_and_pending_analysis(flow: str):
    result = video_selfshotflow4.apply_action(flow, _state(flow), "c4segment", "whole")
    state = result["state"]
    assert result["screen"] == "analysis"
    assert state["selected_start_seconds"] == 0
    assert state["selected_end_seconds"] == 18
    assert state["selected_duration"] == 18
    assert state["source_duration"] == 18
    assert state["source_has_audio"] is True
    assert state["source_ratio"] == "9:16"
    assert state["source_revision"] == 1
    assert state["analysis_status"] == "pending"
    if flow == "ss2":
        assert state["scene_count"] == 3
        assert "scene_count_deferred_to_quality" not in state
    else:
        assert "scene_count" not in state
        assert state["scene_count_deferred_to_quality"] is True

    custom = video_selfshotflow4.apply_text(flow, _state(flow), "segment", "2-12")["state"]
    assert custom["selected_start_seconds"] == 2
    assert custom["selected_end_seconds"] == 12
    assert custom["selected_duration"] == 10
    assert custom["analysis_status"] == "pending"
    if flow == "ss2":
        assert custom["scene_count"] == 2
    else:
        assert "scene_count" not in custom
        assert custom["scene_count_deferred_to_quality"] is True


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
@pytest.mark.parametrize("value", ["-1-5", "5-5", "12-2", "2-25", "khong-hop-le"])
def test_custom_segment_rejects_invalid_or_out_of_range_times(flow: str, value: str):
    with pytest.raises(ValueError):
        video_selfshotflow4.apply_text(flow, _state(flow), "segment", value)


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_reselecting_segment_clears_every_downstream_branch(flow: str):
    state = video_selfshotflow4.apply_action(flow, _state(flow), "c4segment", "whole")["state"]
    state.update({
        "subject_manifest": {"selected_ids": ["person-1"]},
        "selected_subject_ids": ["person-1"],
        "identity_lock": {"enabled": True},
        "relationship_lock": {"enabled": True},
        "selected_content": {"id": "old-content", "title": "Nội dung cũ"},
        "content_source": "idea_catalog",
        "idea_id": "old-idea",
        "selected_prompt": "Prompt cũ",
        "selected_prompt_text": "Prompt cũ",
        "scene_plan": [{"scene_index": 1}],
        "video_prompts": [{"scene_index": 1, "prompt": "Cũ"}],
        "video_tail9": {"status_stage": "invoice"},
    })

    changed = video_selfshotflow4.apply_text(flow, state, "segment", "3-13")["state"]

    assert changed["session_id"] == state["session_id"]
    assert changed["owner"] == state["owner"]
    assert changed["source_video_id"] == state["source_video_id"]
    assert changed["selected_start_seconds"] == 3
    assert changed["selected_end_seconds"] == 13
    assert changed["analysis_status"] == "pending"
    for field in (
        "subject_manifest", "selected_subject_ids", "identity_lock", "relationship_lock",
        "selected_content", "content_source", "idea_id", "selected_prompt",
        "selected_prompt_text", "scene_plan", "video_prompts", "video_tail9",
    ):
        assert field not in changed


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_new_source_reset_keeps_product_session_and_removes_old_segment_state(flow: str):
    state = video_selfshotflow4.apply_action(flow, _state(flow), "c4segment", "whole")["state"]
    state.update({
        "subject_manifest": {"selected_ids": ["person-1"]},
        "selected_content": {"id": "old-content"},
        "selected_prompt": "Prompt cũ",
        "video_tail9": {"status_stage": "invoice"},
    })

    reset = video_selfshotflow4.reset_for_new_source(flow, state)

    assert reset["session_id"] == state["session_id"]
    assert reset["owner"] == state["owner"]
    assert reset["source_revision"] == state["source_revision"]
    assert reset[video_selfshotflow4.FLOW_FLAGS[flow]] is True
    assert reset[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] == "segment"
    assert reset["analysis_status"] == "awaiting_segment"
    for field in (
        "source_segment", "selected_start_seconds", "selected_end_seconds", "selected_duration",
        "analysis_signature",
    ):
        assert field not in reset
    for field in ("subject_manifest", "selected_content", "selected_prompt", "video_tail9"):
        assert not reset.get(field)


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_segment_preview_and_subject_analysis_have_exact_return_owner(flow: str):
    state = video_selfshotflow4.apply_action(flow, _state(flow), "c4segment", "whole")["state"]
    state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "segment"
    segment_model = video_selfshotflow4.screen_model(flow, "segment", state)
    assert segment_model["rows"][-1][0][1] == f"vproduct|{flow}|c4upload"
    upload = video_selfshotflow4.apply_action(flow, state, "c4upload")
    assert upload["pending_media"] == "source_upload"
    preview = video_selfshotflow4.apply_action(flow, state, "c4segment", "preview")
    assert preview["screen"] == "segment_preview"
    preview_model = video_selfshotflow4.screen_model(flow, "segment_preview", preview["state"])
    assert preview_model["rows"][-1][0][1] == f"vproduct|{flow}|c4show|segment"

    subject = dict(state)
    subject[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "subject"
    analysis = video_selfshotflow4.apply_action(flow, subject, "c4show", "analysis")
    assert analysis["screen"] == "analysis"
    analysis_model = video_selfshotflow4.screen_model(flow, "analysis", analysis["state"])
    assert analysis_model["rows"][-1][0][1] == f"vproduct|{flow}|c4show|subject"


def test_local_analysis_normalizes_real_observations_without_provider_calls():
    local = importlib.import_module("services.video_selfshot_local_analysis")
    observations = [
        {
            "timestamp_seconds": 0,
            "frame_index": 0,
            "width": 640,
            "height": 360,
            "detections": [
                {"kind": "person", "bbox": [40, 35, 130, 280], "confidence": 0.94, "face_detected": True},
                {"kind": "object", "bbox": [145, 145, 75, 70], "confidence": 0.81},
                {"kind": "pet", "bbox": [390, 185, 105, 120], "confidence": 0.87},
            ],
            "camera_shift": [0.2, 0.1],
            "motion_score": 0.14,
        },
        {
            "timestamp_seconds": 4,
            "frame_index": 120,
            "width": 640,
            "height": 360,
            "detections": [
                {"kind": "person", "bbox": [50, 35, 130, 280], "confidence": 0.92, "face_detected": True},
                {"kind": "object", "bbox": [155, 145, 75, 70], "confidence": 0.80},
                {"kind": "pet", "bbox": [400, 185, 105, 120], "confidence": 0.85},
            ],
            "camera_shift": [0.4, 0.2],
            "motion_score": 0.18,
        },
    ]
    report = local.analyze_observations(observations, duration_seconds=8, source_hash="source-hash")
    assert report["analysis_status"] == "ready"
    assert len(report["person_tracks"]) == 1
    assert len(report["object_tracks"]) == 1
    assert len(report["pet_tracks"]) == 1
    assert len(report["subject_candidates"]) == 3
    assert report["relationship_candidates"]
    assert report["motion_summary"]
    assert report["camera_summary"]
    assert report["track_confidence"] > 0
    assert report["source_reference_frames"]
    assert report["provider_calls"] == 0
    assert report["job_created"] is False
    assert report["outbox_created"] is False

    empty = local.analyze_observations([], duration_seconds=8, source_hash="empty-source")
    assert empty["analysis_status"] == "ready_no_tracks"
    assert empty["subject_candidates"] == []
    assert empty["provider_calls"] == 0


def test_local_analyzer_reads_a_real_video_file(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    path = tmp_path / "moving-object.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 12.0, (320, 240))
    assert writer.isOpened()
    try:
        for index in range(30):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            x = 30 + index * 5
            cv2.rectangle(frame, (x, 90), (x + 45, 165), (255, 255, 255), -1)
            writer.write(frame)
    finally:
        writer.release()

    local = importlib.import_module("services.video_selfshot_local_analysis")
    report = local.analyze_video_file(
        str(path),
        start_seconds=0,
        end_seconds=2,
        source_hash="real-fixture",
        analysis_revision=2,
        sample_limit=8,
    )
    assert report["analysis_status"] == "ready"
    assert report["analysis_revision"] == 2
    assert report["sample_count"] >= 4
    assert report["object_tracks"]
    assert report["source_reference_frames"]
    assert report["provider_calls"] == 0


def test_bot_selfshot_inspector_uses_exact_selected_segment(monkeypatch):
    captured = {}

    class TelegramFile:
        async def download_to_drive(self, *, custom_path):
            Path(custom_path).write_bytes(b"selfshot-fixture")

    class TelegramBot:
        async def get_file(self, file_id):
            assert file_id == "ss2-video"
            return TelegramFile()

    monkeypatch.setattr(bot_runtime.video_local_validation, "probe_video_file", lambda _path: {
        "ok": True,
        "duration": 18,
        "width": 1080,
        "height": 1920,
        "audio_stream_count": 1,
        "format_name": "mov,mp4",
        "video_codec": "h264",
    })

    def analyze(_path, **kwargs):
        captured.update(kwargs)
        return {
            "analysis_status": "ready_no_tracks",
            "analysis_revision": kwargs["analysis_revision"],
            "subject_candidates": [],
            "relationship_candidates": [],
            "source_reference_frames": [],
            "provider_calls": 0,
        }

    monkeypatch.setattr(bot_runtime.video_selfshot_local_analysis, "analyze_video_file", analyze)
    state = _state("ss2")
    state.update({
        "source_segment": {
            "start_ms": 2000,
            "end_ms": 12000,
            "duration_ms": 10000,
            "start_seconds": 2,
            "end_seconds": 12,
            "duration_seconds": 10,
        },
        "selected_start_seconds": 2,
        "selected_end_seconds": 12,
        "selected_duration": 10,
        "analysis_revision": 4,
    })
    result = asyncio.run(bot_runtime.inspect_selfshot_source(SimpleNamespace(bot=TelegramBot()), state, "ss2"))
    assert result["ok"] is True
    assert captured["start_seconds"] == 2
    assert captured["end_seconds"] == 12
    assert captured["analysis_revision"] == 5
    assert len(captured["source_hash"]) == 64
    assert captured["source_hash"] == result["source_video_hash"]


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_stale_local_analysis_cannot_overwrite_a_new_segment(monkeypatch, flow: str):
    original = video_selfshotflow4.apply_action(flow, _state(flow), "c4segment", "whole")["state"]
    latest = deepcopy(original)
    latest[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "segment"
    latest["source_segment"] = {
        "start_ms": 4000,
        "end_ms": 14000,
        "duration_ms": 10000,
        "start_seconds": 4,
        "end_seconds": 14,
        "duration_seconds": 10,
    }
    latest["analysis_signature"] = f"{latest['source_video_hash']}:4000:14000:{latest['source_revision']}"
    latest["analysis_status"] = "pending"

    saved = []
    rendered = {}

    def canonical_draft(_flow, session=None):
        return deepcopy(dict((session or {}).get("draft") or {}))

    async def inspect(_context, _state, _flow):
        return {
            "ok": True,
            "source_video_hash": "stale-analysis-hash",
            "analysis": {
                "analysis_status": "ready",
                "analysis_revision": 99,
                "subject_candidates": [{"subject_id": "stale-subject"}],
            },
        }

    async def render(_target, _user_id, screen, *, draft=None):
        rendered.update({"screen": screen, "draft": deepcopy(draft or {})})
        return "latest-render"

    monkeypatch.setattr(bot_runtime, "video_selfshotflow4_draft", canonical_draft)
    monkeypatch.setattr(
        bot_runtime,
        "save_video_selfshotflow4_draft",
        lambda _user_id, _flow, draft, **_kwargs: saved.append(deepcopy(draft)) or draft,
    )
    monkeypatch.setattr(bot_runtime, "inspect_selfshot_source", inspect)
    monkeypatch.setattr(bot_runtime, "get_video_session", lambda _user_id: {"draft": deepcopy(latest)})
    monkeypatch.setattr(
        bot_runtime,
        "video_selfshot2_render" if flow == "ss2" else "video_selfshot3_render",
        render,
    )

    result = asyncio.run(
        bot_runtime.video_selfshotflow4_handle_result(
            SimpleNamespace(),
            919001,
            SimpleNamespace(),
            flow,
            {"state": original, "screen": "analysis"},
        )
    )

    assert result == "latest-render"
    assert rendered["screen"] == "segment"
    assert rendered["draft"]["analysis_signature"] == latest["analysis_signature"]
    assert rendered["draft"]["source_segment"] == latest["source_segment"]
    assert "stale-subject" not in str(rendered["draft"])
    assert all("stale-subject" not in str(item) for item in saved)


@pytest.mark.parametrize(
    ("flow", "product", "owner", "step"),
    [
        ("ss2", "self_shot_scene_change", "selfshot2", "awaiting_selfshot2_video"),
        ("ss3", "self_shot_cinematic_transform", "selfshot3", "awaiting_selfshot3_video"),
    ],
)
def test_back_to_upload_keeps_exact_media_owner(monkeypatch, flow: str, product: str, owner: str, step: str):
    captured = {}

    monkeypatch.setattr(bot_runtime, "save_video_selfshotflow4_draft", lambda *_args, **_kwargs: {})

    def session_step(_user_id, current_step, **kwargs):
        captured["step"] = current_step
        captured["step_fields"] = kwargs
        return {}

    monkeypatch.setattr(bot_runtime, "task3d_session_step", session_step)
    monkeypatch.setattr(bot_runtime, "save_video_session", lambda _user_id, session: captured.update(session=session) or session)

    async def render(_target, text, **kwargs):
        captured["text"] = text
        captured["markup"] = kwargs.get("reply_markup")
        return True

    monkeypatch.setattr(bot_runtime, "safe_edit_or_send", render)
    previous = _state(flow)
    previous.update({
        "source_segment": {"start_ms": 0, "end_ms": 18000, "duration_ms": 18000},
        "subject_manifest": {"selected_ids": ["person-1"]},
        "selected_content": {"id": "old-content"},
        "selected_prompt": "Prompt cũ",
        "video_tail9": {"status_stage": "invoice"},
    })
    result = asyncio.run(bot_runtime.video_selfshotflow4_request_source(object(), 7, flow, previous))
    assert result is True
    assert captured["step"] == step
    assert captured["session"]["product_id"] == product
    assert captured["session"]["flow_owner"] == owner
    assert captured["session"]["media_owner"] == owner
    assert captured["session"]["selfshotflow4_owner"] == flow
    assert captured["session"]["awaiting_media"] is True
    assert captured["session"]["provider_called"] is False
    assert captured["session"]["job_created"] is False
    assert captured["session"]["outbox_created"] is False
    assert captured["session"]["draft"]["session_id"] == previous["session_id"]
    assert captured["session"]["draft"]["source_video_id"] == previous["source_video_id"]
    for field in ("source_segment", "selected_content", "selected_prompt", "video_tail9"):
        assert captured["session"]["draft"].get(field) == previous[field]


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_subject_screen_shows_typed_candidates_and_multiple_selection(flow: str):
    state = _state(flow)
    state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "subject"
    model = video_selfshotflow4.screen_model(flow, "subject", state)
    labels = [label for row in model["rows"] for label, _callback in row]
    assert any(label.startswith("👤 Người 1") and "0–18s" in label for label in labels)
    assert any(label.startswith("📦 Vật thể 1") and "1–18s" in label for label in labels)
    assert any(label.startswith("🐾 Thú cưng 1") and "2–17s" in label for label in labels)
    assert "➕ Giữ nhiều chủ thể" in labels
    assert model["rows"][-1][0][1] == f"vproduct|{flow}|c4show|segment"

    opened = video_selfshotflow4.apply_action(flow, state, "c4subject", "multiple")
    assert opened["screen"] == "subject_multiple"
    selected = video_selfshotflow4.apply_action(flow, opened["state"], "c4multi", "person-1")["state"]
    selected = video_selfshotflow4.apply_action(flow, selected, "c4multi", "object-1")["state"]
    done = video_selfshotflow4.apply_action(flow, selected, "c4multi", "done")
    assert done["screen"] == "content_source"
    assert done["state"]["selected_subject_ids"] == ["person-1", "object-1"]
    assert done["state"]["selected_subject_type"] == "multiple"
    assert done["state"]["identity_lock"]["enabled"] is True
    assert done["state"]["relationship_lock"]["enabled"] is True
    assert done["state"]["appearance_lock"]["enabled"] is True
    assert done["state"]["motion_lock"]["enabled"] is True
    assert done["state"]["source_reference_frames"]


def test_selfshot_uses_exact_canonical_32_profiles_and_16_72_idea_catalog():
    profiles = video_selfshotflow4.content_profiles()
    assert len(profiles) == len(video_profile_catalog.PROFILE_SEEDS) == 32
    assert [item["profile_key"] for item in profiles] == [item["profile_key"] for item in video_profile_catalog.PROFILE_SEEDS]

    groups = video_selfshotflow4.idea_groups()
    assert len(groups) == video_idea_catalog.catalog_status()["categories"] == 16
    all_ideas = [idea for group in groups for idea in video_selfshotflow4.ideas_for_group(group["category_id"])]
    assert len(all_ideas) == video_idea_catalog.catalog_status()["ideas"] == 72
    assert len({item["idea_id"] for item in all_ideas}) == 72


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_idea_source_has_group_then_idea_then_five_product_prompts(flow: str):
    state = _state(flow)
    state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "subject"
    state = video_selfshotflow4.apply_action(flow, state, "c4subject", "track:person-1")["state"]
    groups = video_selfshotflow4.apply_action(flow, state, "c4source", "ideas")
    assert groups["screen"] == "idea_groups"
    group_id = video_selfshotflow4.idea_groups()[0]["category_id"]
    ideas = video_selfshotflow4.apply_action(flow, groups["state"], "c4idea_group", group_id)
    assert ideas["screen"] == "ideas"
    idea_id = video_selfshotflow4.ideas_for_group(group_id)[0]["idea_id"]
    prompt = video_selfshotflow4.apply_action(flow, ideas["state"], "c4idea", idea_id)
    assert prompt["screen"] == "prompt"
    assert len(prompt["state"]["selfshotflow4_prompt_candidates"]) == 5
    assert prompt["state"]["idea_id"] == idea_id
    assert prompt["state"]["source_video_id"] == f"{flow}-video"
    assert prompt["state"]["selected_subject_ids"]
    assert video_selfshotflow4.screen_parent(flow, "prompt", prompt["state"]) == "ideas"


@pytest.mark.parametrize(
    ("flow", "required"),
    [
        ("ss2", ("giữ nguyên chủ thể", "quan hệ", "chuyển động nguồn", "đổi cảnh", "continuity", "camera")),
        ("ss3", ("giữ nguyên chủ thể", "biến đổi điện ảnh", "trang phục", "môi trường", "hiệu ứng", "timeline", "continuity")),
    ],
)
def test_five_prompts_are_product_specific(flow: str, required: tuple[str, ...]):
    state = _state(flow)
    state["selected_content"] = {"id": "demo", "title": "Quảng bá sản phẩm", "summary": "Giới thiệu sản phẩm"}
    candidates = video_selfshotflow4.prompt_candidates(flow, state)
    assert len(candidates) == 5
    for candidate in candidates:
        text = candidate["text"].lower()
        for phrase in required:
            assert phrase in text


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_refresh_replaces_all_five_prompt_variants(flow: str):
    state = _state(flow)
    state["selected_content"] = {"id": "demo", "title": "Demo", "summary": "Một câu chuyện liền mạch"}
    state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "prompt"
    first = video_selfshotflow4.apply_action(flow, state, "c4prompt", "refresh")["state"]
    first_texts = {item["text"] for item in first["selfshotflow4_prompt_candidates"]}
    second = video_selfshotflow4.apply_action(flow, first, "c4prompt", "refresh")["state"]
    second_texts = {item["text"] for item in second["selfshotflow4_prompt_candidates"]}
    assert len(first_texts) == len(second_texts) == 5
    assert first_texts.isdisjoint(second_texts)


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_selecting_a_new_prompt_invalidates_the_old_invoice_tail(flow: str):
    state = _state(flow)
    state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "subject"
    state = video_selfshotflow4.apply_action(flow, state, "c4subject", "track:person-1")["state"]
    state = video_selfshotflow4.apply_action(flow, state, "c4source", "profiles")["state"]
    profile_id = video_selfshotflow4.content_profiles()[0]["profile_key"]
    state = video_selfshotflow4.apply_action(flow, state, "c4profile", profile_id)["state"]
    state.update({
        "video_tail9": {
            "status_stage": "invoice",
            "quality_tier_id": "300",
            "package_id": "product_video_300",
            "invoice_id": "old-invoice",
        },
        "b14_quality_xu": 300,
        "video_tail_engine_route": "old-route",
        "video_tail_executor_product_type": "old-product",
    })

    result = video_selfshotflow4.apply_action(flow, state, "c4prompt", "2")

    assert result["screen"] == "tail_review"
    for field in (
        "video_tail9", "b14_quality_xu", "video_tail_engine_route",
        "video_tail_executor_product_type",
    ):
        assert field not in result["state"]
    assert result["state"]["selected_prompt_text"]
    assert result["state"]["provider_called"] is False
    assert result["state"]["job_created"] is False
    assert result["state"]["xu_charged"] == 0


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
def test_switching_content_source_clears_previous_branch_without_route_leak(flow: str):
    state = _state(flow)
    state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "content_source"
    state = video_selfshotflow4.apply_action(flow, state, "c4source", "ideas")["state"]
    group_id = video_selfshotflow4.idea_groups()[0]["category_id"]
    state = video_selfshotflow4.apply_action(flow, state, "c4idea_group", group_id)["state"]
    idea_id = video_selfshotflow4.ideas_for_group(group_id)[0]["idea_id"]
    state = video_selfshotflow4.apply_action(flow, state, "c4idea", idea_id)["state"]
    assert state["idea_id"] == idea_id

    state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "content_source"
    state = video_selfshotflow4.apply_action(flow, state, "c4source", "profiles")["state"]
    profile_id = video_selfshotflow4.content_profiles()[0]["profile_key"]
    state = video_selfshotflow4.apply_action(flow, state, "c4profile", profile_id)["state"]
    assert state["content_source"] == "content_profiles"
    assert state["content_profile_id"] == profile_id
    assert "idea_id" not in state
    assert "selected_preset" not in state
    assert state["owner"] == f"selfshot{flow[-1]}"


@pytest.mark.parametrize("flow", ["ss2", "ss3"])
@pytest.mark.parametrize("source", ["profiles", "ideas", "custom"])
def test_each_content_source_compiles_to_the_same_complete_tail_contract(flow: str, source: str):
    state = _state(flow)
    state["subject_manifest"] = {
        "selection_type": "person",
        "subjects": [state["source_analysis"]["person_tracks"][0]],
        "selected_ids": ["person-1"],
        "person_subject_ids": ["person-1"],
        "object_subject_ids": [],
        "stable_ids": True,
        "source_bound": True,
        "confirmed": True,
    }
    state = video_selfshotflow4.normalize_subject_locks(flow, state)
    state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = "content_source"
    if source == "profiles":
        state = video_selfshotflow4.apply_action(flow, state, "c4source", "profiles")["state"]
        profile_key = video_selfshotflow4.content_profiles()[0]["profile_key"]
        state = video_selfshotflow4.apply_action(flow, state, "c4profile", profile_key)["state"]
        expected_source = "content_profiles"
    elif source == "ideas":
        state = video_selfshotflow4.apply_action(flow, state, "c4source", "ideas")["state"]
        group_id = video_selfshotflow4.idea_groups()[0]["category_id"]
        state = video_selfshotflow4.apply_action(flow, state, "c4idea_group", group_id)["state"]
        idea_id = video_selfshotflow4.ideas_for_group(group_id)[0]["idea_id"]
        state = video_selfshotflow4.apply_action(flow, state, "c4idea", idea_id)["state"]
        expected_source = "idea_catalog"
    else:
        state = video_selfshotflow4.apply_action(flow, state, "c4source", "custom")["state"]
        state = video_selfshotflow4.apply_text(flow, state, "content", "Một hành trình giới thiệu sản phẩm liền mạch.")["state"]
        expected_source = "manual"

    result = video_selfshotflow4.apply_action(flow, state, "c4prompt", "1")
    assert result["screen"] == "tail_review"
    compiled = result["state"]
    assert compiled["product_type"] == video_selfshotflow4.FLOW_PRODUCT_IDS[flow]
    assert compiled["engine_route"] == video_selfshotflow4.FLOW_PRODUCT_IDS[flow]
    assert compiled["flow_owner"] == f"selfshot{flow[-1]}"
    assert compiled["content_source"] == expected_source
    assert compiled["content_mode"] in {"manual", "suggestions"}
    assert compiled["content_choice"]
    assert compiled["per_scene_content"]
    assert compiled["selected_prompt_text"]
    assert compiled["selected_prompt_revision"] >= 1
    assert compiled["plan_status"] == "ready"
    assert compiled["provider_called"] is False
    assert compiled["job_created"] is False
    assert compiled["outbox_created"] is False
    assert compiled["xu_charged"] == 0

    tail = video_tail9.new_state(
        product_type=compiled["product_type"],
        session_id=compiled["session_id"],
        plan_revision=compiled["revision"],
        scene_count=compiled["scene_count"],
        ratio=compiled["aspect_ratio"],
        source_asset_ids=[compiled["source_video_id"]],
    )
    tail = video_tail9.apply_content_contract(tail, compiled)
    assert tail["content_source"] == expected_source
    assert tail["content_mode"] in {"manual", "suggestions"}
    assert tail["scene_content"]
    assert tail["selected_prompt"] == compiled["selected_prompt_text"]


def test_compile_outputs_and_reviews_are_separate_for_both_products():
    ss2 = _state("ss2")
    ss2["subject_manifest"] = {"subjects": [ss2["source_analysis"]["person_tracks"][0]], "selected_ids": ["person-1"]}
    ss2["selected_content"] = {"id": "demo", "title": "Demo", "summary": "Đổi ba bối cảnh"}
    ss2["source_segment"] = {"start_ms": 0, "end_ms": 18000, "duration_ms": 18000}
    ss2 = video_selfshotflow4.normalize_subject_locks("ss2", ss2)
    compiled2 = video_selfshotflow4.compile_selfshot2_content(ss2)
    for field in ("scene_change_plan", "identity_lock", "relationship_lock", "source_motion_map", "per_scene_background", "continuity_rules"):
        assert compiled2[field]
    assert "Review — Tự quay & đổi cảnh AI" in video_selfshotflow4.review_text("ss2", compiled2)

    ss3 = _state("ss3")
    ss3["subject_manifest"] = {"subjects": [ss3["source_analysis"]["person_tracks"][0]], "selected_ids": ["person-1"]}
    ss3["selected_content"] = {"id": "demo", "title": "Fantasy", "summary": "Biến đổi fantasy"}
    ss3["source_segment"] = {"start_ms": 0, "end_ms": 18000, "duration_ms": 18000}
    ss3 = video_selfshotflow4.normalize_subject_locks("ss3", ss3)
    compiled3 = video_selfshotflow4.compile_selfshot3_content(ss3)
    for field in ("cinematic_timeline", "identity_lock", "environment_transformation", "wardrobe_transformation", "lighting_transformation", "effects_plan", "continuity_rules"):
        assert compiled3[field]
    assert "Review — Biến đổi điện ảnh" in video_selfshotflow4.review_text("ss3", compiled3)
    assert compiled2["engine_route"] != compiled3["engine_route"]


@pytest.mark.parametrize("product", ["self_shot_scene_change", "self_shot_cinematic_transform"])
def test_commercial_tail_reaches_invoice_confirm_and_distinct_status_contract(product: str):
    tail = video_tail9.new_state(
        product_type=product,
        session_id=f"{product}-session",
        scene_count=1,
        ratio="9:16",
        source_asset_ids=["source-video"],
    )
    tail = video_tail9.apply_content_contract(tail, {
        "content_source": "manual",
        "content_mode": "manual",
        "selected_prompt_text": "Prompt nguồn hoàn chỉnh",
        "per_scene_content": [{"scene_index": 1, "summary": "Nội dung hoàn chỉnh"}],
        "plan_approved": True,
        "plan_status": "ready",
    })
    tail = video_tail9.mark_audio_complete(tail, skipped=True)
    tail = video_tail9.mark_branding_skipped(tail)
    tail = video_tail9.prepare_summary(tail)
    assert tail["summary_status"] == "ready"
    tail = video_tail9.select_package(
        tail,
        quality_tier_id="300",
        package_id="product_video_300",
        pricing_snapshot={"total_xu": 300, "price_xu": 300},
        capability_snapshot={"ok": True, "engine_route": product},
    )
    assert video_tail9.invoice_allowed(tail) == (True, "ok")
    confirmed, created = video_tail9.confirm_once(tail, "confirm-token")
    assert created is True
    assert confirmed["status_stage"] == "confirmed"
    assert confirmed["job_id"] == ""
    assert confirmed["delivery_message_id"] == ""
    stages = video_tail9.status_contract(product)["product_stages"]
    if product == "self_shot_scene_change":
        assert stages == (
            "source_received", "subject_analyzed", "planning_scene_change", "changing_each_scene",
            "checking_continuity", "composing", "validating_mp4", "delivering",
        )
    else:
        assert stages == (
            "source_received", "subject_analyzed", "planning_cinematic_timeline", "transforming_environment",
            "transforming_wardrobe_effects", "checking_continuity", "composing", "validating_mp4", "delivering",
        )


@pytest.mark.parametrize(
    ("product", "expected"),
    [
        (
            "self_shot_scene_change",
            ("Nhận video", "Phân tích chủ thể", "Lập kế hoạch đổi cảnh", "Biến đổi từng cảnh", "Kiểm tra continuity", "Ghép video", "Kiểm tra MP4", "Gửi kết quả"),
        ),
        (
            "self_shot_cinematic_transform",
            ("Nhận video", "Phân tích chủ thể", "Lập timeline điện ảnh", "Biến đổi môi trường", "Biến đổi trang phục/hiệu ứng", "Kiểm tra continuity", "Ghép video", "Kiểm tra MP4", "Gửi kết quả"),
        ),
    ],
)
def test_public_status_panel_uses_exact_selfshot_stages(product: str, expected: tuple[str, ...]):
    rows = bot_runtime.video_b14_status_step_rows("queued", 0, product_type=product)
    assert tuple(label for _icon, label in rows) == expected
    assert tuple(icon for icon, _label in rows[:3]) == ("✅", "✅", "⏳")


def test_golden_flow_callbacks_are_scoped_short_and_back_exact():
    assert video_selfshotflow4.SELF_SHOT_2_GOLDEN_FLOW[-6:] == (
        "addon", "review", "quality", "invoice", "confirm", "status"
    )
    assert video_selfshotflow4.SELF_SHOT_3_GOLDEN_FLOW[-6:] == video_selfshotflow4.SELF_SHOT_2_GOLDEN_FLOW[-6:]
    assert video_selfshotflow4.SELF_SHOT_2_GOLDEN_FLOW != video_selfshotflow4.SELF_SHOT_3_GOLDEN_FLOW

    for flow in ("ss2", "ss3"):
        state = _state(flow)
        for screen in video_selfshotflow4.FLOW_SCREENS[flow]:
            state[video_selfshotflow4.FLOW_SCREEN_KEYS[flow]] = screen
            model = video_selfshotflow4.screen_model(flow, screen, state)
            for row in model["rows"]:
                for _label, callback_data in row:
                    assert len(callback_data.encode("utf-8")) <= 64
                    if callback_data.startswith("vproduct|ss"):
                        assert callback_data.startswith(f"vproduct|{flow}|")


def test_bot_runs_selfshot_only_local_analysis_after_segment_selection():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "async def inspect_selfshot_source" in source
    handler = source[source.index("async def video_selfshotflow4_handle_result"):source.index("async def video_selfshotflow4_handle_pending_text")]
    assert "inspect_selfshot_source" in handler
    assert "analysis_status" in handler
    assert "video_provider" not in handler.lower()
    assert "call_provider" not in handler.lower()
    assert "video_selfshotflow4_request_source" in handler
    media_handler = source[
        source.index("async def handle_video_product_pending_media"):
        source.index("async def open_prompt_video_finalization_from_state")
    ]
    assert media_handler.count(
        'video_selfshotflow4.reset_for_new_source("ss2", video_selfshot2_draft(session))'
    ) == 1
    assert media_handler.count(
        'video_selfshotflow4.reset_for_new_source("ss3", video_selfshot3_draft(session))'
    ) == 1
