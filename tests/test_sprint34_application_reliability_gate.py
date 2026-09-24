from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from tests.fixture_support import replace_evidence_projects, with_confirmed_role_family

from scripts.evidence_tailoring import evidence_score_contribution
from scripts.score_match import score_job_match
from scripts.package_generator import (
    PackageGenerationError,
    generate_package,
    job_reference_health,
    preflight_package_generation,
)
from scripts.text_cleanup import normalize_candidate_text


ROOT = Path(__file__).resolve().parents[1]


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    for name in ("data", "config", "jobs", "templates"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, root / name)
    return root


def test_missing_job_is_blocked_without_raising(tmp_path: Path):
    root = _runtime(tmp_path)
    tracker = {
        "applications": [{
            "id": "missing-role",
            "stable_slug": "missing-role",
            "company": "Example",
            "role": "Operations Lead",
            "status": "Prospect",
            "job_file": "jobs/no-longer-present.md",
            "source_url": "https://example.test/jobs/123",
            "evidence_project_ids": [],
        }]
    }
    health = job_reference_health(tracker["applications"][0], root)
    assert health["status"] == "missing"
    result = preflight_package_generation("missing-role", tracker, root)
    assert result["status"] == "blocked"
    assert result["job_health"]["recoverable"] is True


def test_selected_evidence_limits_are_transparent(tmp_path: Path):
    root = _runtime(tmp_path)
    job = next((ROOT / "tests" / "fixtures" / "jobs").glob("example_company_senior_operations.md"))
    target = root / "jobs" / job.name
    shutil.copy2(job, target)
    parsed = __import__("scripts.parse_job", fromlist=["parse_job_description"]).parse_job_description(target)
    tracker = {"applications": [{
        "id": "generic",
        "stable_slug": "generic",
        "company": parsed["company"],
        "role": parsed["job_title"],
        "status": "Prospect",
        "job_file": str(target.relative_to(root)),
        "evidence_project_ids": [],
        "material_paths": {},
    }]}
    with_confirmed_role_family(tracker["applications"][0], root)
    result = preflight_package_generation("generic", tracker, root, export_root=root / "qa_exports")
    assert result["status"] in {"ready", "repairable"}
    assert result["evidence_limits"] == {"ats_resume": 3, "styled_resume": 3, "cover_letter": 2}


def test_candidate_normalization_repairs_nonfactual_language_only():
    value = normalize_candidate_text("OMD Entertainment — a seasoned leader with 20+ years")
    assert value == "OMG23 / OMD Entertainment, Omnicom Media Group - an experienced leader with extensive experience"
    assert normalize_candidate_text(value) == value


def test_sanitized_fixture_catalog_covers_required_regressions():
    fixture_root = ROOT / "tests" / "fixtures" / "sprint34"
    fixtures = {path.stem: yaml.safe_load(path.read_text(encoding="utf-8")) for path in fixture_root.glob("*.yml")}
    assert {"openai_program_manager_lead", "3cloud_senior_director_digital_workplace", "netflix_product_manager", "generic_new_prospect"} == set(fixtures)
    expected = fixtures["openai_program_manager_lead"]["expected"]
    # This sanitized posting is intentionally not a copy of the live prospect.
    # Its score must be calibrated to its own deterministic inputs, not to a
    # historical production score that included different posting content.
    assert expected["base_score"] == 75
    assert expected["evidence_contribution"] == 0
    assert expected["final_score"] == 75
    assert fixtures["3cloud_senior_director_digital_workplace"]["missing_job_file"] is True
    assert fixtures["netflix_product_manager"]["formal_product_manager_title_claim"] is False
    assert fixtures["generic_new_prospect"]["compensation"] == "not_listed"


def _write_openai_fixture_runtime(root: Path) -> None:
    fixture_root = ROOT / "tests" / "fixtures" / "sprint34"
    shutil.copy2(
        fixture_root / "openai_program_manager_lead.md",
        root / "jobs" / "openai_program_manager_lead.md",
    )
    projects = [
        {
            "id": "career_catalyst",
            "title": "Career Catalyst",
            "problem": "Applicants needed a grounded application workflow.",
            "actions": "Built product workflows.",
            "results": "Improved product operations.",
            "tags": ["product", "AI transformation"],
            "status": "Active",
            "external_use": True,
        },
        {
            "id": "governance_qa_delivery",
            "title": "Governance and QA Delivery",
            "problem": "Delivery needed clear quality controls.",
            "actions": "Led delivery work.",
            "results": "Established reliable delivery outcomes.",
            "tags": ["delivery", "quality assurance", "governance"],
            "status": "Active",
            "external_use": True,
        },
        {
            "id": "omg23_disney_leadership",
            "title": "OMG23 Disney Leadership",
            "problem": "An enterprise media organization needed stronger operations.",
            "actions": "Led operational work.",
            "results": "Improved operational execution.",
            "tags": ["operations"],
            "status": "Active",
            "external_use": True,
        },
        {
            "id": "roboxt_studios",
            "title": "RoboXT Studios",
            "problem": "A growing studio needed repeatable workflows.",
            "actions": "Improved product operations.",
            "results": "Created delivery outcomes.",
            "tags": ["product", "workflow design"],
            "status": "Active",
            "external_use": True,
        },
    ]
    replace_evidence_projects(root / "data" / "evidence_projects.yml", projects)
    tracker = {
        "applications": [
            {
                "id": "openai_program_manager_lead",
                "stable_slug": "openai_program_manager_lead",
                "company": "OpenAI",
                "role": "Program Manager, Lead",
                "status": "Prospect",
                "priority": "High",
                "show_on_dashboard": True,
                "source_url": "https://jobs.example.test/openai/program-manager-lead",
                "job_file": "jobs/openai_program_manager_lead.md",
                "evidence_project_ids": [
                    "career_catalyst",
                    "governance_qa_delivery",
                    "omg23_disney_leadership",
                    "roboxt_studios",
                ],
                "compensation_disclosure_state": "not_listed",
                "material_paths": {},
            }
        ]
    }
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8"
    )


def test_sanitized_openai_score_is_deterministic_and_unchanged_by_generation(tmp_path: Path):
    root = _runtime(tmp_path)
    _write_openai_fixture_runtime(root)
    from scripts.evidence_engine import evidence_projects_for_role
    from scripts.application_tracker import load_application_tracker

    expected = yaml.safe_load(
        (ROOT / "tests" / "fixtures" / "sprint34" / "openai_program_manager_lead.yml").read_text(
            encoding="utf-8"
        )
    )["expected"]
    application = load_application_tracker(root)[0]
    projects = evidence_projects_for_role(application, root)
    baseline = score_job_match(
        "jobs/openai_program_manager_lead.md", root, []
    )
    adjusted = score_job_match(
        "jobs/openai_program_manager_lead.md", root, projects
    )
    contribution = evidence_score_contribution(baseline, adjusted)
    assert baseline["match_score"] == expected["base_score"] == 75
    assert contribution["delta"] == expected["evidence_contribution"] == 0
    assert contribution["matched_requirements"] == ["delivery outcomes", "product operations"]
    assert adjusted["match_score"] == expected["final_score"] == 75

    generate_package(
        "openai_program_manager_lead",
        root,
        generate_followups_too=False,
        export_root=root / "qa_exports",
    )
    after = score_job_match(
        "jobs/openai_program_manager_lead.md", root, projects
    )
    assert after["match_score"] == adjusted["match_score"] == expected["final_score"] == 75


def test_high_scoring_role_remains_high_scoring_through_generation(tmp_path: Path):
    root = _runtime(tmp_path)
    job_path = root / "jobs" / "high_signal_role.md"
    job_path.write_text(
        """# Director, Program Operations\nCompany: OpenAI\nTracker ID: high_signal_role\nLocation: Remote\nWork arrangement: Remote\nSalary range: $180,000-$240,000\nPosting date: 2026-07-20\n\n## Job Description\nLead enterprise strategy, business operations, strategic programs, program management, portfolio delivery, cross-functional execution, executive communication, operational planning, process improvement, change management, governance, quality assurance, risk, requirements, roadmaps, product operations, AI transformation, automation, marketing technology, measurement, campaign operations, data, analytics, vendor management, budgets, and executive reporting.\n\nQualifications include program management, stakeholder alignment, product operations, workflow design, executive communication, and measurable delivery outcomes.\n""",
        encoding="utf-8",
    )
    tracker = {
        "applications": [{
            "id": "high_signal_role",
            "stable_slug": "high_signal_role",
            "company": "OpenAI",
            "role": "Director, Program Operations",
            "status": "Prospect",
            "priority": "High",
            "show_on_dashboard": True,
            "source_url": "https://jobs.example.test/openai/high-signal",
            "job_file": "jobs/high_signal_role.md",
            "evidence_project_ids": [],
            "compensation_disclosure_state": "provided",
            "material_paths": {},
        }]}
    (root / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8"
    )
    before = score_job_match("jobs/high_signal_role.md", root, [])
    assert before["match_score"] >= 82
    generate_package(
        "high_signal_role",
        root,
        generate_followups_too=False,
        export_root=root / "qa_exports",
    )
    after = score_job_match("jobs/high_signal_role.md", root, [])
    assert after["match_score"] == before["match_score"]
    assert after["match_score"] >= 82


def test_failed_generation_preserves_existing_tracker_and_package(tmp_path, monkeypatch):
    root = _runtime(tmp_path)
    tracker_path = root / "data" / "application_tracker.yml"
    tracker_path.write_text(yaml.safe_dump({"applications": []}), encoding="utf-8")
    existing = root / "qa_exports" / "active" / "in_progress" / "role" / "resume.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("old package\n", encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise PackageGenerationError("sanitized generation failure")

    monkeypatch.setattr("scripts.package_generator._generate_package_in_place", fail)
    before = tracker_path.read_bytes()
    try:
        generate_package("missing-role", root, export_root=root / "qa_exports")
    except PackageGenerationError:
        pass
    assert tracker_path.read_bytes() == before
    assert existing.read_text(encoding="utf-8") == "old package\n"
