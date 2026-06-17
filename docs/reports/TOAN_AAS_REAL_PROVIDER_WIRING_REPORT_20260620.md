# TOAN AAS Real Provider Wiring Report

Date: 2026-06-20

## Scope

Wire real provider paths where safe and add guarded provider status where provider documentation is missing.

## Done

- Key4U provider wrapper supports chat, vision, image edit, video create/query, usage/balance, and safe optional capability stubs.
- Image edit readiness now considers Key4U as a real provider candidate.
- Chat/vision readiness can report Key4U when configured.
- Subtitle/dub/music optional Key4U paths are guarded as `NEED_DOCS` until endpoints are confirmed.
- CSKH/assistant status commands can show readiness without pretending provider output exists.

## Not Done By Design

- No guessed endpoint calls for unknown TTS/STT/Suno/Rerank.
- No public Key4U routing.
- No WokuShop integration.
- No PayOS/top-up changes.

## Launch Rule

Every public capability still needs smoke, cost, refund, and job-lock verification before opening.
