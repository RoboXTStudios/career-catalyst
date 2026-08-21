from __future__ import annotations

from pathlib import Path

import pytest

from scripts.candidate_output import candidate_cover_letter
from scripts.career_claims import PUBLIC_OMG23_NAME, PublicCareerClaimError, validate_public_career_claims
from scripts.evidence_engine import load_evidence_cards, load_evidence_projects, select_evidence_cards
from scripts.evidence_tailoring import candidate_project_reference_violations, evidence_relevance
from scripts.generate_cover_letter import repair_cover_letter_content
from scripts.golden_resume import GoldenResumeError, load_golden_resume, validate_golden_resume
from scripts.resume_foundation import CandidateLanguageError, validate_candidate_language
from scripts.role_state_resolver import resolve_selected_evidence
from scripts.score_match import _score_with_snapshot
from scripts.submission_readiness import build_requirement_coverage_matrix
from scripts.tailor_resume import render_base_resume


ROOT = Path(__file__).resolve().parents[1]


def _by_id(records: list[dict], identifier: str) -> dict:
    return next(record for record in records if record.get("id") == identifier)


def test_canonical_inventory_has_complete_v2_structure_and_stable_atomic_evidence():
    inventory = load_golden_resume(ROOT)
    atomic = inventory["atomic_evidence"]
    stable_ids = [record["stable_id"] for record in atomic]
    parent_ids = {
        record["id"]
        for section in ("employment", "projects", "evidence_projects")
        for record in inventory[section]
    }

    assert validate_golden_resume(inventory)["status"] == "valid"
    assert len(atomic) == 62
    assert len(stable_ids) == len(set(stable_ids))
    assert {record["parent_id"] for record in atomic} <= parent_ids
    assert all(record["candidate_facing_allowed"] in {True, False} for record in atomic)
    assert all(record["canonical_claim"] and record["provenance"] for record in atomic)


def test_production_legacy_evidence_ids_resolve_to_v2_canonical_parents():
    selected_ids = [
        "disney_launch_readiness_tracking_measurement_and_operational_governance",
        "operational_workflow_design_airtable_implementation",
        "career_catalyst_ai_enabled_career_intelligence_application_operations_platform",
    ]
    resolved = resolve_selected_evidence(
        {"evidence_project_ids": selected_ids},
        load_evidence_projects(ROOT),
    )

    assert resolved["selected_ids"] == selected_ids
    assert [project["id"] for project in resolved["projects"]] == [
        "disney_plus_launch_readiness",
        "operational_workflow_design_airtable_implementation",
        "career_catalyst",
    ]
    assert resolved["missing_ids"] == []


def test_exact_education_is_canonical_and_degree_claims_are_blocked():
    inventory = load_golden_resume(ROOT)
    education = inventory["education"]

    assert len(education) == 1
    record = education[0]
    assert record["institution"] == "Los Angeles Valley College"
    assert record["timeframe"] == "2001-2002"
    assert record["study"] == "Business Administration coursework"
    assert record["degree_earned"] is False
    with pytest.raises(CandidateLanguageError):
        validate_candidate_language("Associate degree, Los Angeles Valley College")

    drifted = dict(inventory)
    drifted["education"] = [dict(record, degree_earned=True)]
    with pytest.raises(GoldenResumeError, match="no degree earned"):
        validate_golden_resume(drifted)


def test_public_employer_name_and_scope_are_exact_and_old_short_form_is_rejected():
    inventory = load_golden_resume(ROOT)
    omg23 = _by_id(inventory["employment"], "omg23_omd_entertainment")
    corpus = " ".join(str(value) for value in omg23.values())

    assert PUBLIC_OMG23_NAME == "OMG23 / OMD Entertainment, Omnicom Media Group"
    assert omg23["company"] == PUBLIC_OMG23_NAME
    assert "10 direct reports" in corpus
    assert "64-person organization" in corpus
    validate_public_career_claims(PUBLIC_OMG23_NAME)
    with pytest.raises(PublicCareerClaimError):
        validate_public_career_claims("OMG23 / OMD Entertainment")


def test_projects_have_required_roles_boundaries_and_only_verified_repository():
    inventory = load_golden_resume(ROOT)
    projects = {record["id"]: record for record in inventory["projects"]}

    assert projects["career_catalyst"]["role"] == "Creator & Product Lead"
    assert len(projects["career_catalyst"]["atomic_evidence_ids"]) == 18
    assert projects["roboxt_studios"]["role"] == "Founder & Media Producer"
    assert len(projects["roboxt_studios"]["atomic_evidence_ids"]) == 9
    assert projects["campaignos"]["status"] == "Working prototype"
    assert len(projects["campaignos"]["atomic_evidence_ids"]) == 6
    repositories = [repo for project in projects.values() for repo in project.get("repositories", [])]
    assert [repo["url"] for repo in repositories] == [
        "https://github.com/RoboXTStudios/career-catalyst"
    ]


def test_substack_is_hard_blocked_and_cross_domain_claim_guards_are_canonical():
    inventory = load_golden_resume(ROOT)
    assert "Substack" not in inventory["claim_corpus"]
    with pytest.raises(CandidateLanguageError):
        validate_candidate_language("Published the newsletter on Substack.")
    guardrails = inventory["foundation"]["data"]["personal_brand"]["claim_guardrails"]
    assert "Salesforce" not in guardrails["sales_revenue"]
    assert "CRM administration" in guardrails["sales_revenue"]
    assert "artist management" in guardrails["music_industry"]
    assert "software" in guardrails["technical"]


def test_role_aware_card_priority_prefers_current_product_media_or_enterprise_proof():
    cards = load_evidence_cards(ROOT)
    product = select_evidence_cards(
        {
            "job_title": "Director, AI Product Operations",
            "raw_text": "Own product strategy, AI workflows, requirements, human agency, automation, and quality assurance.",
        },
        cards,
    )
    media = select_evidence_cards(
        {
            "job_title": "Senior Manager, Music Media Production",
            "raw_text": "Lead music media production, photography, video, content operations, and digital publishing.",
        },
        cards,
    )
    traditional = select_evidence_cards(
        {
            "job_title": "Senior Director, PMO",
            "raw_text": "Lead enterprise PMO governance, executive reporting, delivery risk, and program management.",
        },
        cards,
    )

    assert [card["id"] for card in product][:2] == ["career_catalyst", "campaignos"]
    assert media[0]["id"] == "roboxt_studios"
    assert {card["id"] for card in traditional} == {
        "governance_qa_delivery",
        "omg23_disney_leadership",
    }


def test_atomic_child_evidence_is_used_for_parent_relevance_and_score_delta():
    projects = load_evidence_projects(ROOT)
    airtable = _by_id(projects, "operational_workflow_design_airtable_implementation")
    parsed = {
        "job_title": "Director, Workflow Operations",
        "company": "Example",
        "location": "Remote",
        "raw_text": "Lead linked databases, data quality, user training, adoption, and source of truth workflows.",
        "responsibilities": ["Lead linked databases, data quality, user training, adoption, and source of truth workflows."],
        "qualifications": ["Workflow operations"],
        "keywords": ["linked databases", "data quality", "user training", "adoption", "source of truth"],
    }

    assert len(airtable["atomic_evidence"]) == 6
    relevance = evidence_relevance(airtable, parsed)
    assert {"databases", "quality", "training", "adoption"} <= set(relevance["matched_signals"])
    report = _score_with_snapshot(parsed, ROOT, [airtable])
    assert report["evidence_score_delta"] > 0
    assert report["match_score"] > report["base_match_score"]


def test_requirement_coverage_exposes_atomic_evidence_ids():
    inventory = load_golden_resume(ROOT)
    parsed = {
        "job_title": "Workflow Operations Director",
        "raw_text": "Build linked databases and establish data quality workflows.",
        "responsibilities": ["Build linked databases and establish data quality workflows."],
        "qualifications": [],
        "preferred_qualifications": [],
    }
    matrix = build_requirement_coverage_matrix(parsed, inventory, [], "Linked databases and data quality workflows")
    evidence_ids = {identifier for row in matrix for identifier in row["evidence_ids"]}
    assert any(identifier.startswith("atomic_airtable_") for identifier in evidence_ids)


def test_python_is_canonical_working_knowledge_but_not_in_unrelated_base_sections():
    inventory = load_golden_resume(ROOT)
    platforms_and_tools = _by_id(inventory["skill_groups"], "platforms_and_tools")
    assert platforms_and_tools["skills"]["technical"] == ["Python — Working Knowledge"]
    base_resume = render_base_resume(ROOT)
    assert "Python (Working Knowledge)" in base_resume
    assert "Python expert" not in base_resume


def test_project_provenance_blocks_unselected_project_leakage():
    projects = load_evidence_projects(ROOT)
    career_catalyst = _by_id(projects, "career_catalyst")
    text = "Career Catalyst demonstrates grounded product ownership. CampaignOS is a working prototype."
    violations = candidate_project_reference_violations(
        text,
        {
            "evidence_scope_enforced": True,
            "associated_evidence_projects": [career_catalyst],
            "career_data": load_golden_resume(ROOT)["foundation"],
        },
        "cover_letter",
    )
    assert "campaignos" in violations
    assert "career catalyst" not in violations


def test_strategy_cover_letter_uses_selected_career_catalyst_once():
    projects = load_evidence_projects(ROOT)
    career_catalyst = _by_id(projects, "career_catalyst")
    airtable = _by_id(projects, "operational_workflow_design_airtable_implementation")
    parsed = {
        "job_title": "Associate Manager, Marketing Operations",
        "company": "Example",
        "raw_text": "Lead strategy, planning, workflow design, requirements, and cross-functional operations.",
        "responsibilities": ["Lead strategy, planning, workflow design, and requirements."],
        "qualifications": ["Cross-functional operations"],
        "keywords": ["strategy", "planning", "workflow design", "requirements"],
    }
    letter = candidate_cover_letter(
        {
            "parsed_job": parsed,
            "associated_evidence_projects": [career_catalyst, airtable],
            "evidence_scope_enforced": True,
            "role_intent": {
                "package_role_family": "strategy_gtm_operations",
                "primary_archetype": "general_operations",
                "cover_letter": {"greeting": "Dear Hiring Team,"},
            },
        }
    )

    assert letter.count("Career Catalyst") == 1
    assert "Career Catalyst is a current product-building proof point" not in letter
    assert sum("airtable" in paragraph.lower() for paragraph in letter.split("\n\n")) == 1
    assert "selected Evidence records" not in letter
    assert "verified experience" not in letter


def test_cover_letter_length_repair_does_not_duplicate_existing_proof_paragraph():
    proof = (
        "I would apply that discipline to the role's stated priorities, with clear decisions, visible dependencies, "
        "and practical follow-through. I value operating systems that improve quality and momentum without adding "
        "process teams cannot sustain. My approach is grounded in direct experience, clear communication, and "
        "respect for the people closest to the work."
    )
    content = "\n\n".join(
        [
            "Dear Hiring Team,",
            "I am interested in this role because it connects thoughtful planning with dependable execution. " * 6,
            proof,
            "Best,\n\nTrisha Lynch",
        ]
    )
    repaired = repair_cover_letter_content(
        content,
        {
            "parsed_job": {"company": "Example"},
            "role_intent": {"package_role_family": "general_operations"},
        },
    )

    assert repaired.count(proof) == 1
    assert "I would begin by learning how the team coordinates priorities today" in repaired
