"""Targeted S07 exact evidence test binding approved fixture PV-L05.

SPEC_ID: PRODUCT-VIDEO-S07-SELFSHOT2-EXACT-EVIDENCE
Governed by: owner-governed-codex, locked-focus-engineering
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from services import (
    video_project_queue,
    video_tail9,
    video_final_output,
    video_real_render_connector,
)

FIXTURE_NAME = "PV-L05-self-shot-typing-source.mp4"
EXPECTED_SHA256 = "784FBE5BBD7B8D59A40A16AD103DB2B14B5DC7FCE71BE2ADA3E24A3BC04E2732".lower()

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATHS = [
    ROOT / "tests" / "fixtures" / FIXTURE_NAME,
    Path(r"c:\Users\toann\Documents\Codex\2026-06-25\start-new-codex-thread-p0-17b5-4\artifacts\product-video-live-fixtures") / FIXTURE_NAME,
]


def resolve_approved_fixture() -> Path:
    for p in CANDIDATE_PATHS:
        if p.is_file():
            h = hashlib.sha256(p.read_bytes()).hexdigest().lower()
            if h == EXPECTED_SHA256:
                return p
    pytest.fail(f"STATUS=BLOCKED_EVIDENCE: Approved fixture {FIXTURE_NAME} with SHA256 {EXPECTED_SHA256} not found")


def test_s07_approved_fixture_provenance_and_hash():
    """Verify approved fixture PV-L05 is present with exact expected SHA256."""
    fixture_path = resolve_approved_fixture()
    assert fixture_path.is_file()
    computed_sha = hashlib.sha256(fixture_path.read_bytes()).hexdigest().lower()
    assert computed_sha == EXPECTED_SHA256


def test_s07_selfshot2_contract_binds_approved_fixture(tmp_path: Path):
    """Verify Self-shot Scene Change binds the approved PV-L05 fixture to native I2V."""
    fixture_path = resolve_approved_fixture()

    contract = video_project_queue.product_video_engine_contract("self_shot_scene_change")
    assert contract["engine_route"] == "controlled_keyframe_image_to_video"
    assert contract["required_capability"] == "image_to_video"

    # Commercial tail contract
    comm = video_tail9.commercial_contract("self_shot_scene_change")
    assert comm["engine_route"] == "controlled_keyframe_image_to_video"
    assert comm["required_capability"] == "image_to_video"

    # Route adapter
    route = video_final_output.route_for_product_type("self_shot_scene_change")
    assert route["provider_capability"] == "image_to_video"
    assert route["engine_adapter"] == "controlled_keyframe_image_to_video"

    # Local source segment materialization from approved fixture
    asset_pack = {
        "source_video_local_path": str(fixture_path),
        "scene_source_segments": [
            {"scene_index": 1, "start_seconds": 0.0, "end_seconds": 5.0, "duration_seconds": 5.0},
        ],
    }
    segment = video_real_render_connector._selfshot2_scene_source_segment(asset_pack, 1, default_duration=5.0)
    assert segment["duration_seconds"] == 5.0
    assert segment["start_seconds"] == 0.0
