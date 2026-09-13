"""Role-sensitive editing rules for generated application materials."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import re

import yaml

try:
    from .role_intent import build_role_intent
except ImportError:
    from role_intent import build_role_intent


DEFAULT_CATEGORY = "general_operations"


BANNED_VOICE_PHRASE_REWRITES = {
    "clear plan": "clear operating structure",
    "best work together": "work more effectively together",
    "enable great work": "support better execution",
    "genuine enthusiasm": "practical interest",
    "I built my career around": "my experience has centered on",
}


def rewrite_banned_voice_phrases(text: str) -> tuple[str, list[dict[str, str]]]:
    """Rewrite replaceable banned voice phrases before hard-fail validation."""
    rewritten = str(text or "")
    rewrites: list[dict[str, str]] = []
    for phrase, replacement in BANNED_VOICE_PHRASE_REWRITES.items():
        # Match complete phrases only so "clear plan" does not rewrite the
        # unrelated word "planning" inside otherwise correct candidate copy.
        pattern = re.compile(
            rf"(?<!\w){re.escape(phrase)}(?!\w)",
            re.IGNORECASE,
        )
        if pattern.search(rewritten):
            rewritten = pattern.sub(replacement, rewritten)
            rewrites.append({"phrase": phrase, "replacement": replacement})
    return rewritten, rewrites


def remaining_banned_voice_phrases(text: str, banned_phrases: list[str]) -> list[str]:
    """Return banned phrases that remain after deterministic rewrite attempts."""
    value = str(text or "")
    remaining: list[str] = []
    for phrase in banned_phrases:
        candidate = str(phrase or "").strip()
        if candidate and re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", value, re.IGNORECASE):
            remaining.append(candidate)
    return remaining


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


def material_editing_plan(
    role: dict[str, Any],
    project_root: str | Path | None = None,
    role_intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return reusable lead/support/omit/vocabulary/section guidance for a role."""
    rules = load_role_editing_rules(project_root)
    intent = role_intent or build_role_intent(role, project_root)
    intent_category = str(intent.get("primary_archetype") or DEFAULT_CATEGORY)
    category = {
        "business_operations_chief_of_staff": "chief_of_staff_business_operations",
        "ai_transformation": "product_ai_operations",
        "product_operations": "product_ai_operations",
        "marketing_operations_integration": "marketing_operations_entertainment",
        "martech_governance_adoption": "marketing_operations_entertainment",
        "creative_operations": "marketing_operations_entertainment",
        "entertainment_campaign_operations": "marketing_operations_entertainment",
        "pmo_program_delivery": "traditional_pmo_governance",
        "shared_services_operations": "traditional_pmo_governance",
    }.get(intent_category, detect_role_editing_category(role, rules))
    rule = dict(rules.get(category, {}))
    try:
        from .evidence_tailoring import reconcile_manual_evidence
    except ImportError:
        from evidence_tailoring import reconcile_manual_evidence
    merged_omissions = dict(intent)
    merged_omissions["suppressed_evidence"] = list(dict.fromkeys(
        [*intent.get("suppressed_evidence", []), *rule.get("omitted_evidence", [])]
    ))
    omissions = reconcile_manual_evidence(merged_omissions, intent.get("manual_evidence_projects", []))["suppressed_evidence"]
    resume = intent.get("resume") or {}
    return {
        "role_category": category,
        "lead_evidence": list(
            dict.fromkeys([*intent.get("lead_evidence", []), *rule.get("lead_evidence", [])])
        ),
        "supporting_evidence": list(
            dict.fromkeys(
                [*intent.get("supporting_evidence", []), *rule.get("supporting_evidence", [])]
            )
        ),
        "omitted_evidence": omissions,
        "preferred_terms": list(rule.get("preferred_terms", [])),
        "banned_phrases": list(rule.get("banned_phrases", [])),
        "preferred_cover_letter_framing": (
            (intent.get("cover_letter") or {}).get("framing")
            or rule.get("preferred_cover_letter_framing")
        ),
        "resume_section_rules": {
            **dict(rule.get("resume_section_rules", {})),
            "selected_project_limit": resume.get("selected_project_limit"),
            "earlier_career_policy": resume.get("earlier_career_policy"),
        },
        "role_intent": intent,
    }
