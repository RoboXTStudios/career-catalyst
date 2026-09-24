"""Map selected Evidence to parsed posting requirements through shared concepts.

Keyword overlap rewards incidental words ("tools", "new", "provide") and misses
evidence that describes the same work in different vocabulary ("FYC" versus
"award nominations and voting windows").  This module parses the posting into
requirement lines, maps both requirements and Evidence into a small vocabulary
of concepts with synonyms, and reports which requirements each Evidence record
supports.  Coverage only grows as Evidence is added, so the score adjustment
built on it can never drop when matching Evidence is selected.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

try:
    from .dynamic_role_intelligence import strip_posting_boilerplate
except ImportError:
    from dynamic_role_intelligence import strip_posting_boilerplate


# concept id -> (display label, synonyms).  Synonyms are matched as whole
# normalized phrases.  Keep entries specific enough that a match means the
# requirement and the Evidence describe the same kind of work.
CONCEPTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "awards_campaigns": ("awards-season campaigns", (
        "fyc", "for your consideration", "awards season", "awards campaign",
        "awards campaigns", "award nominations", "award campaign", "nominations",
        "voting windows", "voting window", "grammys", "grammy", "emmys", "emmy",
        "oscars", "oscar", "academy awards", "golden globes", "cmas", "acms",
    )),
    "trade_media": ("trade media", (
        "trade media", "trade publications", "trade publication", "trade press",
        "trade advertising", "trade ads", "trade", "trades", "hollywood reporter",
    )),
    "paid_social": ("paid social and ad platforms", (
        "paid social", "social advertising", "ad platforms", "meta", "meta ads manager",
        "facebook ads", "instagram ads", "tiktok", "tiktok ads", "snap", "snapchat",
        "google ads", "youtube", "amazon ads",
    )),
    "programmatic": ("programmatic and CTV", (
        "programmatic", "dsp", "dsps", "demand side platform", "demand side platforms",
        "dv360", "display video 360", "the trade desk", "ctv", "connected tv",
    )),
    "ad_operations": ("ad operations and campaign setup", (
        "ad operations", "ad operation", "ad ops", "trafficking", "campaign setup",
        "campaign set up", "ad server", "cm360", "campaign manager 360", "campaign activation",
        "platform activation",
    )),
    "tracking_tagging": ("tracking and tagging", (
        "tracking", "tagging", "tags", "pixel", "pixels", "gtm", "google tag manager",
        "floodlight", "conversion tracking", "tag management", "taxonomy", "taxonomies",
        "data flows",
    )),
    "measurement": ("measurement and performance analysis", (
        "measurement", "measurement readiness", "measurement operations", "attribution",
        "performance analysis", "performance insights", "performance results",
        "analytics", "dashboards", "dashboard", "kpis", "doubleverify", "ias",
        "videoamp", "ga4", "marketing science",
    )),
    "media_planning": ("media planning and buying", (
        "media plan", "media plans", "media planning", "media strategy", "media strategies",
        "media buying", "media buy", "media buys", "traditional media", "out of home",
        "ooh", "media programs", "media mix",
    )),
    "optimization": ("campaign optimization", (
        "optimization", "optimizations", "optimize", "optimizing", "campaign flights",
        "a b testing", "test new ad products",
    )),
    # Owning a budget is not the same work as processing POs and invoices.
    "budget_management": ("budget management", (
        "budget", "budgets", "budget recaps", "media spend", "spend management",
    )),
    "financial_reconciliation": ("PO and invoice reconciliation", (
        "financial reconciliation", "reconciliation", "reconcile", "invoice", "invoices",
        "invoice approvals", "po requests", "po creation", "purchase order", "purchase orders",
        "billing", "accounts payable",
    )),
    "release_campaigns": ("release-driven entertainment campaigns", (
        "theatrical release", "theatrical releases", "release campaigns", "streaming launch",
        "streaming launches", "launch readiness", "premiere", "album release",
        "release windows", "franchise", "premium entertainment campaigns",
    )),
    "vendor_partners": ("media and platform partners", (
        "vendors", "vendor", "vendor workflows", "vendor integration", "channel partners",
        "platform partners", "media partners", "measurement partners", "technology partners",
        "publishers",
    )),
    "platform_governance": ("platform governance and QA", (
        "platform governance", "quality assurance", "qa", "quality standards",
        "naming conventions", "governance",
    )),
    "workflow_process": ("processes, workflows, and trackers", (
        "processes", "process design", "workflow", "workflows", "ways of working",
        "project trackers", "request forms", "automation", "automated", "operating model",
        "workflow governance", "execution standards",
    )),
    "cross_functional": ("cross-functional collaboration", (
        "cross functional", "cross functional collaboration", "cross functional leadership",
        "collaborate with", "partner with", "stakeholder alignment", "stakeholders",
    )),
    "people_leadership": ("team leadership", (
        "direct reports", "people leadership", "team leads", "led a team",
        "manage a team", "managing managers", "coaching",
    )),
    "music_industry": ("music industry", (
        "music industry", "record label", "labels", "artist", "artists", "playlist",
        "genre", "music",
    )),
    "entertainment_industry": ("entertainment industry", (
        "entertainment", "studio", "studios", "streaming", "theatrical", "film", "disney",
    )),
    # One concept per phrase the earlier explanation used, so existing matches
    # keep their familiar labels.
    **{
        phrase.replace(" ", "_").replace("-", "_"): (phrase, (phrase,))
        for phrase in (
            "audience insights", "business operations", "campaign management",
            "content strategy", "delivery outcomes", "go-to-market strategy",
            "launch readiness", "marketing technology", "measurement readiness",
            "partner enablement", "positioning and messaging", "product adoption",
            "product education", "product launch", "product operations",
            "product marketing", "sales enablement", "stakeholder alignment",
            "workflow governance",
        )
    },
    "marketing_technology": ("marketing technology", (
        "marketing technology", "martech", "adtech", "ad tech",
    )),
    "executive_communication": ("executive communication", ("executive communication",)),
}

# Phrases removed before testing one concept, where a longer name contains a
# synonym for something else ("The Trade Desk" is a DSP, not trade media).
CONCEPT_MASKS: dict[str, tuple[str, ...]] = {
    "trade_media": ("the trade desk", "trade desk", "trade off", "trade offs"),
}

# Industry context alone never makes a requirement "covered"; it only adds
# weight when the requirement is otherwise supported.
CONTEXT_CONCEPTS = frozenset({"music_industry", "entertainment_industry"})

EVIDENCE_TEXT_FIELDS = (
    "title", "problem", "actions", "results", "skills", "technologies", "tags",
    "function", "project_type", "industry",
)
ATOMIC_TEXT_FIELDS = ("canonical_claim", "skills", "technologies", "tags")

# Concepts that nearly every senior operator record mentions.  A requirement
# supported only through these earns half credit.
GENERIC_CONCEPTS = frozenset({
    "cross_functional", "workflow_process", "stakeholder_alignment", "people_leadership",
})

REQUIREMENT_BONUS_MAX = 12


def _normalize(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _flatten(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for nested in value.values() for text in _flatten(nested)]
    if isinstance(value, (list, tuple, set)):
        return [text for nested in value for text in _flatten(nested)]
    return [str(value)]


def concepts_in(text: str) -> set[str]:
    """Return every concept whose synonyms appear as whole phrases in text."""
    padded = f" {_normalize(text)} "
    found = set()
    for concept, (_label, phrases) in CONCEPTS.items():
        candidate = padded
        for mask in CONCEPT_MASKS.get(concept, ()):
            candidate = candidate.replace(f" {_normalize(mask)} ", " ")
        if any(f" {_normalize(phrase)} " in candidate for phrase in phrases):
            found.add(concept)
    return found


def concept_label(concept: str) -> str:
    return CONCEPTS.get(concept, (concept.replace("_", " "), ()))[0]


def evidence_text(project: Mapping[str, Any]) -> str:
    """Candidate-facing claim text only; notes, provenance, and guardrails are excluded."""
    parts = [text for field in EVIDENCE_TEXT_FIELDS for text in _flatten(project.get(field))]
    for atomic in project.get("atomic_evidence") or []:
        if isinstance(atomic, Mapping):
            parts.extend(text for field in ATOMIC_TEXT_FIELDS for text in _flatten(atomic.get(field)))
    return "\n".join(parts)


def _requirement_lines(parsed_job: Mapping[str, Any]) -> list[str]:
    body = str(parsed_job.get("job_description") or parsed_job.get("raw_text") or "")
    if "## Job Description" in body:
        body = body.split("## Job Description", 1)[1]
    lines: list[str] = []
    for raw_line in strip_posting_boilerplate(body).splitlines():
        line = re.sub(r"^[\s\-*•●▪◦·]+", "", raw_line).strip()
        if not line or line.endswith(":") or line.startswith("#"):
            continue
        # Single-line imports carry the whole posting in one line; split it into
        # sentences so each requirement can be matched on its own.
        pieces = re.split(r"(?<=[.!?;])\s+|\s+[●•▪]\s+", line) if len(line) > 280 else [line]
        for piece in pieces:
            piece = piece.strip(" .;")
            if len(piece.split()) >= 4:
                lines.append(piece)
    return list(dict.fromkeys(lines))


def posting_requirements(parsed_job: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Parse requirement lines that name at least one matchable, non-context concept."""
    requirements = []
    for text in _requirement_lines(parsed_job):
        concepts = concepts_in(text)
        if concepts - CONTEXT_CONCEPTS:
            requirements.append({
                "id": f"req-{len(requirements) + 1}",
                "text": text,
                "concepts": sorted(concepts),
            })
    return requirements


def match_evidence_to_requirements(
    parsed_job: Mapping[str, Any],
    projects: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return per-requirement Evidence support and a coverage summary."""
    requirements = posting_requirements(parsed_job)
    project_concepts = [
        (project, concepts_in(evidence_text(project)))
        for project in projects
    ]
    rows = []
    for requirement in requirements:
        required = set(requirement["concepts"]) - CONTEXT_CONCEPTS
        support = []
        for project, concepts in project_concepts:
            shared = sorted(required & concepts)
            if shared:
                support.append({
                    "id": str(project.get("id") or ""),
                    "title": str(project.get("title") or project.get("name") or project.get("id") or "Evidence"),
                    "concepts": shared,
                })
        matched = sorted({concept for item in support for concept in item["concepts"]})
        credit = 0.0 if not matched else (0.5 if set(matched) <= GENERIC_CONCEPTS else 1.0)
        rows.append({
            **requirement,
            "covered": bool(support),
            "coverage": "none" if not support else ("full" if set(matched) >= required else "partial"),
            "supporting_evidence": support,
            "matched_concepts": matched,
            "credit": credit,
        })
    covered = [row for row in rows if row["covered"]]
    matched_concepts = list(dict.fromkeys(
        concept for row in covered for concept in row["matched_concepts"]
    ))
    return {
        "requirements": rows,
        "coverage_credit": sum(row["credit"] for row in rows),
        "covered_count": len(covered),
        "total_count": len(rows),
        "matched_concepts": matched_concepts,
        "matched_labels": [concept_label(concept) for concept in matched_concepts],
    }


def requirement_coverage_bonus(coverage: Mapping[str, Any]) -> int:
    """Score adjustment proportional to weighted requirement coverage.

    Each requirement's credit can only rise as Evidence is added and the total
    is fixed by the posting, so the bonus never drops when Evidence is added.
    """
    total = int(coverage.get("total_count") or 0)
    if not total:
        return 0
    share = float(coverage.get("coverage_credit") or 0.0) / total
    return int(round(REQUIREMENT_BONUS_MAX * min(1.0, share)))


def uncovered_requirements(coverage: Mapping[str, Any]) -> list[str]:
    return [row["text"] for row in coverage.get("requirements") or [] if not row.get("covered")]


def iter_supporting_titles(coverage: Mapping[str, Any]) -> Iterable[str]:
    for row in coverage.get("requirements") or []:
        for item in row.get("supporting_evidence") or []:
            yield item["title"]
