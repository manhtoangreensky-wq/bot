# TOAN AAS Onboarding Funnel

## Goal

Move a new user from trial usage to a paid Xu top-up without exposing internal admin/operator systems.

## Funnel

1. User enters `/start`.
2. Bot explains four value groups:
   - AI tools: chat, voice, audio transcript, background removal, downloader.
   - Video Script Lite: `/film` for Facebook/TikTok/YouTube script packs.
   - Content Pack self-post workflow: paste topic/product/link context, receive script/caption/prompt/CTA, then post manually.
   - PayOS Xu: dynamic QR top-up and manual bill fallback.
3. New user receives 200 Xu trải nghiệm.
4. User checks `/profile`.
5. User tries one `/film` Basic run.
6. When credits are missing, the bot shows current Xu, required Xu, missing Xu, and top-up buttons.
7. User opens `/naptien` or clicks a package button.
8. PayOS webhook or manual admin approval adds Xu.
9. User returns to `/film`, AI tools, or `/growth_ai`.
10. Admin watches `/dashboard`, `/pending`, and `/backup_db`.

## Trial Strategy

- New user trial = 200 Xu.
- Goal: enough for one `/film` Basic run.
- Applies to new users after deploy.
- Existing users are not auto-topped up without a separate migration.

## Key Commands

- `/start`
- `/menu`
- `/help`
- `/profile`
- `/naptien`
- `/film`
- `/growth_ai`
- `/campaign_report`

## Conversion Points

- After free chat limit is reached.
- After a paid action reports insufficient Xu.
- After `/profile` shows low balance.
- After user opens the Video AI menu.
- After `/film` succeeds and user sees the remaining balance.

## Do Not

- Do not show admin/operator commands to normal users.
- Do not expose affiliate vault, publish tracking, social-account connection or ads management to normal users.
- Do not spam payment prompts.
- Do not auto publish without admin approval.
- Do not claim social platform API automation exists before it is implemented and tested.
