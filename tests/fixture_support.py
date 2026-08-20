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
