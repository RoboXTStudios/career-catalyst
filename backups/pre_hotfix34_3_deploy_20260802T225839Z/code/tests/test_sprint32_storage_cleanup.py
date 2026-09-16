from __future__ import annotations

import json
from pathlib import Path

from scripts.application_tracker import save_application_tracker
from scripts.sprint32_cleanup import (
    APPLY_CONFIRMATION,
    apply_storage_cleanup,
    plan_storage_cleanup,
)


def _roots(tmp_path: Path):
    repository = tmp_path / "repository"
    runtime = tmp_path / "runtime"
    exports = tmp_path / "documents" / "exports"
    archives = tmp_path / "documents" / "archive"
    for path in (repository, runtime / "data", exports, archives):
        path.mkdir(parents=True)
    save_application_tracker(
        [{
            "id": "live", "company": "Acme", "role": "Director", "status": "Prospect",
            "priority": "High", "show_on_dashboard": True,
        }],
        runtime,
    )
    return repository, runtime, exports, archives


def test_cleanup_dry_run_is_immutable_and_preserves_user_files(tmp_path: Path):
    repository, runtime, exports, archives = _roots(tmp_path)
    cache = runtime / "scripts" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.pyc").write_bytes(b"cache")
    protected = exports / "active" / "in_progress" / "live" / "ats_resume.docx"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"user material")
    before = protected.read_bytes()
    plan = plan_storage_cleanup(
        repository_root=repository,
        runtime_root=runtime,
        export_root=exports,
        archive_root=archives,
    )
    assert cache.is_dir() and protected.read_bytes() == before
    assert any(item["path"] == str(cache) and item["action"] == "delete" for item in plan["actions"])
    assert any(item["path"] == str(protected) for item in plan["preserve"])


def test_cleanup_apply_quarantines_orphan_and_deletes_only_cache(tmp_path: Path):
    repository, runtime, exports, archives = _roots(tmp_path)
    cache = repository / ".pytest_cache"
    cache.mkdir()
    orphan = exports / "active" / "in_progress" / "orphan"
    orphan.mkdir(parents=True)
    (orphan / "resume.docx").write_bytes(b"orphan user work")
    (orphan / "manifest.json").write_text(json.dumps({"prospect_id": "missing", "files": {}}))
    plan = plan_storage_cleanup(
        repository_root=repository,
        runtime_root=runtime,
        export_root=exports,
        archive_root=archives,
    )
    result = apply_storage_cleanup(
        plan,
        quarantine_root=tmp_path / "quarantine",
        confirmation=APPLY_CONFIRMATION,
        app_stopped=True,
        timestamp="20260731T120000Z",
    )
    destination = Path(result["quarantine_root"]) / "exports" / orphan.relative_to(exports)
    assert not cache.exists()
    assert not orphan.exists()
    assert (destination / "resume.docx").read_bytes() == b"orphan user work"
    assert Path(result["manifest_path"]).is_file()


def test_cleanup_apply_requires_confirmation_and_stopped_app(tmp_path: Path):
    repository, runtime, exports, archives = _roots(tmp_path)
    plan = plan_storage_cleanup(
        repository_root=repository,
        runtime_root=runtime,
        export_root=exports,
        archive_root=archives,
    )
    try:
        apply_storage_cleanup(plan, quarantine_root=tmp_path / "q", confirmation="", app_stopped=True)
    except ValueError as error:
        assert "exact confirmation" in str(error)
    else:
        raise AssertionError("cleanup unexpectedly applied")
    try:
        apply_storage_cleanup(plan, quarantine_root=tmp_path / "q", confirmation=APPLY_CONFIRMATION, app_stopped=False)
    except ValueError as error:
        assert "stopped" in str(error)
    else:
        raise AssertionError("cleanup unexpectedly applied")


def test_cleanup_second_dry_run_is_noop_for_completed_actions(tmp_path: Path):
    repository, runtime, exports, archives = _roots(tmp_path)
    cache = runtime / "__pycache__"
    cache.mkdir()
    plan = plan_storage_cleanup(
        repository_root=repository, runtime_root=runtime, export_root=exports, archive_root=archives
    )
    apply_storage_cleanup(
        plan, quarantine_root=tmp_path / "q", confirmation=APPLY_CONFIRMATION,
        app_stopped=True, timestamp="20260731T120000Z",
    )
    second = plan_storage_cleanup(
        repository_root=repository, runtime_root=runtime, export_root=exports, archive_root=archives
    )
    assert not second["actions"]
