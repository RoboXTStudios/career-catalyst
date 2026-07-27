from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from scripts.career_claims import (
    PublicCareerClaimError,
    public_claim_violations,
    validate_public_career_claims,
)
from scripts.export_docx import export_ats_docx, export_styled_docx
from scripts.generate_cover_letter import _word_count, generate_cover_letter
from scripts.materials_library import organize_package_outputs
from scripts.package_generator import build_package_context, preflight_package_generation
from scripts.parse_job import parse_job_description
from scripts.role_intent import (
    build_role_intent,
    role_intent_snapshot,
    tailoring_plan,
)
from scripts.resume_foundation import CandidateLanguageError, validate_candidate_language
from scripts.tailor_resume import tailor_resume


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path("tests/fixtures/jobs")
MULTI_BRAND = FIXTURE_ROOT / "example_brand_group_marketing_operations_integration.md"
AI_TRANSFORMATION = FIXTURE_ROOT / "gitlab_ai_transformation_owner_marketing.md"
GENERIC = FIXTURE_ROOT / "example_company_senior_operations.md"
FOUNDATION_FILES = (
    "data/achievements.yml",
    "data/positions.yml",
    "data/skills.yml",
    "data/platforms.yml",
    "data/projects.yml",
    "data/evidence_projects.yml",
    "data/certifications.yml",
    "data/personal_brand.yml",
    "config/settings.yml",
    "config/target_companies.yml",
    "config/role_profiles.yml",
    "config/voice.yml",
    "config/company_voice_profiles.yml",
    "config/evidence_cards.yml",
    "config/writing_voice_profiles.yml",
    "config/role_editing_rules.yml",
    "config/role_intent_rules.yml",
)


def _parsed(path: Path) -> dict:
    return parse_job_description(PROJECT_ROOT / path)


def _isolated_root(tmp_path: Path, fixture: Path) -> tuple[Path, Path]:
    root = tmp_path / "runtime"
    for relative in FOUNDATION_FILES:
        source = PROJECT_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    job = root / "jobs" / fixture.name
    job.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / fixture, job)
    parsed = parse_job_description(job)
    tracker_id = str(parsed.get("tracker_id") or fixture.stem)
    tracker = {
        "applications": [
            {
                "id": tracker_id,
                "stable_slug": tracker_id,
                "company": parsed.get("company"),
                "role": parsed.get("job_title"),
                "status": "Drafted",
                "job_file": str(job.relative_to(root)),
                "material_paths": {},
            }
        ]
    }
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8"
    )
    return root, job.relative_to(root)


@pytest.mark.parametrize(
    ("fixture", "expected"),
    (
        (MULTI_BRAND, "marketing_operations_integration"),
        (AI_TRANSFORMATION, "ai_transformation"),
        (GENERIC, "general_operations"),
    ),
)
def test_primary_fixture_archetypes(fixture: Path, expected: str):
    assert build_role_intent(_parsed(fixture), PROJECT_ROOT)["primary_archetype"] == expected


def test_action_outcome_signals_outweigh_generic_nouns():
    intent = build_role_intent(_parsed(MULTI_BRAND), PROJECT_ROOT)
    assert intent["scores"]["marketing_operations_integration"] > intent["scores"]["pmo_program_delivery"]
    assert intent["reasoning_signals"][0] not in {"operations", "marketing", "systems", "governance"}


def test_generic_fallback_is_conservative():
    intent = build_role_intent(_parsed(GENERIC), PROJECT_ROOT)
    assert intent["confidence"] in {"medium", "low"}
    assert intent["resume"]["selected_project_limit"] == 0
    assert intent["resume"]["earlier_career_policy"] == "omit"


@pytest.mark.parametrize(
    "field",
    (
        "primary_archetype",
        "secondary_archetypes",
        "confidence",
        "seniority",
        "business_environment",
        "primary_hiring_need",
        "required_outcomes",
        "work_motions",
        "reasoning_signals",
        "lead_evidence",
        "supporting_evidence",
        "suppressed_evidence",
        "resume",
        "cover_letter",
    ),
)
def test_role_intent_required_fields(field: str):
    assert field in build_role_intent(_parsed(MULTI_BRAND), PROJECT_ROOT)


def test_expected_multi_brand_outcomes_are_stable_ids():
    outcomes = set(build_role_intent(_parsed(MULTI_BRAND), PROJECT_ROOT)["required_outcomes"])
    assert {
        "standardize_workflows",
        "improve_intake_and_prioritization",
        "integrate_marketing_systems",
        "drive_platform_adoption",
        "improve_vendor_efficiency",
        "increase_portfolio_visibility",
    } <= outcomes


@pytest.mark.parametrize(
    ("company", "expected"),
    (
        ("Example Brand Group", "Dear Example Brand Group Hiring Team,"),
        ("Gitlab", "Dear GitLab Hiring Team,"),
        ("", "Dear Hiring Team,"),
        (None, "Dear Hiring Team,"),
    ),
)
def test_dynamic_company_greeting(company, expected):
    intent = build_role_intent({"company": company, "job_title": "Senior Operations"}, PROJECT_ROOT)
    assert intent["cover_letter"]["greeting"] == expected


def test_package_context_computes_role_intent_once(tmp_path: Path):
    root, job = _isolated_root(tmp_path, MULTI_BRAND)
    tracker = yaml.safe_load((root / "data/application_tracker.yml").read_text())
    with patch("scripts.package_generator.build_role_intent", wraps=build_role_intent) as builder:
        context = build_package_context(tracker["applications"][0]["id"], tracker, root)
    assert builder.call_count == 1
    assert context["role_intent"]["primary_archetype"] == "marketing_operations_integration"
    assert context["job_reference"] == str(job)


def test_tailoring_plan_is_a_view_of_same_decision():
    intent = build_role_intent(_parsed(MULTI_BRAND), PROJECT_ROOT)
    plan = tailoring_plan(intent)
    assert plan["primary_hiring_need"] == intent["primary_hiring_need"]
    assert len(plan["leading_with"]) == len(intent["lead_evidence"])
    assert len(plan["matched_signals"]) == len(intent["reasoning_signals"])
    assert all("_" not in value for value in plan["leading_with"] + plan["matched_signals"])


def test_multi_brand_resume_selection(tmp_path: Path):
    root, job = _isolated_root(tmp_path, MULTI_BRAND)
    intent = build_role_intent(parse_job_description(root / job), root)
    result = tailor_resume("executive_operations", job, root, role_intent=intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert result["role_intent"] is intent
    assert intent["resume"]["headline_profile"] in text
    assert all(value in text for value in ("Airtable", "Box", "Trello", "Vendor Integration", "Training", "Adoption"))
    assert all(value not in text for value in ("CampaignOS", "Career Catalyst", "RoboXT Studios", "Multiverse", "Additional Early Experience"))
    assert "Intermedia Advertising" in text and "US International Media" in text
    experience = text.split("## Professional Experience", 1)[1].split("## Earlier Career", 1)[0]
    assert experience.count("\n- ") <= 6
    assert not public_claim_violations(text)


def test_multi_brand_cover_letter_selection_and_length(tmp_path: Path):
    root, job = _isolated_root(tmp_path, MULTI_BRAND)
    intent = build_role_intent(parse_job_description(root / job), root)
    result = generate_cover_letter(job, root, role_intent=intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert result["role_intent"] is intent
    assert text.startswith("Dear Example Brand Group Hiring Team,")
    assert "Airtable implementation" in text
    assert "CampaignOS" not in text and "Career Catalyst" not in text
    assert 250 <= _word_count(text) <= 325
    assert "caught my attention" not in text.lower()
    assert "10 direct reports" in text and "64-person organization" in text


def test_ai_transformation_resume_selection(tmp_path: Path):
    root, job = _isolated_root(tmp_path, AI_TRANSFORMATION)
    intent = build_role_intent(parse_job_description(root / job), root)
    result = tailor_resume("executive_operations", job, root, role_intent=intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert all(value in text for value in ("Career Catalyst", "actively operates", "evidence management", "Airtable", "Microsoft Teams", "champion network", "Disney+", "CampaignOS", "working prototype"))
    assert all(value not in text for value in ("Additional Early Experience", "Evidence management", "60+"))
    assert "focused on designed" not in text.lower()
    assert not public_claim_violations(text)


def test_ai_transformation_cover_letter_selection_and_length(tmp_path: Path):
    root, job = _isolated_root(tmp_path, AI_TRANSFORMATION)
    intent = build_role_intent(parse_job_description(root / job), root)
    result = generate_cover_letter(job, root, role_intent=intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert text.startswith("Dear GitLab Hiring Team,")
    assert text.index("Career Catalyst") < text.index("Airtable")
    assert all(value in text for value in ("Microsoft Teams", "champion network", "Disney+", "working prototype"))
    assert "60+" not in text and not public_claim_violations(text)
    assert 250 <= _word_count(text) <= 325


def test_generic_resume_uses_no_filler_project(tmp_path: Path):
    root, job = _isolated_root(tmp_path, GENERIC)
    intent = build_role_intent(parse_job_description(root / job), root)
    result = tailor_resume("executive_operations", job, root, role_intent=intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert intent["resume"]["headline_profile"] in text
    assert "Relevant Projects & Impact" not in text
    assert "Additional Early Experience" not in text
    assert "OMG23 (Omnicom Media Group)" in text


def test_generic_cover_letter_needs_no_banned_filler(tmp_path: Path):
    root, job = _isolated_root(tmp_path, GENERIC)
    intent = build_role_intent(parse_job_description(root / job), root)
    result = generate_cover_letter(job, root, role_intent=intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert 250 <= _word_count(text) <= 325
    assert result["repair_attempts"] == 0
    assert "I care about the work itself" not in text
    assert "I would welcome the chance to learn more" not in text


@pytest.mark.parametrize("fixture", (MULTI_BRAND, AI_TRANSFORMATION))
def test_ats_and_styled_exports_share_tailored_source(tmp_path: Path, fixture: Path):
    root, job = _isolated_root(tmp_path, fixture)
    intent = build_role_intent(parse_job_description(root / job), root)
    resume = tailor_resume("executive_operations", job, root, role_intent=intent)
    ats = export_ats_docx(resume["output_path"], root)
    styled = export_styled_docx(resume["output_path"], root)
    assert Path(ats["output_path"]).is_file()
    assert Path(styled["output_path"]).is_file()
    assert intent["resume"]["target_max_pages"] == 2


def test_manifest_stores_compact_role_intent_snapshot(tmp_path: Path):
    intent = build_role_intent(_parsed(MULTI_BRAND), PROJECT_ROOT)
    source = tmp_path / "draft.txt"
    source.write_text("draft", encoding="utf-8")
    app = {"id": "example", "company": "Example Brand Group", "role": "Director", "status": "Drafted"}
    result = organize_package_outputs(
        tmp_path,
        app,
        {"cover_letter": str(source)},
        export_root=tmp_path / "canonical",
        role_intent=role_intent_snapshot(intent),
    )
    payload = json.loads(Path(result["manifest"]["manifest_path"]).read_text())
    assert payload["role_intent"] == role_intent_snapshot(intent)


def test_repeated_material_install_is_idempotent(tmp_path: Path):
    intent = role_intent_snapshot(build_role_intent(_parsed(GENERIC), PROJECT_ROOT))
    app = {"id": "generic", "company": "Example Company", "role": "Senior Operations", "status": "Drafted"}
    paths = []
    for index in range(2):
        source = tmp_path / f"draft-{index}.txt"
        source.write_text("identical content", encoding="utf-8")
        result = organize_package_outputs(
            tmp_path,
            app,
            {"cover_letter": str(source)},
            export_root=tmp_path / "canonical",
            role_intent=intent,
        )
        paths.append(result["outputs"]["cover_letter"])
    assert paths[0] == paths[1]
    assert not list((tmp_path / "canonical").rglob("*_2.*"))


def test_role_intent_source_contains_no_employer_conditions():
    source = (PROJECT_ROOT / "scripts/role_intent.py").read_text(encoding="utf-8")
    for employer in ("GitLab", "FAT Brands", "Paramount", "Example Brand Group"):
        assert employer not in source


def test_immutable_leadership_facts_are_unchanged():
    positions = yaml.safe_load((PROJECT_ROOT / "data/positions.yml").read_text())
    text = json.dumps(positions)
    assert "OMG23 (Omnicom Media Group)" in text
    assert "10 direct reports" in text
    assert "64-person organization" in text
    assert "60+" not in text


def test_project_suppression_survives_keyword_overlap(tmp_path: Path):
    root, job = _isolated_root(tmp_path, MULTI_BRAND)
    job_path = root / job
    job_path.write_text(
        job_path.read_text(encoding="utf-8")
        + "\nAI automation prototyping is an adjacent capability, not the primary need.\n",
        encoding="utf-8",
    )
    intent = build_role_intent(parse_job_description(job_path), root)
    assert intent["primary_archetype"] == "marketing_operations_integration"
    result = tailor_resume("executive_operations", job, root, role_intent=intent)
    text = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "CampaignOS" not in text and "Career Catalyst" not in text


def test_another_prospect_material_remains_protected(tmp_path: Path):
    conflict = tmp_path / "other_resume.docx"
    conflict.write_bytes(b"other prospect")
    records = [
        {
            "id": "selected",
            "company": "Example Company",
            "role": "Senior Operations",
            "status": "Drafted",
            "material_paths": {"ATS Resume": str(conflict)},
        },
        {
            "id": "owner",
            "company": "Other Company",
            "role": "Other Role",
            "status": "Drafted",
            "material_paths": {"ATS Resume": str(conflict)},
        },
    ]
    result = preflight_package_generation(
        "selected", records, tmp_path, export_root=tmp_path / "exports"
    )
    assert result["status"] == "conflict"
    assert any(item.get("conflicting_prospect_id") == "owner" for item in result["conflicts"])
    assert conflict.read_bytes() == b"other prospect"


def test_public_language_validator_remains_active():
    with pytest.raises(PublicCareerClaimError):
        validate_public_career_claims("Led operations at OMG23 / OMD Entertainment.")


@pytest.mark.parametrize("claim", ("National Geographic", "Bachelor's degree"))
def test_unsupported_brand_and_education_safeguards_remain_active(claim: str):
    with pytest.raises(CandidateLanguageError):
        validate_candidate_language(f"Candidate claims {claim}.")
