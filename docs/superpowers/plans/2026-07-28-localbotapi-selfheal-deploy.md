# Local Bot API Self-Heal and Immutable VPS Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `tg.toanaas.vn` consume immutable, manifest-verified Local Bot API infrastructure releases from `main`, detect service/config drift or hangs, and roll back to last-known-good without copying bot code or touching any Product Video service.

**Architecture:** GitHub Actions builds a deterministic infra-only tarball and sends it over a dedicated forced-command SSH key. A fixed root-owned VPS bootstrap validates the archive and manifest, derives `release_id = sha256(canonical_manifest_bytes)`, installs it under `/opt/toanaas-localbotapi/releases/$release_id`, flips `current`/`previous` symlinks, reloads only Local Bot API units, verifies health, and rolls back on failure. Release-managed health, reconcile, certificate, and cleanup timers are sandboxed; cleanup fails closed if its open-file guard is unavailable.

**Tech Stack:** Python 3 standard library, Bash, systemd, Docker, Nginx, GitHub Actions, OpenSSH.

---

## Patch contract

- Vulnerable control: the VPS has no release/reconcile/health/LKG layer, so a running-but-hung container or stale unit is not repaired. The existing cleanup service runs as unsandboxed root and `is_open()` returns false when `fuser` disappears, allowing deletion to continue.
- Security invariant: only an allowlisted, hash-verified infra bundle from the dedicated deploy path may change Local Bot API units; service recovery must affect only `toanaas-telegram-bot-api`; cleanup must perform no deletion unless every required guard is present.
- Preserved behavior: image digest remains `aiogram/telegram-bot-api@sha256:2e93a720f71f82e41a42dc89e258efda09e6791f8d959e6801d15f88408e8eb1`; upstream remains `127.0.0.1:8081`; secrets remain external under `/etc`; Nginx/TLS behavior and the production bot stay online; existing Product Video/local/remote workers are untouched.
- Explicit non-goals: no bot source copy to VPS, no Watchtower, no `latest`, no blind `git pull`, no provider/payment/wallet/DB change.

## File map

- Create `tests/test_p0_infra_localbotapi_selfheal.py`: executable release-contract and static infrastructure safety tests.
- Create `deploy/localbotapi/bootstrap/release_contract.py`: safe path, manifest, tar member, and digest validation.
- Create `deploy/localbotapi/bootstrap/build_release.py`: deterministic infra-only release builder.
- Create `deploy/localbotapi/bootstrap/apply_release.py`: root-side immutable install, atomic activation, health gate, and LKG rollback.
- Create `deploy/localbotapi/bootstrap/receive_release.py`: forced-command stdin receiver with command, size, commit, and digest validation.
- Create `deploy/localbotapi/bootstrap/install_bootstrap.sh`: first-install users/directories/forced key/systemd setup.
- Create `deploy/localbotapi/bootstrap/systemd/toanaas-localbotapi-apply.{path,service}`: root apply trigger.
- Create `deploy/localbotapi/release/bin/toanaas-localbotapi-{health,reconcile,cleanup,cert-watch}`: runtime guards.
- Create `deploy/localbotapi/release/systemd/*.service` and `*.timer`: sandboxed release-managed units.
- Create `deploy/localbotapi/release/policy.json`: exact image digest, ports, thresholds, service names, and allowed units.
- Create `.github/workflows/deploy-localbotapi-vps.yml`: path-scoped immutable build/send workflow.
- Create `deploy/localbotapi/README.md`: bootstrap, deploy, rollback, rotation, and evidence runbook.

### Task 1: Encode the immutable-release and scope contract

**Files:**
- Create: `tests/test_p0_infra_localbotapi_selfheal.py`
- Create: `deploy/localbotapi/bootstrap/release_contract.py`
- Create: `deploy/localbotapi/bootstrap/build_release.py`
- Create: `deploy/localbotapi/release/policy.json`

- [ ] **Step 1: Write the failing release-contract tests**

```python
def test_release_builder_is_deterministic_and_infra_only(tmp_path):
    first = build_release(REPO, "1" * 40, tmp_path / "one.tgz")
    second = build_release(REPO, "1" * 40, tmp_path / "two.tgz")
    assert sha256(first) == sha256(second)
    assert set(read_manifest(first)["files"]) == expected_release_files()
    assert all("bot.py" not in name and "worker" not in name for name in members(first))

def test_manifest_rejects_traversal_symlink_and_digest_mismatch(tmp_path):
    for archive in (traversal_tar(tmp_path), symlink_tar(tmp_path), bad_digest_tar(tmp_path)):
        with pytest.raises(ReleaseContractError):
            validate_archive(archive)
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/test_p0_infra_localbotapi_selfheal.py -k 'release_builder or manifest'`

Expected: FAIL because the release package and scripts do not exist.

- [ ] **Step 3: Implement the minimal release contract**

The manifest schema is exactly:

```json
{
  "schema": "toanaas-localbotapi-release/v1",
  "commit": "1111111111111111111111111111111111111111",
  "files": {"release/bin/toanaas-localbotapi-health": "0000000000000000000000000000000000000000000000000000000000000000"},
  "policy_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
}
```

Reject absolute paths, `..`, links/devices, duplicate members, files outside `release/`, archives over 2 MiB, unlisted/missing files, and non-matching hashes. Normalize tar uid/gid/mtime/mode and gzip mtime so two builds match byte-for-byte.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest -q tests/test_p0_infra_localbotapi_selfheal.py -k 'release_builder or manifest'`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add tests/test_p0_infra_localbotapi_selfheal.py deploy/localbotapi/bootstrap/release_contract.py deploy/localbotapi/bootstrap/build_release.py deploy/localbotapi/release/policy.json
git commit -m "feat(infra): add immutable Local Bot API release contract"
```

### Task 2: Add fail-closed runtime guards and sandboxed timers

**Files:**
- Modify: `tests/test_p0_infra_localbotapi_selfheal.py`
- Create: `deploy/localbotapi/release/bin/toanaas-localbotapi-health`
- Create: `deploy/localbotapi/release/bin/toanaas-localbotapi-reconcile`
- Create: `deploy/localbotapi/release/bin/toanaas-localbotapi-cleanup`
- Create: `deploy/localbotapi/release/bin/toanaas-localbotapi-cert-watch`
- Create: `deploy/localbotapi/release/systemd/*.service`
- Create: `deploy/localbotapi/release/systemd/*.timer`

- [ ] **Step 1: Write failing guard/unit tests**

```python
def test_cleanup_fails_closed_before_any_remove_when_fuser_is_missing():
    text = release("bin/toanaas-localbotapi-cleanup").read_text()
    assert "require_tool fuser" in text
    assert text.index("require_tool fuser") < text.index("safe_remove()")

def test_reconcile_is_locked_and_rolls_back_only_the_localbot_service():
    text = release("bin/toanaas-localbotapi-reconcile").read_text()
    assert "flock -n" in text
    assert "toanaas-telegram-bot-api" in text
    assert "previous" in text and "rollback" in text
    assert "product-video" not in text and "remote_worker" not in text

def test_health_checks_real_upstream_and_external_gate():
    text = release("bin/toanaas-localbotapi-health").read_text()
    assert "127.0.0.1:8081" in text
    assert "root_http" in text and "404" in text
    assert "missing_secret_status" in text and "403" in text
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/test_p0_infra_localbotapi_selfheal.py -k 'cleanup or reconcile or health or systemd'`

Expected: FAIL because scripts/units are absent.

- [ ] **Step 3: Implement minimal runtime scripts and units**

Health requires Docker running, `127.0.0.1:8081/` = 404, dummy upstream = 401, public missing-secret = 403, loopback-only listener, and no public 8081/8082. Reconcile takes `/run/lock/toanaas-localbotapi-reconcile.lock`, verifies `current/manifest.json`, checks unit links and health, restarts only `toanaas-telegram-bot-api` once, then invokes the fixed rollback helper when health still fails. Cleanup requires `flock`, `fuser`, `find`, `stat`, `du`, `df`, `sort`, `cut`, and `awk` before enumeration, preserves 120-minute retention, 6144 MiB cap, and 3072 MiB free-space threshold. Cert watch uses `openssl x509 -checkend 1209600` and never changes clock state.

Every oneshot unit uses `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`, `RestrictSUIDSGID=true`, `LockPersonality=true`, an empty capability set unless required, and narrow `ReadWritePaths`.

- [ ] **Step 4: Run GREEN and remote syntax checks**

Run: `python -m pytest -q tests/test_p0_infra_localbotapi_selfheal.py -k 'cleanup or reconcile or health or systemd'`

Then upload only the scripts to `/tmp/toanaas-localbotapi-systemd-verify` and run `bash -n` plus `systemd-analyze verify --root=/tmp/toanaas-localbotapi-systemd-verify` on the VPS. Expected: PASS; no service restart.

- [ ] **Step 5: Commit Task 2**

```powershell
git add tests/test_p0_infra_localbotapi_selfheal.py deploy/localbotapi/release
git commit -m "feat(infra): add Local Bot API self-heal and cleanup guards"
```

### Task 3: Add fixed bootstrap, activation, and last-known-good rollback

**Files:**
- Modify: `tests/test_p0_infra_localbotapi_selfheal.py`
- Create: `deploy/localbotapi/bootstrap/apply_release.py`
- Create: `deploy/localbotapi/bootstrap/receive_release.py`
- Create: `deploy/localbotapi/bootstrap/install_bootstrap.sh`
- Create: `deploy/localbotapi/bootstrap/systemd/toanaas-localbotapi-apply.path`
- Create: `deploy/localbotapi/bootstrap/systemd/toanaas-localbotapi-apply.service`

- [ ] **Step 1: Write failing apply/receiver tests**

```python
def test_apply_activates_atomically_and_restores_previous_on_failed_health(tmp_path):
    result = apply_release(roots(tmp_path), valid_bundle(tmp_path), health=lambda: False)
    assert result.status == "rolled_back"
    assert roots(tmp_path).current.resolve() == roots(tmp_path).previous.resolve()

def test_receiver_rejects_shell_commands_and_wrong_digest(tmp_path):
    with pytest.raises(ReceiveError):
        receive("bash -i", b"archive", tmp_path)
    with pytest.raises(ReceiveError):
        receive("upload " + "1" * 40 + " " + "0" * 64, b"archive", tmp_path)
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/test_p0_infra_localbotapi_selfheal.py -k 'apply or receiver'`

Expected: FAIL because bootstrap files are absent.

- [ ] **Step 3: Implement minimal activation protocol**

`receive_release.py` accepts only the regular expression `^upload [0-9a-f]{40} [0-9a-f]{64}$` from `SSH_ORIGINAL_COMMAND`, reads at most 2 MiB from stdin, checks the archive digest and manifest commit, atomically writes `$archive_sha256.tgz` plus `$archive_sha256.ready`, and offers no shell. `apply_release.py` validates again, extracts regular allowlisted files to `.staging-$release_id`, renames to `releases/$release_id`, updates `previous` then `current` with atomic symlink replacement, reloads only declared units, runs health, and restores `previous` if the gate fails. The installer creates a locked `toanaas-deploy` account and a forced-key entry with `restrict,command="/usr/local/libexec/toanaas-localbotapi/receive-release"`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest -q tests/test_p0_infra_localbotapi_selfheal.py -k 'apply or receiver'`

Expected: PASS, including a deliberate failed-health rollback.

- [ ] **Step 5: Commit Task 3**

```powershell
git add tests/test_p0_infra_localbotapi_selfheal.py deploy/localbotapi/bootstrap
git commit -m "feat(infra): add atomic Local Bot API release activation"
```

### Task 4: Add the path-scoped GitHub deployment workflow and runbook

**Files:**
- Modify: `tests/test_p0_infra_localbotapi_selfheal.py`
- Create: `.github/workflows/deploy-localbotapi-vps.yml`
- Create: `deploy/localbotapi/README.md`

- [ ] **Step 1: Write failing workflow safety tests**

```python
def test_workflow_is_path_scoped_pinned_and_host_key_strict():
    workflow = yaml_text(".github/workflows/deploy-localbotapi-vps.yml")
    assert "deploy/localbotapi/**" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "StrictHostKeyChecking=no" not in workflow
    assert "git pull" not in workflow and ":latest" not in workflow
    assert "LOCALBOT_VPS_SSH_KEY" in workflow
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/test_p0_infra_localbotapi_selfheal.py -k workflow`

Expected: FAIL because the workflow is absent.

- [ ] **Step 3: Implement workflow and runbook**

Trigger on `push` to `main` only when `.github/workflows/deploy-localbotapi-vps.yml` or `deploy/localbotapi/**` changes, plus manual dispatch. Build the tarball for `${GITHUB_SHA}`, verify it locally, write the private key to an ephemeral `0600` file, use a pinned known-hosts secret, stream the bundle with `upload ${GITHUB_SHA} ${BUNDLE_SHA256}`, then remove the key. The runbook documents bootstrap, key rotation, dual-generation Nginx secret rotation, health evidence, LKG rollback, and the explicit ban on Product Video changes.

- [ ] **Step 4: Run GREEN and complete focused suite**

Run: `python -m pytest -q tests/test_p0_infra_localbotapi_selfheal.py`

Expected: PASS with no import of monolithic `bot.py`.

- [ ] **Step 5: Commit Task 4**

```powershell
git add tests/test_p0_infra_localbotapi_selfheal.py .github/workflows/deploy-localbotapi-vps.yml deploy/localbotapi/README.md
git commit -m "ci(infra): deploy immutable Local Bot API releases"
```

### Task 5: Review, deploy, rotate, and verify on the VPS

**Files:**
- No Product Video/bot source changes.
- Install only the committed `deploy/localbotapi` bootstrap/release artifacts.

- [ ] **Step 1: Run spec review then code-quality review**

Review the branch diff against this plan. Reject any `remote_worker.py`, `local_worker.py`, Product Video, PayOS, wallet/Xu, DB, provider, bot token, API hash, or shared-secret content.

- [ ] **Step 2: Run complete verification before deployment**

Run the focused pytest suite, Python AST/compile for new files, deterministic two-build hash comparison, manifest negative tests, `bash -n` on VPS, `systemd-analyze verify`, secret/token regex scans, and `git diff --check`.

- [ ] **Step 3: Bootstrap dedicated deploy path**

Generate a dedicated ED25519 key without printing it, install only its public key as a forced command for `toanaas-deploy`, place the private key and pinned known-hosts content into GitHub Actions secrets, and prove interactive shell/forwarding are denied while a valid bundle is accepted.

- [ ] **Step 4: Apply first release and verify LKG**

Save the current Local Bot API unit/cleanup files as a root-only bootstrap backup, apply the exact release digest, verify `current`/`previous`, all timers, service health, loopback bind, 403 missing/wrong secret, TLS, token-log counts, and disk thresholds. Deliberately use a harmless failed-health fixture to prove rollback, then restore the healthy release.

- [ ] **Step 5: Rotate the proxy secret with dual-generation acceptance**

Generate `next` without argv/stdout, let Nginx accept current+next, reload, update Railway production to next without displaying it, verify Local API and logs, promote next/current, retain prior briefly for rollback, then remove prior after evidence. Never put either value in Git, shell history, reports, or chat.

- [ ] **Step 6: Verify deployment linkage and production evidence**

Dispatch the workflow once, verify the VPS `current/manifest.json` commit/digest matches the workflow SHA, Railway still deploys latest `main`, production bot webhook is healthy, and the prior 74,838,369-byte Local API roundtrip remains reproducible without provider calls or Xu mutation. Claim `SUBDUB MP4 LIVE PASS = NO` unless a separately approved paid output test exists.
