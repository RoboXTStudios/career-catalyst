import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evidence_engine import (
    load_evidence_cards,
    load_writing_voice_profile,
    select_evidence_cards,
)
from scripts.generate_cover_letter import _cover_letter_content


def ids(cards):
    return {card["id"] for card in cards}


def role(title, raw_text, **extra):
    data = {"job_title": title, "company": "Example Co", "raw_text": raw_text, "keywords": []}
    data.update(extra)
    return data


def test_evidence_card_loading_structure():
    cards = load_evidence_cards()
    assert cards
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
    assert all(required <= set(card) for card in cards)


def test_entertainment_role_selects_disney_and_omits_builder_defaults():
    selected = select_evidence_cards(role("Director, Entertainment Marketing Operations", "streaming theatrical campaign marketing operations Disney stakeholder coordination"))
    selected_ids = ids(selected)
    assert "omg23_disney_leadership" in selected_ids
    assert "campaignos" not in selected_ids
    assert "roboxt_studios" not in selected_ids


def test_traditional_pmo_omits_roboxt_and_campaignos():
    selected = select_evidence_cards(role("Senior PMO Lead", "traditional PMO governance delivery risk QA executive reporting"))
    selected_ids = ids(selected)
    assert "governance_qa_delivery" in selected_ids
    assert "roboxt_studios" not in selected_ids
    assert "campaignos" not in selected_ids


def test_builder_friendly_role_includes_builder_projects():
    selected = select_evidence_cards(role("Builder in Residence", "Human Agency builder founder startup AI workflow automation product operations"))
    selected_ids = ids(selected)
    assert {"campaignos", "career_catalyst"} <= selected_ids


def test_martech_role_can_include_campaignos_when_relevant():
    selected = select_evidence_cards(role("Martech Operations Lead", "CRM martech adtech automation measurement campaign workflow systems"))
    selected_ids = ids(selected)
    assert "martech_campaign_execution" in selected_ids
    assert "campaignos" in selected_ids


def test_default_writing_voice_level_is_three_and_bans_corporate_phrases():
    profile = load_writing_voice_profile()
    assert profile["level"] == 3
    assert profile["default_level"] == 3
    assert "proven track record" in profile["banned_phrases"]
    assert "cutting-edge" in profile["banned_phrases"]


def dynamic_context(parsed_job, selected_cards):
    return {
        "parsed_job": parsed_job,
        "effective_voice_profile": {
            "source": "dynamic_inference",
            "role_family": "business_operations",
            "cover_letter_angle": ["strengthen governance and delivery clarity"],
        },
        "profile_key": "default",
        "role_family": "business_operations",
        "selected_evidence_cards": selected_cards,
    }


def body_paragraphs(content):
    return [p for p in content.split("\n\n") if p not in {"Hello,", "Best", "Trisha Lynch"}]


def test_dynamic_cover_letter_blocks_banned_corporate_phrases_and_repetitive_patterns():
    parsed = role("Senior Operations Lead", "governance delivery stakeholder alignment")
    content = _cover_letter_content(dynamic_context(parsed, select_evidence_cards(parsed)))
    lowered = content.lower()
    for phrase in load_writing_voice_profile()["banned_phrases"]:
        assert phrase not in lowered
    starts = [paragraph.split()[0:3] for paragraph in body_paragraphs(content) if paragraph.split()]
    assert len(starts) == len({tuple(start) for start in starts})
    assert lowered.count("the role stood out because") == 0
    assert lowered.count("practical challenge underneath") == 0


def test_no_unsupported_low_confidence_builder_claim_for_pmo_cover_letter():
    parsed = role("Senior PMO Lead", "traditional PMO governance delivery risk QA executive reporting")
    selected = select_evidence_cards(parsed)
    content = _cover_letter_content(dynamic_context(parsed, selected)).lower()
    assert "roboxt" not in content
    assert "launched agency" not in content
    assert "campaignos" not in content


def test_ea_marketing_operations_cover_letter_uses_grounded_interview_voice():
    parsed = role(
        "Senior Manager, Marketing Operations",
        "Electronic Arts entertainment marketing operations campaign governance QA stakeholder visibility dependencies milestones risks decisions",
    )
    context = {
        "parsed_job": parsed,
        "profile_key": "default",
        "role_family": "creative_marketing_ops",
        "effective_voice_profile": {"source": "dynamic_inference", "company_category": "gaming"},
    }
    content = _cover_letter_content(context)
    lowered = content.lower()

    for phrase in (
        "enable great work",
        "best work together",
        "genuine enthusiasm",
        "i would be excited",
        "built my career around",
        "giving complex initiatives a clear plan",
        "clear plan",
    ):
        assert phrase not in lowered

    assert "omg23 / omd entertainment" in lowered
    assert "disney theatrical and streaming campaigns" in lowered
    assert lowered.index("omg23 / omd entertainment") < lowered.index("campaignos")
    assert lowered.count("campaignos") <= 2
    assert "supporting example" in lowered
    assert "main throughline is still the disney and omg23 operating experience" in lowered
    assert "i would welcome the chance" in lowered
    assert "excitement" not in lowered
