import importlib
import unittest
from datetime import date
from pathlib import Path

from scripts.generate_dashboard import (
    _render_metadata,
    _render_priority_sections,
    calculate_follow_up_timing,
    enrich_dashboard_record,
    filter_dashboard_records,
    recommended_next_steps,
    select_dashboard_mode,
    sort_dashboard_records,
)


TODAY = date(2026, 6, 30)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _record(identifier, **updates):
    base = {
        "id": identifier,
        "company": identifier.title(),
        "role": "Director, Operations",
        "status": "Drafted",
        "show_on_dashboard": True,
        "match_score": 75,
        "match_tier": "Good Match",
        "recommended_action": "Generate Package",
        "opportunity_score": 70,
        "source": "Official Careers",
        "salary_range": "$150,000-$180,000",
        "freshness": "Fresh",
        "posting_status": "Open",
        "company_category": "entertainment_streaming",
        "role_family": "business_operations",
        "location": "Remote",
        "match_gaps": ["Confirm scope."],
    }
    base.update(updates)
    return base


class DashboardSortingTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            enrich_dashboard_record(_record("beta", match_score=90, submitted_date="2026-06-20"), TODAY),
            enrich_dashboard_record(_record("alpha", match_score=60, submitted_date="2026-06-29"), TODAY),
            enrich_dashboard_record(_record("charlie", match_score=75, submitted_date="2026-06-25"), TODAY),
        ]

    def test_sort_match_score_high_to_low(self):
        result = sort_dashboard_records(self.records, "Match Score: High to Low")
        self.assertEqual([item["match_score"] for item in result], [90, 75, 60])

    def test_sort_match_score_low_to_high(self):
        result = sort_dashboard_records(self.records, "Match Score: Low to High")
        self.assertEqual([item["match_score"] for item in result], [60, 75, 90])

    def test_sort_applied_date_newest_first(self):
        result = sort_dashboard_records(self.records, "Applied/Submitted Date: Newest First")
        self.assertEqual([item["id"] for item in result], ["alpha", "charlie", "beta"])

    def test_sort_applied_date_oldest_first(self):
        result = sort_dashboard_records(self.records, "Applied/Submitted Date: Oldest First")
        self.assertEqual([item["id"] for item in result], ["beta", "charlie", "alpha"])

    def test_company_is_stable_fallback_for_equal_scores(self):
        records = [_record("zulu", match_score=80), _record("alpha", match_score=80)]
        result = sort_dashboard_records(records)
        self.assertEqual([item["id"] for item in result], ["alpha", "zulu"])


class DashboardFilteringTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            _record("strong", match_tier="Strong Match", status="Applied", company="Paramount"),
            _record("stretch", match_tier="Stretch Match", recommended_action="Review First", role="Strategy Lead"),
            _record("good", match_tier="Good Match", recommended_action="Generate Package", company_category="music_entertainment", role_family="strategic_operations"),
        ]

    def test_filter_strong_match(self):
        self.assertEqual(
            [item["id"] for item in filter_dashboard_records(self.records, match_tier="Strong Match")],
            ["strong"],
        )

    def test_filter_stretch_match(self):
        self.assertEqual(
            [item["id"] for item in filter_dashboard_records(self.records, match_tier="Stretch Match")],
            ["stretch"],
        )

    def test_filter_generate_package(self):
        result = filter_dashboard_records(self.records, recommended_action="Generate Package")
        self.assertEqual({item["id"] for item in result}, {"strong", "good"})

    def test_filter_review_first(self):
        result = filter_dashboard_records(self.records, recommended_action="Review First")
        self.assertEqual([item["id"] for item in result], ["stretch"])

    def test_filter_applied_status(self):
        result = filter_dashboard_records(self.records, application_status="Applied")
        self.assertEqual([item["id"] for item in result], ["strong"])

    def test_text_search_covers_company_title_category_and_role_family(self):
        self.assertEqual(len(filter_dashboard_records(self.records, search="Paramount")), 1)
        self.assertEqual(len(filter_dashboard_records(self.records, search="Strategy Lead")), 1)
        self.assertEqual(len(filter_dashboard_records(self.records, search="music entertainment")), 1)
        self.assertEqual(len(filter_dashboard_records(self.records, search="strategic operations")), 1)


class FollowUpTimingTests(unittest.TestCase):
    def test_recent_application_is_not_due_yet(self):
        result = calculate_follow_up_timing(_record("recent", submitted_date="2026-06-29"), TODAY)
        self.assertEqual(result["follow_up_status"], "Not due yet")
        self.assertEqual(result["suggested_follow_up_date"], "2026-07-04")

    def test_three_to_five_days_is_due_soon(self):
        result = calculate_follow_up_timing(_record("soon", submitted_date="2026-06-26"), TODAY)
        self.assertEqual(result["follow_up_status"], "Due soon")

    def test_six_to_ten_days_is_due_now(self):
        result = calculate_follow_up_timing(_record("now", submitted_date="2026-06-22"), TODAY)
        self.assertEqual(result["follow_up_status"], "Due now")

    def test_more_than_ten_days_is_overdue(self):
        result = calculate_follow_up_timing(_record("late", submitted_date="2026-06-10"), TODAY)
        self.assertEqual(result["follow_up_status"], "Overdue")

    def test_missing_applied_date_is_safe(self):
        result = calculate_follow_up_timing(_record("missing"), TODAY)
        self.assertEqual(result["follow_up_status"], "No applied date")
        self.assertIsNone(result["days_since_applied"])

    def test_existing_follow_up_sent_status_is_respected(self):
        result = calculate_follow_up_timing(
            _record("sent", submitted_date="2026-06-10", follow_up_sent=True), TODAY
        )
        self.assertEqual(result["follow_up_status"], "Follow-up sent")


class DashboardModeTests(unittest.TestCase):
    def setUp(self):
        self.apply = enrich_dashboard_record(_record("apply", match_tier="Strong Match"), TODAY)
        self.follow = enrich_dashboard_record(
            _record("follow", status="Applied", submitted_date="2026-06-22"), TODAY
        )
        self.review = enrich_dashboard_record(
            _record("review", match_tier="Stretch Match", recommended_action="Review First"), TODAY
        )
        self.cleanup = enrich_dashboard_record(
            _record("cleanup", match_tier="Weak Match", recommended_action="Pass"), TODAY
        )
        self.records = [self.apply, self.follow, self.review, self.cleanup]

    def test_apply_mode_returns_strong_or_good_unapplied_roles(self):
        self.assertEqual([item["id"] for item in select_dashboard_mode(self.records, "Apply Mode")], ["apply"])

    def test_follow_up_mode_returns_due_roles(self):
        self.assertEqual([item["id"] for item in select_dashboard_mode(self.records, "Follow-Up Mode")], ["follow"])

    def test_review_mode_returns_stretch_or_review_first_roles(self):
        self.assertEqual([item["id"] for item in select_dashboard_mode(self.records, "Review Mode")], ["review"])

    def test_cleanup_mode_returns_weak_or_pass_roles(self):
        cleanup_ids = {item["id"] for item in select_dashboard_mode(self.records, "Cleanup Mode")}
        self.assertIn("cleanup", cleanup_ids)

    def test_each_mode_returns_actionable_next_steps(self):
        for mode in ("Apply Mode", "Follow-Up Mode", "Review Mode", "Cleanup Mode"):
            visible = select_dashboard_mode(self.records, mode)
            steps = recommended_next_steps(visible, mode)
            self.assertTrue(steps, mode)
            self.assertTrue(all(step.strip() for step in steps), mode)

    def test_each_mode_has_friendly_empty_state(self):
        expected = {
            "Apply Mode": "No strong unapplied matches found.",
            "Follow-Up Mode": "No roles need follow-up right now.",
            "Review Mode": "No stretch or review-first roles found.",
            "Cleanup Mode": "No cleanup items found.",
        }
        for mode, message in expected.items():
            self.assertEqual(recommended_next_steps([], mode), [message])

    def test_follow_up_steps_respect_submitted_application_state(self):
        record = dict(self.follow, _follow_up_materials_status="Available")
        self.assertIn("application is already submitted", recommended_next_steps([record], "Follow-Up Mode")[0])


class DashboardDisplayParityTests(unittest.TestCase):
    def test_streamlit_card_helpers_include_match_and_follow_up_fields(self):
        app = importlib.import_module("app")
        record = enrich_dashboard_record(
            _record("display", status="Applied", submitted_date="2026-06-26"), TODAY
        )
        metadata = app._metadata_html(record, {})
        match = app._match_score_html(record)
        for label in ("Applied", "Days since applied", "Follow-up", "Suggested follow-up"):
            self.assertIn(label, metadata)
        self.assertIn("Match Score", match)
        self.assertIn("Good Match", match)

    def test_html_card_metadata_includes_follow_up_fields(self):
        record = enrich_dashboard_record(
            _record("html", status="Applied", submitted_date="2026-06-22"), TODAY
        )
        content = _render_metadata({"tracker": record})
        for label in ("Applied", "Days since applied", "Follow-up", "Suggested follow-up"):
            self.assertIn(label, content)
        self.assertIn("Due now", content)

    def test_html_dashboard_priority_sections_are_present(self):
        record = enrich_dashboard_record(_record("priority", match_tier="Strong Match"), TODAY)
        package = {"company": record["company"], "role": record["role"], "tracker": record, "files": {}}
        content = _render_priority_sections(
            {"active": [], "draft": [package], "hidden": []},
            PROJECT_ROOT / "exports" / "dashboard",
        )
        for heading in (
            "Recommended Next Steps",
            "Strong Matches",
            "Good Matches",
            "Stretch Matches",
            "Follow-Up Due",
            "Review First",
            "Pass / Hidden / Invalid",
            "Cleanup Needed",
        ):
            self.assertIn(heading, content)


if __name__ == "__main__":
    unittest.main()
