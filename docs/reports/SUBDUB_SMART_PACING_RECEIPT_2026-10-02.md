# Smart Pacing, Voice Count Receipt, And Narrow Acoustic Fallback

## Owner Scope

Fix the reported fast speech/subtitle pacing, missing voice count, and the
specific early failure on job `9aa357e59a4e9edc2ded`. Runtime edits are confined
to `bot.py`. Do not change provider configuration, wallet/charging, ASR
adapters, acoustic models, strict Multi V2, or translation content.

Base: `1e2d0a58156f1839fbc74d1094fdc5d0cf8c4146`.

## Evidence And Corrections

Job `7500d08c5831a5c51f47` delivered an H264/AAC MP4, 181.000 seconds,
53,185,197 bytes, SHA256
`3dc56aec22446dfc16544ecacf9962a3ddf2e4efe479f7ad3a8ccb5e30ca04b3`.
Full decode exited 0 without stderr. It used 3 speakers/voices, 71 successful
TTS cues, 629/629 source words, and charged the Owner 0 Xu. The receipt price
was 843 Xu. However, the Owner rejected its speech pacing. Technical delivery
is not acceptance of synchronized, natural dubbing.

All completed TTS requests observed in that job used speed 1.8. The Smart
estimator multiplied target text units by 0.8 seconds before measuring audio.
Rendering removed internal silences, accelerated overruns, and never slowed
short utterances to fill their subtitle windows. Matching cue starts alone
therefore did not prove speech/subtitle synchronization.

Job `9aa357e59a4e9edc2ded` failed before translation on a 60-second input with
31 recognized words. Its recorded acoustic failure is
`fixed_vocal_view_unstable`. Smart's existing fallback allowlist omitted that
code. This is not evidence of a DeepL translation failure.

The receipt proof validator recognized only the strict multi lane even when
Smart used the same verified V2 cast. It rejected the proof and selected a
receipt branch that omitted both speaker and voice counts.

## Changes

- `subdub_auto_multi_terminal_proof_fields`: recognize Smart with the same
  typed acoustic, cast, attribution, geometry and count proofs. Retain Smart's
  lane identity. No count is inferred from the chosen button or a filename.
- `synthesize_dub_segment_chunks`: Smart requests the selected base speed;
  no text-length guess forces 1.8x. Preserve the measured trimmed utterance
  duration, including its internal pauses, as the fit authority.
- `subdub_plan_dub_timeline`: Smart fits measured duration to the locked
  subtitle window in either direction. Start/end and video duration stay
  unchanged. Other lanes retain their original minimum tempo behavior.
- `build_dub_timeline_audio`: remove Smart's internal-silence deletion; use
  pitch-preserving `atempo` for slower as well as faster fits; reset Smart
  timestamps by sample count after tempo and delay. Real FFmpeg verification
  caught and fixed a nonmonotonic timestamp issue when slowing audio.
- `video_dubbing_prepare_subtitles`: add only `fixed_vocal_view_unstable` to
  Smart's existing single-voice fallback. Preserve all source cues/text; do
  not claim that an uncertain speaker count was proved. Unrelated failures
  still raise.

No compression guard was removed or relaxed. Dense translations may still
be rejected by existing quality limits; this patch does not claim universal
success or authorize omitting translated text to force an MP4.

## Verification

Local Python 3.12, isolated AST extraction of production functions; provider
callbacks are mocked. This avoids starting the production bot during tests.

- Same-machine focused baseline: 16 failed, 2 passed, 28 deselected.
- Same focused checks after patch: 18 passed, 28 deselected.
- Entire pacing/receipt/pending suites: 45 passed, 1 skipped (cached old
  paid artifacts unavailable), latest run 10.88 seconds.
- Added core Smart/checkpoint regression: 182 passed, 1 skipped, 3 deselected.
  The deselected tests are two old branch-only assertions forbidding any
  `bot.py` edit and one integration requiring the complete bot bootstrap.
- A wider shadow run was not accepted as PASS: its runtime-dependent checks
  cannot run against the deliberately minimal bot test module, and its old
  static guards forbid the authorized edit. No production changes were made
  to satisfy those unrelated checks.
- `python3.11.exe -m py_compile bot.py` and all three changed test files:
  exit 0. `git diff --check`: exit 0.
- FFmpeg test: 2-second audio with an internal pause fills its 4-second source
  cue, retains the pause, remains audible near cue end, is silent after the
  cue, and preserves the complete 8-second output timeline.
- Fallback test: raw and wrapped acoustic failures retain all 31 words in
  four cues. The unrelated-failure control remains fail-closed.
- Receipt tests: verified counts 3, 5 and 8 in Vietnamese/English; missing
  verification does not fabricate a voice count.
- Protected source comparators: no changes to strict multi engines, the
  shared product pipeline, or providers. Ordinary TTS speed behavior is
  asserted unchanged.

## State

PROVIDER_CALLS_DURING_PATCH=0
WALLET_MUTATIONS_DURING_PATCH=0
ENV_OR_SECRETS_CHANGED=0
NEW_FAILURES_FOCUSED_COMPARISON=0
LIVE_PASS_NEW_PATCH=NOT_TESTED

Both earlier single-job grants were consumed. A new paid job needs a new
bounded Owner grant; do not replay the interrupted ambiguous TTS submission.
Fresh real-output acceptance must verify the complete translation, voice
count receipt, source/subtitle/speech pacing, and actual MP4 delivery.
