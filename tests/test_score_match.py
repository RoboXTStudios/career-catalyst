import unittest
from pathlib import Path

from scripts.score_match import score_job_match


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JOB = "jobs/sample_job_description.md"


class ScoreMatchTests(unittest.TestCase):
    def test_score_command_returns_dictionary(self):
        report = score_job_match(SAMPLE_JOB, PROJECT_ROOT)

        self.assertIsInstance(report, dict)
        self.assertEqual(report["job_title"], "Director, Enterprise Strategy & Initiatives")
        self.assertEqual(report["company"], "Crunchyroll")

    def test_match_score_is_numeric_and_between_zero_and_one_hundred(self):
        report = score_job_match(SAMPLE_JOB, PROJECT_ROOT)

        self.assertIsInstance(report["match_score"], int)
        self.assertGreaterEqual(report["match_score"], 0)
        self.assertLessEqual(report["match_score"], 100)

    def test_match_band_is_populated(self):
        report = score_job_match(SAMPLE_JOB, PROJECT_ROOT)

        self.assertTrue(report["match_band"])

    def test_recommended_resume_profile_is_populated(self):
        report = score_job_match(SAMPLE_JOB, PROJECT_ROOT)

        self.assertIn(
            report["recommended_resume_profile"],
            {
                "executive_operations",
                "entertainment_marketing",
                "music_industry",
                "product_ai",
            },
        )

    def test_missing_keywords_list_is_returned(self):
        report = score_job_match(SAMPLE_JOB, PROJECT_ROOT)

        self.assertIsInstance(report["missing_keywords"], list)

    def test_sample_crunchyroll_job_scores_as_strong_or_excellent_fit(self):
        report = score_job_match(SAMPLE_JOB, PROJECT_ROOT)

        self.assertIn(report["match_band"], {"Strong fit", "Excellent fit"})


if __name__ == "__main__":
    unittest.main()
