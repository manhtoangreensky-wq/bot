#!/usr/bin/env bash
set -euo pipefail

readonly DEPLOY_USER="toanaas-deploy"
readonly DEPLOY_HOME="/var/lib/toanaas-deploy"
readonly STATE_ROOT="/var/lib/toanaas-localbotapi"
readonly RELEASE_ROOT="/opt/toanaas-localbotapi"
readonly RELEASES_ROOT="/opt/toanaas-localbotapi/releases"
readonly LIBEXEC_ROOT="/usr/local/libexec/toanaas-localbotapi"
readonly HELPER_GENERATIONS_ROOT="$LIBEXEC_ROOT/generations"
readonly HELPER_CURRENT="$LIBEXEC_ROOT/current"
readonly SYSTEMD_ROOT="/etc/systemd/system"
readonly LOCK_FILE="/run/lock/toanaas-localbotapi-reconcile.lock"
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

require_root_directory() {
    local path="$1"
    local mode="$2"
    require_real_directory "$path"
    [[ "$(stat -c '%U:%G' -- "$path")" == "root:root" ]] || fail "unsafe_root_directory_owner"
    [[ "$(stat -c '%a' -- "$path")" == "$mode" ]] || fail "unsafe_root_directory_mode"
}

require_root_file() {
    local path="$1"
    local mode="$2"
    [[ -f "$path" && ! -L "$path" ]] || fail "unsafe_root_helper_file"
    [[ "$(stat -c '%U:%G' -- "$path")" == "root:root" ]] || fail "unsafe_root_helper_owner"
    [[ "$(stat -c '%a' -- "$path")" == "$mode" ]] || fail "unsafe_root_helper_mode"
    [[ "$(stat -c '%h' -- "$path")" == "1" ]] || fail "unsafe_root_helper_links"
}

require_secure_directory_if_present() {
    local path="$1"
    local mode="$2"
    if [[ -e "$path" || -L "$path" ]]; then
        require_root_directory "$path" "$mode"
    fi
}

require_owned_directory_if_present() {
    local path="$1"
    local directory_mode
    if [[ -e "$path" || -L "$path" ]]; then
        require_real_directory "$path"
        [[ "$(stat -c '%U:%G' -- "$path")" == "root:root" ]] || fail "unsafe_directory_owner"
        directory_mode="$(stat -c '%a' -- "$path")"
        [[ "${directory_mode:1:1}" != [2367] && "${directory_mode:2:1}" != [2367] ]] ||
            fail "unsafe_directory_mode"
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
    [[ "$(stat -c '%h' -- "$source_path")" == "1" ]] || fail "unsafe_bootstrap_snapshot_links"
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

for tool in install groupadd useradd usermod getent id systemctl cp chmod chown flock mktemp mv rm rmdir ln readlink cmp ssh-keygen stat python3; do
    command -v "$tool" >/dev/null 2>&1 || fail "missing_tool_${tool}"
done
ssh-keygen -l -f "$PUBLIC_KEY_FILE" >/dev/null 2>&1 || fail "invalid_ed25519_public_key"
for source_path in release_contract.py apply_release.py receive_release.py; do
    [[ -f "$SCRIPT_ROOT/$source_path" && ! -L "$SCRIPT_ROOT/$source_path" ]] ||
        fail "unsafe_bootstrap_helper_source"
done
python3 -c \
    'import ast,pathlib,sys; [ast.parse(pathlib.Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:]]' \
    "$SCRIPT_ROOT/release_contract.py" \
    "$SCRIPT_ROOT/apply_release.py" \
    "$SCRIPT_ROOT/receive_release.py"

python3 -c \
    'import os,stat,sys; p=sys.argv[1]; flags=os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0); fd=os.open(p,flags,0o600); s=os.fstat(fd); ok=stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1; (os.close(fd) or sys.exit(1)) if not ok else os.fchmod(fd,0o600); os.close(fd)' \
    "$LOCK_FILE" || fail "unsafe_reconcile_lock"
exec 9<>"$LOCK_FILE"
flock -w 30 9 || fail "bootstrap_lock_timeout"

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
require_secure_directory_if_present "$BOOTSTRAP_BACKUP_ROOT" 700
require_secure_directory_if_present "$BOOTSTRAP_SNAPSHOT_ROOT" 700
require_secure_directory_if_present "$BOOTSTRAP_SNAPSHOT_ROOT/systemd" 700
require_secure_directory_if_present "$BOOTSTRAP_SNAPSHOT_ROOT/drop-ins" 700
require_owned_directory_if_present "$DEPLOY_HOME/.ssh"
require_secure_directory_if_present "$HELPER_GENERATIONS_ROOT" 755

install -d -o root -g root -m 0755 "$RELEASE_ROOT" "$RELEASES_ROOT"
install -d -o root -g root -m 0755 "$LIBEXEC_ROOT"
install -d -o root -g root -m 0755 "$HELPER_GENERATIONS_ROOT"
install -d -o root -g "$DEPLOY_USER" -m 0750 "$STATE_ROOT"
install -d -o root -g root -m 0700 "$BOOTSTRAP_BACKUP_ROOT"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0750 "$STATE_ROOT/incoming"
install -d -o root -g root -m 0755 "$DEPLOY_HOME"
install -d -o root -g root -m 0700 "$DEPLOY_HOME/.ssh"

authorized_tmp=""
snapshot_tmp=""
contract_tmp=""
apply_tmp=""
receiver_tmp=""
generation_tmp=""
current_stage=""
cleanup() {
    for temporary in "$authorized_tmp" "$contract_tmp" "$apply_tmp" "$receiver_tmp"; do
        if [[ -n "$temporary" ]]; then
            rm -f -- "$temporary"
        fi
    done
    if [[ -n "$snapshot_tmp" && -d "$snapshot_tmp" ]]; then
        rm -rf -- "$snapshot_tmp"
    fi
    if [[ -n "$generation_tmp" && -d "$generation_tmp" ]]; then
        rm -rf -- "$generation_tmp"
    fi
    if [[ -n "$current_stage" && -d "$current_stage" ]]; then
        rm -rf -- "$current_stage"
    fi
}
trap cleanup EXIT

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

python3 "$SCRIPT_ROOT/apply_release.py" verify-bootstrap-snapshot

generation_id="$(python3 -c 'import hashlib,pathlib,sys; modes={"release_contract.py":"644","apply_release.py":"755","receive_release.py":"755"}; h=hashlib.sha256(); [h.update(pathlib.Path(p).name.encode()+b"\\0"+modes[pathlib.Path(p).name].encode()+b"\\0"+pathlib.Path(p).read_bytes()) for p in sys.argv[1:]]; print(h.hexdigest())' \
    "$SCRIPT_ROOT/release_contract.py" "$SCRIPT_ROOT/apply_release.py" "$SCRIPT_ROOT/receive_release.py")"
[[ "$generation_id" =~ ^[0-9a-f]{64}$ ]] || fail "invalid_helper_generation"
generation_path="$HELPER_GENERATIONS_ROOT/$generation_id"
if [[ -L "$generation_path" || ( -e "$generation_path" && ! -d "$generation_path" ) ]]; then
    fail "unsafe_helper_generation"
fi
if [[ ! -d "$generation_path" ]]; then
    generation_tmp="$(mktemp -d "$HELPER_GENERATIONS_ROOT/.generation.XXXXXXXX")"
    chmod 0700 "$generation_tmp"
    install -o root -g root -m 0644 "$SCRIPT_ROOT/release_contract.py" "$generation_tmp/release_contract.py"
    install -o root -g root -m 0755 "$SCRIPT_ROOT/apply_release.py" "$generation_tmp/apply-release"
    install -o root -g root -m 0755 "$SCRIPT_ROOT/receive_release.py" "$generation_tmp/receive-release"
    PYTHONDONTWRITEBYTECODE=1 python3 -B -c \
        'import runpy,sys; sys.path.insert(0,sys.argv[1]); runpy.run_path(sys.argv[1]+"/apply-release",run_name="bootstrap_smoke"); runpy.run_path(sys.argv[1]+"/receive-release",run_name="bootstrap_smoke")' \
        "$generation_tmp" || fail "helper_generation_smoke_failed"
    chmod 0755 "$generation_tmp"
    mv -T -- "$generation_tmp" "$generation_path"
    generation_tmp=""
fi
require_root_directory "$generation_path" 755
for helper_entry in "$generation_path"/* "$generation_path"/.[!.]*; do
    [[ -e "$helper_entry" || -L "$helper_entry" ]] || continue
    case "$(basename -- "$helper_entry")" in
        release_contract.py|apply-release|receive-release) ;;
        *) fail "unsafe_helper_generation_entry" ;;
    esac
done
require_root_file "$generation_path/release_contract.py" 644
require_root_file "$generation_path/apply-release" 755
require_root_file "$generation_path/receive-release" 755
cmp -s "$SCRIPT_ROOT/release_contract.py" "$generation_path/release_contract.py" || fail "helper_generation_mismatch"
cmp -s "$SCRIPT_ROOT/apply_release.py" "$generation_path/apply-release" || fail "helper_generation_mismatch"
cmp -s "$SCRIPT_ROOT/receive_release.py" "$generation_path/receive-release" || fail "helper_generation_mismatch"
if [[ -e "$HELPER_CURRENT" && ! -L "$HELPER_CURRENT" ]]; then
    fail "unsafe_helper_current_pointer"
fi
if [[ -L "$HELPER_CURRENT" ]]; then
    current_target="$(readlink -f -- "$HELPER_CURRENT" 2>/dev/null || true)"
    [[ "$current_target" == "$HELPER_GENERATIONS_ROOT"/* && -d "$current_target" ]] ||
        fail "unsafe_helper_current_pointer"
fi
current_stage="$(mktemp -d "$LIBEXEC_ROOT/.current-link.XXXXXXXX")"
chmod 0700 "$current_stage"
ln -s "generations/$generation_id" "$current_stage/current"
mv -Tf -- "$current_stage/current" "$HELPER_CURRENT"
rmdir -- "$current_stage"
current_stage=""

authorized_tmp="$(mktemp "$DEPLOY_HOME/.ssh/.authorized_keys.install.XXXXXXXX")"
printf 'restrict,command="/usr/local/libexec/toanaas-localbotapi/current/receive-release" %s\n' \
    "$deploy_key" >"$authorized_tmp"
chown root:"$DEPLOY_USER" "$authorized_tmp"
chmod 0640 "$authorized_tmp"

install -o root -g root -m 0644 \
    "$SCRIPT_ROOT/systemd/toanaas-localbotapi-apply.path" \
    "$SYSTEMD_ROOT/toanaas-localbotapi-apply.path"
install -o root -g root -m 0644 \
    "$SCRIPT_ROOT/systemd/toanaas-localbotapi-apply.service" \
    "$SYSTEMD_ROOT/toanaas-localbotapi-apply.service"

systemctl daemon-reload
systemctl enable --now toanaas-localbotapi-apply.path
mv -Tf -- "$authorized_tmp" "$DEPLOY_HOME/.ssh/authorized_keys"
authorized_tmp=""
printf 'localbotapi_bootstrap status=installed\n'
