# TOAN AAS Operations V1B - Support Ticket Runbook

## Scope

Operations V1B adds a manual-review support system for payment/top-up issues, image/video errors, documents, packages, refund requests, product feedback and consulting leads.

The support flow does not automatically refund Xu, modify payments, call provider APIs or send AI-written replies without admin confirmation.

## Public Flow

Public UX is intentionally split:

- `Feedback / Bug report` is the structured ticket path for payment, image,
  video, document, package, refund and product feedback issues.
- `Support` and `/support` open human contact, Premium registration, custom bot
  consulting and service-package advice. The `@toanaas` button is only a link;
  the bot never sends from a personal Telegram account.

1. Select a support category.
2. Send a description.
3. Receive a unique ticket code.
4. Optionally attach one screenshot or document.
5. View only tickets owned by the same Telegram user ID.

Public ticket detail never exposes `admin_note` or assignment metadata.
Repeated messages from the same user and category within 30 minutes are
appended to the existing open ticket instead of creating ticket spam.

Premium and custom-bot requests use `premium_lead` and `custom_bot_lead`,
receive high priority, and alert admins. General human-support tickets use
`general_support`; sensitive payment/refund/error wording is reclassified to
the appropriate operational category.

## CSKH Persona

The deterministic persona layer provides short, warm replies without promising
refunds or delivery times. Rule-based classification runs first. An optional AI
classifier can be enabled for unmatched messages, but rule fallback remains the
source of truth if the provider fails.

Admin can preview classification and wording with:

```text
/support_persona_test <customer message>
```

This command does not create a ticket, send an alert, call refund logic, or
change Xu.

## Admin Flow

Open `Admin -> CSKH / Ticket` or use `/ticket_admin`.

Admin can:

- View new, high-priority and refund-pending tickets.
- Search by ticket code, user ID, username or message keyword.
- Assign a ticket and update operational status.
- Add an internal note.
- Generate a deterministic reply template.
- Preview and explicitly confirm a reply before it is sent.
- Mark a ticket `refund_pending` without changing Xu.
- Check overdue tickets with `/ticket_overdue`.

## Data Safety

Tables are additive:

- `support_tickets`
- `support_ticket_messages`

Migrations add missing columns and indexes only. They do not drop tables, reset balances or remove payment/job history.

Attachments store Telegram `file_id` metadata only. API keys, tokens and raw provider responses are not stored.
