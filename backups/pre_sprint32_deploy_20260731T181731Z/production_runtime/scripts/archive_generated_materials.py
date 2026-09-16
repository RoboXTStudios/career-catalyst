"""Safely archive older duplicate Career Catalyst generated materials."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from .generate_dashboard import load_application_packages
except ImportError:
    from generate_dashboard import load_application_packages


PathInput = Union[str, Path]


def plan_generated_material_archive(
    project_root: PathInput = Path.cwd(),
    archive_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Plan duplicate moves while keeping the newest role/material match active."""
    root = Path(project_root).resolve()
    dated_root = root / "exports" / "archive" / (
        archive_date or date.today()
    ).isoformat()
    package_data = load_application_packages(root)
    candidates: List[Dict[str, Any]] = []
    kept: List[Dict[str, Any]] = []
    for package in package_data["packages"]:
        tracker_id = str(package.get("tracker_id") or "")
        for label, current_path in package.get("files", {}).items():
            current = Path(current_path)
            if current.exists() and label != "Job Description":
                kept.append(
                    {
                        "tracker_id": tracker_id,
                        "company": package.get("company"),
                        "title": package.get("role"),
                        "material_type": label,
                        "current_path": str(current.relative_to(root)),
                    }
                )
        for candidate in package.get("archive_candidates", []):
            original = Path(candidate["path"])
            current = Path(candidate["current_path"])
            relative_original = original.relative_to(root)
            destination = dated_root / relative_original
            candidates.append(
                {
                    "tracker_id": tracker_id,
                    "company": package.get("company"),
                    "title": package.get("role"),
                    "material_type": candidate["material_type"],
                    "original_path": str(relative_original),
                    "archive_path": str(destination.relative_to(root)),
                    "reason": candidate["reason"],
                    "current_file_kept": str(current.relative_to(root)),
                }
            )
    candidates.sort(
        key=lambda item: (
            item["tracker_id"],
            item["material_type"],
            item["original_path"],
        )
    )
    kept.sort(
        key=lambda item: (
            item["tracker_id"],
            item["material_type"],
            item["current_path"],
        )
    )
    return {
        "project_root": str(root),
        "archive_root": str(dated_root),
        "candidates": candidates,
        "kept": kept,
        "candidate_count": len(candidates),
        "kept_count": len(kept),
    }


def apply_generated_material_archive(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Move planned candidates into a dated archive and write a restore manifest."""
    root = Path(plan["project_root"])
    archive_root = Path(plan["archive_root"])
    archived: List[Dict[str, Any]] = []
    planned_moves = [
        (
            candidate,
            root / candidate["original_path"],
            root / candidate["archive_path"],
        )
        for candidate in plan["candidates"]
        if (root / candidate["original_path"]).is_file()
    ]
    conflicts = [destination for _, _, destination in planned_moves if destination.exists()]
    if conflicts:
        raise FileExistsError(
            "Archive destination already exists; no files were moved: "
            + ", ".join(str(path) for path in conflicts)
        )
    for candidate, source, destination in planned_moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        archived.append(dict(candidate))

    manifest_path: Optional[Path] = None
    if archived:
        archive_root.mkdir(parents=True, exist_ok=True)
        manifest_path = archive_root / "archive_manifest.json"
        manifest = {
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "archive_root": str(archive_root.relative_to(root)),
            "archived": archived,
            "kept_current": plan["kept"],
            "restore_hint": (
                "To restore an archived file, move it from archive_path back to "
                "original_path as listed in this manifest."
            ),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return {
        **plan,
        "archived": archived,
        "archived_count": len(archived),
        "manifest_path": str(manifest_path) if manifest_path else None,
    }


def archive_generated_materials(
    project_root: PathInput = Path.cwd(),
    apply: bool = False,
    archive_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Dry-run by default; move files only when apply=True is explicit."""
    plan = plan_generated_material_archive(project_root, archive_date)
    if not apply:
        return {**plan, "archived": [], "archived_count": 0, "manifest_path": None}
    return apply_generated_material_archive(plan)


def _print_summary(result: Dict[str, Any], apply: bool) -> None:
    mode = "APPLY" if apply else "DRY RUN"
    print(f"Generated materials archive — {mode}")
    for candidate in result["candidates"]:
        print(
            f"ARCHIVE {candidate['original_path']} -> {candidate['archive_path']} "
            f"({candidate['reason']} Current: {candidate['current_file_kept']})"
        )
    for kept in result["kept"]:
        print(f"KEEP {kept['current_path']} ({kept['material_type']})")
    print(
        f"Summary: {result['candidate_count']} archive candidates; "
        f"{result['kept_count']} current files kept; "
        f"{result.get('archived_count', 0)} files moved."
    )
    if result.get("manifest_path"):
        print(f"Manifest: {result['manifest_path']}")
        print(
            "Restore: move a file from archive_path back to original_path as listed "
            "in the manifest."
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Archive older duplicate generated materials without deleting them."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="List planned moves only (default)."
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Move planned duplicates and write a manifest.",
    )
    parser.add_argument("--project-root", default=str(Path.cwd()))
    args = parser.parse_args(argv)
    result = archive_generated_materials(args.project_root, apply=args.apply)
    _print_summary(result, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
