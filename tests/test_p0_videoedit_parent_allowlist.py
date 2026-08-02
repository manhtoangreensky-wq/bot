from __future__ import annotations

import pytest

from services import video_edit_state_machine as machine


@pytest.mark.parametrize(
    "callback",
    [
        "videoedit|hub",
        "videoedit|manual",
        "videoedit|ai",
        "videoedit|restore",
        "videoedit|ai_source",
        "videoedit|ai_suggestions",
        "videoedit|ai_settings",
        "videoedit|ai_prompt",
        "videoedit|quality_source",
        "videoedit|workspace",
        "videoedit|cut",
        "videoedit|split",
        "videoedit|join",
        "videoedit|frame",
        "videoedit|transform",
        "videoedit|audio",
        "videoedit|color",
        "videoedit|overlay",
        "videoedit|effects",
        "videoedit|source_info",
        "videoedit|review",
        "videoedit|confirmation",
        "videoedit|options|manual",
        "videoedit|options|split",
    ],
)
def test_videoedit_exact_parent_allowlist_accepts_live_parents(callback: str) -> None:
    assert machine.safe_parent_callback(callback) == callback


@pytest.mark.parametrize(
    "callback",
    [
        "videoedit|unknown",
        "videoedit|set|speed|2",
        "videoedit|confirm_local",
        "videoedit|options|provider",
        "videoedit|../../subdub",
        "videoedit|workspace|extra",
    ],
)
def test_videoedit_same_namespace_unknown_parent_fails_closed(callback: str) -> None:
    assert machine.safe_parent_callback(callback) == "videoedit|hub"


def test_videoedit_declared_parent_matrix_only_uses_allowed_callbacks() -> None:
    for parent in machine.parent_matrix().values():
        assert machine.safe_parent_callback(parent) == parent


def test_confirmation_token_binds_session_and_review_revision_without_exposing_session_id() -> None:
    first = machine.confirmation_token("session-secret-a", 3)
    duplicate = machine.confirmation_token("session-secret-a", 3)
    changed_revision = machine.confirmation_token("session-secret-a", 4)
    changed_session = machine.confirmation_token("session-secret-b", 3)

    assert first == duplicate
    assert len(first) == 16
    assert all(character in "0123456789abcdef" for character in first)
    assert first != changed_revision
    assert first != changed_session
    assert "session-secret" not in first
