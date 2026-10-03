# Smart Mixed-Two Count Recovery

## Scope And Operating Contract

Only `services/subdub_smart_speech_identity.py` changes at runtime. The stable
primary multi-speaker and strict-two lanes, models, thresholds, ASR, translation,
TTS retention, timeline speed, tail borrowing, MP4 renderer, pricing and wallet
remain unchanged. Public/private function signatures are not changed.

Previously, one collapsed speech-view count discarded two otherwise supported
identities before Smart's existing two-voice casting could run. This recovery
is only eligible for count views containing one `1` and two `2`s. Both two-count
partitions must retain cluster support and agree on labels at least 0.95.
At least 0.95 of speech windows must still meet the unchanged 0.98 cosine gate.
Both source registers require at least four strong windows, reusing exact-two's
minimum-evidence constant. The existing gender-constrained speech authority
must validate opposite low/high registers and three partition agreements of
at least 0.95. It is not a new model or a forced two-person setting.

Validated reliable-window labels remain authoritative. Centroids assign only
missing unreliable-window labels, and both base/shifted projections must agree.
Single/same-register insufficiency, excessive noise, corrupt inputs, partition
disagreement and any three-plus count disagreement retain the prior rejection.
Stable same-register two-person and stable 1/3/5/8 cases use the original path.
The strict-two PANN classifier is not changed or relabeled as a fresh inference.

## Verification

- RED: four failures and nine passes against the unchanged deployed helper.
- GREEN: thirteen new regression tests passed, including private fresh evidence.
- Scoped protected suite: 173 passed, nine private/cached-fixture skips, 42.29s.
- Additional skip readback: 97 passed, six explicit private/cached-fixture skips.
- Ubuntu deploy-workflow hygiene: 39 tests, OK.
- Python 3.11 compile: bot, helper and new test exit zero; diff checks exit zero.
- Private fresh source replay: 70/70 words, two low/high identities, two distinct
  approved cast IDs, ten mapped cues, zero changed cue boundary timestamps.
  Original and normalized source were checked; no fresh TTS or paid API call.

Two existing continuity assertions fail identically with and without the
candidate: `test_identity_partition_keeps_one_person_one_register_across_scenes`
and `test_stable_identity_partition_overrides_global_gender_allocation`.
Their shared engine is unchanged. They are reported, not removed or rewritten.
Windows workflow tests had four missing-coreutils failures; the same 39 tests
were run successfully on Ubuntu rather than changing deployment code.

## Tester Checklist And Recovery

- Compare mixed male/female inputs with fresh ASR timings, not an older cache.
- Confirm source identity count, distinct cast IDs and actual dubbed voice count.
- Confirm single-speaker, same-register two speakers and stable 3/5/8 inputs do
  not enter mixed-two count recovery.
- Confirm failed jobs have terminal status rather than an indefinitely running panel.
- Retain ASR, sidecar and TTS manifest before successful workspace cleanup.
- MP4 live listening remains unverified; do not mark this release LIVE PASS.
- Update the checkpoint to the merged PR only after deployed/offline readback.
  For a regression, revert this narrow PR, not unrelated main changes or working
  ASR/TTS/MP4 code. Previous checkpoints remain available.

Private media, transcripts, identities, ASR responses and diagnostic NPZ files
are excluded from GitHub. No new production job, paid call or wallet mutation
is part of this patch's offline verification.
