import inspect
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

import yaml

import app
from scripts.archive_generated_materials import archive_generated_materials, main as archive_main
from scripts.generate_dashboard import (
    _attach_assets,
    load_application_packages,
    record_posting_url,
    structured_recommended_next_steps,
)


def _record(identifier="acme_director_operations", **updates):
    record = {
        "id": identifier,
        "company": "Acme",
        "company_aliases": [],
        "role": "Director, Operations",
        "role_aliases": [],
        "status": "Active",
        "priority": "High",
        "show_on_dashboard": True,
        "source": "Official career page",
        "location": "Los Angeles, CA",
        "work_arrangement": "Hybrid",
        "salary_range": "$150,000-$180,000",
        "verification_status": "Employer Source",
        "source_type": "Direct Employer",
        "match_score": 88,
        "match_tier": "Strong Match",
        "recommended_action": "Generate Package",
        "next_action": "Apply this week.",
    }
    record.update(updates)
    return record


class DashboardSimplificationTests(unittest.TestCase):
    def test_primary_facts_include_core_fields_without_secondary_source_noise(self):
        record = _record(
            freshness_risk="High",
            canonical_apply_url="https://careers.example/jobs/1",
        )
        content = app._primary_facts_html(record, {})
        for label in (
            "Location",
            "Work arrangement",
            "Salary",
            "Source type",
            "Verification",
        ):
            self.assertIn(label, content)
        self.assertNotIn("Freshness Risk", content)
        self.assertNotIn("Canonical Apply URL", content)

    def test_secondary_details_and_advanced_dropdown_are_inside_expanders(self):
        source = inspect.getsource(app._render_role_card)
        for label in (
            'st.expander("Match details"',
            'st.expander("Source Verification"',
            'st.expander("Notes"',
            'with st.expander("Advanced edit role"',
        ):
            self.assertIn(label, source)
        self.assertIn("Use quick actions for common workflow changes", source)
        self.assertLess(source.index('with st.expander("Advanced edit role"'), source.index("edited_status ="))

    def test_quick_actions_include_posting_material_and_common_status_buttons(self):
        labels = dict(app.dashboard_status_actions(_record()))
        for label in (
            "Mark Applied",
            "Mark Reviewed",
            "Pause",
            "Pass",
            "Hide / Invalid",
            "Keep Active",
        ):
            self.assertIn(label, labels)
        source = inspect.getsource(app._render_role_card)
        self.assertIn("contextual_primary_actions", source)
        self.assertIn("open_posting", source)
        self.assertIn("open_materials", source)
        self.assertIn("dashboard_quick_{tracker_id}_{action_key}", source)


class RecommendedActionTests(unittest.TestCase):
    def test_structured_step_has_stable_identity_action_url_and_materials(self):
        record = _record(
            canonical_apply_url="https://careers.example/jobs/1",
            _material_paths={"Cover Letter": "/tmp/cover.md"},
        )
        step = structured_recommended_next_steps([record], "Apply Mode")[0]
        self.assertEqual(step["tracker_id"], record["id"])
        self.assertEqual(step["company"], "Acme")
        self.assertEqual(step["title"], "Director, Operations")
        self.assertEqual(step["action_type"], "generate_package")
        self.assertEqual(step["priority"], 1)
        self.assertEqual(step["posting_url"], "https://careers.example/jobs/1")
        self.assertEqual(step["material_paths"]["Cover Letter"], "/tmp/cover.md")

    def test_open_posting_exists_only_for_a_stored_http_url(self):
        self.assertEqual(
            record_posting_url(_record(original_source_url="https://example.com/job")),
            "https://example.com/job",
        )
        self.assertIsNone(record_posting_url(_record(original_source_url="Sample only")))

    def test_pass_and_hidden_steps_do_not_become_active_or_follow_up_actions(self):
        passed = structured_recommended_next_steps(
            [_record(status="Pass")], "Cleanup Mode"
        )[0]
        hidden = structured_recommended_next_steps(
            [_record(status="Invalid/Hidden")], "Cleanup Mode"
        )[0]
        self.assertEqual(passed["action_type"], "passed")
        self.assertIn("Already passed", passed["recommendation"])
        self.assertEqual(hidden["action_type"], "hidden")
        self.assertIn("Hidden from active workflow", hidden["recommendation"])

    def test_focus_state_uses_stable_id_and_can_be_cleared(self):
        state = {"dashboard_mode": "Cleanup Mode"}
        self.assertEqual(
            app.focus_dashboard_role(state, "acme_director_operations"),
            "acme_director_operations",
        )
        self.assertEqual(state["dashboard_focused_role_id"], "acme_director_operations")
        app.clear_focused_dashboard_role(state)
        self.assertNotIn("dashboard_focused_role_id", state)
        self.assertEqual(state["dashboard_mode"], "Cleanup Mode")

    def test_next_step_ui_wires_focus_and_stable_status_actions(self):
        source = inspect.getsource(app._render_recommended_next_steps)
        self.assertIn("focus_dashboard_role", source)
        self.assertIn("apply_dashboard_status_action", source)
        self.assertIn('key=f"next_{action_key}_{tracker_id}"', source)
        self.assertIn('(cleanup_actions[0], "Mark Pass", "pass")', source)
        self.assertIn(
            '(cleanup_actions[1], "Hide / Invalid", "invalid_hidden")', source
        )
        self.assertIn("Focused role", source)
        self.assertIn("Clear focus", source)


class MaterialSelectionAndArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data").mkdir()
        (self.root / "exports" / "messages").mkdir(parents=True)
        (self.root / "data" / "application_tracker.yml").write_text(
            yaml.safe_dump({"applications": [_record()]}, sort_keys=False),
            encoding="utf-8",
        )
        self.old = (
            self.root
            / "exports/messages/Trisha_Lynch_Director_Operations_Acme_Cover_Letter.md"
        )
        self.current = (
            self.root
            / "exports/messages/TrishaLynch_DirectorOperations_Acme_CoverLetter.md"
        )
        self.old.write_text("old", encoding="utf-8")
        self.current.write_text("current", encoding="utf-8")
        os.utime(self.old, (100, 100))
        os.utime(self.current, (200, 200))

    def tearDown(self):
        self.temporary.cleanup()

    def test_newest_material_is_current_and_older_duplicate_is_candidate(self):
        package = {
            "company": "Acme",
            "role": "Director, Operations",
            "tracker_id": "acme_director_operations",
            "tracker": _record(),
            "files": {},
        }
        unassigned = _attach_assets(self.root, [package])
        self.assertEqual(unassigned, [])
        self.assertEqual(package["files"]["Cover Letter"], self.current)
        self.assertEqual(package["archive_candidates"][0]["path"], self.old)

    def test_dry_run_lists_candidate_and_moves_nothing(self):
        result = archive_generated_materials(
            self.root, apply=False, archive_date=date(2026, 7, 6)
        )
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["archived_count"], 0)
        self.assertTrue(self.old.exists())
        self.assertTrue(self.current.exists())
        self.assertFalse((self.root / "exports/archive").exists())
        self.assertIn("Older duplicate", result["candidates"][0]["reason"])

    def test_dry_run_cli_prints_candidates_destinations_reasons_and_summary(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = archive_main(
                ["--dry-run", "--project-root", str(self.root)]
            )
        content = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("DRY RUN", content)
        self.assertIn("ARCHIVE exports/messages/", content)
        self.assertIn("Older duplicate", content)
        self.assertIn("Summary:", content)
        self.assertTrue(self.old.exists())

    def test_apply_moves_only_old_duplicate_and_creates_restore_manifest(self):
        result = archive_generated_materials(
            self.root, apply=True, archive_date=date(2026, 7, 6)
        )
        self.assertEqual(result["archived_count"], 1)
        self.assertFalse(self.old.exists())
        self.assertTrue(self.current.exists())
        archived_path = self.root / result["archived"][0]["archive_path"]
        self.assertTrue(archived_path.is_file())
        manifest_path = Path(result["manifest_path"])
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertIn("restore_hint", manifest)
        self.assertEqual(manifest["archived"][0]["original_path"], str(self.old.relative_to(self.root)))

        package_data = load_application_packages(self.root)
        package = next(
            item
            for item in package_data["packages"]
            if item.get("tracker_id") == "acme_director_operations"
        )
        self.assertEqual(
            package["files"]["Cover Letter"].resolve(), self.current.resolve()
        )
        self.assertNotIn(
            archived_path.resolve(),
            [path.resolve() for path in package["files"].values()],
        )
        self.assertTrue(package["archived_materials_available"])

    def test_missing_materials_do_not_crash(self):
        self.old.unlink()
        self.current.unlink()
        result = archive_generated_materials(self.root, apply=False)
        self.assertEqual(result["candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
