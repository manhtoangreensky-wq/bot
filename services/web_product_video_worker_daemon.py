"""Web Product Video Worker Daemon.

Task: WEBAPP_PRODUCT_VIDEO_WEB_QUEUE_WORKER_INTEGRATION_R1
Program: P0.WEBAPP.FULL.PRODUCT.TRUTH.REMEDIATION.V1
Tracker: #605

Runs as a dedicated worker service (toanaas-worker-web-product-video.service)
to poll Web Dispatcher (/api/v1/worker/product-video/*), claim canonical
video_ai_prompt jobs, execute them via Bot canonical runtime, maintain Web
heartbeat lease, and report completion or factual failure.

Strict Safety Invariants:
1. Default Activation OFF: Requires explicit WEB_PRODUCT_VIDEO_WORKER_ENABLED=true.
2. Max 1 Job At A Time: Atomic processing; single worker claims at most 1 job per tick.
3. Durable Fencing: Respects lease expiration; aborts on lease loss.
4. Secret Sanitization: Never logs worker secrets, bearer tokens, or provider API keys.
5. Max 1 Provider Submit: Never auto-retries or submits multiple provider jobs.
6. Bounded Graceful Shutdown: Clean exit on SIGINT / SIGTERM.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import signal
import sys
import threading
import time
from typing import Any, Callable, Mapping

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.web_product_video_worker_consumer import (
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_LEASE_SECONDS,
    ConsumerExecutionOutcome,
    WebClaimResponse,
    WebProductVideoDispatcherClient,
    execute_claimed_web_product_video_job,
    get_web_base_url,
    get_worker_secret,
    is_web_product_video_worker_enabled,
)

logger = logging.getLogger("web_product_video_worker_daemon")

DEFAULT_WORKER_ID = "vps-web-product-video-worker"
DEFAULT_POLL_INTERVAL = 5.0


class WebProductVideoWorkerDaemon:
    """Dedicated background polling daemon for Web Product Video jobs."""

    def __init__(
        self,
        worker_id: str | None = None,
        web_api_url: str | None = None,
        worker_secret: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
        environ: Mapping[str, str] | None = None,
        executor_fn: Callable[..., dict[str, Any]] | None = None,
        transport: Callable[..., Any] | None = None,
        client: WebProductVideoDispatcherClient | None = None,
        run_once: bool = False,
        owner_acceptance_auth: Mapping[str, Any] | None = None,
        acceptance_context: Mapping[str, Any] | None = None,
        acceptance_bypass_scope: str | None = None,
    ) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        self.worker_id = str(
            worker_id or self.environ.get("WORKER_ID") or DEFAULT_WORKER_ID
        ).strip()[:80]
        self.web_api_url = str(web_api_url or get_web_base_url(self.environ)).strip()
        self.worker_secret = str(
            worker_secret if worker_secret is not None else get_worker_secret(self.environ)
        ).strip()
        self.poll_interval = max(0.1, float(poll_interval))
        self.lease_seconds = max(30, int(lease_seconds))
        self.heartbeat_interval = max(0.05, float(heartbeat_interval))
        self.executor_fn = executor_fn
        self.transport = transport
        self.run_once = run_once
        self.owner_acceptance_auth = dict(owner_acceptance_auth) if owner_acceptance_auth else None
        self.acceptance_context = dict(acceptance_context) if acceptance_context else None
        self.acceptance_bypass_scope = str(acceptance_bypass_scope) if acceptance_bypass_scope else None
        if client is not None:
            self.client = client
        else:
            self.client = WebProductVideoDispatcherClient(
                base_url=self.web_api_url,
                worker_id=self.worker_id,
                worker_secret=self.worker_secret,
                transport=self.transport,
            )
        self.stop_event = threading.Event()
        self.jobs_processed = 0
        self.stats: dict[str, int] = {
            "jobs_claimed": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
        }

    def stop(self) -> None:
        """Signal daemon to stop gracefully."""
        self.stop_event.set()

    def process_one_tick(
        self,
        *,
        owner_acceptance_auth: Mapping[str, Any] | None = None,
        acceptance_context: Mapping[str, Any] | None = None,
        acceptance_bypass_scope: str | None = None,
    ) -> ConsumerExecutionOutcome | None:
        """Perform one polling tick against Web Dispatcher."""
        if not is_web_product_video_worker_enabled(self.environ):
            logger.warning(
                "worker_disabled_by_config worker_id=%s enabled=false",
                self.worker_id,
            )
            return None

        try:
            claim_res: WebClaimResponse = self.client.claim(lease_seconds=self.lease_seconds)
        except Exception as exc:
            logger.error("claim_request_error worker_id=%s err=%s", self.worker_id, type(exc).__name__)
            return None

        if claim_res.idle or not claim_res.job:
            logger.debug("claim_idle worker_id=%s", self.worker_id)
            return None

        self.stats["jobs_claimed"] += 1
        job = claim_res.job
        job_id = str(job.get("job_id") or "")
        logger.info(
            "claimed_job_start worker_id=%s job_id=%s request_id=%s",
            self.worker_id,
            job_id,
            job.get("request_id"),
        )

        effective_auth = owner_acceptance_auth if owner_acceptance_auth is not None else self.owner_acceptance_auth
        effective_ctx = acceptance_context if acceptance_context is not None else self.acceptance_context
        effective_scope = acceptance_bypass_scope if acceptance_bypass_scope is not None else self.acceptance_bypass_scope

        outcome = execute_claimed_web_product_video_job(
            job=job,
            client=self.client,
            environ=self.environ,
            heartbeat_interval=self.heartbeat_interval,
            lease_seconds=self.lease_seconds,
            executor_fn=self.executor_fn,
            stop_event=self.stop_event,
            owner_acceptance_auth=effective_auth,
            acceptance_context=effective_ctx,
            acceptance_bypass_scope=effective_scope,
        )

        if self.owner_acceptance_auth is not None:
            self.owner_acceptance_auth = None

        self.jobs_processed += 1
        if outcome.ok:
            self.stats["jobs_completed"] += 1
        else:
            self.stats["jobs_failed"] += 1

        logger.info(
            "claimed_job_finished worker_id=%s job_id=%s status=%s ok=%s blocker=%s",
            self.worker_id,
            job_id,
            outcome.status,
            outcome.ok,
            outcome.blocker_reason or "-",
        )
        return outcome

    def run(self, run_once: bool = False, max_jobs: int | None = None) -> int:
        """Main worker polling loop."""
        effective_run_once = run_once or self.run_once
        logger.info(
            "web_product_video_worker_daemon_started worker_id=%s web_url=%s poll_interval=%.1fs "
            "enabled=%s run_once=%s max_jobs=%s",
            self.worker_id,
            self.web_api_url,
            self.poll_interval,
            is_web_product_video_worker_enabled(self.environ),
            effective_run_once,
            max_jobs,
        )

        if not is_web_product_video_worker_enabled(self.environ):
            logger.warning(
                "PRODUCTION_GATE_OFF: WEB_PRODUCT_VIDEO_WORKER_ENABLED is not enabled. "
                "Daemon will idle fail-closed."
            )
            if effective_run_once:
                return 0

        while not self.stop_event.is_set():
            if not is_web_product_video_worker_enabled(self.environ):
                self.stop_event.wait(timeout=self.poll_interval)
                continue

            outcome = self.process_one_tick()

            if effective_run_once:
                break
            if max_jobs is not None and self.jobs_processed >= max_jobs:
                logger.info("max_jobs_reached count=%d", self.jobs_processed)
                break

            if outcome is None:
                # Idle tick; wait before next poll
                self.stop_event.wait(timeout=self.poll_interval)

        logger.info(
            "web_product_video_worker_daemon_stopped worker_id=%s total_processed=%d",
            self.worker_id,
            self.jobs_processed,
        )
        return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TOAN AAS Web Product Video Dedicated Worker Daemon",
    )
    parser.add_argument(
        "--worker-id",
        default=os.getenv("WORKER_ID", DEFAULT_WORKER_ID),
        help="Worker identifier",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("WEB_PRODUCT_VIDEO_WORKER_POLL_INTERVAL", DEFAULT_POLL_INTERVAL)),
        help="Poll interval in seconds",
    )
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=int(os.getenv("WEB_PRODUCT_VIDEO_WORKER_LEASE_SECONDS", DEFAULT_LEASE_SECONDS)),
        help="Job claim lease duration",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=float(os.getenv("WEB_PRODUCT_VIDEO_WORKER_HEARTBEAT_INTERVAL", DEFAULT_HEARTBEAT_INTERVAL)),
        help="Heartbeat interval in seconds",
    )
    parser.add_argument(
        "--web-api-url",
        default=os.getenv("WEB_API_URL", ""),
        help="Web dispatcher base URL",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Process at most one job or exit if empty",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Process at most N jobs then exit",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Logging level",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    daemon = WebProductVideoWorkerDaemon(
        worker_id=args.worker_id,
        web_api_url=args.web_api_url or None,
        poll_interval=args.poll_interval,
        lease_seconds=args.lease_seconds,
        heartbeat_interval=args.heartbeat_interval,
    )

    def handle_signal(sig, frame):
        logger.info("received_signal sig=%s stopping_daemon", sig)
        daemon.stop()

    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
    except (ValueError, AttributeError):
        pass

    return daemon.run(run_once=args.run_once, max_jobs=args.max_jobs)


if __name__ == "__main__":
    sys.exit(main())
