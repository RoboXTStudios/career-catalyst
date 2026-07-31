from __future__ import annotations

from copy import deepcopy

import app
from scripts.application_tracker import (
    VALID_STATUSES,
    get_record_status,
    load_application_tracker,
    save_application_tracker,
    update_status,
)
from scripts.generate_dashboard import filter_dashboard_records, prepare_dashboard_records
from scripts.role_lifecycle import filter_live_records, lifecycle_counts


def _record(tracker_id: str, status: str, **updates):
    record = {
        "id": tracker_id,
        "company": tracker_id.title(),
        "role": "Director, Operations",
        "status": status,
        "priority": "Medium",
        "notes": "",
        "show_on_dashboard": True,
        "match_tier": "Good Match",
    }
    record.update(updates)
    return record


def _authoritative_summary(records):
    return lifecycle_counts(records, status_resolver=get_record_status)


def test_summary_and_every_filter_share_authoritative_status_identity():
    records = [_record(f"role_{index}", status) for index, status in enumerate(VALID_STATUSES)]
    records.append(
        _record(
            "legacy_submitted",
            "Active",
            submitted_date="2026-07-01",
            notes="Employer status: Under Consideration",
        )
    )

    summary = _authoritative_summary(records)
    assert summary["All"] == len(records)
    assert sum(summary[status] for status in VALID_STATUSES) == summary["All"]
    for status in VALID_STATUSES:
        expected_ids = {
            record["id"]
            for record in filter_live_records(
                records,
                status,
                status_resolver=get_record_status,
            )
        }
        dropdown_ids = {
            record["id"]
            for record in filter_dashboard_records(records, application_status=status)
        }
        assert summary[status] == len(expected_ids) == len(dropdown_ids)
        assert expected_ids == dropdown_ids


def test_reproduction_fixture_keeps_three_under_consideration_roles_together():
    records = [
        _record("disney", "Under Consideration", submitted_date="2026-07-09"),
        _record(
            "live_nation",
            "Active",
            submitted_date="2026-07-01",
            notes="Workday Status: Under Consideration",
        ),
        _record("umg", "Under Consideration", submitted_date="2026-07-07"),
        _record("prospect", "Prospect"),
        _record("considered", "Considered"),
        _record("applied", "Applied", submitted_date="2026-07-02"),
        _record("rejected", "Rejected"),
    ]
    package_map = {
        "disney": {"status": "Applied", "material_status": "Applied", "files": {}},
        "live_nation": {"status": "Applied", "material_status": "Applied", "files": {}},
        "umg": {"status": "Applied", "material_status": "Applied", "files": {}},
    }
    enriched = prepare_dashboard_records(records, package_map)
    expected_ids = {"disney", "live_nation", "umg"}

    summary = app.summarize_applications(enriched)
    chip_ids = {
        record["id"]
        for record in filter_live_records(
            enriched,
            "Under Consideration",
            status_resolver=get_record_status,
        )
    }
    dropdown_ids = {
        record["id"]
        for record in filter_dashboard_records(
            enriched,
            application_status="Under Consideration",
        )
    }
    assert summary["Under Consideration"] == 3
    assert chip_ids == dropdown_ids == expected_ids
    assert not expected_ids.intersection(
        {
            record["id"]
            for record in filter_dashboard_records(enriched, application_status="Applied")
        }
    )
    assert all(get_record_status(record) == "Under Consideration" for record in enriched if record["id"] in expected_ids)


def test_tracker_status_remains_authoritative_over_derived_metadata():
    source = _record(
        "authoritative",
        "Under Consideration",
        submitted_date="2026-07-01",
        follow_up_status="Applied",
        material_status="Applied",
    )
    original = deepcopy(source)
    enriched = prepare_dashboard_records(
        [source],
        {
            "authoritative": {
                "status": "Applied",
                "material_status": "Applied",
                "follow_up_status": "Applied",
                "files": {"Recruiter Message": "outside/runtime/recruiter.txt"},
            }
        },
    )[0]
    assert enriched["status"] == original["status"] == "Under Consideration"
    assert get_record_status(enriched) == "Under Consideration"
    assert _authoritative_summary([enriched])["Under Consideration"] == 1


def test_considered_to_rejected_update_changes_only_the_target_summary_bucket(tmp_path):
    (tmp_path / "data").mkdir()
    records = [
        _record("wmg", "Considered"),
        _record("other_considered", "Considered"),
        _record("applied", "Applied", submitted_date="2026-07-02"),
    ]
    save_application_tracker(records, tmp_path)

    update_status("wmg", "Rejected", tmp_path)
    current = load_application_tracker(tmp_path)
    summary = _authoritative_summary(current)
    assert summary["Considered"] == 1
    assert summary["Rejected"] == 1
    assert {record["id"] for record in filter_live_records(current, "Considered", status_resolver=get_record_status)} == {"other_considered"}
    assert {record["id"] for record in filter_live_records(current, "Rejected", status_resolver=get_record_status)} == {"wmg"}
    assert summary["Applied"] == 1
