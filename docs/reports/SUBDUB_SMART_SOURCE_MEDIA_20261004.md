# Smart Post-TTS Source Fallback Contract

## Narrow Runtime Scope

Only `services/subdub_smart_source_audio.py` changes: 12 added/3 removed lines.
The source gender helper from PR1351, ASR, translation, TTS provider/checkpoint,
tail-borrowing algorithm, MP4 renderer, wallet/pricing, ENV, bot and stable lanes
are unchanged. No function signature or other runtime module is changed.

## Two Reproduced Boundary Defects

An existing `source_file` may refer to an SRT artifact. The helper previously
accepted any existing path and passed it to FFmpeg's audio stream selection,
discarding valid media bytes. Known subtitle/text suffixes now reject that path
as audio media and use the already-supplied media bytes. Without media, the
failure remains truthful; corrupt media never yields silence or fake success.

The reported failed job also reproduces `source_window_incomplete` on its valid
MP4: a last cue borrows an empty tail according to a rounded duration hint, while
the source AAC track ends earlier. Replacing with original speech must not ask
FFmpeg to decode the borrowed TTS tail. The helper now validates and decodes the
already-recorded `smart_source_end`, retaining the original source interval.
Cue display/scheduling timestamps remain unchanged. The fallback chunk leaves
duration-aware TTS fitting so original speech plays at tempo1.0, without slowing
to fill a borrowed gap. No generated voice, TTS speed or global timing rule changes.

The cached-prepared loader does not itself return the SRT path as `source_file`;
the path ambiguity alone is not claimed to prove this job's exact exception
chain. Both byte-only MP4-tail and SRT-path failures were independently reproduced.

## Verification

- Initial RED: 14 boundary failures against deployed code.
- Source-tempo RED: ratio0.45 instead of1.0 before the final chunk-flag correction.
- Final new tests: 15 passed, including actual cached last-cue media evidence.
- Protected focused suite: 106 passed/8 private-fixture skips,38.11s.
- Python3.11 bot/helper/test compile and diff checks exit0.
- Ubuntu workflow hygiene: 39tests,OK.
- Offline post-TTS replay reused six successful audio artifacts,retained the
  original two cast IDs and six translated cues,rendered a real H264/AAC MP4,
  and passed full FFmpeg decode. Only the last cue retained source audio;both
  dubbed voices remain used. Source tempo1.0;shifted cue starts0.
- Original source workspace files hashed identically before/after replay;
  no provider request,new job,resubmission,DB write or wallet mutation occurred.

The measured replay output is60.0s versus media-format59.621016s. The unchanged
renderer retains its existing rounded-duration policy and reports0.379s of
video tail extension. This is disclosed,not claimed as exact duration equality
or introduced as a new render-policy fix. No transcript accuracy or newly paid
live listening acceptance is claimed. Private job media/audio/text are excluded
from GitHub. A diagnostic JSON serializer error after rendering was repaired
privately;the MP4 hash/size/full decode were independently checked.

## Checkpoint And Tester Cases

Update the latest source-fallback checkpoint only after exact-SHA deployment
and actual deployed-module MP4 replay. Retain PR1351's gender checkpoint and all
older tags. For regression,revert this narrow PR rather than rolling back main.

- Existing subtitle path plus valid media bytes cannot select text as audio.
- Borrowed source tail does not require nonexistent AAC frames or alter tempo.
- Invalid/corrupt/out-of-range source remains an atomic,truthful failure.
- Fit TTS cues,voice IDs,text and source starts remain unchanged.
- Verify actual MP4 decode,two played dubbing voices and source-fallback receipt.
- Keep offline MP4 proof separate from terminal-job delivery and billing status.
