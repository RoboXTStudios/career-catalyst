"""Focused regressions for Product Marketing intent and Evidence diagnostics."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.dynamic_role_intelligence import build_dynamic_voice_profile, detect_role_family
from scripts.evidence_engine import load_evidence_projects
from scripts.evidence_tailoring import evidence_score_contribution, recommend_evidence_ids
from scripts.role_intent import build_role_intent
from scripts.score_match import score_job_data
from scripts.package_generator import generate_package
from tests.test_sprint36_role_intelligence_overrides import _isolated_root


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AXS_TITLE = "Sr. Manager, Product Marketing"
AXS_POSTING = """
Lead product positioning and messaging, go-to-market strategy, product launches,
product education, content strategy, sales enablement, and adoption for an
entertainment marketplace. Coordinate cross-functional work with product,
marketing, business operations, analytics, and industry partners. Build clear
audience narratives, launch plans, and measurement practices for new products.
"""


def test_explicit_product_marketing_title_wins_over_product_strategy_body():
    conflicting = AXS_POSTING + " Own product strategy, roadmaps, OKRs, and operating rhythms."
    profile = build_dynamic_voice_profile("AXS", AXS_TITLE, conflicting)
    intent = build_role_intent(
        {"company": "AXS", "job_title": AXS_TITLE, "raw_text": conflicting}
    )

    assert profile["role_family"] == "product_marketing"
    assert profile["role_family_label"] == "Product Marketing"
    assert intent["primary_archetype"] == "product_marketing"
    assert intent["package_role_family"] == "product_marketing"
    assert intent["package_role_label"] == "Product Marketing"
    assert "positioning" in intent["primary_hiring_need"]
    assert "product education" in intent["primary_hiring_need"]


def test_adjacent_explicit_product_titles_remain_distinct():
    assert detect_role_family("Senior Product Manager", "Own roadmap and product requirements.") == "product_strategy_ops"
    assert detect_role_family("Director, Product Operations", "Run product workflows and adoption.") == "product_strategy_ops"
    assert detect_role_family("Director, Product Strategy", "Own product strategy and roadmap planning.") == "product_strategy_ops"
    assert detect_role_family("Director, Marketing Operations", "Lead marketing workflow and delivery.") == "creative_marketing_ops"
    assert detect_role_family("VP, Campaign Management & Marketing Infrastructure", "Lead campaign workflows and scalable execution.") == "strategy_gtm_operations"
    product_ops = build_role_intent(
        {"job_title": "Director, Product Operations", "raw_text": "Run product workflows and adoption."}
    )
    assert product_ops["primary_archetype"] == "product_operations"
    assert product_ops["package_role_family"] == "product_strategy_ops"


def test_product_marketing_responsibilities_can_resolve_without_title_signal():
    assert detect_role_family(
        "Senior Marketing Lead",
        "Own product positioning, positioning and messaging, product education, and go-to-market strategy.",
    ) == "product_marketing"


def test_product_marketing_material_recipe_is_transferable_not_product_ops():
    intent = build_role_intent(
        {"company": "AXS", "job_title": AXS_TITLE, "raw_text": AXS_POSTING}
    )
    resume = intent["resume"]
    candidate_text = " ".join(
        [
            resume["headline_profile"], resume["summary_profile"],
            *resume["competency_priorities"], intent["primary_hiring_need"],
        ]
    ).lower()

    for expected in ("positioning", "messaging", "launch readiness", "product adoption"):
        assert expected in candidate_text
    for stale in ("ai workflow design", "prompt and schema", "product operations"):
        assert stale not in candidate_text


def test_evidence_diagnostics_use_semantic_requirements_not_junk_tokens():
    job = {
        "company": "Example",
        "job_title": AXS_TITLE,
        "job_description": (
            "Lead product adoption and launch readiness across a cross-functional team. "
            "The program reached more than 400 employees through product education, "
            "audience communications, measurement, and coordinated execution."
        ),
    }
    evidence = [{
        "id": "verified_adoption",
        "title": "Verified Adoption Program",
        "actions": "Built product adoption workflows and product education for stakeholders.",
        "results": "Improved launch readiness and reached more than 400 employees.",
    }]

    first = score_job_data(job, PROJECT_ROOT, evidence)
    second = score_job_data(job, PROJECT_ROOT, evidence)
    contribution = evidence_score_contribution(
        score_job_data(job, PROJECT_ROOT, []), first
    )

    assert first["associated_evidence_match_details"] == second["associated_evidence_match_details"]
    assert "product adoption" in contribution["matched_requirements"]
    assert "launch readiness" in contribution["matched_requirements"]
    assert not {"more", "than", "cross-functional"} & set(contribution["matched_requirements"])
    assert contribution["delta"] == first["match_score"] - first["base_match_score"]


def test_product_marketing_recommendations_are_role_aware_and_preserve_multiverse_provenance():
    projects = load_evidence_projects(PROJECT_ROOT)
    role = {
        "company": "Example Entertainment Marketplace",
        "job_title": AXS_TITLE,
        "raw_text": (
            "Lead audience insights, editorial strategy, content strategy, positioning and messaging, "
            "product education, and go-to-market strategy across internal and external communications."
        ),
    }

    recommended = recommend_evidence_ids(role, projects, limit=4)

    assert "multiverse_editorial" in recommended
    multiverse = next(project for project in projects if project["id"] == "multiverse_editorial")
    assert multiverse["employer"] == "OMG23"
    assert "400" in multiverse["results"]


def test_isolated_axs_package_uses_product_marketing_recipe(tmp_path: Path):
    root, tracker_id = _isolated_root(tmp_path)
    job = root / "jobs" / "axs_product_marketing.md"
    job.write_text(
        "# Sr. Manager, Product Marketing\n\n"
        "Company: AXS\nLocation: Hybrid\n\n## Job Description\n\n"
        + AXS_POSTING,
        encoding="utf-8",
    )
    tracker_path = root / "data" / "application_tracker.yml"
    payload = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
    record = payload["applications"][0]
    record.update(
        {
            "company": "AXS",
            "role": AXS_TITLE,
            "job_file": str(job.relative_to(root)),
            "match_score": 75,
        }
    )
    tracker_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = generate_package(
        tracker_id, root, force_clean_draft=True, export_root=tmp_path / "exports"
    )
    intent = result["manifest"]["role_intent"]
    candidate_text = "\n".join(
        Path(result["manifest"]["files"][key]).read_text(encoding="utf-8")
        for key in ("resume_text", "cover_letter", "application_note", "package_summary")
    ).lower()

    assert intent["package_role_family"] == "product_marketing"
    assert intent["package_role_label"] == "Product Marketing"
    assert intent["primary_cover_letter_story"] == "enterprise_campaign_delivery"
    assert "positioning" in candidate_text
    assert "go-to-market" in candidate_text
    assert "adoption" in candidate_text
    assert "ai workflow design" not in candidate_text
    assert "prompt and schema" not in candidate_text
    assert "product operations leader" not in candidate_text
    assert "career catalyst" not in candidate_text
    assert "campaignos" not in candidate_text
