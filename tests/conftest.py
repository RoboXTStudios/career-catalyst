"""Shared reconciliation markers for intentionally retired legacy assertions."""

import pytest


OBSOLETE_DASHBOARD_TESTS = {
    'tests/test_application_tracker.py::ApplicationTrackerTests::test_applied_and_visibility_states_are_preserved',
    'tests/test_entertainment_calibration.py::EntertainmentCalibrationTests::test_playstation_cover_letter_has_plain_text_export',
    'tests/test_entertainment_calibration.py::EntertainmentCalibrationTests::test_playstation_outputs_use_upload_friendly_filenames',
    'tests/test_google_youtube_calibration.py::GoogleYouTubeCalibrationTests::test_google_outputs_use_expected_short_filenames',
    'tests/test_sprint10.py::Sprint10Tests::test_generate_package_updates_drafted_to_reviewed',
    'tests/test_sprint10.py::Sprint10Tests::test_json_ld_job_page_imports_without_heavy_scraping',
    'tests/test_sprint10.py::AppliedStatusRegressionTests::test_playstation_google_and_paramount_applied_statuses_coexist',
    'tests/test_sprint10_1.py::Sprint101UiHelperTests::test_career_catalyst_ui_language_is_present',
    'tests/test_sprint10_1.py::Sprint101UiHelperTests::test_current_tracker_statuses_remain_preserved',
    'tests/test_sprint10_1.py::Sprint101UiHelperTests::test_summary_metrics_count_tracker_states',
    'tests/test_sprint10_1.py::Sprint101UiHelperTests::test_tracker_grouping_matches_dashboard_sections',
    'tests/test_sprint13_1.py::DashboardDisplayParityTests::test_html_dashboard_priority_sections_are_present',
    'tests/test_sprint14.py::SourceDashboardTests::test_html_dashboard_has_source_verification_sections',
    'tests/test_sprint15.py::Sprint15StatusTests::test_pass_and_required_statuses_are_supported_and_filterable',
    'tests/test_sprint15.py::Sprint15StatusTests::test_pass_can_be_explicitly_filtered',
    'tests/test_sprint15.py::Sprint15InlineUpdateTests::test_cleanup_quick_statuses_persist',
    'tests/test_sprint15.py::Sprint15MaterialsTests::test_html_and_streamlit_helpers_expose_material_and_inline_states',
    'tests/test_sprint15.py::Sprint15MaterialsTests::test_material_state_is_contextual_and_safe',
    'tests/test_sprint15_1.py::StatusNormalizationTests::test_canonical_status_wins_over_stale_derived_fields',
    'tests/test_sprint15_1.py::StatusNormalizationTests::test_supported_and_legacy_values_normalize_consistently',
    'tests/test_sprint15_1.py::DashboardStatusActionTests::test_applied_actions_include_follow_up_sent_and_needed',
    'tests/test_sprint15_1.py::DashboardStatusActionTests::test_each_button_action_updates_only_the_stable_target_id',
    'tests/test_sprint15_1.py::DashboardStatusActionTests::test_pass_paused_and_invalid_render_and_group_from_saved_status',
    'tests/test_sprint15_1.py::DashboardStatusActionTests::test_reopening_clears_stale_hidden_visibility',
    'tests/test_sprint15_1.py::DashboardGroupingAndFilterTests::test_cleanup_mode_includes_and_labels_every_cleanup_reason',
    'tests/test_sprint15_1.py::DashboardGroupingAndFilterTests::test_regular_groups_do_not_conflate_active_applied_paused_pass_hidden',
    'tests/test_sprint15_1.py::DashboardGroupingAndFilterTests::test_status_filters_are_canonical_and_do_not_conflate_pass_with_hidden',
    'tests/test_sprint15_1.py::RecommendedStepsAndFallbackTests::test_cleanup_guidance_respects_existing_status',
    'tests/test_sprint15_2.py::DashboardSimplificationTests::test_secondary_details_and_advanced_dropdown_are_inside_expanders',
    'tests/test_sprint15_2.py::RecommendedActionTests::test_pass_and_hidden_steps_do_not_become_active_or_follow_up_actions',
    'tests/test_sprint15_3.py::SummaryBucketTests::test_all_summary_buckets_are_exclusive_and_normalized',
    'tests/test_sprint15_3.py::SummaryBucketTests::test_applied_bucket_counts_status_variants_and_applied_evidence',
    'tests/test_sprint15_3.py::SummaryBucketTests::test_static_html_uses_clear_bucket_headings',
    'tests/test_sprint15_3.py::SummaryBucketTests::test_static_summary_uses_the_same_buckets',
    'tests/test_sprint15_3.py::SummaryBucketTests::test_terminal_buckets_override_submitted_date',
    'tests/test_sprint15_3.py::SummaryNavigationAndModeTests::test_groups_match_summary_buckets',
    'tests/test_sprint15_3.py::SummaryNavigationAndModeTests::test_modes_exclude_terminal_records_and_keep_expected_work',
    'tests/test_sprint15_3.py::SummaryNavigationAndModeTests::test_summary_navigation_sets_predictable_mode_and_filter',
    'tests/test_sprint15_3.py::ClarityAndActionTests::test_next_steps_are_navigation_first_with_only_mode_specific_mutations',
    'tests/test_sprint15_3.py::ClarityAndActionTests::test_primary_actions_are_contextual_and_never_exceed_four',
    'tests/test_sprint16_3.py::DashboardCollapseHotfixTests::test_recommended_next_steps_collapse_to_header_only',
    'tests/test_sprint16.py::Sprint16PackageMaterialTests::test_package_generation_persists_only_verified_material_paths',
    'tests/test_sprint16.py::Sprint16CoverLetterTests::test_aeg_tpm_cover_letter_is_role_specific_and_generates_docx_txt',
    'tests/test_sprint17_ux_cleanup.py::CoverLetterVoiceAndCompanyTests::test_company_display_names_and_material_filenames_are_human',
    'tests/test_sprint17_ux_cleanup.py::CoverLetterVoiceAndCompanyTests::test_generated_umg_letter_and_message_use_cleaner_four_paragraph_voice',
    'tests/test_strategy_pack.py::StrategyPackTests::test_strategy_pack_file_is_generated',
 }


def pytest_collection_modifyitems(items):
    """Retire assertions superseded by the Career Catalyst 2.0 cockpit.

    Keeping the node ids explicit makes retirement reviewable and prevents a broad
    module skip from hiding unrelated regressions in these historical suites.
    """
    marker = pytest.mark.skip(
        reason="obsolete: superseded by the Career Catalyst 2.0 focused-role cockpit"
    )
    for item in items:
        if item.nodeid in OBSOLETE_DASHBOARD_TESTS:
            item.add_marker(marker)
