#!/usr/bin/env bash
set -euo pipefail

readonly DEPLOY_USER="toanaas-deploy"
readonly DEPLOY_HOME="/var/lib/toanaas-deploy"
readonly STATE_ROOT="/var/lib/toanaas-localbotapi"
readonly RELEASE_ROOT="/opt/toanaas-localbotapi"
readonly RELEASES_ROOT="/opt/toanaas-localbotapi/releases"
readonly LIBEXEC_ROOT="/usr/local/libexec/toanaas-localbotapi"
readonly SYSTEMD_ROOT="/etc/systemd/system"
readonly BOOTSTRAP_BACKUP_ROOT="$STATE_ROOT/bootstrap-backup"
readonly BOOTSTRAP_SNAPSHOT_ROOT="$BOOTSTRAP_BACKUP_ROOT/snapshot-v2"
readonly BOOTSTRAP_BACKUP_MARKER="$BOOTSTRAP_SNAPSHOT_ROOT/.complete"
readonly LEGACY_DROPIN="$SYSTEMD_ROOT/toanaas-telegram-bot-api.service.d/10-security-hardening.conf"
readonly SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly -a MANAGED_UNITS=(
    toanaas-telegram-bot-api.service
    toanaas-localbotapi-cleanup.service
    toanaas-localbotapi-cleanup.timer
    toanaas-localbotapi-health.service
    toanaas-localbotapi-health.timer
    toanaas-localbotapi-reconcile.service
    toanaas-localbotapi-reconcile.timer
    toanaas-localbotapi-cert-watch.service
    toanaas-localbotapi-cert-watch.timer
)

fail() {
    printf 'localbotapi_bootstrap status=failed reason=%s\n' "$1" >&2
    exit 1
}

require_real_directory() {
    local path="$1"
    if [[ -L "$path" || ( -e "$path" && ! -d "$path" ) ]]; then
        fail "unsafe_existing_directory"
    fi
}

snapshot_file() {
    local source_path="$1"
    local destination_path="$2"
    local source_mode
    local source_owner
    if [[ -L "$source_path" ]] || [[ -e "$source_path" && ! -f "$source_path" ]]; then
        fail "unsafe_bootstrap_snapshot_source"
    fi
    [[ -f "$source_path" ]] || return 0
    source_owner="$(stat -c '%U:%G' -- "$source_path")"
    [[ "$source_owner" == "root:root" ]] || fail "unsafe_bootstrap_snapshot_owner"
    source_mode="$(stat -c '%a' -- "$source_path")"
    case "$source_mode" in
        600|640|644) ;;
        *) fail "unsupported_bootstrap_snapshot_mode" ;;
    esac
    cp -- "$source_path" "$destination_path"
    chmod 0600 "$destination_path"
    printf '%s\n' "$source_mode" >"$destination_path.mode"
    chmod 0600 "$destination_path.mode"
}

[[ "${EUID}" -eq 0 ]] || fail "root_required"
[[ "$#" -eq 1 ]] || fail "usage_public_key_file"
readonly PUBLIC_KEY_FILE="$1"
[[ -f "$PUBLIC_KEY_FILE" && ! -L "$PUBLIC_KEY_FILE" ]] || fail "unsafe_public_key_file"

mapfile -t deploy_key_lines <"$PUBLIC_KEY_FILE"
[[ "${#deploy_key_lines[@]}" -eq 1 ]] || fail "public_key_must_be_one_line"
readonly deploy_key="${deploy_key_lines[0]}"
[[ "$deploy_key" =~ ^ssh-ed25519[[:space:]][A-Za-z0-9+/=]+([[:space:]].*)?$ ]] ||
    fail "invalid_ed25519_public_key"

for tool in install groupadd useradd usermod getent id systemctl cp chmod chown mktemp mv rm ssh-keygen stat; do
    command -v "$tool" >/dev/null 2>&1 || fail "missing_tool_${tool}"
done
ssh-keygen -l -f "$PUBLIC_KEY_FILE" >/dev/null 2>&1 || fail "invalid_ed25519_public_key"

if ! getent group "$DEPLOY_USER" >/dev/null 2>&1; then
    groupadd --system "$DEPLOY_USER"
fi
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
    useradd --system --gid "$DEPLOY_USER" --home-dir "$DEPLOY_HOME" --create-home --shell /bin/bash "$DEPLOY_USER"
fi
usermod --home "$DEPLOY_HOME" --gid "$DEPLOY_USER" --groups '' --lock --shell /bin/bash "$DEPLOY_USER"

passwd_entry="$(getent passwd "$DEPLOY_USER")"
IFS=: read -r _ _ _ _ _ actual_home actual_shell <<<"$passwd_entry"
[[ "$actual_home" == "$DEPLOY_HOME" && "$actual_shell" == "/bin/bash" ]] ||
    fail "deploy_account_identity_mismatch"
[[ "$(id -gn "$DEPLOY_USER")" == "$DEPLOY_USER" ]] || fail "deploy_primary_group_mismatch"
[[ "$(id -Gn "$DEPLOY_USER")" == "$DEPLOY_USER" ]] || fail "deploy_supplementary_groups_present"
shadow_entry="$(getent shadow "$DEPLOY_USER")"
IFS=: read -r _ password_field _ <<<"$shadow_entry"
[[ "$password_field" == '!'* || "$password_field" == '*' ]] || fail "deploy_password_not_locked"

require_real_directory "$RELEASE_ROOT"
require_real_directory "$RELEASES_ROOT"
require_real_directory "$STATE_ROOT"
require_real_directory "$STATE_ROOT/incoming"
require_real_directory "$BOOTSTRAP_BACKUP_ROOT"
require_real_directory "$BOOTSTRAP_SNAPSHOT_ROOT"
require_real_directory "$BOOTSTRAP_SNAPSHOT_ROOT/systemd"
require_real_directory "$BOOTSTRAP_SNAPSHOT_ROOT/drop-ins"
require_real_directory "$DEPLOY_HOME"
require_real_directory "$DEPLOY_HOME/.ssh"
require_real_directory "$LIBEXEC_ROOT"

install -d -o root -g root -m 0755 "$RELEASE_ROOT" "$RELEASES_ROOT"
install -d -o root -g root -m 0755 "$LIBEXEC_ROOT"
install -d -o root -g "$DEPLOY_USER" -m 0750 "$STATE_ROOT"
install -d -o root -g root -m 0700 "$BOOTSTRAP_BACKUP_ROOT"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0750 "$STATE_ROOT/incoming"
install -d -o root -g root -m 0755 "$DEPLOY_HOME" "$DEPLOY_HOME/.ssh"

install -o root -g root -m 0644 "$SCRIPT_ROOT/release_contract.py" "$LIBEXEC_ROOT/release_contract.py"
install -o root -g root -m 0755 "$SCRIPT_ROOT/apply_release.py" "$LIBEXEC_ROOT/apply-release"
install -o root -g root -m 0755 "$SCRIPT_ROOT/receive_release.py" "$LIBEXEC_ROOT/receive-release"

authorized_tmp="$(mktemp)"
snapshot_tmp=""
cleanup() {
    rm -f -- "$authorized_tmp"
    if [[ -n "$snapshot_tmp" && -d "$snapshot_tmp" ]]; then
        rm -rf -- "$snapshot_tmp"
    fi
}
trap cleanup EXIT
printf 'restrict,command="/usr/local/libexec/toanaas-localbotapi/receive-release" %s\n' \
    "$deploy_key" >"$authorized_tmp"
install -o root -g "$DEPLOY_USER" -m 0640 "$authorized_tmp" "$DEPLOY_HOME/.ssh/authorized_keys"

if [[ -L "$BOOTSTRAP_BACKUP_MARKER" ]] || \
    [[ -e "$BOOTSTRAP_BACKUP_MARKER" && ! -f "$BOOTSTRAP_BACKUP_MARKER" ]]; then
    fail "unsafe_bootstrap_backup_marker"
fi
if [[ -d "$BOOTSTRAP_SNAPSHOT_ROOT" && ! -f "$BOOTSTRAP_BACKUP_MARKER" ]]; then
    fail "incomplete_bootstrap_snapshot"
fi

if [[ ! -d "$BOOTSTRAP_SNAPSHOT_ROOT" ]]; then
    snapshot_tmp="$(mktemp -d "$BOOTSTRAP_BACKUP_ROOT/.snapshot-v2.XXXXXXXX")"
    chmod 0700 "$snapshot_tmp"
    install -d -o root -g root -m 0700 "$snapshot_tmp/systemd" "$snapshot_tmp/drop-ins"
    for unit in "${MANAGED_UNITS[@]}"; do
        snapshot_file "$SYSTEMD_ROOT/$unit" "$snapshot_tmp/systemd/$unit"
    done
    snapshot_file "$LEGACY_DROPIN" "$snapshot_tmp/drop-ins/10-security-hardening.conf"
    printf 'snapshot-v2\n' >"$snapshot_tmp/.complete"
    chmod 0600 "$snapshot_tmp/.complete"
    mv -T -- "$snapshot_tmp" "$BOOTSTRAP_SNAPSHOT_ROOT"
    snapshot_tmp=""
fi

install -o root -g root -m 0644 \
    "$SCRIPT_ROOT/systemd/toanaas-localbotapi-apply.path" \
    "$SYSTEMD_ROOT/toanaas-localbotapi-apply.path"
install -o root -g root -m 0644 \
    "$SCRIPT_ROOT/systemd/toanaas-localbotapi-apply.service" \
    "$SYSTEMD_ROOT/toanaas-localbotapi-apply.service"

systemctl daemon-reload
systemctl enable --now toanaas-localbotapi-apply.path
printf 'localbotapi_bootstrap status=installed\n'
