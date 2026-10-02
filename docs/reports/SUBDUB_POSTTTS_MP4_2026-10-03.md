# Smart Post-TTS MP4 Delivery: 806A998EC7 And 53B6E00FC9

## Narrow Owner Contract

Base: `e1e155d10d50e007af8493c5daedc4d64362fc2d`.
Observed incident runtime: `e05ca028a24221d3628d7c2d240b09a576eeafd0`.

Owner now prioritizes a valid MP4 even when the dubbing is imperfect. Fix only
post-TTS audio/result handoff and fit rejection. Keep existing ASR, translation,
acoustic, cast, provider, checkpoint, wallet, ENV and secret paths unchanged.
Retain the approved <=2-second subtitle/audio tail into empty gaps, original
cue starts, subsequent cue starts and source video duration. Do not silently
drop words or change voices. Fit-quality warnings may no longer abort explicit
Smart rendering; actual media/QC, coverage, identity and ambiguous-submit gates
remain fail-closed. No paid calls or job resubmission are authorized here.

## Independently Verified Incident Corrections

Job `806a998ec7fa6a3df38f`: all 5 TTS entries are SUCCEEDED. The generic Smart
adapter can render a real MP4 and return audio bytes, but omitted `tts_provider`
and `output_audio_source`. The outer production guard infers generated audio
only when audio bytes AND a TTS provider are present. It therefore rejects the
successful result as `generated_tts_audio_missing`. The report's claim that
this terminal error necessarily means the 2.5 fit gate fired is unsupported.
The new regression executes that exact production guard without bot bootstrap.

Job `53b6e00fc9113899224e`: 23 successful TTS entries with 5 distinct assigned
voice IDs. Runtime state says `subdub_engine_selected=auto_smart_multivoice`,
`auto_smart_dispatch` empty. Sidecar speaker_3 has register `unknown`. This is
the generic Smart path, NOT proved V2 dispatch; no claim is made that the source
speaker count or genders were recognized with 100-percent accuracy.

Cue 14 starts 36.420, ends 37.300; cue 15 starts 37.300. Its trailing gap is
ZERO, not a long empty gap. Audio duration 2.285469 / 0.88 = 2.59712386.
Gap borrowing alone cannot remove this ratio without moving the next cue.
Cues 22 and 23 do have room and can consume their full utterances naturally.

Replay exposed another local helper defect: existing SRT generator yields
16.254s for a cue ending 16.255s because of float-to-millisecond rounding.
Exact equality in the new tail helper rejected the whole retime. Only 1ms
representation error is now accepted. Starts/text remain untouched; larger
mismatches still fail.

## Runtime Changes

1. `services/subdub_blackboxes/auto_smart_multivoice.py`: retain the actual
   TTS provider and verified expected/generated/mixed counts. Return the real
   captured audio origin, byte count and callback QC result after rendering.
   Explicit Smart duration-aware overfit cues produce
   `smart_audio_fit_degraded` and per-cue `smart_audio_fit_warnings` instead of
   fit-only aborts. State-less legacy guard tests and non-duration-aware checks
   retain their existing behavior.
2. `services/subtitle_dub_product_pipeline.py`: recognize the existing Smart
   lane and explicitly opted-in `n3_plus_proven_v2` dispatch for duration-aware
   timing/gap borrowing. Keep ordinary Multi/two-voice behavior unchanged.
   Apply the same warning policy to explicit Smart duration-aware audio while
   leaving existing thresholds and non-Smart checks intact. No strict V2 code
   or voice assignment is changed.
3. `services/subdub_smart_timing.py`: accept at most 1ms rounding discrepancy
   when matching original subtitle boundaries. Do not weaken gap, video-end,
   retry, text or identity constraints.
4. `tests/test_p0_subdub_smart_posttts_mp4_delivery.py`: eight tests covering
   actual outer audio guard, both cached jobs, generic/shared post-TTS paths,
   Smart-through-V2 compatibility, unchanged plain Multi, explicit quality
   warnings and millisecond validation.

The policy intentionally permits local pitch-preserving acceleration when
no gap exists. Cue 14 remains approximately 2.597x. This is a disclosed quality
degradation under the Owner's latest MP4-first decision, not natural-voice PASS.
No provider speed is raised and no new TTS request is made during verification.

## Empirical Red/Green And Regression

- Before production edits: new suite `6 failed, 1 passed in 15.51s`. The first
  failure is successful MP4 rejected by the actual outer audio guard; the five
  others show Smart gap/fit limitations. Separate 1ms case also fails before fix.
- After fix: `8 passed in 37.33s`, including real MP4 render and full decode.
- Core Smart/tail/timing/checkpoint/orchestrator/compression/strict-Multi suite:
  `217 passed, 1 skipped, 3 deselected in 92.51s`.
- Skip requires a different older 25-cue artifact not supplied. Three excluded
  tests require full bot bootstrap or compare changes against an obsolete SHA.
- Wider same-machine baseline: `194 passed, 11 failed, 1 skipped in 42.83s`.
- Wider branch: `194 passed, 11 failed, 1 skipped in 42.88s`, exact same failures.
  New wider failures: 0. This is not a full-repository test PASS claim.
- Python 3.11 compile for bot.py, all three runtime files and new test: exit 0.
- Workflow hygiene: `Ran 39 tests in 6.046s`, `OK`.
- `git diff --check`: exit 0. Protected-file comparator: exit 0.

## Persisted Real-Output Evidence

All 28 cached MP3s match their manifest SHA256. Real production timeline,
normalization, speech-activity QC, ASS/mux functions run locally without bot
bootstrap. Normalization uses local test defaults, not a production ENV change.
Each MP4 is checked with FFprobe, fully decoded by FFmpeg and accepted by the
actual outer production audio guard. No source/video retiming is introduced.

| Evidence | 806A998EC7 | 53B6E00FC9 |
| --- | --- | --- |
| Complete cues | 5/5 | 23/23 |
| Existing voice IDs retained | 1 | 5 |
| MP4 bytes | 7,912,328 | 18,600,520 |
| Source normalized duration | 59.621016s | 133.396333s |
| Output duration | 59.633333s | 133.396s |
| Codec | H264/AAC | H264/AAC |
| Cue-start shifts | 0 | 0 |
| Speech QC | speech_activity_ok | speech_activity_ok |
| Full decode | exit 0 | exit 0 |
| Outer audio guard | PASS | PASS |
| Quality warning cues | 0 | 4 (5, 7, 13, 14) |

SHA256 for 806A MP4:
`5da17913fba027ffadce3c0bbd28394b61d3bf12c89f6f508a31580374659c92`.
SHA256 for 53B6 MP4:
`94d238755030a068c604955a35c8ae66ae7d295041ed59f4a634f0bbffec599b`.

Artifacts under the parent task directory:
`artifacts/subdub-posttts-20261003/<internal_job_id>/verified-output/` contains
the MP4, matching SRT and verification.json. These are offline cached replays,
not fresh Telegram deliveries. Existing failed job states are not mutated.

## Acceptance Limits And Rollback

PROVIDER_CALLS=0
WALLET_MUTATIONS=0
ENV_OR_SECRETS_CHANGED=0
LIVE_PASS=NOT_TESTED
NEW_WIDER_FAILURES=0

A valid MP4 does not prove semantic translation or perfect speaker attribution.
806A cue 5 still contains unchanged phonetic source text. 53B6 has an unknown
register and a long source cue grouping speech; this release does not certify
their accuracy. Real corrupted/empty audio, missing cues, provider unavailability
and undecodable media still fail; this is not a universal success guarantee.

Deployment must pin the exact tested merge SHA and first check active jobs.
Rollback only these three post-TTS runtime edits via a reviewed revert PR.
Do not roll back ASR, speaker models or earlier receipt/pacing fixes.

Candidate lesson: offline MP4 proof must also execute the outer result/audio
contract and real QC. Do not infer a ratio failure from a generic missing-audio
terminal error. This is task evidence, not a promoted global rule.
