# SubDub Combo Single-Lane Design

## Goal

Make `Phụ đề + Lồng tiếng` expose one customer path only:

`Gửi video` → `Chọn ngôn ngữ dịch` → `Chọn giọng mặc định/tự động` → `Xác nhận` → `VPS tạo và gửi một MP4 cuối`.

## Scope

- Replace the two source-choice buttons on the combo entry screen with one existing `videodub|source_upload` action.
- Reuse speech extraction, subtitle translation, voice selection, audio mixing, billing, and final rendering unchanged.
- Resolve the existing `ASR_PROVIDER=auto` setting through the already-supported Key4U → ShopAIKey → Deepgram adapters; do not change adapter endpoints, credentials, ENV, or payload contracts.
- Keep legacy `videodub|path|...` handlers so buttons in already-sent Telegram messages do not become invalid.
- Do not expose the internal original-transcript/subtitle preparation as a customer step.
- Keep original SRT, transcript, translated SRT, and dubbed audio as internal artifacts; never auto-send them from the combo lane.
- Keep MP4-as-document fallback for large files so support above 50 MiB is not regressed; it still counts as the one final MP4.

## Acceptance

- Combo entry exposes exactly one upload action and no `videodub|path|...` action.
- A fresh combo video upload goes directly to the language picker.
- Preset and custom languages both go directly to the default/automatic voice picker.
- The upload does not call ASR/provider or charge Xu before final confirmation.
- Existing final confirmation remains the only entry to the full SubDub pipeline.
- Success is terminal only after one final MP4 is delivered; missing MP4 fails closed without public audio/SRT/transcript fallback.
- The delivered MP4 is the final public message; no receipt/download message is appended below it.
- Legacy callbacks remain registered but are hidden from the fresh combo UI.
- Pricing, payment, wallet, provider adapter implementations, ENV, DB, and other SubDub lane UI/state machines remain unchanged.

## Verification

- Focused keyboard and upload-routing regression.
- Existing final-confirm comparator.
- `git diff --check` and changed-file AST/compile check.
- Authorized live smoke with the two-speaker video after merge/deploy.
