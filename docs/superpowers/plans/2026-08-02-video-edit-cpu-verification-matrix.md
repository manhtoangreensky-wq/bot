# Video Edit CPU Verification Matrix

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` for the RED/GREEN fixes and
> `superpowers:verification-before-completion` before any PASS, push, PR, or
> merge claim. Run every command sequentially.

**Goal:** Use one explicitly granted CPU window to prove the remaining Video
Edit blockers RED, apply only minimal fixes, and verify every public route,
Back edge, local engine/worker/receipt invariant, isolation boundary, and ship
gate without starting any production execution.

**Architecture:** Keep the current dirty worktree intact. Use the bundled
Python 3.12 runtime with pytest plugin autoload disabled and `--noconftest`, run
focused tests before aggregates, isolate real-media gates, and use the merge
base for local-patch scope until the branch is synchronized with latest main.

**Tech Stack:** PowerShell, Python 3.12, pytest, SQLite, FFmpeg/ffprobe, Git,
GitHub CI.

---

## Authority and hard stops

- This file is a prepared matrix, not permission to run it.
- Do not infer permission from an empty process list or another task's CPU
  release. Start only after an explicit `CPU GRANTED TO VIDEO EDIT`.
- Never use xdist, parallel shells, repository-wide `pytest -q`, `compileall`,
  Telegram production media, providers, workers, wallet/Xu, PayOS, deployment,
  ENV, VPS, webhook, or job creation as part of this matrix.
- A timeout is `TIMEOUT`, never PASS. Stop the bounded Video Edit process tree,
  record the exact gate, and diagnose before continuing.
- Do not manufacture RED with reset/revert. Preserve the dirty worktree and
  observe the tests already written before changing production code.
- Use host/tool timeouts. `pytest-timeout` is not installed and plugin autoload
  is disabled.

## Session setup

Recommended host timeout: 60 seconds.

```powershell
Set-Location -LiteralPath 'C:\Users\toann\Documents\Codex\2026-07-28\t-m-l\work\local-video-studio27b-deploy-39c96bd'

$Py = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $Py -PathType Leaf)) {
    throw "Bundled Python is unavailable: $Py"
}

$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Remove-Item Env:PYTEST_ADDOPTS -ErrorAction SilentlyContinue
$env:PYTHONHASHSEED = '0'

function Confirm-NativeGate([string]$Name) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$Base = (git merge-base HEAD origin/main).Trim()
Confirm-NativeGate 'merge-base'
if ([string]::IsNullOrWhiteSpace($Base)) {
    throw 'No merge base with origin/main'
}

git status --short --branch
Confirm-NativeGate 'initial status'
```

## Gate R0 — focused review blockers, RED then identical GREEN

Recommended host timeout: 900 seconds.

Run this before any production fix. Record each expected failure by exact test
node and reason. The locked behavior covers latest-row ownership/type/ID,
SQLite/stale-render log privacy, saved status language, raw/incomplete delivery
truth, SELECT-only canonical reads, free-task Vietnamese copy, reply-race CAS,
and neutral Split re-upload state.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_latest_status_navigation.py `
  tests/test_p0_videoedit_canonical_bot_routes.py `
  tests/test_p0_videoedit_review_parent_hardening.py `
  tests/test_p0_videoedit_back_hierarchy_adapter.py `
  -k 'canonical_receipt_lookup or preserves_saved_english or empty_and_unavailable_views or unverified_delivered or incomplete_canonical or database_failure or revalidates_owned or free_delivered or reply_failure_guard or split_reupload or stale_rerender_log or logo_upload or complete_local_ai_lane or every_visible_nested or direct_manual_choices'
```

Expected first run: only the intended missing behavior fails. A collection,
fixture, import, syntax, timeout, or unrelated failure is not accepted RED.
After minimal production changes, rerun the identical command and require exit
0 before any broader gate.

### Locked minimal production targets after valid RED

Do not edit these targets until their corresponding RED has been observed:

| RED behavior | Minimal production target |
| --- | --- |
| Canonical receipt read executes DDL | Extract the existing SELECT/decoder in `services/video_editengine1.py` to `get_job_by_worker_id_readonly()`; keep the mutating-path wrapper's `ensure_schema()` behavior unchanged and switch only the status adapter to the read-only helper. |
| Latest row can be foreign/wrong type/invalid ID | In the `latest_status` branch, recheck `user_id == uid`, exact `WORKER_JOB_TYPE`, and positive ID before rendering; otherwise render the same private empty state. |
| SQLite diagnostic exposes raw details | Catch `sqlite3.Error` and log only `type(exc).__name__` under a bounded category. |
| Saved English status is mixed Vietnamese | Localize title, public-state labels, price/job labels, all six stages, counters, result/charge/waiting/failure/uncertain copy; keep internal state keys unchanged. |
| Raw/incomplete delivered state shows completion | Define completion only from complete canonical receipt evidence; make raw or incomplete terminal delivery uncertain, clamp progress to five, and warn on stage six. |
| Free delivered copy exposes `local` | Replace the public implementation term with Vietnamese `cục bộ`; do not change internal contract identifiers. |
| Reply failure overwrites a concurrent winner | Compare the complete post-handler state with the exact expected state before restoring the pre-handler snapshot; preserve and rerender any winner, and prevent outer media recovery from writing over it. |
| Split re-upload lacks neutral manual plan | Persist `neutral_split_manual_plan()` in the Split-owned intake state before replacement media arrives and keep it after probe success. |
| Stale rerender log exposes exception detail | Log bounded exception category only, never `str(exc)` or state/media identifiers. |
| Logo review hides position and opacity | Keep the existing fixed scale contract, add no scale control, and make `public_plan_summary()` render bounded Vietnamese position plus opacity for the selected logo/watermark. |

If a RED proves a different cause, stop and revise the target instead of forcing
the planned implementation.

## Focused functional gates

### Gate F1 — navigation, exact parents, Vietnamese copy

Recommended host timeout: 300 seconds per command.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_canonical_navigation.py `
  tests/test_p0_videoedit_back_hierarchy_adapter.py `
  -k 'review_back or logo_options or audio_upload or audio_reupload or vietnamese'
Confirm-NativeGate 'focused navigation parents'

& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_canonical_bot_routes.py `
  -k 'audio or hub or logo or back'
Confirm-NativeGate 'focused public route copy'

& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_back_hierarchy_adapter.py `
  tests/test_p0_videoedit_review_parent_hardening.py `
  -k 'every_visible_nested or direct_manual_choices or logo_upload or complete_local_ai_lane'
Confirm-NativeGate 'focused complete route traceability'
```

Require saved immediate parents, canonical `videoedit|` callbacks, one useful
logo/watermark lane, and no unavailable stem/provider claim.

### Gate F2 — concurrency, stale state, and Review hardening

Recommended host timeout: 480 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_review_parent_hardening.py
Confirm-NativeGate 'focused review concurrency hardening'
```

Require exact AI/manual Review parents, intake claim exclusivity, full-state
CAS, winner-preserving rollback/rerender, bound destructive Split reset,
canonical legacy migration, and redacted logs.

### Gate F3 — Split ownership and destructive reset

Recommended host timeout: 360 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_back_hierarchy_adapter.py `
  -k 'split or stale or post_render_commit'
Confirm-NativeGate 'focused split navigation'
```

Require no silent manual-plan loss, neutral Split state before re-upload,
exact Back, and stale callback fail-closed behavior.

### Gate F4 — timing, geometry, subtitle, and audio invariants

Recommended host timeout: 480 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_canonical_local_runtime.py `
  -k 'explicit_mute or split_plan or fades or text_wholly or srt or concat_timing or execute_revalidates or slow_zoom or final_timeline or speed_timestamp'
Confirm-NativeGate 'focused local runtime invariants'
```

Require final concat/speed timeline authority, intersecting SRT cues, rotated
zoom geometry, and consistent mute/loudness normalization.

### Gate F5 — rights, asset binding, engine/worker defense

Recommended host timeout: 600 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_job_safety.py `
  tests/test_p0_videoedit_canonical_local_worker_receipt.py `
  -k 'rights or split or unbound_plan_assets or downloaded or final_noop_guard'
Confirm-NativeGate 'focused job worker safety'
```

Require owner/revision-bound rights, Telegram asset binding, independent mixed-
Split rejection, and fresh downloaded-source duration/no-op checks.

### Gate F6 — complete latest-status contract

Recommended host timeout: 720 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_latest_status_navigation.py `
  tests/test_p0_video_edit3_compact_manual_flow.py `
  tests/test_p1_localvideostudio27b_public_ui.py `
  tests/test_p0_videoedit_canonical_bot_routes.py
Confirm-NativeGate 'focused latest status'
```

Require owned/typed/SELECT-only/stateless/localized status, truthful delivery,
sanitized errors, exact Back, one secondary row, and no parent Video-menu row.

### Gate F7 — focused observable real-media evidence

Recommended host timeout: 1,800 seconds.

```powershell
& $Py -c "from services import video_local_validation as v; f=v.find_ffmpeg(); p=v.find_ffprobe(ffmpeg_path=f); assert f and p, 'FFmpeg/ffprobe unavailable'; print('real-media prerequisites available')"
Confirm-NativeGate 'real-media prerequisites'

& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_real_media_matrix.py `
  -k 'fade_out or every_public_speed or shared_visual_audio_marker or speed_and_slow_zoom or loudnorm_hits or sharpen_and_denoise or color_temperature_and_vignette or rotated_slow_zoom or logo_watermark or text_and_srt or gapped_split'
Confirm-NativeGate 'focused real-media evidence'
```

An FFmpeg-unavailable skip does not satisfy this gate. Require observable
artifact changes, AV sync, logo/text/SRT timing, color/effects, rotated zoom,
and gapped Split boundaries.

## Aggregate Video Edit gates

Run these after the last production edit. Do not rerun their focused subsets
again unless code changes afterward.

### Gate A1 — route, Back, status, and compatibility

Recommended host timeout: 900 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_latest_status_navigation.py `
  tests/test_p0_videoedit_review_parent_hardening.py `
  tests/test_p0_videoedit_canonical_bot_routes.py `
  tests/test_p0_videoedit_canonical_navigation.py `
  tests/test_p0_videoedit_back_hierarchy_adapter.py `
  tests/test_p0_video_statusrestore18_old_status_only.py `
  tests/test_p0_video_tailflow16_dedupe_summary_audio_status.py
Confirm-NativeGate 'full Video Edit route back status'
```

### Gate A2 — state, capability, admission, and legacy behavior

Recommended host timeout: 720 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_capability_truth.py `
  tests/test_p0_videoedit_filter_admission.py `
  tests/test_p0_videoedit_worker_filter_snapshot.py `
  tests/test_p0_videoedit_parent_allowlist.py `
  tests/test_p0_videoedit_legacy_compatibility.py `
  tests/test_p0_video_edit2_upgrade_audio_ai_backstack.py `
  tests/test_p0_video_edit3_compact_manual_flow.py `
  tests/test_p0_video_edit3_canonical_intake_route_state_machine.py `
  tests/test_p0_video_edit4_editor_state_ownership.py
Confirm-NativeGate 'full Video Edit state capability admission'
```

### Gate A3 — engine, worker, job safety, and receipts

Recommended host timeout: 1,200 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_video_editengine1_local_render_status_delivery.py `
  tests/test_p0_video_editengine2_buttons_worker_heartbeat_package.py `
  tests/test_p0_videoedit_canonical_local_runtime.py `
  tests/test_p0_videoedit_canonical_local_worker_receipt.py `
  tests/test_p0_videoedit_job_safety.py `
  tests/test_p0_videoedit_local_free_job.py `
  tests/test_p0_videoedit_split_receipt_checkpoint.py
Confirm-NativeGate 'full Video Edit engine worker safety receipt'
```

### Gate A4 — complete canonical real-media matrix

Recommended host timeout: 2,700 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videoedit_real_media_matrix.py
Confirm-NativeGate 'full canonical Video Edit real-media matrix'
```

### Gate A5 — legacy local executor compatibility

Recommended host timeout: 2,400 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_video_local1_manual_editing_smart_splitter.py
Confirm-NativeGate 'legacy local executor compatibility'
```

## Cross-product isolation gates

### Gate X1 — callback/state/product-route isolation

Recommended host timeout: 1,200 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_media_edit_brightness_intake_route.py `
  tests/test_p0_video_storyboard_image_output_brightness_route.py `
  tests/test_p0_video_flow4_callback_route_recovery.py `
  tests/test_p0_video_flow6_canonical_multimode_intake_engine_route.py `
  tests/test_p0_video_flow7_distinct_products_shared_ux_routing.py `
  tests/test_p0_video_flow8_three_content_sources_exact_routes.py `
  tests/test_p0_video_flow_regression.py `
  tests/test_video_flow_state_machine_v4.py `
  tests/test_product_context_separation.py `
  tests/test_p0_video_uifreeze1_menu_pricing_public_freeze.py
Confirm-NativeGate 'cross-product callback route isolation'
```

### Gate X2 — Local Video Studio isolation

Recommended host timeout: 720 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p1_localvideostudio27a_preview.py `
  tests/test_p1_localvideostudio27b_public_ui.py
Confirm-NativeGate 'Local Video Studio isolation'
```

### Gate X3 — RouteEngine29 Product Video isolation

Recommended host timeout: 1,800 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_videomenu_routeengine29b_worker_router_contract.py `
  tests/test_p0_videomenu_routeengine29c_product_video_one_scene.py `
  tests/test_p0_videomenu_routeengine29d_product_video_poll_recovery.py
Confirm-NativeGate 'RouteEngine29 isolation'
```

### Gate X4 — SubDub and changed comparator locks

Recommended host timeout: 600 seconds.

```powershell
& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_subdub_production_receipt_truth.py `
  tests/test_p0_video_aiedit1_blackbox_special_effects_transformation.py::test_aiedit1_menu_entry_present `
  tests/test_p0_video_finalflow12_golden_tail.py::test_unified_summary_is_the_only_final_check_before_quality `
  tests/test_p0_video_knowledge1_profile_router_and_studio_menu.py::test_edit_video_hub_restores_only_tools_with_real_existing_handlers
Confirm-NativeGate 'SubDub and comparator isolation'
```

## Compile, tokenize, AST, and static gates

### Gate S1 — compile all changed Python except separately bounded `bot.py`

Recommended host timeout: 300 seconds.

```powershell
$TrackedChanged = @(git diff --name-only $Base --)
Confirm-NativeGate 'tracked changed paths'
$UntrackedChanged = @(git ls-files --others --exclude-standard)
Confirm-NativeGate 'untracked changed paths'

$Changed = @($TrackedChanged + $UntrackedChanged) |
    ForEach-Object { $_.Trim().Replace('\', '/') } |
    Where-Object { $_ } |
    Sort-Object -Unique

$CompilePaths = @(
    $Changed |
    Where-Object {
        $_.EndsWith('.py', [System.StringComparison]::OrdinalIgnoreCase) -and
        $_ -ne 'bot.py' -and
        (Test-Path -LiteralPath $_ -PathType Leaf)
    }
)

& $Py -m py_compile @CompilePaths
Confirm-NativeGate 'changed Python compile'
```

### Gate S2 — full `bot.py` compile

Recommended host timeout: 180 seconds.

```powershell
& $Py -m py_compile bot.py
Confirm-NativeGate 'bot.py compile'
```

If this times out, report it honestly and require EOF tokenize, narrow AST, and
GitHub exact-head source-compile CI before merge.

### Gate S3 — consume the complete token stream

Recommended host timeout: 120 seconds.

```powershell
& $Py -c "import pathlib,tokenize; from collections import deque; f=pathlib.Path('bot.py').open('rb'); deque(tokenize.tokenize(f.readline), maxlen=0); f.close(); print('bot.py tokenize PASS')"
Confirm-NativeGate 'bot.py tokenize'
```

Do not use an unconsumed `tokenize.tokenize(...)` generator; it can falsely
report success.

### Gate S4 — narrow Python 3.11-compatible Video Edit AST

Recommended host timeout: 120 seconds.

```powershell
$NarrowAst = @'
import ast
import pathlib
import re

path = pathlib.Path("bot.py")
text = path.read_text(encoding="utf-8")
names = (
    "get_latest_video_editor_job",
    "video_edit_hub_keyboard",
    "video_editor_status_keyboard",
    "video_editor_latest_status_fallback_keyboard",
    "video_editor_latest_status_empty_text",
    "video_editor_latest_status_unavailable_text",
    "video_editengine1_job_for_worker",
    "video_editor_job_status_text",
    "video_edit_legacy_tail_compatibility",
    "handle_video_tail_callback",
    "handle_video_editor_pending_upload",
    "video_editor_current_render_model",
    "rerender_video_editor_after_stale_commit",
    "handle_video_editor_callback",
)
next_top = re.compile(r"(?m)^(?:(?:async\s+def|def|class)\s+\w+|@)")
for name in names:
    start_match = re.search(
        rf"(?m)^(?:async\s+def|def)\s+{re.escape(name)}\s*\(",
        text,
    )
    if start_match is None:
        raise AssertionError(f"missing top-level function: {name}")
    end_match = next_top.search(text, start_match.end())
    end = end_match.start() if end_match else len(text)
    source = "from __future__ import annotations\n\n" + text[start_match.start():end]
    tree = ast.parse(source, filename=f"bot.py::{name}", feature_version=(3, 11))
    compile(tree, f"bot.py::{name}", "exec")
print("narrow Video Edit AST PASS")
'@

& $Py -c $NarrowAst
Confirm-NativeGate 'narrow Video Edit AST'
```

### Gate S5 — exactly one callback owner

Recommended host timeout: 60 seconds.

```powershell
$OwnerLines = @(
    rg -n -F 'CallbackQueryHandler(handle_video_editor_callback, pattern=r"^videoedit\|")' bot.py
)
if ($LASTEXITCODE -notin @(0, 1)) {
    throw "rg callback scan failed: $LASTEXITCODE"
}
if ($OwnerLines.Count -ne 1) {
    throw "Expected exactly one registered videoedit callback owner; found $($OwnerLines.Count)"
}
$OwnerLines
```

### Gate S6 — whitespace and changed-path scope

Recommended host timeout: 60 seconds.

```powershell
git diff --check $Base --
Confirm-NativeGate 'whole-scope diff check'

foreach ($Path in $UntrackedChanged) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        continue
    }
    $LineNumber = 0
    foreach ($Line in [System.IO.File]::ReadLines((Resolve-Path -LiteralPath $Path))) {
        $LineNumber += 1
        if ($Line -match '[ \t]+$') {
            throw "Untracked whitespace error: ${Path}:${LineNumber}"
        }
    }
}
'untracked whitespace PASS'
```

Then require every item in `$Changed` to exist in
`VIDEO_EDIT_COMPLETION_SCOPE_FILES` in `tests/aiedit1_scope_guard.py`. Include
untracked files; ignore only explicitly identified local pytest scratch paths.
The static checkpoint before CPU had 30 status paths, all allow-listed; the
new CPU-matrix document raises both sides by one.

### Gate S7 — redacted secret/private-path scan

Recommended host timeout: 60 seconds.

Scan only added production lines in:

```text
bot.py
local_worker.py
services/video_edit_state_machine.py
services/video_edit_capabilities.py
services/video_editengine1.py
services/video_local_editing.py
services/video_local_validation.py
```

Require zero private keys, tokens, API keys, credential-bearing URLs, real
private absolute paths, or hard-coded secrets. Report filenames only, never
raw matching values.

### Gate S8 — repository scope guard after synchronization only

Recommended host timeout: 180 seconds.

```powershell
$Behind = [int](git rev-list --count HEAD..origin/main)
Confirm-NativeGate 'behind count'
if ($Behind -ne 0) {
    throw "Branch is still $Behind commit(s) behind origin/main; defer origin/main-based scope test"
}

& $Py -m pytest -q -rs --noconftest `
  tests/test_p0_video_aiedit1_blackbox_special_effects_transformation.py::test_aiedit1_changed_files_stay_in_exact_scope
Confirm-NativeGate 'repository scope guard'
```

## Integration, review, and release order

1. Obtain independent spec compliance approval.
2. Obtain independent code-quality approval only after spec approval.
3. Fix every valid finding with a new focused RED, minimal GREEN, and affected
   aggregate rerun.
4. Fetch latest main; inspect every intervening path before rebase. Stop for
   owner review if Video Edit route/engine/state/backstack/tests or shared
   callback ownership changed.
5. Rebase without squash only when safe, preserve logical design/test/
   implementation commits, and rerun the exact affected/aggregate/static gates
   on the rebased head.
6. Push, open one non-draft PR, verify changed scope, and require GitHub CI PASS
   on the exact head.
7. Merge with a merge commit, never squash. Record design/test/implementation
   ancestry, merge SHA, new main SHA, and parent count two.
8. Observe only the normal post-merge deployment. Run a fresh `/start` and
   navigation/read-only Video Edit smoke: four existing actions, status row,
   optional planning row position, exact Back hierarchy, no top-level status
   button, and no duplicate/cross-product callback.
9. Do not upload production media, submit/retry/replay a job, call provider or
   worker, mutate wallet/Xu, or deliver media. A real production render needs a
   separate owner gate.

## Unsafe or redundant commands

- Do not run repository-wide `pytest -q`; it includes unrelated and costly
  suites.
- Do not run `pytest --timeout=...`; the plugin is absent.
- Do not run `compileall`; it is redundant, writes broadly, and can be
  unbounded.
- Do not use `python -m tokenize bot.py`; it emits an enormous token dump.
- Do not use `git diff origin/main` as pre-sync scope truth; the branch is
  behind and the result includes upstream-only differences.
- Do not use `git diff origin/main...HEAD` as the sole pre-commit check; it
  excludes unstaged and untracked work.
- Do not print raw secret-scan matches.
- Do not accept an FFmpeg skip as real-media PASS.

## Final evidence record

Record exact exit/result for every gate, not only an aggregate number:

```text
CPU grant source/time:
RED nodes and expected reasons:
Minimal production fixes:
F1-F7:
A1-A5:
X1-X4:
S1-S8:
New failures:
Callback collisions:
Cross-product routes:
Provider calls:
Worker calls:
Paid generations:
Wallet/Xu mutations:
Telegram media deliveries:
Production jobs created:
Spec review:
Code-quality review:
Rebased head:
PR/checks:
Merge/new main/two-parent ancestry:
Navigation-only live smoke:
CPU release time:
Blockers:
```

## Prepared non-draft PR body

Fill only from recorded evidence; never replace a missing result with an
assumption.

```markdown
## Summary

- complete the Vietnamese-first canonical `videoedit|` routes and exact Back hierarchy;
- make manual operations, Split isolation, logo/watermark, local FFmpeg engine/worker, receipts, and zero-price truth verifiable end to end;
- add one read-only `📊 Trạng thái chỉnh sửa` row inside Video Edit that reopens only the requesting user's newest canonical Video Edit job.

## Isolation and safety

- Product Video, Frame Video, SubDub, and Local Video Studio execution/state are unchanged;
- provider calls: 0;
- worker calls outside local test fixtures: 0;
- paid generations: 0;
- wallet/Xu mutations: 0;
- Telegram production media deliveries: 0;
- production jobs created: 0;
- ENV/VPS/webhook/manual deployment changes: 0.

## Verification

- focused RED evidence: <nodes/reasons>;
- focused GREEN F1-F7: <exact results>;
- aggregate Video Edit A1-A5: <exact results>;
- isolation X1-X4: <exact results>;
- compile/tokenize/AST/static S1-S8: <exact results>;
- clean-main/branch failure-set delta: <exact result>;
- independent spec review: <result>;
- independent code-quality review: <result>.

## Scope

<exact `git diff --name-status origin/main...HEAD` output summarized by approved Video Edit files>

## Release contract

Require CI PASS on this exact head. Merge commit only; never squash. After
merge, navigation/read-only smoke only—no production media render or provider,
worker, billing, wallet, job, or delivery action.
```

## Prepared navigation-only live checklist

1. Confirm the normal auto-deployed runtime build equals the merged main SHA;
   do not trigger a manual duplicate deployment.
2. Confirm current health/startup/webhook ownership without mutating webhook or
   ENV.
3. Start a fresh Telegram session with `/start` before testing menu callbacks.
4. Open the top-level Video menu and confirm no top-level Video Edit status or
   duplicate Local Video Studio button was added.
5. Open `🛠️ Chỉnh sửa video`; confirm the four established actions are
   unchanged and `📊 Trạng thái chỉnh sửa` appears exactly once as a secondary
   row.
6. Open the status row with an owner account. Confirm either the newest owned
   canonical Video Edit status or the truthful empty state, exact refresh,
   saved language, and Back to the Video Edit hub.
7. Navigate the four existing entries and every safe no-upload child/Back edge;
   confirm no callback leaves `videoedit|` except the intentional parent/main
   navigation and optional `lvs27b|open` planning boundary.
8. Do not upload media, confirm a render, submit/retry/replay a job, open a paid
   gate, call a provider/worker, mutate wallet/Xu, or deliver media.
9. Record counters as zero and report any reproduced issue. Fix it only through
   a new branch RED/GREEN cycle; do not patch production directly.
