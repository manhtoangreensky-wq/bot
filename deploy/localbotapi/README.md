# TOAN AAS Local Bot API immutable VPS deployment

This directory owns only the Telegram Local Bot API infrastructure at
`tg.toanaas.vn`. Railway continues to run the production bot source. Nothing in
this deployment copies, syncs, reloads, or restarts Product Video,
`remote_worker.py`, `local_worker.py`, providers, PayOS, wallet/Xu, or the DB.

## Safety contract

- VPS host: `tg.toanaas.vn` / `161.248.147.232`.
- Trusted ED25519 host fingerprint:
  `SHA256:xiXs/BXPp12IL8IFBSPQuRE5Jf03Dp6fLAoH+7jSz3o`.
- Local upstream stays on `127.0.0.1:8081`; ports 8081/8082 remain closed
  externally.
- The container image is pinned by digest in `release/policy.json`.
- `api_id`, `api_hash`, Telegram bot tokens, proxy secrets, webhook secrets,
  and private SSH keys never belong in Git, terminal output, reports, or chat.
- The effective production intake limit is 500 MB and the project duration
  limit is 3600 seconds. The protocol hard cap remains 2000 MB, but it is not
  the customer limit and must not be advertised as one.
- Intake verification stops before paid-provider confirmation. Therefore
  `SUBDUB MP4 LIVE PASS = NO` unless a separate paid-live task is approved.

## What updates automatically

The workflow `.github/workflows/deploy-localbotapi-vps.yml` runs on `main` only
when the immutable `release/` payload, its deterministic builder, or the
workflow changes. It builds a
deterministic release, validates it locally, sends it through the dedicated
forced-command key, and waits until the exact release ID is active after the
health gate. A failed activation returns a failing workflow and leaves the
last-known-good release active.

The release contains only `release/`. Bot source and worker source are not VPS
payloads. Normal bot commits deploy to Railway and do not create a fake VPS
update because the VPS does not execute that source.

The root-owned files under `bootstrap/` are the fixed trust anchor. They are
intentionally not writable by the automatic deploy key. A bootstrap change
requires an admin-key review and explicit reinstall; allowing the release key
to replace its own verifier would remove the security boundary.
Bootstrap-only commits deliberately do not emit a misleading green VPS deploy.
The workflow uses the `localbotapi-production` GitHub Environment, restricted
to `main`, so its privileged SSH key is unavailable to pull-request code.

## First bootstrap

1. Generate a dedicated ED25519 deployment key. Do not reuse the admin key and
   do not print the private key.
2. Verify fresh `ssh-keyscan` results for both the domain and IP against the
   trusted fingerprint above before saving a pinned known-hosts file.
3. Copy only the public deployment key plus `deploy/localbotapi/bootstrap/` to
   a temporary VPS directory using the key-only `toanaas-admin` account.
4. From that account run the installer with sudo:

   ```bash
   sudo bash install_bootstrap.sh /path/to/dedicated-deploy-key.pub
   ```

   The installer creates locked account `toanaas-deploy`, a single
   `restrict,command="/usr/local/libexec/toanaas-localbotapi/current/receive-release"`
   authorized key, root-owned verifier/apply helpers, an atomic versioned
   root-only bootstrap snapshot (including original file modes), and the apply
   path unit. It does not restart the Local Bot API or any worker.

5. Restrict the `localbotapi-production` GitHub Environment to `main`. Store
   the private key and pinned known-hosts content as Environment secrets using
   stdin, never as command arguments:

   - `LOCALBOT_VPS_SSH_KEY`
   - `LOCALBOT_VPS_KNOWN_HOSTS`

6. Prove an interactive shell, forwarding, and an arbitrary command are
   rejected by the deployment key. Then dispatch the workflow once.

GitHub Actions needs only `contents: read`. The Environment secrets must be
configured before the first dispatch.

## Release and health behavior

Validated releases live at:

```text
/opt/toanaas-localbotapi/releases/<canonical-manifest-sha256>
/opt/toanaas-localbotapi/current
/opt/toanaas-localbotapi/previous
```

Activation uses atomic symlink replacement, reloads only declared Local Bot
API units, restarts only `toanaas-telegram-bot-api.service`, and runs these
checks:

- Docker container is running.
- local `/` is 404 and dummy local `getMe` is 401.
- public missing and deliberately wrong proxy secrets are both 403.
- 8081 is bound only to `127.0.0.1`; 8082 is absent.
- TLS hostname, chain, and at least 14 days of certificate lifetime are valid.

The health, reconcile, certificate, and cleanup timers are sandboxed. Cleanup
runs every 15 minutes, retains normal artifacts for 120 minutes, keeps Local
Bot API data at or below 6144 MiB, requires at least 3072 MiB free, and fails
closed before enumeration if `fuser` or another guard tool is unavailable.
The legacy unsafe cleanup timer is disabled only after the new release passes.

## Railway production limits

Keep these production values aligned without displaying secret values:

```text
TELEGRAM_API_BASE_URL=https://tg.toanaas.vn
TELEGRAM_API_PROXY_SECRET_HEADER=X-Toanaas-Proxy-Secret
SUBDUB_MAX_INPUT_MB=500
SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB=500
SUBDUB_MAX_DURATION_SECONDS=3600
SUBDUB_LONG_PROJECT_MAX_DURATION_SECONDS=3600
```

The proxy secret, Telegram token, and media path variables remain secret or
environment-specific. Verify names/presence and comparisons in memory; never
dump the Railway variable set.

## Verification

Use sanitized checks only:

```bash
sudo /opt/toanaas-localbotapi/current/release/bin/toanaas-localbotapi-health
sudo /opt/toanaas-localbotapi/current/release/bin/toanaas-localbotapi-cert-watch
sudo systemctl list-timers --all --no-pager | grep -E 'localbotapi|telegram'
sudo systemctl is-active toanaas-telegram-bot-api.service
```

Count token-shaped matches in Nginx, journal, and Railway logs; never print the
matching lines. Confirm the production Telegram intake with a small file and
the 74,838,369-byte control MP4, with provider calls `0` and wallet mutations
`0`. A real 2 GB test is neither required nor accepted under the 500 MB product
limit.

## Rollback

Normal last-known-good rollback:

```bash
sudo /usr/local/libexec/toanaas-localbotapi/current/apply-release rollback \
  --service toanaas-telegram-bot-api.service
```

Emergency return to the root-only pre-bootstrap units:

```bash
sudo /usr/local/libexec/toanaas-localbotapi/current/apply-release restore-bootstrap \
  --service toanaas-telegram-bot-api.service
```

Both commands reject any other service name. Never delete Local Bot API data
as part of rollback. Telegram Cloud migration is a separate token ownership
operation and is not performed by these release helpers.

## Rotation

- Deployment key: add and test a new dedicated key, update
  `LOCALBOT_VPS_SSH_KEY`, dispatch successfully, then remove the prior public
  key entry. Preserve the forced-command restriction for every generation.
- Proxy secret: use dual-generation acceptance in Nginx. Add the next value
  from a root-only source, reload after `nginx -t`, update Railway without
  displaying the value, verify Local API and zero leak counts, promote next,
  then remove the prior generation. Never place either generation in argv.
- TLS: Certbot remains independent; the certificate watcher reports hostname,
  chain, or expiry failure and never changes system time.

After every rotation, rerun the health gate, verify exact Railway/main SHA and
exact VPS release ID, and confirm `Existing workers touched: NO`.
