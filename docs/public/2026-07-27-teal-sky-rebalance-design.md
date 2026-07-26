# TOAN AAS Public Landing — Teal–Sky Rebalance Design

## Role in the product

`www.toanaas.vn` is the public companion to `app.toanaas.vn`.  It introduces
what TOAN AAS helps a visitor do, explains the hand-off into the Workspace,
and keeps Telegram as a quick-action companion.  It is not a dashboard,
payment screen, provider status page or promise of a generated result.

The Landing shares the Workspace colour family but deliberately uses a more
open public composition: true-white surfaces on a pale cyan canvas, deep teal
copy, high-contrast teal actions and sky-blue contextual detail.  It must not
reuse the signed-app sidebar, account UI or dense ERP chrome.

## Visual system

| Role | Value |
| --- | --- |
| Canvas | `#F4FBFC` |
| Surface | `#FFFFFF` |
| Deep ink | `#083344` |
| Primary action | `#0F766E` |
| Brand support | `#14B8A6` |
| Sky context/focus | `#0284C7` / `#38BDF8` |
| Divider | `#D7ECEF` |
| Supporting text | `#486B75` |

The layout uses a 1200–1260px desktop container, a 4/8px spacing rhythm and
16px mobile gutters.  All header, hero, process, companion, capability,
support and footer bands must share their alignment rails.  The hero image is
a code-native workflow illustration; it must never manufacture job output,
balances, customer evidence or provider readiness.

## Content hierarchy

1. Header: TOAN AAS, process/capability/support navigation, language choice
   and a visible Workspace action.
2. Hero: Vietnamese-first explanation, `Mở Workspace` primary action and
   `Dùng Telegram nhanh` secondary action.
3. Exact shared process: `Bản nháp → Ước tính → Xác nhận → Bàn giao`.
4. Clear companion explanation: Workspace for deep project work; Telegram
   for short actions and notifications.
5. Capability overview, trust boundaries, support/lead route and legal
   footer.

No fake metrics, testimonials, provider status, payment readiness, stock
logos, emoji icons, decorative hero eyebrow or unverifiable claims are
allowed.

## Locale, accessibility and safety

`?lang=vi|en|zh` remains display-only.  Every changed fixed label needs a
reviewed key in all three locales; links, form option values and user input
remain canonical.  Preserve the exact `POST /lead` JSON payload and
`landing-clean-clear-v2` source.  The form retains native validation,
near-field feedback, keyboard navigation, focus restoration and a Telegram
recovery route.  Use SVG icons and 44px minimum mobile controls.

## Before/after static visual QA ledger

This is a source-and-contract review only; no live browser observation is
claimed.

| Check | Before | After / static evidence |
| --- | --- | --- |
| Desktop rail and hero balance | The shared rail was 1260px and the hero imposed a 420px media minimum. | The rail is `min(1240px, calc(100% - 48px))`; the hero is `1.08fr / .92fr` with a 28–56px gap. |
| 375px one-column and overflow boundary | Mobile gutters and the tablet collapse already existed. | The 16px mobile gutters, `overflow-x: clip`, and the existing `max-width: 980px` one-column hero rule remain present; this is static evidence, not a rendered 375px observation. |
| Teal action contrast | The primary action used the brighter brand teal with deep-teal text. | Primary, hover, and focus rules use `--teal-action` (`#0F766E`) with white surface text. |
| Sky contextual contrast | Focus, form, and stage context used the light sky alias. | `--sky-context` (`#0284C7`) drives focus/form context; numbered stage markers retain light `--sky-400` with their inherited deep text. |
| Locale, keys, and route scope | The display-only locale selector, canonical links, and lead request existed. | Static contracts retain three entries for each reviewed key, URL-driven locale display, both exact external URLs, native form validation, canonical topics, and the unchanged `/lead` payload/source. |
