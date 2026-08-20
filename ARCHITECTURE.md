# Career Catalyst architecture

## Canonical boundaries

Career Catalyst has three deliberately separate kinds of state:

1. Canonical career data: verified employment, achievements, skills, platforms, projects, certifications, candidate identity, Evidence projects, and Evidence cards.
2. Role state: stable tracker ID, posting, score, status/history, saved Role Intelligence, and explicit Evidence selection.
3. Generated state: a stable-ID-owned package with physical files, hashes, material references, and a canonical manifest.

`scripts/golden_resume.py` is the normalized read and validation service for canonical career data. The existing YAML files remain authoritative. This avoids the earlier risk of one résumé file, project data, Evidence projects, and Evidence cards drifting as separate career histories.

Every canonical record has a deterministic namespaced identity and source path. Evidence-card source references are resolved against the canonical record index. Candidate-facing selection never deletes or rewrites canonical evidence.

## Role and Evidence resolution

`scripts/package_context.py` resolves one tracker record by stable ID, one matching posting, its canonical score, saved Evidence IDs, effective Role Intelligence, and one role-intent snapshot. Package code does not fall back to company/title similarity when a stable identity is present.

Explicit tracker Evidence is the artifact provenance boundary. `scripts/evidence_tailoring.py` records every selected item as used or omitted for ATS résumé, Styled résumé, and cover letter. An unselected fallback can appear only when the selection policy explicitly enables it, and the Package Summary names it.

System recommendations are contextual rather than absolute:

- senior enterprise Evidence normally leads senior corporate applications;
- Career Catalyst leads relevant product, AI-workflow, transformation, and builder proof;
- RoboXT Studios leads relevant music, media, creative, and content proof;
- CampaignOS supports campaign-systems, workflow, QA, and relevant AI-operations proof.

## Generation and quality pipeline

`scripts/package_generator.py` owns the consolidated package path:

1. Stable prospect and posting preflight.
2. Golden Resume validation.
3. Effective role context and explicit Evidence resolution.
4. Requirement coverage mapping.
5. Grounded résumé, letter, note, outreach, strategy, and interview material generation.
6. Candidate-facing factual, provenance, career-language, and restricted-claim checks.
7. Voice-drift, evidence-density, and recruiter-credibility checks.
8. Styled and ATS DOCX export from the same résumé source.
9. Actual OOXML sanitation and validation.
10. ATS round-trip parse and Styled/ATS factual parity.
11. Interview Conversion Gate.
12. Complete-package validation and atomic promotion.

Generation runs in a private temporary project and export root. Only a complete package is copied into a hidden promotion candidate. The existing package is moved to a rollback path immediately before the atomic swap. Tracker serialization passes the same strict validation boundary. Any exception restores the prior package and tracker bytes.

## Requirement coverage

`scripts/submission_readiness.py` classifies meaningful posting requirements as `PROVEN`, `TRANSFERABLE`, `WEAK`, or `NOT_SUPPORTED`. Each row preserves original wording, normalized concept, importance, Evidence IDs and sources, explanation, résumé location, and confidence.

Semantic concepts align genuinely equivalent language such as martech and marketing technology or PMO and delivery governance. Explicit restricted concepts such as Salesforce administration, quota ownership, SQL expertise, P&L ownership, label-account ownership, and artist management remain `NOT_SUPPORTED` unless future canonical evidence is added. No score or keyword rule can turn a gap into a claim.

## DOCX and ATS invariants

`scripts/docx_quality.py` operates on the actual OOXML ZIP package:

- removes comment definitions, references, people parts, and orphan relationships;
- accepts final inserted text, removes deleted/moved-from revision content, and disables tracking markers;
- removes custom XML/properties introduced by generation;
- removes creator, modifier, time, revision, application, version, company, and manager metadata;
- reopens the sanitized file and proves visible text and hyperlinks did not change;
- blocks prohibited generator identifiers;
- requires zero comments and unintended revisions.

The ATS export is single-column, table-free, and text-box-free. Its exported DOCX is parsed in reading order and compared with the intended Markdown. The resulting ATS Parsed Preview is a human audit artifact, not a simulated proprietary ATS score.

Styled and ATS files may differ in layout only. Token-level visible facts and referenced hyperlinks must match.

## Interview Conversion Gate

The final gate reports `READY TO SUBMIT` or `NEEDS REVIEW` with role fit, ATS parse, requirement coverage, evidence grounding, career credibility, voice consistency, specificity, generic language, keyword use, unsupported claims, DOCX hygiene, and human review items. It also states three evidence-backed interview reasons, actual elimination risks, meaningful tailoring performed, and unsupported requirements deliberately not claimed.

A blocking provenance, candidate-language, DOCX, ATS, or parity failure prevents promotion. Truthful gaps may produce `NEEDS REVIEW` without destroying an otherwise valid package.

## Maintenance

Use focused tests for the affected subsystem first, then the complete suite. Package-generation tests must inject temporary tracker, runtime, archive, and export paths. Validate canonical inventory with `load_golden_resume()` and `validate_golden_resume()`. Validate document packages with `inspect_docx_hygiene()`, `validate_ats_round_trip()`, and `compare_docx_factual_parity()`.

Never use production runtime data as fixtures, rewrite generated history during deployment, or use a dirty checkout as the code source.
