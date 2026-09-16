"""Dry-run first cleanup for generated Career Catalyst material clutter."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

try:
    from .application_tracker import load_application_tracker, normalize_status
    from .materials_library import material_route, role_slug
except ImportError:  # pragma: no cover - direct script usage
    from application_tracker import load_application_tracker, normalize_status
    from materials_library import material_route, role_slug

PathInput = Union[str, Path]
ACTIVE_ROOTS = ("exports/active",)
ARCHIVE_ROOT = "exports/archive/inactive"
PRESERVED_EXTENSIONS = {".docx", ".txt", ".json"}
ACTIVE_STATUSES = {"Active", "Drafted", "Reviewed", "Paused", "Applied", "Follow-up", "Interviewing"}
INACTIVE_STATUSES = {"Pass", "Rejected", "Invalid", "Invalid/Hidden", "Archived", "Closed", "No Longer Pursuing"}


def _relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root))


def _issue(action: str, path: Path, reason: str, *, destination: Optional[Path] = None) -> Dict[str, str]:
    item = {"action": action, "path": str(path), "reason": reason}
    if destination is not None:
        item["destination"] = str(destination)
    return item


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _tracker_by_slug(project_root: Path) -> Dict[str, Dict[str, Any]]:
    try:
        records = load_application_tracker(project_root)
    except Exception:
        records = []
    return {role_slug(record): record for record in records if role_slug(record)}


def _is_package_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    return (path / "manifest.json").is_file() or any(path.glob("*.docx")) or any(path.glob("*.txt"))


def _base_duplicate_stem(path: Path) -> Optional[str]:
    match = re.match(r"^(?P<base>.+)_(?P<index>[2-9][0-9]*)$", path.stem)
    return match.group("base") if match else None


def plan_materials_cleanup(project_root: PathInput = Path.cwd()) -> Dict[str, Any]:
    """Return cleanup actions without changing files."""
    root = Path(project_root).resolve()
    exports = root / "exports"
    tracker = _tracker_by_slug(root)
    issues: List[Dict[str, str]] = []
    preserved: List[Dict[str, str]] = []

    if not exports.exists():
        return {"project_root": str(root), "issues": [], "preserved": [], "issue_count": 0}

    for path in sorted(exports.rglob("*")):
        if not path.is_file():
            continue
        rel = _relative(root, path)
        if path.name.startswith("~$") and path.suffix.lower() == ".docx":
            issues.append(_issue("delete", Path(rel), "Microsoft Word temporary file"))
            continue
        if path.suffix.lower() == ".md":
            txt = path.with_suffix(".txt")
            docx = path.with_suffix(".docx")
            if txt.exists() or docx.exists():
                issues.append(_issue("delete", Path(rel), "Markdown remnant with equivalent txt/docx material"))
            continue
        base = _base_duplicate_stem(path)
        if base and (path.with_name(base + path.suffix)).exists():
            issues.append(_issue("delete", Path(rel), "Duplicate generated package file with numeric suffix"))

    for active_root in ACTIVE_ROOTS:
        active_dir = root / active_root
        if not active_dir.is_dir():
            continue
        for folder in sorted(active_dir.glob("*/*")):
            if not _is_package_dir(folder):
                continue
            slug = folder.name
            base_slug = re.sub(r"_[2-9][0-9]*$", "", slug)
            record = tracker.get(base_slug) or tracker.get(slug)
            status = normalize_status(record.get("status")) if record else ""
            if status in INACTIVE_STATUSES or (record and material_route(status)["archived"]):
                destination = root / ARCHIVE_ROOT / base_slug
                issues.append(_issue("move", Path(_relative(root, folder)), f"Inactive tracker status: {status}", destination=Path(_relative(root, _unique_destination(destination)))))
            elif record and status in ACTIVE_STATUSES:
                for material in sorted(folder.iterdir()):
                    if material.is_file() and material.suffix.lower() in PRESERVED_EXTENSIONS and not material.name.startswith("~$"):
                        preserved.append({"path": _relative(root, material), "reason": f"Preserved active/applied material ({status})"})
            if base_slug != slug and (folder.parent / base_slug).exists():
                destination = root / "exports/archive/old_generated_materials" / slug
                issues.append(_issue("move", Path(_relative(root, folder)), "Duplicate package folder with numeric suffix", destination=Path(_relative(root, _unique_destination(destination)))))

    for directory in sorted([p for p in exports.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
        try:
            if not any(directory.iterdir()):
                issues.append(_issue("rmdir", Path(_relative(root, directory)), "Empty generated-material directory"))
        except OSError:
            continue

    return {"project_root": str(root), "issues": issues, "preserved": preserved, "issue_count": len(issues), "preserved_count": len(preserved)}


def apply_materials_cleanup(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a previously generated cleanup plan."""
    root = Path(plan["project_root"])
    applied: List[Dict[str, str]] = []
    for issue in plan.get("issues", []):
        source = root / issue["path"]
        action = issue["action"]
        if action == "delete" and source.is_file():
            source.unlink()
            applied.append(issue)
        elif action == "move" and source.exists():
            destination = root / issue["destination"]
            destination = _unique_destination(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            done = dict(issue)
            done["destination"] = _relative(root, destination)
            applied.append(done)
        elif action == "rmdir" and source.is_dir():
            try:
                source.rmdir()
                applied.append(issue)
            except OSError:
                pass
    manifest = None
    if applied:
        archive = root / "exports/archive/cleanup_reports"
        archive.mkdir(parents=True, exist_ok=True)
        manifest = archive / f"cleanup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        manifest.write_text(json.dumps({**plan, "applied": applied}, indent=2) + "\n", encoding="utf-8")
    return {**plan, "applied": applied, "applied_count": len(applied), "manifest_path": str(manifest) if manifest else None}


def cleanup_materials(project_root: PathInput = Path.cwd(), *, apply: bool = False) -> Dict[str, Any]:
    plan = plan_materials_cleanup(project_root)
    return apply_materials_cleanup(plan) if apply else {**plan, "applied": [], "applied_count": 0, "manifest_path": None}


def _print_report(result: Dict[str, Any], apply: bool) -> None:
    print(f"Generated materials cleanup — {'APPLY' if apply else 'DRY RUN'}")
    for issue in result["issues"]:
        dest = f" -> {issue['destination']}" if issue.get("destination") else ""
        print(f"{issue['action'].upper()} {issue['path']}{dest} ({issue['reason']})")
    for item in result.get("preserved", []):
        print(f"KEEP {item['path']} ({item['reason']})")
    print(f"Summary: {result['issue_count']} issues; {result.get('applied_count', 0)} applied; {result.get('preserved_count', 0)} preserved.")
    if result.get("manifest_path"):
        print(f"Cleanup report: {result['manifest_path']}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Report or clean generated material clutter. Defaults to dry-run.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Report only (default).")
    mode.add_argument("--apply", action="store_true", help="Apply reported deletes/moves and write cleanup report.")
    parser.add_argument("--project-root", default=str(Path.cwd()))
    args = parser.parse_args(argv)
    result = cleanup_materials(args.project_root, apply=args.apply)
    _print_report(result, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
