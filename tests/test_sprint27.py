from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import job_importer
from scripts.job_importer import JobImportError, import_job_from_url
from scripts.parse_job import parse_job_description
from scripts.score_match import score_job_data
from scripts.package_context import PackageContextMismatchError, validate_material_context


def greenhouse_payload(title="Head of Programming", job_id=6119486004):
    return {
        "id": job_id,
        "title": title,
        "absolute_url": "https://job-boards.greenhouse.io/mrbeastyoutube/jobs/6119486004",
        "location": {"name": "Los Angeles, CA"},
        "content": """
        <h2>About the Role</h2><p>We are looking for a Head of Programming to build an original content slate.</p>
        <h2>Responsibilities</h2><ul><li>Lead programming strategy, greenlighting recommendations, and multi-format content development.</li><li>Partner with creators, production, analytics, and distribution teams.</li></ul>
        <h2>Requirements</h2><ul><li>Experience owning original programming, audience strategy, and senior creative partnerships.</li></ul>
        <h2>Compensation</h2><p>$200,000 - $260,000</p>
        """,
    }


class FakeHeaders:
    def get_content_type(self):
        return "application/json"

    def get_content_charset(self):
        return "utf-8"


class FakeResponse:
    headers = FakeHeaders()

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        import json
        return json.dumps(self.payload).encode("utf-8")


def fake_urlopen_for(payload, requested):
    def fake(request, timeout=12):
        requested.append(request.full_url)
        return FakeResponse(payload)
    return fake


@pytest.mark.parametrize("url", [
    "https://job-boards.greenhouse.io/mrbeastyoutube/jobs/6119486004?gh_jid=6119486004",
    "https://boards.greenhouse.io/mrbeastyoutube/jobs/6119486004?utm_source=x",
])
def test_greenhouse_supported_urls_extract_board_job_and_beast_fixture(url):
    requested = []
    with patch.object(job_importer, "urlopen", fake_urlopen_for(greenhouse_payload(), requested)):
        imported = import_job_from_url(url)
    assert requested == ["https://boards-api.greenhouse.io/v1/boards/mrbeastyoutube/jobs/6119486004"]
    assert imported["job_title"] == "Head of Programming"
    assert imported["location"] == "Los Angeles, CA"
    assert imported["source_name"] == "Greenhouse"
    assert imported["external_job_id"] == "6119486004"
    assert imported["description_status"] == "Verified"
    assert "greenlighting" in imported["job_description"]
    assert "Google advertising" not in imported["job_description"]


def test_greenhouse_job_id_mismatch_blocks_confident_import():
    with patch.object(job_importer, "urlopen", fake_urlopen_for(greenhouse_payload(job_id=123), [])):
        with pytest.raises(JobImportError):
            import_job_from_url("https://job-boards.greenhouse.io/mrbeastyoutube/jobs/6119486004")


def test_sections_keep_requirements_preferred_and_boilerplate_separate(tmp_path):
    job = tmp_path / "job.md"
    job.write_text("""# Head of Programming
Company: Beast Industries
Location: Los Angeles, CA

## Job Description

## About Us
We value creativity and philanthropy across the company.

## Responsibilities
- Lead original programming slate planning.

## Requirements
- Experience with content greenlighting.

## Preferred Qualifications
- Experience with creator partnerships.

## Equal Employment Opportunity
We are an equal opportunity employer.
""", encoding="utf-8")
    parsed = parse_job_description(job)
    assert parsed["responsibilities"] == ["Lead original programming slate planning."]
    assert parsed["qualifications"] == ["Experience with content greenlighting."]
    assert parsed["preferred_qualifications"] == ["Experience with creator partnerships."]
    assert any("philanthropy" in item for item in parsed["boilerplate_sections"])


def test_role_associated_evidence_enters_scoring_context_without_leaking(tmp_path):
    role = {
        "company": "Beast Industries",
        "job_title": "Head of Programming",
        "location": "Los Angeles, CA",
        "job_description": "Lead audience strategy and analytics-informed programming operations for a creator content slate. Requirements include audience strategy and analytics.",
    }
    evidence = [{"title": "Audience Analytics Operating Review", "actions": "Built analytics-informed audience strategy reviews.", "results": "Improved planning clarity."}]
    with_evidence = score_job_data(role, tmp_path, associated_evidence_projects=evidence)
    without_evidence = score_job_data(role, tmp_path, associated_evidence_projects=[])
    assert with_evidence["associated_evidence_count"] == 1
    assert "Audience Analytics Operating Review" in with_evidence["associated_evidence_project_titles"]
    assert with_evidence["associated_evidence_matches"]
    assert without_evidence["associated_evidence_count"] == 0
    assert without_evidence["associated_evidence_project_titles"] == []


def test_bad_source_data_blocks_confident_score():
    report = score_job_data({"company": "Beast Industries", "job_title": "Head of Programming", "job_description": "Apply now"})
    assert report["match_score"] is None
    assert report["match_tier"] == "Not scored"


def test_package_mismatch_guard_identifies_material_plainly():
    with pytest.raises(PackageContextMismatchError) as error:
        validate_material_context("This Google opportunity focuses on YouTube product activation.", {"company": "Beast Industries", "job_title": "Head of Programming", "job_description": "programming slate"}, "Tailored_Resume")
    assert error.value.material_type == "Tailored_Resume"
    assert "youtube product activation" in error.value.violations


def test_location_los_angeles_is_separate_from_remote_claim():
    imported = greenhouse_payload()["content"]
    assert "Los Angeles, CA" == job_importer._greenhouse_location({"name": "Los Angeles, CA"})
    assert job_importer._work_arrangement("Los Angeles, CA", imported) == "Not specified"
    assert job_importer._work_arrangement("Los Angeles, CA", "Relocation assistance is available.") != "Remote"
