import re
from pathlib import Path

from scripts.evidence_engine import load_writing_voice_profile, select_evidence_cards
from scripts.generate_cover_letter import _cover_letter_content, _word_count, load_generation_context
from scripts.generate_messages import _hiring_manager_content, _recruiter_content
from scripts.human_positioning import (
    PROFILE_SUMMARIES,
    evidence_capability_score,
    positioning_violations,
    professional_summary,
)
from scripts.load_data import load_all_yaml
from scripts.parse_job import parse_job_description
from scripts.score_match import score_job_match
from scripts.tailor_resume import _render_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROSPECTS = (
    "jobs/sample_job_description.md",
    "jobs/google_strategy_ops_lead_youtube_auction_brand.md",
    "jobs/paramount_director_marketing_operations.md",
)


def test_every_resume_profile_uses_identity_approach_and_outcome_positioning():
    parsed = {"job_title": "Operations Lead", "company": "Example", "raw_text": "operations"}
    for profile in ("executive_operations", "entertainment_marketing", "music_industry", "product_ai"):
        summary = professional_summary(profile, parsed)
        assert summary == PROFILE_SUMMARIES[profile]
        assert not positioning_violations(summary)
        assert any(term in summary.lower() for term in ("known for", "who turns", "operator", "builder"))
        assert any(term in summary.lower() for term in ("systems", "workflows", "decisions"))


def test_google_summary_leads_with_translation_not_tenure():
    parsed = {
        "job_title": "Strategy and Operations Lead, YouTube Auction Brand",
        "company": "Google",
        "raw_text": "YouTube product activation GTM measurement",
    }
    summary = professional_summary("executive_operations", parsed)
    assert summary == PROFILE_SUMMARIES["google_youtube_operations"]
    assert "translating Google and YouTube platform capabilities" in summary
    assert not positioning_violations(summary)


def test_capability_evidence_outranks_tenure_only_claims():
    capability = {
        "id": "capability",
        "label": "Workflow system",
        "short_description": "A system built to reduce ambiguity and improve governance.",
        "proof_points": ["Designed an AI-enabled validation workflow used by a cross-functional team."],
        "tags": ["governance", "systems_built", "ai_workflows", "ambiguity_reduction"],
        "strongest_role_fits": ["operations"],
        "when_to_use": "Use for operations roles.",
        "when_to_avoid": "Avoid when irrelevant.",
        "confidence_level": "high",
        "source": "test",
    }
    tenure = {
        **capability,
        "id": "tenure",
        "label": "Generic leadership",
        "short_description": "A seasoned executive with 20 years of experience.",
        "proof_points": ["Proven leader with extensive experience."],
        "tags": ["governance"],
    }
    role = {"job_title": "Operations Director", "raw_text": "governance operations", "keywords": []}

    assert evidence_capability_score(capability) > evidence_capability_score(tenure)
    selected = select_evidence_cards(role, [tenure, capability], max_cards=1)
    assert [card["id"] for card in selected] == ["capability"]


def test_existing_prospects_generate_human_low_pressure_narratives():
    banned = load_writing_voice_profile(PROJECT_ROOT)["banned_phrases"]
    for job_path in PROSPECTS:
        context = load_generation_context(job_path, PROJECT_ROOT)
        cover_letter = _cover_letter_content(context)
        recruiter = _recruiter_content(context)
        hiring_manager = _hiring_manager_content(context)
        combined = "\n".join((cover_letter, recruiter, hiring_manager)).lower()

        assert "caught my attention" in combined
        assert "i believe i would be a great fit" not in combined
        assert "if you're the right person" not in combined
        assert not positioning_violations(combined)
        assert all(phrase.lower() not in combined for phrase in banned)
        assert 80 <= _word_count(recruiter) <= 130
        assert 120 <= _word_count(hiring_manager) <= 180
        assert 250 <= _word_count(cover_letter) <= 400


def test_resume_refresh_preserves_plain_ats_sections_and_keyword_coverage():
    career_data = load_all_yaml(PROJECT_ROOT)
    for job_path in PROSPECTS:
        parsed = parse_job_description(PROJECT_ROOT / job_path)
        match = score_job_match(job_path, PROJECT_ROOT)
        resume = _render_markdown(career_data, parsed, match, "executive_operations")
        profile = re.search(r"## Profile\n\n(.+)", resume).group(1)
        competencies = resume.split("## Core Competencies", 1)[1].split("## Platforms", 1)[0]

        assert not positioning_violations(profile)
        assert "## Profile" in resume
        assert "## Core Competencies" in resume
        assert "## Professional Experience" in resume
        assert "| ---" not in resume
        assert len(re.findall(r"^- ", competencies, flags=re.MULTILINE)) >= 8
        assert any(
            str(keyword).lower() in competencies.lower()
            for keyword in parsed.get("keywords", [])
        )
        assert "AI Workflow Design" in resume
