"""Deterministic, shared role-intent classification and generation guidance."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import re
import yaml

try:
    from .candidate_output import humanize_identifier, humanize_values
    from .filename_utils import company_display_name
except ImportError:
    from candidate_output import humanize_identifier, humanize_values
    from filename_utils import company_display_name


DEFAULT_ARCHETYPE = "general_operations"
ROLE_INTENT_RULES_PATH = Path("config/role_intent_rules.yml")
SOURCE_ROLE_INTENT_RULES_PATH = Path(__file__).resolve().parents[1] / ROLE_INTENT_RULES_PATH
PACKAGE_ROLE_FAMILIES = {
    "product_operations": ("product_strategy_ops", "Product Strategy & Operations"),
    "product_marketing": ("product_marketing", "Product Marketing"),
    "business_operations_chief_of_staff": ("business_operations", "Business Operations & Strategy"),
    "general_operations": ("business_operations", "Senior Operations Leadership"),
}

ROLE_INTELLIGENCE_OVERRIDE_FIELDS = (
    "company_voice",
    "category",
    "role_family",
    "primary_hiring_need",
    "leading_themes",
    "supporting_themes",
)

# Dynamic families are resolved from the posting, then use the same shared
# role-intent object to drive candidate-facing writing. These descriptions are
# conservative and avoid implying restricted sales or music responsibilities.
DYNAMIC_ROLE_WRITING = {
    "experiential_live_event_production": {
        "headline": "Senior Operations Leader | Entertainment | Activations | Cross-Functional Delivery",
        "summary": (
            "Senior operations leader with entertainment, creative-production, and activation-adjacent experience. "
            "I bring structured planning, stakeholder coordination, timeline visibility, and cross-functional delivery "
            "to live-event environments through dependable, practical execution."
        ),
        "competency_priorities": [
            "Production Operations", "Project & Program Management", "Stakeholder Management",
            "Cross-Functional Leadership", "Creative Operations", "Entertainment Marketing",
            "Workflow Governance", "Quality Assurance",
        ],
        "tools": {
            "Operations & Program Management": [
                "Workflow Design", "Timeline Management", "Stakeholder Coordination",
                "Production Planning", "Quality-Assurance Frameworks",
            ],
            "Creative & Experiential": [
                "Creative Collaboration", "Activation Planning", "Cross-Functional Delivery",
            ],
        },
    },
    "strategy_gtm_operations": {
        "headline": "Senior Strategy & Operations Leader | Transformation | AI Systems | Marketing Operations",
        "summary": (
            "Senior strategy and operations leader who translates go-to-market priorities into clear planning rhythms, "
            "workflow visibility, data quality, and cross-functional execution. At OMG23 / OMD Entertainment, Omnicom Media Group, I led "
            "10 direct reports and provided strategic and operational leadership across an integrated 64-person organization. "
            "My strengths include operating model design, stakeholder alignment, workflow governance, and disciplined delivery "
            "in complex organizations."
        ),
        "competency_priorities": [
            "Strategic Operations", "Business Operations", "Operating Model Design",
            "Executive Stakeholder Management", "Cross-Functional Leadership",
            "Workflow Governance", "Measurement & Data Governance", "Quality Assurance",
        ],
        "tools": {
            "Business Productivity & Collaboration": ["Airtable", "Microsoft Teams", "Microsoft 365"],
            "Operations & Program Management": [
                "Workflow Design", "Operating Models", "Process Documentation",
                "Reporting Workflows", "Quality-Assurance Frameworks",
            ],
        },
    },
    "paid_media": {
        "headline": "Senior Media Operations Leader | Paid Media Execution | Measurement & Tracking | Entertainment",
        "summary": (
            "Senior media operations leader with enterprise entertainment experience across campaign activation, "
            "platform governance, tagging, and measurement readiness for theatrical releases, streaming launches, and "
            "franchise priorities. At OMG23 / OMD Entertainment, Omnicom Media Group, I led 10 direct reports and provided "
            "strategic and operational leadership across an integrated 64-person organization spanning Ad Operations, "
            "Creative Management, and Marketing Science and Analytics."
        ),
        "competency_priorities": [
            "Media Operations", "Entertainment Marketing", "Measurement & Data Governance",
            "MarTech Strategy", "Vendor Integration", "Quality Assurance",
            "Workflow Governance", "Cross-Functional Leadership",
        ],
        "tools": {
            "Marketing Technology & Measurement": [
                "Google Marketing Platform", "CM360", "DV360", "Google Ads", "YouTube",
                "The Trade Desk", "Meta Ads Manager", "TikTok Ads", "Innovid",
                "DoubleVerify", "IAS",
            ],
            "Operations & Program Management": [
                "Campaign Taxonomy", "Pixel and Tagging Strategy", "Measurement Readiness",
                "Platform Governance", "Quality-Assurance Frameworks",
            ],
        },
    },
    "music_partnerships_label_relations": {
        "headline": "Senior Operations & Entertainment Partnerships Leader | Media Operations | Creator Platforms",
        "summary": (
            "Senior operations and entertainment-media leader with direct audio production experience and a record of "
            "coordinating complex work across creative, media, analytics, technology, vendors, and client stakeholders. "
            "At OMG23 / OMD Entertainment, Omnicom Media Group, I led 10 direct reports and provided strategic and operational leadership "
            "across an integrated 64-person organization. I bring strengths in partner coordination, release readiness, "
            "workflow governance, and cross-functional execution."
        ),
        "competency_priorities": [
            "Media Operations", "Entertainment Marketing", "Cross-Functional Leadership",
            "Partner Coordination", "Workflow Governance", "Quality Assurance",
            "Executive Stakeholder Management", "Creative Operations",
        ],
        "tools": {
            "Operations & Program Management": [
                "Workflow Design", "Process Documentation", "Quality-Assurance Frameworks",
                "Reporting Workflows",
            ],
            "Publishing & Creative": ["Editorial Production", "Post-Production Workflows"],
        },
    },
}


def load_role_intent_rules(project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root) if project_root is not None else Path.cwd()
    candidates = (SOURCE_ROLE_INTENT_RULES_PATH, root / ROLE_INTENT_RULES_PATH)
    rules_path = next((path for path in candidates if path.is_file()), None)
    if rules_path is None:
        raise FileNotFoundError("config/role_intent_rules.yml was not found in code or runtime roots")
    loaded = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    rules = loaded.get("role_intent") if isinstance(loaded, dict) else None
    if not isinstance(rules, dict) or not isinstance(rules.get("archetypes"), dict):
        raise ValueError("config/role_intent_rules.yml must contain role_intent.archetypes")
    return rules


def _role_text(role: Mapping[str, Any]) -> str:
    values = (
        role.get("job_title"),
        role.get("title"),
        role.get("role"),
        role.get("raw_text"),
        role.get("job_description"),
        " ".join(str(value) for value in role.get("keywords", []) if value),
        " ".join(str(value) for value in role.get("responsibilities", []) if value),
        " ".join(str(value) for value in role.get("qualifications", []) if value),
    )
    return re.sub(r"\s+", " ", " ".join(str(value or "") for value in values)).lower()


def _product_management_title(role: Mapping[str, Any]) -> bool:
    """Return whether the exact title is product management, with explicit exclusions."""
    title = re.sub(
        r"\s+", " ", str(role.get("job_title") or role.get("title") or role.get("role") or "")
    ).strip().lower()
    if _product_management_title_excluded(title):
        return False
    return any(
        re.match(pattern, title) is not None
        for pattern in (
            r"^(?:(?:senior|sr\.?|principal|ai)\s+)*product manager\b",
            r"^director of product\b",
            r"^product lead\b",
        )
    )


def _product_marketing_title(role: Mapping[str, Any]) -> bool:
    title = re.sub(
        r"\s+", " ", str(role.get("job_title") or role.get("title") or role.get("role") or "")
    ).strip().lower()
    return _contains(title, "product marketing")


def _product_management_title_excluded(title_or_role: Any) -> bool:
    if isinstance(title_or_role, Mapping):
        title = str(
            title_or_role.get("job_title")
            or title_or_role.get("title")
            or title_or_role.get("role")
            or ""
        ).lower()
    else:
        title = str(title_or_role or "").lower()
    return any(
        excluded in title
        for excluded in (
            "product marketing",
            "marketing product",
            "product sales",
            "sales product",
        )
    )


def _contains(text: str, phrase: str) -> bool:
    phrase = re.sub(r"\s+", " ", str(phrase or "").strip().lower())
    if not phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _seniority(role: Mapping[str, Any]) -> str:
    title = str(role.get("job_title") or role.get("title") or role.get("role") or "").lower()
    if "senior" in title and "manager" in title:
        return "senior_manager"
    for label, terms in (
        ("executive", ("chief", "vice president", "vp", "head of")),
        ("director", ("director",)),
        ("senior_manager", ("senior manager", "sr. manager", "sr manager")),
        ("manager", ("manager",)),
        ("senior_individual_contributor", ("senior", "lead", "principal")),
    ):
        if any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", title) for term in terms):
            return label
    return "unspecified"


def _explicit_operational_guidance(
    text: str, dynamic_family: str, title: str = ""
) -> tuple[str | None, list[str], list[str], list[str]]:
    """Return deterministic hiring guidance from explicit posting responsibilities."""
    title_text = str(title or "").lower()
    marketing_signals = (
        "annual planning", "budgeting", "forecasting", "resource planning",
        "resource allocation", "finance", "analytics", "marketing operations",
        "creative production", "process design", "process optimization",
        "scalable process", "performance visibility",
    )
    campaign_signals = (
        "campaign management", "campaign infrastructure", "marketing infrastructure",
        "workflow governance", "scalable execution", "campaign workflows",
    )
    campaign_management_title = any(
        _contains(title_text, signal)
        for signal in ("campaign management", "campaign infrastructure")
    )
    if dynamic_family == "experiential_live_event_production":
        return (
            "Plan and execute live-event and experiential activations, managing production workflows, budgets, timelines, vendors and fabrication, venues, logistics, and onsite execution from planning through load-out.",
            [
                "experiential production", "live-event execution", "production/project management",
                "budget management", "timeline management", "vendor/fabrication management",
                "venue/logistics coordination", "creative-production coordination", "onsite execution",
            ],
            [
                "sponsorship activations", "client/stakeholder management",
                "cross-functional coordination", "problem solving", "production operations",
                "creative collaboration",
            ],
            [
                "MarTech campaign execution", "measurement readiness", "platform implementation",
                "editorial leadership", "content systems", "Career Catalyst",
                "generic tracking and training themes",
            ],
        )
    if dynamic_family == "paid_media":
        return (
            "Plan, activate, and optimize paid media across social, CTV, programmatic, and traditional channels, "
            "keeping campaign setup, trafficking, tracking and tagging, measurement, and partner coordination "
            "dependable through release-driven and awards-season windows.",
            [
                "paid media execution", "campaign setup and activation", "trafficking and ad operations",
                "measurement and tracking", "tagging quality", "campaign optimization",
            ],
            [
                "release-driven campaign timing", "awards-season campaigns", "trade media",
                "platform and vendor coordination", "cross-functional leadership",
            ],
            [
                "community growth", "editorial storytelling", "Multiverse",
                "nonprofit social impact", "unsupported media negotiation or buying-authority claims",
            ],
        )
    if dynamic_family == "strategy_gtm_operations" and campaign_management_title and any(
        _contains(text, signal) for signal in campaign_signals
    ):
        return (
            "Build and govern campaign-management infrastructure, workflows, systems, accountability, and scalable execution across marketing teams.",
            [
                "campaign management", "marketing infrastructure", "workflow governance",
                "scalable execution", "cross-functional leadership",
            ],
            ["planning", "measurement", "stakeholder alignment"],
            ["nonprofit social impact", "editorial storytelling", "Multiverse"],
        )
    if dynamic_family == "strategy_gtm_operations" and any(
        _contains(text, signal) for signal in marketing_signals
    ):
        return (
            "Build and optimize the frameworks, processes, tools, planning systems, and operating practices that help global Marketing and Creative teams scale efficiently and increase business impact.",
            [
                "marketing operations", "strategy and business operations",
                "annual planning and budgeting", "resource planning",
                "operating-system and process design", "process optimization",
                "executive communication", "cross-functional leadership",
            ],
            [
                "Finance and Analytics partnership", "measurement frameworks",
                "project tracking", "global marketing operations",
                "creative and production workflows", "stakeholder alignment",
            ],
            ["nonprofit social impact", "editorial storytelling", "Multiverse"],
        )
    return None, [], [], []


def _score_archetype(
    text: str,
    rule: Mapping[str, Any],
    weights: Mapping[str, Any],
) -> tuple[int, list[tuple[int, str]]]:
    matches: list[tuple[int, str]] = []
    signals = rule.get("signals") or {}
    for tier in ("action_outcome", "supporting", "generic"):
        weight = int(weights.get(tier, 0))
        for phrase in signals.get(tier, []) or []:
            if _contains(text, str(phrase)):
                matches.append((weight, str(phrase)))
    if rule.get("requires_specific_action"):
        action_weight = int(weights.get("action_outcome", 0))
        discriminating = [phrase for weight, phrase in matches
                          if weight == action_weight and phrase not in rule.get("nonspecific_actions", [])]
        if not discriminating:
            matches = [(weight, phrase) for weight, phrase in matches if weight < action_weight]
    matches.sort(key=lambda item: (-item[0], item[1].lower()))
    return sum(weight for weight, _phrase in matches), matches


def _confidence(best_score: int, second_score: int, threshold: int) -> str:
    if best_score >= max(18, threshold * 2) and best_score - second_score >= 4:
        return "high"
    if best_score >= threshold:
        return "medium"
    return "low"


def _greeting(company: Any) -> str:
    display = company_display_name(company).strip()
    if display.lower() in {"", "company", "unknown", "unknown company", "not provided"}:
        return "Dear Hiring Team,"
    return f"Dear {display} Hiring Team,"


def build_role_intent(
    role: Mapping[str, Any],
    project_root: str | Path | None = None,
    *,
    rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one inspectable Role Intent Profile from action-and-outcome signals."""
    configured = dict(rules or load_role_intent_rules(project_root))
    archetypes = configured["archetypes"]
    weights = configured.get("score_weights") or {}
    threshold = int(configured.get("specialized_threshold", 9))
    secondary_threshold = int(configured.get("secondary_threshold", 6))
    text = _role_text(role)
    ranked: list[tuple[int, str, list[tuple[int, str]]]] = []
    for archetype, rule in archetypes.items():
        if archetype == DEFAULT_ARCHETYPE:
            continue
        score, matches = _score_archetype(text, rule, weights)
        ranked.append((score, str(archetype), matches))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_archetype, best_matches = ranked[0] if ranked else (0, DEFAULT_ARCHETYPE, [])
    dynamic_family = str(
        role.get("role_family") or role.get("dynamic_role_family") or ""
    ).strip()
    if not dynamic_family:
        # Keep direct callers (CLI/tests/intake) on the same title-and-posting
        # classification path as package generation without introducing a module
        # dependency cycle at import time.
        try:
            from .dynamic_role_intelligence import detect_role_family
        except ImportError:
            from dynamic_role_intelligence import detect_role_family
        dynamic_family = detect_role_family(
            str(role.get("job_title") or role.get("title") or role.get("role") or ""),
            str(role.get("raw_text") or role.get("job_description") or ""),
        )
    product_marketing_override = _product_marketing_title(role)
    product_override = _product_management_title(role) or (
        dynamic_family == "product_strategy_ops"
        and not _product_management_title_excluded(role)
    )
    if product_marketing_override:
        primary = "product_marketing"
        product_marketing_entry = next(
            (item for item in ranked if item[1] == "product_marketing"),
            (0, "product_marketing", []),
        )
        best_score = max(best_score, threshold * 2)
        selected_matches = list(product_marketing_entry[2])
        title = str(role.get("job_title") or role.get("title") or role.get("role") or "")
        selected_matches.insert(0, (threshold * 2, title or "product marketing title"))
        confidence = "high"
    elif product_override:
        primary = "product_operations"
        product_entry = next(
            (item for item in ranked if item[1] == "product_operations"),
            (0, "product_operations", []),
        )
        best_score = max(best_score, threshold * 2)
        selected_matches = list(product_entry[2])
        title = str(role.get("job_title") or role.get("title") or role.get("role") or "")
        selected_matches.insert(0, (threshold * 2, title or "product management title"))
        confidence = "high"
    elif best_score < threshold:
        primary = DEFAULT_ARCHETYPE
        selected_matches = best_matches
        confidence = "low" if best_score < max(1, threshold // 2) else "medium"
    else:
        primary = best_archetype
        selected_matches = best_matches
        second_score = ranked[1][0] if len(ranked) > 1 else 0
        confidence = _confidence(best_score, second_score, threshold)
    secondary = [
        archetype
        for score, archetype, _matches in ranked
        if archetype != primary and score >= secondary_threshold and score >= best_score * 0.5
    ][:3]
    try:
        from .dynamic_role_intelligence import is_agency_delivery_role
    except ImportError:
        from dynamic_role_intelligence import is_agency_delivery_role
    agency_delivery = is_agency_delivery_role(
        str(role.get("job_title") or role.get("role") or ""), text
    )
    if agency_delivery:
        primary = DEFAULT_ARCHETYPE
        confidence = "high"
        secondary = []
    rule = deepcopy(archetypes[primary])
    resume = deepcopy(rule.get("resume") or {})
    cover_letter = deepcopy(rule.get("cover_letter") or {})
    if primary == "product_operations" and any(
        signal in text
        for signal in ("emerging format", "podcast", "streaming", "content lifecycle")
    ):
        resume["headline"] = (
            "Product Strategy & Operations Leader | Emerging Media | AI Systems | Entertainment"
        )
        resume["summary"] = (
            "Product strategy and operations leader who translates ambiguous requirements into clear "
            "priorities and cross-functional delivery, connecting streaming launch readiness, active "
            "product development, and hands-on media production with practical product judgment."
        )
    dynamic_writing = DYNAMIC_ROLE_WRITING.get(dynamic_family)
    explicit_need, explicit_lead, explicit_support, explicit_suppressed = _explicit_operational_guidance(
        text,
        dynamic_family,
        str(role.get("job_title") or role.get("title") or role.get("role") or ""),
    )
    primary_hiring_need = explicit_need or str(rule.get("primary_hiring_need") or "")
    lead_evidence = explicit_lead or list(rule.get("lead_evidence") or [])
    supporting_evidence = explicit_support or list(rule.get("supporting_evidence") or [])
    suppressed_evidence = explicit_suppressed or list(rule.get("suppressed_evidence") or [])
    if dynamic_writing:
        resume["headline"] = dynamic_writing["headline"]
        resume["summary"] = dynamic_writing["summary"]
        resume["competency_priorities"] = list(dynamic_writing["competency_priorities"])
        resume["tools"] = deepcopy(dynamic_writing["tools"])
        resume["omg23_bullet_limit"] = 4 if dynamic_family == "strategy_gtm_operations" else 6
        resume["selected_project_limit"] = 0
        resume["earlier_career_policy"] = "omit"
        resume["target_max_pages"] = 2
    if agency_delivery:
        primary_hiring_need = (
            "Lead and develop the agency's delivery-team leaders; redesign workflows, establish operating "
            "standards and quality, improve capacity visibility, and partner with technology and executive "
            "leaders on practical AI enablement."
        )
        lead_evidence = ["people_leadership", "leadership_development", "workflow_governance", "operating_standards"]
        supporting_evidence = ["delivery_outcomes", "capacity_visibility", "technology_enablement", "executive_partnership"]
        suppressed_evidence = ["unrelated_independent_projects", "additional_early_experience"]
        resume.update({
            "headline": "Senior Operations & Transformation Leader | People Leadership | Delivery | Workflow Design",
            "summary": "Operations and transformation leader who develops people, clarifies delivery standards, "
                       "redesigns workflows, and connects quality and capacity visibility with practical technology enablement. "
                       "Brings enterprise media operations experience and cross-functional leadership to complex delivery organizations.",
            "competency_priorities": ["People Leadership", "Leadership Development", "Operations Transformation", "Workflow Governance", "Quality Assurance", "Cross-Functional Leadership", "Process Excellence", "Executive Stakeholder Management"],
        })
        cover_letter["framing"] = primary_hiring_need
    resume.setdefault("headline_profile", resume.pop("headline", ""))
    if "headline" in resume:
        resume.pop("headline")
    resume.setdefault("summary_profile", resume.pop("summary", ""))
    if "summary" in resume:
        resume.pop("summary")
    resume.setdefault("competency_profile", primary)
    resume.setdefault("tools_profile", primary)
    cover_letter["greeting"] = _greeting(role.get("company"))
    default_family = dynamic_family or primary
    package_family, package_label = PACKAGE_ROLE_FAMILIES.get(
        primary,
        (default_family, humanize_identifier(default_family or primary)),
    )
    dynamic_package_labels = {
        "product_marketing": "Product Marketing",
        "music_partnerships_label_relations": "Music Partnerships & Label Relations",
        "experiential_live_event_production": "Experiential Production / Live Event Production",
        "strategy_gtm_operations": "Strategy & GTM Operations",
        "paid_media": "Paid Media / Media Planning & Buying",
    }
    if dynamic_family in dynamic_package_labels:
        package_family = dynamic_family
        package_label = dynamic_package_labels[dynamic_family]
        if dynamic_family == "strategy_gtm_operations" and any(
            _contains(
                str(role.get("job_title") or role.get("title") or role.get("role") or "").lower(),
                signal,
            )
            for signal in ("campaign management", "campaign infrastructure")
        ):
            package_label = "Marketing Operations / Campaign Management"
        elif dynamic_family == "strategy_gtm_operations" and _contains(text, "marketing operations"):
            package_label = "Marketing Operations / Strategy & Business Operations"
    reasoning_signals = list(lead_evidence + supporting_evidence) if agency_delivery else [phrase for _weight, phrase in selected_matches[:12]]
    if explicit_lead:
        # Dynamic families expose the same explicit production or operating
        # signals used by the Tailoring Plan instead of generic archetype
        # matches such as "creative" or "tracking".
        reasoning_signals = list(explicit_lead)
    return {
        "mandate": "agency_delivery" if agency_delivery else "",
        "primary_archetype": primary,
        "package_role_family": package_family,
        "package_role_label": package_label,
        "secondary_archetypes": secondary,
        "confidence": confidence,
        "seniority": _seniority(role),
        "business_environment": secondary + [primary],
        "primary_hiring_need": primary_hiring_need,
        "required_outcomes": list(rule.get("required_outcomes") or []),
        "work_motions": list(rule.get("work_motions") or []),
        "reasoning_signals": reasoning_signals,
        "lead_evidence": lead_evidence,
        "supporting_evidence": supporting_evidence,
        "suppressed_evidence": suppressed_evidence,
        "resume": resume,
        "cover_letter": cover_letter,
        "scores": {archetype: score for score, archetype, _matches in ranked},
    }


def _theme_values(value: Any) -> list[str]:
    """Normalize editable theme input without changing inferred source data."""
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = re.split(r"[;\n]+", str(value or ""))
    return [str(item).strip() for item in values if str(item).strip()]


def normalize_role_intelligence_overrides(value: Any) -> dict[str, Any]:
    """Return the small, stable override schema persisted on one tracker record."""
    if not isinstance(value, Mapping):
        return {}
    resolved: dict[str, Any] = {}
    for field in ROLE_INTELLIGENCE_OVERRIDE_FIELDS:
        raw = value.get(field)
        if field in {"leading_themes", "supporting_themes"}:
            themes = _theme_values(raw)
            if themes:
                resolved[field] = themes
            continue
        text = str(raw or "").strip()
        if text:
            resolved[field] = text
    return resolved


ROLE_FAMILY_CHOICE_LABELS = {
    "paid_media": "Paid Media / Media Planning & Buying",
    "strategy_gtm_operations": "Strategy & GTM Operations",
    "business_operations": "Business Operations",
    "creative_marketing_ops": "Creative & Marketing Operations",
    "product_marketing": "Product Marketing",
    "product_strategy_ops": "Product Strategy & Operations",
    "gtm_product_activation": "GTM Product Activation",
    "transformation_advisory": "Transformation Advisory",
    "ai_operations_systems": "AI Operations & Systems",
    "streaming_strategy": "Streaming Strategy",
    "music_content_strategy": "Music Content Strategy",
    "editorial_content_strategy": "Editorial & Content Strategy",
    "community_growth": "Community Growth",
    "music_partnerships_label_relations": "Music Partnerships & Label Relations",
    "experiential_live_event_production": "Experiential Production / Live Event Production",
    "generic_senior_operator": "Senior Operations Leadership",
}


def _family_key(value: Any) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def known_role_family(value: Any) -> str:
    """Resolve a family key or its display label to a known role family."""
    key = _family_key(value)
    if not key:
        return ""
    for family, label in ROLE_FAMILY_CHOICE_LABELS.items():
        if key in {family, _family_key(label)}:
            return family
    if any(_contains(key.replace("_", " "), phrase) for phrase in (
        "paid media", "media planning", "media buying", "ad operations",
    )):
        return "paid_media"
    return ""


def role_family_confirmation_status(
    application: Mapping[str, Any], intelligence: Mapping[str, Any]
) -> dict[str, Any]:
    """Decide whether a low-confidence inferred role family must be confirmed.

    Fallback inference (keyword guesses) is Medium or Low confidence.  Package
    generation waits until the person either confirms the inferred family for
    this posting or saves a role-family override.
    """
    family = str(intelligence.get("role_family") or "")
    confidence = str(intelligence.get("role_family_confidence_label") or "High")
    needs = bool(intelligence.get("role_family_needs_confirmation"))
    overrides = normalize_role_intelligence_overrides(
        application.get("role_intelligence_overrides")
    )
    confirmation = application.get("role_family_confirmation")
    confirmed_family = (
        str(confirmation.get("role_family") or "") if isinstance(confirmation, Mapping) else ""
    )
    if overrides.get("role_family"):
        resolution = "override"
    elif confirmed_family and confirmed_family == family:
        resolution = "confirmed"
    else:
        resolution = ""
    return {
        "role_family": family,
        "role_family_label": str(
            intelligence.get("role_family_label")
            or ROLE_FAMILY_CHOICE_LABELS.get(family)
            or humanize_identifier(family)
        ),
        "basis": str(intelligence.get("role_family_basis") or ""),
        "confidence_label": confidence,
        "required": needs,
        "resolved": (not needs) or bool(resolution),
        "resolution": resolution,
    }


def _generation_family_for_override(
    overrides: Mapping[str, Any], inferred: Mapping[str, Any]
) -> str:
    """Map free-form editorial labels to an existing conservative writing profile."""
    known = known_role_family(overrides.get("role_family"))
    if known:
        return known
    text = " ".join(
        str(overrides.get(field) or "")
        for field in ("category", "role_family", "primary_hiring_need", "leading_themes")
    ).lower()
    if "music" in text or "label" in text or "artist" in text:
        return "music_partnerships_label_relations"
    if "marketing" in text and ("strategy" in text or "operations" in text):
        return "strategy_gtm_operations"
    if "product" in text and ("strategy" in text or "operations" in text):
        return "product_strategy_ops"
    return str(inferred.get("package_role_family") or "business_operations")


def _intelligence_snapshot(intelligence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: intelligence.get(key)
        for key in (
            "profile_name",
            "source",
            "company_category",
            "company_category_label",
            "role_family",
            "role_family_label",
            "company_voice_label",
            "confidence_label",
        )
        if intelligence.get(key) is not None
    }


def apply_role_intelligence_overrides(
    application: Mapping[str, Any],
    intelligence: Mapping[str, Any],
    role_intent: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Overlay explicit role intelligence while retaining complete inferred provenance."""
    overrides = normalize_role_intelligence_overrides(
        application.get("role_intelligence_overrides")
    )
    resolved_intelligence = deepcopy(dict(intelligence))
    resolved_intent = deepcopy(dict(role_intent))
    inferred_intelligence = _intelligence_snapshot(intelligence)
    inferred_intent = role_intent_snapshot(role_intent)
    generation_family = _generation_family_for_override(overrides, role_intent)

    if overrides.get("company_voice"):
        resolved_intelligence["company_voice_label"] = overrides["company_voice"]
        resolved_intelligence["company_voice_override"] = overrides["company_voice"]
        resolved_intent["effective_company_voice"] = overrides["company_voice"]
    if overrides.get("category"):
        resolved_intelligence["company_category"] = overrides["category"]
        resolved_intelligence["company_category_label"] = overrides["category"]
        resolved_intent["effective_company_category"] = overrides["category"]
    if overrides.get("role_family"):
        resolved_intelligence["role_family"] = overrides["role_family"]
        resolved_intelligence["role_family_label"] = overrides["role_family"]
        resolved_intent["effective_role_family"] = overrides["role_family"]
    if overrides.get("primary_hiring_need"):
        resolved_intent["primary_hiring_need"] = overrides["primary_hiring_need"]
    if overrides.get("leading_themes"):
        resolved_intent["lead_evidence"] = list(overrides["leading_themes"])
    if overrides.get("supporting_themes"):
        resolved_intent["supporting_evidence"] = list(overrides["supporting_themes"])

    if overrides:
        # Keep existing, tested writing profiles in charge of candidate-facing copy.
        # The free-form labels remain visible in the plan and manifest, while the
        # generation family selects conservative, evidence-grounded templates.
        writing = DYNAMIC_ROLE_WRITING.get(generation_family)
        if writing:
            resume = deepcopy(writing)
            resume["headline_profile"] = resume.pop("headline")
            resume["summary_profile"] = resume.pop("summary")
            resume.setdefault("selected_project_limit", 0)
            resume.setdefault("earlier_career_policy", "omit")
            resume.setdefault("target_max_pages", 2)
            resolved_intent["resume"] = resume
        resolved_intent["package_role_family"] = generation_family
        if overrides.get("role_family"):
            resolved_intent["package_role_label"] = overrides["role_family"]
        resolved_intelligence["generation_role_family"] = generation_family
        # A saved override is the active source for UI guidance as well as
        # generation. Keep inferred values only in the provenance snapshots.
        resolved_intelligence["source"] = "saved_override"
        resolved_intelligence["confidence_label"] = "Confirmed"
        if generation_family == "strategy_gtm_operations":
            resolved_intelligence["cover_letter_angle"] = [
                "Connect planning, process design, measurement, and cross-functional execution to the role's stated operating priorities.",
                "Emphasize scalable systems, workflow visibility, and disciplined delivery without importing unrelated mission or editorial themes.",
            ]
            resolved_intelligence["proof_points_to_emphasize"] = [
                "enterprise media operations transformation",
                "workflow governance and cross-functional execution",
                "planning and measurement readiness",
            ]
            resolved_intelligence["proof_points_to_avoid"] = [
                "unrelated nonprofit, mission, or editorial storytelling examples",
            ]

    resolved_intelligence["role_intelligence_overrides"] = overrides
    resolved_intelligence["inferred_role_intelligence"] = inferred_intelligence
    resolved_intent["role_intelligence_overrides"] = overrides
    resolved_intent["inferred_role_intelligence"] = inferred_intelligence
    resolved_intent["inferred_role_intent"] = inferred_intent
    return resolved_intelligence, resolved_intent


def role_intent_snapshot(role_intent: Mapping[str, Any]) -> dict[str, Any]:
    resume = role_intent.get("resume") or {}
    cover = role_intent.get("cover_letter") or {}
    return {
        "mandate": role_intent.get("mandate", ""),
        "primary_archetype": role_intent.get("primary_archetype"),
        "package_role_family": role_intent.get("package_role_family"),
        "package_role_label": role_intent.get("package_role_label"),
        "secondary_archetypes": list(role_intent.get("secondary_archetypes") or []),
        "confidence": role_intent.get("confidence"),
        "primary_hiring_need": role_intent.get("primary_hiring_need"),
        "required_outcomes": list(role_intent.get("required_outcomes") or []),
        "reasoning_signals": list(role_intent.get("reasoning_signals") or []),
        "lead_evidence": list(role_intent.get("lead_evidence") or []),
        "supporting_evidence": list(role_intent.get("supporting_evidence") or []),
        "suppressed_evidence": list(role_intent.get("suppressed_evidence") or []),
        "headline_profile": resume.get("headline_profile"),
        "earlier_career_policy": resume.get("earlier_career_policy"),
        "selected_project_limit": resume.get("selected_project_limit"),
        "target_max_pages": resume.get("target_max_pages"),
        "primary_cover_letter_story": cover.get("primary_story"),
        "secondary_cover_letter_story": cover.get("secondary_story"),
        "generated_greeting": cover.get("greeting"),
        "effective_company_category": role_intent.get("effective_company_category"),
        "effective_company_voice": role_intent.get("effective_company_voice"),
        "effective_role_family": role_intent.get("effective_role_family"),
        "role_intelligence_overrides": normalize_role_intelligence_overrides(
            role_intent.get("role_intelligence_overrides")
        ),
    }


def reconcile_package_role_intelligence(
    intelligence: Mapping[str, Any], role_intent: Mapping[str, Any]
) -> dict[str, Any]:
    """Make dynamic intelligence and package generation expose one role family."""
    resolved = dict(intelligence)
    overrides = normalize_role_intelligence_overrides(
        role_intent.get("role_intelligence_overrides")
    )
    stale_experiential_intent = (
        not overrides
        and str(
            role_intent.get("package_role_family")
            or role_intent.get("primary_archetype")
            or ""
        )
        == "martech_governance_adoption"
        and str(resolved.get("role_family") or "")
        == "experiential_live_event_production"
    )
    family = str(
        resolved.get("role_family")
        if stale_experiential_intent
        else (
            (role_intent.get("package_role_family") if overrides else None)
            or role_intent.get("package_role_family")
            or resolved.get("role_family")
        )
        or "business_operations"
    )
    dynamic_labels = {
        "music_partnerships_label_relations": "Music Partnerships & Label Relations",
        "experiential_live_event_production": "Experiential Production / Live Event Production",
        "strategy_gtm_operations": "Strategy & GTM Operations",
        "paid_media": "Paid Media / Media Planning & Buying",
    }
    label = str(
        (
            None
            if stale_experiential_intent
            else role_intent.get("package_role_label")
        )
        or resolved.get("role_family_label")
        or dynamic_labels.get(family)
        or humanize_identifier(family)
    )
    resolved["dynamic_role_family"] = intelligence.get("role_family")
    resolved["generation_role_family"] = family
    resolved["role_family"] = str(
        role_intent.get("effective_role_family")
        or resolved.get("role_family")
        or family
    )
    resolved["role_family_label"] = str(
        role_intent.get("effective_role_family") or label
    )
    resolved["package_role_archetype"] = role_intent.get("primary_archetype")
    return resolved


def align_role_intent_to_effective_intelligence(
    role_intent: Mapping[str, Any], intelligence: Mapping[str, Any]
) -> dict[str, Any]:
    """Keep candidate-facing writing on the resolved role family.

    Persisted role-intent snapshots are retained for provenance, but a package
    must not let a stale archetype or writing profile override current dynamic
    Role Intelligence. Saved manual overrides remain authoritative.
    """
    resolved = deepcopy(dict(role_intent))
    stale_experiential_intent = (
        str(
            resolved.get("package_role_family")
            or resolved.get("primary_archetype")
            or ""
        )
        == "martech_governance_adoption"
        and str(intelligence.get("role_family") or "")
        == "experiential_live_event_production"
    )
    if normalize_role_intelligence_overrides(
        resolved.get("role_intelligence_overrides")
    ) or not stale_experiential_intent:
        return resolved
    family = str(
        intelligence.get("role_family")
        or resolved.get("effective_role_family")
        or resolved.get("package_role_family")
        or ""
    )
    if not family:
        return resolved
    labels = {
        "music_partnerships_label_relations": "Music Partnerships & Label Relations",
        "experiential_live_event_production": "Experiential Production / Live Event Production",
        "strategy_gtm_operations": "Strategy & GTM Operations",
        "paid_media": "Paid Media / Media Planning & Buying",
    }
    resolved["package_role_family"] = family
    resolved["effective_role_family"] = str(
        intelligence.get("role_family_label") or labels.get(family) or family
    )
    resolved["package_role_label"] = str(
        intelligence.get("role_family_label") or labels.get(family) or family
    )
    writing = DYNAMIC_ROLE_WRITING.get(family)
    if writing:
        resume = deepcopy(writing)
        resume["headline_profile"] = resume.pop("headline")
        resume["summary_profile"] = resume.pop("summary")
        resume.setdefault("selected_project_limit", 0)
        resume.setdefault("earlier_career_policy", "omit")
        resume.setdefault("target_max_pages", 2)
        resolved["resume"] = resume
    return resolved


def tailoring_plan(role_intent: Mapping[str, Any]) -> dict[str, Any]:
    resume = role_intent.get("resume") or {}
    manual_evidence = list(role_intent.get("manual_evidence_projects") or [])
    output_use = role_intent.get("output_use_metadata") or {}
    suppressed = list(role_intent.get("suppressed_evidence") or [])
    if manual_evidence:
        suppressed = [value for value in suppressed if "unrelated" not in str(value).lower()]
    return {
        "detected_role": str(role_intent.get("package_role_label") or "")
        or humanize_identifier(role_intent.get("primary_archetype") or DEFAULT_ARCHETYPE),
        "primary_hiring_need": role_intent.get("primary_hiring_need"),
        "company_voice": role_intent.get("effective_company_voice"),
        "company_category": role_intent.get("effective_company_category"),
        "role_family": role_intent.get("effective_role_family")
        or role_intent.get("package_role_label"),
        "intelligence_overrides": normalize_role_intelligence_overrides(
            role_intent.get("role_intelligence_overrides")
        ),
        "leading_with": humanize_values(role_intent.get("lead_evidence") or []),
        "supporting_with": humanize_values(role_intent.get("supporting_evidence") or []),
        "de_emphasizing": humanize_values(suppressed),
        "earlier_career": humanize_identifier(resume.get("earlier_career_policy")),
        "selected_projects": humanize_values(resume.get("selected_project_ids") or []),
        "selected_relevant_evidence": [
            str(project.get("title") or project.get("name") or "Untitled Evidence")
            for project in manual_evidence
        ],
        "system_recommended_projects": humanize_values(
            resume.get("selected_project_ids") or []
        ),
        "planned_artifact_selections": dict(role_intent.get("planned_artifact_selections") or {}),
        "resume_projects_used": list(output_use.get("resume_projects_used") or []),
        "cover_letter_projects_used": list(
            output_use.get("cover_letter_projects_used") or []
        ),
        "projects_not_used": list(output_use.get("projects_not_used") or []),
        "evidence_score_contribution": dict(
            role_intent.get("evidence_score_contribution") or {}
        ),
        "target_resume_length": f"{int(resume.get('target_max_pages') or 2)} pages maximum",
        "confidence": str(role_intent.get("confidence") or "low").title(),
        "matched_signals": humanize_values(role_intent.get("reasoning_signals") or []),
    }
