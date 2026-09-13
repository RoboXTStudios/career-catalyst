# Career Catalyst reconciliation review — 2026-09-13

Prepared for review only. No deployment, restart, push, live-checkout commit, runtime-data modification, or original-workspace cleanup was performed.

## Implementation lineage and preservation

Development clone: `/Users/trisha.lynch/Documents/career-catalyst-reconcile`.
Branch: `codex/reconcile-installed-and-astra-fixes`.
Base: `d06a32f2c2c491fa5da2af5aa40be5f187d816b9`.
Origin: `/Users/trisha.lynch/Library/Application Support/Career Catalyst/code` (local source; do not push to this origin).
The development revision hash is supplied with the final review response; this document is included in that revision.

The installed clone remains on `main` at that base commit. The Documents clone remains at `1adb8490b631084ca2f4bb9c79e8b7da57810607` on `codex/sprint-23-role-lens`. These are separate clones, not worktrees. Development shares the installed HEAD as its initial ancestor; the common ancestor with Documents is `158811124f30b6d3d64efeda4d4fba7ee8f5c9b1`.

The launcher configuration and submitted launchd service both point to the installed code path. Final read-only inspection found Python PID 1984 still listening on 127.0.0.1:8503 and the installed Git worktree clean. The installed runtime and export directories remain separate from code, under the same Application Support parent.

The Documents diff is mixed pre-existing work: tracked changes total +39,738/-602, primarily the application tracker (+39,490/-517), plus Evidence/capability data, generated dashboard HTML, and four intentionally edited source files. Untracked material includes backups, archives, quarantine, generated packages, job postings, reports, and the DOCX metadata helper/output-fidelity test. The earlier UI +58k/-1.7k display is not a reproducible Git tracked-diff total. It must not be treated as a single implementation patch. No original files were altered, cleaned, stashed, or copied wholesale.

## Selective port decisions

| Documents source/function considered | Installed equivalent and decision |
| --- | --- |
| `scripts/docx_metadata.py::clean_docx_metadata`; `scripts/export_docx.py::_export_docx` | Installed `scripts/docx_quality.py` already removes revisions, comments, custom XML, and generated metadata. Retained that stronger sanitizer and set Creator/Author and Last Modified By to Trisha Lynch. Did not introduce the parallel sanitizer. |
| `scripts/generate_cover_letter.py::_dynamic_cover_letter_content`, `_export_cover_letter_docx` | Retained installed explicit selected-Evidence grounding and shared DOCX sanitation. Ported output-fidelity intent through the corrected agency mandate opening and shared saved-posting scoring/writing context. |
| `scripts/tailor_resume.py::_select_core_competencies`, `_render_markdown`, `tailor_resume` | Retained installed source-grounded project bullets and artifact selection. Added selected-Evidence skills matching posting text and agency leadership competencies. Four manual records remain associated; résumé capacity remains three, as explicitly permitted in phases 3/4. Protected specialized music/experiential profiles. |
| `scripts/public_advocacy.py` claim-safety phrases | Removed candidate-facing stock disclaimers at installed `scripts/text_cleanup.py::normalize_candidate_text`. Kept source Evidence and factual grounding intact. Did not transplant the alternate advocacy module. |
| `tests/test_application_output_fidelity.py` | Recreated compatible assertions in `tests/test_astra_reconciliation.py`, including actual ATS/styled résumé and cover-letter DOCX content and author metadata. |
| September `scripts/prospect_intake.py` persisted JD/evaluation handoff; app intake saving | Ported saved JD/requirements and preservation of the displayed evaluation. No automatic tracker recovery or runtime migration. |
| September `scripts/package_generator.py` persisted description/context/preflight and transaction work | Ported authoritative saved-description handoff into context, scoring, and writers. Retained installed newer missing-posting, ownership, package-history, preflight, and transactional-generation protections. |
| September Evidence intelligence (`scripts/evidence_engine.py::rank_evidence_projects`, `candidate_positioning_narrative`, `job_requirement_coverage`, `seniority_erosion_warnings`; alternate `role_evidence_selection`/capability graph and UI) | Documents uses a divergent Evidence schema. Retained installed recommendation, relevance, artifact selection, coverage, and source-grounding mechanisms. Did not transplant this separate ranking/UI subsystem or its data; original work remains available in Documents. |

No runtime tracker/history, user Evidence data, exports, backups, archive, quarantine, or generated dashboards were ported. The new One Firefly fixture contains a posting excerpt, not a user application record. One absent tracked-baseline Evidence record is represented synthetically in the isolated tests.

## Astra changes

- Both intake and saved-file evaluation normalize the substantive posting separately from its serialization metadata. Saved description and verified metadata flow through Evidence saving and package writers.
- Each evaluation uses one loaded profile for its no-Evidence and adjusted calculations. Persisted provenance includes base, adjusted, delta, engine/input versions, posting/profile/Evidence-content fingerprints, evaluation date/ID, and predecessor reference. The already-adjusted tracker score cannot replace the baseline. Legacy scores have no invented historical delta; unavailable evaluations retain the saved score with an explicit unavailable contribution.
- Numeric contribution is distinct from semantic requirement support. Common words including not, people, them, and they cannot count as numeric Evidence keyword matches.
- Explicit marketing-agency identity outranks incidental automation. Director of Agency Operations resolves to marketing_advertising / business_operations. The existing general_operations archetype carries the delivery-leadership mandate; no new company/role taxonomy category was created.
- Throughput alone cannot activate the specialized marketing-integration action weight. Agency writing prioritizes people development, delivery workflows, quality/standards, capacity, technology enablement, and executive partnership.
- Shared manual-Evidence reconciliation removes selected identities from automatic suppression, including after material-editing rules are combined. Pre-generation plans expose résumé capacity three / letter capacity two and rank/capacity omission reasons. Final writers retain installed Evidence-grounding order.

Read-only evaluation with current runtime One Firefly data produced intake base 75, saved-file base 75, and selected-Evidence adjusted 77 (+2). The semantic exact-phrase result is empty, and the explanation correctly describes numeric keyword overlap. This does not claim a historical 82-to-77 change: the live stored score remains 82 and was not rewritten.

## Validation

Eleven new targeted regressions cover classification/mandate, input parity and common-word exclusion, evaluation save/reload/idempotence and legacy safety, manual precedence and capacities, honest numeric explanation, replacement-description handoff, actual final DOCX fidelity, disclaimer cleanup, intake evaluation preservation, Evidence content fingerprint changes, and employer-vs-client agency context.

The combined relevant group ran 156 tests: 155 passed; one older monkeypatch rejected the newly introduced keyword argument. The stub was updated to assert the authoritative saved description and title are passed, and its entire 23-test module passed on rerun. Thus all 156 tests are covered by passing results across these runs. No production code changed after the combined run. Earlier targeted/related groups also passed; the full repository suite was not run.

Combined command (in development clone):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q \
  tests/test_astra_reconciliation.py tests/test_score_match.py \
  tests/test_dynamic_role_intelligence.py tests/test_sprint39_1_package_score_context.py \
  tests/test_sprint31_1_evidence_tailoring_integration.py \
  tests/test_final_role_intelligence_material_quality.py \
  tests/test_hotfix_selected_evidence_provenance.py \
  tests/test_sprint35_package_scoring_reliability.py \
  tests/test_sprint36_role_intelligence_overrides.py \
  tests/test_parse_job.py tests/test_export_docx.py \
  tests/test_sprint38_5_reparse_state_consistency.py \
  tests/test_golden_resume_v2.py tests/test_sprint42_production_consolidation.py \
  -p no:cacheprovider
```

Affected-module rerun:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q \
  tests/test_sprint31_1_evidence_tailoring_integration.py -p no:cacheprovider
```

`git diff --check` passes. Tests used isolated temporary roots. No package generation ran against live runtime data.

## Remaining limits

- Input normalization intentionally changes scores; old records are not bulk-migrated. New evaluation dates/profile or Evidence edits can change future results.
- Semantic support remains a conservative exact-phrase diagnostic, while numeric scoring retains meaningful keyword overlap. A positive numeric delta does not prove the full hiring requirement.
- Agency mandate recognition is deliberately narrow and title/context based; it is not a general semantic classifier.
- Provenance references previous evaluations but does not introduce a separate immutable history ledger.
- Actual DOCX text/XML and package checks passed. No interactive live-app walkthrough or visual page-by-page layout review was performed, because deployment and live regeneration remain outside this phase.
- The full suite and unrelated divergent Documents Evidence-intelligence features remain outside this bounded sprint.

## Proposed deployment — only after explicit approval

Deploy the reviewed commit by a local fetch and fast-forward of the installed clone. Do not copy directories or change launcher/runtime/export paths. Do not merge Documents or push to any remote. If the installed HEAD, cleanliness, or launcher configuration has changed, stop and reconcile first.

1. Pin `reviewed_revision` to the exact development commit supplied in the final response. Recheck installed main is clean at d06a32f2c2c491fa5da2af5aa40be5f187d816b9, development is clean, and the service/config still target the known roots. Retain that base hash for rollback review.
2. Fetch the development branch locally into the installed clone; verify FETCH_HEAD equals the approved hash, the base is its ancestor, and its changed-path list is exactly this review's source/config/tests/document list. Inspect this before stopping the service.
3. Stop the submitted launchd job with `launchctl remove com.roboxtstudios.careercatalyst.8503`; confirm port 8503 is free. This is a submitted job, not an on-disk LaunchAgents plist.
4. Fast-forward the installed code to the pinned revision using `git merge --ff-only`. No data copy or migration.
5. Invoke the existing installed launcher, which recreates the submitted service with its existing configuration; verify the port, code path, Git HEAD, health endpoint, and an initial read-only UI view. Saving Evidence or regenerating an application is a separate explicit action, not an automatic deployment step.

Commands for the approved maintenance window (the revision assignment must contain the reviewed hash, not a moving branch):

```sh
cc_live='/Users/trisha.lynch/Library/Application Support/Career Catalyst/code'
cc_dev='/Users/trisha.lynch/Documents/career-catalyst-reconcile'
reviewed_revision='<exact hash from final review>'
git -C "$cc_live" fetch "$cc_dev" codex/reconcile-installed-and-astra-fixes
test "$(git -C "$cc_live" rev-parse FETCH_HEAD)" = "$reviewed_revision"
git -C "$cc_live" merge-base --is-ancestor d06a32f2c2c491fa5da2af5aa40be5f187d816b9 "$reviewed_revision"
git -C "$cc_live" diff --name-status d06a32f2c2c491fa5da2af5aa40be5f187d816b9 "$reviewed_revision"
# Proceed only after the preceding guards and changed-path review pass.
launchctl remove com.roboxtstudios.careercatalyst.8503
# Confirm no listener before updating code.
git -C "$cc_live" merge --ff-only "$reviewed_revision"
/bin/bash '/Users/trisha.lynch/Library/Application Support/Career Catalyst/launch_career_catalyst.sh'
curl -fsS http://127.0.0.1:8503/_stcore/health
```

These commands are a reviewed proposal, not executed deployment. Run guarded steps individually and stop on any failure.

## Complete changed-file list

- `RECONCILIATION_REVIEW.md`
- `app.py`
- `config/role_intent_rules.yml`
- `scripts/application_tracker.py`
- `scripts/candidate_output.py`
- `scripts/docx_quality.py`
- `scripts/dynamic_role_intelligence.py`
- `scripts/evidence_tailoring.py`
- `scripts/generate_cover_letter.py`
- `scripts/package_generator.py`
- `scripts/parse_job.py`
- `scripts/prospect_intake.py`
- `scripts/role_editing.py`
- `scripts/role_intent.py`
- `scripts/score_match.py`
- `scripts/tailor_resume.py`
- `scripts/text_cleanup.py`
- `tests/fixtures/jobs/one_firefly_agency_operations.md`
- `tests/test_astra_reconciliation.py`
- `tests/test_sprint31_1_evidence_tailoring_integration.py`
- `tests/test_sprint38_5_reparse_state_consistency.py`
- `tests/test_sprint39_1_package_score_context.py`
- `tests/test_sprint42_production_consolidation.py`
