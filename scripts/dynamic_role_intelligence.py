"""Deterministic company, role, and voice inference for any local prospect."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

try:
    from .load_data import load_yaml_file
except ImportError:
    from load_data import load_yaml_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]

COMPANY_CATEGORIES = (
    "music_live_events",
    "music_entertainment_operations",
    "entertainment_streaming",
    "talent_agency_media",
    "gaming_fandom",
    "ai_technology_startup",
    "product_technology",
    "marketing_advertising",
    "nonprofit_social_impact",
    "generic_business_operations",
)

ROLE_FAMILIES = (
    "creative_marketing_ops",
    "product_marketing",
    "product_strategy_ops",
    "transformation_advisory",
    "music_content_strategy",
    "ai_operations_systems",
    "streaming_strategy",
    "gtm_product_activation",
    "business_operations",
    "editorial_content_strategy",
    "community_growth",
    "music_partnerships_label_relations",
    "experiential_live_event_production",
    "strategy_gtm_operations",
    "generic_senior_operator",
)


def extract_seniority(job_title: str = "") -> dict[str, str | None]:
    """Extract only seniority stated explicitly in the title.

    This intentionally does not infer seniority from responsibilities or company
    language.  The compact result is safe for UI provenance and diagnostics.
    """
    title = " ".join(str(job_title or "").split())
    lowered = title.lower()
    patterns = (
        ("Vice President", r"\b(?:vice\s+president|vp)\b"),
        ("Senior Director", r"\bsenior\s+director\b"),
        ("Director", r"\bdirector\b"),
        ("Senior Manager", r"\bsenior\s+(?:manager|mgr)\b"),
        ("Manager", r"\bmanager\b"),
        ("Lead", r"\blead\b"),
        ("Principal", r"\bprincipal\b"),
        ("Chief", r"\bchief\b"),
        ("Head", r"\bhead\s+of\b"),
    )
    for label, pattern in patterns:
        if re.search(pattern, lowered):
            return {"label": label, "source": "explicit_title"}
    return {"label": None, "source": "not_explicit"}

CATEGORY_SIGNALS = {
    "music_live_events": (
        "bandsintown",
        "concert",
        "live music",
        "live events",
        "touring",
        "venue",
        "festival",
        "ticketing",
        "fan community",
        "event production",
        "promoter",
    ),
    "music_entertainment_operations": (
        "warner music group",
        "warner chappell",
        " wmg ",
        "record label",
        "music publishing",
        "music company",
        "music industry",
    ),
    "talent_agency_media": (
        "united talent agency",
        "talent agency",
        "artist representation",
        "client advisory",
        "agency clients",
        "agents",
    ),
    "gaming_fandom": (
        "playstation",
        "gaming",
        "video game",
        "game studio",
        "players",
        "game development",
    ),
    "ai_technology_startup": (
        "fieldai",
        "artificial intelligence",
        "ai startup",
        "robotics",
        "automation",
        "machine learning",
        "matrix operations",
        "organizational efficiency",
    ),
    "nonprofit_social_impact": (
        "nonprofit",
        "non-profit",
        "foundation",
        "social impact",
        "mission-driven",
        "mission driven",
        "humanitarian",
        "public benefit",
    ),
    "entertainment_streaming": (
        "disney",
        "paramount",
        "crunchyroll",
        "streaming",
        "studios",
        "entertainment",
        "franchise",
        "theatrical",
        "content slate",
    ),
    "product_technology": (
        "youtube",
        "product platform",
        "product activation",
        "seller enablement",
        "product adoption",
        "software platform",
        "product and technology",
        "engineering",
    ),
    "marketing_advertising": (
        "marketing operations",
        "advertising",
        "campaign",
        "media agency",
        "creative operations",
        "brand marketing",
        "martech",
    ),
}

CATEGORY_GUIDANCE = {
    "music_live_events": {
        "tone": ["music-aware", "human", "editorial", "community-minded"],
        "cover_letter_angle": [
            "connect music and audience understanding with editorial judgment and reliable content systems",
            "balance creative voice with operational discipline across artists, partners, fans, and live discovery",
        ],
        "proof_points": [
            "Multiverse editorial leadership",
            "RoboXT Studios creative and publishing systems",
            "entertainment marketing and campaign operations",
        ],
        "avoid": [
            "unsupported label, artist management, or music journalism claims",
            "language that reads like fan mail",
        ],
    },
    "music_entertainment_operations": {
        "tone": ["music-aware", "strategic", "systems-minded", "operational"],
        "cover_letter_angle": [
            "connect music and entertainment experience with operational transformation, integration, and scalable execution",
            "show how strategy becomes clear processes, systems, ownership, and cross-functional operating rhythms",
        ],
        "proof_points": [
            "entertainment marketing and campaign operations",
            "cross-functional leadership and workflow transformation",
            "CampaignOS systems thinking and operational visibility",
        ],
        "avoid": [
            "assuming a live-events focus without touring, venue, ticketing, fan-community, or event-production evidence",
            "unsupported label or music-publishing experience claims",
        ],
    },
    "entertainment_streaming": {
        "tone": ["entertainment-aware", "strategic", "audience-aware", "operational"],
        "cover_letter_angle": [
            "connect theatrical and streaming entertainment experience with franchise/IP priorities and scalable execution",
            "show how cross-functional strategy becomes clear operating rhythms for creative and business teams",
        ],
        "proof_points": [
            "Disney Studios Theatrical and Disney Streaming/DSS campaign operations",
            "cross-functional leadership across creative, media, analytics, and technology",
            "CampaignOS workflow governance and visibility",
        ],
        "avoid": ["invented familiarity with current titles, teams, or company priorities"],
    },
    "talent_agency_media": {
        "tone": ["advisory", "sharp", "media-fluent", "stakeholder-aware"],
        "cover_letter_angle": [
            "connect media, marketing, advertising, and technology fluency with advisory thinking and practical execution",
            "emphasize operating models, stakeholder recommendations, and strategy carried through implementation",
        ],
        "proof_points": [
            "senior stakeholder and external partner management",
            "cross-functional operating model and workflow design",
            "CampaignOS as transformation translated into a working system",
        ],
        "avoid": ["unsupported client relationships or consulting claims"],
    },
    "gaming_fandom": {
        "tone": ["creative", "product-aware", "fandom-aware", "operational"],
        "cover_letter_angle": [
            "connect entertainment IP and creative execution with product development workflows and operating rhythms",
            "show respect for creative work while bringing milestone, capacity, and cross-functional clarity",
        ],
        "proof_points": [
            "premium entertainment and franchise/IP campaign execution",
            "leadership of 10 direct reports across an integrated 64-person organization",
            "workflow governance, milestones, and quality standards",
        ],
        "avoid": ["unsupported gaming studio or game development experience"],
    },
    "ai_technology_startup": {
        "tone": ["systems-minded", "AI-forward", "practical", "startup-aware"],
        "cover_letter_angle": [
            "connect organizational clarity with matrix operations, capacity visibility, automation, and accountable execution",
            "show where AI workflow systems improve decisions without replacing human judgment",
        ],
        "proof_points": [
            "CampaignOS AI-powered workflow governance and quality assurance",
            "schema-driven validation, dashboards, and operational reporting",
            "leadership across complex cross-functional teams",
        ],
        "avoid": ["presenting automation as a substitute for organizational judgment"],
    },
    "product_technology": {
        "tone": ["product-aware", "precise", "data-fluent", "strategic"],
        "cover_letter_angle": [
            "connect product priorities with adoption, feedback loops, stakeholder alignment, and measurable execution",
            "show an ability to translate user and business needs into clear operating systems",
        ],
        "proof_points": [
            "CampaignOS product and systems design",
            "platform activation and measurement readiness",
            "cross-functional alignment across business, analytics, and technology",
        ],
        "avoid": ["unsupported product ownership or employment claims"],
    },
    "marketing_advertising": {
        "tone": ["clear", "creative-operations-aware", "practical", "commercial"],
        "cover_letter_angle": [
            "position marketing operations as the connective layer between strategy, creative work, measurement, and delivery",
            "emphasize workflows, capacity, dashboards, quality, and high-volume campaign execution",
        ],
        "proof_points": [
            "large-scale entertainment marketing operations",
            "workflow governance and cross-functional execution standards",
            "CampaignOS dashboards, validation, and AI enablement",
        ],
        "avoid": ["over-indexing on narrow ad operations terminology"],
    },
    "nonprofit_social_impact": {
        "tone": ["mission-aware", "human", "thoughtful", "practical"],
        "cover_letter_angle": [
            "connect mission clarity with stakeholder alignment, thoughtful communication, and dependable operations",
            "show how scalable systems can protect human-centered work and improve organizational focus",
        ],
        "proof_points": [
            "cross-functional leadership and stakeholder communication",
            "Multiverse editorial leadership and employee storytelling",
            "workflow governance and scalable operating standards",
        ],
        "avoid": ["invented nonprofit experience or personal connection to the mission"],
    },
    "generic_business_operations": {
        "tone": ["warm", "senior", "specific", "operational"],
        "cover_letter_angle": [
            "connect the role's stated priorities with cross-functional clarity, scalable systems, and reliable execution",
            "lead with the strongest job-description themes rather than unsupported company assumptions",
        ],
        "proof_points": [
            "leadership of 10 direct reports across an integrated 64-person organization",
            "workflow governance and execution standards",
            "CampaignOS systems thinking and operational visibility",
        ],
        "avoid": ["unsupported claims about the company's culture, customers, or internal priorities"],
    },
}

ROLE_GUIDANCE = {
    "experiential_live_event_production": {
        "tone": ["experiential", "production-minded", "calm", "execution-focused"],
        "angle": "connect live-event and experiential production management with budgets, timelines, vendors, venues, logistics, and onsite delivery",
        "proof_points": ["production management and execution standards", "creative-production coordination", "cross-functional stakeholder and vendor coordination"],
    },
    "music_partnerships_label_relations": {
        "tone": ["music-aware", "partner-centered", "commercial", "senior"],
        "angle": "connect label relations and music partnerships with trusted partner management, negotiation, and cross-functional delivery",
        "proof_points": ["Just for Us Podcast", "RoboXT Studios", "enterprise media operations transformation"],
    },
    "strategy_gtm_operations": {
        "tone": ["analytical", "commercial", "precise", "operational"],
        "angle": "connect strategy and operations with GTM planning, pipeline governance, forecasting, and executive decisions",
        "proof_points": ["enterprise media operations transformation", "Career Catalyst", "Disney+ launch readiness"],
    },
    "music_content_strategy": {
        "tone": ["editorial", "music-aware", "human"],
        "angle": "connect music culture and audience understanding with voice, content strategy, and repeatable editorial systems",
        "proof_points": ["Multiverse", "RoboXT Studios", "entertainment marketing experience"],
    },
    "editorial_content_strategy": {
        "tone": ["editorial", "clear", "audience-aware"],
        "angle": "connect writing and editorial judgment with content planning, voice systems, and cross-functional delivery",
        "proof_points": ["Multiverse", "RoboXT Studios", "content and campaign systems"],
    },
    "transformation_advisory": {
        "tone": ["advisory", "structured", "stakeholder-aware"],
        "angle": "translate a clear transformation hypothesis into an operating model, stakeholder recommendation, and executable plan",
        "proof_points": ["stakeholder alignment", "workflow governance", "CampaignOS"],
    },
    "product_strategy_ops": {
        "tone": ["product-aware", "strategic", "data-fluent"],
        "angle": "align product, technology, data, and business priorities through decisions, roadmaps, OKRs, and operating rhythms",
        "proof_points": ["CampaignOS product thinking", "executive operating clarity", "technology partnerships"],
    },
    "product_marketing": {
        "tone": ["audience-aware", "product-aware", "clear", "commercial"],
        "angle": "connect audience insight and product value with positioning, messaging, go-to-market plans, launch readiness, product education, enablement, and adoption",
        "proof_points": ["entertainment marketing delivery", "launch readiness and adoption", "audience and stakeholder communications"],
    },
    "gtm_product_activation": {
        "tone": ["precise", "commercial", "product-aware"],
        "angle": "connect product priorities with GTM activation, seller enablement, adoption, feedback loops, and measurable learning",
        "proof_points": ["platform activation", "measurement readiness", "large advertiser execution"],
    },
    "ai_operations_systems": {
        "tone": ["systems-minded", "AI-forward", "practical"],
        "angle": "improve matrix operations through capacity visibility, operating cadences, dashboards, automation, and thoughtful governance",
        "proof_points": ["CampaignOS", "AI workflow design", "validation and reporting systems"],
    },
    "business_operations": {
        "tone": ["clear", "practical", "senior"],
        "angle": "create ownership, capacity visibility, decision cadence, and reliable execution across business functions",
        "proof_points": ["cross-functional leadership", "workflow governance", "operational reporting"],
    },
    "creative_marketing_ops": {
        "tone": ["creative-operations-aware", "clear", "practical"],
        "angle": "connect creative and marketing priorities with workflow, capacity, quality, and dependable delivery",
        "proof_points": ["entertainment marketing operations", "creative workflows", "CampaignOS"],
    },
    "streaming_strategy": {
        "tone": ["streaming-aware", "audience-aware", "strategic"],
        "angle": "turn streaming, content, franchise/IP, and audience priorities into a strategy teams can execute",
        "proof_points": ["theatrical and streaming operations", "franchise/IP execution", "cross-functional systems"],
    },
    "community_growth": {
        "tone": ["community-minded", "human", "growth-aware"],
        "angle": "connect audience insight and community trust with clear programs, content, measurement, and sustainable growth",
        "proof_points": ["Multiverse community storytelling", "RoboXT Studios creative systems", "audience campaign experience"],
    },
    "generic_senior_operator": {
        "tone": ["warm", "senior", "specific"],
        "angle": "connect the role's stated priorities with strategic clarity, stakeholder alignment, and reliable execution",
        "proof_points": ["cross-functional leadership", "workflow governance", "CampaignOS"],
    },
}


def _normalize(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _dedupe(values: Iterable[Any]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _profiles(existing_profiles: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if existing_profiles is None:
        existing_profiles = _load_default_profiles()
    profiles = existing_profiles.get("company_voice_profiles", existing_profiles)
    return profiles if isinstance(profiles, dict) else {}


@lru_cache(maxsize=1)
def _load_default_profiles() -> Dict[str, Any]:
    return load_yaml_file("config/company_voice_profiles.yml", PROJECT_ROOT)


def _known_profile_match(
    company_name: str,
    existing_profiles: Optional[Dict[str, Any]],
) -> Optional[Tuple[str, Dict[str, Any], str]]:
    company_key = _normalize(company_name)
    if not company_key:
        return None
    exact_matches = []
    fuzzy_matches = []
    for profile_name, profile in _profiles(existing_profiles).items():
        if not isinstance(profile, dict):
            continue
        for alias in profile.get("companies", []):
            alias_key = _normalize(alias)
            if not alias_key:
                continue
            if company_key == alias_key:
                exact_matches.append((len(alias_key), str(profile_name), profile, "exact"))
                continue
            phrase_match = f" {alias_key} " in f" {company_key} "
            similarity = SequenceMatcher(None, company_key, alias_key).ratio()
            if phrase_match or similarity >= 0.84:
                fuzzy_matches.append(
                    (max(len(alias_key), int(similarity * 100)), str(profile_name), profile, "fuzzy")
                )
    matches = exact_matches or fuzzy_matches
    if not matches:
        return None
    _score, profile_name, profile, match_type = max(matches, key=lambda item: item[0])
    return profile_name, profile, match_type


def _combined_text(*values: Any) -> str:
    return _normalize(" ".join(str(value or "") for value in values))


def _contains_phrase(text: str, signal: str) -> bool:
    """Match normalized words or phrases without firing inside unrelated words."""
    return f" {_normalize(signal)} " in f" {_normalize(text)} "


def _category_scores(text: str) -> Dict[str, int]:
    padded = f" {text} "
    return {
        category: sum(
            1 for signal in signals if f" {_normalize(signal)} " in padded
        )
        for category, signals in CATEGORY_SIGNALS.items()
    }


def infer_company_context(
    company_name: str = "",
    job_title: str = "",
    job_description: str = "",
    source_url: str = "",
) -> Dict[str, Any]:
    """Infer a broad company category without network access or external models."""
    text = _combined_text(company_name, job_title, job_description, source_url)
    company_key = _normalize(company_name)
    scores = _category_scores(text)
    precedence = (
        "music_live_events",
        "music_entertainment_operations",
        "talent_agency_media",
        "gaming_fandom",
        "ai_technology_startup",
        "nonprofit_social_impact",
        "entertainment_streaming",
        "product_technology",
        "marketing_advertising",
    )
    company_overrides = (
        ("music_live_events", ("bandsintown", "live nation", "ticketmaster")),
        ("music_entertainment_operations", ("warner music group", "warner chappell", "wmg")),
        ("talent_agency_media", ("united talent agency", " uta ", "creative artists agency")),
        ("gaming_fandom", ("playstation", "riot games", "xbox", "nintendo")),
        ("ai_technology_startup", ("fieldai", "field ai")),
        ("entertainment_streaming", ("disney", "paramount", "crunchyroll", "netflix")),
        ("product_technology", ("google", "youtube")),
    )
    category = next(
        (
            value
            for value, signals in company_overrides
            if any(_contains_phrase(company_key, signal) for signal in signals)
        ),
        "",
    )
    top_score = max(scores.values(), default=0)
    if not category:
        category = next(
            (value for value in precedence if scores.get(value) == top_score and top_score > 0),
            "generic_business_operations",
        )
    matched_signals = [
        signal
        for signal in CATEGORY_SIGNALS.get(category, ())
        if f" {_normalize(signal)} " in f" {text} "
    ]
    confidence = 0.38 if not text else min(0.88, 0.52 + (0.08 * len(matched_signals)))
    if category == "generic_business_operations":
        summary = "No specialized company-category signals were strong enough, so the role text will lead the guidance."
    else:
        signal_text = ", ".join(matched_signals[:4]) or "role and company language"
        summary = f"The available text points to {category} through signals including {signal_text}."
    return {
        "company_category": category,
        "confidence": round(confidence, 2),
        "matched_signals": matched_signals,
        "reasoning_summary": summary,
    }


def detect_role_family(job_title: str = "", job_description: str = "") -> str:
    """Infer one role family from title-first, deterministic rules."""
    title = _normalize(job_title)
    description = _normalize(job_description)
    combined = f"{title} {description}"
    music_context = any(
        signal in combined
        for signal in ("music", "artist", "concert", "tour", "venue", "fan", "festival")
    )
    operations_context = any(
        signal in combined
        for signal in (
            "operations", "operational", "strategy", "strategic", "integration",
            "transformation", "systems", "process", "workflow",
        )
    )
    music_operations_company = any(
        signal in combined
        for signal in (
            "warner chappell", "warner music", "music publishing", "record label", "music company"
        )
    )
    wmg_context = any(
        signal in combined for signal in ("warner chappell", "warner music", " wmg ")
    )
    explicit_product_strategy = any(
        signal in combined
        for signal in (
            "product roadmap",
            "roadmap ownership",
            "product lifecycle",
            "feature prioritization",
            "feature prioritisation",
            "product management",
            "product strategy",
            "product planning",
            "product requirements",
            "product org",
            "product organization",
        )
    )
    product_marketing_title = any(
        _contains_phrase(title, signal)
        for signal in (
            "product marketing", "product marketing manager",
            "product marketing lead", "product marketing director",
        )
    )
    product_operations_title = any(
        _contains_phrase(title, signal)
        for signal in ("product operations", "product ops")
    )

    # Explicit operational responsibilities outrank broad creative, mission, or
    # company-theme signals.  Keep the existing family vocabulary so all current
    # writing profiles and package consumers remain compatible.
    campaign_management_title = any(
        signal in title
        for signal in ("campaign management", "campaign infrastructure")
    )
    marketing_operations_title = any(
        signal in title
        for signal in ("marketing operations", "marketing-operations", "marketing ops")
    )
    marketing_operations_signals = (
        "annual planning", "budgeting", "forecasting", "resource planning",
        "resource allocation", "operating system", "process design",
        "process optimization", "finance", "analytics", "global marketing",
        "creative production", "scalable process", "performance visibility",
    )
    experiential_title = (
        ("producer" in title and any(
            signal in title
            for signal in ("experiential", "live event", "event producer", "experiential production")
        ))
        or "experiential production manager" in title
        or ("executive producer" in title and "experiential" in title)
        or "experiential project manager" in title
    )
    production_signals = (
        "experiential producer", "experiential production", "live event producer",
        "live event production", "event producer", "event production",
        "production management", "branded activation", "brand activation",
        "experiential activation", "sponsorship activation", "fabrication",
        "venue search", "venue sourcing", "onsite production", "on site production",
        "load in", "load out", "production budget", "production budgets",
        "production timeline", "production timelines", "vendor management",
        "production logistics", "on site builds", "onsite builds",
        "production schedule", "venue management",
    )
    production_hits = [signal for signal in production_signals if _contains_phrase(combined, signal)]
    production_density = len(production_hits)
    if product_marketing_title:
        return "product_marketing"
    if product_operations_title:
        return "product_strategy_ops"
    if campaign_management_title:
        return "strategy_gtm_operations"
    if (experiential_title and production_density >= 2) or (
        production_density >= 5
        and any(_contains_phrase(combined, signal) for signal in (
            "event production", "experiential production", "production management",
            "fabrication", "onsite production", "production logistics",
        ))
    ):
        return "experiential_live_event_production"
    if (
        marketing_operations_title
        and not any(signal in title for signal in ("integration", "shared services", "multi-brand"))
        and any(signal in combined for signal in marketing_operations_signals)
    ):
        return "strategy_gtm_operations"
    if "label relations" in title or (
        "music partnerships" in combined and any(signal in title for signal in ("manager", "lead", "director"))
    ):
        return "music_partnerships_label_relations"
    if any(signal in title for signal in ("sales strategy operations", "sales strategy and operations")):
        return "strategy_gtm_operations"

    if (wmg_context or (music_operations_company and "integration operations" in title)) and operations_context and any(
        signal in title
        for signal in ("operations", "integration", "transformation", "strategy")
    ):
        return "business_operations"

    if any(
        signal in title
        for signal in (
            "operations director",
            "director of operations",
            "business operations",
            "studio operations",
            "strategic operations",
            "program operations",
            "product operations",
            "cross functional operations",
            "cross-functional operations",
        )
    ) and not explicit_product_strategy:
        return "business_operations"

    if any(
        signal in title
        for signal in ("copywriter", "content strategist", "editorial", "content marketing", "content strategy")
    ):
        return "music_content_strategy" if music_context else "editorial_content_strategy"
    if any(signal in title for signal in ("marketing operations", "creative operations", "campaign operations", "brand operations")):
        return "creative_marketing_ops"
    if any(signal in title for signal in ("matrix operations", "organizational efficiency", "ai operations")):
        if any(
            _contains_phrase(combined, signal)
            for signal in ("ai", "artificial intelligence", "automation", "robotics", "startup")
        ):
            return "ai_operations_systems"
        return "business_operations"
    if any(signal in title for signal in ("transformation", "advisory", "consultant", "consulting")):
        return "transformation_advisory"
    if "creative" in title and "operations" in title:
        return "creative_marketing_ops"
    if any(signal in title for signal in ("product", "technology")) and (
        explicit_product_strategy or any(signal in combined for signal in ("strategy", "roadmap", "okr"))
    ) and any(
        signal in combined for signal in ("strategy", "operations", "roadmap", "okr")
    ):
        return "product_strategy_ops"
    if (
        any(
            signal in combined
            for signal in ("seller enablement", "product activation", "product adoption")
        )
        or any(signal in title for signal in ("gtm", "go to market"))
    ):
        return "gtm_product_activation"
    product_marketing_responsibilities = sum(
        1
        for signal in (
            "product positioning", "positioning and messaging", "product messaging",
            "go to market strategy", "go-to-market strategy", "product education",
            "product marketing strategy", "product launch", "sales enablement",
        )
        if _contains_phrase(description, signal)
    )
    if product_marketing_responsibilities >= 2:
        return "product_marketing"
    if any(signal in combined for signal in ("streaming", "franchise", "content slate", "studios")) and any(
        signal in title for signal in ("strategy", "operations", "initiatives")
    ):
        return "streaming_strategy"
    if any(signal in combined for signal in ("community", "audience growth", "fan growth", "member growth")):
        return "community_growth"
    if any(signal in combined for signal in ("transformation", "advisory", "operating model", "consultant", "consulting")):
        return "transformation_advisory"
    if any(signal in combined for signal in ("matrix operations", "organizational efficiency", "capacity planning", "operating cadence")):
        if any(
            _contains_phrase(combined, signal)
            for signal in ("ai", "artificial intelligence", "automation", "robotics", "startup")
        ):
            return "ai_operations_systems"
        return "business_operations"
    if any(signal in combined for signal in ("marketing operations", "creative operations", "campaign workflow", "campaign operations")):
        return "creative_marketing_ops"
    if any(signal in title for signal in ("strategy operations", "strategy and operations")):
        return "business_operations"
    if any(signal in title for signal in ("product operations", "product strategy")) and explicit_product_strategy:
        return "product_strategy_ops"
    if (
        any(signal in combined for signal in ("roadmap", "okr", "product", "technology"))
        and any(signal in title for signal in ("strategy", "operations", "director", "lead"))
        and explicit_product_strategy
    ):
        return "product_strategy_ops"
    if any(signal in title for signal in ("business operations", "strategic operations", "strategy operations", "integration operations", "operations director", "chief of staff", "program operations")):
        return "business_operations"
    if any(signal in title for signal in ("marketing", "creative", "brand", "campaign")):
        return "creative_marketing_ops"
    if any(signal in title for signal in ("director", "head", "lead", "vice president", "vp", "chief")):
        return "generic_senior_operator"
    return "generic_senior_operator"


def _proof_guidance(company_category: str, role_family: str) -> Tuple[list[str], list[str]]:
    category = CATEGORY_GUIDANCE[company_category]
    role = ROLE_GUIDANCE[role_family]
    emphasize = _dedupe((*category["proof_points"], *role["proof_points"]))
    avoid = _dedupe(category["avoid"])
    return emphasize, avoid


def _effective_proof_guidance(company_category: str, role_family: str) -> Tuple[list[str], list[str]]:
    """Keep experiential roles grounded in production proof rather than generic music content."""
    emphasize, avoid = _proof_guidance(company_category, role_family)
    if role_family == "experiential_live_event_production":
        emphasize = [
            "production management and execution standards",
            "creative-production coordination",
            "cross-functional stakeholder and vendor coordination",
            "budget and timeline management",
            "venue, fabrication, and onsite logistics",
        ]
        avoid = _dedupe((*avoid, "unrelated editorial or content systems", "MarTech campaign execution"))
    return emphasize, avoid


def build_dynamic_voice_profile(
    company_name: str = "",
    job_title: str = "",
    job_description: str = "",
    source_url: str = "",
) -> Dict[str, Any]:
    """Build normalized local voice guidance for an unknown company."""
    context = infer_company_context(company_name, job_title, job_description, source_url)
    category = context["company_category"]
    role_family = detect_role_family(job_title, job_description)
    category_guidance = CATEGORY_GUIDANCE[category]
    role_guidance = ROLE_GUIDANCE[role_family]
    emphasize, proof_avoid = _effective_proof_guidance(category, role_family)
    is_music_operations = category == "music_entertainment_operations" and role_family in {
        "business_operations", "product_strategy_ops", "transformation_advisory", "generic_senior_operator"
    }
    confidence_label = "High" if context["confidence"] >= 0.8 else "Medium"
    explicit_seniority = extract_seniority(job_title)
    normalized_title = _normalize(job_title)
    normalized_text = _combined_text(job_title, job_description)
    if role_family == "experiential_live_event_production":
        category_label = "Music / Live Events & Experiential"
        family_label = "Experiential Production / Live Event Production"
        voice_label = "Music + Experiential Production"
    elif role_family == "product_marketing":
        category_label = (
            "Music / Entertainment Operations"
            if category == "music_entertainment_operations"
            else category.replace("_", " ").title()
        )
        family_label = "Product Marketing"
        voice_label = f"Dynamic {category.replace('_', ' ').title()}"
    elif role_family == "strategy_gtm_operations" and any(
        signal in normalized_title
        for signal in ("campaign management", "campaign infrastructure")
    ):
        category_label = "Entertainment Marketing"
        family_label = "Marketing Operations / Campaign Management"
        voice_label = "Entertainment Marketing Operations"
    elif role_family == "strategy_gtm_operations" and "marketing operations" in normalized_text:
        category_label = "Global Marketing Operations"
        family_label = "Marketing Operations / Strategy & Business Operations"
        # Keep the inferred voice label generic; a saved company-voice override
        # remains the only authoritative candidate-facing company voice.
        voice_label = f"Dynamic {category.replace('_', ' ').title()}"
    elif role_family == "strategy_gtm_operations" and "campaign management" in normalized_text:
        category_label = "Entertainment Marketing"
        family_label = "Marketing Operations / Campaign Management"
        voice_label = "Entertainment Marketing Operations"
    else:
        category_label = (
            "Music / Entertainment Operations"
            if category == "music_entertainment_operations"
            else category.replace("_", " ").title()
        )
        family_label = "Strategic Operations" if is_music_operations else role_family.replace("_", " ").title()
        voice_label = "Music + Operational Transformation" if is_music_operations else f"Dynamic {category.replace('_', ' ').title()}"
    cover_letter_angles = _dedupe((*category_guidance["cover_letter_angle"], role_guidance["angle"]))
    if role_family == "experiential_live_event_production":
        cover_letter_angles = [
            "connect experiential production with disciplined budgets, timelines, vendors, venues, and onsite execution",
            "balance creative activation goals with reliable production workflows, logistics, and cross-functional delivery",
        ]
    return {
        "profile_name": f"dynamic_{category}",
        "company_name": str(company_name or "").strip(),
        "source": "dynamic_inference",
        "company_category": category,
        "role_family": role_family,
        "seniority": explicit_seniority["label"],
        "seniority_source": explicit_seniority["source"],
        "tone": _dedupe((*category_guidance["tone"], *role_guidance["tone"])),
        "cover_letter_angle": cover_letter_angles,
        "proof_points_to_emphasize": emphasize,
        "proof_points_to_avoid": proof_avoid,
        "avoid": _dedupe(category_guidance["avoid"]),
        "confidence": context["confidence"],
        "confidence_label": confidence_label,
        "reasoning_summary": context["reasoning_summary"],
        "company_voice_label": voice_label,
        "company_category_label": category_label,
        "role_family_label": family_label,
    }


def detect_company_voice(
    company_name: str,
    job_title: str = "",
    job_description: str = "",
    existing_profiles: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Detect a known voice profile or return deterministic dynamic guidance."""
    return get_effective_voice_profile(
        company_name=company_name,
        job_title=job_title,
        job_description=job_description,
        existing_profiles=existing_profiles,
    )


def get_effective_voice_profile(
    company_name: str = "",
    job_title: str = "",
    job_description: str = "",
    source_url: str = "",
    existing_profiles: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a normalized known or dynamically inferred voice profile."""
    dynamic = build_dynamic_voice_profile(
        company_name, job_title, job_description, source_url
    )
    match = _known_profile_match(company_name, existing_profiles)
    if match is None:
        return dynamic

    profile_name, profile, match_type = match
    category = dynamic["company_category"]
    role_family = dynamic["role_family"]
    emphasize, proof_avoid = _effective_proof_guidance(category, role_family)
    confidence = 0.99 if match_type == "exact" else 0.9
    article = "an" if match_type == "exact" else "a"
    return {
        "profile_name": profile_name,
        "company_name": str(company_name or "").strip(),
        "source": "known_profile",
        "company_category": category,
        "role_family": role_family,
        "tone": _dedupe(profile.get("tone", dynamic["tone"])),
        "cover_letter_angle": _dedupe(
            (*profile.get("cover_letter_angle", []), *dynamic["cover_letter_angle"])
        ),
        "proof_points_to_emphasize": emphasize,
        "proof_points_to_avoid": proof_avoid,
        "avoid": _dedupe((*profile.get("avoid", []), *dynamic["avoid"])),
        "confidence": confidence,
        "confidence_label": "High" if confidence >= 0.8 else "Medium",
        "reasoning_summary": (
            f"Matched {company_name or 'the company'} to the configured {profile_name} profile "
            f"using {article} {match_type} company-name match; role text maps to {role_family}."
        ),
        "company_voice_label": dynamic.get("company_voice_label", profile_name),
        "company_category_label": dynamic.get("company_category_label", category.replace("_", " ").title()),
        "role_family_label": dynamic.get("role_family_label", role_family.replace("_", " ").title()),
    }
