from __future__ import annotations

from datetime import datetime
import json
import sqlite3

import remote_worker
from services import remote_worker_api
from services import video_provider_router


READY_CAPABILITY = "product_video_provider_ready:shopaikey_video"


def _bot_missing_provider_status() -> dict:
    return {
        "provider_chain": ["shopaikey_video"],
        "effective_provider_chain": ["shopaikey_video"],
        "providers": [
            {
                "provider": "shopaikey_video",
                "enabled": False,
                "configured": False,
                "credit_ok": True,
                "selection_blocker": "not_configured",
            }
        ],
    }


def _runtime_result(*, hard_block: str = "") -> dict:
    result = {
        "source": "product_video",
        "product_video": True,
        "public_product_type": "video_ai_prompt",
        "admission_enforced": True,
        "admission_mode": "public_confirmed_probation",
        "provider_eligibility_snapshot": {
            "configured_provider_keys": ["shopaikey_video"],
            "eligible_provider_keys": ["shopaikey_video"],
            "contract_valid_provider_chain": ["shopaikey_video"],
        },
        "runtime_candidate_keys": ["shopaikey_video"],
        "preconfirm_candidate_keys": ["shopaikey_video"],
        "contract_valid_provider_chain": ["shopaikey_video"],
        "provider_health_at_submit": {},
        "scene_count": 2,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "worker_compatible": True,
        "worker_connected": True,
        "probation_candidate_key": "shopaikey_video",
        "probation_job_id": 19,
        "probation_lock_owner_job": 19,
        "current_job_matches_lock": True,
        "same_job_lock_reentry_allowed": True,
        "charge": 0,
        "charged_xu": 0,
    }
    if hard_block:
        result["provider_hard_block_reason_by_provider"] = {
            "shopaikey_video": hard_block
        }
    return result


def _readiness_conn(result: dict, *, ready: bool) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE system_settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE video_jobs (
            id INTEGER PRIMARY KEY,
            project_id INTEGER,
            user_id INTEGER,
            job_type TEXT,
            status TEXT,
            result_json TEXT,
            created_at TEXT,
            updated_at TEXT,
            completed_at TEXT
        );
        """
    )
    capabilities = [READY_CAPABILITY] if ready else []
    conn.execute(
        "INSERT INTO system_settings (key,value) VALUES (?,?)",
        (
            "remote_worker:owner_product_video:worker_capabilities",
            json.dumps(capabilities),
        ),
    )
    conn.execute(
        """INSERT INTO video_jobs
           (id,project_id,user_id,job_type,status,result_json,created_at,updated_at)
           VALUES (19,23,7126457028,'video_render','queued',?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
        (json.dumps(result),),
    )
    conn.commit()
    return conn


def _patch_bot_missing_provider_env(monkeypatch) -> None:
    monkeypatch.setattr(
        video_provider_router,
        "provider_status_payload",
        lambda _env=None: _bot_missing_provider_status(),
    )
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda _env=None: [],
    )
    monkeypatch.setattr(
        video_provider_router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "source": "test"},
    )


def test_worker_advertises_ready_provider_name_without_config(monkeypatch) -> None:
    monkeypatch.setattr(
        video_provider_router,
        "provider_status_payload",
        lambda _env=None: {
            "ready": True,
            "providers": [
                {
                    "provider": "shopaikey_video",
                    "enabled": True,
                    "configured": True,
                    "credit_ok": True,
                },
                {
                    "provider": "disabled_video",
                    "enabled": False,
                    "configured": True,
                    "credit_ok": True,
                },
            ],
        },
    )

    capabilities = remote_worker.product_video_worker_capabilities()

    assert READY_CAPABILITY in capabilities
    assert "product_video_provider_ready:disabled_video" not in capabilities
    assert not any("secret" in item or "token" in item for item in capabilities)


def test_runtime_uses_authenticated_worker_local_provider_readiness(monkeypatch) -> None:
    _patch_bot_missing_provider_env(monkeypatch)
    result = _runtime_result()
    conn = _readiness_conn(result, ready=True)

    eligibility = remote_worker_api._product_video_runtime_eligibility(
        {"id": 19, "project_id": 23, "user_id": 7126457028},
        result,
        {"project_id": 23, "user_id": 7126457028, "profile_id": "video_ai_prompt"},
        now=datetime(2026, 8, 22, 10, 0, 0),
        conn=conn,
    )

    assert eligibility["runtime_candidate_keys"] == ["shopaikey_video"]
    assert eligibility["provider_submit_allowed"] is True
    assert eligibility["worker_local_provider_hydration"] is True
    assert eligibility["provider_credentials_forwarded"] is False


def test_worker_readiness_never_overrides_external_hard_block(monkeypatch) -> None:
    _patch_bot_missing_provider_env(monkeypatch)
    result = _runtime_result(hard_block="security_block_active")
    conn = _readiness_conn(result, ready=True)

    eligibility = remote_worker_api._product_video_runtime_eligibility(
        {"id": 19, "project_id": 23, "user_id": 7126457028},
        result,
        {"project_id": 23, "user_id": 7126457028, "profile_id": "video_ai_prompt"},
        now=datetime(2026, 8, 22, 10, 0, 0),
        conn=conn,
    )

    assert eligibility["runtime_candidate_keys"] == []
    assert eligibility["provider_submit_allowed"] is False
