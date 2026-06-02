# TOAN AAS Onboarding Funnel

## Goal

Move a new user from trial usage to a paid Xu top-up without exposing internal admin/operator systems.

## Funnel

1. User enters `/start`.
2. Bot explains four value groups:
   - AI tools: chat, voice, audio transcript, background removal, downloader.
   - Video Script Lite: `/film` for Facebook/TikTok/YouTube script packs.
   - Affiliate workflow: save links, plan content, track performance.
   - PayOS Xu: dynamic QR top-up and manual bill fallback.
3. User checks `/profile`.
4. User uses a trial/free tool.
5. When credits are missing, the bot shows current Xu, required Xu, missing Xu, and top-up buttons.
6. User opens `/naptien` or clicks a package button.
7. PayOS webhook or manual admin approval adds Xu.
8. User returns to `/film`, AI tools, or affiliate workflow.
9. Admin watches `/dashboard`, `/pending`, `/performance_report`, and `/backup_db`.

## Key Commands

- `/start`
- `/menu`
- `/help`
- `/profile`
- `/naptien`
- `/film`
- `/addlink`
- `/links`
- `/calendar`
- `/publish_done`
- `/performance_report`
- `/growth_loop`

## Conversion Points

- After free chat limit is reached.
- After a paid action reports insufficient Xu.
- After `/profile` shows low balance.
- After user opens the Video AI menu.
- After `/film` succeeds and user sees the remaining balance.

## Do Not

- Do not show admin/operator commands to normal users.
- Do not spam payment prompts.
- Do not auto publish without admin approval.
- Do not claim social platform API automation exists before it is implemented and tested.
