# Test suite

The repository test suite covers tracker lifecycle, Evidence selection and provenance,
role intelligence, scoring, candidate-facing generation, transactional packages,
DOCX/ATS quality, archive ownership, dashboard behavior, and launcher lifecycle.

Tests that generate files must use a temporary project/export root. They must not rely
on committed generated exports, a durable runtime snapshot, the protected Documents
checkout, or another test's output.

## Sprint 42 legacy reconciliation

The production-acceptance pass classified and reconciled inherited failures by shared
root cause:

- **Current implementation defects:** legacy and canonical IDs for the same selected
  project were not treated as one provenance identity; cover-letter generation assumed
  every mocked context included `role_intent`; and launcher diagnostics still named the
  removed command-file launcher. These were repaired in the shared implementation and
  retain direct regression coverage.
- **Superseded generated-output contracts:** legacy tests expected title-cased or
  historical filenames, committed generated exports, and pre-transaction package
  contents. Tests now assert the canonical lower-snake-case package, required readiness
  artifacts, manifests, DOCX hygiene, and ATS/styled parity from isolated roots.
- **Superseded lifecycle/UI copy:** tests expected raw legacy statuses, retired dashboard
  labels/actions, a mutable closed-posting preflight, and obsolete follow-up wording.
  Tests now use canonical status access and the current non-mutating lifecycle/UI contract.
- **Superseded candidate-copy expectations:** exact historical employer aliases,
  mandatory project mentions, and old company-specific prose were replaced by assertions
  for canonical employer identity, supported leadership scope, role-relevant language,
  selected-Evidence provenance, and current safety guards.
- **Superseded launcher architecture:** command-file assumptions were replaced with the
  repository-owned macOS app, launchctl-managed process reuse, explicit durable roots,
  and current rebuilt Streamlit entrypoint.

No skip, xfail, blanket ignore, or weakened safety gate is used to obtain the acceptance
result. Narrow unit tests may mock a separately covered quality gate only when their
subject is transactional persistence or material routing, and they must still create all
artifacts required by the current package contract.
