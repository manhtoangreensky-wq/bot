# Smart Multi Speaker Range Recovery

Date: 2026-10-01. Scope: Smart Multi acoustic preparation and cast dispatch.
Base: 31802da. Branch: fix/subdub-smart-asr-contract-20261001.

## Contract

Smart uses ASR text and word timing without requiring cloud speaker labels.
Discover 1-8 speech-backed identities, preserve every transcribed word and keep
one stable voice per speaker. A confident register uses its matching voice pool.
An uncertain register uses the existing distinct-voice policy. A successful
strict multi result keeps the proven v2 engine. The default legacy multi minimum
remains 3. A valid MP4 alone does not prove speaker identity or gender accuracy.

Protected: Auto 2, default multi count policy, translation, paid TTS routing,
compression QC, audio mixing, subtitle render, mux, delivery and settlement.
No new Telegram job or paid provider call is authorized by this source repair.

## Ordered Specs And Checklist

- [x] S1: Explicit Smart ASR contract, including cached-source bootstrap.
  Evidence: pending-sync tests cover fresh and cached Smart source without labels.
- [x] S2: Preserve the proven 3-8 raw acoustic count before accepting 1-2.
  Evidence: engine tests cover 1-8; legacy rejects 2; strict Smart 5 dispatches v2.
- [x] S3: Reuse extracted acoustic views during count fallback. Retain proven
  speech-backed identities when register allocation fails.
  Evidence: first red was 2 failed with fixed_vocal_gender_evidence_invalid;
  final contract/engine suite was 189 passed. Integration spies prove one vocal
  extraction and the same raw authority reaches the register fallback.
- [x] S4: Carry generic classifications through pending state and prepared cache.
  Generic 1-8 results do not masquerade as strict multi acoustic evidence.
  Evidence: prepare tests verify labels, coverage and generic state; cache writes
  and reads classifications only for the explicit generic marker.
- [x] S5: Protect real 5-speaker comparator under the default legacy engine.
  Fixture SHA256: 83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e.
  Evidence: actual 145-word resource gate: 1 passed in 193.42s; 5 speakers,
  145/145 words, registers high/low/low/high/low, 2 female and 3 male.
- [x] S6: Real Smart comparator: 1 passed in 254.16s. Five speakers, 145 words,
  five distinct test-pool voices; registers high/unknown/low/high/low. Source
  confidences: 0.999986 / 0 / 0.999632 / 0.999999 / 0.999802. Speaker 1 remains
  distinct and receives a stable separate voice despite conflicting gender votes.
- [x] S7: Finish protected Smart/TTS/render comparison and final source compile.
  Seven failures reproduce on original 31802da source; one environment failure
  is missing telegram. No new failure identified in the compared cases.
- [ ] S8: Commit, update to current main, PR, squash merge and exact-SHA deploy.
- [ ] S9: Inspect production SHA and systemd services after deploy.
- [ ] S10: New live MP4 with cast map and audible 10-20s verification.
  Requires a new bounded paid-provider authorization; old job grants are consumed.

## Patch Boundaries

- bot.py: Smart ASR kwargs, cached media bootstrap, generic acoustic validation,
  pending marker, prepared-cache classification persistence and restore.
- auto_multi_speaker.py: forward Smart's optional minimum to the existing runner.
- subdub_multi_speaker_embedding_onnx.py: optional 1-8 range with legacy default,
  strict count first, count retry using the same views and register fallback.
- auto_smart_multivoice.py: generic evidence uses Smart casting; strict 3-8
  evidence continues to use auto_multi_speaker_v2.
- Focused tests and the real-fixture resource gate only.

## Runtime Observations

Read-only VPS check: bot f81132c9b28c3145c7a749318368d9deceea27bd;
worker 82ed875d53a981fa08a4f2b6bca6b4c68651837d. Bot, web, nginx and owner
product-video worker were active. Worker precheck sees untracked bot.db: exactly
0 bytes, timestamp 2026-10-01 10:43:30 +07, no holder reported by fuser.
It must be preserved before the standard transaction can proceed. No reset,
clean, autostash or overwrite of WIP is allowed.

## Completion Limits

Synthetic count tests and the real comparator do not prove universal diarization
accuracy, all possible videos, or a new delivered MP4. Preserve distinct speaker
count, report degraded register truthfully, and audit actual output audio in live
acceptance. Merged, deployed and delivered remain separate evidence gates.

## Two Failed Recovery Attempts

Both experiments are recorded and excluded from merge/deploy acceptance:

1. Raw-centroid fallback over grouped ASR units: real Smart fixture returned
   raw_speaker_count=5, detected_speaker_count=4. Resource gate failed in 147.54s.
2. Raw-centroid fallback over individual words: a short-turn unit regression
   passed, but the real Smart fixture still returned 4/5. Gate failed in 147.57s.

Do not weaken the five-speaker assertion or publish either failed experiment.

## Verified Recovery

Read-only local diagnostic replay on the same PCM and 145-word timeline:
raw speakers=5; proven legacy speech partition=5; mapped word speakers=5;
word coverage=145. Original-audio constrained partition throws
fixed_vocal_gender_allocation_unstable. On the proven legacy identity, original
gender votes are:

| Speaker | Strong Female | Strong Male | Windows |
| --- | --- | --- | --- |
| 0 | 15 | 0 | 16 |
| 1 | 6 | 4 | 12 |
| 2 | 0 | 13 | 13 |
| 3 | 11 | 0 | 11 |
| 4 | 0 | 8 | 8 |

Implemented recovery: retain the existing legacy speech-window partition and its
word mapping as identity authority. Apply original-audio votes to those same
speaker IDs; speaker 1 is unknown, not forcibly female or merged with another
speaker. Assign five distinct stable voices. Remove the unsuccessful raw-centroid
fallback from the candidate patch. Default legacy and post-65 paths stay locked.
Acceptance: real Smart fixture 5/5 speakers, 145/145 words, five distinct voices;
source-register conflicts produce unknown; default legacy fixture still passes.

Current verification: focused suite 189 passed in 13.91s; real Smart 1 passed in
254.16s; unchanged legacy comparator 1 passed in 193.42s. Runtime-interpreter
compile on a temporary copy of bot.py passed, with matching SHA256
801370333d107170935d1290b1f8c5532160978f729c17b026d607fd7e1746ae.
Final engine and test modules compile locally, exit 0. git diff --check exit 0.
Wider service suite: 149 passed, 8 failed, 2 deselected. One failure is missing
telegram in the temporary environment. On an archive of unchanged 31802da source,
all seven selected non-environment failures reproduce: 7 failed, 127 deselected
in 519.53s. They are one obsolete historical diff guard, two existing canonical
SRT fixture failures, and four existing compression fixture failures. Those
paths remain outside this repair. This is not a claim that the full suite passes.

The replay script is outside the repository worktree at
../../.diagnostics/smart_identity_comparison_20261001.py. It calls local models
only, without importing bot or contacting providers.
