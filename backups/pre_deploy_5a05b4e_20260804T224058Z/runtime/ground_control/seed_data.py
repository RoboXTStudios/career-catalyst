"""Safe first-run fallback data for Ground Control.

Manual Override saves runtime changes to local state. This seed remains the
known-good fallback when no saved state exists or saved state cannot be loaded.
"""

from __future__ import annotations

from typing import Any, Final


SEED_DATA: Final[dict[str, Any]] = {
    "person": {
        "name": "Trisha",
    },
    "finance": {
        "cash": 14280,
        "monthly_burn": 4500,
        "retirement_401k": 160000,
        "edd_remaining": 7083,
    },
    "missions": [
        "Check Fidelity rollover status",
        "Finish Ground Control Sprint 1",
        "Protect mortgage runway",
    ],
    "active_project": {
        "name": "Ground Control",
        "priority": "Review Ground Control and define the next release priority",
    },
    "career": {
        "status": "In Flight",
        "summary": "The search is active; keep meaningful conversations moving.",
    },
    "major_tom": (
        "Runway is {runway_months:.1f} months. "
        "Stay steady; no retirement move is needed today."
    ),
}
