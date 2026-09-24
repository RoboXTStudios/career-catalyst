from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from scripts.evidence_tailoring import project_header_line, resume_project_bullets
from scripts.evidence_engine import evidence_placeholders, load_evidence_projects, upsert_evidence_project
from scripts.package_generator import preflight_package_generation
from scripts.package_quality import _PLACEHOLDER_PATTERNS
from scripts.parse_job import parse_job_description
from tests.fixture_support import with_confirmed_role_family


ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "tests" / "fixtures" / "jobs" / "example_company_senior_operations.md"

FYC_WITH_PLACEHOLDER = {
    "id": "fyc_placeholder",
    "title": "Awards Season (FYC) Campaign Operations",
    "problem": "FYC campaigns run on fixed nomination and voting windows.",
    "actions": "Managed creative and ad operations for FYC campaigns across studios.",
    "results": "Supported FYC campaigns. [Add any concrete outcome you can stand behind.]",
    "status": "Active",
}


@pytest.fixture()
def runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    for name in ("data", "config", "templates"):
        shutil.copytree(ROOT / name, root / name)
    (root / "jobs").mkdir()
    shutil.copy2(JOB, root / "jobs" / JOB.name)
    return root


def test_bracketed_author_notes_are_detected_but_links_are_not():
    found = evidence_placeholders(FYC_WITH_PLACEHOLDER)
    assert found == [{"field": "results", "text": "[Add any concrete outcome you can stand behind.]"}]
    assert evidence_placeholders({"actions": "Led [confirm dates] rollout."})[0]["field"] == "actions"
    assert not evidence_placeholders({"actions": "See [the case study](https://example.com) and note [1]."})


def test_generated_text_with_author_notes_fails_the_placeholder_gate():
    for text in ("Delivered on time [confirm dates].", "Grew reach [add metric]."):
        assert any(re.search(pattern, text) for pattern in _PLACEHOLDER_PATTERNS), text
    assert not any(re.search(pattern, "Worked across CM360 and DV360.") for pattern in _PLACEHOLDER_PATTERNS)


def test_preflight_blocks_selected_evidence_with_placeholders(runtime: Path):
    upsert_evidence_project(dict(FYC_WITH_PLACEHOLDER), runtime)
    parsed = parse_job_description(runtime / "jobs" / JOB.name)
    record = with_confirmed_role_family({
        "id": "generic",
        "stable_slug": "generic",
        "company": parsed["company"],
        "role": parsed["job_title"],
        "status": "Prospect",
        "job_file": f"jobs/{JOB.name}",
        "evidence_project_ids": ["fyc_placeholder"],
        "material_paths": {},
    }, runtime)
    result = preflight_package_generation(
        "generic", {"applications": [record]}, runtime, export_root=runtime / "qa_exports"
    )
    assert result["status"] == "blocked"
    issue = next(item for item in result["blocking_issues"] if "placeholder" in item)
    assert "Awards Season (FYC) Campaign Operations" in issue
    assert "results" in issue

    record["evidence_project_ids"] = [load_evidence_projects(runtime)[0]["id"]]
    clean = preflight_package_generation(
        "generic", {"applications": [record]}, runtime, export_root=runtime / "qa_exports"
    )
    assert not any("placeholder" in item for item in clean["blocking_issues"])


FYC_SAVED = {
    "id": "fyc",
    "title": "Awards Season (FYC) Campaign Operations",
    "employer": "OMG23 (Omnicom Media Group)",
    "client": "The Walt Disney Company: Pixar, Searchlight Pictures, 20th Century Studios, and Disney+",
    "project_type": "Awards Campaign Operations",
    "actions": (
        "Managed creative and ad operations for FYC campaigns across Disney's film studios, including Pixar, "
        "Searchlight Pictures, and 20th Century Studios. Coordinated creative specs, asset delivery, and placement "
        "deadlines with entertainment trade publications, including Deadline and The Hollywood Reporter."
    ),
    "results": (
        "Supported FYC campaigns across multiple Disney studios through repeated awards seasons. "
        "[Add any concrete outcome you can stand behind.]"
    ),
    "tags": ["FYC", "trade media"],
}
THEATRICAL_SAVED = {
    "id": "theatrical",
    "title": "Disney Studios Theatrical & Home Entertainment Campaign Operations",
    "client": "The Walt Disney Company: Disney Studios Theatrical and Home Entertainment (including Pixar, Marvel, Lucasfilm, and Disney+)",
    "actions": "Oversaw campaign execution for every release, including all Marvel Phase 5 films and Lucasfilm titles.",
    "results": (
        "Delivered campaign operations for the full slate over a decade. "
        "Managed budgets that ranged from about $5M to about $25M per title across all Disney IPs."
    ),
    "technologies": ["CM360", "DV360"],
}


def test_header_keeps_only_names_the_evidence_supports():
    line, dropped = project_header_line(FYC_SAVED)
    assert "Pixar, Searchlight Pictures, and 20th Century Studios" in line
    assert "Disney+" not in line
    assert dropped == ["Disney+"]
    line, dropped = project_header_line(THEATRICAL_SAVED)
    assert "(including Marvel and Lucasfilm)" in line
    assert dropped == ["Pixar", "Disney+"]


def test_bullets_keep_named_entities_and_figures_over_generic_results():
    fyc = resume_project_bullets(FYC_SAVED, {})
    assert any("Deadline and The Hollywood Reporter" in bullet for bullet in fyc)
    assert not any("[" in bullet for bullet in fyc)
    theatrical = resume_project_bullets(THEATRICAL_SAVED, {})
    assert any("$5M" in bullet and "$25M" in bullet for bullet in theatrical)
    assert not any(bullet.startswith("Delivered campaign operations for the full slate") for bullet in theatrical)
