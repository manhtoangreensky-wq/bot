import os

import bot


def test_stale_pipeline_job_prune_removes_its_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "PIPELINE_TEMP_ROOT", str(tmp_path / "pipeline"))
    monkeypatch.setattr(bot, "PIPELINE_JOB_LOCK_TTL_SECONDS", 60)
    monkeypatch.setattr(
        bot,
        "persist_subtitle_dub_pipeline_job_snapshot",
        lambda *_args, **_kwargs: True,
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    workspace = bot.create_subtitle_dub_pipeline_workspace("stale-job")
    bot.SUBTITLE_DUB_PIPELINE_JOBS["stale-job"] = {
        "status": "completed",
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "workspace": workspace,
        "started_at": 100.0,
        "updated_at": 100.0,
    }

    bot._prune_subtitle_dub_pipeline_jobs(now_ts=161.0)

    assert "stale-job" not in bot.SUBTITLE_DUB_PIPELINE_JOBS
    assert not os.path.exists(workspace)


def test_orphan_workspace_sweep_preserves_active_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "PIPELINE_TEMP_ROOT", str(tmp_path / "pipeline"))
    monkeypatch.setattr(bot, "PIPELINE_JOB_LOCK_TTL_SECONDS", 60)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    active = bot.create_subtitle_dub_pipeline_workspace("active")
    orphan = bot.create_subtitle_dub_pipeline_workspace("orphan")
    os.utime(active, (100.0, 100.0))
    os.utime(orphan, (100.0, 100.0))
    bot.SUBTITLE_DUB_PIPELINE_JOBS["active"] = {
        "status": "running",
        "workspace": active,
        "started_at": 150.0,
        "updated_at": 150.0,
    }

    cleaned = bot.cleanup_stale_subtitle_dub_pipeline_workspaces(now_ts=200.0)

    assert cleaned == 1
    assert os.path.isdir(active)
    assert not os.path.exists(orphan)


def test_cleanup_reports_failure_when_workspace_still_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "PIPELINE_TEMP_ROOT", str(tmp_path / "pipeline"))
    workspace = bot.create_subtitle_dub_pipeline_workspace("not-removed")
    monkeypatch.setattr(bot.shutil, "rmtree", lambda *_args, **_kwargs: None)

    assert bot.cleanup_subtitle_dub_pipeline_workspace(workspace) is False
    assert os.path.isdir(workspace)


def test_cleanup_refuses_pipeline_root_and_external_paths(monkeypatch, tmp_path):
    root = tmp_path / "pipeline"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    monkeypatch.setattr(bot, "PIPELINE_TEMP_ROOT", str(root))

    assert bot.cleanup_subtitle_dub_pipeline_workspace(str(root)) is False
    assert bot.cleanup_subtitle_dub_pipeline_workspace(str(external)) is False
    assert root.is_dir()
    assert external.is_dir()
