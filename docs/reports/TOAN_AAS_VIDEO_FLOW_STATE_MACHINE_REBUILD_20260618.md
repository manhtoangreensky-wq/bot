# TOAN AAS Video Flow State Machine Rebuild

Date: 2026-06-18

## Scope

- Added a shared video session with `current_screen`, `screen_stack`, `draft`, and `order`.
- Kept existing video planning, provider, pricing, billing, refund, and job execution behavior.
- Connected the video finalization and paid add-on screens to explicit screen state.
- Changed Back actions to pop exactly one screen instead of opening a hard-coded menu.
- Added an upload-first entry gate for Self-shot Scene AI while retaining a plan-first path.
- Added the existing Voice/Music/SFX hub to the Video menu with a Video-specific Back route.

## Finalization Flow

The guarded paid path remains:

`prompt/plan -> finalization -> tier -> add-ons -> itemized invoice -> final confirm -> job`

No provider call or Xu deduction is performed by opening menus, selecting suggestions, changing a tier, or navigating Back.

## Back Routing

- Add-on menu -> tier/detail
- Language -> add-on menu
- Voice -> language or add-on menu, depending on entry path
- Invoice -> the exact prior selection screen
- Video music hub -> Video menu
- Self-shot direction -> source-video gate

The invoice is now a real screen in `video_order.screen_stack`; it is not treated as a terminal text-only message.

## Regression Coverage

- Shared session push/pop preserves draft and order.
- Add-on state synchronizes with the shared video session.
- Back pops one screen at a time.
- Language and voice controls use the real Back callback.
- Invoice Back returns to the exact previous voice screen.
- Self-shot Scene AI starts at the source-video gate and keeps the plan-first option.
- Video menus continue to use no more than two buttons per row.

## Locked Areas

- PayOS and `/naptien`
- Wallet, Xu top-up, packages, and combo logic
- Provider endpoint and provider selection logic
- Video billing, deduction, refund, and job lock core
- Public image flow
- Local Worker implementation
- Database schema and persistence
