from __future__ import annotations

import hashlib
import json

from services import remote_worker_api
from services import video_uiflow3_execution_contract


def _hash_bound_snapshot() -> dict:
    snapshot = {
        "draft_id": "snapshot-sanitizer-regression",
        "format": {"ratio": "9:16", "scene_count": 2},
        "scenes": [{"scene_id": "scene_01"}, {"scene_id": "scene_02"}],
        "side_effects": {
            "provider_calls": 0,
            "jobs_created": 0,
            "wallet_mutations": 0,
        },
    }
    encoded = json.dumps(
        snapshot,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    snapshot["config_hash"] = hashlib.sha256(encoded).hexdigest()
    return snapshot


def test_worker_sanitizer_preserves_hash_bound_zero_wallet_counter() -> None:
    snapshot = _hash_bound_snapshot()

    sanitized = remote_worker_api.strip_secret_fields(
        {
            "uiflow3_approved_snapshot": snapshot,
            "api_key": "must-not-leak",
            "wallet_token": "must-not-leak",
        }
    )

    assert "api_key" not in sanitized
    assert "wallet_token" not in sanitized
    worker_snapshot = sanitized["uiflow3_approved_snapshot"]
    assert worker_snapshot == snapshot
    assert video_uiflow3_execution_contract.snapshot_hash_valid(worker_snapshot)
