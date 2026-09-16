from pathlib import Path

import pytest
import yaml

from scripts.application_tracker import load_application_tracker, update_prospect
from scripts.evidence_engine import (
    EvidenceEngineError,
    archive_evidence_project,
    filter_evidence_projects,
    load_evidence_projects,
    save_evidence_projects,
    upsert_evidence_project,
)


def write_tracker(root: Path) -> None:
    data = {
        "applications": [
            {
                "id": "sample_role",
                "company": "Example Co",
                "role": "Operations Lead",
                "status": "Drafted",
                "priority": "Medium",
                "show_on_dashboard": True,
            }
        ]
    }
    (root / "data").mkdir()
    (root / "data" / "application_tracker.yml").write_text(yaml.safe_dump(data), encoding="utf-8")


def valid_project(**updates):
    project = {
        "title": "Airtable Implementation",
        "employer": "OMG23",
        "problem": "Campaign status lived in disconnected files.",
        "actions": "Designed workflows and trained users.",
        "results": "Created a shared source of truth.",
        "skills": ["Workflow Design"],
        "technologies": ["Airtable"],
        "tags": ["Process Improvement"],
        "status": "Active",
    }
    project.update(updates)
    return project


def test_create_edit_and_persist_evidence_project(tmp_path):
    created = upsert_evidence_project(valid_project(), tmp_path)
    assert created["id"] == "airtable_implementation"

    edited = upsert_evidence_project(
        valid_project(id=created["id"], results="Reduced duplicate status chasing."),
        tmp_path,
    )

    reloaded = load_evidence_projects(tmp_path)
    assert len(reloaded) == 1
    assert edited["results"] == "Reduced duplicate status chasing."
    assert reloaded[0]["results"] == "Reduced duplicate status chasing."


def test_required_field_validation(tmp_path):
    with pytest.raises(EvidenceEngineError):
        upsert_evidence_project(valid_project(problem=""), tmp_path)


def test_archive_without_deleting_evidence_project(tmp_path):
    project = upsert_evidence_project(valid_project(), tmp_path)
    archive_evidence_project(project["id"], tmp_path)

    projects = load_evidence_projects(tmp_path)
    assert len(projects) == 1
    assert projects[0]["status"] == "Archived"


def test_filter_searches_title_employer_skill_technology_tag_and_status(tmp_path):
    save_evidence_projects(
        [
            valid_project(),
            valid_project(
                title="Teams Rollout",
                problem="Stakeholders needed support.",
                actions="Held office hours.",
                results="Improved readiness.",
                technologies=["Microsoft Teams"],
                tags=["Change Management"],
                status="Draft",
            ),
        ],
        tmp_path,
    )
    projects = load_evidence_projects(tmp_path)

    assert [p["title"] for p in filter_evidence_projects(projects, query="Airtable")] == ["Airtable Implementation"]
    assert [p["title"] for p in filter_evidence_projects(projects, query="Change Management")] == ["Teams Rollout"]
    assert [p["title"] for p in filter_evidence_projects(projects, status="Draft")] == ["Teams Rollout"]


def test_manual_role_association_preserves_evidence_project(tmp_path):
    write_tracker(tmp_path)
    project = upsert_evidence_project(valid_project(), tmp_path)

    updated = update_prospect("sample_role", {"evidence_project_ids": [project["id"]]}, tmp_path)
    assert updated["evidence_project_ids"] == [project["id"]]

    update_prospect("sample_role", {"evidence_project_ids": []}, tmp_path)
    assert load_application_tracker(tmp_path)[0]["evidence_project_ids"] == []
    assert load_evidence_projects(tmp_path)[0]["title"] == "Airtable Implementation"
