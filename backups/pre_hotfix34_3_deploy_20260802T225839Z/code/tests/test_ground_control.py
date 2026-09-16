import json
import re
from datetime import date, datetime, timezone

import pytest

from ground_control.career import (
    CareerState,
    LocalCareerCatalystProvider,
    load_career_state,
)
from ground_control.local_time import (
    LOCAL_TIMEZONE,
    as_local_time,
    format_local_datetime,
    greeting_for_datetime,
    local_date,
)
from ground_control.model import (
    FinanceSnapshot,
    build_creative_state,
    build_finance_cards,
    build_financial_state,
    build_major_tom_message,
    calculate_runway_months,
    limit_major_tom_message,
    load_finance_snapshot,
    load_missions,
    runway_status,
    runway_status_label,
)
from ground_control.seed_data import SEED_DATA
from ground_control.state import (
    DailyMission,
    GroundControlState,
    MissionDay,
    daily_mission_suggestions,
    ensure_daily_suggestions,
    load_state,
    reuse_unfinished_missions,
    rollover_for_date,
    save_state,
    seed_state,
    unfinished_from_previous_day,
    yesterday_mission_day,
)


def test_los_angeles_timezone_controls_local_date_and_display():
    utc_value = datetime(2026, 7, 11, 6, 30, tzinfo=timezone.utc)

    local_value = as_local_time(utc_value)

    assert local_value.hour == 23
    assert local_value.tzname() == "PDT"
    assert local_date(utc_value) == date(2026, 7, 10)
    assert format_local_datetime(utc_value) == "Friday, July 10, 2026 · 11:30:00 PM PDT"


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (0, 0, "Good morning"),
        (11, 59, "Good morning"),
        (12, 0, "Good afternoon"),
        (17, 59, "Good afternoon"),
        (18, 0, "Good evening"),
        (23, 59, "Good evening"),
    ],
)
def test_greeting_uses_local_time_boundaries(hour, minute, expected):
    local_value = datetime(2026, 7, 11, hour, minute, tzinfo=LOCAL_TIMEZONE)

    assert greeting_for_datetime(local_value) == expected


def test_financial_telemetry_keeps_raw_amounts_out_of_state_summary():
    snapshot = load_finance_snapshot(SEED_DATA)

    cards = build_finance_cards(snapshot)
    state = build_financial_state(snapshot)

    assert [card.label for card in cards] == ["Cash", "Essentials burn", "401(k)", "EDD"]
    assert state.status == "Nominal"
    assert state.runway_label == "4.7 months"
    assert "$" not in state.summary


def test_seed_runway_uses_cash_plus_edd_against_monthly_burn():
    snapshot = load_finance_snapshot(SEED_DATA)

    runway = calculate_runway_months(
        cash=snapshot.cash,
        edd_remaining=snapshot.edd_remaining,
        monthly_burn=snapshot.monthly_burn,
    )

    assert runway == pytest.approx(4.7473, rel=0.0001)


def test_seed_has_exactly_three_daily_missions():
    missions = load_missions(SEED_DATA)

    assert len(missions) == 3


def test_mission_count_validation_rejects_scope_creep():
    seed = {**SEED_DATA, "missions": ["One", "Two", "Three", "Four"]}

    with pytest.raises(ValueError, match="exactly three missions"):
        load_missions(seed)


def test_major_tom_message_communicates_mission_engine_brief():
    message = build_major_tom_message(
        mission_summary=(
            "Finance nominal; Ground Control in motion; "
            "Career in flight; Health check-in waiting."
        ),
        current_date=date(2026, 7, 10),
        missions_completed=1,
        next_mission="Confirm the next EDD certification and payment date",
    )

    assert "Friday, July 10" in message
    assert "Finance nominal" in message
    assert "Career in flight" in message
    assert "Ground Control in motion" in message
    assert "Health check-in waiting" in message
    assert "Next move: Confirm the next EDD certification and payment" in message
    assert "4.7" not in message
    assert "$" not in message


def test_major_tom_message_is_limited_to_two_short_sentences():
    message = build_major_tom_message(mission_summary="Finance nominal")
    sentences = re.findall(r".+?(?:[.!?](?=\s|$)|$)", message)

    assert len(sentences) <= 2
    assert all(len(sentence.split()) <= 16 for sentence in sentences)


def test_major_tom_message_trims_longer_templates_to_two_sentences():
    message = limit_major_tom_message("One. Two. Three.")

    assert message == "One. Two."


def test_missing_saved_state_uses_seed_fallback(tmp_path):
    state = load_state(tmp_path / "missing.json", SEED_DATA)

    assert state == seed_state(SEED_DATA)


def test_saved_state_round_trips_manual_overrides(tmp_path):
    state_file = tmp_path / "ground-control.json"
    saved = GroundControlState(
        person_name="Trisha",
        finance=FinanceSnapshot(
            cash=20000,
            monthly_burn=5000,
            retirement_401k=155000,
            edd_remaining=6500,
        ),
        mission_date="2026-07-10",
        missions=(
            DailyMission("Call Fidelity", True),
            DailyMission("Update homepage", False),
            DailyMission("Pay phone bill", True),
        ),
        mission_history=(
            MissionDay(
                "2026-07-09",
                tuple(DailyMission(f"Old mission {index}") for index in range(1, 4)),
            ),
        ),
    )

    save_state(saved, state_file)
    loaded = load_state(state_file, SEED_DATA)

    assert loaded == saved


def test_saved_finance_recalculates_financial_state():
    state = GroundControlState(
        person_name="Trisha",
        finance=FinanceSnapshot(
            cash=20000,
            monthly_burn=5000,
            retirement_401k=155000,
            edd_remaining=5000,
        ),
        mission_date="2026-07-10",
        missions=tuple(DailyMission(f"Mission {index}") for index in range(1, 4)),
    )

    runway = calculate_runway_months(
        cash=state.finance.cash,
        edd_remaining=state.finance.edd_remaining,
        monthly_burn=state.finance.monthly_burn,
    )
    financial_state = build_financial_state(state.finance)

    assert runway == pytest.approx(5.0)
    assert financial_state.runway_label == "5.0 months"
    assert financial_state.status == "Nominal"


def test_new_day_rollover_archives_prior_day_and_resets_completion():
    prior = GroundControlState(
        person_name="Trisha",
        finance=load_finance_snapshot(SEED_DATA),
        mission_date="2026-07-09",
        missions=(
            DailyMission("Finished", True),
            DailyMission("Still open", False),
            DailyMission("Also open", False),
        ),
    )

    current = rollover_for_date(prior, date(2026, 7, 10))

    assert current.mission_date == "2026-07-10"
    assert len(current.missions) == 3
    assert current.missions[0].text == "Confirm the next EDD certification and payment date"
    assert current.missions[1].text == SEED_DATA["active_project"]["priority"]
    assert current.missions[2].text == "Review the next career follow-up"
    assert not any(mission.completed for mission in current.missions)
    assert current.mission_history == (MissionDay("2026-07-09", prior.missions),)


def test_first_launch_prefills_three_local_rule_suggestions():
    state = seed_state(SEED_DATA, current_date=date(2026, 7, 11))
    suggestions = state.missions

    assert state.mission_date == "2026-07-11"
    assert len(suggestions) == 3
    assert suggestions[0].text == "Confirm the next EDD certification and payment date"
    assert suggestions[1].text == SEED_DATA["active_project"]["priority"]
    assert suggestions[2].text == "Review the next career follow-up"
    assert not any(mission.completed for mission in suggestions)


def test_placeholder_day_receives_suggestions_once_without_overwriting_edits():
    placeholder_state = GroundControlState(
        person_name="Trisha",
        finance=load_finance_snapshot(SEED_DATA),
        mission_date="2026-07-11",
        missions=tuple(DailyMission(f"Mission {index}") for index in range(1, 4)),
        mission_suggestions_applied=False,
    )

    suggested = ensure_daily_suggestions(placeholder_state)

    assert len(suggested.missions) == 3
    assert suggested.mission_suggestions_applied is True
    assert ensure_daily_suggestions(suggested) == suggested


def test_prior_day_unfinished_mission_is_an_optional_suggestion_candidate():
    finance = load_finance_snapshot(SEED_DATA)
    previous = (
        DailyMission("Already complete", True),
        DailyMission("Submit benefits paperwork", False),
        DailyMission("Another open item", False),
    )

    suggestions = daily_mission_suggestions(finance, previous)

    assert suggestions[0].text == "Continue if still relevant: Submit benefits paperwork"


def test_yesterday_summary_uses_only_the_prior_local_calendar_day():
    yesterday = MissionDay(
        "2026-07-10",
        (
            DailyMission("One", True),
            DailyMission("Two", False),
            DailyMission("Three", True),
        ),
    )
    older = MissionDay(
        "2026-07-09",
        tuple(DailyMission(f"Older {index}") for index in range(1, 4)),
    )
    state = GroundControlState(
        person_name="Trisha",
        finance=load_finance_snapshot(SEED_DATA),
        mission_date="2026-07-11",
        missions=seed_state(SEED_DATA, current_date=date(2026, 7, 11)).missions,
        mission_history=(older, yesterday),
    )

    summary = yesterday_mission_day(state, date(2026, 7, 11))

    assert summary == yesterday
    assert sum(mission.completed for mission in summary.missions) == 2


def test_unfinished_missions_are_reused_only_on_request():
    prior_missions = (
        DailyMission("Finished", True),
        DailyMission("Still open", False),
        DailyMission("Also open", False),
    )
    current = GroundControlState(
        person_name="Trisha",
        finance=load_finance_snapshot(SEED_DATA),
        mission_date="2026-07-10",
        missions=tuple(DailyMission(f"Mission {index}") for index in range(1, 4)),
        mission_history=(MissionDay("2026-07-09", prior_missions),),
    )

    assert [mission.text for mission in unfinished_from_previous_day(current)] == [
        "Still open",
        "Also open",
    ]

    reused = reuse_unfinished_missions(current)

    assert [mission.text for mission in reused.missions] == ["Still open", "Also open", "Mission 3"]
    assert not any(mission.completed for mission in reused.missions)


@pytest.mark.parametrize(
    ("months", "expected"),
    [(0.9, "critical burn"), (2.9, "adjust course"), (3.0, "nominal")],
)
def test_runway_status_tracks_financial_thresholds(months, expected):
    assert runway_status(months) == expected


@pytest.mark.parametrize(
    ("cash", "expected"),
    [(4499, "Critical Burn"), (8999, "Adjust Course"), (13500, "Nominal")],
)
def test_financial_state_uses_operational_status_thresholds(cash, expected):
    snapshot = FinanceSnapshot(
        cash=cash,
        monthly_burn=4500,
        retirement_401k=160000,
        edd_remaining=0,
    )

    state = build_financial_state(snapshot)

    assert state.status == expected
    assert runway_status_label(state.runway_months) == expected


def test_career_state_loads_through_internal_provider_interface():
    class StubCareerCatalystProvider:
        def load_career_state(self):
            return CareerState(
                status="Active Conversations",
                summary="Two meaningful conversations are moving.",
                launch_target="career-catalyst://home",
            )

    state = load_career_state(StubCareerCatalystProvider())
    fallback = load_career_state(LocalCareerCatalystProvider(SEED_DATA))

    assert state.status == "Active Conversations"
    assert state.launch_target == "career-catalyst://home"
    assert fallback.status == "In Flight"
    assert fallback.launch_target is None
    assert "rejection" not in fallback.summary.lower()
    assert "application" not in fallback.summary.lower()


def test_career_state_normalizes_non_operational_status_language():
    class RawCareerCatalystProvider:
        def load_career_state(self):
            return CareerState(status="Rejected", summary="The latest role has closed.")

    state = load_career_state(RawCareerCatalystProvider())

    assert state.status == "Waiting"


def test_creative_state_tracks_active_project_momentum():
    priority = SEED_DATA["active_project"]["priority"]
    pending = build_creative_state(
        SEED_DATA,
        missions=(DailyMission(priority), DailyMission("Other"), DailyMission("Another")),
    )
    completed = build_creative_state(
        SEED_DATA,
        missions=(DailyMission(priority, True), DailyMission("Other"), DailyMission("Another")),
    )

    assert pending.status == "In Motion"
    assert pending.project_name == "Ground Control"
    assert completed.status == "Momentum Secured"


def test_invalid_saved_state_falls_back_to_seed(tmp_path):
    state_file = tmp_path / "ground-control.json"
    state_file.write_text("{not valid json")

    assert load_state(state_file, SEED_DATA) == seed_state(SEED_DATA)


def test_invalid_saved_mission_count_falls_back_to_seed(tmp_path):
    state_file = tmp_path / "ground-control.json"
    state_file.write_text(
        json.dumps(
            {
                "finance": SEED_DATA["finance"],
                "missions": [{"text": "One", "completed": False}],
            }
        )
    )

    assert load_state(state_file, SEED_DATA) == seed_state(SEED_DATA)
