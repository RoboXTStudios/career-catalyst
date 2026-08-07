"""Sprint 38.1 regression coverage for experiential/live-event production inference."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.dynamic_role_intelligence import build_dynamic_voice_profile, detect_role_family
from scripts.package_generator import build_package_context
from scripts.parse_job import parse_job_description
from scripts.role_intent import build_role_intent
from scripts.score_match import score_job_match


TITLE = "LN Media & Sponsorship || Future Freelance Opportunities: Live Event Experiential Producers"
POSTING = """
Live Nation Media & Sponsorship seeks experienced producers to manage experiential live event production.
Responsibilities include production management, production budgets and timelines, fabrication, venue sourcing,
onsite builds, load-in/load-out, vendor management, and production logistics. Partner with clients and creative teams.
"""


def test_live_nation_title_and_production_density_route_to_experiential_family():
    profile = build_dynamic_voice_profile("Live Nation Worldwide", TITLE, POSTING)
    assert profile["role_family"] == "experiential_live_event_production"
    assert profile["role_family_label"] == "Experiential Production / Live Event Production"
    assert profile["company_category_label"] == "Music / Live Events & Experiential"
    assert "production management" in " ".join(profile["proof_points_to_emphasize"]).lower()
    assert "Multiverse" not in " ".join(profile["proof_points_to_emphasize"])

    intent = build_role_intent({"company": "Live Nation Worldwide", "job_title": TITLE, "raw_text": POSTING})
    assert intent["package_role_label"] == "Experiential Production / Live Event Production"
    assert "budgets" in intent["primary_hiring_need"]
    assert "load-out" in intent["primary_hiring_need"]
    assert "MarTech campaign execution" in intent["suppressed_evidence"]


def test_experiential_producer_title_requires_production_responsibility_signals():
    assert detect_role_family("Senior Experiential Producer", "Lead experiential production, budgets, vendors, and onsite execution.") == "experiential_live_event_production"
    assert detect_role_family("Live Event Producer", "Own venue logistics, fabrication, production timelines, and load-in/load-out.") == "experiential_live_event_production"
    assert detect_role_family("Producer", "Develop editorial content and publish event coverage for audiences.") == "generic_senior_operator"


def test_negative_controls_keep_marketing_operations_and_editorial_roles_out():
    assert detect_role_family(
        "Marketing Operations Lead",
        "Own marketing operations, annual planning, analytics, and one event communications initiative.",
    ) == "strategy_gtm_operations"
    assert detect_role_family(
        "Editorial Content Strategist",
        "Write editorial coverage of live events, concerts, and community stories.",
    ) == "music_content_strategy"


def test_experiential_family_reaches_isolated_package_context(tmp_path: Path):
    from tests.test_sprint36_role_intelligence_overrides import FOUNDATION_FILES
    import shutil

    root = tmp_path / "runtime"
    shutil.copytree(Path(__file__).resolve().parents[1] / "templates", root / "templates")
    for relative in FOUNDATION_FILES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).resolve().parents[1] / relative, target)
    job = root / "jobs" / "live_nation_experiential_producer.md"
    job.parent.mkdir(parents=True, exist_ok=True)
    job.write_text(
        f"# {TITLE}\n\nCompany: Live Nation Worldwide\nTracker ID: live-nation-role\nOfficial URL: https://example.invalid/live-nation\n\n## Job Description\n{POSTING}",
        encoding="utf-8",
    )
    parsed = parse_job_description(job)
    record = {
        "id": "live-nation-role",
        "stable_slug": "live-nation-role",
        "company": parsed["company"],
        "role": parsed["job_title"],
        "status": "Considered",
        "job_file": str(job.relative_to(root)),
        "match_score": 62,
        "evidence_project_ids": [],
        "material_paths": {},
    }
    tracker = {"applications": [record]}
    (root / "data" / "application_tracker.yml").write_text(yaml.safe_dump(tracker), encoding="utf-8")
    score_before = score_job_match(str(job.relative_to(root)), root, [])
    context = build_package_context("live-nation-role", tracker, root)
    assert context["role_intelligence"]["role_family"] == "experiential_live_event_production"
    assert context["role_intent"]["package_role_label"] == "Experiential Production / Live Event Production"
    assert "MarTech" in " ".join(context["role_intent"]["suppressed_evidence"])
    score_after = score_job_match(str(job.relative_to(root)), root, [])
    assert context["baseline_match_report"]["match_score"] == score_before["match_score"]
    assert score_after["match_score"] == score_before["match_score"]
