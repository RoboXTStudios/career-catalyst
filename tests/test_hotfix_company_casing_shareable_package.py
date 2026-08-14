from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.filename_utils import build_upload_filename, company_display_name
from scripts.materials_library import (
    copy_role_package_for_sharing,
    organize_package_outputs,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_company_display_preserves_only_approved_acronym_casing():
    assert company_display_name("AXS") == "AXS"
    assert company_display_name("Axs") == "AXS"
    assert company_display_name("axs") == "AXS"
    assert company_display_name("Ordinary Company") == "Ordinary Company"
    assert company_display_name("Cascade") == "Cascade"
    assert company_display_name("OMG23") == "OMG23 (Omnicom Media Group)"


def test_axs_filename_slug_remains_lowercase():
    filename = build_upload_filename(
        "Trisha Lynch",
        "Senior Manager, Product Marketing",
        "AXS",
        "ATS Resume",
        "docx",
    )
    assert filename == "axs_senior_manager_product_marketing_trisha_lynch_ats_resume.docx"


def test_share_copy_is_manifest_owned_atomic_and_read_only(tmp_path: Path):
    runtime = tmp_path / "runtime"
    export_root = tmp_path / "canonical_exports"
    share_root = tmp_path / "Downloads" / "Career Catalyst"
    tracker = runtime / "data" / "application_tracker.yml"
    tracker.parent.mkdir(parents=True)
    tracker.write_text("applications:\n  - id: axs_role\n", encoding="utf-8")
    application = {
        "id": "axs_role",
        "company": "AXS",
        "role": "Senior Manager, Product Marketing",
        "status": "Considered",
    }
    generated = tmp_path / "generated"
    generated.mkdir()
    ats = generated / "ats.docx"
    cover = generated / "cover.docx"
    summary = generated / "summary.txt"
    ats.write_bytes(b"ats-v1")
    cover.write_bytes(b"cover-v1")
    summary.write_text("summary-v1", encoding="utf-8")
    organized = organize_package_outputs(
        runtime,
        application,
        {
            "ats_docx": str(ats),
            "cover_letter_docx": str(cover),
            "package_summary_text": str(summary),
        },
        export_root=export_root,
    )
    manifest_path = Path(organized["manifest"]["manifest_path"])
    canonical_files = [
        path
        for path in manifest_path.parent.iterdir()
        if path.is_file()
    ]
    canonical_hashes = {path.name: _sha256(path) for path in canonical_files}
    assert organized["manifest"]["company"] == "AXS"
    tracker_before = tracker.read_bytes()

    first = copy_role_package_for_sharing(
        runtime,
        application,
        destination_root=share_root,
        export_root=export_root,
    )
    destination = Path(first["destination_folder"])
    assert destination == share_root / "axs_role"
    assert {path.name for path in destination.iterdir()} == set(canonical_hashes)
    assert {_sha256(path) for path in destination.iterdir()} == set(canonical_hashes.values())

    stale = destination / "stale.txt"
    stale.write_text("old share copy", encoding="utf-8")
    second = copy_role_package_for_sharing(
        runtime,
        application,
        destination_root=share_root,
        export_root=export_root,
    )
    assert second["destination_folder"] == first["destination_folder"]
    assert not stale.exists()
    assert sorted(path.name for path in share_root.iterdir()) == ["axs_role"]
    assert tracker.read_bytes() == tracker_before
    assert {
        path.name: _sha256(path)
        for path in canonical_files
    } == canonical_hashes
    copied_manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert copied_manifest["prospect_id"] == "axs_role"
    assert copied_manifest["files"] == organized["manifest"]["files"]


def test_share_copy_rejects_manifest_for_another_role(tmp_path: Path):
    runtime = tmp_path / "runtime"
    export_root = tmp_path / "exports"
    folder = export_root / "active" / "in_progress" / "axs_role"
    folder.mkdir(parents=True)
    artifact = folder / "axs_resume.docx"
    artifact.write_bytes(b"resume")
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "prospect_id": "different_role",
                "slug": "axs_role",
                "files": {"ats_docx": str(artifact)},
            }
        ),
        encoding="utf-8",
    )
    try:
        copy_role_package_for_sharing(
            runtime,
            {"id": "axs_role", "status": "Considered"},
            destination_root=tmp_path / "share",
            export_root=export_root,
        )
    except ValueError as error:
        assert "No exact canonical package" in str(error)
    else:
        raise AssertionError("a package owned by another role must not be copied")
