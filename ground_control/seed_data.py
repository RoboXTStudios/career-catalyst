"""Editable seed data for Ground Control Sprint 1.

Update this file when the starting balances or daily mission change. The app is
local-first by design: no auth, no backend, no database, and no network calls.
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
