# Smart Source Gender Parity With Multi

## Scope

One runtime file changes: `services/subdub_smart_speech_identity.py`.
Only Smart's already-existing speech recovery is affected. Stable primary
multi and strict-two paths, ASR, translation, TTS provider/speed/checkpoint,
cue timing, MP4 rendering, financial logic, ENV and model assets are unchanged.
No public function signature is changed. No filename/job/language/timestamp
selects this correction, and gender evidence never sets the speaker count.

## Working Multi Code Reused

The existing multi preflight first accepts validated acoustic register evidence;
otherwise it classifies source ranges via PANN/UVR and per-person vote/margin
aggregation. The Smart correction reuses:

- `subdub_two_speaker_gender_onnx._validated_model_paths` and `_infer_selected_cues`
  for a bounded source-context anchor, including speech and singing classes.
- The same PANN CPU session and class indices on already-separated vocal windows.
- `subdub_multi_speaker_gender_onnx._aggregate_one_gender_result` for its existing
  vote, score-margin and register-confidence rules.

The stable implementations above are called, not edited or copied. PANN is an
optional local verification pass; missing/busy/expired/resource failures return
available evidence or preserve the previous recovery rather than a new MP4 crash.
Source batches remain bounded by the existing 48-second evidence limit; long
continuous runs do not become a single-person gender authority.

## Correction Contract

A run needs full-source and window-vote agreement. Strong opposite-window
evidence vetoes smoothing, preserving real speaker turns. A stable identity
whose supported source evidence consistently contradicts its old register is
reclassified in place, preserving its identity and count. Otherwise, a proven
misattributed window may move only to an existing identity of the evidenced
register when both embedding views agree and cluster support remains valid.
Same-register people remain distinct; weak/missing/conflicting evidence leaves
the prior decision in place. This does not guarantee human-perfect attribution
for overlap, music, falsetto, sparse speech or ambiguous input.

## Measured Verification

- Initial RED: 11 failed against the deployed helper without source correction.
- Additional stable-person RED: four failures for counts 2/3/5/8 before in-place
  register correction; the completed tests also cover single and same-gender cases.
- Final focused suite: 190 passed, 10 private/cached-fixture skips, 42.93 seconds.
- Actual scalar Smart synth boundary test: corrected source register reaches the
  correct male/female voice ID; second invocation reuses the checkpoint.
- Python 3.11 bot/helper/test compile and diff checks: exit zero.
- Ubuntu deploy workflow hygiene: 39 tests, OK.
- Private same-source replay with real existing PANN/UVR: all 70 words retained,
  source cue boundary shift zero, two identities retained, opposite approved test
  cast routes. Ten conflicting original-source windows corrected; eight on the
  normalized source. No remaining full-run source-PANN-reference conflict.

Source PANN comparisons are model parity evidence, not human-labeled accuracy.
No new paid TTS audio, MP4 regeneration or listening acceptance is claimed.
The reported latest MP4's full workspace had been cleaned; a retained earlier
ASR response from the same media is not claimed as its exact fresh word timeline.
The Owner-selected interval is evaluation-only, never a runtime constant.

## Baseline Failures And Private Data

The legacy `test_p0_subdub_per_speaker_auto_gender_cast.py` suite has the same
28 failures/225 passes on baseline; its failures remain on the expanded candidate
run. The old synth-signature suite has the same four compression-fixture failures
and three passes on baseline and candidate. Neither test suite nor the runtime
they cover was changed to hide failures. No new failure was found in the scoped
comparators. Private media, transcripts, source scores and diagnostic data are
not published to GitHub.

## Release And Tester Checklist

Update the latest source-gender checkpoint only after exact-SHA deployment and
actual deployed-module offline replay. Preserve prior tags; revert only this
narrow PR for a regression, never reset unrelated main changes.

- Check source gender versus voice payload per cue, not merely distinct voice IDs.
- Check identity/register continuity and real opposite-speaker turns.
- Check 1/2/3/5/8 speakers and same-gender speakers without forced pairing.
- Check model-unavailable/lock-busy/deadline fallbacks do not add a whole-job failure.
- Check word coverage, original timestamps, checkpoint reuse and final MP4 controls.
- Retain fresh ASR/sidecar/manifest before cleanup for a separately approved live test.
- Keep merged, deployed, offline-verified and live-listened statuses separate.
