#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---dry-run}"
ROOT="${WORKER_TMP_DIR:-/tmp}"

if [[ "$MODE" != "--dry-run" && "$MODE" != "--apply" ]]; then
  echo "Usage: WORKER_TMP_DIR=/tmp $0 --dry-run|--apply" >&2
  exit 2
fi

case "$ROOT" in
  /tmp|/tmp/*|/var/tmp|/var/tmp/*)
    ;;
  *)
    echo "Refusing unsafe temp root: $ROOT" >&2
    exit 3
    ;;
esac

if [[ ! -d "$ROOT" ]]; then
  echo "Temp root not found: $ROOT"
  exit 0
fi

PATTERNS=(
  "remote_worker_job_*.mp4"
  "remote_worker_canary_*.mp4"
  "remote_worker_admin_canary_*.mp4"
  "remote_worker_admin_video_*.mp4"
  "toanaas-worker-*"
)

echo "TOAN AAS worker temp cleanup"
echo "Root: $ROOT"
echo "Mode: $MODE"

for pattern in "${PATTERNS[@]}"; do
  if [[ "$MODE" == "--apply" ]]; then
    find "$ROOT" -maxdepth 2 -name "$pattern" -mtime +1 -print -exec rm -rf {} +
  else
    find "$ROOT" -maxdepth 2 -name "$pattern" -mtime +1 -print
  fi
done
