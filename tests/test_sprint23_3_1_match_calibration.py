from pathlib import Path

from scripts.score_match import _enforce_classification_consistency, score_job_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REDDIT_DESCRIPTION = """Reddit is looking for a dynamic leader to scale our Technical Solutions team. Sitting at the intersection of Sales, Product, and Engineering, the team owns the technical foundation behind campaign delivery, ad signals, issue resolution, and product feedback loops. Their work ensures Reddit's ads products function reliably in-market while supporting GTM readiness and advertiser success.
As Manager, Technical Solutions, you'll lead a high-impact team of Technical Solutions Managers responsible for validating system reliability, resolving complex technical blockers, and optimizing ad tech configurations. You will guide technical execution for Reddit's largest advertiser initiatives, manage feedback loops into Product and Engineering, and drive operational readiness.
This role is required to work in person from our LA office 1-2 days per week.
Supervise and mentor a group of technical solutions managers, providing strategic direction, coaching, and fostering professional growth.
Oversee ads signals enablement, ensuring advertisers successfully integrate key measurement products (pixels and conversions API) and maintain high-quality signals.
Drive strategic, broad-reaching technical initiatives leveraging cross-functional team participation.
Work closely with Sales, Product, and Engineering leads to remove technical obstacles and product constraints that impede revenue growth.
Lead the team in executing advanced diagnostic procedures to troubleshoot and resolve client technical challenges.
Facilitate communication between XFN leads, relaying advertiser insights, recurring technical gaps, and operational feedback to shape product development, tooling, and GTM strategies.
Identify and implement processes and tooling changes to increase team bandwidth, optimize workflows, and scale support models.
Regularly share strategic themes and metrics with leadership team.
8+ years experience in a technical support role or similar. 3+ years in a people management role leading technical ICs. Strong foundational understanding of ad tech ecosystems and signal technologies, including direct experience with pixel implementation and conversions API setups. Experience leveraging AI tools, machine learning workflows, or AI-driven solutions to optimize technical troubleshooting, scale team operations, or analyze complex data sets. Adept at technical troubleshooting, data analysis, and using debugging and diagnostic tools to solve complex systems and data discrepancies. Experience with a data management platform such as Hex, Tableau, Looker, or Sense. Strong cross-functional collaboration skills, with a proven track record of influencing product, engineering, and sales teams."""


def _reddit_values(**overrides):
    values = {
        "official_url": "https://job-boards.greenhouse.io/reddit/jobs/8068464",
        "company": "Reddit",
        "job_title": "Manager, Technical Solutions",
        "location": "Los Angeles, CA",
        "work_arrangement": "Hybrid",
        "salary_range": "$180,200 - $252,300",
        "salary_source": "manual",
        "posting_date": "7/16/2026",
        "job_description": REDDIT_DESCRIPTION,
    }
    values.update(overrides)
    return values


def test_multiple_aligned_dimensions_plus_one_mild_caution_is_not_stretch():
    report = score_job_data(_reddit_values(), PROJECT_ROOT)

    assert report["match_tier"] in {"Good Match", "Strong Match"}
    assert report["recommended_action"] == "Review First"
    assert report["material_fit_gaps"] == []
    assert report["diligence_cautions"] == [
        "Confirm the reporting line and decision authority before generating the package."
    ]
    assert report["score_breakdown"]["base_score"] == 37
    assert report["score_breakdown"]["dimensions"]["functional_alignment"]["score"] == 100
    assert report["score_breakdown"]["penalties"] == []


def test_strong_adjacency_counts_when_prior_title_differs():
    report = score_job_data(_reddit_values(), PROJECT_ROOT)

    assert report["functional_evidence"]["level"] == "Strong functional adjacency"
    assert len(report["functional_evidence"]["adjacent_capabilities"]) >= 3
    assert any(
        "strong functional adjacency" in strength.lower()
        for strength in report["match_strengths"]
    )
    assert report["match_tier"] in {"Good Match", "Strong Match"}


def test_stretch_requires_a_material_gap():
    report = _enforce_classification_consistency(
        {
            "match_score": 64,
            "match_tier": "Stretch Match",
            "match_summary": "Credible alignment with minor questions.",
            "match_strengths": ["Functional alignment", "Compatible compensation"],
            "match_gaps": ["Confirm reporting line."],
            "material_fit_gaps": [],
            "recommended_action": "Review First",
            "score_breakdown": {"final_classification": "Stretch Match"},
        }
    )

    assert report["match_tier"] == "Good Match"
    assert report["classification_consistency"]["consistent"] is True
    assert "no material fit gap" in report["classification_consistency"]["adjustment"].lower()


def test_positive_narrative_and_minor_caution_are_classification_consistent():
    report = score_job_data(_reddit_values(), PROJECT_ROOT)

    assert len(report["match_strengths"]) >= 4
    assert report["material_fit_gaps"] == []
    assert report["classification_consistency"]["consistent"] is True
    assert report["match_tier"] != "Stretch Match"
    assert "stretch" not in report["match_summary"].lower()


def test_genuine_technical_stretch_remains_stretch():
    report = score_job_data(
        {
            "company": "InfraCo",
            "job_title": "Manager, Software Architecture Operations",
            "location": "Los Angeles, CA",
            "work_arrangement": "Hybrid",
            "salary_range": "$180,000",
            "job_description": (
                "Lead strategic operations, campaign operations, marketing technology, measurement, "
                "workflow automation, governance, and cross-functional Product and Engineering "
                "initiatives. Software engineering degree required. Must provide hands-on C++ "
                "development and distributed systems architecture."
            ),
        },
        PROJECT_ROOT,
    )

    assert report["match_tier"] == "Stretch Match"
    assert any("software engineering degree" in gap.lower() for gap in report["material_fit_gaps"])


def test_genuine_enterprise_executive_seniority_stretch_remains_stretch():
    report = score_job_data(
        {
            "company": "Acme",
            "job_title": "Chief Enterprise Operations Officer",
            "location": "Los Angeles, CA",
            "work_arrangement": "Hybrid",
            "salary_range": "$220,000",
            "job_description": (
                "Own enterprise-wide executive ownership and C-suite accountability for global "
                "strategic operations, business operations, transformation, workflow governance, "
                "process automation, and cross-functional delivery across every company division."
            ),
        },
        PROJECT_ROOT,
    )

    assert report["match_tier"] == "Stretch Match"
    assert any("enterprise executive scope" in gap.lower() for gap in report["material_fit_gaps"])


def test_manager_title_is_not_a_level_penalty_against_group_director_history():
    report = score_job_data(_reddit_values(), PROJECT_ROOT)
    seniority = report["score_breakdown"]["dimensions"]["seniority_scope"]

    assert seniority["score"] == 100
    assert any("group director" in strength.lower() for strength in report["match_strengths"])
    assert not any("seniority" in gap.lower() for gap in report["material_fit_gaps"])
