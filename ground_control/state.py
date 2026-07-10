"""Local persistence for Ground Control manual overrides."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ground_control.model import FinanceSnapshot, load_finance_snapshot, load_missions
from ground_control.seed_data import SEED_DATA


STATE_VERSION = 1
DEFAULT_STATE_FILE = Path(__file__).resolve().parent / "local_state.json"


@dataclass(frozen=True)
class DailyMission:
    text: str
    completed: bool = False


@dataclass(frozen=True)
class GroundControlState:
    person_name: str
    finance: FinanceSnapshot
    missions: tuple[DailyMission, ...]


def _seed_person_name(seed: Mapping[str, Any]) -> str:
    person = seed.get("person")
    if isinstance(person, Mapping) and person.get("name"):
        return str(person["name"])
    return "Trisha"


def seed_state(seed: Mapping[str, Any] = SEED_DATA) -> GroundControlState:
    return GroundControlState(
        person_name=_seed_person_name(seed),
        finance=load_finance_snapshot(seed),
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


def _missions_from_saved(raw: Mapping[str, Any], seed: Mapping[str, Any]) -> tuple[DailyMission, ...]:
    seed_missions = load_missions(seed)
    saved_missions = raw.get("missions")
    if not isinstance(saved_missions, list):
        return tuple(DailyMission(text=mission) for mission in seed_missions)
    if len(saved_missions) != 3:
        raise ValueError("Ground Control expects exactly three missions")

    return tuple(
        _mission_from_saved(mission, fallback)
        for mission, fallback in zip(saved_missions, seed_missions)
    )


def state_from_mapping(raw: Mapping[str, Any], seed: Mapping[str, Any] = SEED_DATA) -> GroundControlState:
    person = raw.get("person")
    person_name = _seed_person_name(seed)
    if isinstance(person, Mapping) and person.get("name"):
        person_name = str(person["name"])

    return GroundControlState(
        person_name=person_name,
        finance=_finance_from_saved(raw, seed),
        missions=_missions_from_saved(raw, seed),
    )


def state_to_mapping(state: GroundControlState) -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "person": {"name": state.person_name},
        "finance": {
            "cash": state.finance.cash,
            "monthly_burn": state.finance.monthly_burn,
            "retirement_401k": state.finance.retirement_401k,
            "edd_remaining": state.finance.edd_remaining,
        },
        "missions": [
            {"text": mission.text, "completed": mission.completed}
            for mission in state.missions
        ],
    }


def load_state(path: Path = DEFAULT_STATE_FILE, seed: Mapping[str, Any] = SEED_DATA) -> GroundControlState:
    if not path.exists():
        return seed_state(seed)

    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, Mapping):
            raise ValueError("Saved Ground Control state must be a mapping")
        return state_from_mapping(raw, seed)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return seed_state(seed)


def save_state(state: GroundControlState, path: Path = DEFAULT_STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state_to_mapping(state), indent=2) + "\n")
