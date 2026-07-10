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
    "major_tom": (
        "Cash plus EDD covers about {runway_months:.1f} months at the current "
        "essentials burn. No retirement move needs to happen today; keep the signal clean."
    ),
}
