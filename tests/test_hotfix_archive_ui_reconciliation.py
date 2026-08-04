from __future__ import annotations

import inspect
from pathlib import Path

import app
from scripts.application_tracker import (
    active_tracker_records,
    load_application_tracker,
    save_application_tracker,
)
from scripts.role_archive import archive_role, list_archive_entries


def _runtime(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    root = tmp_path / "runtime"
    exports = tmp_path / "exports"
    archives = tmp_path / "archive"
    (root / "data").mkdir(parents=True)
    (root / "jobs").mkdir(parents=True)
    record = {
        "id": "closed-role",
        "company": "Example Media",
        "role": "Director of Operations",
        "status": "Withdrawn / Closed",
        "priority": "Medium",
        "notes": "Preserve this note.",
        "source": "Official career page",
        "location": "Los Angeles, CA",
        "salary_range": "$150,000-$180,000",
        "posting_status": "Open",
        "verification_status": "Employer Source",
        "source_trust_label": "Direct Employer",
        "match_tier": "Strong Match",
        "job_file": "jobs/closed-role.md",
        "show_on_dashboard": True,
        "application_history": [{"event": "status changed", "to": "Withdrawn / Closed"}],
        "match_score": 81,
    }
    save_application_tracker([record], root)
    (root / "jobs" / "closed-role.md").write_text(
        "# Director of Operations\n\nCompany: Example Media\n",
        encoding="utf-8",
    )
    return root, exports, archives, record


def test_active_summary_label_and_filter_exclude_archived_only_status():
    summary = {"Total": 32, "Rejected": 9, "Applied": 20, "Under Consideration": 3}

    assert app.application_summary_navigation(summary)[0] == ("Active", "All", 32)
    assert "Withdrawn / Closed" not in app.active_application_status_options()
    assert "Rejected" in app.active_application_status_options()


def test_archive_confirmation_and_transaction_preserve_final_status(tmp_path: Path):
    root, exports, archives, record = _runtime(tmp_path)

    archive_role(
        record["id"],
        "Withdrawn / Closed",
        root,
        export_root=exports,
        archive_root=archives,
        archived_at="2026-08-04T20:00:00+00:00",
    )

    message = app.archive_confirmation_message("Withdrawn / Closed")
    assert message == (
        "Archived as Withdrawn / Closed. Open the Archive tab to view this retained record."
    )
    assert active_tracker_records(load_application_tracker(root)) == []
    entries = list_archive_entries(archives)
    assert len(entries) == 1
    assert entries[0]["final_status"] == "Withdrawn / Closed"
    assert entries[0]["original_role_id"] == record["id"]


def test_archive_view_keeps_existing_folder_control():
    source = inspect.getsource(app._render_archive)

    assert "Open Folder" in source
    assert "Reopen as New Prospect" in source
