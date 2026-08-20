import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

import app
from scripts import job_importer
from scripts.evidence_engine import evidence_is_externally_usable, select_evidence_cards
from scripts.materials_library import find_exact_role_package, organize_package_outputs
from scripts.next_steps import constrain_ai_wording, deterministic_next_steps
from scripts.parse_job import normalize_compensation
from scripts.resume_foundation import load_resume_foundation
from scripts.storage_paths import canonical_export_root, legacy_material_paths
from scripts.tailor_resume import _selected_projects


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIRECT_URL = "https://careers.example.com/jobs/product-operations-manager"


def _json_ld_html(**overrides):
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Product Operations Manager",
        "description": "<p>Build reliable product operations workflows, launch systems, governance, quality assurance, and AI automation across product and GTM teams.</p>",
        "hiringOrganization": {"name": "Example Labs"},
        "jobLocation": {"address": {"addressLocality": "Los Angeles", "addressRegion": "CA", "addressCountry": "US"}},
        "datePosted": "2026-07-20",
        "url": "https://apply.example.com/jobs/123",
        "identifier": {"value": "REQ-123"},
        "baseSalary": {"currency": "USD", "value": {"minValue": 150000, "maxValue": 190000, "unitText": "YEAR"}},
    }
    posting.update(overrides)
    return f'<html><head><script type="application/ld+json">{json.dumps(posting)}</script></head><body><nav>Recommended jobs</nav><h1>{posting["title"]}</h1></body></html>'


def test_direct_employer_json_ld_layers_fields_and_separates_urls():
    fields = job_importer.extract_job_fields(_json_ld_html(), DIRECT_URL)
    assert fields["company"] == "Example Labs"
    assert fields["job_title"] == "Senior Product Operations Manager"
    assert fields["posting_url"] == DIRECT_URL
    assert fields["application_url"] == "https://apply.example.com/jobs/123"
    assert fields["posting_date"] == "2026-07-20"
    assert "$150,000-$190,000" in fields["salary_range"]
    assert "<p>" not in fields["job_description"]
    assert "Recommended jobs" not in fields["job_description"]


def test_repeated_currency_salary_range_from_live_icims_copy_is_parsed_completely():
    text = "The base salary range for this job is USD $124,000.00 - USD $329,200.00 /Yr."
    compensation = normalize_compensation(text)
    assert compensation["minimum"] == 124000
    assert compensation["maximum"] == 329200
    assert compensation["display"] == "$124,000 – $329,200 per year"


def test_greenhouse_adapter_decodes_double_escaped_html_and_normalizes_employer():
    url = "https://job-boards.greenhouse.io/mrbeastyoutube/jobs/6119486004"
    payload = {
        "id": 6119486004,
        "title": "Head of Programming",
        "location": {"name": "Los Angeles, CA"},
        "absolute_url": "https://boards.greenhouse.io/mrbeastyoutube/jobs/6119486004#app",
        "content": "&amp;lt;p&amp;gt;Lead original programming strategy, content roadmaps, creator partnerships, audience insight, production, and cross-functional launch operations.&amp;lt;/p&amp;gt;",
    }
    with patch.object(job_importer, "_fetch_json", return_value=payload):
        imported = job_importer.import_job_from_url(url)
    assert imported["company"] == "Beast Industries"
    assert imported["job_title"] == "Head of Programming"
    assert imported["posting_url"] == url
    assert imported["application_url"].endswith("#app")
    assert "&lt;" not in imported["job_description"]
    assert "<p>" not in imported["job_description"]


@pytest.mark.parametrize(
    "url,payload,platform,company",
    [
        (
            "https://jobs.lever.co/acme/abc-123",
            {"id": "abc-123", "text": "Operations Lead", "descriptionPlain": "Lead product and operating workflows across teams with enough detail for a reliable public import.", "categories": {"location": "Remote"}, "applyUrl": "https://jobs.lever.co/acme/abc-123/apply"},
            "Lever",
            "Acme",
        ),
        (
            "https://jobs.ashbyhq.com/acme/ashby-123",
            {"jobs": [{"id": "ashby-123", "title": "Operations Lead", "descriptionPlain": "Lead product and operating workflows across teams with enough detail for a reliable public import.", "location": "Remote", "applyUrl": "https://jobs.ashbyhq.com/acme/ashby-123/application"}]},
            "Ashby",
            "Acme",
        ),
    ],
)
def test_public_platform_adapters_use_structured_endpoints(url, payload, platform, company):
    with patch.object(job_importer, "_fetch_json", return_value=payload), patch.object(job_importer, "fetch_job_page") as page:
        imported = job_importer.import_job_from_url(url)
    assert imported["source_platform"] == platform
    assert imported["company"] == company
    page.assert_not_called()


def test_workday_public_fixture_uses_layered_json_ld_without_ai():
    url = "https://acme.wd1.myworkdayjobs.com/en-US/Careers/job/Remote/Operations-Lead_REQ-9"
    with patch.object(job_importer, "fetch_job_page", return_value=_json_ld_html()), patch("scripts.job_importer._fetch_json") as structured:
        imported = job_importer.import_job_from_url(url)
    assert imported["source_name"] == "Workday"
    assert imported["job_title"] == "Senior Product Operations Manager"
    structured.assert_not_called()


def test_smartrecruiters_public_url_uses_company_and_posting_id_endpoint():
    url = "https://jobs.smartrecruiters.com/ExampleLabs/744000012345678-operations-lead"
    payload = {
        "id": "744000012345678",
        "name": "Operations Lead",
        "company": {"name": "Example Labs"},
        "location": {"city": "Remote"},
        "jobAd": {
            "company": "Example Labs builds useful products.",
            "jobDescription": "Lead product operations, workflow governance, quality assurance, and cross-functional delivery for a growing product organization.",
        },
    }
    with patch.object(job_importer, "_fetch_json", return_value=payload) as fetch, patch.object(job_importer, "fetch_job_page") as page:
        imported = job_importer.import_job_from_url(url)
    assert imported["source_platform"] == "SmartRecruiters"
    assert imported["job_title"] == "Operations Lead"
    assert "/companies/ExampleLabs/postings/744000012345678" in fetch.call_args.args[0]
    page.assert_not_called()


@pytest.mark.parametrize(
    "url,platform",
    [
        ("https://jobs.example.jobvite.com/example/job/oABC123", "Jobvite"),
        ("https://careers.example.icims.com/jobs/1234/operations-lead/job", "iCIMS"),
    ],
)
def test_page_fallback_platforms_keep_adapter_identity(url, platform):
    with patch.object(job_importer, "fetch_job_page", return_value=_json_ld_html()):
        imported = job_importer.import_job_from_url(url)
    assert imported["import_status"] == "success"
    assert imported["source_platform"] == platform


def test_public_linkedin_is_classified_but_falls_back_without_losing_url():
    url = "https://www.linkedin.com/jobs/view/123456"
    with pytest.raises(job_importer.JobImportError) as error:
        job_importer.import_job_from_url(url)
    assert "paste the job description" in str(error.value).lower()
    assert job_importer.PLATFORM_ADAPTERS[-1].matches(url)


def test_clean_html_fallback_rejects_sentence_title_and_removes_raw_html():
    html = """<html><head><meta property='og:site_name' content='Acme'><title>Jobs | Careers</title></head>
    <body><nav>Accept cookies</nav><h1>Director, Creative Operations</h1><main><p>Lead creative production, content systems, programming roadmaps, analytics, and cross-functional operations for a growing entertainment team.</p></main></body></html>"""
    fields = job_importer.extract_job_fields(html, "https://acme.example/jobs/creative-operations")
    assert fields["job_title"] == "Director, Creative Operations"
    assert fields["company"] == "Acme"
    assert "<main>" not in fields["job_description"]
    assert "Accept cookies" not in fields["job_description"]


def test_partial_and_blocked_import_preserve_source_url_and_successful_fields():
    html = "<html><head><meta property='og:site_name' content='Acme'></head><body><h1>Operations Lead</h1></body></html>"
    with patch.object(job_importer, "fetch_job_page", return_value=html):
        imported = job_importer.import_job_from_url(DIRECT_URL)
    assert imported["import_status"] == "partial"
    assert imported["source_url"] == DIRECT_URL
    assert imported["company"] == "Acme"
    assert "job description" in imported["missing_fields"]

    state = {"prospect_url_input": DIRECT_URL}
    result = app.apply_prospect_url_import_state(state, lambda _url: (_ for _ in ()).throw(job_importer.JobImportError("blocked")))
    assert result["status"] == "partial"
    assert state["prospect_original_source_url"] == DIRECT_URL


def _record(status, **extra):
    return {"id": "role", "company": "Acme", "role": "Operations Lead", "status": status, **extra}


@pytest.mark.parametrize(
    "status,forbidden",
    [
        ("Applied", {"generate_materials", "apply_or_archive"}),
        ("Under Consideration", {"generate_materials", "apply_or_archive", "track_application"}),
        ("Interviewing", {"generate_materials", "apply_or_archive", "track_application"}),
        ("Rejected", {"generate_materials", "apply_or_archive", "follow_up"}),
        ("Withdrawn / Closed", {"generate_materials", "apply_or_archive", "follow_up"}),
        ("Offer", {"generate_materials", "apply_or_archive", "follow_up"}),
    ],
)
def test_each_saved_status_maps_only_to_allowed_actions(status, forbidden):
    categories = {step["category"] for step in deterministic_next_steps(_record(status), date(2026, 7, 22))}
    assert not categories & forbidden


def test_existing_package_suppresses_regeneration_and_completed_actions_do_not_repeat(tmp_path):
    package = tmp_path / "resume.txt"
    package.write_text("existing", encoding="utf-8")
    drafted = _record("Drafted", material_paths={"Tailored Resume": str(package)})
    assert "generate_materials" not in {step["category"] for step in deterministic_next_steps(drafted)}
    applied = _record("Applied", submitted_date="2026-07-01", completed_actions=["follow_up"])
    assert "follow_up" not in {step["category"] for step in deterministic_next_steps(applied, date(2026, 7, 22))}
    assert constrain_ai_wording(applied, "Apply again and generate a package") == ""


def test_relevance_based_projects_are_distinct_for_github_and_beast():
    career_data = load_resume_foundation(PROJECT_ROOT)
    github = {"job_title": "Senior Product Operations Manager", "raw_text": "Own product operations, AI automation roadmap, backlog, workflow governance, requirements, QA, and iterative development.", "keywords": []}
    beast = {"job_title": "Head of Programming", "raw_text": "Lead original content programming, creator partnerships, creative production, audience experience, editorial strategy, and a content roadmap.", "keywords": []}
    github_names = [project["name"] for project, _ in _selected_projects(career_data, github, "executive_operations")]
    beast_names = [project["name"] for project, _ in _selected_projects(career_data, beast, "executive_operations")]
    assert "Career Catalyst" in github_names
    assert "RoboXT Studios" in beast_names
    assert "OMG23 Multiverse Newsletter" in beast_names
    assert "OMG23 Multiverse Newsletter" not in github_names


def test_evidence_privacy_and_project_cards_remain_grounded():
    assert not evidence_is_externally_usable({"status": "Active", "private": True})
    assert not evidence_is_externally_usable({"status": "Archived"})
    cards = select_evidence_cards({"job_title": "Senior Product Operations Manager", "raw_text": "AI product operations workflow governance automation roadmap and QA"}, list(load_cards()))
    assert "career_catalyst" in {card["id"] for card in cards}


def load_cards():
    from scripts.evidence_engine import load_evidence_cards
    return load_evidence_cards(PROJECT_ROOT)


def test_canonical_export_root_is_stable_and_test_output_is_injected(tmp_path, monkeypatch):
    monkeypatch.delenv("CAREER_CATALYST_EXPORT_ROOT", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    canonical = canonical_export_root(PROJECT_ROOT)
    assert canonical.name == "exports"
    application = {"id": "acme_operations_lead", "company": "Acme", "role": "Operations Lead", "status": "Drafted"}
    source = tmp_path / "generated.txt"
    source.write_text("generated", encoding="utf-8")
    test_root = tmp_path / "test_exports"
    result = organize_package_outputs(tmp_path, application, {"resume_text": str(source)}, export_root=test_root)
    manifest = Path(result["manifest"]["manifest_path"])
    assert test_root in manifest.parents
    assert canonical not in manifest.parents
    assert "acme_operations_lead_trisha_lynch_resume.txt" in result["outputs"]["resume_text"]


def test_manifest_tracker_and_open_materials_lookup_share_one_exact_package(tmp_path):
    application = {"id": "acme_operations_lead", "company": "Acme", "role": "Operations Lead", "status": "Drafted"}
    source = tmp_path / "generated.txt"
    source.write_text("grounded generated material", encoding="utf-8")
    export_root = tmp_path / "canonical_exports"
    organized = organize_package_outputs(
        tmp_path,
        application,
        {"resume_text": str(source)},
        export_root=export_root,
    )
    manifest = organized["manifest"]
    tracker_record = {
        **application,
        "material_paths": {"Tailored Resume": organized["outputs"]["resume_text"]},
        "package_manifest": {**manifest, "materials": {"Tailored Resume": organized["outputs"]["resume_text"]}},
    }
    found = find_exact_role_package(tmp_path, tracker_record, export_root=export_root)
    assert found["folder"] == Path(manifest["manifest_path"]).parent
    assert found["files"]["resume_text"] == Path(tracker_record["material_paths"]["Tailored Resume"])
    assert found["files"]["resume_text"].read_text(encoding="utf-8") == "grounded generated material"


def test_legacy_paths_are_reported_without_mutation(tmp_path):
    stranded = tmp_path / "worktree" / "exports" / "resume.txt"
    record = {"material_paths": {"Tailored Resume": str(stranded)}}
    before = dict(record)
    assert legacy_material_paths(record, tmp_path / "canonical") == [str(stranded.resolve())]
    assert record == before


def test_new_generation_sources_contain_no_obsolete_project_name():
    for relative in ("scripts", "config", "data", "templates"):
        for path in (PROJECT_ROOT / relative).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".yml", ".yaml", ".md", ".txt"}:
                assert "Substack" not in path.read_text(encoding="utf-8")
