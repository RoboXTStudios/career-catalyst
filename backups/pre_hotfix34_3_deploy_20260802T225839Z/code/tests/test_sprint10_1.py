import importlib
import unittest
from pathlib import Path

from scripts.application_tracker import load_application_tracker


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Sprint101UiHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = importlib.import_module("app")
        cls.source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    def test_app_imports_without_running_streamlit(self):
        self.assertTrue(callable(self.app.main))

    def test_summary_metrics_count_tracker_states(self):
        applications = [
            {"status": "Applied", "show_on_dashboard": True},
            {"status": "Considered", "show_on_dashboard": True},
            {"status": "Considered", "show_on_dashboard": True},
            {"status": "Invalid", "show_on_dashboard": False},
        ]

        self.assertEqual(
            self.app.summarize_applications(applications),
            {
                "Total": 4,
                "Applied": 1,
                "Considered": 2,
                "Withdrawn / Closed": 1,
            },
        )

    def test_tracker_grouping_matches_dashboard_sections(self):
        applications = [
            {"id": "applied", "status": "Applied", "show_on_dashboard": True},
            {"id": "interview", "status": "Interviewing", "show_on_dashboard": True},
            {"id": "reviewed", "status": "Considered", "show_on_dashboard": True},
            {"id": "considered", "status": "Considered", "show_on_dashboard": True},
            {"id": "invalid", "status": "Invalid", "show_on_dashboard": False},
        ]

        grouped = self.app.group_applications_by_status(applications)

        self.assertEqual(
            {item["id"] for item in grouped["Applied"]},
            {"applied"},
        )
        self.assertEqual(
            {item["id"] for item in grouped["Interviewing"]},
            {"interview"},
        )
        self.assertEqual(
            {item["id"] for item in grouped["Considered"]},
            {"reviewed", "considered"},
        )
        self.assertEqual({item["id"] for item in grouped["Withdrawn / Closed"]}, {"invalid"})

    def test_career_catalyst_ui_language_is_present(self):
        for phrase in (
            "Career Catalyst",
            "Trisha Lynch Application Cockpit",
            "Application Dashboard",
            "Application Tracker",
            "Application materials",
            "Styled resume",
            "ATS resume",
            "Cover letter",
            "Recruiter message",
            "Hiring manager message",
            "Application note",
            "Strategy pack",
        ):
            self.assertIn(phrase, self.source)

    def test_unrelated_product_branding_is_not_in_ui_source(self):
        lowered = self.source.lower()
        for phrase in (
            "campaignos",
            "launchguard",
            "media trafficking dashboard",
            "campaign readiness",
        ):
            self.assertNotIn(phrase, lowered)

    def test_current_tracker_statuses_remain_preserved(self):
        applications = load_application_tracker(PROJECT_ROOT)
        by_id = {item["id"]: item for item in applications}

        self.assertEqual(by_id["playstation_head_global_creative_ops"]["status"], "Applied")
        self.assertEqual(by_id["google_strategy_ops_youtube_auction_brand"]["status"], "Applied")
        self.assertEqual(by_id["paramount_director_marketing_operations"]["status"], "Applied")
        self.assertEqual(by_id["playstation_director_ad_ops_invalid"]["status"], "Invalid")
        self.assertFalse(
            by_id["playstation_director_ad_ops_invalid"]["show_on_dashboard"]
        )


if __name__ == "__main__":
    unittest.main()
