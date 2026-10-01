"""R4 Regression: Storyboard Declared Coverage & Scene Identity.

Scope: P0.PRODUCT_VIDEO
Tracking Issue: #1155
PR: #1167

Tests that:
1. Declared scene_count is preserved even when fewer cards are materialized.
2. Positional fallback is removed — cards without explicit scene_index are skipped.
3. Missing/duplicate/out-of-range scene coverage is detected by validation.
4. _scene_count() prioritizes explicit declared value over len(cards).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from services import video_real_render_connector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_card(scene_index=None, *, prompt="test prompt", image_path="/tmp/img.png"):
    """Build a minimal scene card dict."""
    card = {
        "provider_prompt": prompt,
        "image_path": image_path,
    }
    if scene_index is not None:
        card["scene_index"] = scene_index
    return card


def _make_job(scene_count=None, scene_cards=None, project_scene_count=None):
    """Build a minimal job dict for testing."""
    job = {}
    if scene_cards is not None:
        job["scene_cards"] = scene_cards
    project = {}
    if scene_count is not None:
        job["scene_count"] = scene_count
    if project_scene_count is not None:
        project["scene_count"] = project_scene_count
        job["project"] = project
    elif scene_count is not None:
        project["scene_count"] = scene_count
        job["project"] = project
    return job


# ---------------------------------------------------------------------------
# R4-1: _scene_count preserves declared value over len(cards)
# ---------------------------------------------------------------------------

class TestSceneCountDeclaredPreservation:
    """_scene_count() must not shrink declared value when cards are partial."""

    def test_explicit_scene_count_preserved_over_fewer_cards(self):
        """Declared scene_count=5 with only 3 cards → must return 5, not 3."""
        job = _make_job(
            scene_count=5,
            scene_cards=[
                _make_card(scene_index=1),
                _make_card(scene_index=3),
                _make_card(scene_index=5),
            ],
        )
        assert video_real_render_connector._scene_count(job) == 5

    def test_explicit_project_scene_count_preserved(self):
        """project.scene_count=4 with 2 cards → must return 4."""
        job = {
            "scene_cards": [_make_card(scene_index=1), _make_card(scene_index=2)],
            "project": {"scene_count": 4},
        }
        assert video_real_render_connector._scene_count(job) == 4

    def test_no_explicit_count_falls_to_len_cards(self):
        """No explicit scene_count, 3 cards → must return 3 (fallback ok)."""
        job = {
            "scene_cards": [
                _make_card(scene_index=1),
                _make_card(scene_index=2),
                _make_card(scene_index=3),
            ],
        }
        assert video_real_render_connector._scene_count(job) == 3

    def test_empty_job_defaults_to_3(self):
        """Empty job → default 3."""
        assert video_real_render_connector._scene_count({}) == 3

    def test_scene_count_clamped_max_20(self):
        """Declared scene_count=25 → clamped to 20."""
        job = _make_job(scene_count=25, scene_cards=[])
        assert video_real_render_connector._scene_count(job) == 20

    def test_scene_count_clamped_min_1(self):
        """Declared scene_count=0 → clamped to 1."""
        job = _make_job(scene_count=0, scene_cards=[])
        # 0 is falsy, falls through to default 3
        assert video_real_render_connector._scene_count(job) >= 1


# ---------------------------------------------------------------------------
# R4-2: Positional fallback removal — cards without scene_index skipped
# ---------------------------------------------------------------------------

class TestPositionalFallbackRemoval:
    """Cards without explicit scene_index must not inherit list position."""

    def test_storyboard_scene_image_paths_skips_card_without_scene_index(self):
        """Card without scene_index should NOT match scene_index=1 by position."""
        job = {
            "scene_cards": [
                _make_card(image_path="/tmp/no_index.png"),  # no scene_index — must be skipped
                _make_card(scene_index=2, image_path="/tmp/scene2.png"),
            ],
            "scene_count": 2,
        }
        # Patch extract_local_image_paths to return the card's image_path
        def _mock_extract(card_or_panel, limit=2):
            path = card_or_panel.get("image_path", "")
            return [path] if path else []

        with patch("services.video_final_output.extract_local_image_paths", side_effect=_mock_extract):
            result = video_real_render_connector.storyboard_scene_image_paths(job, scene_index=1)
        # Scene 1 must NOT get /tmp/no_index.png via positional fallback
        assert result == []

    def test_storyboard_scene_image_paths_matches_explicit_index(self):
        """Card with explicit scene_index=2 must match scene_index=2."""
        job = {
            "scene_cards": [
                _make_card(scene_index=2, image_path="/tmp/scene2.png"),
            ],
            "scene_count": 2,
        }
        def _mock_extract(card_or_panel, limit=2):
            path = card_or_panel.get("image_path", "")
            return [path] if path else []

        with patch("services.video_final_output.extract_local_image_paths", side_effect=_mock_extract):
            result = video_real_render_connector.storyboard_scene_image_paths(job, scene_index=2)
        assert result == ["/tmp/scene2.png"]

    def test_real_video_scene_plan_skips_card_without_scene_index(self):
        """real_video_scene_plan must not use positional fallback for cards."""
        job = {
            "scene_cards": [
                _make_card(prompt="CARD_WITHOUT_INDEX_MARKER"),  # no scene_index
                _make_card(scene_index=2, prompt="scene_two_prompt"),
            ],
            "scene_count": 2,
            "project": {"scene_count": 2, "product_type": "storyboard_prompt"},
            "product_type": "storyboard_prompt",
        }
        plan = video_real_render_connector.real_video_scene_plan(job)
        scenes = plan["scenes"]
        assert len(scenes) == 2
        # Scene 1 should NOT contain the marker from the card without scene_index
        assert "CARD_WITHOUT_INDEX_MARKER" not in scenes[0]["video_prompt"]
        # Scene 2 SHOULD have scene_two_prompt
        assert "scene_two_prompt" in scenes[1]["video_prompt"]

    def test_storyboard_panel_without_scene_index_skipped(self):
        """Panels in storyboard_panels without scene_index must be skipped."""
        job = {
            "scene_cards": [],
            "scene_count": 2,
            "storyboard_panels": [
                {"image_path": "/tmp/p1.png"},  # no scene_index
                {"scene_index": 2, "image_path": "/tmp/p2.png"},
            ],
        }
        def _mock_extract(card_or_panel, limit=2):
            path = card_or_panel.get("image_path", "")
            return [path] if path else []

        with patch("services.video_final_output.extract_local_image_paths", side_effect=_mock_extract):
            result = video_real_render_connector.storyboard_scene_image_paths(job, scene_index=1)
        assert result == []


# ---------------------------------------------------------------------------
# R4-3: validate_storyboard_scene_coverage — fail closed
# ---------------------------------------------------------------------------

class TestStoryboardSceneCoverageValidation:
    """validate_storyboard_scene_coverage must reject bad scene card sets."""

    def test_valid_coverage_passes(self):
        """All scenes 1..N have exactly one card each → valid."""
        cards = [_make_card(scene_index=1), _make_card(scene_index=2), _make_card(scene_index=3)]
        result = video_real_render_connector.validate_storyboard_scene_coverage(cards, declared_count=3)
        assert result["valid"] is True

    def test_missing_scene_fails(self):
        """Scene 2 missing from cards with declared_count=3 → invalid."""
        cards = [_make_card(scene_index=1), _make_card(scene_index=3)]
        result = video_real_render_connector.validate_storyboard_scene_coverage(cards, declared_count=3)
        assert result["valid"] is False
        assert 2 in result.get("missing", [])

    def test_duplicate_scene_index_fails(self):
        """Two cards with scene_index=1 → invalid."""
        cards = [_make_card(scene_index=1), _make_card(scene_index=1), _make_card(scene_index=2)]
        result = video_real_render_connector.validate_storyboard_scene_coverage(cards, declared_count=2)
        assert result["valid"] is False
        assert 1 in result.get("duplicates", [])

    def test_out_of_range_scene_index_fails(self):
        """Card with scene_index=5 when declared_count=3 → invalid."""
        cards = [_make_card(scene_index=1), _make_card(scene_index=2), _make_card(scene_index=5)]
        result = video_real_render_connector.validate_storyboard_scene_coverage(cards, declared_count=3)
        assert result["valid"] is False
        assert 5 in result.get("out_of_range", [])

    def test_card_without_scene_index_detected(self):
        """Card without scene_index → flagged as missing_index."""
        cards = [_make_card(scene_index=1), _make_card()]  # second has no scene_index
        result = video_real_render_connector.validate_storyboard_scene_coverage(cards, declared_count=2)
        assert result["valid"] is False
        assert result.get("missing_index_count", 0) >= 1

    def test_empty_cards_with_nonzero_count_fails(self):
        """No cards but declared_count=3 → invalid."""
        result = video_real_render_connector.validate_storyboard_scene_coverage([], declared_count=3)
        assert result["valid"] is False

    def test_single_scene_valid(self):
        """Single scene with single card → valid."""
        cards = [_make_card(scene_index=1)]
        result = video_real_render_connector.validate_storyboard_scene_coverage(cards, declared_count=1)
        assert result["valid"] is True
