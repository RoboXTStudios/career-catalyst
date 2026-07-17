from pathlib import Path

import app
import pytest

from scripts.evidence_engine import (
    PERSONAL_EVIDENCE_IDS,
    professional_evidence_recommendations,
    select_evidence_cards,
)
from scripts.generate_cover_letter import load_generation_context
from scripts.job_source_registry import normalize_job_source
from scripts.prospect_validation import (
    PROSPECT_HEALTH_STATES,
    compute_prospect_validation_state,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION = (
    "This role leads business operations across product, marketing, and finance teams. "
    "It clarifies ownership, builds practical operating rhythms, improves quality, and "
    "helps cross-functional partners turn ambiguous priorities into measurable delivery."
)
FORBIDDEN_EVIDENCE = ("Career Catalyst", "CampaignOS", "Substack")


def _score(_values, _root):
    return {
        "match_score": 88,
        "match_tier": "Strong Match",
        "recommended_action": "Generate Package",
        "match_summary": "Strong operational alignment.",
        "match_reasons": ["Cross-functional operations"],
        "match_gaps": [],
    }


def _complete_values(**overrides):
    values = {
        "official_url": "https://careers.google.com/jobs/results/123",
        "company": "Google",
        "job_title": "Business Operations Lead",
        "job_description": DESCRIPTION,
        "salary_range": "",
        "posting_date": "",
    }
    values.update(overrides)
    return values


def _intelligence(verification, *, score=88):
    return {
        "role_family": "business_operations",
        "match_report": {"match_score": score},
        "source_verification": verification,
    }


def test_successful_manual_recovery_clears_import_history_and_reconciles_state(monkeypatch):
    monkeypatch.setattr(app, "score_job_data", _score)
    state = {
        "prospect_url_value": "https://careers.google.com/jobs/results/123",
        "prospect_original_source_url": "https://careers.google.com/jobs/results/123",
        "prospect_company": "Google",
        "prospect_role": "Business Operations Lead",
        "prospect_location": "",
        "prospect_salary": "",
        "prospect_posting_date": "",
        "prospect_work_arrangement": "Not specified",
        "prospect_description": DESCRIPTION,
        "prospect_import_result": ("warning", "Old import warning that must disappear."),
        "prospect_intelligence_stale": True,
        "prospect_next_action": "Paste the job description and re-score.",
    }

    refreshed = app.apply_manual_reparse_state(state)

    assert state["prospect_intelligence_stale"] is False
    assert "prospect_import_result" not in state
    assert state["prospect_match_report"]["match_score"] == 88
    assert state["prospect_validation_state"] == refreshed["validation_state"]
    assert state["prospect_validation_state"]["health"] == "Ready to Apply"
    assert state["prospect_validation_state"]["package_ready"] is True
    labels = [item["label"] for item in state["prospect_validation_state"]["posting_verification"]]
    assert "Posting date unavailable." in labels
    assert "Salary information unavailable." in labels
    assert "Description manually supplied by user." in labels
    assert not any("Old import warning" in label for label in labels)


def test_every_reparse_replaces_validation_with_current_content(monkeypatch):
    monkeypatch.setattr(app, "score_job_data", _score)
    first = app.reparse_prospect_fields(_complete_values(description_source="manual"))
    second = app.reparse_prospect_fields(
        _complete_values(job_description="Enable JavaScript to continue.", description_source="manual")
    )

    assert first["validation_state"]["package_ready"] is True
    assert first["validation_state"]["health"] == "Ready to Apply"
    assert second["validation_state"]["package_ready"] is False
    assert second["validation_state"]["health"] == "Incomplete"
    assert second["match_report"]["match_score"] is None


@pytest.mark.parametrize(
    ("url", "source_name"),
    (
        ("https://www.google.com/about/careers/applications/jobs/results/123", "Google Careers"),
        ("https://job-boards.greenhouse.io/example/jobs/123", "Greenhouse"),
        ("https://jobs.ashbyhq.com/example/123", "Ashby"),
        ("https://jobs.lever.co/example/123", "Lever"),
        ("https://example.wd5.myworkdayjobs.com/en-US/jobs/job/123", "Workday"),
        ("https://www.indeed.com/viewjob?jk=123", "Indeed"),
        ("https://www.linkedin.com/jobs/view/123", "LinkedIn"),
        ("https://jobs.smartrecruiters.com/Example/123", "SmartRecruiters"),
        ("https://example.successfactors.com/career?job=123", "SAP SuccessFactors"),
        ("https://careers-example.icims.com/jobs/123", "iCIMS"),
        ("https://example.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/job/123", "Oracle Recruiting / Taleo"),
    ),
)
def test_known_sources_report_recognition_even_when_metadata_is_unavailable(url, source_name):
    verification = normalize_job_source({"official_url": url})

    assert verification["source_name"] == source_name
    assert verification["source_recognition"] == "Known source"
    assert verification["metadata_status"] == "Metadata unavailable"
    assert "Source domain is not recognized" not in verification["source_warnings"]


def test_shared_evidence_defaults_to_professional_proof_and_requires_opt_in():
    role = {
        "company": "Example Robotics",
        "job_title": "AI Operations and Workflow Lead",
        "raw_text": (
            "AI workflow automation, product operations, governance, quality assurance, "
            "cross-functional leadership, and systems implementation"
        ),
    }
    default = professional_evidence_recommendations(role)
    opted_in = select_evidence_cards(role, include_personal_projects=True)
    rendered_default = " ".join(default["labels"] + default["proof_points"])

    assert not (set(default["ids"]) & PERSONAL_EVIDENCE_IDS)
    assert not any(term.lower() in rendered_default.lower() for term in FORBIDDEN_EVIDENCE)
    assert "campaignos" in {card["id"] for card in opted_in}
    assert "career_catalyst" in {card["id"] for card in opted_in}


def test_package_generation_context_and_preview_use_identical_evidence_selection():
    context = load_generation_context(
        "jobs/director_of_matrix_operations_organizational_efficiency_fieldai.md",
        PROJECT_ROOT,
    )
    generation_ids = [card["id"] for card in context["selected_evidence_cards"]]
    preview_ids = context["effective_voice_profile"]["selected_evidence_ids"]
    rendered = " ".join(context["effective_voice_profile"]["proof_points_to_emphasize"])

    assert preview_ids == generation_ids
    assert not any(term.lower() in rendered.lower() for term in FORBIDDEN_EVIDENCE)


@pytest.mark.parametrize(
    ("expected", "values", "verification", "score"),
    (
        (
            "Excellent",
            _complete_values(salary_range="$150,000-$180,000"),
            {"source_recognition": "Known source", "source_name": "Google Careers", "posting_age_days": 3, "requires_verification": False, "verification_status": "Employer Source"},
            88,
        ),
        (
            "Ready to Apply",
            _complete_values(),
            {"source_recognition": "Known source", "source_name": "Google Careers", "posting_age_days": None, "requires_verification": False, "verification_status": "Employer Source"},
            88,
        ),
        (
            "Needs Review",
            _complete_values(official_url="https://jobs.example.invalid/123"),
            {"source_recognition": "Unrecognized source", "source_name": "jobs.example.invalid", "posting_age_days": None, "requires_verification": True, "verification_status": "Not Verified"},
            88,
        ),
        (
            "Incomplete",
            _complete_values(job_description="Too short"),
            {"source_recognition": "Known source", "source_name": "Google Careers", "posting_age_days": None, "requires_verification": False, "verification_status": "Employer Source"},
            None,
        ),
        (
            "Blocked",
            _complete_values(),
            {"source_recognition": "Known source", "source_name": "Google Careers", "posting_age_days": 120, "requires_verification": False, "verification_status": "Stale / Closed Risk"},
            88,
        ),
    ),
)
def test_prospect_health_states(expected, values, verification, score):
    validation = compute_prospect_validation_state(
        values, _intelligence(verification, score=score)
    )

    assert expected in PROSPECT_HEALTH_STATES
    assert validation["health"] == expected


class _FakeStreamlit:
    def __init__(self):
        self.links = []

    def markdown(self, *_args, **_kwargs):
        pass

    def caption(self, *_args, **_kwargs):
        pass

    def link_button(self, label, url, **_kwargs):
        self.links.append((label, url))


def test_open_original_posting_action_is_rendered_when_url_exists():
    fake = _FakeStreamlit()
    validation = compute_prospect_validation_state(_complete_values())

    app._render_prospect_validation(fake, validation)

    assert fake.links == [
        ("Open Original Posting", "https://careers.google.com/jobs/results/123")
    ]
