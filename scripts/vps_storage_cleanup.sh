#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${ARTIFACT_VPS_BASE_DIR:-/opt/toanaas-storage}"
TMP_TTL_HOURS="${ARTIFACT_TMP_TTL_HOURS:-6}"
ARTIFACT_TTL_HOURS="${ARTIFACT_TTL_HOURS:-72}"
DRY_RUN="${STORAGE_CLEANUP_DRY_RUN:-1}"

if [[ ! -d "$BASE_DIR" ]]; then
  echo "missing_base_dir=$BASE_DIR"
  exit 0
fi

case "$BASE_DIR" in
  /opt/toanaas-storage|/opt/toanaas-storage/*) ;;
  *)
    echo "refuse_unsafe_base_dir=$BASE_DIR"
    exit 2
    ;;
esac

delete_or_print() {
  local ttl_minutes="$1"
  local target="$2"
  if [[ ! -d "$target" ]]; then
    return 0
  fi
  if [[ "$DRY_RUN" == "1" || "$DRY_RUN" == "true" ]]; then
    find "$target" -type f \
      \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.webm' -o -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' -o -iname '*.srt' -o -iname '*.vtt' -o -iname '*.ass' -o -iname '*.tmp' -o -iname '*.json' -o -iname '*.txt' -o -iname '*.zip' \) \
      -mmin +"$ttl_minutes" -print
  else
    find "$target" -type f \
      \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.webm' -o -iname '*.mp3' -o -iname '*.wav' -o -iname '*.m4a' -o -iname '*.srt' -o -iname '*.vtt' -o -iname '*.ass' -o -iname '*.tmp' -o -iname '*.json' -o -iname '*.txt' -o -iname '*.zip' \) \
      -mmin +"$ttl_minutes" -delete
  fi
}

tmp_ttl_minutes=$(( TMP_TTL_HOURS * 60 ))
artifact_ttl_minutes=$(( ARTIFACT_TTL_HOURS * 60 ))

echo "storage_cleanup base=$BASE_DIR dry_run=$DRY_RUN tmp_ttl_hours=$TMP_TTL_HOURS artifact_ttl_hours=$ARTIFACT_TTL_HOURS"
delete_or_print "$tmp_ttl_minutes" "$BASE_DIR/tmp"
for dir in worker_results artifacts music subdub video cache; do
  delete_or_print "$artifact_ttl_minutes" "$BASE_DIR/$dir"
done
