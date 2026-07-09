"""Role-sensitive editing rules for generated application materials."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CATEGORY = "general_operations"


def _role_text(role: dict[str, Any]) -> str:
    values = [
        role.get("job_title"),
        role.get("title"),
        role.get("company"),
        role.get("category"),
        role.get("role_family"),
        role.get("raw_text"),
        role.get("job_description"),
        " ".join(str(v) for v in role.get("keywords", []) if v),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _signals(text: str, terms: list[str] | tuple[str, ...]) -> int:
    return sum(1 for term in terms if str(term).lower() in text)


def load_role_editing_rules(project_root: str | Path | None = None) -> dict[str, Any]:
    """Load role-sensitive material editing rules."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = root / "config" / "role_editing_rules.yml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = loaded.get("role_editing_rules") if isinstance(loaded, dict) else None
    if not isinstance(rules, dict):
        raise ValueError("config/role_editing_rules.yml must contain role_editing_rules mapping")
    return rules


def detect_role_editing_category(role: dict[str, Any], rules: dict[str, Any] | None = None) -> str:
    """Infer the material-editing category from role/title/JD language."""
    rules = rules if rules is not None else load_role_editing_rules()
    text = _role_text(role)
    scores: dict[str, int] = {}
    for category, rule in rules.items():
        scores[category] = _signals(text, rule.get("signals", []))
    # Product/AI and chief-of-staff need to win over broad PMO words such as roadmap or governance.
    priority = [
        "chief_of_staff_business_operations",
        "product_ai_operations",
        "marketing_operations_entertainment",
        "traditional_pmo_governance",
    ]
    best = max(priority, key=lambda category: (scores.get(category, 0), -priority.index(category)))
    return best if scores.get(best, 0) > 0 else DEFAULT_CATEGORY


def material_editing_plan(role: dict[str, Any], project_root: str | Path | None = None) -> dict[str, Any]:
    """Return reusable lead/support/omit/vocabulary/section guidance for a role."""
    rules = load_role_editing_rules(project_root)
    category = detect_role_editing_category(role, rules)
    rule = dict(rules.get(category, {}))
    return {
        "role_category": category,
        "lead_evidence": list(rule.get("lead_evidence", [])),
        "supporting_evidence": list(rule.get("supporting_evidence", [])),
        "omitted_evidence": list(rule.get("omitted_evidence", [])),
        "preferred_terms": list(rule.get("preferred_terms", [])),
        "banned_phrases": list(rule.get("banned_phrases", [])),
        "preferred_cover_letter_framing": rule.get("preferred_cover_letter_framing"),
        "resume_section_rules": dict(rule.get("resume_section_rules", {})),
    }
