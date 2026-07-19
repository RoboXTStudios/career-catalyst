from datetime import date, timedelta
from pathlib import Path

import app
import pytest

from scripts.application_tracker import load_application_tracker
from scripts.parse_job import parse_job_description
from scripts.package_context import prospect_context_fingerprint
from scripts.prospect_intake import create_prospect
from scripts.score_match import score_job_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today()
STRONG_DESCRIPTION = (
    "Lead cross-functional technical solutions operations across marketing technology, "
    "analytics, creative, and platform teams. Own programmatic and campaign operations, "
    "measurement workflows, process automation, governance, and translate advertising "
    "platform capabilities into execution and measurement readiness."
)


def _reddit_values(**overrides):
    values = {
        "official_url": "https://job-boards.greenhouse.io/reddit/jobs/123456",
        "company": "Reddit",
        "job_title": "Manager, Technical Solutions",
        "location": "Los Angeles, CA",
        "work_arrangement": "Hybrid",
        "salary_range": "$180,200–$252,300",
        "salary_source": "manual",
        "posting_date": "",
        "source": "Greenhouse",
        "job_description": STRONG_DESCRIPTION,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    "salary",
    (
        "$180,200 - $252,300",
        "$180,200–$252,300",
        "180200 to 252300",
        "$180K–$252K",
        "$180,200",
    ),
)
def test_manual_salary_formats_override_failed_import_for_scoring(salary):
    report = score_job_data(
        _reddit_values(salary_range=salary, salary_source="manual"), PROJECT_ROOT
    )

    assert report["salary_range"] == salary
    assert not any("not disclosed" in gap.lower() for gap in report["match_gaps"])
    assert not any("salary information unavailable" in note.lower() for note in report["verification_notes"])
    assert any("entered manually" in note.lower() for note in report["verification_notes"])


def test_reparse_preserves_reviewed_salary_date_and_arrangement_over_stale_metadata():
    reviewed = _reddit_values(
        posting_date=(TODAY - timedelta(days=3)).isoformat(),
        job_description=(
            "Salary range: Unknown\nPosting date: 2020-01-01\n"
            "Work arrangement: On-site\n" + STRONG_DESCRIPTION
        ),
    )

    refreshed = app.reparse_prospect_fields(reviewed)

    assert refreshed["salary_range"] == "$180,200–$252,300"
    assert refreshed["posting_date"] == reviewed["posting_date"]
    assert refreshed["work_arrangement"] == "Hybrid"
    assert refreshed["match_report"]["salary_range"] == "$180,200–$252,300"
    assert not any("posting date unavailable" in note.lower() for note in refreshed["match_report"]["verification_notes"])


def test_unknown_posting_date_and_salary_are_neutral_to_fit_score_and_tier():
    complete = score_job_data(
        _reddit_values(
            salary_source="imported",
            posting_date=(TODAY - timedelta(days=2)).isoformat(),
        ),
        PROJECT_ROOT,
    )
    incomplete_metadata = score_job_data(
        _reddit_values(salary_range="", salary_source="", posting_date=""),
        PROJECT_ROOT,
    )

    assert incomplete_metadata["match_score"] == complete["match_score"]
    assert incomplete_metadata["match_tier"] == complete["match_tier"]
    assert incomplete_metadata["match_tier"] != "Stretch Match"
    assert incomplete_metadata["data_confidence"] in {"Medium", "Low"}
    assert "Posting date unavailable." in incomplete_metadata["verification_notes"]
    assert "Salary information unavailable." in incomplete_metadata["verification_notes"]
    assert not any("posting" in gap.lower() or "salary" in gap.lower() or "compensation" in gap.lower() for gap in incomplete_metadata["match_gaps"])


def test_manual_posting_date_is_honored_and_age_is_calculated():
    posting_date = (TODAY - timedelta(days=4)).isoformat()
    intelligence = app.detect_prospect_intelligence(_reddit_values(posting_date=posting_date))

    assert intelligence["freshness"]["posting_date"] == posting_date
    assert intelligence["freshness"]["age_days"] == 4
    assert "Posting date unavailable." not in intelligence["match_report"]["verification_notes"]
    labels = [item["label"] for item in intelligence["validation_state"]["posting_verification"]]
    assert "Posting date unavailable." not in labels


def test_preview_labels_fit_gaps_separately_from_posting_verification():
    report = score_job_data(_reddit_values(), PROJECT_ROOT)

    rendered = app._match_score_html(report)

    assert "Fit gaps / cautions" in rendered
    assert "Posting verification" in rendered
    assert "Salary entered manually" in rendered
    assert "Data confidence" in rendered


def test_current_reviewed_form_values_mark_preview_stale_until_explicit_refresh():
    state = {
        "prospect_url_input": _reddit_values()["official_url"],
        "prospect_url_value": _reddit_values()["official_url"],
        "prospect_original_source_url": _reddit_values()["official_url"],
        "prospect_canonical_url": _reddit_values()["official_url"],
        "prospect_company": "Reddit",
        "prospect_role": "Manager, Technical Solutions",
        "prospect_location": "Los Angeles, CA",
        "prospect_salary": "",
        "prospect_salary_source": "",
        "prospect_posting_date": "",
        "prospect_source": "Greenhouse",
        "prospect_priority": "High",
        "prospect_status": "Drafted",
        "prospect_work_arrangement": "On-site",
        "prospect_description": STRONG_DESCRIPTION,
        "prospect_description_source": "imported",
        "prospect_notes": "",
        "prospect_next_action": "Review fit.",
        "prospect_match_report": {"match_score": 1, "match_tier": "Stretch Match"},
        "prospect_role_intelligence": {"match_report": {"match_score": 1}},
        "last_package_result": {"stale": True},
    }

    state["prospect_salary"] = "$180,200–$252,300"
    state["prospect_work_arrangement"] = "Hybrid"
    intelligence = app.refresh_prospect_preview_state(state, "salary_range")

    assert intelligence is None
    assert state["prospect_intelligence_stale"] is True
    assert state["role_analysis_dirty"] is True
    assert state["score_dirty"] is True
    assert state["application_strategy_dirty"] is True
    assert state["package_dirty"] is True
    assert "prospect_match_report" not in state
    assert state["prospect_salary_source"] == "manual"
    assert "last_package_result" not in state


def test_scoring_field_edit_invalidates_package_context_fingerprint():
    values = _reddit_values()
    report = score_job_data(values, PROJECT_ROOT)
    intelligence = {"match_report": report, "role_family": "business_operations"}

    first = prospect_context_fingerprint(values, intelligence)
    second = prospect_context_fingerprint(
        {**values, "salary_range": "$90,000", "salary_source": "manual"},
        {"match_report": score_job_data({**values, "salary_range": "$90,000"}, PROJECT_ROOT), "role_family": "business_operations"},
    )

    assert first != second


def test_import_does_not_overwrite_nonempty_reviewed_salary():
    values = _reddit_values()
    state = {
        "prospect_url_input": values["official_url"],
        "prospect_url_value": values["official_url"],
        "prospect_context_url": values["official_url"],
        "prospect_company": values["company"],
        "prospect_role": values["job_title"],
        "prospect_location": values["location"],
        "prospect_salary": values["salary_range"],
        "prospect_salary_source": "manual",
        "prospect_posting_date": "",
        "prospect_work_arrangement": "Hybrid",
        "prospect_description": values["job_description"],
        "prospect_description_source": "manual",
        "prospect_source": "Greenhouse",
        "prospect_job_id": "",
        "prospect_reviewed_fields": {"salary_range", "job_description"},
    }

    result = app.apply_prospect_url_import_state(
        state,
        importer=lambda _url: {
            **values,
            "salary_range": "Unknown",
            "job_description": "Stale importer description that should not replace reviewed content.",
        },
    )

    assert result["status"] == "success"
    assert state["prospect_salary"] == "$180,200–$252,300"
    assert state["prospect_salary_source"] == "manual"
    assert state["prospect_description"] == STRONG_DESCRIPTION


def test_true_substantive_gap_remains_stretch():
    report = score_job_data(
        {
            "company": "Example Health",
            "job_title": "Manager, Clinical Operations",
            "location": "Los Angeles, CA",
            "work_arrangement": "Hybrid",
            "salary_range": "$150,000",
            "posting_date": (TODAY - timedelta(days=1)).isoformat(),
            "job_description": (
                "Lead strategic operations, workflow automation, process improvement, and "
                "cross-functional teams. Active medical license and registered nurse experience required."
            ),
        },
        PROJECT_ROOT,
    )

    assert report["match_tier"] == "Stretch Match"
    assert any("hard non-fit requirement" in gap.lower() for gap in report["match_gaps"])


def test_save_reopen_preserves_reviewed_values_and_uses_stored_fallbacks(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "jobs").mkdir()
    (tmp_path / "data" / "application_tracker.yml").write_text(
        "applications: []\n", encoding="utf-8"
    )
    first = create_prospect(_reddit_values(posting_date="2026-07-14"), tmp_path)

    second = create_prospect(
        _reddit_values(
            location="",
            work_arrangement="",
            salary_range="",
            salary_source="",
            posting_date="",
        ),
        tmp_path,
    )
    saved = load_application_tracker(tmp_path)[0]
    parsed = parse_job_description(Path(second["job_file_path"]))

    assert first["tracker_id"] == second["tracker_id"]
    assert saved["salary_range"] == "$180,200–$252,300"
    assert saved["posting_date"] == "2026-07-14"
    assert saved["location"] == "Los Angeles, CA"
    assert saved["work_arrangement"] == "Hybrid"
    assert parsed["salary_range"] == "$180,200–$252,300"
    assert parsed["posting_date"] == "2026-07-14"
    assert saved["match_tier"] == first["application"]["match_tier"]
    assert saved["match_score"] == first["application"]["match_score"]
