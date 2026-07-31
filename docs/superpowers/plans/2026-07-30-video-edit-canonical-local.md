# Video Edit Canonical Local Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every public control inside `🛠️ Chỉnh sửa / Nâng cấp video` useful and truthful by routing it through one Vietnamese-first, local FFmpeg editor with exact navigation, validated MP4 delivery, and zero wallet/provider activity.

**Architecture:** Keep `videoedit|` as the sole callback namespace and `video_editor:<user_id>` as the sole conversational state. Compile manual, local-assistant, and quality choices into the existing `manual_edit_plan`, submit exactly once to `video_editengine1` / `video_local_edit`, and validate the resulting artifact before delivery truth. The independent `lvs27b` planning preview remains unchanged and does not hand state to Video Edit.

**Tech Stack:** Python 3.11, python-telegram-bot callback handlers, SQLite job/outbox contracts, local worker, FFmpeg/ffprobe, pytest.

**Interaction-reference boundary:** CapCut may inform only the familiar grouping
of simple tools and the short select → review → run flow. Do not copy its
timeline, keyframes, templates/assets, cloud AI, or app-only gestures into the
Telegram bot.

---

## Research alignment and explicit deferrals

The owner-supplied architecture recommends a declarative edit graph, explicit statechart navigation, local-free jobs, application-level idempotency, durable checkpoints/outbox, and receipt-before-accounting. This plan adopts those parts using the repository's existing SQLite queue, worker lease, `video_editengine1`, and Telegram receipt contract.

This branch does **not** add PostgreSQL, Redis, RabbitMQ, Kafka, S3/MinIO, CDN, Kubernetes, WebRTC, GStreamer, provider-paid execution, or a planning-to-editor handoff. Those are separate infrastructure/product gates and are not required to make the current local editor real.

## File map

- Modify `bot.py`: Video Edit text/keyboards/callbacks, explicit parent routing, local confirmation/submit, zero-price worker update; one narrow saved-language fix for `lvs27b` root Back.
- Modify `services/video_edit_state_machine.py`: allow-listed screen/parent transitions and callback-safe navigation helpers.
- Modify `services/video_edit_capabilities.py`: expose only locally executable actions and compile deterministic assistant/quality selections to local plan fields.
- Modify `services/video_local_editing.py`: normalize/build/execute the approved local filter fields.
- Modify `services/video_editengine1.py`: validate the `local-free` package and finish zero-price receipt state without a charge claim.
- Modify `local_worker.py`: consume only the new local plan fields while preserving delivery and receipt truth.
- Create `tests/test_p0_videoedit_canonical_navigation.py`: public callback, Vietnamese, parent, stale/duplicate and isolation tests.
- Create `tests/test_p0_videoedit_canonical_local_runtime.py`: plan/capability/FFmpeg real-media tests.
- Create `tests/test_p0_videoedit_local_free_job.py`: confirm/idempotency/outbox/no-wallet/receipt tests.
- Keep `services/local_video_studio_public.py`, Product Video, SubDub, Frame Video, provider adapters, shared `video_tail9`, Railway/VPS, PayOS, wallet and webhook files unchanged.

### Task 1: Lock the public route and explicit parent model

**Files:**
- Modify: `services/video_edit_state_machine.py`
- Create: `tests/test_p0_videoedit_canonical_navigation.py`

- [ ] **Step 1: Write the failing route-contract tests**

Add tests that require an allow-listed parent for every canonical screen and reject a parent outside `videoedit|` except the two root exits:

```python
from services import video_edit_state_machine as machine


def test_videoedit_parent_matrix_is_exact():
    assert machine.parent_callback("workspace", lane="manual_edit") == "videoedit|manual"
    assert machine.parent_callback("cut") == "videoedit|workspace"
    assert machine.parent_callback("trim_input") == "videoedit|cut"
    assert machine.parent_callback("join") == "videoedit|workspace"
    assert machine.parent_callback("concat_input") == "videoedit|join"
    assert machine.parent_callback("transform") == "videoedit|workspace"
    assert machine.parent_callback("rotation_value") == "videoedit|transform"
    assert machine.parent_callback("review") == "videoedit|workspace"
    assert machine.parent_callback("confirmation") == "videoedit|review"


def test_videoedit_parent_callback_fails_closed():
    assert machine.safe_parent_callback("vproduct|open|product_video") == "videoedit|hub"
    assert machine.safe_parent_callback("subdub|menu") == "videoedit|hub"
    assert machine.safe_parent_callback("menu|main_video", root=True) == "menu|main_video"
```

Add one public keyboard audit that constructs every Video Edit keyboard and asserts every row satisfies the current adaptive-row contract, every callback is non-empty, and no row repeats callback data. This must reproduce the current one-button Brightness review row and the duplicate `videoedit|hub` legacy redirect before implementation.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m pytest -q tests/test_p0_videoedit_canonical_navigation.py
```

Expected: FAIL because `parent_callback` and `safe_parent_callback` do not exist.

- [ ] **Step 3: Implement the minimal pure navigation contract**

Add immutable parent maps and helpers to `services/video_edit_state_machine.py`:

```python
_SCREEN_PARENTS = {
    "cut": "videoedit|workspace",
    "trim_input": "videoedit|cut",
    "split": "videoedit|cut",
    "split_input": "videoedit|split",
    "join": "videoedit|workspace",
    "concat_input": "videoedit|join",
    "reorder_input": "videoedit|join",
    "frame": "videoedit|workspace",
    "transform": "videoedit|workspace",
    "rotation_value": "videoedit|transform",
    "audio": "videoedit|workspace",
    "audio_input": "videoedit|audio",
    "color": "videoedit|workspace",
    "overlay": "videoedit|workspace",
    "text_input": "videoedit|overlay",
    "logo_input": "videoedit|overlay",
    "srt_input": "videoedit|overlay",
    "effects": "videoedit|workspace",
    "effect_detail": "videoedit|effects",
    "source_info": "videoedit|workspace",
    "review": "videoedit|workspace",
    "confirmation": "videoedit|review",
}


def safe_parent_callback(value: Any, *, root: bool = False) -> str:
    callback = str(value or "").strip()
    if callback.startswith("videoedit|"):
        return callback
    if root and callback in {"menu|main_video", "menu|main"}:
        return callback
    return "videoedit|hub"


def parent_callback(screen: Any, *, lane: Any = "") -> str:
    key = str(screen or "").strip().lower()
    if key == "workspace":
        return lane_callback(lane)
    return _SCREEN_PARENTS.get(key, "videoedit|hub")
```

The state contract must also reject unknown requested operation keys. A plan field that the normalizer does not understand is an error, not something it may silently discard while still delivering an unchanged MP4.

- [ ] **Step 4: Run the navigation tests and verify GREEN**

Run the same pytest command. Expected: all Task 1 tests PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add services/video_edit_state_machine.py tests/test_p0_videoedit_canonical_navigation.py
git commit -m "test(video-edit): lock canonical parent routes"
```

### Task 2: Replace obsolete/dead routes with the canonical Vietnamese workspace

**Files:**
- Modify: `bot.py`
- Modify: `tests/test_p0_videoedit_canonical_navigation.py`

- [ ] **Step 1: Write failing public-seam tests**

Cover these exact behaviors with the existing fake query adapter:

```python
def test_video_enhance_command_opens_canonical_hub():
    text, callbacks = run_video_enhance_command(language="vi")
    assert "Chỉnh sửa / Nâng cấp video" in text
    assert callbacks[:4] == [
        "videoedit|ai", "videoedit|manual", "videoedit|restore", "videoedit|guide"
    ]


def test_legacy_compress_opens_resolution_group_without_duplicate_callback():
    result = press("videoedit|compress", ready_manual_state())
    assert result.callback_error is None
    assert result.callbacks.count("videoedit|workspace") == 1
    assert "Độ phân giải" in result.text


def test_cut_legacy_entry_opens_cut_not_join():
    result = press("videoedit|cut", ready_manual_state())
    assert "Cắt & chia đoạn" in result.text
    assert "Ghép" not in result.heading


def test_lvs27b_root_back_uses_saved_ui_language(monkeypatch):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    result = press_lvs27b_root_back(telegram_language="en")
    assert "Chỉnh sửa / Nâng cấp video" in result.text
    assert "Edit / enhance video" not in result.text
```

Also assert no public Video Edit text includes raw internal tokens such as `LOCAL_PLANNING_READY`, `standard_cut`, `provider_task_id`, or an absolute private path.

- [ ] **Step 2: Verify RED**

Run only the four tests above. Expected failures: obsolete command menu, `compress` duplicate-row exception, wrong `cut` redirect, and English hub on 27B Back.

- [ ] **Step 3: Implement compatibility mapping and saved-language return**

In `bot.py`:

- Make `/video_enhance` call the same hub renderer as `videoedit|hub`.
- Replace the current compact Manual options keyboard with one canonical workspace whose Vietnamese rows are exactly:

```python
[
    [("✂️ Cắt & chia đoạn", "videoedit|cut"), ("🧩 Ghép & sắp xếp", "videoedit|join")],
    [("📐 Khung hình & kích thước", "videoedit|frame"), ("🔄 Tốc độ, xoay & lật", "videoedit|transform")],
    [("🔊 Âm thanh", "videoedit|audio"), ("🎨 Ánh sáng & màu", "videoedit|color")],
    [("🔠 Chữ, logo & phụ đề", "videoedit|overlay"), ("✨ Hiệu ứng local", "videoedit|effects")],
    [("ℹ️ Thông tin video", "videoedit|source_info"), ("📋 Xem lại", "videoedit|review")],
    [("⬅️ Quay lại", "videoedit|manual"), ("🏠 Menu chính", "menu|main")],
]
```

Every row must pass the existing adaptive-row validator and every callback must have exactly one `videoedit|` owner.
- Replace the early legacy redirect block with a canonical group map:

```python
VIDEO_EDIT_LEGACY_GROUP = {
    "cut": "cut",
    "resize": "frame",
    "crop": "frame",
    "ratio": "frame",
    "vertical": "frame",
    "compress": "resolution",
    "resolution": "resolution",
    "color": "color",
    "preset": "color",
    "brightness": "color",
    "text": "overlay",
    "logo": "overlay",
    "srt": "overlay",
    "subtitle": "overlay",
    "volume": "audio",
    "audio": "audio",
    "sharpen": "quality",
}
```

- When no source exists, persist `requested_group` and request upload. When a valid inspected source exists, render that exact group.
- Use `get_user_language(user_id)` when `lvs27b` root returns to the hub; do not change `lvs27b` state, callbacks, summary or actions.
- Ensure each keyboard row has distinct non-empty callback data.
- Make the Brightness keyboard's final row valid by pairing `✅ Xem lại` with its exact Back action; do not weaken the shared keyboard validator.
- Pass the exact caller when Guide or Source Info is opened from AI, Manual, Quality, Cut, Join or another child. No `menu|guide_video_ai` route may leave the `videoedit|` product unexpectedly.

- [ ] **Step 4: Verify GREEN and existing hub freeze**

Run:

```powershell
python -m pytest -q tests/test_p0_videoedit_canonical_navigation.py tests/test_p1_localvideostudio27b_public_ui.py
```

Expected: new tests PASS; existing 27B hub order/flag behavior remains PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add bot.py tests/test_p0_videoedit_canonical_navigation.py
git commit -m "fix(video-edit): route legacy actions to real local tools"
```

### Task 3: Make every Back edge return to the exact invoking parent

**Files:**
- Modify: `bot.py`
- Modify: `services/video_edit_state_machine.py`
- Modify: `tests/test_p0_videoedit_canonical_navigation.py`

- [ ] **Step 1: Add a parameterized failing Back matrix**

```python
@pytest.mark.parametrize(
    ("open_callback", "back_callback"),
    [
        ("videoedit|manual_cut", "videoedit|workspace"),
        ("videoedit|trim_edges", "videoedit|cut"),
        ("videoedit|split_from_manual", "videoedit|cut"),
        ("videoedit|manual_join", "videoedit|workspace"),
        ("videoedit|concat", "videoedit|join"),
        ("videoedit|reorder", "videoedit|join"),
        ("videoedit|manual_rotate_flip", "videoedit|transform"),
        ("videoedit|rotation", "videoedit|transform"),
        ("videoedit|manual_audio", "videoedit|workspace"),
        ("videoedit|audio_custom", "videoedit|audio"),
        ("videoedit|manual_effects", "videoedit|workspace"),
        ("videoedit|source_info", "videoedit|workspace"),
        ("videoedit|review", "videoedit|workspace"),
        ("videoedit|confirm_local", "videoedit|review"),
    ],
)
def test_videoedit_back_matrix(open_callback, back_callback):
    result = press(open_callback, ready_manual_state())
    assert back_callback in result.callbacks
```

Add tests for source-info invoked from Cut and Join, asserting Back returns to the actual caller rather than always Workspace.

Add AI Source and Guide caller cases. A caller stored for one screen must not be reused by a sibling screen.

- [ ] **Step 2: Verify RED**

Expected failures include trim, concat/reorder, rotation/flip and source-info parent loss.

- [ ] **Step 3: Persist exact parent before rendering each child**

Use one helper in `bot.py`:

```python
def update_video_editor_screen(user_id, screen_id, *, parent_callback, **fields):
    parent = video_edit_state_machine.safe_parent_callback(parent_callback)
    return update_video_editor_pending(
        user_id,
        screen_id,
        current_screen=screen_id,
        parent_callback=parent,
        **fields,
    )
```

Every child keyboard reads `parent_callback` from the committed state. `source_info` stores the invoking callback. Remove the unreachable second `if action == "review"` and keep one guarded review edge.

- [ ] **Step 4: Verify GREEN plus stale/malformed behavior**

Add and run tests proving a missing/foreign parent fails to `videoedit|hub`, stale state requests a new upload, and malformed callbacks create no state/job.

- [ ] **Step 5: Commit Task 3**

```powershell
git add bot.py services/video_edit_state_machine.py tests/test_p0_videoedit_canonical_navigation.py
git commit -m "fix(video-edit): preserve exact back hierarchy"
```

### Task 4: Expand the local edit plan with only verified FFmpeg operations

**Files:**
- Modify: `services/video_local_editing.py`
- Modify: `local_worker.py`
- Create: `tests/test_p0_videoedit_canonical_local_runtime.py`

- [ ] **Step 1: Write failing plan and command tests**

Require exact normalized fields:

```python
plan.update({
    "audio_normalization": "loudnorm",
    "quality_filters": {"sharpen": True, "denoise": True},
    "local_effects": {"fade_in_ms": 300, "fade_out_ms": 400, "vignette": True, "slow_zoom": True},
})
normalized = editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)
assert normalized["audio_normalization"] == "loudnorm"
assert normalized["quality_filters"] == {"sharpen": True, "denoise": True}
assert normalized["local_effects"]["fade_in_ms"] == 300
```

Command tests must find `loudnorm`, `unsharp`, `hqdn3d`, `fade`, `vignette`, and a bounded zoom expression only when selected. Invalid durations or unknown effect/filter keys must raise exact `LocalVideoEditError` reasons.

Add an explicit RED test that passes an unknown top-level operation key and asserts `unknown_edit_plan_field`; the current merge-and-allowlist behavior silently drops such keys and can otherwise create fake success.

- [ ] **Step 2: Verify RED**

Run the new runtime test file. Expected: fields are absent or ignored.

- [ ] **Step 3: Implement normalization and filter compilation**

Extend `default_manual_edit_plan` with disabled defaults:

```python
"audio_normalization": "none",
"quality_filters": {"sharpen": False, "denoise": False},
"local_effects": {
    "fade_in_ms": 0,
    "fade_out_ms": 0,
    "vignette": False,
    "slow_zoom": False,
},
```

Validate every field with bounded numeric values. Compile selected filters into the existing argument array without a shell. Add `loudnorm` to the audio filter chain only when audio exists. Keep output H.264/AAC MP4 and preserve the existing partial-file/final-validation transaction.

Implement one filter-discovery helper using `ffmpeg -hide_banner -filters`, cached by the resolved FFmpeg binary path. The worker must re-check requested filters before execution. If the worker heartbeat can safely carry an optional `video_edit_filters` field, publish the discovered set without changing another product's readiness; otherwise keep the UI conservative and let the worker fail closed before rendering. UI and executor must never assume that the test machine and production worker have identical filters.

Implement `remove_middle` as one joined MP4, not a set of unrelated delivered clips. Validate the removed interval inside the selected trim, render the two kept intervals to normalized intermediates, concatenate in order, and validate the resulting duration. Do not reset the user's requested trim after concat; compute the timeline from the actual selected clips. Extend `expected_manual_duration_ms` to include kept intervals, concatenated clip duration and any future transition overlap.

Crossfade remains hidden until a two-clip real-media test proves a stable `xfade`/audio transition pipeline; do not expose it merely because the FFmpeg filter exists.

- [ ] **Step 4: Add real-media tests and verify GREEN**

Generate 2–4 second `testsrc2` + sine fixtures and prove each selected operation produces a non-empty validated MP4 with expected duration/dimensions/audio policy. If `hqdn3d` is absent, test the same preflight used by the UI and assert the capability is hidden, not failed after confirmation.

The real-media matrix must cover the complete already-advertised editor, not only the newly added filters:

- trim start/end and an arbitrary keep range;
- remove-middle as one joined MP4 with the removed interval absent;
- fixed-duration, exact-count and custom split coverage;
- two-clip concat and persisted reorder;
- crop/fit for 9:16, 16:9, 1:1 and 4:5 at keep/720p/1080p;
- speed 0.5x through 2x with matching audio duration;
- rotation and horizontal/vertical flip;
- mute, bounded volume and available loudness normalization;
- brightness, every public color preset, sharpen and available denoise;
- Vietnamese text, logo placement/opacity and validated SRT burn-in;
- fade, vignette and slow zoom when their runtime filter preflight passes.

For concat/reorder/remove-middle/crossfade fixtures, use distinguishable color clips and audio frequencies, then sample the first/middle/last output regions. Duration alone is insufficient proof of requested ordering.

- [ ] **Step 5: Commit Task 4**

```powershell
git add services/video_local_editing.py local_worker.py tests/test_p0_videoedit_canonical_local_runtime.py
git commit -m "feat(video-edit): add verified local quality and effects"
```

### Task 5: Make Manual, local assistant, and Quality lanes compile to the same plan

**Files:**
- Modify: `services/video_edit_capabilities.py`
- Modify: `bot.py`
- Modify: `tests/test_p0_videoedit_canonical_navigation.py`
- Modify: `tests/test_p0_videoedit_canonical_local_runtime.py`

- [ ] **Step 1: Write failing capability truth tests**

```python
def test_every_actionable_capability_has_local_plan_mapping():
    for item in capabilities.public_actionable_capabilities():
        assert item["enabled"] is True
        assert item["execution_owner"] == "video_local_editing"
        assert item["local_or_provider"] == "local"
        assert capabilities.plan_patch(item["feature_key"])


def test_provider_only_effects_are_not_actionable():
    keys = {item["feature_key"] for item in capabilities.capabilities_for("effects")}
    assert not keys & {"effect_parallax", "effect_particles", "effect_moving_light", "effect_light_outline"}
```

Add assistant tests for Vietnamese intent strings such as `làm sáng, rõ và âm lượng đều`, `video dọc TikTok`, and an unsupported `tạo phép thuật/parallax`, requiring deterministic local patches or a truthful no-job explanation.

- [ ] **Step 2: Verify RED**

Expected: provider-guarded effects are currently enabled and restore selections route through AI/provider suggestions instead of a local plan.

- [ ] **Step 3: Add explicit plan patches and local intent compiler**

In `services/video_edit_capabilities.py`, define local mappings such as:

```python
LOCAL_PLAN_PATCHES = {
    "enhance_basic_sharpen": {"quality_filters": {"sharpen": True}},
    "enhance_light_color": {"color_preset": "bright_clear"},
    "enhance_denoise": {"quality_filters": {"denoise": True}},
    "audio_loudnorm": {"audio_normalization": "loudnorm"},
    "effect_fade": {"local_effects": {"fade_in_ms": 300, "fade_out_ms": 300}},
    "effect_vignette": {"local_effects": {"vignette": True}},
    "effect_slow_zoom": {"local_effects": {"slow_zoom": True}},
}
```

Merge nested patches without deleting prior choices. Filter UI actions through runtime preflight. `videoedit|restore_pick` and locally supported assistant suggestions update `manual_edit_plan` and return to the same Workspace/Review path; they never open an invoice. Unsupported generative intent renders Vietnamese alternatives and no confirm button.

Rewrite `video_edit_guide_text` so it lists only the operations in the real-media matrix, explains the 50 MB/source limits, `0 Xu`, MP4 validation, audio-stem truth, and which provider-only transformations are unavailable. Do not mention an invoice or paid provider in the public local editor guide.

- [ ] **Step 4: Verify all three lanes use the same plan**

Run tests proving Manual, assistant and Quality produce equivalent plan patches for the same local operation, provider-call count remains zero, and no route enters Product Video/SubDub/Frame Video.

- [ ] **Step 5: Commit Task 5**

```powershell
git add services/video_edit_capabilities.py bot.py tests/test_p0_videoedit_canonical_navigation.py tests/test_p0_videoedit_canonical_local_runtime.py
git commit -m "feat(video-edit): compile every public lane to local plan"
```

### Task 6: Replace the shared commercial tail with local-free confirmation

**Files:**
- Modify: `bot.py`
- Modify: `services/video_editengine1.py`
- Create: `tests/test_p0_videoedit_local_free_job.py`

- [ ] **Step 1: Write failing confirmation/job/accounting tests**

Require:

```python
def test_local_confirmation_is_zero_xu_and_has_one_confirm():
    view = render_confirmation(ready_manual_state())
    assert "0 Xu" in view.text
    assert view.callbacks.count("videoedit|confirm_local") == 1
    assert "video_tail|" not in view.callbacks


def test_local_free_job_is_idempotent_and_has_empty_tail(conn):
    first = submit_ready_local_edit(conn)
    second = submit_ready_local_edit(conn)
    assert first["created"] is True
    assert second["created"] is False
    job = video_editengine1.get_job_by_worker_id(conn, first["local_worker_job_id"])
    assert job["quality_tier_id"] == "local-free"
    assert job["price_xu"] == 0
    assert job["tail"] == {}
    assert count_worker_jobs(conn) == 1


def test_zero_price_delivery_never_claims_wallet(monkeypatch):
    wallet_calls = []
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *a, **k: wallet_calls.append((a, k)))
    deliver_zero_price_worker_update()
    assert wallet_calls == []
    assert canonical_job()["status"] == "delivered"
    assert canonical_job()["charge_state"] == "not_charged"
    assert canonical_job()["charged_xu"] == 0
```

- [ ] **Step 2: Verify RED**

Expected failures: review enters `video_tail9`, submit rejects `price_xu <= 0`, and worker-update claims the charge before checking zero price.

- [ ] **Step 3: Implement dedicated local confirmation and submit**

`videoedit|review` renders a Video Edit-specific summary. `videoedit|confirm_local` is the only creation edge and requires source, inspection, review state and unchanged revision.

Intercept legacy `video_tail|` callbacks while their owner/route marker is
Video Edit and migrate them to the canonical local Review/Status screen before
any commercial invoice or balance gate. Stale markers without a source must
show upload recovery and must not create editor state or enter Product Video.

Call `video_editengine1.create_job` with:

```python
tail={}
quality_tier_id="local-free"
price_xu=0
worker_payload={
    **payload,
    "price_xu": 0,
    "quoted_price_xu": 0,
    "charge_policy": "free_local_tool",
    "provider_call": False,
}
```

In `handle_video_local_edit_worker_job_update`, compute price before claiming:

```python
price_xu = max(0, safe_int(canonical.get("price_xu"), 0))
should_charge = bool(
    canonical.get("status") == "delivered"
    and price_xu > 0
    and video_editengine1.claim_charge(conn, worker_job_id=worker_job_id)
)
```

Do not change shared `video_tail9` or wallet functions.

Update Video Edit worker receipt/caption truth for the free package: `charge_policy="free_local_tool"`, `charge_status="not_required_free"`, `charged_xu=0`, and Vietnamese copy that says the tool is free. The current generic caption saying a fee is recorded after delivery must not remain on a zero-price job.

- [ ] **Step 4: Verify GREEN and receipt truth**

Run the new file plus `tests/test_p0_video_editengine1_local_render_status_delivery.py`. A delivered free job remains `delivered`, receipt fields are present, and zero wallet calls occur.

- [ ] **Step 5: Commit Task 6**

```powershell
git add bot.py services/video_editengine1.py tests/test_p0_videoedit_local_free_job.py
git commit -m "fix(video-edit): submit local jobs free without wallet"
```

### Task 7: Complete transaction, stale-state and duplicate-callback safety

**Files:**
- Modify: `bot.py`
- Modify: `services/video_editengine1.py`
- Modify: `tests/test_p0_videoedit_canonical_navigation.py`
- Modify: `tests/test_p0_videoedit_local_free_job.py`

- [ ] **Step 1: Write failing transaction tests**

Test successful edit commits state only after `safe_edit_or_send` succeeds; failed UI edit keeps the previous valid state; duplicate `confirm_local` reuses the existing job; stale confirmation creates no job; status refresh is read-only; deleted state does not resurrect; a user cannot access another user's job.

Add malformed `videoedit|set|...` cases for arbitrary aspect/resolution/flip/color strings, non-numeric rotation, `nan`/`inf` speed or volume, and invalid logo opacity. Each must alert/fail closed without changing the prior plan or screen.

- [ ] **Step 2: Verify RED**

Run only transaction tests and record each expected failure reason.

- [ ] **Step 3: Implement bounded callback claims and fail-closed state transitions**

Store a bounded list of handled callback IDs only around the final confirm edge. Commit screen state after successful Telegram rendering. Preserve the database idempotency key as the authoritative duplicate guard. Status callbacks read the existing job and never submit, charge or deliver.

For navigation callbacks, derive a candidate state first, render the candidate view, and persist it only after the Telegram edit/reply succeeds. Do not leave state on `brightness`, `await_*`, review or another child after a keyboard/render exception.

Keep rollback local to `handle_video_editor_callback`; do not extend the shared
Product Video failure guard. A successful Video Edit route must order its
transaction as Telegram render → state commit/deletion → callback answer.

Before queue insertion, require a non-empty matching worker/filter worker ID,
matching normalized worker/filter FFmpeg path, valid local mode, an observable
operation or structurally valid split ranges, and non-negative exact price
truth. Duplicate idempotency hits must also match chat, tier, price, and tail.
The final receipt must carry positive duration/dimensions, MP4 container, H.264,
hash/size, Telegram IDs, and exact `free_local_tool` / `not_required_free` /
`charged_xu=0` fields.

- [ ] **Step 4: Verify GREEN and no fake success**

Assert no public success text is emitted without a validated receipt, no exception routes to another product, and all failure paths state `chưa tạo tác vụ` / `chưa trừ Xu` truthfully.

- [ ] **Step 5: Commit Task 7**

```powershell
git add bot.py services/video_editengine1.py tests/test_p0_videoedit_canonical_navigation.py tests/test_p0_videoedit_local_free_job.py
git commit -m "fix(video-edit): make confirm and status idempotent"
```

### Task 8: Full verification, independent reviews, and ship gate

**Files:**
- Modify only if a verified review finding requires a narrow fix.

- [ ] **Step 1: Run focused Video Edit tests**

```powershell
python -m pytest -q tests/test_p0_videoedit_canonical_navigation.py
python -m pytest -q tests/test_p0_videoedit_canonical_local_runtime.py
python -m pytest -q tests/test_p0_videoedit_local_free_job.py
python -m pytest -q tests/test_p0_video_local1_manual_editing_smart_splitter.py tests/test_p0_video_editengine1_local_render_status_delivery.py tests/test_p0_video_storyboard_image_output_brightness_route.py
```

- [ ] **Step 2: Run isolation regressions**

```powershell
python -m pytest -q tests/test_p1_localvideostudio27a_preview.py tests/test_p1_localvideostudio27b_public_ui.py
python -m pytest -q tests/test_p0_videomenu_routeengine29b_shared_contract.py tests/test_p0_videomenu_routeengine29c_product_video_one_scene.py tests/test_p0_videomenu_routeengine29d_product_poll_recovery.py
python -m pytest -q tests/test_p0_subdub_production_receipt_truth.py
```

Also run the existing callback-owner, Product Video UI-freeze and relevant Video menu/UI tests discovered with `rg --files tests`.

- [ ] **Step 3: Run static and scope checks**

```powershell
python -m py_compile local_worker.py services/video_edit_state_machine.py services/video_edit_capabilities.py services/video_local_editing.py services/video_editengine1.py
python -c "import pathlib,tokenize; tokenize.open('bot.py').read(); print('tokenize PASS')"
git diff --check origin/main...HEAD
git diff --name-status origin/main...HEAD
git status --short --branch
```

If full `bot.py` `py_compile` exceeds its bounded timeout, record `TIMEOUT` honestly and require tokenize plus narrow AST source parsing and GitHub source-compile CI before merge.

Scope scan must prove no changed Product Video, SubDub, Frame Video, `services/local_video_studio_public.py`, provider adapter, wallet/PayOS, Railway/VPS, webhook, Music/Suno, Motion or Higgsfield file.

- [ ] **Step 4: Independent spec and code-quality review**

Give reviewers the exact design spec, this plan, base SHA and branch diff. Fix only validated findings, rerun the failing test first, then the complete focused matrix.

- [ ] **Step 5: Commit final narrow fixes, push and open one PR**

```powershell
git push -u origin feat/p0-videoedit-canonical-local
gh pr create --base main --head feat/p0-videoedit-canonical-local --title "feat(video-edit): complete canonical local editor" --body-file <reviewed-ship-report>
```

Do not merge, deploy, change ENV, run production Telegram media smoke, call providers/workers, mutate wallet/Xu, or deliver media without a separate owner gate.

## Completion evidence matrix

- Every visible button useful/truthful: callback matrix + real local operation tests.
- Vietnamese-first UI: public copy scan + saved-language Back test.
- Exact Back hierarchy: parameterized parent matrix and fake Telegram navigation.
- Local-free accounting: zero-price job/receipt tests with wallet spy count `0`.
- Real artifact: FFmpeg fixtures with validated H.264 MP4, duration, dimensions and audio policy.
- No fake success: failed FFmpeg/invalid receipt tests.
- Idempotency: duplicate confirm creates one worker job/outbox; status is read-only.
- Planning isolation: 27B regressions and state store separation.
- Cross-product isolation: changed-path scan and callback-owner regression count `0`.
- External side effects: provider calls `0`, wallet mutations `0`, production media deliveries `0`, deploys `0`.
