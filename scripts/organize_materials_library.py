"""Safely migrate exact packages and generated Markdown into the materials library."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

try:
    from .application_tracker import load_application_tracker, update_prospect
    from .materials_library import (
        LEGACY_MARKDOWN_DIRS,
        archive_legacy_markdown,
        archive_matching_legacy_text,
        material_route,
        organize_exact_material_paths,
    )
except ImportError:
    from application_tracker import load_application_tracker, update_prospect
    from materials_library import (
        LEGACY_MARKDOWN_DIRS,
        archive_legacy_markdown,
        archive_matching_legacy_text,
        material_route,
        organize_exact_material_paths,
    )


def organize_materials_library(project_root: Path, *, apply: bool = False) -> Dict[str, Any]:
    """Organize tracker-owned packages and archive legacy Markdown with a report."""
    root = Path(project_root).resolve()
    applications = load_application_tracker(root)
    exact_candidates = [
        record for record in applications if record.get("material_paths")
    ]
    ambiguous = [
        str(record.get("id") or "")
        for record in exact_candidates
        if material_route(record.get("status"))["needs_review"]
    ]
    migrated = []
    if apply:
        for application in exact_candidates:
            result = organize_exact_material_paths(root, application)
            manifest = result.get("manifest")
            if not manifest:
                continue
            update_prospect(
                str(application["id"]),
                {
                    "material_paths": dict(manifest.get("materials") or {}),
                    "package_manifest": manifest,
                },
                root,
            )
            migrated.append(
                {
                    "prospect_id": str(application["id"]),
                    "moved_count": result["moved_count"],
                    "manifest_path": manifest["manifest_path"],
                    "archived": manifest["archived"],
                }
            )
    markdown = archive_legacy_markdown(root, apply=apply)
    matching_text = archive_matching_legacy_text(root, apply=apply)
    archive_root = root / "exports/archive/old_generated_materials"
    archived_markdown_total = sum(1 for path in archive_root.rglob("*.md") if path.is_file())
    archived_text_total = sum(1 for path in archive_root.rglob("*.txt") if path.is_file())
    legacy_report_dirs = (*LEGACY_MARKDOWN_DIRS, "exports/docx", "exports/pdf", "exports/interview")
    legacy_files_remaining = sum(
        1
        for relative in legacy_report_dirs
        for path in (root / relative).glob("*")
        if path.is_file()
    )
    report = {
        "applied": apply,
        "exact_role_candidates": len(exact_candidates),
        "role_folders_created": len(migrated),
        "active_role_folders": sum(not item["archived"] for item in migrated),
        "archived_role_folders": sum(item["archived"] for item in migrated),
        "legacy_markdown_planned": markdown["planned_count"],
        "legacy_markdown_moved": markdown["moved_count"],
        "txt_companions_created": markdown["txt_companions_created"],
        "legacy_text_moved": matching_text["moved_count"],
        "archived_markdown_total": archived_markdown_total,
        "archived_text_total": archived_text_total,
        "legacy_files_remaining": legacy_files_remaining,
        "ambiguous_roles_left_as_is": ambiguous,
        "files_left_as_is": legacy_files_remaining
        + max(0, len(exact_candidates) - len(migrated)),
        "migrated": migrated,
    }
    if apply:
        report_path = root / "exports/archive/material_cleanup_report.txt"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        lines = (
            "Career Catalyst Material Cleanup Report",
            "",
            f"Active role folders: {report['active_role_folders']}",
            f"Archived role folders: {report['archived_role_folders']}",
            f"Legacy Markdown files archived (total): {report['archived_markdown_total']}",
            f"Legacy TXT files archived (total): {report['archived_text_total']}",
            f"Legacy files retained for review: {report['legacy_files_remaining']}",
            f"Files/roles left as-is: {report['files_left_as_is']}",
            f"Warnings / needs review: {', '.join(ambiguous) if ambiguous else 'None'}",
        )
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report["report_path"] = str(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = organize_materials_library(Path(args.project_root), apply=args.apply)
    print(
        f"exact roles={result['exact_role_candidates']} "
        f"markdown planned={result['legacy_markdown_planned']} "
        f"moved={result['legacy_markdown_moved']} "
        f"applied={result['applied']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
