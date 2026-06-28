# VPS Remote Worker Runbook

Runbook nay danh cho van hanh VPS chi chay `remote_worker.py`. Railway van giu bot chinh, database, PayOS, vi Xu va webhook Telegram.

## First deployment checklist

- PR W2 da merge vao `main`.
- Railway da deploy build mong doi.
- `/runtime build` dung commit/build dang chay.
- `/runtime` bao:
  - `worker_api_enabled=true`
  - `local_worker_token_configured=true`
  - `remote_worker_mode_supported=true`
- Telegram admin `/remote_worker_status` khong lo token va huong dan dung `python remote_worker.py --ping`.
- Telegram admin `/tool_test_remote_worker_ping --no-charge` pass, bao `no job claimed` va `charge: NO`.
- `LOCAL_WORKER_TOKEN` da tao tren Railway va chi copy vao `/etc/toanaas-worker.env` tren VPS.
- `/etc/toanaas-worker.env` co quyen `600`.
- `BOT_API_URL` tro ve Railway public URL.
- `WORKER_ID` la duy nhat, vi du `vps-1`.
- VPS co `python3`, `.venv`, `ffmpeg`, `curl`.
- Chay doctor:

```bash
sudo bash /opt/toanaas/bot/scripts/vps/remote_worker_doctor.sh
```

- Chay W3 staging tren VPS:

```bash
cd /opt/toanaas/bot
source .venv/bin/activate
python remote_worker.py --doctor
python remote_worker.py --ping
python remote_worker.py --dry-run --once
```

- Chay W4 canary thu cong truoc khi nghi toi production worker:

```text
/remote_worker_canary --no-charge
```

```bash
python remote_worker.py --canary --once
```

```text
/remote_worker_canary_status RW-CANARY-<id>
/remote_worker_status
```

- Chay W5 admin production canary thu cong truoc khi bat bat ky public worker mode nao:

```text
/remote_worker_prod_canary --no-charge
```

```bash
python remote_worker.py --admin-canary --once
```

```text
/remote_worker_prod_canary_status RW-PROD-CANARY-<id>
/queue_status
/remote_worker_status
```

- Chay Telegram admin dry-run:

```text
/tool_test_remote_worker_ping --no-charge
/tool_test_remote_worker_api --fake-job --no-charge
```

- Chi start service sau khi staging/dry-run pass va release owner xac nhan video flow san sang.
- P0.18D.4 owner-product lane chi claim owner/admin product video. Public product lane van khoa neu `REMOTE_WORKER_PUBLIC_ENABLED` chua bat.

## W3 staging handshake checklist

On Railway:

1. Set `LOCAL_WORKER_TOKEN`.
2. Deploy build.
3. Telegram: `/runtime`.
4. Telegram: `/remote_worker_status`.
5. Telegram: `/tool_test_remote_worker_ping --no-charge`.

On VPS:

1. Create `/etc/toanaas-worker.env`.
2. Run `chmod 600 /etc/toanaas-worker.env`.
3. Run:

```bash
source .venv/bin/activate
python remote_worker.py --doctor
python remote_worker.py --ping
python remote_worker.py --dry-run --once
```

Only after all pass:

- `sudo systemctl start toanaas-worker-admin-canary`
- Do not start public product worker until owner approval and `REMOTE_WORKER_PUBLIC_ENABLED=true`.

## W4 safe canary checklist

W4 la canary end-to-end an toan giua Railway va VPS. No chi tao job `remote_worker_canary`, sinh MP4 nho tai VPS bang ffmpeg, upload ve Railway, va bao status/admin. No khong claim video khach that, khong goi ShopAIKey/Key4U/provider, khong tru/hoan Xu.

On Railway/Telegram:

```text
/runtime
/remote_worker_status
/tool_test_remote_worker_ping --no-charge
/remote_worker_canary --no-charge
```

On VPS:

```bash
source .venv/bin/activate
python remote_worker.py --doctor
python remote_worker.py --ping
python remote_worker.py --canary --once
```

Back on Telegram:

```text
/remote_worker_canary_status RW-CANARY-<id>
/remote_worker_status
```

Can thay:

- `status=completed`.
- `result_uploaded=yes`.
- `Production jobs enabled=no` tru khi owner da cau hinh rieng.
- Neu Telegram app san sang, admin co the nhan file canary MP4.

Systemd staging:

- Khong start production service trong W4.
- Co the chay one-shot canary thu cong truoc.
- W5 moi duoc them controlled production canary neu owner approve.

## W5 admin production canary checklist

W5 la production-like canary dau tien qua normal `video_render` job type, nhung van chi owner/admin. No khong bat public worker, khong claim job khach, khong goi provider mac dinh, khong tru/hoan Xu.

On Railway/Telegram:

```text
/runtime
/remote_worker_status
/remote_worker_prod_canary --no-charge
```

On VPS:

```bash
source .venv/bin/activate
python remote_worker.py --doctor
python remote_worker.py --ping
python remote_worker.py --admin-canary --once
```

Back on Telegram:

```text
/remote_worker_prod_canary_status RW-PROD-CANARY-<id>
/queue_status
/remote_worker_status
```

Can thay:

- `status=completed`.
- `result_uploaded=yes`.
- Queue label: `OWNER/ADMIN WORKER CANARY — không trừ Xu`.
- `Public worker enabled=NO`.
- Provider: `no`.
- No-charge: `yes`.

Warnings:

- W5 is admin/owner only.
- Do not run public worker mode.
- Do not set `REMOTE_WORKER_PUBLIC_ENABLED=true` yet.
- W6/P0.18A se quyet dinh controlled production worker sau live QA.

## P0.18D.4 owner product worker live claim

P0.18D.4 tach service theo lane de tranh tinh trang VPS con heartbeat nhung khong co claim loop dang chay.

Repo path mac dinh:

```bash
cd /opt/toanaas/bot
pwd
git rev-parse HEAD
git fetch origin
git pull --ff-only origin main
.venv/bin/python --version
test -x .venv/bin/python && echo venv_ok
```

Env check tren VPS, khong in token:

```bash
grep -E '^(BOT_API_URL|LOCAL_WORKER_TOKEN|WORKER_ID)=' /etc/toanaas-worker.env | sed 's/=.*/=configured/'
```

Service lanes:

```text
toanaas-worker-admin-canary.service        -> python remote_worker.py --admin-canary
toanaas-worker-owner-product-video.service -> python remote_worker.py --owner-product-video
toanaas-worker-product-video.service       -> python remote_worker.py --product-video
toanaas-worker-admin-video.service         -> python remote_worker.py --admin-video
```

Install or refresh systemd files:

```bash
cd /opt/toanaas/bot
sudo bash scripts/vps/install_remote_worker_service.sh
sudo systemctl daemon-reload
```

Enable/status/journal owner product worker:

```bash
sudo systemctl enable --now toanaas-worker-owner-product-video
sudo systemctl status toanaas-worker-owner-product-video --no-pager -l
sudo journalctl -u toanaas-worker-owner-product-video -n 100 --no-pager -l
sudo systemctl restart toanaas-worker-owner-product-video
```

Enable/status/journal admin canary worker:

```bash
sudo systemctl enable --now toanaas-worker-admin-canary
sudo systemctl status toanaas-worker-admin-canary --no-pager -l
sudo journalctl -u toanaas-worker-admin-canary -n 100 --no-pager -l
sudo systemctl restart toanaas-worker-admin-canary
```

Public product worker:

```bash
sudo systemctl status toanaas-worker-product-video --no-pager -l
```

Chi `enable --now toanaas-worker-product-video` sau khi owner bat `REMOTE_WORKER_PUBLIC_ENABLED=true` va chap nhan cho VPS claim public product jobs.

Admin delivery/test worker:

```bash
sudo systemctl status toanaas-worker-admin-video --no-pager -l
```

Bot Telegram chi co the hien thi runbook/status. Bot khong the chay `systemctl` hoac `journalctl`; cac lenh nay chi chay tren terminal VPS.

Telegram admin checks sau khi service chay:

```text
/video_worker_status
/tool_test_video_product_worker_claim --no-charge
/remote_worker_prod_canary --no-charge
/remote_worker_prod_canary_status RW-PROD-CANARY-<id>
```

## Daily check

```bash
sudo systemctl status toanaas-worker-owner-product-video --no-pager -l
sudo journalctl -u toanaas-worker-owner-product-video --since "24 hours ago" --no-pager -l
sudo systemctl status toanaas-worker-admin-canary --no-pager -l
sudo journalctl -u toanaas-worker-admin-canary --since "24 hours ago" --no-pager -l
sudo bash /opt/toanaas/bot/scripts/vps/remote_worker_doctor.sh
df -h
free -h
```

Can thay:

- Service active neu dang trong cua so van hanh.
- Khong co lap `HTTP 401`/`HTTP 403`.
- Khong co token, provider secret, PayOS secret trong log.
- Disk con du dung luong cho `/opt/toanaas/tmp`.

## After deploy check

Sau moi lan Railway deploy:

```text
/runtime build
```

Kiem tra:

- Build Railway dung commit mong doi.
- `worker_api_enabled=true`.
- `local_worker_token_configured=true`.
- `remote_worker_mode_supported=true`.
- Public video queue/status khong bi loi.
- `/remote_worker_status` pass va khong hien token/path nhay cam.
- `/tool_test_remote_worker_ping --no-charge` pass truoc khi fake job test.
- `/tool_test_remote_worker_api --fake-job --no-charge` pass truoc khi worker that xu ly job.
- `/remote_worker_canary --no-charge` va `python remote_worker.py --canary --once` pass truoc moi rollout production.
- `/remote_worker_prod_canary --no-charge` va `python remote_worker.py --admin-canary --once` pass truoc moi rollout public worker.

Neu deploy thay doi worker contract, restart VPS worker:

```bash
sudo systemctl restart toanaas-worker-owner-product-video
sudo systemctl restart toanaas-worker-admin-canary
sudo journalctl -u toanaas-worker-owner-product-video -f
```

## How to stop worker

Dung ngay worker:

```bash
sudo systemctl stop toanaas-worker-owner-product-video
sudo systemctl stop toanaas-worker-admin-canary
sudo systemctl stop toanaas-worker-product-video
sudo systemctl stop toanaas-worker-admin-video
```

Chan auto-start sau reboot:

```bash
sudo systemctl disable toanaas-worker-owner-product-video
sudo systemctl disable toanaas-worker-admin-canary
sudo systemctl disable toanaas-worker-product-video
sudo systemctl disable toanaas-worker-admin-video
```

Kiem tra da stop:

```bash
sudo systemctl status toanaas-worker-owner-product-video --no-pager -l
sudo systemctl status toanaas-worker-admin-canary --no-pager -l
```

## How to rotate token

1. Stop worker:

```bash
sudo systemctl stop toanaas-worker-owner-product-video
sudo systemctl stop toanaas-worker-admin-canary
sudo systemctl stop toanaas-worker-product-video
sudo systemctl stop toanaas-worker-admin-video
```

2. Tao token moi tren Railway ENV `LOCAL_WORKER_TOKEN`.
3. Deploy/restart Railway neu quy trinh Railway yeu cau.
4. Cap nhat VPS:

```bash
sudo nano /etc/toanaas-worker.env
sudo chmod 600 /etc/toanaas-worker.env
```

5. Kiem tra doctor khong in full token:

```bash
sudo bash /opt/toanaas/bot/scripts/vps/remote_worker_doctor.sh
```

6. Chay dry-run admin:

```text
/tool_test_remote_worker_api --fake-job --no-charge
```

7. Start lai worker khi dry-run pass:

```bash
sudo systemctl start toanaas-worker-owner-product-video
sudo systemctl start toanaas-worker-admin-canary
```

## How to inspect logs

Follow log realtime:

```bash
sudo journalctl -u toanaas-worker-owner-product-video -f
```

Xem 200 dong gan nhat:

```bash
sudo journalctl -u toanaas-worker-owner-product-video -n 200 --no-pager -l
sudo journalctl -u toanaas-worker-admin-canary -n 200 --no-pager -l
```

Loc tu lan boot hien tai:

```bash
sudo journalctl -u toanaas-worker-owner-product-video -b --no-pager -l
```

Khong paste log cong khai neu co du lieu user, duong dan noi bo, token, provider key, hoac payload nhay cam.

## How to handle worker stuck

1. Kiem tra service:

```bash
sudo systemctl status toanaas-worker-owner-product-video --no-pager -l
sudo systemctl status toanaas-worker-admin-canary --no-pager -l
```

2. Kiem tra log:

```bash
sudo journalctl -u toanaas-worker-owner-product-video -n 200 --no-pager -l
sudo journalctl -u toanaas-worker-admin-canary -n 200 --no-pager -l
```

3. Kiem tra disk/tmp:

```bash
df -h
du -sh /opt/toanaas/tmp || true
```

4. Neu worker lap loi auth:

```bash
sudo systemctl stop toanaas-worker-owner-product-video
sudo systemctl stop toanaas-worker-admin-canary
```

Sau do rotate token hoac sua `/etc/toanaas-worker.env`.

5. Neu worker lap loi ket noi Railway, dung service va kiem tra `BOT_API_URL`, Railway health, firewall/DNS.
6. Neu safe canary fail, xem `/remote_worker_canary_status RW-CANARY-<id>` truoc. Ly do an toan thuong gap: `ffmpeg_missing`, bad token / `HTTP 401` / `HTTP 403`, upload failed, job lease expired, hoac no canary job.
7. Neu admin prod canary fail, xem `/remote_worker_prod_canary_status RW-PROD-CANARY-<id>` truoc. Ly do an toan thuong gap: `ffmpeg_missing`, output missing, bad token, upload failed, job lease expired.
8. Neu worker dang claim job nhung khong heartbeat, stop service va de Railway lease het han/retry theo queue policy. Khong sua SQLite truc tiep tu VPS.
9. Khi da sua xong:

```bash
sudo systemctl restart toanaas-worker-owner-product-video
sudo systemctl restart toanaas-worker-admin-canary
```

## How to avoid duplicate workers

- Moi VPS phai co `WORKER_ID` rieng.
- Khong chay service systemd va process thu cong cung luc voi cung `WORKER_ID`.
- Truoc khi start worker moi:

```bash
pgrep -af remote_worker.py || true
sudo systemctl status toanaas-worker-owner-product-video --no-pager -l
sudo systemctl status toanaas-worker-admin-canary --no-pager -l
```

- Neu clone VPS/image, doi `WORKER_ID` truoc khi start.

## When not to run worker

Khong start hoac phai stop worker neu:

- Owner has not approved this worker lane for the current release.
- `LOCAL_WORKER_TOKEN` missing.
- `/tool_test_remote_worker_ping --no-charge` fails.
- `python remote_worker.py --dry-run --once` fails.
- `/tool_test_remote_worker_api --fake-job --no-charge` fails.
- Railway `/runtime` not on expected build.
- Public video queue/status broken.
- Bot dang deploy loi, webhook Telegram khong on dinh, hoac owner dang freeze release.
- VPS co duplicate `WORKER_ID`.
- Logs cho thay auth failed, token leak, hoac config leak.
