import json
from pathlib import Path
from unittest.mock import patch

import app
import pytest

from scripts.evidence_engine import BUILDER_IDS, select_evidence_cards
from scripts.export_docx import DocxExportError, _load_platform_categories, export_ats_docx
from scripts.generate_application_note import _application_note_content
from scripts.generate_cover_letter import _cover_letter_content, load_generation_context
from scripts.generate_messages import _hiring_manager_content, _recruiter_content
from scripts.human_positioning import PERSONAL_PROJECT_TERMS, positioning_violations
from scripts.job_importer import (
    IMPORT_EXTRACTION_FALLBACK_MESSAGE,
    JobImportError,
    import_job_from_url,
)
from scripts.tailor_resume import _render_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _FakeHeaders:
    def __init__(self, content_type="text/html", charset="utf-8"):
        self.content_type = content_type
        self.charset = charset

    def get_content_type(self):
        return self.content_type

    def get_content_charset(self):
        return self.charset


class _FakeResponse:
    def __init__(self, body):
        self.body = body.encode("utf-8")
        self.headers = _FakeHeaders()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def _assert_applicant_safe(content):
    lowered = content.lower()
    for term in PERSONAL_PROJECT_TERMS:
        assert term.lower() not in lowered
    assert not positioning_violations(content)


def test_google_careers_server_rendered_fixture_imports_offline():
    url = "https://www.google.com/about/careers/applications/jobs/results/12345"
    html = """
    <html><head>
      <meta property="og:site_name" content="Google Careers">
      <meta property="og:title" content="Strategy and Operations Lead - Google Careers">
    </head><body><main>
      <h1>Strategy and Operations Lead</h1>
      <h2>About the job</h2>
      <p>This role leads cross-functional strategy and operations for product activation.
      Responsibilities include aligning sales, product, measurement, and regional teams,
      improving operating rhythms, and building clear feedback loops for business decisions.</p>
      <h2>Qualifications</h2>
      <p>Experience solving ambiguous operational problems and working with stakeholders.</p>
    </main></body></html>
    """
    with patch("scripts.job_importer.urlopen", return_value=_FakeResponse(html)):
        imported = import_job_from_url(url)

    assert imported["job_title"] == "Strategy and Operations Lead"
    assert imported["company"] == "Google"
    assert "cross-functional strategy" in imported["job_description"]
    assert imported["source_url"] == url


def test_indeed_json_ld_fixture_imports_offline():
    url = "https://www.indeed.com/viewjob?jk=abc123"
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Director, Business Operations",
        "hiringOrganization": {"name": "Example Media"},
        "jobLocation": {
            "address": {
                "addressLocality": "Los Angeles",
                "addressRegion": "CA",
                "addressCountry": "US",
            }
        },
        "description": (
            "<p>This role leads business operations, cross-functional planning, governance, "
            "and executive communication. Responsibilities include building operating rhythms, "
            "clarifying ownership, and improving measurable delivery across product and marketing teams.</p>"
        ),
        "identifier": {"value": "abc123"},
    }
    html = '<script type="application/ld+json; charset=utf-8">' + json.dumps(posting) + "</script>"
    with patch("scripts.job_importer.urlopen", return_value=_FakeResponse(html)):
        imported = import_job_from_url(url)

    assert imported["job_title"] == "Director, Business Operations"
    assert imported["company"] == "Example Media"
    assert imported["location"] == "Los Angeles, CA, US"
    assert imported["job_id"] == "abc123"
    assert imported["source_name"] == "Indeed"


def test_incomplete_import_preserves_url_and_never_scores():
    url = "https://careers.example.com/jobs/operations-lead"
    state = {"prospect_url": url}

    def incomplete(_url):
        raise JobImportError(
            "No substantive description",
            partial_data={"company": "Example", "job_title": "Operations Lead"},
        )

    with patch.object(app, "score_job_data") as scorer:
        result = app.apply_prospect_url_import_state(state, incomplete)

    assert result["status"] == "partial"
    assert result["message"] == IMPORT_EXTRACTION_FALLBACK_MESSAGE
    assert state["prospect_original_source_url"] == url
    assert state["prospect_company"] == "Example"
    assert state["prospect_role"] == "Operations Lead"
    assert "prospect_match_report" not in state
    scorer.assert_not_called()


def test_direct_intelligence_preview_does_not_score_incomplete_content():
    values = {
        "company": "Example",
        "job_title": "Operations Lead",
        "job_description": "Enable JavaScript to continue.",
        "official_url": "https://careers.example.com/jobs/operations-lead",
    }
    with patch.object(app, "score_job_data") as scorer:
        intelligence = app.detect_prospect_intelligence(values)

    assert intelligence["match_report"]["incomplete_import"] is True
    assert intelligence["match_report"]["match_score"] is None
    scorer.assert_not_called()


def test_personal_projects_require_explicit_evidence_opt_in():
    role = {
        "job_title": "AI Product Operations Lead",
        "company": "Example",
        "raw_text": "AI product workflow automation governance systems operations",
        "keywords": ["AI", "workflow automation", "governance"],
    }
    default_ids = {card["id"] for card in select_evidence_cards(role)}
    opt_in_ids = {
        card["id"]
        for card in select_evidence_cards(role, include_personal_projects=True)
    }

    assert not (default_ids & BUILDER_IDS)
    assert opt_in_ids & BUILDER_IDS


def test_docx_platform_reconstruction_does_not_reintroduce_personal_projects():
    platform_text = " ".join(
        item
        for category in _load_platform_categories(PROJECT_ROOT)
        for item in category["items"]
    )
    _assert_applicant_safe(platform_text)


def test_docx_export_blocks_stale_resume_with_personal_project_evidence(tmp_path):
    source = tmp_path / "unsafe_resume.md"
    source.write_text(
        "# Trisha Lynch\n\n## Profile\n\nCampaignOS is a proof point.\n",
        encoding="utf-8",
    )
    with pytest.raises(DocxExportError, match="Regenerate the tailored resume"):
        export_ats_docx(source, PROJECT_ROOT)


def test_three_existing_prospects_generate_professional_evidence_only():
    jobs = (
        "jobs/strategic_operations_senior_manager_crunchyroll.md",
        "jobs/paramount_director_marketing_operations.md",
        "jobs/senior_copywriter_content_strategist_bandsintown.md",
    )
    for job in jobs:
        context = load_generation_context(job, PROJECT_ROOT)
        resume = _render_markdown(
            context["career_data"],
            context["parsed_job"],
            context["match_report"],
            context["match_report"].get("recommended_resume_profile")
            or "executive_operations",
        )
        materials = (
            resume,
            _cover_letter_content(context),
            _recruiter_content(context),
            _hiring_manager_content(context),
            _application_note_content(context),
        )
        for material in materials:
            _assert_applicant_safe(material)
        assert "## Core Competencies" in resume
        assert "## Professional Experience" in resume
        assert "OMG23 / OMD Entertainment" in resume
        assert any(
            signal in " ".join(materials).lower()
            for signal in ("60+", "400+", "workflow governance", "quality")
        )
