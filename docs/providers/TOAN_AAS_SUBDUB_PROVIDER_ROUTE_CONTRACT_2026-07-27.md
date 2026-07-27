# TOAN AAS SubDub Provider Route Contract

**Checked:** 2026-07-27 (Asia/Saigon)
**Scope:** provider route, readiness, ASR/TTS response truth, and four-lane MP4 prerequisites only.
**Hard lock:** no UI/UX, menus, callbacks, subtitle renderer/style, MP4 engine, FFmpeg service, worker implementation, Product Video, Music/Suno runtime, wallet/Xu, PayOS, database schema, Railway variables, or Telegram webhook changes.

## Operational Rule

This document is the durable reference for the four SubDub lanes:

1. Create subtitle from audio
2. Translate subtitle
3. Dub
4. Subtitle plus dub

Each lane must select one explicit ASR/TTS/translation route. Documentation, a configured key, a HTTP 200, or an old smoke record never proves that an MP4 is ready. A real public lane needs all of the following:

```text
documented contract
-> configured exact provider
-> current-runtime smoke pass
-> existing lane gate allowed
-> existing pipeline produces a validated artifact
-> Telegram delivers the artifact
```

No automatic paid fallback is allowed between Key4U, ShopAIKey, Deepgram, DeepL, or MiniMax. `auto` is not an executable paid-provider selection for SubDub.

## Live Source Scan

Official sources read during this audit:

- [Key4U documentation](https://docs.key4u.vn/)
- [Key4U model URL](https://key4u.shop/models)
- [ShopAIKey introduction](https://shopaikey.com/docs/introduction)
- [ShopAIKey model catalog](https://shopaikey.com/models)
- [ShopAIKey API reference](https://shopaikey.com/api-docs)
- [ShopAIKey OpenAI-compatible API](https://shopaikey.com/docs/openai-format)
- [ShopAIKey TTS API](https://shopaikey.com/docs/tts)

The current Key4U docs index exposes the relevant OpenAI and MiniMax routes. On this date, `key4u.shop/models` returned a ParkLogic parking redirect, so it is not a trustworthy live catalog. The owner-only, read-only canonical model check is `GET https://api.key4u.shop/v1/models` with the active key; do not run it from a customer flow.

ShopAIKey's public model page listed current MiniMax TTS model families including `speech-01-*`, `speech-02-*`, `speech-2.6-*`, and `speech-2.8-*`. The configured key/group still decides which models are actually callable.

One unauthenticated `GET https://api.shopaikey.com/tts/minimax/voices` was made during the documentation audit before this contract was supplied. It used no secret, did not generate media, did not submit Telegram media, and did not mutate wallet/Xu. No paid provider call was made.

## Canonical Provider Matrix

| Provider | Capability | Base URL | Endpoint | Model | Response contract |
| --- | --- | --- | --- | --- | --- |
| Key4U | ASR | `https://api.key4u.shop/v1` | `POST /audio/transcriptions` | `whisper-1` or `gpt-4o-transcribe` | transcript must be non-empty; segment/cue generation must succeed |
| Key4U | OpenAI TTS | `https://api.key4u.shop/v1` | `POST /audio/speech` | configured OpenAI TTS model | binary audio, bytes must be non-zero |
| Key4U | MiniMax sync TTS | `https://api.key4u.shop/minimax/v1` | `POST /t2a_v2` | `speech-02-hd` example | hex audio or URL; decoded/downloaded bytes must be non-zero |
| Key4U | MiniMax async TTS | `https://api.key4u.shop/minimax/v1` | `POST /t2a_async_v2` | configured MiniMax model | submit requires `task_id`; final retrieve requires file/download artifact |
| ShopAIKey | ASR | `https://api.shopaikey.com/v1` | `POST /audio/transcriptions` | `whisper-1` example | transcript must be non-empty; segment/cue generation must succeed |
| ShopAIKey | OpenAI-compatible TTS | `https://api.shopaikey.com/v1` | `POST /audio/speech` | `tts-1` example | binary audio, bytes must be non-zero |
| ShopAIKey | Custom OpenAI TTS | `https://api.shopaikey.com` | `POST /tts/openai/speech` | `tts-1` | JSON URL; downloaded audio bytes must be non-zero |
| ShopAIKey | MiniMax sync TTS | `https://api.shopaikey.com` | `POST /tts/minimax/t2a_v2` | `speech-02-hd` example | `data.audio` hex or validated URL |
| ShopAIKey | MiniMax async TTS | `https://api.shopaikey.com` | `/tts/minimax/t2a_async_v2`, query, retrieve | configured MiniMax model | submit requires `task_id`, terminal query success and valid file artifact |
| Deepgram | ASR | existing adapter config | existing adapter route | configured model | existing transcript/segment contract |
| DeepL | text translation | existing adapter config | existing adapter route | configured model | translated text only; source cue timestamps remain unchanged |

### Forbidden URL Shapes

```text
https://api.key4u.shop/v1/minimax/v1/...
https://api.key4u.shop/v1/tts/minimax/...
https://api.key4u.shop/minimax/v1/v1/...
https://api.shopaikey.com/v1/tts/minimax/...
https://api.shopaikey.com/v1/tts/openai/speech
https://api.shopaikey.com/v1/v1/audio/transcriptions
```

## Voice Contract

MiniMax voice IDs are provider-owned opaque identifiers. They may use letters, digits, `_`, `-`, or `.`. Never rewrite `_` to `-` before sending it.

The ShopAIKey public MiniMax catalog returned 18 current Vietnamese voice IDs. It contained `Vietnamese_Cute_Girl_v1`, `Vietnamese_Male_Narrator_v1`, and other underscore-containing values. It did **not** contain either `female-shaonv` or `male-qn-qingse`.

Rules:

1. Never use `female-shaonv` or `male-qn-qingse` as universal defaults.
2. A ShopAIKey MiniMax request uses only an explicitly configured ShopAIKey default or an explicit catalog-compatible selected ID.
3. A Key4U MiniMax ID may include `_`; Key4U documentation itself shows a `moss_audio_...` example.
4. OpenAI-compatible TTS uses its own known voice set (`alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`), not a MiniMax voice ID.
5. If the catalog is unavailable, do not silently substitute a legacy voice. Return a truthful internal classification such as `voice_catalog_unavailable` or `voice_not_supported`; keep public copy clean.

## Key4U Translation Rule

Key4U documentation labels `POST /v1/audio/translations` as "Create translation (not supported)". SubDub must not use this audio-translation route for subtitle translation. Its text-translation path remains the existing explicit translation provider (for example DeepL); changing subtitle timestamps is forbidden.

## Four-Lane Provider Prerequisites

| Lane | Required capability when source cues are absent | Additional required capability | Existing output truth |
| --- | --- | --- | --- |
| Create subtitle | explicit ASR | FFmpeg/ffprobe/subtitle runtime | valid timed subtitle artifact or validated MP4 per existing lane contract |
| Translate subtitle | explicit ASR | explicit text translation | translated text must preserve original cue timings |
| Dub | explicit ASR unless canonical cues already exist | explicit TTS; translation only when requested | non-empty audio plus validated muxed MP4, never fake success |
| Subtitle plus dub | explicit ASR unless canonical cues already exist | explicit text translation and TTS | one validated MP4 containing the canonical translated subtitle and dub |

If `ASR_PROVIDER=auto` or `TTS_PROVIDER=auto`, the current SubDub code intentionally has no exact paid-provider route. It must remain blocked until an owner selects an explicit provider. This avoids an unapproved paid fallback, but it means `auto` cannot produce a real MP4.

The intended Railway configuration **after** owner smoke is one exact choice per capability, for example:

```text
ASR_PROVIDER=shopaikey | key4u | deepgram
TTS_PROVIDER=shopaikey_minimax | key4u_minimax | direct_minimax
TRANSLATE_PROVIDER=deepl | existing approved explicit provider
```

Do not set these values, open public flags, or remove provider freeze from documentation alone.

## Current Code Audit Before Patch

| Finding | Location | Status |
| --- | --- | --- |
| Key4U base split | `bot.py:591-617` | Correct defaults: OpenAI `/v1`; MiniMax `/minimax` plus `/v1/...` endpoint |
| ShopAIKey base split | `bot.py:564-566`, `bot.py:905-917` | Correct separate OpenAI `/v1` and custom media root defaults |
| ShopAIKey configured test uses generic MiniMax variables | `bot.py:60509-60510` | Mismatch: it should use `SHOPAIKEY_TTS_BASE_URL`, `SHOPAIKEY_TTS_ENDPOINT`, and `SHOPAIKEY_TTS_MODEL` |
| ShopAIKey MiniMax submit uses generic endpoint | `bot.py:61737-61747` | Mismatch: it should use `SHOPAIKEY_TTS_ENDPOINT` |
| MiniMax adapter destroys underscores | `services/minimax_voice_adapter.py:82-98` | Mismatch: `_` becomes `-`, invalidating live ShopAIKey catalog IDs |
| Generic default voice flows into provider-independent resolver | `bot.py:137551-137652` | Mismatch for ShopAIKey: legacy direct-MiniMax defaults can be sent to its catalog |
| ASR route selection | `bot.py:62166-62382` | `auto` has no provider order; explicit provider configuration is required, not an automatic paid fallback |
| TTS route selection | `bot.py:204213-204220`, `bot.py:211380-211497` | `auto` is blocked by provider policy; explicit TTS provider required |
| Exact-runtime smoke binding | `bot.py:204162-204207` | Correct: a PASS smoke without matching runtime SHA becomes `STALE` |
| Key4U audio translation | references only at `bot.py:618` | Not used by SubDub text translation route; keep it unused |

## Readiness State Model

Keep these meanings separate:

```text
documented      = official docs show a route
configured      = exact environment values exist
catalog_loaded  = provider-specific voice/catalog data was obtained safely
smoke_pass      = owner ran an approved probe on current runtime SHA
public_allowed  = existing public flags and exact smoke gates permit it
live_mp4_pass   = a real artifact passed validation and Telegram delivery
```

`configured` never implies `smoke_pass`; `smoke_pass` never implies `live_mp4_pass`.

## Applied Route Fix

The following provider-only corrections are applied in this worktree:

1. ShopAIKey MiniMax configuration, request submit, and route audit all use `SHOPAIKEY_TTS_BASE_URL`, `SHOPAIKEY_TTS_ENDPOINT`, and `SHOPAIKEY_TTS_MODEL`. They do not borrow generic `MINIMAX_*` values.
2. A selected `shopaikey_minimax` route never falls back to Direct MiniMax. Missing ShopAIKey configuration returns `MISSING` truthfully and cannot create an unapproved provider call.
3. ShopAIKey MiniMax legacy defaults are mapped only inside the ShopAIKey adapter to an explicit ShopAIKey default. Explicit catalog voice IDs, including underscore IDs such as `Vietnamese_Cute_Girl_v1`, are preserved unchanged.
4. The shared MiniMax voice validator and Key4U clone input accept provider-owned `_`, `-`, and `.` characters without rewriting `_`.
5. No ASR/TTS `auto` fallback loop was added. Owner configuration must make a deliberate, explicit provider selection before a live SubDub lane can produce a real MP4.

## Verification Snapshot

**Completed offline, with no provider network call:**

- `tests/test_p0_subdub_providerroute23_contract.py`: PASS. It checks exact Key4U/ShopAIKey URLs, no `/v1/tts/minimax` shape, underscore voice preservation, ShopAIKey-only endpoint/model use, no ShopAIKey-to-Direct-MiniMax fallback, and the correct audit route.
- `py_compile services/subdub_provider_contract.py services/minimax_voice_adapter.py providers/key4u_provider.py`: PASS.
- `git diff --check`: PASS.
- Provider generation calls, real media submits, Telegram delivery, wallet mutations, and Xu charges: `0`.

**Not claimed:**

- Full `bot.py` parse/compile was attempted once and timed out after 360 seconds in this workspace while parsing the very large source file. It is not marked PASS.
- No Railway configuration, deploy, runtime smoke, Telegram delivery, or real four-lane MP4 result occurred in this task. Therefore `live_mp4_pass` remains unproven until the owner chooses explicit providers, deploys, runs approved smokes, and performs real admin MP4 validation.

## Public Opening Procedure

This task does not open public flags. Public opening is a post-deploy owner operation only:

1. Deploy the code change and verify the exact runtime SHA.
2. Choose explicit `ASR_PROVIDER`, `TTS_PROVIDER`, and translation provider in Railway.
3. Run one owner-approved smoke for the chosen ASR provider.
4. Run one owner-approved smoke for the chosen text translation provider.
5. Run one owner-approved TTS smoke using a provider-compatible voice ID.
6. Verify smoke records carry the deployed runtime SHA.
7. Run one real admin MP4 each for subtitle, translation, dub, and combo.
8. Confirm artifact validation, one Telegram delivery, terminal panel, and receipt are correct.
9. Only then set the already-existing public flags for the four lanes.

No live test, public opening, Railway variable update, or paid provider generation is performed by this provider-route task.

## Future Task Guardrails

- Do not touch UI/UX, callbacks, menus, copy, or subtitle renderer/style while working this contract.
- Do not modify `services/dubbing_pipeline.py`, `services/subtitle_dub_pipeline.py`, or `services/subtitle_dub_product_pipeline.py` in this task.
- Do not add a provider fallback loop for `auto`.
- Do not treat 200 with empty transcript/audio or missing task/file ID as success.
- Do not leak provider name, URL, endpoint, model, voice ID, task ID, file ID, or raw provider response to public users.
- Do not open public lanes merely because this document or a model list says a capability exists.

## Required Offline Checks

```text
Key4U ASR/OpenAI TTS/MiniMax sync+async URLs are exact.
ShopAIKey ASR/OpenAI/custom TTS/MiniMax URLs are exact.
No duplicate /v1 and no /v1/tts/minimax route.
MiniMax IDs with underscores validate and transmit unchanged.
No provider fallback occurs from `auto`.
200 with empty transcript/audio is failure.
Async without task ID/file ID is failure.
Current-runtime smoke is required before public readiness.
No provider calls, media submissions, wallet mutations, or Xu charge occur in tests.
```
