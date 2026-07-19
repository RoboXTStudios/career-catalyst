from pathlib import Path

import yaml

import app
from scripts.application_strategy import build_application_strategy, build_hiring_manager_lens
from scripts.capability_graph import (
    alignment_score,
    build_alignment_matrix,
    load_capability_graph,
    save_capability_review,
)
from scripts.evidence_profile import (
    add_discovery,
    confirm_discovery,
    discover_evidence,
    evidence_gap_analysis,
    load_evidence_profile,
    query_evidence,
    reject_discovery,
    related_evidence,
    save_evidence_profile,
    select_profile_evidence,
    validate_evidence,
)
from scripts.generate_cover_letter import _cover_letter_content, load_generation_context
from scripts.generate_messages import _profile_hiring_manager_content, _profile_recruiter_content
from scripts.score_match import score_job_match


ROOT = Path(__file__).resolve().parents[1]
REDDIT_JOB = "tests/fixtures/jobs/reddit_manager_technical_solutions.md"
UTA_JOB = "tests/fixtures/jobs/uta_director_people_operations.md"


def test_profile_contains_confirmed_adtech_and_ai_evidence_with_provenance():
    profile = load_evidence_profile(ROOT)
    evidence = {item["id"]: item for item in profile["evidence"]}

    assert len(evidence) >= 25
    assert {
        "campaign_operations_leadership", "cm360", "dv360",
        "server_to_server_conversion_api", "people_leadership",
        "career_catalyst_ai_product", "career_catalyst_responsible_ai",
    } <= set(evidence)
    assert all(not validate_evidence(item) for item in evidence.values())
    assert all(item["provenance"]["where"] for item in evidence.values())
    assert evidence["server_to_server_conversion_api"]["resume_visibility"] == "Intentionally Omitted"
    assert evidence["server_to_server_conversion_api"]["recommended_usage"]["match_scoring"] is True
    assert evidence["server_to_server_conversion_api"]["recommended_usage"]["resume"] is False


def test_discovery_requires_confirmation_and_can_be_rejected(tmp_path):
    profile = {"schema_version": 1, "evidence": [], "discoveries": []}
    proposal = discover_evidence("New operating proof", "Designed a useful operating workflow.")
    proposed = add_discovery(profile, proposal)

    assert proposed["evidence"] == []
    assert proposed["discoveries"][0]["confidence"] == "Medium"
    confirmed = confirm_discovery(proposed, proposal["id"])
    assert confirmed["evidence"][0]["verification_status"] == "User Confirmed"
    assert confirmed["evidence"][0]["confidence"] == "High"

    second = discover_evidence("Unwanted claim", "This should not become evidence.")
    rejected = reject_discovery(add_discovery(confirmed, second), second["id"])
    assert rejected["discoveries"][-1]["status"] == "Rejected"
    save_evidence_profile(rejected, tmp_path)
    assert load_evidence_profile(tmp_path)["evidence"][0]["title"] == "New operating proof"


def test_explorer_filters_and_relationships_are_queryable():
    profile = load_evidence_profile(ROOT)
    results = query_evidence(
        profile, search="CM360", category="Platform Implementation", confidence="High"
    )
    assert {item["id"] for item in results} == {"cm360"}
    assert "dv360" in {item["id"] for item in related_evidence(profile, "cm360")}


def test_capabilities_are_derived_from_multiple_facts_and_reviewed_separately(tmp_path):
    profile = load_evidence_profile(ROOT)
    graph = load_capability_graph(ROOT, profile)
    capabilities = {item["id"]: item for item in graph["capabilities"]}

    assert len(capabilities) >= 41
    assert len(capabilities["implementation_leadership"]["supporting_evidence_ids"]) >= 4
    assert "career_catalyst_ai_product" in capabilities["ai_product_ownership"]["supporting_evidence_ids"]
    assert capabilities["technical_program_leadership_ai"]["strength"] == "Strong Adjacent Experience"
    assert capabilities["ai_product_ownership"]["user_review_status"] == "Derived"

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "capability_graph.yml").write_text(
        yaml.safe_dump({"schema_version": 1, "capability_reviews": []}), encoding="utf-8"
    )
    save_capability_review(
        "ai_product_ownership",
        {"user_review_status": "Confirmed", "strength": "Direct Experience"},
        tmp_path,
    )
    reviewed = load_capability_graph(tmp_path, profile)
    item = next(value for value in reviewed["capabilities"] if value["id"] == "ai_product_ownership")
    assert item["user_review_status"] == "Confirmed"
    assert all(
        value["user_review_status"] == "Derived"
        for value in reviewed["capabilities"]
        if value["id"] != "ai_product_ownership"
    )


def test_hard_gates_receive_zero_credit_and_adjacent_work_receives_configured_credit():
    profile = load_evidence_profile(ROOT)
    graph = load_capability_graph(ROOT, profile)
    rows = build_alignment_matrix(
        [
            "Lead a team of People Operations Specialists",
            "Own HRIS administration and employee relations investigations",
            "Develop production APIs and lead software engineering",
        ],
        graph,
        profile,
    )

    assert rows[0]["alignment_level"] == "Strong Adjacent"
    assert rows[0]["score_credit"] == 0.82
    assert rows[1]["requirement_type"] == "Hard Gate"
    assert rows[1]["alignment_level"] == "Unsupported"
    assert rows[1]["score_credit"] == 0.0
    assert rows[2]["alignment_level"] == "Unsupported"
    assert alignment_score(rows) == 27


def test_uta_uses_adjacent_people_leadership_without_inventing_hr_experience():
    report = score_job_match(UTA_JOB, ROOT)
    matrix = report["capability_graph"]["alignment_matrix"]
    strategy = build_application_strategy(
        report["role_interpretation"],
        build_hiring_manager_lens(
            report["role_interpretation"], matrix, report["evidence_gap_analysis"]
        ),
        report,
    )

    assert report["role_interpretation"]["primary_archetype"] == "People Operations"
    assert any(
        row["alignment_level"] == "Strong Adjacent"
        and "People Leadership" in row["derived_capabilities"]
        for row in matrix
    )
    assert any(row["alignment_level"] == "Unsupported" for row in matrix)
    assert "people_leadership" in report["evidence_profile"]["selected_evidence_ids"]
    assert not any(value.startswith("career_catalyst_") for value in report["evidence_profile"]["selected_evidence_ids"])
    assert "formal hr" not in strategy["strongest_direct_evidence"]


def test_reddit_uses_direct_adtech_proof_and_preserves_engineering_boundary():
    report = score_job_match(REDDIT_JOB, ROOT)
    context = load_generation_context(REDDIT_JOB, ROOT)
    content = _cover_letter_content(context).lower()

    assert report["match_score"] >= 80
    assert all(row["alignment_level"] == "Direct" for row in report["capability_graph"]["alignment_matrix"])
    assert {"cm360", "dv360", "technical_troubleshooting"} <= set(
        report["evidence_profile"]["selected_evidence_ids"]
    )
    assert "cm360" in content and "dv360" in content and "conversion tracking" in content
    assert "solve advertiser implementation challenges" in content
    assert "not software engineering" not in content
    assert "my background is not" not in content
    assert "adjacent" not in content


def test_ai_product_evidence_is_direct_but_ml_engineering_remains_unsupported():
    profile = load_evidence_profile(ROOT)
    graph = load_capability_graph(ROOT, profile)
    role = {
        "job_title": "Director, AI Product Operations",
        "raw_text": "AI product ownership, human-in-the-loop design, AI evaluation, responsible AI, and UAT",
        "primary_archetype": "Product Operations",
    }
    selected = select_profile_evidence(role, profile, usage="match_scoring", max_items=6)
    rows = build_alignment_matrix(
        [
            "Own AI product strategy and human-in-the-loop workflow design",
            "Train machine learning models and own MLOps and cloud architecture",
        ],
        graph,
        profile,
    )

    assert selected[0]["id"] == "career_catalyst_ai_product"
    assert rows[0]["alignment_level"] == "Direct"
    assert rows[1]["requirement_type"] == "Hard Gate"
    assert rows[1]["alignment_level"] == "Unsupported"
    ai_owner = next(item for item in graph["capabilities"] if item["id"] == "ai_product_ownership")
    assert any("sole software-engineering ownership" in value for value in ai_owner["limitations"])


def test_ai_product_public_materials_lead_with_verified_product_ownership():
    job = "tests/fixtures/jobs/ai_product_operations.md"
    context = load_generation_context(job, ROOT)
    cover = _cover_letter_content(context).lower()
    recruiter = _profile_recruiter_content(context).lower()
    hiring_manager = _profile_hiring_manager_content(context).lower()
    combined = "\n".join((cover, recruiter, hiring_manager))

    assert "product owner and domain lead" in cover
    assert "human-in-the-loop" in combined
    assert "directed implementation through codex" in cover
    assert "career catalyst" not in combined
    assert "sole software engineering" not in combined
    assert "model training" not in combined


def test_gap_analysis_keeps_resume_language_confirmation_unsupported_and_absence_separate():
    profile = load_evidence_profile(ROOT)
    profile = {
        **profile,
        "evidence": [
            *profile["evidence"],
            {
                "id": "pending_tableau",
                "title": "Tableau",
                "description": "Possible Tableau reporting experience.",
                "category": "Analytics",
                "evidence_type": "Inferred",
                "verification_status": "Needs Review",
                "confidence": "Medium",
                "resume_visibility": "Not Included",
                "skills": ["Tableau"],
            },
            {
                "id": "unsupported_ml",
                "title": "Machine-learning engineering",
                "description": "No machine-learning engineering evidence.",
                "category": "AI Systems",
                "evidence_type": "Unsupported",
                "verification_status": "Unsupported",
                "confidence": "High",
                "resume_visibility": "Intentionally Omitted",
                "skills": ["machine-learning engineering"],
            },
        ],
    }
    gaps = evidence_gap_analysis(
        ["CM360 implementation", "Tableau reporting", "machine-learning engineering", "licensed attorney"],
        profile,
        resume_text="Campaign operations leadership",
    )

    assert "cm360" in gaps["missing_because_not_on_resume"][0]["evidence_ids"]
    assert gaps["missing_because_needs_confirmation"][0]["evidence_ids"] == ["pending_tableau"]
    assert gaps["missing_because_unsupported"][0]["evidence_ids"] == ["unsupported_ml"]
    assert gaps["missing_because_truly_absent"][0]["requirement"] == "licensed attorney"


def test_ui_exposes_evidence_filters_discovery_and_capability_review_controls():
    source = Path(app.__file__).read_text(encoding="utf-8")
    for phrase in (
        "Evidence & Capabilities", "Evidence Explorer", "Capability Explorer",
        "Awaiting confirmation", "Resume visibility", "Approved usage",
        "Confirm evidence", "Mark Direct", "Mark Adjacent", "Add supporting evidence",
    ):
        assert phrase in source
