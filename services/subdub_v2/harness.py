"""Aggregate offline replay harness. It is not imported by production V1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .config import V2Flags
from .replay import replay_fixture


def run_replay_suite(fixtures: Iterable[str | Path], *, output_dir: str | Path) -> dict:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    reports = []
    for fixture in fixtures:
        path = Path(fixture)
        metrics_path = destination / f"{path.stem}.replay_metrics.json"
        reports.append(replay_fixture(path, flags=V2Flags.shadow_defaults_for_test(), metrics_path=metrics_path))
    aggregate = {
        "fixture_count": len(reports),
        "shadow_contract_pass": bool(reports) and all(item["shadow_contract_pass"] for item in reports),
        "replay_pass": bool(reports) and all(item["replay_pass"] for item in reports),
        "provider_calls": sum(item["provider_calls"] for item in reports),
        "wallet_mutations": sum(item["wallet_mutations"] for item in reports),
        "customer_deliveries": sum(item["customer_deliveries"] for item in reports),
        "production_traffic": sum(item["production_traffic"] for item in reports),
        "v1_still_available": all(item["v1_still_available"] for item in reports),
        "v2_live_pass": False,
    }
    (destination / "aggregate_replay_metrics.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return {"aggregate": aggregate, "reports": reports}


__all__ = ["run_replay_suite"]
