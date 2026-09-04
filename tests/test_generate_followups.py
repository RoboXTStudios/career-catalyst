import io
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.application_tracker import get_record_status, load_application_tracker
from scripts.cli import main
from scripts.generate_dashboard import generate_dashboard
from scripts.generate_followups import MESSAGE_LIMITS, generate_followups


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARAMOUNT_ID = "paramount_director_marketing_operations"
GOOGLE_ID = "google_strategy_ops_youtube_auction_brand"
SUBMITTED_IDS = {
    "playstation_head_global_creative_ops",
    GOOGLE_ID,
    PARAMOUNT_ID,
    "united_talent_agency_director_transformation",
    "disney_entertainment_and_espn_product_technology_director_strategy_operations_product_technology",
    "fieldai_director_of_matrix_operations_organizational_efficiency",
}
MESSAGE_KEYS = (
    "recruiter_followup",
    "hiring_manager_followup",
    "warm_contact_message",
    "referral_ask",
)
BANNED_PHRASES = (
    "just checking in",
    "perfect fit",
    "top of your inbox",
    "desperate",
)


def _word_count(text):
    return len(re.findall(r"\b[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*\b", text))


class GenerateFollowupsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.project_root = Path(cls.temporary_directory.name)
        for directory in ("config", "data", "jobs"):
            shutil.copytree(PROJECT_ROOT / directory, cls.project_root / directory)
        tracker_path = cls.project_root / "data" / "application_tracker.yml"
        tracker = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
        for application in tracker["applications"]:
            if application["id"] in SUBMITTED_IDS:
                application["status"] = "Applied"
                for key in (
                    "is_archived",
                    "archived_at",
                    "archive_reason",
                    "archived_from_status",
                    "archive_history",
                ):
                    application.pop(key, None)
            if application["id"] in {PARAMOUNT_ID, GOOGLE_ID}:
                application.update(
                    {
                        "status": "Applied",
                        "submitted_date": "2026-07-01",
                        "show_on_dashboard": True,
                        "recruiter_email": "recruiter@example.com",
                        "portal_only": False,
                        "no_contact": False,
                        "follow_up_possible": True,
                        "follow_up_status": "Due now",
                        "follow_up_sent": False,
                        "follow_up_not_applicable": False,
                        "application_history": [],
                    }
                )
        tracker_path.write_text(
            yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8"
        )
        cls.paramount = generate_followups(PARAMOUNT_ID, cls.project_root)
        cls.google = generate_followups(GOOGLE_ID, cls.project_root)

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    def test_followups_function_generates_all_files_for_applied_role(self):
        self.assertEqual(self.paramount["status"], "Applied")
        self.assertEqual(
            set(self.paramount["outputs"]),
            {*MESSAGE_KEYS, "followup_strategy"},
        )
        for path_value in self.paramount["outputs"].values():
            path = Path(path_value)
            self.assertTrue(path.is_file())
            self.assertTrue(path.read_text(encoding="utf-8").strip())

    def test_primary_followup_files_are_not_empty(self):
        for key in (
            "recruiter_followup",
            "hiring_manager_followup",
            "followup_strategy",
        ):
            content = Path(self.paramount["outputs"][key]).read_text(encoding="utf-8")
            self.assertTrue(content.strip())

    def test_message_types_stay_within_requested_word_limits(self):
        for key in MESSAGE_KEYS:
            content = Path(self.paramount["outputs"][key]).read_text(encoding="utf-8")
            minimum, maximum = MESSAGE_LIMITS[key]
            self.assertGreaterEqual(_word_count(content), minimum)
            self.assertLessEqual(_word_count(content), maximum)

    def test_strategy_contains_required_sections(self):
        strategy = Path(self.paramount["outputs"]["followup_strategy"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("# Follow-Up Strategy", strategy)
        self.assertIn("## Paramount | Director, Marketing Operations", strategy)
        for section in (
            "Current Status",
            "Best Outreach Angle",
            "Who To Look For",
            "What To Avoid",
            "Suggested Timing",
            "Core Value Point",
            "Message Options",
        ):
            self.assertIn(f"### {section}", strategy)

    def test_messages_have_no_em_dash_or_banned_phrases(self):
        for result in (self.paramount, self.google):
            for key in MESSAGE_KEYS:
                content = Path(result["outputs"][key]).read_text(encoding="utf-8")
                self.assertNotIn("—", content)
                lowered = content.lower()
                for phrase in BANNED_PHRASES:
                    self.assertNotIn(phrase, lowered)

    def test_google_followups_avoid_unsupported_relationship_language(self):
        for path_value in self.google["outputs"].values():
            lowered = Path(path_value).read_text(encoding="utf-8").lower()
            for phrase in ("cousin", "family", "internal referral"):
                self.assertNotIn(phrase, lowered)

    def test_dashboard_links_followup_materials(self):
        result = generate_dashboard(self.project_root)
        content = Path(result["output_path"]).read_text(encoding="utf-8")
        strategy_name = Path(self.paramount["outputs"]["followup_strategy"]).name

        self.assertIn("Follow-Up Materials", content)
        self.assertIn(strategy_name, content)

    def test_followups_cli_command_reports_role_status_and_files(self):
        output = io.StringIO()
        with patch("scripts.cli.PROJECT_ROOT", self.project_root), redirect_stdout(
            output
        ):
            return_code = main(["followups", PARAMOUNT_ID])

        rendered = output.getvalue()
        self.assertEqual(return_code, 0)
        self.assertIn("Company: Paramount", rendered)
        self.assertIn("Role: Director, Marketing Operations", rendered)
        self.assertIn("Status: Applied", rendered)
        self.assertIn("Generated follow-up files:", rendered)
        self.assertIn("Follow-up materials generated successfully.", rendered)

    def test_all_six_submitted_application_statuses_remain_applied(self):
        by_id = {
            application["id"]: application
            for application in load_application_tracker(self.project_root)
        }
        self.assertEqual(
            {
                tracker_id: get_record_status(by_id[tracker_id])
                for tracker_id in SUBMITTED_IDS
            },
            {tracker_id: "Applied" for tracker_id in SUBMITTED_IDS},
        )


if __name__ == "__main__":
    unittest.main()
