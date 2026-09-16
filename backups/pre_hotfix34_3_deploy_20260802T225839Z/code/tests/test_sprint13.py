import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts.application_tracker import load_application_tracker
from scripts.generate_dashboard import _render_match_score, generate_dashboard
from scripts.prospect_intake import create_prospect
from scripts.score_match import score_job_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today()


def _posting_date(days_ago=1):
    return (TODAY - timedelta(days=days_ago)).isoformat()


class MatchScoreModelTests(unittest.TestCase):
    def test_strong_media_operations_role_returns_full_gate_model(self):
        report = score_job_data(
            {
                "company": "Northstar Streaming",
                "job_title": "Director, Media Operations and Ad Technology",
                "location": "Remote",
                "work_arrangement": "Remote",
                "salary_range": "$170,000-$205,000",
                "posting_date": _posting_date(),
                "job_description": (
                    "Lead media operations, ad operations, programmatic trafficking, campaign "
                    "execution, measurement vendor operations, marketing technology, workflow "
                    "automation, and cross-functional strategic operations for a streaming business."
                ),
            },
            PROJECT_ROOT,
        )

        self.assertEqual(report["match_tier"], "Strong Match")
        self.assertEqual(report["recommended_action"], "Generate Package")
        self.assertGreaterEqual(report["match_score"], 82)
        self.assertIn(report["confidence"], {"Medium", "High"})
        self.assertGreaterEqual(len(report["match_strengths"]), 3)
        self.assertGreaterEqual(len(report["match_gaps"]), 1)

    def test_music_doorway_role_keeps_good_match_with_compensation_caution(self):
        report = score_job_data(
            {
                "company": "Harmony Music",
                "job_title": "Senior Manager, Strategic Integration and Operations",
                "location": "Los Angeles, CA",
                "work_arrangement": "On-site",
                "salary_range": "$85k-$100k",
                "posting_date": _posting_date(5),
                "job_description": (
                    "Lead strategic operations, business operations, workflow automation, process "
                    "improvement, executive stakeholder alignment, and transformation for a global "
                    "music streaming and artist services company. This role is on-site."
                ),
            },
            PROJECT_ROOT,
        )

        self.assertEqual(report["match_tier"], "Good Match")
        self.assertEqual(report["recommended_action"], "Generate Package")
        self.assertIn("strategic doorway", report["match_summary"].lower())
        self.assertTrue(
            any("$120k" in caution for caution in report["match_gaps"]),
            report["match_gaps"],
        )

    def test_missing_salary_is_not_disclosed_and_reduces_confidence(self):
        report = score_job_data(
            {
                "company": "Signal Media",
                "job_title": "Director, Campaign Operations",
                "location": "Remote",
                "work_arrangement": "Remote",
                "posting_date": _posting_date(),
                "job_description": (
                    "Lead campaign operations, media execution, measurement, workflow automation, "
                    "and strategic operations for an entertainment platform."
                ),
            },
            PROJECT_ROOT,
        )

        self.assertEqual(
            report["salary_range"],
            "Compensation unknown — verify posting or recruiter details.",
        )
        self.assertEqual(
            report["compensation_disclosure_state"], "unknown_unverified"
        )
        self.assertNotEqual(report["confidence"], "High")
        self.assertTrue(
            any(
                "compensation is unknown" in gap.lower()
                for gap in report["match_gaps"]
            )
        )

    def test_closed_role_is_always_a_pass(self):
        report = score_job_data(
            {
                "company": "Closed Media",
                "job_title": "Director, Media Operations",
                "location": "Remote",
                "work_arrangement": "Remote",
                "salary_range": "$180,000-$210,000",
                "posting_date": _posting_date(),
                "job_description": (
                    "Lead media operations, programmatic campaign operations, and workflow automation. "
                    "Applications are closed."
                ),
            },
            PROJECT_ROOT,
        )

        self.assertEqual(report["match_tier"], "Pass")
        self.assertEqual(report["recommended_action"], "Pass")
        self.assertLessEqual(report["match_score"], 25)


class MatchScorePersistenceAndDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data").mkdir()
        (self.root / "jobs").mkdir()
        (self.root / "data" / "application_tracker.yml").write_text(
            "applications: []\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_import_persists_score_and_dashboard_shows_gate_before_materials(self):
        result = create_prospect(
            {
                "company": "Acme Streaming",
                "job_title": "Director, Strategic Media Operations",
                "location": "Remote",
                "work_arrangement": "Remote",
                "salary_range": "$165,000-$190,000",
                "posting_date": _posting_date(),
                "job_description": (
                    "Lead media operations, campaign operations, programmatic execution, strategic "
                    "operations, process improvement, and workflow automation for a streaming media "
                    "company with cross-functional brand and technology partners."
                ),
            },
            self.root,
        )
        application = load_application_tracker(self.root)[0]

        for field in (
            "match_score",
            "match_tier",
            "match_summary",
            "match_strengths",
            "match_gaps",
            "recommended_action",
            "confidence",
        ):
            self.assertIn(field, application)

        dashboard = generate_dashboard(self.root)
        content = Path(dashboard["output_path"]).read_text(encoding="utf-8")
        card_start = content.index("Acme Streaming")
        score_position = content.index("Match Score", card_start)
        materials_position = content.index("<h4>Materials</h4>", card_start)
        self.assertLess(score_position, materials_position)
        self.assertIn(application["match_tier"], content)
        self.assertIn(application["recommended_action"], content)
        self.assertNotIn("Tailored Markdown Resume", content[card_start:])
        self.assertTrue(Path(result["job_file_path"]).is_file())

    def test_older_unscored_records_have_safe_dashboard_fallback(self):
        content = _render_match_score({})
        self.assertIn("Match Score", content)
        self.assertIn("Not scored yet", content)


if __name__ == "__main__":
    unittest.main()
