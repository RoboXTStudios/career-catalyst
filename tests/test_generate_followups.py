import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.application_tracker import load_application_tracker
from scripts.cli import main
from scripts.generate_dashboard import generate_dashboard
from scripts.generate_followups import MESSAGE_LIMITS, generate_followups


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARAMOUNT_ID = "paramount_director_marketing_operations"
GOOGLE_ID = "google_strategy_ops_youtube_auction_brand"
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
        cls.paramount = generate_followups(PARAMOUNT_ID, PROJECT_ROOT)
        cls.google = generate_followups(GOOGLE_ID, PROJECT_ROOT)

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
        result = generate_dashboard(PROJECT_ROOT)
        content = Path(result["output_path"]).read_text(encoding="utf-8")
        strategy_name = Path(self.paramount["outputs"]["followup_strategy"]).name

        self.assertIn("Follow-Up Materials", content)
        self.assertIn(strategy_name, content)

    def test_followups_cli_command_reports_role_status_and_files(self):
        output = io.StringIO()
        with redirect_stdout(output):
            return_code = main(["followups", PARAMOUNT_ID])

        rendered = output.getvalue()
        self.assertEqual(return_code, 0)
        self.assertIn("Company: Paramount", rendered)
        self.assertIn("Role: Director, Marketing Operations", rendered)
        self.assertIn("Status: Applied", rendered)
        self.assertIn("Generated follow-up files:", rendered)
        self.assertIn("Follow-up materials generated successfully.", rendered)

    def test_all_six_submitted_application_statuses_remain_applied(self):
        expected_ids = {
            "playstation_head_global_creative_ops",
            "google_strategy_ops_youtube_auction_brand",
            "paramount_director_marketing_operations",
            "united_talent_agency_director_transformation",
            "disney_entertainment_and_espn_product_technology_director_strategy_operations_product_technology",
            "fieldai_director_of_matrix_operations_organizational_efficiency",
        }
        by_id = {
            application["id"]: application
            for application in load_application_tracker(PROJECT_ROOT)
        }
        self.assertEqual(
            {tracker_id: by_id[tracker_id]["status"] for tracker_id in expected_ids},
            {tracker_id: "Applied" for tracker_id in expected_ids},
        )


if __name__ == "__main__":
    unittest.main()
