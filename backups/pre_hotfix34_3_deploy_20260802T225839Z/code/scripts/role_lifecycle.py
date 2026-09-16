"""Canonical Career Catalyst role lifecycle and legacy normalization."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Callable, Iterable, Mapping


LIVE_STATUSES = (
    "Prospect",
    "Considered",
    "Applied",
    "Under Consideration",
    "Interviewing",
    "Offer",
    "Rejected",
    "Withdrawn / Closed",
)
PRE_APPLICATION_STATUSES = frozenset({"Prospect", "Considered"})
POST_APPLICATION_STATUSES = frozenset(
    {"Applied", "Under Consideration", "Interviewing", "Offer"}
)
TERMINAL_STATUSES = frozenset({"Rejected", "Withdrawn / Closed"})
ARCHIVE_ELIGIBLE_STATUSES = TERMINAL_STATUSES
DASHBOARD_STATUS_ORDER = LIVE_STATUSES
STATUS_LABELS = {status: status for status in LIVE_STATUSES}

# These values are accepted only as legacy input. They are never offered by UI controls.
LEGACY_STATUS_ALIASES = {
    "active": "Prospect",
    "draft": "Prospect",
    "drafted": "Prospect",
    "in progress": "Prospect",
    "open": "Prospect",
    "reviewed": "Considered",
    "review first": "Considered",
    "manually reviewed": "Considered",
    "verified": "Considered",
    "paused": "Considered",
    "submitted": "Applied",
    "application submitted": "Applied",
    "follow up": "Applied",
    "followup": "Applied",
    "follow up needed": "Applied",
    "follow up sent": "Under Consideration",
    "due now": "Under Consideration",
    "recruiter contacted": "Under Consideration",
    "hiring manager contacted": "Under Consideration",
    "under review": "Under Consideration",
    "on hold": "Under Consideration",
    "passed": "Withdrawn / Closed",
    "pass": "Withdrawn / Closed",
    "declined": "Withdrawn / Closed",
    "do not pursue": "Withdrawn / Closed",
    "hidden": "Withdrawn / Closed",
    "invalid": "Withdrawn / Closed",
    "invalid hidden": "Withdrawn / Closed",
    "archived": "Withdrawn / Closed",
    "closed": "Withdrawn / Closed",
    "stale closed risk": "Withdrawn / Closed",
}


def normalize_status_key(value: Any) -> str:
    """Normalize status text for deterministic comparison."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def canonical_status(value: Any, *, default: str = "Prospect") -> str:
    """Return a canonical live status while preserving unknown values for audit."""
    clean = str(value or "").strip()
    if not clean:
        return default
    key = normalize_status_key(clean)
    if key in LEGACY_STATUS_ALIASES:
        return LEGACY_STATUS_ALIASES[key]
    canonical = {normalize_status_key(status): status for status in LIVE_STATUSES}
    return canonical.get(key, clean)


def migrate_legacy_statuses(
    records: Iterable[Mapping[str, Any]],
    *,
    migrated_at: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Migrate legacy live statuses without changing unknown values.

    The migration is idempotent. Only records whose stored status is a known
    legacy value are changed; malformed or unknown values are reported.
    """
    timestamp = migrated_at or datetime.now(timezone.utc).isoformat()
    migrated: list[dict[str, Any]] = []
    changes: list[dict[str, str]] = []
    unknown: list[dict[str, str]] = []
    before: dict[str, int] = {}
    after: dict[str, int] = {}
    for source in records:
        record = deepcopy(dict(source))
        raw = str(record.get("status") or "").strip()
        before[raw or "(empty)"] = before.get(raw or "(empty)", 0) + 1
        canonical = canonical_status(raw)
        if canonical not in LIVE_STATUSES:
            unknown.append({"id": str(record.get("id") or ""), "status": raw})
        elif normalize_status_key(raw) == "paused":
            metadata = dict(record.get("lifecycle_migration") or {})
            if "original_status" not in metadata:
                metadata["original_status"] = raw or "(empty)"
                metadata["migrated_at"] = timestamp
                metadata["migration"] = "sprint32_role_lifecycle"
            record["lifecycle_migration"] = metadata
            record["status"] = canonical
            changes.append(
                {"id": str(record.get("id") or ""), "from": raw, "to": canonical}
            )
        after_status = str(record.get("status") or "")
        after[after_status or "(empty)"] = after.get(after_status or "(empty)", 0) + 1
        migrated.append(record)
    report = {
        "changed": changes,
        "changed_count": len(changes),
        "unknown_statuses": unknown,
        "before_counts": dict(sorted(before.items())),
        "after_counts": dict(sorted(after.items())),
    }
    return migrated, report


StatusResolver = Callable[[Mapping[str, Any]], str]


def _default_status_resolver(record: Mapping[str, Any]) -> str:
    return canonical_status(record.get("status"))


def filter_live_records(
    records: Iterable[Mapping[str, Any]],
    status: str = "All",
    *,
    status_resolver: StatusResolver | None = None,
) -> list[dict[str, Any]]:
    """Use one status predicate for summary chips and dropdown filters.

    The dashboard supplies the tracker-aware resolver so legacy records whose
    submitted evidence promotes ``Active`` to ``Applied`` or ``Under
    Consideration`` are grouped exactly like their role cards. Callers that
    only have canonical lifecycle records retain the deterministic default.
    """
    resolve_status = status_resolver or _default_status_resolver
    selected = canonical_status(status, default="All") if status != "All" else "All"
    values = [dict(record) for record in records if record.get("archived") is not True]
    if selected == "All":
        return values
    return [record for record in values if resolve_status(record) == selected]


def lifecycle_counts(
    records: Iterable[Mapping[str, Any]],
    *,
    status_resolver: StatusResolver | None = None,
) -> dict[str, int]:
    """Return counts whose values exactly match the shared filter."""
    values = filter_live_records(records, status_resolver=status_resolver)
    return {
        "All": len(values),
        **{
            status: len(
                filter_live_records(
                    values,
                    status,
                    status_resolver=status_resolver,
                )
            )
            for status in DASHBOARD_STATUS_ORDER
        },
    }
