from __future__ import annotations

from typing import Any, Mapping

from .base import SubDubLaneContract, SubDubRunner


LANE = SubDubLaneContract(name="dub_only", modes=frozenset({"dub"}))


async def run(runner: SubDubRunner, payload: Mapping[str, Any]) -> dict[str, Any]:
    return await LANE.run(runner=runner, payload=payload)
