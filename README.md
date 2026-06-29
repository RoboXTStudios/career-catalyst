# Career Catalyst

Career Catalyst is a personal career optimization engine for Trisha Lynch. It is designed to become a structured source of truth for resume content, achievements, skills, projects, target roles, target companies, and job application materials.

The project exists to make career materials easier to tailor without losing consistency. Instead of rewriting resumes, cover letters, recruiter notes, hiring manager messages, and interview prep from scratch, Career Catalyst will eventually draw from a shared data layer and assemble role-specific outputs.

## Folder Structure

- `config/` stores project settings, target companies, and role profiles.
- `data/` stores the candidate source of truth in YAML.
- `jobs/` stores job descriptions and notes for future analysis.
- `templates/` stores starter Markdown templates for resumes, letters, messages, and interview prep.
- `exports/` is reserved for generated documents and messages.
- `scripts/` is reserved for future project scripts.
- `tests/` is reserved for future validation and regression tests.

## Sprint 0

Sprint 0 includes only the foundational project structure and documentation:

- Project README, project brief, architecture notes, roadmap, and changelog.
- Starter YAML files based on Trisha Lynch's current career profile.
- Starter Markdown templates for common job application materials.
- Empty export folders for future generated outputs.

Sprint 0 does not include application logic, scoring, resume generation, OpenAI API integration, web scraping, a CLI, or a UI.

## Sprint 1 Commands

Validate required YAML files:

```bash
python3 scripts/cli.py validate-data
```

Show the candidate profile summary:

```bash
python3 scripts/cli.py show-profile
```

## Sprint 2 Commands

Parse a local job description:

```bash
python3 scripts/cli.py parse-job jobs/sample_job_description.md
```

## Sprint 3 Commands

Score a local job description against the structured career data:

```bash
python3 scripts/cli.py score jobs/sample_job_description.md
```

## Sprint 4 Commands

Generate a tailored Markdown resume:

```bash
python3 scripts/cli.py tailor executive_operations jobs/sample_job_description.md
```

## Sprint 5 Commands

Generate the tailored Markdown resume:

```bash
python3 scripts/cli.py tailor executive_operations jobs/sample_job_description.md
```

Export the tailored Markdown resume to DOCX:

```bash
python3 scripts/cli.py export-docx exports/markdown/Trisha_Lynch_executive_operations_Crunchyroll_Resume.md
```

## Sprint 5.1 Commands

Export a styled resume for human reviewers and direct uploads where formatting is accepted:

```bash
python3 scripts/cli.py export-docx styled exports/markdown/Trisha_Lynch_executive_operations_Crunchyroll_Resume.md
```

Export a plain resume for applicant tracking systems and portals that parse resumes aggressively:

```bash
python3 scripts/cli.py export-docx ats exports/markdown/Trisha_Lynch_executive_operations_Crunchyroll_Resume.md
```

Both versions use the same tailored Markdown content source. The original Sprint 5 command remains available and defaults to styled mode.

## Sprint 5.2

Styled DOCX:

- Uses compact visual formatting.
- Includes a table-style Platforms & Technologies section.
- Is intended for human reviewers and direct uploads.

ATS DOCX:

- Uses no tables.
- Uses simple headings and bullets.
- Is intended for applicant tracking systems and portals that aggressively parse resumes.

## Canonical Platforms

Platforms & Technologies are controlled by `data/platforms.yml`. Styled and ATS exports must use this canonical file so important positioning language such as AI Workflow Design and Process Automation is preserved.

## Sprint 6 Commands

Generate a cover letter:

```bash
python3 scripts/cli.py cover-letter jobs/sample_job_description.md
```

Generate a recruiter message:

```bash
python3 scripts/cli.py message recruiter jobs/sample_job_description.md
```

Generate a hiring manager message:

```bash
python3 scripts/cli.py message hiring-manager jobs/sample_job_description.md
```

Generate a short application portal note:

```bash
python3 scripts/cli.py application-note jobs/sample_job_description.md
```

Generated messages are drafts and should be reviewed before sending. Materials are grounded in structured career data and parsed job details; contacts, referrals, personal relationships, and unsupported company-specific claims must not be invented.

## Voice Calibration

Career Catalyst uses `config/voice.yml` to guide generated application materials. The target voice is warm, human, confident, strategic, and grounded. Generated materials should sound like a thoughtful senior operator, not a corporate template.

## Sprint 7 Commands

Generate a Standout Strategy Pack:

```bash
python3 scripts/cli.py strategy-pack jobs/sample_job_description.md
```

Strategy packs are designed to help Trisha stand out beyond resume tailoring. They are grounded in the job description and structured career data, and can support interview preparation, hiring manager outreach, application notes, and follow-up messages. Each pack should be reviewed before use.

## Sprint 8 Commands

Generate the local application dashboard:

```bash
python3 scripts/cli.py dashboard
```

Open the generated dashboard in the default browser:

```bash
open exports/dashboard/index.html
```

The dashboard is a local static HTML file that groups generated application materials by job. It links to resumes, messages, cover letters, application notes, and strategy packs without using a server or external services. Application status can be updated manually in `data/application_tracker.yml`.

## Entertainment Experience Calibration

Career Catalyst emphasizes Trisha's primary entertainment experience across Disney Studios Theatrical, Disney Streaming/DSS, theatrical and streaming film campaign operations, franchise/IP priorities, and premium entertainment campaign execution.

Disney Studios Theatrical includes Pixar, Lucasfilm, Marvel, 20th Century Studios, and Searchlight Pictures. Disney Streaming/DSS includes Disney+, Disney Streaming Services, streaming pushes from theatrical IP, and relevant Disney Branded Television / DBT work.

Generated materials should not overemphasize Networks or make Corporate Brand Management the central headline. Corporate Brand Management should be framed as franchise/IP and brand management support where relevant.

## Upload-Friendly Filenames

Career Catalyst exports application materials using concise filenames designed for applicant portals.

Example: `TrishaLynch_HeadGlobalCreativeOps_PlayStation_Styled.docx`

Styled files are intended for human reviewers. ATS files are intended for applicant tracking systems.

## Google/YouTube Positioning

For Google and YouTube roles, Career Catalyst may reference Trisha's long-term hands-on experience with Google advertising products, including YouTube, dating back to the early 2000s. Generated materials should frame this as platform familiarity and campaign activation experience, not employment at Google or internal product ownership.

Generated application and networking materials must not reference family connections, internal Google relationships, or unsupported referrals. Professional outreach should remain grounded in Trisha's direct work experience and professional contacts.

## Application Tracker

Career Catalyst uses `data/application_tracker.yml` as the source of truth for application status.

Supported statuses:

- Drafted
- Reviewed
- Applied
- Follow-up
- Interviewing
- Paused
- Rejected
- Invalid
- Archived

Validate tracker data and regenerate the dashboard:

```bash
python3 scripts/cli.py validate-tracker
python3 scripts/cli.py dashboard
```

Tracker entries can include company and role aliases to help the dashboard match generated job packages to the correct application record. Invalid or unavailable roles can be preserved with `show_on_dashboard: false` so they do not clutter the active dashboard.

## What Comes Next

Later sprints can add interview prep generation and carefully verified company or job-source workflows.
