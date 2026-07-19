from __future__ import annotations

from typing import Any, Mapping

from .base import SubDubLaneContract, SubDubRunner


LANE = SubDubLaneContract(
    name="subtitle_dub",
    modes=frozenset({"subtitle_plus_dub"}),
)


async def run(runner: SubDubRunner, payload: Mapping[str, Any]) -> dict[str, Any]:
    return await LANE.run(runner=runner, payload=payload)
