# P0.18D.3 Product Video Worker Claim + Provider Readiness

Status: CODE PASS / DEPLOY PENDING / VPS SERVICE PENDING / LIVE QA NOT STARTED

Scope: product video worker claim, provider readiness diagnostics, clean failure/status behavior.

## Fixed

1. Product video jobs now have a separate worker claim path:
   - `source=product_video`
   - `render_mode=real`
   - `test_pattern=false`
   - `admin_video_delivery=false`
   - `provider_call=true`
2. `remote_worker.py --admin-video` remains only for `/tool_test_video_delivery_worker --no-charge` delivery/test-pattern checks.
3. Added VPS modes:
   - `python remote_worker.py --owner-product-video`
   - `python remote_worker.py --product-video`
4. Owner/admin product jobs can be claimed by the owner product mode without opening public video.
5. Public product jobs require `REMOTE_WORKER_PUBLIC_ENABLED=1` plus `--product-video`.
6. Missing/failing real provider route marks product jobs failed cleanly/no retry in product worker mode. It does not produce fake MP4.
7. Old queued product jobs can fail cleanly with `product_video_worker_unavailable` instead of staying forever in preparing.
8. Added admin-only diagnostics:
   - `/tool_test_video_product_worker_claim --no-charge`
   - `/video_worker_status`

## Not Changed

- No public video UI redesign.
- No menu/package/invoice/add-on button changes.
- No PayOS/wallet/Xu ratio changes.
- No voice/subtitle/dub logic changes.
- No canary/test route reused for normal product video.

## VPS Runbook

Owner/admin live product QA:

```bash
python remote_worker.py --owner-product-video
```

Public product worker only after product video is intentionally opened:

```bash
python remote_worker.py --product-video
```

Delivery canary/test pattern remains separate:

```bash
python remote_worker.py --admin-video
```

Do not use `--admin-video` to prove product video rendering. It only proves the file delivery/test-pattern lane.

## Manual QA After Deploy

1. Run `/video_worker_status`.
2. Run `/tool_test_video_product_worker_claim --no-charge`.
3. Start VPS worker with `python remote_worker.py --owner-product-video`.
4. Admin creates one normal product video.
5. Expected:
   - If provider is configured and succeeds: final real MP4 is delivered.
   - If provider is missing/fails: clean no-charge failure, no fake MP4, no infinite preparing.
6. Public product video remains governed by the public worker gate.
