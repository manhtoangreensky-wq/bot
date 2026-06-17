# TOAN AAS Provider Admin Dashboard Report

Date: 2026-06-20

## Provider Dashboard Goals

Admin must be able to see provider readiness without remembering scattered commands.

## Current Provider Rows

| Provider | Role | Public | Admin smoke | Notes |
| --- | --- | --- | --- | --- |
| ShopAIKey | primary production route | controlled by existing flags | yes | Existing live pass provider. |
| Key4U | parallel hub/backup candidate | OFF | yes | Added usage/status/smoke dashboard. |
| WokuShop | parked | OFF | OFF | Parked due higher cost. |

## Added Admin Visibility

- `/providers` includes Key4U role, usage/balance summary, and command hints.
- `/provider_matrix` shows primary provider, parallel mode, fallback mode, and parked providers.
- `/key4u_status` is the detailed Key4U provider card.
- `/key4u_usage` is the detailed usage/balance card.
- `docs/COMMAND_REGISTRY.md` now lists Key4U status/usage/smoke commands.

## Safety Notes

- Public routing remains closed.
- Fallback remains explicit/admin-controlled.
- Provider commands do not expose secrets.
- WokuShop is visible as parked, not callable.
