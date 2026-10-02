# Smart Source-Locked MP4 Recovery

Date: 2026-10-02. Owner acceptance: speech must match original video timing.
Do not deploy sequential recovery that shifts speech by 22.662313 seconds.

## Evidence And Correction

Job `139167d9f74dfa76cd62` has 25 successful TTS entries and five voices, but
16/25 raw fit ratios exceed 1.8; the maximum is 4.070455. It failed before mux.
The original PR #1285 callback-based bypass was insufficient: decoding audio
compressed at 4x does not prove intelligibility or a complete MP4.

An offline experiment reused the existing sequential scheduler and production
FFmpeg builder/renderer, isolated from bot startup with controlled font/style.
It produced H264/audio MP4: 134 seconds, 18,155,750 bytes, SHA256
`d2b49f24bff19b4a7c6e16e924e65a122671bf51e7d0ffe6949b6d7616ea2381`.
Full decode passed; 25 texts and five voice identities were retained.
However, maximum source shift was 22.662313 seconds. Owner rejected this on
2026-10-02. This is NOT accepted product evidence; that code was removed.

The narrower source defect: Smart's generic route bypasses original-speech
binding. The failed manifest's `source_text` equals translated text. A test
using the real speech-rate function measured request speed 0.95 before the
fix and 1.8 after preserving original text. This proves request shaping, not
the actual duration of a future TTS.

## Contract

- Match original speech by unique stable cue ID, never position/speaker guess.
- Do not change translated words, speaker/voice IDs, cue start/end or SRT.
- Preserve raw audio duration so trimmed duration cannot clip trim bounds.
- Respect false audio QC before mux. Restore original compression gates.
- Shared pipeline, strict multi V2, auto two, ASR/acoustic, wallet and ENV
  remain unchanged relative to main. No paid calls during source verification.
- Accepted MP4 must be technically valid AND source synchronized. A tone
  fixture proves rendering, not a successful fresh live job.

## Ordered Checklist

- [x] Inspect cached TTS/source artifact; preserve hashes.
- [x] Remove raw-gate bypass and rejected sequential drift.
- [x] FIRST RED: original speech lost; actual request speed stays 0.95.
- [x] Bind original text on generic Smart only; retain IDs/timing.
- [x] Test matching, reordered, unknown and duplicate identities.
- [x] Preserve raw trim authority and stop on false audio QC.
- [x] Real FFmpeg tone MP4: H264/audio, burned subtitles, full decode,
  unchanged cue timing and three-second video duration.
- [x] Cached overfit audio remains fail-closed, not accepted as synced MP4.
- [x] Source suite: 7 passed, including local cached-artifact guard.
- [x] Regression: 204 passed, one identical baseline/branch failure below;
  no new failures in the comparable six-file suite.
- [x] Python 3.11 compile (bot, Smart, shared pipeline, new tests): exit 0;
  diff check clean; bot/shared timeline/strict V2 unchanged by this task.
- [ ] Update PR #1285 with narrow patch and truthful report.
- [ ] Merge/deploy source-locked patch only after verification/review.
- [ ] One new bounded paid job only with fresh Owner authorization.
- [ ] Verify real MP4, source timing, five voices, 10-20 second speech/receipt.

## Verification

Run `python -m pytest -q -p no:cacheprovider
tests/test_p0_subdub_smart_bounded_audio_recovery.py`.
Cached-artifact guard additionally needs local-only input paths
`SMART_CACHED_MP4_REPLAY_DIR` and `SMART_CACHED_TTS_MANIFEST`.
Do not change production provider ENV for this test.

Known failure on base `7c85013` and branch: payload-contract test
`test_smart_multivoice_standard_pipeline_delegation_succeeds_without_typeerror`
uses an `extract_pcm` fake rejecting required `workspace` keyword. It fails
before changed source-rate/render code. Do not modify unrelated PCM/ASR code
to hide this baseline test defect.

## Remaining Limit

Old audio cannot prove fresh TTS duration/intelligibility. Cue 13 has 6.425
seconds of detected speech in a 1.760-second window: even deleting all silence
would require 3.65x compression. Fresh source-aware TTS and, if still too long,
duration-aware translation/TTS adaptation need real evidence. Do not declare
all valid videos supported or claim LIVE PASS from this source patch.

The previous one-job live grants were consumed before this task. A fresh
bounded grant was requested; no paid request or new job has been made here.
