from __future__ import annotations

import threading
import urllib.parse

import pytest

import local_worker


def test_liveness_initial_renewal_failure_fails_closed_without_background_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_threads: list[object] = []

    class FakeThread:
        def __init__(self, **_kwargs) -> None:
            created_threads.append(self)

        def start(self) -> None:
            pytest.fail("a failed initial renewal must not start a background thread")

    def reject_renewal(*_args, **_kwargs) -> None:
        raise RuntimeError("lease rejected")

    monkeypatch.setattr(local_worker, "update_job", reject_renewal)
    monkeypatch.setattr(local_worker.threading, "Thread", FakeThread)
    liveness = local_worker.video_edit_job_liveness(2701, 30, 1, claim_attempt=1)

    with pytest.raises(
        local_worker.LocalVideoEditError,
        match="video_local_edit_worker_lease_lost",
    ):
        liveness.start()

    assert created_threads == []


def test_liveness_thread_start_failure_permanently_closes_without_join_masking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renewals: list[dict] = []
    created_threads: list[object] = []
    join_calls: list[object] = []

    class FakeThread:
        def __init__(self, **_kwargs) -> None:
            created_threads.append(self)

        def start(self) -> None:
            raise RuntimeError("thread runtime unavailable")

        def join(self, *_args, **_kwargs) -> None:
            join_calls.append(self)
            pytest.fail("stop must not join a thread candidate that never started")

    def record_renewal(*_args, **kwargs) -> None:
        renewals.append(dict(kwargs))

    monkeypatch.setattr(local_worker, "update_job", record_renewal)
    monkeypatch.setattr(local_worker.threading, "Thread", FakeThread)
    liveness = local_worker.video_edit_job_liveness(2701, 30, 1, claim_attempt=1)

    with pytest.raises(
        local_worker.LocalVideoEditError,
        match="video_local_edit_worker_lease_lost",
    ):
        liveness.start()

    liveness.stop()

    with pytest.raises(
        local_worker.LocalVideoEditError,
        match="video_local_edit_worker_lease_lost",
    ):
        liveness.start()

    assert len(renewals) == 1
    assert len(created_threads) == 1
    assert join_calls == []


def test_liveness_stop_before_start_permanently_closes_the_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renewals: list[dict] = []
    created_threads: list[object] = []

    class FakeThread:
        def __init__(self, **_kwargs) -> None:
            created_threads.append(self)

        def start(self) -> None:
            pytest.fail("a stopped liveness instance must not start a background thread")

    def record_renewal(*_args, **kwargs) -> None:
        renewals.append(dict(kwargs))

    monkeypatch.setattr(local_worker, "update_job", record_renewal)
    monkeypatch.setattr(local_worker.threading, "Thread", FakeThread)
    liveness = local_worker.video_edit_job_liveness(2701, 30, 1, claim_attempt=1)

    liveness.stop()
    for _attempt in range(2):
        with pytest.raises(
            local_worker.LocalVideoEditError,
            match="video_local_edit_worker_lease_lost",
        ):
            liveness.start()

    assert renewals == []
    assert created_threads == []


def test_liveness_concurrent_start_performs_one_renewal_and_starts_one_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_thread = threading.Thread
    first_renewal_entered = threading.Event()
    release_first_renewal = threading.Event()
    second_lock_attempted = threading.Event()
    second_caller_ident: list[int] = []
    renewals: list[int] = []
    created_threads: list[object] = []
    started_threads: list[object] = []
    errors: list[BaseException] = []

    class ObservedRLock:
        def __init__(self) -> None:
            self._lock = threading.RLock()

        def acquire(self, *args, **kwargs) -> bool:
            if (
                second_caller_ident
                and threading.get_ident() == second_caller_ident[0]
            ):
                second_lock_attempted.set()
            return self._lock.acquire(*args, **kwargs)

        def release(self) -> None:
            self._lock.release()

        def __enter__(self) -> ObservedRLock:
            self.acquire()
            return self

        def __exit__(self, *_args) -> None:
            self.release()

    class FakeThread:
        def __init__(self, **_kwargs) -> None:
            created_threads.append(self)

        def start(self) -> None:
            started_threads.append(self)

    def controlled_renewal(*_args, **_kwargs) -> None:
        renewals.append(1)
        if len(renewals) == 1:
            first_renewal_entered.set()
            assert release_first_renewal.wait(1)

    monkeypatch.setattr(local_worker, "update_job", controlled_renewal)
    monkeypatch.setattr(local_worker.threading, "Thread", FakeThread)
    liveness = local_worker.video_edit_job_liveness(2701, 30, 1, claim_attempt=1)
    liveness._lock = ObservedRLock()

    def call_start(is_second: bool = False) -> None:
        if is_second:
            second_caller_ident.append(threading.get_ident())
        try:
            liveness.start()
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    first = real_thread(target=call_start)
    first.start()
    assert first_renewal_entered.wait(1)
    second = real_thread(target=call_start, args=(True,))
    second.start()
    assert second_lock_attempted.wait(1)
    release_first_renewal.set()
    first.join(1)
    second.join(1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert len(renewals) == 1
    assert len(created_threads) == 1
    assert len(started_threads) == 1


def test_liveness_stop_waits_for_an_active_renewal_before_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_thread = threading.Thread
    real_event = threading.Event
    allow_background_renewal = real_event()
    renewal_active = threading.Event()
    release_renewal = threading.Event()
    stop_join_called = threading.Event()
    stop_done = threading.Event()
    renewal_calls = 0

    def controlled_renewal(*_args, **_kwargs) -> None:
        nonlocal renewal_calls
        renewal_calls += 1
        if renewal_calls == 1:
            return
        renewal_active.set()
        assert release_renewal.wait(1)

    monkeypatch.setattr(local_worker, "update_job", controlled_renewal)
    # Force the legacy bounded join path to return immediately.  A liveness
    # stop must still wait for the in-flight renewal before reporting done.
    monkeypatch.setattr(local_worker, "VIDEO_EDIT_LIVENESS_UPDATE_TIMEOUT_SECONDS", -5)
    liveness = local_worker.video_edit_job_liveness(2701, 30, 1, claim_attempt=1)

    class GateStopEvent:
        def __init__(self) -> None:
            self._stopped = real_event()
            self._first_wait = True

        def set(self) -> None:
            self._stopped.set()

        def wait(self, timeout: float | None = None) -> bool:
            if self._first_wait:
                self._first_wait = False
                assert allow_background_renewal.wait(timeout)
                return False
            return self._stopped.wait(timeout)

    liveness._stop_event = GateStopEvent()
    liveness.start()
    renewal_thread = liveness._thread
    stopper: threading.Thread | None = None
    try:
        assert renewal_thread is not None
        original_join = renewal_thread.join

        def observed_join(*args, **kwargs) -> None:
            stop_join_called.set()
            original_join(*args, **kwargs)

        monkeypatch.setattr(renewal_thread, "join", observed_join)
        allow_background_renewal.set()
        assert renewal_active.wait(1)

        def call_stop() -> None:
            liveness.stop()
            stop_done.set()

        stopper = real_thread(target=call_stop)
        stopper.start()
        assert stop_join_called.wait(1)
        assert not stop_done.wait(0.1)
        release_renewal.set()
        stopper.join(1)

        assert stop_done.is_set()
        assert not stopper.is_alive()
        assert renewal_calls == 2
        assert not renewal_thread.is_alive()
    finally:
        allow_background_renewal.set()
        release_renewal.set()
        liveness._stop_event.set()
        if stopper is not None and stopper.is_alive():
            stopper.join(1)
        if renewal_thread is not None and renewal_thread.is_alive():
            renewal_thread.join(1)


def test_poll_job_binds_a_process_instance_and_bounded_lease_without_losing_claim_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict | None, dict]] = []
    claimed = {
        "id": 311,
        "job_type": "video_local_edit",
        "claim_attempt": 7,
        "artifact_receipt_prefix": [{"message_id": "1001", "file_id": "file-1"}],
        "delivery_cursor": 1,
        "source_sha256": "a" * 64,
    }

    def fake_http(method: str, path: str, payload=None, **kwargs) -> dict:
        calls.append((method, path, payload, dict(kwargs)))
        return {"ok": True, "job": claimed}

    monkeypatch.setattr(local_worker, "LOCAL_WORKER_ID", "worker-a")
    monkeypatch.setattr(local_worker, "LOCAL_WORKER_INSTANCE_ID", "worker-a:host-a:99")
    monkeypatch.setattr(local_worker, "LOCAL_WORKER_MAX_JOB_SECONDS", 99_999)
    monkeypatch.setattr(local_worker, "http_json", fake_http)

    assert local_worker.poll_job() == claimed
    assert len(calls) == 1
    method, path, payload, kwargs = calls[0]
    assert method == "GET"
    assert payload is None
    assert kwargs["timeout"] == 25
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
    assert query == {
        "worker_id": ["worker-a"],
        "worker_instance_id": ["worker-a:host-a:99"],
        "lease_seconds": ["3600"],
        "video_edit_resume_version": ["1"],
    }
    assert claimed["claim_attempt"] == 7
    assert claimed["artifact_receipt_prefix"] == [{"message_id": "1001", "file_id": "file-1"}]
    assert claimed["delivery_cursor"] == 1
    assert claimed["source_sha256"] == "a" * 64


def test_video_edit_update_binds_instance_and_exact_claim_attempt_and_rejects_false_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict, dict]] = []

    def fake_http(method: str, path: str, payload=None, **kwargs) -> dict:
        calls.append((method, path, dict(payload or {}), dict(kwargs)))
        return {"ok": True, "job": {"id": 312}}

    monkeypatch.setattr(local_worker, "LOCAL_WORKER_ID", "worker-a")
    monkeypatch.setattr(local_worker, "LOCAL_WORKER_INSTANCE_ID", "worker-a:host-a:99")
    monkeypatch.setattr(local_worker, "http_json", fake_http)

    response = local_worker.update_job(
        312,
        "running",
        stage="processing_video",
        lease_seconds=99_999,
        claim_attempt=7,
    )

    assert response == {"ok": True, "job": {"id": 312}}
    assert len(calls) == 1
    method, path, payload, kwargs = calls[0]
    assert (method, path) == ("POST", "/internal/worker/job_update")
    assert payload["worker_id"] == "worker-a"
    assert payload["worker_instance_id"] == "worker-a:host-a:99"
    assert payload["claim_attempt"] == 7
    assert payload["lease_seconds"] == 3600
    assert kwargs["total_deadline_seconds"] == local_worker.VIDEO_EDIT_LIVENESS_UPDATE_TIMEOUT_SECONDS

    monkeypatch.setattr(local_worker, "http_json", lambda *_args, **_kwargs: {"ok": False})
    with pytest.raises(local_worker.LocalVideoEditError, match="video_local_edit_worker_update_rejected"):
        local_worker.update_job(
            312,
            "running",
            stage="processing_video",
            claim_attempt=7,
        )


def test_video_edit_liveness_renews_the_same_claim_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renewals: list[dict] = []

    class FakeThread:
        def __init__(self, **_kwargs) -> None:
            pass

        def start(self) -> None:
            pass

    def record_renewal(*_args, **kwargs) -> dict:
        renewals.append(dict(kwargs))
        return {"ok": True}

    monkeypatch.setattr(local_worker, "update_job", record_renewal)
    monkeypatch.setattr(local_worker.threading, "Thread", FakeThread)
    liveness = local_worker.video_edit_job_liveness(313, 30, 1, claim_attempt=9)

    liveness.start()
    liveness.update_stage("processing_video")
    assert liveness._renew() is True

    assert renewals == [
        {"stage": "inspecting_input", "lease_seconds": 30, "claim_attempt": 9},
        {"stage": "processing_video", "lease_seconds": 30, "claim_attempt": 9},
    ]


def test_non_video_update_keeps_the_legacy_call_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict, dict]] = []

    def fake_http(method: str, path: str, payload=None, **kwargs) -> dict:
        calls.append((method, path, dict(payload or {}), dict(kwargs)))
        return {"ok": True}

    monkeypatch.setattr(local_worker, "http_json", fake_http)

    response = local_worker.update_job(314, "succeeded", output_url="legacy-output")

    assert response == {"ok": True}
    assert len(calls) == 1
    _method, _path, payload, kwargs = calls[0]
    assert "worker_instance_id" not in payload
    assert "claim_attempt" not in payload
    assert "stage" not in payload
    assert "lease_seconds" not in payload
    assert "total_deadline_seconds" not in kwargs


@pytest.mark.parametrize(
    "claim_fields",
    [
        pytest.param({}, id="missing"),
        pytest.param({"claim_attempt": None}, id="none"),
        pytest.param({"claim_attempt": True}, id="bool"),
        pytest.param({"claim_attempt": 0}, id="zero"),
        pytest.param({"claim_attempt": -1}, id="negative"),
        pytest.param({"claim_attempt": 1.0}, id="float"),
        pytest.param({"claim_attempt": "1"}, id="string"),
    ],
)
def test_run_video_local_edit_rejects_missing_or_invalid_claim_attempt_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    claim_fields: dict,
) -> None:
    side_effects: list[str] = []

    def record(name: str):
        def call(*_args, **_kwargs):
            side_effects.append(name)

        return call

    monkeypatch.setattr(local_worker, "create_job_workspace", record("workspace"))
    monkeypatch.setattr(local_worker, "_video_edit_download_asset", record("download"))
    monkeypatch.setattr(local_worker, "execute_manual_edit", record("manual_render"))
    monkeypatch.setattr(local_worker, "execute_split_plan", record("split_render"))
    monkeypatch.setattr(
        local_worker.video_edit_media_transport,
        "send_artifact_from_path",
        record("transport"),
    )
    monkeypatch.setattr(local_worker, "update_job", record("update"))

    with pytest.raises(
        local_worker.LocalVideoEditError,
        match="video_local_edit_claim_attempt_invalid",
    ):
        local_worker.run_video_local_edit(
            {
                "id": 315,
                "job_type": "video_local_edit",
                "input_file_id": "{}",
                **claim_fields,
            }
        )

    assert side_effects == []
