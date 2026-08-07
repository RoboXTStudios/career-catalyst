from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from scripts.application_tracker import load_application_tracker, save_application_tracker
from scripts.materials_library import find_exact_role_package, write_role_manifest
from scripts.package_generator import _duplicate_posting_conflicts
from scripts.role_archive import archive_role, list_archive_entries


def _record(tracker_id: str, status: str, *, company: str = "Live Nation Worldwide") -> dict:
    return {
        "id": tracker_id,
        "company": company,
        "role": "LN Media & Sponsorship || Future Freelance Opportunities: Live Event Experiential Producers",
        "status": status,
        "priority": "Medium",
        "show_on_dashboard": True,
        "job_file": f"jobs/{tracker_id}.md",
        "job_id": "987654",
        "source_url": "https://boards.greenhouse.io/livenation/jobs/987654",
        "application_history": [{"event": "created", "date": "2026-08-01"}],
        "evidence_project_ids": ["enterprise_media_operations_transformation"],
        "match_score": 62,
        "notes": "Preserve this history.",
    }


def _runtime(tmp_path: Path, records: list[dict]) -> tuple[Path, Path, Path]:
    root = tmp_path / "runtime"
    exports = tmp_path / "exports"
    archives = tmp_path / "archive"
    (root / "data").mkdir(parents=True)
    (root / "jobs").mkdir(parents=True)
    save_application_tracker(records, root)
    for record in records:
        (root / record["job_file"]).write_text(
            "# Live Event Experiential Producers\n\n"
            "Produce live event experiences and coordinate partners.\n",
            encoding="utf-8",
        )
    return root, exports, archives


def _package(exports: Path, record: dict) -> Path:
    folder = exports / "active" / "in_progress" / record["id"]
    folder.mkdir(parents=True)
    material = folder / "ats_resume.docx"
    material.write_bytes(b"historical package")
    write_role_manifest(folder, record, {"ATS Resume": str(material)}, archived=False)
    return folder


def test_partial_terminal_archive_reconciles_and_repeats_safely(tmp_path: Path):
    record = _record("old_role_id", "Withdrawn / Closed")
    root, exports, archives = _runtime(tmp_path, [record])
    package = _package(exports, record)
    partial = archives / "live-nation-worldwide" / (
        "2026-08-07_ln-media-sponsorship-future-freelance-opportunities-live-event-"
        "experiential-producers-old-role-id"
    )
    partial.mkdir(parents=True)
    (partial / "notes_and_status_history.txt").write_text("partial archive", encoding="utf-8")

    first = archive_role(
        record["id"],
        "Withdrawn / Closed",
        root,
        export_root=exports,
        archive_root=archives,
        archived_at="2026-08-07T10:00:00+00:00",
    )
    assert first.get("skipped") is not True
    assert not load_application_tracker(root)
    entries = list_archive_entries(archives)
    assert len(entries) == 1
    assert entries[0]["original_role_id"] == record["id"]
    bundle = Path(first["folder"])
    assert (bundle / "role_manifest.json").is_file()
    assert (bundle / "materials" / "ats_resume.docx").read_bytes() == b"historical package"
    assert not package.exists()

    second = archive_role(
        record["id"],
        "Withdrawn / Closed",
        root,
        export_root=exports,
        archive_root=archives,
    )
    assert second["skipped"] is True
    assert len(list_archive_entries(archives)) == 1


def test_terminal_same_posting_is_history_not_reopened_material_conflict(tmp_path: Path):
    old = _record("old_role_id", "Withdrawn / Closed")
    new = _record("new_role_id", "Prospect")
    root, exports, _archives = _runtime(tmp_path, [old, new])
    old_package = _package(exports, old)

    assert _duplicate_posting_conflicts(new, [old, new]) == []
    found_new = find_exact_role_package(root, new, export_root=exports)
    assert found_new["folder"] is None
    found_old = find_exact_role_package(root, old, export_root=exports)
    assert found_old["folder"] == old_package
    assert (old_package / "ats_resume.docx").read_bytes() == b"historical package"

    active_duplicate = deepcopy(old)
    active_duplicate["id"] = "active_duplicate_id"
    active_duplicate["status"] = "Prospect"
    assert _duplicate_posting_conflicts(new, [new, active_duplicate])


def test_reopened_live_nation_identity_remains_unchanged_and_unowned(tmp_path: Path):
    old_id = "live_nation_worldwide_ln_media_amp_sponsorship_future_freelance_opportunities_live_event_experiential_producers"
    new_id = old_id + "_reopened_20260807"
    old = _record(old_id, "Withdrawn / Closed")
    reopened = _record(new_id, "Prospect")
    root, exports, _archives = _runtime(tmp_path, [old, reopened])
    old_package = _package(exports, old)
    before = deepcopy(reopened)

    assert _duplicate_posting_conflicts(reopened, [old, reopened]) == []
    assert find_exact_role_package(root, reopened, export_root=exports)["folder"] is None
    assert find_exact_role_package(root, old, export_root=exports)["folder"] == old_package
    current = next(item for item in load_application_tracker(root) if item["id"] == new_id)
    assert current == before
    assert (old_package / "ats_resume.docx").is_file()
