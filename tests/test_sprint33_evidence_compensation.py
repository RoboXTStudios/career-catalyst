from __future__ import annotations

import json
import shutil
from pathlib import Path

import app
from scripts.evidence_tailoring import (
    cover_letter_project_paragraph,
    output_use_metadata,
    public_artifact_selection,
    select_evidence_for_artifact,
)
from scripts.generate_cover_letter import (
    _ground_cover_letter_in_selected_evidence,
    generate_cover_letter,
)
from scripts.job_importer import _import_compensation, _structured_job_fields, create_job_markdown
from scripts.opportunity_scoring import score_opportunity
from scripts.package_quality import save_package_summary
from scripts.parse_job import extract_metadata, normalize_compensation, parse_job_description
from scripts.score_match import score_job_data
from scripts.tailor_resume import tailor_resume
from tests.test_sprint31_1_evidence_tailoring_integration import FOUNDATION_FILES, PROJECT_ROOT


DIGITAL_WORKPLACE_POSTING = {
    "company": "Example Company",
    "job_title": "Director, Digital Workplace",
    "raw_text": (
        "Lead digital workplace strategy, SharePoint information architecture, Microsoft Teams "
        "adoption, content governance, employee communications, stakeholder training, and "
        "cross-functional change management."
    ),
    "job_description": (
        "Lead digital workplace strategy, SharePoint information architecture, Microsoft Teams "
        "adoption, content governance, employee communications, stakeholder training, and "
        "cross-functional change management."
    ),
    "responsibilities": [
        "Lead SharePoint governance and Microsoft Teams adoption.",
        "Improve employee communications and digital workplace workflows.",
    ],
    "qualifications": ["Experience with stakeholder training and change management."],
}

SELECTED_EVIDENCE = [
    {
        "id": "floodlight_content_governance",
        "title": "Floodlight Content Governance",
        "problem": "A distributed team needed consistent content governance and clearer employee communications workflows across a growing digital workplace.",
        "actions": "Led digital workplace content governance and employee communications workflows.",
        "results": "Improved cross-functional publishing clarity and stakeholder adoption.",
        "skills": ["Content Governance", "Employee Communications"],
    },
    {
        "id": "sharepoint_information_architecture",
        "title": "SharePoint Information Architecture",
        "problem": "Distributed teams lacked a governed, consistently structured source for shared content, creating duplicate and outdated files.",
        "actions": "Designed SharePoint information architecture, permissions, and content standards.",
        "results": "Created a clearer governed source for distributed teams.",
        "technologies": ["SharePoint"],
    },
    {
        "id": "teams_adoption_enablement",
        "title": "Microsoft Teams Adoption Enablement",
        "problem": "Cross-functional teams were slow to adopt Microsoft Teams, limiting collaboration and stakeholder training.",
        "actions": "Led Microsoft Teams adoption, stakeholder training, and peer enablement.",
        "results": "Improved collaboration practices across cross-functional teams.",
        "technologies": ["Microsoft Teams"],
    },
    {
        "id": "ai_product_experiment",
        "title": "AI Product Experiment",
        "problem": "A separate use case needed a verified, testable AI product prototype before further investment.",
        "actions": "Defined AI product requirements and iterative quality tests.",
        "results": "Produced a verified prototype for a separate use case.",
        "skills": ["AI Product Development"],
    },
]

GENERIC_UNSELECTED = {
    "id": "generic_airtable_workflow",
    "title": "Generic Airtable Workflow",
    "problem": "Routine status tracking was scattered across spreadsheets with no shared workflow.",
    "actions": "Built a generic Airtable workflow and status dashboard.",
    "results": "Improved routine tracking.",
    "technologies": ["Airtable"],
}


def _selection(artifact_type: str, capacity: int) -> dict:
    return select_evidence_for_artifact(
        DIGITAL_WORKPLACE_POSTING,
        SELECTED_EVIDENCE,
        artifact_type=artifact_type,
        capacity=capacity,
        fallback_projects=[GENERIC_UNSELECTED],
        minimum_selected=min(2, capacity),
    )


def test_selected_evidence_is_ranked_before_unselected_fallback_and_accounted():
    resume = _selection("ats_resume", 3)
    assert {item["id"] for item in resume["used"]} == {
        "floodlight_content_governance",
        "sharepoint_information_architecture",
        "teams_adoption_enablement",
    }
    assert resume["fallback_used"] == []
    assert [item["id"] for item in resume["omitted"]] == ["ai_product_experiment"]
    assert resume["omitted"][0]["reason"]


def test_cover_letter_uses_strongest_selected_evidence_without_generic_substitution():
    cover = _selection("cover_letter", 2)
    context = {
        "parsed_job": DIGITAL_WORKPLACE_POSTING,
        "cover_letter_evidence_selection": cover,
    }
    base = (
        "Dear Hiring Team,\n\n"
        "I am interested in the Director, Digital Workplace role because it connects strategy and adoption.\n\n"
        "I have led complex cross-functional operations and practical change programs.\n\n"
        "I also built a generic Airtable workflow for routine status tracking.\n\n"
        "I would welcome the opportunity to discuss the role.\n\n"
        "Best,\n\nTrisha Lynch"
    )
    grounded = _ground_cover_letter_in_selected_evidence(base, context)
    # Cover letters describe projects in natural first-person prose without
    # naming their titles (the résumé carries the titles), so verify the
    # strongest selected evidence actually shows up by checking its real
    # generated paragraph text rather than a literal title string.
    used_ids = {project["id"] for project in cover["used_projects"]}
    assert used_ids == {"floodlight_content_governance", "teams_adoption_enablement"}
    for project in cover["used_projects"]:
        paragraph = cover_letter_project_paragraph(project, DIGITAL_WORKPLACE_POSTING)
        assert paragraph
        assert paragraph in grounded
    assert "Generic Airtable Workflow" not in grounded
    assert "generic airtable workflow" not in grounded.lower()
    assert "unsupported" not in grounded.lower()


def test_package_metadata_accounts_for_every_selected_record_and_round_trips(tmp_path: Path):
    ats = _selection("ats_resume", 3)
    styled = _selection("styled_resume", 3)
    cover = _selection("cover_letter", 2)
    metadata = output_use_metadata(
        SELECTED_EVIDENCE,
        parsed_job=DIGITAL_WORKPLACE_POSTING,
        artifact_selections={
            "ats_resume": ats,
            "styled_resume": styled,
            "cover_letter": cover,
        },
    )
    assert metadata["selected_count"] == 4
    assert metadata["used_anywhere_count"] == 3
    assert metadata["omitted_from_package_count"] == 1
    assert metadata["unselected_fallback_used"] == []
    persisted = json.loads(json.dumps(metadata))
    assert persisted == metadata

    summary = save_package_summary(
        tmp_path,
        {"company": "Example Company", "job_title": "Director, Digital Workplace"},
        {"label": "Fresh", "posting_status": "Active", "posting_date": "2026-08-01"},
        {
            "overall_score": 80,
            "apply_recommendation": "Apply Immediately",
            "dimensions": {"Resume Fit": 85, "Salary Fit": None},
        },
        {
            "resume_tailoring_score": 85,
            "cover_letter_score": 84,
            "ats_keyword_match": 86,
            "voice_match": 82,
            "confidence_level": "High",
        },
        tailoring_metadata=metadata,
    )
    content = Path(summary["output_path"]).read_text(encoding="utf-8")
    for project in SELECTED_EVIDENCE:
        assert project["title"] in content
    assert "ATS résumé: Used" in content
    assert "Not scored (neutral)" in content


def test_real_resume_and_cover_generators_share_selected_evidence_service(tmp_path: Path):
    root = tmp_path / "runtime"
    for relative in FOUNDATION_FILES:
        source = PROJECT_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    job = root / "jobs" / "digital_workplace.md"
    job.parent.mkdir(parents=True, exist_ok=True)
    job.write_text(
        "# Director, Digital Workplace\n\n"
        "Company: Example Company\n\n"
        "Compensation status: not_listed\n\n"
        "## Job Description\n\n"
        + DIGITAL_WORKPLACE_POSTING["job_description"],
        encoding="utf-8",
    )
    relative_job = job.relative_to(root)
    resume = tailor_resume(
        "executive_operations", relative_job, root, SELECTED_EVIDENCE
    )
    cover = generate_cover_letter(relative_job, root, SELECTED_EVIDENCE)
    resume_text = Path(resume["output_path"]).read_text(encoding="utf-8")
    cover_text = Path(cover["output_path"]).read_text(encoding="utf-8")
    assert set(resume["resume_projects_used"]) == {
        project["title"] for project in SELECTED_EVIDENCE[:3]
    }
    assert len(cover["cover_letter_projects_used"]) == 2
    for title in resume["resume_projects_used"]:
        assert title in resume_text
    # Cover letters describe projects in prose without naming their titles
    # (the résumé carries the titles), so verify each used project actually
    # shows up by checking its distinguishing problem statement instead.
    projects_by_title = {project["title"]: project for project in SELECTED_EVIDENCE}
    for title in cover["cover_letter_projects_used"]:
        assert projects_by_title[title]["problem"] in cover_text
    assert "CampaignOS" not in resume_text
    assert "Generic Airtable Workflow" not in cover_text
    assert cover["evidence_selection"]["omitted"]


def test_public_artifact_selection_never_persists_full_project_payload():
    public = public_artifact_selection(_selection("ats_resume", 3))
    assert "_project" not in json.dumps(public)


def test_compensation_states_distinguish_range_absence_and_parser_uncertainty(tmp_path: Path):
    provided = normalize_compensation("The salary range is $150,000 to $190,000 per year")
    not_listed = _structured_job_fields(
        {
            "title": "Director, Digital Workplace",
            "hiringOrganization": {"name": "Example Company"},
            "description": DIGITAL_WORKPLACE_POSTING["job_description"],
        },
        "https://example.com/jobs/123",
    )["compensation"]
    unknown = _import_compensation(extract_metadata("Import failed"), "Import failed")
    assert provided["disclosure_state"] == "provided"
    assert not_listed["disclosure_state"] == "not_listed"
    assert not_listed["minimum"] is None and not_listed["maximum"] is None
    assert unknown["disclosure_state"] == "unknown_unverified"
    assert normalize_compensation("", disclosure_state="provided")["disclosure_state"] == "unknown_unverified"

    markdown = create_job_markdown(
        {
            "job_title": "Director, Digital Workplace",
            "company": "Example Company",
            "job_description": DIGITAL_WORKPLACE_POSTING["job_description"],
            "compensation": not_listed,
            "compensation_disclosure_state": "not_listed",
        }
    )
    job = tmp_path / "role.md"
    job.write_text(markdown, encoding="utf-8")
    parsed = parse_job_description(job)
    assert parsed["compensation_disclosure_state"] == "not_listed"


def test_missing_compensation_is_neutral_and_generation_action_remains_available(tmp_path: Path):
    base = {
        "company": "Example Company",
        "job_title": "Director, Digital Workplace",
        "job_description": DIGITAL_WORKPLACE_POSTING["job_description"],
        "location": "Remote",
        "work_arrangement": "Remote",
    }
    not_listed = normalize_compensation("", disclosure_state="not_listed")
    unknown = normalize_compensation("", disclosure_state="unknown_unverified")
    report_not_listed = score_job_data({**base, "compensation": not_listed}, tmp_path)
    report_unknown = score_job_data({**base, "compensation": unknown}, tmp_path)
    assert report_not_listed["match_score"] == report_unknown["match_score"]
    assert report_not_listed["compensation_disclosure_state"] == "not_listed"
    assert report_unknown["compensation_disclosure_state"] == "unknown_unverified"
    assert report_not_listed["match_score"] is not None
    assert not any("mismatch" in gap.lower() for gap in report_not_listed["match_gaps"])
    assert "verify" in report_not_listed["salary_verification_action"].lower()

    opportunity_not_listed = score_opportunity(
        {**base, "compensation": not_listed},
        match_report={"match_score": 75},
    )
    opportunity_unknown = score_opportunity(
        {**base, "compensation": unknown},
        match_report={"match_score": 75},
    )
    assert opportunity_not_listed["overall_score"] == opportunity_unknown["overall_score"]
    assert opportunity_not_listed["dimensions"]["Salary Fit"] is None
    assert opportunity_not_listed["salary_verification_action"]


def test_entering_compensation_later_updates_state_and_preserves_explicit_missing_state():
    missing = app.compensation_record_updates("not_listed", "")
    assert missing["compensation_disclosure_state"] == "not_listed"
    assert missing["compensation_minimum"] is None
    assert missing["salary_range"] == "Compensation not listed — verify before recruiter screen."

    provided = app.compensation_record_updates("unknown_unverified", "$155,000–$185,000")
    assert provided["compensation_disclosure_state"] == "provided"
    assert provided["compensation_minimum"] == 155000
    assert provided["compensation_maximum"] == 185000

    intake_state = {
        "prospect_salary": "$155,000–$185,000",
        "prospect_salary_auto_value": "",
        "prospect_compensation_state": "unknown_unverified",
    }
    app.mark_compensation_manual_override(intake_state)
    assert intake_state["prospect_compensation_state"] == "provided"


def test_evidence_change_invalidates_all_artifact_preview_state():
    state = {
        "package_preview_prospect_id": "role-1",
        "package_preview_selection_fingerprint": "stale",
        "ats_resume_preview": "old",
        "styled_resume_preview": "old",
        "cover_letter_preview": "old",
        "package_summary_preview": "old",
        "package_evidence_usage": {"old": True},
    }
    assert app.reset_package_preview_for_selection(state, "role-1", ["evidence-1"])
    for key in (
        "ats_resume_preview",
        "styled_resume_preview",
        "cover_letter_preview",
        "package_summary_preview",
        "package_evidence_usage",
    ):
        assert key not in state
