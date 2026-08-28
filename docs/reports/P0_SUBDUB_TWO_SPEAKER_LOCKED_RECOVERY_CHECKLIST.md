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

- Current SPEC: `SPEC-08`.
- Current SUBSPEC: `SPEC-08.0F.4`.
- Current phase: `BLOCKED_BY_SHARED_RESOURCE / source READY_TO_SHIP`.
- Production action active: `NO; Product Video currently owns LIVE/CHROME/VPS`.
- Telegram/provider job active: `NO; job #6DC569C0A6 terminal failed_no_charge`.
- Wallet mutation: `0`.
- Next allowed action: wait for exact Product Video LIVE/CHROME/VPS/DEPLOY
  releases, then fetch/rebase latest main, run one post-rebase focused gate,
  create one commit/PR, squash merge, deploy/runtime readback and combo live.
- Next forbidden action: ship the raw-frame/YIN fallback; edit shared
  classifier/cast thresholds, audio UI, pricing, wallet, TTS/mux, multi engine;
  start Telegram/provider/VPS action while Product Video owns the shared slot;
  or move to standalone/multi before the combo artifact passes.

### Task contract — active SPEC-08 correction

- `GOAL`: exact fixture SHA `85C8793D...` produces a real combo MP4 + SRT +
  receipt with independently detected male/female speaker groups; then the same
  fixture produces a standalone dubbed MP4; only then lock lane 2 and open
  multi-speaker work.
- `SCOPE`: replace only the failed exact-two singing-gender authority after the
  already-passing Key4U ASR + Gemini diarization boundary.
- `BASE_SHA`: local task HEAD
  `8965cbc0863a9546d625d80a67bebc76bc33e9dd`; remote rebase is deferred until
  Product Video releases shared Git/LIVE/VPS and source GREEN is terminal.
- `ALLOWED_FILES`:
  - new `services/subdub_two_speaker_gender_onnx.py`;
  - `services/subdub_blackboxes/auto_speaker.py`, exact-two integration only;
  - `bot.py`, only `_extract_subdub_auto_pcm` exact stereo contract;
  - `assets/models/subdub_auto_gender/*`, the two hash-locked ONNX models and
    their MIT/CC-BY notices;
  - `requirements.txt` / `requirements.lock`, only to pin NumPy/ONNX Runtime
    for the production Linux/Python 3.11 runtime;
  - `.github/workflows/deploy-vps.yml` and its existing contract test, only to
    sync the target hash-locked dependencies before bot restart;
  - dedicated exact-two ONNX tests, the two existing lane-lock tests, this
    checklist, tester docs and durable state.
- `PROTECTED_FILES`: `services/subdub_blackboxes/auto_multi_speaker.py` SHA-256
  `55AAB894...`; `services/subdub_speaker_cast.py` SHA-256 `DE93620F...`;
  `services/subdub_two_speaker_asr_fallback.py` SHA-256 `94748DEF...`; audio
  UI/state, Key4U transport/retry, Gemini parser, pricing/wallet, TTS/mux and
  Product Video remain semantically unchanged.
- `ACCEPTANCE`: independent `male-male`, `male-female`, `female-female` are
  legal; tie/weak/missing/hash/deadline/cancel is fail-closed; exact fixture
  groups are `speaker_0=male/low` and `speaker_1=female/high`; evidence is at
  most 48 unique seconds; provider calls and wallet mutations are zero.
- `TARGETED_TESTS`: dedicated service contract + exact-two preflight stereo
  integration + cleanup + extractor validation, first observed RED and then
  fresh GREEN.
- `REGRESSION_TESTS`: two/multi isolation, protected hashes, timeout/cancel,
  audio numeric UI, pricing/receipt and no-provider/no-wallet comparators.
- `PROHIBITED_ACTIONS`: no forced opposite-gender pairing, threshold loosening,
  generative gender authority, paid provider test, ENV/secret or wallet change,
  UI redesign, refactor of shared modules, premature Telegram live.
- `STOP_CONDITIONS`: any protected hash changes, aggregate evidence exceeds
  48 seconds, model/license/hash cannot be verified, a new applicable failure
  appears, or LIVE produces no real final MP4/SRT/receipt.

### Luật bất biến

- Không có ô checklist tương ứng ⇒ không được làm.
- Không xóa file, DB, artifact, table hoặc user data.
- Không `git reset --hard`, không checkout đè working tree, không xóa `artifacts/`.
- Không sửa Product Video, PayOS, wallet, ENV/secrets, onboarding, PWA.
- Không sửa/chạy live lane nhiều giọng trước khi `SPEC-10` hoàn tất.
- Shared audio UI must remain numeric-only for both `Lồng tiếng video` and
  `Phụ đề + Lồng tiếng`, independent of default, saved, custom, Auto 2-speaker,
  or Auto multi-speaker voice selection.
- Không được tái tạo grid `Gốc xx%` / `Lồng xx%` hoặc callback preset
  `audio_original_volume` / `audio_dub_volume`.
- Không dùng `Download.mp4`.
- Không dùng fixture lịch sử `test 2 giọng.mp4` cho acceptance cuối.
- Không công nhận PASS từ mock, metadata, HTTP 200 hoặc job id.
- `MERGED != DEPLOYED != LIVE`.
- Lane 2 chỉ được khóa sau hai MP4 thật: combo và standalone.

## 1. Source truth và phạm vi khóa

### Mốc rollback composite bắt buộc

| Phần | Mốc | Giá trị/bằng chứng |
| --- | --- | --- |
| Engine/PCM đã giao MP4 | PR `#842` | SHA `71c7e881...`; job `#7BC3037DF8`; video `26895`; receipt `26896`; charged `0` |
| Bảng/receipt hoàn thiện Owner nhớ | PR `#846` | SHA `2ccba0e...`; giữ snapshot receipt sau delivery, không đổi classifier |
| Full lane gần nhất trước pitch drift | PR `#852` | SHA `ebe77bc...`; gồm #846 và callback ACK best-effort |
| Mốc bị loại | PR `#853` | SHA `7b4053a...`; thêm band-pass/denoise và hạ pitch-frame `2 → 1` |

Không có một SHA duy nhất đại diện cả engine đã giao MP4 và bảng receipt mới
nhất. Rollback đúng là **composite**: engine/PCM pre-#853 của #842, receipt #846,
callback resilience #852, rồi giữ các correction pricing/SRT/UI đã có test.
PR #847 là Product Video, không thuộc SubDub.

Historical job `#7BC3037DF8` dùng fixture SHA `a89b16b8...`, không phải fixture
Owner acceptance hiện tại `85c8793d...`. Vì vậy mốc lịch sử chỉ chứng minh
engine baseline; fixture hiện tại vẫn bắt buộc giao MP4 live mới.

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
| Public job | `#6DC569C0A6` |
| Internal job | `6dc569c0a6200b6355e9` |
| Mode | `subtitle_plus_dub` |
| Terminal | `failed_no_charge` |
| Runtime | `77fee7ce472ffa65c32d91e248b87fee38fcb69b` |
| ASR/diarization | `PASS`; Key4U transcript + Gemini labels; `18` cues, speakers `8/10` |
| Failure boundary | after sidecar/cast input persistence; before TTS, dub audio, mux and delivery |
| charged_xu | `0` |
| Wallet | credits `200`, total_spent `0`, transactions `0`, credit_events `1` |

### Allowed production scope

- `services/subdub_two_speaker_gender_onnx.py`: bounded exact-two UVR-small +
  PANNs ONNX authority; no network/provider path.
- `services/subdub_blackboxes/auto_speaker.py`: exact-two service integration
  and guaranteed transient-PCM cleanup only.
- `assets/models/subdub_auto_gender/*`: only hash-locked model/license assets.
- `bot.py`: only exact lane-2 dispatch/compatibility and audio-mix UI/state symbols
  listed in `SPEC-02`.
- `bot.py`: `_extract_subdub_auto_pcm` may add only stereo `44,100 Hz` `s16le`
  beside the protected mono `16,000 Hz` contract; no filter or UI change.
- `bot.py`: live-failure exception for the scoped
  `subdub_deepgram_request_params(require_diarization=True)` model only; default
  non-diarized ASR remains unchanged.
- `bot.py`: UI follow-up may only remove PR #896 fixed-percentage rows/actions
  from `subdub_audio_mix_keyboard`, `subdub_dynamic_volume_ui_future_spec`, and
  the audio-action branch in `handle_video_dubbing_callback`.
- A new regression test file dedicated to this recovery.
- This checklist and final evidence report.

### Protected production scope

- `services/subdub_blackboxes/auto_multi_speaker.py`: byte-locked; no edit.
- Multi callback marker/state (`auto_speaker_lane="multi"`): no semantic edit.
- `services/subdub_speaker_cast.py`: Git blob `9f763b38...`, equal at PR #842,
  #846 and #852; no edit.
- `bot.py`: hunk receipt #846 and callback ACK #852 must remain present.
- Current two-button voice UI labels/order: preserve; both buttons remain one row.
- Shared numeric input owners `subdub_audio_layer_keyboard` and
  `handle_video_dubbing_pending_text` remain intact: original `0–100`, dub
  `0–200`, with state/mux propagation unchanged.
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
- [x] Confirm PR #846 is the post-delivery receipt/table anchor, not a
  classifier change.
- [x] Confirm PR #852 is the last SubDub full-lane merge before #853.
- [x] Confirm PR #847 belongs to Product Video and is not a SubDub anchor.
- [x] Confirm historical delivered fixture SHA `a89b16...` differs from current
  acceptance fixture SHA `85c879...`.

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
- [x] `subdub_audio_mix_keyboard` — preserve the two category buttons on one row
  while removing the fixed-percentage grid added by PR #896.
- [x] `subdub_audio_layer_keyboard` — preserve the compact toggle/numeric input
  submenu; no preset controls.
- [x] `handle_video_dubbing_callback` audio actions — remove only PR #896 preset
  actions; preserve numeric input callbacks.
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
| audio controls | numeric submenu before PR #896 | PR #896 added preset grid | REMOVE PRESET + preserve one-row category layout | UI/callback tests |
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
reason: historical engine/font/layout assertions; preset expectations are now
  explicitly superseded by `SPEC-07.4`
```

### SPEC-03.2 — Audio controls RED

Both `dub` and `subtitle_plus_dub`:

- [x] Confirm screen exposes `videodub|audio_mix`.
- [x] Audio screen exposes `audio_original` and `audio_dub` **same row**.
- [x] Original layer supports off/on and numeric input `0–100` only.
- [x] Dub layer supports numeric input `0–200` only.
- [x] Original percent range is bounded and persists.
- [x] Dub percent range is bounded and persists.
- [x] Back returns to same lane confirm.
- [x] Confirm text shows both values.
- [x] Exact-price pause/resume preserves both values.
- [x] Final mux receives both values.
- [x] Original PR #896 RED/rollback history is retained as evidence only.
- [x] Current compact-UI RED failed all `3` assertions before rollback; current
  source removes the preset rows/actions while preserving numeric owners.

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
- [x] Main audio screen contains only the two layer buttons plus Back.
- [x] Original submenu contains only toggle, numeric input and Back.
- [x] Dub submenu contains only numeric input and Back.
- [x] The same owner is used for default female, default male, voice vault,
  custom voice, Auto 2-speaker and Auto multi-speaker selections.

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

- [x] Current source-focused batch exercised both modes, 12 lane/voice matrix
  cases, numeric `40/150` persistence, state and mux propagation.
- [!] PR #896 deployed fixed-percentage rows; Owner rejected this as a UI
  regression. It is evidence of the defect, never an accepted baseline.
- [ ] Follow-up runtime must show `Âm thanh gốc | Giọng lồng tiếng` on one row,
  no `Gốc xx%` / `Lồng xx%`, and both numeric submenus.

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
- [x] One focused correction PR/deploy: PR `#899`, merge SHA `397ca576...`.

### SPEC-07.4 — Remove PR #896 preset-grid regression everywhere

#### SPEC-07.4A — Root cause and RED

- [x] Git diff proves PR #896 / `3fc190c...` added every fixed-percentage row,
  the two preset callback actions and `public_fixed_percentage_grid=True`.
- [x] Pre-#896 source proves compact numeric submenus already existed.
- [x] Dedicated RED `tests/test_p0_subdub_compact_numeric_audio_ui.py` terminal:
  `3 failed in 3.84s` before the production rollback.

#### SPEC-07.4B — Minimal BUILD and focused verification

- [x] Production diff is exactly `bot.py`: `1` insertion / `32` deletions;
  the insertion is only `public_fixed_percentage_grid=False` replacing `True`.
- [x] No production function outside the shared audio UI/action owner changed.
- [x] Two stale tests no longer demand preset callbacks.
- [x] Matrix covers `dub` + `subtitle_plus_dub` across default female, default
  male, voice vault, custom voice, Auto 2-speaker and Auto multi-speaker.
- [x] Numeric callbacks persist original `40%` and dub `150%` in both lanes.
- [x] Combined terminal: `58 passed, 1 skipped, 1 baseline failure in 548.67s`.
- [x] Sole failure is unrelated stale copy: test expects `Chi phí:` while exact
  `HEAD` receipt owner emits `Giá:`; receipt test file and receipt owner have no
  branch diff, so `NEW_FAILURES=0`.
- [x] Final branch-focused GREEN terminal: `35 passed, 3 warnings in 12.44s`,
  exit `0`; warnings are Google GenAI and existing `re.split` deprecations only.
- [x] Locked engines remain unedited; expected SHA-256 values:
  `auto_speaker=49E905C0...`, `auto_multi=55AAB894...`,
  `subdub_speaker_cast=DE93620F...`.
- [x] Final `py_compile bot.py` and current test files exit `0`.
- [x] YAML parser check for durable state + `2` SubDub issue templates:
  `YAML_OK 3`, exit `0`; no dependency install.
- [x] `git diff --check` exits `0` (line-ending warnings only).

#### SPEC-07.4C — One follow-up PR/deploy/runtime proof

- [x] Reacquired shared Git/LIVE/VPS after exact Product Video releases.
- [x] Fetched/rebased onto `origin/main 82ffb117...`; Git skipped upstream
  `ac7cb76` from PR #908 and retained exactly one follow-up commit.
- [x] Branch after rebase is `0 behind / 1 ahead`; production diff remains
  `bot.py` only, `1` insertion / `32` deletions.
- [x] Post-rebase focused GREEN: `35 passed, 3 warnings in 489.20s`, exit `0`.
- [x] Post-rebase compile of `bot.py` + three audio contract files and range
  `git diff --check origin/main...HEAD`: exit `0`.
- [x] Push one focused commit, PR `#911`, squash merge
  `4458d4c29ea7f63022ec7746ebff785a36f7974e`.
- [x] Deploy run `33082986178` SUCCESS in `4m04s`; VPS and Telegram runtime
  exact `4458d4c`, bot/web/nginx active, health OK.
- [x] Runtime UI proves only `Âm thanh gốc | Giọng lồng tiếng` on one row,
  numeric `0–100 / 0–200`, and no fixed-percentage preset callbacks.

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

### SPEC-08.0 — Live failure loop: multilingual diarized ASR

- [x] RED proves the diarized request still selects `nova-2` instead of the
  current Deepgram multi-speaker/multilingual model `nova-3-general`.
- [x] Exact fixture is Mandarin Chinese with two visible speakers and Chinese
  hard subtitles; six-frame contact sheet inspected.
- [x] Source audio is AAC stereo `48.344s`; decoded mono signal mean `-12.2 dB`,
  max `0.0 dB`, with no `>-0.5s` silence below `-35 dB`.
- [x] Job `#EE4E7E69CD` saved exact source SHA `85C8793D...` and normalized MP4,
  then terminalized `empty_transcript` before sidecar/cast/TTS/mux.
- [x] Official Deepgram docs checked: Nova-3 is recommended for multi-speaker,
  multilingual, noisy/far-field batch audio and supports Chinese `zh`.
- [x] Minimal GREEN changes only the diarized model to `nova-3-general`.
- [x] Default/non-diarized request remains `nova-2`.
- [x] PR `#903` merged as `43d8664...`; deploy run `33015967128` SUCCESS;
  bot/worker same SHA and owner generation heartbeat accepted.
- [!] Same-fixture retry did not reach ASR because Telegram progress edit 502
  terminalized the callback first; continued in `SPEC-08.0B`.

Measured source evidence:

```text
RED: 1 failed, 1 warning in 460.89s
RED assertion: expected nova-3-general; actual nova-2
INVALID first GREEN: collection SyntaxError after apply-patch mechanically lost
2,004 unrelated Product Video lines; no assertion ran; restored exact origin/main
GREEN source-only AST: 1 passed in 534.54s
PROTECTED: 9 passed, 1 warning in 1002.61s
PY_COMPILE: bot.py exit 0
DIFF_CHECK: exit 0; CRLF warnings only
PROTECTED_HASHES: auto_multi_speaker=55AAB894...;
subdub_speaker_cast=DE93620F...
PRODUCTION_DIFF: bot.py +1 line in scoped diarized request helper
```

### SPEC-08.0B — Live failure loop: combo progress edit 502

- [x] Same-flow final confirm reached callback `videodub|combo_full_dub`.
- [x] Telegram Bot API returned `502 Bad Gateway` at `bot.py:253539` while
  rendering the initial combo progress text.
- [x] No pipeline workspace/job/provider/wallet mutation occurred.
- [x] RED reached the exact line with pipeline call count `0`:
  `1 failed, 1 warning in 523.88s`.
- [x] Minimal patch catches only the progress render exception; state remains
  final-confirmed and executor runs once.
- [x] GREEN: `1 passed, 1 warning in 662.31s`.
- [x] Protected batch: new 502 selector + background status `2` cases + exact
  #842 engine blob passed; `4 passed`. Two adjacent legacy callback tests failed
  before their target because their test fixtures omit `created_at_ts`; same
  failure reproduced on exact `origin/main 43d8664`: `2 failed, 1 warning in
  521.11s`, same two test names. `NEW_FAILURES=0`.
- [x] `py_compile bot.py` and regression test exit `0`; diff-check clean.
- [x] Production diff is `7` added / `1` removed line, only around the combo
  progress edit. Engine/cast/multi hashes unchanged.
- [x] Rebased onto exact `origin/main 43d8664`; post-rebase GREEN
  `1 passed, 1 warning in 464.66s`; compile/diff/hash gates pass.
- [x] PR `#904` merged as `8d23bbf1a09dee8d43896bad963a800d3dd25cda`.
- [x] Deploy run `33045092186` SUCCESS in `10m40s`; bot runtime matches merge SHA.
- [x] Same-fixture retry reached real pipeline stage `35% / Nhận diện lời thoại`,
  proving the initial progress edit can no longer abort the executor.

### SPEC-08.0C — Live failure loop: exact fixture ASR/provider root cause

- [x] Fresh combo job `#19A16753A4` used exact fixture SHA `85C8793D...`,
  workspace `/tmp/toan_aas_pipeline/19a16753a4491d975921`, then terminalized
  `empty_transcript` before sidecar/cast/TTS/mux/delivery.
- [x] Persisted provider attempt is `DEEPGRAM_EMPTY_TRANSCRIPT`; charged Xu and
  wallet mutations remain `0`.
- [x] Bounded Deepgram replay on extracted mono MP3 (`582,540` bytes) returned
  HTTP `200`, detected `id` at confidence `0.31629473`, but transcript/words/
  speaker IDs all `0`; retry pinned to `id` remained empty.
- [x] ShopAIKey is not a usable fallback for this fixture: diarized/GPT models
  return `model_not_found`; `whisper-1` returned `429 do_request_failed`.
- [x] Key4U legacy `.shop` OpenAI base has a TLS certificate verification failure;
  TLS verification was never disabled. Canonical documented `.vn/v1` is healthy.
- [x] Key4U canonical `gpt-4o-transcribe` returns HTTP `200` and `142` chars.
- [x] Key4U canonical `whisper-1 verbose_json` returns HTTP `200`, language
  `chinese`, `145` chars and `18/18` timestamped segments covering `0..48s`.
- [x] Neither ShopAIKey nor Key4U exposes `gpt-4o-transcribe-diarize`; exact
  diarized requests fail and no speaker labels are returned.
- [x] Rejected acoustic heuristic: spectral clustering produced an outlier split
  `2/16`; pitch evidence existed for only `1/18` cue and did not match visible
  speaker turns on the contact sheet.
- [x] Rejected visual-only heuristic: two Key4U vision models agreed on only
  `11/18` cues (`61.1111%`), with one model collapsing `16/18` cues to one person.
- [x] Rejected stereo heuristic: channel balance spans only `1.3457 dB`, maximum
  absolute balance `1.052 dB`, and correlation is `0.695482..0.931335`; microphones
  are not cleanly isolated by channel.
- [x] Provider research found the first dedicated replacement contract with real
  diarization: official Gemini `gemini-3.5-transcribe` supports speaker labels
  and word timestamps (up to eight speakers). The installed Google GenAI SDK has
  Interactions and audio input types; no dependency install is required.
- [x] Next single diagnostic: call Gemini Transcribe once on the exact normalized
  fixture with `zh-CN`, verbatim mode, `diarization_mode=speaker`, and word
  timestamps. Accept only exactly two returned speakers, each with at least two
  timed annotations; otherwise remain fail-closed. Key4U Whisper remains the
  already-proven transcript/timestamp fallback if Gemini transcript text needs
  cue reconciliation.
- [x] Gemini Transcribe diagnostic PASS: HTTP `200`, exactly `2` speaker labels,
  `125/125` timed word annotations (`58` vs `67` words), schema fields
  `text/speaker/start_offset/end_offset` with second offsets.
- [x] Key4U-to-Gemini reconciliation maps all `18/18` Key4U Whisper cue windows,
  minimum per-cue dominance `1.0`, split `8/10`; no forced label exists.
- [x] Final RED for Key4U cues + Gemini speaker labels and live route wiring:
  `3 failed, 2 passed, 1 warning in 8.43s`. Two product failures are the
  missing `allow_two_speaker_key4u_fallback` gate; one proves the exact
  two-speaker preparation path does not forward it. The protected multi/default
  route stops after Deepgram and makes exactly `0` fallback calls.
- [x] Focused GREEN: `5 passed, 1 warning in 1523.09s (0:25:23)`; warning only
  Google GenAI deprecation. Includes exact two-speaker wiring, protected
  multi/default zero-fallback behavior, and single-speaker fail-closed behavior.
- [x] Independent review RED reopened four gaps: permissive Gemini annotation
  parsing; synthetic Key4U timestamps; legacy `.shop` endpoint; unbounded
  chunked fallback. Service RED `1 failed, 4 passed in 0.97s`; bot RED
  `3 failed in 610.67s`.
- [x] Review-fix GREEN: service parser/request `5 passed in 0.51s`; full focused
  bot route/provenance/long guard `7 passed, 1 warning in 540.56s`.
- [x] Final protected comparator batch: `19 passed, 1 warning in 543.25s`;
  warning only Google GenAI deprecation.
- [x] `py_compile bot.py services/subdub_two_speaker_asr_fallback.py` plus focused
  test exits `0`; `git diff --check` exits `0`.
- [x] Locked source hashes remain exact:
  `auto_speaker=49E905C0...`, `auto_multi=55AAB894...`,
  `subdub_speaker_cast=DE93620F...`.
- [x] Diagnostic provider requests made in this root-cause round: `22`; wallet,
  Telegram job admission and Xu mutations during diagnostics: `0`.
- [x] Independent re-review: no Critical/Important code blocker; verdict
  `Ready to merge: Yes`. Synthetic timestamps, legacy hostname, long-media
  provider budget and permissive parser findings are all closed by tests above.
- [x] Pre-push operating docs, original-vs-current comparison, tester guide and
  issue templates updated because Owner explicitly requires the ordered
  checklist/evidence handoff on GitHub in this same focused recovery PR.
- [x] PR `#908` merged as `71434bd6254ac12e747bf6f6e144583ba3435f08`.
- [x] Deploy run `33070712713` SUCCESS in `8m29s`; bot/worker runtime identity
  verified before the UI regression follow-up.
- [B] Restart the same exact-fixture combo only after `SPEC-07.4C` deploy proves
  compact numeric UI on the new runtime.

### SPEC-08.0D — Live failure loop: Key4U two-speaker transcript unavailable

#### SPEC-08.0D.1 — Exact live evidence

- [x] Runtime `4458d4c`; fresh flow selected combo, English, `Tự động 2 giọng`,
  original `40%`, dub `150%`, then confirmed exactly once.
- [x] Public/internal job `#00911B6FF0` /
  `00911b6ff01590de3834`; workspace
  `/tmp/toan_aas_pipeline/00911b6ff01590de3834`.
- [x] Original fixture persisted at exactly `4,284,017` bytes and SHA-256
  `85c8793d197cf2782bb554d46282e82a83bcb062a0483e412a0ca1da668f9f51`.
- [x] Media preflight PASS: duration `48.4s`, H.264 `576×884`, AAC stereo
  `44.1kHz`; normalized processing SHA `a9572c8f...`.
- [x] Terminal `failed_no_charge`; MP4/SRT/delivery all absent; Owner
  `credits=200`, `total_spent=0`, transactions `0`, credit events `1`.
- [x] Persisted provider attempt at `22:54:49`:
  `key4u_audio+gemini_diarization / two_speaker_fallback /
  AUTO_CAST_UNAVAILABLE / key4u_two_speaker_transcript_unavailable`.
- [x] Runtime config is correct and non-secret readback confirms:
  TTS provider `key4u_minimax`, Key4U host `api.key4u.vn`, endpoint
  `/audio/transcriptions`, model `whisper-1`, and Key4U/Gemini/Deepgram
  keys all PRESENT.
- [x] Classifier/cast/TTS/mux did not run; do not edit their locked source.

#### SPEC-08.0D.2 — One bounded production-contract diagnostic

- [x] Extract mono MP3 exactly like production: `-vn -ac 1 -ar 16000
  -c:a libmp3lame -b:a 96k`.
- [x] Make exactly one Key4U canonical `.vn` `whisper-1 verbose_json`
  transcription request on the same fixture.
- [x] Record only sanitized HTTP/status/chars/segment/timestamp evidence; never
  persist or print API key/raw provider body.

Measured evidence:

- Production-equivalent mono MP3: `582,540` bytes.
- Key4U call count: exactly `1`.
- HTTP `200`, model `whisper-1`, format `verbose_json`, language
  `chinese`, transcript `145` chars.
- `18/18` provider-timed segments cover `0.0..48.0s`; duration
  `48.4000015s`; no raw text/body/key persisted.
- This proves the contract/fixture/model are usable and the live failure is a
  transient unusable first response; the current one-shot boundary has no
  bounded retry.

#### SPEC-08.0D.3 — RED from exact diagnostic

- [x] If upstream returns a usable timed transcript, RED proves the live adapter
  loses/normalizes the successful payload incorrectly.
- [x] If upstream returns a transient/retryable failure, RED proves the confirmed
  exact two-speaker fallback has no bounded retry/evidence preservation.
- [x] If upstream returns a permanent contract failure, stop and report the exact
  blocker; do not patch around it or force speaker labels.

RED evidence:

- Selector: two service-only retry/permanent-failure cases, no network.
- Terminal: `2 failed in 0.88s`.
- Transient case failed because result stayed `ok=False` after attempt 1.
- Permanent case failed because attempt-count evidence did not exist.

#### SPEC-08.0D.4 — Minimal fix and protected GREEN

- [x] Change only the exact Key4U fallback request/result boundary proven by RED.
- [x] Preserve Deepgram-first policy, Gemini schema parser, classifier/cast,
  multi lane, UI, pricing, wallet, TTS and mux.
- [x] Run focused GREEN, protected two/multi isolation, locked hashes,
  `py_compile` and `git diff --check`.

GREEN evidence:

- Exact two retry/permanent selectors: `2 passed in 0.48s`.
- Full fallback service file: `7 passed in 0.43s`.
- Bot exact-two wiring + default/multi isolation: `7 passed, 1 warning in
  11.73s`; warning only Google GenAI deprecation.
- Locked engine/multi hash selectors: `2 passed, 1 warning in 7.95s`.
- `py_compile` service + changed test: exit `0`.
- `git diff --check`: exit `0`.
- Production diff: only `services/subdub_two_speaker_asr_fallback.py`.
- Retry policy: maximum `2` Key4U attempts; `1s` delay; retry only
  unusable results with HTTP `0/2xx/408/425/429/5xx` or bounded
  timeout/provider/empty statuses. Permanent `401` and provider-timestamp
  invalid responses stop before Gemini.

#### SPEC-08.0D.5 — Ship and retry

- [x] Rebased onto `origin/main
  4458d4c29ea7f63022ec7746ebff785a36f7974e`; upstream UI commit skipped
  naturally; branch `0 behind / 1 ahead`, head `c9112b0`.
- [x] Post-rebase combined fallback/wiring/isolation/hash gate:
  `16 passed, 1 warning in 11.87s`.
- [x] Post-rebase `py_compile` service + test and range diff-check: exit `0`.
- [x] One focused PR `#912`, squash merge
  `a9471b65b558128a8c5e28a18c887acf73d8e60c`, deploy run `33097609372`
  SUCCESS in `6m27s`; bot/web/nginx active, health OK, runtime constants exact.
- [!] Fresh exact-fixture combo retry job `#A86321F62B` /
  `a86321f62b714edbc342` terminalized before artifacts:
  `key4u_two_speaker_transcript_unavailable:attempts=2;http=0;
  status=FAIL_PROVIDER_ERROR`.
- [B] Remain in SPEC-08 until real artifact acceptance; do not start SPEC-09/11.

### SPEC-08.0E — Live failure loop: production HTTP transport

#### SPEC-08.0E.1 — Exact transport diagnostic

- [x] Raw bounded Key4U multipart request on the same `582,540`-byte audio
  succeeds HTTP `200` with `18` timed segments.
- [x] Production fallback made exactly `2` attempts and both returned
  `http=0 / FAIL_PROVIDER_ERROR`.
- [x] Make exactly one request through the actual production
  `openai_compatible_asr_transcribe/httpx` adapter with the same audio/config.
- [x] Record sanitized exception/detail only; never print key/raw body.

Measured result:

- Production-equivalent audio: `582,540` bytes.
- Provider calls: exactly `1`.
- Result: `FAIL_PROVIDER_ERROR`, HTTP `0`, chars/segments `0`.
- Sanitized exception:
  `Attempted to send an sync request with an AsyncClient instance.`
- Root cause: multipart form `data` is a sync `list[tuple]` stream submitted
  through `httpx.AsyncClient`; request fails before reaching Key4U.

#### SPEC-08.0E.2 — RED and minimal transport fix

- [x] Write RED from the exact sanitized exception and the working repository
  transport pattern.
- [x] Change only the production Key4U/OpenAI-compatible HTTP transport boundary.
- [x] Do not change retry count, provider order, Gemini, classifier/cast, multi,
  UI, pricing, wallet, TTS, or mux.

GREEN evidence:

- Exact real-httpx MockTransport selector:
  `1 passed, 1 warning in 607.69s`.
- Full Key4U/Gemini + fallback service + locked hash batch:
  `17 passed, 1 warning in 9.72s`.
- `py_compile bot.py`, fallback service and two focused tests: exit `0`.
- `git diff --check`: exit `0`.
- Production diff is one function in `bot.py`: multipart form fields changed
  from sync `list[tuple]` to async-compatible `dict`; field names/values
  unchanged.

RED evidence:

- Real `httpx.AsyncClient + MockTransport`, no network.
- Terminal: `1 failed, 2 warnings in 14.26s`.
- Failure: expected `result["ok"] is True`, actual `False`; request never
  reached the async MockTransport handler.

#### SPEC-08.0E.3 — GREEN, ship, retry

- [x] Focused/protected GREEN, hashes, compile/diff.
- [x] Scoped local commit `710c7df`; no push/PR/deploy while Product Video
  owns shared resources.
- [x] Rebased onto `origin/main
  a9471b65b558128a8c5e28a18c887acf73d8e60c`; retry commit #912 skipped
  naturally; branch `0 behind / 1 ahead`, head `bc33e2d` before evidence
  amend.
- [x] Post-rebase protected batch: `17 passed, 1 warning in 546.00s`.
- [x] Post-rebase `py_compile bot.py` + transport test and range diff-check:
  exit `0`.
- [x] Rebased again onto latest Product Video main
  `ccf9523613418dfd37535f14901173624d5cbc3e`; branch stayed
  `0 behind / 1 ahead`, head `e4ff883` before evidence amend.
- [x] Latest-main protected batch: `17 passed, 1 warning in 541.67s`.
- [x] Independent Claude technical review: list-tuples sync stream is a
  plausible and evidence-matched httpx root cause; dict preserves all unique
  multipart fields; fix is the smallest valid change; no Critical/Important
  blocker before deploy. Optional extra field-shape test is not required.
- [x] Final rebase onto Trend4 main
  `d92a98ddbc10ea4c626f75a65c2ddb58403a2fc6`; branch
  `0 behind / 1 ahead`, head `93bfca7` before evidence amend.
- [x] Exact latest-main transport selector:
  `1 passed, 1 warning in 542.49s`.
- [x] Latest-main `py_compile bot.py` + transport test and range diff-check:
  exit `0`.
- [x] One PR `#915`, squash/deploy/runtime readback at
  `77fee7ce472ffa65c32d91e248b87fee38fcb69b`; deploy run `33111291104`
  SUCCESS in `5m45s`; bot/web/nginx active and tracked VPS diff clean.
- [!] Exact combo retry `#6DC569C0A6` passed transport/ASR/diarization and
  persisted `18` cues with exactly two labels (`speaker_0=8`, `speaker_1=10`),
  then stopped before TTS/mux/delivery. Continue at `SPEC-08.0F`; do not reopen
  transport or start standalone/multi.

### SPEC-08.0F — Live failure loop: exact acoustic cast boundary

#### SPEC-08.0F.1 — Exact production classifier diagnostic

- [x] Update this checklist and durable state to job `#6DC569C0A6` before any
  source diagnostic.
- [x] Use only fixture `2 giọng nam nữ.mp4` SHA-256 `85C8793D...`, its
  production-normalized PCM (`mono`, `16 kHz`, `s16le`) and the exact persisted
  18-cue speaker ranges; no provider/network/Telegram call.
- [x] Call the production owner
  `subdub_speaker_cast.classify_speaker_registers(...)` with a bounded 30-second
  deadline and a non-cancelling stop callback.
- [x] Record per-speaker register, confidence and returned acoustic evidence, or
  the exact `AUTO_CAST_MANUAL_REQUIRED` / `AUTO_CAST_UNAVAILABLE` exception.
- [x] State one falsifiable root-cause hypothesis from this output. Do not edit
  production source in this SUBSPEC.

Measured evidence:

- Exact fixture: `4,284,017` bytes, SHA-256 `85C8793D...`; extracted PCM:
  `1,547,794` bytes, mono `16 kHz` `s16le`, SHA-256 `82F1FFB6...`.
- Exact production call returned `AUTO_CAST_MANUAL_REQUIRED` in `0.265s` after
  trying all `18` selected windows for `speaker_0`; all `18` yielded no accepted
  pitch, so `speaker_1` was never evaluated.
- Signal is not silent: production-selected RMS spans `0.154301..0.269327`,
  peak spans `0.652008..0.923553`.
- Dense `0.25s` scan measured `81` windows for `speaker_0` and `105` for
  `speaker_1`: `156` lacked two pitch frames; `14` had a stable competing
  pitch; the remainder mostly failed purity/confidence/stability gates.
- Only four windows survived: speaker 0 `72.398 Hz`; speaker 1
  `260.135 / 131.148 / 130.753 Hz`. The speaker-1 evidence conflicts across
  registers, so relaxing a threshold or forcing opposite genders would guess.
- Falsifiable root-cause hypothesis: karaoke backing audio is present inside
  diarized cue windows and the raw full-mix PCM does not provide stable,
  speaker-specific F0 evidence. Inspect whether the existing diarization
  response already carries independent acoustic/gender evidence before RED;
  otherwise the failing boundary is classifier input, not its thresholds.

Verify:

```text
python .agents/tools/subdub_exact_cast_diagnostic.py
expected: exact fixture/sidecar hashes, two speaker labels, then either two
measured register results or one exact fail-closed exception; provider_calls=0
```

#### SPEC-08.0F.2 — Historical raw-frame RED (rejected after review)

- [x] Inspect the exact diarization parser/result contract for speaker-specific
  acoustic or gender evidence before choosing the RED seam; no provider call.
- [x] Exact Gemini annotations contain only `text`, `speaker`, `start_offset`
  and `end_offset`; no gender/acoustic field is discarded by the parser.
- [x] Reject the old #853 / protected-multi audio filter comparator: it returns
  `high/high` on this male/female fixture and therefore cannot be restored.
- [x] Exact raw-PCM sparse-offset frame evidence resolves independently:
  speaker 0 `3 low / 0 high`, median `87.073 Hz`, weight ratio `1.0`;
  speaker 1 `9 high / 5 low`, median high `198.813 Hz`, weight ratio
  `0.661405`. No opposite-gender constraint is used.
- [x] Source history proves PR `#889` already contained the fail-closed
  `_independent_two_speaker_classifications` contract for low/low, low/high and
  high/high, but rollback PR `#896` removed it with the whole-file #842 restore.
- [x] Write one no-network RED that restores the PR #889 independent helper and
  feeds it bounded known pitch-frame evidence from the same raw PCM/sparse
  offsets after the anchor whole-window classifier fails.
- [B] If the production classifier returns both casts, RED the wrapper/preflight
  propagation that discards them before TTS.
- [B] If it fails on input/ranges, RED the exact normalization/merge boundary;
  do not change thresholds first.
- [B] If acoustic evidence itself is insufficient, RED only the smallest
  fail-closed classifier contract needed for this fixture while preserving
  nam–nam, nam–nữ, nữ–nữ and ambiguous/manual-required behavior.

Historical RED seam below is evidence only and **must not ship**:

- `services/subdub_blackboxes/auto_speaker.py` only.
- Preserve the PR #842 whole-window classifier as the first attempt.
- On `AutoCastManualRequired` and exactly two labels only, restore the already
  shipped PR #889 independent weighted-vote helper.
- The collector keeps the same raw PCM and `_speaker_window_offsets`; it reads
  known `low/high` evidence from bounded pitch frames inside those windows.
- At least two winning observations and weighted support `>=0.60` remain
  required independently for each speaker; ties/unknowns remain manual.
- `subdub_speaker_cast.py`, `auto_multi_speaker.py`, PCM extraction/filter,
  parser/provider/UI/pricing/wallet/TTS/mux remain byte/behavior locked.

RED evidence:

- First invocation was invalid for one case because the OS pytest temp root
  denied access; the other five product assertions failed because the helper
  symbols did not exist. No product conclusion was taken from that invocation.
- Corrected no-cache workspace-basetemp RED: `6 failed in 0.48s`; every failure
  was the missing independent/helper boundary, with no setup, import or
  collection error.
- Focused metric RED: `1 failed in 0.44s`; three accepted 200 ms pitch frames
  were incorrectly reported as `1.5s` instead of `0.6s` before the correction.

#### SPEC-08.0F.3 — Reject raw-frame fallback and replace exact-two authority

##### SPEC-08.0F.3A — Review the rejected fallback

- [x] Verify all four reviewer findings against the actual working diff.
- [x] Mark the fallback `Ready to merge: NO`; no commit/push/PR/deploy/live.
- [x] Preserve the measured exact-fixture result as historical diagnostic only.
- [x] Choose no threshold relaxation and no forced gender pair.

- [x] Change only the production boundary proven by `08.0F.2` RED.
- [x] Keep Key4U transport/retry, Gemini parser, audio UI, pricing, wallet,
  TTS/mux and the multi-speaker engine unchanged.
- [!] Run the exact GREEN, two/multi isolation, locked hashes, `py_compile` and
  `git diff --check`; stop editing when they pass.

BUILD/REVIEW evidence so far:

- Production diff is only `services/subdub_blackboxes/auto_speaker.py`: anchor
  whole-window classifier remains first; exact-two only fallback collects
  bounded known pitch frames from the same raw PCM offsets, then applies the
  already-shipped independent `>=2` winning observations / `>=0.60` weighted
  support contract without forcing opposite genders.
- Exact focused GREEN: `6 passed in 0.38s`; metric GREEN + hash selector:
  `8 passed in 4.97s`; final focused/timeout/cancel/central-first batch:
  `26 passed in 5.95s`.
- Exact fixture production helper: `speaker_0=low`, confidence `0.778687`,
  `0.6s / 9,600 samples`; `speaker_1=high`, confidence `0.904186`,
  `1.8s / 28,800 samples`; provider calls `0`, wallet mutations `0`.
- Protected historical comparator before test alignment: `13 passed, 3 failed
  in 527.07s`; all three failures were source-lock assertions that demanded
  byte-for-byte #842/no fallback. UI, multi isolation, central-first,
  same-gender and ambiguous fail-closed assertions passed.
- Focused regression: `55 passed, 3 baseline-stale failures in 8.42s`.
  The three owners are unchanged by this branch: direct shared-classifier
  voiced-seconds expectation, one-frame acceptance expectation, and the old
  #853 filter expectation in `bot.py`; `NEW_FAILURES=0` by unchanged source.
- Aligned lock now requires the scoped exact-two fallback and forbids any
  protected-multi filter seam. Current post-correction engine Git blob is
  `b6001cdc26bed4c463075596cfa3ba3b9bf1901a`.

Independent review reopened four Important gaps; `Ready to merge: NO`:

- Raw frame YIN ignores the competing-pitch/purity/stability reasons that made
  the whole-window classifier fail. A mixed `120+220 Hz` probe can be cast as
  low/low; exact karaoke success alone does not prove voice ownership.
- 200 ms frames overlap at a 100 ms hop; summing frame lengths can report more
  `voiced_seconds/sample_count` than unique input audio and supplies correlated
  votes to the `>=2` gate.
- Output confidence reports only median winning-frame confidence; it must also
  reflect weighted vote support (fixture support was `0.661405`, not `0.904186`).
- Whole-window and fallback each reset a 48-second counter, so aggregate sample
  work can reach 96 seconds despite the advertised job cap.
- `08.0F.3` remains FAIL/REOPENED until all four have RED, minimal GREEN and a
  new independent review. No commit/push/PR/deploy/live is allowed meanwhile.

##### SPEC-08.0F.3B — ONNX service and integration RED

- [x] Replace the raw-frame test contract with one dedicated behavioral file:
  `tests/subdub_service_only/test_p0_subdub_two_speaker_onnx_gender.py`.
- [x] RED independent vote grouping for `male-male`, `male-female` and
  `female-female`; no rule may make the two outputs opposite by construction.
- [x] RED tie, dominance `<0.75`, fewer than four classified cues, NaN/invalid
  score and wrong label count to exact `AUTO_CAST_MANUAL_REQUIRED`.
- [x] RED confidence equals literal group vote dominance, not a winning-logit
  confidence; selected seconds/sample count are the union of cue ranges.
- [x] RED one aggregate exact-two evidence budget `<=48.0s` and bounded cue
  count; no second/reset budget after a failed classifier.
- [x] RED model missing/hash mismatch/license path/deadline/stop callback to
  fail-closed with no partial authority.
- [x] RED exact-two preflight requests stereo `44,100 Hz` `s16le`, invokes the
  ONNX service once and deletes PCM on success, manual result, timeout, cancel
  and unexpected exception.
- [x] RED mono `16 kHz` and stereo `44.1 kHz` as the only extractor contracts;
  every other channel/rate/format tuple rejects before FFmpeg.
- [x] RED default/manual/multi paths never call the exact-two ONNX service.
- [x] Run the whole dedicated file with workspace `--basetemp`; accept RED only
  when assertions fail for the missing service/stereo/integration contracts,
  not import/setup/collection errors.

RED terminal evidence:

- Command: Python 3.14 `pytest -q --noconftest -p no:cacheprovider
  --basetemp artifacts/pytest-08f-onnx-red-1` on the dedicated file.
- Result: `20 failed, 5 passed, 1 warning in 466.65s`, exit `1`.
- All 19 service/integration cases failed because
  `services.subdub_two_speaker_gender_onnx` did not exist; the stereo extractor
  case failed with exact `AUTO_CAST_UNAVAILABLE` at its old mono-only guard.
- Protected mono `16 kHz` extractor and four invalid tuple guards passed. No
  collection/setup/harness error, provider call, ffmpeg process or wallet action.

##### SPEC-08.0F.3C — Minimal ONNX GREEN

- [x] Remove every rejected raw-frame helper and import from
  `auto_speaker.py`; do not retain it as a fallback.
- [x] Add one local service with public owner
  `classify_two_speaker_genders(stereo_pcm_path, ranges_by_speaker,
  deadline_monotonic, stop_requested)`.
- [x] Verify and ship only UVR `UVR_MDXNET_3_9662.onnx` SHA-256
  `E02220E8...` and PANNs MobileNetV1 SHA-256 `0DA2C433...`, plus licenses and
  third-party notices; no Torch/checkpoint/Cnn14/audio-separator assets.
- [x] Pure local flow: stereo PCM → UVR vocal separation → per-cue PANNs
  `max(male speech, male singing)` vs `max(female speech, female singing)` →
  per-speaker vote dominance → `male=low`, `female=high`.
- [x] Exact-two preflight uses the service; multi/default/manual remain on
  their existing owners; all transient PCM is cleaned.
- [x] Turn the full `08.0F.3B` file GREEN and stop production edits.

GREEN/BUILD evidence:

- Dedicated ONNX file: `33 passed, 1 warning in 9.39s`, exit `0` on a fresh
  basetemp; warning only google.genai deprecation.
- Exact fixture on shipped `onnxruntime 1.29.0`: `42.938s`, provider calls `0`,
  wallet mutations `0`; speaker 0 `male/low`, votes `7/8`, dominance `0.875`,
  evidence `21s`; speaker 1 `female/high`, votes `8/10`, dominance `0.800`,
  evidence `27s`; aggregate unique evidence `48s`.
- Post-rebase wall-time RED: the same fixture hit the former `120s` deadline at
  a PANN cue while local CPU was contended. This was a real fail-closed result,
  so shipping stopped. Exact-two wall budget alone is now bounded at `300s`;
  evidence remains `48s`, concurrency remains `1`, and timeout/cancel/drain
  contracts remain fail-closed. Regressions: `5 passed`; exact ORT `1.29.0`
  fixture rerun PASS in `106.031s` with the same two casts and provider/wallet
  `0`.
- UVR asset: `29,704,436` bytes, SHA-256 `E02220E8...`, official UVR model MIT
  declaration/copyright preserved. PANNs asset: `23,570,561` bytes, SHA-256
  `0DA2C433...`; code MIT and Zenodo pretrained-model record CC BY 4.0.
- Review RED/GREEN corrections: non-cooperative timeout + concurrency lock
  `2 failed → 5 passed`; ONNX IndexError/OverflowError `2 failed → 6 passed`;
  `>64`/later-valid cue selection `2 failed → GREEN`; multi marker isolation
  `1 failed → 1 passed`; deploy dependency/incremental NUL-safe backup contract
  and real space/Unicode temp-repo integration `10 passed`.
- Fractional-tail extractor RED was valid: reported duration `1s`, final cue end
  `1.75s`, expected `-t 1.75`, actual `-t 1`. Minimal extractor now uses
  `max(reported duration, max cue end)` under the existing `1800s` cap; GREEN
  `7 passed in 619.81s`, including real `_read_montage` read of the final cue.
- Actual PANNs ONNX minimum-input probe disproved a speculative `0.31s` floor:
  tracked ORT/model fails only at `1` sample and returns `(1,527)` from `2`
  samples; production resampler already requires at least `2` samples. No
  arbitrary duration threshold was added.
- One prior combined focused invocation was `INVALID_HARNESS`: `34 passed,
  18 setup errors` from WinError 5 while pytest removed a reused basetemp. No
  product conclusion was taken; fresh basetemp runs above are authoritative.

##### SPEC-08.0F.3D — Protected verification and review

- [x] Re-run dedicated GREEN, timeout/cancel, two/multi isolation, UI/audio,
  price/receipt and locked-hash comparators.
- [x] Run `py_compile` on every changed Python file and `git diff --check`.
- [x] Measure exact fixture locally with provider calls `0`: require
  `speaker_0=male/low`, `speaker_1=female/high`, dominance `>=0.75` each.
- [x] Confirm protected SHA-256 values are unchanged and the diff contains no
  UI, pricing/wallet, provider transport, TTS/mux or multi-engine change.
- [x] Independent review must return Critical `0`, Important `0`, ready to
  merge `YES`; otherwise remain at `SPEC-08.0F.3`.

Final review/verify evidence:

- `py_compile bot.py` terminal exit `0`; all other changed Python files compile
  exit `0`; `git diff --check` exit `0`, only LF→CRLF warnings.
- Lock/cleanup/extractor selectors: `24 passed, 1 warning in 8.64s`.
- Current-snapshot protected comparator: `278 passed, 28 failed, 1 skipped,
  1 warning in 30.59s`; exact `28` failure IDs match BASE_SHA, so
  `NEW_FAILURES=0`. The skipped fractional montage case was separately GREEN
  with Python 3.12 + NumPy/ORT `1.29.0` (`7 passed`).
- Deploy dependency + NUL-safe incremental backup contract and real temp-repo
  round trip for `admin ID.txt` / `thư mục/giọng nữ.txt`: `10 passed`.
- Linux/Python 3.11 requirements dry-run: `78` packages resolvable with hashes,
  including NumPy `2.4.6` and ONNX Runtime `1.29.0`.
- Protected hashes unchanged: multi engine `55AAB894...`, shared cast
  `DE93620F...`, exact-two ASR fallback `94748DEF...`.
- Independent final verdict: Critical `0`, Important `0`,
  `READY_TO_MERGE=YES`.

#### SPEC-08.0F.4 — One ship/deploy/combo retry

- [B] Waiting only for Product Video to release the shared Git/LIVE/VPS slot;
  no source blocker remains.
- [B] One focused commit and PR, squash merge, one deploy/runtime identity
  check, then one exact combo retry.
- [B] PASS only with real MP4 + SRT + receipt, correct two independent casts,
  original `40%`, dub `150%`, nonzero list prices, admin `charged_xu=0`, and
  unchanged wallet/transactions; otherwise stay in `SPEC-08`.

### SPEC-08.1 — Pre-admission

- [x] Runtime SHA `085a1aaa...` verified in Telegram/VPS.
- [x] Correct fixture hash rechecked immediately before upload.
- [x] Baseline wallet captured: credits `200`, total_spent `0`, transactions `0`,
  credit_events `1`.
- [x] Exactly one valid fresh-flow upload; prior stale-state upload was rejected
  before SubDub admission with `InvalidToken` and zero provider/wallet action.
- [x] Select English.
- [x] Select `Tự động 2 giọng`.
- [x] Set and record original `40%` / dub `150%`.
- [x] Confirm exactly once; public job `#EE4E7E69CD`.

### SPEC-08.2 — Observe stages

- [x] Status panel visible through `35%`.
- [x] Source saved with correct SHA in workspace
  `/tmp/toan_aas_pipeline/ee4e7e69cdaf4b4e459d`.
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
