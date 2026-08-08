"""Sprint 38.4 regression coverage for effective-role scoring diagnostics."""

from __future__ import annotations

from pathlib import Path

from scripts.dynamic_role_intelligence import build_dynamic_voice_profile
from scripts.role_intent import build_role_intent, tailoring_plan
from scripts.score_match import score_job_data


TITLE = "LN Media & Sponsorship || Future Freelance Opportunities: Live Event Experiential Producers"
POSTING = """
Live Nation Media & Sponsorship seeks experienced producers to manage experiential live event production.
Responsibilities include production management, production budgets and timelines, fabrication, venue sourcing,
onsite builds, load-in/load-out, vendor management, and production logistics. Partner with clients and creative teams.
"""


def test_reparsed_live_nation_diagnostics_follow_effective_experiential_intelligence(tmp_path: Path):
    role = {
        "company": "Live Nation Worldwide",
        "job_title": TITLE,
        "job_description": POSTING,
        "raw_text": POSTING,
    }
    effective = build_dynamic_voice_profile(role["company"], TITLE, POSTING)
    intent = build_role_intent({**role, "role_family": effective["role_family"]}, tmp_path)

    baseline = score_job_data(role, tmp_path)
    first = score_job_data(role, tmp_path, role_intelligence=effective)
    second = score_job_data(role, tmp_path, role_intelligence=effective)
    plan = tailoring_plan(intent)

    assert effective["role_family_label"] == "Experiential Production / Live Event Production"
    assert effective["company_category_label"] == "Music / Live Events & Experiential"
    assert plan["matched_signals"] == [
        "Experiential production",
        "Live-event execution",
        "Production/project management",
        "Budget management",
        "Timeline management",
        "Vendor/fabrication management",
        "Venue/logistics coordination",
        "Creative-production coordination",
        "Onsite execution",
    ]
    assert first["match_score"] == baseline["match_score"] == second["match_score"]
    assert first["matched_signals"][:4] == [
        "experiential production",
        "live-event execution",
        "production management",
        "budget and timeline management",
    ]
    diagnostics = " ".join(first["match_strengths"] + first["matched_signals"]).lower()
    assert "marketing technology" not in diagnostics
    assert "martech" not in diagnostics
    assert "tracking" not in diagnostics
    assert "training" not in diagnostics
    assert "experiential production" in diagnostics
    assert "live-event execution" in diagnostics
