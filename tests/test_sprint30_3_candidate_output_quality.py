from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml

from scripts.candidate_output import (
    ARCHETYPE_LABELS,
    CandidateOutputError,
    candidate_output_violations,
    domain_adjacency,
    evidence_recipe,
    humanize_identifier,
    validate_candidate_output,
)
from scripts.export_docx import export_ats_docx, export_styled_docx
from scripts.generate_cover_letter import _word_count, generate_cover_letter
from scripts.parse_job import parse_job_description
from scripts.role_intent import build_role_intent, load_role_intent_rules, tailoring_plan
from scripts.tailor_resume import tailor_resume


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path("tests/fixtures/jobs")
CX = FIXTURES / "gitlab_director_customer_experience_strategy.md"
AI = FIXTURES / "gitlab_ai_transformation_owner_marketing.md"
MULTI_BRAND = FIXTURES / "example_brand_group_marketing_operations_integration.md"
PMO = FIXTURES / "example_company_program_delivery.md"
GENERIC = FIXTURES / "example_company_senior_operations.md"
FOUNDATION_FILES = (
    "data/achievements.yml", "data/positions.yml", "data/skills.yml",
    "data/platforms.yml", "data/projects.yml", "data/evidence_projects.yml",
    "data/certifications.yml", "data/personal_brand.yml", "config/settings.yml",
    "config/target_companies.yml", "config/role_profiles.yml", "config/voice.yml",
    "config/company_voice_profiles.yml", "config/evidence_cards.yml",
    "config/writing_voice_profiles.yml", "config/role_editing_rules.yml",
)


def _isolated_root(tmp_path: Path, fixture: Path) -> tuple[Path, Path]:
    root = tmp_path / fixture.stem
    for relative in FOUNDATION_FILES:
        source = PROJECT_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    job = root / "jobs" / fixture.name
    job.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / fixture, job)
    return root, job.relative_to(root)


@pytest.mark.parametrize("archetype", sorted(ARCHETYPE_LABELS))
def test_all_archetypes_have_deterministic_evidence_recipes(archetype: str):
    first = evidence_recipe(archetype)
    assert first == evidence_recipe(archetype)
    assert len(first) == 6
    assert all("_" not in sentence for sentence in first)


@pytest.mark.parametrize(
    "identifier",
    (
        "business_operations_chief_of_staff", "career_catalyst", "workflow_governance",
        "compact_agency_only", "pmo_program_delivery", "ai_transformation",
        "campaignos_working_prototype", "executive_visibility",
    ),
)
def test_internal_identifiers_have_human_labels(identifier: str):
    label = humanize_identifier(identifier)
    assert label and "_" not in label


@pytest.mark.parametrize(
    "phrase",
    (
        "work motions", "role signals", "required outcomes", "primary hiring need",
        "lead evidence", "supporting evidence", "suppressed evidence", "matched signals",
        "detected role", "role intent", "archetype", "fixture",
        "fundamentally about this operating need", "focus on improve",
        "business_operations_chief_of_staff",
    ),
)
def test_candidate_validator_rejects_orchestration_language(phrase: str):
    assert candidate_output_violations(f"Candidate copy exposes {phrase}.")
    with pytest.raises(CandidateOutputError):
        validate_candidate_output(f"Candidate copy exposes {phrase}.")


def test_source_rules_load_without_runtime_config(tmp_path: Path):
    assert not (tmp_path / "config/role_intent_rules.yml").exists()
    assert "archetypes" in load_role_intent_rules(tmp_path)


def test_explicit_rules_remain_highest_precedence():
    configured = load_role_intent_rules(PROJECT_ROOT)
    configured = {**configured, "specialized_threshold": 999}
    intent = build_role_intent(
        {"job_title": "AI Transformation", "raw_text": "AI agents prompt engineering"},
        PROJECT_ROOT,
        rules=configured,
    )
    assert intent["primary_archetype"] == "general_operations"


def test_tailoring_plan_values_are_humanized():
    intent = build_role_intent(parse_job_description(PROJECT_ROOT / CX), PROJECT_ROOT)
    plan = tailoring_plan(intent)
    candidate_values = " ".join(
        [str(plan["detected_role"]), str(plan["earlier_career"])]
        + plan["leading_with"] + plan["supporting_with"] + plan["de_emphasizing"]
        + plan["selected_projects"] + plan["matched_signals"]
    )
    assert not re.search(r"[a-z]+_[a-z]+", candidate_values)


def test_customer_domain_adjacency_uses_job_content():
    parsed = parse_job_description(PROJECT_ROOT / CX)
    assert domain_adjacency(parsed) == {
        "customer_experience": True,
        "traditional_saas_customer_success": True,
    }


def test_business_operations_resume_quality(tmp_path: Path):
    root, job = _isolated_root(tmp_path, CX)
    parsed = parse_job_description(root / job)
    intent = build_role_intent(parsed, root)
    assert intent["primary_archetype"] == "business_operations_chief_of_staff"
    result = tailor_resume("executive_operations", job, root, role_intent=intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    profile = text.split("## Profile", 1)[1].split("## Core Competencies", 1)[0].strip()
    assert 55 <= len(profile.split()) <= 95
    assert profile.count(".") in {2, 3}
    for value in (
        "Business Operations", "Strategic Operations", "Executive Stakeholder Management",
        "Decision Support", "Client Advisory", "Airtable", "Microsoft Teams", "Microsoft 365",
        "Box", "Trello", "Operating Models", "Workflow Design", "Reporting Workflows",
        "Intermedia Advertising", "US International Media", "10 direct reports", "64-person organization",
    ):
        assert value in text
    for unsupported in (
        "Customer Success", "retention", "renewals", "Salesforce", "Gainsight", "SQL",
        "annual planning", "60+", "Additional Early Experience", "Education",
    ):
        assert unsupported.lower() not in text.lower()
    validate_candidate_output(text)


def test_customer_experience_cover_letter_is_grounded_and_natural(tmp_path: Path):
    root, job = _isolated_root(tmp_path, CX)
    intent = build_role_intent(parse_job_description(root / job), root)
    result = generate_cover_letter(job, root, role_intent=intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert text.startswith("Dear GitLab Hiring Team,")
    assert 250 <= _word_count(text) <= 325
    assert "background is rooted in enterprise marketing operations" in text
    assert "highly transferable to Customer Experience" in text
    assert "support the Customer Experience organization" in text
    assert "would not overstate" not in text
    assert "traditional SaaS Customer Success" not in text
    assert "10 direct reports" in text and "64-person organization" in text
    assert "Salesforce" not in text and "Gainsight" not in text and "60+" not in text
    validate_candidate_output(text)


@pytest.mark.parametrize(
    ("fixture", "expected"),
    (
        (AI, "ai_transformation"),
        (MULTI_BRAND, "marketing_operations_integration"),
        (PMO, "pmo_program_delivery"),
        (GENERIC, "general_operations"),
    ),
)
def test_existing_and_new_fixture_archetypes(fixture: Path, expected: str):
    assert build_role_intent(parse_job_description(PROJECT_ROOT / fixture), PROJECT_ROOT)["primary_archetype"] == expected


@pytest.mark.parametrize("fixture", (PMO, GENERIC))
def test_general_candidate_packages_contain_no_internal_language(tmp_path: Path, fixture: Path):
    root, job = _isolated_root(tmp_path, fixture)
    intent = build_role_intent(parse_job_description(root / job), root)
    resume = tailor_resume("executive_operations", job, root, role_intent=intent)
    letter = generate_cover_letter(job, root, role_intent=intent)
    resume_text = Path(resume["output_path"]).read_text(encoding="utf-8")
    letter_text = Path(letter["output_path"]).read_text(encoding="utf-8")
    assert 250 <= _word_count(letter_text) <= 325
    validate_candidate_output(resume_text)
    validate_candidate_output(letter_text)


@pytest.mark.parametrize("fixture", (CX, AI, MULTI_BRAND, PMO, GENERIC))
def test_visual_fixture_exports_create_three_candidate_documents(tmp_path: Path, fixture: Path):
    root, job = _isolated_root(tmp_path, fixture)
    intent = build_role_intent(parse_job_description(root / job), root)
    resume = tailor_resume("executive_operations", job, root, role_intent=intent)
    ats = export_ats_docx(resume["output_path"], root)
    styled = export_styled_docx(resume["output_path"], root)
    letter = generate_cover_letter(job, root, role_intent=intent)
    visual = tmp_path / "visual"
    visual.mkdir(parents=True, exist_ok=True)
    outputs = {
        "ats_resume.docx": Path(ats["output_path"]),
        "styled_resume.docx": Path(styled["output_path"]),
        "cover_letter.docx": Path(letter["docx_output_path"]),
    }
    for name, source in outputs.items():
        shutil.copy2(source, visual / name)
    assert len(list(visual.glob("*.docx"))) == 3
