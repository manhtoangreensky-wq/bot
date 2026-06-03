# TOAN AAS Deploy Workflow

Production domain:

`https://bot-production-2dd7.up.railway.app`

Do not use GitHub Pages for this project:

`https://manhtoangreensky-wq.github.io`

## Standard Steps

1. Edit only the required files.
2. Run syntax check:

```powershell
python -m py_compile bot.py
```

3. Review changed files:

```powershell
git status --short
git diff --stat
```

4. Add only required files:

```powershell
git add bot.py index.html LOGO.png banner.png TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V1.docx TOAN_AAS_DIEU_KHOAN_SU_DUNG_DICH_VU_V1.pdf docs/DEPLOY_WORKFLOW.md
```

5. Commit:

```powershell
git commit -m "Your commit message"
```

6. Push to GitHub main:

```powershell
git push origin main
```

7. Railway auto deploys from GitHub.

## Production Smoke Test

Test the Railway domain only:

- `https://bot-production-2dd7.up.railway.app/`
- `https://bot-production-2dd7.up.railway.app/health`
- `https://bot-production-2dd7.up.railway.app/asset_check`
- `https://bot-production-2dd7.up.railway.app/LOGO.png?v=20260603`
- `https://bot-production-2dd7.up.railway.app/banner.png?v=20260603`
- `https://bot-production-2dd7.up.railway.app/download/huong-dan-toan-aas.docx`
- `https://bot-production-2dd7.up.railway.app/download/dieu-khoan-su-dung-toan-aas.pdf`

## Rules

- Do not test production website/downloads through GitHub Pages.
- Do not commit `.env`, database files, backup files, logs, cache folders, or test media.
- Keep public website assets served by FastAPI routes or relative paths.
- Use cache-busting query strings for logo/banner when replacing images.
