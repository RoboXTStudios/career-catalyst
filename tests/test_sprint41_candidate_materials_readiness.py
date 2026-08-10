"""Sprint 41 candidate-facing readiness and provenance regressions."""

from __future__ import annotations

from pathlib import Path

from scripts.package_generator import generate_package
from scripts.package_quality import evaluate_candidate_facing_quality
from scripts.dynamic_role_intelligence import detect_role_family
from scripts.role_intent import build_role_intent
from scripts.text_cleanup import normalize_candidate_text
from tests.test_sprint35b_document_writing import _isolated_runtime
from tests.test_sprint39_2_experiential_package_generation import (
    _reopened_live_nation_root,
    _select_three_evidence,
)


def _score_canary(_job, _root, associated, **_kwargs):
    if associated:
        return {
            "match_score": 62,
            "match_tier": "Stretch Match",
            "match_summary": "Canonical canary score.",
            "match_strengths": ["Experiential production responsibilities are explicit."],
            "match_gaps": ["Confirm reporting line before applying."],
            "recommended_action": "Review First",
            "confidence": "Medium",
        }
    return {
        "match_score": 62,
        "match_tier": "Stretch Match",
        "match_summary": "Canonical canary score.",
        "match_strengths": ["Experiential production responsibilities are explicit."],
        "match_gaps": ["Confirm reporting line before applying."],
        "recommended_action": "Review First",
        "confidence": "Medium",
    }


def _experiential_metadata() -> dict:
    return {
        "role_intelligence": {
            "effective": {
                "role_family": "Experiential Production / Live Event Production",
            }
        },
        "artifact_usage": {
            "ats_resume": {"used": []},
            "styled_resume": {"used": []},
            "cover_letter": {"used": []},
        },
    }


def test_live_nation_readiness_blocks_unsafe_direct_claims_and_stale_family_language():
    unsafe = (
        "Experiential Production & Live Events Leader. I managed fabrication, venues, production logistics, "
        "onsite execution, and load-out. The role at Company requires MarTech governance and platform implementation."
    )
    result = evaluate_candidate_facing_quality(
        {"ats_resume": unsafe, "cover_letter": unsafe},
        parsed_job={
            "company": "Live Nation Worldwide",
            "job_title": "Experiential Producer",
            "raw_text": "Live Nation seeks an experiential producer to coordinate production, activation, and stakeholder delivery. " * 8,
        },
        tailoring_metadata=_experiential_metadata(),
    )
    assert result["status"] == "BLOCKED"
    assert any("unsupported direct experiential" in reason for reason in result["blocking_reasons"])
    assert any("stale MarTech" in reason for reason in result["blocking_reasons"])
    assert any("placeholder" in reason for reason in result["blocking_reasons"])


def test_live_nation_package_uses_transferable_language_and_selected_evidence(tmp_path: Path, monkeypatch):
    root, tracker_id = _reopened_live_nation_root(tmp_path)
    _select_three_evidence(root, tracker_id)
    monkeypatch.setattr("scripts.package_generator.score_job_match", _score_canary)

    result = generate_package(tracker_id, root, export_root=tmp_path / "exports")
    files = result["manifest"]["files"]
    resume = Path(files["resume_text"]).read_text(encoding="utf-8")
    cover = Path(files["cover_letter"]).read_text(encoding="utf-8")
    summary = Path(files["package_summary"]).read_text(encoding="utf-8")
    candidate_text = "\n".join((resume, cover))

    assert result["package_quality"]["candidate_facing_qa"]["status"] == "PASS"
    assert result["match_score"] == 62
    assert "Senior Operations Leader | Entertainment | Activations" in resume
    assert "transferable to experiential production" in cover
    assert "Live Nation Worldwide" in cover
    assert "MarTech" not in cover
    assert "Experiential Production & Live Events Leader" not in candidate_text
    assert "fabrication" not in candidate_text.lower()
    assert "load-out" not in candidate_text.lower()
    assert "Company" not in cover
    assert "Career Catalyst" not in candidate_text
    assert "Enterprise Media Operations Transformation" in summary
    assert "Operational Workflow Design & Airtable Implementation" in summary
    assert "Enterprise Collaboration Platform Adoption & Stakeholder Enablement" in summary
    assert "Unselected Fallback Evidence" in summary
    assert "- None" in summary


def test_strong_fit_openai_package_remains_confident_and_ready(tmp_path: Path):
    root = _isolated_runtime(
        tmp_path,
        "openai-strong-fit",
        "openai_sales_strategy_operations.md",
        [
            "enterprise_media_operations_transformation",
            "career_catalyst",
            "disney_plus_launch_readiness",
        ],
    )
    result = generate_package("openai-strong-fit", root, export_root=tmp_path / "exports")
    files = result["manifest"]["files"]
    resume = Path(files["resume_text"]).read_text(encoding="utf-8")
    cover = Path(files["cover_letter"]).read_text(encoding="utf-8")
    assert result["package_quality"]["candidate_facing_qa"]["status"] == "PASS"
    assert "Senior Strategy & Operations Leader" in resume
    assert "led 10 direct reports" in (resume + cover)
    assert "CampaignOS" not in cover or "prototype" in cover.lower()
    assert "Company" not in cover


def test_role_family_matrix_keeps_experiential_and_operations_labels_distinct():
    cases = (
        (
            "Live Event Experiential Producer",
            "manage experiential live event production and activation workflows",
            "experiential_live_event_production",
        ),
        (
            "Marketing Operations Lead",
            "marketing operations planning, budgeting, and process optimization",
            "strategy_gtm_operations",
        ),
        (
            "Product Manager, Emerging Formats",
            "product strategy, emerging formats, podcast content lifecycle, roadmap",
            "product_strategy_ops",
        ),
        (
            "Director, Transformation",
            "transformation advisory, consulting, and operating model design",
            "transformation_advisory",
        ),
        (
            "Marketing Operations Integration Lead",
            "marketing operations integration across shared services, multi-brand, and MarTech workflows",
            "creative_marketing_ops",
        ),
    )
    for title, description, family in cases:
        assert detect_role_family(title, description) == family
        intent = build_role_intent(
            {"company": "Example Co", "job_title": title, "raw_text": description}
        )
        assert intent["package_role_family"]
        assert intent["resume"]["headline_profile"]
        assert intent["primary_hiring_need"]


def test_candidate_boundary_decodes_escaped_html_entities():
    assert normalize_candidate_text("Live Nation Media &amp; Sponsorship") == (
        "Live Nation Media & Sponsorship"
    )
    assert normalize_candidate_text("Trisha&#x27;s work") == "Trisha's work"
