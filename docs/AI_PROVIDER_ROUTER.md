# AI Provider Router - TOAN AAS

## Purpose

The router chooses an AI provider for normal/pro/deep chat without exposing keys or forcing a provider that is not configured.

## Current MVP Rules

| Tier | Requested model | Provider rule |
|---|---|---|
| Normal | auto | Gemini if configured, otherwise OpenAI. |
| Pro | auto | Gemini if configured, otherwise OpenAI. |
| Pro | gemini/gemini_pro | Gemini only; no charge if missing. |
| Pro | openai/gpt_pro | OpenAI only; no charge if missing. |
| Deep | auto | Gemini if configured, otherwise OpenAI. |
| Deep | sonnet/opus/claude | Planned only; no charge. |
| Deep | grok | Planned only; no charge. |

## Configured Providers

- Gemini: uses existing `GEMINI_API_KEY`.
- OpenAI: uses existing `OPENAI_API_KEY`.
- Claude: planned, no active client in Step 11.
- Grok: planned, no active client in Step 11.

## Fallback Rules

- Normal `AgentGemini.chat` remains Gemini first, OpenAI fallback.
- `/chat_pro model=auto` uses Gemini first, OpenAI second.
- `/chat_pro model=openai` does not silently switch to Gemini.
- Planned providers return a clear setup message and do not charge Xu.

## Security

- `/providers` shows configured/missing/planned only.
- No key prefix, suffix, checksum, token, or raw secret is printed.
- Provider errors must not log prompt content or secrets.
