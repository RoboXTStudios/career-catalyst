from difflib import SequenceMatcher
from pathlib import Path

import pytest

from scripts.employer_identity import (
    OMG23_DISPLAY_NAME,
    canonical_employer_name,
    normalize_applicant_employer_names,
)
from scripts.evidence_engine import load_evidence_cards, professional_evidence_recommendations
from scripts.generate_cover_letter import (
    _cover_letter_content,
    _word_count,
    load_generation_context,
)
from scripts.generate_messages import _hiring_manager_content, _recruiter_content
from scripts.generate_strategy_pack import _render_strategy_pack
from scripts.human_positioning import positioning_violations
from scripts.load_data import load_all_yaml
from scripts.package_context import PackageContextMismatchError, validate_material_context
from scripts.parse_job import parse_job_description
from scripts.role_lens import (
    GENERIC_ADVISORY_PHRASES,
    PEOPLE_OPERATIONS_OVERCLAIMS,
    build_requirement_map,
    classify_role_lens,
    enforce_role_lens_quality,
    role_lens_quality_violations,
)
from scripts.score_match import score_job_match
from scripts.tailor_resume import _render_markdown


ROOT = Path(__file__).resolve().parents[1]
UTA_JOB = "jobs/united_talent_agency_director_people_operations.md"
BUSINESS_JOB = "jobs/sample_job_description.md"
MARKETING_JOB = "jobs/paramount_director_marketing_operations.md"
DISABLED_EVIDENCE = ("Career Catalyst", "CampaignOS", "Substack")


@pytest.mark.parametrize(
    "alias",
    (
        "OMG23",
        "OMD Entertainment",
        "Omnicom Media Group",
        "OMG23 / OMD Entertainment",
        "OMG23 / OMD Entertainment, Omnicom Media Group",
    ),
)
def test_historical_employer_aliases_normalize_to_one_display_name(alias):
    assert canonical_employer_name(alias) == OMG23_DISPLAY_NAME


def test_employer_full_name_appears_once_and_later_references_use_shorthand():
    content = normalize_applicant_employer_names(
        "At OMG23 / OMD Entertainment, Omnicom Media Group, I led the work.\n\n"
        "At OMG23 / OMD Entertainment, I improved the workflow."
    )

    assert content.count(OMG23_DISPLAY_NAME) == 1
    assert "At OMG23, I improved" in content
    assert "OMD Entertainment" not in content


def test_uta_is_people_operations_with_organizational_effectiveness_secondary():
    parsed = parse_job_description(ROOT / UTA_JOB)
    lens = classify_role_lens(parsed)

    assert lens["primary"] == "people_operations"
    assert lens["secondary"] == "organizational_effectiveness"
    assert lens["confidence_label"] == "High"
    assert {"people strategy", "employee life cycle", "people systems"}.issubset(
        set(lens["supporting_signals"])
    )


def test_role_lens_uses_description_signals_instead_of_title_alone():
    lens = classify_role_lens(
        {
            "job_title": "Director, People Operations",
            "job_description": (
                "Own marketing operations, campaign execution, marketing performance, CRM, "
                "brand marketing, and campaign measurement across a global portfolio."
            ),
        }
    )

    assert lens["primary"] == "marketing_operations"


def test_uta_requirement_map_separates_transferable_and_unsupported_work():
    parsed = parse_job_description(ROOT / UTA_JOB)
    requirements = build_requirement_map(parsed, classify_role_lens(parsed))
    unsupported = {
        item["normalized_concept"]
        for item in requirements
        if item["strength"] == "Unsupported"
    }
    transferable = [
        item for item in requirements if item["strength"] == "Strong transferable evidence"
    ]

    assert {
        "organizational design",
        "people analytics",
        "employee lifecycle ownership",
        "direct People Operations tenure",
        "people policy ownership",
    }.issubset(unsupported)
    assert any("governance_qa_delivery" in item["evidence_ids"] for item in transferable)
    assert any("omg23_disney_leadership" in item["evidence_ids"] for item in transferable)


def test_people_operations_evidence_prioritizes_team_change_and_communication():
    parsed = parse_job_description(ROOT / UTA_JOB)
    lens = classify_role_lens(parsed)
    parsed = {**parsed, "primary_role_lens": lens["primary"], "role_lens": lens}
    evidence = professional_evidence_recommendations(
        parsed, load_evidence_cards(ROOT)
    )
    rendered = " ".join((*evidence["ids"], *evidence["proof_points"])).lower()

    assert evidence["ids"][:2] == [
        "governance_qa_delivery",
        "omg23_disney_leadership",
    ]
    assert "multiverse_editorial" in evidence["ids"]
    assert "cross-functional teams of 60+" in rendered
    assert "martech_campaign_execution" not in evidence["ids"]
    assert "seller enablement" not in rendered
    assert "product activation" not in rendered


def _uta_materials():
    context = load_generation_context(UTA_JOB, ROOT)
    return context, {
        "cover_letter": _cover_letter_content(context),
        "recruiter": _recruiter_content(context),
        "hiring_manager": _hiring_manager_content(context),
        "strategy_pack": _render_strategy_pack(context),
    }


def test_uta_materials_are_transparent_and_do_not_generate_unsupported_hr_claims():
    _context, materials = _uta_materials()
    combined = "\n".join(materials.values()).lower()

    assert "operations rather than a traditional hr function" in combined
    assert "transferable" in combined
    for phrase in PEOPLE_OPERATIONS_OVERCLAIMS:
        assert phrase not in combined


def test_uta_cover_letter_is_people_specific_and_not_advisory_transformation_copy():
    _context, materials = _uta_materials()
    letter = materials["cover_letter"]
    lowered = letter.lower()

    assert 250 <= _word_count(letter) <= 350
    assert letter.count(OMG23_DISPLAY_NAME) == 1
    assert "how people experience the way an organization works" in lowered
    assert "people closest to the work" in lowered
    assert "people team" in lowered
    for phrase in GENERIC_ADVISORY_PHRASES:
        assert phrase not in lowered


def test_uta_letter_differs_materially_from_business_and_marketing_variants():
    uta = _cover_letter_content(load_generation_context(UTA_JOB, ROOT))
    business = _cover_letter_content(load_generation_context(BUSINESS_JOB, ROOT))
    marketing = _cover_letter_content(load_generation_context(MARKETING_JOB, ROOT))

    assert SequenceMatcher(None, uta, business).ratio() < 0.65
    assert SequenceMatcher(None, uta, marketing).ratio() < 0.65
    assert "traditional HR function" in uta
    assert "traditional HR function" not in business
    assert "traditional HR function" not in marketing


def test_uta_messages_address_people_operations_problems_not_swapped_titles():
    _context, materials = _uta_materials()
    recruiter = materials["recruiter"]
    manager = materials["hiring_manager"]

    assert 80 <= _word_count(recruiter) <= 130
    assert 120 <= _word_count(manager) <= 180
    assert "how teams adopt systems" in recruiter
    assert "managers and teams" in manager
    assert "People programs" in manager
    assert "transformation hypothesis" not in (recruiter + manager)


def test_disabled_evidence_and_age_signals_remain_excluded():
    _context, materials = _uta_materials()
    combined = "\n".join(materials.values())

    for term in DISABLED_EVIDENCE:
        assert term not in combined
    assert not positioning_violations(combined)


def test_people_operations_resume_preserves_ats_sections_and_truthful_positioning():
    parsed = parse_job_description(ROOT / UTA_JOB)
    match = score_job_match(UTA_JOB, ROOT)
    resume = _render_markdown(
        load_all_yaml(ROOT), parsed, match, "executive_operations"
    )

    assert "## Profile" in resume
    assert "## Core Competencies" in resume
    assert "## Professional Experience" in resume
    assert "| ---" not in resume
    assert OMG23_DISPLAY_NAME in resume
    assert "OMD Entertainment" not in resume
    assert "Team Enablement" in resume
    assert "Ownership & Responsibility Clarity" in resume
    assert "improving how cross-functional teams communicate" in resume
    assert "People Operations leader" not in resume


@pytest.mark.parametrize(
    ("job", "expected"),
    (
        ({"job_title": "Director, Business Operations", "job_description": "Own business operations, capacity planning, and operational reporting."}, "business_operations"),
        ({"job_title": "Strategy and Operations Lead", "job_description": "Lead strategic priorities, business planning, and executive decisions."}, "strategic_operations"),
        ({"job_title": "Product Operations Lead", "job_description": "Own product adoption, product feedback, roadmaps, and user needs."}, "product_operations"),
        ({"job_title": "Marketing Operations Director", "job_description": "Lead marketing operations, CRM, campaign execution, and marketing performance."}, "marketing_operations"),
        ({"job_title": "Portfolio Program Manager", "job_description": "Own portfolio management, milestones, dependencies, and program governance."}, "program_portfolio_management"),
        ({"job_title": "Operational Excellence Director", "job_description": "Lead continuous improvement, change adoption, and process improvement."}, "transformation_operational_excellence"),
        ({"job_title": "Chief of Staff", "job_description": "Support executive priorities, leadership decisions, and executive communication."}, "chief_of_staff_executive_operations"),
        ({"job_title": "Creative Operations Director", "job_description": "Lead creative teams, entertainment workflows, content production, and creative assets."}, "creative_entertainment_operations"),
    ),
)
def test_other_role_lenses_remain_functionally_relevant(job, expected):
    assert classify_role_lens(job)["primary"] == expected


def test_stale_context_safeguard_still_blocks_real_cross_role_contamination():
    with pytest.raises(PackageContextMismatchError):
        validate_material_context(
            "This Google opportunity centers on YouTube product activation and seller enablement.",
            {
                "company": "Netflix",
                "job_title": "Program Manager, Design",
                "raw_text": "Lead design programs and creative workflows.",
            },
        )


def test_role_lens_guard_catches_generic_people_operations_letter():
    lens = {"primary": "people_operations"}
    generic = (
        "I form a clear hypothesis, shape an operating model, and bring an advisory mindset "
        "to strategically sound measurable execution."
    )

    violations = role_lens_quality_violations(
        generic, lens, material_type="cover_letter"
    )

    assert {item["code"] for item in violations} >= {
        "generic_advisory_transformation_framing",
        "generic_people_operations_letter",
    }


def test_role_lens_guard_allows_one_controlled_rewrite():
    lens = {"primary": "people_operations"}
    original = "I shape an operating model and bring an advisory mindset."
    rewritten = (
        "I listen to how teams work, clarify ownership and communication, and help people "
        "adopt practical changes in their day-to-day work."
    )

    content, report = enforce_role_lens_quality(
        original,
        lens,
        material_type="cover_letter",
        rewrite=lambda _content: rewritten,
    )

    assert content == rewritten
    assert report["valid"] is True
    assert report["rewrite_attempted"] is True
    assert report["rewrite_succeeded"] is True
