# Sprint 32 Storage Cleanup Dry Run Review

- Generated: 20260731T204411Z
- Dry-run command exit status: 0
- Files inspected: 11,976
- Disk space inspected: 81,097,240 bytes
- Cleanup actions proposed by existing tool: 179
- Integrity findings: 0 critical, 1061 warnings

## Classification summary

| Category | Physical files | Size | Inventory rows |
|---|---:|---:|---:|
| A. PRESERVE — ACTIVE OR REQUIRED | 7,240 | 38,330,358 bytes | 7,240 |
| B. PRESERVE — HISTORICAL BUT VALID | 4,423 | 37,202,006 bytes | 4,423 |
| C. SAFE TEMPORARY DELETION CANDIDATES | 107 | 2,243,381 bytes | 26 |
| D. QUARANTINE CANDIDATES | 159 | 2,741,456 bytes | 159 |
| E. MANUAL REVIEW REQUIRED | 47 | 580,039 bytes | 47 |

## Unreferenced materials

- Total File Count: `1051`
- Total Size Bytes: `7401518`
- Extension Breakdown: `{'.docx': 151, '.html': 1, '.json': 2, '.md': 345, '.pdf': 1, '.txt': 543, '[no extension]': 8}`
- Top Level Directory Breakdown: `{'.DS_Store': 1, 'active': 147, 'archive': 734, 'dashboard': 1, 'docx': 54, 'followups': 30, 'internal': 15, 'messages': 54, 'pdf': 3, 'strategy_packs': 12}`
- Oldest Modification Date: `2026-06-26T23:46:48.072176+00:00`
- Newest Modification Date: `2026-07-30T21:54:05.569299+00:00`
- Linked To Known Live Role Ids: `307`
- Linked To Archive Role Ids: `15`
- Matching Active Package Files By Checksum: `113`
- Matching Archived Copies By Checksum: `26`
- Appearing Duplicate By Checksum: `569`
- Appearing Unique By Checksum: `482`
- Resume Files: `196`
- Cover Letters: `124`
- Strategy Packs: `254`
- Notes Messages Interview Prep: `542`
- Obvious Temporary Artifacts: `8`
- Manual Review Required: `15`
- Classification Breakdown: `{'C': 8, 'D': 159, 'A': 299, 'E': 15, 'B': 570}`

## Duplicate package directories

### duplicate-package-1 — Azira — Director, Chief of Staff & Business Operations

- Role ID: `azira_director_chief_of_staff_business_operations`
- Strict duplicate: `False`
- Recommendation: Manual review required: preserve the tracker-selected folder and do not quarantine either directory until unique versions are reconciled.
- `/Users/trisha.lynch/Documents/career-catalyst/exports/active/applied_followup/azira_director_chief_of_staff_business_operations` — 12 files, 128442 bytes, tracker referenced: True, archive referenced: False, tree SHA-256: `aed9d89b5d67a90d468ffee45244023605904c55c42e66c184302baa3b9530c2`
- `/Users/trisha.lynch/Documents/career-catalyst/exports/active/in_progress/azira_director_chief_of_staff_business_operations` — 17 files, 117143 bytes, tracker referenced: False, archive referenced: False, tree SHA-256: `6b4521f2ae5367170d6bd4468e34092733f51763a097cd9a3ec7157117b69ec6`
- Unique/different in `/Users/trisha.lynch/Documents/career-catalyst/exports/active/applied_followup/azira_director_chief_of_staff_business_operations`: `['azira_director_chief_staff_business_operations_trisha_lynch_ats_resume.docx', 'azira_director_chief_staff_business_operations_trisha_lynch_cover_letter.docx', 'azira_director_chief_staff_business_operations_trisha_lynch_cover_letter.txt', 'azira_director_chief_staff_business_operations_trisha_lynch_resume.txt', 'azira_director_chief_staff_business_operations_trisha_lynch_styled_resume.docx', 'manifest.json']`
- Unique/different in `/Users/trisha.lynch/Documents/career-catalyst/exports/active/in_progress/azira_director_chief_of_staff_business_operations`: `['azira_director_chief_staff_business_operations_trisha_lynch_ats_resume.docx', 'azira_director_chief_staff_business_operations_trisha_lynch_cover_letter.docx', 'azira_director_chief_staff_business_operations_trisha_lynch_cover_letter.txt', 'azira_director_chief_staff_business_operations_trisha_lynch_followup_strategy.txt', 'azira_director_chief_staff_business_operations_trisha_lynch_hiring_manager_followup.txt', 'azira_director_chief_staff_business_operations_trisha_lynch_recruiter_followup.txt', 'azira_director_chief_staff_business_operations_trisha_lynch_referral_ask.txt', 'azira_director_chief_staff_business_operations_trisha_lynch_resume.txt', 'azira_director_chief_staff_business_operations_trisha_lynch_styled_resume.docx', 'azira_director_chief_staff_business_operations_trisha_lynch_warm_contact_message.txt', 'manifest.json']`

### duplicate-package-2 — Disney Entertainment and ESPN Product & Technology — Principal Product Mgr

- Role ID: `disney_entertainment_and_espn_product_technology_principal_product_mgr`
- Strict duplicate: `False`
- Recommendation: Manual review required: preserve the tracker-selected folder and do not quarantine either directory until unique versions are reconciled.
- `/Users/trisha.lynch/Documents/career-catalyst/exports/active/applied_followup/disney_entertainment_and_espn_product_technology_principal_product_mgr` — 13 files, 138482 bytes, tracker referenced: True, archive referenced: False, tree SHA-256: `d0895c86459b07983ed277b47f66a7c29f23209c2918a6916195bbaa5a10009c`
- `/Users/trisha.lynch/Documents/career-catalyst/exports/active/in_progress/disney_entertainment_and_espn_product_technology_principal_product_mgr` — 18 files, 117517 bytes, tracker referenced: False, archive referenced: False, tree SHA-256: `ba5ae40c2381e06084dce9e3bbd9f8f246a68bbdbbb1fec2050ed50431589c95`
- Unique/different in `/Users/trisha.lynch/Documents/career-catalyst/exports/active/applied_followup/disney_entertainment_and_espn_product_technology_principal_product_mgr`: `['disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_application_note.txt', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_ats_resume.docx', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_cover_letter.docx', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_cover_letter.txt', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_hiring_manager_message.txt', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_interview_prep.txt', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_package_summary.txt', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_recruiter_message.txt', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_resume.txt', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_strategy_pack.txt', 'disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_styled_resume.docx', 'manifest.json', 'versions/20260729T223336Z/disney_entertainment_and_espn_principal_product_mgr_trisha_lynch_interview_prep.txt']`
- Unique/different in `/Users/trisha.lynch/Documents/career-catalyst/exports/active/in_progress/disney_entertainment_and_espn_product_technology_principal_product_mgr`: `['TWDC_Principal_Product_Manager_Trisha_Lynch_ats_resume.docx', 'TWDC_Principal_Product_Manager_Trisha_Lynch_cover_letter.docx', 'application_note.txt', 'cover_letter.txt', 'followup_strategy.txt', 'hiring_manager_followup.txt', 'hiring_manager_message.txt', 'interview_prep.txt', 'manifest.json', 'package_summary.txt', 'recruiter_followup.txt', 'recruiter_message.txt', 'referral_ask.txt', 'resume.txt', 'strategy_pack.txt', 'styled_resume.docx', 'warm_contact_message.txt', '~$ver_letter.docx']`

## Historical Passed archive reasons

- `about_tiktok_creator_program_manager_emerging_verticals_tiktok_operations_los_angeles` — About TikTok — Creator Program Manager, Emerging Verticals - TikTok Operations (Los Angeles) — final status `Withdrawn / Closed`, archive reason `Withdrawn / Closed`; historical metadata only, no correction needed.
- `bandsintown_senior_copywriter_content_strategist` — BandsInTown — Senior Copywriter & Content Strategist — final status `Withdrawn / Closed`, archive reason `Withdrawn / Closed`; historical metadata only, no correction needed.
- `live_nation_worldwide_inc_ln_concerts_architectural_design_manager` — Live Nation Worldwide, Inc. — LN Concerts, Architectural Design Manager — final status `Withdrawn / Closed`, archive reason `Withdrawn / Closed`; historical metadata only, no correction needed.
- `mrbeastyoutube_head_of_programming` — Mrbeastyoutube — Head of Programming — final status `Withdrawn / Closed`, archive reason `Withdrawn / Closed`; historical metadata only, no correction needed.
- `netflix_inc_product_manager_ads_supply` — Netflix, Inc. — Product Manager, Ads (Supply) — final status `Withdrawn / Closed`, archive reason `Withdrawn / Closed`; historical metadata only, no correction needed.
- `netflix_inc_specialist_performance_marketing` — Netflix, Inc. — Specialist, Performance Marketing — final status `Withdrawn / Closed`, archive reason `Withdrawn / Closed`; historical metadata only, no correction needed.
- `the_walt_disney_company_corporate_director_talent_growth` — The Walt Disney Company (Corporate) — Director, Talent & Growth — final status `Withdrawn / Closed`, archive reason `Withdrawn / Closed`; historical metadata only, no correction needed.
- `tiktok_creator_operations_manager_emerging_verticals_tiktok_operations_los_angeles` — TikTok — Creator Operations Manager, Emerging Verticals - TikTok Operations (Los Angeles) — final status `Withdrawn / Closed`, archive reason `Withdrawn / Closed`; historical metadata only, no correction needed.

## Top 20 largest cleanup candidates

- C · 1,100,546 bytes · `/Users/trisha.lynch/Documents/career-catalyst/scripts/__pycache__` — Provably disposable Python/test cache directory
- C · 630,437 bytes · `/Users/trisha.lynch/Documents/career-catalyst/tests/__pycache__` — Provably disposable Python/test cache directory
- C · 202,266 bytes · `/Users/trisha.lynch/Documents/career-catalyst/__pycache__` — Provably disposable Python/test cache directory
- E · 139,590 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/dashboard/index.html` — Unique unreferenced material lacks a provable live/archive owner
- C · 94,923 bytes · `/Users/trisha.lynch/Documents/career-catalyst/.pytest_cache` — Provably disposable Python/test cache directory
- C · 45,141 bytes · `/Users/trisha.lynch/Documents/career-catalyst/ground_control/__pycache__` — Provably disposable Python/test cache directory
- D · 39,232 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_SeniorCopywriterContentStrategist_Bandsintown_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,207 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_HeadGlobalCreativeOps_PlayStation_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,203 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorMarketingOps_Paramount_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,201 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_AssociateManagerUcanMarketingOps_Netflix_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,187 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_HeadGlobalCreativeProductDevOps_PlayStation_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,115 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_SeniorDirectorTeamOps_UniversalMusicGroupUmg_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,086 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_SeniorDirectorProjectPmoLead_UMG_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,076 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_SrManagerStrategicIntegrationOps_WarnerChappellMusic_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,072 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_StrategyOpsLeadYouTube_Google_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,020 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorTransformation_UnitedTalentAgency_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,010 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorMatrixOpsOrganizationalEfficiency_Fieldai_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,003 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_AssociateDirectorCrmMartech_Spotify_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 39,003 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_StrategicOpsSeniorManager_Crunchyroll_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 38,998 bytes · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorConcertCommunications_LiveNationWorldwide_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest

## Top 20 oldest cleanup candidates

- D · 2026-06-26T23:46:48.072176+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/Trisha_Lynch_executive_operations_Crunchyroll_Resume.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-27T19:18:40.995907+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_HeadGlobalCreativeProductDevOps_PlayStation_Styled.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-27T19:18:41.057998+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_HeadGlobalCreativeProductDevOps_PlayStation_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-27T19:18:41.678400+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/Trisha_Lynch_executive_operations_Crunchyroll_Resume_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-27T19:18:41.971752+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/Trisha_Lynch_executive_operations_Crunchyroll_Resume_Styled.docx` — Legacy generated output is not referenced by a live role or archive manifest
- C · 2026-06-27T20:32:04.519603+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/templates/.DS_Store` — Operating-system metadata file
- D · 2026-06-27T20:33:59.794029+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/messages/PlayStation_Cover_Letter.txt` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:48:32.342380+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorAdOpsTechnology_PlayStation_Styled.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:48:32.399967+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorAdOpsTechnology_PlayStation_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:48:53.224338+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorMarketingOps_Paramount_Styled.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:48:53.289401+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorMarketingOps_Paramount_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:49:08.658796+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorTransformation_UnitedTalentAgency_Styled.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:49:08.715627+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorTransformation_UnitedTalentAgency_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:49:23.474417+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorStrategyOpsProductTechnology_DisneyEntertainmentAndEspn_Styled.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:49:23.531182+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorStrategyOpsProductTechnology_DisneyEntertainmentAndEspn_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:49:39.531066+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorMatrixOpsOrganizationalEfficiency_Fieldai_Styled.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:49:39.589509+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorMatrixOpsOrganizationalEfficiency_Fieldai_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:49:53.934556+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_SeniorCopywriterContentStrategist_Bandsintown_Styled.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:49:53.999570+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_SeniorCopywriterContentStrategist_Bandsintown_ATS.docx` — Legacy generated output is not referenced by a live role or archive manifest
- D · 2026-06-30T18:50:06.379041+00:00 · `/Users/trisha.lynch/Documents/career-catalyst/exports/docx/TrishaLynch_DirectorTalentGrowth_TheWaltDisneyCompany_Styled.docx` — Legacy generated output is not referenced by a live role or archive manifest

## Stop condition and next action

Both duplicate package-directory warnings contain unique or differing files. Cleanup apply is blocked pending explicit manual decisions. No files were deleted, moved, or quarantined.

The documented apply command is recorded in the JSON report for review only and was not run.
