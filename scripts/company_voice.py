"""Detect company voice profiles and broad role families from local job data."""

from __future__ import annotations

from typing import Any, Dict, Tuple

try:
    from .dynamic_role_intelligence import (
        ROLE_FAMILIES,
        detect_role_family as infer_role_family,
        get_effective_voice_profile,
    )
except ImportError:
    from dynamic_role_intelligence import (
        ROLE_FAMILIES,
        detect_role_family as infer_role_family,
        get_effective_voice_profile,
    )


ROLE_FAMILY_LABELS = {
    "creative_marketing_ops": "Creative & Marketing Operations",
    "product_marketing": "Product Marketing",
    "product_strategy_ops": "Product Strategy & Operations",
    "transformation_advisory": "Transformation Advisory",
    "music_content_strategy": "Music Content Strategy",
    "ai_operations_systems": "AI Operations & Systems",
    "streaming_strategy": "Streaming Strategy",
    "gtm_product_activation": "GTM Product Activation",
    "business_operations": "Business Operations",
    "editorial_content_strategy": "Editorial & Content Strategy",
    "community_growth": "Community Growth",
    "music_partnerships_label_relations": "Music Partnerships & Label Relations",
    "experiential_live_event_production": "Experiential Production / Live Event Production",
    "strategy_gtm_operations": "Strategy & GTM Operations",
    "generic_senior_operator": "Senior Operations Leadership",
}

PROFILE_LABELS = {
    "disney": "Disney",
    "google_youtube": "Google / YouTube",
    "paramount": "Paramount",
    "uta": "UTA",
    "fieldai": "FieldAI",
    "bandsintown": "Bandsintown",
    "crunchyroll": "Crunchyroll",
}


def _profiles(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    profiles = config.get("company_voice_profiles", config)
    return profiles if isinstance(profiles, dict) else {}


def detect_company_voice_profile(
    company: Any,
    config: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """Return the configured profile key and data for a company name."""
    effective = get_effective_voice_profile(
        company_name=str(company or ""), existing_profiles=config
    )
    profile_key = str(effective["profile_name"])
    if effective["source"] == "known_profile":
        return profile_key, _profiles(config).get(profile_key, effective)
    return profile_key, effective


def detect_role_family(parsed_job: Dict[str, Any]) -> str:
    """Classify a job using its title, company, keywords, and local description text."""
    return infer_role_family(
        str(parsed_job.get("job_title") or ""),
        str(parsed_job.get("raw_text") or ""),
    )


def company_voice_context(
    parsed_job: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Return all reusable voice metadata for one parsed job."""
    effective = get_effective_voice_profile(
        company_name=str(parsed_job.get("company") or ""),
        job_title=str(parsed_job.get("job_title") or ""),
        job_description=str(parsed_job.get("raw_text") or ""),
        source_url=str(parsed_job.get("source_url") or ""),
        existing_profiles=config,
    )
    profile_key = str(effective["profile_name"])
    role_family = str(effective["role_family"])
    return {
        "profile_key": profile_key,
        "company_voice_profile": profile_key,
        "profile": effective,
        "effective_voice_profile": effective,
        "profile_label": PROFILE_LABELS.get(profile_key, profile_key.replace("_", " ").title()),
        "profile_source": effective["source"],
        "company_category": effective["company_category"],
        "role_family": role_family,
        "role_family_label": ROLE_FAMILY_LABELS[role_family],
    }
