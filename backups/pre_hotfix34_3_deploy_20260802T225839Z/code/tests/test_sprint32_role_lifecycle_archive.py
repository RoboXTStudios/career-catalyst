from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path
import shutil

import pytest
import yaml

import app
from scripts.application_tracker import (
    VALID_STATUSES,
    active_tracker_records,
    get_record_status,
    load_application_tracker,
    save_application_tracker,
    update_status,
)
from scripts.generate_dashboard import STATUS_FILTERS, filter_dashboard_records
from scripts.materials_library import write_role_manifest
from scripts.role_archive import (
    ARCHIVE_REASONS,
    archive_role,
    bulk_archive_roles,
    list_archive_entries,
    open_archive_folder,
    reopen_as_new_prospect,
)
from scripts.role_integrity import audit_role_integrity
from scripts.role_lifecycle import (
    ARCHIVE_ELIGIBLE_STATUSES,
    DASHBOARD_STATUS_ORDER,
    LIVE_STATUSES,
    TERMINAL_STATUSES,
    filter_live_records,
    lifecycle_counts,
    migrate_legacy_statuses,
)
from scripts.sprint32_maintenance import (
    MIGRATION_CONFIRMATION,
    apply_migration,
    migration_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _record(tracker_id: str, status: str = "Rejected", **values):
    return {
        "id": tracker_id,
        "company": values.pop("company", "Acme Media"),
        "role": values.pop("role", "Product Operations Director"),
        "status": status,
        "priority": "High",
        "show_on_dashboard": True,
        "job_file": f"jobs/{tracker_id}.md",
        "notes": "Preserve this note.",
        "application_history": [{"event": "status changed", "to": status}],
        "match_score": 81,
        "match_tier": "Strong Match",
        "evidence_project_ids": ["do_not_restore"],
        "follow_up_plan": {"stale": True},
        **values,
    }


def _runtime(tmp_path: Path, records: list[dict] | None = None) -> tuple[Path, Path, Path]:
    root = tmp_path / "runtime"
    exports = tmp_path / "documents" / "exports"
    archives = tmp_path / "documents" / "archive"
    (root / "data").mkdir(parents=True)
    (root / "jobs").mkdir(parents=True)
    records = records or [_record("acme_product_ops")]
    save_application_tracker(records, root)
    posting = (
        "# Product Operations Director\n\nCompany: Acme Media\nLocation: Los Angeles, CA\n\n"
        "Lead product strategy, roadmap planning, requirements, analytics, and cross-functional "
        "operations for emerging media experiences. Partner with content and technology teams.\n"
    )
    for record in records:
        (root / str(record["job_file"])).write_text(posting, encoding="utf-8")
    return root, exports, archives


def _package(exports: Path, record: dict, content: bytes = b"existing resume") -> Path:
    folder = exports / "active" / "in_progress" / record["id"]
    folder.mkdir(parents=True)
    resume = folder / "ats_resume.docx"
    resume.write_bytes(content)
    write_role_manifest(
        folder,
        record,
        {"ATS Resume": str(resume)},
        archived=False,
    )
    return folder


def _copy_foundation(root: Path) -> None:
    for directory in ("config", "data"):
        for source in (PROJECT_ROOT / directory).glob("*.yml"):
            target = root / directory / source.name
            if target.name == "application_tracker.yml":
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def test_canonical_registry_has_no_paused_and_is_shared_by_ui():
    assert "Paused" not in LIVE_STATUSES
    assert VALID_STATUSES == LIVE_STATUSES == DASHBOARD_STATUS_ORDER
    assert STATUS_FILTERS == ("All",) + LIVE_STATUSES
    assert app.status_options("Considered") == LIVE_STATUSES
    assert TERMINAL_STATUSES == ARCHIVE_ELIGIBLE_STATUSES


def test_paused_migrates_to_considered_and_second_run_is_noop():
    source = [_record("paused", "Paused")]
    migrated, first = migrate_legacy_statuses(source, migrated_at="2026-07-31T00:00:00Z")
    second, second_report = migrate_legacy_statuses(migrated, migrated_at="later")
    assert migrated[0]["status"] == "Considered"
    assert migrated[0]["lifecycle_migration"]["original_status"] == "Paused"
    assert get_record_status(migrated[0]) == "Considered"
    assert first["changed_count"] == 1
    assert second == migrated
    assert second_report["changed_count"] == 0


def test_unknown_status_is_preserved_and_reported():
    migrated, report = migrate_legacy_statuses([_record("odd", "Awaiting Oracle")])
    assert migrated[0]["status"] == "Awaiting Oracle"
    assert report["unknown_statuses"] == [{"id": "odd", "status": "Awaiting Oracle"}]


def test_summary_and_dropdown_filters_return_identical_live_sets():
    records = [_record(f"role_{index}", status) for index, status in enumerate(LIVE_STATUSES)]
    records.append(_record("legacy_archive", "Rejected", archived=True))
    counts = lifecycle_counts(records)
    assert counts["All"] == len(LIVE_STATUSES)
    assert {item["id"] for item in filter_live_records(records)} == {
        item["id"] for item in filter_dashboard_records(records, application_status="All")
    }
    for status in LIVE_STATUSES:
        expected = filter_live_records(records, status)
        actual = filter_dashboard_records(records, application_status=status)
        assert counts[status] == len(actual) == len(expected) == 1


def test_terminal_status_change_does_not_archive_automatically(tmp_path: Path):
    root, _exports, _archives = _runtime(tmp_path, [_record("role", "Prospect")])
    rejected = update_status("role", "Rejected", root)
    closed = update_status("role", "Withdrawn / Closed", root)
    assert rejected.get("archived") is not True
    assert closed.get("archived") is not True
    assert load_application_tracker(root)[0]["id"] == "role"


def test_archive_bundle_verified_before_live_removal(tmp_path: Path):
    record = _record("acme_product_ops")
    root, exports, archives = _runtime(tmp_path, [record])
    package = _package(exports, record)
    result = archive_role(
        record["id"], "Rejected", root, export_root=exports, archive_root=archives,
        archived_at="2026-07-31T10:00:00+00:00",
    )
    folder = Path(result["folder"])
    manifest = json.loads((folder / "role_manifest.json").read_text())
    assert not load_application_tracker(root)
    assert not package.exists()
    assert (folder / "role_summary.html").is_file()
    assert (folder / "job_posting.txt").is_file()
    assert (folder / "notes_and_status_history.txt").is_file()
    assert manifest["original_role_id"] == record["id"]
    assert manifest["final_status"] == "Rejected"
    assert manifest["match_score_snapshot"] == 81
    assert manifest["materials"][0]["sha256"]
    assert (folder / manifest["materials"][0]["filename"]).read_bytes() == b"existing resume"


def test_archive_failure_keeps_live_role_and_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    record = _record("acme_product_ops")
    root, exports, archives = _runtime(tmp_path, [record])
    package = _package(exports, record)
    monkeypatch.setattr("scripts.role_archive._copy_materials", lambda *_args: (_ for _ in ()).throw(OSError("copy failed")))
    with pytest.raises(OSError, match="copy failed"):
        archive_role(record["id"], "Rejected", root, export_root=exports, archive_root=archives)
    assert load_application_tracker(root)[0]["id"] == record["id"]
    assert package.is_dir()
    assert not list_archive_entries(archives)


def test_archive_cleanup_failure_rolls_back_tracker_bundle_and_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    record = _record("acme_product_ops")
    root, exports, archives = _runtime(tmp_path, [record])
    package = _package(exports, record)
    original_rmtree = shutil.rmtree
    failed_once = False

    def fail_staged_package_once(path, *args, **kwargs):
        nonlocal failed_once
        candidate = Path(path)
        if candidate.parent.name == ".sprint32_archive_staging" and not failed_once:
            failed_once = True
            raise OSError("cleanup failed")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("scripts.role_archive.shutil.rmtree", fail_staged_package_once)
    with pytest.raises(OSError, match="cleanup failed"):
        archive_role(record["id"], "Rejected", root, export_root=exports, archive_root=archives)
    assert load_application_tracker(root)[0]["id"] == record["id"]
    assert package.is_dir()
    assert not list_archive_entries(archives)


def test_archive_does_not_touch_shared_assets(tmp_path: Path):
    record = _record("acme_product_ops")
    root, exports, archives = _runtime(tmp_path, [record])
    _package(exports, record)
    shared = exports / "shared" / "golden_resume.docx"
    shared.parent.mkdir(parents=True)
    shared.write_bytes(b"golden")
    archive_role(record["id"], "Rejected", root, export_root=exports, archive_root=archives)
    assert shared.read_bytes() == b"golden"


def test_archive_ledger_is_minimal_and_reports_real_final_status(tmp_path: Path):
    record = _record("acme_product_ops", "Withdrawn / Closed")
    root, exports, archives = _runtime(tmp_path, [record])
    archive_role(record["id"], "Withdrawn / Closed", root, export_root=exports, archive_root=archives)
    ledger = list_archive_entries(archives)
    assert set(ledger[0]) == {
        "original_role_id", "company", "role_title", "final_status", "archived_at",
        "archive_folder", "manifest_path",
    }
    assert ledger[0]["final_status"] == "Withdrawn / Closed"
    source = inspect.getsource(app._render_archive)
    assert "Generate Package" not in source
    assert "Restore as" not in source


def test_open_folder_validates_archive_boundary_and_missing_folder(tmp_path: Path):
    archives = tmp_path / "archive"
    folder = archives / "acme" / "bundle"
    folder.mkdir(parents=True)
    calls = []
    opened, _message = open_archive_folder(
        folder, archives, opener=lambda args, **kwargs: calls.append((args, kwargs))
    )
    assert opened and calls[0][0] == ["open", str(folder.resolve())]
    assert not open_archive_folder(tmp_path / "outside", archives)[0]
    assert not open_archive_folder(archives / "missing", archives)[0]


def test_reopen_creates_fresh_scored_prospect_and_is_repeat_safe(tmp_path: Path):
    record = _record(
        "acme_product_ops",
        "Rejected",
        submitted_date="2026-07-01",
        selected_evidence_ids=["stale"],
        career_intelligence={"stale": True},
    )
    root, exports, archives = _runtime(tmp_path, [record])
    _copy_foundation(root)
    archived = archive_role(record["id"], "Rejected", root, export_root=exports, archive_root=archives)
    first = reopen_as_new_prospect(
        Path(archived["folder"]) / "role_manifest.json",
        root,
        archive_root=archives,
        request_id="click-1",
    )
    second = reopen_as_new_prospect(
        Path(archived["folder"]) / "role_manifest.json",
        root,
        archive_root=archives,
        request_id="click-1",
    )
    reopened = first["application"]
    assert first["created"] is True and second["created"] is False
    assert reopened["id"] != record["id"]
    assert get_record_status(reopened) == "Prospect"
    assert reopened["reopened_from_archive_id"] == record["id"]
    assert "submitted_date" not in reopened
    assert "selected_evidence_ids" not in reopened
    assert "career_intelligence" not in reopened
    assert reopened.get("match_score") is not None
    assert Path(archived["folder"]).is_dir()
    assert len(load_application_tracker(root)) == 1


def test_bulk_archive_reports_each_success_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    records = [_record("first"), _record("second")]
    root, exports, archives = _runtime(tmp_path, records)
    original = archive_role

    def selective(tracker_id, *args, **kwargs):
        if tracker_id == "second":
            raise OSError("simulated failure")
        return original(tracker_id, *args, **kwargs)

    monkeypatch.setattr("scripts.role_archive.archive_role", selective)
    result = bulk_archive_roles(
        ["first", "second"], root, export_root=exports, archive_root=archives
    )
    assert result["archived"] == ["first"]
    assert result["failed"] == {"second": "simulated failure"}
    assert [item["id"] for item in load_application_tracker(root)] == ["second"]


def test_integrity_audit_detects_paused_invisible_orphan_and_archive_mismatch(tmp_path: Path):
    records = [
        _record(
            "paused",
            "Paused",
            show_on_dashboard=False,
            material_paths={"ATS Resume": "/missing/resume.docx"},
        )
    ]
    root, exports, archives = _runtime(tmp_path, records)
    orphan = exports / "active" / "in_progress" / "orphan"
    orphan.mkdir(parents=True)
    (orphan / "manifest.json").write_text(json.dumps({"prospect_id": "missing", "files": {}}))
    missing_manifest = archives / "acme" / "bundle"
    missing_manifest.mkdir(parents=True)
    report = audit_role_integrity(root, export_root=exports, archive_root=archives)
    codes = {item["code"] for item in report["issues"]}
    assert {
        "legacy_paused_status",
        "invisible_live_role",
        "orphan_package_folder",
        "archive_folder_missing_manifest",
        "live_package_folder_missing",
    } <= codes
    assert report == audit_role_integrity(root, export_root=exports, archive_root=archives)


def test_archive_reason_registry_does_not_expose_legacy_passed():
    assert "Passed" not in ARCHIVE_REASONS


def test_post_merge_migration_is_backed_up_and_idempotent_on_runtime_copy(tmp_path: Path):
    records = [
        _record("paused", "Paused"),
        _record("legacy_archive", "Rejected", archived=True, archive_reason="Passed"),
    ]
    root, exports, archives = _runtime(tmp_path, records)
    tracker_path = root / "data/application_tracker.yml"
    import hashlib

    fingerprint = hashlib.sha256(tracker_path.read_bytes()).hexdigest()
    dry_run = migration_plan(root)
    assert dry_run["changed_count"] == 1
    assert dry_run["legacy_archive_count"] == 1
    result = apply_migration(
        root,
        export_root=exports,
        archive_root=archives,
        backup_root=tmp_path / "documents" / "backups",
        confirmation=MIGRATION_CONFIRMATION,
        app_stopped=True,
        expected_tracker_sha256=fingerprint,
        timestamp="20260731T130000Z",
    )
    remaining = load_application_tracker(root)
    assert [item["id"] for item in remaining] == ["paused"]
    assert remaining[0]["status"] == "Considered"
    assert result["post_migration_noop"] is True
    assert migration_plan(root)["would_mutate"] is False
    assert Path(result["backup"]["manifest_path"]).is_file()
    manifest = json.loads(next(archives.glob("*/*/role_manifest.json")).read_text())
    assert manifest["legacy_archive_reason"] == "Passed"
    assert manifest["legacy_status"] == "Rejected"
