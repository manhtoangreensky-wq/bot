# TOAN AAS Production Deployment Truth (VPS-Only) Reference

## Purpose
Documents the actual production deployment architecture, eliminating obsolete Railway assumptions from active engineering decisions.

## Canonical Architecture
- **Host**: Ubuntu VPS (`161.248.147.232` / `tg.toanaas.vn`).
- **Services**:
  - `toanaas-bot.service`: Telegram Bot runtime (`/opt/toanaas/bot/bot.py`).
  - `toanaas-web.service`: FastAPI web and webhook runtime.
  - `nginx.service`: Reverse proxy and SSL termination.
- **Database**: SQLite with WAL mode (`/data/toandaas_system.db`).

## CI/CD Pipeline Truth
```
GitHub repo (main) ──► GitHub Actions (.github/workflows/deploy.yml) ──► SSH Deploy to VPS ──► systemctl restart toanaas-bot toanaas-web
```

## Legacy Status Note
- **Railway**: Deprecated for production runtime. Retained in historical documentation only. Active deploy logic MUST target VPS only.
