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

## What Comes Next

Later sprints can add PDF export, cover letter generation, interview prep generation, and carefully verified company or job-source workflows.
