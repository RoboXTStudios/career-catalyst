from __future__ import annotations

import inspect

import app
from scripts.role_interpreter import interpret_role
from scripts.score_match import score_job_data
from scripts.prospect_intake import create_prospect


def _job(title: str, description: str, company: str = "Example") -> dict:
    return {
        "company": company,
        "job_title": title,
        "job_description": description,
        "location": "Los Angeles, CA",
        "work_arrangement": "Hybrid",
        "salary_range": "$180,000-$220,000",
    }


def test_buzzword_heavy_posting_follows_operational_mission_not_boilerplate():
    result = interpret_role(
        _job(
            "Director, Strategic Initiatives",
            """Be a strategic thinker in a fast-paced, ambiguous environment. Drive alignment
            and influence without authority. Build the annual operating plan, prepare decision
            support for leaders, and run the cadence that tracks executive priorities through
            implementation. Coordinate owners and follow through on business planning decisions.""",
        )
    )
    assert result["primary_archetype"] == "Strategic Operations"
    assert "business planning" in result["diagnostics"]["concrete_signals_used"]
    assert "fast-paced" in result["generic_language"]
    assert "strategic thinker" in result["generic_language"]


def test_reddit_technical_solutions_decode_surfaces_real_technical_and_client_scope():
    description = """Reddit is hiring a Manager, Technical Solutions to lead a high-impact team
    of Technical Solutions Managers. The team sits between Sales, Product, and Engineering and
    supports large advertisers. Oversee ads signals enablement so advertisers integrate pixels,
    SDKs, and Conversions API measurement products. Lead advanced diagnostic procedures to
    troubleshoot campaign delivery and resolve client technical challenges. Own product feedback
    loops and operational readiness. 8+ years experience in technical support required, including
    direct pixel implementation and Conversions API setups. Coding experience is preferred."""
    result = interpret_role(_job("Manager, Technical Solutions", description, "Reddit"))
    assert result["primary_archetype"] in {
        "Technical Solutions / Solutions Consulting",
        "Advertising Technology / Ad Operations",
    }
    assert result["secondary_archetype"] in {
        "Technical Solutions / Solutions Consulting",
        "Advertising Technology / Ad Operations",
        None,
    }
    assert "Advertisers" in result["primary_customer_or_stakeholder"]
    assert result["technical_depth"] == "High"
    assert result["people_management_expectation"] == "Required"
    assert result["client_facing_expectation"] in {"Likely", "Required"}
    assert any("APIs, pixels, SDKs" in question for question in result["major_fit_questions"])
    assert result["primary_archetype"] != "General Business Operations"


def test_product_operations_is_distinct_from_product_management():
    product_ops = interpret_role(
        _job(
            "Product Operations Lead",
            "Own launch readiness, product governance, release process, product feedback, and "
            "launch enablement across product and engineering. Improve product adoption workflows.",
        )
    )
    product_manager = interpret_role(
        _job(
            "Product Lead",
            "Own the roadmap and product vision. Conduct user research, define product requirements, "
            "prioritize features, and make product decisions with design and engineering.",
        )
    )
    assert product_ops["primary_archetype"] == "Product Operations"
    assert product_manager["primary_archetype"] == "Product Management"
    assert "roadmap" in product_ops["role_not_to_be_confused_with"].lower()


def test_people_operations_requires_hr_domain_signals():
    result = interpret_role(
        _job(
            "Operations Leader",
            "Administer the HRIS and employee lifecycle, lead workforce planning, maintain people "
            "policies, and support employee relations and benefits administration. Lead a team "
            "cross-functionally in a fast-paced environment.",
        )
    )
    assert result["primary_archetype"] == "People Operations"
    assert "hris" in result["diagnostics"]["concrete_signals_used"]
    assert "General Business Operations" in result["role_not_to_be_confused_with"]


def test_chief_of_staff_identifies_executive_leverage_and_cadence():
    result = interpret_role(
        _job(
            "Chief of Staff",
            "Prepare executive briefings and board materials, provide decision support, run the "
            "leadership cadence, and ensure executive priorities have owners and follow-through.",
        )
    )
    assert result["primary_archetype"] == "Chief of Staff"
    combined = " ".join((result["core_mission"], *result["likely_day_to_day"])).lower()
    assert "decision" in combined
    assert "cadence" in combined
    assert "priorit" in combined


def test_misleading_strategy_title_loses_to_sales_operations_duties():
    result = interpret_role(
        _job(
            "Manager, Commercial Strategy",
            "Own sales forecasting, pipeline management, territory planning, quota planning, "
            "deal desk process, and Salesforce administration. Coordinate weekly sales reviews.",
        )
    )
    assert result["primary_archetype"] == "Revenue Operations"
    assert result["primary_archetype"] != "Strategic Operations"


def test_user_corrected_interpretation_is_source_of_truth_for_scoring(tmp_path):
    job = _job(
        "Strategy Manager",
        "Coordinate project plans, milestones, dependencies, owners, status reporting, and delivery "
        "timelines for sales-process changes. This role works cross-functionally.",
    )
    automatic = interpret_role(job)
    automatic["primary_archetype"] = "Revenue Operations"
    automatic["actual_role_type"] = "Revenue Operations"
    automatic["user_reviewed"] = True
    automatic["user_overrides"] = {"primary_archetype": "Revenue Operations"}
    report = score_job_data({**job, "role_interpretation": automatic}, tmp_path)
    assert report["role_interpretation"]["primary_archetype"] == "Revenue Operations"
    assert report["role_interpretation"]["user_reviewed"] is True
    assert report["interpretation_assessment"]["interpretation_source"] == "user_reviewed"
    assert report["interpretation_assessment"]["primary_archetype_assessed"] == "Revenue Operations"


def test_user_reviewed_interpretation_is_persisted_with_prospect(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "application_tracker.yml").write_text(
        "applications: []\n", encoding="utf-8"
    )
    job = _job(
        "Strategy Manager",
        "This role owns sales forecasting, pipeline management, territory planning, quota planning, and "
        "Salesforce administration. Coordinate sales process improvements and weekly reviews. "
        "Build reporting for sales leaders, maintain pipeline definitions, improve territory data, "
        "and document the operating cadence used for commercial decisions and forecast reviews.",
    )
    reviewed = interpret_role(job)
    reviewed.update(
        {
            "primary_archetype": "Revenue Operations",
            "actual_role_type": "Revenue Operations",
            "user_reviewed": True,
            "user_feedback": "User correction",
            "user_overrides": {"primary_archetype": "Revenue Operations"},
        }
    )
    saved = create_prospect({**job, "role_interpretation": reviewed}, tmp_path)["application"]
    assert saved["role_interpretation"]["primary_archetype"] == "Revenue Operations"
    assert saved["role_interpretation"]["user_reviewed"] is True
    assert saved["interpretation_assessment"]["interpretation_source"] == "user_reviewed"


def test_interpretation_score_consistency_assesses_material_technical_requirements(tmp_path):
    job = _job(
        "Technical Implementation Lead",
        "Hands-on implementation is required. Configure APIs, SDKs, pixels, and integrations; debug "
        "code and troubleshoot customer measurement failures. Own client escalations.",
    )
    report = score_job_data(job, tmp_path)
    interpretation = report["role_interpretation"]
    assessment = report["interpretation_assessment"]
    assert interpretation["technical_depth"] == "High"
    assert "technical_depth" in {item["field"] for item in assessment["dimension_checks"]}
    assert "true_must_haves" in assessment["fields_passed_into_scoring"]
    assert report["score_breakdown"]["interpretation_inputs"]["technical_depth"] == "High"
    assert any("technical depth" in gap.lower() for gap in report["material_fit_gaps"])


def test_missing_details_are_marked_uncertain_without_inventing_scope():
    result = interpret_role(
        _job(
            "Operations Partner",
            "Support important work across the organization. Be results-oriented, collaborative, "
            "and comfortable in a fast-paced, ambiguous environment while driving alignment.",
        )
    )
    assert result["confidence_label"] == "Low"
    assert result["technical_depth"] == "Low"
    assert result["people_management_expectation"] == "Not indicated"
    assert result["client_facing_expectation"] == "Not indicated"
    assert any("not stated" in note.lower() for note in result["interpretation_notes"])
    assert not any("team of" in item.lower() for item in result["likely_day_to_day"])


def test_review_ui_places_interpretation_match_and_strategy_before_cover_angle():
    source = inspect.getsource(app._render_intelligence_preview)
    assert source.index("_render_role_interpretation") < source.index("_match_score_html")
    assert source.index("_match_score_html") < source.index("_render_application_strategy")
    assert source.index("_render_application_strategy") < source.index("cover_letter_angle")
