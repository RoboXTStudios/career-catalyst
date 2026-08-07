"""Focused Sprint 38 tests for explicit signals and effective overrides."""

from __future__ import annotations

from scripts.dynamic_role_intelligence import (
    build_dynamic_voice_profile,
    detect_role_family,
    extract_seniority,
)
from scripts.role_intent import apply_role_intelligence_overrides, build_role_intent
from scripts.score_match import _seniority_fit


AIRBNB_POSTING = """
Own annual planning, budgeting, forecasting, and resource planning for global
Marketing and Creative. Partner with Finance and Analytics, improve performance
visibility, design scalable processes, and lead executive communication across
Creative and Production workflows.
"""

STARZ_POSTING = """
Lead campaign management and marketing infrastructure across planning, workflows,
governance, accountability, and scalable execution for marketing teams.
"""


def test_airbnb_uses_explicit_marketing_operations_signals():
    profile = build_dynamic_voice_profile(
        "Airbnb", "Marketing Operations Lead", AIRBNB_POSTING
    )
    assert profile["role_family"] == "strategy_gtm_operations"
    assert profile["role_family_label"] == "Marketing Operations / Strategy & Business Operations"
    assert profile["company_category_label"] == "Global Marketing Operations"
    assert profile["company_category"] != "nonprofit_social_impact"
    assert "Creative Marketing Ops" not in profile["role_family_label"]

    intent = build_role_intent(
        {"company": "Airbnb", "job_title": "Marketing Operations Lead", "raw_text": AIRBNB_POSTING}
    )
    assert "planning systems" in intent["primary_hiring_need"]
    assert "marketing operations" in intent["lead_evidence"]
    assert "nonprofit social impact" in intent["suppressed_evidence"]


def test_starz_explicit_campaign_title_and_seniority_win():
    profile = build_dynamic_voice_profile(
        "STARZ Entertainment",
        "VP, Campaign Management & Marketing Infrastructure",
        STARZ_POSTING,
    )
    assert profile["seniority"] == "Vice President"
    assert profile["role_family_label"] == "Marketing Operations / Campaign Management"
    assert profile["company_category_label"] == "Entertainment Marketing"
    assert "campaign-management infrastructure" in build_role_intent(
        {
            "company": "STARZ Entertainment",
            "job_title": "VP, Campaign Management & Marketing Infrastructure",
            "raw_text": STARZ_POSTING,
        }
    )["primary_hiring_need"]
    assert _seniority_fit("VP, Campaign Management & Marketing Infrastructure")[0] == 100


def test_campaign_title_wins_over_conflicting_marketing_operations_body_signals():
    title = "VP, Campaign Management & Marketing Infrastructure"
    posting = (
        "Campaign management, campaign workflows, and scalable execution. "
        "Also partner on marketing operations, analytics, planning, and resource management."
    )
    profile = build_dynamic_voice_profile("STARZ Entertainment", title, posting)
    assert profile["seniority"] == "Vice President"
    assert profile["role_family_label"] == "Marketing Operations / Campaign Management"
    assert profile["company_category_label"] == "Entertainment Marketing"
    intent = build_role_intent(
        {"company": "STARZ Entertainment", "job_title": title, "raw_text": posting}
    )
    assert intent["package_role_label"] == "Marketing Operations / Campaign Management"
    assert "campaign-management infrastructure" in intent["primary_hiring_need"]
    assert "Strategy & Business Operations" not in intent["package_role_label"]


def test_title_seniority_extraction_does_not_hallucinate():
    assert extract_seniority("Senior Director, Digital Activation")["label"] == "Senior Director"
    assert extract_seniority("Director of Media and Sponsorship")["label"] == "Director"
    assert extract_seniority("Senior Manager, Marketing Operations")["label"] == "Senior Manager"
    assert extract_seniority("Operations Partner")["label"] is None


def test_saved_override_is_authoritative_and_clear_restores_inference():
    inferred_i = {
        "source": "dynamic_inference",
        "company_category": "nonprofit_social_impact",
        "company_category_label": "Nonprofit Social Impact",
        "role_family": "creative_marketing_ops",
        "role_family_label": "Creative Marketing Ops",
        "company_voice_label": "Dynamic Nonprofit Social Impact",
    }
    inferred_r = {
        "primary_archetype": "general_operations",
        "package_role_family": "business_operations",
        "package_role_label": "Senior Operations Leadership",
        "primary_hiring_need": "Inferred need",
        "resume": {},
        "cover_letter": {},
    }
    overrides = {
        "company_voice": "Airbnb / global consumer technology marketplace",
        "category": "Global Marketing Operations",
        "role_family": "Marketing Operations / Strategy & Business Operations",
        "primary_hiring_need": "Build scalable marketing operating systems.",
    }
    effective_i, effective_r = apply_role_intelligence_overrides(
        {"role_intelligence_overrides": overrides}, inferred_i, inferred_r
    )
    assert effective_i["source"] == "saved_override"
    assert effective_i["company_category_label"] == "Global Marketing Operations"
    assert effective_i["role_family_label"] == "Marketing Operations / Strategy & Business Operations"
    assert effective_i["inferred_role_intelligence"]["company_category"] == "nonprofit_social_impact"
    assert effective_r["effective_role_family"] == "Marketing Operations / Strategy & Business Operations"
    assert effective_r["primary_hiring_need"] == "Build scalable marketing operating systems."

    cleared_i, cleared_r = apply_role_intelligence_overrides(
        {}, inferred_i, inferred_r
    )
    assert cleared_i["source"] == "dynamic_inference"
    assert cleared_i["company_category"] == "nonprofit_social_impact"
    assert cleared_r["primary_hiring_need"] == "Inferred need"


def test_saved_override_suppresses_inferred_role_warning_in_ui_context():
    from app import prospect_warning_messages

    intelligence = {
        "source": "saved_override",
        "source_verification": {},
        "company_category": "Global Marketing Operations",
        "role_family": "Marketing Operations / Strategy & Business Operations",
        "match_report": {},
    }
    warnings = prospect_warning_messages(intelligence)
    assert not any("role family was inferred" in value.lower() for value in warnings)


def test_saved_override_reaches_package_summary_without_stale_inference(tmp_path):
    from pathlib import Path

    from scripts.application_tracker import update_prospect
    from scripts.package_generator import generate_package
    from tests.test_sprint36_role_intelligence_overrides import (
        _airbnb_overrides,
        _isolated_root,
    )

    root, tracker_id = _isolated_root(tmp_path)
    update_prospect(tracker_id, {"role_intelligence_overrides": _airbnb_overrides()}, root)
    result = generate_package(tracker_id, root, export_root=tmp_path / "exports")
    effective = result["tailoring_metadata"]["role_intelligence"]["effective"]
    assert effective["role_family"] == "Marketing Strategy & Operations"
    summary = Path(result["manifest"]["files"]["package_summary"]).read_text(encoding="utf-8")
    assert "Marketing Strategy & Operations" in summary
    assert "Nonprofit Social Impact" not in summary
    assert "Multiverse" not in summary
