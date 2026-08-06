# Video Edit Large-Media Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every existing Video Edit lane the SubDub-aligned short/large-media lifecycle, with `<=60 seconds AND <=20 MiB` selecting the short path and every other input selecting file-backed processing through `tg.toanaas.vn`, without using proportional RAM or adding an arbitrary rejection cap.

**Architecture:** Keep one production Local Bot API origin and the existing Video Edit job/engine/outbox/receipt contracts. Add a Video Edit-owned streaming transport and long-media policy that copy SubDub's lifecycle semantics—classification, preflight, adaptive deadline, checkpoint, monotonic progress, delivery-once, recovery, and guarded cleanup—without importing or modifying `subdub_*` code. Segment only operations proven segment-safe; otherwise run one checkpointed whole-timeline FFmpeg part with per-job liveness.

**Tech Stack:** Python 3.11, python-telegram-bot 22.7, httpx/standard-library streaming I/O, SQLite existing schema, FFmpeg/FFprobe, pytest, Railway, Telegram Local Bot API at `https://tg.toanaas.vn`.

---

## File map

- Create `services/video_edit_media_transport.py`: Video Edit lane selection, endpoint configuration, file-backed download, and streaming multipart delivery.
- Create `services/video_edit_long_media.py`: deterministic project key, plan classification, resource estimate, adaptive deadline, and atomic checkpoint helpers.
- Modify `services/telegram_transport.py`: dependency-free validated Telegram method/file/localfile URL builders.
- Modify `services/video_local_validation.py`: allow Video Edit callers to disable public byte/duration rejection while preserving all existing defaults.
- Modify `services/video_editengine1.py`: renew and fence the existing Video Edit outbox lease without a schema change.
- Modify `bot.py`: Video Edit-only inspection, capability copy, lane persistence, and localized resource/transport failure mapping.
- Modify `local_worker.py`: Video Edit-only transport, long-media checkpoint/liveness, render, and delivery wiring.
- Create `tests/test_p0_videoedit_large_media_transport.py`: pure transport, lane, resource, streaming, and secret-redaction tests.
- Create `tests/test_p0_videoedit_large_media_runtime.py`: pure long-media policy/checkpoint/liveness tests.
- Modify `tests/test_p0_video_edit3_canonical_intake_route_state_machine.py`: reuse its executable canonical upload harness for bot inspection/lane tests.
- Modify `tests/test_p0_videoedit_canonical_local_worker_receipt.py`: reuse its real `run_video_local_edit` harness for worker transport/receipt tests.
- Modify `tests/test_p0_videoedit_canonical_bot_routes.py`: exact truthful copy and route assertions; do not change SubDub tests or code.

### Task 1: Close the pending callback-context follow-up before large-media work

**Files:**
- Modify: `bot.py`
- Test: `tests/test_p0_videoedit_callbackquery_frozen_runtime.py`
- Verify: `docs/superpowers/plans/2026-08-02-video-edit-legacy-callback-context.md`

- [ ] **Step 1: Wait for exact CPU ownership**

Do not run Python, pytest, py_compile, FFmpeg, or ffprobe until the coordinating task sends exact `CPU RELEASED BY ROUTEENGINE` and Video Edit announces exact `CPU ACQUIRED BY VIDEO EDIT`.

- [ ] **Step 2: Execute the existing three callback RED regressions**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q tests/test_p0_videoedit_callbackquery_frozen_runtime.py
```

Expected before implementation: the frozen legacy delegation and stale-tail ContextVar boundary tests fail for their documented reasons, never by collection/import error.

- [ ] **Step 3: Implement and verify the callback plan exactly**

Follow `docs/superpowers/plans/2026-08-02-video-edit-legacy-callback-context.md`; preserve legacy mutation for `menu`, `framevideo`, `selfscene`, and `videoref`, and use `callback_data_override` only for Video Edit.

- [ ] **Step 4: Ship callback closure separately**

Run its ordered comparator/compile/review/PR/merge/deploy/navigation gates. Start the large-media branch only from the resulting latest `origin/main`; never mix the large-media files into the callback PR.

### Task 2: Encode exact lane and validation semantics

**Files:**
- Create: `services/video_edit_media_transport.py`
- Modify: `services/video_local_validation.py`
- Test: `tests/test_p0_videoedit_large_media_transport.py`

- [ ] **Step 1: Write boundary RED tests**

Add:

```python
from services import video_edit_media_transport as media_transport
from services import video_local_validation


MIB = 1024 * 1024


def test_video_edit_lane_uses_both_short_media_boundaries():
    assert media_transport.select_media_lane(duration_seconds=60, size_bytes=20 * MIB) == "short_media"
    assert media_transport.select_media_lane(duration_seconds=61, size_bytes=20 * MIB) == "large_media"
    assert media_transport.select_media_lane(duration_seconds=60, size_bytes=20 * MIB + 1) == "large_media"
    assert media_transport.select_media_lane(duration_seconds=0, size_bytes=10 * MIB) == "large_media"
    assert media_transport.select_media_lane(duration_seconds=30, size_bytes=0) == "large_media"


def test_video_edit_can_disable_product_size_and_duration_rejection_only_explicitly():
    metadata = {"ok": True, "bytes": 300 * MIB, "duration": 7_200, "width": 1920, "height": 1080}
    assert not video_local_validation.validate_source_metadata(metadata, file_size=300 * MIB)["ok"]
    accepted = video_local_validation.validate_source_metadata(
        metadata,
        file_size=300 * MIB,
        maximum_bytes=0,
        maximum_duration_seconds=0,
    )
    assert accepted["ok"] is True
```

- [ ] **Step 2: Run RED**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q tests/test_p0_videoedit_large_media_transport.py -k "lane or disable_product"
```

Expected: FAIL because the module and keyword parameters do not exist.

- [ ] **Step 3: Implement the minimal pure classifier and opt-out parameters**

Create:

```python
SHORT_MEDIA_MAX_SECONDS = 60.0
SHORT_MEDIA_MAX_BYTES = 20 * 1024 * 1024


def select_media_lane(*, duration_seconds: float, size_bytes: int) -> str:
    duration = max(0.0, float(duration_seconds or 0.0))
    size = max(0, int(size_bytes or 0))
    if duration and size and duration <= SHORT_MEDIA_MAX_SECONDS and size <= SHORT_MEDIA_MAX_BYTES:
        return "short_media"
    return "large_media"
```

Change `validate_source_metadata` compatibly:

```python
def validate_source_metadata(
    metadata: dict[str, Any],
    *,
    file_size: int = 0,
    maximum_bytes: int = MAX_UPLOAD_BYTES,
    maximum_duration_seconds: int = MAX_DURATION_SECONDS,
) -> dict[str, Any]:
    data = dict(metadata or {})
    size = int(file_size or data.get("bytes") or 0)
    duration = float(data.get("duration") or 0)
    if int(maximum_bytes or 0) > 0 and size > int(maximum_bytes):
        return {**data, "ok": False, "reason": "video_too_large"}
    if int(maximum_duration_seconds or 0) > 0 and duration > int(maximum_duration_seconds):
        return {**data, "ok": False, "reason": "duration_too_long"}
    if not data.get("ok"):
        return {**data, "ok": False, "reason": str(data.get("reason") or "invalid_video")}
    return {**data, "ok": True, "reason": ""}
```

- [ ] **Step 4: Run GREEN and compatibility**

Run the RED command plus every existing `video_local_validation` selector. Expected: new boundary cases PASS and all default-limit callers remain unchanged.

- [ ] **Step 5: Commit the pure policy**

```powershell
git add services/video_edit_media_transport.py services/video_local_validation.py tests/test_p0_videoedit_large_media_transport.py
git commit -m "feat(video-edit): classify short and large media"
```

### Task 3: Centralize safe Telegram endpoint construction

**Files:**
- Modify: `services/telegram_transport.py`
- Modify: `services/video_edit_media_transport.py`
- Test: `tests/test_p0_videoedit_large_media_transport.py`

- [ ] **Step 1: Add RED URL/secret tests**

Cover exact `https://tg.toanaas.vn`, Cloud rollback, unsafe remote HTTP, user-info/query/fragment, Local absolute file path mapping, `..`, redirect refusal, and the invariant that proxy secret headers are returned only for the exact Local origin.

```python
def test_localfile_builder_maps_absolute_path_without_leaking_or_traversal():
    url = telegram_transport.local_media_url(
        api_root="https://tg.toanaas.vn",
        absolute_file_path="/var/lib/telegram-bot-api/123:token/videos/file_1.mp4",
        file_root="/var/lib/telegram-bot-api",
        media_path="/localfile",
    )
    assert url == "https://tg.toanaas.vn/localfile/123:token/videos/file_1.mp4"
    with pytest.raises(ValueError):
        telegram_transport.local_media_url(
            api_root="https://tg.toanaas.vn",
            absolute_file_path="/var/lib/telegram-bot-api/../secret",
            file_root="/var/lib/telegram-bot-api",
            media_path="/localfile",
        )
```

- [ ] **Step 2: Run RED**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q tests/test_p0_videoedit_large_media_transport.py -k "url or secret or localfile"
```

Expected: FAIL because policy builders are absent.

- [ ] **Step 3: Add dependency-free builders**

Implement validated builders with strict method token and path checks:

```python
from dataclasses import dataclass
import re


_BOT_METHOD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


@dataclass(frozen=True)
class TelegramMediaConfig:
    token: str
    api_root: str
    proxy_secret_header: str
    proxy_secret: str
    local_file_root: str
    local_media_path: str

    @property
    def is_local(self) -> bool:
        root = telegram_transport.normalize_api_root(self.api_root)
        return bool(root and not telegram_transport.is_cloud_api_url(root))

    def request_headers(self) -> dict[str, str]:
        if not self.is_local or not self.proxy_secret:
            return {}
        return {self.proxy_secret_header: self.proxy_secret}


def bot_method_url(*, api_root: str, token: str, method: str) -> str:
    root = normalize_api_root(api_root) or "https://api.telegram.org"
    if not token or not _BOT_METHOD.fullmatch(str(method or "")):
        raise ValueError("invalid Telegram API request")
    return validate_api_url(f"{root}/bot{token}/{method}")


def local_media_url(*, api_root: str, absolute_file_path: str, file_root: str, media_path: str) -> str:
    root = normalize_api_root(api_root)
    base = "/" + str(file_root or "").strip("/")
    raw = "/" + str(absolute_file_path or "").strip("/")
    if not root or not raw.startswith(base + "/"):
        raise ValueError("invalid Telegram local media path")
    relative = raw[len(base):].lstrip("/")
    if not relative or any(part in {"", ".", ".."} for part in relative.split("/")):
        raise ValueError("invalid Telegram local media path")
    return validate_api_url(f"{root}/{str(media_path or 'localfile').strip('/')}/{relative}")
```

- [ ] **Step 4: Run GREEN with existing infra tests**

Run the RED command plus `tests/test_infra_localbotapi_base_url.py` and `tests/test_p0_secfix_local_api_transport.py`. Expected: all pass and no secret is ever sent to Cloud.

- [ ] **Step 5: Commit endpoint policy**

```powershell
git add services/telegram_transport.py services/video_edit_media_transport.py tests/test_p0_videoedit_large_media_transport.py
git commit -m "feat(video-edit): share safe Local Bot API endpoints"
```

### Task 4: Implement file-backed Telegram download

**Files:**
- Modify: `services/video_edit_media_transport.py`
- Test: `tests/test_p0_videoedit_large_media_transport.py`

- [ ] **Step 1: Add RED streaming tests**

Use injected fake responses that yield bounded chunks. Prove `.partial` atomicity, incremental SHA-256, declared/actual byte evidence, progress, deadline, disk guard, cleanup, bounded retry, redirect refusal, and classified errors without token URLs.

```python
def local_config():
    return TelegramMediaConfig(
        token="123:test-token",
        api_root="https://tg.toanaas.vn",
        proxy_secret_header="X-Toanaas-Proxy-Secret",
        proxy_secret="test-secret",
        local_file_root="/var/lib/telegram-bot-api",
        local_media_path="/localfile",
    )


def fake_get_file(file_path: str):
    def request(*_args, **_kwargs):
        return {"ok": True, "result": {"file_path": file_path}}
    return request


def fake_stream(chunks: list[bytes]):
    def open_stream(*_args, **_kwargs):
        return iter(chunks)
    return open_stream


def test_download_streams_to_partial_then_atomically_renames(tmp_path):
    chunks = [b"a" * 262_144, b"b" * 262_144, b"c"]
    result = download_file_to_path(
        config=local_config(),
        file_id="file-id",
        destination=tmp_path / "source.mp4",
        expected_size=sum(map(len, chunks)),
        open_json=fake_get_file("/var/lib/telegram-bot-api/token/videos/file.mp4"),
        open_stream=fake_stream(chunks),
        free_bytes=lambda _: 10 * 1024 * 1024,
    )
    assert result.bytes_written == sum(map(len, chunks))
    assert result.sha256 == hashlib.sha256(b"".join(chunks)).hexdigest()
    assert (tmp_path / "source.mp4").read_bytes() == b"".join(chunks)
    assert not (tmp_path / "source.mp4.partial").exists()
```

- [ ] **Step 2: Run RED**

Run the focused download cases. Expected: FAIL because `download_file_to_path` is absent.

- [ ] **Step 3: Implement bounded download**

Use a dataclass receipt and a classified exception:

```python
@dataclass(frozen=True)
class DownloadReceipt:
    path: str
    bytes_written: int
    sha256: str
    lane: str
    transport: str


class MediaTransferError(RuntimeError):
    def __init__(self, reason: str):
        self.reason = str(reason or "media_transfer_failed")
        super().__init__(self.reason)
```

The implementation must open `destination.with_suffix(destination.suffix + ".partial")` with exclusive ownership, call the injected stream with redirects disabled, write at most 512-KiB chunks, update hash/progress after each write, check free-space reserve and deadline before the next write, `os.replace()` only after success, and unlink the partial in `except/finally`. Never include the request URL in `MediaTransferError`.

- [ ] **Step 4: Run GREEN and memory-shape tests**

Run all transport tests. Assert the fake stream rejects any requested read larger than 512 KiB and no production function calls `.read()` without a bounded size.

- [ ] **Step 5: Commit download transport**

```powershell
git add services/video_edit_media_transport.py tests/test_p0_videoedit_large_media_transport.py
git commit -m "feat(video-edit): stream Telegram media to workspace"
```

### Task 5: Implement streaming multipart delivery-once

**Files:**
- Modify: `services/video_edit_media_transport.py`
- Test: `tests/test_p0_videoedit_large_media_transport.py`

- [ ] **Step 1: Add RED multipart and ambiguity tests**

Test exact body length, bounded file reads, direct `sendDocument` selection for a large artifact, `sendVideo` for a compatible small artifact, deterministic 4xx fallback only, and no second request after timeout/5xx/connection loss.

```python
def sparse_mp4(path: Path, size: int) -> Path:
    with path.open("wb") as handle:
        handle.write(b"\x00\x00\x00\x18ftypmp42")
        handle.seek(max(12, int(size)) - 1)
        handle.write(b"\x00")
    return path


def small_mp4(tmp_path: Path) -> Path:
    return sparse_mp4(tmp_path / "small.mp4", 1 * MIB)


def accepted_document_receipt() -> dict:
    return {
        "ok": True,
        "result": {
            "message_id": 77,
            "document": {"file_id": "document-file-id"},
        },
    }


def raise_timeout():
    raise TimeoutError("simulated timeout without URL")


def test_large_artifact_selects_document_before_any_request(tmp_path):
    artifact = sparse_mp4(tmp_path / "large.mp4", 21 * MIB)
    calls = []
    receipt = send_artifact_from_path(
        config=local_config(),
        chat_id="123",
        artifact=artifact,
        caption="done",
        request=lambda request: calls.append(request.method_name) or accepted_document_receipt(),
    )
    assert calls == ["sendDocument"]
    assert receipt.delivery_method == "sendDocument"


def test_ambiguous_upload_is_never_retried(tmp_path):
    calls = []
    with pytest.raises(MediaTransferError, match="delivery_unknown"):
        send_artifact_from_path(
            config=local_config(),
            chat_id="123",
            artifact=small_mp4(tmp_path),
            request=lambda request: calls.append(request.method_name) or raise_timeout(),
        )
    assert calls == ["sendVideo"]
```

- [ ] **Step 2: Run RED**

Run the multipart/delivery cases. Expected: FAIL because the streaming sender is absent.

- [ ] **Step 3: Implement the multipart iterator and receipt parser**

Use fixed header/footer bytes, `artifact.stat().st_size`, and bounded file reads to compute `Content-Length` without materializing the body. Return:

```python
@dataclass(frozen=True)
class DeliveryReceipt:
    message_id: str
    file_id: str
    delivery_method: str
    bytes_sent: int
    sha256: str
```

Select the method before opening the network request. Preserve existing rules: only deterministic client rejection may trigger document fallback; all uncertain outcomes raise `delivery_unknown` and stop.

- [ ] **Step 4: Run GREEN**

Run all transport tests. Expected: PASS with no whole-file `read()`, `bytes(body)`, `bytearray` multipart, or `BytesIO` artifact path.

- [ ] **Step 5: Commit delivery transport**

```powershell
git add services/video_edit_media_transport.py tests/test_p0_videoedit_large_media_transport.py
git commit -m "feat(video-edit): stream Telegram artifact delivery"
```

### Task 6: Add SubDub-aligned long-media policy and checkpoints

**Files:**
- Create: `services/video_edit_long_media.py`
- Test: `tests/test_p0_videoedit_large_media_runtime.py`

- [ ] **Step 1: Write RED policy/checkpoint tests**

Cover stable project keys, canonical plan ordering, resource estimates, adaptive deadline ordering, segment-safe classification, whole-timeline operations, atomic checkpoint replacement, mismatched-part rejection, canonical-output recovery, and delivery-cursor fencing.

```python
def test_project_key_is_stable_for_canonical_plan_order():
    first = project_key(user_id="7", source_sha256="a" * 64, plan={"volume": 80, "speed": 1.0}, revision=4)
    second = project_key(user_id="7", source_sha256="a" * 64, plan={"speed": 1.0, "volume": 80}, revision=4)
    assert first == second


@pytest.mark.parametrize("plan", [
    {"concat_inputs": ["a.mp4", "b.mp4"]},
    {"audio_loudnorm": True},
    {"transitions": [{"kind": "crossfade"}]},
])
def test_global_operations_require_one_timeline_checkpoint(plan):
    assert classify_plan_execution(plan) == "whole_timeline_required"
```

- [ ] **Step 2: Run RED**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q tests/test_p0_videoedit_large_media_runtime.py -k "project_key or checkpoint or timeline or deadline or workspace"
```

Expected: FAIL because the module is absent.

- [ ] **Step 3: Implement minimal pure helpers**

Use canonical JSON and SHA-256:

```python
def canonical_plan_hash(plan: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(plan or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def project_key(*, user_id: str, source_sha256: str, plan: Mapping[str, Any], revision: int) -> str:
    material = f"video-edit-long-v1:{user_id}:{source_sha256}:{canonical_plan_hash(plan)}:{int(revision)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
```

Write checkpoints to a sibling temporary JSON file, flush/fsync, then `os.replace`. Validate all hashes, ranges, FFprobe evidence, project key, plan hash, and delivery cursor when loading. Do not store bot tokens, absolute Telegram URLs, or proxy secrets.

- [ ] **Step 4: Run GREEN**

Run the RED command. Expected: all pure policy/checkpoint cases pass.

- [ ] **Step 5: Commit long-media policy**

```powershell
git add services/video_edit_long_media.py tests/test_p0_videoedit_large_media_runtime.py
git commit -m "feat(video-edit): checkpoint long media jobs"
```

### Task 7: Wire file-backed inspection into the Video Edit bot flow

**Files:**
- Modify: `bot.py`
- Test: `tests/test_p0_video_edit3_canonical_intake_route_state_machine.py`

- [ ] **Step 1: Add RED bot inspection tests**

Test ownership, exact lane boundaries, unknown metadata, Local `/localfile` selection, no `download_as_bytearray`, actual-byte promotion, no render job on transfer/resource failure, concurrent-state winner preservation, saved language, and exact Back target.

```python
def test_edit3_large_upload_persists_large_lane_without_job_submission():
    first, second, state, replies, probes = _run_canonical_upload(
        "manual_edit",
        source_size=21 * 1024 * 1024,
        source_duration=30,
        inspected_size=21 * 1024 * 1024,
        inspected_duration=30.0,
    )
    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert state["media_lane"] == "large_media"
    assert state.get("local_worker_job_id") in {None, ""}


def test_edit3_long_upload_persists_large_lane_at_small_size():
    _first, _second, state, _replies, _probes = _run_canonical_upload(
        "manual_edit",
        source_size=1 * 1024 * 1024,
        source_duration=61,
        inspected_size=1 * 1024 * 1024,
        inspected_duration=61.0,
    )
    assert state["media_lane"] == "large_media"
```

Extend the existing `_run_canonical_upload` helper with the four explicit parameters shown above, defaulting to its current 1,024-byte/8-second behavior. Its fake inspector must return `media_lane = select_media_lane(...)`, actual size, and actual duration; do not create a parallel upload harness.

- [ ] **Step 2: Run RED**

Run the new bot cases with `--noconftest` where possible. Expected: current 50-MiB/30-minute validation and existing downloader behavior fail the new contract.

- [ ] **Step 3: Integrate only `inspect_video_editor_source` and Video Edit upload copy**

Build transport config from existing Telegram Local Bot API constants, pass an inspection destination, call the file-backed downloader, probe/hash the path, call `validate_source_metadata(..., maximum_bytes=0, maximum_duration_seconds=0)`, and persist `media_lane` plus actual evidence in canonical Video Edit state. Leave SelfShot, Product Video, Frame Video, SubDub, generic media cache, and all other upload handlers unchanged.

- [ ] **Step 4: Run GREEN and concurrency regressions**

Run the new runtime cases plus current Video Edit upload/state-guard/canonical-navigation suites. Expected: all pass, including concurrent winner preservation and no duplicate panels.

- [ ] **Step 5: Commit bot inspection**

```powershell
git add bot.py tests/test_p0_video_edit3_canonical_intake_route_state_machine.py
git commit -m "feat(video-edit): inspect large media through Local Bot API"
```

### Task 8: Wire worker download, liveness, rendering, and delivery

**Files:**
- Modify: `bot.py`
- Modify: `local_worker.py`
- Modify: `services/video_editengine1.py`
- Modify: `services/video_edit_long_media.py`
- Test: `tests/test_p0_videoedit_canonical_local_worker_receipt.py`
- Test: `tests/test_p0_videoedit_job_safety.py`

- [ ] **Step 1: Add RED worker tests**

Test Local endpoint/secret propagation, source/concat/logo/subtitle file-backed downloads, actual-metadata lane promotion, adaptive timeout, one job-specific heartbeat loop, outbox lease renewal, stale-owner and terminal fencing, whole-timeline versus segment-safe execution, validated checkpoint reuse, direct document selection, durable receipt order, partial multi-output resume, and ambiguous-delivery no-resend.

```python
def test_video_edit_worker_large_media_uses_local_transport_and_document_delivery(monkeypatch, tmp_path):
    evidence: dict = {"downloads": [], "deliveries": [], "full_file_reads": 0}
    terminal, _captions = _run_job(
        monkeypatch,
        tmp_path,
        mode="manual",
        payload_patch={"media_lane": "large_media", "source_file_size": 21 * 1024 * 1024},
        downloaded_probe={
            "ok": True,
            "reason": "",
            "duration": 90.0,
            "duration_ms": 90_000,
            "width": 1280,
            "height": 720,
            "has_video": True,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
            "bytes": 21 * 1024 * 1024,
        },
        transport_evidence=evidence,
    )
    receipt = json.loads(terminal["output_url"])
    assert evidence["downloads"] == ["local_bot_api"]
    assert evidence["deliveries"] == ["sendDocument"]
    assert receipt["delivery_message_id"]
    assert receipt["delivery_file_id"]
    assert evidence["full_file_reads"] == 0


def test_video_edit_outbox_lease_rejects_live_competitor_and_terminal_update():
    conn = _conn()
    created = _create(conn)
    worker_job_id = created["local_worker_job_id"]
    assert video_editengine1.renew_worker_lease(
        conn,
        worker_job_id=worker_job_id,
        lease_owner="worker-a",
        now="2026-08-02 10:00:00",
        lease_expires_at="2026-08-02 10:05:00",
    ) is True
    assert video_editengine1.renew_worker_lease(
        conn,
        worker_job_id=worker_job_id,
        lease_owner="worker-b",
        now="2026-08-02 10:01:00",
        lease_expires_at="2026-08-02 10:06:00",
    ) is False
    conn.execute("UPDATE video_edit_jobs SET status='delivered' WHERE local_worker_job_id=?", (worker_job_id,))
    conn.commit()
    assert video_editengine1.renew_worker_lease(
        conn,
        worker_job_id=worker_job_id,
        lease_owner="worker-a",
        now="2026-08-02 10:02:00",
        lease_expires_at="2026-08-02 10:07:00",
    ) is False
```

Extend the existing `_run_job` helper with `transport_evidence: dict | None = None`. When provided, patch the new `download_file_to_path` and `send_artifact_from_path` functions with file-backed fakes that append the transport/method evidence and return real `DownloadReceipt`/`DeliveryReceipt` values. Keep all existing `_run_job` callers byte-for-byte compatible.

Update the helper's existing `observe_source_validation` fake to accept and forward `maximum_bytes` and `maximum_duration_seconds`; otherwise the integration test would fail because of a stale test-double signature rather than production behavior:

```python
def observe_source_validation(metadata: dict, *, file_size: int = 0, **limits) -> dict:
    if source_validation_calls is not None:
        source_validation_calls.append({"metadata": deepcopy(metadata), "file_size": file_size, **limits})
    return original_validate_source_metadata(metadata, file_size=file_size, **limits)
```

- [ ] **Step 2: Run RED**

Run worker-focused nodes only. Expected: hard-coded Cloud URLs, fixed timeouts, and RAM-buffered delivery violate the new assertions.

- [ ] **Step 3: Replace only Video Edit transport calls**

In `_local1_download_asset`, call `download_file_to_path` with the asset-specific byte policy, workspace reserve, progress callback, and job deadline. In `run_video_local_edit`, derive the project key/deadline, start a bounded per-job liveness context, classify the plan, reuse only validated checkpoints, run the existing FFmpeg functions, then call `send_artifact_from_path` and persist each existing receipt before continuing.

Add `video_editengine1.renew_worker_lease(...)` over the existing `video_edit_outbox.lease_owner` and `lease_expires_at` columns. The SQL update must require the matching `local_worker_job_id`, a nonterminal Video Edit job, an outbox status in `pending/running`, and either an empty owner, the same owner, or an expired lease. Return `False` when another unexpired owner or a terminal job wins.

Extend `/internal/worker/job_update` only for `video_local_edit` with `lease_seconds` and a bounded `stage`. Before accepting a running or terminal update, renew/verify the outbox lease for the authenticated worker ID; return HTTP 409 on stale ownership. The liveness writer posts the current real stage at a bounded interval, never changes artifact receipts, and stops before terminal receipt persistence. Do not alter unrelated worker routes.

- [ ] **Step 4: Run GREEN and real-media fixtures**

Run all new worker cases, existing `video_local_edit`/manual/split/overlay/logo/watermark/receipt/job-safety suites, and deterministic real-media fixtures. Expected: zero branch-only failures; peak-memory evidence stays bounded independently of artifact size.

- [ ] **Step 5: Commit worker integration**

```powershell
git add bot.py local_worker.py services/video_editengine1.py services/video_edit_long_media.py tests/test_p0_videoedit_canonical_local_worker_receipt.py tests/test_p0_videoedit_job_safety.py
git commit -m "feat(video-edit): process large media with durable streaming"
```

### Task 9: Close UI truth, Back hierarchy, and regression matrix

**Files:**
- Modify: `bot.py`
- Modify: `tests/test_p0_videoedit_canonical_bot_routes.py`
- Verify: `services/video_edit_state_machine.py`

- [ ] **Step 1: Add RED copy and route assertions**

Assert no Video Edit public copy promises fixed 50 MB/30 minutes, unlimited processing, or Cloud capacity. Assert the capability message explains automatic short/large routing and every failure uses the current Video Edit Back target. Assert all callback data remains in `videoedit|` except existing main-menu Back.

- [ ] **Step 2: Run RED then implement minimal copy**

Use saved language. Vietnamese copy should state: “Video ngắn được xử lý theo luồng nhanh; video dài hoặc dung lượng lớn tự chuyển sang luồng xử lý media lớn. Hệ thống kiểm tra khả năng xử lý trước khi nhận việc.” Do not expose secret headers, internal cap values, host paths, or fake percentages.

- [ ] **Step 3: Run the ordered Video Edit matrix**

Run, one process at a time, the callback follow-up, large-media focused tests, canonical routes, job safety, manual/split, overlays/logo/watermark, status/receipt/idempotency, real-media fixtures, accepted Video Edit regression, clean-main comparator, branch comparator, and changed-module compile. Record exact node counts, runtime, failure set, and node delta.

- [ ] **Step 4: Static scope audit**

Run:

```powershell
git diff --check
git status --short
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
rg -n "subdub_|wallet|payos|product_video|frame_video" services/video_edit_media_transport.py services/video_edit_long_media.py tests/test_p0_videoedit_large_media_transport.py tests/test_p0_videoedit_large_media_runtime.py
```

Expected: no changed SubDub/Product/Frame/wallet/PayOS/provider/schema file; incidental string assertions are explained.

### Task 10: Review, PR, merge, deploy, and live evidence

**Files:**
- Review: all branch changes
- Evidence: PR checks, deployed SHA, Telegram receipts, no committed secret

- [ ] **Step 1: Rebase onto exact latest main and rerun all gates**

Fetch `origin`, record the new main SHA, rebase without whole-file conflict resolution, verify upstream RouteEngine/SubDub symbols remain present, then rerun the entire ordered matrix and compile.

- [ ] **Step 2: Obtain independent spec review**

Reviewer must verify exact 60-second/20-MiB routing, single production origin, SubDub lifecycle parity, no SubDub modification/import, no proportional RAM, no arbitrary public rejection, durable fencing, delivery ambiguity, and scope.

- [ ] **Step 3: Obtain independent code-quality review**

Resolve every Critical/Important finding with a fresh RED/GREEN cycle. Rerun affected tests and the final matrix after the last code change.

- [ ] **Step 4: Push one non-draft PR**

Push only the large-media branch, open one non-draft PR, and require source compile/CI/review to pass. Merge only because the owner has authorized automatic completion after tests; do not merge with any unresolved branch-only failure or unknown deployed SHA.

- [ ] **Step 5: Verify Railway and Local Bot API liveness**

Prove the deployed SHA matches the merge commit and `https://bot-production-2dd7.up.railway.app/health` is live. Verify `tg.toanaas.vn` through existing authenticated operational evidence without printing tokens or proxy secrets.

- [ ] **Step 6: Run owner-authorized Telegram live matrix**

Use Telegram Web and the production bot:

1. `/start` and navigate only to Video Edit.
2. Run one small control at or below both thresholds.
3. Run one file above 20 MiB or above 60 seconds through the large-media lane.
4. Use only a free local Video Edit operation; no provider, Xu, wallet, PayOS, or recovery command.
5. Verify exact Back hierarchy, real stage progression, validated MP4, delivery method, message/file receipt, no duplicate delivery, and workspace cleanup.
6. Record declared/actual bytes, duration, source/output SHA-256, peak worker memory, elapsed time, merge/deployed SHA, and Telegram message ID.

- [ ] **Step 7: Apply strict completion wording**

Claim `VIDEO EDIT LARGE-MEDIA LIVE PASS` only when the deployed merge SHA, actual large-lane classification, validated MP4, Telegram receipt, bounded-memory evidence, and no duplicate delivery are all proven. Otherwise preserve the exact blocker and continue repairing within Video Edit scope.
