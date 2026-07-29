from datetime import date
from pathlib import Path
import tempfile
import unittest

from app import build_prospect_payload, contextual_primary_actions, summarize_applications
from scripts.application_tracker import (
    VALID_STATUSES,
    add_prospect,
    follow_up_eligibility,
    get_record_status,
    load_application_tracker,
)
from scripts.generate_dashboard import (
    record_application_portal_url,
    record_posting_url,
)


class ApplicationStatusPortalCleanupTests(unittest.TestCase):
    def test_primary_status_model_and_legacy_mapping(self):
        self.assertEqual(
            VALID_STATUSES,
            ("Drafted", "Paused", "Applied", "Under Consideration", "Interviewing", "Offer", "Rejected", "Withdrawn / Closed"),
        )
        cases = {
            "Active": "Drafted",
            "Reviewed": "Drafted",
            "Paused": "Paused",
            "Follow-up": "Applied",
            "Pass": "Withdrawn / Closed",
            "Invalid/Hidden": "Withdrawn / Closed",
        }
        for legacy, expected in cases.items():
            self.assertEqual(get_record_status({"status": legacy}), expected)

    def test_legacy_value_is_preserved_when_record_is_migrated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data").mkdir()
            (root / "data" / "application_tracker.yml").write_text("applications: []\n")
            add_prospect({
                "id": "legacy",
                "company": "Acme",
                "role": "Operator",
                "status": "Follow-up",
                "priority": "High",
                "show_on_dashboard": True,
            }, root)
            saved = load_application_tracker(root)[0]
            self.assertEqual(saved["status"], "Applied")
            self.assertEqual(saved["legacy_status"], "Follow-up")

    def test_posting_and_application_portal_urls_are_independent(self):
        values = build_prospect_payload({
            "posting_url": "https://jobs.example/role",
            "application_portal_url": "https://portal.example/my-applications",
        })
        self.assertEqual(record_posting_url(values), "https://jobs.example/role")
        self.assertEqual(record_application_portal_url(values), "https://portal.example/my-applications")
        self.assertNotEqual(record_posting_url(values), record_application_portal_url(values))

    def test_follow_up_eligibility_is_derived_and_safe(self):
        eligible = {
            "status": "Applied",
            "submitted_date": "2026-07-01",
            "show_on_dashboard": True,
            "recruiter_email": "recruiter@example.com",
        }
        self.assertTrue(follow_up_eligibility(eligible, date(2026, 7, 13))[0])
        self.assertFalse(follow_up_eligibility(dict(eligible, submitted_date="2026-07-11"), date(2026, 7, 13))[0])
        for updates in (
            {"portal_only": True},
            {"no_contact": True},
            {"follow_up_status": "Not applicable"},
            {"status": "Rejected"},
            {"status": "Withdrawn / Closed"},
            {"show_on_dashboard": False},
        ):
            self.assertFalse(follow_up_eligibility(dict(eligible, **updates), date(2026, 7, 13))[0])

    def test_contextual_actions_and_summary_use_primary_statuses(self):
        actions = contextual_primary_actions(
            {"status": "Applied", "submitted_date": "2026-07-01", "follow_up_status": "Due now"},
            has_materials=True,
            has_posting_url=True,
        )
        self.assertIn(("Open posting", "open_posting"), actions)
        summary = summarize_applications([
            {"status": "Active"},
            {"status": "Applied"},
            {"status": "Rejected"},
        ])
        self.assertEqual(summary, {"Total": 3, "Drafted": 1, "Applied": 1, "Rejected": 1})


if __name__ == "__main__":
    unittest.main()
