"""Deterministic, candidate-safe use of prospect-scoped Evidence projects."""

from __future__ import annotations

from copy import deepcopy

import hashlib
import json
import re
from typing import Any, Mapping, Sequence


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "into", "is", "it", "of", "on", "or", "role", "that", "the", "their",
    "this", "to", "was", "were", "will", "with",
}

GENERIC_EVIDENCE_TERMS = {
    "leadership",
    "management",
    "operations",
    "priorities",
    "strategy",
}

ARTIFACT_CAPACITIES = {
    "ats_resume": 4,
    "styled_resume": 4,
    "cover_letter": 2,
}

ARTIFACT_LABELS = {
    "ats_resume": "ATS resume",
    "styled_resume": "styled resume",
    "cover_letter": "cover letter",
}


def project_title(project: Mapping[str, Any]) -> str:
    return str(project.get("title") or project.get("name") or "Untitled Evidence").strip()


def _candidate_project_records(context: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return known project records without changing source Evidence."""
    data = (context.get("career_data") or {}).get("data", {})
    records: list[Mapping[str, Any]] = [
        item
        for item in (context.get("associated_evidence_projects") or [])
        if isinstance(item, Mapping)
    ]
    for section, key in (("projects", "projects"), ("evidence_projects", "evidence_projects")):
        values = data.get(section, {})
        if isinstance(values, Mapping):
            values = values.get(key, [])
        if isinstance(values, list):
            records.extend(item for item in values if isinstance(item, Mapping))
    return records


def artifact_allowed_project_ids(
    context: Mapping[str, Any], artifact_type: str
) -> set[str]:
    """Resolve the exact project IDs authorized for one candidate artifact."""
    associated = list(context.get("associated_evidence_projects") or [])
    decision_key = {
        "ats_resume": "resume_evidence_selection",
        "styled_resume": "resume_evidence_selection",
        "cover_letter": "cover_letter_evidence_selection",
    }.get(artifact_type)
    decision = context.get(decision_key) if decision_key else None
    if not isinstance(decision, Mapping):
        return {_project_id(project) for project in associated}
    allowed: set[str] = set()
    for entry in [*(decision.get("used_projects") or []), *(decision.get("fallback_used") or [])]:
        project = entry.get("_project") if isinstance(entry, Mapping) else None
        allowed.add(_project_id(project or entry))
    return {value for value in allowed if value}


def candidate_project_reference_violations(
    text: str, context: Mapping[str, Any], artifact_type: str
) -> list[str]:
    """Find known unselected project names in candidate-facing text.

    This is intentionally a final provenance check. It only blocks a known
    project reference that is not authorized for the artifact; ordinary prose
    and source Evidence titles are not rewritten.
    """
    if not context.get("evidence_scope_enforced"):
        # Preserve compatibility for direct legacy builder callers that do not
        # provide a non-empty tracker-selected Evidence pool. Legacy packages
        # without a tracker selection retain their system-recommended behavior.
        return []

    try:
        from .text_cleanup import normalize_candidate_text
    except ImportError:
        from text_cleanup import normalize_candidate_text

    normalized = normalize_candidate_text(text).lower()
    allowed = artifact_allowed_project_ids(context, artifact_type)
    known_projects = _candidate_project_records(context)
    # Some preserved records predate the canonical Evidence IDs. Treat a
    # recognized project identity as selected when any of its stable legacy or
    # canonical records is selected; this prevents a short public name such as
    # "Career Catalyst" from being mistaken for an unselected project merely
    # because the tracker retains its older ID.
    allowed_kinds = {
        project_kind(project)
        for project in known_projects
        if _project_id(project) in allowed
        and project_kind(project) in {"career_catalyst", "campaignos", "roboxt_studios", "podcast"}
    }
    aliases: dict[str, set[str]] = {}
    alias_kinds: dict[str, set[str]] = {}
    for project in known_projects:
        project_id = _project_id(project)
        if not project_id:
            continue
        for raw in (project.get("id"), project.get("title"), project.get("name")):
            for alias in {
                str(raw or "").strip().lower(),
                normalize_candidate_text(str(raw or "")).strip().lower(),
            }:
                if len(alias) >= 4:
                    aliases.setdefault(alias, set()).add(project_id)
                    alias_kinds.setdefault(alias, set()).add(project_kind(project))
        human_id = normalize_candidate_text(project_id.replace("_", " ")).strip().lower()
        if len(human_id) >= 4:
            aliases.setdefault(human_id, set()).add(project_id)
            alias_kinds.setdefault(human_id, set()).add(project_kind(project))
    violations = [
        alias
        for alias, project_ids in sorted(aliases.items(), key=lambda item: -len(item[0]))
        if not (project_ids & allowed)
        and not (alias_kinds.get(alias, set()) & allowed_kinds)
        and alias in normalized
    ]
    return list(dict.fromkeys(violations))


def project_kind(project: Mapping[str, Any]) -> str:
    identity = " ".join(
        str(project.get(key) or "") for key in ("id", "title", "name")
    ).lower()
    if "career catalyst" in identity or "career_catalyst" in identity:
        return "career_catalyst"
    if "campaignos" in identity:
        return "campaignos"
    if "roboxt studios" in identity or "roboxt_studios" in identity:
        return "roboxt_studios"
    if "multiverse" in identity:
        return "multiverse"
    if "just for us" in identity or "podcast" in identity:
        return "podcast"
    return "other"


def _flatten(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _flatten(nested)]
    if isinstance(value, (list, tuple, set)):
        return [item for nested in value for item in _flatten(nested)]
    return [str(value)] if value not in (None, "") else []


def _terms(value: Any) -> set[str]:
    words = re.findall(r"[a-z0-9]+", " ".join(_flatten(value)).lower())
    return {word for word in words if len(word) > 2 and word not in STOP_WORDS}


def role_text(parsed_job: Mapping[str, Any]) -> str:
    return " ".join(
        _flatten(
            [
                parsed_job.get("job_title"),
                parsed_job.get("role"),
                parsed_job.get("raw_text"),
                parsed_job.get("job_description"),
                parsed_job.get("responsibilities"),
                parsed_job.get("qualifications"),
                parsed_job.get("keywords"),
            ]
        )
    ).lower()


def is_music_partnerships_role(parsed_job: Mapping[str, Any]) -> bool:
    """Return whether direct music/audio release Evidence should lead."""
    text = role_text(parsed_job)
    return bool(
        re.search(
            r"\b(label relations|music partnerships?|music content|audio|creator|artists?|"
            r"streaming platform)\b",
            text,
        )
    )


def evidence_relevance(
    project: Mapping[str, Any], parsed_job: Mapping[str, Any]
) -> dict[str, Any]:
    """Return unique, posting-grounded Evidence matches without title repetition."""
    posting_terms = _terms(role_text(parsed_job))
    evidence_terms = _terms(
        [
            project.get("title"),
            project.get("problem"),
            project.get("actions"),
            project.get("results"),
            project.get("function"),
            project.get("project_type"),
            project.get("skills"),
            project.get("technologies"),
            project.get("tags"),
            project.get("atomic_evidence"),
        ]
    )
    matched = sorted(posting_terms & evidence_terms)
    specific_matches = [term for term in matched if term not in GENERIC_EVIDENCE_TERMS]
    text = role_text(parsed_job)
    kind = project_kind(project)
    phrase_matches: list[str] = []
    if kind == "career_catalyst" and re.search(
        r"\b(product manager|product strategy|product operations|product requirements|roadmap)\b",
        text,
    ):
        phrase_matches.append("product development")
    priority_bonus = 0
    if kind == "podcast" and (
        is_music_partnerships_role(parsed_job)
        or any(
            phrase in text
            for phrase in ("podcast", "emerging format", "audio", "content lifecycle")
        )
    ):
        phrase_matches.append("direct music/audio release experience")
        priority_bonus = 6 if is_music_partnerships_role(parsed_job) else 0
    matched_signals = list(dict.fromkeys([*phrase_matches, *matched]))
    return {
        "score": len(matched) + (3 * len(phrase_matches)) + priority_bonus,
        "specific_score": len(specific_matches) + (3 * len(phrase_matches)) + priority_bonus,
        "matched_signals": matched_signals[:10],
    }


def relevant_selected_evidence(
    projects: Sequence[Mapping[str, Any]],
    parsed_job: Mapping[str, Any],
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, project in enumerate(projects):
        relevance = evidence_relevance(project, parsed_job)
        if int(relevance["score"]) <= 0:
            continue
        item = dict(project)
        item["_tailoring_relevance"] = relevance
        ranked.append((int(relevance["score"]), index, item))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item for _score, _index, item in ranked[: max(0, limit)]]


def _project_id(project: Mapping[str, Any]) -> str:
    return str(project.get("id") or project_title(project)).strip()


def deduplicate_evidence_projects(
    projects: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate recommendations by stable Evidence ID, preserving order."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for project in projects:
        identity = _project_id(project)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        result.append(dict(project))
    return result


def recommend_evidence_ids(
    parsed_job: Mapping[str, Any],
    projects: Sequence[Mapping[str, Any]],
    *,
    limit: int = 3,
) -> list[str]:
    """Return deterministic, role-aware suggestions without changing selection."""
    unique = deduplicate_evidence_projects(projects)
    text = role_text(parsed_job)
    preferred: list[str] = []
    if "label relations" in text or ("music partnerships" in text and "label" in text):
        preferred = [
            "just_for_us_podcast",
            "roboxt_studios",
            "enterprise_media_operations_transformation",
        ]
    elif "sales strategy" in text or "sales operations" in text or "revenue operations" in text:
        preferred = [
            "enterprise_media_operations_transformation",
            "career_catalyst",
            "disney_plus_launch_readiness",
        ]
    available = {_project_id(project): project for project in unique}
    ordered = [identity for identity in preferred if identity in available]
    if len(ordered) < limit:
        ranked = relevant_selected_evidence(unique, parsed_job, limit=len(unique))
        ordered.extend(
            identity
            for project in ranked
            if (identity := _project_id(project)) not in ordered
        )
    return ordered[: max(0, limit)]


def _verified_detail(project: Mapping[str, Any]) -> bool:
    return bool(
        _flatten(
            [
                project.get("actions"),
                project.get("results"),
                project.get("candidate_facing_bullet"),
                project.get("highlights"),
            ]
        )
    )


def _artifact_suitability(project: Mapping[str, Any], artifact_type: str) -> int:
    detail = _flatten(
        [
            project.get("actions"),
            project.get("results"),
            project.get("candidate_facing_bullet"),
            project.get("highlights"),
            project.get("atomic_evidence"),
        ]
    )
    if not detail:
        return 0
    if artifact_type == "cover_letter":
        return 2 if project.get("actions") and project.get("results") else 1
    return 2 if len(detail) >= 2 else 1


def _selection_entry(
    project: Mapping[str, Any],
    *,
    relevance: Mapping[str, Any],
    user_order: int,
    suitability: int,
    source: str,
) -> dict[str, Any]:
    return {
        "id": _project_id(project),
        "title": project_title(project),
        "source": source,
        "user_order": user_order,
        "relevance_score": int(relevance.get("score") or 0),
        "matched_signals": list(relevance.get("matched_signals") or []),
        "artifact_suitability": suitability,
        "_project": dict(project),
    }


def _redundancy_ratio(
    entry: Mapping[str, Any], selected: Sequence[Mapping[str, Any]]
) -> float:
    signals = {str(value).lower() for value in entry.get("matched_signals") or []}
    if not signals or not selected:
        return 0.0
    return max(
        len(
            signals
            & {str(value).lower() for value in prior.get("matched_signals") or []}
        )
        / len(signals)
        for prior in selected
    )


def public_artifact_selection(selection: Mapping[str, Any]) -> dict[str, Any]:
    """Return the persisted, candidate-safe portion of one artifact decision."""

    def public_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in entry.items()
            if key != "_project"
        }

    return {
        "artifact_type": selection.get("artifact_type"),
        "artifact_label": selection.get("artifact_label"),
        "capacity": selection.get("capacity"),
        "selected_ids": list(selection.get("selected_ids") or []),
        "eligible": [public_entry(item) for item in selection.get("eligible") or []],
        "ranked": [public_entry(item) for item in selection.get("ranked") or []],
        "used": [public_entry(item) for item in selection.get("used") or []],
        "omitted": [public_entry(item) for item in selection.get("omitted") or []],
        "fallback_used": [
            public_entry(item) for item in selection.get("fallback_used") or []
        ],
    }


def select_evidence_for_artifact(
    parsed_job: Mapping[str, Any],
    selected_projects: Sequence[Mapping[str, Any]],
    *,
    artifact_type: str,
    capacity: int | None = None,
    fallback_projects: Sequence[Mapping[str, Any]] = (),
    minimum_selected: int = 0,
) -> dict[str, Any]:
    """Rank one authoritative selected-Evidence pool for a specific artifact.

    Selected records are always evaluated before unselected fallbacks.  Every
    selected record is returned as either used or omitted with a concrete reason.
    """
    resolved_capacity = max(
        0, int(capacity if capacity is not None else ARTIFACT_CAPACITIES.get(artifact_type, 3))
    )
    ranked: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    for index, project in enumerate(selected_projects):
        relevance = evidence_relevance(project, parsed_job)
        suitability = _artifact_suitability(project, artifact_type)
        entry = _selection_entry(
            project,
            relevance=relevance,
            user_order=index,
            suitability=suitability,
            source="selected",
        )
        if (
            artifact_type == "cover_letter"
            and project_kind(project) == "career_catalyst"
            and int(relevance.get("specific_score") or 0) <= 0
        ):
            omitted.append(
                {
                    **entry,
                    "reason": "Better suited to another artifact; this posting lacks a direct product or AI connection.",
                }
            )
            continue
        if not _verified_detail(project):
            omitted.append({**entry, "reason": "Insufficient verified detail for this artifact."})
            continue
        if int(relevance.get("score") or 0) <= 0:
            omitted.append(
                {
                    **entry,
                    "reason": "Lower role relevance than the Evidence used for this artifact.",
                }
            )
            continue
        ranked.append(entry)
    ranked.sort(
        key=lambda item: (
            -int(item["relevance_score"]),
            -int(item["artifact_suitability"]),
            int(item["user_order"]),
        )
    )
    remaining = list(ranked)
    used: list[dict[str, Any]] = []
    while remaining and len(used) < resolved_capacity:
        remaining.sort(
            key=lambda item: (
                -(
                    int(item["relevance_score"])
                    - (2 if _redundancy_ratio(item, used) >= 0.75 else 0)
                ),
                -int(item["artifact_suitability"]),
                int(item["user_order"]),
            )
        )
        used.append(remaining.pop(0))
    ranked = [*used, *remaining]
    for entry in remaining:
        redundancy = _redundancy_ratio(entry, used)
        omitted.append(
            {
                **entry,
                "reason": (
                    "Redundant with stronger selected Evidence already used in this artifact."
                    if redundancy >= 0.75
                    else (
                        f"Space limit: ranked below the top {resolved_capacity} selected Evidence "
                        f"record{'s' if resolved_capacity != 1 else ''} for this "
                        f"{ARTIFACT_LABELS.get(artifact_type, artifact_type)}."
                    )
                ),
            }
        )

    fallback_used: list[dict[str, Any]] = []
    fallback_slots = min(
        max(0, resolved_capacity - len(used)),
        max(0, int(minimum_selected) - len(used)),
    )
    if fallback_slots:
        selected_ids = {_project_id(project) for project in selected_projects}
        fallback_ranked: list[dict[str, Any]] = []
        for index, project in enumerate(fallback_projects):
            if _project_id(project) in selected_ids or not _verified_detail(project):
                continue
            relevance = evidence_relevance(project, parsed_job)
            if int(relevance.get("score") or 0) <= 0:
                continue
            fallback_ranked.append(
                _selection_entry(
                    project,
                    relevance=relevance,
                    user_order=index,
                    suitability=_artifact_suitability(project, artifact_type),
                    source="unselected_fallback",
                )
            )
        fallback_ranked.sort(
            key=lambda item: (
                -int(item["relevance_score"]),
                -int(item["artifact_suitability"]),
                int(item["user_order"]),
            )
        )
        fallback_used = fallback_ranked[:fallback_slots]
        used.extend(fallback_used)

    omitted_by_id = {_project_id(item.get("_project") or item): item for item in omitted}
    omitted = [
        omitted_by_id[_project_id(project)]
        for project in selected_projects
        if _project_id(project) in omitted_by_id
    ]
    return {
        "artifact_type": artifact_type,
        "artifact_label": ARTIFACT_LABELS.get(artifact_type, artifact_type),
        "capacity": resolved_capacity,
        "selected_ids": [_project_id(project) for project in selected_projects],
        "eligible": list(ranked),
        "ranked": list(ranked),
        "used": used,
        "used_projects": [dict(item["_project"]) for item in used],
        "omitted": omitted,
        "fallback_used": fallback_used,
    }


def _first_sentence(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return next(
            (
                sentence
                for item in value
                if (sentence := _first_sentence(item))
            ),
            "",
        )
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    match = re.match(r"(.+?[.!?])(?:\s|$)", text)
    return (match.group(1) if match else text).strip()


def resume_project_bullets(
    project: Mapping[str, Any], parsed_job: Mapping[str, Any]
) -> list[str]:
    """Condense verified Evidence into one or two complete candidate-facing bullets."""
    corpus = " ".join(
        _flatten([
            project.get("problem"), project.get("actions"), project.get("results"),
            project.get("atomic_evidence"),
        ])
    ).lower()
    kind = project_kind(project)
    if kind == "career_catalyst" and "product" in corpus:
        return [
            "Created and led development of an active AI-enabled career intelligence and application-operations product, defining product vision, requirements, priorities, workflows, acceptance criteria, and release guardrails.",
            "Built and iterated a tested local application integrating prospect evaluation, evidence selection, tailored materials, follow-up planning, interview preparation, status management, and role archiving.",
        ]
    if kind == "podcast" and re.search(r"\b(ten|10)[ -]episode", corpus):
        return [
            "Served as audio producer and editor for a ten-episode, multi-host podcast series released on Spotify, managing dialogue editing, pacing, audio quality, revisions, quality control, and release-ready delivery."
        ]
    child_claims = [
        _first_sentence(item.get("canonical_claim"))
        for item in project.get("atomic_evidence") or []
        if isinstance(item, Mapping) and item.get("candidate_facing_allowed") is not False
    ]
    bullets = [
        sentence
        for sentence in (
            _first_sentence(project.get("actions")),
            _first_sentence(project.get("results")),
            *child_claims,
        )
        if sentence
    ]
    return list(dict.fromkeys(bullets))[:2]


def cover_letter_project_paragraph(
    project: Mapping[str, Any], parsed_job: Mapping[str, Any]
) -> str:
    kind = project_kind(project)
    corpus = " ".join(_flatten(project)).lower()
    if kind == "career_catalyst" and "product" in corpus:
        return (
            "Career Catalyst is a current, hands-on proof point: I am actively developing an AI-enabled "
            "career intelligence and application-operations product. I translate user needs into product "
            "vision, requirements, feature priorities, workflows, acceptance criteria, iterative testing, "
            "and release guardrails, work that connects product judgment with disciplined delivery."
        )
    if kind == "podcast" and re.search(r"\b(ten|10)[ -]episode", corpus):
        return (
            "I also served as audio producer and editor for Just for Us, a ten-episode, multi-host podcast "
            "series released on Spotify. I shaped pacing and episode flow, cleaned and balanced dialogue, "
            "managed revisions and quality control, and prepared each episode for release."
        )
    actions = _first_sentence(project.get("actions"))
    result = _first_sentence(project.get("results"))
    if not actions:
        return ""
    explicit_subject = re.compile(r"^(?:I|We|This|That|The|My)\b", flags=re.IGNORECASE)
    if not explicit_subject.search(actions):
        actions = "I " + actions[:1].lower() + actions[1:]
    if result and result != actions and not explicit_subject.search(result):
        result = "This work " + result[:1].lower() + result[1:]
    proof = f" {result}" if result and result != actions else ""
    return f"{actions}{proof}"


def reconcile_manual_evidence(role_intent: Mapping[str, Any], projects: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Resolve manual identity precedence before any automatic guidance is consumed."""
    resolved = deepcopy(dict(role_intent))
    selected = [dict(project) for project in projects]
    aliases = {
        " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))
        for project in selected for value in (project.get("id"), project.get("title"), project.get("name"))
        if value
    }
    kinds = {project_kind(project) for project in selected} - {"other"}
    def selected_identity(value: Any) -> bool:
        identity = " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))
        return identity in aliases or project_kind({"id": value}) in kinds
    resolved["suppressed_evidence"] = [
        value for value in resolved.get("suppressed_evidence", []) if not selected_identity(value)
    ]
    resolved["manual_evidence_projects"] = selected
    return resolved


def evidence_score_contribution(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    if after.get("evaluation_unavailable"):
        return {"before": None, "after": after.get("match_score"), "delta": None,
                "matched_requirements": [], "explanation": "Saved score retained; a current Evidence evaluation is unavailable."}
    before_score = int(before.get("match_score") or 0)
    after_score = int(after.get("match_score") or 0)
    details = after.get("associated_evidence_match_details")
    matched = list(details if isinstance(details, list) else after.get("associated_evidence_matches") or [])
    noise = {"more", "than", "cross-functional", "cross functional"}
    matched = [value for value in matched if str(value).strip().lower() not in noise]
    if not matched and after_score != before_score:
        explanation = "Numeric contribution reflects keyword overlap; no substantive requirement matches were identified."
    elif not matched:
        explanation = "No additional role requirements were matched by the selected Evidence."
    elif after_score == before_score:
        explanation = (
            "Selected Evidence matched relevant role requirements but did not change the overall score."
        )
    else:
        explanation = "Selected Evidence matched additional verified role requirements."
    return {
        "before": before_score,
        "after": after_score,
        "delta": after_score - before_score,
        "matched_requirements": matched,
        "explanation": explanation,
    }


def output_use_metadata(
    selected_projects: Sequence[Mapping[str, Any]],
    *,
    system_recommended_projects: Sequence[str] = (),
    resume_projects_used: Sequence[str] = (),
    cover_letter_projects_used: Sequence[str] = (),
    score_contribution: Mapping[str, Any] | None = None,
    parsed_job: Mapping[str, Any] | None = None,
    artifact_selections: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    parsed = parsed_job or {}
    resume_used = list(dict.fromkeys(str(value) for value in resume_projects_used if value))
    cover_used = list(dict.fromkeys(str(value) for value in cover_letter_projects_used if value))
    public_selections = {
        key: public_artifact_selection(value)
        for key, value in (artifact_selections or {}).items()
    }
    if public_selections:
        resume_used = list(
            dict.fromkeys(
                item["title"]
                for key in ("ats_resume", "styled_resume")
                for item in public_selections.get(key, {}).get("used", [])
                if item.get("source") == "selected"
            )
        )
        cover_used = [
            item["title"]
            for item in public_selections.get("cover_letter", {}).get("used", [])
            if item.get("source") == "selected"
        ]
    used = set(resume_used) | set(cover_used)
    used_selected_ids = {
        str(item.get("id") or "")
        for selection in public_selections.values()
        for item in selection.get("used", [])
        if item.get("source") == "selected" and item.get("id")
    }
    selected = []
    not_used = []
    for project in selected_projects:
        title = project_title(project)
        evidence_id = str(project.get("id") or "")
        relevance = evidence_relevance(project, parsed)
        selected.append(
            {
                "id": evidence_id,
                "title": title,
                "manual": True,
                "relevance_score": int(relevance["score"]),
                "matched_signals": list(relevance["matched_signals"]),
            }
        )
        project_was_used = (
            evidence_id in used_selected_ids
            if public_selections
            else title in used
        )
        if not project_was_used:
            artifact_reasons = [
                item.get("reason")
                for selection in public_selections.values()
                for item in selection.get("omitted", [])
                if item.get("id") == str(project.get("id") or "") and item.get("reason")
            ]
            not_used.append(
                {
                    "id": str(project.get("id") or ""),
                    "title": title,
                    "reason": artifact_reasons[0] if artifact_reasons else "No sufficiently specific role connection was found in the verified record.",
                }
            )
    fallback_used = list(
        {
            (item.get("id"), item.get("title")): item
            for selection in public_selections.values()
            for item in selection.get("fallback_used", [])
        }.values()
    )
    return {
        "selected_evidence": selected,
        "selected_count": len(selected),
        "used_anywhere_count": (
            len(used_selected_ids) if public_selections else len(used)
        ),
        "omitted_from_package_count": len(not_used),
        "system_recommended_projects": list(
            dict.fromkeys(str(value) for value in system_recommended_projects if value)
        ),
        "resume_projects_used": resume_used,
        "cover_letter_projects_used": cover_used,
        "projects_not_used": not_used,
        "artifact_usage": public_selections,
        "unselected_fallback_used": fallback_used,
        "evidence_score_contribution": dict(score_contribution or {}),
    }


def package_preview_fingerprint(
    prospect_id: str, evidence_project_ids: Sequence[Any]
) -> str:
    payload = {
        "prospect_id": str(prospect_id or "").strip(),
        "evidence_project_ids": [
            str(value).strip() for value in evidence_project_ids if str(value).strip()
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
