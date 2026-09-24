from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services import video_selfshot2
from services.video_ai_edit_provider import (
    AiEditProviderConfig,
    PUBLIC_FINAL_CONFIRM_SOURCE,
    parse_provider_payload,
    poll_video_edit,
    submit_video_edit,
)
from services.video_real_render_connector import (
    _selfshot2_continuity_evidence_from_payload,
    selfshot2_continuity_validation,
)


class MockHttpResponse:
    def __init__(self, body: dict[str, Any], status: int = 200) -> None:
        self.status = status
        self.code = status
        self._raw = json.dumps(body).encode("utf-8")

    def read(self, *args, **kwargs) -> bytes:
        return self._raw


def _valid_config() -> AiEditProviderConfig:
    return AiEditProviderConfig(
        provider_name="key4u_video",
        enabled=True,
        submit_url="https://api.key4u.vn/v1/video/generations",
        poll_url="https://api.key4u.vn/v1/video/generations/{task_id}",
        auth_header_name="Authorization",
        auth_header_value="Bearer valid-token-secret",
        model="kling-video",
        interface="video_to_video_multipart",
        capabilities=("video_to_video",),
    )


def _ready_job(scene_count: int = 1) -> dict[str, Any]:
    return {
        "product_type": "self_shot_scene_change",
        "scene_count": scene_count,
        "asset_pack": {
            "product_type": "self_shot_scene_change",
            "scene_count": scene_count,
            "subject_manifest": {
                "person_subject_ids": ["person-1"],
                "object_subject_ids": ["object-1"],
            },
        },
    }


def _ready_output(mp4_path: Path, scene_count: int = 1) -> dict[str, Any]:
    mp4_path.write_bytes(b"dummy-valid-mp4-data")
    return {
        "final_video_path": str(mp4_path),
        "output_bytes": mp4_path.stat().st_size,
        "has_video": True,
        "validation_status": "candidate_mp4_valid_full",
        "concat_ready": scene_count > 1 or scene_count == 1,
    }


def test_first_red_normalization_preserves_continuity_evidence() -> None:
    """1. Normalization preserves continuity evidence containers and extracts valid canonical evidence."""
    raw_payload = {
        "code": "success",
        "data": {
            "task_id": "task-test-01",
            "status": "succeeded",
            "video_url": "https://example.com/v.mp4",
            "continuity_evidence": {
                "person_identity": "pass",
                "object_identity": "pass",
                "person_object_relationship": "pass",
            },
        },
    }

    # Continuity is present in raw provider payload
    assert "continuity_evidence" in raw_payload["data"]

    parsed = parse_provider_payload(raw_payload)

    # After normalization, continuity container must survive
    assert "continuity_evidence" in parsed, "continuity_evidence was discarded by parse_provider_payload"
    assert parsed["continuity_evidence"] == {
        "person_identity": "pass",
        "object_identity": "pass",
        "person_object_relationship": "pass",
    }

    # Extractor extracts canonical evidence
    evidence = _selfshot2_continuity_evidence_from_payload(parsed)
    assert evidence == {
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }


def test_submit_video_edit_propagates_continuity_evidence(tmp_path: Path) -> None:
    """2. submit_video_edit preserves continuity evidence when present in submit response."""
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"dummy-video-data")
    config = _valid_config()

    provider_response = {
        "code": "success",
        "data": {
            "task_id": "submit-task-123",
            "status": "completed",
            "result_url": "https://example.com/final.mp4",
            "continuity_evidence": {
                "person_identity": "true",
                "object_identity": "true",
                "person_object_relationship": "true",
            },
        },
    }

    def fake_opener(req, timeout=None):
        return MockHttpResponse(provider_response, 200)

    result = submit_video_edit(
        config,
        source_video_path=str(source_file),
        prompt="Self-shot scene",
        negative_prompt="blurry",
        aspect_ratio="9:16",
        duration_seconds=5,
        job_id="job-ss2-submit",
        submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
        public_user_confirmed=True,
        opener=fake_opener,
    )

    assert result["provider_task_id"] == "submit-task-123"
    assert result["status"] == "completed"
    assert result["result_url_present"] is True
    assert result["provider_name"] == "key4u_video"
    assert result["model"] == "kling-video"
    assert "continuity_evidence" in result

    extracted = _selfshot2_continuity_evidence_from_payload(result)
    assert extracted["person_identity"] is True
    assert extracted["object_identity"] is True
    assert extracted["person_object_relationship"] is True


def test_poll_video_edit_propagates_continuity_evidence() -> None:
    """3. poll_video_edit preserves continuity evidence when polling completed task."""
    config = _valid_config()

    poll_response = {
        "code": "success",
        "data": {
            "task_id": "poll-task-456",
            "status": "succeeded",
            "video_url": "https://example.com/polled_output.mp4",
            "continuity_evidence": {
                "person_identity_preserved": "valid",
                "object_identity_preserved": "valid",
                "person_object_relationship_preserved": "valid",
            },
        },
    }

    def fake_opener(req, timeout=None):
        return MockHttpResponse(poll_response, 200)

    result = poll_video_edit(config, "poll-task-456", opener=fake_opener)

    assert result["provider_task_id"] == "poll-task-456"
    assert result["status"] == "completed"
    assert result["result_url_present"] is True
    assert "continuity_evidence" in result

    extracted = _selfshot2_continuity_evidence_from_payload(result)
    assert extracted["person_identity"] is True
    assert extracted["object_identity"] is True
    assert extracted["person_object_relationship"] is True


def test_missing_continuity_evidence_fails_closed(tmp_path: Path) -> None:
    """4. Provider returns success + video_url, but missing continuity evidence fails closed."""
    raw_payload = {
        "code": "success",
        "data": {
            "task_id": "task-no-evidence",
            "status": "succeeded",
            "video_url": "https://example.com/v.mp4",
        },
    }

    parsed = parse_provider_payload(raw_payload)
    extracted = _selfshot2_continuity_evidence_from_payload(parsed)
    assert extracted == {}

    job = _ready_job(scene_count=1)
    output = _ready_output(tmp_path / "final.mp4", scene_count=1)
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[{"scene_index": 1, "status": "downloaded", "clip_valid": True}],
        debug_results=[{"scene_index": 1, "status": "downloaded", **parsed}],
    )

    assert validation["ok"] is False
    assert validation["continuity_metadata_present"] is False
    assert validation["blocker"] == "selfshot2_person_continuity_evidence_missing"


def test_explicit_false_person_evidence_fails(tmp_path: Path) -> None:
    """5. Explicit false person_identity causes continuity validation failure."""
    raw_payload = {
        "data": {
            "task_id": "task-false-person",
            "status": "succeeded",
            "video_url": "https://example.com/v.mp4",
            "continuity_evidence": {
                "person_identity": False,
                "object_identity": True,
                "person_object_relationship": True,
            },
        }
    }
    parsed = parse_provider_payload(raw_payload)
    extracted = _selfshot2_continuity_evidence_from_payload(parsed)
    assert extracted.get("person_identity") is False

    job = _ready_job(scene_count=1)
    output = _ready_output(tmp_path / "final.mp4", scene_count=1)
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[{"scene_index": 1, "status": "downloaded", "clip_valid": True}],
        debug_results=[{"scene_index": 1, "continuity_evidence": extracted}],
    )
    assert validation["ok"] is False
    assert validation["metrics"]["person_identity"] is False
    assert validation["blocker"] == "selfshot2_person_continuity_evidence_missing"


def test_explicit_false_object_evidence_fails(tmp_path: Path) -> None:
    """6. Explicit false object_identity causes continuity validation failure."""
    raw_payload = {
        "data": {
            "task_id": "task-false-object",
            "status": "succeeded",
            "video_url": "https://example.com/v.mp4",
            "continuity_evidence": {
                "person_identity": True,
                "object_identity": False,
                "person_object_relationship": True,
            },
        }
    }
    parsed = parse_provider_payload(raw_payload)
    extracted = _selfshot2_continuity_evidence_from_payload(parsed)
    assert extracted.get("object_identity") is False

    job = _ready_job(scene_count=1)
    output = _ready_output(tmp_path / "final.mp4", scene_count=1)
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[{"scene_index": 1, "status": "downloaded", "clip_valid": True}],
        debug_results=[{"scene_index": 1, "continuity_evidence": extracted}],
    )
    assert validation["ok"] is False
    assert validation["metrics"]["object_identity"] is False
    assert validation["blocker"] == "selfshot2_object_continuity_evidence_missing"


def test_explicit_false_relationship_evidence_fails(tmp_path: Path) -> None:
    """7. Explicit false person_object_relationship causes continuity validation failure."""
    raw_payload = {
        "data": {
            "task_id": "task-false-rel",
            "status": "succeeded",
            "video_url": "https://example.com/v.mp4",
            "continuity_evidence": {
                "person_identity": True,
                "object_identity": True,
                "person_object_relationship": False,
            },
        }
    }
    parsed = parse_provider_payload(raw_payload)
    extracted = _selfshot2_continuity_evidence_from_payload(parsed)
    assert extracted.get("person_object_relationship") is False

    job = _ready_job(scene_count=1)
    output = _ready_output(tmp_path / "final.mp4", scene_count=1)
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[{"scene_index": 1, "status": "downloaded", "clip_valid": True}],
        debug_results=[{"scene_index": 1, "continuity_evidence": extracted}],
    )
    assert validation["ok"] is False
    assert validation["metrics"]["person_object_relationship"] is False
    assert validation["blocker"] == "selfshot2_relationship_continuity_evidence_missing"


def test_complete_one_scene_metadata_pass(tmp_path: Path) -> None:
    """8. Complete 1-scene evidence passes metadata contract without falsifying visual validation."""
    raw_payload = {
        "data": {
            "task_id": "task-pass-1scene",
            "status": "succeeded",
            "video_url": "https://example.com/v.mp4",
            "continuity_evidence": {
                "person_identity": "pass",
                "object_identity": "pass",
                "person_object_relationship": "pass",
            },
        }
    }
    parsed = parse_provider_payload(raw_payload)
    extracted = _selfshot2_continuity_evidence_from_payload(parsed)

    job = _ready_job(scene_count=1)
    output = _ready_output(tmp_path / "final.mp4", scene_count=1)
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[{"scene_index": 1, "status": "downloaded", "clip_valid": True}],
        debug_results=[{"scene_index": 1, "continuity_evidence": extracted}],
    )

    assert validation["ok"] is True
    assert validation["metadata_contract_pass"] is True
    assert validation["continuity_metadata_present"] is True
    assert validation["metrics"]["person_identity"] is True
    assert validation["metrics"]["object_identity"] is True
    assert validation["metrics"]["person_object_relationship"] is True
    assert validation["blocker"] == ""
    # Visual validation remains NOT_PERFORMED
    assert validation["independent_visual_validation"] == "NOT_PERFORMED"
    assert validation["independent_visual_validation_pass"] is False


def test_two_scene_partial_evidence_fails(tmp_path: Path) -> None:
    """9. Multi-scene isolation: Scene 1 evidence does NOT satisfy Scene 2."""
    evidence_scene_1 = {
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }

    job = _ready_job(scene_count=2)
    output = _ready_output(tmp_path / "final.mp4", scene_count=2)
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[
            {"scene_index": 1, "status": "downloaded", "clip_valid": True},
            {"scene_index": 2, "status": "downloaded", "clip_valid": True},
        ],
        debug_results=[
            {"scene_index": 1, "continuity_evidence": evidence_scene_1},
            {"scene_index": 2, "status": "downloaded"},  # missing evidence
        ],
    )

    assert validation["ok"] is False
    assert validation["continuity_evidence_scene_indexes"] == [1]
    assert validation["continuity_missing_scene_indexes"] == [2]
    assert validation["blocker"] == "selfshot2_person_continuity_evidence_missing"


def test_two_scene_complete_evidence_metadata_pass(tmp_path: Path) -> None:
    """10. Multi-scene complete: Both Scene 1 and Scene 2 have complete evidence -> PASS."""
    evidence_scene_1 = {
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }
    evidence_scene_2 = {
        "person_identity_preserved": "ok",
        "object_identity_preserved": "ok",
        "person_object_relationship_preserved": "ok",
    }

    job = _ready_job(scene_count=2)
    output = _ready_output(tmp_path / "final.mp4", scene_count=2)
    validation = selfshot2_continuity_validation(
        job,
        output,
        scene_tasks=[
            {"scene_index": 1, "status": "downloaded", "clip_valid": True},
            {"scene_index": 2, "status": "downloaded", "clip_valid": True},
        ],
        debug_results=[
            {"scene_index": 1, "continuity_evidence": evidence_scene_1},
            {"scene_index": 2, "continuity_evidence": evidence_scene_2},
        ],
    )

    assert validation["ok"] is True
    assert validation["metadata_contract_pass"] is True
    assert validation["continuity_evidence_scene_indexes"] == [1, 2]
    assert validation["continuity_missing_scene_indexes"] == []
    assert validation["blocker"] == ""


def test_transport_success_alone_is_not_evidence(tmp_path: Path) -> None:
    """11. Transport success alone (status=succeeded, task_id, result_url) is NOT continuity evidence."""
    transport_payload = {
        "provider_task_id": "task-xyz",
        "raw_status": "succeeded",
        "status": "completed",
        "result_url": "https://example.com/video.mp4",
        "result_url_present": True,
    }
    evidence = _selfshot2_continuity_evidence_from_payload(transport_payload)
    assert evidence == {}


def test_no_arbitrary_raw_provider_payload_leakage() -> None:
    """12. Normalization drops arbitrary provider metadata, tokens, and cluster secrets."""
    dirty_payload = {
        "api_key": "top-secret-api-key",
        "auth_token": "bearer-12345",
        "internal_ip": "10.0.0.99",
        "cluster": "prod-k8s-01",
        "billing_account": "acct_999",
        "data": {
            "task_id": "task-safe-id",
            "status": "succeeded",
            "video_url": "https://example.com/out.mp4",
            "admin_secret": "inside-secret",
            "continuity_evidence": {
                "person_identity": "pass",
                "object_identity": "pass",
                "person_object_relationship": "pass",
                "secret_key": "nested-token",
            },
        },
    }

    parsed = parse_provider_payload(dirty_payload)

    # Allowed keys only
    allowed_keys = {
        "provider_task_id",
        "raw_status",
        "status",
        "result_url",
        "result_url_present",
        "continuity_evidence",
    }
    assert set(parsed.keys()) == allowed_keys

    # No sensitive leaks in top level
    assert "api_key" not in parsed
    assert "auth_token" not in parsed
    assert "internal_ip" not in parsed
    assert "cluster" not in parsed
    assert "billing_account" not in parsed
    assert "admin_secret" not in parsed

    # No sensitive leaks nested in continuity container
    assert "secret_key" not in parsed["continuity_evidence"]
    assert parsed["continuity_evidence"] == {
        "person_identity": "pass",
        "object_identity": "pass",
        "person_object_relationship": "pass",
    }
