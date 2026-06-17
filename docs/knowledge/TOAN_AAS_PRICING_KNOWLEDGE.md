# TOAN AAS Pricing Knowledge

Last updated: 2026-06-20

## Runtime Rule

This document is knowledge/backlog. Runtime pricing remains in bot configuration/code until explicitly migrated. Do not import this document as code.

## Xu Conversion

- 1 Xu = 100 VND.
- User is charged only after the final confirmation step.
- Provider failure before valid output must not leave the user charged incorrectly.

## Video Pricing Current Policy

| Tier | Price | Role | Notes |
| --- | ---: | --- | --- |
| Video Trải Nghiệm | 200 Xu | marketing starter | Intentional low/mồi product; 3 uses/day per account. |
| Video Cơ Bản | 300 Xu | starter paid tier | Public beta when provider gate passes. |
| Video Phổ Thông | 400 Xu | normal public tier | Public beta when provider gate passes. |
| Video Nâng Cao | 500 Xu | higher tier | Open only after smoke/cost gate. |
| Video Bán Hàng | 600 Xu | main revenue tier | Open only after smoke/cost gate. |
| Video Cao Cấp | 800 Xu | high tier | Open only after smoke/cost gate. |
| Future premium | 1000/1500 Xu | future provider tiers | Keep OFF until cost verified. |

## Provider Cost Rule

- Do not open a public provider path without cost data or explicit marketing-loss policy.
- Key4U costs are not finalized from code alone; use admin smoke + dashboard/usage before public routing.
- WokuShop remains parked due higher cost.

## Image Pricing Current Policy

- Low/test image: 50 Xu.
- Standard image: 200 Xu.
- Standard + warranty: 250 Xu.
- High image: 400 Xu.
- High + warranty: 500 Xu.

Warranty means one guarded retry in the same job/context only.
