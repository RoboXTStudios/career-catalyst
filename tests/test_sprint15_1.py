import inspect
import tempfile
import unittest
from pathlib import Path

import yaml

import app
from scripts.application_tracker import (
    get_record_status,
    load_application_tracker,
    normalize_status,
)
from scripts.generate_dashboard import (
    STATUS_FILTERS,
    filter_dashboard_records,
    recommended_next_steps,
    select_dashboard_mode,
)


def _record(identifier, **updates):
    record = {
        "id": identifier,
        "company": identifier.title(),
        "role": "Director, Operations",
        "status": "Active",
        "priority": "Medium",
        "notes": "",
        "next_action": "Review fit",
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


class StatusNormalizationTests(unittest.TestCase):
    def test_supported_and_legacy_values_normalize_consistently(self):
        expected = {
            "Pass": "Pass",
            "passed": "Pass",
            "Paused": "Paused",
            "on hold": "Paused",
            "Invalid/Hidden": "Invalid/Hidden",
            "hidden": "Invalid/Hidden",
            "submitted": "Applied",
            "followup": "Follow-up",
        }
        for value, canonical in expected.items():
            self.assertEqual(normalize_status(value), canonical)
        self.assertEqual(normalize_status("Contacted"), "Contacted")

    def test_canonical_status_wins_over_stale_derived_fields(self):
        record = {
            "status": "Pass",
            "application_status": "Applied",
            "dashboard_status": "Active",
            "stage": "Submitted",
        }
        self.assertEqual(get_record_status(record), "Pass")
        self.assertEqual(get_record_status({"application_status": "submitted"}), "Applied")


class DashboardStatusActionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data").mkdir()
        self.original = [_record("first"), _record("second")]
        self._write(self.original)

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, records):
        (self.root / "data" / "application_tracker.yml").write_text(
            yaml.safe_dump({"applications": records}, sort_keys=False),
            encoding="utf-8",
        )

    def _stored(self):
        return {item["id"]: item for item in load_application_tracker(self.root)}

    def test_each_button_action_updates_only_the_stable_target_id(self):
        expected = {
            "applied": "Applied",
            "paused": "Paused",
            "pass": "Pass",
            "invalid_hidden": "Invalid/Hidden",
            "active": "Active",
        }
        for action, status in expected.items():
            self._write(self.original)
            updated = app.apply_dashboard_status_action("second", action, self.root)
            stored = self._stored()
            self.assertEqual(get_record_status(updated), status)
            self.assertEqual(get_record_status(stored["second"]), status)
            self.assertEqual(stored["first"], self.original[0])
            self.assertEqual(
                stored["second"]["show_on_dashboard"],
                status not in {"Pass", "Invalid/Hidden"},
            )

    def test_pass_paused_and_invalid_render_and_group_from_saved_status(self):
        for action, label in (
            ("pass", "Passed"),
            ("paused", "Paused"),
            ("invalid_hidden", "Hidden / Invalid"),
        ):
            self._write(self.original)
            updated = app.apply_dashboard_status_action("second", action, self.root)
            self.assertIn(get_record_status(updated), app._status_badges(updated))
            grouped = app.group_applications_by_status(
                list(self._stored().values()), mode="Cleanup Mode"
            )
            self.assertEqual([item["id"] for item in grouped[label]], ["second"])

    def test_reopening_clears_stale_hidden_visibility(self):
        records = [
            _record("first"),
            _record("second", status="Invalid/Hidden", show_on_dashboard=False),
        ]
        self._write(records)
        updated = app.apply_dashboard_status_action("second", "active", self.root)
        self.assertEqual(get_record_status(updated), "Active")
        self.assertTrue(updated["show_on_dashboard"])

    def test_applied_actions_include_follow_up_sent_and_needed(self):
        labels = dict(app.dashboard_status_actions(_record("applied", status="Applied")))
        self.assertIn("Follow-Up Sent", labels)
        self.assertIn("Follow-Up Needed", labels)
        sent = app.apply_dashboard_status_action("second", "follow_up_sent", self.root)
        self.assertEqual(get_record_status(sent), "Follow-up")
        self.assertEqual(sent["follow_up_status"], "Follow-up sent")


class DashboardGroupingAndFilterTests(unittest.TestCase):
    def test_regular_groups_do_not_conflate_active_applied_paused_pass_hidden(self):
        records = [
            _record("applied", status="Applied"),
            _record("active", status="Active"),
            _record("drafted", status="Drafted"),
            _record("paused", status="Paused"),
            _record("pass", status="Pass", show_on_dashboard=False),
            _record("hidden", status="Invalid/Hidden", show_on_dashboard=False),
        ]
        grouped = app.group_applications_by_status(records)
        expected = {
            "Applied / Follow-Up": "applied",
            "Active": "active",
            "Drafted / Reviewed": "drafted",
            "Paused": "paused",
            "Passed": "pass",
            "Hidden / Invalid": "hidden",
        }
        for label, identifier in expected.items():
            self.assertEqual([item["id"] for item in grouped[label]], [identifier])

    def test_cleanup_mode_includes_and_labels_every_cleanup_reason(self):
        records = [
            _record("weak", match_tier="Weak Match"),
            _record("paused", status="Paused"),
            _record("pass", status="Pass", show_on_dashboard=False),
            _record("hidden", status="Invalid/Hidden", show_on_dashboard=False),
            _record("stale", verification_status="Stale / Closed Risk"),
            _record("cannot", verification_status="Cannot Verify"),
            _record("unknown", source_trust_label="Unknown Source"),
            _record("aggregator", verification_status="Aggregator Only"),
        ]
        cleanup = select_dashboard_mode(records, "Cleanup Mode")
        self.assertEqual({item["id"] for item in cleanup}, {item["id"] for item in records})
        grouped = app.group_applications_by_status(cleanup, mode="Cleanup Mode")
        self.assertEqual([item["id"] for item in grouped["Paused"]], ["paused"])
        self.assertEqual([item["id"] for item in grouped["Passed"]], ["pass"])
        self.assertEqual([item["id"] for item in grouped["Hidden / Invalid"]], ["hidden"])
        self.assertEqual(
            {item["id"] for item in grouped["Stale / Cannot Verify"]},
            {"stale", "cannot", "unknown"},
        )
        self.assertEqual(
            {item["id"] for item in grouped["Needs decision"]},
            {"weak", "aggregator"},
        )

    def test_status_filters_are_canonical_and_do_not_conflate_pass_with_hidden(self):
        for status in (
            "All",
            "Drafted",
            "Active",
            "Applied",
            "Reviewed",
            "Paused",
            "Pass",
            "Invalid/Hidden",
        ):
            self.assertIn(status, STATUS_FILTERS)
        records = [
            _record("pass", status="Pass", show_on_dashboard=False),
            _record("paused", status="Paused"),
            _record("hidden", status="Invalid/Hidden", show_on_dashboard=False),
            _record("active_stale_flag", status="Active", show_on_dashboard=False),
        ]
        self.assertEqual(
            [item["id"] for item in filter_dashboard_records(records, application_status="Pass")],
            ["pass"],
        )
        self.assertEqual(
            [item["id"] for item in filter_dashboard_records(records, application_status="Paused")],
            ["paused"],
        )
        self.assertEqual(
            [item["id"] for item in filter_dashboard_records(records, application_status="Invalid/Hidden")],
            ["hidden"],
        )
        self.assertEqual(
            [item["id"] for item in select_dashboard_mode(records, "All Mode")],
            ["paused", "active_stale_flag"],
        )


class RecommendedStepsAndFallbackTests(unittest.TestCase):
    def test_cleanup_guidance_respects_existing_status(self):
        scenarios = (
            (_record("pass", status="Pass"), "Already passed", "mark pass"),
            (_record("hidden", status="Invalid/Hidden"), "Hidden from active workflow", "mark pass"),
            (_record("paused", status="Paused"), "Review later or mark pass", "Keep hidden"),
        )
        for record, expected, rejected in scenarios:
            step = recommended_next_steps([record], "Cleanup Mode")[0]
            self.assertIn(expected, step)
            self.assertNotIn(rejected, step)

    def test_applied_follow_up_guidance_still_works(self):
        record = _record(
            "applied",
            status="Applied",
            follow_up_status="Due now",
            suggested_follow_up_date="2026-07-06",
            _follow_up_materials_status="Available",
        )
        step = recommended_next_steps([record], "Follow-Up Mode")[0]
        self.assertIn("Due now", step)
        self.assertIn("Use existing follow-up materials", step)

    def test_buttons_and_advanced_tab_share_canonical_update_helper(self):
        card_source = inspect.getsource(app._render_role_card)
        tab_source = inspect.getsource(app._render_update_status)
        self.assertIn("apply_dashboard_status_action", card_source)
        self.assertIn("update_dashboard_role", tab_source)
        self.assertNotIn("updated = update_status(", tab_source)
        self.assertIn("dashboard_quick_{tracker_id}_{action_key}", card_source)


if __name__ == "__main__":
    unittest.main()
