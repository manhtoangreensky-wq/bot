import os
from pathlib import Path

import pytest

import bot


def _setup(monkeypatch, tmp_path):
    root = tmp_path / "pipeline"
    monkeypatch.setattr(bot, "PIPELINE_TEMP_ROOT", str(root))
    monkeypatch.setattr(bot, "PIPELINE_JOB_LOCK_TTL_SECONDS", 60)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    persisted = []
    monkeypatch.setattr(
        bot,
        "persist_subtitle_dub_pipeline_job_snapshot",
        lambda key, job, reason="": persisted.append((key, dict(job), reason)) or True,
    )
    return root, persisted


def _record(workspace, status="failed", **fields):
    return {
        "job_id": "cleanup-job",
        "status": status,
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "workspace": str(workspace),
        "started_at": 100.0,
        "updated_at": 100.0,
        **fields,
    }


def test_cleanup_success_persisted_before_stale_record_removed(monkeypatch, tmp_path):
    _root, persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace("success")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["success"] = _record(workspace)

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    assert not os.path.exists(workspace)
    assert "success" not in bot.SUBTITLE_DUB_PIPELINE_JOBS
    assert persisted[-1][1]["cleanup_status"] == "cleanup_succeeded"
    assert persisted[-1][1]["cleanup_result"]["deleted"] is True


def test_record_removal_waits_for_cleanup_audit_persistence(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace("persist-retry")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["persist-retry"] = _record(workspace)
    persistence_results = iter((False, True))
    monkeypatch.setattr(
        bot,
        "persist_subtitle_dub_pipeline_job_snapshot",
        lambda *_args, **_kwargs: next(persistence_results),
    )

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS["persist-retry"]
    assert not os.path.exists(workspace)
    assert stored["cleanup_status"] == "cleanup_succeeded"
    assert stored["cleanup_audit_persisted"] is False
    assert stored["cleanup_record_removal_pending"] is True

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=162.0)

    assert "persist-retry" not in bot.SUBTITLE_DUB_PIPELINE_JOBS


def test_permission_error_keeps_record_and_audits_failure(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace("permission")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["permission"] = _record(workspace)
    with monkeypatch.context() as cleanup_patch:
        cleanup_patch.setattr(
            bot.shutil,
            "rmtree",
            lambda _path: (_ for _ in ()).throw(PermissionError("denied")),
        )
        bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS["permission"]
    assert os.path.isdir(workspace)
    assert stored["cleanup_status"] == "cleanup_failed"
    assert stored["cleanup_error_type"] == "PermissionError"
    assert "denied" in stored["cleanup_error"]
    assert stored["cleanup_attempt_count"] == 1


def test_oserror_keeps_record(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace("oserror")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["oserror"] = _record(workspace)
    with monkeypatch.context() as cleanup_patch:
        cleanup_patch.setattr(
            bot.shutil,
            "rmtree",
            lambda _path: (_ for _ in ()).throw(OSError("busy")),
        )
        bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS["oserror"]
    assert stored["cleanup_status"] == "cleanup_failed"
    assert stored["cleanup_error_type"] == "OSError"
    assert os.path.isdir(workspace)


def test_file_not_found_is_audited_and_record_can_close(monkeypatch, tmp_path):
    _root, persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace("vanished")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["vanished"] = _record(workspace)

    def vanished(path):
        os.rmdir(path)
        raise FileNotFoundError(path)

    with monkeypatch.context() as cleanup_patch:
        cleanup_patch.setattr(bot.shutil, "rmtree", vanished)
        bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    assert "vanished" not in bot.SUBTITLE_DUB_PIPELINE_JOBS
    assert persisted[-1][1]["cleanup_status"] == "workspace_missing"
    assert persisted[-1][1]["cleanup_result"]["already_missing"] is True


@pytest.mark.parametrize("status", [
    "queued", "accepted", "preparing", "processing", "running", "rendering",
    "muxing", "delivering", "retrying_delivery", "waiting_retry",
    "waiting_provider", "waiting_scene", "finalizing",
])
def test_active_statuses_preserve_workspace(monkeypatch, tmp_path, status):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace(status)
    bot.SUBTITLE_DUB_PIPELINE_JOBS[status] = _record(workspace, status=status)

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    assert status in bot.SUBTITLE_DUB_PIPELINE_JOBS
    assert os.path.isdir(workspace)
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[status]["cleanup_status"] == "cleanup_skipped_active"


@pytest.mark.parametrize("status", ["completed", "failed", "failed_no_charge", "cancelled", "expired", "abandoned"])
def test_terminal_status_past_ttl_can_cleanup(monkeypatch, tmp_path, status):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace(status)
    bot.SUBTITLE_DUB_PIPELINE_JOBS[status] = _record(workspace, status=status)

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    assert status not in bot.SUBTITLE_DUB_PIPELINE_JOBS
    assert not os.path.exists(workspace)


def test_active_lock_and_recent_heartbeat_win_over_ttl(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    lock_workspace = bot.create_subtitle_dub_pipeline_workspace("lock")
    heartbeat_workspace = bot.create_subtitle_dub_pipeline_workspace("heartbeat")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["lock"] = _record(lock_workspace, status="completed", active_lock=True)
    bot.SUBTITLE_DUB_PIPELINE_JOBS["heartbeat"] = _record(
        heartbeat_workspace,
        status="completed",
        last_heartbeat_at=150.0,
    )

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    assert bot.SUBTITLE_DUB_PIPELINE_JOBS["lock"]["cleanup_status"] == "cleanup_skipped_active_lock"
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS["heartbeat"]["cleanup_status"] == "cleanup_skipped_active_lock"
    assert os.path.isdir(lock_workspace)
    assert os.path.isdir(heartbeat_workspace)


def test_path_safety_blocks_root_parent_and_external(monkeypatch, tmp_path):
    root, _persisted = _setup(monkeypatch, tmp_path)
    root.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()

    child = root / "normal-child"
    child.mkdir()
    assert bot.subtitle_dub_workspace_path_safety(str(child))["allowed"] is True
    assert bot.subtitle_dub_workspace_path_safety(str(root))["blocked_reason"] == "allowed_root_blocked"
    assert bot.subtitle_dub_workspace_path_safety(str(root / ".." / "external"))["allowed"] is False
    assert bot.subtitle_dub_workspace_path_safety(str(external))["allowed"] is False
    assert bot.subtitle_dub_workspace_path_safety(Path(root.anchor))["blocked_reason"] == "filesystem_root_blocked"


def _simulate_reparse_escape(monkeypatch, root, external, name, *, junction=False):
    entry = root / name
    entry.mkdir()
    entry_abs = Path(os.path.abspath(entry))
    root_abs = Path(os.path.abspath(root))
    external_resolved = external.resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    real_resolve = bot.Path.resolve

    def fake_resolve(self, strict=False):
        normalized = os.path.normcase(os.path.abspath(str(self)))
        if normalized == os.path.normcase(str(entry_abs)):
            return external_resolved
        if normalized == os.path.normcase(str(root_abs)):
            return root_resolved
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(bot.Path, "resolve", fake_resolve)
    monkeypatch.setattr(bot.os.path, "islink", lambda path: not junction and os.path.normcase(os.path.abspath(path)) == os.path.normcase(str(entry_abs)))
    monkeypatch.setattr(
        bot.os.path,
        "isjunction",
        lambda path: junction and os.path.normcase(os.path.abspath(path)) == os.path.normcase(str(entry_abs)),
        raising=False,
    )
    return bot.subtitle_dub_workspace_path_safety(str(entry))


def test_symlink_escape_blocked(monkeypatch, tmp_path):
    root, _persisted = _setup(monkeypatch, tmp_path)
    root.mkdir(parents=True)
    external = tmp_path / "outside"
    external.mkdir()
    result = _simulate_reparse_escape(monkeypatch, root, external, "symlink", junction=False)
    assert result["allowed"] is False
    assert result["blocked_reason"] == "symlink_escape_blocked"


def test_junction_escape_blocked(monkeypatch, tmp_path):
    root, _persisted = _setup(monkeypatch, tmp_path)
    root.mkdir(parents=True)
    external = tmp_path / "outside"
    external.mkdir()
    result = _simulate_reparse_escape(monkeypatch, root, external, "junction", junction=True)
    assert result["allowed"] is False
    assert result["blocked_reason"] == "junction_escape_blocked"


def test_final_inside_workspace_and_delivery_pending_is_preserved(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace("pending-final")
    final_file = Path(workspace) / "final.mp4"
    final_file.write_bytes(b"mp4")
    job = _record(
        workspace,
        status="completed",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        final_mp4=str(final_file),
        final_mp4_delivered=False,
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS["pending-final"] = job

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    assert "pending-final" in bot.SUBTITLE_DUB_PIPELINE_JOBS
    assert final_file.exists()
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS["pending-final"]["cleanup_status"] == "cleanup_skipped_delivery_pending"


def test_delivery_retry_and_dedupe_reference_preserve_workspace(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    retry_workspace = bot.create_subtitle_dub_pipeline_workspace("retry")
    dedupe_workspace = bot.create_subtitle_dub_pipeline_workspace("dedupe")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["retry"] = _record(
        retry_workspace,
        status="completed",
        delivery_retry_pending=True,
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS["dedupe"] = _record(
        dedupe_workspace,
        status="completed",
        dedupe_reference_count=1,
    )

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    assert bot.SUBTITLE_DUB_PIPELINE_JOBS["retry"]["cleanup_status"] == "cleanup_skipped_delivery_pending"
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS["dedupe"]["cleanup_status"] == "cleanup_skipped_active_reference"
    assert os.path.isdir(retry_workspace)
    assert os.path.isdir(dedupe_workspace)


def test_canonical_final_delivered_allows_cleanup(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace("canonical")
    workspace_final = Path(workspace) / "final.mp4"
    workspace_final.write_bytes(b"workspace-mp4")
    canonical = tmp_path / "canonical-output.mp4"
    canonical.write_bytes(b"canonical-mp4")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["canonical"] = _record(
        workspace,
        status="completed",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        terminal_state="delivered",
        final_mp4=str(workspace_final),
        canonical_output_path=str(canonical),
        final_mp4_delivered=True,
        output_sent=True,
        delivery_succeeded=True,
    )

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    assert "canonical" not in bot.SUBTITLE_DUB_PIPELINE_JOBS
    assert not os.path.exists(workspace)
    assert canonical.exists()


def test_delivered_record_with_missing_canonical_output_is_preserved(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace("missing-canonical")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["missing-canonical"] = _record(
        workspace,
        status="completed",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        terminal_state="delivered",
        canonical_output_path=str(tmp_path / "missing.mp4"),
        final_mp4_delivered=True,
        output_sent=True,
        delivery_succeeded=True,
    )

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS["missing-canonical"]
    assert stored["cleanup_status"] == "cleanup_skipped_delivered_output_inconsistent"
    assert os.path.isdir(workspace)


def test_cleanup_is_idempotent_and_success_requires_absence(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    workspace = bot.create_subtitle_dub_pipeline_workspace("idempotent")
    first = bot.cleanup_subtitle_dub_pipeline_workspace_result(workspace)
    second = bot.cleanup_subtitle_dub_pipeline_workspace_result(workspace)

    assert first["deleted"] is True
    assert second["already_missing"] is True
    assert bot.cleanup_subtitle_dub_pipeline_workspace(workspace) is True

    stubborn = bot.create_subtitle_dub_pipeline_workspace("stubborn")
    with monkeypatch.context() as cleanup_patch:
        cleanup_patch.setattr(bot.shutil, "rmtree", lambda _path: None)
        failed = bot.cleanup_subtitle_dub_pipeline_workspace_result(stubborn)
    assert failed["deleted"] is False
    assert failed["error_type"] == "WorkspaceStillExists"


def test_orphan_ttl_keeps_recent_and_removes_only_stale(monkeypatch, tmp_path):
    _root, _persisted = _setup(monkeypatch, tmp_path)
    recent = bot.create_subtitle_dub_pipeline_workspace("recent")
    stale = bot.create_subtitle_dub_pipeline_workspace("stale")
    os.utime(recent, (170.0, 170.0))
    os.utime(stale, (100.0, 100.0))

    cleaned = bot.cleanup_stale_subtitle_dub_pipeline_workspaces(now_ts=200.0)

    assert cleaned == 1
    assert os.path.isdir(recent)
    assert not os.path.exists(stale)
    assert bot.cleanup_stale_subtitle_dub_pipeline_workspaces(now_ts=200.0) == 0
