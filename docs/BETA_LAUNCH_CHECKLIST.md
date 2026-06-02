# Beta Launch Checklist - TOAN AAS

Date: 2026-06-02

## Before Inviting Users

- [ ] Railway deploy is on latest Git commit.
- [ ] `/runtime` build matches latest commit.
- [ ] `/health` returns JSON and `db_ok=true`.
- [ ] `/backup_db` has been run.
- [ ] Railway volume or backup plan is confirmed.
- [ ] `/providers` shows PayOS configured.
- [ ] `/promo_seed_beta` has been run if using BETA50.
- [ ] `/sales_ready` is not `SALES READY` until real PayOS test PASS.

## Real Money Test

- [ ] Test user activates `/promo BETA50`.
- [ ] Test user pays 10k PayOS QR.
- [ ] Test user receives exactly 150 Xu.
- [ ] Duplicate/replay does not add more Xu.
- [ ] Admin runs `/mark_payos_test pass order=<order_code> note="Test 10k+BETA50 OK"`.
- [ ] `/sales_ready` now shows `SALES READY`.

## First 3-10 Users

- [ ] Invite only known beta users.
- [ ] Do not promise guaranteed revenue.
- [ ] Ask each user to run `/profile`.
- [ ] Let new users test one `/film` Basic with 200 trial Xu.
- [ ] Offer topup 10k/50k/100k only after they understand Xu.
- [ ] If using a promo, send code privately and ask user to run `/promo <code>`.
- [ ] Ask user to post manually, then record result with `/publish_done`.
- [ ] Ask user to add metrics with `/performance_add`.
- [ ] Ask user to run `/growth_ai` after enough data.

## Stop Conditions

- [ ] PayOS credits wrong amount.
- [ ] Promo credits twice.
- [ ] Admin/operator commands leak to user.
- [ ] Provider failure does not refund charged Xu.
- [ ] DB backup cannot be created.
