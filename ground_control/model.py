"""Pure helpers for Ground Control's local-first dashboard."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from ground_control.local_time import local_date
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


@dataclass(frozen=True)
class FinancialState:
    status: str
    runway_months: float
    runway_label: str
    summary: str


@dataclass(frozen=True)
class CreativeState:
    status: str
    project_name: str
    summary: str


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
    return [
        FinanceCard(
            label="Cash",
            value=format_dollars(snapshot.cash),
            caption="Current checking and savings",
        ),
        FinanceCard(
            label="Essentials burn",
            value=format_dollars(snapshot.monthly_burn),
            caption="Monthly essential expenses",
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


def runway_status_label(runway_months: float) -> str:
    return {
        "nominal": "Nominal",
        "adjust course": "Adjust Course",
        "critical burn": "Critical Burn",
    }[runway_status(runway_months)]


def build_financial_state(snapshot: FinanceSnapshot) -> FinancialState:
    runway_months = calculate_runway_months(
        cash=snapshot.cash,
        edd_remaining=snapshot.edd_remaining,
        monthly_burn=snapshot.monthly_burn,
    )
    status = runway_status_label(runway_months)
    summaries = {
        "Nominal": "Runway is stable. Keep essential spending on course.",
        "Adjust Course": "Runway needs attention. Review the next essential moves.",
        "Critical Burn": "Runway is compressed. Protect immediate essentials first.",
    }
    return FinancialState(
        status=status,
        runway_months=runway_months,
        runway_label=f"{runway_months:.1f} months",
        summary=summaries[status],
    )


def build_creative_state(
    seed: Mapping[str, Any] = SEED_DATA,
    *,
    missions: Sequence[object] = (),
) -> CreativeState:
    project = seed.get("active_project")
    if not isinstance(project, Mapping) or not project.get("name") or not project.get("priority"):
        raise ValueError("Seed data must include an active project name and priority")

    project_name = str(project["name"]).strip()
    priority = str(project["priority"]).strip()
    matching_mission = next(
        (
            mission
            for mission in missions
            if getattr(mission, "text", "") == priority
            or project_name.casefold() in str(getattr(mission, "text", "")).casefold()
        ),
        None,
    )
    if matching_mission is None:
        return CreativeState(
            status="Holding Pattern",
            project_name=project_name,
            summary="The active project is ready for its next deliberate move.",
        )
    if bool(getattr(matching_mission, "completed", False)):
        return CreativeState(
            status="Momentum Secured",
            project_name=project_name,
            summary="Today's project priority is complete.",
        )
    return CreativeState(
        status="In Motion",
        project_name=project_name,
        summary="Today's project priority is on the flight plan.",
    )


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
    *,
    mission_summary: str,
    current_date: date | None = None,
    missions_completed: int = 0,
    next_mission: str | None = None,
) -> str:
    today = current_date or local_date()
    completed = min(max(missions_completed, 0), 3)
    engine_summary = mission_summary.strip().rstrip(".") or "Mission systems waiting"
    first = f"{today.strftime('%A, %B')} {today.day}: {engine_summary}."
    if completed == 3:
        second = "All missions complete; today's momentum is secured."
    elif next_mission:
        short_mission = " ".join(next_mission.split()[:8])
        second = f"Next move: {short_mission}."
    elif completed == 0:
        second = "Choose the first mission and hold course."
    else:
        second = f"{completed} missions complete; hold course."
    return limit_major_tom_message(f"{first} {second}")
