# Beta Launch Checklist - TOAN AAS

Date: 2026-06-02

## Before Inviting Users

- [ ] Railway deploy is on latest Git commit.
- [ ] `/runtime` build matches latest commit.
- [ ] `/health` returns JSON and `db_ok=true`.
- [ ] `/backup_db` has been run.
- [ ] Railway volume or backup plan is confirmed.
- [ ] `/providers` shows PayOS configured.
- [ ] `/promo_seed_policy` has been run.
- [ ] `/sales_ready` is not `SALES READY` until real PayOS test PASS.

## Real Money Test

- [ ] Test user activates `/promo FIRST30`.
- [ ] Test user pays 50k or higher PayOS QR.
- [ ] Test user receives base Xu plus Launch Bonus if eligible plus exactly one +30% promo bonus.
- [ ] Duplicate/replay does not add more Xu.
- [ ] Admin runs `/mark_payos_test pass order=<order_code> note="Test FIRST30 OK"`.
- [ ] `/sales_ready` now shows `SALES READY`.

## First 3-10 Users

- [ ] Invite only known beta users.
- [ ] Do not promise guaranteed revenue.
- [ ] Ask each user to run `/profile`.
- [ ] Let new users test one `/film` Basic with 200 trial Xu.
- [ ] Offer topup 10k/20k as trial packages, and 50k/100k when they want promo.
- [ ] Ask users to check `/khuyenmai`; public first top-up offer is `FIRST30`.
- [ ] If sending a free Xu reward, use `/gift <code>` instead of deposit promo codes.
- [ ] Ask user to post manually and keep basic metrics outside the public bot.
- [ ] If reporting is needed, ask user to send metrics to admin for manual review.
- [ ] Ask user to run `/growth_ai` after enough data.

## Stop Conditions

- [ ] PayOS credits wrong amount.
- [ ] Promo credits twice.
- [ ] Admin/operator commands leak to user.
- [ ] Provider failure does not refund charged Xu.
- [ ] DB backup cannot be created.
