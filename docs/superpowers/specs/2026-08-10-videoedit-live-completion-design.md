# Video Edit Live Completion Design

## Goal

Make every public Video Edit route preserve the user's exact requested operation, render a professional receipt-backed status panel, and produce a verified MP4 through the dedicated local worker without touching Product Video, Frame, PayOS, or paid providers.

## Approved approach

Use deterministic, context-aware parsing for exact numeric edit values. A percentage near a brightness phrase maps only to `brightness_percent`; a percentage near a master-volume phrase maps only to `volume`. Numeric values outside the already supported public ranges fail closed. Requests without explicit values keep the existing preset and loudness-normalization behavior. No LLM or external provider participates in this compiler.

## Data flow

1. Telegram receives the source video and probes its real metadata.
2. `compile_local_intent` converts the user's Vietnamese request into the canonical local edit plan.
3. The existing runtime admission checks the needed FFmpeg filters against the dedicated worker heartbeat.
4. Review and confirmation show the exact compiled operations and 0 Xu for local work.
5. One confirmation creates one job; the dedicated VPS worker renders, validates, and delivers one MP4.
6. The worker persists the operation summary only after terminal success, and the
   status panel reads only that terminal evidence plus persisted receipt,
   validation, charge, and timestamp data. It never reinterprets the original
   request as proof that an edit actually ran.

## Status panel

While running, keep the six-stage progress board. At terminal success, switch the heading to `Đã hoàn tất` and add: processing code, concrete edit result, output video duration, processing elapsed time, execution engine, confirmed price, actually charged Xu, account balance only when authoritatively available, and delivery status. At terminal failure, retain the same board, identify the failed stage and public reason, and show 0 Xu charged when no successful delivery receipt exists. Missing values must be omitted or described as unavailable; never rendered as invented zeroes.

## Safety boundaries

- Local brightness, volume, trim, logo, watermark, and supported quality filters remain 0 Xu.
- No provider call, wallet mutation, invoice, ENV change, service restart, merge, or deploy is part of the code change without a separate Owner gate.
- Product Video, Frame, Subdub behavior, PayOS, onboarding, and PWA are protected comparators only.

## Verification

- RED then GREEN for the exact live phrase `Làm sáng video lên 120% và tăng âm lượng lên 110%`.
- RED then GREEN for success and failure Video Edit status receipt fields.
- Existing Video Edit route/engine and wallet/provider-zero comparators.
- `py_compile` for touched Python entry points.
- After an authorized deployment at the exact commit: Telegram live execution, MP4 download, ffprobe, full decode, and measurable image/audio change.
