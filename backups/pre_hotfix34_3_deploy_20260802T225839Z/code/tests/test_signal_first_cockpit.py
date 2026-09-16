from datetime import date

from scripts.application_tracker import get_record_status, legacy_status_value, update_status
from scripts.career_signals import (
    next_action_signal,
    operational_signal_summary,
    select_todays_focus,
)
from scripts.generate_dashboard import classify_application_urls, filter_dashboard_records
from scripts.generate_dashboard import _render_html, _render_package
from app import apply_summary_navigation, clear_dashboard_filters
from ground_control.career import CareerCatalystSignalAdapter


def test_record_aware_primary_status_mapping_preserves_legacy_values():
    active_application = {
        "status": "Active",
        "submitted_date": "2026-07-01",
    }
    assert get_record_status(active_application) == "Applied"
    assert legacy_status_value(active_application) == "Active"
    assert get_record_status({"status": "Paused"}) == "Considered"
    assert get_record_status({"status": "Follow-up"}) == "Applied"


def test_status_update_adds_history_without_overwriting_other_fields(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "application_tracker.yml").write_text(
        "applications:\n"
        "- id: role\n  company: Acme\n  role: Operator\n  status: Reviewed\n"
        "  priority: High\n  show_on_dashboard: true\n  notes: Keep me\n"
    )
    saved = update_status("role", "Applied", tmp_path)
    assert saved["legacy_status"] == "Reviewed"
    assert saved["notes"] == "Keep me"
    assert saved["application_history"][-1]["to"] == "Applied"


def test_url_classification_separates_portal_and_posting():
    urls = classify_application_urls(
        {
            "official_url": "https://jobs.example.com/role",
            "notes": "Check https://company.wd5.myworkdayjobs.com/en-US/site/userHome",
        }
    )
    assert urls["posting_url"] == "https://jobs.example.com/role"
    assert urls["application_portal_url"].endswith("/userHome")
    assert urls["posting_url"] != urls["application_portal_url"]

    portal_only = classify_application_urls(
        {
            "official_url": "https://company.wd5.myworkdayjobs.com/en-US/site/userHome",
            "notes": "Use https://company.wd5.myworkdayjobs.com/en-US/site/userHome",
        }
    )
    assert portal_only["posting_url"] is None
    assert portal_only["application_portal_url"].endswith("/userHome")


def test_portal_only_role_never_gets_follow_up_action():
    role = {
        "status": "Applied",
        "submitted_date": "2026-07-01",
        "portal_only": True,
        "application_portal_url": "https://portal.example/applications",
    }
    signal = next_action_signal(role, date(2026, 7, 13))
    assert signal["kind"] == "check_application_status"
    assert signal["label"] == "Check Application Status"
    assert "employer portal" in signal["reason"]


def test_todays_focus_selects_exactly_one_highest_leverage_role():
    records = [
        {
            "id": "draft",
            "company": "Acme",
            "role": "Director",
            "status": "Drafted",
            "match_score": 99,
            "priority": "High",
            "show_on_dashboard": True,
        },
        {
            "id": "interview",
            "company": "Beta",
            "role": "VP",
            "status": "Interviewing",
            "match_score": 75,
            "priority": "Medium",
            "show_on_dashboard": True,
        },
    ]
    focus = select_todays_focus(records, date(2026, 7, 13))
    assert focus is not None
    assert focus["id"] == "interview"
    assert focus["label"] == "Interview Preparation"


def test_ground_control_summary_is_operational_and_private():
    records = [
        {
            "id": "role",
            "company": "Acme",
            "role": "Operator",
            "status": "Applied",
            "submitted_date": "2026-07-01",
            "recruiter_email": "recruiter@example.com",
            "notes": "private note",
            "resume_text": "private resume",
            "show_on_dashboard": True,
        }
    ]
    summary = operational_signal_summary(records, date(2026, 7, 13))
    assert set(summary) == {
        "applications_in_flight",
        "under_consideration",
        "interviews_scheduled",
        "genuine_follow_ups_due",
        "todays_highest_leverage_action",
        "career_state",
    }
    assert "private" not in str(summary)
    assert summary["genuine_follow_ups_due"] == 1
    assert summary["career_state"] == "Action Needed"


def test_summary_navigation_and_reset_share_status_state():
    state = {"dashboard_status": "All", "dashboard_search": "netflix"}
    apply_summary_navigation(state, "Interviewing")
    assert state["dashboard_status"] == "Interviewing"
    filtered = filter_dashboard_records(
        [
            {"id": "applied", "status": "Applied"},
            {"id": "interview", "status": "Interviewing"},
        ],
        application_status=state["dashboard_status"],
    )
    assert [record["id"] for record in filtered] == ["interview"]
    clear_dashboard_filters(state)
    assert state["dashboard_status"] == "All"
    assert state["dashboard_search"] == ""


def test_static_summary_controls_filter_cards_and_hide_obsolete_sections(tmp_path):
    package = {
        "company": "Acme",
        "role": "Operator",
        "tracker": {
            "id": "role",
            "status": "Applied",
            "priority": "High",
            "show_on_dashboard": True,
            "match_tier": "Strong Match",
        },
        "files": {},
    }
    groups = {
        "active": [],
        "applied": [package],
        "reviewed": [],
        "paused": [],
        "pass": [],
        "hidden": [],
    }
    rendered = _render_html(groups, {"Total": 1}, [], tmp_path)
    assert 'data-status-filter="Applied"' in rendered
    assert "statusFilter.value = card.dataset.statusFilter" in rendered
    assert "aria-pressed" in rendered
    assert "Applications in Flight" in rendered
    assert "Recommended Next Steps" not in rendered
    assert "Priority Queues" not in rendered
    for obsolete_group in (
        'id="active-applied"',
        'id="applied-follow-up"',
        'id="reviewed"',
        'id="draft-paused"',
        'id="passed"',
        'id="hidden-invalid-roles"',
    ):
        assert obsolete_group not in rendered
    assert rendered.count("Today’s Focus") == 1
    assert rendered.count('class="today-focus"') == 1
    assert rendered.count('class="focus-role"') == 1


def test_role_card_only_renders_usable_actions(tmp_path):
    without_links = {
        "company": "Acme",
        "role": "Operator",
        "tracker": {"id": "role", "status": "Drafted"},
        "files": {},
    }
    rendered = _render_package(without_links, tmp_path)
    assert "View Role" in rendered
    assert "Open Posting" not in rendered
    assert "Check Application Status" not in rendered
    assert "Open Materials" not in rendered

    material = tmp_path / "resume.txt"
    material.write_text("resume")
    with_links = {
        **without_links,
        "tracker": {
            "id": "role",
            "status": "Applied",
            "posting_url": "https://jobs.example/role",
            "application_portal_url": "https://portal.example/applications",
        },
        "files": {"Resume Text": material},
    }
    rendered = _render_package(with_links, tmp_path)
    assert "Open Posting" in rendered
    assert "Check Application Status" in rendered
    assert "Open Materials" in rendered


def test_ground_control_adapter_reads_only_signal_payload(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "application_tracker.yml").write_text(
        "applications:\n"
        "- id: role\n"
        "  company: Acme\n"
        "  role: Operator\n"
        "  status: Interviewing\n"
        "  priority: High\n"
        "  show_on_dashboard: true\n"
        "  notes: private note\n"
    )
    tracker_path = tmp_path / "data" / "application_tracker.yml"
    before = tracker_path.read_bytes()
    signals = CareerCatalystSignalAdapter(tmp_path).load_signals(date(2026, 7, 13))
    assert tracker_path.read_bytes() == before
    assert signals["career_state"] == "Interviewing"
    assert signals["interviews_scheduled"] == 1
    assert "private" not in str(signals)
