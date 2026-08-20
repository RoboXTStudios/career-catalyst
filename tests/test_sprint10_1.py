import importlib
import unittest
from pathlib import Path

from scripts.application_tracker import VALID_STATUSES, get_record_status, load_application_tracker


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
            "Dashboard",
            "Evidence Projects",
            "Generate Package",
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

    def test_committed_tracker_statuses_use_current_lifecycle(self):
        applications = load_application_tracker(PROJECT_ROOT)
        by_id = {item["id"]: item for item in applications}

        for tracker_id in (
            "playstation_head_global_creative_ops",
            "google_strategy_ops_youtube_auction_brand",
            "paramount_director_marketing_operations",
            "playstation_director_ad_ops_invalid",
        ):
            self.assertIn(tracker_id, by_id)
            self.assertIn(get_record_status(by_id[tracker_id]), VALID_STATUSES)


if __name__ == "__main__":
    unittest.main()
