# P0.CSKH.CONTINUITY Design

## Status and authority

The owner-approved master task `P0_CSKH_CONTINUITY_UNIFIED_MASTER_CODEX_TASK.md` is the source of truth. This design records the bot-only implementation of that approved scope. No standalone web app, provider route, paid engine, worker, payment, wallet/Xu write, pricing write, or webhook ownership changes are allowed.

## Discovery result

- Base: `origin/main` at `61f17108b9482fa1f6fef0e1e12bf8d7f647bfb4`.
- Branch: `fix/p0-cskh-continuity-unified`, clean at discovery close.
- Existing bot text dispatch preserves all pending product-state handlers, then currently falls through to support persona, AIChat, and generic paid/provider-backed chat. The covered CSKH reply route must run after valid pending states but before those fallbacks.
- Existing resolver is reusable: `services/telegram_business_support.py` delegates to `services/aas_shared_knowledge.py`; AIChat reuses that resolver.
- Existing CSKH and AIChat memories are separate JSON state. They do not provide owner-isolated cross-surface turns, a 48-hour session boundary, 30-day retention, or persistent cross-surface deduplication.
- Live price sources are the read-only pricing/menu helpers in `bot.py`: canonical price settings, image/video tier payloads, music tier maps, the Xu conversion source, and the active Product Video scene-duration value. The old CSKH documents and static constants are reference material only and must never be the production reply price source.
- SQLite convention is `init_db()` plus `CREATE TABLE IF NOT EXISTS` and explicit indexes, using `db_connect()` and `system_settings` helpers. Exactly one table, `conversation_turns`, is authorized.
- No open CSKH/AIChat PR conflicts were found. The only open PRs are unrelated SubDub/Music work.

## Architecture

1. `services/aas_shared_knowledge.py` remains the one deterministic human-touch reply facade. It will use the existing intent matcher and human-touch playbook, add direct caption/script drafting and history-aware follow-ups, and accept an explicit runtime pricing snapshot. With no explicit snapshot it must use an honest unknown-price reply; it must never present documentation values as live prices.
2. `services/cskh_session_memory.py` is the one small storage service. It owns sanitization, owner-scoped session selection, bounded retrieval, duplicate turn keys, retention deletion, and closing-notice eligibility. It has no Telegram, provider, wallet, or `bot.py` imports.
3. `bot.py` supplies the read-only runtime price snapshot and owns SQLite connections, settings access, private-chat reply persistence, Business callback injection, and the one-time inactivity notice scheduler. The scheduler sends no paid/media action, checks that no newer customer turn exists, and persists the notice only after a successful send.
4. `services/ai_chatbot_copilot.py` and `services/telegram_business_support.py` accept explicit `conversation_memory` and `runtime_facts` from `bot.py`; their legacy JSON state remains compatibility/trace state, not the authoritative continuity store.

## Session and customer notice policy

- Session window: `48` hours by default (`cskh_session_window_hours`). A gap greater than the configured window starts a new session; a timestamp cutoff alone never mixes sessions.
- Raw turn retention: `30` days by default (`cskh_turn_retention_days`). Purge is indexed, bounded, idempotent, and at most once per configured cadence.
- Context budget: configurable recent-turn count and character budget; preserve newest turn boundaries and only permitted customer-facing context.
- After five minutes with no newer customer message, send at most one closing note per active session. Default Vietnamese copy is plain language: `Dạ em tạm chốt phần hỗ trợ tại đây nhé. Nội dung mình trao đổi được giữ trong 48 giờ để em nối tiếp khi anh/chị nhắn lại. Qua thời gian đó, nếu hỏi lại việc cũ hoặc có việc mới, anh/chị nhắc ngắn nội dung giúp em để em hỗ trợ đúng hơn ạ.`
- A closing note is never sent after opt-out, never sent twice for the same session, never sends provider/media/payment actions, and is only tested with fake Telegram transports.

## Data and safety model

`conversation_turns` stores only: the owner Telegram id, chat id, session id, surface (`bot_menu`, `cskh`, `aichat`), role (`user`, `assistant`, `context_event`), sanitized customer-facing content, a safe source-message key, content hash/redaction marker, and creation time. It stores no secrets, provider IDs, callback data, file paths, raw API payloads, wallet internals, or hidden prompts.

Every read, existence check, write, retention operation, and closing-notice check includes the owner id. Recent history is marked untrusted before it is supplied to any response assembly. It is context only: it cannot create a job, confirm an invoice, call a provider, submit a worker, change a wallet, refund Xu, or execute a callback.

## Reply policy

- Vietnamese replies use `em – anh/chị`; an answer comes first, with no more than one necessary follow-up question.
- Complaint replies begin with an apology, identify the customer’s issue, request the narrowest needed evidence, and promise neither refund/Xu/voucher/VIP nor completion without a verified result.
- Prompt, caption, and script requests produce an immediately usable draft without provider calls.
- Unsafe phrases, credentials, provider/API/debug names, private paths, unverified completion claims, and unsafe promises are blocked or replaced before public sending.

## Verification strategy

Each master subtask has its own RED → GREEN test gate and commit. The final gate runs focused CSKH/AIChat tests, bot/menu routing tests, DB/settings/action-guard tests, compile/static checks, secret/private-path scans, and the exact same collected test command on this branch and a clean `origin/main` worktree. No deploy, merge, provider call, paid action, job, wallet mutation, or real Telegram send is permitted.
