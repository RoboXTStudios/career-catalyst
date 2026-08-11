"""Surgical Sprint 41 production-shaped material-generation regressions."""

from __future__ import annotations

from pathlib import Path
import re

from scripts import package_generator
from scripts.generate_cover_letter import _ground_cover_letter_in_selected_evidence
from scripts.package_generator import generate_package, preflight_package_generation
from scripts.role_intent import align_role_intent_to_effective_intelligence
from tests.test_sprint38_5_reparse_state_consistency import _reopened_live_nation_root
from tests.test_sprint41_candidate_materials_readiness import (
    _score_canary,
    _select_three_evidence,
)


def test_live_nation_production_shape_uses_tracker_company_and_effective_family(
    tmp_path: Path, monkeypatch
):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    _select_three_evidence(root, tracker_id)
    job = next((root / "jobs").glob("*.md"))
    job.write_text(
        job.read_text(encoding="utf-8").replace("Company: Live Nation Worldwide\n", ""),
        encoding="utf-8",
    )

    original_build_role_intent = package_generator.build_role_intent

    def stale_role_intent(role, project_root=None):
        intent = original_build_role_intent(role, project_root)
        intent["primary_archetype"] = "martech_governance_adoption"
        intent["package_role_family"] = "martech_governance_adoption"
        intent["resume"]["headline_profile"] = (
            "Experiential Production & Live Events Leader | Activations"
        )
        return intent

    monkeypatch.setattr(package_generator, "build_role_intent", stale_role_intent)
    monkeypatch.setattr("scripts.package_generator.score_job_match", _score_canary)
    export_root = tmp_path / "exports"
    preflight = preflight_package_generation(
        tracker_id,
        package_generator.load_application_tracker(root),
        root,
        export_root=export_root,
    )
    assert not any("different opportunity" in str(item).lower() for item in preflight["conflicts"])

    result = generate_package(tracker_id, root, export_root=export_root)
    files = result["manifest"]["files"]
    assert Path(files["ats_docx"]).is_file()
    assert Path(files["styled_docx"]).is_file()
    resume = Path(files["resume_text"]).read_text(encoding="utf-8")
    cover = Path(files["cover_letter"]).read_text(encoding="utf-8")
    note = Path(files["application_note"]).read_text(encoding="utf-8")

    assert result["match_score"] == 62
    assert "Live Nation Worldwide" in cover
    candidate_text = resume + cover + note
    assert not re.search(r"\b(?:at|for|to|from) Company\b", candidate_text)
    assert "career-catalyst-company: Company -->" not in candidate_text
    assert "MarTech" not in cover
    assert "Experiential Production & Live Events Leader" not in resume
    assert cover.lower().count("just for us") <= 1
    assert "Live Nation Worldwide" in note
    assert result["package_quality"]["candidate_facing_qa"]["status"] == "PASS"


def test_effective_family_replaces_stale_candidate_writing_profile():
    stale = {
        "primary_archetype": "martech_governance_adoption",
        "package_role_family": "martech_governance_adoption",
        "resume": {
            "headline_profile": "Experiential Production & Live Events Leader | Activations"
        },
    }
    aligned = align_role_intent_to_effective_intelligence(
        stale,
        {
            "role_family": "experiential_live_event_production",
            "role_family_label": "Experiential Production / Live Event Production",
        },
    )
    assert aligned["package_role_family"] == "experiential_live_event_production"
    assert aligned["resume"]["headline_profile"].startswith("Senior Operations Leader")


def test_selected_podcast_proof_is_not_reappended_by_grounding():
    project = {
        "id": "just_for_us_podcast",
        "title": "Just for Us Podcast — Audio Production & Editing",
        "actions": "Served as audio producer and editor for a ten-episode series.",
        "results": "Prepared each episode for release.",
    }
    context = {
        "parsed_job": {"job_title": "Experiential Producer"},
        "cover_letter_evidence_selection": {"used_projects": [project]},
        "role_intent": {"package_role_family": "experiential_live_event_production"},
        "associated_evidence_projects": [project],
    }
    content = (
        "Dear Hiring Team,\n\nI served as audio producer and editor for Just for Us.\n\nBest,\nTrisha Lynch"
    )
    grounded = _ground_cover_letter_in_selected_evidence(content, context)
    assert grounded.lower().count("just for us") == 1


def test_strong_fit_martech_language_remains_available(tmp_path: Path):
    from tests.test_sprint35b_document_writing import _isolated_runtime

    root = _isolated_runtime(
        tmp_path,
        "openai-strong-fit-hotfix",
        "openai_sales_strategy_operations.md",
        [
            "enterprise_media_operations_transformation",
            "career_catalyst",
            "disney_plus_launch_readiness",
        ],
    )
    result = generate_package(
        "openai-strong-fit-hotfix", root, export_root=tmp_path / "exports"
    )
    assert result["package_quality"]["candidate_facing_qa"]["status"] == "PASS"
    resume = Path(result["manifest"]["files"]["resume_text"]).read_text(encoding="utf-8")
    assert "Senior Strategy & Operations Leader" in resume
