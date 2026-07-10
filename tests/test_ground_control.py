import json
import re

import pytest

from ground_control.model import (
    FinanceSnapshot,
    build_finance_cards,
    build_major_tom_message,
    calculate_runway_months,
    limit_major_tom_message,
    load_finance_snapshot,
    load_missions,
)
from ground_control.seed_data import SEED_DATA
from ground_control.state import (
    DailyMission,
    GroundControlState,
    load_state,
    save_state,
    seed_state,
)


def test_seed_finance_cards_cover_sprint_one_metrics():
    snapshot = load_finance_snapshot(SEED_DATA)

    cards = build_finance_cards(snapshot)

    assert [card.label for card in cards] == ["Cash", "Runway", "401(k)", "EDD"]


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


def test_major_tom_message_receives_runway_context():
    message = build_major_tom_message(SEED_DATA, runway_months=4.7)

    assert "4.7 months" in message


def test_major_tom_message_is_limited_to_two_short_sentences():
    message = build_major_tom_message(SEED_DATA, runway_months=4.7)
    sentences = re.findall(r".+?(?:[.!?](?=\s|$)|$)", message)

    assert len(sentences) <= 2
    assert all(len(sentence.split()) <= 10 for sentence in sentences)


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
        missions=(
            DailyMission("Call Fidelity", True),
            DailyMission("Update homepage", False),
            DailyMission("Pay phone bill", True),
        ),
    )

    save_state(saved, state_file)
    loaded = load_state(state_file, SEED_DATA)

    assert loaded == saved


def test_saved_finance_recalculates_runway():
    state = GroundControlState(
        person_name="Trisha",
        finance=FinanceSnapshot(
            cash=20000,
            monthly_burn=5000,
            retirement_401k=155000,
            edd_remaining=5000,
        ),
        missions=tuple(DailyMission(f"Mission {index}") for index in range(1, 4)),
    )

    runway = calculate_runway_months(
        cash=state.finance.cash,
        edd_remaining=state.finance.edd_remaining,
        monthly_burn=state.finance.monthly_burn,
    )
    message = build_major_tom_message(SEED_DATA, runway_months=runway)

    assert runway == pytest.approx(5.0)
    assert "5.0 months" in message


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
