from __future__ import annotations

import ast
import asyncio
import ctypes
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace

import pytest

import local_worker
from services import (
    video_edit_cleanup_audit,
    video_editengine1,
    video_local_validation,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def test_cleanup_audit_module_exposes_the_approved_contract() -> None:
    spec = importlib.util.find_spec("services.video_edit_cleanup_audit")

    assert spec is not None, "cleanup audit module must exist"

    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.CLEANUP_AUDIT_SCHEMA == "video-edit-cleanup-audit-v1"
    assert module.CLEANUP_AUDIT_VERSION == 1
    assert module.MAX_CLEANUP_ATTEMPTS == 3


@pytest.mark.parametrize(
    "job_id,claim_attempt",
    [
        (True, 1),
        (1, False),
        (0, 1),
        (1, 0),
        (-1, 1),
        (1, -1),
        ("1", 1),
        (1, "1"),
    ],
)
def test_workspace_key_accepts_only_positive_numeric_server_identity(
    job_id: object,
    claim_attempt: object,
) -> None:
    with pytest.raises(ValueError, match="cleanup_identity_invalid"):
        video_edit_cleanup_audit.workspace_key(job_id, claim_attempt)


def test_cleanup_intent_contains_only_minimal_server_derived_identity() -> None:
    intent = video_edit_cleanup_audit.build_cleanup_intent(
        job_id=17,
        delivery_claim_attempt=4,
        delivery_owner="worker-a:host-a:700",
        workspace_present=True,
    )

    assert intent == {
        "schema": "video-edit-cleanup-audit-v1",
        "version": 1,
        "job_id": 17,
        "delivery_claim_attempt": 4,
        "delivery_owner": "worker-a:host-a:700",
        "workspace_key": "job_17_claim_4",
        "tombstone_key": "job_17_claim_4",
        "workspace_present": True,
    }


def test_project_workspace_discovery_is_no_create_and_server_derived(
    tmp_path: Path,
) -> None:
    worker_root = tmp_path / "video-edit-worker"

    assert (
        video_edit_cleanup_audit.discover_project_workspace(worker_root, 17)
        is None
    )
    assert not worker_root.exists()

    project = worker_root / "job_17"
    project.mkdir(parents=True)
    assert video_edit_cleanup_audit.discover_project_workspace(
        worker_root,
        17,
    ) == project


def test_project_workspace_discovery_rejects_unsafe_or_reparse_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    worker_root = tmp_path / "video-edit-worker"
    worker_root.mkdir()
    project = worker_root / "job_17"
    project.write_bytes(b"not-a-directory")

    with pytest.raises(ValueError, match="cleanup_project_workspace_invalid"):
        video_edit_cleanup_audit.discover_project_workspace(worker_root, 17)

    project.unlink()
    project.mkdir()
    original_is_reparse = video_edit_cleanup_audit._is_reparse_or_link
    monkeypatch.setattr(
        video_edit_cleanup_audit,
        "_is_reparse_or_link",
        lambda path: Path(path) == project or original_is_reparse(Path(path)),
    )
    with pytest.raises(ValueError, match="cleanup_project_workspace_invalid"):
        video_edit_cleanup_audit.discover_project_workspace(worker_root, 17)


def test_project_cleanup_intent_removes_every_claim_child_and_keeps_v1_compatible(
    tmp_path: Path,
) -> None:
    worker_root = tmp_path / "video-edit-worker"
    project, active_claim = video_local_validation.create_video_edit_claim_workspace(
        17,
        4,
        root=worker_root,
    )
    prior_claim = project / "claim_3"
    prior_claim.mkdir()
    (prior_claim / "old-output.mp4").write_bytes(b"old-output")
    (active_claim / "new-output.mp4").write_bytes(b"new-output")
    (project / "manual.checkpoint.json").write_bytes(b"checkpoint")

    intent = video_edit_cleanup_audit.build_cleanup_intent(
        job_id=17,
        delivery_claim_attempt=4,
        delivery_owner="worker-instance-1",
        workspace_present=True,
        project_workspace=True,
    )
    assert intent == {
        "schema": video_edit_cleanup_audit.PROJECT_CLEANUP_AUDIT_SCHEMA,
        "version": video_edit_cleanup_audit.PROJECT_CLEANUP_AUDIT_VERSION,
        "job_id": 17,
        "delivery_claim_attempt": 4,
        "delivery_owner": "worker-instance-1",
        "workspace_key": "job_17_claim_4",
        "tombstone_key": "job_17_claim_4",
        "target_workspace_key": "job_17",
        "workspace_present": True,
    }
    assert video_edit_cleanup_audit.write_cleanup_intent(worker_root, intent) == {
        "persisted": True,
        "intent_key": "job_17_claim_4.json",
        "workspace_key": "job_17_claim_4",
        "tombstone_key": "job_17_claim_4",
    }

    cleanup = video_edit_cleanup_audit.secure_cleanup_workspace(
        worker_root,
        intent,
    )
    assert cleanup["ok"] is True
    assert cleanup["removed"] is True
    assert not project.exists()

    legacy = video_edit_cleanup_audit.build_cleanup_intent(
        job_id=18,
        delivery_claim_attempt=2,
        delivery_owner="worker-instance-1",
        workspace_present=False,
    )
    assert legacy["schema"] == video_edit_cleanup_audit.CLEANUP_AUDIT_SCHEMA
    assert legacy["version"] == video_edit_cleanup_audit.CLEANUP_AUDIT_VERSION
    assert "target_workspace_key" not in legacy

    tampered = {**intent, "target_workspace_key": "job_18"}
    with pytest.raises(ValueError, match="cleanup_intent_invalid"):
        video_edit_cleanup_audit.normalize_cleanup_intent(tampered)


def test_delivery_unknown_retains_the_stable_project_workspace_without_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    worker_root = tmp_path / "video-edit-worker"
    project, claim = video_local_validation.create_video_edit_claim_workspace(
        23,
        2,
        root=worker_root,
    )
    (claim / "uncertain.mp4").write_bytes(b"uncertain")
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "VIDEO_LOCAL_WORKSPACE_ROOT",
        worker_root,
    )

    intent, evidence = local_worker.prepare_video_edit_cleanup_intent(
        job_id=23,
        claim_attempt=2,
        workspace=project,
        terminal_stage="delivery_unknown",
        project_workspace=True,
    )

    assert intent is not None
    assert intent["target_workspace_key"] == "job_23"
    assert evidence == {"persisted": False, "workspace_present": True}
    assert project.is_dir()
    active = worker_root / video_edit_cleanup_audit.SPOOL_DIRECTORY / "active"
    assert not active.exists() or not list(active.iterdir())
    serialized = json.dumps(intent, sort_keys=True)
    assert ":\\" not in serialized
    assert "/" not in serialized


@pytest.mark.parametrize(
    "unsafe_key",
    [
        "../job_17_claim_4",
        "job_17_claim_4/child",
        r"job_17_claim_4\\child",
        ".",
        "..",
        "/job_17_claim_4",
        r"C:\\job_17_claim_4",
        "job_17_claim_04",
        "job_017_claim_4",
        "job_17_claim_4.json",
    ],
)
def test_cleanup_spool_rejects_dot_backslash_absolute_and_ambiguous_keys(
    tmp_path: Path,
    unsafe_key: str,
) -> None:
    with pytest.raises(ValueError, match="cleanup_key_invalid"):
        video_edit_cleanup_audit.cleanup_spool_path(
            tmp_path,
            bucket="active",
            key=unsafe_key,
            job_id=17,
            delivery_claim_attempt=4,
        )


def test_cleanup_intent_write_is_durable_and_loads_exact_minimal_payload(
    tmp_path: Path,
) -> None:
    intent = video_edit_cleanup_audit.build_cleanup_intent(
        job_id=17,
        delivery_claim_attempt=4,
        delivery_owner="worker-a:host-a:700",
        workspace_present=True,
    )

    result = video_edit_cleanup_audit.write_cleanup_intent(tmp_path, intent)

    assert result == {
        "persisted": True,
        "intent_key": "job_17_claim_4.json",
        "workspace_key": "job_17_claim_4",
        "tombstone_key": "job_17_claim_4",
    }
    active = (
        tmp_path
        / ".video_edit_cleanup_audit"
        / "active"
        / "job_17_claim_4.json"
    )
    assert active.is_file()
    assert video_edit_cleanup_audit.load_cleanup_intent(active) == intent
    assert list(active.parent.glob("*.tmp")) == []


def test_cleanup_intent_loader_reads_only_the_bounded_limit_plus_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "oversized.json"
    target.write_bytes(b"placeholder")
    requested: list[int] = []

    class Reader:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            requested.append(size)
            if size != 8 * 1024 + 1:
                raise AssertionError("cleanup intent read was not bounded")
            return b"x" * size

    monkeypatch.setattr(Path, "open", lambda _self, *args, **kwargs: Reader())

    with pytest.raises(ValueError, match="cleanup_intent_invalid"):
        video_edit_cleanup_audit.load_cleanup_intent(target)
    assert requested == [8 * 1024 + 1]


@pytest.mark.parametrize("failure_point", ["flush", "replace"])
def test_cleanup_intent_persistence_failure_is_bounded_and_leaves_no_claimable_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    intent = video_edit_cleanup_audit.build_cleanup_intent(
        job_id=19,
        delivery_claim_attempt=2,
        delivery_owner="worker-a:host-a:701",
        workspace_present=True,
    )

    def fail(*_args, **_kwargs):
        raise OSError("secret path must never escape: C:/private/token-value")

    monkeypatch.setattr(
        video_edit_cleanup_audit,
        "_flush_file" if failure_point == "flush" else "_durable_replace",
        fail,
    )

    result = video_edit_cleanup_audit.write_cleanup_intent(tmp_path, intent)

    assert result["persisted"] is False
    assert result["reason"] == "cleanup_intent_persist_failed:OSError"
    assert len(result["reason"]) <= 120
    active_dir = tmp_path / ".video_edit_cleanup_audit" / "active"
    assert not (active_dir / "job_19_claim_2.json").exists()
    assert list(active_dir.glob("*.tmp")) == []


def _intent(
    *,
    job_id: int = 23,
    delivery_claim_attempt: int = 5,
) -> dict:
    return video_edit_cleanup_audit.build_cleanup_intent(
        job_id=job_id,
        delivery_claim_attempt=delivery_claim_attempt,
        delivery_owner="worker-a:host-a:702",
        workspace_present=True,
    )


def _workspace(tmp_path: Path, intent: dict) -> Path:
    target = tmp_path / intent["workspace_key"]
    target.mkdir(parents=True)
    (target / "artifact.mp4").write_bytes(b"video-evidence")
    return target


def test_active_workspace_is_renamed_to_tombstone_then_removed_but_intent_waits_for_ack(
    tmp_path: Path,
) -> None:
    intent = _intent()
    active_workspace = _workspace(tmp_path, intent)
    assert video_edit_cleanup_audit.write_cleanup_intent(tmp_path, intent)[
        "persisted"
    ]

    result = video_edit_cleanup_audit.secure_cleanup_workspace(tmp_path, intent)

    tombstone = (
        tmp_path
        / ".video_edit_cleanup_audit"
        / "tombstones"
        / intent["tombstone_key"]
    )
    active_intent = (
        tmp_path
        / ".video_edit_cleanup_audit"
        / "active"
        / f"{intent['workspace_key']}.json"
    )
    assert result == {"ok": True, "outcome": "succeeded", "removed": True}
    assert not active_workspace.exists()
    assert not tombstone.exists()
    assert active_intent.is_file(), "audit ACK must precede intent removal"


def test_tombstone_only_resumes_deletion_after_rename_crash(tmp_path: Path) -> None:
    intent = _intent(job_id=24)
    _workspace_root, _active, tombstones, _orphan = (
        video_edit_cleanup_audit._spool_directories(tmp_path)
    )
    tombstone = tombstones / intent["tombstone_key"]
    tombstone.mkdir()
    (tombstone / "output.mp4").write_bytes(b"evidence")

    result = video_edit_cleanup_audit.secure_cleanup_workspace(tmp_path, intent)

    assert result == {"ok": True, "outcome": "succeeded", "removed": True}
    assert not tombstone.exists()


def test_missing_active_and_tombstone_is_idempotent_success(tmp_path: Path) -> None:
    result = video_edit_cleanup_audit.secure_cleanup_workspace(
        tmp_path,
        _intent(job_id=25),
    )

    assert result == {
        "ok": True,
        "outcome": "already_absent",
        "removed": False,
    }


def test_active_and_tombstone_together_fail_closed_and_delete_neither(
    tmp_path: Path,
) -> None:
    intent = _intent(job_id=26)
    active = _workspace(tmp_path, intent)
    _root, _active_bucket, tombstones, _orphan = (
        video_edit_cleanup_audit._spool_directories(tmp_path)
    )
    tombstone = tombstones / intent["tombstone_key"]
    tombstone.mkdir()
    (tombstone / "older.mp4").write_bytes(b"older")

    result = video_edit_cleanup_audit.secure_cleanup_workspace(tmp_path, intent)

    assert result == {
        "ok": False,
        "outcome": "failed_retryable",
        "reason": "cleanup_active_and_tombstone_present",
    }
    assert active.is_dir()
    assert tombstone.is_dir()


def test_secure_cleanup_rejects_symlink_descendant_without_touching_external_file(
    tmp_path: Path,
) -> None:
    intent = _intent(job_id=27)
    active = _workspace(tmp_path, intent)
    external = tmp_path / "external.txt"
    external.write_bytes(b"must-survive")
    link = active / "external-link"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")

    result = video_edit_cleanup_audit.secure_cleanup_workspace(tmp_path, intent)
    tombstone = (
        tmp_path
        / ".video_edit_cleanup_audit"
        / "tombstones"
        / intent["tombstone_key"]
    )

    assert result["ok"] is False
    assert result["reason"] == "cleanup_unsafe_path"
    assert not active.exists()
    assert tombstone.is_dir()
    assert (tombstone / "external-link").is_symlink()
    assert external.read_bytes() == b"must-survive"


def test_secure_cleanup_rechecks_identity_and_fails_closed_on_race_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent = _intent(job_id=28)
    active = _workspace(tmp_path, intent)
    monkeypatch.setattr(
        video_edit_cleanup_audit,
        "_same_file_identity",
        lambda *_args, **_kwargs: False,
    )

    result = video_edit_cleanup_audit.secure_cleanup_workspace(tmp_path, intent)

    assert result["ok"] is False
    assert result["reason"] == "cleanup_race_detected"
    assert active.is_dir()


def test_workspace_root_rejects_a_reparse_ancestor_before_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ancestor = tmp_path / "reparse-ancestor"
    root = ancestor / "video-local"
    root.mkdir(parents=True)
    real_check = video_edit_cleanup_audit._is_reparse_or_link

    def simulated_reparse(path: Path) -> bool:
        candidate = Path(path)
        if candidate == ancestor:
            return True
        return real_check(candidate)

    monkeypatch.setattr(
        video_edit_cleanup_audit,
        "_is_reparse_or_link",
        simulated_reparse,
    )

    with pytest.raises(ValueError, match="cleanup_workspace_root_invalid"):
        video_edit_cleanup_audit._workspace_root(root)


def test_active_identity_must_survive_the_atomic_tombstone_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent = _intent(job_id=281)
    active = _workspace(tmp_path, intent)
    original = tmp_path / "original-evidence"
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "must-not-delete.mp4").write_bytes(b"replacement")
    real_move = video_edit_cleanup_audit._durable_move_noreplace

    def swap_then_move(source: Path, destination: Path) -> None:
        source.rename(original)
        replacement.rename(source)
        real_move(source, destination)

    monkeypatch.setattr(
        video_edit_cleanup_audit,
        "_durable_move_noreplace",
        swap_then_move,
    )

    result = video_edit_cleanup_audit.secure_cleanup_workspace(tmp_path, intent)
    tombstone = (
        tmp_path
        / ".video_edit_cleanup_audit"
        / "tombstones"
        / intent["tombstone_key"]
    )

    assert result == {
        "ok": False,
        "outcome": "failed_retryable",
        "reason": "cleanup_race_detected",
    }
    assert original.is_dir() and (original / "artifact.mp4").is_file()
    assert tombstone.is_dir() and (tombstone / "must-not-delete.mp4").is_file()
    assert not active.exists()


def test_tombstone_created_during_rename_is_never_replaced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent = _intent(job_id=282)
    active = _workspace(tmp_path, intent)
    real_move = video_edit_cleanup_audit._durable_move_noreplace

    def occupy_destination(source: Path, destination: Path) -> None:
        destination.mkdir()
        (destination / "concurrent-evidence.mp4").write_bytes(b"concurrent")
        real_move(source, destination)

    monkeypatch.setattr(
        video_edit_cleanup_audit,
        "_durable_move_noreplace",
        occupy_destination,
    )

    result = video_edit_cleanup_audit.secure_cleanup_workspace(tmp_path, intent)
    tombstone = (
        tmp_path
        / ".video_edit_cleanup_audit"
        / "tombstones"
        / intent["tombstone_key"]
    )

    assert result == {
        "ok": False,
        "outcome": "failed_retryable",
        "reason": "cleanup_destination_exists",
    }
    assert active.is_dir() and (active / "artifact.mp4").is_file()
    assert tombstone.is_dir()
    assert (tombstone / "concurrent-evidence.mp4").read_bytes() == b"concurrent"


def test_recursive_cleanup_dispatches_to_nofollow_handle_implementations() -> None:
    public_source = inspect.getsource(
        video_edit_cleanup_audit.secure_cleanup_workspace
    )
    dispatch_source = inspect.getsource(
        video_edit_cleanup_audit._delete_tree_secure_nofollow
    )
    posix_source = inspect.getsource(
        video_edit_cleanup_audit._delete_tree_secure_posix
    )

    assert "_delete_tree_secure_nofollow" in public_source
    assert "_delete_tree_secure_posix" in dispatch_source
    assert "_delete_tree_secure_posix_fd" in posix_source
    assert "_delete_tree_secure_windows_handle" in dispatch_source
    assert "os.scandir(path)" not in dispatch_source


def test_windows_open_closes_handle_exactly_once_when_post_open_lstat_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CallableApi:
        def __init__(self, result: object) -> None:
            self.result = result
            self.argtypes = None
            self.restype = None

        def __call__(self, *_args: object) -> object:
            return self.result

    class FakeKernel32:
        def __init__(self) -> None:
            self.CreateFileW = CallableApi(ctypes.c_void_p(1234))
            self.close_calls: list[object] = []

        def CloseHandle(self, handle: object) -> int:
            self.close_calls.append(handle)
            return 1

    kernel32 = FakeKernel32()
    monkeypatch.setattr(
        video_edit_cleanup_audit,
        "_windows_kernel32",
        lambda: kernel32,
    )
    monkeypatch.setattr(
        video_edit_cleanup_audit,
        "_safe_lstat",
        lambda _path: (_ for _ in ()).throw(
            video_edit_cleanup_audit._CleanupSafetyError(
                "cleanup_race_detected"
            )
        ),
    )

    with pytest.raises(
        video_edit_cleanup_audit._CleanupSafetyError,
        match="cleanup_race_detected",
    ):
        video_edit_cleanup_audit._windows_open_locked(
            tmp_path / "race",
            directory=True,
        )

    assert len(kernel32.close_calls) == 1


def test_cleanup_failure_reason_is_bounded_and_never_contains_raw_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent = _intent(job_id=29)
    _workspace(tmp_path, intent)

    def fail(_path: Path, _expected: object) -> None:
        raise OSError("C:/private/users/customer/raw-video.mp4")

    monkeypatch.setattr(
        video_edit_cleanup_audit,
        "_delete_tree_secure_nofollow",
        fail,
    )

    result = video_edit_cleanup_audit.secure_cleanup_workspace(tmp_path, intent)

    assert result == {
        "ok": False,
        "outcome": "failed_retryable",
        "reason": "cleanup_failed:OSError",
    }
    assert len(result["reason"]) <= 120


def test_orphan_retention_durably_moves_intent_without_deleting_workspace(
    tmp_path: Path,
) -> None:
    intent = _intent(job_id=30)
    active_workspace = _workspace(tmp_path, intent)
    video_edit_cleanup_audit.write_cleanup_intent(tmp_path, intent)

    result = video_edit_cleanup_audit.retain_orphan_intent(tmp_path, intent)

    orphan = (
        tmp_path
        / ".video_edit_cleanup_audit"
        / "orphan-retained"
        / f"{intent['workspace_key']}.json"
    )
    assert result == {"ok": True, "outcome": "orphan_retained"}
    assert active_workspace.is_dir()
    assert orphan.is_file()
    assert video_edit_cleanup_audit.load_cleanup_intent(orphan) == intent


def test_active_intent_is_removed_only_by_explicit_post_ack_step(tmp_path: Path) -> None:
    intent = _intent(job_id=31)
    video_edit_cleanup_audit.write_cleanup_intent(tmp_path, intent)

    removed = video_edit_cleanup_audit.remove_active_intent(tmp_path, intent)
    removed_again = video_edit_cleanup_audit.remove_active_intent(tmp_path, intent)

    assert removed == {"ok": True, "removed": True}
    assert removed_again == {"ok": True, "removed": False}


def _db(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=1.0)
    conn.execute(
        """CREATE TABLE local_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, command TEXT, job_type TEXT, status TEXT,
            provider TEXT, input_file_id TEXT, created_at TEXT,
            output_file_id TEXT DEFAULT '', output_url TEXT DEFAULT '',
            error_short TEXT DEFAULT '', started_at TEXT DEFAULT '',
            finished_at TEXT DEFAULT '', worker_id TEXT DEFAULT '',
            xu_cost INTEGER, admin_only INTEGER, updated_at TEXT
        )"""
    )
    return conn


def _create_canonical_job(
    conn: sqlite3.Connection,
    *,
    session: str,
    price_xu: int = 0,
) -> tuple[int, dict]:
    free = price_xu == 0
    initial_tail = (
        {}
        if free
        else {"pricing_snapshot": {"total_xu": price_xu}}
    )
    created = video_editengine1.create_job(
        conn,
        user_id=7101,
        chat_id="7101",
        edit_session_id=session,
        source_file_id="source-file",
        source_metadata={"ok": True, "duration_ms": 4_000},
        plan={
            "trim": {"start_ms": 0, "end_ms": 4_000},
            "brightness_percent": 110,
        },
        tail=initial_tail,
        quality_tier_id="local-free" if free else "paid-hd",
        price_xu=price_xu,
        worker_payload={
            "local1_contract": 1,
            "local1_mode": "manual",
            "source_file_id": "source-file",
            "source_video_hash": "a" * 64,
            "concat_sources": [],
            "provider_call": False,
            "charge_policy": "free_local_tool" if free else "after_valid_mp4_delivery",
            "price_xu": price_xu,
            "quoted_price_xu": price_xu,
            "state_revision": 3,
            "rights_confirmation": {
                "confirmed": True,
                "policy": "video_edit_rights_v1",
                "user_id": "7101",
                "review_revision": 3,
                "confirmed_at_unix": 1_750_000_000,
            },
        },
    )
    conn.execute(
        "UPDATE video_edit_jobs SET tail_json=? WHERE local_worker_job_id=?",
        (
            json.dumps(
                {
                    **initial_tail,
                    "unrelated": {"must": "survive"},
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            int(created["local_worker_job_id"]),
        ),
    )
    conn.commit()
    claim = video_editengine1.claim_next_video_local_edit(
        conn,
        lease_owner="worker-a:host-a:703",
        now="2030-01-02 03:04:05",
        lease_seconds=300,
    )
    conn.commit()
    return int(created["local_worker_job_id"]), claim


def _terminal_receipt(*, price_xu: int = 0) -> dict:
    free = price_xu == 0
    return {
        "delivery_message_id": "1001",
        "delivery_file_id": "telegram-output-1",
        "source_video_path": "source.mp4",
        "source_sha256": "a" * 64,
        "output_path": "output.mp4",
        "output_sha256": "f" * 64,
        "output_size_bytes": 8_192,
        "ffprobe": {
            "ok": True,
            "has_video": True,
            "video_codec": "h264",
            "duration_ms": 4_000,
            "width": 1_280,
            "height": 720,
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        },
        "output_count": 1,
        "charge_policy": "free_local_tool" if free else "after_valid_mp4_delivery",
        "charge_status": "not_required_free" if free else "pending_post_delivery",
        "charged_xu": 0,
    }


def _intent_evidence(job_id: int, claim_attempt: int, *, persisted: bool = True) -> dict:
    key = f"job_{job_id}_claim_{claim_attempt}"
    evidence = {
        "persisted": persisted,
        "workspace_present": True,
    }
    if persisted:
        evidence.update(
            intent_key=f"{key}.json",
            workspace_key=key,
            tombstone_key=key,
        )
    else:
        evidence["reason"] = "cleanup_intent_persist_failed:OSError"
    return evidence


def test_terminal_delivery_atomically_seeds_pending_cleanup_audit_from_server_binding() -> None:
    conn = _db()
    job_id, claim = _create_canonical_job(conn, session="cleanup-seed-pending")
    conn.execute(
        """CREATE TRIGGER require_cleanup_seed_before_delivered
           BEFORE UPDATE OF status ON video_edit_jobs
           WHEN NEW.status='delivered'
            AND COALESCE(json_extract(NEW.tail_json,'$.cleanup_audit.state'),'')<>'pending'
           BEGIN SELECT RAISE(ABORT,'cleanup seed missing'); END"""
    )

    terminal = video_editengine1.record_worker_update(
        conn,
        worker_job_id=job_id,
        worker_status="succeeded",
        detail={
            "stage": "delivered",
            "validation": "passed",
            "cleanup_intent": _intent_evidence(job_id, claim["claim_attempt"]),
        },
        receipt=_terminal_receipt(),
    )

    audit = terminal["tail"]["cleanup_audit"]
    assert terminal["status"] == "delivered"
    assert terminal["tail"]["unrelated"] == {"must": "survive"}
    assert audit["schema"] == "video-edit-cleanup-audit-v1"
    assert audit["state"] == "pending"
    assert audit["job_id"] == job_id
    assert audit["delivery_owner"] == claim["lease_owner"]
    assert audit["delivery_claim_attempt"] == claim["claim_attempt"]
    assert audit["workspace_key"] == f"job_{job_id}_claim_{claim['claim_attempt']}"
    assert audit["tombstone_key"] == audit["workspace_key"]
    assert audit["audit_owner"] == ""
    assert audit["audit_attempt"] == 0
    assert audit["lease_expires_at"] == ""


def test_intent_persistence_failure_never_blocks_delivery_and_seeds_failed_exhausted() -> None:
    conn = _db()
    job_id, claim = _create_canonical_job(conn, session="cleanup-seed-failed")

    terminal = video_editengine1.record_worker_update(
        conn,
        worker_job_id=job_id,
        worker_status="succeeded",
        detail={
            "stage": "delivered",
            "validation": "passed",
            "cleanup_intent": _intent_evidence(
                job_id,
                claim["claim_attempt"],
                persisted=False,
            ),
        },
        receipt=_terminal_receipt(),
    )

    assert terminal["status"] == "delivered"
    assert terminal["tail"]["cleanup_audit"]["state"] == "failed_exhausted"
    assert terminal["tail"]["cleanup_audit"]["reason"] == (
        "cleanup_intent_not_persisted"
    )


def test_delivery_unknown_is_always_retained_and_never_cleanup_claimable() -> None:
    conn = _db()
    job_id, claim = _create_canonical_job(conn, session="cleanup-seed-unknown")

    terminal = video_editengine1.record_worker_update(
        conn,
        worker_job_id=job_id,
        worker_status="delivery_unknown",
        detail={
            "stage": "delivery_unknown",
            "reason": "telegram_delivery_outcome_uncertain",
            "cleanup_intent": _intent_evidence(job_id, claim["claim_attempt"]),
        },
        receipt={},
    )

    assert terminal["status"] == "delivery_unknown"
    assert terminal["tail"]["cleanup_audit"]["state"] == (
        "retained_delivery_unknown"
    )


def test_terminal_without_workspace_seeds_succeeded_without_cleanup_lease() -> None:
    conn = _db()
    job_id, claim = _create_canonical_job(conn, session="cleanup-seed-absent")

    terminal = video_editengine1.record_worker_update(
        conn,
        worker_job_id=job_id,
        worker_status="failed",
        detail={
            "stage": "failed_no_charge",
            "reason": "input_failed_before_workspace",
            "cleanup_intent": {
                "persisted": False,
                "workspace_present": False,
            },
        },
        receipt={},
    )

    assert terminal["status"] == "failed_no_charge"
    assert terminal["tail"]["cleanup_audit"]["state"] == "succeeded"
    assert terminal["tail"]["cleanup_audit"]["workspace_present"] is False
    assert terminal["tail"]["cleanup_audit"]["reason"] == "workspace_not_created"
    assert video_editengine1._cleanup_audit_record(
        terminal["tail"]["cleanup_audit"],
        worker_job_id=job_id,
    ) == terminal["tail"]["cleanup_audit"]
    reconciliation = _claim_audit(
        conn,
        job_id=job_id,
        claim=claim,
    )
    assert reconciliation == {
        "ok": True,
        "action": "remove_intent",
        "state": "succeeded",
    }


def _terminal_with_pending_audit(
    conn: sqlite3.Connection,
    *,
    session: str,
    price_xu: int = 0,
    worker_status: str = "succeeded",
) -> tuple[int, dict, dict]:
    job_id, claim = _create_canonical_job(
        conn,
        session=session,
        price_xu=price_xu,
    )
    if worker_status == "succeeded":
        detail = {
            "stage": "delivered",
            "validation": "passed",
            "cleanup_intent": _intent_evidence(job_id, claim["claim_attempt"]),
        }
        receipt = _terminal_receipt(price_xu=price_xu)
    elif worker_status == "delivery_unknown":
        detail = {
            "stage": "delivery_unknown",
            "reason": "telegram_delivery_outcome_uncertain",
            "cleanup_intent": _intent_evidence(job_id, claim["claim_attempt"]),
        }
        receipt = {}
    else:
        detail = {
            "stage": "failed_no_charge",
            "reason": "deterministic_failure",
            "cleanup_intent": _intent_evidence(job_id, claim["claim_attempt"]),
        }
        receipt = {}
    terminal = video_editengine1.record_worker_update(
        conn,
        worker_job_id=job_id,
        worker_status=worker_status,
        detail=detail,
        receipt=receipt,
    )
    conn.commit()
    return job_id, claim, terminal


def _claim_audit(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    claim: dict,
    audit_owner: str = "audit-worker-a:host-a:900",
    now: str = "2030-01-02 04:00:00",
    lease_seconds: int = 30,
    delivery_owner: str | None = None,
    delivery_claim_attempt: int | None = None,
) -> dict:
    return video_editengine1.claim_cleanup_audit(
        conn,
        worker_job_id=job_id,
        delivery_owner=(
            claim["lease_owner"] if delivery_owner is None else delivery_owner
        ),
        delivery_claim_attempt=(
            claim["claim_attempt"]
            if delivery_claim_attempt is None
            else delivery_claim_attempt
        ),
        audit_owner=audit_owner,
        now=now,
        lease_seconds=lease_seconds,
    )


@pytest.mark.parametrize(
    "case",
    [
        "unknown_state",
        "succeeded_workspace_present",
        "succeeded_reason",
        "pending_workspace_absent",
        "failed_retryable_without_reason",
        "failed_exhausted_wrong_attempt",
        "attempt_above_maximum",
        "extra_field",
    ],
)
def test_cleanup_audit_record_rejects_state_invariant_conflicts(
    case: str,
) -> None:
    conn = _db()
    job_id, _delivery_claim, terminal = _terminal_with_pending_audit(
        conn,
        session=f"cleanup-state-invariant-{case}",
        worker_status="failed",
    )
    audit = dict(terminal["tail"]["cleanup_audit"])
    if case == "unknown_state":
        audit["state"] = "finished"
    elif case == "succeeded_workspace_present":
        audit["state"] = "succeeded"
        audit["workspace_present"] = True
    elif case == "succeeded_reason":
        audit["state"] = "succeeded"
        audit["workspace_present"] = False
        audit["reason"] = "unexpected"
    elif case == "pending_workspace_absent":
        audit["workspace_present"] = False
    elif case == "failed_retryable_without_reason":
        audit["state"] = "failed_retryable"
        audit["audit_attempt"] = 1
        audit["reason"] = ""
    elif case == "failed_exhausted_wrong_attempt":
        audit["state"] = "failed_exhausted"
        audit["audit_attempt"] = 1
        audit["reason"] = "cleanup_failed:OSError"
    elif case == "attempt_above_maximum":
        audit["audit_attempt"] = video_edit_cleanup_audit.MAX_CLEANUP_ATTEMPTS + 1
    elif case == "extra_field":
        audit["unexpected"] = "must-fail-closed"

    assert (
        video_editengine1._cleanup_audit_record(
            audit,
            worker_job_id=job_id,
        )
        is None
    )


def test_cleanup_claim_rejects_wrong_delivery_owner_or_attempt_without_mutation() -> None:
    conn = _db()
    job_id, delivery_claim, terminal = _terminal_with_pending_audit(
        conn,
        session="cleanup-wrong-delivery-binding",
    )
    before = json.dumps(terminal["tail"], sort_keys=True)

    wrong_owner = _claim_audit(
        conn,
        job_id=job_id,
        claim=delivery_claim,
        delivery_owner="worker-forged:host:1",
    )
    wrong_attempt = _claim_audit(
        conn,
        job_id=job_id,
        claim=delivery_claim,
        delivery_claim_attempt=delivery_claim["claim_attempt"] + 1,
    )

    assert wrong_owner["action"] == "orphan_retained"
    assert wrong_attempt["action"] == "orphan_retained"
    after = video_editengine1.get_job_by_worker_id(conn, job_id)
    assert json.dumps(after["tail"], sort_keys=True) == before


def test_cleanup_claim_is_single_winner_and_new_owner_recovers_after_expiry() -> None:
    conn = _db()
    job_id, delivery_claim, _terminal = _terminal_with_pending_audit(
        conn,
        session="cleanup-lease-recovery",
    )

    first = _claim_audit(
        conn,
        job_id=job_id,
        claim=delivery_claim,
        now="2030-01-02 04:00:00",
    )
    conn.commit()
    concurrent = _claim_audit(
        conn,
        job_id=job_id,
        claim=delivery_claim,
        audit_owner="audit-worker-b:host-b:901",
        now="2030-01-02 04:00:20",
    )
    recovered = _claim_audit(
        conn,
        job_id=job_id,
        claim=delivery_claim,
        audit_owner="audit-worker-b:host-b:901",
        now="2030-01-02 04:00:31",
    )

    assert first["ok"] is True and first["action"] == "cleanup"
    assert first["audit_attempt"] == 1
    assert concurrent == {
        "ok": False,
        "action": "defer",
        "reason": "cleanup_audit_lease_active",
    }
    assert recovered["ok"] is True and recovered["action"] == "cleanup"
    assert recovered["audit_owner"] == "audit-worker-b:host-b:901"
    assert recovered["audit_attempt"] == 2


def test_two_connections_have_exactly_one_cleanup_lease_winner(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cleanup-claim-race.sqlite3"
    setup = _db(str(database))
    job_id, delivery_claim, _terminal = _terminal_with_pending_audit(
        setup,
        session="cleanup-two-connection-race",
    )
    setup.close()
    barrier = threading.Barrier(2)
    results: list[dict] = []
    errors: list[BaseException] = []

    def run_claim(owner: str) -> None:
        connection = sqlite3.connect(database, timeout=3.0)
        try:
            barrier.wait(timeout=3.0)
            result = _claim_audit(
                connection,
                job_id=job_id,
                claim=delivery_claim,
                audit_owner=owner,
            )
            connection.commit()
            results.append(result)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=run_claim, args=("audit-race-a:host:1",)),
        threading.Thread(target=run_claim, args=("audit-race-b:host:2",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2
    assert sum(result.get("action") == "cleanup" for result in results) == 1
    assert sum(
        result.get("reason") == "cleanup_audit_lease_active"
        for result in results
    ) == 1


def test_stale_cleanup_result_loses_and_only_cleanup_subobject_changes() -> None:
    conn = _db()
    job_id, delivery_claim, terminal = _terminal_with_pending_audit(
        conn,
        session="cleanup-stale-result",
    )
    first = _claim_audit(
        conn,
        job_id=job_id,
        claim=delivery_claim,
        now="2030-01-02 04:00:00",
    )
    conn.commit()
    second = _claim_audit(
        conn,
        job_id=job_id,
        claim=delivery_claim,
        audit_owner="audit-worker-b:host-b:901",
        now="2030-01-02 04:00:31",
    )
    conn.commit()
    before = video_editengine1.get_job_by_worker_id(conn, job_id)

    stale = video_editengine1.record_cleanup_audit_result(
        conn,
        worker_job_id=job_id,
        delivery_owner=delivery_claim["lease_owner"],
        delivery_claim_attempt=delivery_claim["claim_attempt"],
        audit_owner=first["audit_owner"],
        audit_attempt=first["audit_attempt"],
        now="2030-01-02 04:00:32",
        outcome="succeeded",
        reason="",
    )
    accepted = video_editengine1.record_cleanup_audit_result(
        conn,
        worker_job_id=job_id,
        delivery_owner=delivery_claim["lease_owner"],
        delivery_claim_attempt=delivery_claim["claim_attempt"],
        audit_owner=second["audit_owner"],
        audit_attempt=second["audit_attempt"],
        now="2030-01-02 04:00:32",
        outcome="succeeded",
        reason="",
    )
    after = video_editengine1.get_job_by_worker_id(conn, job_id)

    assert stale == {
        "ok": False,
        "reason": "cleanup_audit_lease_conflict",
    }
    assert accepted["ok"] is True
    assert after["tail"]["cleanup_audit"]["state"] == "succeeded"
    before_tail = dict(before["tail"])
    after_tail = dict(after["tail"])
    before_tail.pop("cleanup_audit")
    after_tail.pop("cleanup_audit")
    assert after_tail == before_tail == {
        "unrelated": {"must": "survive"}
    }
    for field in (
        "status",
        "delivery_message_id",
        "delivery_file_id",
        "output_file_id",
        "output_path",
        "output_sha256",
        "output_size_bytes",
        "receipt_state",
        "charge_state",
        "charged_xu",
    ):
        assert after[field] == before[field] == terminal[field]


def test_third_cleanup_failure_is_exhausted_and_reason_is_sanitized() -> None:
    conn = _db()
    job_id, delivery_claim, _terminal = _terminal_with_pending_audit(
        conn,
        session="cleanup-max-attempts",
        worker_status="failed",
    )

    for attempt in range(1, 4):
        lease = _claim_audit(
            conn,
            job_id=job_id,
            claim=delivery_claim,
            audit_owner=f"audit-worker-{attempt}:host:9{attempt}",
            now=f"2030-01-02 04:0{attempt}:00",
        )
        assert lease["audit_attempt"] == attempt
        result = video_editengine1.record_cleanup_audit_result(
            conn,
            worker_job_id=job_id,
            delivery_owner=delivery_claim["lease_owner"],
            delivery_claim_attempt=delivery_claim["claim_attempt"],
            audit_owner=lease["audit_owner"],
            audit_attempt=lease["audit_attempt"],
            now=f"2030-01-02 04:0{attempt}:01",
            outcome="failed_retryable",
            reason="cleanup_failed:OSError",
        )
        expected = "failed_exhausted" if attempt == 3 else "failed_retryable"
        assert result["cleanup_audit"]["state"] == expected
        assert result["cleanup_audit"]["reason"] == "cleanup_failed:OSError"
    exhausted = _claim_audit(
        conn,
        job_id=job_id,
        claim=delivery_claim,
        audit_owner="audit-worker-four:host:94",
        now="2030-01-02 04:04:00",
    )
    assert exhausted["action"] == "remove_intent"
    assert exhausted["state"] == "failed_exhausted"


def test_expired_third_cleanup_lease_terminalizes_without_a_result() -> None:
    conn = _db()
    job_id, delivery_claim, _terminal = _terminal_with_pending_audit(
        conn,
        session="cleanup-third-lease-crash",
        worker_status="failed",
    )

    for attempt in range(1, 4):
        lease = _claim_audit(
            conn,
            job_id=job_id,
            claim=delivery_claim,
            audit_owner=f"audit-crash-{attempt}:host:9{attempt}",
            now=f"2030-01-02 05:0{attempt}:00",
            lease_seconds=30,
        )
        conn.commit()
        assert lease["ok"] is True
        assert lease["audit_attempt"] == attempt

    exhausted = _claim_audit(
        conn,
        job_id=job_id,
        claim=delivery_claim,
        audit_owner="audit-after-third-crash:host:94",
        now="2030-01-02 05:04:00",
        lease_seconds=30,
    )
    canonical = video_editengine1.get_job_by_worker_id(conn, job_id)
    audit = canonical["tail"]["cleanup_audit"]

    assert exhausted == {
        "ok": True,
        "action": "remove_intent",
        "state": "failed_exhausted",
    }
    assert audit["state"] == "failed_exhausted"
    assert audit["audit_attempt"] == 3
    assert audit["audit_owner"] == ""
    assert audit["lease_expires_at"] == ""
    assert audit["reason"] == "cleanup_audit_attempts_exhausted"
    assert audit["workspace_present"] is True


def test_delivery_unknown_and_nonterminal_jobs_never_receive_cleanup_authority() -> None:
    conn = _db()
    unknown_id, unknown_claim, _unknown = _terminal_with_pending_audit(
        conn,
        session="cleanup-unknown-not-claimable",
        worker_status="delivery_unknown",
    )
    nonterminal_id, nonterminal_claim = _create_canonical_job(
        conn,
        session="cleanup-nonterminal-not-claimable",
    )

    unknown = _claim_audit(
        conn,
        job_id=unknown_id,
        claim=unknown_claim,
    )
    nonterminal = _claim_audit(
        conn,
        job_id=nonterminal_id,
        claim=nonterminal_claim,
    )
    missing = video_editengine1.claim_cleanup_audit(
        conn,
        worker_job_id=999_999,
        delivery_owner="worker-missing:host:1",
        delivery_claim_attempt=1,
        audit_owner="audit-worker-a:host:1",
        now="2030-01-02 04:00:00",
        lease_seconds=30,
    )

    assert unknown == {
        "ok": True,
        "action": "remove_intent",
        "state": "retained_delivery_unknown",
    }
    assert nonterminal == {
        "ok": False,
        "action": "retain_nonterminal",
        "reason": "cleanup_job_nonterminal",
    }
    assert missing["action"] == "orphan_retained"


def test_paid_cleanup_waits_for_atomic_charge_terminal_then_becomes_claimable(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cleanup-paid.sqlite3"
    setup = _db(str(database))
    job_id, delivery_claim, _terminal = _terminal_with_pending_audit(
        setup,
        session="cleanup-paid-charge-race",
        price_xu=17,
    )
    setup.close()
    charge_conn = sqlite3.connect(database, timeout=1.0)
    audit_conn = sqlite3.connect(database, timeout=1.0)

    before_charge = _claim_audit(
        audit_conn,
        job_id=job_id,
        claim=delivery_claim,
    )
    audit_conn.commit()
    assert before_charge == {
        "ok": False,
        "action": "defer",
        "reason": "cleanup_charge_not_terminal",
    }

    assert video_editengine1.claim_charge(
        charge_conn,
        worker_job_id=job_id,
    ) is True
    charged = video_editengine1.mark_charge_result(
        charge_conn,
        worker_job_id=job_id,
        ok=True,
        charged_xu=17,
    )
    charge_conn.commit()
    assert charged["status"] == "charged"

    after_charge = _claim_audit(
        audit_conn,
        job_id=job_id,
        claim=delivery_claim,
    )
    assert after_charge["ok"] is True
    assert after_charge["action"] == "cleanup"
    charge_conn.close()
    audit_conn.close()


class _CleanupEndpointHTTPException(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _CleanupEndpointRequest:
    def __init__(self) -> None:
        self.headers = {"x-worker-id": "worker-a"}


class _CleanupEndpointConnection:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1
        self.events.append("commit")

    def rollback(self) -> None:
        self.rollback_calls += 1
        self.events.append("rollback")

    def close(self) -> None:
        self.close_calls += 1
        self.events.append("close")


def _cleanup_endpoint_source(name: str) -> str:
    marker = f"async def {name}("
    start = BOT_SOURCE.index(marker)
    remainder = BOT_SOURCE[start:]
    next_route = remainder.find("\n@fastapi_app.")
    return remainder if next_route < 0 else remainder[:next_route]


def _compile_cleanup_endpoint(
    name: str,
    *,
    payload: dict,
    result: dict,
) -> tuple[object, list[str], list[dict], _CleanupEndpointConnection]:
    endpoint = ast.parse(_cleanup_endpoint_source(name)).body[0]
    assert isinstance(endpoint, ast.AsyncFunctionDef)
    endpoint.decorator_list = []
    events: list[str] = []
    calls: list[dict] = []
    connection = _CleanupEndpointConnection(events)

    async def read_json_body(_request: object) -> dict:
        events.append("read_json")
        return dict(payload)

    def claim_cleanup_audit(_conn: object, **kwargs: object) -> dict:
        events.append("claim")
        calls.append(dict(kwargs))
        return dict(result)

    def record_cleanup_audit_result(_conn: object, **kwargs: object) -> dict:
        events.append("result")
        calls.append(dict(kwargs))
        return dict(result)

    namespace = {
        "Request": object,
        "HTTPException": _CleanupEndpointHTTPException,
        "sqlite3": sqlite3,
        "verify_local_worker_access": lambda _request: events.append("auth"),
        "read_json_body": read_json_body,
        "db_connect": lambda: (events.append("connect") or connection),
        "now_text": lambda: "2030-01-02 06:00:00",
        "video_editengine1": SimpleNamespace(
            claim_cleanup_audit=claim_cleanup_audit,
            record_cleanup_audit_result=record_cleanup_audit_result,
        ),
    }
    compiled = compile(
        ast.fix_missing_locations(ast.Module(body=[endpoint], type_ignores=[])),
        str(ROOT / "bot.py"),
        "exec",
    )
    exec(compiled, namespace)
    return namespace[name], events, calls, connection


def test_bot_cleanup_endpoints_are_audit_only_and_transaction_bounded() -> None:
    claim_payload = {
        "job_id": 701,
        "delivery_owner": "worker-a:host-a:7",
        "delivery_claim_attempt": 3,
        "audit_owner": "worker-b:host-b:8",
        "lease_seconds": 30,
    }
    claim_endpoint, claim_events, claim_calls, claim_connection = (
        _compile_cleanup_endpoint(
            "internal_worker_video_edit_cleanup_claim",
            payload=claim_payload,
            result={"ok": True, "action": "cleanup"},
        )
    )
    claim_response = asyncio.run(claim_endpoint(_CleanupEndpointRequest()))

    assert claim_response == {"ok": True, "action": "cleanup"}
    assert claim_calls == [
        {
            "worker_job_id": 701,
            "delivery_owner": "worker-a:host-a:7",
            "delivery_claim_attempt": 3,
            "audit_owner": "worker-b:host-b:8",
            "now": "2030-01-02 06:00:00",
            "lease_seconds": 30,
        }
    ]
    assert claim_events == ["auth", "read_json", "connect", "claim", "commit", "close"]
    assert claim_connection.rollback_calls == 0

    result_payload = {
        **claim_payload,
        "audit_attempt": 2,
        "outcome": "succeeded",
        "reason": "",
    }
    result_endpoint, result_events, result_calls, result_connection = (
        _compile_cleanup_endpoint(
            "internal_worker_video_edit_cleanup_result",
            payload=result_payload,
            result={"ok": True, "cleanup_audit": {"state": "succeeded"}},
        )
    )
    result_response = asyncio.run(result_endpoint(_CleanupEndpointRequest()))

    assert result_response["ok"] is True
    assert result_calls == [
        {
            "worker_job_id": 701,
            "delivery_owner": "worker-a:host-a:7",
            "delivery_claim_attempt": 3,
            "audit_owner": "worker-b:host-b:8",
            "audit_attempt": 2,
            "now": "2030-01-02 06:00:00",
            "outcome": "succeeded",
            "reason": "",
        }
    ]
    assert result_events == ["auth", "read_json", "connect", "result", "commit", "close"]
    assert result_connection.rollback_calls == 0

    endpoint_source = "\n".join(
        _cleanup_endpoint_source(endpoint_name)
        for endpoint_name in (
            "internal_worker_video_edit_cleanup_claim",
            "internal_worker_video_edit_cleanup_result",
        )
    )
    for forbidden in (
        "update_local_worker_job",
        "record_worker_update",
        "claim_charge",
        "spend_fixed_credit_info",
        "wallet",
        "provider",
        "frame_video",
        "product_video",
    ):
        assert forbidden not in endpoint_source


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("job_id", True),
        ("delivery_claim_attempt", 0),
        ("audit_owner", ""),
        ("lease_seconds", "30"),
    ],
)
def test_bot_cleanup_claim_rejects_ambiguous_identity_before_db(
    field: str,
    bad_value: object,
) -> None:
    payload = {
        "job_id": 701,
        "delivery_owner": "worker-a:host-a:7",
        "delivery_claim_attempt": 3,
        "audit_owner": "worker-b:host-b:8",
        "lease_seconds": 30,
    }
    payload[field] = bad_value
    endpoint, events, calls, connection = _compile_cleanup_endpoint(
        "internal_worker_video_edit_cleanup_claim",
        payload=payload,
        result={"ok": True},
    )

    with pytest.raises(_CleanupEndpointHTTPException) as captured:
        asyncio.run(endpoint(_CleanupEndpointRequest()))

    assert captured.value.status_code == 400
    assert calls == []
    assert "connect" not in events
    assert connection.commit_calls == connection.rollback_calls == 0


def _worker_cleanup_intent(job_id: int = 801, attempt: int = 4) -> dict:
    return video_edit_cleanup_audit.build_cleanup_intent(
        job_id=job_id,
        delivery_claim_attempt=attempt,
        delivery_owner="worker-a:host-a:77",
        workspace_present=True,
    )


def test_worker_cleanup_prepare_persistence_failure_has_no_reconcilable_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = 804
    claim_attempt = 4
    workspace = tmp_path / video_edit_cleanup_audit.workspace_key(
        job_id,
        claim_attempt,
    )
    monkeypatch.setattr(
        local_worker.video_edit_cleanup_audit,
        "write_cleanup_intent",
        lambda _root, _intent: {
            "persisted": False,
            "reason": "cleanup_intent_persist_failed:OSError",
        },
    )

    intent, evidence = local_worker.prepare_video_edit_cleanup_intent(
        job_id=job_id,
        claim_attempt=claim_attempt,
        workspace=workspace,
        terminal_stage="delivered",
    )

    assert intent is None
    assert evidence == {
        "persisted": False,
        "workspace_present": True,
        "reason": "cleanup_intent_persist_failed:OSError",
    }


def test_worker_cleanup_reconciliation_orders_authority_delete_audit_ack_and_intent_removal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent = _worker_cleanup_intent()
    events: list[str] = []

    def fake_http(method: str, path: str, payload=None, **_kwargs: object) -> dict:
        events.append(f"http:{path}")
        if path.endswith("/claim"):
            return {
                "ok": True,
                "action": "cleanup",
                "audit_owner": "worker-current:host:9",
                "audit_attempt": 1,
            }
        return {"ok": True, "cleanup_audit": {"state": "succeeded"}}

    monkeypatch.setattr(local_worker, "http_json", fake_http)
    monkeypatch.setattr(local_worker, "LOCAL_WORKER_INSTANCE_ID", "worker-current:host:9")
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "VIDEO_LOCAL_WORKSPACE_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        local_worker.video_edit_cleanup_audit,
        "secure_cleanup_workspace",
        lambda _root, _intent: (
            events.append("secure_cleanup")
            or {"ok": True, "outcome": "succeeded", "removed": True}
        ),
    )
    monkeypatch.setattr(
        local_worker.video_edit_cleanup_audit,
        "remove_active_intent",
        lambda _root, _intent: (
            events.append("remove_intent") or {"ok": True, "removed": True}
        ),
    )

    result = local_worker.reconcile_video_edit_cleanup_intent(intent)

    assert result["ok"] is True
    assert events == [
        "http:/internal/worker/video_edit_cleanup/claim",
        "secure_cleanup",
        "http:/internal/worker/video_edit_cleanup/result",
        "remove_intent",
    ]


def test_worker_cleanup_reconciliation_never_deletes_delivery_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent = _worker_cleanup_intent(job_id=802)
    events: list[str] = []
    monkeypatch.setattr(local_worker, "LOCAL_WORKER_INSTANCE_ID", "worker-current:host:9")
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "VIDEO_LOCAL_WORKSPACE_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        local_worker,
        "http_json",
        lambda _method, path, _payload=None, **_kwargs: (
            events.append(f"http:{path}")
            or {
                "ok": True,
                "action": "remove_intent",
                "state": "retained_delivery_unknown",
            }
        ),
    )
    monkeypatch.setattr(
        local_worker.video_edit_cleanup_audit,
        "secure_cleanup_workspace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("delivery_unknown must retain workspace")
        ),
    )
    monkeypatch.setattr(
        local_worker.video_edit_cleanup_audit,
        "remove_active_intent",
        lambda _root, _intent: (
            events.append("remove_intent") or {"ok": True, "removed": False}
        ),
    )

    result = local_worker.reconcile_video_edit_cleanup_intent(intent)

    assert result["action"] == "remove_intent"
    assert events == [
        "http:/internal/worker/video_edit_cleanup/claim",
        "remove_intent",
    ]


def test_worker_cleanup_retryable_result_keeps_intent_for_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intent = _worker_cleanup_intent(job_id=803)
    events: list[str] = []

    def fake_http(_method: str, path: str, _payload=None, **_kwargs: object) -> dict:
        events.append(f"http:{path}")
        if path.endswith("/claim"):
            return {
                "ok": True,
                "action": "cleanup",
                "audit_owner": "worker-current:host:9",
                "audit_attempt": 1,
            }
        return {
            "ok": True,
            "cleanup_audit": {"state": "failed_retryable"},
        }

    monkeypatch.setattr(local_worker, "LOCAL_WORKER_INSTANCE_ID", "worker-current:host:9")
    monkeypatch.setattr(local_worker, "http_json", fake_http)
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "VIDEO_LOCAL_WORKSPACE_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        local_worker.video_edit_cleanup_audit,
        "secure_cleanup_workspace",
        lambda _root, _intent: {
            "ok": False,
            "outcome": "failed_retryable",
            "reason": "cleanup_failed:OSError",
        },
    )
    monkeypatch.setattr(
        local_worker.video_edit_cleanup_audit,
        "remove_active_intent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("retryable audit must keep active intent")
        ),
    )

    result = local_worker.reconcile_video_edit_cleanup_intent(intent)

    assert result["cleanup_audit"]["state"] == "failed_retryable"
    assert events == [
        "http:/internal/worker/video_edit_cleanup/claim",
        "http:/internal/worker/video_edit_cleanup/result",
    ]


def test_worker_cleanup_replay_is_bounded_and_main_runs_it_off_poll_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intents = [_worker_cleanup_intent(job_id=900 + index) for index in range(6)]
    reconciled: list[int] = []
    monkeypatch.setattr(
        local_worker.video_edit_cleanup_audit,
        "list_active_cleanup_intents",
        lambda _root, *, limit: intents[:limit],
        raising=False,
    )
    monkeypatch.setattr(
        local_worker,
        "reconcile_video_edit_cleanup_intent",
        lambda intent: reconciled.append(intent["job_id"]) or {"ok": True},
        raising=False,
    )

    processed = local_worker.replay_video_edit_cleanup_intents(limit=4)

    assert processed == 4
    assert reconciled == [900, 901, 902, 903]
    main_source = inspect.getsource(local_worker.main)
    assert "run_video_edit_cleanup_replay_loop" in main_source
    assert "video-edit-cleanup-replay" in main_source


def test_video_edit_terminal_flow_uses_stable_project_workspace_and_ack_fence() -> None:
    source = inspect.getsource(local_worker.run_video_local_edit)

    assert "create_video_edit_claim_workspace(" in source
    assert "workspace=project_workspace" in source
    assert source.count("project_workspace=True") == 2
    assert "video_edit_cleanup_audit.workspace_key(job_id, claim_attempt)" not in source
    assert "prepare_video_edit_cleanup_intent" in source
    assert "reconcile_video_edit_cleanup_intent" in source
    assert "create_job_workspace(f\"job_{job_id}\")" not in source
    assert source.index("prepare_video_edit_cleanup_intent") < source.rindex(
        "update_job("
    )
    assert source.rindex("update_job(") < source.index(
        "reconcile_video_edit_cleanup_intent"
    )
