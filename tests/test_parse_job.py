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


if __name__ == "__main__":
    unittest.main()
