from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.package_generator import PackageGenerationError, generate_package
from scripts.package_quality import evaluate_candidate_facing_quality, save_package_summary
from tests.test_sprint35b_document_writing import _isolated_runtime


def _project(project_id: str, title: str | None = None) -> dict[str, str]:
    return {
        "id": project_id,
        "title": title or project_id.replace("_", " ").title(),
        "actions": "Coordinated the operating workflow and stakeholder delivery.",
        "results": "Improved visibility and execution quality.",
    }


def _metadata(selected: list[dict[str, str]], cover_used: list[dict[str, str]] | None = None):
    cover_used = cover_used or selected[:1]
    return {
        "selected_evidence": selected,
        "artifact_usage": {
            "ats_resume": {"used": selected[:3], "omitted": selected[3:], "fallback_used": []},
            "styled_resume": {"used": selected[:3], "omitted": selected[3:], "fallback_used": []},
            "cover_letter": {"used": cover_used, "omitted": [item for item in selected if item not in cover_used], "fallback_used": []},
        },
        "role_intelligence": {},
    }


def _gate(cover: str, *, selected: list[dict[str, str]], known: list[dict[str, str]] | None = None, metadata=None):
    metadata = metadata or _metadata(selected)
    return evaluate_candidate_facing_quality(
        {"cover_letter": cover},
        parsed_job={"company": "Airbnb", "job_title": "Marketing Operations Lead", "raw_text": "Marketing Operations"},
        tailoring_metadata=metadata,
        associated_evidence_projects=selected,
        known_projects=known or selected,
    )


def test_airbnb_duplicate_proof_is_blocked_with_specific_reasons():
    airtable = _project("operational_workflow_design_airtable", "Operational Workflow Design & Airtable Implementation")
    catalyst = _project("career_catalyst", "Career Catalyst")
    cover = (
        "Through Operational Workflow Design & Airtable Implementation, I coordinated an Airtable implementation "
        "that created a shared source of truth for campaign tracking, documentation, and status reporting.\n\n"
        "The Operational Workflow Design & Airtable Implementation work created a shared source of truth for "
        "campaign tracking, documentation, and workflow visibility across teams.\n\n"
        "Through Career Catalyst, I translated user needs into requirements, workflows, testing, and release guardrails.\n\n"
        "Career Catalyst also translated user needs into requirements, workflows, testing, and release guardrails for an active product."
    )
    result = _gate(cover, selected=[airtable, catalyst], metadata=_metadata([airtable, catalyst], [airtable, catalyst]))
    assert result["status"] == "BLOCKED"
    assert any("Airtable" in reason for reason in result["blocking_reasons"])
    assert any("Career Catalyst" in reason for reason in result["blocking_reasons"])


def test_airbnb_clean_proof_passes():
    airtable = _project("operational_workflow_design_airtable", "Operational Workflow Design & Airtable Implementation")
    catalyst = _project("career_catalyst", "Career Catalyst")
    result = _gate(
        "Through Operational Workflow Design & Airtable Implementation, I coordinated campaign tracking and "
        "documentation through a shared Airtable workflow.\n\n"
        "Through Career Catalyst, I translate user needs into tested requirements and release guardrails.",
        selected=[airtable, catalyst],
        metadata=_metadata([airtable, catalyst], [airtable, catalyst]),
    )
    assert result["status"] == "PASS"


def test_reusing_a_project_name_for_distinct_points_passes():
    project = _project("career_catalyst", "Career Catalyst")
    result = _gate(
        "Career Catalyst helped me define release guardrails for a local application.\n\n"
        "I also reference Career Catalyst when discussing the importance of testing workflows with users.",
        selected=[project],
        metadata=_metadata([project], [project]),
    )
    assert result["status"] == "PASS"


def test_unselected_evidence_leak_is_blocked():
    selected = _project("airtable", "Operational Workflow Design & Airtable Implementation")
    unselected = _project("career_catalyst", "Career Catalyst")
    result = _gate(
        "I coordinated the selected Airtable workflow. Career Catalyst is another product proof point.",
        selected=[selected],
        known=[selected, unselected],
    )
    assert result["status"] == "BLOCKED"
    assert any("unselected Evidence/project" in reason for reason in result["blocking_reasons"])


def test_valid_selected_evidence_omission_passes():
    selected = [_project(f"project_{index}", f"Selected Project {index}") for index in range(4)]
    metadata = _metadata(selected, selected[:2])
    result = _gate(
        "Through Selected Project 0, I improved planning visibility.\n\n"
        "Through Selected Project 1, I strengthened stakeholder execution.",
        selected=selected,
        metadata=metadata,
    )
    assert result["status"] == "PASS"


def test_role_override_contradiction_is_blocked_and_valid_override_passes():
    selected = _project("airtable", "Operational Workflow Design & Airtable Implementation")
    metadata = _metadata([selected])
    metadata["role_intelligence"] = {
        "inferred": {"category": "Nonprofit Social Impact", "role_family": "Creative Marketing Ops"},
        "effective": {"category": "Marketing Operations", "role_family": "Marketing Strategy & Operations"},
        "overrides": {"category": "Marketing Operations", "role_family": "Marketing Strategy & Operations"},
    }
    blocked = _gate("My background spans Nonprofit Social Impact and Creative Marketing Ops.", selected=[selected], metadata=metadata)
    assert blocked["status"] == "BLOCKED"
    assert any("stale inferred" in reason for reason in blocked["blocking_reasons"])
    clean = _gate("My background supports Marketing Operations and Marketing Strategy & Operations.", selected=[selected], metadata=metadata)
    assert clean["status"] == "PASS"


def test_package_summary_exposes_candidate_facing_qa_status(tmp_path: Path):
    result = save_package_summary(
        tmp_path,
        {"job_title": "Marketing Operations Lead", "company": "Airbnb"},
        {"label": "Fresh", "posting_status": "Open"},
        {"overall_score": 88, "apply_recommendation": "Apply", "dimensions": {}},
        {
            "resume_tailoring_score": 88,
            "cover_letter_score": 88,
            "ats_keyword_match": 88,
            "voice_match": 88,
            "confidence_level": "High",
            "candidate_facing_qa": {"status": "PASS", "blocking_reasons": []},
        },
    )
    summary = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "Candidate-facing QA: PASS" in summary


def test_blocked_staged_package_preserves_existing_valid_package(tmp_path: Path, monkeypatch):
    root = _isolated_runtime(tmp_path, "airbnb-quality-role", "openai_sales_strategy_operations.md", ["career_catalyst"])
    export_root = tmp_path / "exports"
    prior = export_root / "active" / "in_progress" / "airbnb-quality-role"
    prior.mkdir(parents=True)
    marker = prior / "prior.txt"
    marker.write_text("prior valid package", encoding="utf-8")
    (prior / "manifest.json").write_text(json.dumps({"prospect_id": "airbnb-quality-role", "files": {"prior": str(marker)}}), encoding="utf-8")
    tracker_before = (root / "data" / "application_tracker.yml").read_bytes()

    monkeypatch.setattr(
        "scripts.package_generator.evaluate_candidate_facing_quality",
        lambda *args, **kwargs: {"status": "BLOCKED", "blocking_reasons": ["fixture duplication"], "checks": {}},
    )
    with pytest.raises(PackageGenerationError, match="Candidate-facing QA blocked"):
        generate_package("airbnb-quality-role", root, force_clean_draft=True, export_root=export_root)
    assert marker.read_text(encoding="utf-8") == "prior valid package"
    assert (prior / "manifest.json").is_file()
    assert (root / "data" / "application_tracker.yml").read_bytes() == tracker_before
