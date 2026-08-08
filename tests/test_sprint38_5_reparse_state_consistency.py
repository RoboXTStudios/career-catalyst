"""Sprint 38.5 regressions for one authoritative reparsed prospect state."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from app import _match_score_html, reparse_dashboard_role
from scripts.application_tracker import load_application_tracker
from scripts.package_generator import build_package_context
from scripts.parse_job import parse_job_description
from scripts.role_intent import tailoring_plan


ROOT = Path(__file__).resolve().parents[1]
from tests.test_sprint36_role_intelligence_overrides import FOUNDATION_FILES


TITLE = "LN Media & Sponsorship || Future Freelance Opportunities: Live Event Experiential Producers"
POSTING = """
Live Nation Media & Sponsorship seeks experienced producers to manage experiential live event production.
Responsibilities include production management, production budgets and timelines, fabrication, venue sourcing,
onsite builds, load-in/load-out, vendor management, and production logistics. Partner with clients and creative teams.
"""


def _reopened_live_nation_root(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "runtime"
    shutil.copytree(ROOT / "templates", root / "templates")
    for relative in FOUNDATION_FILES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    job = root / "jobs" / "live_nation_experiential_producer.md"
    job.parent.mkdir(parents=True, exist_ok=True)
    job.write_text(
        f"# {TITLE}\n\n"
        "Company: Live Nation Worldwide\n"
        "Tracker ID: live-nation-reopened\n"
        "Location: California\n"
        "Work arrangement: On-site\n"
        "Official URL: https://example.invalid/live-nation\n\n"
        f"## Job Description\n{POSTING}",
        encoding="utf-8",
    )
    parsed = parse_job_description(job)
    record = {
        "id": "live-nation-reopened",
        "stable_slug": "live-nation-reopened",
        "company": parsed["company"],
        "role": parsed["job_title"],
        "status": "Prospect",
        "priority": "Medium",
        "show_on_dashboard": True,
        "location": "Work From Home - New York",
        "work_arrangement": "Not specified",
        "job_file": str(job.relative_to(root)),
        # This is the canonical score saved by the successful reparse/rescore.
        "match_score": 62,
        "match_tier": "Stretch Match",
        "match_summary": "Canonical canary score.",
        "match_strengths": [
            "Experiential production responsibilities are explicit.",
            "Live event scope is clearly identified.",
            "The posting provides enough detail for review.",
        ],
        "match_gaps": ["Confirm reporting line before applying."],
        "recommended_action": "Review First",
        "confidence": "Medium",
        "evidence_project_ids": [],
        "material_paths": {},
        "application_history": [{"event": "created", "date": "2026-08-07"}],
    }
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump({"applications": [record]}, sort_keys=False), encoding="utf-8"
    )
    return root, record["id"]


def test_reopened_live_nation_uses_one_saved_score_and_effective_role_state(tmp_path: Path):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    context = build_package_context(
        tracker_id,
        [{"id": tracker_id, **yaml.safe_load((root / "data" / "application_tracker.yml").read_text())["applications"][0]}],
        root,
    )

    # The posting parses to different metadata and a different computed score,
    # but the saved prospect state is authoritative after reparse/rescore.
    assert context["match_report"]["match_score"] == 62
    assert context["baseline_match_report"]["match_score"] == 62
    assert context["evidence_score_contribution"] == {
        "before": 62,
        "after": 62,
        "delta": 0,
        "matched_requirements": [],
        "explanation": "No additional role requirements were matched by the selected Evidence.",
    }
    assert "Not scored yet" not in _match_score_html(context["match_report"])
    assert context["parsed_job"]["location"] == "Work From Home - New York"
    assert context["parsed_job"]["work_arrangement"] == "Not specified"

    intelligence = context["role_intelligence"]
    assert intelligence["role_family_label"] == "Experiential Production / Live Event Production"
    assert intelligence["company_category_label"] == "Music / Live Events & Experiential"
    assert intelligence["company_voice_label"] == "Music + Experiential Production"

    plan = tailoring_plan(context["role_intent"])
    assert plan["company_voice"] == "Music + Experiential Production"
    assert plan["company_category"] == "Music / Live Events & Experiential"
    assert plan["role_family"] == "Experiential Production / Live Event Production"
    assert plan["evidence_score_contribution"]["delta"] == 0


def test_reparse_persists_canonical_score_without_overwriting_saved_location(
    tmp_path: Path, monkeypatch
):
    root, tracker_id = _reopened_live_nation_root(tmp_path)

    def canonical_reparse_score(*_args, **_kwargs):
        return {
            "match_score": 62,
            "match_band": "Stretch Match",
            "match_tier": "Stretch Match",
            "match_summary": "Canonical canary score.",
            "match_strengths": [
                "Experiential production responsibilities are explicit.",
                "Live event scope is clearly identified.",
                "The posting provides enough detail for review.",
            ],
            "match_gaps": ["Confirm reporting line before applying."],
            "recommended_action": "Review First",
            "confidence": "Medium",
        }

    monkeypatch.setattr("app.score_job_data", canonical_reparse_score)
    reparse_dashboard_role(tracker_id, project_root=root)
    saved = load_application_tracker(root)[0]
    assert saved["match_score"] == 62
    assert saved["location"] == "Work From Home - New York"
    assert saved["work_arrangement"] == "Not specified"
    assert saved["role_family"] == "experiential_live_event_production"
