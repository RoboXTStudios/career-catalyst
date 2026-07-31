import inspect
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import yaml

import app
from scripts.application_tracker import (
    VALID_STATUSES,
    load_application_tracker,
    validate_tracker_entries,
)
from scripts.generate_dashboard import (
    STATUS_FILTERS,
    _package_for_asset,
    _render_metadata,
    filter_dashboard_records,
    prepare_dashboard_records,
    select_dashboard_mode,
)


def _record(identifier, **updates):
    record = {
        "id": identifier,
        "company": identifier.title(),
        "role": "Director, Operations",
        "status": "Prospect",
        "priority": "Medium",
        "notes": "",
        "next_action": "Review fit",
        "show_on_dashboard": True,
        "source": "Official career page",
        "salary_range": "$150,000-$180,000",
        "freshness": "Fresh",
        "posting_status": "Open",
        "verification_status": "Employer Source",
        "match_tier": "Good Match",
        "recommended_action": "Generate Package",
    }
    record.update(updates)
    return record


class Sprint15StatusTests(unittest.TestCase):
    def test_required_statuses_are_supported_and_filterable(self):
        for status in VALID_STATUSES:
            self.assertIn(status, VALID_STATUSES)
            self.assertIn(status, STATUS_FILTERS)

    def test_unknown_legacy_status_is_preserved_as_warning(self):
        report = validate_tracker_entries([_record("legacy", status="Contacted")])
        self.assertEqual(report["errors"], [])
        self.assertTrue(any("legacy status" in warning for warning in report["warnings"]))

    def test_cleanup_includes_pass_and_invalid_hidden(self):
        records = [
            _record("pass", status="Pass"),
            _record("hidden", status="Invalid/Hidden"),
            _record("active", status="Active"),
        ]
        cleanup_ids = {
            item["id"] for item in select_dashboard_mode(records, "Cleanup Mode")
        }
        self.assertTrue({"pass", "hidden"}.issubset(cleanup_ids))

    def test_withdrawn_closed_can_be_explicitly_filtered(self):
        records = [_record("pass", status="Pass"), _record("active", status="Active")]
        self.assertEqual(
            [item["id"] for item in filter_dashboard_records(records, application_status="Withdrawn / Closed")],
            ["pass"],
        )


class Sprint15InlineUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data").mkdir()
        self.records = [_record("first"), _record("second")]
        (self.root / "data" / "application_tracker.yml").write_text(
            yaml.safe_dump({"applications": self.records}, sort_keys=False),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_inline_update_targets_stable_id_and_persists_all_fields(self):
        updated = app.update_dashboard_role(
            "second",
            {
                "status": "Applied",
                "priority": "High",
                "notes": "Applied through employer site.",
                "next_action": "Follow up with recruiter.",
                "follow_up_status": "Due soon",
                "suggested_follow_up_date": "2026-07-10",
                "show_on_dashboard": True,
            },
            self.root,
        )
        stored = {item["id"]: item for item in load_application_tracker(self.root)}
        self.assertEqual(stored["first"], self.records[0])
        self.assertEqual(updated["status"], "Applied")
        self.assertEqual(stored["second"]["priority"], "High")
        self.assertEqual(stored["second"]["notes"], "Applied through employer site.")
        self.assertEqual(stored["second"]["next_action"], "Follow up with recruiter.")
        self.assertEqual(stored["second"]["follow_up_status"], "Due soon")
        self.assertEqual(stored["second"]["suggested_follow_up_date"], "2026-07-10")
        self.assertIn("status_updated_at", stored["second"])

    def test_canonical_quick_statuses_persist(self):
        for status in ("Considered", "Withdrawn / Closed"):
            app.update_dashboard_role("second", {"status": status}, self.root)
            stored = {item["id"]: item for item in load_application_tracker(self.root)}
            self.assertEqual(stored["second"]["status"], status)
        self.assertTrue(stored["second"]["show_on_dashboard"])

    def test_legacy_status_can_update_notes_without_crashing(self):
        records = load_application_tracker(self.root)
        records[1]["status"] = "Contacted"
        (self.root / "data" / "application_tracker.yml").write_text(
            yaml.safe_dump({"applications": records}, sort_keys=False),
            encoding="utf-8",
        )
        updated = app.update_dashboard_role(
            "second", {"status": "Contacted", "notes": "Keep legacy state."}, self.root
        )
        self.assertEqual(updated["status"], "Contacted")
        self.assertEqual(updated["notes"], "Keep legacy state.")

    def test_advanced_selection_stays_on_same_stable_id(self):
        ids = ["first", "second"]
        self.assertEqual(app.resolve_selected_tracker_id(ids, "second"), "second")
        self.assertEqual(app.resolve_selected_tracker_id(ids, "removed"), "first")


class Sprint15MaterialsTests(unittest.TestCase):
    def test_compact_generated_names_match_netflix_paramount_fieldai_and_bandsintown(self):
        examples = (
            (
                "Netflix",
                "Associate Manager, UCAN Marketing Operations",
                "TrishaLynch_AssociateManagerUcanMarketingOps_Netflix_FollowupStrategy.md",
            ),
            (
                "Paramount",
                "Director, Marketing Operations",
                "TrishaLynch_DirectorMarketingOps_Paramount_FollowupStrategy.md",
            ),
            (
                "FieldAI",
                "Director of Matrix Operations & Organizational Efficiency",
                "TrishaLynch_DirectorMatrixOpsOrganizationalEfficiency_Fieldai_FollowupStrategy.md",
            ),
            (
                "BandsInTown",
                "Senior Copywriter & Content Strategist",
                "TrishaLynch_SeniorCopywriterContentStrategist_Bandsintown_FollowupStrategy.md",
            ),
        )
        for company, role, filename in examples:
            package = {"company": company, "role": role, "tracker": {"id": company}}
            self.assertIs(
                _package_for_asset(Path("exports/followups") / filename, [package]),
                package,
            )

    def test_material_state_is_contextual_and_safe(self):
        follow_up = Path("exports/followups/example_FollowupStrategy.md")
        message = Path("exports/messages/example_RecruiterMessage.md")
        applications = [
            _record("applied", status="Applied"),
            _record("missing", status="Applied"),
            _record("considered", status="Considered"),
            _record("pass", status="Pass"),
        ]
        packages = {
            "applied": {"files": {"Follow-Up Materials": follow_up}},
            "missing": {"files": {}},
            "considered": {"files": {"Recruiter Message": message}},
            "pass": {"files": {"Follow-Up Materials": follow_up}},
        }
        states = {
            item["id"]: item for item in prepare_dashboard_records(applications, packages)
        }
        self.assertEqual(states["applied"]["_follow_up_materials_status"], "Available")
        self.assertEqual(states["missing"]["_follow_up_materials_status"], "Missing")
        self.assertEqual(states["considered"]["_materials_availability_label"], "Application messages available")
        self.assertEqual(states["pass"]["follow_up_status"], "Not applicable")
        self.assertEqual(states["pass"]["_follow_up_materials_status"], "Not applicable")

    def test_html_and_streamlit_helpers_expose_material_and_inline_states(self):
        record = _record(
            "html",
            status="Applied",
            follow_up_status="Due soon",
            _materials_availability_label="Follow-up materials available",
        )
        html_content = _render_metadata({"tracker": record})
        self.assertIn("Materials availability", html_content)
        self.assertIn("Follow-up materials available", html_content)
        card_source = inspect.getsource(app._render_role_card)
        for text in (
            "Save role updates",
            "Generate Follow-Up Materials",
            "dashboard_notes_",
            "dashboard_next_action_",
            "dashboard_follow_up_",
        ):
            self.assertIn(text, card_source)


if __name__ == "__main__":
    unittest.main()
