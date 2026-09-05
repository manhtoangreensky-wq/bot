# SubDub Auto Multi Resume Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. This stays single-agent because all steps share one branch, one exact job, and one recovery marker.

**Goal:** Continue the existing checkpoint and make exact job `#B4CB6D5FE8` deliver one real English multi-voice MP4 followed by one receipt, with `3–8` acoustically discovered speakers, source timing preserved, and `charged_xu=0`.

**Architecture:** Continue the fixed-vocal v3 ONNX engine, strict Deepgram word timeline, translation, per-speaker TTS, FFmpeg mux, validation, and delivery pipeline. Raw acoustic clusters remain audit evidence; only clusters with dominant-overlap word support create voices. Complete only measured same-job recovery boundaries, then continue the existing job.

**Tech Stack:** Python, python-telegram-bot, SQLite WAL, Deepgram, ONNX Runtime CPU, existing TTS adapters, FFmpeg, GitHub Actions, Ubuntu VPS/systemd.

**Spec:**

- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\subdub-mergecheck-fd57-833d\docs\superpowers\specs\2026-09-02-subdub-auto-multi-fixed-vocal-authority.md`
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\subdub-mergecheck-fd57-833d\docs\superpowers\specs\2026-09-01-subdub-auto-multi-local-speaker-embedding-design.md`
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\subdub-mergecheck-fd57-833d\.agents\state\SUBDUB-AUTO-MULTI-RESUME-20260903.md`

## Global Constraints

- Exact internal job: `b4cb6d5fe8a7bdfce507`; public code: `B4CB6D5FE8`.
- Exact fixture SHA-256: `83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E`.
- Output selection: English, original audio `40%`, dubbed audio `150%`.
- No upload, no Confirm, no replacement/second job, no old recovery command.
- `charged_xu` remains integer `0`; wallet credits/spent delta remains `0`.
- Paid provider call requires fresh action-time Owner confirmation naming the deployed SHA and exact job.
- Protected exact-two files remain byte-identical to current `origin/main`:
  - `services/subdub_speaker_cast.py`
  - `services/subdub_two_speaker_asr_fallback.py`
- Do not change PayOS, `/naptien`, wallet, Product Video, WebApp, ENV, provider prices, model bytes/hash/license, or exact-two behavior.
- Only a validated real MP4 plus Telegram video then receipt plus zero-wallet evidence is completion.

## Resume Ledger

### Complete and locked

- [x] Auto 2-speaker combo and standalone are `LOCKED_LIVE_PASS` with real MP4/receipt.
- [x] Fixed-vocal model/hash/license/CPU-only engine is deployed; v3 source is pending release.
- [x] Exact fixture offline acoustic evidence discovers raw `k=5`; live D/E and targeted ASR prove only `4` speech-supported clusters.
- [x] Exact PCM duration and strict-word Deepgram `300s` timeout corrections are deployed.
- [x] WIP `216b68d` contains the 9-line private context handoff and its regression.

### Remaining

- [x] Final WIP selector and full acoustic file terminate green: exact selector `1 passed in 603.88s`; full acoustic file `46 passed in 5.84s`.
- [x] WIP rebased onto `origin/main=ecb99f2`; new HEAD `a7721e8`; exact-two bytes unchanged.
- [x] Current job state is queried read-only. Identity/selection/markers/no-charge match; source bytes and strict word timeline are absent. Live later proved the legacy job persisted only `file_unique_id`, not a downloadable Telegram `file_id`.
- [ ] Context-repair marker is TDD RED/GREEN and CAS/idempotency protected.
- [ ] One PR merges and exact SHA deploys to the bot/required runner.
- [ ] The same job runs once and reaches MP4, delivery, receipt, and zero-wallet PASS.

## Review V2 Decisions Accepted on 04/09/2026

- [x] Production authority is read before marker design. Exact job, selection,
  three consumed repair markers, no-output and no-charge match. Strict word
  timeline is not persisted. Workspace exists but original and normalized
  source files have been cleaned.
- [x] Do not create a lane-proof replacement job. First restore through the
  existing Telegram `file_id` stored on the same job. Downloaded bytes must
  hash exactly to `83DE97B...98AD3E` before any DB CAS.
- [x] Add an offline full-chain context invariant for all four `_pipeline_*`
  fields at boundaries that actually consume them. Do not patch every text
  match merely because a field name appears there.
- [x] Strengthen attribution: the acoustic speaker set must equal the set sent
  to TTS; every cue has one speaker; each speaker keeps one unique voice.
- [x] Superseded 05/09: retain raw post-cluster `k=5` for audit, but require
  speech-supported `k=4` for this fixture. Raw label 0 has zero dominant-overlap
  word support and targeted vocal/original ASR both return empty; it must not
  create a fifth voice. This remains evidence, never a clustering hint.
- [ ] Measure final synthetic voice distinctness with ONNX embeddings using a
  calibrated within-speaker versus between-speaker separation rule or an
  existing measured constant; do not invent an absolute cosine threshold.
- [x] Overlap behavior is already explicit: one speaker per word unit; dominant
  overlap wins at dominance `>=0.2`, otherwise nearest centroid wins. Final
  evidence must report overlap/centroid mapping counts.
- [x] Run provider-stub full-chain rehearsal before live.
- [ ] Record the previous runtime SHA. If post-deploy model/context/recovery
  preflight fails, stop recovery and restore that SHA; do not mutate the job.

---

### Task 1: Finish the existing WIP verification

**Files:**

- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\subdub-mergecheck-fd57-833d\bot.py`
- `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\subdub-mergecheck-fd57-833d\tests\test_p0_subdub_auto_multi_acoustic_word_timeline.py`

- [x] Observe the already-running selector to terminal. Measured result: `1 passed in 603.88s`. If this selector must be reproduced later, run:

```powershell
$taskPy = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = 'C:\Users\toann\AppData\Local\Temp\payos-pytestdeps'
& $taskPy -c "import pytest,sys; raise SystemExit(pytest.main(sys.argv[1:]))" -q --noconftest -p no:cacheprovider tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py::test_exact_multi_fresh_asr_preserves_private_pipeline_context_before_acoustic
```

Expected: `1 passed`; workspace and saved source path reach `_extract_subdub_auto_pcm()`.

- [x] Run the complete acoustic word-timeline file with the same runner. Measured: `46 passed in 5.84s`.

Expected: zero failures for acoustic-before-translation, strict words, duration, sidecar/hash, and context.

- [x] If another boundary fails, record that boundary and write one RED before changing production. No additional failure appeared in the full file.

### Task 2: Rebase the checkpoint instead of rebuilding

- [x] Fetch and measure: pre-rebase divergence was `7 behind / 1 ahead`.

```powershell
git fetch origin main
git rev-list --left-right --count origin/main...HEAD
git diff --name-only origin/main...HEAD
```

- [x] Rebase the existing commit: completed conflict-free; new HEAD `a7721e8`.

```powershell
git rebase origin/main
```

- [x] Verify one commit and clean scope: `0 behind / 1 ahead`; `git diff --check=0`.

```powershell
git rev-list --left-right --count origin/main...HEAD
git diff --check origin/main...HEAD
git diff --exit-code origin/main...HEAD -- services/subdub_speaker_cast.py services/subdub_two_speaker_asr_fallback.py
```

Expected: `0 1`; diff-check `0`; protected exact-two diff empty. Measured: all three conditions pass on `a7721e8`.

### Task 3: Read exact production failure authority

- [x] Query `engine_async_job:b4cb6d5fe8a7bdfce507` using SQLite read-only/query-only.

Capture: job/fixture/user identity, English/40/150, status/stage/error, attempt/correction, all v2/duration/ASR-timeout markers, ASR/downstream flags, acoustic aggregate fields, output/delivery paths, charge fields, workspace/source path/hash, and provider-attempt receipt.

- [x] Verify source state. Workspace exists, but saved original and normalized
  files are absent. No matching name/size was found under `/data`, `/opt`,
  `/var/lib`, `/tmp`, or the searched Owner local roots.

- [x] Verify strict ASR resume authority. No strict word timeline, sidecar,
  subtitle, cue, TTS, or acoustic evidence persists. The latest Deepgram
  aggregate says PASS but cannot replace strict words; strict ASR must run again
  after byte-identical source rehydration.

- [x] Preflight stored Telegram identity without DB mutation. Runtime
  `b5a97285...` one-shot failed at Telegram `get_file` before CAS because the
  15-character `file_unique_id` had been persisted as `file_id`. Marker,
  provider usage, job count and wallet remained unchanged.
- [x] TDD-separate the two authorities: `job_key` matches `file_unique_id`;
  only a distinct full `file_id` may be sent to Telegram download. Missing,
  conflicting or non-string identities fail closed.

### Task 4: Add one exact same-job context-repair marker

**Files:**

- Modify: `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\subdub-mergecheck-fd57-833d\scripts\recover_subdub_fixed_vocal_v2.py`
- Test: `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\subdub-mergecheck-fd57-833d\tests\test_p0_subdub_auto_multi_failed_job_recovery.py`

- [x] Write RED tests:

```text
test_context_repair_rearms_exact_consumed_timeout_job_once
test_context_repair_rejects_second_claim_and_identity_mismatch
test_context_repair_rejects_output_charge_or_acoustic_evidence
test_context_repair_cas_loser_does_not_mutate_job
```

- [x] RED expected: `3 failed, 5 passed, 103 deselected in 7.86s` because the
  context-repair branch and source rehydration did not exist.

- [x] Implement one constant `auto_multi_private_pipeline_context_repair_used` and one mutually exclusive branch inside existing `claim_same_attempt()`.

Required success mutation:

```text
same internal/public job and source path/hash
attempt/correction stay 4/3
old v2/duration/ASR-timeout markers remain true
new context marker becomes true exactly once
status returns to existing same-job recovery status
progress stays 5
reset only the exact stage flag needed for fresh strict-word ASR/context hydration
charged_xu remains 0
no provider submit during the claim
```

Every mismatch/duplicate/CAS loser must leave the stored JSON byte-identical.

- [x] Run the complete failed-job recovery test file. Measured before the four
  additional source guards: `111 passed in 10.07s`; final combined focused gate
  includes all `115` recovery cases.

### Task 5: Protected gates

- [x] Auto Multi focused suite:

```powershell
$taskPy = 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = 'C:\Users\toann\AppData\Local\Temp\payos-pytestdeps'
& $taskPy -c "import pytest,sys; raise SystemExit(pytest.main(sys.argv[1:]))" -q --noconftest -p no:cacheprovider tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py tests/test_p0_subdub_auto_multi_embedding_onnx.py tests/test_p0_subdub_auto_multi_failed_job_recovery.py
```

- [x] Exact-two comparator:

```powershell
& $taskPy -c "import pytest,sys; raise SystemExit(pytest.main(sys.argv[1:]))" -q --noconftest -p no:cacheprovider tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k 'protected_two_speaker' tests/subdub_service_only/test_p0_subdub_two_speaker_onnx_gender.py
```

- [x] Real fixture/model gate:

```powershell
& $taskPy -c "import pytest,sys; raise SystemExit(pytest.main(sys.argv[1:]))" -q --noconftest -p no:cacheprovider tests/resource_gates/test_p0_subdub_auto_multi_embedding_fixture.py
```

Expected: exact model/hash/CPU PASS, stable `k=5`, no exact-two regression.

- [x] Compile/scope:

```powershell
& $taskPy -m py_compile bot.py scripts/recover_subdub_fixed_vocal_v2.py tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py tests/test_p0_subdub_auto_multi_failed_job_recovery.py
git diff --check origin/main...HEAD
git diff --exit-code origin/main...HEAD -- services/subdub_speaker_cast.py services/subdub_two_speaker_asr_fallback.py
```

Expected: all exit `0`.

Measured 04/09/2026 after the Review V2 additions:

```text
context-repair GREEN: 12 passed, 103 deselected in 6.85s
full recovery: 111 passed in 10.07s before four added source guards
context + attribution focused: 5 passed in 5.92s
Auto Multi combined pre-final: 309 passed in 12.93s
overlap evidence RED: 9 failed in 5.71s
overlap evidence focused GREEN: 14 passed in 383.36s
final focused + provider-fallback protected: 365 passed, 1 baseline stale-hash test deselected in 12.36s
full-chain five-speaker provider-stub rehearsal: 1 passed in 5.39s
exact-two selected comparator: 46 passed, 241 deselected in 6.39s
exact-two files: git diff against origin/main empty; both Git blobs identical
real exact-fixture fixed-vocal gate run 1: 1 passed in 136.87s
real exact-fixture fixed-vocal gate run 2: 1 passed in 119.25s
real model-byte / notice negative gates: 2 passed, 2 deselected in 0.89s
full changed-file py_compile: exit 0, no stderr
git diff --check: exit 0
provider calls: 0
production DB mutations: 0
wallet mutations: 0
```

The adjacent multilingual contract run is `10 passed` plus one unrelated
baseline PR330 failure: that old test requests `TTS_PROVIDER=auto`, while
current `origin/main` requires an explicit paid TTS provider policy. This
branch does not modify that function or provider policy.

Live runtime `9715b6f0` proved the next boundary: Deepgram passed `145` words,
but normalized-source PCM raised `fixed_vocal_speaker_count_unstable` before
translation. The exact original source returned stable `k=5`. The correction
therefore changes only exact Auto Multi acoustic PCM input to original source;
normalized media remains the ASR/render authority and all other lanes retain
their current saved-source priority.

Because the context marker was consumed by that live RED, continuation uses a
separate original-source marker. It accepts only the exact measured aggregate
`acoustic_failure_unknown`, `145` words, `134000ms`, attempts `4/3`, all
downstream/output flags false and `charged_xu=0`; it preserves prior markers,
does not increment attempts and blocks duplicate claims.

The existing provider-fallback suite produced `50 passed` plus one stale
hard-coded exact-two SHA assertion. `origin/main` contains the same stale test,
while both protected source files are byte-identical to `origin/main`; this is
baseline-equivalent and not an Auto Multi regression.

### Task 5C: Runtime-budget and variable-timeline closeout — 05/09/2026

- [x] Capture two fresh strict timing-only variants without raw word text.
  Both have `145` words; hashes are `8ad855ec...2737de8` and
  `948b4f94...df42af`; exactly `3` rows differ by at most `80ms`.
- [x] Run exact original-source acoustic with the actual timing: `k=5`, `37`
  units, `178` embedding views, clusters `[9,18,26,25,11]`, speaker-unit
  counts `[2,9,9,11,6]`, overlap/centroid `29/8`, `23` cues and complete five-
  speaker coverage.
- [x] Run the production async wrapper twice. Both variants PASS; measured wall
  times are `247s` and `156s` for a `133.37542s` source. The old fixed `300s`
  budget is therefore not a reliable policy across the supported `0..300s`
  direct lane.
- [x] TDD a generic measured-PCM timeout policy: floor `300s`,
  `ceil(duration*4)`, cap `1200s`. No fixture hash, exact job, expected `k`,
  codec or provider-label condition exists in production.
- [x] Preserve bounded `acoustic_*` and `fixed_vocal_*` cause codes; timeout is
  `acoustic_runtime_timeout`, so another failure cannot collapse to the same
  unhelpful `acoustic_failure_unknown`.
- [x] Add one exact-job CAS marker solely to permit the already-authorized
  same-job continuation after deploy. Attempts stay `4/3`; every prior marker
  stays true; duplicate and identity/charge/output/failure mutations are no-op.
- [x] Evidence: RED `7 failed, 1 passed`; focused GREEN `8 passed`; marker
  GREEN `5 passed`; Auto Multi `338 passed`; exact-two `37 passed`; resource
  `5 passed in 255.84s`; full compile/diff-check exit `0`.

### Task 5D: Full original media-duration correction — 05/09/2026

- [x] PR `#995` merged/deployed exact `f4fe6653`; same-job invocation reached
  `35%` then emitted the now-visible `fixed_vocal_speaker_count_unstable` before
  translation/TTS/mux, `charged_xu=0`.
- [x] Reproduce the exact boundary: strict last word `126.505s`; original media
  `133.37542s`; truncated PCM fails in `115.134s`; full PCM passes three
  consecutive runs in `121.628/116.797/130.717s` with unchanged `k=5/37`.
- [x] TDD the generic fix: exact Auto Multi probes its selected original source
  and extracts full media duration. Non-Multi stays unchanged; no exact SHA,
  job, fixture duration or expected speaker count exists in production.
- [x] Add one new exact-job CAS marker for this measured live RED; retain every
  prior marker and attempts `4/3`; duplicate/mutation/CAS loser no-op.
- [x] Fresh gates: PCM `5 passed`; Auto Multi `345 passed`; exact-two `37
  passed`; real resource `5 passed in 255.02s`; target language preservation
  covers `vi/ja/en/ko/zh`.

### Task 5E: Preserve the Auto Multi lane across pending writes — 05/09/2026

- [x] PR `#996` live RED still selected normalized source at `126.505s`.
- [x] Full prepare diagnostic with real pending storage proved
  `auto_speaker_lane` was dropped; private context alone was insufficient.
- [x] TDD one-line whitelist fix: RED `KeyError auto_speaker_lane`; GREEN `1
  passed`; context + marker focused `7 passed`; full Auto Multi `350 passed`.
- [x] Candidate full production boundary selects original source at `133.375s`
  and reaches acoustic PASS before intentional translation stop.
- [x] Add one exact-job CAS marker; attempts `4/3`, prior markers and no-charge
  authority preserved; duplicates/mutations no-op.

### Task 5F: Speech-supported speaker authority — 05/09/2026

- [x] Capture failing timing D/E: both raw `k=5`, but raw label 0 has zero
  word-unit coverage; four labels retain real coverage.
- [x] Targeted ASR over five missing-cluster regions on both vocal stem and
  original audio returns empty; historical Gemini count is `4`. This supersedes
  the earlier fixture-level “5 speakers/5 voices” acceptance.
- [x] Reject whole-file retry, forced assignment, and threshold relaxation.
- [x] Implement fixed-vocal v3: retain raw clusters for audit; require dominant
  overlap word support for effective speaker identity; drop centroid-only raw
  cluster, preserve every word and remap only among supported centroids; fail
  when fewer than `3` effective speakers remain.
- [x] Verify the offline full chain for every supported effective count `3..8`
  and the mapper matrix across raw counts `4..8`, including zero, one and
  multiple dropped labels at nonzero positions. Exact fixture raw `5` →
  effective `4`; no job/SHA/expected-k/label-position production branch.
- [x] Evidence: mapper RED `1 failed`; generic label matrix `7 passed`; focused
  Auto Multi `368 passed`; exact-two `37 passed`; real resource `6 passed in
  369.68s`; offline full chain `6 passed` for effective counts `3..8`; final
  changed-file compile/YAML/diff/protected/scope/secret gates exit `0`.
- [x] Add same-job marker `auto_multi_speech_supported_repair_used`; current
  payload candidate is true; attempts remain `4/3` and prior markers persist.

### Task 6: One optimized release

- [x] Update measured counts in the resume handoff, blackbox state, current
  operations/original-vs-current docs, tester guide, and tester case; live PASS
  remains false.
- [ ] Create one clean feature commit containing context handoff plus the exact marker.
- [ ] Push one branch and create one PR reporting RED/GREEN, protected gates,
  resource gate, compile/diff, and all `7` authorized diagnostic Deepgram calls
  in this forensic sequence (`2` initial timing, `3` mapping D/E/C, `2`
  targeted vocal/original), production job mutations `0`, and wallet mutations
  `0`.
- [ ] Squash merge only when required CI is `SUCCESS` and merge state is `CLEAN`.
- [ ] Wait exact-SHA deploy. Verify `/opt/toanaas/bot`, the actual SubDub runner, services, model/hash/license/CPU provider, and runtime SHA.

### Task 7: Continue only the existing job once

- [ ] Immediately before execution, obtain action-time Owner confirmation naming deployed SHA, script, exact job, English/40/150, paid-provider allowance, no new job, and `charged_xu=0`.
- [ ] Snapshot job/provider/wallet/output counts read-only.
- [ ] Run deployed `scripts/recover_subdub_fixed_vocal_v2.py` exactly once. Do not send the old Telegram recovery command.
- [ ] Observe only job `b4cb6d5fe8a7bdfce507` to terminal. No retry click, upload, Confirm, or replacement job.
- [ ] If live exposes another defect, record its first failing boundary and use one RED → minimal fix → protected gate → deploy → new exact one-shot marker loop. Never mix another subsystem.

#### Measured continuation on runtime `e129a2d2`

- [x] Exact job crossed the historical 5% failure and completed strict ASR,
  raw `5` / speech-supported `4` acoustic attribution, English translation,
  `21/21` TTS, cue-locked mux and MP4 validation.
- [x] Real MP4 exists: `18,171,909` bytes, H.264/AAC, `854x480`, `30fps`,
  `48kHz` stereo, `134.0s`.
- [x] Independent WeSpeaker audit proves four output voices are distinct:
  minimum within-speaker cosine `0.571435` > maximum between-speaker cosine
  `0.376944`, margin `0.194492`.
- [x] Isolate the terminal RED to the recovery message adapter: it had
  `reply_text` but no `reply_video`/`reply_document`, so no Telegram video call
  occurred and no public failure message was sent.
- [x] TDD a delivery-only CAS path reusing the validated artifact, with no
  provider/pipeline replay: RED `3 failed`; GREEN `3 passed`; signature RED →
  GREEN `1 failed` → `1 passed`; full recovery `148 passed`; protected `7
  passed`.
- [ ] Ship this delivery-only adapter (local compile/diff/YAML/scope/secret gates
  already exit `0`), run it once, then audit the exact video
  and receipt IDs, delivery order, companion-file count and finance deltas.

### Task 8: Artifact completion audit

- [ ] Acoustic: `speaker_count` is `3..8`; stable acoustic evidence; distinct voice IDs count equals speaker count; no forced pairing or expected-count hint.
- [ ] Language/timing: English output; every translated/TTS cue maps to one source cue; monotonic original start/end; no cumulative drift; final duration within existing tolerance.
- [ ] MP4: non-zero valid MP4, H.264 video, AAC audio, readable duration/dimensions, audible distinct dubbed voices, original `40%`, dub `150%`.
- [ ] Telegram: exactly one video followed by exactly one receipt; automatic SRT/audio/document companions `0`; durable delivery IDs; dedupe holds.
- [ ] Finance: same job ID; new job count `0`; `charged_xu=0`; wallet credits/spent delta `0`; provider submission count is limited to the authorized same-job continuation.
- [ ] Only after every item passes, set Auto Multi to `LOCKED_LIVE_PASS` and issue the final evidence report.

## Time Estimate

| Stage | Expected wall time |
|---|---:|
| Finish WIP selector + acoustic file | 15–35 minutes |
| Rebase + post-rebase/exact-two gates | 20–40 minutes |
| Live-state audit + one-shot marker TDD | 25–50 minutes |
| Protected/resource/compile review | 25–50 minutes |
| PR, CI, deploy, runtime readback | 10–25 minutes |
| Same-job ASR/acoustic/translation/TTS/mux/delivery | 20–60 minutes |
| **If context loss is the final defect** | **about 2–4 hours total** |
| Each additional live-only downstream defect | **add 45–90 minutes per bounded loop** |

This lane can be solved technically. Completion cannot be guaranteed by a clock or source tests because external provider latency and live-only downstream defects are empirical, but the plan forbids replacing the job or weakening quality gates and continues until the exact job has a real verified MP4 or a precisely evidenced external blocker.
