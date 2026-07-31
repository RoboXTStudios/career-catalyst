"""Compatibility coverage for the canonical Sprint 32 lifecycle."""

import inspect
import unittest

import app
from scripts.application_tracker import get_record_status
from scripts.generate_dashboard import (
    _partition_packages,
    _summary_counts,
    filter_dashboard_records,
    select_dashboard_mode,
)
from scripts.role_lifecycle import LIVE_STATUSES


def _record(identifier, status="Prospect", **updates):
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


class SummaryLifecycleTests(unittest.TestCase):
    def test_summary_counts_every_live_status_exclusively(self):
        records = [_record(str(index), status) for index, status in enumerate(LIVE_STATUSES)]
        summary = app.summarize_applications(records)
        self.assertEqual(summary["Total"], len(LIVE_STATUSES))
        self.assertEqual(sum(value for key, value in summary.items() if key != "Total"), len(records))
        for status in LIVE_STATUSES:
            self.assertEqual(summary[status], 1)

    def test_legacy_inputs_resolve_to_current_statuses(self):
        self.assertEqual(get_record_status(_record("active", "Active")), "Prospect")
        self.assertEqual(get_record_status(_record("reviewed", "Reviewed")), "Considered")
        self.assertEqual(get_record_status(_record("legacy_hold", "Paused")), "Considered")
        self.assertEqual(get_record_status(_record("pass", "Pass")), "Withdrawn / Closed")

    def test_static_summary_uses_canonical_statuses(self):
        packages = [
            {"company": record["company"], "role": record["role"], "tracker": record, "files": {}}
            for record in (
                _record("prospect", "Prospect"),
                _record("considered", "Considered"),
                _record("applied", "Applied"),
                _record("closed", "Withdrawn / Closed"),
            )
        ]
        counts = _summary_counts(None, _partition_packages(packages))
        self.assertEqual(counts["Total"], 4)
        self.assertEqual(counts["Prospect"], 1)
        self.assertEqual(counts["Considered"], 1)
        self.assertEqual(counts["Applied"], 1)
        self.assertEqual(counts["Withdrawn / Closed"], 1)


class FilterAndModeTests(unittest.TestCase):
    def test_summary_navigation_sets_exact_canonical_filter(self):
        for status in LIVE_STATUSES:
            state = {"dashboard_focused_role_id": "old"}
            app.apply_summary_navigation(state, status)
            self.assertEqual(state["dashboard_status"], status)
            self.assertNotIn("dashboard_focused_role_id", state)

    def test_dropdown_filter_matches_status_exactly(self):
        records = [_record(str(index), status) for index, status in enumerate(LIVE_STATUSES)]
        for index, status in enumerate(LIVE_STATUSES):
            self.assertEqual(
                [item["id"] for item in filter_dashboard_records(records, application_status=status)],
                [str(index)],
            )

    def test_all_mode_keeps_terminal_roles_until_explicit_archive(self):
        records = [
            _record("prospect"),
            _record("rejected", "Rejected"),
            _record("closed", "Withdrawn / Closed"),
            _record("archived", "Rejected", archived=True),
        ]
        self.assertEqual(
            [item["id"] for item in select_dashboard_mode(records, "All Mode")],
            ["prospect", "rejected", "closed"],
        )


class ClarityAndActionTests(unittest.TestCase):
    def test_primary_actions_are_contextual_and_never_exceed_four(self):
        scenarios = (
            (_record("prospect"), {"Open posting", "Generate package", "Mark Applied"}),
            (_record("considered", "Considered"), {"Open materials", "Mark Applied", "Withdraw / Close"}),
            (_record("rejected", "Rejected"), set()),
        )
        for record, expected in scenarios:
            actions = app.contextual_primary_actions(
                record, has_materials=True, has_posting_url=True
            )
            self.assertLessEqual(len(actions), 4)
            self.assertEqual({label for label, _ in actions}, expected)

    def test_focus_and_advanced_edit_remain_stable_and_secondary(self):
        state = {"dashboard_status": "Applied"}
        app.focus_dashboard_role(state, "stable_role_id")
        self.assertEqual(state["dashboard_focused_role_id"], "stable_role_id")
        app.clear_focused_dashboard_role(state)
        source = inspect.getsource(app._render_role_card)
        self.assertIn('with st.expander("More actions"', source)
        self.assertIn('with st.expander("Advanced edit role"', source)


if __name__ == "__main__":
    unittest.main()
