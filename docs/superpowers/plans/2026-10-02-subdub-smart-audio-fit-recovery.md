# Smart Multi Audio Fit Recovery

Date: 2026-10-02. Scope: the Smart Multi cue-fit gate between TTS artifacts and
the existing cue-locked FFmpeg timeline builder.

## First Red

Live job `139167d9f74dfa76cd62` produced 25/25 successful Key4U MiniMax TTS
entries, five stable speaker IDs and five stable voices. It stopped before mux
because 16/25 raw cue ratios exceeded 1.8 (64%) and the Smart gate rejected the
whole job at 30%. The highest ratio was 4.070455 and no cue exceeded hard cap 5.

Offline replay of the same 25 TTS artifacts through the existing
`bot.build_dub_timeline_audio` produced a valid 134.064-second audio file:
`speech_activity_ok`, 2,683,140 bytes, 25 cue-locked inputs, `atempo` fit,
`timeline_extended=no`, `overlap_count=0`. This proves the raw-ratio gate was
blocking a render path that already knows how to fit the audio.

## Contract

- Smart-only defer is allowed only when cue-locked timing is active and a real
  render/timeline callback is present.
- The existing FFmpeg timeline builder is the authority for actual fit and
  audio validation.
- A cue above hard cap 5.0 still fails immediately.
- If FFmpeg produces empty/invalid audio, the existing downstream failure gate
  still fails the job.
- Auto 2, legacy multi, manual voice, translation and wallet behavior remain
  unchanged.
- No threshold is raised and no cue is dropped or merged across speakers.

## Ordered Checklist

- [x] Confirm first-red live evidence from job 139.
- [x] Replay the exact TTS artifacts offline with the production FFmpeg builder.
- [x] Defer Smart raw overfit count gate to actual render when callback exists.
- [x] Keep hard cap and downstream audio validation unchanged.
- [x] Add a regression with 16/25 overfit cues and a render callback.
- [x] Compile changed modules and run focused suite.
- [ ] PR, merge, deploy exact SHA.
- [ ] One fresh bounded live job after deploy, if Owner authorizes it.
- [ ] MP4, receipt and 10-20 second audible check.

## Evidence

- Focused suite after patch: `196 passed in 10.68s`.
- Changed-module compile: exit `0`.
- Offline production FFmpeg fit: valid audio, 134.064 seconds,
  `speech_activity_ok`, five speaker voice map preserved by input artifacts.
- No provider call was made during offline replay.
