# TOAN AAS Public Landing — Teal–Sky Design

## Purpose and boundary

`https://www.toanaas.vn/` is the public introduction to TOAN AAS.  It should
explain the product, guide a visitor into the independent Web Workspace, and
make Telegram's quick-action role clear.  It is not a dashboard, a payment
surface, an admin screen, or a promise of provider output.

This slice changes only repository-root `index.html`.  It does not change
`bot.py`, Telegram handlers, PayOS, wallet/Xu logic, webhooks, database code,
or the existing `POST /lead` contract.

## Approved visual direction

Reference concepts:

- Desktop: `C:\Users\toann\.codex\generated_images\019f4b14-cdaa-7d90-8869-cf654fcab17a\exec-7c1e9242-f9c4-42cc-8cfe-3b287f52cbdf.png`
- Mobile: `C:\Users\toann\.codex\generated_images\019f4b14-cdaa-7d90-8869-cf654fcab17a\exec-aab0ce77-498b-4a9a-a04b-fe0aa83b2e06.png`

The landing uses the same family as `app.toanaas.vn` while keeping its public
role distinct:

| Role | Value |
| --- | --- |
| Public canvas | `#F4FBFC` |
| White surface | `#FFFFFF` |
| Deep teal ink | `#092B36` |
| Workspace teal | `#062A36` |
| Primary action | `#14B8A6` |
| Primary hover | `#2DD4BF` |
| Sky context/focus | `#38BDF8` |
| Light border | `#D7ECEF` |

Use clean aligned bands, a 4/8px rhythm, 16px mobile gutters, 44px minimum
touch controls, restrained flat borders and subtle shadows.  Do not use
purple/pink, emoji as structural icons, fake metrics, fake output, fake
customer names, live provider state, success claims, or a decorative hero
eyebrow/pill.

## Content and information architecture

1. A simple header links to product explanation, workflow, support, Telegram,
   and the independent Web Workspace.
2. The hero gives a plain Vietnamese-first explanation and one primary action:
   `Mở Workspace`; `Dùng Telegram nhanh` is secondary.
3. The four-stage explanation is exact and non-promissory:
   `Bản nháp → Ước tính → Xác nhận → Bàn giao`.
4. A companion section explains the intentional split: Workspace for deep
   projects and Telegram for fast actions.
5. Three concise capability groups describe content, image/video and
   voice/document work without claiming every feature is currently enabled.
6. A trust section states verified boundaries: review, clear ownership,
   explicit readiness, and no payment or output claim on this public page.
7. The existing lead form stays available and continues to submit its exact
   safe payload to `/lead`; its visible wording must state the real recovery
   route if the request cannot be sent.

## Language behavior

The public surface supports Vietnamese, English and Simplified Chinese.
Vietnamese is the default.  The language control uses `?lang=vi|en|zh` and
updates only display copy plus document metadata; it does not write a browser
identity/profile, infer account state, or change a server-side authority.
Every visible fixed label introduced by this landing has a reviewed entry in
all three locales.  Telegram handles, URLs, form values and customer-entered
information remain unmodified.

## Interaction and safety

- `Mở Workspace` opens `https://app.toanaas.vn/login`; the independent
  Workspace handles its own signed session.
- Telegram links retain `target="_blank" rel="noopener"` and are secondary.
- The lead form keeps native labels, required input types, near-field browser
  validation, a disabled submit state while pending, `aria-live` status and a
  direct Telegram recovery link on a failed request.
- Hash navigation has an accessible mobile menu toggle, Escape close behavior,
  click-away close behavior and no horizontal overflow.
- Motion uses opacity/transform under 220ms and is disabled for
  `prefers-reduced-motion`.

## Verification plan

- Static contract: locale key parity, semantic navigation, app/Telegram link
  ownership, `/lead` payload preservation, absence of structural emoji and
  no fake-metric language.
- Visual smoke: landing at 1440px and 390px, verify aligned header/hero,
  44px controls, mobile menu and no horizontal overflow.
- Functional smoke: locale URL control, section links, mobile-menu state,
  form native validation and failed-request recovery copy.  No lead is sent
  during test and no external provider, PayOS, Telegram or production flow is
  exercised.
