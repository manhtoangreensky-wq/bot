# Backup And Recovery

## Goal

If the server crashes or a redeploy loses data, TOAN AAS should recover user credits, PayOS orders, manual bill approvals, affiliate links, and operator work quickly.

## Short Term

- Identify the actual SQLite DB path.
- Back up the SQLite file daily.
- Store backup outside Railway runtime storage, for example Google Drive/S3 when a connector is approved.
- Keep at least 7 recent backups.
- Back up before large deploys or schema changes.

## Medium Term

- Move to managed PostgreSQL.
- Enable automated backups.
- Use point-in-time restore if the provider supports it.
- Export critical tables on a schedule:
  - `users`
  - `payos_orders`
  - `payos_processed`
  - `credit_events`
  - `pending_deposits`
  - `transactions`
  - `affiliate_links`
  - `performance_events`

## Recovery Checklist

1. Stop service.
2. Restore DB.
3. Start service.
4. Check `/health`.
5. Check `/runtime`.
6. Check `/dashboard`.
7. Verify recent PayOS orders.
8. Verify user credits.
9. Verify manual bills pending/approved.
10. Notify admin with recovery summary.

## Do Not Implement Yet

Do not implement automatic backup in this task. This file is a plan until the storage target and credentials are approved.
