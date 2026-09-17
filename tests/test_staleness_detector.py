from datetime import date

import pytest

from scripts.application_tracker import days_since_status_update, stale_waiting_records

TODAY = date(2026, 9, 17)


@pytest.mark.parametrize('timestamp', ['2026-08-27', '2026-08-27T10:30:00', '2026-08-27T10:30:00.123456', '2026-08-27T10:30:00+00:00', '2026-08-27T10:30:00Z'])
def test_date_and_iso_timestamps(timestamp):
    assert days_since_status_update({'status_updated_at': timestamp}, today=TODAY) == 21


def test_submission_fallback_and_invalid_dates():
    assert days_since_status_update({'submitted_date': '2026-08-27'}, today=TODAY) == 21
    assert days_since_status_update({'status_updated_at': 'invalid', 'submitted_date': '2026-08-27'}, today=TODAY) == 21
    assert days_since_status_update({}, today=TODAY) is None
    assert days_since_status_update({'status_updated_at': '2026-99-99'}, today=TODAY) is None


@pytest.mark.parametrize('status', ['Applied', 'Under Consideration', 'Follow-up'])
def test_waiting_statuses_at_threshold(status):
    record = {'status': status, 'status_updated_at': '2026-08-27T12:00:00'}
    assert stale_waiting_records([record], today=TODAY) == [record]


@pytest.mark.parametrize('timestamp', ['2026-08-28', '2026-09-18'])
def test_recent_and_future_statuses_are_not_stale(timestamp):
    assert stale_waiting_records([{'status': 'Applied', 'status_updated_at': timestamp}], today=TODAY) == []


@pytest.mark.parametrize('status', ['Rejected', 'Withdrawn / Closed', 'Interviewing', 'Offer', 'Drafted'])
def test_other_statuses_are_excluded(status):
    assert stale_waiting_records([{'status': status, 'submitted_date': '2026-06-01'}], today=TODAY) == []


@pytest.mark.parametrize('signal', [{'response_required': True}, {'follow_up_required': True}, {'response_action': 'Send availability'}])
def test_actionable_employer_requests_are_excluded(signal):
    record = {'status': 'Under Consideration', 'submitted_date': '2026-06-01', **signal}
    assert stale_waiting_records([record], today=TODAY) == []
