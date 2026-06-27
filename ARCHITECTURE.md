# Architecture

Career Catalyst is organized around a source-of-truth model. The project begins with structured candidate data, then later layers can read that data to produce tailored career materials.

## Source Of Truth

The source of truth is the canonical career dataset for Trisha Lynch. It should include positions, achievements, skills, projects, certifications, target roles, target companies, and personal brand language.

Future generation should reference this data instead of inventing or duplicating content across documents.

## YAML Data Layer

The YAML files in `data/` and `config/` hold structured information that can later be loaded, validated, filtered, and matched to job descriptions.

Examples:

- `data/positions.yml` for employment history.
- `data/achievements.yml` for reusable impact statements.
- `data/skills.yml` for skill groups and tools.
- `config/role_profiles.yml` for target role patterns.
- `config/target_companies.yml` for priority companies and industries.

## Markdown Template Layer

The Markdown files in `templates/` provide placeholders for future outputs. These are not generated resumes yet. They define the shape of common materials so future scripts know where tailored content might go.

## Export Layer

The `exports/` folder is reserved for future generated assets:

- `exports/docx/` for Word documents.
- `exports/pdf/` for PDF files.
- `exports/messages/` for generated outreach.
- `exports/interview/` for generated interview prep.

## Future CLI Layer

A future CLI may provide commands for loading candidate data, analyzing job descriptions, generating Markdown outputs, and exporting documents.

No CLI is included in Sprint 0.

## Future Automation Layer

Future automation may support verified job-source checks, target company tracking, reusable application packets, and export workflows.

No automation, scraping, API usage, or external job verification is included in Sprint 0.
