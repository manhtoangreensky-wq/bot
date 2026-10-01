#!/usr/bin/env python3
"""Dedicated server-side one-shot Owner acceptance runner for Web Product Video.

Contract:
- Requires --expected-job-id and --owner-auth-file.
- Secret/authorization transport: reads protected local file, never exposed in argv or logs.
- Enforces strict POSIX permissions (0600 or 0400) on the auth file.
- Validates expected job ID == auth["job_id"] before claiming.
- Performs exact targeted claim against Web Dispatcher API (claim(target_job_id=...)).
- Validates claimed job ID == expected job ID. If not, fails closed with 0 provider calls.
- Injects owner_acceptance_auth and executes canonical Bot Product Video runtime.
- Exits after exactly 1 job execution (single-use).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import stat
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.web_product_video_worker_consumer import (
    ConsumerExecutionOutcome,
    WebClaimResponse,
    WebProductVideoDispatcherClient,
    execute_claimed_web_product_video_job,
    get_web_base_url,
    get_worker_secret,
)

logger = logging.getLogger("toanaas.runner.pv_live_acceptance")


def check_file_permissions(path: Path) -> None:
    """Enforce POSIX file permissions: must not have group or other permissions (0600 or 0400)."""
    if os.name == "posix":
        file_stat = path.stat()
        mode = file_stat.st_mode
        if (mode & 0o077) != 0:
            raise PermissionError(
                f"OWNER_AUTH_PERMISSIONS_INSECURE: file mode {oct(stat.S_IMODE(mode))} "
                f"is insecure; requires 0600 or 0400 (no group/other access)"
            )


def load_protected_owner_auth(file_path: str | Path, expected_job_id: str) -> dict[str, Any]:
    """Load and validate Owner acceptance authorization from a protected local file.

    Invariants:
    1. File must exist and be a regular file.
    2. On POSIX, file permissions must not be group/world accessible (0600 or 0400).
    3. File must contain valid JSON.
    4. auth["job_id"] must exactly match expected_job_id.
    """
    clean_path = Path(file_path).resolve()
    if not clean_path.is_file():
        raise FileNotFoundError(f"OWNER_AUTH_FILE_NOT_FOUND: {clean_path}")

    check_file_permissions(clean_path)

    try:
        content = clean_path.read_text(encoding="utf-8")
        auth_data = json.loads(content)
    except Exception as exc:
        raise ValueError(f"OWNER_AUTH_PARSE_FAILED: Malformed JSON in {clean_path}") from exc

    if not isinstance(auth_data, dict):
        raise ValueError("OWNER_AUTH_INVALID: Auth payload must be a JSON object")

    auth_job_id = str(auth_data.get("job_id") or "").strip()
    if not auth_job_id:
        raise ValueError("OWNER_AUTH_MISSING_JOB_ID: Auth payload missing 'job_id'")

    if auth_job_id != str(expected_job_id).strip():
        raise ValueError(
            f"OWNER_AUTH_EXPECTED_JOB_MISMATCH: Auth job_id {auth_job_id!r} "
            f"does not match expected_job_id {expected_job_id!r}"
        )

    return auth_data


def run_live_acceptance_once(
    expected_job_id: str,
    owner_auth_file: str | Path,
    acceptance_bypass_scope: str = "probation_liveness_only",
    worker_id: str | None = None,
    base_url: str | None = None,
    dry_run: bool = False,
    client: WebProductVideoDispatcherClient | None = None,
) -> int:
    """Execute exactly one targeted Owner acceptance job and terminate.

    Returns exit code (0 = success, non-zero = failure/blocked).
    """
    clean_expected_id = str(expected_job_id or "").strip()
    if not clean_expected_id:
        print("STATUS=BLOCKED_MISSING_EXPECTED_JOB_ID", file=sys.stderr)
        print("PROVIDER_CALLS=0")
        return 1

    # Phase C: Load protected Owner auth
    try:
        owner_auth = load_protected_owner_auth(owner_auth_file, clean_expected_id)
    except Exception as exc:
        print(f"STATUS=BLOCKED_OWNER_AUTH_INVALID: {exc}", file=sys.stderr)
        print("PROVIDER_CALLS=0")
        return 1

    dispatcher_client = client or WebProductVideoDispatcherClient(
        base_url=base_url,
        worker_id=worker_id,
    )

    # Phase B & D: Targeted claim
    try:
        claim_res: WebClaimResponse = dispatcher_client.claim(
            lease_seconds=300,
            target_job_id=clean_expected_id,
        )
    except Exception as exc:
        print(f"STATUS=BLOCKED_CLAIM_REQUEST_FAILED: {exc}", file=sys.stderr)
        print("PROVIDER_CALLS=0")
        return 1

    if claim_res.idle or not claim_res.job:
        print("STATUS=BLOCKED_TARGET_JOB_NOT_CLAIMABLE")
        print("PROVIDER_CALLS=0")
        return 1

    claimed_job_id = str(claim_res.job.get("job_id") or "").strip()
    if claimed_job_id != clean_expected_id:
        print("STATUS=BLOCKED_TARGET_JOB_ID_MISMATCH")
        print(f"CLAIMED_JOB_ID={claimed_job_id}")
        print(f"EXPECTED_JOB_ID={clean_expected_id}")
        print("PROVIDER_CALLS=0")
        return 1

    if dry_run:
        print("STATUS=DRY_RUN_CLAIM_SUCCESS")
        print(f"JOB_ID={claimed_job_id}")
        print("EXPECTED_CLAIMED_MATCH=YES")
        print("PROVIDER_CALLS=0")
        return 0

    # Phase D: Execute canonical runtime with server-side Owner auth injection
    try:
        outcome: ConsumerExecutionOutcome = execute_claimed_web_product_video_job(
            claim_res.job,
            client=dispatcher_client,
            owner_acceptance_auth=owner_auth,
            acceptance_context={"job_id": clean_expected_id},
            acceptance_bypass_scope=acceptance_bypass_scope,
        )
    finally:
        # Single use in-memory retirement
        owner_auth.clear()

    # Output execution summary (sanitized, zero secret leakage)
    print(f"JOB_ID={outcome.job_id}")
    print(f"STATUS={outcome.status}")
    print(f"OK={'YES' if outcome.ok else 'NO'}")
    print(f"PROVIDER_CALLS={outcome.provider_calls}")
    print(f"PAID_PROVIDER_CALLS={outcome.paid_provider_calls}")
    print(f"VIDEO_RENDERS={outcome.video_renders}")
    print("WALLET_MUTATIONS=0")
    if outcome.blocker_reason:
        print(f"BLOCKER_REASON={outcome.blocker_reason}")
    if outcome.output_url:
        print(f"OUTPUT_URL={outcome.output_url}")

    return 0 if outcome.ok else 1


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="One-shot Owner acceptance runner for Web Product Video jobs."
    )
    parser.add_argument(
        "--expected-job-id",
        required=True,
        help="Exact durable Web job ID (must match auth file)",
    )
    parser.add_argument(
        "--owner-auth-file",
        required=True,
        help="Path to protected server-side Owner acceptance authorization JSON file (mode 0600)",
    )
    parser.add_argument(
        "--acceptance-bypass-scope",
        default="probation_liveness_only",
        help="Scope for spend-freeze bypass (default: probation_liveness_only)",
    )
    parser.add_argument(
        "--worker-id",
        default=None,
        help="Optional worker ID override",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional Web dispatcher base URL override",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Claim and validate target job only without invoking provider runtime",
    )

    args = parser.parse_args()

    return run_live_acceptance_once(
        expected_job_id=args.expected_job_id,
        owner_auth_file=args.owner_auth_file,
        acceptance_bypass_scope=args.acceptance_bypass_scope,
        worker_id=args.worker_id,
        base_url=args.base_url,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
