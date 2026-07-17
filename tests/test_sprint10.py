import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import yaml

from scripts.application_tracker import (
    add_prospect,
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
        (self.root / "data").mkdir(parents=True)
        (self.root / "jobs").mkdir(parents=True)
        (self.root / "data" / "application_tracker.yml").write_text(
            "applications: []\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _create_tracker_job(self, status="Drafted"):
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
        self.assertIn("saved the posting URL", str(context.exception))
        self.assertIn("Paste the description below", str(context.exception))

    def test_indeed_url_is_attempted_before_manual_fallback(self):
        with patch("scripts.job_importer.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(JobImportError) as context:
                fetch_job_page("https://www.indeed.com/viewjob?jk=123")

        self.assertIn("could not be reached", str(context.exception))
        self.assertIn("saved the posting URL", str(context.exception))

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
        self.assertEqual(imported["source"], "Greenhouse")
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
                "status": "Drafted",
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
            "status": "Drafted",
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
                "status": "Reviewed",
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

    def test_generate_package_updates_drafted_to_reviewed(self):
        self._create_tracker_job("Drafted")
        result = self._generate_with_mocks()

        self.assertEqual(result["status"], "Reviewed")
        self.assertEqual(
            load_application_tracker(self.root)[0]["status"], "Reviewed"
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


class AppliedStatusRegressionTests(unittest.TestCase):
    def test_playstation_google_and_paramount_applied_statuses_coexist(self):
        project_root = Path(__file__).resolve().parents[1]
        applications = load_application_tracker(project_root)
        by_id = {item["id"]: item for item in applications}

        self.assertEqual(by_id["playstation_head_global_creative_ops"]["status"], "Applied")
        self.assertEqual(by_id["google_strategy_ops_youtube_auction_brand"]["status"], "Applied")
        self.assertEqual(by_id["paramount_director_marketing_operations"]["status"], "Applied")


if __name__ == "__main__":
    unittest.main()
