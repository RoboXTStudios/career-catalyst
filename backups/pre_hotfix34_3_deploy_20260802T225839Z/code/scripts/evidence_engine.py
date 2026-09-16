"""Evidence card loading and role-aware selection for generated materials."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

try:
    from .role_editing import detect_role_editing_category
except ImportError:
    from role_editing import detect_role_editing_category


CONFIDENCE_ORDER = {"low": 1, "medium": 2, "high": 3}
BUILDER_IDS = {"campaignos", "career_catalyst", "roboxt_studios"}
DEFAULT_MAX_CARDS = 4


class EvidenceEngineError(Exception):
    """Raised when evidence cards are missing or malformed."""


def load_evidence_cards(project_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Load configured evidence cards and validate required fields."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = root / "config" / "evidence_cards.yml"
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EvidenceEngineError(f"Unable to read evidence cards: {error}") from error
    cards = loaded.get("evidence_cards") if isinstance(loaded, dict) else None
    if not isinstance(cards, list):
        raise EvidenceEngineError("config/evidence_cards.yml must contain evidence_cards list")
    required = {
        "id",
        "label",
        "short_description",
        "proof_points",
        "tags",
        "strongest_role_fits",
        "when_to_use",
        "when_to_avoid",
        "confidence_level",
        "source",
    }
    for card in cards:
        missing = required - set(card)
        if missing:
            raise EvidenceEngineError(f"Evidence card {card.get('id', '<unknown>')} missing {sorted(missing)}")
        if card["confidence_level"] not in CONFIDENCE_ORDER:
            raise EvidenceEngineError(f"Evidence card {card['id']} has invalid confidence_level")
    return cards


def _role_text(role: dict[str, Any]) -> str:
    values = [
        role.get("job_title"),
        role.get("title"),
        role.get("company"),
        role.get("category"),
        role.get("role_family"),
        role.get("seniority"),
        role.get("source_notes"),
        role.get("inferred_strategic_angle"),
        role.get("raw_text"),
        role.get("job_description"),
        " ".join(str(v) for v in role.get("keywords", []) if v),
    ]
    return " ".join(str(value or "") for value in values).lower()


def _signals(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def role_evidence_category(role: dict[str, Any]) -> str:
    """Infer the evidence-selection category from role metadata and description."""
    editing_category = detect_role_editing_category(role)
    if editing_category == "chief_of_staff_business_operations":
        return "chief_of_staff_business_operations"
    if editing_category == "product_ai_operations":
        return "product_ai_operations"
    if editing_category == "marketing_operations_entertainment":
        return "entertainment_marketing_operations"
    if editing_category == "traditional_pmo_governance":
        return "traditional_pmo"
    text = _role_text(role)
    if _signals(text, ("human agency", "builder", "founder", "startup", "ai workflow", "automation", "entrepreneur")) >= 2:
        return "builder_friendly"
    if _signals(text, ("pmo", "program management office", "governance", "delivery", "risk", "qa", "executive reporting")) >= 2:
        return "traditional_pmo"
    if _signals(text, ("martech", "crm", "lifecycle", "adtech", "ad tech", "marketing technology", "measurement")):
        return "martech_crm"
    if _signals(text, ("creative operations", "content", "editorial", "storytelling", "photography", "creative production")):
        return "creative_operations"
    if _signals(text, ("entertainment", "marketing operations", "campaign", "disney", "streaming", "theatrical")) >= 2:
        return "entertainment_marketing_operations"
    return "general_operations"


def select_evidence_cards(
    role: dict[str, Any],
    cards: list[dict[str, Any]] | None = None,
    *,
    max_cards: int = DEFAULT_MAX_CARDS,
    minimum_confidence: str = "medium",
) -> list[dict[str, Any]]:
    """Select focused evidence cards for a role, preferring relevance over breadth."""
    cards = cards if cards is not None else load_evidence_cards()
    category = role_evidence_category(role)
    text = _role_text(role)
    minimum = CONFIDENCE_ORDER[minimum_confidence]
    category_tags = {
        "chief_of_staff_business_operations": {"governance", "qa", "pmo", "operations_leadership", "executive_communication"},
        "product_ai_operations": {"builder", "ai_workflows", "product_thinking", "operations_leadership", "governance"},
        "builder_friendly": {"builder", "ai_workflows", "product_thinking", "operations_leadership"},
        "traditional_pmo": {"governance", "qa", "pmo", "operations_leadership", "executive_communication"},
        "martech_crm": {"martech", "adtech", "campaign_execution", "measurement", "product_thinking"},
        "creative_operations": {"creative_operations", "creative_work", "storytelling", "editorial", "operations_leadership"},
        "entertainment_marketing_operations": {"entertainment_marketing_operations", "campaign_execution", "operations_leadership", "governance"},
        "general_operations": {"operations_leadership", "governance", "executive_communication"},
    }[category]
    selected: list[tuple[int, dict[str, Any]]] = []
    for card in cards:
        card_id = str(card["id"])
        confidence = CONFIDENCE_ORDER[str(card["confidence_level"])]
        if confidence < minimum:
            continue
        if category in {"traditional_pmo", "chief_of_staff_business_operations"} and card_id in {"roboxt_studios", "photography_creative_voice", "career_catalyst"}:
            continue
        if category not in {"builder_friendly", "martech_crm", "product_ai_operations", "chief_of_staff_business_operations", "creative_operations"} and card_id in {"campaignos", "career_catalyst", "roboxt_studios"}:
            continue
        if category == "creative_operations" and card_id in {"campaignos", "career_catalyst"}:
            continue
        if category == "chief_of_staff_business_operations" and card_id == "campaignos" and "campaignos" not in text and _signals(text, ("ai", "automation", "product", "systems")) == 0:
            continue
        tags = set(card.get("tags", []))
        score = len(tags & category_tags) * 3 + confidence
        score += _signals(text, tuple(str(tag).replace("_", " ") for tag in tags))
        if category == "builder_friendly" and card_id in BUILDER_IDS:
            score += 5
        if category == "entertainment_marketing_operations" and card_id == "omg23_disney_leadership":
            score += 5
        if category == "traditional_pmo" and card_id == "governance_qa_delivery":
            score += 5
        if category == "chief_of_staff_business_operations" and card_id in {"governance_qa_delivery", "omg23_disney_leadership"}:
            score += 5
        if category == "product_ai_operations" and card_id == "campaignos":
            score += 6
        if category == "product_ai_operations" and card_id == "career_catalyst":
            score += 8
        if category == "creative_operations" and card_id == "roboxt_studios":
            score += 7
        if score >= 5:
            selected.append((score, card))
    selected.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [card for _, card in selected[:max_cards]]


def load_writing_voice_profile(project_root: str | Path | None = None, level: int | None = None) -> dict[str, Any]:
    """Load the configured writing voice profile; defaults to Level 3."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = root / "config" / "writing_voice_profiles.yml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    default_level = int(loaded.get("default_level", 3))
    selected_level = int(level or default_level)
    levels = loaded.get("levels", {})
    profile = dict(levels.get(selected_level) or {})
    profile.update({
        "level": selected_level,
        "default_level": default_level,
        "banned_phrases": list(loaded.get("banned_phrases", [])),
    })
    return profile


EVIDENCE_PROJECTS_PATH = "data/evidence_projects.yml"
EVIDENCE_PROJECT_STATUSES = ("Active", "Draft", "Archived")
EVIDENCE_PROJECT_REQUIRED_FIELDS = ("title", "problem", "actions", "results")


def _slug(value: Any) -> str:
    import re
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "evidence_project"


def _evidence_project_path(project_root: str | Path | None = None) -> Path:
    root = Path(project_root) if project_root is not None else Path.cwd()
    return root / EVIDENCE_PROJECTS_PATH


def normalize_multivalue(value: Any) -> list[str]:
    """Normalize comma/newline/list evidence fields into stable, unique text values."""
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value or "").replace("\n", ",").split(",")
    values: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        clean = str(item or "").strip()
        key = clean.lower()
        if clean and key not in seen:
            values.append(clean)
            seen.add(key)
    return values


def normalize_evidence_project(project: dict[str, Any]) -> dict[str, Any]:
    """Return a storage-safe evidence project without discarding optional fields."""
    normalized = dict(project)
    title = str(normalized.get("title") or normalized.get("project_title") or "").strip()
    normalized["title"] = title
    normalized.setdefault("id", _slug(title))
    normalized["id"] = _slug(normalized.get("id") or title)
    for field in EVIDENCE_PROJECT_REQUIRED_FIELDS:
        normalized[field] = str(normalized.get(field) or "").strip()
    status = str(normalized.get("status") or "Active").strip().title()
    normalized["status"] = status if status in EVIDENCE_PROJECT_STATUSES else "Active"
    for field in ("skills", "technologies", "tags", "supporting_evidence", "links"):
        normalized[field] = normalize_multivalue(normalized.get(field))
    for field in (
        "employer", "organization", "client", "business_unit", "timeframe", "start_date",
        "end_date", "duration", "industry", "function", "project_type", "notes",
    ):
        if field in normalized:
            normalized[field] = str(normalized.get(field) or "").strip()
    return normalized


def validate_evidence_project(project: dict[str, Any]) -> None:
    """Validate required first-version evidence project fields."""
    missing = [field for field in EVIDENCE_PROJECT_REQUIRED_FIELDS if not str(project.get(field) or "").strip()]
    if missing:
        raise EvidenceEngineError(f"Evidence project missing required fields: {', '.join(missing)}")


def load_evidence_projects(project_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Load reusable project-based career evidence from YAML storage."""
    path = _evidence_project_path(project_root)
    if not path.exists():
        return []
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise EvidenceEngineError(f"Malformed evidence project YAML: {error}") from error
    projects = loaded.get("evidence_projects") if isinstance(loaded, dict) else None
    if projects is None:
        return []
    if not isinstance(projects, list):
        raise EvidenceEngineError("data/evidence_projects.yml must contain evidence_projects list")
    return [normalize_evidence_project(project) for project in projects if isinstance(project, dict)]


def save_evidence_projects(projects: list[dict[str, Any]], project_root: str | Path | None = None) -> Path:
    """Persist evidence projects without introducing a new storage system."""
    normalized = [normalize_evidence_project(project) for project in projects]
    ids = [project["id"] for project in normalized]
    if len(ids) != len(set(ids)):
        raise EvidenceEngineError("Evidence project ids must be unique")
    for project in normalized:
        validate_evidence_project(project)
    path = _evidence_project_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"evidence_projects": normalized}, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8")
    return path


def upsert_evidence_project(project: dict[str, Any], project_root: str | Path | None = None) -> dict[str, Any]:
    """Create or update one evidence project by id."""
    normalized = normalize_evidence_project(project)
    validate_evidence_project(normalized)
    projects = load_evidence_projects(project_root)
    existing_index = next((i for i, item in enumerate(projects) if item.get("id") == normalized["id"]), None)
    if existing_index is None:
        projects.append(normalized)
    else:
        projects[existing_index] = {**projects[existing_index], **normalized}
    save_evidence_projects(projects, project_root)
    return normalized


def archive_evidence_project(project_id: str, project_root: str | Path | None = None) -> dict[str, Any]:
    """Archive one evidence project without deleting its record."""
    projects = load_evidence_projects(project_root)
    target_id = _slug(project_id)
    for project in projects:
        if project.get("id") == target_id:
            project["status"] = "Archived"
            save_evidence_projects(projects, project_root)
            return project
    raise EvidenceEngineError(f"Evidence project not found: {project_id}")



def _merge_unique(existing: Any, additions: Any) -> list[str]:
    """Merge multivalue fields without dropping user-supplied values."""
    return normalize_multivalue(list(normalize_multivalue(existing)) + list(normalize_multivalue(additions)))


def _safe_seed_merge(existing: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    """Enrich an untouched seed record while preserving user edits and associations."""
    merged = dict(existing)
    for field, value in seed.items():
        if field in {"skills", "technologies", "tags", "supporting_evidence", "links"}:
            merged[field] = _merge_unique(existing.get(field), value)
            continue
        if field == "status" and existing.get("status"):
            continue
        if field == "id":
            merged[field] = existing.get("id") or value
            continue
        current = str(existing.get(field) or "").strip()
        if not current:
            merged[field] = value
    return merged


SPRINT_26_5_SEEDED_PROJECTS: tuple[dict[str, Any], ...] = (
    {
        "id": "enterprise_media_operations_transformation",
        "title": "Enterprise Media Operations Transformation",
        "employer": "OMG23",
        "client": "The Walt Disney Company",
        "business_unit": "The Walt Disney Company",
        "industry": "Entertainment & Media",
        "function": "Operations",
        "project_type": "Operations Project Management",
        "status": "Active",
        "problem": "A large enterprise media organization managed high-volume campaigns across theatrical releases, streaming, television, and corporate brands. As the business evolved, teams needed more consistent operational processes, stronger governance, clearer ownership, and scalable workflows to support increasingly complex marketing initiatives.",
        "actions": "Led cross-functional initiatives to improve media operations by redesigning workflows, establishing governance and quality-assurance standards, aligning stakeholders across media, marketing, analytics, and technology teams, and implementing scalable operational processes.",
        "results": "Established more consistent operational standards, improved cross-functional collaboration, increased visibility into complex initiatives, and created scalable processes that supported execution across multiple business units.",
        "tags": ["Media Operations", "Governance", "Quality Assurance", "Cross-Functional Leadership", "Process Improvement", "Program Management", "Business Transformation"],
    },
    {
        "id": "enterprise_collaboration_platform_adoption_stakeholder_enablement",
        "title": "Enterprise Collaboration Platform Adoption & Stakeholder Enablement",
        "employer": "OMG23",
        "client": "The Walt Disney Company",
        "business_unit": "The Walt Disney Company",
        "industry": "Entertainment & Media",
        "function": "Operations",
        "project_type": "Change Management",
        "status": "Active",
        "problem": "A large entertainment organization was transitioning to Microsoft Teams and needed practical support to help stakeholders adopt the platform, navigate new collaboration tools, and establish consistent ways of working. Adoption depended on accessible guidance and trusted users who could support teams through the change.",
        "actions": "Served as a Microsoft Teams power user and stakeholder resource during the rollout. Held recurring office hours for Disney stakeholders, answered platform and workflow questions, helped users troubleshoot adoption challenges, and identified and coordinated a network of champions and power users who could provide peer support across teams.",
        "results": "Improved stakeholder readiness and supported broader adoption of Microsoft Teams through practical guidance and peer support. The champion network expanded internal expertise, helped resolve questions more efficiently, and created a sustainable support structure as teams adjusted to new collaboration practices.",
        "technologies": ["Microsoft Teams"],
        "tags": ["Change Management", "Technology Adoption", "Stakeholder Enablement", "Training", "Office Hours", "Champion Network", "Collaboration"],
    },
    {
        "id": "operational_workflow_design_airtable_implementation",
        "title": "Operational Workflow Design & Airtable Implementation",
        "employer": "OMG23",
        "client": "Disney Performance Marketing",
        "business_unit": "Disney Performance Marketing",
        "industry": "Entertainment & Media",
        "function": "Marketing Operations",
        "project_type": "Technology Implementation Project Management",
        "status": "Active",
        "problem": "Disney Performance Marketing needed a centralized way to track multiple concurrent campaigns across its intellectual properties while reducing reliance on Google Sheets, Google Docs, and disconnected internal systems. Teams lacked a consistent source of truth for campaign status, documentation, and cross-functional reporting.",
        "actions": "Coordinated stakeholders across Disney Performance Marketing, OMG23 Marketing Science, business operations, and technical teams to support the Airtable implementation. Connected Disney and agency technology teams, tested workflows, trained users, and helped configure campaign tracking, status reporting, linked databases, a knowledge base, and automations. Established naming conventions, permissions, quality assurance, standardized workflows, and data-quality practices.",
        "results": "Created a centralized source of truth for campaign activity across teams, reducing duplicate work and the need for frequent status emails. The implementation improved visibility, strengthened data consistency, and provided a more structured and scalable way to manage campaign information before the platform was transitioned to the client.",
        "technologies": ["Airtable", "Google Sheets", "Google Docs"],
        "tags": ["Workflow Design", "Process Improvement", "Technology Implementation", "Campaign Tracking", "Status Reporting", "Data Governance", "Quality Assurance", "User Training", "Source of Truth"],
    },
    {
        "id": "enterprise_employee_engagement_community_fundraising_initiative",
        "title": "Enterprise Employee Engagement & Community Fundraising Initiative",
        "employer": "OMG23",
        "industry": "Entertainment & Media",
        "function": "Operations",
        "project_type": "Change Management",
        "duration": "Approximately three weeks",
        "status": "Active",
        "problem": "During the Southern California wildfires, employee morale was affected as teams were asked to participate in a scheduled company engagement event while surrounding communities were experiencing significant loss. Leadership wanted to strengthen company culture, but employees also needed a meaningful way to support those affected.",
        "actions": "Proposed and led a company-wide fundraising initiative that transformed an employee event into a community-impact campaign. Secured more than $35,000 in partner pledges, coordinated executive stakeholders, managed communications and logistics, and organized a raffle-based donation program supporting World Central Kitchen, Pasadena Humane, Altadena Girls, and the Los Angeles Fire Relief Fund.",
        "results": "Achieved 100% employee participation and directed more than $35,000 in pledged donations to wildfire-relief organizations. The initiative transformed a routine engagement event into a meaningful community response, strengthened employee morale, and aligned company culture with the needs of the moment.",
        "tags": ["Employee Engagement", "Community Impact", "Fundraising", "Crisis Response", "Executive Stakeholder Management", "Internal Communications", "Event Operations", "Culture", "Leadership"],
    },
)


def enrich_seed_evidence_projects(project_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Idempotently add missing Sprint 26.5 seed detail without overwriting edits."""
    projects = load_evidence_projects(project_root)
    by_id = {project.get("id"): index for index, project in enumerate(projects)}
    for seed in SPRINT_26_5_SEEDED_PROJECTS:
        normalized_seed = normalize_evidence_project(seed)
        if normalized_seed["id"] in by_id:
            index = by_id[normalized_seed["id"]]
            projects[index] = normalize_evidence_project(_safe_seed_merge(projects[index], normalized_seed))
        else:
            projects.append(normalized_seed)
            by_id[normalized_seed["id"]] = len(projects) - 1
    save_evidence_projects(projects, project_root)
    return load_evidence_projects(project_root)


def evidence_projects_for_role(application: dict[str, Any], project_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Return prospect-scoped, externally usable Evidence in saved order."""
    requested = [str(project_id) for project_id in application.get("evidence_project_ids", []) if str(project_id).strip()]
    if not requested:
        return []
    projects = {project["id"]: project for project in load_evidence_projects(project_root)}
    selected = [projects[project_id] for project_id in requested if project_id in projects]
    return [project for project in selected if evidence_is_externally_usable(project)]


def evidence_is_externally_usable(project: dict[str, Any]) -> bool:
    """Honor Evidence status and explicit privacy/usage controls."""
    if str(project.get("status") or "Active") != "Active":
        return False
    if project.get("external_use") is False or project.get("private") is True:
        return False
    usage = str(project.get("usage") or project.get("usage_control") or "").lower()
    return usage not in {"private", "internal only", "do not use externally", "exclude"}


def evidence_generation_context(projects: list[dict[str, Any]]) -> str:
    """Format associated projects as concise verified generation context."""
    if not projects:
        return ""
    lines = [
        "Verified role-associated Evidence projects. Use these as supporting proof points where relevant; do not invent metrics, employers, dates, or responsibilities, and do not paste raw records verbatim."
    ]
    for project in projects:
        context = ", ".join(
            value for value in [project.get("employer"), project.get("client") or project.get("business_unit"), project.get("industry"), project.get("function"), project.get("project_type"), project.get("duration")] if value
        )
        lines.append(f"- {project.get('title')}")
        if context:
            lines.append(f"  Context: {context}")
        for label, field in (("Problem", "problem"), ("Actions", "actions"), ("Results", "results")):
            if project.get(field):
                lines.append(f"  {label}: {project[field]}")
        for label, field in (("Skills", "skills"), ("Technologies", "technologies"), ("Tags", "tags")):
            values = project.get(field) or []
            if values:
                lines.append(f"  {label}: {', '.join(values)}")
    return "\n".join(lines)


def filter_evidence_projects(projects: list[dict[str, Any]], query: str = "", status: str = "All") -> list[dict[str, Any]]:
    """Filter evidence by title, employer, skills, technologies, tags, and status."""
    clean_query = str(query or "").strip().lower()
    clean_status = str(status or "All").strip()
    results = []
    for project in projects:
        if clean_status != "All" and project.get("status") != clean_status:
            continue
        haystack = " ".join(
            str(value)
            for value in (
                project.get("title"), project.get("employer"), project.get("organization"),
                project.get("client"), project.get("business_unit"), project.get("function"),
                project.get("project_type"), project.get("status"), " ".join(project.get("skills", [])),
                " ".join(project.get("technologies", [])), " ".join(project.get("tags", [])),
            )
        ).lower()
        if clean_query and clean_query not in haystack:
            continue
        results.append(project)
    return results
