# SECFIX B4 dependency audit — 2026-07-27

## Scope

- Input: `requirements.lock`
- Runtime target: Linux x86_64, Python 3.11 (`python:3.11-slim`)
- Resolved packages: 75
- Direct requirements: all exact-pinned in `requirements.txt`
- Lock integrity: hashes required for every distribution

## Reproducibility checks

```text
uv pip compile requirements.txt \
  --python-platform x86_64-unknown-linux-gnu \
  --python-version 3.11 \
  --generate-hashes --no-annotate --no-header \
  --output-file requirements.lock
```

Result: resolved 75 packages.

```text
uv pip sync --dry-run --require-hashes --system \
  --python-version 3.11 \
  --python-platform x86_64-unknown-linux-gnu \
  requirements.lock
```

Result: exit 0, 75 packages resolved.

The same lock was mounted read-only into an isolated `python:3.11-slim`
Linux container on the VPS and checked with:

```text
python -m pip install --dry-run --require-hashes -r /requirements.lock
```

Result: exit 0. No production volume, bot container, worker, or secret was
mounted into the check container.

## CVE result

`pip-audit` was run over every exact-pinned package in the lock without
installing platform-specific wheels on Windows:

```text
pip-audit -r requirements.lock --no-deps --disable-pip --format json
```

Result: 1 known vulnerability in 1 package.

| Package | Version | Advisory | Fixed release |
|---|---:|---|---|
| paramiko | 3.5.1 | PYSEC-2026-2858 / CVE-2026-44405 / GHSA-r374-rxx8-8654 | None published in the audit feed |

The audit description reports that the RSA key path permits SHA-1. This is
not marked fixed because the vulnerability feed supplied no fixed release.

## Why Paramiko remains in the runtime lock

`services/artifact_storage.py` imports Paramiko lazily for the live
`vps_sftp` artifact backend, including key loading, upload, verification, and
recovery. `services/storage_weekly.py` also uses that SFTP path for remote
backup operations. It is therefore a runtime dependency, not a deploy-only
tool that can be moved to `requirements-dev.txt` without removing supported
runtime behavior.

Operational mitigation until upstream publishes a fixed release:

- the production Local Telegram Bot API path does not use the SFTP artifact
  backend;
- the VPS login path uses ED25519 keys;
- keep the package pinned and rerun the audit on every dependency update;
- upgrade immediately when a fixed Paramiko release is available and passes
  the artifact-storage tests.

## Honest closure status

B4 dependency pinning and lockfile reproducibility are complete. The single
Paramiko advisory remains an explicitly tracked upstream risk; the dependency
set is not described as vulnerability-free.
