"""Guard generated materials against stale company or role context."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict

try:
    from .filename_utils import company_display_name
except ImportError:
    from filename_utils import company_display_name


CONTEXT_MISMATCH_MESSAGE = (
    "Career Catalyst found material tied to a different role and stopped generation "
    "to prevent a mixed application package."
)

COMPANY_CONTEXT_FAMILIES = {
    "Google": {"google", "youtube", "google youtube"},
    "Netflix": {"netflix", "netflix inc"},
    "Universal Music Group": {
        "universal music group",
        "umg",
        "umg recordings",
        "600 umg recordings inc",
    },
    "Paramount": {"paramount", "paramount streaming", "paramount streaming llc"},
    "AEG/AXS": {"aeg", "axs", "aeg axs", "aeg worldwide axs"},
    "WMG": {"wmg", "warner music group", "warner chappell music"},
    "UTA": {"uta", "united talent agency"},
}

STALE_CONTEXT_SIGNALS = {
    "Google": (
        "this google opportunity",
        "google opportunity",
        "youtube product activation",
        "youtube brand auction",
        "seller enablement",
    ),
    "Netflix": (
        "this netflix opportunity",
        "netflix opportunity",
        "role at netflix",
    ),
    "Universal Music Group": (
        "universal music group opportunity",
        "role at universal music group",
    ),
    "Paramount": (
        "paramount opportunity",
        "role at paramount",
    ),
    "AEG/AXS": (
        "aeg/axs opportunity",
        "role at aeg/axs",
    ),
    "WMG": (
        "wmg opportunity",
        "role at wmg",
    ),
}


class PackageContextMismatchError(ValueError):
    """Raised before a generated material with stale role context is written."""

    def __init__(
        self,
        violations: list[str],
        material_type: str = "material",
        *,
        diagnostics: Dict[str, Any] | None = None,
    ):
        self.violations = tuple(violations)
        self.material_type = material_type
        self.diagnostics = dict(diagnostics or {})
        super().__init__(CONTEXT_MISMATCH_MESSAGE)


def _normalized_identity(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def company_context_family(company: Any) -> str:
    """Return a stable company family so employer brands authorize their own terms."""
    normalized = _normalized_identity(company_display_name(company))
    for family, aliases in COMPANY_CONTEXT_FAMILIES.items():
        if normalized in aliases:
            return family
    return company_display_name(company) or str(company or "").strip()


def _description_text(values: Dict[str, Any]) -> str:
    direct = values.get("job_description") or values.get("description")
    if direct:
        return str(direct).strip()
    raw = str(values.get("raw_text") or "")
    marker = re.search(r"^##\s+Job Description\s*$", raw, re.I | re.M)
    return raw[marker.end() :].strip() if marker else raw.strip()


def prospect_context_fingerprint(
    values: Dict[str, Any], intelligence: Dict[str, Any] | None = None
) -> str:
    """Hash only fields that materially affect role-specific package content."""
    intelligence = dict(intelligence or {})
    match_report = (
        intelligence.get("match_report")
        if isinstance(intelligence.get("match_report"), dict)
        else values.get("match_report")
        if isinstance(values.get("match_report"), dict)
        else {}
    )
    payload = {
        "prospect_id": str(values.get("prospect_id") or values.get("id") or "").strip(),
        "company": _normalized_identity(values.get("company")),
        "company_family": company_context_family(values.get("company")),
        "job_title": _normalized_identity(values.get("job_title") or values.get("role")),
        "source_url": str(
            values.get("source_url")
            or values.get("official_url")
            or values.get("original_source_url")
            or ""
        ).strip(),
        "job_description": re.sub(r"\s+", " ", _description_text(values)).strip(),
        "company_category": str(intelligence.get("company_category") or ""),
        "role_family": str(intelligence.get("role_family") or ""),
        "evidence_ids": sorted(
            str(value)
            for value in intelligence.get("selected_evidence_ids", [])
            if str(value).strip()
        ),
        "evidence_proof": [
            re.sub(r"\s+", " ", str(value)).strip()
            for value in intelligence.get("proof_points_to_emphasize", [])
            if str(value).strip()
        ],
        "analysis": {
            "match_score": match_report.get("match_score"),
            "match_tier": str(match_report.get("match_tier") or ""),
            "match_summary": re.sub(
                r"\s+", " ", str(match_report.get("match_summary") or "")
            ).strip(),
            "match_strengths": [
                re.sub(r"\s+", " ", str(value)).strip()
                for value in (match_report.get("match_strengths") or [])
                if str(value).strip()
            ],
            "match_gaps": [
                re.sub(r"\s+", " ", str(value)).strip()
                for value in (match_report.get("match_gaps") or [])
                if str(value).strip()
            ],
            "recommended_action": str(
                match_report.get("recommended_action") or ""
            ),
            "confidence": str(match_report.get("confidence") or ""),
        },
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_material_context(
    content: str,
    parsed_job: Dict[str, Any],
    material_type: str = "material",
) -> Dict[str, Any]:
    """Validate content against only the selected job's company and description."""
    target_company = company_display_name(parsed_job.get("company"))
    target_family = company_context_family(target_company)
    job_text = " ".join(
        str(parsed_job.get(key) or "")
        for key in ("job_title", "raw_text", "job_description")
    ).lower()
    material_text = re.sub(r"\s+", " ", str(content or "").lower())
    confirmed = []
    uncertain = []
    authorized_overlap = []
    for context_company, phrases in STALE_CONTEXT_SIGNALS.items():
        if company_context_family(context_company) == target_family:
            authorized_overlap.extend(
                phrase for phrase in phrases if phrase in material_text
            )
            continue
        foreign_hits = []
        for phrase in phrases:
            if phrase not in material_text:
                continue
            if phrase in job_text:
                authorized_overlap.append(phrase)
                continue
            foreign_hits.append(phrase)
        family_aliases = COMPANY_CONTEXT_FAMILIES.get(
            company_context_family(context_company), set()
        )
        foreign_company_hits = [
            alias
            for alias in family_aliases
            if len(alias) >= 4 and alias in material_text and alias not in job_text
        ]
        explicit_company_hits = [
            phrase
            for phrase in foreign_hits
            if context_company.lower() in phrase
            or phrase.startswith("role at ")
            or phrase.startswith("this ")
            or phrase.endswith(" opportunity")
        ]
        if explicit_company_hits or len(foreign_hits) >= 2 or (
            foreign_hits and foreign_company_hits
        ):
            confirmed.extend([*foreign_company_hits, *foreign_hits])
        else:
            uncertain.extend(foreign_hits)
    violations = list(dict.fromkeys(confirmed))
    result = {
        "valid": not violations,
        "mismatch_status": "confirmed" if violations else "uncertain" if uncertain else "current_role_overlap" if authorized_overlap else "clear",
        "target_company": target_company,
        "target_company_family": target_family,
        "material_type": material_type,
        "violations": violations,
        "uncertain_indicators": list(dict.fromkeys(uncertain)),
        "current_role_overlap": list(dict.fromkeys(authorized_overlap)),
    }
    if violations:
        raise PackageContextMismatchError(
            result["violations"], material_type, diagnostics=result
        )
    return result
