import pytest

from ground_control.model import (
    build_finance_cards,
    build_major_tom_message,
    calculate_runway_months,
    load_finance_snapshot,
    load_missions,
)
from ground_control.seed_data import SEED_DATA


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
