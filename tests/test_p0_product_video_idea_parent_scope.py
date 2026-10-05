"""Test suite for S05: Parent scope, owner, session, and revision handoff verification.

SPEC_ID: PRODUCT-VIDEO-S05-PARENT-SCOPE-HANDOFF
Governed by: owner-governed-codex, locked-focus-engineering

Invariants:
1. Legacy handoff: exact product, session, revision, and continuation matching.
2. UIFLOW3 handoff: strict draft_id, user_id, chat_id, and parent_product matching.
3. Cross-user, cross-chat, cross-product, and cross-draft callbacks are denied.
4. Stale revision or mismatched handoff produces zero active-draft mutation.
5. Assets (video/panel refs) survive handoff intact.
"""

from __future__ import annotations

from copy import deepcopy
import pytest

import bot
from services import video_idea_handoff, video_uiflow3


def _legacy_parent_state(product: str = "self_shot_scene_change") -> dict:
    return {
        "flow_session_id": "session-legacy-xyz-01",
        "flow_revision": 4,
        "flow_kind": f"flow-{product}",
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "subject": "Self shot scene change subject",
        "idea_return_step": video_idea_handoff.NEXT_STEPS[product],
        "trend_source": {},
        "reference_assets": {
            "source_media_ref": "video-fixture-token-999",
            "items": [{"file_id": "video-fixture-token-999", "media_kind": "video"}],
        },
    }


def test_legacy_parent_session_matching_and_rejection():
    parent = _legacy_parent_state("self_shot_scene_change")
    handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id="self_shot_scene_change",
        return_callback="vproduct|idea_back|self_shot_scene_change",
    )

    state = {
        "idea_parent_product": "self_shot_scene_change",
        "idea_parent_session_id": "session-legacy-xyz-01",
        "idea_parent_revision": 4,
        "idea_parent_continuation": "scene_plan",
    }
    assert video_idea_handoff.parent_session_matches(state, handoff) is True

    # 1. Stale revision rejection
    stale_state = dict(state, idea_parent_revision=3)
    assert video_idea_handoff.parent_session_matches(stale_state, handoff) is False

    # 2. Session ID mismatch rejection
    wrong_session = dict(state, idea_parent_session_id="session-different-999")
    assert video_idea_handoff.parent_session_matches(wrong_session, handoff) is False

    # 3. Product mismatch rejection
    wrong_product = dict(state, idea_parent_product="video_ai_real")
    assert video_idea_handoff.parent_session_matches(wrong_product, handoff) is False


def test_legacy_apply_parent_handoff_preserves_asset_locks():
    parent = _legacy_parent_state("self_shot_scene_change")
    handoff = video_idea_handoff.build_parent_handoff(
        parent,
        product_id="self_shot_scene_change",
        return_callback="vproduct|idea_back|self_shot_scene_change",
    )

    scene_state = {"idea_content": "New approved idea text"}
    restored = video_idea_handoff.apply_parent_handoff(scene_state, handoff)

    assert restored["source_product_id"] == "self_shot_scene_change"
    assert restored["idea_parent_session_id"] == "session-legacy-xyz-01"
    assert restored["idea_parent_revision"] == 4
    assert restored["source_video_id"] == "video-fixture-token-999"


def test_uiflow3_idea_handoff_isolation_matrix():
    draft_id = "draft-uiflow3-alpha-123"
    state = {
        "draft_id": draft_id,
        "parent_product": "video_ai_real",
        "owner_user_id": 1001,
        "owner_chat_id": 2001,
        "ui_revision": 5,
    }

    valid_handoff = {
        "uiflow3_owner": bot.UIFLOW3_IDEA_HANDOFF_OWNER,
        "uiflow3_draft_id": draft_id,
        "uiflow3_parent_product": "video_ai_real",
        "uiflow3_owner_user_id": 1001,
        "uiflow3_owner_chat_id": 2001,
        "uiflow3_session_revision": 5,
    }

    # Valid match
    assert bot._video_uiflow3_idea_handoff_matches(
        state, valid_handoff, user_id=1001, chat_id=2001
    ) is True

    # Cross-user mismatch (User 1002 attempting to use handoff)
    assert bot._video_uiflow3_idea_handoff_matches(
        state, valid_handoff, user_id=1002, chat_id=2001
    ) is False

    # Cross-chat mismatch
    assert bot._video_uiflow3_idea_handoff_matches(
        state, valid_handoff, user_id=1001, chat_id=2002
    ) is False

    # Cross-draft mismatch
    other_draft_handoff = dict(valid_handoff, uiflow3_draft_id="draft-other-999")
    assert bot._video_uiflow3_idea_handoff_matches(
        state, other_draft_handoff, user_id=1001, chat_id=2001
    ) is False

    # Rejection of video_idea as parent product
    idea_as_parent = dict(valid_handoff, uiflow3_parent_product="video_idea")
    assert bot._video_uiflow3_idea_handoff_matches(
        state, idea_as_parent, user_id=1001, chat_id=2001
    ) is False
