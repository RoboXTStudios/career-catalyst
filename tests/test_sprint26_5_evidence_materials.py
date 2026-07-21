from pathlib import Path

import yaml

from scripts.application_tracker import update_prospect
from scripts.evidence_engine import (
    SPRINT_26_5_SEEDED_PROJECTS,
    enrich_seed_evidence_projects,
    evidence_generation_context,
    evidence_projects_for_role,
    load_evidence_projects,
    save_evidence_projects,
)
from scripts.generate_cover_letter import load_generation_context
from scripts.tailor_resume import _render_markdown


def _write_tracker(root: Path) -> None:
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump(
            {
                "applications": [
                    {"id": "role_a", "company": "A", "role": "Ops", "status": "Drafted", "priority": "Medium", "show_on_dashboard": True},
                    {"id": "role_b", "company": "B", "role": "Ops", "status": "Drafted", "priority": "Medium", "show_on_dashboard": True},
                ]
            }
        ),
        encoding="utf-8",
    )


def test_sprint_26_5_seed_projects_are_complete_and_idempotent(tmp_path):
    projects = enrich_seed_evidence_projects(tmp_path)
    by_id = {project["id"]: project for project in projects}

    assert set(by_id) == {seed["id"] for seed in SPRINT_26_5_SEEDED_PROJECTS}
    for seed in SPRINT_26_5_SEEDED_PROJECTS:
        project = by_id[seed["id"]]
        assert project["problem"] == seed["problem"]
        assert project["actions"] == seed["actions"]
        assert project["results"] == seed["results"]

    fundraising = by_id["enterprise_employee_engagement_community_fundraising_initiative"]
    assert "more than $35,000" in fundraising["actions"]
    assert "100% employee participation" in fundraising["results"]
    airtable = by_id["operational_workflow_design_airtable_implementation"]
    assert airtable["technologies"] == ["Airtable", "Google Sheets", "Google Docs"]
    assert "linked databases" in airtable["actions"]

    rerun = enrich_seed_evidence_projects(tmp_path)
    assert [project["id"] for project in rerun].count("operational_workflow_design_airtable_implementation") == 1


def test_seed_enrichment_preserves_user_edits_and_multivalue_fields(tmp_path):
    seed = dict(SPRINT_26_5_SEEDED_PROJECTS[0])
    save_evidence_projects(
        [
            {
                **seed,
                "problem": "User edited problem.",
                "status": "Archived",
                "skills": ["Custom Skill"],
                "technologies": ["Custom Tool"],
                "tags": ["Custom Tag"],
                "links": ["https://example.com"],
                "notes": "Keep this note.",
            }
        ],
        tmp_path,
    )

    project = enrich_seed_evidence_projects(tmp_path)[0]
    assert project["problem"] == "User edited problem."
    assert project["status"] == "Archived"
    assert "Custom Skill" in project["skills"]
    assert "Custom Tool" in project["technologies"]
    assert "Custom Tag" in project["tags"]
    assert "Media Operations" in project["tags"]
    assert project["links"] == ["https://example.com"]
    assert project["notes"] == "Keep this note."


def test_role_associated_evidence_generation_context_is_role_scoped(tmp_path):
    _write_tracker(tmp_path)
    projects = enrich_seed_evidence_projects(tmp_path)
    ids = [projects[2]["id"], projects[3]["id"]]
    update_prospect("role_a", {"evidence_project_ids": ids}, tmp_path)

    tracker = yaml.safe_load((tmp_path / "data" / "application_tracker.yml").read_text(encoding="utf-8"))["applications"]
    role_a, role_b = tracker
    associated = evidence_projects_for_role(role_a, tmp_path)
    assert [project["id"] for project in associated] == ids
    assert evidence_projects_for_role(role_b, tmp_path) == []

    context = evidence_generation_context(associated)
    assert context.startswith("Verified role-associated Evidence projects")
    assert "Operational Workflow Design & Airtable Implementation" in context
    assert "more than $35,000" in context

    update_prospect("role_a", {"evidence_project_ids": [ids[0]]}, tmp_path)
    updated = yaml.safe_load((tmp_path / "data" / "application_tracker.yml").read_text(encoding="utf-8"))["applications"][0]
    assert [project["id"] for project in evidence_projects_for_role(updated, tmp_path)] == [ids[0]]
    assert len(load_evidence_projects(tmp_path)) == 4


def test_associated_evidence_reaches_resume_and_cover_letter_context():
    project_root = Path(__file__).resolve().parents[1]
    projects = load_evidence_projects(project_root)
    selected = [project for project in projects if project["id"] in {
        "operational_workflow_design_airtable_implementation",
        "enterprise_employee_engagement_community_fundraising_initiative",
    }]
    selected.sort(key=lambda project: project["id"])

    cover_context = load_generation_context("jobs/sample_job_description.md", project_root, selected)
    assert [project["title"] for project in cover_context["associated_evidence_projects"]] == [project["title"] for project in selected]
    assert "Verified role-associated Evidence" in cover_context["associated_evidence_context"]
    assert "100% employee participation" in cover_context["associated_evidence_context"]

    resume = _render_markdown(
        __import__("scripts.load_data", fromlist=["load_all_yaml"]).load_all_yaml(project_root),
        {"company": "Example", "job_title": "Operations Lead", "raw_text": "operations governance Airtable"},
        {"keyword_matches": [], "transferable_strengths": []},
        "executive_operations",
        selected,
    )
    assert "Operational Workflow Design & Airtable Implementation" in resume
    assert "100% employee participation" in resume
