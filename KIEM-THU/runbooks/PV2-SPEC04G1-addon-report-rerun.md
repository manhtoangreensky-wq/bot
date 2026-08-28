# PV2 SPEC-04G.1 - Add-on Truth and Delivery Report Live Rerun

This runbook closes the live RED exposed by Product Video job #26. It is a
correction rerun of the same manual Tail seam, not a representative `V2-03`
product run and not permission to start another product.

## Lock

- Pointer: `V2-02I/SPEC-04G.1`.
- Product: `video_ai_real` / public `Video AI chân thật`.
- Lane: manual prompt -> shared Tail.
- Case ID: `PV2-S04G1-RERUN-20260828`.
- Prompt: `PV2-S04G1-RERUN-20260828: Nghệ nhân hoàn thiện bình gốm xanh | giới thiệu quy trình thủ công trong 2 cảnh | chân thật, nhất quán, thành phẩm rõ ràng`.
- Scenes: `2`; ratio: `9:16`.
- Quality: internal `tier_id=400`; public `Nhanh gọn`, `80 Xu/cảnh`,
  `8 giây/cảnh`.
- Expected duration: `16 giây`.
- Add-ons: default transition only. Voice, dubbing, music, subtitles, SFX,
  logo, watermark and text overlays remain off.
- Expected invoice: list `160 Xu`, multi-scene discount `16 Xu`, video price
  and invoice total `144 Xu`, Add-on total `0 Xu`.
- Owner test account: actual charge `0 Xu`; transactions and credit events must
  remain unchanged.
- Standing Owner direction already authorizes the assigned Product Video live
  tests. Do not interrupt the run to ask for another business approval. Browser
  safety and shared-resource ownership still apply.

## Preconditions

1. Receive exact `SUBDUB AUTO LIVE RELEASED`, `CHROME RELEASED BY SUBDUB AUTO`
   and `VPS/DEPLOY RELEASED BY SUBDUB AUTO` markers.
2. Fetch/rebase the single local commit onto current `origin/main`; run the exact
   post-rebase focused gate, compile and diff check.
3. Push one branch, create one PR, squash merge once, and wait for the exact merge
   SHA deploy. Verify bot and Owner worker run that same SHA and current generation.
4. Verify no Product Video or SubDub provider job, deploy, restart or Telegram
   action is active.
5. Snapshot project/job/outbox counts and max IDs, provider usage, Owner credits,
   total spent, transaction count/max ID and credit-event count/max ID.
6. Reserve exactly one Product Video job and at most two scene-render creates.
   No image-generation task, fallback paid submit or second Product Video job is
   allowed for this correction rerun.

## Exact UI Path

1. `/start -> Tạo video AI -> Video AI chân thật -> Prompt -> Video`.
2. Select `2 cảnh`, then `9:16`.
3. Select `Tự mô tả nội dung` and send the exact locked prompt once.
4. Verify direct input enters `Add-on` immediately. A jump to a legacy wizard,
   another product, Quality before Add-on, or main menu is FAIL before provider.
5. Leave voice, dubbing, music, subtitles, SFX, logo, watermark and text overlays
   off. Keep only the default transition between scene 1 and scene 2.
6. Review must show `Video AI chân thật`, two scenes, 9:16, the exact prompt and
   no audio/voice/subtitle selection.
7. Click `Nhanh gọn - 80 Xu/cảnh` once. It must open Invoice with internal tier
   `400`, `8 giây/cảnh`, `16 giây` total and must never jump to tier `1500` or
   `2360 Xu`.
8. Invoice and Confirmation must show `144 Xu` total and `0 Xu` Add-on fee.
9. Click final Confirm exactly once, then observe Status read-only through terminal.
   Do not reuse an old callback or submit a second prompt.

## Durable Add-on Gate

- Persisted project `addon_plan_json.contract_version` is
  `product-video-addons-v1`.
- `requested_addons` is exactly `['transitions']`.
- Transition material requirement exists for scene 1 -> scene 2.
- Voice, dubbing, music, subtitle, SFX, logo, watermark and text are absent from
  `requested_addons` and remain disabled in their component payloads.
- Worker result and final manifest satisfy:
  - `addon_application.requested == ['transitions']`;
  - `addon_application.applied == ['transitions']`;
  - `addon_application.missing == []`;
  - `partial_addons == 0`;
  - no implicit profile voice, music or subtitle material exists.
- Any silent drop, implicit Add-on, missing transition or `partial_addons=1` is
  terminal FAIL; stop before starting `V2-03`.

## Artifact and Delivery Gate

- Two independent provider scene records and two non-duplicate scene clips.
- Final MP4 has `ftyp`/`moov`, H.264 video, expected AAC audio when present,
  `540x960` or another exact 9:16 geometry with SAR 1:1, duration consistent with
  16 seconds, first/last frame decode, no black interval and no letterbox padding.
- Record path, bytes, SHA-256, streams, duration, dimensions and scene-boundary
  frame evidence.
- Telegram MP4 send succeeds once; persist video message ID, file ID and
  `file_unique_id` before Status becomes delivered.
- Delivery receipt is durable before settlement. Owner settlement is terminal
  `charged_xu=0`; transaction and credit-event row count/max ID deltas are zero.

## Customer Report Gate

After MP4 receipt persistence and settlement, exactly one later Telegram text
message must contain the following business truth:

```text
✅ Video đã hoàn tất

• Sản phẩm: Video AI chân thật
• Chất lượng: Nhanh gọn · 8 giây/cảnh
• Video: 2 cảnh · 16 giây · 9:16
• Giá video: 144 Xu
• Add-on đã chọn: 1 mục
• Miễn phí: 1 · Có phí: 0
• Add-on đã áp dụng: 1/1
• Phí Add-on: 0 Xu
• Tổng hóa đơn: 144 Xu
• Xu thực trả: 0 Xu
• Trạng thái: Đã gửi video thành công
```

- The report message ID is persisted in the job result as
  `delivery_report_message_id`, with `delivery_report_sent=true`.
- The customer message must not expose provider, worker, job/task ID, SHA,
  manifest, JSON, engine route, internal diagnostics or raw error codes.
- A duplicate completion callback must not resend the MP4, settle again or send a
  second report. If MP4 is durable but the report never sent, one safe report-only
  retry is allowed.
- Report failure must leave the MP4 receipt and settlement intact and must not
  change wallet state.

## PASS and Freeze

PASS requires every gate above plus exact PR, merge SHA, deploy run, bot/worker
runtime SHA, project/job/outbox identity, artifact evidence, video receipt, report
receipt and zero-wallet snapshots in both master checklist files. Only then mark
`SPEC-04G.1` complete and freeze its route/tests/artifact/report evidence before
moving to `V2-03`.
