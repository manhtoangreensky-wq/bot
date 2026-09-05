# SubDub Auto Multi — Resume Handoff (2026-09-03)

## Scope lock

- Product: SubDub Auto Multi only.
- Exact job: `#B4CB6D5FE8` / internal `b4cb6d5fe8a7bdfce507`.
- Fixture SHA-256: `83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e`.
- Selection: English, original audio `40%`, dubbed audio `150%`.
- No new job, no upload, no Confirm, `charged_xu=0`.
- Protected exact-two files are unchanged and must stay unchanged:
  `services/subdub_speaker_cast.py`, `services/subdub_two_speaker_asr_fallback.py`.

## Git checkpoint

- Worktree: `work/subdub-mergecheck-fd57-833d`.
- Current branch: `fix/p0-subdub-auto-multi-private-pipeline-context`.
- Current base/main: `ecb99f2eebef2813eed8a17353386f1395c407a8`.
- Rebased WIP checkpoint: `a7721e8aa7eb6ed413bb02635149d4fec76f2208`,
  `0 behind / 1 ahead`; not pushed.
- The dirty continuation deliberately builds on that checkpoint and is limited
  to Auto Multi context, attribution, same-job source rehydration/recovery,
  focused tests, and the closeout plan.
- Production changes are limited to exact Auto Multi context restoration,
  attribution/mapping evidence and the exact same-job recovery runner.
- TDD evidence: RED `1 failed in 7.45s` showed `_pipeline_workspace` and
  `_pipeline_saved_source_path` were lost; an earlier implementation GREEN was
  `1 passed in 524.54s`. The reduced context seam later passed the complete
  acoustic file; the current measured gates are recorded below.

## Last deployed/live evidence

- SubDub timeout correction PR `#981` merged as
  `09a06aef40b1c21cc5ab4197c3da18f697e0fbba`; deploy succeeded and the SubDub
  runner/ASR/model bytes were unchanged when Product Video later deployed
  `095b6c88aa98a42ebbb3fc6535d44d7222e29779`.
- Owner-authorized one-shot unit:
  `toanaas-subdub-asr-timeout-actual-b4cb6d5fe8-09a06aef.service`, invocation
  `ba099f135ad54590b1bb377049103b68`, terminal exit `0`.
- That invocation was LIVE RED, not PASS: manifest `failed_no_charge` at `5%`.
  Deepgram receipt was `PASS`; no translation/TTS/mux/artifact/delivery ran.
- Durable state after that invocation: `attempt/correction=4/3`,
  `auto_multi_fixed_vocal_v2_asr_timeout_repair_used=true`,
  `charged_xu=0`, `charge_status=not_charged`, no final MP4/path/message.
- Financial readback: engine jobs `322`, transactions `0`, provider usage `0`,
  credit events `11`, wallet `200/0`.

## Root cause proved

`set_video_dubbing_pending()` and `video_dubbing_sync_state_fields()` deliberately
drop private `_pipeline_*` keys. In fresh exact Auto Multi, Deepgram returns a
strict word timeline, then `video_dubbing_prepare_subtitles()` calls
`set_video_dubbing_pending()` before `_extract_subdub_auto_pcm()`. The wrapper's
later reattachment is too late. The extractor therefore sees no workspace and
fails before local acoustic evidence, matching the live `5%` failure and empty
acoustic fields.

## Local correction ready for one commit

The checkpoint snapshots `_pipeline_*` fields only for exact Auto Multi and
reattaches them to the local state after the two pending-state writes that can
precede fresh acoustic extraction. It does not write those private fields into
`USER_PENDING`; exact-two and other lanes are untouched.

Review V2 additions now implemented and locally measured:

- all four private `_pipeline_*` values survive prepare, translation and the
  returned state consumed by classifier/TTS/mux;
- every acoustic speaker must appear in TTS, one speaker keeps one voice, and
  all voices are distinct before the attribution proof can be persisted;
- terminal proof now requires `auto_multi_attribution_verified=true`;
- missing same-job source is rehydrated only through a stored downloadable
  Telegram `file_id`; `job_key` separately anchors `file_unique_id`. Exact size,
  MIME and fixture SHA are verified before atomic write and before the DB CAS;
- existing correct source is reused; wrong existing hash, mismatched file ID,
  wrong downloaded hash, duplicate marker and CAS loser all fail without DB
  mutation or source overwrite;
- offline full-chain rehearsal proves five speakers through translated cues,
  ten scalar TTS calls, five unique voices, cue-locked timeline and mux.

Measured local evidence on 04–05/09/2026:

```text
context repair: 12 passed, 103 deselected in 6.85s
Auto Multi combined pre-final: 309 passed in 12.93s
overlap evidence RED/GREEN: 9 failed in 5.71s / 14 passed in 383.36s
final focused/protected: 365 passed; 1 baseline stale-hash test deselected in 12.36s
provider-stub full chain: 1 passed in 5.39s
exact-two selected comparator: 46 passed, 241 deselected in 6.39s
real exact fixture fixed-vocal run 1/run 2: 1 passed in 136.87s / 119.25s
real asset negative gates: 2 passed, 2 deselected in 0.89s
full changed-file py_compile: exit 0
git diff --check: exit 0
provider calls / production DB mutations / wallet mutations: 0 / 0 / 0
```

Adjacent language contracts are `10 passed` plus one baseline PR330 provider-
policy failure outside this diff; Auto Multi still preserves `vi/ja/en/ko/zh`
target selections and the exact live recovery remains English.

The exact fixture gate proves `k=5`, word coverage `50/50`, `23` units, `178`
  embedding views, clusters `[9,18,26,25,11]`, speaker-unit counts
  `[3,2,4,11,3]`, overlap mappings `19`, centroid mappings `4`, and `11` cues
  covering five speaker IDs.

## Required resume order

1. Final combined focused gate: complete, `365 passed / 1` known baseline test
   deselected.
2. Operational YAML, current/original docs, tester guide and cases: updated with
   measured evidence only; LIVE PASS remains false.
3. Final compile/YAML/diff/scope/secret review: complete; create one local
   commit from the existing WIP checkpoint.
4. Rebase/fetch only after shared-resource ownership is clear, then request fresh exact-head
   Owner authorization before PR/squash/deploy; the old `#981` authorization is
   not reusable for a new SHA.
5. After deployment and runtime/source/model preflight, obtain fresh action-time
   authorization for one execution of the deployed recovery script. Never send
   the old recovery command, reset/delete markers, or create a second job.
6. Only claim completion after a real MP4, one Telegram video followed by one
   receipt, stable distinct speakers/voices, cue/timing evidence, and zero Xu
   financial delta are measured.

## Runtime `b5a97285` live RED and current correction

- PR `#990` merged/deployed exact SHA
  `b5a972850a5bf441d44a50c4a445f342088a3165`; workflow `33903797590`
  SUCCESS. VPS checkout/model/services/health preflight passed.
- Exact one-shot invocation `8dfa559e6a034a9081b63669f28ad805` exited `1`
  before CAS/provider at Telegram `get_file`: persisted `input_save.file_id`
  was actually the same 15-character `file_unique_id` stored in `job_key`.
- Context marker remains unused; job `#B4CB6D5FE8` remains failed/no-charge;
  job/provider/transaction/credit/wallet/output deltas are all zero.
- Read-only search of `20` startup DB backups, `2` exact job JSON backups,
  journal and Local Bot API cache found no full downloadable file ID or source.
- Local correction branch `fix/p0-subdub-auto-multi-downloadable-source-id`
  starts at deployed `b5a97285`. It preserves both identities separately and
  fail-closes malformed/conflicting aliases.
- Measured source gates: recovery `124 passed`; direct impact `373 passed` plus
  one known baseline test deselected; exact-two `46 passed`. Compile/diff/docs
  gates exit `0`; YAML parse passes. Local commit remains to create.
- Never rerun invocation `8dfa559e...`. After deploy, the exact same job needs
  fresh Owner authorization for byte-identical fixture restore and one new unit;
  no Telegram command, Confirm, upload flow or replacement job.

## Runtime `9715b6f0` live RED and original-acoustic correction

- Exact fixture was restored atomically to the same workspace, mode `600`,
  `9,869,032` bytes, SHA `83DE97B7...98AD3E`.
- Authorized unit invocation `648943c375da47659795fb6314040dc3` reached
  Deepgram PASS (`145` words), then terminalized before translation/TTS/mux with
  `multi_acoustic_failure_code=acoustic_failure_unknown`.
- Direct local traceback on the same job normalized source proved
  `fixed_vocal_speaker_count_unstable`. Normalization changed audio
  `44.1kHz -> 48kHz -> 44.1kHz`; direct original-source acoustic execution
  returned exact `k=5`, `50` words, `23` units, `178` views, clusters
  `[9,18,26,25,11]`, speaker units `[3,2,4,11,3]`, overlap/centroid `19/4`.
- Minimal correction keeps normalized media for ASR/render, but exact Auto Multi
  speaker extraction reads the original hash-locked source path. Non-Multi PCM
  extraction keeps normalized-path priority.
- RED/isolation was `1 failed, 1 passed`; focused GREEN `3 passed`. No provider,
  production DB, wallet, job or Telegram mutation occurred in the source loop.
- Direct impact `375 passed / 1` known baseline deselected; exact-two `46
  passed`; full compile/YAML/diff exit `0`.
- Original-source same-job rearm adds one marker only for exact live aggregate
  `acoustic_failure_unknown/145 words/134000ms`, keeps attempts `4/3`, preserves
  context marker and blocks duplicates. RED/GREEN `1 failed -> 1 passed`;
  marker subset `15 passed`, full recovery `125 passed`, direct impact `376
  passed`, exact-two `46 passed`.

## PayOS handoff boundary

This checkpoint is independent of the manual-top-up/PayOS task. Do not mix its
state, files, PRs, jobs, provider receipts or wallet evidence into PayOS work.
