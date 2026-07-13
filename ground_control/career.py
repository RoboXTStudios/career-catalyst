"""Internal Career Catalyst boundary for Ground Control state summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ground_control.seed_data import SEED_DATA


CAREER_OPERATIONAL_STATES = frozenset({"Waiting", "In Flight", "Active Conversations"})


@dataclass(frozen=True)
class CareerState:
    status: str
    summary: str
    launch_target: str | None = None


class CareerCatalystProvider(Protocol):
    """Supplies a compact career snapshot without coupling either product."""

    def load_career_state(self) -> CareerState:
        """Return the current operational career state."""


class LocalCareerCatalystProvider:
    """Local fallback that can later be replaced by a Career Catalyst adapter."""

    def __init__(self, seed: Mapping[str, Any] = SEED_DATA) -> None:
        self._seed = seed

    def load_career_state(self) -> CareerState:
        career = self._seed.get("career")
        if not isinstance(career, Mapping):
            raise ValueError("Seed data must include a career mapping")

        status = str(career.get("status", "Waiting")).strip() or "Waiting"
        summary = str(career.get("summary", "")).strip()
        if not summary:
            summary = "The search is active; hold for the next meaningful signal."
        return CareerState(status=status, summary=summary)


def load_career_state(provider: CareerCatalystProvider) -> CareerState:
    """Read career state through the integration boundary."""

    state = provider.load_career_state()
    if state.status in CAREER_OPERATIONAL_STATES:
        return state
    return CareerState(
        status="Waiting",
        summary=state.summary,
        launch_target=state.launch_target,
    )
