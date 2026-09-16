# Roadmap

## Sprint 0: Project Setup And Documentation

- Create project folder structure.
- Add foundational documentation.
- Add starter YAML source-of-truth files.
- Add starter Markdown templates.

## Sprint 1: YAML Data Loading

- Load YAML files from `config/` and `data/`.
- Validate required fields.
- Report missing or malformed content.

## Sprint 2: Job Description Parsing

- Store job descriptions in `jobs/`.
- Parse key responsibilities, qualifications, and keywords.
- Preserve original job description text for review.

## Sprint 3: Keyword And Match Scoring

- Compare job descriptions against the candidate source of truth.
- Identify matching skills, achievements, industries, and tools.
- Produce transparent match notes.

## Sprint 4: Resume Markdown Generation

- Generate tailored resume drafts in Markdown.
- Select relevant achievements and projects by role profile.
- Preserve candidate-approved language.

## Sprint 5: DOCX Export

- Convert generated Markdown resumes to DOCX.
- Apply consistent formatting.
- Store outputs in `exports/docx/`.

## Sprint 6: Cover Letter And Message Generation

- Generate role-specific cover letters.
- Generate recruiter and hiring manager messages.
- Store outputs in `exports/messages/`.

## Sprint 7: Interview Prep Generation

- Generate company and role-specific interview prep.
- Include likely themes, achievement prompts, and questions.
- Store outputs in `exports/interview/`.

## Future

- Web verification.
- Company tracker.
- Official job source validation.
- Application packet management.
