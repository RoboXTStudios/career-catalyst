import inspect
import unittest

import app
from scripts.application_tracker import workflow_status_bucket
from scripts.generate_dashboard import (
    _partition_packages,
    _render_html,
    _summary_counts,
    filter_dashboard_records,
    select_dashboard_mode,
)


def _record(identifier, status="Active", **updates):
    record = {
        "id": identifier,
        "company": identifier.title(),
        "role": "Director, Operations",
        "status": status,
        "priority": "Medium",
        "show_on_dashboard": True,
        "source": "Official career page",
        "location": "Los Angeles, CA",
        "salary_range": "$150,000-$180,000",
        "freshness": "Fresh",
        "posting_status": "Open",
        "verification_status": "Employer Source",
        "source_trust_label": "Direct Employer",
        "match_tier": "Good Match",
        "recommended_action": "Generate Package",
    }
    record.update(updates)
    return record


class SummaryBucketTests(unittest.TestCase):
    def test_applied_bucket_counts_status_variants_and_applied_evidence(self):
        records = [
            _record("applied", "Applied"),
            _record("follow", "Follow-up"),
            _record("sent", "Follow-Up Sent"),
            _record("due", "Due Now"),
            _record("submitted", "Submitted"),
            _record("interview", "Interviewing"),
            _record("recruiter", "Recruiter Contacted"),
            _record("manager", "Hiring Manager Contacted"),
            _record("active_applied", "Active", submitted_date="2026-07-01"),
        ]
        summary = app.summarize_applications(records)
        self.assertEqual(summary["Applied / Follow-up"], len(records))
        self.assertGreater(summary["Applied / Follow-up"], 0)
        self.assertEqual(summary["Active"], 0)

    def test_all_summary_buckets_are_exclusive_and_normalized(self):
        records = [
            _record("active", "Active"),
            _record("drafted", "Drafted"),
            _record("open", "Open"),
            _record("reviewed", "Reviewed"),
            _record("manual", "Manually Reviewed"),
            _record("paused", "Paused"),
            _record("pass", "Passed"),
            _record("hidden", "Invalid/Hidden", show_on_dashboard=False),
            _record("closed", "Closed", show_on_dashboard=False),
        ]
        summary = app.summarize_applications(records)
        self.assertEqual(
            summary,
            {
                "Total": 9,
                "Active": 3,
                "Applied / Follow-up": 0,
                "Reviewed": 2,
                "Paused": 1,
                "Pass": 1,
                "Hidden / Invalid": 2,
            },
        )
        self.assertEqual(sum(value for key, value in summary.items() if key != "Total"), 9)

    def test_terminal_buckets_override_submitted_date(self):
        self.assertEqual(
            workflow_status_bucket(_record("paused", "Paused", submitted_date="2026-06-01")),
            "Paused",
        )
        self.assertEqual(
            workflow_status_bucket(_record("pass", "Pass", submitted_date="2026-06-01")),
            "Pass",
        )
        self.assertEqual(
            workflow_status_bucket(
                _record("hidden", "Invalid/Hidden", submitted_date="2026-06-01")
            ),
            "Hidden / Invalid",
        )

    def test_static_summary_uses_the_same_buckets(self):
        packages = [
            {"company": record["company"], "role": record["role"], "tracker": record, "files": {}}
            for record in (
                _record("active"),
                _record("applied", "Follow-up"),
                _record("paused", "Paused"),
                _record("pass", "Pass"),
                _record("hidden", "Invalid/Hidden"),
            )
        ]
        groups = _partition_packages(packages)
        counts = _summary_counts(None, groups)
        self.assertEqual(counts["Active"], 1)
        self.assertEqual(counts["Applied / Follow-up"], 1)
        self.assertEqual(counts["Paused"], 1)
        self.assertEqual(counts["Pass"], 1)
        self.assertEqual(counts["Hidden / Invalid"], 1)

    def test_static_html_uses_clear_bucket_headings(self):
        groups = {
            "active": [],
            "applied": [],
            "reviewed": [],
            "paused": [],
            "pass": [],
            "hidden": [],
        }
        counts = {
            "Total": 0,
            "Active": 0,
            "Applied / Follow-up": 0,
            "Reviewed": 0,
            "Paused": 0,
            "Pass": 0,
            "Hidden / Invalid": 0,
        }
        content = _render_html(groups, counts, [], app.PROJECT_ROOT / "exports/dashboard")
        for heading in ("Active", "Applied / Follow-Up", "Reviewed", "Paused", "Passed"):
            self.assertIn(f">{heading}<", content)


class SummaryNavigationAndModeTests(unittest.TestCase):
    def test_summary_navigation_sets_predictable_mode_and_filter(self):
        expected = {
            "Active": ("All Mode", "Active"),
            "Applied / Follow-up": ("Follow-Up Mode", "Applied / Follow-up"),
            "Paused": ("All Mode", "Paused"),
            "Pass": ("Cleanup Mode", "Pass"),
            "Hidden / Invalid": ("Cleanup Mode", "Invalid/Hidden"),
        }
        for bucket, (mode, status_filter) in expected.items():
            state = {"dashboard_focused_role_id": "old"}
            app.apply_summary_navigation(state, bucket)
            self.assertEqual(state["dashboard_mode"], mode)
            self.assertEqual(state["dashboard_status"], status_filter)
            self.assertNotIn("dashboard_focused_role_id", state)

    def test_bucket_filters_match_summary_semantics(self):
        records = [
            _record("active"),
            _record("drafted", "Drafted"),
            _record("applied_status", "Applied"),
            _record("applied_date", "Active", submitted_date="2026-07-01"),
            _record("paused", "Paused"),
            _record("pass", "Pass"),
            _record("hidden", "Invalid/Hidden"),
        ]
        self.assertEqual(
            {item["id"] for item in filter_dashboard_records(records, application_status="Active")},
            {"active", "drafted"},
        )
        self.assertEqual(
            {
                item["id"]
                for item in filter_dashboard_records(
                    records, application_status="Applied / Follow-up"
                )
            },
            {"applied_status", "applied_date"},
        )

    def test_modes_exclude_terminal_records_and_keep_expected_work(self):
        records = [
            _record("apply", match_tier="Strong Match"),
            _record("applied", "Active", submitted_date="2026-07-01"),
            _record("reviewed", "Reviewed"),
            _record("paused", "Paused"),
            _record("pass", "Pass"),
            _record("hidden", "Invalid/Hidden"),
        ]
        self.assertEqual(
            [item["id"] for item in select_dashboard_mode(records, "Apply Mode")],
            ["apply"],
        )
        self.assertEqual(
            [item["id"] for item in select_dashboard_mode(records, "Follow-Up Mode")],
            ["applied"],
        )
        self.assertNotIn("pass", {item["id"] for item in select_dashboard_mode(records, "Review Mode")})
        self.assertNotIn("hidden", {item["id"] for item in select_dashboard_mode(records, "Review Mode")})

    def test_groups_match_summary_buckets(self):
        records = [
            _record("active"),
            _record("drafted", "Drafted"),
            _record("applied", "Active", submitted_date="2026-07-01"),
            _record("reviewed", "Reviewed"),
            _record("paused", "Paused"),
            _record("pass", "Pass"),
            _record("hidden", "Invalid/Hidden"),
        ]
        groups = app.group_applications_by_status(records)
        self.assertEqual({item["id"] for item in groups["Active"]}, {"active", "drafted"})
        self.assertEqual([item["id"] for item in groups["Applied / Follow-Up"]], ["applied"])
        self.assertEqual([item["id"] for item in groups["Reviewed"]], ["reviewed"])
        self.assertEqual([item["id"] for item in groups["Paused"]], ["paused"])
        self.assertEqual([item["id"] for item in groups["Passed"]], ["pass"])
        self.assertEqual([item["id"] for item in groups["Hidden / Invalid"]], ["hidden"])


class ClarityAndActionTests(unittest.TestCase):
    def test_primary_actions_are_contextual_and_never_exceed_four(self):
        scenarios = (
            (_record("active"), {"Open posting", "Generate package", "Mark Applied"}),
            (
                _record("applied", "Active", submitted_date="2026-07-01", follow_up_status="Due now"),
                {"Open materials", "Open posting", "Mark follow-up sent"},
            ),
            (_record("paused", "Paused"), {"Resume / Active", "Pass", "Hide / Invalid"}),
            (_record("pass", "Pass"), {"Reopen / Active", "Hide / Invalid"}),
            (_record("hidden", "Invalid/Hidden"), {"Reopen / Active"}),
        )
        for record, expected in scenarios:
            actions = app.contextual_primary_actions(
                record, has_materials=True, has_posting_url=True
            )
            self.assertLessEqual(len(actions), 4)
            self.assertEqual({label for label, _ in actions}, expected)

    def test_next_steps_are_navigation_first_with_only_mode_specific_mutations(self):
        source = inspect.getsource(app._render_recommended_next_steps)
        for label in ("View role", "Open posting", "Open materials"):
            self.assertIn(label, source)
        self.assertNotIn("Generate package", source)
        self.assertNotIn("Verify manually", source)
        self.assertNotIn('mode == "Cleanup Mode"', source)
        self.assertNotIn('mode == "Follow-Up Mode"', source)

    def test_focus_and_advanced_edit_remain_stable_and_secondary(self):
        state = {"dashboard_mode": "Follow-Up Mode", "dashboard_status": "Applied / Follow-up"}
        app.focus_dashboard_role(state, "stable_role_id")
        self.assertEqual(state["dashboard_focused_role_id"], "stable_role_id")
        app.clear_focused_dashboard_role(state)
        self.assertEqual(state["dashboard_mode"], "Follow-Up Mode")
        source = inspect.getsource(app._render_role_card)
        self.assertIn('with st.expander("More actions"', source)
        self.assertIn('with st.expander("Advanced edit role"', source)
        self.assertLess(source.index('with st.expander("Advanced edit role"'), source.index("edited_status ="))


if __name__ == "__main__":
    unittest.main()
