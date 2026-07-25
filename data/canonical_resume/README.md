# Canonical résumé foundation

`Trisha_Lynch_Golden_Resume_2026.docx` is the approved human-readable Golden
Master content reference. The structured YAML files listed under
`canonical_resume_foundation.baseline_files` in `config/settings.yml` are the
operational source consumed by Career Catalyst.

The structured source must preserve the Golden Master’s factual scope,
positioning, full role history, products, tools, and dates. Candidate-authored
materials must not add unsupported Disney brand claims, age-signaling language,
or an academic degree that is not present in the approved baseline.

When the Golden Master is deliberately revised:

1. update and visually verify the DOCX;
2. reconcile the approved changes into the structured YAML;
3. run `tests/test_sprint30_golden_resume.py`; and
4. generate and visually inspect temporary ATS and styled exports.

Evidence records remain separate, retain their stable IDs and provenance, and
are eligible for candidate materials only under their existing usage controls.
