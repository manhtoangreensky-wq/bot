# VPS Video Edit Worker

This is a dedicated `video_edit_only` local-worker service. It must not replace or modify any Product Video `remote_worker` unit.

1. Create or verify the dedicated `toanaas` service account, then install the environment file as `/etc/toanaas-video-edit-worker.env` from `deploy/env/toanaas-video-edit-worker.env.example`; keep the file owned by root with mode `0600` because systemd reads it before dropping privileges.
2. Set `LOCAL_WORKER_BOT_URL` to the Railway bot's public HTTPS origin that is reachable from the VPS. Keep it separate from `TELEGRAM_API_BASE_URL=https://tg.toanaas.vn`; do not use a Railway private/internal hostname from an external VPS.
3. The `video_edit_only` scope requires its own `VIDEO_EDIT_WORKER_TOKEN` in both this VPS environment file and the Railway bot service. Set the same non-empty secret at both ends; this scope never falls back to `LOCAL_WORKER_TOKEN`. On the Railway bot service also confirm `LOCAL_WORKER_ENABLED=true` and `LOCAL_WORKER_POLL_ENABLED=true`. These are production ENV changes and require current Owner approval before applying them.
4. Set `TELEGRAM_BOT_TOKEN` to the bot token used for source download and final MP4 delivery. Because `tg.toanaas.vn` is a non-local Telegram API proxy, also set `TELEGRAM_API_PROXY_SECRET`; keep `TELEGRAM_API_PROXY_SECRET_HEADER=X-Toanaas-Proxy-Secret` unless the proxy is configured with another header.
5. Install FFmpeg, FFprobe and the configured font, then verify the example paths: `/usr/bin/ffmpeg`, `/usr/bin/ffprobe`, and `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`. Text watermark rendering depends on this font path.
6. Create `VIDEO_LOCAL_WORKSPACE_ROOT=/var/lib/toanaas/video-edit`, grant read/write access to `toanaas:toanaas`, and confirm it has enough free space for the source plus rendered output. The systemd unit runs as this same non-root account.
7. Keep `LOCAL_WORKER_JOB_SCOPE=video_edit_only`, `VIDEO_PROJECT_QUEUE_ENABLED=false`, and `LOCAL_VIDEO_FAKE_RENDERER_ENABLED=false`. This service only claims `video_local_edit` jobs and does not poll the Product Video project queue.
8. Install and manage `toanaas-video-edit-worker.service` independently. Review the queue and obtain Owner approval before any production restart; do not replace or restart a Product Video worker unit.

Before a restart, run the worker's local import/compile gate and confirm every required variable is non-empty without printing secret values. After start, the bot persists the authenticated worker scope in the heartbeat and rejects unknown or mismatched scopes.
