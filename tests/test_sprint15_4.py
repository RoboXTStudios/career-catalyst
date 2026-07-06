import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from scripts.application_tracker import load_application_tracker, save_application_tracker
from scripts.generate_dashboard import structured_recommended_next_steps


def _record(identifier="stable-role", **updates):
    record = {
        "id": identifier,
        "company": "Netflix",
        "role": "Director, Operations",
        "status": "Active",
        "priority": "High",
        "show_on_dashboard": True,
        "match_score": 90,
        "match_tier": "Strong Match",
        "recommended_action": "Generate Package",
    }
    record.update(updates)
    return record


class _Element:
    def __init__(self, root):
        self.root = root

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def button(self, label, key=None, **_kwargs):
        self.root.buttons.append((label, key))
        return key in self.root.clicks

    def link_button(self, label, url, **_kwargs):
        self.root.links.append((label, url))

    def markdown(self, value, **_kwargs):
        self.root.messages.append(("markdown", value))

    def caption(self, value, **_kwargs):
        self.root.messages.append(("caption", value))

    def warning(self, value, **_kwargs):
        self.root.messages.append(("warning", value))

    def success(self, value, **_kwargs):
        self.root.messages.append(("success", value))


class _FakeStreamlit(_Element):
    def __init__(self, state=None, clicks=()):
        self.session_state = state if state is not None else {}
        self.clicks = set(clicks)
        self.buttons = []
        self.links = []
        self.messages = []
        self.reruns = 0
        super().__init__(self)

    def container(self, **_kwargs):
        return _Element(self)

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [_Element(self) for _ in range(count)]

    def rerun(self):
        self.reruns += 1


class FocusedRoleTests(unittest.TestCase):
    def test_role_reference_and_lookup_use_stable_fallback_order(self):
        record = _record(
            "tracker-id",
            prospect_id="prospect-id",
            record_id="record-id",
            stable_slug="netflix-director",
        )
        self.assertEqual(app.dashboard_role_reference(record), "prospect-id")
        self.assertIs(app.find_dashboard_role([record], "record-id"), record)
        self.assertIs(app.find_dashboard_role([record], "tracker-id"), record)
        self.assertIs(app.find_dashboard_role([record], "netflix-director"), record)

        fallback = _record("", company="Acme & Co.", role="VP / Operations")
        self.assertEqual(
            app.dashboard_role_reference(fallback), "role:acme-co:vp-operations"
        )
        self.assertIs(
            app.find_dashboard_role([fallback], "role:acme-co:vp-operations"),
            fallback,
        )
        self.assertEqual(
            structured_recommended_next_steps([fallback])[0]["tracker_id"],
            "role:acme-co:vp-operations",
        )

    def test_view_role_sets_focus_and_renders_focused_card(self):
        record = _record()
        st = _FakeStreamlit(clicks={"next_view_stable-role"})
        rendered = []
        with patch.object(app, "_render_role_card", side_effect=lambda *_args: rendered.append(record)):
            focused = app._render_recommended_next_steps(
                st, [record], "All Mode", {}, focus_records=[record]
            )
        self.assertEqual(st.session_state["dashboard_focused_role_id"], "stable-role")
        self.assertEqual(focused, "stable-role")
        self.assertEqual(rendered, [record])
        self.assertTrue(any("Focused role" in value for _, value in st.messages))

    def test_clear_focus_removes_focused_role(self):
        record = _record()
        state = {"dashboard_focused_role_id": "stable-role"}
        st = _FakeStreamlit(state, clicks={"dashboard_clear_focus"})
        with patch.object(app, "_render_role_card"):
            app._render_recommended_next_steps(st, [record], "All Mode", {})
        self.assertNotIn("dashboard_focused_role_id", state)
        self.assertEqual(st.reruns, 1)

    def test_focused_role_outside_filters_still_renders(self):
        visible = _record("visible", company="Acme")
        focused = _record("focused")
        state = {"dashboard_focused_role_id": "focused"}
        st = _FakeStreamlit(state)
        rendered = []
        with patch.object(app, "_render_role_card", side_effect=lambda _st, role, *_args: rendered.append(role)):
            app._render_recommended_next_steps(
                st, [visible], "All Mode", {}, focus_records=[visible, focused]
            )
        self.assertEqual(rendered, [focused])
        self.assertTrue(
            any("outside current filters" in value for kind, value in st.messages if kind == "caption")
        )

    def test_missing_focused_role_warns_without_clearing_state(self):
        state = {"dashboard_focused_role_id": "missing"}
        st = _FakeStreamlit(state)
        app._render_recommended_next_steps(st, [], "All Mode", {}, focus_records=[])
        self.assertEqual(state["dashboard_focused_role_id"], "missing")
        self.assertTrue(any(kind == "warning" for kind, _ in st.messages))


class NavigationActionTests(unittest.TestCase):
    def test_posting_and_material_buttons_only_render_when_available(self):
        with tempfile.TemporaryDirectory() as temporary:
            material = Path(temporary) / "resume.md"
            material.write_text("resume", encoding="utf-8")
            record = _record(
                canonical_apply_url="https://jobs.netflix.com/example",
                _material_paths={"resume": str(material)},
            )
            st = _FakeStreamlit()
            app._render_recommended_next_steps(st, [record], "All Mode", {})
            self.assertIn(("Open posting", record["canonical_apply_url"]), st.links)
            self.assertIn("Open materials", {label for label, _ in st.buttons})

        no_links = _FakeStreamlit()
        app._render_recommended_next_steps(no_links, [_record()], "All Mode", {})
        self.assertFalse(no_links.links)
        self.assertNotIn("Open materials", {label for label, _ in no_links.buttons})

    def test_source_url_is_a_valid_posting_fallback(self):
        record = _record(source_url="https://example.com/jobs/123")
        st = _FakeStreamlit()
        app._render_recommended_next_steps(st, [record], "All Mode", {})
        self.assertIn(("Open posting", record["source_url"]), st.links)

    def test_all_mode_next_steps_remain_navigation_only(self):
        source = inspect.getsource(app._render_recommended_next_steps)
        self.assertIn("View role", source)
        self.assertNotIn("Generate package", source)
        self.assertNotIn("Pause", source)


class AdvancedStatusStabilityTests(unittest.TestCase):
    def test_safe_source_fallbacks_handle_missing_and_malformed_values(self):
        self.assertEqual(
            app.safe_source_metadata(
                {
                    "source_name": [],
                    "source_type": {},
                    "verification_status": None,
                    "source_trust_label": [],
                    "freshness_risk": {},
                }
            ),
            {
                "source": "Unknown",
                "source_type": "Unknown Source",
                "verification_status": "Not Verified",
                "source_trust_label": "Unknown Source",
                "freshness_risk": "Unknown",
            },
        )

    def test_persisted_widget_sync_updates_stale_status_without_resetting_edits(self):
        state = {}
        app._sync_persisted_widget_value(state, "status_role_value", "Active")
        state["status_role_value"] = "Applied"
        app._sync_persisted_widget_value(state, "status_role_value", "Active")
        self.assertEqual(state["status_role_value"], "Applied")
        app._sync_persisted_widget_value(state, "status_role_value", "Reviewed")
        self.assertEqual(state["status_role_value"], "Reviewed")

    def test_update_targets_selected_role_and_keeps_canonical_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save_application_tracker(
                [_record("first"), _record("second", company="Acme")], root
            )
            updated = app.update_dashboard_role(
                "second", {"status": "Follow-Up", "notes": "Sent"}, root
            )
            records = {record["id"]: record for record in load_application_tracker(root)}
            self.assertEqual(updated["status"], "Follow-up")
            self.assertEqual(records["second"]["status"], "Follow-up")
            self.assertEqual(records["first"]["status"], "Active")
            self.assertEqual(
                app.resolve_selected_tracker_id(list(records), "second"), "second"
            )

    def test_advanced_tab_uses_safe_source_and_canonical_update_helpers(self):
        source = inspect.getsource(app._render_update_status)
        self.assertIn("safe_source_metadata", source)
        self.assertIn("get_record_status", source)
        self.assertIn("update_dashboard_role", source)
        self.assertIn("status_update_notice", source)


if __name__ == "__main__":
    unittest.main()
