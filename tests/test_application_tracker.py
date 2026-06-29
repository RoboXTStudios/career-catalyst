import io
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path

from scripts.application_tracker import (
    load_application_tracker,
    validate_application_tracker,
    validate_tracker_entries,
)
from scripts.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ApplicationTrackerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.applications = load_application_tracker(PROJECT_ROOT)

    def test_application_tracker_loads_successfully(self):
        self.assertEqual(len(self.applications), 5)
        self.assertTrue(all(isinstance(item, dict) for item in self.applications))

    def test_application_tracker_validates_successfully(self):
        report = validate_application_tracker(PROJECT_ROOT)

        self.assertEqual(report["errors"], [])
        self.assertEqual(report["status_counts"]["Applied"], 3)
        self.assertEqual(report["status_counts"]["Paused"], 1)
        self.assertEqual(report["status_counts"]["Invalid"], 1)

    def test_validate_tracker_cli_command_works(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["validate-tracker"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Application tracker validation succeeded.", output.getvalue())
        self.assertIn("- Applied: 3", output.getvalue())
        self.assertIn("- Paused: 1", output.getvalue())
        self.assertIn("- Invalid: 1", output.getvalue())

    def test_duplicate_tracker_ids_are_caught(self):
        applications = deepcopy(self.applications)
        duplicate = deepcopy(applications[0])
        applications.append(duplicate)

        report = validate_tracker_entries(applications)

        self.assertTrue(
            any("Duplicate tracker id" in error for error in report["errors"])
        )

    def test_duplicate_active_company_and_role_produces_warning(self):
        applications = deepcopy(self.applications)
        duplicate = deepcopy(applications[0])
        duplicate["id"] = "another_playstation_application"
        applications.append(duplicate)

        report = validate_tracker_entries(applications)

        self.assertTrue(
            any("same normalized company and role" in warning for warning in report["warnings"])
        )

    def test_applied_and_visibility_states_are_preserved(self):
        by_id = {application["id"]: application for application in self.applications}

        self.assertEqual(
            by_id["playstation_head_global_creative_ops"]["status"],
            "Applied",
        )
        self.assertEqual(
            by_id["google_strategy_ops_youtube_auction_brand"]["status"],
            "Applied",
        )
        self.assertEqual(
            by_id["paramount_director_marketing_operations"]["status"],
            "Applied",
        )
        self.assertEqual(
            by_id["crunchyroll_enterprise_strategy_paused"]["status"],
            "Paused",
        )
        self.assertFalse(
            by_id["playstation_director_ad_ops_invalid"]["show_on_dashboard"]
        )


if __name__ == "__main__":
    unittest.main()
