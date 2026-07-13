"""Local mission sources and priority-based daily mission selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol, Sequence

from ground_control.model import (
    FinanceSnapshot,
    calculate_runway_months,
    runway_status_label,
)
from ground_control.seed_data import SEED_DATA


MISSION_LIMIT = 3


@dataclass(frozen=True)
class MissionContext:
    finance: FinanceSnapshot
    active_project_name: str
    active_project_priority: str
    career_status: str
    previous_unfinished: tuple[str, ...] = ()


@dataclass(frozen=True)
class MissionSuggestion:
    source_id: str
    mission: str
    priority: int
    state_summary: str


@dataclass(frozen=True)
class MissionEngineResult:
    ranked_suggestions: tuple[MissionSuggestion, ...]
    selected_suggestions: tuple[MissionSuggestion, ...]
    summary: str

    @property
    def missions(self) -> tuple[str, ...]:
        return tuple(suggestion.mission for suggestion in self.selected_suggestions)


class MissionSource(Protocol):
    """Independent contributor of one daily mission and one state signal."""

    source_id: str

    def suggest(self, context: MissionContext) -> MissionSuggestion:
        """Return one deterministic mission suggestion for the current context."""


class MissionEngine:
    def __init__(self, sources: Iterable[MissionSource] = ()) -> None:
        self._sources: list[MissionSource] = []
        for source in sources:
            self.register(source)

    @property
    def sources(self) -> tuple[MissionSource, ...]:
        return tuple(self._sources)

    def register(self, source: MissionSource) -> None:
        source_id = str(source.source_id).strip()
        if not source_id:
            raise ValueError("Mission sources require a source_id")
        if any(existing.source_id == source_id for existing in self._sources):
            raise ValueError(f"Mission source already registered: {source_id}")
        self._sources.append(source)

    def run(self, context: MissionContext, *, limit: int = MISSION_LIMIT) -> MissionEngineResult:
        if limit <= 0:
            raise ValueError("Mission selection limit must be greater than zero")

        gathered = tuple(source.suggest(context) for source in self._sources)
        ranked = tuple(
            suggestion
            for _, suggestion in sorted(
                enumerate(gathered),
                key=lambda item: (-item[1].priority, item[0]),
            )
        )
        selected = ranked[:limit]
        summaries = [
            suggestion.state_summary.strip().rstrip(".")
            for suggestion in ranked
            if suggestion.state_summary.strip()
        ]
        summary = "; ".join(summaries)
        if summary:
            summary += "."
        return MissionEngineResult(
            ranked_suggestions=ranked,
            selected_suggestions=selected,
            summary=summary,
        )


def _continuation_for(context: MissionContext, keywords: Sequence[str]) -> str | None:
    normalized_keywords = tuple(keyword.casefold() for keyword in keywords if keyword)
    return next(
        (
            mission
            for mission in context.previous_unfinished
            if any(keyword in mission.casefold() for keyword in normalized_keywords)
        ),
        None,
    )


class FinanceMissionSource:
    source_id = "finance"

    def suggest(self, context: MissionContext) -> MissionSuggestion:
        runway = calculate_runway_months(
            cash=context.finance.cash,
            edd_remaining=context.finance.edd_remaining,
            monthly_burn=context.finance.monthly_burn,
        )
        status = runway_status_label(runway)
        if runway < 1:
            mission = f"Protect essential bills with only {runway:.1f} months of runway"
            priority = 100
        elif runway < 3:
            mission = f"Review essential expenses against {runway:.1f} months of runway"
            priority = 90
        elif context.finance.edd_remaining > 0:
            mission = "Confirm the next EDD certification and payment date"
            priority = 80
        else:
            mission = "Confirm Fidelity rollover availability"
            priority = 75

        unfinished = _continuation_for(
            context,
            ("edd", "fidelity", "mortgage", "expense", "bill", "benefit", "runway"),
        )
        if unfinished:
            mission = f"Continue if still relevant: {unfinished}"
            priority += 5
        return MissionSuggestion(
            source_id=self.source_id,
            mission=mission,
            priority=priority,
            state_summary=f"Finance {status.lower()}",
        )


class ProjectMissionSource:
    source_id = "project"

    def suggest(self, context: MissionContext) -> MissionSuggestion:
        unfinished = _continuation_for(
            context,
            (context.active_project_name, context.active_project_priority),
        )
        mission = context.active_project_priority
        priority = 70
        if unfinished:
            mission = f"Continue if still relevant: {unfinished}"
            priority += 5
        return MissionSuggestion(
            source_id=self.source_id,
            mission=mission,
            priority=priority,
            state_summary=f"{context.active_project_name} in motion",
        )


class CareerMissionSource:
    """Local placeholder until Career Catalyst synchronization is introduced."""

    source_id = "career"

    def suggest(self, context: MissionContext) -> MissionSuggestion:
        unfinished = _continuation_for(
            context,
            ("career", "interview", "application", "recruiter", "follow-up", "follow up"),
        )
        mission = "Review the next career follow-up"
        priority = 40
        if unfinished:
            mission = f"Continue if still relevant: {unfinished}"
            priority += 5
        return MissionSuggestion(
            source_id=self.source_id,
            mission=mission,
            priority=priority,
            state_summary=f"Career {context.career_status.lower()}",
        )


class HealthMissionSource:
    """Local placeholder for future user-configured health signals."""

    source_id = "health"

    def suggest(self, context: MissionContext) -> MissionSuggestion:
        unfinished = _continuation_for(
            context,
            ("health", "walk", "rest", "recovery", "appointment"),
        )
        mission = "Protect one short recovery block"
        priority = 20
        if unfinished:
            mission = f"Continue if still relevant: {unfinished}"
            priority += 5
        return MissionSuggestion(
            source_id=self.source_id,
            mission=mission,
            priority=priority,
            state_summary="Health check-in waiting",
        )


def build_mission_context(
    finance: FinanceSnapshot,
    previous_missions: Sequence[object] = (),
    seed: Mapping[str, Any] = SEED_DATA,
) -> MissionContext:
    project = seed.get("active_project")
    if not isinstance(project, Mapping) or not project.get("name") or not project.get("priority"):
        raise ValueError("Seed data must include an active project name and priority")

    career = seed.get("career")
    career_status = "Waiting"
    if isinstance(career, Mapping) and career.get("status"):
        career_status = str(career["status"]).strip() or "Waiting"

    previous_unfinished = tuple(
        str(getattr(mission, "text", "")).strip()
        for mission in previous_missions
        if not bool(getattr(mission, "completed", False))
        and str(getattr(mission, "text", "")).strip()
        and not str(getattr(mission, "text", "")).startswith("Mission ")
    )
    return MissionContext(
        finance=finance,
        active_project_name=str(project["name"]).strip(),
        active_project_priority=str(project["priority"]).strip(),
        career_status=career_status,
        previous_unfinished=previous_unfinished,
    )


def build_default_mission_engine() -> MissionEngine:
    return MissionEngine(
        (
            FinanceMissionSource(),
            ProjectMissionSource(),
            CareerMissionSource(),
            HealthMissionSource(),
        )
    )


def run_default_mission_engine(
    finance: FinanceSnapshot,
    previous_missions: Sequence[object] = (),
    seed: Mapping[str, Any] = SEED_DATA,
) -> MissionEngineResult:
    context = build_mission_context(finance, previous_missions, seed)
    return build_default_mission_engine().run(context)
