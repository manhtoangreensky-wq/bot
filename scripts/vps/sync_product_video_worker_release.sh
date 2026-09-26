#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_SHA="${TARGET_SHA:-}"
STAGING_DIR="${STAGING_DIR:-}"
BOT_DIR="${BOT_DIR:-/opt/toanaas/bot}"
WORKER_DIR="${WORKER_DIR:-/opt/toanaas-worker}"
WORKER_ENV_FILE="${WORKER_ENV_FILE:-/etc/toanaas-worker.env}"
BOT_SERVICE_NAME="${BOT_SERVICE_NAME:-toanaas-bot.service}"
SERVICE_NAME="${SERVICE_NAME:-toanaas-worker-owner-product-video.service}"
NGINX_SERVICE_NAME="${NGINX_SERVICE_NAME:-nginx.service}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/health}"
HEALTH_ATTEMPTS="${HEALTH_ATTEMPTS:-120}"
HEALTH_SLEEP_SECONDS="${HEALTH_SLEEP_SECONDS:-2}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"
CURL_BIN="${CURL_BIN:-curl}"
RELEASE_REF="refs/deployments/bot-release"
BOT_RELEASE_REF="refs/deployments/product-video-bot-release"
WORKER_RELEASE_REF="refs/deployments/product-video-worker-release"

TRANSACTION_MARKER_PATH="${TRANSACTION_MARKER_PATH:-$STAGING_DIR/transaction_manifest.json}"
WORKER_PREPARED=0
BOT_HEALTHY=0
WORKER_ACTIVATED=0
WORKER_VERIFIED=0
TRANSACTION_COMMITTED=0

PREV_BOT_SHA=""
PREV_WORKER_SHA=""
PREV_BOT_MAIN_SHA=""
PREV_BOT_ORIGIN_MAIN_SHA=""
PREV_BOT_HEAD_SYMBOLIC=""
BOT_WAS_ACTIVE=0
WORKER_WAS_ACTIVE=0
ROLLBACK_ARMED=0

log() {
  printf '%s\n' "$*"
}

write_transaction_manifest() {
  local marker_file="${TRANSACTION_MARKER_PATH}"
  local marker_dir
  marker_dir="$(dirname "$marker_file")"
  mkdir -p "$marker_dir"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cat > "$marker_file" <<EOF
{
  "target_sha": "${TARGET_SHA}",
  "previous_bot_sha": "${PREV_BOT_SHA}",
  "previous_worker_sha": "${PREV_WORKER_SHA}",
  "worker_prepared": $( [[ "$WORKER_PREPARED" == "1" ]] && echo "true" || echo "false" ),
  "bot_healthy": $( [[ "$BOT_HEALTHY" == "1" ]] && echo "true" || echo "false" ),
  "worker_activated": $( [[ "$WORKER_ACTIVATED" == "1" ]] && echo "true" || echo "false" ),
  "worker_verified": $( [[ "$WORKER_VERIFIED" == "1" ]] && echo "true" || echo "false" ),
  "committed": $( [[ "$TRANSACTION_COMMITTED" == "1" ]] && echo "true" || echo "false" ),
  "timestamp_utc": "${ts}"
}
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  return 1
}

assert_exact_sha() {
  local repo="$1"
  local expected="$2"
  local label="$3"
  local actual
  actual="$(git -C "$repo" rev-parse HEAD)"
  if [[ "$actual" != "$expected" ]]; then
    fail "$label SHA mismatch: expected=$expected actual=$actual"
  fi
}

sync_locked_dependencies() {
  local repo="$1"
  local python="$repo/.venv/bin/python"
  [[ -x "$python" ]] || fail "$repo virtualenv Python is missing or not executable"
  [[ -f "$repo/requirements.lock" ]] || fail "$repo/requirements.lock is missing"
  "$python" -m pip install --require-hashes -r "$repo/requirements.lock"
  "$python" -m pip check
}

restore_repo() {
  local repo="$1"
  local previous_sha="$2"
  local label="$3"
  [[ -n "$previous_sha" ]] || return 0
  git -C "$repo" checkout --detach "$previous_sha"
  assert_exact_sha "$repo" "$previous_sha" "$label rollback"
}

restore_service_state() {
  local service="$1"
  local was_active="$2"
  if [[ "$was_active" == "1" ]]; then
    "$SYSTEMCTL_BIN" start "$service"
  else
    "$SYSTEMCTL_BIN" stop "$service"
  fi
}

restore_bot_refs() {
  local main_sha="${PREV_BOT_MAIN_SHA:-$PREV_BOT_SHA}"
  local origin_main_sha="${PREV_BOT_ORIGIN_MAIN_SHA:-$PREV_BOT_SHA}"
  git -C "$BOT_DIR" update-ref refs/heads/main "$main_sha"
  git -C "$BOT_DIR" update-ref refs/remotes/origin/main "$origin_main_sha"
  if [[ -n "$PREV_BOT_HEAD_SYMBOLIC" ]]; then
    git -C "$BOT_DIR" symbolic-ref HEAD "$PREV_BOT_HEAD_SYMBOLIC"
    git -C "$BOT_DIR" read-tree "$PREV_BOT_SHA"
  fi
}

rollback_transaction() {
  local original_status="${1:-1}"
  local rollback_failed=0
  trap - ERR INT TERM
  set +e

  if [[ "$ROLLBACK_ARMED" != "1" ]]; then
    exit "$original_status"
  fi

  log "ROLLBACK_STARTED"
  "$SYSTEMCTL_BIN" stop "$SERVICE_NAME" || rollback_failed=1

  restore_repo "$BOT_DIR" "$PREV_BOT_SHA" "bot" || rollback_failed=1
  restore_bot_refs || rollback_failed=1
  sync_locked_dependencies "$BOT_DIR" || rollback_failed=1
  restore_repo "$WORKER_DIR" "$PREV_WORKER_SHA" "worker" || rollback_failed=1
  sync_locked_dependencies "$WORKER_DIR" || rollback_failed=1

  if [[ "$BOT_WAS_ACTIVE" == "1" ]]; then
    "$SYSTEMCTL_BIN" restart "$BOT_SERVICE_NAME" || rollback_failed=1
  else
    "$SYSTEMCTL_BIN" stop "$BOT_SERVICE_NAME" || rollback_failed=1
  fi
  restore_service_state "$SERVICE_NAME" "$WORKER_WAS_ACTIVE" || rollback_failed=1

  if [[ "$rollback_failed" == "0" ]]; then
    log "ROLLBACK_COMPLETED"
  else
    log "ROLLBACK_COMPLETED_WITH_ERRORS"
  fi
  TRANSACTION_COMMITTED=0
  write_transaction_manifest
  exit "$original_status"
}

validate_inputs_and_bundle() {
  [[ "$TARGET_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || fail "TARGET_SHA must be a 40-character commit SHA"
  [[ -d "$STAGING_DIR" ]] || fail "staging directory does not exist: $STAGING_DIR"
  [[ -f "$STAGING_DIR/release.bundle" ]] || fail "release bundle is missing"
  [[ -f "$STAGING_DIR/checksums.sha256" ]] || fail "release checksums are missing"

  (
    cd "$STAGING_DIR"
    sha256sum -c checksums.sha256
  )
  (
    cd "$BOT_DIR"
    git bundle verify "$STAGING_DIR/release.bundle" >/dev/null
  )

  local advertised_sha
  advertised_sha="$( ( cd "$BOT_DIR" && git bundle list-heads "$STAGING_DIR/release.bundle" "$RELEASE_REF" ) | awk 'NR == 1 {print $1}')"
  if [[ "$advertised_sha" != "$TARGET_SHA" ]]; then
    fail "bundle target mismatch: expected=$TARGET_SHA advertised=${advertised_sha:-missing}"
  fi
}

require_repo_and_runtime() {
  local repo="$1"
  local label="$2"
  [[ -d "$repo" ]] || fail "$label repo does not exist: $repo"
  git -C "$repo" rev-parse --git-dir >/dev/null
  [[ -x "$repo/.venv/bin/python" ]] || fail "$label virtualenv is missing"
}

assert_worker_worktree_safe() {
  local status
  status="$(git -C "$WORKER_DIR" status --porcelain=v1 --untracked-files=all)"
  [[ -z "$status" ]] || fail "worker worktree is not clean; tracked and untracked WIP are protected"
}

assert_bot_worktree_safe() {
  git -C "$BOT_DIR" diff --quiet HEAD -- || fail "bot tracked worktree is dirty"
  git -C "$BOT_DIR" diff --cached --quiet || fail "bot index is dirty"
}

fetch_verified_release() {
  local repo="$1"
  local destination_ref="$2"
  git -C "$repo" fetch "$STAGING_DIR/release.bundle" "+$RELEASE_REF:$destination_ref"
  local fetched_sha
  fetched_sha="$(git -C "$repo" rev-parse "$destination_ref")"
  if [[ "$fetched_sha" != "$TARGET_SHA" ]]; then
    fail "fetched release mismatch for $repo: expected=$TARGET_SHA actual=$fetched_sha"
  fi
  git -C "$repo" cat-file -e "$TARGET_SHA^{commit}"
}

assert_bot_untracked_files_do_not_collide() {
  local path
  while IFS= read -r -d '' path; do
    if git -C "$BOT_DIR" cat-file -e "$TARGET_SHA:$path" 2>/dev/null; then
      fail "bot untracked path would be overwritten by target release: $path"
    fi
  done < <(git -C "$BOT_DIR" ls-files --others --exclude-standard -z)
}

assert_service_contract() {
  local unit
  unit="$("$SYSTEMCTL_BIN" cat "$SERVICE_NAME")" || fail "owner Product Video worker service unit is missing"
  [[ "$unit" == *"WorkingDirectory=$WORKER_DIR"* ]] || fail "worker service WorkingDirectory does not use $WORKER_DIR"
  [[ "$unit" == *"$WORKER_DIR/.venv/bin/python $WORKER_DIR/remote_worker.py --owner-product-video"* ]] || fail "worker service ExecStart is not the dedicated owner Product Video worker"
  [[ -f "$WORKER_ENV_FILE" ]] || fail "worker environment file is missing"
}

create_backup_refs() {
  local timestamp="$1"
  git -C "$BOT_DIR" update-ref "refs/backups/product-video-deploy/bot-$TARGET_SHA-$timestamp" "$PREV_BOT_SHA"
  git -C "$WORKER_DIR" update-ref "refs/backups/product-video-deploy/worker-$TARGET_SHA-$timestamp" "$PREV_WORKER_SHA"
}

switch_to_target() {
  local repo="$1"
  local label="$2"
  git -C "$repo" checkout --detach "$TARGET_SHA"
  assert_exact_sha "$repo" "$TARGET_SHA" "$label target"
  git -C "$repo" diff --quiet HEAD -- || fail "$label tracked worktree changed after target checkout"
  git -C "$repo" diff --cached --quiet || fail "$label index changed after target checkout"
}

prove_bot_health() {
  local health_json=""
  local attempt
  for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
    if health_json="$("$CURL_BIN" -sSf "$HEALTH_URL")"; then
      break
    fi
    sleep "$HEALTH_SLEEP_SECONDS"
  done
  [[ -n "$health_json" ]] || fail "bot health endpoint failed"
  printf '%s' "$health_json" | "$BOT_DIR/.venv/bin/python" -c 'import json,sys; payload=json.load(sys.stdin); assert payload.get("status") == "ok"'
  assert_exact_sha "$BOT_DIR" "$TARGET_SHA" "bot target"
  BOT_HEALTHY=1
  write_transaction_manifest
  log "BOT_TARGET_HEALTH_PROVEN sha=$TARGET_SHA"
}

prove_worker_capability_and_safe_heartbeat() {
  local probe_output
  if ! probe_output="$({
    set -a
    source "$WORKER_ENV_FILE"
    set +a
    cd "$WORKER_DIR"
    "$WORKER_DIR/.venv/bin/python" -c 'import remote_worker; required = {"owner_product_video", "canonical_multiscene_b13_r18c_v1"}; capabilities = set(remote_worker.product_video_worker_capabilities()); missing = sorted(required - capabilities); assert not missing, missing'
    "$WORKER_DIR/.venv/bin/python" remote_worker.py --ping --dry-run --owner-product-video
  } 2>&1)"; then
    printf '%s\n' "$probe_output" >&2
    fail "safe worker dry-run probe failed"
  fi
  printf '%s\n' "$probe_output"
  [[ "$probe_output" == *"ping: OK"* ]] || fail "safe worker dry-run probe did not report ping success"
  [[ "$probe_output" == *"claim skipped because dry-run: yes"* ]] || fail "safe worker probe did not prove claim suppression"
}

prepare_product_video_worker_release() {
  validate_inputs_and_bundle
  require_repo_and_runtime "$BOT_DIR" "bot"
  require_repo_and_runtime "$WORKER_DIR" "worker"
  assert_worker_worktree_safe
  assert_bot_worktree_safe
  assert_service_contract

  PREV_BOT_SHA="$(git -C "$BOT_DIR" rev-parse HEAD)"
  PREV_WORKER_SHA="$(git -C "$WORKER_DIR" rev-parse HEAD)"
  PREV_BOT_MAIN_SHA="$(git -C "$BOT_DIR" rev-parse --verify refs/heads/main 2>/dev/null || true)"
  PREV_BOT_ORIGIN_MAIN_SHA="$(git -C "$BOT_DIR" rev-parse --verify refs/remotes/origin/main 2>/dev/null || true)"
  PREV_BOT_HEAD_SYMBOLIC="$(git -C "$BOT_DIR" symbolic-ref -q HEAD 2>/dev/null || true)"
  if "$SYSTEMCTL_BIN" is-active --quiet "$BOT_SERVICE_NAME"; then BOT_WAS_ACTIVE=1; fi
  if "$SYSTEMCTL_BIN" is-active --quiet "$SERVICE_NAME"; then WORKER_WAS_ACTIVE=1; fi

  fetch_verified_release "$BOT_DIR" "$BOT_RELEASE_REF"
  fetch_verified_release "$WORKER_DIR" "$WORKER_RELEASE_REF"
  assert_bot_untracked_files_do_not_collide

  local timestamp
  timestamp="$(date -u +%Y%m%d%H%M%S)"
  create_backup_refs "$timestamp"
  ROLLBACK_ARMED=1
  trap 'rollback_transaction $?' ERR
  trap 'rollback_transaction 130' INT
  trap 'rollback_transaction 143' TERM

  "$SYSTEMCTL_BIN" stop "$SERVICE_NAME"
  switch_to_target "$WORKER_DIR" "worker"
  assert_exact_sha "$WORKER_DIR" "$TARGET_SHA" "worker target"
  sync_locked_dependencies "$WORKER_DIR"
  WORKER_PREPARED=1
  write_transaction_manifest
}

activate_product_video_worker_release() {
  BOT_HEALTHY=1
  assert_exact_sha "$BOT_DIR" "$TARGET_SHA" "bot target"
  prove_worker_capability_and_safe_heartbeat

  "$SYSTEMCTL_BIN" start "$SERVICE_NAME"
  "$SYSTEMCTL_BIN" is-active --quiet "$SERVICE_NAME" || fail "owner Product Video worker service is not active"
  WORKER_ACTIVATED=1
  assert_exact_sha "$WORKER_DIR" "$TARGET_SHA" "worker target"
  WORKER_VERIFIED=1
  write_transaction_manifest
  log "WORKER_TARGET_HEALTH_PROVEN sha=$TARGET_SHA capabilities=owner_product_video,canonical_multiscene_b13_r18c_v1"
}

commit_product_video_release_transaction() {
  TRANSACTION_COMMITTED=1
  write_transaction_manifest
  ROLLBACK_ARMED=0
  trap - ERR INT TERM
  log "PRODUCT_VIDEO_DEPLOY_TRANSACTION_COMMITTED bot_sha=$TARGET_SHA worker_sha=$TARGET_SHA"
}

main() {
  prepare_product_video_worker_release

  switch_to_target "$BOT_DIR" "bot"
  assert_exact_sha "$BOT_DIR" "$TARGET_SHA" "bot target"
  sync_locked_dependencies "$BOT_DIR"

  "$SYSTEMCTL_BIN" restart "$BOT_SERVICE_NAME"
  "$SYSTEMCTL_BIN" is-active --quiet "$NGINX_SERVICE_NAME" || fail "nginx service is not active"
  prove_bot_health
  activate_product_video_worker_release
  commit_product_video_release_transaction
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
