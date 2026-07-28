# Local Video Studio 26I — Codex Capability Index

## Phạm vi

26I tạo một index ngắn gọn, machine-readable cho capability đã cài ngoài repo
và các contract 26C–26H trong repo. Index chỉ trỏ source-of-truth, không copy
implementation, không đăng ký runtime, không thêm UI/nút/route và không gọi
provider, model, wallet, Telegram hoặc deployment.

Branch: `feat/p1-localvideostudio26i-codex-index`, base sau correction 26H là
`599470bd55acdecd22f196004f60e0c3b3182b23`.

## Inventory

Index có đúng 14 record nhóm và 251 qualified capability IDs không trùng:

- OpenMontage local: path
  `C:/Users/toann/Documents/Codex/tools/OpenMontage`, official checkout pin
  `c36e41223e819441748817105635ac4036d41b10`, AGPL-3.0, local demo đã probe;
- 26C: editing 13, framing 20, pacing 11, camera 14, rights 8;
- 26D: transition 20, transition-audio 8, motion-design 12, kinetic type 10;
- 26E: sound layers 10, audio-post 14, loudness 5, timeline 9, audio QA 10;
- 26F: ten viral effects;
- 26G: 30 local capabilities, 11 delivery profiles, 10 heavy-model inventory;
- 26H: 19 video QA checks;
- Motion/Mosaic Motion: owner-reported installed, audit-only, paid-disabled;
- Higgsfield: command presence verified, audit-only, paid-disabled;
- Suno: policy-only, locked-disabled, evidence ceiling `NOT_INSTALLED`.

OpenMontage `LOCAL_INSTALLATION.md` là record workstation ngoài bot repo và
không được copy vào TOAN AAS. Index chỉ ghi path, pin, license, evidence và
test command đã dùng. Higgsfield/Motion không được chạy smoke hoặc generation.

## Readiness semantics

Index dùng đúng bảy state theo thứ tự:

```text
NOT_INSTALLED
INSTALLED
CONTRACT_PASS
LOCAL_DEMO_PASS
PAID_SMOKE_REQUIRED
PRODUCTION_READY
PUBLIC
```

State là evidence ceiling, không phải suy diễn. `INSTALLED` không đồng nghĩa
`PRODUCTION_READY`; `CONTRACT_PASS` không đồng nghĩa local demo; local demo
không đồng nghĩa production/public. Chỉ record có evidence riêng mới được nâng
state. Tất cả record 26I giữ `production_readiness=false`, không record nào là
`PRODUCTION_READY` hoặc `PUBLIC`.

## Contract shape

`capability_index.json` có baseline main SHA, readiness definitions, global
policy/counters, 14 record và four planning locks. Mỗi record có:

- capability ID, display tiếng Việt, location/kind và source files;
- status, local/cloud, free/paid, required tools;
- planned-shoot/explicit-confirmation policy;
- focused test command, highest readiness và production flag;
- version/SHA, official source, exact qualified IDs và evidence;
- four planning locks.

Các record repo dùng relative tracked paths. OpenMontage dùng workstation path
explicit vì master task yêu cầu local path. Motion/Higgsfield/Suno dùng
`SKIP_PAID_SMOKE`, không chứa lệnh generation.

## Acceptance

Focused test phải kiểm tra exact tree/schema/14 record, readiness order,
baseline SHA, 244 repo capability IDs lấy trực tiếp từ source JSON, tổng 251 IDs
unique, relative tracked source files, OpenMontage path/remote/pin, paid-disabled
status, safe test commands, deterministic UTF-8 JSON, official URL allowlist,
relative SKILL links và four locks. Chạy regression 26C–26H, skill validator,
test compile, `git diff --check`, scope và secret/placeholder scans.

Provider/Motion/Higgsfield/paid calls, wallet/Xu, Telegram, deployments và
production changes giữ 0/NO. Product Video, SubDub, renderer, worker, VPS,
Railway và UI/UX sản phẩm cũ không thay đổi.
