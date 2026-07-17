import tempfile
import unittest
from pathlib import Path

from scripts.parse_job import (
    MissingJobDescriptionError,
    load_job_description,
    parse_job_description,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JOB = PROJECT_ROOT / "jobs" / "sample_job_description.md"
PLAYSTATION_JOB = PROJECT_ROOT / "jobs" / "playstation_head_global_creative_product_dev_ops.md"


class ParseJobTests(unittest.TestCase):
    def test_job_description_file_loads(self):
        text = load_job_description(SAMPLE_JOB)

        self.assertIn("Crunchyroll", text)
        self.assertIn("Director, Enterprise Strategy & Initiatives", text)

    def test_parser_returns_dictionary(self):
        parsed = parse_job_description(SAMPLE_JOB)

        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed["job_title"], "Director, Enterprise Strategy & Initiatives")
        self.assertEqual(parsed["company"], "Crunchyroll")
        self.assertEqual(parsed["location"], "Los Angeles, CA")
        self.assertEqual(parsed["salary_range"], "$183,000 - $228,000")
        self.assertEqual(parsed["employment_type"], "Full-time")

    def test_parser_extracts_salary_range_when_second_amount_omits_currency_symbol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job_file = Path(temp_dir) / "salary_range_job.txt"
            job_file.write_text(
                "# Director, Media Operations\n\n"
                "Company: Signal Media\n\n"
                "## Job Description\n\n"
                "Lead media operations and campaign execution for a streaming platform. "
                "The annual salary range for this role is $170,000 - 205,000 plus benefits.",
                encoding="utf-8",
            )

            parsed = parse_job_description(job_file)

        self.assertEqual(parsed["salary_range"], "$170,000 - 205,000")

    def test_parser_extracts_keywords(self):
        parsed = parse_job_description(SAMPLE_JOB)

        self.assertIn("enterprise strategy", parsed["keywords"])
        self.assertIn("cross-functional", parsed["keywords"])
        self.assertGreater(len(parsed["keywords"]), 0)

    def test_parser_uses_first_h1_as_job_title_when_no_title_label_exists(self):
        parsed = parse_job_description(PLAYSTATION_JOB)

        self.assertEqual(
            parsed["job_title"],
            "Head of Global Creative and Product Development Operations",
        )

    def test_parser_extracts_responsibilities_and_qualifications(self):
        parsed = parse_job_description(SAMPLE_JOB)

        self.assertGreater(len(parsed["responsibilities"]), 0)
        self.assertGreater(len(parsed["qualifications"]), 0)

    def test_parser_handles_missing_optional_fields_gracefully(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            job_file = Path(temp_dir) / "minimal_job.txt"
            job_file.write_text(
                "Role: Operations Lead\n\nLead planning, process improvement, and stakeholder alignment.",
                encoding="utf-8",
            )

            parsed = parse_job_description(job_file)

        self.assertEqual(parsed["job_title"], "Operations Lead")
        self.assertIsNone(parsed["company"])
        self.assertIsNone(parsed["location"])
        self.assertIsNone(parsed["salary_range"])
        self.assertIsNone(parsed["employment_type"])
        self.assertIsNone(parsed["source_url"])
        self.assertIsInstance(parsed["keywords"], list)

    def test_parser_raises_helpful_error_for_missing_file(self):
        missing_path = PROJECT_ROOT / "jobs" / "missing_job_description.md"

        with self.assertRaises(MissingJobDescriptionError) as context:
            parse_job_description(missing_path)

        self.assertIn("Job description file not found", str(context.exception))

class GreenhouseUrlImportRegressionTests(unittest.TestCase):
    def test_airtable_greenhouse_job_board_url_extracts_via_boards_api(self):
        from unittest.mock import patch

        from scripts import job_importer

        url = "https://job-boards.greenhouse.io/airtable/jobs/8597950002"
        payload = {
            "id": 8597950002,
            "title": "Strategic Operations Lead",
            "absolute_url": url,
            "location": {"name": "San Francisco, CA"},
            "content": (
                "<p>Lead cross-functional planning, operations, stakeholder alignment, "
                "business reviews, launch readiness, and execution governance across Airtable teams.</p>"
            ),
        }

        class FakeHeaders:
            def get_content_type(self):
                return "application/json"

            def get_content_charset(self):
                return "utf-8"

        class FakeResponse:
            headers = FakeHeaders()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                import json

                return json.dumps(payload).encode("utf-8")

        requested_urls = []

        def fake_urlopen(request, timeout=12):
            requested_urls.append(request.full_url)
            return FakeResponse()

        with patch.object(job_importer, "urlopen", fake_urlopen):
            imported = job_importer.import_job_from_url(url)

        self.assertEqual(
            requested_urls,
            ["https://boards-api.greenhouse.io/v1/boards/airtable/jobs/8597950002"],
        )
        self.assertEqual(imported["company"], "Airtable")
        self.assertEqual(imported["job_title"], "Strategic Operations Lead")
        self.assertEqual(imported["location"], "San Francisco, CA")
        self.assertIn("cross-functional planning", imported["job_description"])
        self.assertEqual(imported["source_url"], url)
        self.assertEqual(imported["original_source_url"], url)
        self.assertEqual(imported["canonical_apply_url"], url)
        self.assertEqual(imported["source_name"], "Greenhouse")

    def test_partial_failure_preserves_url_and_manual_fallback_fields(self):
        import app
        from scripts.job_importer import JobImportError

        url = "https://job-boards.greenhouse.io/airtable/jobs/8597950002"
        state = {
            "prospect_url": url,
            "prospect_company": "Manually Typed Co",
            "prospect_role": "Manual Role",
            "prospect_description": "Manual pasted text stays available for fallback.",
        }

        def fail(_url):
            raise JobImportError("blocked")

        result = app.apply_prospect_url_import_state(state, fail)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(state["prospect_url"], url)
        self.assertEqual(state["prospect_original_source_url"], url)
        self.assertEqual(state["prospect_canonical_url"], url)
        self.assertEqual(state["prospect_company"], "Manually Typed Co")
        self.assertEqual(state["prospect_role"], "Manual Role")
        self.assertEqual(
            state["prospect_description"],
            "Manual pasted text stays available for fallback.",
        )
        self.assertIn("saved the posting URL", state["prospect_import_result"][1])
        self.assertIn("Paste the description below", state["prospect_import_result"][1])

    def test_url_import_does_not_mutate_widget_owned_input_key(self):
        import app
        from scripts.job_importer import JobImportError

        url = "https://job-boards.greenhouse.io/airtable/jobs/8597950002"
        state = {
            "prospect_url_input": url,
            "prospect_company": "Manual Co",
            "prospect_role": "Manual Role",
            "prospect_description": "Manual pasted text stays available for fallback.",
        }

        def fail(_url):
            raise JobImportError("blocked")

        result = app.apply_prospect_url_import_state(state, fail)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(state["prospect_url_input"], url)
        self.assertEqual(state["prospect_url_value"], url)
        self.assertEqual(state["prospect_import_url"], url)
        self.assertEqual(state["prospect_url_last_imported"], url)
        self.assertNotIn("prospect_url", state)


if __name__ == "__main__":
    unittest.main()
