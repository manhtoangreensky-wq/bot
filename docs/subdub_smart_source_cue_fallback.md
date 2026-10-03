# Smart Source-Cue Fallback

Owner approved: retain original audio for only a cue that cannot fit naturally
after the existing <=2-second empty-gap tail extension. Keep translated subtitles,
source start, later cue starts and video duration. A failed translation cue retains
source text/audio and explicit review metadata, instead of aborting the whole MP4.
This is not full-video source audio fallback or a claim of fully translated output.

Only explicit Smart generic and Smart-dispatched V2 use the new helper. It checks
duration-aware chunks after bounded tails, extracts the exact corresponding source
window with FFmpeg into PCM WAV, verifies decoded frame duration, and replaces only
that cue's render payload. No `atempo` or text shortening is used. Every replacement
is prepared/verified before mutating chunks, so a failed window cannot leave a
half-modified timeline. Corrupt/absent source remains a typed real failure, never
silence or a fake validated output. Valid cues and all non-Smart paths stay unchanged.

Paid TTS checkpoint artifacts are not changed. Their generated counts remain the
actual generation count. Render evidence separately lists source-audio cue IDs,
reason per cue and the number of TTS voices actually played. Receipt discloses
original-audio cues and actual played voices, not only the assigned cast map.
Price/confirmation/wallet/settlement formulas and provider-call policy are unchanged.

Smart speaker uncertainty follows the same render-only source policy. After
acoustic recovery, unproven attribution is not evidence of one real speaker;
unproven register cues must not play an arbitrarily selected male/female voice.
Preparation records the affected cue IDs, preserves them through bounded JSON
resume, and only Smart render paths mark those chunks for exact source extraction.
Known identities/cues continue dubbing unchanged. If every attribution is uncertain,
all affected cues retain source audio and the receipt explicitly reports that the
speaker count is not reliably determined, with zero dubbing voices actually played.
This is degraded translated-subtitle output, not a claim that all speech was dubbed.
Checkpoint generation counts and artifacts remain untouched. Per-cue provenance
uses `speaker_attribution_uncertain`, distinct from translation/duration failures.

Measured source case: a0.88s source window with2.285469s generated audio and no
next gap used to need2.597x. The new policy preserves original audio at1x for that
cue; other cues continue to use target TTS when they fit. Synthetic test-only byte
tags were replaced by real decodable source fixtures where source extraction is
required. Existing hard-fail controls for plain multi remain intact.

Tests cover real WAV duration, no cue shift/voice reassignment, exact cue coverage,
missing translation flags surviving QC, Smart-only partial preparation, corrupt
source, out-of-video windows, atomicity, truthful vi/en receipt and cached1/2/5-voice
MP4/decode/outer guards/production-send-boundary regressions. No paid or Telegram
live calls run in these tests. Semantic perfection is not inferred from decode.

Final measured suite:250 passed,1 older archival fixture not supplied and skipped,
7 subtests passed (196.66s). Workflow hygiene:39 passed. Compile/diff checks exit0.
Old forced-fit expectations were deliberately replaced by stronger <=1.001 tempo
checks and explicit per-cue source provenance, not removed. Cached BBDD final cue
now uses source at1x instead of1.279338x; cached five-speaker cue14 uses1x instead
of2.597x. Missing/corrupt media and plain-multi quality failures still fail safely.
