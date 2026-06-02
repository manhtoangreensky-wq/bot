# CHAT AI AUDIT - TOAN AAS

Date: 2026-06-02
Scope: Phase 1 Step 11, Chat AI Tier System.

## Compile

- `py_compile`: PASS before implementation.
- `py_compile`: PASS after implementation.

## Current chat flow

| Item | Current state |
|---|---|
| Handler | `handle_message` handles plain text messages after URL/voice routing. |
| Default provider | `AgentGemini.chat`, Gemini first when configured. |
| Fallback | OpenAI fallback through existing `OPENAI_API_KEY` client. |
| Free daily | Trial accounts use `FREE_CHAT_DAILY = 20`. |
| Charge logic | Trial chat uses free daily count; deposited normal chat keeps existing dynamic cost path. |
| Refund | Paid normal chat refunds with `chat_refund` if AI call raises. |

## Current providers

| Provider | Env | Client exists? | Used? |
|---|---|---:|---:|
| Gemini | `GEMINI_API_KEY` | YES when configured | YES, primary. |
| OpenAI | `OPENAI_API_KEY` | YES when configured | YES, fallback and router option. |
| Claude | Not active in code | NO | Planned only. |
| Grok | Not active in code | NO | Planned only. |

## Current risks

1. Normal chat still uses current legacy billing for deposited users; Step 11 avoids changing this path to protect existing billing.
2. Gemini/OpenAI calls are synchronous in current bot style; heavy prompts can still consume provider quota.
3. Claude/Grok should not be advertised as active until a real client and key policy are added.

## Recommendation

- Normal chat: keep fast/fair-use UX and avoid token wording for customers.
- Pro chat: use explicit `/chat_pro` with upfront Xu price and refund on provider failure.
- Router: support Gemini/OpenAI now, keep Claude/Grok as planned until provider setup is done.
