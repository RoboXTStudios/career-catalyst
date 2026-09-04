from copy import deepcopy

from scripts.evidence_engine import (
    candidate_positioning_narrative,
    evidence_projects_for_role,
    job_requirement_coverage,
    rank_evidence_projects,
    seniority_erosion_warnings,
)


def project(identifier, **updates):
    value = {
        "id": identifier,
        "title": identifier.replace("_", " ").title(),
        "status": "Active",
        "industry": "",
        "function": "Operations",
        "problem": "The organization needed a stronger operating model.",
        "actions": "Improved a workflow.",
        "results": "Improved delivery.",
        "skills": [],
        "technologies": [],
        "tags": [],
    }
    value.update(updates)
    return value


def test_leadership_and_outcomes_outrank_superficial_technology_overlap():
    role = {"job_title": "Head of Operations", "job_description": "Lead enterprise transformation using Airtable and Teams."}
    leader = project(
        "leader",
        actions="Led and owned a company-wide cross-functional operating model transformation with executive stakeholders.",
        results="Reduced delivery risk by 35% and developed team leaders across multiple business units.",
        tags=["Leadership", "Transformation", "Business Impact"],
    )
    tools = project(
        "tools",
        actions="Used Airtable and Microsoft Teams.",
        results="Used Airtable for tracking.",
        technologies=["Airtable", "Microsoft Teams"],
    )
    ranked = rank_evidence_projects(role, [tools, leader])
    assert [item["project_id"] for item in ranked] == ["leader", "tools"]
    assert ranked[0]["dimensions"]["technology"] <= 6
    assert "Leadership / ownership match" in ranked[0]["reasons"]
    assert "Measurable business outcome" in ranked[0]["reasons"]


def test_archived_excluded_top_five_ordered_and_input_not_mutated():
    role = {"job_description": "Lead operations transformation, executive stakeholders, and measurable outcomes."}
    projects = [
        project(f"p{i}", actions=("Led transformation with executive stakeholders. " * i), results=f"Improved outcome by {i}0%.")
        for i in range(1, 7)
    ]
    projects[-1]["status"] = "Archived"
    before = deepcopy(projects)
    ranked = rank_evidence_projects(role, projects, limit=5)
    assert len(ranked) == 5
    assert all(item["project_id"] != "p6" for item in ranked)
    assert [item["score"] for item in ranked] == sorted((item["score"] for item in ranked), reverse=True)
    assert all(2 <= len(item["reasons"]) <= 4 for item in ranked)
    assert projects == before


def test_manual_selection_remains_authoritative(monkeypatch):
    projects = [project("recommended", actions="Led enterprise transformation."), project("manual")]
    monkeypatch.setattr("scripts.evidence_engine.load_evidence_projects", lambda root=None: projects)
    application = {"evidence_project_ids": ["manual"]}
    rank_evidence_projects({"job_description": "enterprise transformation"}, projects)
    assert [item["id"] for item in evidence_projects_for_role(application)] == ["manual"]
    assert application["evidence_project_ids"] == ["manual"]


def test_narrative_uses_only_supported_evidence_signals():
    role = {"job_title": "Operations Director", "job_description": "Lead transformation."}
    evidence = project(
        "operating_model",
        industry="Entertainment & Media",
        actions="Led a scalable workflow transformation and aligned executive stakeholders.",
    )
    narrative = candidate_positioning_narrative(role, rank_evidence_projects(role, [evidence]))
    assert "Entertainment operations" in narrative
    assert "transformation" in narrative
    assert "AI" not in narrative
    assert "talent" not in narrative


def test_requirement_coverage_names_supporters_and_preserves_unsupported_gaps():
    role = {"requirements": ["Lead enterprise workflow transformation", "Own pharmaceutical regulatory submissions"]}
    evidence = project("workflow", actions="Led enterprise workflow transformation.")
    coverage = job_requirement_coverage(role, rank_evidence_projects(role, [evidence]))
    assert coverage[0]["status"] == "Strongly supported"
    assert coverage[0]["evidence_projects"] == ["Workflow"]
    assert coverage[1] == {
        "requirement": "Own pharmaceutical regulatory submissions",
        "status": "Unsupported",
        "evidence_projects": [],
    }


def test_seniority_erosion_warnings_are_diagnostic_only():
    evidence = project(
        "leadership",
        actions="Led and owned enterprise transformation and trained a cross-functional team.",
    )
    before = deepcopy(evidence)
    content = "Supported delivery and provided support. Supporting teams, coordinating work, coordinated tasks, and coordination were central. Assisted with execution."
    warnings = seniority_erosion_warnings(content, [evidence])
    assert any("support language" in warning for warning in warnings)
    assert any("coordination language" in warning for warning in warnings)
    assert any("leadership or ownership" in warning for warning in warnings)
    assert any("enterprise or client scale" in warning for warning in warnings)
    assert any("transformation ownership" in warning for warning in warnings)
    assert evidence == before
