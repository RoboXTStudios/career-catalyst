from datetime import date

import pytest

from scripts.application_tracker import follow_up_action_state, follow_up_eligibility
from scripts import generate_followups as followup_generator


TODAY = date(2026, 7, 13)


def role(**updates):
    values = {
        "id": "acme_operator",
        "company": "Acme",
        "role": "Operator",
        "status": "Applied",
        "submitted_date": "2026-07-01",
        "show_on_dashboard": True,
        "recruiter_email": "recruiter@example.com",
    }
    values.update(updates)
    return values


def assert_action(values, key, label, eligible=False):
    action = follow_up_action_state(values, TODAY)
    assert action["key"] == key
    assert action["label"] == label
    assert action["eligible"] is eligible
    assert action["reason"]
    assert follow_up_eligibility(values, TODAY)[0] is eligible
    return action


def test_drafted_role_never_shows_follow_up_generation():
    assert_action(
        role(status="Drafted"),
        "no_action_today",
        "No action today",
    )


def test_applied_role_before_waiting_period_is_not_yet_eligible():
    action = assert_action(
        role(submitted_date="2026-07-11"),
        "not_yet_eligible",
        "Not yet eligible",
    )
    assert "3 days remaining" in action["reason"]


def test_applied_role_after_configured_wait_with_contact_can_generate():
    assert_action(
        role(submitted_date="2026-07-09", follow_up_wait_days=4),
        "generate_follow_up",
        "Generate Follow-Up",
        eligible=True,
    )


def test_applied_portal_only_role_uses_application_status_fallback():
    action = assert_action(
        role(
            portal_only=True,
            recruiter_email="",
            application_portal_url="https://portal.example/applications",
        ),
        "check_application_status",
        "Check Application Status",
    )
    assert action["portal_url"] == "https://portal.example/applications"


def test_under_consideration_requires_contact_or_specific_response():
    assert_action(
        role(status="Under Consideration", recruiter_email=""),
        "no_direct_follow_up_path",
        "No direct follow-up path",
    )
    assert_action(
        role(status="Under Consideration"),
        "generate_follow_up",
        "Generate Follow-Up",
        eligible=True,
    )
    assert_action(
        role(
            status="Under Consideration",
            recruiter_email="",
            response_required=True,
        ),
        "generate_follow_up",
        "Generate Follow-Up",
        eligible=True,
    )


def test_interviewing_only_allows_stage_specific_follow_up():
    assert_action(
        role(status="Interviewing", next_action="Prepare interview examples"),
        "no_action_today",
        "No action today",
    )
    assert_action(
        role(status="Interviewing", interview_follow_up_type="Send thank-you"),
        "generate_follow_up",
        "Generate Follow-Up",
        eligible=True,
    )


def test_follow_up_already_sent_without_new_trigger_is_contextual():
    assert_action(
        role(follow_up_status="Follow-up sent"),
        "follow_up_already_sent",
        "Follow-up already sent",
    )


def test_new_interview_trigger_after_sent_follow_up_can_generate_again():
    assert_action(
        role(
            status="Interviewing",
            follow_up_status="Follow-up sent",
            application_history=[
                {"event": "follow up sent"},
                {"event": "interview scheduled"},
            ],
        ),
        "generate_follow_up",
        "Generate Follow-Up",
        eligible=True,
    )


@pytest.mark.parametrize("status", ["Rejected", "Withdrawn / Closed", "Offer"])
def test_terminal_statuses_have_no_generic_follow_up(status):
    assert_action(role(status=status), "no_action_today", "No action today")


def test_bulk_generation_prefilters_and_reports_every_skip(monkeypatch, tmp_path):
    records = [
        role(id="eligible"),
        role(id="draft", status="Drafted"),
        role(
            id="portal",
            portal_only=True,
            recruiter_email="",
            application_portal_url="https://portal.example/applications",
        ),
        role(id="sent", follow_up_status="Follow-up sent"),
    ]
    attempted = []
    monkeypatch.setattr(followup_generator, "load_application_tracker", lambda root: records)
    monkeypatch.setattr(
        followup_generator,
        "_expected_followup_paths",
        lambda application, root: {"strategy": root / f"{application['id']}.missing"},
    )
    monkeypatch.setattr(
        followup_generator,
        "generate_followups",
        lambda tracker_id, root: attempted.append(tracker_id),
    )

    summary = followup_generator.generate_missing_followups(tmp_path)

    assert attempted == ["eligible"]
    assert summary["generated"] == ["eligible"]
    assert summary["skipped_count"] == 3
    assert set(summary["skipped"]) == {"draft", "portal", "sent"}
    assert all(summary["skipped"].values())
    assert summary["failed_count"] == 0
