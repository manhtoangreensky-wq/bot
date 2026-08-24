# SubDub Multi-Speaker Blackbox Design

## Goal

Ship a Vietnamese Auto SubDub product for multiple detected speakers without changing the proven two-speaker lane. The current one-button Auto route is split into two explicit runtime profiles that share pricing, settlement, delivery, and subtitle contracts but own separate acoustic preflight behavior.

## Locked baseline

- Two-speaker live rollback anchor: PR #844, merge SHA `0c5e0dc9b0b11bb864124fa44403c7c049a06904`, delivered job `5ECF6FB24B`.
- The existing `services/subdub_blackboxes/auto_speaker.py` path remains the default when no multi marker is present.
- Default/manual voice lanes, subtitle lanes, pricing, Xu settlement, provider credentials, environment, Telegram receipt, mux, and delivery are protected.
- PR #853/SHA `7b4053acd9a2bd44c29a15ebc5e0e86152fab24f` is an empirical checkpoint, not the final separation boundary.

## Architecture

Add a thin `services/subdub_blackboxes/auto_multi_speaker.py` adapter. A new state marker `auto_speaker_lane="multi"` selects it; the existing exact Auto state pair remains unchanged so quote, confirmation, settlement, and receipt code do not branch.

The bot dispatches:

- no multi marker → existing `auto_speaker` blackbox and original PCM/classifier defaults;
- exact multi marker → `auto_multi_speaker` adapter, multi-only filtered PCM, and a multi-only classifier profile.

The adapter delegates once to the existing Auto blackbox and protected lane runner. It may inject only the multi classifier and extractor dependencies. It must not copy the existing assignment, per-cue TTS, mux, delivery, or settlement implementation.

## Detection contract

- Deepgram batch `diarize_model=latest` remains the single approved ASR/diarization call.
- The multi lane accepts 2–16 canonical Deepgram speaker labels and preserves every returned label independently.
- It never invents extra speakers when Deepgram returns fewer labels.
- Multi acoustic classification may use the PR #853 band-pass/denoise and one-frame evidence profile, but the two-speaker default retains its pre-PR #853 behavior.
- Ambiguous, noisy, conflicting, insufficient, timed-out, or resource-overflow evidence remains fail-closed before TTS/provider voice synthesis and before charge.

## UI and state

Add one compact voice choice for the multi profile. Selecting it sets the existing Auto state pair plus `auto_speaker_lane="multi"`. Selecting existing Auto or any manual voice clears the marker. No other text, layout, subtitle lane, or confirmation step changes.

## Verification

RED/GREEN tests must prove:

1. Existing Auto state without the marker dispatches only the old blackbox and uses original PCM/classifier defaults.
2. The marker dispatches only the new blackbox and uses the filtered multi profile.
3. Manual/default/subtitle lanes never enter either new branch.
4. Pricing and Owner/Admin zero-Xu behavior are identical between Auto profiles.
5. Two-speaker protected comparators and rollback-anchor behavior remain green.
6. A 3+ speaker synthetic sidecar preserves every speaker and assigns distinct voices while capacity allows.
7. The existing `Download.mp4` artifact classifies its two provider-returned IDs without fallback; a live job must deliver one MP4 + SRT + one green receipt and charge Owner 0 Xu.

## Rollback

If the multi branch changes the old two-speaker command, state, mapping, or protected comparators, stop and revert the multi PR. Runtime rollback target is PR #844/SHA `0c5e0dc9b0b11bb864124fa44403c7c049a06904`; never reset/clean production data or untracked runtime files.
