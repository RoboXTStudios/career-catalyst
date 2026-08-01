from __future__ import annotations

import shutil
from pathlib import Path

import yaml

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
    result = preflight_package_generation("generic", tracker, root, export_root=root / "qa_exports")
    assert result["status"] in {"ready", "repairable"}
    assert result["evidence_limits"] == {"ats_resume": 3, "styled_resume": 3, "cover_letter": 2}


def test_candidate_normalization_repairs_nonfactual_language_only():
    value = normalize_candidate_text("OMD Entertainment — a seasoned leader with 20+ years")
    assert value == "OMG23 (Omnicom Media Group) - an experienced leader with extensive experience"
    assert normalize_candidate_text(value) == value


def test_sanitized_fixture_catalog_covers_required_regressions():
    fixture_root = ROOT / "tests" / "fixtures" / "sprint34"
    fixtures = {path.stem: yaml.safe_load(path.read_text(encoding="utf-8")) for path in fixture_root.glob("*.yml")}
    assert {"openai_program_manager_lead", "3cloud_senior_director_digital_workplace", "netflix_product_manager", "generic_new_prospect"} == set(fixtures)
    assert fixtures["openai_program_manager_lead"]["expected"]["evidence_adjusted_score"] == 91
    assert fixtures["3cloud_senior_director_digital_workplace"]["missing_job_file"] is True
    assert fixtures["netflix_product_manager"]["formal_product_manager_title_claim"] is False
    assert fixtures["generic_new_prospect"]["compensation"] == "not_listed"


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
