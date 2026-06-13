# TOAN AAS Deploy Workflow

Production website:

`https://www.toanaas.vn/`

Railway remains the backend/runtime host for webhook, health checks and internal routes when configured through `PUBLIC_BASE_URL`.

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
git add bot.py index.html LOGO.png banner.png TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V2.docx TOAN_AAS_DIEU_KHOAN_CHINH_SACH_DICH_VU_V2.pdf docs/public archive/public_docs_20260603 docs/DEPLOY_WORKFLOW.md
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

## Production Website Smoke Test

Test the official website domain for public website/download UX:

- `https://www.toanaas.vn/`
- `https://www.toanaas.vn/LOGO.png?v=20260603`
- `https://www.toanaas.vn/banner.png?v=20260603`
- `https://www.toanaas.vn/download/huong-dan-toan-aas.docx`
- `https://www.toanaas.vn/download/dieu-khoan-su-dung-toan-aas.pdf`

Backend/runtime smoke checks can still use the configured Railway `PUBLIC_BASE_URL`:

- `/health`
- `/asset_check`

## Rules

- Do not test production website/downloads through GitHub Pages.
- Do not commit `.env`, database files, backup files, logs, cache folders, or test media.
- Keep public website assets served by FastAPI routes or relative paths.
- Use cache-busting query strings for logo/banner when replacing images.
