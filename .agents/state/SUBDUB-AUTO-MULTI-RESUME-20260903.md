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

## Acoustic runtime-budget correction — 05/09/2026

- Base/runtime before correction: `a0c45d4d6b222bc747c71202eb228f67c72b94a6`.
- Exact prior live still ended `failed_no_charge` at `5%`, `145` words, before
  translation/TTS/mux/artifact/delivery, with `acoustic_failure_unknown` and
  `charged_xu=0`.
- Read-only diagnostic A: timing SHA `8ad855ec...2737de8`, acoustic PASS `k=5`,
  `37` units, `23` cues. Cached-timing production wrapper PASS in `247s` wall.
- Read-only diagnostic B: timing SHA `948b4f94...df42af`, `3/145` timing rows
  changed by at most `80ms`; fresh-ASR production wrapper PASS in `156s`, same
  `k=5/37/23` authority. Raw text/provider payload was not persisted.
- Root correction is generic for every supported direct Auto Multi source:
  derive acoustic timeout from measured PCM duration with floor `300s`, factor
  `4`, cap `1200s` over the engine's `300s` source limit. No job/SHA/expected-k
  production branch and no clustering threshold change.
- Observability correction preserves bounded `fixed_vocal_*` as well as
  `acoustic_*`; timeout emits `acoustic_runtime_timeout`.
- Same-job correction marker:
  `auto_multi_acoustic_runtime_budget_repair_used`. It requires every prior
  marker, exact current failure aggregate and no-output/no-charge authority;
  attempts stay `4/3`, duplicate/mutation/CAS loser are no-op.
- Measured source evidence: TDD RED `7 failed, 1 passed`; focused GREEN `8
  passed`; marker RED/GREEN `1 failed, 4 passed` → `5 passed`; Auto Multi `338
  passed`; exact-two `37 passed`; real resource `5 passed in 255.84s`; full
  compile/diff-check `0`.
- Next: final review/commit → push/PR/squash/deploy exact SHA → one same-job
  script invocation → observe through MP4 + exactly one Telegram video and one
  receipt. No upload/Confirm/new job/old command; Owner provider authority is
  limited to this job and `charged_xu=0`.

## Full original media-duration correction after PR #995 LIVE RED

- PR `#995` merged as `f4fe665388715df276081aab999598f36ff07386`;
  deploy run `33948594192` SUCCESS in `3m52s`; bot checkout exact SHA, tracked
  tree clean, bot/web/nginx active, model preflight PASS on CPU with hash
  `9fea6516...056a1`.
- Setup-only unit without `PYTHONPATH` exited before importing `bot`; marker,
  provider, job and wallet deltas were `0`. Actual unit invocation
  `614e31ec478742a1a28bfafb045da420` consumed the runtime-budget marker, reached
  `35%`, then terminalized `failed_no_charge` before translation/TTS/mux with
  the newly preserved cause `fixed_vocal_speaker_count_unstable`; Xu stayed `0`.
- Root reproduced exactly: strict words end at `126.505s`; recovery state has
  no media duration before prepare, so `_extract_subdub_auto_pcm()` used last
  cue end and cut original PCM to `126.505s`. That PCM reproduces the same
  failure in `115.134s`. Full original PCM is `133.37542s` and three consecutive
  runs PASS `k=5/37 units` in `121.628s`, `116.797s`, and `130.717s`.
- Minimal generic correction: only exact Auto Multi probes the selected original
  source with ffprobe and uses the full media duration for PCM extraction.
  Non-Multi source priority and duration remain unchanged; no fixture/job/k
  condition exists in the engine.
- Core RED/GREEN: `1 failed` because no original-media probe occurred, then
  `5 passed` covering full duration, probe fail-closed, original-over-normalized,
  stereo contract, and non-Multi unchanged. Fresh Auto Multi regression `345 passed`; exact-two
  `37 passed`; real resource/model gate `5 passed in 255.02s`; multi-language
  preservation for `vi/ja/en/ko/zh` remains inside the green suite.
- New exact same-job marker:
  `auto_multi_acoustic_full_media_duration_repair_used`; current production
  payload candidate evaluates `true`. It preserves attempts `4/3` and every
  prior marker; duplicate and charge/output/duration/word mutation are no-op.
- Next: final compile/docs/diff → one follow-up PR/deploy → one same-job
  continuation. No upload/Confirm/new job/old command.

## Pending Auto Multi lane marker closeout — 05/09/2026

- PR `#996` merged/deployed exact
  `3f87f5e4184c8b4753923f0227caeb8b7de3b649`; deploy `33954073514`
  SUCCESS `4m08s`. Same-job continuation consumed full-duration marker but
  again failed with `fixed_vocal_speaker_count_unstable`, no downstream/output,
  `charged_xu=0`.
- Full production-boundary diagnostic with real `set_video_dubbing_pending()`
  captured the actual command: normalized source + `-t 126.505`. Root is the
  pending whitelist: it persists `voice_selection_mode` but omits
  `auto_speaker_lane`. After the pending write, state is no longer recognized as
  Auto Multi, so original-source and full-duration branches never execute.
- One-line production correction adds `auto_speaker_lane` to the existing
  pending whitelist. No engine/threshold/provider/translation/TTS/mux change.
- Causal diagnostic after only that candidate change captures original source +
  `-t 133.375` and reaches acoustic PASS before the intentional translation
  stop. Before candidate it captured normalized + `-t 126.505` and failed.
- TDD real pending store RED: `KeyError auto_speaker_lane`; GREEN `1 passed`.
  Context + marker focused `7 passed`. New marker is
  `auto_multi_pending_lane_repair_used`; attempts remain `4/3`, prior markers
  stay true, duplicate/mutation no-op.
- Next: full gate/compile → one follow-up PR/deploy → same job once → artifact.
- Full Auto Multi gate after the final marker is `350 passed`.

## Speech-supported speaker authority — 05/09/2026

- Runtime `319fa19e9d53effe585f08fffc652955598d8911` with pending-lane fix
  reached full original PCM but same-job terminalized at the deeper boundary
  `fixed_vocal_word_speaker_coverage_invalid`; no translation/TTS/mux/output,
  `charged_xu=0`.
- Fresh timing D `7f571a38...ccf82c` and E `2321cd6f...31830` reproduce raw
  acoustic `k=5` but raw speaker-unit counts `[0,9,9,11,6]` and
  `[0,8,9,11,6]`. Raw cluster 0 has `9` core windows but dominant-overlap word
  support `0`; the other raw clusters have overlap support `[7,8,10,4]`.
- Targeted Deepgram ASR over the five missing-cluster ranges on both the UVR
  vocal stem and original mono audio returns `deepgram_empty_transcript` for all
  `13s`. Historical Gemini evidence also reported `4` speakers. Therefore raw
  cluster 0 is non-speech/music acoustic structure, not a person to dub.
- Rejected approaches: repeated whole-file Deepgram (D and E both fail),
  constrained re-assignment to raw cluster 0 (would invent a speaker), and
  lowering clustering thresholds.
- Fixed-vocal v3 keeps two authorities: raw acoustic clusters for audit and
  speech-supported speakers for voice creation. A raw label must have at least
  one dominant-overlap word-unit; centroid-only labels are removed from the
  effective set. Every word remains exactly once and units assigned to a removed
  raw label are remapped by centroid only among supported labels. Fewer than `3`
  effective speakers still fails closed.
- Exact fixture result is now raw `5` → speech-supported `4`, not five people.
  Generic mapping is verified across raw counts `4..8`, with dropped labels at
  arbitrary positions, and the offline full chain is verified for every
  effective speech count `3..8`; no fixture hash/job/expected-k/label-position
  branch exists in production.
- Evidence: mapper RED `1 failed`; generic label matrix `7 passed`; full Auto
  Multi `368 passed`; exact-two `37 passed`; real resource `6 passed in
  369.68s`; offline full-chain `6 passed`; marker payload candidate `true`. New
  marker:
  `auto_multi_speech_supported_repair_used`, attempts remain `4/3`.
- Final changed-file `py_compile`, YAML parse (`42` top-level keys),
  `git diff --check`, protected exact-two/model diff, fixture-literal scan and
  secret scan all exit `0` before commit.
- Live forensic used `4` authorized diagnostic Deepgram calls for this exact
  job: whole-file D/E plus targeted vocal/original. They wrote no provider
  receipt, job state, wallet or delivery data. Code/resource tests used `0`.
- Total authorized diagnostic calls across the current timing/acoustic forensic
  sequence are `7`: initial A/B `2`, whole-file mapping C/D/E `3`, and targeted
  vocal/original `2`. Recovery invocations are accounted separately.

## Runtime `e129a2d2` artifact PASS / delivery-adapter RED — 05/09/2026

- PR `#998` merged exact SHA
  `e129a2d27bcb4c91dcc8c72446c82fd74b40ed69`; deploy run `33975619245`
  SUCCESS in `3m54s`. VPS checkout exact SHA; tracked diff `0`; bot/web/nginx
  active; fixed-vocal v3 model SHA `9fea6516...056a1` on CPU provider.
- Exact one-shot invocation `22784da7ec724de59b1fe1dffef64d97` consumed
  `auto_multi_speech_supported_repair_used`, crossed the old `5%` boundary and
  completed strict ASR, acoustic, English translation, `21/21` TTS cues,
  cue-lock, mux and validation. It created `final.mp4`, `18,171,909` bytes,
  H.264/AAC, `854x480`, `30fps`, `48kHz` stereo, `134.0s`.
- Acoustic sidecar is raw `5` / speech-supported `4`, `145/145` words,
  `35` units, `21` final cues. Independent output-audio audit selected `3`
  long cues per speaker: four speakers, minimum within-speaker cosine
  `0.571435`, maximum between-speaker cosine `0.376944`, separation margin
  `0.194492`; distinctness PASS.
- Delivery alone failed: the exact recovery script's synthetic message exposed
  only `reply_text`; shared delivery requires `reply_video` or
  `reply_document`. Therefore Telegram send was never attempted and the job
  ended `failed_no_charge` with `missing_valid_delivered_mp4`; no public failure
  message was sent. Root jobs `322`, wallet `200/0`, transactions `0`, credit
  events `12`, provider usage rows `0`, charged Xu `0`.
- Current branch `fix/p0-subdub-auto-multi-recovery-delivery-adapter` starts at
  exact deployed main `e129a2d2`. Minimal correction adds the missing Bot media
  adapter plus a one-shot CAS delivery-only marker. It reuses only the existing
  validated MP4 and explicitly does not invoke ASR, translation, TTS, mux,
  upload, Confirm or a new job.
- TDD: adapter/CAS/order RED `3 failed`; GREEN `3 passed`; Bot signature RED
  `1 failed` at unexpected `filename`; GREEN `1 passed`; full recovery `148
  passed`; protected delivery/receipt/no-provider-replay `7 passed`.

Current next action: commit/push/PR → exact-SHA deploy → one delivery-only
execution → verify exactly one MP4 then one receipt and zero financial delta.

### Deploy `f3ca9df8` preflight exposed lost-root-lineage guard

- PR `#999` merged as `f3ca9df871bc266a89346739ce9d877c6756bd37`;
  deploy run `33979562459` SUCCESS in `5m36s`; checkout exact, tracked diff
  `0`, bot/web/nginx active.
- Pre-delivery readback correctly stopped before Telegram: the generic failure
  snapshot retained the validated MP4 but dropped `job_key`, selection and the
  consumed speech-supported marker from the root job. The first delivery-only
  candidate therefore returned false; no delivery marker, Telegram message,
  receipt, provider call, job or wallet mutation occurred.
- Durable workspace authority remains complete and mutually linked: manifest
  exact job/user/chat/no-delivery/source SHA; cache English plus source and
  translated SRT hashes; sidecar fixed-vocal v3 model/processing SHA, raw `5`,
  speech-supported `4`, `145/145`; MP4 exact `18,171,909` bytes and SHA
  `07fdfe65...43c7f0`.
- Follow-up local correction reconstructs only the lost `job_key` from the
  exact `file_unique_id`, requires DB/manifest/cache/sidecar/SRT content hashes
  to agree, and recalculates receipt price using current source functions:
  `189` English words, dubbing `95 Xu`, subtitle/translation `86 Xu`, total
  `181 Xu`, Owner charge `0`, wallet `200`.
- TDD: lost-lineage candidate RED `1 failed`; GREEN `1 passed`; lost-job-key
  CAS RED `1 failed`; GREEN included in focused lineage; ten metadata mutation
  guards PASS; full recovery now `149 passed`.

Current next action: compile/diff → amend/push follow-up commit → PR/deploy →
one delivery-only invocation; never replay ASR/translation/TTS/mux.

## Auto Multi v4 five-speaker/gender/aspect local continuation — 2026-09-07

- Scope remains only Auto Multi for exact job `#B4CB6D5FE8`, fixture SHA
  `83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E`,
  English, original `40%`, dub `150%`, `charged_xu=0`; no new job, upload,
  Confirm, old recovery command or provider replay.
- Local branch is `fix/p0-subdub-auto-multi-five-speaker-gender-aspect` at
  base `aea17efc7d996d6efdc8ae04fdcfa6c03babc5c7`; current worktree is
  intentionally dirty with the existing v4 WIP only. Exact-two protected
  modules remain diff-empty.
- v4 keeps raw fixed-vocal speaker count independent from ASR, partitions
  speech-supported windows with bounded gender evidence, maps each word at
  word granularity, persists one register per speaker and requires distinct
  speaker/voice attribution before terminal proof. The final cue at
  `126.005–126.505` is measured as `high`; the prior v3 four-speaker result is
  not accepted as Multi PASS.
- The remaining local RED was a synthetic generic `k=5..8` spectral
  eigenspace degeneracy with repeated orthogonal vectors, not a fixture
  authority failure. The minimal production correction keeps stable spectral
  clustering as primary and falls back only when its labels are explicitly
  under-supported to deterministic original-space K-means. Direct contract
  execution now passes `k=3..8`, cluster size `3` each, correct high/low
  allocation, and `base/shift` plus `base/aggregate` agreement `1.0`.
- Fresh local evidence after that correction: full focused Auto Multi
  `449 passed`; terminal/recovery persistence `7 passed`; exact-two protected
  `51 passed`; renderer/volume/language/media regression `64 passed`; real
  fixture resource gate `9 passed in 410.72s`;
  changed-module/full-core `py_compile` exit `0`; `git diff --check` exit `0`;
  model hash
  `E98F8BC6D7960A8A2169368FE4533636903E712790E96DBFF81B679EDE5DE252`;
  strong-PANN/weak-pitch keeps PANN, weak-PANN/robust-pitch selects pitch,
  strong source conflict fails closed. The exact source probes as AV1/AAC,
  `854x480`, rotation `0`, duration `133.37542s`; production FFmpeg renderer
  created a local H.264/AAC yuv420p MP4, `16,927,256` bytes, same geometry and
  duration, SHA `0a143785...59226`.
- Geometry RED was `9 failed`; GREEN `9 passed`. Auto Multi now preflights
  ffprobe before pipeline, probes off the event loop, rejects changed display
  aspect or rotation metadata before delivery and persists source/output
  geometry proof. Stubborn acoustic worker cleanup RED `1 failed`; GREEN
  `3 passed`, deferring PCM unlink until a detached worker is terminal.
- Production read-only truth changed after the earlier handoff: the v3 MP4 was
  already delivered. The same row is `delivered/admin_free`, raw speaker `5`,
  effective speaker/voice `4/4`, charged `0`, old video and receipt present.
  Workspace remains, but `final.mp4` and the exact 9,869,032-byte source are
  absent; only the 23,310,949-byte normalized source remains and Telegram has
  only `file_unique_id`, not a downloadable `file_id`.
- New runner `scripts/recover_subdub_auto_multi_v4.py` never calls legacy
  delivery. Before execution the exact fixture must be restored to the same
  workspace and hash-checked. Its one-shot CAS stores the old v3 video/receipt
  IDs as superseded history, clears only active v3 acoustic/output/delivery
  dedupe fields, creates a fresh correction nonce and runs the current full v4
  pipeline on the same internal job. RED `3 failed`; focused source/candidate/
  CAS/runner GREEN `4 passed`; the fresh terminal/recovery persistence gate is
  `7 passed` and the full focused Auto Multi gate is `449 passed` after the
  subsequent delivered-snapshot hardening.
- Side effects remain `PROVIDER_CALLS=0` after the authorized Deepgram one-shot,
  production `DB_MUTATIONS=0`, `JOB_MUTATIONS=0`, `WALLET_MUTATIONS=0`,
  `DEPLOY=NO`, `LIVE_PASS=NO`. Next: final combined gates and review → commit/
  PR/deploy → restore exact source → read-only candidate PASS → execute the v4
  runner exactly once → validate corrected MP4/Telegram receipt/zero-Xu state.

### V4 live RED and acoustic-view quorum correction — 2026-09-07

- PR `#1001` merged as `bd1461666c474e765e4ce505b767a4359b6e73c0`;
  deploy run `34086789018` SUCCESS in `5m31s`; VPS checkout/tree exact,
  bot/web/nginx active and gender model CPU preflight PASS.
- Exact fixture was restored to the same job workspace with `9,869,032` bytes,
  SHA `83DE97B7...AD3E`, mode `600`. Invocation
  `0ffe6be7ad3b4ef784b510b770956b6e` crossed 5% then failed before
  translation/TTS/mux/artifact/delivery with
  `fixed_vocal_gender_partition_unstable`; same job, `charged_xu=0`.
- Measured root: raw/effective speaker count `5/5`, coverage `145/145`,
  registers `[high,low,low,high,low]`; base/aggregate agreement `1.0`, while
  the shifted perturbation alone was `0.915254`. Requiring both comparisons
  above `0.95` rejected an otherwise exact 2-of-3 acoustic consensus.
- Minimal correction keeps the `0.95` threshold and accepts only a pairwise
  2-of-3 view quorum; if no pair reaches `0.95`, it still fails closed. A
  second exact CAS marker is permitted only for this measured failure, before
  downstream/provider output, preserving v3 history and forbidding any third
  execution.
- TDD quorum RED `1 failed / 1 passed`, GREEN `2 passed`; repair-marker RED
  `2 failed`, GREEN `2 passed`; full focused `453 passed`; exact-two protected
  `51 passed`; full exact-fixture resource `9 passed in 398.34s`; provider,
  new-job and wallet mutations during source correction remain `0`.

Current next action: compile/diff → one correction commit/PR/deploy → exact
quorum-repair candidate PASS → one same-job continuation → artifact/Telegram/
receipt/zero-Xu verification. `LIVE_PASS=NO` until that evidence exists.

### V4 artifact delivered; proof/receipt closeout — 2026-09-07

- PR `#1002` merged as `4c8e8ebaef2e49d9fb82c03db90b2954f6e7fa1c`;
  deploy `34092384011` SUCCESS. Invocation
  `baf19627da7843838f8b2bb8d86199e1` crossed acoustic, translation, TTS,
  mux and delivery on the same job. Telegram video message is `28129`; MP4 is
  `18,277,796` bytes, SHA `D72EE09B65D6D0142099F0F21DC6BD871846D1D4A6DA2CADEAED191CF76C91C8`,
  H.264/AAC, `854x480`, rotation `0`, duration `134.0s`; `charged_xu=0`.
- Durable TTS QC retains `21/21` rows with `ok=true`, dropped `0`. No SRT,
  audio or document companion was delivered. Old v3 video/receipt IDs remain
  history `28112/28113`; the v4 video ID is distinct.
- The process exited `1` only after delivery: successful multi wrapper kept
  acoustic evidence in its mutable `current` map but omitted it when returning
  `result.state`; the final durable helper therefore received incomplete proof.
  A Telegram status-panel edit also timed out, so the receipt correctly stayed
  unsent rather than creating another status table.
- Minimal general fix merges the already-validated acoustic bundle into the
  successful result state. RED was `KeyError multi_acoustic_speaker_count`;
  GREEN `1 passed`. Exact-job closeout is provider-free: recompute acoustic
  proof from exact source plus locked timing hash, CAS it once, edit the same
  panel and send only the missing receipt; it has no video-send or pipeline
  replay path. Closeout focused `5 passed`; full focused `457 passed`; exact-two
  protected `51 passed`; previous post-quorum resource `9 passed in 398.34s`.

Current next action: compile/diff → one proof-closeout PR/deploy → restore exact
source only → run provider-free closeout once → verify new receipt and complete
terminal evidence. No ASR/translation/TTS/mux/video replay and no new job.

### Public access và continuity follow-up — 2026-09-07

- Runtime read-only trên SHA `165d34def67a6781ca6e51130c31de3174e9c809` xác nhận
  cả `4/4` lane canonical của SubDub (`subtitle_create`, `subtitle_translate`,
  `dub`, `subtitle_plus_dub`) đều `public_flag_enabled=true`,
  `effective_ready=true`, `blockers=[]`; user non-admin nhận
  `allowed_public` sau final Confirm. Auto 2 và Auto Multi capacity/menu/route
  cũng đang mở. Không cần mở thêm một gate chỉ-Owner.
- Job khách `#66C9613DF7` đã qua `gate_matrix.access_status=allowed_public` và
  dừng ở `5%` với `fixed_vocal_demix_busy`, trước translation/TTS; `charged_xu=0`.
  Đây là tranh chấp local acoustic lock, không phải ngôn ngữ hay quyền.
- Local correction trên branch `fix/p0-subdub-auto-multi-acoustic-view-quorum`
  (HEAD sau rebase `9142a05c8f1d30aac6a2a53f570945ceb56709df`) chỉ chạm Auto
  Multi: serialize fixed-vocal work, chờ lock tối đa `1200s`, cấp lại full
  processing budget sau khi lock được giữ, và giữ register theo acoustic
  identity-majority để một window nhiễu không đổi nữ↔nam giữa các cảnh.
  Hai người cùng register vẫn là hai speaker distinct.
- Evidence mới: continuity/concurrency `4 passed`; Auto Multi embedding `123
  passed`; provider/gender fallback `56 passed`; exact-two `41 passed`; exact
  fixture `1 passed in 135.31s` sau rebase; compile/diff-check `0`. Không gọi
  provider, không tạo job, không mutation DB/wallet trong source loop.
- Chưa tạo PR/merge/deploy vì GitHub CLI token hết hạn và Codex Browser đang
  `Sign in`; branch đã push lease-safe và trang compare báo `Able to merge`,
  `1 commit / 6 files`. Cần đăng nhập đúng tài khoản Codex rồi mới tạo PR và
  xin chốt deploy; không dùng nhầm tài khoản khác.

### Rejected identity/register isolation — 2026-09-08

- Deep local probe trên exact fixture xác nhận voice allocator hiện hữu giữ
  đúng một voice hash cho mỗi speaker; lỗi còn lại nằm trước TTS ở acoustic
  label/register authority.
- Root code: identity candidate có đủ majority register nhưng không khớp số
  register của gender allocation nên không được chọn; nhánh cũ vẫn tái sử dụng
  `identity_registers` với label của partition khác, có thể làm nữ/nam gắn sai
  hoặc fail ở acoustic gate.
- RED mới terminal `1 failed` tại `AUTO_CAST_MANUAL_REQUIRED`; production fix
  chỉ thêm guard `identity_partition_selected`; GREEN continuity `5 passed`,
  embedding `123 passed`, provider/gender fallback `56 passed`; protected Auto
  2 core/recovery `34 + 10 passed`; public four-lane selectors `12 passed`.
- Exact fixture SHA `83DE97B7...AD3E` sau fix giữ label cũ, `5` speaker và
  register `[high,low,low,high,low]`; resource selector `1 passed in 131.23s`.
  Provider calls, DB/job/wallet mutation và deploy trong loop này đều `0`.
  Changed-file compile và full `py_compile bot.py` đều exit `0`; diff/scope/
  secret checks exit `0`. Một test public TTS không liên quan có stale fake
  signature và fail y hệt trên hai file diff-empty; không sửa ngoài scope.

### Customer acoustic consensus + Local Bot API binlog — 2026-09-08

- PR `#1004` merged `af4119ef074d2b87214640d41126078a7ecbd626`.
  Bot deploy workflow hết health deadline trước khi startup xong, nhưng direct
  readback xác nhận checkout exact/clean, bot/web/nginx active, health HTTP 200
  và VPS continuity test `5 passed`.
- Fresh customer job `#E061920890` dùng exact fixture SHA
  `83DE97B7...AD3E`, qua `allowed_public`, strict ASR `145` words và UI
  từng đạt `35%`; nó terminal `failed_no_charge` với
  `fixed_vocal_gender_partition_unstable`, trước translation/TTS/mux,
  `charged_xu=0`. Queue fix đã hoạt động: blocker không còn
  `fixed_vocal_demix_busy`.
- RED mới chứng minh ba valid view có thể lệch ở các boundary khác nhau nên
  không pair nào đạt global `0.95` dù mỗi window có 2/3 authority. Fallback
  chỉ chạy khi consensus khớp từng view `≥0.95`; majority 2/3 thắng,
  three-way tie dùng aggregate; cluster support và gender evidence vẫn
  fail-closed.
  Existing divergent-view negative comparator vẫn PASS.
- Account-neutral comparator chạy cùng payload với
  `allow_admin=False/True`: cả hai đi ASR → acoustic → translation và cho
  cùng speaker/register state, `2 passed`. Không có customer-only algorithm.
- Callback delay tại `13:15:47` là Local Bot API container exit: cleanup có
  thể xóa durable `tqueue.binlog`/`webhooks_db.binlog`/`td.binlog` khi file
  đóng ngắn giữa rotation; vòng TQueue GC sau báo `Failed to unlink old
  binlog`, systemd restart sau 10 giây và bot nhận `502`. Fix loại toàn bộ
  `*.binlog*` trước fuser/rm; không đổi Telegram handler.
- Side effects trong source loop: provider calls `0`, new jobs `0`,
  production DB/wallet mutation `0`.

### Public fresh normalization + product information — 2026-09-08

- Runtime before this follow-up: `752ce070cf6b73052ed00388bdb19c2c6b5edd22`.
- Job `#76EAF3A29A` is the exact new public acoustic RED: `allowed_public`,
  input SHA `83DE97B7...AD3E`, terminal `5%`
  `fixed_vocal_gender_partition_unstable`, before ASR and no charge.
- Root: fresh normalization retained the original hash but reused a path later
  occupied by normalized media. The local acoustic override therefore read
  normalized H.264/48kHz instead of the original AV1/AAC 44.1kHz bytes.
- Minimal generic correction persists `original_source_for_acoustic.mp4` only
  when normalization occurs; Auto Multi acoustic uses it while ASR/render use
  `normalized_source.mp4`. No admin/user/job/SHA condition and no Auto 2 diff.
- Job `#E937B761F8` is separate: ASR/translation reached `60%`, exact quote was
  `247` words / `226 Xu`, then confirmation expired; terminal/no-charge.
- Presentation now states all `4` lanes, Auto 2 exact `2`, Auto Multi `3–8`,
  every voice choice, primary MP4 and result-screen SRT across `17` locale
  copy rows. Admin/customer catalog equality is regression-tested.
- Evidence: source RED `1 failed`; source GREEN `1 passed`; product-info/parity
  `8 passed`; i18n/continuity/embedding `136 passed`; full changed-file compile
  exit `0`. Provider/new-job/production DB/wallet delta remains `0`.

### Admin route + customer exact-price resume parity — 2026-09-08

- The live `menu|admin` callback calls `localized_menu_content()`. That function
  had no `action == "admin"` branch, so even an authenticated administrator was
  rendered back to the main menu. The bounded correction routes only that
  admin-only action to the existing Admin Control Center.
- Customer job `#8B6C0B0D1B` reached the same Auto Multi preparation used by
  admin: acoustic `k=5`, `145/145` words and exact quote `222 Xu`. After the
  customer confirmed, cached resume failed with `AUTO_EXACT_RECEIPT_INVALID`.
- All signed media, subtitle and sidecar hashes matched. The only byte-level
  difference was cue 2 ending at `16254 ms` after SRT serialization versus the
  signed sidecar authority at `16255 ms`.
- Cached resume now accepts only SRT quantization drift of at most `1 ms`,
  restores start/end and source timing from the already hash-verified sidecar,
  then runs the existing strict cue-id and sidecar validation. Drift above
  `1 ms` remains fail-closed.
- The loader proof returns all `26` cached cues with
  `asr_provider=cached_auto_exact_receipt` and an empty translation provider;
  it does not replay ASR or translation. No Auto 2, acoustic/voice algorithm,
  provider routing, pricing, wallet or payment code is changed.
- Final focused + protected gate: `173 passed in 7.61s`; changed-file compile
  exit `0`; diff/scope/secret checks exit `0`. The three legacy exact-resume
  selectors, Admin compact `13 <= 12`, and two i18n/export selectors reproduce
  identically on detached `origin/main`; `NEW_FAILURES=0`.

### Customer exact-confirm acoustic bundle continuity — 2026-09-09

- Public job `#9F5AECE9AD` reached exact-price with local acoustic `5` speakers,
  registers `[high,low,low,high,low]`, coverage `145/145`, `26` source cues,
  `26` translated cues and quote `227 Xu`. The customer confirmed once.
- It then failed no-charge at `5%` with `AUTO_CAST_MANUAL_REQUIRED`; ASR,
  translation, TTS and mux flags in the terminal snapshot were reset/false,
  output bytes `0`, charged Xu `0`.
- Root is the exact-confirm serialization seam: `_subdub_auto_resume_state()`
  retained scalars but discarded nine validated acoustic arrays, including
  cluster sizes, unit counts, supported labels, speaker registers and register
  confidences. Admin does not pause through this customer exact-price seam.
- Correction persists only `bounded_multi_acoustic_evidence()` and rehydrates
  missing structured fields from the already hash-verified sidecar. The full
  sidecar acoustic bundle is revalidated against current model/algorithm
  constants and every pre-existing scalar must match. Semantic tampering remains
  fail-closed; non-Multi and Auto 2 do not enter the restore branch.
