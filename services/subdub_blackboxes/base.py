from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping


SubDubRunner = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class SubDubLaneContract:
    name: str
    modes: frozenset[str]

    async def run(
        self,
        *,
        runner: SubDubRunner,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        runner_payload = dict(payload)
        mode = str(runner_payload.get("mode") or "").strip()
        if mode not in self.modes:
            raise ValueError(f"mode_not_owned_by_{self.name}")
        return await runner(**runner_payload)
