# Career Catalyst

Career Catalyst is a local, evidence-grounded career operations system for Trisha Lynch. It joins a validated career source of truth to role intelligence, stable prospect records, selected Evidence, truthful candidate writing, ATS-safe document export, application tracking, and retained package history.

The application does not treat a job description as permission to invent résumé content. Its package path is:

`canonical career history → role requirements → selected Evidence → grounded writing → candidate quality checks → DOCX hygiene → ATS round trip → Interview Conversion Gate → atomic promotion`

## Current system

- `data/positions.yml`, `achievements.yml`, `skills.yml`, `platforms.yml`, `projects.yml`, `certifications.yml`, `personal_brand.yml`, and `evidence_projects.yml` remain the authoritative candidate records.
- `scripts/golden_resume.py` assembles and validates those sources as the complete Golden Resume inventory. It does not create a second résumé or data store.
- `config/evidence_cards.yml` provides reusable, source-linked Evidence cards. Tracker-selected Evidence is authoritative for candidate artifacts; unselected fallback must be explicit and disclosed.
- `scripts/role_intent.py` and the role-intelligence modules resolve current role context and saved overrides.
- `scripts/package_generator.py` generates in private staging and promotes only a complete, validated package. A failed run preserves the last valid package and tracker state.
- `scripts/docx_quality.py` sanitizes actual OOXML packages, removes comments/revisions/generator identity, verifies visible content and hyperlinks, and parses the exported ATS résumé.
- `scripts/submission_readiness.py` builds the requirement matrix, specificity and voice checks, recruiter-credibility review, ATS Parsed Preview, and Interview Conversion Gate.
- `app.py` is the current Streamlit application.

Detailed design and invariants are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Golden Resume

The Golden Resume is the full verified inventory, not a submission résumé. Candidate-facing résumés select only evidence that earns space for the role. Established senior career evidence normally outranks recent projects, with contextual exceptions:

- Career Catalyst is primary current product and applied AI-workflow evidence for relevant product, transformation, builder, and technical-program roles.
- RoboXT Studios is current media-production, creative, content, music, and publishing evidence when those domains matter.
- CampaignOS is a working prototype and supporting evidence for campaign systems, workflow governance, QA, and role-relevant AI operations.
- GitHub is included only when the verified public build record adds credibility. URLs remain visible and clickable.

Historical employer aliases are matching-only. Candidate-facing language uses `OMG23 / OMD Entertainment, Omnicom Media Group` and preserves the verified scope of 10 direct reports and an integrated 64-person organization.

## Package outputs

A complete package contains both résumé DOCX variants, a cover-letter DOCX, a Package Summary, an ATS Parsed Preview, a Requirement Coverage Matrix, an Interview Conversion Gate, and a canonical manifest. Additional notes, outreach, strategy, interview, and follow-up materials are retained when generated.

The readiness artifacts are intentionally plain-language. ATS validation checks parseability; it does not pretend to reproduce a proprietary ATS score. `NOT_SUPPORTED` requirements remain gaps and are never converted into candidate claims.

## Local commands

```bash
python3 scripts/cli.py validate-data
python3 scripts/cli.py parse-job jobs/sample_job_description.md
python3 scripts/cli.py score jobs/sample_job_description.md
python3 scripts/cli.py generate-package <tracker-id>
python3 -m streamlit run app.py --server.address 127.0.0.1 --server.port 8503
```

Run validation:

```bash
python3 -m pytest -q
PYTHONPYCACHEPREFIX=/private/tmp/career-catalyst-pyc python3 -m compileall -q scripts app.py
git diff --check
```

All generation or tests that exercise writes should use an isolated runtime and injected export root. Never point fixtures at durable production data.

## Safety boundaries

Career Catalyst does not fabricate experience, hide keywords, inject invisible text, impersonate applications, or manipulate metadata to deceive hiring systems. It does not infer ownership from adjacency. Candidate materials require source-linked evidence and remain subject to human review before submission.
