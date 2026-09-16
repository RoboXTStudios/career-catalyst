# Changelog

## 0.0.23 - Sprint 11

- Added follow-up and networking message generation.
- Added follow-up strategy packs for applied roles.
- Added recruiter, hiring manager, warm contact, and referral ask message drafts.
- Added company voice profiles for cover letter generation.
- Added role family detection for creative, music, GTM, transformation, streaming, and AI operations roles.
- Improved company-specific cover letter tone and proof point selection.
- Added Bandsintown/music content strategy cover letter support.
- Added dynamic company and role intelligence.
- Added deterministic company category and role family detection for new prospects.
- Added dynamic voice profile fallback for unknown companies.
- Updated cover letters, messages, application notes, and follow-ups to use effective voice profiles.
- Added followups-all command for applied roles.
- Added role detection preview in the local UI.
- Added Follow-Up tab to the local Career Catalyst UI.
- Added follow-up links to dashboard application cards.
- Added dashboard metadata for company category and role family.
- Added tests for follow-up generation, company voice profiles, dynamic role intelligence, and tone safeguards.

## 0.0.22 - Sprint 10.2

- Added macOS one-click launcher for Career Catalyst.
- Added launcher documentation.
- Added optional launcher-info CLI command.
- Reduced need to manually type Streamlit launch commands.

## 0.0.21 - Sprint 10.1

- Restyled local Streamlit UI to match Career Catalyst dashboard.
- Replaced CampaignOS-style branding with Career Catalyst application cockpit language.
- Added dashboard-like cards, status groupings, and application workflow sections.
- Preserved tracker statuses across applied, paused, and invalid roles.
- Added tests for UI helper imports and branding safeguards.

## 0.0.20 - Sprint 10

- Added local Career Catalyst application cockpit UI.
- Added prospect intake from official career page URL and pasted job description text.
- Added simple URL import helper with manual paste fallback.
- Added package generation from tracker entries.
- Added status update workflow without manual YAML editing.
- Added tracker utilities for prospect management.
- Preserved applied statuses across PlayStation, Google, and Paramount.
- Added tests for prospect intake, tracker updates, dashboard status preservation, and URL import fallback.

## 0.0.19 - Sprint 9.1

- Updated resume headers to show Trisha’s full LinkedIn URL.
- Added LinkedIn URL preservation in Markdown, Styled DOCX, and ATS DOCX exports.
- Added clickable LinkedIn hyperlink support where feasible.
- Added tests for LinkedIn URL visibility and old-link prevention.

## 0.0.18 - Sprint 9

- Stabilized application tracker schema.
- Added tracker ids, aliases, and dashboard visibility flags.
- Fixed dashboard matching across multiple applied roles.
- Added Applied tracking for PlayStation and Google.
- Marked invalid PlayStation Ad Operations role as hidden.
- Marked Crunchyroll Enterprise Strategy role as Paused.
- Added tracker validation command.
- Added tests for tracker matching, dashboard status badges, and hidden invalid roles.

## 0.0.17 - Sprint 8.4

- Added Google/YouTube-specific positioning.
- Added long-term hands-on Google advertising product familiarity.
- Calibrated Google/YouTube materials toward GTM operations, product activation, and large advertiser execution.
- Added safeguards against implying Google employment or internal access.
- Added tests for Google/YouTube positioning.

## 0.0.16 - Sprint 8.3

- Added upload-friendly filename generation.
- Shortened DOCX resume export filenames.
- Shortened application material filenames.
- Added company and role filename shortening helpers.
- Added plain text cover letter export support.
- Updated dashboard file linking for shortened filenames.
- Added tests for filename safety and upload-friendly exports.

## 0.0.15 - Sprint 8.2

- Polished cover letter paragraph structure.
- Reduced repetitive entertainment experience phrasing.
- Added shorthand handling for OMG23 after first full mention.
- Added tests for cover letter concision and employer shorthand.

## 0.0.14 - Sprint 8.1

- Calibrated Disney entertainment experience taxonomy.
- Added Disney Studios Theatrical and Disney Streaming/DSS hierarchy.
- Added Pixar, Lucasfilm, Marvel, 20th Century Studios, Searchlight Pictures, Disney+, and franchise/IP language where relevant.
- Reweighted experience toward theatrical and streaming film campaign operations.
- Reduced overemphasis on Networks and Corporate Brand Management.
- Improved PlayStation-specific creative/product operations positioning.
- Improved cover letter opening sentence generation.
- Added repeated-word cleanup safeguards.
- Regenerated PlayStation application package.
- Added tests for entertainment experience calibration and repeated-word prevention.

## 0.0.13 - Sprint 8

- Added local static HTML dashboard.
- Added application package view across resumes, messages, and strategy packs.
- Added application tracker data file.
- Added dashboard CLI command.
- Added dashboard tests.

## 0.0.12 - Sprint 7

- Added Standout Strategy Pack generation.
- Added Role Opportunity Brief.
- Added Why Trisha value proposition.
- Added 30/60/90-day plan.
- Added Strategic POV Note.
- Added interview talking points and smart interview questions.
- Added strategy-pack CLI command.
- Added tests for strategy pack generation.

## 0.0.11 - Sprint 6.1

- Improved application material voice and warmth.
- Added warm executive operator tone guidance.
- Added voice configuration file.
- Reduced robotic phrasing in cover letters and messages.
- Added tests for banned phrases, length limits, and tone safeguards.

## 0.0.10 - Sprint 6

- Added cover letter generation.
- Added recruiter message generation.
- Added hiring manager message generation.
- Added application note generation.
- Added application material CLI commands.
- Added tests for generated application materials.

## 0.0.9 - Sprint 5.3

- Added canonical platforms data source.
- Updated resume generation to preserve full platform/category language.
- Restored AI Workflow Design and Process Automation in Platforms & Technologies.
- Ensured styled and ATS exports use exact platform labels.
- Added tests for canonical platform preservation.

## 0.0.8 - Sprint 5.2

- Improved styled DOCX export to better match Trisha's v2 resume style.
- Added compact Platforms & Technologies table for styled resumes.
- Preserved table-free ATS export.
- Improved executive profile language.
- Strengthened CampaignOS bullets in generated output.
- Added tests for styled table output and ATS no-table output.

## 0.0.7 - Sprint 5.1

- Added styled DOCX export mode.
- Added ATS DOCX export mode.
- Added support for styled_resume_template.docx.
- Added export mode argument to export-docx CLI command.
- Added ATS-safe no-table output.
- Added tests for styled and ATS DOCX exports.

## 0.0.6 - Sprint 5

- Added DOCX export from tailored Markdown resumes.
- Added clean ATS-friendly DOCX styling.
- Added optional DOCX template support.
- Added export-docx CLI command.
- Added DOCX export tests.

## 0.0.5 - Sprint 4

- Added tailored Markdown resume generation.
- Added profile-specific tailoring logic.
- Added Markdown export folder.
- Added tailor CLI command.
- Added tests for resume generation.

## 0.0.4 - Sprint 3

- Added match scoring between career data and parsed job descriptions.
- Added weighted scoring model.
- Added match bands.
- Added recommended resume profile selection.
- Added missing keyword detection.
- Added tailoring notes.
- Added score CLI command.
- Added score matching tests.

## 0.0.3 - Sprint 2

- Added job description parsing.
- Added metadata extraction for job title, company, location, salary, employment type, and source URL.
- Added keyword extraction.
- Added responsibility and qualification parsing.
- Added parse-job CLI command.
- Added parser tests.

## 0.0.2 - Sprint 1

- Added YAML data loading.
- Added data validation CLI command.
- Added profile display CLI command.
- Added basic tests for data loading.

## 0.0.1 - Sprint 0

- Initialized Career Catalyst project structure.
- Added foundational documentation.
- Added starter YAML and Markdown template files.
