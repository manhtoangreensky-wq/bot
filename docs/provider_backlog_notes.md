# TOAN AAS Provider Backlog Notes

This file records provider status and backlog decisions so they do not need to live in chat memory.

## Current ShopAIKey Status

- ShopAIKey balance still has remaining credit based on the latest admin usage checks.
- Chat smoke test: PASS with configured admin-only models.
- TTS smoke test: PASS with `tts-1`/voice smoke flow.
- Image smoke test: PASS with the custom Google image endpoint and `nano-banana`.
- Video submit can work, but VEO/Grok video availability is provider/group dependent and may return no-channel or provider-busy states.
- Public video must continue to rely on billing guard, refund guard, job lock, freeze guard, and terminal-status handling.

## Current Runtime Policy

- Public image/video flags are controlled by ENV.
- Admin smoke tests do not deduct Xu, but provider credits may still be consumed.
- Do not log API keys, full prompts, raw provider responses, or sensitive output URLs.
- Failed terminal video jobs must not promise automatic delivery; they should show retry/choose-tier/contact-admin actions.

## Backlog Only

These items are not implemented in this hotfix:

- Central provider router/orchestrator expansion beyond the existing safe status layer.
- Public Suno/music generation.
- Public voice/TTS productization beyond current admin/status tests.
- Multi-provider redundancy with Key4U/WokuShop/fallback routing.
- More advanced video-provider model selection for customers.

Build these only in a separate task after the current paid image/video/package flows remain stable.
