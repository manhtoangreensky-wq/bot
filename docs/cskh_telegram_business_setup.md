# Telegram Business CSKH Runtime Guide

Telegram Business manual setup is already done for:

- Connected bot: `AAS ONE / @toanaasbot`
- Access mode: `Only Selected Chats`
- Initial test scope: one selected non-admin customer chat

## Verify runtime

1. Send one simple message from a selected customer chat.
2. In the bot, admin runs `/cskh_business_status`.
3. Confirm:
   - `Receiving business updates: yes`
   - `Receiving business messages: yes`
   - `Allowed updates include business: yes`
   - latest connection id is masked
4. Run `/cskh_test <message>` to inspect the classifier without sending to a customer.
5. Run `/cskh_on` only after the status proves updates are arriving.

## Live test

Start with one selected chat only. Keep Telegram Business access on `Only Selected Chats` until duplicate, cooldown, and handoff behavior are verified.

Do not switch to all private chats until:

- `/cskh_business_status` shows business messages are being received.
- `/cskh_test` classifies payment/refund/error messages as handoff.
- One live auto-reply is sent with a selected chat.
- Repeated messages are suppressed by cooldown.
- `/cskh_handoff_on <chat_id>` stops auto-replies for that customer.

## Commands

- `/cskh_business_status` checks connection/update/runtime state.
- `/cskh_test <message>` classifies safely without sending.
- `/cskh_on` enables guarded rules-only auto-reply.
- `/cskh_off` disables auto-reply while still recording receipt status.
- `/cskh_handoff_on <chat_id>` pauses auto-reply for one customer chat.
- `/cskh_handoff_off <chat_id>` resumes auto-reply for one customer chat.

Server code cannot connect the bot to a Telegram Business account by itself. That link must be managed in Telegram Business settings. Never expose the bot token.
