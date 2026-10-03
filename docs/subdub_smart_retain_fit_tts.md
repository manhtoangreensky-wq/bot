# Smart Fitting TTS Retention

## Narrow Contract

Measured defect: a whole-source attribution warning marked every cue uncertain;
the source-selection helper then discarded every valid translated TTS payload.
An MP4 existed, but actual played dubbing voices were zero.

Runtime scope: only `replace_unfit_smart_cues` in
`services/subdub_smart_source_audio.py`. No caller signature, ASR, translation,
speaker model/threshold, cast decision, checkpoint, pacing, tail limit, renderer,
delivery, pricing, wallet, ENV or DB change.

## Selection Rules

1. Non-duration-aware input keeps legacy behavior unchanged.
2. Translation-present TTS within the available cue window stays unchanged,
   including bytes, duration, voice ID and uncertainty metadata.
3. Missing translation retains source with reason `translation_missing`.
4. A measured unfit duration retains source with reason
   `natural_audio_exceeds_window`, preserving all existing decode/window guards.
5. Uncertainty alone cannot replace audio. Existing approximate fallback voice
   selection remains disclosed; no confident speaker count or gender is invented.

## Acceptance Checklist

- [x] Eight uncertain, fitting TTS payloads are retained byte-for-byte.
- [x] Mixed fit/unfit/missing cues replace only the actual local exceptions.
- [x] Generic Smart and Smart-dispatched V2 preserve fitting dubbing.
- [x] Same-source cached paid TTS remains in a real rendered MP4.
- [x] Source-only actual failures, atomic decoding and non-Smart controls remain.
- [x] Timestamps are not shifted, speed is not increased, no text is dropped.

Focused verification:32 passed in83.79s. The four added cases failed before the
patch, including an eight-cue real MP4 with zero dubbed voices and cached paid
TTS discarded by whole-source uncertainty. Final wider regression:245 passed,
1 unsupplied archival fixture skipped. Workflow hygiene:39 passed. Python3.11
compile and diff checks passed. These are offline results, not paid LIVE PASS.

No paid provider request or production job is created by these tests. Cached
and synthetic render tests prove payload retention/media integrity, not new
live delivery or correct gender for acoustically unproven speech.
