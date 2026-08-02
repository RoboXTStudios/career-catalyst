from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.materials_library import find_exact_role_package
from scripts.repair_durable_paths import CONFIRMATION, build_report, main
from scripts.role_state_resolver import resolve_job_file, resolve_role_state


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    (root / "jobs").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "jobs" / "openai.md").write_text(
        "# Program Manager Lead\nCompany: OpenAI\nTracker ID: openai_program_manager_lead\n"
        "Source URL: https://jobs.example.test/openai/program-manager-lead\n\n"
        + "Lead cross-functional program delivery and operating rhythms. " * 8,
        encoding="utf-8",
    )
    return root


def _record(job_file: str = "/private/old/temp/openai.md") -> dict:
    return {
        "id": "openai_program_manager_lead",
        "company": "OpenAI",
        "role": "Program Manager Lead",
        "status": "Applied",
        "match_score": 91,
        "job_file": job_file,
        "evidence_project_ids": ["disney", "enterprise", "campaignos", "career-catalyst"],
        "application_history": [{"event": "Applied"}],
    }


def test_resolver_relinks_legacy_job_by_stable_tracker_id(tmp_path):
    root = _runtime(tmp_path)
    result = resolve_job_file(_record(), root)
    assert result["status"] == "valid"
    assert result["relinked"] is True
    assert Path(result["path"]) == root / "jobs" / "openai.md"


def test_resolver_rejects_ambiguous_identity(tmp_path):
    root = _runtime(tmp_path)
    duplicate = root / "jobs" / "openai-copy.md"
    duplicate.write_text((root / "jobs" / "openai.md").read_text(encoding="utf-8"), encoding="utf-8")
    result = resolve_job_file(_record(), root)
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2


def test_role_state_keeps_tracker_evidence_authoritative(tmp_path):
    root = _runtime(tmp_path)
    state = resolve_role_state("openai_program_manager_lead", {"applications": [_record()]}, root)
    assert state["evidence_project_ids"] == ["disney", "enterprise", "campaignos", "career-catalyst"]
    assert state["record"]["application_history"] == [{"event": "Applied"}]


def test_legacy_manifest_rebases_only_owned_package(tmp_path):
    root = _runtime(tmp_path)
    export = root / "exports"
    folder = export / "active" / "applied_followup" / "openai_program_manager_lead"
    folder.mkdir(parents=True)
    material = folder / "ats_resume.docx"
    material.write_bytes(b"owned")
    (folder / "manifest.json").write_text(json.dumps({"prospect_id": "openai_program_manager_lead", "files": {"ats_docx": "/private/old/temp/ats_resume.docx"}}), encoding="utf-8")
    found = find_exact_role_package(root, _record(), export_root=export)
    assert found["files"]["ats_docx"] == material


def test_repair_utility_dry_run_and_idempotent_apply(tmp_path):
    root = _runtime(tmp_path)
    tracker_path = root / "data" / "application_tracker.yml"
    tracker_path.write_text(yaml.safe_dump({"applications": [_record()]}, sort_keys=False), encoding="utf-8")
    export = root / "exports"
    first = build_report(root, export)
    assert first["roles_with_repairs"] == 1
    report_path = tmp_path / "report.json"
    assert main(["--runtime-root", str(root), "--export-root", str(export), "--report-json", str(report_path), "--apply", "--confirm", CONFIRMATION, "--backup-root", str(tmp_path / "backup")]) == 0
    applied = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
    assert applied["applications"][0]["job_file"] == "jobs/openai.md"
    second = build_report(root, export)
    assert second["roles_with_repairs"] == 0


def test_dry_run_writes_no_runtime_files(tmp_path):
    root = _runtime(tmp_path)
    tracker_path = root / "data" / "application_tracker.yml"
    tracker_path.write_text(yaml.safe_dump({"applications": [_record()]}, sort_keys=False), encoding="utf-8")
    before = tracker_path.read_bytes()
    report = build_report(root, root / "exports")
    assert report["apply"]["allowed"] is False
    assert tracker_path.read_bytes() == before
