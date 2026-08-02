from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path

import yaml

import app
from scripts.application_tracker import (
    find_existing_prospect,
    load_application_tracker,
    save_application_tracker,
)
from scripts.materials_library import write_role_manifest
from scripts.package_generator import preflight_package_generation


ROOT = Path(__file__).resolve().parents[1]


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    for name in ("data", "config", "jobs", "templates"):
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, root / name)
    return root


def _record(**updates):
    record = {
        "id": "openai_program_manager_lead",
        "company": "OpenAI",
        "role": "Program Manager Lead",
        "status": "Applied",
        "priority": "High",
        "show_on_dashboard": True,
        "official_url": "https://jobs.example.test/openai/12345",
        "job_id": "12345",
        "match_score": 91,
        "evidence_project_ids": ["evidence-one", "evidence-two"],
        "application_history": [{"event": "Applied", "date": "2026-08-01"}],
        "notes": "Preserve this note",
    }
    record.update(updates)
    return record


def test_duplicate_identity_is_read_only_and_stable_id_first(tmp_path):
    save_application_tracker([_record()], tmp_path)
    before = (tmp_path / "data" / "application_tracker.yml").read_bytes()
    found = find_existing_prospect(
        {
            "company": "OpenAI",
            "job_title": "Program Manager Lead",
            "official_url": "https://jobs.example.test/openai/12345/",
        },
        tmp_path,
    )
    assert found and found["id"] == "openai_program_manager_lead"
    assert (tmp_path / "data" / "application_tracker.yml").read_bytes() == before


def test_edit_existing_role_preserves_status_score_evidence_and_history(tmp_path):
    save_application_tracker([_record()], tmp_path)
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "openai.md").write_text(
        "# Program Manager Lead\nCompany: OpenAI\n\nOld posting text.\n",
        encoding="utf-8",
    )
    app.update_dashboard_role(
        "openai_program_manager_lead",
        {
            "company": "OpenAI",
            "role": "Senior Program Manager Lead",
            "location": "Remote",
            "work_arrangement": "Remote",
            "status": "Applied",
            "notes": "Updated note",
            "job_file": "jobs/openai.md",
            "job_description": "Updated posting text with delivery and governance outcomes.",
        },
        tmp_path,
    )
    updated = load_application_tracker(tmp_path)[0]
    assert updated["role"] == "Senior Program Manager Lead"
    assert updated["status"] == "Applied"
    assert updated["match_score"] == 91
    assert updated["evidence_project_ids"] == ["evidence-one", "evidence-two"]
    assert updated["application_history"] == [{"event": "Applied", "date": "2026-08-01"}]
    assert "Updated posting text" in (tmp_path / "jobs" / "openai.md").read_text(encoding="utf-8")


def test_exact_owned_manifest_replaces_stale_private_tracker_paths(tmp_path, monkeypatch):
    root = _runtime(tmp_path)
    application = _record(
        job_file="jobs/openai.md",
        material_paths={"Tailored Resume": "/private/Users/stale/exports/resume.md"},
    )
    job = root / "jobs" / "openai.md"
    job.write_text(
        "# Program Manager Lead\nCompany: OpenAI\nTracker ID: openai_program_manager_lead\n\n"
        + "Lead program operations and cross-functional delivery with measurable outcomes.\n",
        encoding="utf-8",
    )
    export_root = root / "exports"
    package_folder = export_root / "active" / "applied_followup" / application["id"]
    material = package_folder / "resume.docx"
    material.parent.mkdir(parents=True)
    material.write_bytes(b"owned")
    manifest = write_role_manifest(
        package_folder,
        application,
        {"ats_docx": str(material)},
        archived=False,
    )
    application["package_manifest"] = manifest
    monkeypatch.setenv("CAREER_CATALYST_EXPORT_ROOT", str(export_root))
    result = preflight_package_generation(
        application["id"], {"applications": [application]}, root
    )
    assert not any(item.get("material_type") == "Legacy package path" for item in result["conflicts"])


def test_generation_page_uses_persistent_exact_package_controls():
    source = inspect.getsource(app._render_generate_package)
    assert "_render_persistent_package_controls" in source
    helper = inspect.getsource(app._render_persistent_package_controls)
    assert "find_exact_role_package" in helper
    assert "Open package folder" in helper


def test_failed_generation_validates_before_organizing():
    source = inspect.getsource(__import__("scripts.package_generator", fromlist=["_generate_package_in_place"])._generate_package_in_place)
    assert source.index("precheck = validate_package_outputs") < source.index("organized = organize_package_outputs")
