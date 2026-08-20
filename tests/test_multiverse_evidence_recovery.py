from __future__ import annotations

from pathlib import Path

from scripts.evidence_engine import load_evidence_projects
from scripts.evidence_tailoring import recommend_evidence_ids


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MULTIVERSE_ID = "multiverse_editorial"


def test_multiverse_is_one_active_selectable_evidence_project():
    projects = load_evidence_projects(PROJECT_ROOT)
    matches = [project for project in projects if project["id"] == MULTIVERSE_ID]

    assert len(matches) == 1
    multiverse = matches[0]
    assert multiverse["status"] == "Active"
    assert multiverse["employer"] == "OMG23"
    assert "400" in multiverse["results"]
    assert "Internal Communications" in multiverse["skills"]


def test_multiverse_is_recommended_for_relevant_internal_editorial_role():
    projects = load_evidence_projects(PROJECT_ROOT)
    role = {
        "company": "Example Company",
        "job_title": "Director, Internal Communications and Editorial Operations",
        "raw_text": (
            "Lead company-wide internal communications, employee storytelling, editorial "
            "operations, content strategy, contributor coordination, culture, and employee "
            "engagement for a large organization."
        ),
    }

    recommended = recommend_evidence_ids(role, projects, limit=3)

    assert MULTIVERSE_ID in recommended


def test_multiverse_does_not_change_unrelated_evidence_recommendations():
    projects = load_evidence_projects(PROJECT_ROOT)
    without_multiverse = [
        project for project in projects if project["id"] != MULTIVERSE_ID
    ]
    unrelated_role = {
        "company": "Example Company",
        "job_title": "Technical Program Manager, Data Governance",
        "raw_text": (
            "Lead technical program governance, workflow quality assurance, data controls, "
            "technology implementation, reporting, and cross-functional delivery."
        ),
    }

    assert recommend_evidence_ids(
        unrelated_role, projects, limit=3
    ) == recommend_evidence_ids(unrelated_role, without_multiverse, limit=3)


def test_existing_evidence_ids_remain_unique_and_stable():
    projects = load_evidence_projects(PROJECT_ROOT)
    ids = [project["id"] for project in projects]

    assert len(ids) == len(set(ids))
    assert set(
        [
        "enterprise_media_operations_transformation",
        "enterprise_collaboration_platform_adoption_stakeholder_enablement",
        "operational_workflow_design_airtable_implementation",
        "enterprise_employee_engagement_community_fundraising_initiative",
        MULTIVERSE_ID,
        ]
    ).issubset(ids)
