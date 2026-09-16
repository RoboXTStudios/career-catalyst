from __future__ import annotations

import copy
import hashlib
import inspect
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from streamlit.testing.v1 import AppTest

import app
from scripts import job_importer
import scripts.generate_cover_letter as cover_letter_module
import scripts.tailor_resume as resume_module
from scripts.application_tracker import load_application_tracker
from scripts.job_freshness import detect_job_freshness
from scripts.job_importer import _plain_html_text
from scripts.parse_job import extract_metadata, normalize_compensation
from scripts.prospect_intake import create_prospect
from scripts.resume_foundation import (
    canonical_resume_foundation_info,
    load_resume_foundation,
)
from scripts.score_match import score_job_data
from scripts.tailor_resume import _render_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION = (
    "Lead cross-functional business operations, workflow governance, product planning, "
    "quality assurance, and executive stakeholder alignment for a growing media company. "
    "The base salary range is $150,000–$190,000 per year."
)


def _tracker_root(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "application_tracker.yml").write_text(
        yaml.safe_dump({"applications": []}), encoding="utf-8"
    )


def _digest(paths: tuple[Path, ...]) -> dict[Path, str]:
    return {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def test_live_add_prospect_renders_posting_date_and_one_primary_action():
    rendered = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=20).run()
    assert not list(rendered.exception)
    assert "Posting Date" in [widget.label for widget in rendered.text_input]
    labels = [widget.label for widget in rendered.button]
    assert labels.count("Add Prospect") == 1
    assert "Save Prospect + Generate Package" not in labels
    handler = inspect.getsource(app._render_add_prospect)
    assert "generate_package(" not in handler
    assert "generate_dashboard(" not in handler
    assert "run_match_analysis=False" in handler


def test_imported_and_manual_posting_dates_share_persistent_state():
    state = {
        "prospect_url_input": "https://example.com/jobs/42",
        "prospect_context_url": "https://example.com/jobs/42",
        "prospect_role": "",
        "prospect_company": "",
    }
    imported_date = (date.today() - timedelta(days=4)).isoformat()
    app.apply_prospect_url_import_state(
        state,
        lambda _url: {
            "job_title": "Director, Operations",
            "company": "Example",
            "location": "Los Angeles, CA",
            "posting_date": imported_date,
            "job_description": DESCRIPTION,
        },
    )
    assert state["prospect_posting_date"] == imported_date
    assert state["prospect_posting_date_manual_override"] is False

    manual_date = (date.today() - timedelta(days=12)).isoformat()
    state["prospect_posting_date"] = manual_date
    app.mark_posting_date_manual_override(state)
    state["prospect_company"] = "Example Media"
    app.mark_prospect_intelligence_stale(state)
    assert state["prospect_posting_date"] == manual_date
    assert state["prospect_posting_date_manual_override"] is True
    assert detect_job_freshness(f"Posting date: {manual_date}")["age_days"] == 12
    assert detect_job_freshness("No reliable posting date")["category"] == "Unknown freshness"


@pytest.mark.parametrize(
    ("text", "minimum", "maximum", "period"),
    (
        ("$150,000–$190,000", 150000, 190000, "year"),
        ("$150,000 - $190,000", 150000, 190000, "year"),
        ("$150K–$190K", 150000, 190000, "year"),
        ("$150k to $190k", 150000, 190000, "year"),
        ("$72.50–$90.00 per hour", 72.5, 90, "hour"),
        ("Base salary: minimum $150,000 per year", 150000, None, "year"),
        ("The minimum salary is $150,000 per year", 150000, None, "year"),
        ("Salary starts at $150,000 per year", 150000, None, "year"),
        ("Compensation up to $190,000 annually", None, 190000, "year"),
        ("The maximum salary is $190,000 annually", None, 190000, "year"),
    ),
)
def test_normalized_compensation_formats(text, minimum, maximum, period):
    result = normalize_compensation(text)
    assert result["detected"] is True
    assert result["minimum"] == minimum
    assert result["maximum"] == maximum
    assert result["period"] == period
    assert result["currency"] == "USD"


def test_compensation_rejects_unrelated_numbers_and_survives_cleaned_greenhouse_html():
    for unrelated_text in (
        "Managed a $150,000–$190,000 media budget and improved revenue 20%.",
        "Equity valued at $150,000–$190,000.",
        "Job ID $150,000–$190,000.",
        "Bonus opportunity of $150,000–$190,000.",
    ):
        assert normalize_compensation(unrelated_text)["detected"] is False

    cleaned = _plain_html_text(
        "&amp;lt;h2&amp;gt;Compensation&amp;lt;/h2&amp;gt;"
        "&amp;lt;p&amp;gt;$150,000–$190,000 per year&amp;lt;/p&amp;gt;"
    )
    metadata = extract_metadata(cleaned)
    assert "<" not in cleaned
    assert metadata["compensation"]["detected"] is True
    assert metadata["compensation"]["minimum"] == 150000


def test_greenhouse_import_carries_cleaned_compensation_into_intake():
    payload = {
        "id": 6119486004,
        "title": "Head of Programming",
        "absolute_url": "https://job-boards.greenhouse.io/mrbeastyoutube/jobs/6119486004",
        "location": {"name": "Los Angeles, CA"},
        "content": (
            "&amp;lt;h2&amp;gt;Responsibilities&amp;lt;/h2&amp;gt;"
            "&amp;lt;p&amp;gt;Lead programming strategy, content operations, analytics, "
            "production planning, and cross-functional delivery for an original creator slate."
            "&amp;lt;/p&amp;gt;&amp;lt;h2&amp;gt;Compensation&amp;lt;/h2&amp;gt;"
            "&amp;lt;p&amp;gt;$150,000–$190,000 per year&amp;lt;/p&amp;gt;"
        ),
    }
    url = "https://job-boards.greenhouse.io/mrbeastyoutube/jobs/6119486004"
    with patch.object(job_importer, "_fetch_json", return_value=payload):
        imported = job_importer._extract_greenhouse_job(url)
    assert imported is not None
    assert imported["company"] == "Beast Industries"
    assert imported["salary_range"] == "$150,000–$190,000 per year"
    assert imported["compensation"]["minimum"] == 150000
    assert "<" not in imported["job_description"]


def test_detected_compensation_prefills_and_manual_override_wins():
    state = {
        "prospect_description": DESCRIPTION,
        "prospect_salary": "",
        "prospect_salary_auto_value": "",
        "prospect_salary_manual_override": False,
        "prospect_posting_date": "",
        "prospect_posting_date_auto_value": "",
        "prospect_posting_date_manual_override": False,
    }
    app.apply_detected_intake_metadata(state)
    assert state["prospect_salary"] == "$150,000–$190,000 per year"

    state["prospect_salary"] = "$175,000 minimum"
    app.mark_compensation_manual_override(state)
    app.apply_detected_intake_metadata(state)
    assert state["prospect_salary"] == "$175,000 minimum"
    assert state["prospect_salary_manual_override"] is True


def test_saved_compensation_warning_details_and_score_share_one_result(tmp_path):
    _tracker_root(tmp_path)
    compensation = normalize_compensation("$150,000–$190,000", source="manual", manual_override=True)
    with patch("scripts.prospect_intake.import_job_from_url") as importer, patch(
        "scripts.prospect_intake.score_job_match"
    ) as scorer:
        saved = create_prospect(
            {
                "company": "Example Media",
                "job_title": "Director, Operations",
                "job_description": DESCRIPTION,
                "official_url": "https://example.com/jobs/director-operations",
                "posting_date": date.today().isoformat(),
                "salary_range": compensation["display"],
                "compensation": compensation,
                "compensation_manual_override": True,
            },
            tmp_path,
            run_match_analysis=False,
        )
    importer.assert_not_called()
    scorer.assert_not_called()
    record = load_application_tracker(tmp_path)[0]
    assert record["salary_range"] == compensation["display"]
    assert record["compensation_minimum"] == 150000
    assert record["compensation_maximum"] == 190000
    assert record["compensation_manual_override"] is True
    assert record["posting_date"] == date.today().isoformat()
    assert not (tmp_path / "exports").exists()
    assert not record.get("package_manifest")
    assert not record.get("material_paths")
    assert saved["tracker_id"] == "example_media_director_operations"

    intelligence = {
        "compensation": compensation,
        "job_description": DESCRIPTION,
        "source_verification": {},
        "freshness": {},
        "location": "Los Angeles, CA",
    }
    messages = app.prospect_warning_messages(intelligence)
    assert not any("could not be confirmed" in message for message in messages)


def test_scoring_uses_saved_normalized_compensation():
    compensation = normalize_compensation("$150k to $190k")
    report = score_job_data(
        {
            "company": "Example Media",
            "job_title": "Director, Operations",
            "location": "Los Angeles, CA",
            "job_description": DESCRIPTION,
            "salary_range": compensation["display"],
            "compensation": compensation,
            "posting_date": date.today().isoformat(),
        },
        PROJECT_ROOT,
    )
    assert report["salary_range"] == compensation["display"]


def test_resume_and_cover_letter_share_explicit_immutable_foundation():
    info = canonical_resume_foundation_info(PROJECT_ROOT)
    assert info["name"] == "Career Catalyst structured career dataset"
    assert info["supplemental_evidence_source"] == "data/evidence_projects.yml"
    assert resume_module.load_resume_foundation is cover_letter_module.load_resume_foundation

    foundation_paths = tuple(PROJECT_ROOT / path for path in info["baseline_files"])
    before = _digest(foundation_paths)
    career_data = load_resume_foundation(PROJECT_ROOT)
    evidence = [
        {
            "id": "role-proof",
            "title": "Role Proof",
            "employer": "Example",
            "actions": "Built a verified workflow.",
            "results": "Improved planning clarity.",
        }
    ]
    original_evidence = copy.deepcopy(evidence)
    resume = _render_markdown(
        career_data,
        {
            "company": "Example",
            "job_title": "Operations Director",
            "raw_text": "operations governance workflow quantum teleportation",
            "keywords": ["operations", "governance", "quantum teleportation"],
        },
        {"keyword_matches": [], "transferable_strengths": []},
        "executive_operations",
        evidence,
    )
    assert "Advanced through five roles" in resume
    assert "Senior Operations & Transformation Leader" in resume
    assert "Role Proof" in resume
    assert "quantum teleportation" not in resume.lower()
    assert evidence == original_evidence
    assert _digest(foundation_paths) == before


def test_role_scoped_evidence_does_not_become_foundation():
    foundation = load_resume_foundation(PROJECT_ROOT)
    baseline = _render_markdown(
        foundation,
        {"company": "Example", "job_title": "Operations Director", "raw_text": "operations"},
        {"keyword_matches": [], "transferable_strengths": []},
        "executive_operations",
        [],
    )
    assert "Unrelated Role Evidence" not in baseline
    assert "## Selected Projects" not in baseline
