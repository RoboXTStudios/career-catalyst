"""Guard generated materials against stale company or role context."""

from __future__ import annotations

import re
from typing import Any, Dict

try:
    from .filename_utils import company_display_name
except ImportError:
    from filename_utils import company_display_name


CONTEXT_MISMATCH_MESSAGE = (
    "Package context mismatch detected. Career Catalyst blocked this material because "
    "it appears to include stale context from another role. Regenerate after reloading "
    "the selected role."
)

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

    def __init__(self, violations: list[str], material_type: str = "material"):
        self.violations = tuple(violations)
        self.material_type = material_type
        detail = ", ".join(violations)
        super().__init__(f"{CONTEXT_MISMATCH_MESSAGE} Detected: {detail}")


def validate_material_context(
    content: str,
    parsed_job: Dict[str, Any],
    material_type: str = "material",
) -> Dict[str, Any]:
    """Validate content against only the selected job's company and description."""
    target_company = company_display_name(parsed_job.get("company"))
    job_text = " ".join(
        str(parsed_job.get(key) or "")
        for key in ("job_title", "raw_text", "job_description")
    ).lower()
    material_text = re.sub(r"\s+", " ", str(content or "").lower())
    violations = []
    for context_company, phrases in STALE_CONTEXT_SIGNALS.items():
        if context_company == target_company:
            continue
        for phrase in phrases:
            if phrase in material_text and phrase not in job_text:
                violations.append(phrase)
    result = {
        "valid": not violations,
        "target_company": target_company,
        "material_type": material_type,
        "violations": list(dict.fromkeys(violations)),
    }
    if violations:
        raise PackageContextMismatchError(result["violations"], material_type)
    return result
