"""Isolated STARZ regressions for Evidence provenance and escaped job text."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from tests.fixture_support import replace_evidence_projects
from docx import Document

from scripts.candidate_output import candidate_cover_letter
from scripts.generate_cover_letter import load_generation_context
from scripts.package_generator import generate_package
from scripts.parse_job import parse_job_description


ROOT = Path(__file__).resolve().parents[1]

SELECTED = [
    {
        "id": "enterprise_media_operations_transformation",
        "title": "Enterprise Media Operations Transformation",
        "problem": "Cross-functional media operations required clearer governance and delivery.",
        "actions": "Led cross-functional operations, workflow design, and stakeholder alignment.",
        "results": "Improved visibility, execution quality, and reliable delivery.",
        "status": "Active",
    },
    {
        "id": "operational_workflow_design_airtable_implementation",
        "title": "Operational Workflow Design & Airtable Implementation",
        "problem": "Campaign teams needed a dependable shared operating view.",
        "actions": "Coordinated Airtable workflow design, documentation, permissions, and adoption.",
        "results": "Improved status visibility and delivery consistency.",
        "status": "Active",
    },
    {
        "id": "disney_plus_launch_readiness",
        "title": "Disney+ Launch Readiness - Tracking, Measurement and Operational Governance",
        "problem": "A launch required coordinated governance and measurement readiness.",
        "actions": "Coordinated governance, QA, and cross-functional execution.",
        "results": "Improved launch readiness and measurement coordination.",
        "status": "Active",
    },
    {
        "id": "enterprise_collaboration_platform_adoption_stakeholder_enablement",
        "title": "Enterprise Collaboration Platform Adoption & Stakeholder Enablement",
        "problem": "Teams needed consistent collaboration practices and enablement.",
        "actions": "Supported platform adoption through guidance, office hours, and peer enablement.",
        "results": "Improved collaboration visibility and stakeholder confidence.",
        "status": "Active",
    },
]

CAREER_CATALYST = {
    "id": "career_catalyst",
    "title": "Career Catalyst",
    "problem": "Job-search work required role-aware product workflows and quality controls.",
    "actions": "Created and led development of an active AI-enabled career intelligence product.",
    "results": "Built and iterated tested local workflows, acceptance criteria, and release guardrails.",
    "status": "Active",
}


def _isolated_starz_runtime(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "starz_runtime"
    for name in ("data", "config", "templates"):
        shutil.copytree(ROOT / name, root / name)
    (root / "jobs").mkdir()
    job_file = root / "jobs" / "starz_vp_campaign_management.md"
    job_file.write_text(
        """# VP, Campaign Management &amp; Marketing Infrastructure
Company: STARZ Entertainment
Location: Los Angeles, CA
Work arrangement: Hybrid
URL: https://example.com/starz
Salary range: $180,000-$220,000

## Job Description
Lead campaign management and marketing infrastructure across planning, workflows,
cross-functional teams, reporting, technology, governance, and operations.

## Qualifications
Experience with marketing operations, campaign governance, executive communication,
workflow design, and cross-functional delivery.
""",
        encoding="utf-8",
    )
    replace_evidence_projects(
        root / "data" / "evidence_projects.yml", [*SELECTED, CAREER_CATALYST]
    )
    tracker = {
        "applications": [
            {
                "id": "starz_vp_campaign_management",
                "stable_slug": "starz_vp_campaign_management",
                "company": "STARZ Entertainment",
                "role": "VP, Campaign Management &amp; Marketing Infrastructure",
                "status": "Prospect",
                "job_file": "jobs/starz_vp_campaign_management.md",
                "priority": "High",
                "show_on_dashboard": True,
                "evidence_project_ids": [item["id"] for item in SELECTED],
                "material_paths": {},
            }
        ]
    }
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8"
    )
    return root, "jobs/starz_vp_campaign_management.md"


def test_starz_strategy_cover_letter_excludes_unselected_career_catalyst(tmp_path: Path):
    root, job_path = _isolated_starz_runtime(tmp_path)
    context = load_generation_context(
        job_path,
        root,
        associated_evidence_projects=[*SELECTED],
        role_intent={
            "package_role_family": "strategy_gtm_operations",
            "primary_archetype": "general_operations",
            "cover_letter": {"greeting": "Dear Hiring Team,"},
        },
    )
    content = candidate_cover_letter(context)
    assert "Career Catalyst" not in content
    assert "&amp;" not in content
    assert "&" in content
    assert "\n\n" in content


def test_starz_package_has_no_unselected_project_leak_and_decodes_entities(tmp_path: Path):
    root, _job_path = _isolated_starz_runtime(tmp_path)
    result = generate_package(
        "starz_vp_campaign_management",
        root,
        export_root=tmp_path / "exports",
    )
    assert result["package_complete"] is True
    files = result["manifest"]["files"]
    candidate_outputs = [
        Path(files[key]).read_text(encoding="utf-8")
        for key in ("resume_text", "cover_letter", "application_note")
    ]
    candidate_outputs.extend(
        "\n".join(paragraph.text for paragraph in Document(files[key]).paragraphs)
        for key in ("ats_docx", "styled_docx")
    )
    combined = "\n".join(candidate_outputs)
    assert "career catalyst" not in combined.lower()
    assert "&amp;" not in combined
    assert "&" in combined
    summary = Path(files["package_summary"]).read_text(encoding="utf-8")
    assert "Selected: 4" in summary
    assert "### Unselected Fallback Evidence\n\n- None" in summary
    for project in SELECTED:
        assert project["title"] in summary


def test_allowed_fallback_is_explicitly_available_to_candidate_guard():
    from scripts.evidence_tailoring import candidate_project_reference_violations

    fallback = {**CAREER_CATALYST, "fallback": True}
    context = {
        "career_data": {"data": {"evidence_projects": {"evidence_projects": [CAREER_CATALYST]}}},
        "associated_evidence_projects": [*SELECTED],
        "evidence_scope_enforced": True,
        "cover_letter_evidence_selection": {"used_projects": [], "fallback_used": [{"_project": fallback}]},
    }
    assert candidate_project_reference_violations(
        "Career Catalyst is an explicitly permitted fallback.", context, "cover_letter"
    ) == []
