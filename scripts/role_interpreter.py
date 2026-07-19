"""Plain-English, responsibility-led job interpretation.

The interpreter is deliberately deterministic: it separates concrete duties from
posting boilerplate, classifies the work from those duties, and records every
inference that should be verified before fit scoring.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable


GENERIC_POSTING_PHRASES = (
    "cross-functional",
    "strategic thinker",
    "results-oriented",
    "results driven",
    "fast-paced",
    "stakeholder management",
    "operational excellence",
    "drive alignment",
    "influence without authority",
    "ambiguous environment",
    "executive presence",
    "excellent communication",
    "self-starter",
)


ARCHETYPE_SIGNALS: dict[str, dict[str, tuple[str, ...]]] = {
    "General Business Operations": {
        "title": (
            "business operations", "operations manager", "director of operations",
            "matrix operations", "organizational efficiency",
        ),
        "duties": (
            "business operations", "operating cadence", "capacity planning",
            "business performance", "operational reporting", "organizational systems",
            "organizational design", "organizational clarity", "staffing plan",
            "capacity matches demand",
        ),
    },
    "Strategic Operations": {
        "title": ("strategic operations", "strategy and operations"),
        "duties": ("strategic initiatives", "business planning", "decision support", "executive priorities", "operating plan"),
    },
    "Product Operations": {
        "title": ("product operations",),
        "duties": ("launch readiness", "product feedback", "product process", "product adoption", "release process", "product governance", "product and engineering", "launch enablement"),
    },
    "Product Management": {
        "title": ("product manager", "product management"),
        "duties": ("own the roadmap", "product roadmap", "prioritize features", "product requirements", "user research", "product vision", "define requirements", "product decisions"),
    },
    "Program / Project Management": {
        "title": ("program manager", "project manager", "pmo"),
        "duties": ("project plan", "program plan", "milestones", "dependencies", "project coordination", "program governance", "status reporting", "delivery timeline"),
    },
    "Technical Program Management": {
        "title": ("technical program manager", "technical program management"),
        "duties": ("technical program", "engineering dependencies", "technical delivery", "system architecture", "software delivery", "engineering roadmap"),
    },
    "Technical Solutions / Solutions Consulting": {
        "title": ("technical solutions", "solutions consultant", "solutions consulting"),
        "duties": (
            "technical solutions", "technical consultation", "technical troubleshooting",
            "client solutions", "solution design", "technical escalations",
            "advertiser solutions", "technical support", "technical blockers",
            "client technical challenges", "issue resolution", "technical execution",
        ),
    },
    "Implementation / Onboarding": {
        "title": ("implementation", "onboarding"),
        "duties": (
            "implementation plan", "customer onboarding", "configure the platform",
            "go live", "customer deployment", "platform deployment",
            "integration project", "implementation support",
        ),
    },
    "Customer Success": {
        "title": ("customer success", "client success"),
        "duties": ("customer retention", "customer adoption", "renewals", "customer health", "success plan", "customer outcomes"),
    },
    "Revenue Operations": {
        "title": ("revenue operations", "sales operations"),
        "duties": ("sales forecasting", "revenue forecasting", "pipeline management", "salesforce administration", "territory planning", "quota planning", "sales process", "deal desk"),
    },
    "Marketing Operations": {
        "title": ("marketing operations",),
        "duties": ("campaign operations", "marketing automation", "lead routing", "campaign execution", "marketing performance", "marketing workflow"),
    },
    "Marketing Technology": {
        "title": ("marketing technology", "martech"),
        "duties": ("martech", "marketing technology", "marketing platform", "marketing systems", "crm integration", "marketing stack"),
    },
    "Advertising Technology / Ad Operations": {
        "title": ("ad operations", "advertising technology", "ad tech"),
        "duties": ("programmatic", "campaign delivery", "ad serving", "pixels", "pixel implementation", "sdk", "conversions api", "ads api", "measurement integration", "advertiser troubleshooting", "campaign troubleshooting"),
    },
    "Data / Analytics Operations": {
        "title": ("analytics operations", "data operations"),
        "duties": ("data governance", "data quality", "analytics operations", "reporting pipeline", "experimentation framework", "measurement framework", "business intelligence"),
    },
    "People Operations": {
        "title": ("people operations", "human resources", "hr operations"),
        "duties": ("employee lifecycle", "employee relations", "workforce planning", "hris", "benefits administration", "people policies", "talent acquisition", "performance management"),
    },
    "Chief of Staff": {
        "title": ("chief of staff",),
        "duties": ("executive priorities", "leadership cadence", "decision support", "board materials", "office of the ceo", "chief executive", "leadership team", "executive briefings"),
    },
    "Transformation / Operational Excellence": {
        "title": ("transformation", "operational excellence", "continuous improvement"),
        "duties": ("process redesign", "continuous improvement", "operating model", "change adoption", "business transformation", "lean six sigma"),
    },
    "Sales Engineering": {
        "title": ("sales engineer", "solutions engineer", "sales engineering"),
        "duties": ("technical pre-sales", "product demonstration", "proof of concept", "sales cycle", "technical discovery", "solutions engineers", "technical win"),
    },
    "Engineering Management": {
        "title": ("engineering manager", "director of engineering"),
        "duties": ("manage engineers", "software engineers", "engineering team", "code review", "software architecture", "engineering delivery"),
    },
    "Creative Operations": {
        "title": ("creative operations",),
        "duties": ("creative workflow", "creative production", "creative assets", "creative resourcing", "agency roster", "studio operations"),
    },
    "Content Operations": {
        "title": ("content operations",),
        "duties": ("content workflow", "content publishing", "editorial operations", "content moderation", "content production", "content supply chain"),
    },
}

ROLE_ARCHETYPES = tuple(ARCHETYPE_SIGNALS)


ARCHETYPE_GUIDANCE = {
    "General Business Operations": ("run the operating processes that keep the business coordinated", "a broad business operator"),
    "Strategic Operations": ("turn leadership priorities into analysis, decisions, and coordinated execution", "a strategic operator who can move between analysis and follow-through"),
    "Product Operations": ("make product planning, launches, feedback, and operating processes work consistently", "a product-facing operator, not necessarily the person deciding the roadmap"),
    "Product Management": ("decide what the product should solve and guide roadmap and feature priorities", "a product decision-maker who can translate user needs into priorities"),
    "Program / Project Management": ("coordinate plans, owners, milestones, risks, and delivery", "a delivery leader who creates accountability across teams"),
    "Technical Program Management": ("coordinate complex technical delivery across engineering teams and dependencies", "a technically credible program leader"),
    "Technical Solutions / Solutions Consulting": ("make a technical product usable for customers and resolve difficult implementation problems", "a technical client-solutions leader who translates between customers, sales, product, and engineering"),
    "Implementation / Onboarding": ("get customers configured, integrated, and live on the product", "an implementation leader who can manage both customer expectations and technical dependencies"),
    "Customer Success": ("help customers adopt the product, realize value, and remain successful", "a customer outcome owner with strong relationship and adoption skills"),
    "Revenue Operations": ("make the sales and revenue system measurable, predictable, and scalable", "a revenue-process operator with forecasting and systems fluency"),
    "Marketing Operations": ("make campaigns, workflows, data, and marketing execution run reliably", "a marketing operator with process and platform fluency"),
    "Marketing Technology": ("own and connect the systems that enable marketing execution and measurement", "a marketing-technology owner who can bridge business requirements and platforms"),
    "Advertising Technology / Ad Operations": ("make advertising delivery, integrations, and measurement work reliably", "an ad-tech operator with hands-on campaign and measurement troubleshooting credibility"),
    "Data / Analytics Operations": ("make data, measurement, reporting, and analytical workflows trustworthy and usable", "an analytics operator who can turn data requirements into reliable processes"),
    "People Operations": ("run the systems and specialist processes that support employees and managers", "a People/HR operator with direct domain experience"),
    "Chief of Staff": ("increase an executive's leverage through decision support, operating cadence, and priority follow-through", "an executive operator with judgment, synthesis, and follow-through"),
    "Transformation / Operational Excellence": ("redesign how work gets done and help the organization adopt the change", "a transformation operator who can diagnose, redesign, and implement"),
    "Sales Engineering": ("provide the technical credibility and solution design needed to win complex sales", "a customer-facing technical seller and solution designer"),
    "Engineering Management": ("lead engineers and deliver reliable software systems", "an engineering people leader with software delivery depth"),
    "Creative Operations": ("make creative intake, resourcing, production, and delivery run predictably", "a creative-production operator"),
    "Content Operations": ("make content production, publishing, quality, and governance run reliably", "a content workflow and governance operator"),
}


TECHNICAL_SIGNALS = (
    "api", "apis", "sdk", "pixels", "pixel implementation", "integration", "integrations",
    "coding", "code", "debug", "troubleshoot", "technical architecture", "sql", "javascript",
    "ad serving", "conversions api", "software architecture",
)
CLIENT_SIGNALS = (
    "client", "clients", "customer", "customers", "advertiser", "advertisers", "agency partners",
    "sales cycle", "pre-sales", "renewal", "client escalation", "customer escalation",
)
PEOPLE_MANAGEMENT_SIGNALS = (
    "manage a team", "lead a team", "manage the team", "people manager", "direct reports",
    "lead and develop a team", "hire and develop", "coach and develop", "manage solutions engineers", "lead solutions engineers",
    "manage engineers", "team of",
)


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _lower(value: Any) -> str:
    return _normalize(value).lower()


def _dedupe(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _normalize(value).strip(" -:;•")
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _description(job: dict[str, Any]) -> str:
    direct = job.get("job_description") or job.get("description")
    if direct:
        return str(direct)
    raw = str(job.get("raw_text") or "")
    marker = re.search(r"^##\s+Job Description\s*$", raw, re.I | re.M)
    return raw[marker.end():] if marker else raw


def _sentences(text: str) -> list[str]:
    pieces = re.split(r"(?:\n+|(?<=[.!?])\s+|[•·])", text)
    return _dedupe(piece for piece in pieces if len(_normalize(piece).split()) >= 4)


def _has_any(text: str, signals: Iterable[str]) -> bool:
    return any(signal in text for signal in signals)


def _classify(title: str, description: str) -> tuple[str, str | None, float, dict[str, Any]]:
    title_lower = _lower(title)
    desc_lower = _lower(description)
    scores: dict[str, int] = {}
    concrete: dict[str, list[str]] = {}
    title_hits: dict[str, list[str]] = {}
    for archetype, groups in ARCHETYPE_SIGNALS.items():
        duties = [signal for signal in groups["duties"] if signal in desc_lower]
        titles = [signal for signal in groups["title"] if signal in title_lower]
        # Duties intentionally dominate titles; a misleading title cannot win on its own.
        scores[archetype] = (4 * len(duties)) + len(titles)
        concrete[archetype] = duties
        title_hits[archetype] = titles
    ranked = sorted(scores, key=lambda value: (-scores[value], list(ARCHETYPE_SIGNALS).index(value)))
    primary = ranked[0] if scores[ranked[0]] else "General Business Operations"
    if (
        "people operations" in title_lower
        and title_hits.get("People Operations")
        and scores.get(primary, 0) <= 4
    ):
        primary = "People Operations"
        ranked.remove(primary)
        ranked.insert(0, primary)
    secondary = next(
        (value for value in ranked[1:] if scores[value] >= max(4, round(scores[primary] * 0.35))),
        None,
    )
    evidence_count = len(concrete[primary])
    lead = scores[primary] - (scores.get(secondary or "", 0) if secondary else 0)
    confidence = min(0.95, 0.42 + (0.09 * evidence_count) + (0.02 * max(0, lead)))
    if not concrete[primary]:
        confidence = min(confidence, 0.5)
    diagnostics = {
        "archetype_scores": scores,
        "concrete_signals_by_archetype": concrete,
        "title_signals_by_archetype": title_hits,
        "concrete_signals_used": concrete[primary],
    }
    return primary, secondary, round(confidence, 2), diagnostics


def _requirement_groups(sentences: list[str]) -> tuple[list[str], list[str]]:
    must: list[str] = []
    preferred: list[str] = []
    for sentence in sentences:
        lowered = sentence.lower()
        if _has_any(lowered, ("preferred", "nice to have", "bonus", "a plus", "ideally", "familiarity with")):
            preferred.append(sentence)
        elif _has_any(lowered, ("required", "must have", "minimum", "years of experience", "years experience", "proven experience", "demonstrated experience", "expertise in", "experience with")):
            must.append(sentence)
    return _dedupe(must)[:6], _dedupe(preferred)[:5]


def _responsibility_sentences(sentences: list[str]) -> list[str]:
    action_terms = (
        "lead", "manage", "own", "build", "implement", "design", "develop", "deliver", "coordinate",
        "configure", "troubleshoot", "resolve", "partner", "advise", "define", "create", "support", "drive",
    )
    concrete_terms = tuple(
        signal for groups in ARCHETYPE_SIGNALS.values() for signal in groups["duties"]
    ) + TECHNICAL_SIGNALS + CLIENT_SIGNALS
    ranked = []
    for sentence in sentences:
        lowered = sentence.lower()
        if re.match(
            r"^(?:\d+\+?\s+years?|experience|strong (?:foundational )?(?:understanding|knowledge)|adept at|familiarity|bachelor)",
            lowered,
        ):
            continue
        generic_only = _has_any(lowered, GENERIC_POSTING_PHRASES) and not _has_any(lowered, concrete_terms)
        if generic_only:
            continue
        score = sum(term in lowered for term in action_terms) + (2 * sum(term in lowered for term in concrete_terms))
        if score:
            ranked.append((score, sentence))
    return _dedupe(sentence for _score, sentence in sorted(ranked, key=lambda item: -item[0]))[:6]


def _day_to_day(primary: str, description: str, responsibilities: list[str]) -> list[str]:
    lower = description.lower()
    activities: list[str] = []
    if primary in {"Technical Solutions / Solutions Consulting", "Sales Engineering"}:
        activities.append("Work with customers or advertisers and internal sales teams to understand technical needs and unblock difficult issues.")
        if _has_any(lower, TECHNICAL_SIGNALS):
            activities.append("Review implementations and troubleshoot the technical signals, integrations, or measurement setup named in the posting.")
        activities.append("Translate recurring customer problems into clear requests for product and engineering teams.")
    elif primary == "Advertising Technology / Ad Operations":
        activities.extend((
            "Monitor and troubleshoot advertising delivery, implementation, and measurement issues named in the posting.",
            "Coordinate with advertisers, sales, product, and engineering when campaign or integration problems cross team boundaries.",
        ))
    elif primary == "Product Operations":
        activities.extend((
            "Coordinate product planning or launch processes and make ownership, readiness, and decisions visible.",
            "Collect recurring feedback from go-to-market or support teams and route it to product and engineering.",
        ))
    elif primary == "Product Management":
        activities.extend((
            "Study user and business needs, decide priorities, and maintain the product roadmap.",
            "Write or refine product requirements and work with design and engineering through delivery.",
        ))
    elif primary == "People Operations":
        activities.extend((
            "Run the employee, manager, policy, or HR-system processes explicitly named in the posting.",
            "Answer operational questions, maintain accurate people processes, and coordinate with People specialists.",
        ))
    elif primary == "Chief of Staff":
        activities.extend((
            "Prepare decision-ready analysis and briefings for the executive or leadership team.",
            "Run the operating cadence, track decisions, and follow up on a small set of leadership priorities.",
        ))
    elif primary == "Revenue Operations":
        activities.extend((
            "Maintain the sales processes, forecasts, pipeline views, or systems named in the posting.",
            "Turn revenue data into decisions for sales leaders and coordinate changes across the commercial team.",
        ))
    elif primary in {"Program / Project Management", "Technical Program Management"}:
        activities.extend((
            "Maintain plans, owners, milestones, dependencies, and risks for the work described in the posting.",
            "Run working sessions and status reviews, resolve blockers, and make decisions visible.",
        ))
    else:
        activities.extend((
            "Turn the priorities in the posting into clear owners, decisions, and repeatable operating steps.",
            "Meet with the teams named in the posting to resolve blockers and keep execution moving.",
        ))
    if _has_any(lower, PEOPLE_MANAGEMENT_SIGNALS):
        activities.append("Coach the team, review priorities and escalations, and improve how the function operates.")
    if responsibilities:
        activities.append("Deliver the concrete outcomes described in the posting, while confirming any ambiguous scope with the hiring team.")
    return _dedupe(activities)[:6]


def _stakeholder(primary: str, text: str) -> str:
    lower = text.lower()
    if "advertiser" in lower:
        return "Advertisers and the sales teams supporting them"
    if _has_any(lower, ("client", "customer")):
        return "Customers or clients and the internal teams supporting them"
    if primary == "Chief of Staff":
        return "The supported executive and leadership team"
    if primary == "People Operations":
        return "Employees, managers, and People/HR partners"
    if primary in {"Product Operations", "Product Management"}:
        return "Product, engineering, and the users or go-to-market teams named in the posting"
    return "The internal business teams named in the posting"


def _expectation(text: str, positive: tuple[str, ...], *, required: str, likely: str) -> str:
    lower = text.lower()
    if positive == PEOPLE_MANAGEMENT_SIGNALS and re.search(
        r"\b(?:lead|manage|supervise|mentor)\b[^.\n]{0,80}\bteam\b", lower
    ):
        return required
    if positive == CLIENT_SIGNALS and _has_any(
        lower,
        ("own client escalations", "own customer escalations", "resolve client technical", "advise advertisers", "advise clients", "advise customers"),
    ):
        return required
    if not _has_any(lower, positive):
        return "Not indicated"
    sentence = next((value for value in _sentences(text) if _has_any(value.lower(), positive)), "")
    if _has_any(sentence.lower(), ("must", "required", "will manage", "responsible for", "lead a team", "manage a team")):
        return required
    return likely


def _technical_depth(text: str, primary: str) -> str:
    lower = text.lower()
    hits = [signal for signal in TECHNICAL_SIGNALS if signal in lower]
    hands_on = _has_any(lower, ("hands-on", "implement", "configure", "debug", "troubleshoot", "coding", "write code", "technical architecture"))
    if len(hits) >= 3 and hands_on:
        return "High"
    if hits or primary in {"Technical Solutions / Solutions Consulting", "Technical Program Management", "Sales Engineering", "Marketing Technology", "Advertising Technology / Ad Operations"}:
        return "Moderate" if hits else "Unclear"
    return "Low"


def _fit_questions(primary: str, text: str, technical: str, people: str, client: str) -> list[str]:
    questions: list[str] = []
    lower = text.lower()
    if primary in {"Technical Solutions / Solutions Consulting", "Sales Engineering", "Advertising Technology / Ad Operations", "Implementation / Onboarding"}:
        questions.append("How hands-on is the role with APIs, pixels, SDKs, integrations, debugging, or code?")
        questions.append("Is the work primarily implementation, troubleshooting, pre-sales solution design, or product feedback?")
    if people in {"Likely", "Not indicated"}:
        questions.append("Is this a formal people-management role, and what team or disciplines would report to it?")
    if client in {"Likely", "Not indicated"}:
        questions.append("How much direct customer or client interaction and escalation ownership is expected?")
    if primary == "Product Operations":
        questions.append("Does this role enable product decisions and launches, or own roadmap and feature-priority decisions?")
    if primary == "Chief of Staff":
        questions.append("Which executive is supported, and how much authority does the role have beyond coordination?")
    if not _has_any(lower, ("success metric", "kpi", "measured by", "first 90", "first three months")):
        questions.append("What outcomes would define success in the first 90 days and first year?")
    return _dedupe(questions)[:5]


def _hidden_criteria(primary: str, text: str) -> list[str]:
    lower = text.lower()
    criteria: list[str] = []
    if primary in {"Technical Solutions / Solutions Consulting", "Technical Program Management", "Sales Engineering"}:
        criteria.append("Likely inferred: credibility with technical teams and the ability to translate between technical and nontechnical groups.")
    if _has_any(lower, CLIENT_SIGNALS) and _has_any(lower, ("escalation", "troubleshoot", "resolve", "critical")):
        criteria.append("Likely inferred: composure and credibility when a valuable customer has a difficult problem.")
    if _has_any(lower, ("build from scratch", "build the function", "establish the function", "0 to 1", "zero to one")):
        criteria.append("Likely inferred: experience building a function or operating model from scratch.")
    if _has_any(lower, ("ambiguity", "fast-paced", "rapid growth", "scaling")):
        criteria.append("Likely inferred: willingness to create structure while the organization is changing.")
    if _has_any(lower, PEOPLE_MANAGEMENT_SIGNALS):
        criteria.append("Likely inferred: willingness to handle detailed team execution and escalations despite the senior title.")
    if not criteria:
        criteria.append("No distinct hidden criterion is strongly supported; verify the hiring manager's actual screening priorities.")
    return _dedupe(criteria)[:5]


def apply_interpretation_overrides(
    interpretation: dict[str, Any], overrides: dict[str, Any] | None
) -> dict[str, Any]:
    """Apply explicit user corrections and mark the result authoritative for scoring."""
    result = deepcopy(interpretation)
    clean_overrides = dict(overrides or {})
    allowed = {
        "primary_archetype", "secondary_archetype", "technical_depth",
        "people_management_expectation", "client_facing_expectation",
        "plain_english_summary", "strategic_vs_execution_balance",
    }
    applied: dict[str, Any] = {}
    for field in allowed:
        value = clean_overrides.get(field)
        if value not in (None, ""):
            result[field] = value
            applied[field] = value
    if "primary_archetype" in applied:
        result["actual_role_type"] = applied["primary_archetype"]
        guidance = ARCHETYPE_GUIDANCE.get(str(applied["primary_archetype"]))
        if guidance:
            result["core_mission"] = guidance[0].capitalize() + "."
            result["candidate_profile"] = guidance[1].capitalize() + "."
    result["user_overrides"] = applied
    result["user_reviewed"] = bool(applied or clean_overrides.get("user_reviewed"))
    if clean_overrides.get("feedback"):
        result["user_feedback"] = str(clean_overrides["feedback"])
    if result.get("ranked_interpretations"):
        result = _with_ranked_interpretations(result)
    return result


def _interpretation_option(
    archetype: str,
    confidence: float,
    interpretation: dict[str, Any],
    signals: list[str],
    contradicting: list[str],
) -> dict[str, Any]:
    mission, profile = ARCHETYPE_GUIDANCE[archetype]
    is_primary = archetype == interpretation.get("primary_archetype")
    stakeholder = str(
        interpretation.get("primary_customer_or_stakeholder")
        or "the stakeholders named in the posting"
    )
    alternate_day_to_day = [
        f"Focus day-to-day on work that would {mission}.",
        f"Work with {stakeholder.lower()} around the posting's concrete {archetype.lower()} responsibilities.",
    ]
    return {
        "archetype": archetype,
        "confidence": round(confidence, 2),
        "confidence_percent": round(confidence * 100),
        "plain_english_description": (
            interpretation.get("plain_english_summary")
            if is_primary
            else f"This appears to be a {archetype.lower()} role focused on helping the organization {mission}."
        ),
        "core_mission": interpretation.get("core_mission") if is_primary else mission.capitalize() + ".",
        "primary_stakeholders": interpretation.get("primary_customer_or_stakeholder"),
        "expected_day_to_day_work": (
            list(interpretation.get("likely_day_to_day") or [])
            if is_primary else alternate_day_to_day
        ),
        "true_must_haves": list(interpretation.get("true_must_haves") or []),
        "likely_success_measures": list(interpretation.get("success_metrics") or []),
        "technical_depth": interpretation.get("technical_depth"),
        "client_facing_level": interpretation.get("client_facing_expectation"),
        "people_management_expectation": interpretation.get("people_management_expectation"),
        "strategic_vs_execution_balance": interpretation.get("strategic_vs_execution_balance"),
        "candidate_archetype": profile.capitalize() + ".",
        "supporting_evidence_signals": list(signals),
        "contradicting_evidence_signals": list(contradicting),
    }


def _with_ranked_interpretations(interpretation: dict[str, Any]) -> dict[str, Any]:
    """Attach explainable primary/alternate interpretations from concrete-signal scores."""
    result = deepcopy(interpretation)
    diagnostics = dict(result.get("diagnostics") or {})
    scores = dict(diagnostics.get("archetype_scores") or {})
    concrete = dict(diagnostics.get("concrete_signals_by_archetype") or {})
    chosen = str(result.get("primary_archetype") or "General Business Operations")
    positive = [
        archetype for archetype, score in scores.items()
        if score > 0 and concrete.get(archetype)
    ]
    positive.sort(key=lambda archetype: (-scores[archetype], list(ARCHETYPE_SIGNALS).index(archetype)))
    if chosen not in positive:
        positive.insert(0, chosen)
        scores.setdefault(chosen, 1)
        concrete.setdefault(chosen, [])
    primary_score = max(scores.get(positive[0], 1), scores.get(chosen, 1))
    credible = [
        archetype for archetype in positive
        if archetype == chosen or scores.get(archetype, 0) >= max(4, round(primary_score * 0.35))
    ][:4]
    credible = [chosen, *[value for value in credible if value != chosen]]
    total = sum(max(1, scores.get(value, 0)) for value in credible) or 1
    raw_confidences = [max(1, scores.get(archetype, 0)) / total for archetype in credible]
    rounded_confidences = [round(value, 2) for value in raw_confidences]
    if len(rounded_confidences) == 1:
        rounded_confidences[0] = round(float(result.get("confidence") or 0.42), 2)
    elif rounded_confidences:
        rounded_confidences[-1] = round(
            max(0.0, 1.0 - sum(rounded_confidences[:-1])), 2
        )
    options = []
    for rank, (archetype, confidence) in enumerate(
        zip(credible, rounded_confidences), start=1
    ):
        contradicting = [
            signal
            for other in credible
            if other != archetype
            for signal in (concrete.get(other) or [])[:2]
        ]
        option = _interpretation_option(
                archetype,
                confidence,
                result,
                list(concrete.get(archetype) or []),
                _dedupe(contradicting),
            )
        option["rank"] = rank
        options.append(option)
    primary_confidence = options[0]["confidence"] if options else float(result.get("confidence") or 0)
    second_confidence = options[1]["confidence"] if len(options) > 1 else 0.0
    margin = round(primary_confidence - second_confidence, 2)
    has_concrete_basis = bool(options and options[0].get("supporting_evidence_signals"))
    if not has_concrete_basis:
        ambiguity = "High"
    elif len(options) == 1:
        ambiguity = "Low" if primary_confidence >= 0.6 else "Medium"
    elif margin >= 0.3:
        ambiguity = "Low"
    elif margin >= 0.15:
        ambiguity = "Medium"
    else:
        ambiguity = "High"
    decisive = list(options[0].get("supporting_evidence_signals") or []) if options else []
    conflicting = _dedupe(
        signal
        for option in options[1:]
        for signal in option.get("supporting_evidence_signals") or []
    )
    ambiguity_reason = (
        "The posting lacks enough concrete functional responsibilities to support a confident interpretation."
        if not has_concrete_basis
        else
        "One functional interpretation clearly dominates the concrete responsibility signals."
        if ambiguity == "Low"
        else "The posting contains concrete responsibility signals for more than one functional archetype."
    )
    result.update(
        {
            "primary_interpretation": options[0] if options else {},
            "secondary_interpretations": options[1:],
            "ranked_interpretations": options,
            "interpretation_confidence": primary_confidence,
            "interpretation_margin": margin,
            "ambiguity_level": ambiguity,
            "ambiguity_reason": ambiguity_reason,
            "decisive_signals": decisive,
            "conflicting_signals": conflicting,
            "unresolved_questions": list(result.get("major_fit_questions") or []),
            "confirmed_interpretation": options[0] if result.get("user_reviewed") and options else None,
        }
    )
    diagnostics.update(
        {
            "ranked_interpretations": [
                {"archetype": item["archetype"], "confidence": item["confidence"]}
                for item in options
            ],
            "interpretation_margin": margin,
            "ambiguity_level": ambiguity,
            "user_override_state": dict(result.get("user_overrides") or {}),
        }
    )
    result["diagnostics"] = diagnostics
    return result


def interpret_role(
    job: dict[str, Any], overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return a structured, plain-English interpretation of a posting."""
    title = str(job.get("job_title") or job.get("role") or job.get("title") or "").strip()
    description = _description(job)
    sentences = _sentences(description)
    primary, secondary, confidence, diagnostics = _classify(title, description)
    responsibilities = _responsibility_sentences(sentences)
    true_must_haves, preferred = _requirement_groups(sentences)
    ignored = [phrase for phrase in GENERIC_POSTING_PHRASES if phrase in description.lower()]
    mission, archetype_profile = ARCHETYPE_GUIDANCE[primary]
    technical = _technical_depth(description, primary)
    people = _expectation(description, PEOPLE_MANAGEMENT_SIGNALS, required="Required", likely="Likely")
    client = _expectation(description, CLIENT_SIGNALS, required="Required", likely="Likely")
    stakeholder = _stakeholder(primary, description)
    strategy_terms = sum(term in description.lower() for term in ("strategy", "roadmap", "planning", "recommendations", "vision"))
    execution_terms = sum(term in description.lower() for term in ("implement", "execute", "deliver", "troubleshoot", "configure", "operate", "manage"))
    if strategy_terms and execution_terms:
        balance = "Balanced strategy and execution"
    elif strategy_terms:
        balance = "Primarily strategic"
    elif execution_terms:
        balance = "Primarily execution"
    else:
        balance = "Unclear"
    customer_phrase = stakeholder.lower()
    article = "an" if primary[0].lower() in "aeiou" else "a"
    summary = f"This appears to be {article} {primary.lower()} role that would {mission} for {customer_phrase}."
    uncertain: list[str] = []
    if technical == "Unclear":
        uncertain.append("Technical depth is unclear from the posting.")
    if people == "Not indicated":
        uncertain.append("Formal people-management responsibility is not stated.")
    if client == "Not indicated":
        uncertain.append("Direct client-facing responsibility is not stated.")
    if not true_must_haves:
        uncertain.append("The posting does not clearly separate required from preferred qualifications.")
    success_metrics = [
        sentence for sentence in sentences
        if _has_any(sentence.lower(), ("success", "metric", "kpi", "increase", "reduce", "improve", "revenue", "adoption", "reliability"))
    ][:4]
    first_90 = [
        sentence for sentence in sentences
        if _has_any(sentence.lower(), ("first 90", "first three months", "first 3 months", "within 90"))
    ][:3]
    if not first_90:
        first_90 = ["Not stated; verify the first 90-day outcomes with the hiring manager."]
    not_confused = {
        "Product Operations": "Product Management: the posting emphasizes launch/process enablement rather than roadmap ownership.",
        "Product Management": "Product Operations: the posting suggests roadmap and product-decision ownership.",
        "Technical Solutions / Solutions Consulting": "General Business Operations: shared leadership language does not replace the technical customer-solution work.",
        "Advertising Technology / Ad Operations": "General Marketing Operations: advertising delivery and measurement technology are material.",
        "People Operations": "General Business Operations: HR-domain systems and employee processes are substantive requirements.",
        "Chief of Staff": "General project coordination: the role exists to increase executive leverage and decision follow-through.",
    }.get(primary, f"A title-led interpretation that ignores the posting's concrete {primary.lower()} duties.")
    interpretation = {
        "plain_english_summary": summary,
        "core_mission": mission.capitalize() + ".",
        "actual_role_type": primary,
        "primary_archetype": primary,
        "secondary_archetype": secondary,
        "archetype_confidence": confidence,
        "primary_customer_or_stakeholder": stakeholder,
        "primary_work_mode": balance,
        "likely_day_to_day": _day_to_day(primary, description, responsibilities),
        "top_responsibilities": responsibilities,
        "true_must_haves": true_must_haves,
        "preferred_or_trainable": preferred,
        "generic_language": ignored,
        "hidden_hiring_criteria": _hidden_criteria(primary, description),
        "success_metrics": success_metrics or ["Not explicitly stated; verify measurable outcomes."],
        "likely_first_90_day_expectations": first_90,
        "role_not_to_be_confused_with": not_confused,
        "candidate_profile": archetype_profile.capitalize() + ".",
        "major_fit_questions": _fit_questions(primary, description, technical, people, client),
        "technical_depth": technical,
        "people_management_expectation": people,
        "client_facing_expectation": client,
        "strategic_vs_execution_balance": balance,
        "confidence": confidence,
        "confidence_label": "High" if confidence >= 0.8 else "Medium" if confidence >= 0.6 else "Low",
        "interpretation_notes": uncertain,
        "diagnostics": {
            **diagnostics,
            "generic_phrases_ignored": ignored,
            "inferred_hidden_criteria": _hidden_criteria(primary, description),
            "uncertain_conclusions": uncertain,
        "classification_basis": "Concrete responsibility signals are weighted four times more than title signals; an exact People Operations title prevents a single generic duty from changing the department.",
        },
        "user_reviewed": False,
        "user_overrides": {},
    }
    interpretation = _with_ranked_interpretations(interpretation)
    return apply_interpretation_overrides(interpretation, overrides) if overrides else interpretation


def substantive_interpretation_text(interpretation: dict[str, Any]) -> str:
    """Return only interpreted functional requirements for substantive scoring."""
    fields = (
        "primary_archetype", "secondary_archetype", "core_mission",
        "top_responsibilities", "true_must_haves", "success_metrics",
        "technical_depth", "people_management_expectation",
        "client_facing_expectation", "strategic_vs_execution_balance",
    )
    values: list[str] = []
    for field in fields:
        value = interpretation.get(field)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))
    return "\n".join(values)


INTERPRETATION_SCORE_FIELDS = (
    "primary_archetype", "secondary_archetype", "core_mission", "true_must_haves",
    "technical_depth", "people_management_expectation", "client_facing_expectation",
    "strategic_vs_execution_balance", "success_metrics", "major_fit_questions",
)
