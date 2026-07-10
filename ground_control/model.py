"""Pure helpers for Ground Control's local-first dashboard."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from ground_control.seed_data import SEED_DATA


@dataclass(frozen=True)
class FinanceSnapshot:
    cash: float
    monthly_burn: float
    retirement_401k: float
    edd_remaining: float


@dataclass(frozen=True)
class FinanceCard:
    label: str
    value: str
    caption: str


def format_dollars(amount: float) -> str:
    return f"${amount:,.0f}"


def calculate_runway_months(*, cash: float, edd_remaining: float, monthly_burn: float) -> float:
    if monthly_burn <= 0:
        raise ValueError("monthly_burn must be greater than zero")
    return (cash + edd_remaining) / monthly_burn


def _number_from_seed(section: Mapping[str, Any], key: str) -> float:
    value = section.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"Seed value finance.{key} must be a number")
    return float(value)


def load_finance_snapshot(seed: Mapping[str, Any] = SEED_DATA) -> FinanceSnapshot:
    finance = seed.get("finance")
    if not isinstance(finance, Mapping):
        raise ValueError("Seed data must include a finance mapping")

    return FinanceSnapshot(
        cash=_number_from_seed(finance, "cash"),
        monthly_burn=_number_from_seed(finance, "monthly_burn"),
        retirement_401k=_number_from_seed(finance, "retirement_401k"),
        edd_remaining=_number_from_seed(finance, "edd_remaining"),
    )


def build_finance_cards(snapshot: FinanceSnapshot) -> list[FinanceCard]:
    runway_months = calculate_runway_months(
        cash=snapshot.cash,
        edd_remaining=snapshot.edd_remaining,
        monthly_burn=snapshot.monthly_burn,
    )

    return [
        FinanceCard(
            label="Cash",
            value=format_dollars(snapshot.cash),
            caption="Current checking/savings seed value",
        ),
        FinanceCard(
            label="Runway",
            value=f"{runway_months:.1f} mo",
            caption=f"Cash plus EDD at {format_dollars(snapshot.monthly_burn)}/mo",
        ),
        FinanceCard(
            label="401(k)",
            value=format_dollars(snapshot.retirement_401k),
            caption="Traditional pre-tax balance estimate",
        ),
        FinanceCard(
            label="EDD",
            value=format_dollars(snapshot.edd_remaining),
            caption="Remaining unemployment claim balance",
        ),
    ]


def load_missions(seed: Mapping[str, Any] = SEED_DATA) -> list[str]:
    missions = seed.get("missions")
    if not isinstance(missions, list) or not all(isinstance(item, str) for item in missions):
        raise ValueError("Seed data must include a missions list of strings")
    if len(missions) != 3:
        raise ValueError("Ground Control expects exactly three missions")
    return missions


def _brief_sentences(message: str) -> list[str]:
    sentences = re.findall(r".+?(?:[.!?](?=\s|$)|$)", message.strip())
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def limit_major_tom_message(message: str, *, max_sentences: int = 2) -> str:
    sentences = _brief_sentences(message)
    if not sentences:
        return ""
    return " ".join(sentences[:max_sentences])


def runway_status(runway_months: float) -> str:
    if runway_months < 1:
        return "critical burn"
    if runway_months < 3:
        return "adjust course"
    return "nominal"


def build_major_tom_message(
    seed: Mapping[str, Any] = SEED_DATA,
    *,
    runway_months: float,
    current_date: date | None = None,
    missions_completed: int = 0,
) -> str:
    del seed  # Retained for API compatibility with existing callers.
    today = current_date or date.today()
    completed = min(max(missions_completed, 0), 3)
    first = (
        f"{today.strftime('%A, %B')} {today.day}: runway is "
        f"{runway_months:.1f} months and {runway_status(runway_months)}."
    )
    if completed == 3:
        second = "All three missions complete; flight plan secured."
    elif completed == 0:
        second = "Three missions remain; choose the first move."
    else:
        second = f"{completed} of 3 missions complete; hold course."
    return limit_major_tom_message(f"{first} {second}")
