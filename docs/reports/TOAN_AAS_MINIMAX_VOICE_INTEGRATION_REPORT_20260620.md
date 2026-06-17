# TOAN AAS MiniMax Voice Integration Report - 2026-06-20

## Current State

MiniMax Voice has standardized readiness and admin commands, but direct provider execution remains guarded until verified endpoint/model docs are configured.

Required env:

- `MINIMAX_API_KEY`
- `MINIMAX_GROUP_ID`
- `MINIMAX_TTS_ENDPOINT`
- `MINIMAX_TTS_MODEL`
- `MINIMAX_VOICE_CLONE_ENDPOINT` for voice clone

## Commands

- `/minimax_status`
- `/tool_test_minimax_tts`
- `/tool_test_minimax_voice_clone`
- `/minimax_voice_job <task_id>`
- `/voice_public_open`
- `/voice_public_close`

## Consent

Voice clone/profile is user-scoped and requires explicit consent. The `voice_profiles` table stores provider voice id, consent status, source file id, status and timestamps.

## Public Gate

MiniMax public voice remains OFF by default. It can only open after readiness and smoke PASS.
