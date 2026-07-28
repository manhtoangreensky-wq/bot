#!/usr/bin/env bash
set -euo pipefail

readonly DEPLOY_USER="toanaas-deploy"
readonly DEPLOY_HOME="/var/lib/toanaas-deploy"
readonly STATE_ROOT="/var/lib/toanaas-localbotapi"
readonly RELEASE_ROOT="/opt/toanaas-localbotapi"
readonly RELEASES_ROOT="/opt/toanaas-localbotapi/releases"
readonly LIBEXEC_ROOT="/usr/local/libexec/toanaas-localbotapi"
readonly SYSTEMD_ROOT="/etc/systemd/system"
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

[[ "${EUID}" -eq 0 ]] || fail "root_required"
[[ "$#" -eq 1 ]] || fail "usage_public_key_file"
readonly PUBLIC_KEY_FILE="$1"
[[ -f "$PUBLIC_KEY_FILE" && ! -L "$PUBLIC_KEY_FILE" ]] || fail "unsafe_public_key_file"

mapfile -t deploy_key_lines <"$PUBLIC_KEY_FILE"
[[ "${#deploy_key_lines[@]}" -eq 1 ]] || fail "public_key_must_be_one_line"
readonly deploy_key="${deploy_key_lines[0]}"
[[ "$deploy_key" =~ ^ssh-ed25519[[:space:]][A-Za-z0-9+/=]+([[:space:]].*)?$ ]] ||
    fail "invalid_ed25519_public_key"

for tool in install useradd usermod id systemctl cp chmod chown mktemp; do
    command -v "$tool" >/dev/null 2>&1 || fail "missing_tool_${tool}"
done

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$DEPLOY_HOME" --create-home --shell /bin/bash "$DEPLOY_USER"
fi
usermod --lock --shell /bin/bash "$DEPLOY_USER"

require_real_directory "$RELEASE_ROOT"
require_real_directory "$RELEASES_ROOT"
require_real_directory "$STATE_ROOT"
require_real_directory "$STATE_ROOT/incoming"
require_real_directory "$DEPLOY_HOME"
require_real_directory "$DEPLOY_HOME/.ssh"
require_real_directory "$LIBEXEC_ROOT"

install -d -o root -g root -m 0755 "$RELEASE_ROOT" "$RELEASES_ROOT"
install -d -o root -g root -m 0755 "$LIBEXEC_ROOT"
install -d -o root -g root -m 0700 "$STATE_ROOT" "$STATE_ROOT/bootstrap-backup"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0750 "$STATE_ROOT/incoming"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0700 "$DEPLOY_HOME/.ssh"

install -o root -g root -m 0644 "$SCRIPT_ROOT/release_contract.py" "$LIBEXEC_ROOT/release_contract.py"
install -o root -g root -m 0755 "$SCRIPT_ROOT/apply_release.py" "$LIBEXEC_ROOT/apply-release"
install -o root -g root -m 0755 "$SCRIPT_ROOT/receive_release.py" "$LIBEXEC_ROOT/receive-release"

authorized_tmp="$(mktemp)"
trap 'rm -f -- "$authorized_tmp"' EXIT
printf 'restrict,command="/usr/local/libexec/toanaas-localbotapi/receive-release" %s\n' \
    "$deploy_key" >"$authorized_tmp"
install -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0600 "$authorized_tmp" "$DEPLOY_HOME/.ssh/authorized_keys"

backup_root="$STATE_ROOT/bootstrap-backup/systemd"
if [[ ! -f "$STATE_ROOT/bootstrap-backup/.complete" ]]; then
    install -d -o root -g root -m 0700 "$backup_root"
    for unit in "${MANAGED_UNITS[@]}"; do
        source_path="$SYSTEMD_ROOT/$unit"
        if [[ -f "$source_path" ]]; then
            cp --dereference -- "$source_path" "$backup_root/$unit"
            chown root:root "$backup_root/$unit"
            chmod 0600 "$backup_root/$unit"
        fi
    done
    install -o root -g root -m 0600 /dev/null "$STATE_ROOT/bootstrap-backup/.complete"
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
