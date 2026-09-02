# SubDub Auto Multi — Fixed Vocal Acoustic Authority

## Problem measured live

The existing Auto Multi engine groups ASR words into acoustic regions before
speaker clustering. On one source file, two independent local ASR timelines
selected `k=6` and `k=5`; therefore word segmentation is not a valid speaker
identity authority. Raw-mix VAD also varies with background music. A permissive
pairwise threshold was rejected because its measured adjusted Rand index was
only `0.637`.

## Authority contract

Only exact `auto_speaker_lane=multi` uses this design:

1. Extract the existing bounded stereo PCM and reuse the existing hash-locked
   UVR vocal model without modifying the exact-two module or model bytes.
2. Resample the vocal stem to mono 16 kHz.
3. Build fixed `1.5s` windows at `0.75s` period, independent of ASR words and
   language.
4. Select vocal-evidence windows by gain-invariant energy percentiles
   `42.5/45/47.5/50`. All four views must select the same `k` in `3..8`.
5. The core `47.5` and `50` percentile partitions must match exactly on their
   common windows after numeric-label alignment. Each cluster must retain the
   existing minimum unit and speech support.
6. Use the top-50 partition to build normalized speaker centroids.
7. Map ASR-derived word units after speaker discovery: temporal-overlap
   majority wins when dominance is at least `0.2`; otherwise use nearest
   acoustic centroid. Every source word is assigned exactly once, every
   acoustic speaker has at least one mapped word unit, and cue timing is never
   changed.

## Fail-closed constraints

- No expected speaker count or fixture hash branch.
- No raw word text, PCM, embedding, centroid or provider payload persistence.
- No threshold relaxation when percentile views disagree.
- No change to exact-two files, pricing, wallet, TTS, mux or delivery.
- No provider/live action without fresh Owner authorization after deployment.

## Measured design evidence

- Fixed vocal windows have base/shift cosine mean about `0.997`.
- Energy percentile `42.5/45/47.5/50` all select `k=5` on the exact fixture.
- Core `47.5` vs `50` partition ARI is `1.0`.
- Hybrid mapping covers all five identities on two independent ASR timelines:
  `23` units -> `[3,2,4,11,3]`; `35` units -> `[4,4,12,9,6]`.

## Post-main verification

On base `ab267bedd4aa300bf2160be7b8d828009578127c`, the clean branch is
`0 behind / 2 ahead`. Recovery is `57 passed in 529.16s`; focused/protected is
`307 passed in 10.84s`; the full real-resource gate is `4 passed in 165.18s`.
The fixed-vocal exact-fixture call takes `139.76s`, below the `300s` production
budget. Full compile, YAML, diff, protected hashes, and secret scan exit clean.
Provider calls, database mutations, and wallet mutations are all zero.
