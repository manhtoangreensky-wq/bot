# TOAN AAS Key4U Parallel Provider Report

Date: 2026-06-20

## Decision

Key4U is added as a parallel provider hub and backup candidate. It is not enabled as default public traffic.

## Router Mode

- `PROVIDER_PRIMARY=shopaikey`
- `PROVIDER_PARALLEL_ENABLED=true`
- `PROVIDER_FALLBACK_ENABLED=false`
- `PROVIDER_FALLBACK_ORDER=shopaikey,key4u`

This means TOAN AAS can inspect and smoke-test Key4U without silently moving customer jobs away from stable ShopAIKey routes.

## One-Key Smart Routing

Key4U uses one API key and configurable endpoints. Optional capabilities return safe `NEED_DOCS` if the endpoint is not configured, rather than guessing undocumented routes.

## Public Launch Gate

Key4U can only serve public traffic after:

1. Admin smoke passes for the exact capability.
2. Provider cost is known.
3. Refund/job lock behavior is verified.
4. Public flag is explicitly enabled.

## Not Changed

- PayOS/top-up/payment logic.
- ShopAIKey live routes.
- Video pricing and 200 Xu marketing starter limits.
- WokuShop parked status.
