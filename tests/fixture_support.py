from __future__ import annotations

from pathlib import Path

import yaml


def replace_evidence_projects(path: Path, projects: list[dict]) -> None:
    """Replace fixture parents without orphaning the canonical atomic layer."""
    existing = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    existing = existing if isinstance(existing, dict) else {}
    old_parent_ids = {
        str(item.get("id") or "")
        for item in existing.get("evidence_projects", [])
        if isinstance(item, dict)
    }
    new_parent_ids = {
        str(item.get("id") or "") for item in projects if isinstance(item, dict)
    }
    atomic = [
        item
        for item in existing.get("atomic_evidence", [])
        if str(item.get("parent_id") or "") not in old_parent_ids
        or str(item.get("parent_id") or "") in new_parent_ids
    ]
    payload = {"evidence_projects": projects}
    if "atomic_evidence" in existing:
        payload["atomic_evidence"] = atomic
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def with_confirmed_role_family(record: dict, root: Path) -> dict:
    """Record the person's confirmation of the posting's inferred role family.

    Package generation waits for this when the family came from fallback
    inference; fixtures that exercise generation confirm it the way a user would.
    """
    from scripts.dynamic_role_intelligence import classify_role_family
    from scripts.parse_job import parse_job_description

    job_path = Path(str(record["job_file"])).expanduser()
    if not job_path.is_absolute():
        job_path = Path(root) / job_path
    parsed = parse_job_description(job_path)
    family = classify_role_family(
        str(record.get("role") or parsed.get("job_title") or ""),
        str(parsed.get("raw_text") or ""),
    )["role_family"]
    record["role_family_confirmation"] = {"role_family": family}
    return record


def confirm_tracker_role_family(tracker_id: str, root: Path) -> None:
    """Persist a role-family confirmation on one isolated-runtime tracker record."""
    from scripts.application_tracker import load_application_tracker, update_prospect

    record = next(
        item for item in load_application_tracker(root) if item.get("id") == tracker_id
    )
    confirmation = with_confirmed_role_family(dict(record), root)["role_family_confirmation"]
    update_prospect(tracker_id, {"role_family_confirmation": confirmation}, root)
