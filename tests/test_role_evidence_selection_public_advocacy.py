from copy import deepcopy
from pathlib import Path

import app

from scripts.generate_cover_letter import _cover_letter_content, load_generation_context
from scripts.generate_messages import _hiring_manager_content, _recruiter_content
from scripts.public_advocacy import positioning_review, rewrite_public_advocacy
from scripts.role_evidence_selection import (
    build_role_evidence_selection,
    selected_evidence,
    update_selection_overrides,
)
from scripts.capability_graph import load_capability_graph
from scripts.evidence_profile import load_evidence_profile
from scripts.score_match import score_job_match


ROOT = Path(__file__).resolve().parents[1]
REDDIT_JOB = "tests/fixtures/jobs/reddit_manager_technical_solutions.md"
UTA_JOB = "tests/fixtures/jobs/uta_director_people_operations.md"


def test_role_evidence_is_selected_automatically_and_excludes_irrelevant_strengths():
    report = score_job_match(REDDIT_JOB, ROOT)
    selection = report["role_evidence_selection"]
    selected_ids = set(selection["selected_evidence_ids"])
    excluded_ids = {item["id"] for item in selection["excluded_evidence"]}

    assert selection["automatic_by_default"] is True
    assert selection["primary_evidence"]
    assert selection["supporting_evidence"]
    assert {"technical_troubleshooting", "cm360", "dv360"} <= selected_ids
    assert "career_catalyst_ai_product" in excluded_ids
    assert all(item["why_selected"] for item in selected_evidence(selection))
    assert "Technical Troubleshooting" in selection["important_capabilities"]


def test_people_role_separates_transferable_leadership_and_known_gaps():
    selection = score_job_match(UTA_JOB, ROOT)["role_evidence_selection"]

    assert "people_leadership" in {
        item["id"] for item in selection["transferable_evidence"]
    }
    assert selection["known_gaps"]
    assert any("Direct evidence is required" in item["reason"] for item in selection["known_gaps"])
    assert not any(
        item["id"].startswith("career_catalyst_")
        for item in selected_evidence(selection)
    )


def test_prospect_overrides_change_contextual_selection_without_mutating_profile():
    profile = load_evidence_profile(ROOT)
    original = deepcopy(profile)
    graph = load_capability_graph(ROOT, profile)
    report = score_job_match(REDDIT_JOB, ROOT)
    matrix = report["capability_graph"]["alignment_matrix"]
    role = {
        "job_title": "Manager, Technical Solutions",
        "raw_text": "advertiser implementation troubleshooting measurement CM360 DV360",
        "primary_archetype": "Technical Solutions / Solutions Consulting",
    }
    overrides = update_selection_overrides({}, "technical_troubleshooting", "exclude")
    overrides = update_selection_overrides(overrides, "people_leadership", "make_primary")
    selection = build_role_evidence_selection(
        role, profile, matrix, report["evidence_gap_analysis"], overrides,
        usage="match_scoring",
    )

    assert "technical_troubleshooting" not in selection["selected_evidence_ids"]
    assert selection["primary_evidence"][0]["id"] == "people_leadership"
    assert profile == original
    assert graph["capabilities"]


def test_package_generation_context_uses_exact_prospect_override_set():
    package_context = {
        "evidence_selection_overrides": {
            "excluded_ids": ["technical_troubleshooting"],
            "included_ids": ["people_leadership"],
            "primary_ids": ["people_leadership"],
            "supporting_ids": [],
            "user_reviewed": True,
        }
    }
    context = load_generation_context(REDDIT_JOB, ROOT, package_context)
    selected_ids = {item["id"] for item in context["selected_profile_evidence"]}
    package_ids = [item["id"] for item in context["selected_evidence_cards"]]

    assert "technical_troubleshooting" not in selected_ids
    assert "people_leadership" in selected_ids
    assert context["role_evidence_selection"]["overrides"]["user_reviewed"] is True
    assert package_ids == context["role_evidence_selection"]["selected_evidence_ids"]


def test_user_demotion_and_include_take_precedence_over_automatic_bucket_limits():
    initial = score_job_match(REDDIT_JOB, ROOT)["role_evidence_selection"]
    primary_id = initial["primary_evidence"][0]["id"]
    excluded_id = initial["excluded_evidence"][-1]["id"]
    overrides = update_selection_overrides({}, primary_id, "demote_supporting")
    overrides = update_selection_overrides(overrides, excluded_id, "include")
    report = score_job_match(
        REDDIT_JOB,
        ROOT,
        evidence_selection_overrides=overrides,
    )["role_evidence_selection"]

    primary_ids = {item["id"] for item in report["primary_evidence"]}
    supporting_ids = {item["id"] for item in report["supporting_evidence"]}
    assert primary_id not in primary_ids
    assert {primary_id, excluded_id}.issubset(supporting_ids)


def test_public_materials_remove_internal_reasoning_and_limitation_narration():
    for job in (REDDIT_JOB, UTA_JOB, "tests/fixtures/jobs/ai_product_operations.md"):
        context = load_generation_context(job, ROOT)
        materials = (
            _cover_letter_content(context),
            _recruiter_content(context),
            _hiring_manager_content(context),
        )
        for material in materials:
            review = positioning_review(material)
            assert review["valid"] is True, review["issues"]
            lowered = material.lower()
            for phrase in (
                "adjacent", "transferable", "strong fit", "good match", "stretch match",
                "match score", "confidence", "unsupported", "this is not",
                "not software engineering", "rather than traditional hr",
            ):
                assert phrase not in lowered


def test_public_advocacy_rewriter_preserves_strengths_and_removes_disclosures():
    internal = (
        "Led technical advertising implementations across Disney Studios and Disney Streaming. "
        "That is strong adjacent experience. This is not software engineering. "
        "I am curious how the team thinks about delivery."
    )
    rewritten, review = rewrite_public_advocacy(
        internal, company="Example Co", role="Technical Solutions"
    )

    assert "Led technical advertising implementations" in rewritten
    assert "adjacent" not in rewritten.lower()
    assert "not software engineering" not in rewritten.lower()
    assert "welcome the opportunity to contribute" in rewritten.lower()
    assert review["valid"] is True


def test_transparency_opt_in_allows_one_limitation_but_not_internal_scoring_terms():
    internal = (
        "Led technical advertising implementations across Disney Studios. "
        "I have not owned an SDK. This is adjacent experience with high confidence."
    )
    rewritten, review = rewrite_public_advocacy(
        internal,
        company="Example Co",
        role="Technical Solutions",
        transparency_requested=True,
    )

    assert "I have not owned an SDK" in rewritten
    assert "adjacent" not in rewritten.lower()
    assert "confidence" not in rewritten.lower()
    assert review["valid"] is True


def test_ui_contains_role_selection_sections_and_override_controls():
    source = Path(app.__file__).read_text(encoding="utf-8")
    for phrase in (
        "Evidence Selected for This Role", "Primary Evidence", "Supporting Evidence",
        "Transferable Evidence", "Known Gaps", "Excluded Evidence", "Why Selected",
        "Make Primary", "Demote to Supporting", "Add Evidence", "Replace Evidence",
        "View Source", "Include", "Exclude",
    ):
        assert phrase in source
