import unittest
from unittest.mock import patch

import app
from tests.test_sprint15_4 import _FakeStreamlit, _record


class _VerificationStreamlit(_FakeStreamlit):
    def __init__(self):
        super().__init__()
        self.selects = {}
        self.inputs = {}

    def text_input(self, label, value="", **_kwargs):
        self.inputs[label] = value
        return value

    def selectbox(self, label, options, index=0, **_kwargs):
        values = tuple(options)
        self.selects[label] = (values, index)
        return values[index]

    def checkbox(self, label, value=False, **_kwargs):
        self.inputs[label] = value
        return value

    def text_area(self, label, value="", **_kwargs):
        self.inputs[label] = value
        return value


class VerificationPanelHotfixTests(unittest.TestCase):
    def test_source_verification_renders_missing_fields_with_safe_defaults(self):
        st = _VerificationStreamlit()
        app._render_source_verification_panel(st, _record(), "stable-role")

        verification_options, verification_index = st.selects["Verified status"]
        freshness_options, freshness_index = st.selects["Freshness"]
        self.assertEqual(verification_options[verification_index], "Not Verified")
        self.assertEqual(freshness_options[freshness_index], "Unknown freshness")
        self.assertEqual(st.inputs["Posting date"], "")
        self.assertFalse(st.inputs["Source verified"])

    def test_missing_canonical_statuses_use_local_fallback(self):
        with patch.dict(app.__dict__, {"CANONICAL_VERIFICATION_STATUSES": ()}):
            self.assertEqual(
                app.verification_status_options(),
                app.FALLBACK_VERIFICATION_STATUSES,
            )

    def test_existing_tracker_verification_value_remains_selectable(self):
        options = app.verification_status_options("Legacy Verified")
        self.assertEqual(options[0], "Legacy Verified")

    def test_verify_manually_focuses_role_and_opens_source_panel(self):
        state = {"dashboard_compact_mode": True}
        app.focus_source_verification(state, "stable-role")
        self.assertEqual(state["dashboard_focused_role_id"], "stable-role")
        self.assertEqual(
            state["dashboard_source_verification_role_id"], "stable-role"
        )
        self.assertFalse(state["dashboard_compact_mode"])


class DashboardCollapseHotfixTests(unittest.TestCase):
    def test_collapse_all_sets_compact_mode_without_clearing_focus_or_filters(self):
        state = {
            "dashboard_focused_role_id": "stable-role",
            "dashboard_mode": "Follow-Up Mode",
            "dashboard_status": "Applied / Follow-up",
            "dashboard_materials_role_id": "stable-role",
        }
        app.collapse_dashboard_working_view(state)
        self.assertTrue(state["dashboard_compact_mode"])
        self.assertEqual(state["dashboard_focused_role_id"], "stable-role")
        self.assertEqual(state["dashboard_mode"], "Follow-Up Mode")
        self.assertNotIn("dashboard_materials_role_id", state)

    def test_recommended_next_steps_collapse_to_header_only(self):
        record = _record(
            canonical_apply_url="https://jobs.example.com/role",
            posting_date="",
            freshness="Unknown freshness",
            _material_paths={"resume": __file__},
        )
        st = _FakeStreamlit(
            state={
                "dashboard_compact_mode": True,
                "dashboard_next_steps_collapsed": True,
            }
        )
        app._render_recommended_next_steps(st, [record], "All Mode", {})

        self.assertEqual({label for label, _ in st.buttons}, {"Expand"})
        self.assertEqual(st.links, [])
        rendered = "\n".join(value for kind, value in st.messages if kind == "markdown")
        self.assertIn("Recommended Next Steps (1)", rendered)
        self.assertNotIn("Director, Operations", rendered)

    def test_application_tracker_renders_nonfocused_roles_compact(self):
        st = _FakeStreamlit(state={"dashboard_compact_mode": True})
        st.expander = lambda *_args, **_kwargs: st
        record = _record()
        with patch.object(app, "_render_role_card") as render_role:
            app._render_application_tracker(st, [record], {}, "All Mode")
        self.assertTrue(render_role.call_args.kwargs["compact"])

    def test_compact_role_card_omits_full_primary_facts(self):
        st = _FakeStreamlit()
        with patch.object(app, "_primary_facts_html") as primary_facts:
            app._render_role_card(st, _record(), {}, compact=True)
        primary_facts.assert_not_called()

    def test_expand_focused_expands_only_focused_role(self):
        state = {
            "dashboard_compact_mode": True,
            "dashboard_focused_role_id": "focused-role",
        }
        self.assertTrue(app.expand_focused_dashboard_role(state))
        self.assertFalse(state["dashboard_compact_mode"])

        no_focus = {"dashboard_compact_mode": True}
        self.assertFalse(app.expand_focused_dashboard_role(no_focus))
        self.assertTrue(no_focus["dashboard_compact_mode"])

    def test_compact_mode_hides_focused_workspace_until_expanded(self):
        record = _record()
        st = _FakeStreamlit(
            state={
                "dashboard_compact_mode": True,
                "dashboard_focused_role_id": "stable-role",
            }
        )
        with patch.object(app, "_render_role_card") as render_role:
            app._render_recommended_next_steps(
                st, [record], "All Mode", {}, focus_records=[record]
            )
        render_role.assert_not_called()

    def test_clear_focus_preserves_compact_mode_and_filters(self):
        state = {
            "dashboard_compact_mode": True,
            "dashboard_focused_role_id": "stable-role",
            "dashboard_mode": "Cleanup Mode",
        }
        app.clear_focused_dashboard_role(state)
        self.assertNotIn("dashboard_focused_role_id", state)
        self.assertTrue(state["dashboard_compact_mode"])
        self.assertEqual(state["dashboard_mode"], "Cleanup Mode")


if __name__ == "__main__":
    unittest.main()
