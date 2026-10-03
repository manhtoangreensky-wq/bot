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
PROC_DIR="${PROC_DIR:-/proc}"
PRODUCTION_BOT_PYTHON_EXACT_PATH="$BOT_DIR/.venv/bin/python"
RELEASE_REF="refs/deployments/bot-release"
BOT_RELEASE_REF="refs/deployments/product-video-bot-release"
WORKER_RELEASE_REF="refs/deployments/product-video-worker-release"

SUBDUB_SERVICE_NAME="${SUBDUB_SERVICE_NAME:-toanaas-worker-subdub.service}"
SUBDUB_DAEMON_REL_PATH="services/subdub_worker_daemon.py"
SUBDUB_WAS_ACTIVE=0
PREV_SUBDUB_PID=""
SUBDUB_STOPPED=0
SUBDUB_DOCTOR_PASS=0
SUBDUB_ACTIVATED=0
SUBDUB_NEW_PID=""
SUBDUB_VERIFIED=0

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
  "subdub_service_name": "${SUBDUB_SERVICE_NAME}",
  "subdub_was_active": $( [[ "$SUBDUB_WAS_ACTIVE" == "1" ]] && echo "true" || echo "false" ),
  "previous_subdub_pid": "${PREV_SUBDUB_PID}",
  "subdub_stopped": $( [[ "$SUBDUB_STOPPED" == "1" ]] && echo "true" || echo "false" ),
  "subdub_doctor_pass": $( [[ "$SUBDUB_DOCTOR_PASS" == "1" ]] && echo "true" || echo "false" ),
  "subdub_activated": $( [[ "$SUBDUB_ACTIVATED" == "1" ]] && echo "true" || echo "false" ),
  "subdub_new_pid": "${SUBDUB_NEW_PID}",
  "subdub_verified": $( [[ "$SUBDUB_VERIFIED" == "1" ]] && echo "true" || echo "false" ),
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
  "$SYSTEMCTL_BIN" stop "$SUBDUB_SERVICE_NAME" || rollback_failed=1

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

  if [[ "$SUBDUB_WAS_ACTIVE" == "1" ]]; then
    "$SYSTEMCTL_BIN" start "$SUBDUB_SERVICE_NAME" || rollback_failed=1
    if "$SYSTEMCTL_BIN" is-active --quiet "$SUBDUB_SERVICE_NAME"; then
      local rb_pid
      rb_pid="$("$SYSTEMCTL_BIN" show -p MainPID --value "$SUBDUB_SERVICE_NAME" 2>/dev/null || echo "")"
      if [[ -z "$rb_pid" || "$rb_pid" == "0" ]]; then
        rollback_failed=1
      fi
    else
      rollback_failed=1
    fi
  else
    "$SYSTEMCTL_BIN" stop "$SUBDUB_SERVICE_NAME" || rollback_failed=1
  fi

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

get_bot_python() {
  local exact_python="$BOT_DIR/.venv/bin/python"
  if [[ -n "${BOT_PYTHON:-}" && "$BOT_PYTHON" != "$exact_python" ]]; then
    fail "Arbitrary BOT_PYTHON override is forbidden: ambient BOT_PYTHON='$BOT_PYTHON' does not match exact production path '$exact_python'"
    return 1
  fi
  if [[ ! -f "$exact_python" ]]; then
    fail "Exact Bot venv Python is missing: $exact_python"
    return 1
  fi
  if [[ ! -x "$exact_python" ]]; then
    fail "Exact Bot venv Python is not executable: $exact_python"
    return 1
  fi
  echo "$exact_python"
}

get_subdub_service_env_file() {
  local unit
  if ! unit="$("$SYSTEMCTL_BIN" cat "$SUBDUB_SERVICE_NAME" 2>/dev/null)"; then
    fail "SubDub worker service unit ($SUBDUB_SERVICE_NAME) is missing"
    return 1
  fi
  local env_file=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*EnvironmentFile=(-)?([^[:space:]]+) ]]; then
      env_file="${BASH_REMATCH[2]}"
      break
    fi
  done <<< "$unit"
  if [[ -z "$env_file" ]]; then
    fail "SubDub worker service unit does not declare EnvironmentFile"
    return 1
  fi
  if [[ ! -f "$env_file" ]]; then
    fail "SubDub worker EnvironmentFile is missing: $env_file"
    return 1
  fi
  echo "$env_file"
}

# Documented Canonical Precedence for SubDub Queue DB:
# 1. DB_PATH (bot.py primary)
# 2. DB_FILE (bot.py fallback / services/video_edit_state_store)
# 3. DATABASE_PATH (services/video_trace_state)
# 4. SQLITE_DB_PATH (services/video_provider_router)
#
# Derived strictly from the SubDub worker service unit's EnvironmentFile.
# Filesystem guessing fallback is strictly forbidden (FILESYSTEM_GUESS_FALLBACK_ALLOWED=NO).
resolve_subdub_db_path() {
  local env_file="${1:-}"
  if [[ -z "$env_file" ]]; then
    env_file="$(get_subdub_service_env_file)" || return 1
  fi
  if [[ ! -f "$env_file" ]]; then
    fail "Cannot resolve SubDub DB path: environment file does not exist: $env_file"
    return 1
  fi

  extract_db_var() {
    local var_name="$1"
    local file="$2"
    grep -E "^[[:space:]]*${var_name}=" "$file" 2>/dev/null | tail -n 1 | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//'
  }

  check_db_var_ambiguity() {
    local var_name="$1"
    local file="$2"
    local distinct_count
    distinct_count="$(grep -E "^[[:space:]]*${var_name}=" "$file" 2>/dev/null | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//' | sort -u | grep -v '^$' | wc -l)"
    if [[ "$distinct_count" -gt 1 ]]; then
      return 1
    fi
    return 0
  }

  for check_var in DB_PATH DB_FILE DATABASE_PATH SQLITE_DB_PATH; do
    if ! check_db_var_ambiguity "$check_var" "$env_file"; then
      fail "SubDub queue authority ambiguity: variable '$check_var' has conflicting values in $env_file"
      return 1
    fi
  done

  local val_db_path
  local val_db_file
  local val_database_path
  local val_sqlite_db_path

  val_db_path="$(extract_db_var "DB_PATH" "$env_file")"
  val_db_file="$(extract_db_var "DB_FILE" "$env_file")"
  val_database_path="$(extract_db_var "DATABASE_PATH" "$env_file")"
  val_sqlite_db_path="$(extract_db_var "SQLITE_DB_PATH" "$env_file")"

  local chosen_path=""
  local chosen_source=""

  # Documented Canonical Precedence: DB_PATH > DB_FILE > DATABASE_PATH > SQLITE_DB_PATH
  if [[ -n "$val_db_path" ]]; then
    chosen_path="$val_db_path"
    chosen_source="DB_PATH"
  elif [[ -n "$val_db_file" ]]; then
    chosen_path="$val_db_file"
    chosen_source="DB_FILE"
  elif [[ -n "$val_database_path" ]]; then
    chosen_path="$val_database_path"
    chosen_source="DATABASE_PATH"
  elif [[ -n "$val_sqlite_db_path" ]]; then
    chosen_path="$val_sqlite_db_path"
    chosen_source="SQLITE_DB_PATH"
  fi

  if [[ -z "$chosen_path" ]]; then
    fail "SubDub queue authority missing: no canonical DB variable (DB_PATH, DB_FILE, DATABASE_PATH, SQLITE_DB_PATH) found in $env_file"
    return 1
  fi

  # Filesystem guessing fallback is strictly forbidden
  echo "$chosen_path"
}

assert_subdub_service_contract() {
  local unit
  if ! unit="$("$SYSTEMCTL_BIN" cat "$SUBDUB_SERVICE_NAME" 2>/dev/null)"; then
    fail "SubDub worker service unit ($SUBDUB_SERVICE_NAME) is missing"
    return 1
  fi
  if [[ "$unit" != *"WorkingDirectory=$BOT_DIR"* ]]; then
    fail "SubDub worker service WorkingDirectory does not use $BOT_DIR"
    return 1
  fi
  if [[ "$unit" != *"$BOT_DIR/.venv/bin/python -u services/subdub_worker_daemon.py"* && "$unit" != *"$BOT_DIR/.venv/bin/python -u $BOT_DIR/services/subdub_worker_daemon.py"* ]]; then
    fail "SubDub worker service ExecStart is not $BOT_DIR/.venv/bin/python -u services/subdub_worker_daemon.py"
    return 1
  fi
  local py_bin
  py_bin="$(get_bot_python)" || return 1
  if [[ ! -f "$BOT_DIR/$SUBDUB_DAEMON_REL_PATH" ]]; then
    fail "SubDub worker daemon source is missing: $BOT_DIR/$SUBDUB_DAEMON_REL_PATH"
    return 1
  fi
  get_subdub_service_env_file >/dev/null || return 1
}

assert_subdub_queue_safe() {
  local env_file
  env_file="$(get_subdub_service_env_file)" || return 1

  local db_path=""
  db_path="$(resolve_subdub_db_path "$env_file")" || {
    fail "SubDub queue authority missing: canonical DB path could not be resolved from $env_file"
    return 1
  }

  log "QUEUE_DB_SOURCE=SUBDUB_SYSTEMD_ENVIRONMENT_FILE"
  log "SUBDUB_QUEUE_DB_DERIVED_FROM_SERVICE_ENVIRONMENT_FILE=YES env_file=$env_file db_path=$db_path"

  if [[ -z "$db_path" ]]; then
    fail "SubDub queue authority missing: resolved DB path is empty"
    return 1
  fi
  log "QUEUE_DB_PATH_NONEMPTY=YES"

  if [[ ! -f "$db_path" ]]; then
    fail "SubDub queue authority missing: DB file does not exist: $db_path"
    return 1
  fi
  log "QUEUE_DB_FILE_EXISTS=YES"

  local py_bin
  py_bin="$(get_bot_python)" || return 1

  local query_result
  query_result="$("$py_bin" -c "
import sqlite3, sys
try:
    conn = sqlite3.connect('$db_path')
    tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='subdub_worker_jobs'\").fetchall()]
    if not tables:
        print('TABLE_MISSING')
        sys.exit(0)
    row = conn.execute(\"SELECT count(*) FROM subdub_worker_jobs WHERE status = 'processing'\").fetchone()
    print(f'COUNT:{row[0] if row else 0}')
except Exception as e:
    print(f'ERROR:{e}')
    sys.exit(1)
" 2>&1)" || { fail "SubDub queue safety query failed (Python error): $query_result"; return 1; }

  if [[ "$query_result" == "TABLE_MISSING" ]]; then
    fail "SubDub queue authority missing: subdub_worker_jobs table does not exist in $db_path"
    return 1
  fi

  if [[ "$query_result" == ERROR:* ]]; then
    fail "SubDub queue safety query error: $query_result"
    return 1
  fi

  log "QUEUE_TABLE_EXISTS=YES"
  log "QUEUE_QUERY_SUCCESS=YES"

  local active_count="${query_result#COUNT:}"
  if ! [[ "$active_count" =~ ^[0-9]+$ ]]; then
    fail "SubDub queue safety query returned non-numeric result: $query_result"
    return 1
  fi

  if [[ "$active_count" -gt 0 ]]; then
    fail "SubDub queue safety violation: $active_count processing jobs in flight before deploy"
    return 1
  fi
}

run_subdub_doctor() {
  local py_bin
  py_bin="$(get_bot_python)"
  local doctor_output
  if ! doctor_output="$("$py_bin" -u "$BOT_DIR/$SUBDUB_DAEMON_REL_PATH" --dry-run 2>&1)"; then
    printf '%s\n' "$doctor_output" >&2
    fail "SubDub worker dry-run doctor failed"
  fi
  printf '%s\n' "$doctor_output"
  [[ "$doctor_output" == *"DOCTOR_OK"* ]] || fail "SubDub worker dry-run doctor did not report DOCTOR_OK"
  SUBDUB_DOCTOR_PASS=1
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
  local py_bin
  py_bin="$(get_bot_python)"
  printf '%s' "$health_json" | "$py_bin" -c 'import json,sys; payload=json.load(sys.stdin); assert payload.get("status") == "ok"'
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
  assert_subdub_service_contract
  assert_subdub_queue_safe

  PREV_BOT_SHA="$(git -C "$BOT_DIR" rev-parse HEAD)"
  PREV_WORKER_SHA="$(git -C "$WORKER_DIR" rev-parse HEAD)"
  PREV_BOT_MAIN_SHA="$(git -C "$BOT_DIR" rev-parse --verify refs/heads/main 2>/dev/null || true)"
  PREV_BOT_ORIGIN_MAIN_SHA="$(git -C "$BOT_DIR" rev-parse --verify refs/remotes/origin/main 2>/dev/null || true)"
  PREV_BOT_HEAD_SYMBOLIC="$(git -C "$BOT_DIR" symbolic-ref -q HEAD 2>/dev/null || true)"
  if "$SYSTEMCTL_BIN" is-active --quiet "$BOT_SERVICE_NAME"; then BOT_WAS_ACTIVE=1; fi
  if "$SYSTEMCTL_BIN" is-active --quiet "$SERVICE_NAME"; then WORKER_WAS_ACTIVE=1; fi
  if "$SYSTEMCTL_BIN" is-active --quiet "$SUBDUB_SERVICE_NAME"; then
    SUBDUB_WAS_ACTIVE=1
    PREV_SUBDUB_PID="$("$SYSTEMCTL_BIN" show -p MainPID --value "$SUBDUB_SERVICE_NAME" 2>/dev/null || echo "")"
  else
    SUBDUB_WAS_ACTIVE=0
    PREV_SUBDUB_PID=""
  fi

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
  if [[ "$SUBDUB_WAS_ACTIVE" == "1" ]]; then
    "$SYSTEMCTL_BIN" stop "$SUBDUB_SERVICE_NAME" || fail "Failed to stop SubDub worker service"
    SUBDUB_STOPPED=1
  fi
  switch_to_target "$WORKER_DIR" "worker"
  assert_exact_sha "$WORKER_DIR" "$TARGET_SHA" "worker target"
  sync_locked_dependencies "$WORKER_DIR"
  WORKER_PREPARED=1
  write_transaction_manifest
}

activate_and_verify_subdub_worker() {
  run_subdub_doctor

  if [[ "$SUBDUB_WAS_ACTIVE" == "1" ]]; then
    "$SYSTEMCTL_BIN" start "$SUBDUB_SERVICE_NAME" || { fail "Failed to start SubDub worker service"; return 1; }
    "$SYSTEMCTL_BIN" is-active --quiet "$SUBDUB_SERVICE_NAME" || { fail "SubDub worker service is not active after start"; return 1; }
    SUBDUB_ACTIVATED=1

    local new_pid=""
    local attempt
    for ((attempt = 1; attempt <= 30; attempt++)); do
      new_pid="$("$SYSTEMCTL_BIN" show -p MainPID --value "$SUBDUB_SERVICE_NAME" 2>/dev/null || echo "")"
      if [[ -n "$new_pid" && "$new_pid" != "0" ]]; then
        break
      fi
      sleep 0.5
    done
    [[ -n "$new_pid" && "$new_pid" != "0" ]] || { fail "SubDub worker MainPID is 0 or missing"; return 1; }
    SUBDUB_NEW_PID="$new_pid"

    if [[ -n "$PREV_SUBDUB_PID" && "$PREV_SUBDUB_PID" != "0" ]]; then
      if [[ "$new_pid" == "$PREV_SUBDUB_PID" ]]; then
        fail "SubDub worker PID did not change after reload (old=$PREV_SUBDUB_PID new=$new_pid)"
        return 1
      fi
    fi

    [[ -d "$PROC_DIR/$new_pid" ]] || { fail "SubDub worker /proc/$new_pid directory is missing: cannot verify process"; return 1; }

    local proc_cwd=""
    proc_cwd="$(readlink -f "$PROC_DIR/$new_pid/cwd" 2>/dev/null)" || true
    [[ -n "$proc_cwd" ]] || { fail "SubDub worker /proc/$new_pid/cwd is unreadable"; return 1; }
    local canonical_bot_dir
    canonical_bot_dir="$(cd "$BOT_DIR" && pwd -P)"
    [[ "$proc_cwd" == "$canonical_bot_dir" ]] || { fail "SubDub worker process cwd ($proc_cwd) does not match $canonical_bot_dir"; return 1; }

    local proc_cmdline=""
    proc_cmdline="$(tr '\0' ' ' < "$PROC_DIR/$new_pid/cmdline" 2>/dev/null)" || true
    [[ -n "$proc_cmdline" ]] || { fail "SubDub worker /proc/$new_pid/cmdline is unreadable"; return 1; }
    [[ "$proc_cmdline" == *"services/subdub_worker_daemon.py"* ]] || { fail "SubDub worker process cmdline ($proc_cmdline) does not execute services/subdub_worker_daemon.py"; return 1; }

    assert_exact_sha "$BOT_DIR" "$TARGET_SHA" "bot target while subdub active"
    SUBDUB_VERIFIED=1
    log "SUBDUB_WORKER_TARGET_HEALTH_PROVEN sha=$TARGET_SHA pid=$new_pid service=$SUBDUB_SERVICE_NAME"
  else
    if "$SYSTEMCTL_BIN" is-active --quiet "$SUBDUB_SERVICE_NAME"; then
      fail "SubDub worker was inactive pre-deploy but is active unexpectedly"
      return 1
    fi
    SUBDUB_VERIFIED=1
    log "SUBDUB_WORKER_PRESERVED_INACTIVE sha=$TARGET_SHA service=$SUBDUB_SERVICE_NAME"
  fi
  write_transaction_manifest
}

handle_subdub_reconciliation_failure() {
  local stage="$1"
  local reason="$2"
  local prev_was_active="${3:-0}"
  local prev_pid="${4:-}"
  local mutation_started="${5:-0}"

  local curr_active=0
  if "$SYSTEMCTL_BIN" is-active --quiet "$SUBDUB_SERVICE_NAME" 2>/dev/null; then
    curr_active=1
  fi
  local curr_pid=""
  curr_pid="$("$SYSTEMCTL_BIN" show -p MainPID --value "$SUBDUB_SERVICE_NAME" 2>/dev/null || echo "")"

  log "RECONCILIATION_FAILURE_CAPTURED stage=$stage reason=\"$reason\" prev_active=$prev_was_active prev_pid=${prev_pid:-none} mutation_started=$mutation_started curr_active=$curr_active curr_pid=${curr_pid:-none}"

  if [[ "$mutation_started" == "1" ]]; then
    log "RECONCILIATION_POST_RESTART_RECOVERY_STARTED stage=$stage"
    if [[ "$prev_was_active" == "1" ]]; then
      local recovery_proven=0
      local rec_pid=""
      # Best-provable recovery: attempt restart and full verification of running process
      if "$SYSTEMCTL_BIN" restart "$SUBDUB_SERVICE_NAME" 2>/dev/null && "$SYSTEMCTL_BIN" is-active --quiet "$SUBDUB_SERVICE_NAME" 2>/dev/null; then
        rec_pid="$("$SYSTEMCTL_BIN" show -p MainPID --value "$SUBDUB_SERVICE_NAME" 2>/dev/null || echo "")"
        if [[ -n "$rec_pid" && "$rec_pid" != "0" && -d "$PROC_DIR/$rec_pid" ]]; then
          local rec_cwd=""
          rec_cwd="$(readlink -f "$PROC_DIR/$rec_pid/cwd" 2>/dev/null)" || true
          local canonical_bot_dir
          canonical_bot_dir="$(cd "$BOT_DIR" && pwd -P)"
          local rec_cmdline=""
          rec_cmdline="$(tr '\0' ' ' < "$PROC_DIR/$rec_pid/cmdline" 2>/dev/null)" || true
          if [[ "$rec_cwd" == "$canonical_bot_dir" && "$rec_cmdline" == *"services/subdub_worker_daemon.py"* ]]; then
            recovery_proven=1
          fi
        fi
      fi

      if [[ "$recovery_proven" == "1" ]]; then
        log "RECONCILIATION_ROLLBACK_RESTORED: service recovered to verified active process (stage=$stage rec_pid=$rec_pid)"
      else
        log "RECONCILIATION_ROLLBACK_DEGRADED: could not prove active service restoration after post-restart verification failure (stage=$stage)"
      fi
    else
      # Service was originally inactive, restore inactive state
      "$SYSTEMCTL_BIN" stop "$SUBDUB_SERVICE_NAME" 2>/dev/null || true
      if ! "$SYSTEMCTL_BIN" is-active --quiet "$SUBDUB_SERVICE_NAME" 2>/dev/null; then
        log "RECONCILIATION_ROLLBACK_RESTORED: service restored to prior inactive state"
      else
        log "RECONCILIATION_ROLLBACK_DEGRADED: could not restore prior inactive state"
      fi
    fi
  else
    log "RECONCILIATION_PRE_MUTATION_FAILURE: no service mutation occurred (stage=$stage)"
  fi

  fail "SubDub worker reconciliation failed at stage '$stage': $reason"
  return 1
}

reconcile_subdub_worker_already_deployed() {
  assert_subdub_service_contract || return 1
  run_subdub_doctor || return 1

  if "$SYSTEMCTL_BIN" is-active --quiet "$SUBDUB_SERVICE_NAME"; then
    log "SubDub worker is active: performing queue check and governed reload"
    assert_subdub_queue_safe || return 1

    local prev_pid=""
    prev_pid="$("$SYSTEMCTL_BIN" show -p MainPID --value "$SUBDUB_SERVICE_NAME" 2>/dev/null || echo "")"
    local prev_was_active=1
    local mutation_started=0

    # Service mutation begins
    mutation_started=1
    if ! "$SYSTEMCTL_BIN" restart "$SUBDUB_SERVICE_NAME"; then
      handle_subdub_reconciliation_failure "restart_failed" "systemctl restart returned non-zero" "$prev_was_active" "$prev_pid" "$mutation_started"
      return 1
    fi

    if ! "$SYSTEMCTL_BIN" is-active --quiet "$SUBDUB_SERVICE_NAME"; then
      handle_subdub_reconciliation_failure "not_active_after_restart" "service is not active after restart" "$prev_was_active" "$prev_pid" "$mutation_started"
      return 1
    fi

    local new_pid=""
    local attempt
    local max_attempts="${SUBDUB_PID_POLL_ATTEMPTS:-30}"
    local sleep_seconds="${SUBDUB_PID_POLL_SLEEP:-0.5}"
    for ((attempt = 1; attempt <= max_attempts; attempt++)); do
      new_pid="$("$SYSTEMCTL_BIN" show -p MainPID --value "$SUBDUB_SERVICE_NAME" 2>/dev/null || echo "")"
      if [[ -n "$new_pid" && "$new_pid" != "0" ]]; then
        break
      fi
      sleep "$sleep_seconds"
    done
    if [[ -z "$new_pid" || "$new_pid" == "0" ]]; then
      handle_subdub_reconciliation_failure "new_pid_missing" "SubDub worker MainPID is 0 or missing after restart" "$prev_was_active" "$prev_pid" "$mutation_started"
      return 1
    fi

    if [[ -n "$prev_pid" && "$prev_pid" != "0" ]]; then
      if [[ "$new_pid" == "$prev_pid" ]]; then
        handle_subdub_reconciliation_failure "same_pid" "SubDub worker PID did not change after reload (old=$prev_pid new=$new_pid)" "$prev_was_active" "$prev_pid" "$mutation_started"
        return 1
      fi
    fi

    if [[ ! -d "$PROC_DIR/$new_pid" ]]; then
      handle_subdub_reconciliation_failure "proc_pid_missing" "SubDub worker /proc/$new_pid directory is missing: cannot verify process" "$prev_was_active" "$prev_pid" "$mutation_started"
      return 1
    fi

    local proc_cwd=""
    if [[ -e "$PROC_DIR/$new_pid/cwd" || -L "$PROC_DIR/$new_pid/cwd" ]]; then
      proc_cwd="$(readlink -f "$PROC_DIR/$new_pid/cwd" 2>/dev/null)" || true
    fi
    if [[ -z "$proc_cwd" ]]; then
      handle_subdub_reconciliation_failure "proc_cwd_unreadable" "SubDub worker /proc/$new_pid/cwd is unreadable" "$prev_was_active" "$prev_pid" "$mutation_started"
      return 1
    fi

    local canonical_bot_dir
    canonical_bot_dir="$(cd "$BOT_DIR" && pwd -P)"
    if [[ "$proc_cwd" != "$canonical_bot_dir" ]]; then
      handle_subdub_reconciliation_failure "proc_cwd_mismatch" "SubDub worker process cwd ($proc_cwd) does not match $canonical_bot_dir" "$prev_was_active" "$prev_pid" "$mutation_started"
      return 1
    fi

    local proc_cmdline=""
    proc_cmdline="$(tr '\0' ' ' < "$PROC_DIR/$new_pid/cmdline" 2>/dev/null)" || true
    if [[ -z "$proc_cmdline" ]]; then
      handle_subdub_reconciliation_failure "proc_cmdline_unreadable" "SubDub worker /proc/$new_pid/cmdline is unreadable" "$prev_was_active" "$prev_pid" "$mutation_started"
      return 1
    fi

    if [[ "$proc_cmdline" != *"services/subdub_worker_daemon.py"* ]]; then
      handle_subdub_reconciliation_failure "proc_cmdline_mismatch" "SubDub worker process cmdline ($proc_cmdline) does not execute services/subdub_worker_daemon.py" "$prev_was_active" "$prev_pid" "$mutation_started"
      return 1
    fi

    if [[ -n "${TARGET_SHA:-}" ]]; then
      if ! assert_exact_sha "$BOT_DIR" "$TARGET_SHA" "bot target while subdub active during reconciliation"; then
        handle_subdub_reconciliation_failure "target_sha_mismatch" "bot target SHA mismatch: expected=$TARGET_SHA" "$prev_was_active" "$prev_pid" "$mutation_started"
        return 1
      fi
    fi

    SUBDUB_VERIFIED=1
    log "SUBDUB_WORKER_RECONCILED sha=${TARGET_SHA:-current} pid=$new_pid service=$SUBDUB_SERVICE_NAME active=true"
  else
    SUBDUB_VERIFIED=1
    log "SUBDUB_WORKER_PRESERVED_INACTIVE sha=${TARGET_SHA:-current} service=$SUBDUB_SERVICE_NAME active=false"
  fi
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

  activate_and_verify_subdub_worker
}

commit_product_video_release_transaction() {
  [[ "$SUBDUB_VERIFIED" == "1" ]] || fail "Cannot commit transaction: SubDub worker not verified"
  TRANSACTION_COMMITTED=1
  write_transaction_manifest
  ROLLBACK_ARMED=0
  trap - ERR INT TERM
  log "PRODUCT_VIDEO_DEPLOY_TRANSACTION_COMMITTED bot_sha=$TARGET_SHA worker_sha=$TARGET_SHA subdub_verified=1"
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
