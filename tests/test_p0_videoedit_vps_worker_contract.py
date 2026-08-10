from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
import local_worker
from services import video_editengine1


VIDEO_EDIT_ONLY = "video_edit_only"


def _worker_request(scope: str, token: str) -> SimpleNamespace:
    return SimpleNamespace(
        headers={
            "authorization": f"Bearer {token}",
            "x-local-worker-job-scope": scope,
            "x-worker-id": f"vps-{scope}",
        },
        query_params={
            "worker_id": f"vps-{scope}",
            "worker_instance_id": f"vps-{scope}:1",
            "job_scope": scope,
            "lease_seconds": "60",
        },
    )


def test_dedicated_video_edit_token_is_sufficient_for_video_edit_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "")
    monkeypatch.setattr(bot, "VIDEO_EDIT_WORKER_TOKEN", "dedicated-token", raising=False)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"token_configured": False})
    monkeypatch.setattr(
        bot,
        "get_system_setting",
        lambda _key, default="": default,
    )
    monkeypatch.setattr(bot, "parse_utc_text", lambda _value: None)

    assert bot.video_edit_worker_status_payload()["token_configured"] is True

    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "legacy-token")
    monkeypatch.setattr(bot, "VIDEO_EDIT_WORKER_TOKEN", "", raising=False)
    assert bot.video_edit_worker_status_payload()["token_configured"] is False


def test_video_edit_only_scope_requires_its_dedicated_token_at_both_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "legacy-token")
    monkeypatch.setattr(bot, "VIDEO_EDIT_WORKER_TOKEN", "", raising=False)
    request = _worker_request(VIDEO_EDIT_ONLY, "legacy-token")

    with pytest.raises(bot.HTTPException) as server_rejection:
        bot.verify_local_worker_access(request)
    assert server_rejection.value.status_code == 503

    monkeypatch.setattr(local_worker, "LOCAL_WORKER_JOB_SCOPE", VIDEO_EDIT_ONLY)
    monkeypatch.setattr(local_worker, "LOCAL_WORKER_TOKEN", "legacy-token")
    monkeypatch.setattr(local_worker, "VIDEO_EDIT_WORKER_TOKEN", "", raising=False)
    with pytest.raises(
        local_worker.LocalVideoEditError,
        match="video_edit_worker_token_missing",
    ):
        local_worker.local_worker_auth_token()


def test_all_scope_heartbeat_cannot_overwrite_dedicated_video_edit_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "legacy-token")
    monkeypatch.setattr(bot, "VIDEO_EDIT_WORKER_TOKEN", "dedicated-token", raising=False)
    settings: dict[str, str] = {}
    monkeypatch.setattr(
        bot,
        "set_system_setting",
        lambda key, value, *_args: settings.__setitem__(key, value),
    )

    async def payload(request):
        return dict(request.payload)

    monkeypatch.setattr(bot, "read_json_body", payload)
    base_payload = {
        "heartbeat_contract_version": 1,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "capabilities": [video_editengine1.WORKER_CAPABILITY],
        "video_edit_filters_known": True,
        "video_edit_filters": ["format", "scale", "setsar"],
        "video_edit_filter_worker_id": "vps-video-edit",
        "video_edit_filter_ffmpeg_path": "/usr/bin/ffmpeg",
        "ffmpeg_path": "/usr/bin/ffmpeg",
        "ffprobe_path": "/usr/bin/ffprobe",
        "workspace_ready": True,
        "workspace_free_bytes": 10 * 1024 * 1024 * 1024,
        "video_edit_max_deadline_seconds": 21_600,
        "worker_token_ready": True,
        "local_bot_api_ready": True,
    }
    all_request = _worker_request("all", "legacy-token")
    all_request.payload = {**base_payload, "job_scope": "all", "worker_id": "vps-all"}
    asyncio.run(bot.internal_worker_heartbeat(all_request))
    assert "local_worker:video_edit_received_at_utc" not in settings

    settings.clear()
    dedicated_request = _worker_request(VIDEO_EDIT_ONLY, "dedicated-token")
    dedicated_request.payload = {
        **base_payload,
        "job_scope": VIDEO_EDIT_ONLY,
        "worker_id": "vps-video-edit",
    }
    asyncio.run(bot.internal_worker_heartbeat(dedicated_request))
    assert "local_worker:last_heartbeat" not in settings
    assert "local_worker:worker_id" not in settings
    assert "local_worker:frame_video_engine_flags_json" not in settings
    assert settings["local_worker:video_edit_job_scope"] == VIDEO_EDIT_ONLY
    assert settings["local_worker:video_edit_worker_id"] == "vps-video-edit"
    assert settings
    assert all(key.startswith("local_worker:video_edit_") for key in settings)


def test_all_scope_worker_never_claims_a_video_edit_only_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "legacy-token")
    monkeypatch.setattr(bot, "VIDEO_EDIT_WORKER_TOKEN", "dedicated-token", raising=False)
    monkeypatch.setattr(bot, "LOCAL_WORKER_ENABLED", True)
    monkeypatch.setattr(bot, "LOCAL_WORKER_POLL_ENABLED", True)
    monkeypatch.setattr(bot, "set_system_setting", lambda *_args, **_kwargs: None)
    claim_calls: list[str] = []

    def claim(_conn, **kwargs):
        claim_calls.append(str(kwargs.get("lease_owner") or ""))
        return {"id": 701, "job_type": video_editengine1.WORKER_JOB_TYPE}

    monkeypatch.setattr(bot.video_editengine1, "claim_next_video_local_edit", claim)

    class Cursor:
        def execute(self, *_args, **_kwargs):
            return self

        def fetchone(self):
            return None

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(bot, "db_connect", lambda: Connection())

    all_response = asyncio.run(
        bot.internal_worker_poll(_worker_request("all", "legacy-token"))
    )
    assert all_response["job"] is None
    assert claim_calls == []

    monkeypatch.setattr(local_worker, "LOCAL_WORKER_JOB_SCOPE", "all")
    assert "video_edit" not in local_worker.local_worker_capabilities()
    executed: list[int] = []
    monkeypatch.setattr(
        local_worker,
        "run_video_local_edit",
        lambda job: executed.append(int(job["id"])),
    )
    with pytest.raises(
        local_worker.LocalVideoEditError,
        match="worker_scope_job_type_forbidden",
    ):
        local_worker.process_job({"id": 701, "job_type": "video_local_edit"})
    assert executed == []

    dedicated_response = asyncio.run(
        bot.internal_worker_poll(
            _worker_request(VIDEO_EDIT_ONLY, "dedicated-token")
        )
    )
    assert dedicated_response["job"]["id"] == 701
    assert claim_calls == [f"vps-{VIDEO_EDIT_ONLY}:1"]


@pytest.mark.parametrize(
    ("scope", "cleanup_started"),
    [("all", False), (VIDEO_EDIT_ONLY, True)],
)
def test_video_edit_cleanup_replay_starts_only_for_the_dedicated_scope(
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    cleanup_started: bool,
) -> None:
    targets: list[object] = []

    class ThreadProbe:
        def __init__(self, *, target, args, name, daemon):
            del args, name, daemon
            self.target = target
            targets.append(target)

        def start(self) -> None:
            pass

        def join(self, *, timeout: int) -> None:
            assert timeout == 2

    monkeypatch.setattr(local_worker, "LOCAL_WORKER_JOB_SCOPE", scope)
    monkeypatch.setattr(local_worker, "local_worker_auth_token", lambda: "worker-token")
    monkeypatch.setattr(local_worker.threading, "Thread", ThreadProbe)
    monkeypatch.setattr(
        local_worker,
        "poll_job",
        lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    local_worker.main()

    assert local_worker.run_heartbeat_loop in targets
    assert (
        local_worker.run_video_edit_cleanup_replay_loop in targets
    ) is cleanup_started


def test_video_edit_only_vps_scope_isolated_at_worker_api_and_deploy_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An edit-only VPS is authenticated, claimed, and deployed independently."""

    monkeypatch.setattr(local_worker, "LOCAL_WORKER_JOB_SCOPE", VIDEO_EDIT_ONLY, raising=False)
    monkeypatch.setattr(local_worker, "LOCAL_WORKER_TOKEN", "legacy-token")
    monkeypatch.setattr(local_worker, "VIDEO_EDIT_WORKER_TOKEN", "dedicated-token", raising=False)

    headers = local_worker.auth_headers()
    assert headers["x-local-worker-job-scope"] == VIDEO_EDIT_ONLY

    heartbeat = local_worker.local_worker_heartbeat_payload()
    assert heartbeat["job_scope"] == VIDEO_EDIT_ONLY
    assert heartbeat["capabilities"] == ["video_edit"]

    calls: list[tuple[str, str]] = []

    def fake_http_json(method: str, path: str, **_kwargs) -> dict:
        calls.append((method, path))
        return {"ok": True, "job": None}

    monkeypatch.setattr(local_worker, "http_json", fake_http_json)
    assert local_worker.poll_job() is None
    assert "job_scope=video_edit_only" in calls[-1][1]

    side_effects: list[object] = []
    monkeypatch.setattr(local_worker, "update_job", lambda *args, **kwargs: side_effects.append(args))
    with pytest.raises(local_worker.LocalVideoEditError, match="worker_scope_job_type_forbidden"):
        local_worker.process_job({"id": 701, "job_type": "frame_video_render"})
    assert side_effects == []

    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "legacy-token")
    monkeypatch.setattr(bot, "VIDEO_EDIT_WORKER_TOKEN", "dedicated-token", raising=False)
    request = SimpleNamespace(
        headers={
            "authorization": "Bearer dedicated-token",
            "x-local-worker-job-scope": VIDEO_EDIT_ONLY,
        },
        query_params={
            "worker_id": "vps-video-edit",
            "worker_instance_id": "vps-video-edit:1",
            "job_scope": VIDEO_EDIT_ONLY,
            "lease_seconds": "60",
        },
    )
    assert bot.verify_local_worker_access(request) == VIDEO_EDIT_ONLY

    persisted: dict[str, str] = {}
    monkeypatch.setattr(
        bot,
        "set_system_setting",
        lambda key, value, *_args: persisted.__setitem__(key, value),
    )
    monkeypatch.setattr(
        bot.video_editengine1,
        "claim_next_video_local_edit",
        lambda *_args, **_kwargs: None,
    )

    class NoGenericFallbackConnection:
        def commit(self) -> None:
            pass

        def close(self) -> None:
            pass

        def cursor(self):
            raise AssertionError("video_edit_only must not query local_worker_jobs fallback")

    monkeypatch.setattr(bot, "db_connect", lambda: NoGenericFallbackConnection())
    response = asyncio.run(bot.internal_worker_poll(request))
    assert response["job"] is None
    assert persisted["local_worker:video_edit_poll_job_scope"] == VIDEO_EDIT_ONLY
    assert "local_worker:last_heartbeat" not in persisted
    assert "local_worker:worker_id" not in persisted
    assert "local_worker:job_scope" not in persisted

    unknown_scope = SimpleNamespace(
        headers={
            "authorization": "Bearer dedicated-token",
            "x-local-worker-job-scope": "unknown-scope",
        },
        query_params={},
    )
    with pytest.raises(bot.HTTPException):
        bot.verify_local_worker_access(unknown_scope)

    service = Path("deploy/systemd/toanaas-video-edit-worker.service").read_text(encoding="utf-8")
    environment = Path("deploy/env/toanaas-video-edit-worker.env.example").read_text(encoding="utf-8")
    runbook = Path("docs/ops/VPS_VIDEO_EDIT_WORKER_RUNBOOK.md").read_text(encoding="utf-8")
    assert "local_worker.py" in service
    assert "remote_worker.py" not in service
    assert "User=toanaas" in service
    assert "Group=toanaas" in service
    assert "LOCAL_WORKER_JOB_SCOPE=video_edit_only" in environment
    assert "VIDEO_PROJECT_QUEUE_ENABLED=false" in environment
    assert "LOCAL_WORKER_BOT_URL=" in environment
    assert "TELEGRAM_API_BASE_URL=https://tg.toanaas.vn" in environment
    assert "TELEGRAM_BOT_TOKEN=" in environment
    assert "TELEGRAM_API_PROXY_SECRET=" in environment
    assert "TELEGRAM_API_PROXY_SECRET_HEADER=X-Toanaas-Proxy-Secret" in environment
    assert "LOCAL_FFMPEG_PATH=/usr/bin/ffmpeg" in environment
    assert "FFPROBE_PATH=/usr/bin/ffprobe" in environment
    assert "LOCAL_FFMPEG_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" in environment
    assert "VIDEO_LOCAL_WORKSPACE_ROOT=/var/lib/toanaas/video-edit" in environment
    assert "LOCAL_WORKER_POLL_ENABLED" not in environment
    assert "VIDEO_EDIT_WORKER_TOKEN=" in environment
    assert "toanaas-video-edit-worker.service" in runbook
    assert "TELEGRAM_BOT_TOKEN" in runbook
    assert "TELEGRAM_API_PROXY_SECRET" in runbook
    assert "VIDEO_LOCAL_WORKSPACE_ROOT" in runbook
    assert "LOCAL_WORKER_ENABLED=true" in runbook
    assert "LOCAL_WORKER_POLL_ENABLED=true" in runbook
    assert "public HTTPS" in runbook
    assert "Railway bot service" in runbook
    assert "requires its own `VIDEO_EDIT_WORKER_TOKEN`" in runbook
    assert "legacy token remains the backward-compatible fallback" not in runbook


def test_worker_scopes_cannot_cross_update_or_cleanup_product_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "legacy-token")
    monkeypatch.setattr(bot, "VIDEO_EDIT_WORKER_TOKEN", "dedicated-token", raising=False)
    request = SimpleNamespace(
        headers={
            "authorization": "Bearer dedicated-token",
            "x-local-worker-job-scope": VIDEO_EDIT_ONLY,
            "x-worker-id": "vps-video-edit",
        },
        query_params={
            "worker_id": "vps-video-edit",
            "job_scope": VIDEO_EDIT_ONLY,
        },
    )
    monkeypatch.setattr(bot, "set_system_setting", lambda *_args, **_kwargs: None)

    with pytest.raises(bot.HTTPException) as product_poll:
        asyncio.run(bot.internal_video_worker_poll(request))
    assert product_poll.value.status_code == 403

    with pytest.raises(bot.HTTPException) as product_update:
        asyncio.run(bot.internal_video_worker_job_update(request))
    assert product_update.value.status_code == 403

    with pytest.raises(bot.HTTPException) as generic_upload:
        asyncio.run(
            bot.internal_worker_upload_result(
                request,
                job_id="702",
                file=SimpleNamespace(filename="result.mp4"),
            )
        )
    assert generic_upload.value.status_code == 403

    async def update_payload(_request):
        return {"id": 702, "status": "running"}

    mutations: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(bot, "read_json_body", update_payload)
    monkeypatch.setattr(
        bot,
        "get_local_worker_job",
        lambda _job_id: {"id": 702, "job_type": "worker_ping", "status": "queued"},
    )
    monkeypatch.setattr(
        bot,
        "update_local_worker_job",
        lambda *args, **kwargs: mutations.append((args, kwargs)) or {
            "id": 702,
            "job_type": "worker_ping",
            "status": "running",
        },
    )
    for handler_name in (
        "handle_frame_video_worker_job_update",
        "handle_paid_video_preview_worker_job_update",
        "handle_video_ai_edit_worker_job_update",
        "handle_video_local_edit_worker_job_update",
        "handle_social_link_import_worker_job_update",
    ):
        monkeypatch.setattr(bot, handler_name, lambda *_args, **_kwargs: None)

    with pytest.raises(bot.HTTPException) as generic_update:
        asyncio.run(bot.internal_worker_job_update(request))
    assert generic_update.value.status_code == 403
    assert mutations == []

    all_request = _worker_request("all", "legacy-token")

    async def video_edit_update_payload(_request):
        return {
            "id": 703,
            "status": "running",
            "worker_id": "vps-all",
            "worker_instance_id": "vps-all:1",
            "claim_attempt": 1,
        }

    monkeypatch.setattr(bot, "read_json_body", video_edit_update_payload)
    monkeypatch.setattr(
        bot,
        "get_local_worker_job",
        lambda _job_id: {
            "id": 703,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "status": "running",
            "worker_id": "vps-all:1",
            "worker_instance_id": "vps-all:1",
            "claim_attempt": 1,
        },
    )
    with pytest.raises(bot.HTTPException) as video_edit_update:
        asyncio.run(bot.internal_worker_job_update(all_request))
    assert video_edit_update.value.status_code == 403

    async def body_must_not_be_read(_request):
        raise AssertionError("generic worker must be rejected before cleanup body")

    monkeypatch.setattr(bot, "read_json_body", body_must_not_be_read)
    for endpoint in (
        bot.internal_worker_video_edit_cleanup_claim,
        bot.internal_worker_video_edit_cleanup_result,
    ):
        with pytest.raises(bot.HTTPException) as cleanup_rejection:
            asyncio.run(endpoint(all_request))
        assert cleanup_rejection.value.status_code == 403
