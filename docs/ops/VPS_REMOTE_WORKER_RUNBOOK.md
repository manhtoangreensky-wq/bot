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

- Chay Telegram admin dry-run:

```text
/tool_test_remote_worker_ping --no-charge
/tool_test_remote_worker_api --fake-job --no-charge
```

- Chi start service sau khi staging/dry-run pass va release owner xac nhan video flow san sang.
- Van chua route production video jobs cho VPS cho toi khi B14.5 video flow/queue/status on dinh.

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

- `sudo systemctl start toanaas-worker`
- Still do not route production jobs until B14.5 video flow/queue/status is stable.

## Daily check

```bash
sudo systemctl status toanaas-worker -n 80
sudo journalctl -u toanaas-worker --since "24 hours ago" --no-pager
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

Neu deploy thay doi worker contract, restart VPS worker:

```bash
sudo systemctl restart toanaas-worker
sudo journalctl -u toanaas-worker -f
```

## How to stop worker

Dung ngay worker:

```bash
sudo systemctl stop toanaas-worker
```

Chan auto-start sau reboot:

```bash
sudo systemctl disable toanaas-worker
```

Kiem tra da stop:

```bash
sudo systemctl status toanaas-worker -n 40
```

## How to rotate token

1. Stop worker:

```bash
sudo systemctl stop toanaas-worker
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
sudo systemctl start toanaas-worker
```

## How to inspect logs

Follow log realtime:

```bash
sudo journalctl -u toanaas-worker -f
```

Xem 200 dong gan nhat:

```bash
sudo journalctl -u toanaas-worker -n 200 --no-pager
```

Loc tu lan boot hien tai:

```bash
sudo journalctl -u toanaas-worker -b --no-pager
```

Khong paste log cong khai neu co du lieu user, duong dan noi bo, token, provider key, hoac payload nhay cam.

## How to handle worker stuck

1. Kiem tra service:

```bash
sudo systemctl status toanaas-worker -n 80
```

2. Kiem tra log:

```bash
sudo journalctl -u toanaas-worker -n 200 --no-pager
```

3. Kiem tra disk/tmp:

```bash
df -h
du -sh /opt/toanaas/tmp || true
```

4. Neu worker lap loi auth:

```bash
sudo systemctl stop toanaas-worker
```

Sau do rotate token hoac sua `/etc/toanaas-worker.env`.

5. Neu worker lap loi ket noi Railway, dung service va kiem tra `BOT_API_URL`, Railway health, firewall/DNS.
6. Neu worker dang claim job nhung khong heartbeat, stop service va de Railway lease het han/retry theo queue policy. Khong sua SQLite truc tiep tu VPS.
7. Khi da sua xong:

```bash
sudo systemctl restart toanaas-worker
```

## How to avoid duplicate workers

- Moi VPS phai co `WORKER_ID` rieng.
- Khong chay service systemd va process thu cong cung luc voi cung `WORKER_ID`.
- Truoc khi start worker moi:

```bash
pgrep -af remote_worker.py || true
sudo systemctl status toanaas-worker -n 40
```

- Neu clone VPS/image, doi `WORKER_ID` truoc khi start.

## When not to run worker

Khong start hoac phai stop worker neu:

- Video flow B14.5 not stable.
- `LOCAL_WORKER_TOKEN` missing.
- `/tool_test_remote_worker_ping --no-charge` fails.
- `python remote_worker.py --dry-run --once` fails.
- `/tool_test_remote_worker_api --fake-job --no-charge` fails.
- Railway `/runtime` not on expected build.
- Public video queue/status broken.
- Bot dang deploy loi, webhook Telegram khong on dinh, hoac owner dang freeze release.
- VPS co duplicate `WORKER_ID`.
- Logs cho thay auth failed, token leak, hoac config leak.
