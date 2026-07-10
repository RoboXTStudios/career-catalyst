"""Local persistence for Ground Control manual overrides and daily missions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from ground_control.model import FinanceSnapshot, load_finance_snapshot, load_missions
from ground_control.seed_data import SEED_DATA


STATE_VERSION = 2
MISSION_COUNT = 3
HISTORY_LIMIT = 30
DEFAULT_STATE_FILE = Path(__file__).resolve().parent / "local_state.json"


@dataclass(frozen=True)
class DailyMission:
    text: str
    completed: bool = False


@dataclass(frozen=True)
class MissionDay:
    date: str
    missions: tuple[DailyMission, ...]


@dataclass(frozen=True)
class GroundControlState:
    person_name: str
    finance: FinanceSnapshot
    mission_date: str
    missions: tuple[DailyMission, ...]
    mission_history: tuple[MissionDay, ...] = ()


def _seed_person_name(seed: Mapping[str, Any]) -> str:
    person = seed.get("person")
    if isinstance(person, Mapping) and person.get("name"):
        return str(person["name"])
    return "Trisha"


def _blank_missions() -> tuple[DailyMission, ...]:
    return tuple(DailyMission(f"Mission {index}") for index in range(1, MISSION_COUNT + 1))


def seed_state(
    seed: Mapping[str, Any] = SEED_DATA,
    *,
    current_date: date | None = None,
) -> GroundControlState:
    today = current_date or date.today()
    return GroundControlState(
        person_name=_seed_person_name(seed),
        finance=load_finance_snapshot(seed),
        mission_date=today.isoformat(),
        missions=tuple(DailyMission(text=mission) for mission in load_missions(seed)),
    )


def _finance_from_saved(raw: Mapping[str, Any], seed: Mapping[str, Any]) -> FinanceSnapshot:
    seed_finance = seed.get("finance")
    if not isinstance(seed_finance, Mapping):
        raise ValueError("Seed data must include a finance mapping")

    saved_finance = raw.get("finance")
    merged_finance = dict(seed_finance)
    if isinstance(saved_finance, Mapping):
        merged_finance.update(saved_finance)

    return load_finance_snapshot({"finance": merged_finance})


def _mission_text(value: object, fallback: str) -> str:
    text = str(value).strip()
    return text or fallback


def _mission_from_saved(value: object, fallback: str) -> DailyMission:
    if isinstance(value, Mapping):
        return DailyMission(
            text=_mission_text(value.get("text", ""), fallback),
            completed=bool(value.get("completed", False)),
        )
    return DailyMission(text=_mission_text(value, fallback))


def _missions_from_values(values: object, fallbacks: list[str]) -> tuple[DailyMission, ...]:
    if not isinstance(values, list):
        return tuple(DailyMission(text=mission) for mission in fallbacks)
    if len(values) != MISSION_COUNT:
        raise ValueError("Ground Control expects exactly three missions")
    return tuple(
        _mission_from_saved(mission, fallback)
        for mission, fallback in zip(values, fallbacks)
    )


def _mission_history_from_saved(raw: Mapping[str, Any]) -> tuple[MissionDay, ...]:
    saved_history = raw.get("mission_history", [])
    if not isinstance(saved_history, list):
        raise ValueError("Mission history must be a list")

    history: list[MissionDay] = []
    fallbacks = [f"Mission {index}" for index in range(1, MISSION_COUNT + 1)]
    for item in saved_history[-HISTORY_LIMIT:]:
        if not isinstance(item, Mapping) or not item.get("date"):
            raise ValueError("Mission history entries require a date")
        history.append(
            MissionDay(
                date=str(item["date"]),
                missions=_missions_from_values(item.get("missions"), fallbacks),
            )
        )
    return tuple(history)


def state_from_mapping(
    raw: Mapping[str, Any],
    seed: Mapping[str, Any] = SEED_DATA,
    *,
    current_date: date | None = None,
) -> GroundControlState:
    today = current_date or date.today()
    person = raw.get("person")
    person_name = _seed_person_name(seed)
    if isinstance(person, Mapping) and person.get("name"):
        person_name = str(person["name"])

    return GroundControlState(
        person_name=person_name,
        finance=_finance_from_saved(raw, seed),
        mission_date=str(raw.get("mission_date") or today.isoformat()),
        missions=_missions_from_values(raw.get("missions"), load_missions(seed)),
        mission_history=_mission_history_from_saved(raw),
    )


def state_to_mapping(state: GroundControlState) -> dict[str, Any]:
    def missions_to_mapping(missions: tuple[DailyMission, ...]) -> list[dict[str, Any]]:
        return [
            {"text": mission.text, "completed": mission.completed}
            for mission in missions
        ]

    return {
        "version": STATE_VERSION,
        "person": {"name": state.person_name},
        "finance": {
            "cash": state.finance.cash,
            "monthly_burn": state.finance.monthly_burn,
            "retirement_401k": state.finance.retirement_401k,
            "edd_remaining": state.finance.edd_remaining,
        },
        "mission_date": state.mission_date,
        "missions": missions_to_mapping(state.missions),
        "mission_history": [
            {"date": day.date, "missions": missions_to_mapping(day.missions)}
            for day in state.mission_history[-HISTORY_LIMIT:]
        ],
    }


def rollover_for_date(state: GroundControlState, current_date: date) -> GroundControlState:
    today = current_date.isoformat()
    if state.mission_date == today:
        return state

    history = (*state.mission_history, MissionDay(state.mission_date, state.missions))
    return replace(
        state,
        mission_date=today,
        missions=_blank_missions(),
        mission_history=history[-HISTORY_LIMIT:],
    )


def unfinished_from_previous_day(state: GroundControlState) -> tuple[DailyMission, ...]:
    if not state.mission_history:
        return ()
    return tuple(
        DailyMission(mission.text)
        for mission in state.mission_history[-1].missions
        if not mission.completed
    )


def reuse_unfinished_missions(state: GroundControlState) -> GroundControlState:
    unfinished = unfinished_from_previous_day(state)[:MISSION_COUNT]
    reused = (*unfinished, *_blank_missions()[len(unfinished):])
    return replace(state, missions=tuple(reused))


def load_state(
    path: Path = DEFAULT_STATE_FILE,
    seed: Mapping[str, Any] = SEED_DATA,
    *,
    current_date: date | None = None,
) -> GroundControlState:
    if not path.exists():
        return seed_state(seed, current_date=current_date)

    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, Mapping):
            raise ValueError("Saved Ground Control state must be a mapping")
        return state_from_mapping(raw, seed, current_date=current_date)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return seed_state(seed, current_date=current_date)


def save_state(state: GroundControlState, path: Path = DEFAULT_STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state_to_mapping(state), indent=2) + "\n")
