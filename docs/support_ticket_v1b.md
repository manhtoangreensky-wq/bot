# TOAN AAS Operations V1B - Support Ticket Runbook

## Scope

Operations V1B adds a manual-review support system for payment/top-up issues, image/video errors, documents, packages, refund requests, product feedback and consulting leads.

The support flow does not automatically refund Xu, modify payments, call provider APIs or send AI-written replies without admin confirmation.

## Public Flow

Users enter from `Support`, `Feedback / Bug`, `/support`, `/tickets` or `/ticket_status`.

1. Select a support category.
2. Send a description.
3. Receive a unique ticket code.
4. Optionally attach one screenshot or document.
5. View only tickets owned by the same Telegram user ID.

Public ticket detail never exposes `admin_note` or assignment metadata.

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
