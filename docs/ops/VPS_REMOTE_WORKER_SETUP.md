# VPS Remote Worker Setup

Huong dan nay dung de chuan bi VPS Ubuntu chay `remote_worker.py` sau khi Railway da deploy bot chinh. VPS chi la may worker phu tro, khong thay the Railway va khong nam quyen thanh toan/vi Xu.

## A. Kien truc

- Railway giu bot chinh, database, PayOS, vi Xu, webhook Telegram va quyen dieu phoi job.
- VPS chi chay `remote_worker.py`.
- VPS khong giu quyen PayOS.
- VPS khong cong/tru Xu.
- VPS khong doc SQLite truc tiep.
- VPS chi goi Worker API bang `LOCAL_WORKER_TOKEN`.
- VPS nhan job qua `/api/v1/worker/claim`, gui heartbeat, upload ket qua, hoac bao fail an toan.
- Railway van la noi giao ket qua cuoi cung cho Telegram user.

## B. Chuan bi Railway ENV

Required:

```text
LOCAL_WORKER_TOKEN=<secret chi luu tren Railway va VPS>
WORKER_RESULT_UPLOAD_DIR=files/worker_results  # neu can override
PUBLIC_BASE_URL=<Railway public URL da cau hinh san>
TELEGRAM_WEBHOOK_SECRET=<da cau hinh san neu production>
```

Ghi chu an toan:

- Khong paste `LOCAL_WORKER_TOKEN` vao GitHub, docs public, issue, PR comment, chat log, hoac screenshot.
- Neu token bi lo, rotate ngay tren Railway, cap nhat `/etc/toanaas-worker.env` tren VPS, roi restart worker.
- Khong bat public product worker neu video flow va owner approval chua san sang. Owner-product worker chi danh cho owner/admin product QA va chay sau khi `/tool_test_video_product_worker_claim --no-charge` duoc kiem tra.

Runtime check tren Telegram/admin:

```text
/runtime build
```

Can thay cac flag an toan:

```text
worker_api_enabled=true
local_worker_token_configured=true
remote_worker_mode_supported=true
```

Neu mot trong cac flag nay khong dung, dung setup worker va sua Railway ENV truoc.

W3 staging handshake tren Railway:

1. Set `LOCAL_WORKER_TOKEN`.
2. Deploy build moi.
3. Telegram admin chay:

```text
/runtime
/remote_worker_status
/tool_test_remote_worker_ping --no-charge
```

Ket qua can thay:

- Worker API enabled.
- Token configured yes/no chi la boolean, khong hien token.
- Remote mode supported.
- Ping OK.
- No job claimed.
- No charge.

## C. Chuan bi VPS Ubuntu

Chay bang user co quyen `sudo`:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl python3 python3-venv python3-pip ffmpeg sqlite3 nano
```

Tao swap 4G neu VPS chua co swap:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Co the dung script bootstrap an toan:

```bash
sudo bash scripts/vps/bootstrap_remote_worker_ubuntu.sh
```

Script nay khong yeu cau token that va khong start service.

## D. Clone repo and install

```bash
sudo mkdir -p /opt/toanaas
cd /opt/toanaas
sudo git clone https://github.com/manhtoangreensky-wq/bot.git
cd bot
sudo python3 -m venv .venv
sudo .venv/bin/python -m pip install -U pip
sudo .venv/bin/python -m pip install -r requirements.txt
sudo mkdir -p /opt/toanaas/tmp
```

Neu repo da ton tai, khong overwrite. Kiem tra nhanh:

```bash
cd /opt/toanaas/bot
git status --short
git rev-parse HEAD
```

## E. Create env file

Tao file:

```text
/etc/toanaas-worker.env
```

Template chi dung tren server:

```text
BOT_API_URL=https://bot-production-2dd7.up.railway.app
LOCAL_WORKER_TOKEN=PASTE_REAL_TOKEN_ON_SERVER_ONLY
WORKER_ID=vps-1
WORKER_POLL_INTERVAL_SECONDS=5
WORKER_CONCURRENCY=1
WORKER_TMP_DIR=/opt/toanaas/tmp
FFMPEG_MAX_CONCURRENT=1
```

Dat quyen:

```bash
sudo chown root:root /etc/toanaas-worker.env
sudo chmod 600 /etc/toanaas-worker.env
```

Khong commit file `/etc/toanaas-worker.env` hoac token that vao repo.

## F. Systemd

P0.18D.4 dung cac lane service rieng de tranh worker heartbeat chay nhung khong claim dung queue:

```text
toanaas-worker-admin-canary.service        -> python remote_worker.py --admin-canary
toanaas-worker-owner-product-video.service -> python remote_worker.py --owner-product-video
toanaas-worker-product-video.service       -> python remote_worker.py --product-video
toanaas-worker-admin-video.service         -> python remote_worker.py --admin-video
```

Service templates nam tai:

```text
deploy/systemd/toanaas-worker-admin-canary.service
deploy/systemd/toanaas-worker-owner-product-video.service
deploy/systemd/toanaas-worker-product-video.service
deploy/systemd/toanaas-worker-admin-video.service
```

Co the dung installer an toan de copy va enable ca 4 service:

```bash
sudo bash scripts/vps/install_remote_worker_service.sh
```

Mac dinh installer chi `enable`, khong auto-start. Neu chi muon cai mot lane:

```bash
sudo SERVICE_NAME=toanaas-worker-owner-product-video.service bash scripts/vps/install_remote_worker_service.sh
```

Neu muon start ro rang sau khi dry-run pass:

```bash
sudo RUN_START=1 SERVICE_NAME=toanaas-worker-owner-product-video.service bash scripts/vps/install_remote_worker_service.sh
```

## G. Start/stop/status/logs

Chi start worker that sau khi Railway `/runtime` dung build va dry-run fake job pass.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now toanaas-worker-owner-product-video
sudo systemctl status toanaas-worker-owner-product-video --no-pager -l
sudo journalctl -u toanaas-worker-owner-product-video -n 100 --no-pager -l
sudo systemctl enable --now toanaas-worker-admin-canary
sudo systemctl status toanaas-worker-admin-canary --no-pager -l
sudo journalctl -u toanaas-worker-admin-canary -n 100 --no-pager -l
sudo systemctl restart toanaas-worker-owner-product-video
sudo systemctl restart toanaas-worker-admin-canary
```

`systemctl` va `journalctl` chi chay tren terminal VPS. Bot Telegram khong the chay cac lenh nay.

Kiem tra repo, commit, venv va env tren VPS:

```bash
cd /opt/toanaas/bot
pwd
git rev-parse HEAD
git fetch origin
git pull --ff-only origin main
.venv/bin/python --version
test -x .venv/bin/python && echo venv_ok
grep -E '^(BOT_API_URL|LOCAL_WORKER_TOKEN|WORKER_ID)=' /etc/toanaas-worker.env | sed 's/=.*/=configured/'
```

Doctor script:

```bash
sudo bash scripts/vps/remote_worker_doctor.sh
```

Doctor khong in full token; chi bao token da cau hinh hay chua.

W3 staging handshake tren VPS:

```bash
cd /opt/toanaas/bot
source .venv/bin/activate
python remote_worker.py --doctor
python remote_worker.py --ping
python remote_worker.py --dry-run --once
```

Yeu cau:

- `--doctor` chi kiem tra local env, token masked, ffmpeg va tmp dir.
- `--ping` chi goi `/api/v1/worker/ping`.
- `--dry-run --once` khong claim job, khong complete job, khong xu ly video that.
- Neu token sai, log chi duoc co status/reason an toan, khong co full token.

## G2. W4 safe canary end-to-end

W4 chi kiem tra duong claim -> heartbeat -> upload/complete bang job canary admin. Khong bat worker xu ly video khach that, khong goi provider, khong tru Xu.

Tren Railway/Telegram admin:

```text
/runtime
/remote_worker_status
/tool_test_remote_worker_ping --no-charge
/remote_worker_canary --no-charge
```

Lenh canary se tra ve ma job dang `RW-CANARY-<id>`.

Tren VPS:

```bash
cd /opt/toanaas/bot
source .venv/bin/activate
python remote_worker.py --doctor
python remote_worker.py --ping
python remote_worker.py --canary --once
```

Quay lai Telegram admin:

```text
/remote_worker_canary_status RW-CANARY-<id>
/remote_worker_status
```

Yeu cau:

- Canary status la `completed`.
- Result uploaded la `yes`.
- Sent to admin co the la `yes` neu Telegram app san sang, hoac `no` neu chi dang test API/server.
- Production jobs enabled van la `no` tru khi owner da cau hinh rieng o phase sau.
- Neu fail, xem log systemd/VPS voi cac ly do an toan nhu `ffmpeg_missing`, `upload failed`, `HTTP 401/403`, hoac network error. Khong paste token vao log chia se.

## G3. W5 admin production canary

W5 la job `video_render` production-like dau tien cho VPS, nhung chi danh cho owner/admin. Mac dinh khong public, khong goi provider, khong tru Xu, va khong bat public worker.

Tren Railway/Telegram admin:

```text
/runtime
/remote_worker_status
/remote_worker_prod_canary --no-charge
```

Lenh se tra ve ma job dang `RW-PROD-CANARY-<id>`.

Tren VPS:

```bash
cd /opt/toanaas/bot
source .venv/bin/activate
python remote_worker.py --doctor
python remote_worker.py --ping
python remote_worker.py --admin-canary --once
```

Quay lai Telegram admin:

```text
/remote_worker_prod_canary_status RW-PROD-CANARY-<id>
/queue_status
/remote_worker_status
```

Yeu cau:

- Status la `completed`.
- Result uploaded la `yes`.
- Queue label la `OWNER/ADMIN WORKER CANARY — không trừ Xu`.
- Public worker enabled van la `NO`.
- Khong set `REMOTE_WORKER_PUBLIC_ENABLED=true` trong W5.
- Chi W6/P0.18A moi quyet dinh controlled production worker sau live QA.

## H. Safety

- Do not paste token into GitHub.
- `chmod 600 /etc/toanaas-worker.env`.
- Rotate `LOCAL_WORKER_TOKEN` if leaked.
- Do not run two workers with the same `WORKER_ID`.
- Do not start public product worker before owner approval and `REMOTE_WORKER_PUBLIC_ENABLED=true`.
- Owner-product worker may run only for owner/admin product video jobs after P0.18D.4 code is deployed and checked.
- W3 dry-run only verifies handshake; it must not process real user video.
- W4 canary only claims `remote_worker_canary` jobs; it must not process real user video.
- W5 admin production canary only claims jobs marked `worker_admin_canary=true`; it must not process real user video.
- First run only after `/tool_test_remote_worker_api --fake-job --no-charge` passes.
- Staging ping can run first with `/tool_test_remote_worker_ping --no-charge`.
- Safe canary can run manually with `/remote_worker_canary --no-charge` and `python remote_worker.py --canary --once`.
- Admin production canary can run manually with `/remote_worker_prod_canary --no-charge` and `python remote_worker.py --admin-canary --once`.
- Do not set `REMOTE_WORKER_PUBLIC_ENABLED=true` yet.
- VPS khong can PayOS ENV, wallet ENV, Telegram bot token, webhook secret, hay quyen doc SQLite.
- Neu `/runtime` khong dung build, dung worker.
- Neu public video queue/status broken, dung worker.
- Neu log co `HTTP 401`, `HTTP 403`, hoac `LOCAL_WORKER_TOKEN missing`, stop worker va kiem tra token tren Railway/VPS.
