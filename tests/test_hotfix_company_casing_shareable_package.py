from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.filename_utils import (
    build_upload_filename,
    canonicalize_employer_mentions,
    company_display_name,
)
from scripts.generate_cover_letter import save_material
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
    assert company_display_name("OMG23") == "OMG23 / OMD Entertainment, Omnicom Media Group"


def test_candidate_employer_boundary_repairs_only_the_current_known_employer():
    source = (
        "Dear Axs Hiring Team,\n\n"
        "I would bring Axs grounded product thinking. "
        "Netflix and Paramount are market examples, while short words stay as written."
    )

    repaired = canonicalize_employer_mentions(source, "AXS")

    assert "Dear AXS Hiring Team," in repaired
    assert "I would bring AXS" in repaired
    assert "Axs" not in repaired
    assert "Netflix and Paramount" in repaired
    assert "short words stay as written" in repaired


def test_known_employer_mappings_remain_stable_in_candidate_prose():
    assert canonicalize_employer_mentions("Gitlab role", "GitLab") == "GitLab role"
    assert canonicalize_employer_mentions(
        "OMD Entertainment role", "OMG23 / OMD Entertainment, Omnicom Media Group"
    ) == "OMG23 / OMD Entertainment, Omnicom Media Group role"
    assert canonicalize_employer_mentions("netflix role", "Netflix") == "netflix role"


def test_saved_cover_letter_canonicalizes_greeting_and_body_after_repair(tmp_path: Path):
    context = {
        "root": tmp_path,
        "parsed_job": {
            "job_title": "Sr. Manager, Product Marketing",
            "company": "AXS",
            "raw_text": "Lead product marketing and cross-functional launch planning at AXS.",
        },
        "career_data": {
            "data": {"personal_brand": {"candidate": {"name": "Trisha Lynch"}}}
        },
        "match_report": {"match_score": 80},
        "voice": {"avoid": []},
        "writing_voice": {"banned_phrases": []},
        "material_editing_plan": {"banned_phrases": []},
    }

    result = save_material(
        context,
        "Cover_Letter",
        "Too short.",
        minimum_words=12,
        maximum_words=80,
        repair_content=lambda _content, _context: (
            "Dear Axs Hiring Team,\n\n"
            "I would bring Axs grounded product thinking, clear priorities, and dependable "
            "cross-functional execution for this role."
        ),
    )
    saved = Path(result["output_path"]).read_text(encoding="utf-8")

    assert "Dear AXS Hiring Team," in saved
    assert "I would bring AXS" in saved
    assert "Axs" not in saved


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
