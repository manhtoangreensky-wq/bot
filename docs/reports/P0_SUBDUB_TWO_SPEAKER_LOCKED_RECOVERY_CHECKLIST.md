# P0 SubDub — Locked Recovery Checklist: Tự động 2 giọng

> Owner order: phục hồi hoàn toàn lane 2 giọng từ bản đã giao video thật; phục
> hồi điều khiển âm thanh gốc/giọng lồng tiếng; live PASS rồi khóa lane; chỉ sau
> đó mới sang nhiều giọng.

## 0. Cách đọc và luật cập nhật

### Trạng thái

- `[ ]` chưa làm.
- `[-]` đang làm; toàn file chỉ được có **một SUBSPEC** ở trạng thái này.
- `[x]` đã có bằng chứng thực nghiệm.
- `[!]` FAIL, phải ở lại cùng SPEC và chạy failure loop.
- `[B]` bị chặn bởi SPEC trước; cấm làm trước thứ tự.

### Current pointer

- Current SPEC: `SPEC-07`.
- Current SUBSPEC: `SPEC-07.3`.
- Current phase: `SHIP LIVE-FOUND LABEL CORRECTION / pre-confirm`.
- Production action active: `focused source correction only`.
- Telegram/provider job active: `NO; flow paused before final confirmation`.
- Wallet mutation: `0`.
- Next allowed action: push the two-line truthful audio label correction, deploy,
  resume the existing combo flow before final confirmation.
- Next forbidden action: final confirm/provider call on misleading old keyboard.

### Luật bất biến

- Không có ô checklist tương ứng ⇒ không được làm.
- Không xóa file, DB, artifact, table hoặc user data.
- Không `git reset --hard`, không checkout đè working tree, không xóa `artifacts/`.
- Không sửa Product Video, PayOS, wallet, ENV/secrets, onboarding, PWA.
- Không sửa/chạy live lane nhiều giọng trước khi `SPEC-10` hoàn tất.
- Không dùng `Download.mp4`.
- Không dùng fixture lịch sử `test 2 giọng.mp4` cho acceptance cuối.
- Không công nhận PASS từ mock, metadata, HTTP 200 hoặc job id.
- `MERGED != DEPLOYED != LIVE`.
- Lane 2 chỉ được khóa sau hai MP4 thật: combo và standalone.

## 1. Source truth và phạm vi khóa

### Mốc rollback bắt buộc

| Trường | Giá trị |
| --- | --- |
| PR | `#842` |
| SHA | `71c7e881f2af24d59c4873f8ca3999f59618daec` |
| Job đã giao video | `#7BC3037DF8` |
| Telegram video message | `26895` |
| Telegram receipt message | `26896` |
| charged_xu | `0` |

### Fixture acceptance cuối

| Trường | Giá trị |
| --- | --- |
| Path | `C:\Users\toann\Downloads\test sub\2 giọng nam nữ.mp4` |
| Bytes | `4,284,017` |
| Duration Telegram | `0:48` |
| SHA-256 | `85C8793D197CF2782BB554D46282E82A83BCB062A0483E412A0CA1DA668F9F51` |
| Expected cast | một speaker male pool + một speaker female pool, từ evidence độc lập |

### Latest failed evidence

| Trường | Giá trị |
| --- | --- |
| Public job | `#FD14FC02D6` |
| Internal job | `fd14fc02d60727ff0e44` |
| Mode | `subtitle_plus_dub` |
| Terminal | `failed_no_charge` |
| Blocker | `pipeline_failed:RuntimeError` |
| charged_xu | `0` |
| Status panel message | `27383` |
| Telegram incident | Bot API returned repeated `502 Bad Gateway` during the same flow |

### Allowed production scope

- `services/subdub_blackboxes/auto_speaker.py`: exact 2-speaker engine rollback.
- `bot.py`: only exact lane-2 dispatch/compatibility and audio-mix UI/state symbols
  listed in `SPEC-02`.
- A new regression test file dedicated to this recovery.
- This checklist and final evidence report.

### Protected production scope

- `services/subdub_blackboxes/auto_multi_speaker.py`: byte-locked; no edit.
- Multi callback marker/state (`auto_speaker_lane="multi"`): no semantic edit.
- `services/subdub_speaker_cast.py`: already equal to PR #842; no edit unless
  byte comparison later disproves this statement.
- Current two-button voice UI labels/order: preserve; both buttons remain one row.
- Exact pricing and receipt improvements from PR #885: preserve.
- Auto combo SRT companion from PR #887: preserve.
- Admin list price remains nonzero; only settlement is `charged_xu=0`.
- Wallet/transactions/schema: no edit.

## SPEC-01 — Prove exact rollback anchor and current failure

### SPEC-01.1 — Anchor identity

- [x] Read commit `71c7e881...` metadata.
- [x] Confirm commit title `fix(subdub): finalize auto delivery receipt and CJK captions (#842)`.
- [x] Confirm historical delivered job `#7BC3037DF8`.
- [x] Confirm Telegram video/receipt `26895` / `26896`.
- [x] Confirm admin charged `0 Xu`.

Evidence:

- `git show --no-patch --format=fuller 71c7e881...`.
- Durable historical job/Telegram evidence in
  `.agents/state/p0-subdub-multi-blackbox.yaml`.

### SPEC-01.2 — Current failure identity

- [x] Identify public/internal job `FD14FC02D6` / `fd14fc02d60727ff0e44`.
- [x] Verify `failed_no_charge` and `charged_xu=0`.
- [x] Verify failure occurred before final artifact delivery.
- [x] Capture exact journal window `19:02:30–19:05:00`.
- [x] Record simultaneous Telegram Bot API `502 Bad Gateway` evidence.
- [x] Inspect deepest persisted evidence: inner reason was **not persisted**;
  only `pipeline_failed:RuntimeError` exists. Workspace contains source and
  normalized MP4 only; FFprobe shows H.264 + AAC stereo 48 kHz, duration
  `48.421016s`, and full audio decode exits `0`.

### SPEC-01 acceptance

- [x] Rollback anchor is based on a delivered artifact, not a branch name.
- [x] Latest failure is measured and zero-charge.

## SPEC-02 — Map every lane-2 symbol and freeze unrelated code

### SPEC-02.1 — Module parity map

- [x] Compare `services/subdub_blackboxes/auto_speaker.py` PR #842 vs current.
- [x] Confirm current additions include independent fallback/font guard.
- [x] Classify every hunk as: `ROLLBACK`, `CURRENT-ADAPTER`, or `PROTECTED`.
- [x] Confirm `run_auto_speaker_preflight` remains the PR #842 public owner.
- [x] Confirm `run_auto_speaker_blackbox` remains the PR #842 public owner.
- [x] Confirm the exact dependency list needed by current multi adapter.
- [x] Decide rollback method using Git source, not hand-written replacement.

Measured module evidence:

| Item | PR #842 | Current | Decision |
| --- | --- | --- | --- |
| `auto_speaker.py` lines | `660` | `902` | restore whole file from Git object |
| normalized/worktree SHA-256 | `49E905C0…` | `AA4F0E0D…` | RED, then rollback |
| independent fallback | absent | 3 new private owners | rollback |
| font guard | absent | 2 new owners | rollback |
| preflight/blackbox public owner | present | present | restore anchor bodies |
| helpers used by multi | present | present | anchor satisfies multi imports |

### SPEC-02.2 — Bot symbol parity map

Required owners to compare PR #842 → current:

- [x] `subdub_auto_speaker_route_enabled` — CURRENT-ADAPTER, preserve.
- [x] `subdub_auto_blackbox_runner` / direct PR #842 dispatch — CURRENT-ADAPTER
  only for multi isolation; exact two-speaker result remains anchor runner.
- [x] `_extract_subdub_auto_pcm` — anchor-compatible; no edit.
- [x] `_execute_video_dubbing_pipeline_core` lane-2 branch — remove only new
  font guard; preserve current resume/pricing adapters and runner selector.
- [x] `_subdub_auto_post_prepare_gate` — PROTECTED PR #885 exact pricing.
- [x] `video_dubbing_confirm_text` — PROTECTED pricing; audio copy retained.
- [x] `video_dubbing_confirm_keyboard` — edit only audio layout.
- [x] `subdub_audio_mix_available` — anchor-compatible; preserve.
- [x] `subdub_audio_mix_state_fields` — anchor-compatible; preserve.
- [x] `subdub_audio_mix_keyboard` — restore controls from `6309f03`, category
  buttons one row per Owner.
- [x] `subdub_audio_layer_keyboard` — restore preset controls from `6309f03`
  while preserving numeric input.
- [x] `handle_video_dubbing_callback` audio actions — restore preset callbacks
  from `6309f03`; preserve numeric callbacks.
- [x] `handle_video_dubbing_pending_text` numeric audio input — PROTECTED.
- [x] auto exact pause/resume state retention — PROTECTED PR #885/current.
- [x] final mux arguments for original/dub volume — anchor-compatible/current;
  preserve and verify behaviorally.
- [x] delivery/receipt adapters — PROTECTED PR #885/#887.

For every owner, record:

| Symbol | PR #842 SHA/body | Current SHA/body | Decision | Test |
| --- | --- | --- | --- | --- |
| `auto_speaker.py` full engine | anchor Git object | +independent/font owners | ROLLBACK | engine source contract |
| `subdub_auto_blackbox_runner` | direct runner | lane selector | CURRENT-ADAPTER | two/multi isolation |
| `_execute_video_dubbing_pipeline_core` | no module font guard | module font guard | ROLLBACK guard only | anchor route + CJK protected |
| audio mix state/mux | present | present | PROTECTED | state + render tests |
| audio controls | preset grid at `6309f03`; numeric at #842 | numeric submenu only | RESTORE + one-row layout | UI/callback tests |
| pricing/receipt/SRT | older | PR #885/#887 | PROTECTED | component price/admin0/SRT |

### SPEC-02.3 — Protected byte hashes before edit

- [x] Hash `auto_multi_speaker.py` before edit: `55AAB8949EFAECAD8DD987AC6DFE056AB0E4BC4EF81A23977EA5EDD1CDF64911`.
- [x] Hash `subdub_speaker_cast.py`: `DE93620F3F038B5759A53E696C5C85D3553FCEE758686DF56C70E6B11BAC145B`.
- [x] Hash multi protected test: `B39464A61EBF8D1256F6BD86D1701D5B2F97DB4D7B0FBE34DF554C7A129C9B87`.
- [x] Hash current per-speaker protected test: `7A5E63D08ED3DF105D754C7E383633D6A78E39487B4A7A9DC291B3222143AB46`.
- [x] Hash audio test before edit: `624EC9062FF913757D5A9901DA92A0B71F8A89138792826835933A2A2F957FF1`.
- [x] Record pre-edit `origin/main` SHA: `edf4320790fe4ac378dd5d09d3da5eb057835e1e`.
- [x] Rebase clean onto latest Product Video main:
  `5a4f942` (`#888/#891/#892/#893`); 7-file SubDub diff unchanged.
- [x] Record working tree: only `artifacts/` and this new checklist untracked;
  production source clean.

### SPEC-02 acceptance

- [x] Every lane-2 owner has an explicit decision.
- [x] Every unrelated owner is protected by hash or comparator.
- [x] No production edit occurred before this acceptance.

## SPEC-03 — RED contracts before rollback

### SPEC-03.1 — Exact engine parity RED

- [x] Test proves current two-speaker module differs from PR #842 source.
- [x] Test excludes current multi adapter from rollback comparison.
- [x] Test names exact differing symbols/hunks.
- [x] Run RED: `4 failed, 1 passed in 0.76s`; multi hash comparator PASS.

Expected RED evidence:

```text
selector: tests/test_p0_subdub_two_speaker_locked_recovery.py
exit: 1
failures: 4
reason: current blob, post-anchor font guard, two-row audio layout, missing presets
```

### SPEC-03.2 — Audio controls RED

Both `dub` and `subtitle_plus_dub`:

- [x] Confirm screen exposes `videodub|audio_mix`.
- [x] Audio screen exposes `audio_original` and `audio_dub` **same row**.
- [x] Original layer supports off/on, preset increase/decrease, numeric input.
- [x] Dub layer supports preset increase/decrease, numeric input.
- [x] Original percent range is bounded and persists.
- [x] Dub percent range is bounded and persists.
- [x] Back returns to same lane confirm.
- [x] Confirm text shows both values.
- [x] Exact-price pause/resume preserves both values.
- [x] Final mux receives both values.
- [x] RED included missing one-row/preset assertions; final narrowed GREEN proves
  behavior in both `dub` and `subtitle_plus_dub`.

### SPEC-03.3 — Failure-boundary RED

- [x] Telegram callback ACK failure cannot corrupt pending lane state; existing
  callback owner catches ACK network errors and continues.
- [x] Status edit/send failure cannot abort ASR/engine work; PR #890 focused
  GREEN `2 passed in 10.24s`.
- [!] Bot API 502 coincided with job `FD14FC02D6`; inner ASR error was not
  persisted. No speculative retry patch is permitted in this rollback. Must be
  re-observed during `SPEC-08` and handled only if it recurs.
- [x] Genuine ASR/classifier/TTS/mux errors still fail closed and no-charge.

### SPEC-03 acceptance

- [x] RED failures are product assertions, not import/collection failures.
- [x] Each RED maps to exactly one rollback/compatibility requirement.

## SPEC-04 — Rollback exact lane-2 engine via Git

### SPEC-04.1 — Restore module source

- [x] Restore PR #842 `auto_speaker.py` source using Git object content.
- [x] Do not retype or reinterpret the classifier.
- [x] Verify restored Git blob `6634191cb2c0d463b86d7d9b58ded94e493a7b07`.
- [x] Keep only separately listed current compatibility adapters in `bot.py`.
- [x] Retained selector isolates multi via `auto_speaker_lane="multi"`; retained
  pricing/resume/SRT adapters are later proven fixes and do not alter anchor engine.

### SPEC-04.2 — Restore bot lane-2 owners

- [x] Restore exact PR #842 behavior for each symbol marked `ROLLBACK`.
- [x] Keep current multi dispatch isolated behind `auto_speaker_lane="multi"`.
- [x] Preserve PR #885 pricing fields.
- [x] Preserve PR #887 combo SRT delivery.
- [x] Preserve current UI labels/order outside audio layout.

### SPEC-04.3 — Static scope audit

- [x] `git diff --name-only` contains only allowed files/checklist/tests.
- [x] `auto_multi_speaker.py` hash unchanged: `55AAB894...`.
- [x] No wallet/PayOS/schema/ENV diff.
- [x] No deleted file.

### SPEC-04 acceptance

- [x] Engine parity test GREEN.
- [x] Multi module byte hash unchanged.
- [x] No hand-written replacement algorithm exists; file restored by
  `git restore --source=71c7e881...`.

## SPEC-05 — Restore and lock audio-mix controls

### SPEC-05.1 — UI layout

- [x] `Âm thanh gốc` and `Giọng lồng tiếng` are in one row by behavioral/source test.
- [x] Both modes show Audio from confirmation.
- [x] Back edges remain in the same product/lane.
- [x] No unrelated button moves.

### SPEC-05.2 — State persistence

- [x] Set original audio to measured test value `40%`.
- [x] Set dub voice to measured test value `150%`.
- [x] Back/forward preserves both through canonical state fields.
- [x] Confirmation renders both.
- [x] Auto exact pause snapshot preserves both.
- [x] Resume restores both.

### SPEC-05.3 — Runtime propagation

- [x] `original_audio_volume_percent` reaches mux.
- [x] `dubbed_voice_volume_percent` reaches mux.
- [x] Audio mix applies only after explicit user change.
- [x] Default behavior remains PR #842-compatible.

### SPEC-05 acceptance

- [x] Focused audio-control behavior GREEN for both modes.
- [x] Deployed UI screenshot/DOM shows `Âm thanh gốc` and `Giọng lồng tiếng`
  in one row, with all original/dub presets visible.
- [!] Live confirm keyboard exposed the correct `audio_mix` callback with the
  misleading label `✏️ Sửa theo số dòng`; focused RED reproduced it.

## SPEC-06 — Focused verification only

### SPEC-06.1 — Required focused tests

- [x] Exact PR #842 engine parity.
- [x] Two-speaker preflight/blackbox protected files exercised.
- [x] Nam–nam labels classified independently from own evidence.
- [x] Nam–nữ labels classified independently from own evidence.
- [x] Nữ–nữ labels classified independently from own evidence.
- [x] Ambiguous evidence fail-closed in canonical protected tests.
- [x] Audio controls and mux propagation.
- [x] Combo SRT companion.
- [x] Exact pricing and receipt.
- [x] Admin list price nonzero / charged zero.
- [x] Telegram status/callback failure boundary from PR #890 unchanged.

Note: canonical pure-tone baseline on exact anchor passes low `120/155 Hz` but
fails high `165/170/185/220 Hz`; this is pre-existing anchor behavior, not a
branch regression. Same-gender architecture tests inject measured per-label
evidence; actual nam–nữ accuracy remains gated by the Owner fixture live.

### SPEC-06.2 — Protected comparators

- [x] Multi module hash unchanged.
- [x] Multi isolation selector GREEN.
- [x] Manual/default routing code untouched.
- [x] Subtitle-only production routes untouched.
- [x] No wallet mutation in tests.

### SPEC-06.3 — Static gates

- [x] `python -m py_compile bot.py` exit 0.
- [x] Compile restored module exit 0.
- [x] `git diff --check` exit 0; CRLF warnings only.
- [x] Review full diff before staging; no unrelated production hunk found.
- [x] Four unrelated/stale failures reproduced by direct `origin/main` source
  comparison; invalid harness failure documented. Branch-focused failures fixed.

### SPEC-06 evidence

```text
RED: 4 failed, 1 passed in 0.76s
GREEN: 21 passed, 3 warnings in 583.88s
PROTECTED: 19 passed, 1 warning in 12.27s
SUPERSEDED_TEST_ALIGNMENT: 19 passed, 1 warning in 12.71s
POST_REBASE_FOCUSED: 28 passed, 1 warning in 780.87s
INVALID_INVOCATION: selector-not-found; no assertions ran
BASELINE_BATCH: 33 passed + 14 subtests; 5 stale/harness failures in 4642.72s
PY_COMPILE: bot.py + auto_speaker.py exit 0 before and after rebase
DIFF_CHECK: origin/main...HEAD exit 0 after rebase
FILES_CHANGED: bot.py, auto_speaker.py, audio regression, CJK anchor regression,
per-speaker anchor regression, recovery regression, checklist
PROVIDER_CALLS=0
WALLET_MUTATIONS=0
```

## SPEC-07 — One PR, deploy truth, runtime sync

### SPEC-07.1 — GitHub

- [x] Update this checklist with test evidence.
- [x] One focused commit.
- [x] Push one branch.
- [x] Create PR `#896`.
- [x] Exact main source compile run `32988259783` PASS; PR check attempt was
  cancelled before any step due the repository-wide GitHub runner queue.
- [x] Squash merge.
- [x] PR `https://github.com/manhtoangreensky-wq/bot/pull/896`; merge SHA
  `3fc190c8997e834845550410cd7753cc7c4ec4e1`.

### SPEC-07.2 — Deploy

- [x] GitHub Actions deploy `32988259955` SUCCESS in `4m15s`.
- [x] Bot checkout equals `3fc190c8`.
- [x] Owner worker checkout equals `3fc190c8` after safe fast-forward.
- [x] Worker generation `efc4539da339484c9baece07b89a0147` persisted.
- [x] Reject reason empty.
- [x] Bot/worker/web/nginx active; `/health` OK.

### SPEC-07.3 — Live-found truthful audio label correction

- [x] Fresh combo uploaded the exact Owner fixture once.
- [x] Selected English and `Tự động 2 giọng`.
- [x] Confirm text showed original `Off` and dub `100%`.
- [x] Clicking the misleading `✏️ Sửa theo số dòng` proved its callback was
  actually `videodub|audio_mix` and opened the restored controls.
- [x] RED: expected `🎚 Âm thanh`, got `✏️ Sửa theo số dòng`.
- [x] Minimal production diff: replace two `audio_mix` button labels only;
  callbacks/state/engine unchanged.
- [x] GREEN: `1 passed, 1 warning in 588.26s`.
- [x] Final `py_compile bot.py` exit `0`; diff-check clean.
- [x] Latest main `bc11296` changes landing/docs only; no overlap with the
  three-file live-label correction.
- [-] One focused correction PR/deploy.

### SPEC-07 evidence

```text
PR: #896 https://github.com/manhtoangreensky-wq/bot/pull/896
MERGE_SHA: 3fc190c8997e834845550410cd7753cc7c4ec4e1
DEPLOY_RUN: 32988259955
DEPLOY_DURATION: 4m15s
BOT_SHA: 3fc190c8997e834845550410cd7753cc7c4ec4e1
WORKER_SHA: 3fc190c8997e834845550410cd7753cc7c4ec4e1
GENERATION: efc4539da339484c9baece07b89a0147
REJECT_REASON: empty
```

## SPEC-08 — Live combo: Phụ đề + Lồng tiếng

### SPEC-08.1 — Pre-admission

- [ ] Runtime SHA verified in Telegram/VPS.
- [ ] Correct fixture hash rechecked immediately before upload.
- [ ] Baseline wallet transactions/count/balance captured.
- [ ] Exactly one upload.
- [ ] Select English.
- [ ] Select `Tự động 2 giọng`.
- [ ] Set and record non-default original/dub volume percentages.
- [ ] Confirm exactly once.

### SPEC-08.2 — Observe stages

- [ ] Status panel visible.
- [ ] Source saved with correct SHA.
- [ ] ASR/diarization sidecar exists.
- [ ] Exactly 2 speaker labels.
- [ ] Cast evidence records one low/male and one high/female for fixture.
- [ ] TTS voice IDs come from matching gender pools.
- [ ] User volume values reach mux.
- [ ] Mux produces validated final MP4.
- [ ] Telegram delivery terminal.

### SPEC-08.3 — Artifact/receipt evidence

- [ ] MP4 message id.
- [ ] SRT message id.
- [ ] MP4 SHA-256/bytes/duration/dimensions/codecs.
- [ ] AAC audible measurement.
- [ ] SRT cue count/timeline QC.
- [ ] Receipt says `Tự động 2 giọng`.
- [ ] Receipt shows subtitle price.
- [ ] Receipt shows dubbing price.
- [ ] Receipt shows total.
- [ ] `charged_xu=0` for admin.
- [ ] Wallet transactions unchanged.

### SPEC-08 acceptance

- [ ] Real MP4 + SRT + receipt delivered and independently verified.

## SPEC-09 — Live standalone: Lồng tiếng video

### SPEC-09.1 — Flow

- [ ] Fresh `/subdub` flow.
- [ ] Select `Lồng tiếng video`.
- [ ] Upload same exact fixture once.
- [ ] Select `Tự động 2 giọng`.
- [ ] Set and record non-default original/dub volume percentages.
- [ ] Confirm exactly once.

### SPEC-09.2 — Evidence

- [ ] Two labels and correct male/female pools.
- [ ] MP4 delivered and validated.
- [ ] Receipt shows type, dubbing price, total.
- [ ] Admin charged zero while list price remains nonzero.
- [ ] Wallet unchanged.

### SPEC-09 acceptance

- [ ] Real standalone MP4 + receipt delivered and independently verified.

## SPEC-10 — Lock lane 2 and prohibit future edits

### SPEC-10.1 — Lock manifest

- [ ] List every locked file/symbol.
- [ ] Record source hashes after PASS.
- [ ] Record regression selectors.
- [ ] Record PR/merge/deploy/runtime evidence.
- [ ] Record both live jobs and artifact hashes.
- [ ] Add explicit rule: future tasks must not edit these symbols without a new
  Owner instruction naming lane 2 and a failing live artifact.

### SPEC-10.2 — Completion audit

- [ ] Every SPEC-01…SPEC-09 item has evidence or explicit N/A with reason.
- [ ] No unresolved blocker remains in either 2-speaker lane.
- [ ] Checklist pushed to GitHub.
- [ ] Lane status changed to `LOCKED_LIVE_PASS`.

## SPEC-11 — Multi-speaker only after lane 2 lock

- [B] Evaluate `test nhiều giọng.mp4` after `SPEC-10`.
- [B] Run multi live only after `LOCKED_LIVE_PASS`.
- [B] Never modify a locked lane-2 symbol during multi work.

## Canonical final report schema

```text
TASK=P0 SubDub two-speaker locked recovery
BASE_SHA=
HEAD_SHA=
ANCHOR_SHA=71c7e881f2af24d59c4873f8ca3999f59618daec
FILES_CHANGED=
LOCKED_FILES=
TESTS=
BASELINE_FAILURES=
BRANCH_FAILURES=
NEW_FAILURES=
PROVIDER_CALLS=
WALLET_MUTATIONS=
PR=
MERGE_SHA=
DEPLOY_RUN=
RUNTIME_SHA=
COMBO_JOB=
COMBO_MP4=
COMBO_SRT=
STANDALONE_JOB=
STANDALONE_MP4=
LIVE_PASS=
BLOCKERS=
```
