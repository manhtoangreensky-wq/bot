# SubDub Combo Single-Lane Design

## Goal

Make `Phụ đề + Lồng tiếng` expose one customer path only:

`Gửi video` → `Chọn ngôn ngữ dịch` → `Chọn giọng` → `Xác nhận` → `Tạo MP4`.

## Scope

- Replace the two source-choice buttons on the combo entry screen with one existing `videodub|source_upload` action.
- Keep speech extraction, subtitle translation, voice selection, audio mixing, billing, and final rendering unchanged.
- Keep legacy `videodub|path|...` handlers so buttons in already-sent Telegram messages do not become invalid.
- Do not expose the internal original-transcript/subtitle preparation as a customer step.

## Acceptance

- Combo entry exposes exactly one upload action and no `videodub|path|...` action.
- A fresh combo video upload goes directly to the language picker.
- The upload does not call ASR/provider or charge Xu before final confirmation.
- Existing final confirmation remains the only entry to the full SubDub pipeline.
- Pricing, payment, wallet, provider adapters, ENV, DB, and other SubDub lanes remain unchanged.

## Verification

- Focused keyboard and upload-routing regression.
- Existing final-confirm comparator.
- `git diff --check` and changed-file AST/compile check.
- Authorized live smoke with the two-speaker video after merge/deploy.
