"""Canonical, durable resolution of tracker role state.

The active worktree is code, not the source of truth for runtime data.  This
module keeps identity and path resolution in one place so every workflow can
use the configured runtime root without guessing from a filename.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import re

try:
    from .parse_job import JobParseError, parse_job_description
except ImportError:  # pragma: no cover
    from parse_job import JobParseError, parse_job_description


_IDENTITY_KEYS = ("prospect_id", "id", "stable_slug", "record_id")
_EXTERNAL_KEYS = ("external_job_id", "job_id", "greenhouse_job_id", "requisition_id")
_URL_KEYS = ("canonical_apply_url", "official_url", "source_url", "original_source_url", "posting_url")


def tracker_records(tracker: Any) -> List[Dict[str, Any]]:
    records = tracker.get("applications", []) if isinstance(tracker, dict) else tracker
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def resolve_tracker_record(prospect_id: str, tracker: Any) -> Dict[str, Any]:
    """Resolve exactly one record by stable identity; never by company or role."""
    target = str(prospect_id or "").strip()
    matches = [
        record for record in tracker_records(tracker)
        if target and target in {str(record.get(key) or "").strip() for key in _IDENTITY_KEYS}
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one exact tracker record for '{target}'; found {len(matches)}.")
    return dict(matches[0])


def selected_evidence_ids(record: Dict[str, Any]) -> List[str]:
    """Read the one canonical tracker Evidence field with legacy read aliases.

    ``evidence_project_ids`` is authoritative whenever it is present, including
    when it is an intentionally empty list.  Historical aliases are accepted
    only for older records that do not contain the canonical field; package
    manifests and Streamlit session state are never consulted here.
    """
    if "evidence_project_ids" in record:
        raw_values = record.get("evidence_project_ids")
    elif "selected_evidence_ids" in record:
        raw_values = record.get("selected_evidence_ids")
    else:
        raw_values = record.get("selected_evidence")
    if isinstance(raw_values, dict):
        raw_values = raw_values.get("ids") or raw_values.get("selected_ids") or []
    values = raw_values if isinstance(raw_values, (list, tuple, set)) else []
    resolved: List[str] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("id")
        clean = str(value or "").strip()
        if clean and clean not in resolved:
            resolved.append(clean)
    return resolved


def resolve_selected_evidence(
    record: Dict[str, Any], projects: Iterable[Dict[str, Any]]
) -> Dict[str, Any]:
    """Resolve tracker-selected Evidence without allowing stale state to win."""
    selected_ids = selected_evidence_ids(record)
    by_id: Dict[str, Dict[str, Any]] = {}
    for project in projects:
        if not isinstance(project, dict):
            continue
        project_id = str(project.get("id") or "").strip()
        if not project_id:
            continue
        by_id.setdefault(project_id, project)
        for legacy_id in project.get("legacy_ids") or []:
            alias = str(legacy_id or "").strip()
            if alias:
                by_id.setdefault(alias, project)
    missing_ids = [project_id for project_id in selected_ids if project_id not in by_id]
    resolved_projects: List[Dict[str, Any]] = []
    resolved_project_ids: set[str] = set()
    for selected_id in selected_ids:
        project = by_id.get(selected_id)
        canonical_id = str((project or {}).get("id") or "").strip()
        if project and canonical_id not in resolved_project_ids:
            resolved_projects.append(project)
            resolved_project_ids.add(canonical_id)
    return {
        "selected_ids": selected_ids,
        "projects": resolved_projects,
        "missing_ids": missing_ids,
    }


def _normal(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _external_ids(record: Dict[str, Any]) -> set[str]:
    values = {str(record.get(key) or "").strip() for key in _EXTERNAL_KEYS}
    values.update(re.findall(r"/(?:jobs?/|requisitions?/)([A-Za-z0-9_-]{3,})", " ".join(str(record.get(key) or "") for key in _URL_KEYS), re.I))
    return {value for value in values if value}


def _urls(record: Dict[str, Any]) -> set[str]:
    return {str(record.get(key) or "").strip().rstrip("/").lower() for key in _URL_KEYS if str(record.get(key) or "").strip()}


def _job_candidates(root: Path) -> Iterable[Path]:
    jobs = root / "jobs"
    if not jobs.is_dir():
        return ()
    return (path for path in sorted(jobs.iterdir()) if path.is_file() and path.suffix.lower() in {".md", ".txt"} and path.name.lower() != "readme.md")


def _parse(path: Path) -> Optional[Dict[str, Any]]:
    try:
        parsed = parse_job_description(path)
        if len(str(parsed.get("raw_text") or "").strip()) < 80:
            return None
        return parsed
    except (OSError, JobParseError, ValueError, TypeError):
        return None


def resolve_job_file(application: Dict[str, Any], project_root: Path | str) -> Dict[str, Any]:
    """Resolve a posting beneath ``project_root/jobs`` without unsafe guessing."""
    root = Path(project_root).expanduser().resolve()
    jobs_root = (root / "jobs").resolve()
    def relative(path: Path) -> str:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)
    stored = str(application.get("job_file") or "").strip()
    explicit_material_job = False
    if not stored:
        for label, value in dict(application.get("material_paths") or {}).items():
            if str(label).strip().lower().replace("_", " ") in {"job description", "job file"} and value:
                stored = str(value).strip()
                explicit_material_job = True
                break
    candidates: List[Path] = []
    if stored:
        raw = Path(stored).expanduser()
        if not raw.is_absolute():
            raw = root / raw
        try:
            resolved = raw.resolve()
            if resolved.is_file():
                parsed = _parse(resolved)
                embedded = str((parsed or {}).get("raw_text") or "").lower()
                tracker_id = str(application.get("id") or application.get("prospect_id") or "").strip().lower()
                if (resolved == jobs_root or jobs_root in resolved.parents or explicit_material_job or (tracker_id and tracker_id in embedded)):
                    candidates.append(resolved)
        except OSError:
            pass
    parsed_candidates = [(path, _parse(path)) for path in _job_candidates(root)]
    parsed_candidates = [(path, parsed) for path, parsed in parsed_candidates if parsed]
    if candidates:
        parsed = _parse(candidates[0])
        if parsed:
            return {"status": "valid", "path": str(candidates[0]), "relative_path": relative(candidates[0]), "parsed": parsed, "relinked": False}
    tracker_id = str(application.get("id") or application.get("prospect_id") or "").strip()
    by_id = [(path, parsed) for path, parsed in parsed_candidates if tracker_id and tracker_id.lower() in str(parsed.get("raw_text") or "").lower()]
    if len(by_id) == 1:
        path, parsed = by_id[0]
        return {"status": "valid", "path": str(path), "relative_path": relative(path), "parsed": parsed, "relinked": bool(stored)}
    if len(by_id) > 1:
        return {"status": "ambiguous", "candidates": [str(path) for path, _ in by_id], "reason": "multiple job files contain the same tracker identity"}
    ids = _external_ids(application)
    urls = _urls(application)
    by_external = []
    for path, parsed in parsed_candidates:
        parsed_ids = _external_ids(parsed)
        parsed_urls = _urls(parsed)
        if (ids and ids.intersection(parsed_ids)) or (urls and urls.intersection(parsed_urls)):
            by_external.append((path, parsed))
    if len(by_external) == 1:
        path, parsed = by_external[0]
        return {"status": "valid", "path": str(path), "relative_path": relative(path), "parsed": parsed, "relinked": bool(stored)}
    if len(by_external) > 1:
        return {"status": "ambiguous", "candidates": [str(path) for path, _ in by_external], "reason": "multiple job files match the posting identity"}
    company = _normal(application.get("company"))
    role = _normal(application.get("role") or application.get("job_title"))
    by_title = [(path, parsed) for path, parsed in parsed_candidates if _normal(parsed.get("company")) == company and _normal(parsed.get("job_title")) == role and company and role]
    if len(by_title) == 1:
        path, parsed = by_title[0]
        return {"status": "valid", "path": str(path), "relative_path": relative(path), "parsed": parsed, "relinked": bool(stored)}
    if len(by_title) > 1:
        return {"status": "ambiguous", "candidates": [str(path) for path, _ in by_title], "reason": "multiple postings share the same company and role"}
    return {"status": "missing", "path": str(Path(stored).expanduser()) if stored else "", "recoverable": bool(_urls(application)), "reason": "no usable posting file matched the stable role identity"}


def resolve_role_state(prospect_id: str, tracker: Any, project_root: Path | str) -> Dict[str, Any]:
    record = resolve_tracker_record(prospect_id, tracker)
    return {"record": record, "job": resolve_job_file(record, project_root), "evidence_project_ids": selected_evidence_ids(record)}
