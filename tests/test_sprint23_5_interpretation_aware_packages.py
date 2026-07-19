from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import app
from scripts.application_strategy import (
    build_application_strategy,
    build_hiring_manager_lens,
    interview_preparation_model,
    role_specificity_check,
)
from scripts.evidence_engine import load_evidence_cards, select_evidence_cards
from scripts.dynamic_role_intelligence import build_dynamic_voice_profile
from scripts.generate_cover_letter import (
    _cover_letter_content,
    _word_count,
    load_generation_context,
)
from scripts.prospect_intake import create_prospect
from scripts.role_interpreter import apply_interpretation_overrides, interpret_role
from scripts.score_match import score_job_data
from tests.test_sprint23_3_1_match_calibration import REDDIT_DESCRIPTION


ROOT = Path(__file__).resolve().parents[1]


def _job(title: str, description: str, company: str = "Example") -> dict:
    return {
        "company": company,
        "job_title": title,
        "job_description": description,
        "location": "Los Angeles, CA",
        "work_arrangement": "Hybrid",
        "salary_range": "$180,000-$220,000",
    }


def _reddit_job() -> dict:
    return _job("Manager, Technical Solutions", REDDIT_DESCRIPTION, "Reddit")


def _reddit_context(tmp_path: Path) -> dict:
    job_path = tmp_path / "reddit.md"
    job_path.write_text(
        "# Manager, Technical Solutions\n\n"
        "Company: Reddit\n"
        "Location: Los Angeles, CA\n"
        "Work arrangement: Hybrid\n"
        "Salary range: $180,200 - $252,300\n\n"
        "## Job Description\n\n"
        + REDDIT_DESCRIPTION,
        encoding="utf-8",
    )
    return load_generation_context(job_path, ROOT)


def test_a_primary_technical_solutions_interpretation_drives_reddit_letter(tmp_path):
    context = _reddit_context(tmp_path)
    interpretation = context["role_interpretation"]
    content = _cover_letter_content(context)
    quality = role_specificity_check(
        content, interpretation, context["hiring_manager_lens"]
    )

    assert interpretation["primary_archetype"] == "Technical Solutions / Solutions Consulting"
    assert "advertising technology" in content.lower()
    assert "technical blockers" in content.lower()
    assert "advertiser" in content.lower()
    assert "product" in content.lower() and "engineering" in content.lower()
    assert "senior team operating support" not in content.lower()
    assert quality["valid"] is True
    assert quality["generic_operations_fallback_warning"] is False
    assert 300 <= _word_count(content) <= 400


def test_b_strategic_operations_interpretation_allows_operating_cadence_to_lead():
    interpretation = interpret_role(
        _job(
            "Director, Strategic Operations",
            "Own business planning, decision support, executive priorities, the operating plan, "
            "and strategic initiatives. Build the operating cadence and governance that turns "
            "leadership decisions into accountable cross-functional execution.",
        )
    )
    lens = build_hiring_manager_lens(interpretation)
    content = (
        "I improve executive decision support through business planning and an operating cadence. "
        "My governance systems connect strategic initiatives to clear cross-functional execution."
    )

    assert interpretation["primary_archetype"] == "Strategic Operations"
    assert "executive priorities" in lens["hiring_problem"].lower()
    assert role_specificity_check(content, interpretation, lens)["valid"] is True


def test_c_ranked_ambiguity_and_user_selection_change_scoring_and_strategy(tmp_path):
    automatic = interpret_role(_reddit_job())
    assert len(automatic["ranked_interpretations"]) == 2
    assert automatic["ambiguity_level"] in {"Medium", "High"}
    assert automatic["interpretation_margin"] < 0.3
    assert sum(item["confidence"] for item in automatic["ranked_interpretations"]) == 1.0
    assert [item["rank"] for item in automatic["ranked_interpretations"]] == [1, 2]

    alternate = automatic["secondary_interpretations"][0]["archetype"]
    reviewed = apply_interpretation_overrides(
        automatic,
        {
            "primary_archetype": alternate,
            "user_reviewed": True,
            "feedback": "Use the secondary interpretation",
        },
    )
    report = score_job_data({**_reddit_job(), "role_interpretation": reviewed}, tmp_path)
    lens = build_hiring_manager_lens(report["role_interpretation"])
    strategy = build_application_strategy(report["role_interpretation"], lens, report)

    assert report["interpretation_assessment"]["primary_archetype_assessed"] == alternate
    assert strategy["confirmed_role_interpretation"]["archetype"] == alternate
    assert strategy["strategy_basis"] == "confirmed interpretation"


def test_d_user_override_persists_as_prospect_source_of_truth(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "application_tracker.yml").write_text(
        "applications: []\n", encoding="utf-8"
    )
    interpretation = interpret_role(_reddit_job())
    alternate = interpretation["secondary_interpretations"][0]["archetype"]
    reviewed = apply_interpretation_overrides(
        interpretation,
        {
            "primary_archetype": alternate,
            "plain_english_summary": "An advertiser technology implementation role.",
            "technical_depth": "High",
            "client_facing_expectation": "Required",
            "people_management_expectation": "Required",
            "strategic_vs_execution_balance": "Primarily execution",
            "user_reviewed": True,
        },
    )

    saved = create_prospect(
        {**_reddit_job(), "role_interpretation": reviewed}, tmp_path
    )["application"]

    assert saved["role_interpretation"]["primary_archetype"] == alternate
    assert saved["role_interpretation"]["user_reviewed"] is True
    assert saved["role_interpretation"]["plain_english_summary"] == (
        "An advertiser technology implementation role."
    )
    assert saved["application_strategy"]["confirmed_role_interpretation"]["archetype"] == alternate


def test_e_hiring_manager_lens_is_role_specific_and_labels_fact_vs_inference():
    interpretation = interpret_role(_reddit_job())
    lens = build_hiring_manager_lens(interpretation)
    joined_yes = " ".join(lens["likely_yes_factors"]).lower()
    joined_probes = " ".join(lens["interview_probe_areas"]).lower()

    assert "technical implementation" in joined_yes
    assert "troubleshooting" in joined_yes
    assert "advertising-technology" in joined_probes
    assert all(value.startswith("The posting explicitly requires:") for value in lens["non_negotiables"])
    assert all("likely to care about" in value for value in lens["likely_yes_factors"])
    assert "general operations" in " ".join(lens["likely_hesitations"]).lower()


def test_f_and_g_consistency_gate_rejects_role_mismatch_and_generic_fallback():
    interpretation = interpret_role(_reddit_job())
    lens = build_hiring_manager_lens(interpretation)
    generic = (
        "I provide senior leadership support through operating structures and planning rhythms. "
        "My strengths are ownership clarity, stakeholder alignment, governance without bureaucracy, "
        "communication routines, operational traction, and translating priorities into execution."
    )
    result = role_specificity_check(generic, interpretation, lens)

    assert result["valid"] is False
    assert result["interpretation_package_consistent"] is False
    assert result["generic_operations_fallback_warning"] is True
    assert result["role_specificity_score"] < 50


def test_h_and_i_adjacent_positioning_is_honest_and_unsupported_claims_are_blocked():
    interpretation = interpret_role(_reddit_job())
    lens = build_hiring_manager_lens(interpretation)
    match = {
        "interpretation_assessment": {
            "directly_relevant_evidence": [],
            "adjacent_relevance": ["Advertising-platform activation and measurement readiness"],
        },
        "material_fit_gaps": ["Direct API implementation ownership is unverified."],
    }
    strategy = build_application_strategy(interpretation, lens, match)
    honest = (
        "This technical solutions work connects advertiser measurement and product and engineering "
        "partnership. I would not claim API development or SDK implementation; my evidence is "
        "platform activation, campaign troubleshooting, and measurement readiness."
    )
    invented = (
        "I led technical solutions for customers, built APIs, implemented SDKs, and managed "
        "Solutions Engineers through platform integrations and troubleshooting."
    )

    assert strategy["strongest_direct_evidence"] == []
    assert strategy["strongest_adjacent_evidence"] == [
        "Advertising-platform activation and measurement readiness"
    ]
    assert "do not present general operations" in strategy["honest_boundary"].lower()
    assert role_specificity_check(honest, interpretation, lens)["unsupported_claims_blocked"] == []
    blocked = role_specificity_check(invented, interpretation, lens)
    assert blocked["valid"] is False
    assert {"built apis", "implemented sdks", "managed solutions engineers"}.issubset(
        set(blocked["unsupported_claims_blocked"])
    )


def test_j_role_specific_evidence_selection_changes_with_interpretation():
    cards = load_evidence_cards(ROOT)
    technical = _reddit_job()
    technical["role_interpretation"] = interpret_role(technical)
    strategic = _job(
        "Director, Strategic Operations",
        "Own business planning, decision support, executive priorities, operating cadence, "
        "governance, and cross-functional execution.",
    )
    strategic["role_interpretation"] = interpret_role(strategic)

    technical_ids = [item["id"] for item in select_evidence_cards(technical, cards)]
    strategic_ids = [item["id"] for item in select_evidence_cards(strategic, cards)]

    assert technical_ids[:2] == ["martech_campaign_execution", "governance_qa_delivery"]
    assert strategic_ids[0] == "governance_qa_delivery"
    assert technical_ids != strategic_ids


def test_k_interview_preparation_uses_only_supported_strategy_examples():
    interpretation = interpret_role(_reddit_job())
    lens = build_hiring_manager_lens(interpretation)
    strategy = build_application_strategy(
        interpretation,
        lens,
        {
            "interpretation_assessment": {
                "directly_relevant_evidence": ["Programmatic campaign operations"],
                "adjacent_relevance": ["Google and YouTube measurement readiness"],
            }
        },
    )
    prep = interview_preparation_model(interpretation, lens, strategy)

    assert "advertising-technology" in prep["likely_technical_or_functional_probe"].lower()
    assert prep["examples_to_prepare"] == [
        "Programmatic campaign operations",
        "Google and YouTube measurement readiness",
    ]
    assert prep["questions_to_clarify_role"]


def test_l_single_clear_interpretation_has_no_unnecessary_alternate():
    interpretation = interpret_role(
        _job(
            "Director, People Operations",
            "Own the HRIS, employee lifecycle, employee relations, benefits administration, "
            "workforce planning, people policies, and manager support. Manage the People team.",
        )
    )

    assert interpretation["primary_archetype"] == "People Operations"
    assert len(interpretation["ranked_interpretations"]) == 1
    assert interpretation["secondary_interpretations"] == []
    assert interpretation["ambiguity_level"] == "Low"


def test_m_incomplete_posting_stays_uncertain_and_warns_about_unconfirmed_strategy():
    interpretation = interpret_role(
        _job(
            "Operations Partner",
            "Support important work in a fast-paced environment. Be results-oriented, "
            "collaborative, and comfortable driving alignment through ambiguity.",
        )
    )
    lens = build_hiring_manager_lens(interpretation)
    strategy = build_application_strategy(interpretation, lens)

    assert interpretation["interpretation_confidence"] < 0.6
    assert interpretation["ambiguity_level"] == "High"
    assert "lacks enough concrete" in interpretation["ambiguity_reason"].lower()
    assert interpretation["technical_depth"] == "Low"
    assert interpretation["people_management_expectation"] == "Not indicated"
    assert strategy["unconfirmed_interpretation_warning"]


def test_ui_exposes_alternates_controls_hiring_lens_and_required_order():
    role_source = inspect.getsource(app._render_role_interpretation)
    preview_source = inspect.getsource(app._render_intelligence_preview)

    assert "secondary_interpretations" in role_source
    assert "Use the secondary interpretation" in role_source
    assert "What would change the answer?" in role_source
    assert "Too technical" in role_source
    assert "Too operational" in role_source
    assert "Plain-English role summary" in role_source
    assert preview_source.index("_render_role_interpretation") < preview_source.index("_match_score_html")
    assert preview_source.index("_match_score_html") < preview_source.index("_render_application_strategy")
    assert preview_source.index("_render_application_strategy") < preview_source.index("cover_letter_angle")


def test_application_strategy_resume_emphasis_is_interpretation_specific():
    technical = interpret_role(_reddit_job())
    strategic = interpret_role(
        _job(
            "Director, Strategic Operations",
            "Own business planning, decision support, executive priorities, operating cadence, "
            "governance, and cross-functional execution.",
        )
    )
    technical_strategy = build_application_strategy(
        technical, build_hiring_manager_lens(technical)
    )
    strategic_strategy = build_application_strategy(
        strategic, build_hiring_manager_lens(strategic)
    )

    assert "measurement" in technical_strategy["resume_emphasis"]
    assert "governance" in strategic_strategy["resume_emphasis"]
    assert technical_strategy["resume_emphasis"] != strategic_strategy["resume_emphasis"]
    assert "coding" not in technical_strategy["resume_emphasis"]
    assert "software engineering" not in technical_strategy["resume_emphasis"]


def test_precomputed_interpretation_is_reused_without_reinterpreting():
    interpretation = interpret_role(_reddit_job())
    with patch("scripts.dynamic_role_intelligence.interpret_role") as interpreter:
        profile = build_dynamic_voice_profile(
            company_name="Reddit",
            job_title="Manager, Technical Solutions",
            job_description=REDDIT_DESCRIPTION,
            role_interpretation_result=interpretation,
        )

    interpreter.assert_not_called()
    assert profile["role_interpretation"] == interpretation
