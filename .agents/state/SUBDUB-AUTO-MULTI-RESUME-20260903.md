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
