import importlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import yaml

from scripts.application_tracker import (
    VALID_STATUSES,
    add_prospect,
    get_record_status,
    load_application_tracker,
    update_status,
)
from scripts.job_importer import (
    JobImportError,
    extract_job_text,
    fetch_job_page,
    parse_imported_job,
)
from scripts.package_generator import generate_package
from scripts.prospect_intake import create_prospect


DESCRIPTION = (
    "Lead cross-functional marketing operations, build scalable intake workflows, "
    "improve capacity planning, and partner with creative leaders on delivery."
)


class Sprint10Tests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        project_root = Path(__file__).resolve().parents[1]
        shutil.copytree(project_root / "data", self.root / "data")
        shutil.copytree(project_root / "config", self.root / "config")
        shutil.copytree(project_root / "templates", self.root / "templates")
        (self.root / "jobs").mkdir(parents=True)
        (self.root / "data" / "application_tracker.yml").write_text(
            "applications: []\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _create_tracker_job(self, status="Prospect"):
        job_path = self.root / "jobs" / "director_operations_acme.md"
        job_path.write_text(
            "\n".join(
                (
                    "# Director, Operations",
                    "",
                    "Company: Acme Entertainment",
                    "Tracker ID: acme_director_operations",
                    "Official URL: https://careers.acme.example/jobs/1",
                    "",
                    "## Job Description",
                    "",
                    DESCRIPTION,
                )
            ),
            encoding="utf-8",
        )
        add_prospect(
            {
                "id": "acme_director_operations",
                "company": "Acme Entertainment",
                "role": "Director, Operations",
                "status": status,
                "priority": "High",
                "show_on_dashboard": True,
                "job_file": "jobs/director_operations_acme.md",
            },
            self.root,
        )
        return job_path

    def test_unreachable_url_returns_manual_paste_fallback(self):
        with patch("scripts.job_importer.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(JobImportError) as context:
                fetch_job_page("https://careers.example.com/jobs/123")

        self.assertIn("could not be reached", str(context.exception))
        self.assertIn("paste the job description text manually", str(context.exception))

    def test_aggregator_url_is_rejected_as_primary_source(self):
        with self.assertRaises(JobImportError) as context:
            fetch_job_page("https://www.indeed.com/viewjob?jk=123")

        self.assertIn("official company career pages", str(context.exception))
        self.assertIn("paste the job description text manually", str(context.exception))

    def test_json_ld_job_page_imports_without_heavy_scraping(self):
        posting = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Director, Marketing Operations",
            "hiringOrganization": {"name": "Acme Entertainment"},
            "jobLocation": {
                "address": {"addressLocality": "Los Angeles", "addressRegion": "CA"}
            },
            "description": f"<p>{DESCRIPTION}</p>",
        }
        html = (
            '<html><script type="application/ld+json">'
            + json.dumps(posting)
            + "</script></html>"
        )
        raw_text = extract_job_text(html, "https://boards.greenhouse.io/acme/jobs/123")
        imported = parse_imported_job(raw_text, "https://boards.greenhouse.io/acme/jobs/123")

        self.assertEqual(imported["company"], "Acme Entertainment")
        self.assertEqual(imported["job_title"], "Director, Marketing Operations")
        self.assertEqual(imported["source"], "Official Greenhouse")
        self.assertIn("cross-functional marketing operations", imported["job_description"])

    def test_pasted_text_creates_job_file_and_tracker_entry(self):
        result = create_prospect(
            {
                "official_url": "https://careers.acme.example/jobs/123",
                "company": "Acme Entertainment",
                "job_title": "Director, Marketing Operations",
                "location": "Los Angeles, CA",
                "salary_range": "$150,000-$180,000",
                "source": "Official Acme Careers",
                "priority": "High",
                "status": "Prospect",
                "work_arrangement": "Hybrid",
                "job_description": DESCRIPTION,
                "notes": "Strong fit.",
                "next_action": "Generate package.",
            },
            self.root,
        )

        job_path = Path(result["job_file_path"])
        content = job_path.read_text(encoding="utf-8")
        applications = load_application_tracker(self.root)
        self.assertTrue(job_path.is_file())
        self.assertIn("Official URL: https://careers.acme.example/jobs/123", content)
        self.assertIn("## Job Description", content)
        self.assertEqual(len(applications), 1)
        self.assertEqual(applications[0]["id"], result["tracker_id"])

    def test_add_prospect_does_not_duplicate_existing_entry(self):
        prospect = {
            "company": "Acme Entertainment",
            "role": "Director, Operations",
            "status": "Prospect",
            "priority": "High",
            "show_on_dashboard": True,
        }
        first = add_prospect(prospect, self.root)
        second = add_prospect(prospect, self.root)

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(len(load_application_tracker(self.root)), 1)

    def test_update_status_applied_sets_missing_submitted_date(self):
        self._create_tracker_job()
        updated = update_status("acme_director_operations", "Applied", self.root)

        self.assertRegex(updated["submitted_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_readding_prospect_preserves_applied_status(self):
        self._create_tracker_job("Applied")
        result = add_prospect(
            {
                "id": "acme_director_operations",
                "company": "Acme Entertainment",
                "role": "Director, Operations",
                "status": "Considered",
                "priority": "High",
                "show_on_dashboard": True,
            },
            self.root,
        )

        self.assertEqual(result["application"]["status"], "Applied")

    def _mock_generation_pipeline(self):
        parsed = {
            "job_title": "Director, Operations",
            "company": "Acme Entertainment",
        }
        output_dir = self.root / "exports"
        output_dir.mkdir(exist_ok=True)
        for relative_path in (
            "resume.md", "styled.docx", "ats.docx", "cover.md", "cover.txt", "cover.docx",
            "recruiter.md", "manager.md", "note.md", "strategy.md",
            "dashboard/index.html",
        ):
            path = output_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "Acme Entertainment Director, Operations candidate material.",
                encoding="utf-8",
            )
        return (
            patch("scripts.package_generator.parse_job_description", return_value=parsed),
            patch(
                "scripts.package_generator.score_job_match",
                return_value={"match_score": 88, "match_band": "Strong"},
            ),
            patch(
                "scripts.package_generator.tailor_resume",
                return_value={"output_path": str(self.root / "exports/resume.md")},
            ),
            patch(
                "scripts.package_generator.export_styled_docx",
                return_value={"output_path": str(self.root / "exports/styled.docx")},
            ),
            patch(
                "scripts.package_generator.export_ats_docx",
                return_value={"output_path": str(self.root / "exports/ats.docx")},
            ),
            patch(
                "scripts.package_generator.generate_cover_letter",
                return_value={
                    "output_path": str(self.root / "exports/cover.md"),
                    "txt_output_path": str(self.root / "exports/cover.txt"),
                    "docx_output_path": str(self.root / "exports/cover.docx"),
                },
            ),
            patch(
                "scripts.package_generator.generate_message",
                side_effect=(
                    {"output_path": str(self.root / "exports/recruiter.md")},
                    {"output_path": str(self.root / "exports/manager.md")},
                ),
            ),
            patch(
                "scripts.package_generator.generate_application_note",
                return_value={"output_path": str(self.root / "exports/note.md")},
            ),
            patch(
                "scripts.package_generator.generate_strategy_pack",
                return_value={"output_path": str(self.root / "exports/strategy.md")},
            ),
            patch(
                "scripts.package_generator.generate_dashboard",
                return_value={"output_path": str(self.root / "exports/dashboard/index.html")},
            ),
            patch(
                "scripts.package_generator.evaluate_candidate_facing_quality",
                return_value={"status": "PASS", "blocking_reasons": []},
            ),
            patch(
                "scripts.package_generator.compare_docx_factual_parity",
                return_value={"status": "PASS", "visible_facts_match": True, "hyperlinks_match": True},
            ),
            patch(
                "scripts.package_generator.build_interview_conversion_gate",
                return_value={"status": "PASS", "blocking_reasons": []},
            ),
        )

    def _generate_with_mocks(self):
        managers = self._mock_generation_pipeline()
        for manager in managers:
            manager.start()
        try:
            return generate_package("acme_director_operations", self.root)
        finally:
            for manager in reversed(managers):
                manager.stop()

    def test_generate_package_updates_prospect_to_considered(self):
        self._create_tracker_job("Prospect")
        result = self._generate_with_mocks()

        self.assertEqual(result["status"], "Considered")
        self.assertEqual(
            load_application_tracker(self.root)[0]["status"], "Considered"
        )

    def test_generate_package_does_not_overwrite_applied(self):
        self._create_tracker_job("Applied")
        result = self._generate_with_mocks()

        self.assertEqual(result["status"], "Applied")
        self.assertEqual(load_application_tracker(self.root)[0]["status"], "Applied")

    def test_ui_helpers_import_without_running_streamlit(self):
        module = importlib.import_module("app")

        payload = module.build_prospect_payload({"company": "Acme", "job_title": "Role"})
        self.assertEqual(payload["company"], "Acme")
        self.assertTrue(callable(module.main))


class CanonicalStatusFixtureTests(unittest.TestCase):
    def test_committed_tracker_uses_valid_current_statuses(self):
        project_root = Path(__file__).resolve().parents[1]
        applications = load_application_tracker(project_root)
        by_id = {item["id"]: item for item in applications}

        for tracker_id in (
            "playstation_head_global_creative_ops",
            "google_strategy_ops_youtube_auction_brand",
            "paramount_director_marketing_operations",
        ):
            self.assertIn(tracker_id, by_id)
            self.assertIn(get_record_status(by_id[tracker_id]), VALID_STATUSES)


if __name__ == "__main__":
    unittest.main()
