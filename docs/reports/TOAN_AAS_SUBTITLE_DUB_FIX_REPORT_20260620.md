# TOAN AAS Subtitle Dub Fix Report

Date: 2026-06-20

## Scope

Provider readiness for subtitle/dubbing pipeline only.

## Done

- Key4U STT/TTS commands exist as admin smoke commands.
- Unknown Key4U STT/TTS endpoints return `NEED_DOCS` safely.
- No public subtitle/dub route is opened by this change.

## Pipeline Gate

Public subtitle/dubbing still requires:

1. ASR provider pass.
2. Translation provider pass.
3. TTS provider pass.
4. Local worker or provider mux/burn step pass.
5. Final confirm and billing guard.

## Not Touched

- Existing video public pricing.
- Video 200/300/400 open policy.
- PayOS/top-up.
