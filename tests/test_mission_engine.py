from datetime import date

import pytest

from ground_control.mission_engine import (
    CareerMissionSource,
    FinanceMissionSource,
    HealthMissionSource,
    MissionEngine,
    MissionSuggestion,
    ProjectMissionSource,
    build_default_mission_engine,
    build_mission_context,
    run_default_mission_engine,
)
from ground_control.model import build_major_tom_message, load_finance_snapshot
from ground_control.seed_data import SEED_DATA


class StubMissionSource:
    def __init__(self, source_id, priority, summary=None):
        self.source_id = source_id
        self.priority = priority
        self.summary = summary or f"{source_id} ready"

    def suggest(self, context):
        del context
        return MissionSuggestion(
            source_id=self.source_id,
            mission=f"Mission from {self.source_id}",
            priority=self.priority,
            state_summary=self.summary,
        )


def _seed_context():
    return build_mission_context(load_finance_snapshot(SEED_DATA), seed=SEED_DATA)


def test_default_mission_sources_are_registered_independently():
    engine = build_default_mission_engine()

    assert [source.source_id for source in engine.sources] == [
        "finance",
        "project",
        "career",
        "health",
    ]
    assert isinstance(engine.sources[0], FinanceMissionSource)
    assert isinstance(engine.sources[1], ProjectMissionSource)
    assert isinstance(engine.sources[2], CareerMissionSource)
    assert isinstance(engine.sources[3], HealthMissionSource)


def test_mission_source_registration_rejects_duplicate_ids():
    engine = MissionEngine((StubMissionSource("finance", 50),))

    with pytest.raises(ValueError, match="already registered"):
        engine.register(StubMissionSource("finance", 90))


def test_mission_engine_sorts_by_priority_and_preserves_tie_order():
    engine = MissionEngine(
        (
            StubMissionSource("low", 10),
            StubMissionSource("high", 90),
            StubMissionSource("tie-a", 60),
            StubMissionSource("tie-b", 60),
        )
    )

    result = engine.run(_seed_context())

    assert [suggestion.source_id for suggestion in result.ranked_suggestions] == [
        "high",
        "tie-a",
        "tie-b",
        "low",
    ]


def test_mission_engine_selects_exactly_the_top_three():
    result = run_default_mission_engine(load_finance_snapshot(SEED_DATA), seed=SEED_DATA)

    assert len(result.ranked_suggestions) == 4
    assert len(result.selected_suggestions) == 3
    assert [suggestion.source_id for suggestion in result.selected_suggestions] == [
        "finance",
        "project",
        "career",
    ]
    assert result.missions == (
        "Confirm the next EDD certification and payment date",
        SEED_DATA["active_project"]["priority"],
        "Review the next career follow-up",
    )


def test_each_source_returns_one_scored_mission_and_state_summary():
    context = _seed_context()

    suggestions = [source.suggest(context) for source in build_default_mission_engine().sources]

    assert len(suggestions) == 4
    assert all(suggestion.mission for suggestion in suggestions)
    assert all(isinstance(suggestion.priority, int) for suggestion in suggestions)
    assert all(suggestion.state_summary for suggestion in suggestions)


def test_major_tom_communicates_mission_engine_output():
    result = run_default_mission_engine(load_finance_snapshot(SEED_DATA), seed=SEED_DATA)

    message = build_major_tom_message(
        mission_summary=result.summary,
        current_date=date(2026, 7, 13),
        next_mission=result.missions[0],
    )

    assert "Monday, July 13" in message
    assert "Finance nominal" in message
    assert "Ground Control in motion" in message
    assert "Career in flight" in message
    assert "Health check-in waiting" in message
    assert f"Next move: {result.missions[0]}" in message
