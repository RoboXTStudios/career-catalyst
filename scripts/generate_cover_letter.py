"""Generate grounded cover letters from Career Catalyst data and job analysis."""

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

try:
    from .docx_metadata import clean_docx_metadata
    from .application_strategy import (
        TECHNICAL_ARCHETYPES,
        build_application_strategy,
        build_hiring_manager_lens,
        interview_preparation_model,
        role_specificity_check,
    )
    from .company_voice import company_voice_context
    from .cover_letter_quality import cover_letter_quality_pass
    from .evidence_engine import load_evidence_cards, load_writing_voice_profile
    from .evidence_profile import (
        evidence_as_card,
        load_evidence_profile,
    )
    from .capability_graph import load_capability_graph
    from .role_evidence_selection import selected_evidence as selected_role_evidence
    from .employer_identity import (
        OMG23_DISPLAY_NAME,
        canonical_employer_name,
        normalize_applicant_employer_names,
    )
    from .filename_utils import build_upload_filename, company_display_name
    from .human_positioning import (
        positioning_violations,
        replace_personal_project_paragraphs,
        validate_applicant_evidence,
    )
    from .load_data import load_all_yaml
    from .parse_job import parse_job_description
    from .package_context import validate_material_context
    from .public_advocacy import rewrite_public_advocacy, validate_public_advocacy
    from .role_lens import enforce_role_lens_quality
    from .role_context import (
        GOOGLE_IMPLICATION_PHRASES,
        google_claim_violations,
        is_google_youtube_role,
    )
    from .role_editing import (
        material_editing_plan,
        remaining_banned_voice_phrases,
        rewrite_banned_voice_phrases,
    )
    from .score_match import score_job_match
    from .text_cleanup import cleanup_repeated_words
except ImportError:
    from docx_metadata import clean_docx_metadata
    from application_strategy import (
        TECHNICAL_ARCHETYPES,
        build_application_strategy,
        build_hiring_manager_lens,
        interview_preparation_model,
        role_specificity_check,
    )
    from company_voice import company_voice_context
    from cover_letter_quality import cover_letter_quality_pass
    from evidence_engine import load_evidence_cards, load_writing_voice_profile
    from evidence_profile import evidence_as_card, load_evidence_profile
    from capability_graph import load_capability_graph
    from role_evidence_selection import selected_evidence as selected_role_evidence
    from employer_identity import (
        OMG23_DISPLAY_NAME,
        canonical_employer_name,
        normalize_applicant_employer_names,
    )
    from filename_utils import build_upload_filename, company_display_name
    from human_positioning import (
        positioning_violations,
        replace_personal_project_paragraphs,
        validate_applicant_evidence,
    )
    from load_data import load_all_yaml
    from parse_job import parse_job_description
    from package_context import validate_material_context
    from public_advocacy import rewrite_public_advocacy, validate_public_advocacy
    from role_lens import enforce_role_lens_quality
    from role_context import (
        GOOGLE_IMPLICATION_PHRASES,
        google_claim_violations,
        is_google_youtube_role,
    )
    from role_editing import (
        material_editing_plan,
        remaining_banned_voice_phrases,
        rewrite_banned_voice_phrases,
    )
    from score_match import score_job_match
    from text_cleanup import cleanup_repeated_words


PathInput = Union[str, Path]


class ApplicationMaterialError(Exception):
    """Raised when an application material cannot be generated safely."""


def load_generation_context(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    package_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load career data, parsed job details, and the match report."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    resolved_job_path = Path(job_path)
    if not resolved_job_path.is_absolute():
        resolved_job_path = root / resolved_job_path

    career_data = load_all_yaml(root)
    parsed_job = parse_job_description(resolved_job_path)
    package_context = dict(package_context or {})
    saved_interpretation = (
        package_context.get("role_interpretation")
        or (package_context.get("role_intelligence") or {}).get("role_interpretation")
        or {}
    )
    voice_context = company_voice_context(
        parsed_job,
        career_data["config"].get("company_voice_profiles", {}),
        saved_interpretation if isinstance(saved_interpretation, dict) else None,
    )
    parsed_job = dict(parsed_job)
    parsed_job["company_legal_name"] = parsed_job.get("company")
    parsed_job["company"] = company_display_name(parsed_job.get("company"))
    role_lens = dict(voice_context.get("role_lens") or {})
    requirement_map = list(voice_context.get("requirement_map") or [])
    parsed_job["primary_role_lens"] = role_lens.get("primary")
    parsed_job["role_lens"] = role_lens
    parsed_job["requirement_map"] = requirement_map
    parsed_job["role_interpretation"] = dict(
        voice_context.get("role_interpretation") or {}
    )
    evidence_cards = load_evidence_cards(root)
    evidence_profile = load_evidence_profile(root)
    writing_voice = load_writing_voice_profile(root)
    evidence_selection_overrides = dict(
        package_context.get("evidence_selection_overrides")
        or (package_context.get("role_evidence_selection") or {}).get("overrides")
        or {}
    )
    match_report = (
        score_job_match(
            job_path,
            root,
            parsed_job["role_interpretation"],
            evidence_selection_overrides or None,
        )
        if parsed_job.get("role_interpretation")
        else score_job_match(
            job_path, root, evidence_selection_overrides=evidence_selection_overrides or None
        )
    )
    role_interpretation = dict(
        match_report.get("role_interpretation")
        or parsed_job.get("role_interpretation")
        or {}
    )
    parsed_job["role_interpretation"] = role_interpretation
    role_evidence_selection = dict(
        match_report.get("role_evidence_selection") or {}
    )
    exact_role_evidence = selected_role_evidence(role_evidence_selection)
    selected_profile_evidence = [
        item for item in exact_role_evidence
        if (item.get("recommended_usage") or {}).get("cover_letter", True)
    ][:6]
    selected_interview_profile_evidence = [
        item for item in exact_role_evidence
        if (item.get("recommended_usage") or {}).get("interview", True)
    ][:8]
    exact_role_evidence_cards = [evidence_as_card(item) for item in exact_role_evidence]
    combined_selected_evidence = list(exact_role_evidence_cards)
    effective_voice = dict(voice_context.get("effective_voice_profile") or {})
    effective_voice.update({
        "selected_evidence_ids": [item["id"] for item in exact_role_evidence_cards],
        "selected_evidence_labels": [item["label"] for item in exact_role_evidence_cards],
        "proof_points_to_emphasize": [
            point
            for item in exact_role_evidence_cards
            for point in item.get("proof_points") or []
        ],
        "profile_evidence_to_emphasize": selected_profile_evidence,
        "selected_profile_evidence_ids": [
            str(item.get("id")) for item in selected_profile_evidence
        ],
    })
    voice_context["effective_voice_profile"] = effective_voice
    capability_graph = load_capability_graph(root, evidence_profile)
    alignment_matrix = list(
        (match_report.get("capability_graph") or {}).get("alignment_matrix") or []
    )
    gap_analysis = dict(match_report.get("evidence_gap_analysis") or {})
    hiring_manager_lens = build_hiring_manager_lens(
        role_interpretation, alignment_matrix, gap_analysis
    )
    application_strategy = build_application_strategy(
        role_interpretation,
        hiring_manager_lens,
        match_report,
        combined_selected_evidence,
    )
    career_coach = dict(package_context.get("career_coach") or {})
    if career_coach:
        positioning = str(career_coach.get("recommended_positioning") or "").strip()
        if positioning:
            application_strategy["candidate_positioning"] = positioning
            application_strategy["cover_letter_thesis"] = positioning
        lead_with = list(career_coach.get("lead_with") or [])
        if lead_with:
            application_strategy["resume_emphasis"] = lead_with
    editing_plan = material_editing_plan(parsed_job, root)
    return {
        "root": root,
        "career_data": career_data,
        "voice": career_data["config"].get("voice", {}),
        "writing_voice": writing_voice,
        "evidence_cards": evidence_cards,
        "selected_evidence_cards": exact_role_evidence_cards,
        "combined_selected_evidence_cards": combined_selected_evidence,
        "evidence_profile": evidence_profile,
        "selected_profile_evidence": selected_profile_evidence,
        "selected_interview_profile_evidence": selected_interview_profile_evidence,
        "capability_graph": capability_graph,
        "alignment_matrix": alignment_matrix,
        "evidence_gap_analysis": gap_analysis,
        "role_evidence_selection": role_evidence_selection,
        "evidence_selection_overrides": evidence_selection_overrides,
        "material_editing_plan": editing_plan,
        "role_lens": role_lens,
        "requirement_map": requirement_map,
        "role_interpretation": role_interpretation,
        "hiring_manager_lens": hiring_manager_lens,
        "application_strategy": application_strategy,
        "career_coach": career_coach,
        "interview_preparation": interview_preparation_model(
            role_interpretation, hiring_manager_lens, application_strategy
        ),
        "parsed_job": parsed_job,
        "match_report": match_report,
        **voice_context,
    }


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*\b", text))


def save_material(
    context: Dict[str, Any],
    suffix: str,
    content: str,
    minimum_words: int,
    maximum_words: int,
    repair_content: Optional[Callable[[str, Dict[str, Any]], str]] = None,
    repair_attempts: int = 3,
) -> Dict[str, Any]:
    """Validate and save one Markdown application material, repairing length when configured."""
    content = normalize_applicant_employer_names(cleanup_repeated_words(content))
    advocacy_review: Dict[str, Any] = {}

    def apply_public_advocacy(value: str) -> str:
        nonlocal advocacy_review
        parsed = context.get("parsed_job") or {}
        rewritten, advocacy_review = rewrite_public_advocacy(
            value,
            company=str(parsed.get("company") or "the organization"),
            role=str(parsed.get("job_title") or "the role"),
            transparency_requested=bool(context.get("public_transparency_requested")),
        )
        return rewritten

    content = apply_public_advocacy(content)
    content, role_lens_quality = enforce_role_lens_quality(
        content,
        context.get("role_lens", {}),
        material_type=suffix,
    )
    if not role_lens_quality["valid"]:
        reason = role_lens_quality["violations"][0]
        raise ApplicationMaterialError(
            "Generated application material does not match the role lens: "
            f"{reason['code']} ({reason['detail']})."
        )
    rewrite_notes: list[dict[str, str]] = []
    content, initial_rewrites = rewrite_banned_voice_phrases(content)
    rewrite_notes.extend(initial_rewrites)
    word_count = _word_count(content)
    attempts = 0
    while not minimum_words <= word_count <= maximum_words and repair_content and attempts < repair_attempts:
        content = cleanup_repeated_words(repair_content(content, context))
        content = apply_public_advocacy(content)
        content, attempt_rewrites = rewrite_banned_voice_phrases(content)
        rewrite_notes.extend(attempt_rewrites)
        word_count = _word_count(content)
        attempts += 1
    cover_letter_quality = None
    interpretation_quality = None
    if suffix.lower().replace(" ", "_") == "cover_letter":
        prohibited_rewrites = list(GOOGLE_IMPLICATION_PHRASES)
        for requirement in context.get("requirement_map", []):
            if isinstance(requirement, dict):
                prohibited_rewrites.extend(
                    str(value)
                    for value in requirement.get("prohibited_overclaim_language", [])
                    if value
                )
        content, cover_letter_quality = cover_letter_quality_pass(
            content,
            is_google_youtube=is_google_youtube_role(context["parsed_job"]),
            forbidden_phrases=prohibited_rewrites,
        )
        content = cleanup_repeated_words(content)
        word_count = _word_count(content)
        content, role_lens_quality = enforce_role_lens_quality(
            content,
            context.get("role_lens", {}),
            material_type=suffix,
        )
        if not role_lens_quality["valid"]:
            reason = role_lens_quality["violations"][0]
            raise ApplicationMaterialError(
                "Generated application material does not match the role lens after quality cleanup: "
                f"{reason['code']} ({reason['detail']})."
            )
        role_interpretation = context.get("role_interpretation") or {}
        if isinstance(role_interpretation, dict) and role_interpretation:
            interpretation_quality = role_specificity_check(
                content,
                role_interpretation,
                context.get("hiring_manager_lens") or {},
            )
            if not interpretation_quality["valid"]:
                reason = (interpretation_quality.get("failure_reasons") or [
                    "The cover letter does not match the confirmed role interpretation."
                ])[0]
                raise ApplicationMaterialError(
                    "Cover letter interpretation mismatch: " + str(reason)
                )
    if "—" in content:
        raise ApplicationMaterialError("Generated application materials must not contain em dashes.")
    if "placeholder" in content.lower():
        raise ApplicationMaterialError("Generated application materials must not contain placeholder text.")
    if rewrite_notes:
        context.setdefault("material_warnings", []).append(
            "Rewrote banned voice phrases before validation: "
            + ", ".join(note["phrase"] for note in rewrite_notes)
        )

    if is_google_youtube_role(context["parsed_job"]):
        violations = google_claim_violations(content)
        if violations:
            raise ApplicationMaterialError(
                f"Google/YouTube material contains unsupported relationship claim: {violations[0]}"
            )
    configured_banned_phrases = list(context.get("voice", {}).get("avoid", []))
    configured_banned_phrases.extend(context.get("writing_voice", {}).get("banned_phrases", []))
    configured_banned_phrases.extend(context.get("material_editing_plan", {}).get("banned_phrases", []))
    remaining_banned = remaining_banned_voice_phrases(content, configured_banned_phrases)
    if remaining_banned:
        raise ApplicationMaterialError(
            f"Generated application materials contain banned voice phrase: {remaining_banned[0]}"
        )

    if not minimum_words <= word_count <= maximum_words:
        raise ApplicationMaterialError(
            f"Generated {suffix} must be {minimum_words}-{maximum_words} words; got {word_count}."
        )

    validate_material_context(content, context["parsed_job"], suffix)
    validate_applicant_evidence(content, suffix)
    positioning_issues = positioning_violations(content)
    if positioning_issues:
        raise ApplicationMaterialError(
            "Generated application materials contain tenure-forward or clichéd positioning: "
            f"{positioning_issues[0]}"
        )
    try:
        advocacy_review = validate_public_advocacy(
            content,
            suffix,
            transparency_requested=bool(context.get("public_transparency_requested")),
        )
    except ValueError as error:
        raise ApplicationMaterialError(str(error)) from error

    parsed_job = context["parsed_job"]
    personal_brand = context["career_data"]["data"].get("personal_brand", {})
    candidate = personal_brand.get("candidate", {})
    candidate_name = (
        str(candidate.get("name") or "Trisha Lynch")
        if isinstance(candidate, dict)
        else "Trisha Lynch"
    )
    filename = build_upload_filename(
        candidate_name,
        str(parsed_job.get("job_title") or "Role"),
        str(parsed_job.get("company") or "Company"),
        suffix,
        "txt",
    )
    output_path = (
        context["root"]
        / "exports"
        / "messages"
        / filename
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content.rstrip() + "\n", encoding="utf-8")

    return {
        "job_title": parsed_job.get("job_title"),
        "company": parsed_job.get("company"),
        "match_score": context["match_report"].get("match_score"),
        "company_voice_profile": context.get("profile_key", "default"),
        "company_voice_source": context.get("profile_source", "dynamic_inference"),
        "company_category": context.get("company_category", "generic_business_operations"),
        "role_family": context.get("role_family", "creative_marketing_ops"),
        "voice_confidence": context.get("effective_voice_profile", {}).get("confidence"),
        "output_path": str(output_path),
        "txt_output_path": str(output_path),
        "word_count": word_count,
        "repair_attempts": attempts,
        "warnings": list(context.get("material_warnings", [])),
        "banned_phrase_rewrites": rewrite_notes,
        "role_lens": context.get("role_lens", {}),
        "requirement_map": context.get("requirement_map", []),
        "role_lens_quality": role_lens_quality,
        "cover_letter_quality": cover_letter_quality,
        "interpretation_quality": interpretation_quality,
        "role_interpretation": context.get("role_interpretation", {}),
        "hiring_manager_lens": context.get("hiring_manager_lens", {}),
        "application_strategy": context.get("application_strategy", {}),
        "public_advocacy_review": advocacy_review,
    }


def _cover_letter_value_sentences(context: Dict[str, Any]) -> List[str]:
    parsed_job = context.get("parsed_job", {})
    company = str(parsed_job.get("company") or "the team")
    role_family = str(context.get("role_family") or "business_operations")
    role_sentence = {
        "creative_marketing_ops": "I know how much strong creative work depends on clear intake, thoughtful prioritization, and practical systems that help teams protect quality under pressure.",
        "business_operations": "My best work has been making complex operations easier to see and run, with clear ownership, useful decision rhythms, and systems people can actually maintain.",
        "product_strategy_ops": "I am comfortable translating product and business priorities into roadmaps, decisions, feedback loops, and operating rhythms that keep cross-functional work moving.",
        "ai_operations_systems": "I build AI-enabled workflows with a practical bias: reduce repetitive work, surface risks earlier, and leave important judgment with the people closest to the work.",
    }.get(
        role_family,
        "I start by listening closely, clarifying the real constraint, and building enough structure for people to move with confidence.",
    )
    return [
        role_sentence,
        f"That is the perspective I would bring to {company}, along with calm stakeholder leadership and a habit of turning recurring friction into a clearer, more dependable way of working.",
        "The through line in my experience is simple: I care about the work itself, the people doing it, and the operating conditions that allow both to be at their best.",
        "Across entertainment campaigns and internal transformation work, I have learned to ask direct questions, make tradeoffs visible, and keep the solution proportionate to the problem.",
        "I am equally comfortable shaping the plan, working through the details with a team, and giving leaders a concise view of what needs a decision.",
        "That combination of strategic range and hands-on follow-through has helped me earn trust across creative, marketing, analytics, technology, and operations partners.",
        "I would approach the first months by learning how work moves today, where teams lose time or context, and which small changes would create meaningful momentum.",
        "I am drawn to roles where better operations do more than improve a dashboard; they give talented people more room to focus on thoughtful, high-quality work.",
        "That is the kind of contribution I am looking to make next, with curiosity, candor, and respect for what is already working.",
        "My background has taught me to move between strategy and execution without treating either as the easy part, and to communicate clearly when the path is still taking shape.",
        "I bring the patience to understand a complicated environment and the urgency to make useful progress once the real problem is clear.",
        "Most of all, I value work that leaves a team stronger: clearer about its priorities, more confident in its decisions, and better equipped for what comes next.",
    ]


def _expand_cover_letter(content: str, context: Dict[str, Any], target: int = 285) -> str:
    additions: List[str] = []
    for sentence in _cover_letter_value_sentences(context):
        additions.append(sentence)
        if _word_count(content + "\n\n" + " ".join(additions)) >= target:
            break
    paragraph = " ".join(additions)
    signoff = re.search(r"\n\n((?:Sincerely|Best|Warmly|Thank you)[\s\S]*)$", content.strip(), re.I)
    if signoff:
        return content[: signoff.start()].rstrip() + "\n\n" + paragraph + "\n\n" + signoff.group(1).strip()
    return content.rstrip() + "\n\n" + paragraph


def _trim_cover_letter(content: str, target: int = 325) -> str:
    clean = content.strip()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", clean) if part.strip()]
    greeting = paragraphs.pop(0) if paragraphs and _word_count(paragraphs[0]) <= 4 else ""
    signoff_parts: List[str] = []
    while paragraphs and (
        re.match(r"^(?:Sincerely|Best|Warmly|Thank you)\b", paragraphs[-1], re.I)
        or _word_count(paragraphs[-1]) <= 4
    ):
        signoff_parts.insert(0, paragraphs.pop())
    body = "\n\n".join(paragraphs)
    sentences = [value.strip() for value in re.split(r"(?<=[.!?])\s+", body) if value.strip()]
    reserved = _word_count(" ".join([greeting, *signoff_parts]))
    budget = max(250 - reserved, target - reserved)
    selected: List[str] = []
    for sentence in sentences:
        if _word_count(" ".join(selected + [sentence])) <= budget:
            selected.append(sentence)
        elif not selected:
            words = sentence.split()[:budget]
            selected.append(" ".join(words).rstrip(".,;:") + ".")
        if _word_count(" ".join(selected)) >= budget - 15:
            break
    pieces = [value for value in (greeting, " ".join(selected), *signoff_parts) if value]
    trimmed = "\n\n".join(pieces)
    if _word_count(trimmed) > 400:
        words = trimmed.split()[:target]
        trimmed = " ".join(words).rstrip(".,;:") + "."
    return trimmed


def repair_cover_letter_content(content: str, context: Dict[str, Any]) -> str:
    """Repair cover-letter length while preserving its existing language and order."""
    count = _word_count(content)
    if count < 250:
        return _expand_cover_letter(content, context)
    if count > 400:
        return _trim_cover_letter(content)
    return content


def _join_human(values: List[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def _job_focus(parsed_job: Dict[str, Any]) -> str:
    if is_google_youtube_role(parsed_job):
        return "YouTube product activation, GTM operations, and large advertiser execution"
    if _is_creative_product_operations_role(parsed_job):
        return "global creative operations, product development, and cross-functional execution"

    preferred = (
        "enterprise strategy",
        "operational planning",
        "cross-functional",
        "process improvement",
        "stakeholder alignment",
        "executive communication",
    )
    keywords = [str(keyword).lower() for keyword in parsed_job.get("keywords", [])]
    selected = [term for term in preferred if term in keywords][:3]
    if not selected:
        selected = keywords[:3]
    display_terms = {
        "cross-functional": "cross-functional execution",
    }
    selected = [display_terms.get(term, term) for term in selected]
    return _join_human(selected) or "strategy and execution"


def _is_creative_product_operations_role(parsed_job: Dict[str, Any]) -> bool:
    text = " ".join(
        str(value)
        for value in (
            parsed_job.get("job_title", ""),
            parsed_job.get("raw_text", ""),
        )
    ).lower()
    creative_signals = ("creative operations", "creative leadership", "creative assets")
    product_signals = ("product development", "licensed merchandise", "licensing")
    return any(signal in text for signal in creative_signals) and any(
        signal in text for signal in product_signals
    )


def _as_first_person(statement: str) -> str:
    text = statement.strip()
    if not text or text.startswith("I "):
        return text
    return "I " + text[0].lower() + text[1:]


def _achievement(career_data: Dict[str, Any], achievement_id: str) -> str:
    achievements = career_data["data"]["achievements"].get("achievements", [])
    achievement = next(
        (item for item in achievements if item.get("id") == achievement_id),
        {},
    )
    return str(achievement.get("statement", "")).strip()


def _position(career_data: Dict[str, Any], company_fragment: str) -> Dict[str, Any]:
    positions = career_data["data"]["positions"].get("positions", [])
    return next(
        (item for item in positions if company_fragment in str(item.get("company", ""))),
        {},
    )


def _project(career_data: Dict[str, Any], project_name: str) -> Dict[str, Any]:
    projects = career_data["data"]["projects"].get("projects", [])
    return next((item for item in projects if item.get("name") == project_name), {})


def _professional_evidence_paragraph(context: Dict[str, Any]) -> str:
    """Return role-relevant proof grounded only in stored professional experience."""
    career_data = context.get("career_data", {})
    parsed_job = context.get("parsed_job", {})
    role_family = str(context.get("role_family") or "")
    role_title = str(parsed_job.get("job_title") or "").lower()
    if not career_data.get("data"):
        return (
            "At OMG23 / OMD Entertainment, I led cross-functional work across creative, marketing, "
            "media, analytics, technology, and campaign operations. I introduced workflow governance "
            "and execution standards that made ownership, handoffs, and decisions easier to see."
        )
    editorial_title = any(
        signal in role_title
        for signal in ("copywriter", "editorial", "content strategist", "communications")
    )
    if role_family in {"music_content_strategy", "editorial_content_strategy", "community_growth"} and editorial_title:
        editorial = _achievement(career_data, "multiverse_editorial")
        if editorial:
            return (
                f"At OMG23 / OMD Entertainment, {_as_first_person(editorial)} I built the contributor "
                "framework and recurring content process around the publication, balancing a clear "
                "editorial voice with dependable delivery. The work reached 400+ employees and showed "
                "how a human point of view and a reliable operating process can strengthen each other."
            )
    if is_google_youtube_role(parsed_job):
        platform = _achievement(career_data, "google_youtube_platform_familiarity")
        return (
            f"At OMG23 / OMD Entertainment, {_as_first_person(platform)} The work connected brand "
            "goals, media execution, analytics, technology, and senior stakeholders around decisions "
            "teams could act on. It also required clear measurement readiness, quality checks, and "
            "feedback across large advertiser programs where small operational gaps could slow adoption."
        )
    workflow = _achievement(career_data, "workflow_governance")
    return (
        f"At OMG23 / OMD Entertainment, {_as_first_person(workflow)} The useful change was not more "
        "process; it was clearer ownership, more dependable handoffs, quality assurance (QA), and "
        "better operational risk visibility in the "
        "decisions affecting delivery. That work connected creative, marketing, analytics, and "
        "technology partners around shared standards while keeping day-to-day execution practical."
    )


def _entertainment_scope(career_data: Dict[str, Any]) -> str:
    position = _position(career_data, "OMG23")
    return next(
        (
            str(highlight)
            for highlight in position.get("highlights", [])
            if "Disney Studios Theatrical" in str(highlight)
        ),
        "",
    )


def _employer_names(position: Dict[str, Any]) -> tuple[str, str]:
    """Return the full employer name and a safe shorthand for later mentions."""
    full_name = canonical_employer_name(position.get("company") or OMG23_DISPLAY_NAME)
    shorthand = "OMG23" if "OMG23" in full_name else full_name
    return full_name, shorthand


def _validate_cover_letter_repetition(content: str) -> None:
    phrase_limits = {
        "campaign operations": 1,
        "complex": 1,
        "cross-functional": 1,
    }
    for paragraph in content.split("\n\n"):
        lowered = paragraph.lower()
        for phrase, maximum in phrase_limits.items():
            if lowered.count(phrase) > maximum:
                raise ApplicationMaterialError(
                    f"Cover letter paragraph repeats '{phrase}' too many times."
                )
        if "role role" in lowered:
            raise ApplicationMaterialError("Cover letter paragraph contains repeated role wording.")
    lowered_content = content.lower()
    for phrase in (
        "clear ownership",
        "move the work forward",
        "calm senior judgment",
        "builder's mindset",
        "practical operating style",
        "recurring friction",
    ):
        if lowered_content.count(phrase) > 1:
            raise ApplicationMaterialError(
                f"Cover letter repeats the operating theme '{phrase}'."
            )


def _job_text(parsed_job: Dict[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in (parsed_job.get("job_title"), parsed_job.get("raw_text"))
    ).lower()


def _editorial_evidence_relevant(parsed_job: Dict[str, Any]) -> bool:
    text = _job_text(parsed_job)
    return any(
        signal in text
        for signal in (
            "content",
            "editorial",
            "community",
            "audience programming",
            "storytelling",
            "brand voice",
            "publication",
            "social media",
            "creator",
            "communications",
            "culture",
        )
    )


def _is_technical_operations_role(parsed_job: Dict[str, Any]) -> bool:
    text = _job_text(parsed_job)
    return any(
        signal in text
        for signal in (
            "technical project manager",
            "technical program manager",
            "project management",
            "product operations",
            "marketing operations",
            "martech",
            "adtech",
            "ad tech",
            "crm",
            "systems operations",
        )
    )


def _technical_operations_cover_letter_content(context: Dict[str, Any]) -> str:
    """Build four distinct paragraphs for TPM, martech, product-ops, and systems roles."""
    parsed_job = context["parsed_job"]
    company = str(parsed_job.get("company") or "the organization")
    role = str(parsed_job.get("job_title") or "technical operations role")
    text = _job_text(parsed_job)
    live_context = any(
        signal in text for signal in ("live entertainment", "ticketing", "concert", "fan experience", "axs", "aeg")
    )
    platform_focus = (
        "campaign, adtech, and martech systems"
        if any(signal in text for signal in ("martech", "adtech", "ad tech", "campaign", "marketing technology"))
        else "technical and operational systems"
    )
    opening = (
        f"The {role} role at {company} caught my attention because the work sits in the real operating "
        "space between strategy and delivery. Roles like this need someone who can make handoffs clear, "
        "keep reporting rhythms useful, and help creative, technical, and business partners understand "
        "what is needed next without turning the process into extra noise."
    )
    experience = (
        "At OMG23 / OMD Entertainment, I helped creative, marketing, media, analytics, technology, and "
        "operations teams coordinate Disney theatrical and streaming campaigns. The work required turning business "
        "requirements into executable plans, coordinating internal teams and external partners, managing "
        "dependencies, and giving senior stakeholders clear visibility into milestones, risks, and decisions. "
        "The pace was fast, but the processes still had to be practical enough for teams to trust and use."
    )
    fit = (
        f"As a supporting proof point, I also built CampaignOS around {platform_focus}: intake, validation, "
        "QA standards, operational risk flags, and reporting readiness. It reflects the same practical habit I bring "
        "to operations work: make dependencies visible, reduce avoidable rework, and give teams a shared "
        "view of the decisions that affect delivery."
    )
    adjacency = (
        " My entertainment background also gives me useful context for a live and fan-facing ecosystem where "
        "reliability affects both internal teams and the customer experience."
        if live_context
        else ""
    )
    closing = (
        f"I would welcome the chance to learn more about how {company} is shaping this work and where the "
        "team most needs stronger operating support. I can help strengthen delivery through practical "
        "operating discipline, visible milestones, surfaced risks, and useful decision routines that let stakeholders stay aligned "
        f"without slowing teams down.{adjacency} I care about leaving the team with a system that is clearer "
        "to operate, easier to question, and useful after the immediate delivery pressure has passed."
    )
    return _signed_content(opening, experience, fit, closing)


def _interpretation_aware_technical_cover_letter_content(context: Dict[str, Any]) -> str:
    """Ground technical-solutions and ad-tech letters in the confirmed function."""
    parsed = context["parsed_job"]
    company = str(parsed.get("company") or "the organization")
    role = str(parsed.get("job_title") or "technical solutions position")
    role_reference = role if role.lower().endswith((" role", " position")) else f"{role} role"
    interpretation = context.get("role_interpretation") or {}
    hiring_lens = context.get("hiring_manager_lens") or {}
    archetype = str(interpretation.get("primary_archetype") or "Technical Solutions / Solutions Consulting")
    if archetype == "Advertising Technology / Ad Operations":
        role_focus = (
            "advertising technology, advertiser problem-solving, measurement reliability, and partnership across sales, product, and engineering"
        )
    elif archetype == "Sales Engineering":
        role_focus = (
            "technical customer discovery, credible solution design, and partnership across sales, product, and engineering"
        )
    else:
        role_focus = (
            "technical products, customer problem-solving, implementation reliability, and partnership across sales, product, and engineering"
        )
    opening = (
        f"The {role_reference} at {company} caught my attention because it sits at the intersection of {role_focus}. "
        f"The posting appears to need a leader who can help make complex platform capabilities usable, resolve difficult technical blockers, and turn recurring advertiser issues into better support and product feedback. That is a more specific challenge than general operations, and it is the part of the role I find most compelling."
    )
    experience = (
        "At OMG23 / OMD Entertainment, Omnicom Media Group, I led campaign operations across Disney Studios Theatrical and Disney Streaming/DSS while working across creative, media, analytics, technology, and operations. My direct advertising technology work included Google and YouTube activation, CM360 and DV360 campaign implementation, trafficking and launch readiness, conversion tracking, measurement validation, QA, and technical troubleshooting for large entertainment advertisers. I translated platform requirements into decisions and workflows that kept delivery reliable under demanding launch timelines."
    )
    proof = (
        "I also supported server-to-server conversion API implementation from the business and campaign-operations side: clarifying requirements, coordinating the right technical partners, validating launch readiness, and troubleshooting measurement issues. Alongside that work, I led Supervisors, Senior Campaign Managers, Campaign Managers, and Coordinators and built validation and escalation practices that surfaced delivery risk earlier. That experience taught me how to partner across technical and business teams, solve advertiser implementation challenges, and build operational practices that improve delivery quality at scale while keeping teams aligned around clear owners, validation steps, and escalation paths."
    )
    closing_problem = str(hiring_lens.get("hiring_problem") or "make technical products reliable and usable for advertisers").rstrip(".")
    closing = (
        f"I would welcome the opportunity to contribute relevant advertising-platform experience, measurement and delivery discipline, and a practical approach to helping {company} {closing_problem[0].lower() + closing_problem[1:]}. I look forward to discussing how that experience can support the team's immediate goals."
    )
    return _signed_content(opening, experience, proof, closing)


def _role_sensitive_cover_letter_content(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    plan = context.get("material_editing_plan") or material_editing_plan(parsed_job, context.get("root"))
    category = plan.get("role_category")
    company = str(parsed_job.get("company") or "the organization")
    role = str(parsed_job.get("job_title") or "senior operations role")
    framing = plan.get("preferred_cover_letter_framing")
    preferred = ", ".join(plan.get("preferred_terms", [])[:4])

    if category == "chief_of_staff_business_operations":
        opening = (
            f"The {role} role at {company} caught my attention because senior team operating support is the work beneath the title. "
            f"{framing or 'I help senior teams turn broad priorities into clear plans, ownership, communication rhythms, and follow-through'} "
            "The role reads like one where planning rhythms, ownership clarity, stakeholder alignment, risk surfacing, and consistent follow-through matter more than adding process for its own sake."
        )
        experience = (
            "At OMG23 / OMD Entertainment, Omnicom Media Group, I connected creative, marketing, media, "
            "analytics, technology, and operations partners around Disney Studios Theatrical and Disney "
            "Streaming/DSS work. That required executive visibility, "
            "senior stakeholder support, decision tracking, quality standards, and communication routines that helped "
            "leaders understand what needed attention."
        )
        proof = (
            "As a supporting proof point, CampaignOS reflects how I think about operating systems: intake, workflow "
            "governance, QA checks, risk flags, and reporting readiness. I would keep that example brief here because "
            "the central qualification is the operating discipline behind it, not founder positioning or product-building detail."
        )
        closing = (
            f"I would welcome the chance to learn where {company}'s leadership team most needs clarity and traction. "
            "I would bring governance without bureaucracy, calm cross-functional alignment, and a bias toward translating "
            "priorities into execution that teams can actually sustain."
        )
        return _signed_content(opening, experience, proof, closing)

    if category == "product_ai_operations":
        opening = (
            f"The {role} role at {company} caught my attention because the product need is inseparable from usable operating systems: "
            "clear workflows, thoughtful schemas, feedback loops, and automation that leaves room for human judgment."
        )
        experience = (
            "I am the product owner and domain lead for a functioning AI-enabled career intelligence product. "
            "I defined the product vision, decomposed user and system failures into requirements and acceptance "
            "criteria, and designed the multi-stage workflow that connects role interpretation, evidence, scoring, "
            "generation, persistence, and quality checks. I directed implementation through Codex while retaining "
            "ownership of product decisions, evaluation, and user acceptance testing."
        )
        proof = (
            "The product includes human-in-the-loop review, evidence provenance, review and verification states, "
            "user confirmation and rejection controls, and safeguards that keep generated claims grounded in verified evidence. I built regression "
            "and qualitative evaluation around real job descriptions, then used failures to refine prompts, context, "
            "schemas, requirements, and test coverage. My work at OMG23 / Omnicom Media Group leading Disney "
            "campaign operations keeps that product judgment grounded in how people actually make decisions "
            "under delivery pressure."
        )
        lesson = (
            "I bring hands-on AI product ownership, workflow and requirements design, prompt and context design, "
            "human review, evaluation, safety review, Codex implementation direction, and UAT. That combination "
            "helps teams turn ambitious AI concepts into reliable product behavior people can understand and use."
        )
        closing = (
            f"I would welcome the chance to learn how {company} is shaping this product work and where the team "
            f"needs stronger {preferred or 'AI workflows, product judgment, workflow governance, and usable tools'}. "
            "I would bring hands-on AI product judgment and enterprise operations experience to keep the solution grounded."
        )
        return _signed_content(opening, experience, proof, lesson, closing)

    return ""


def _campaignos_is_relevant(context: Dict[str, Any]) -> bool:
    top_projects = context["match_report"].get("top_matching_projects", [])
    if any(project.get("name") == "CampaignOS" for project in top_projects):
        return True

    text = " ".join(
        str(value)
        for value in (
            context["parsed_job"].get("job_title", ""),
            *context["parsed_job"].get("keywords", []),
        )
    ).lower()
    return any(term in text for term in ("ai", "automation", "systems", "workflow", "product"))


def _default_cover_letter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title")
    job_focus = _job_focus(parsed_job)

    position = _position(career_data, "OMG23")
    position_company, position_shorthand = _employer_names(position)

    campaignos = _project(career_data, "CampaignOS")
    campaignos_summary = str(campaignos.get("summary", "")).strip()

    if role and is_google_youtube_role(parsed_job):
        opening_sentence = (
            f"The {role} role at {company} caught my attention because it brings {job_focus} together "
            "across a large advertiser ecosystem."
        )
    elif role:
        opening_sentence = (
            f"The {role} role at {company} caught my attention because it brings {job_focus} together "
            "in a global entertainment organization."
        )
    else:
        opening_sentence = (
            f"This opportunity at {company} caught my attention because it brings {job_focus} together "
            "in a global entertainment organization."
        )

    opening = (
        f"{opening_sentence} What caught my attention is the "
        "practical challenge behind the title: helping many functions turn complex priorities into "
        "clear workflows, aligned milestones, useful standards, and reliable execution. I have spent "
        "much of my career helping creative and marketing teams build that kind of clarity without "
        "slowing down the work."
    )

    if is_google_youtube_role(parsed_job):
        experience = (
            "Across agency and entertainment roles, I have translated Google and YouTube platform "
            "capabilities into campaign execution, "
            "measurement readiness, and operational workflows. At "
            f"{position_company}, that meant connecting brand objectives, platform activation, "
            "measurement, and delivery across large entertainment advertisers. Disney Studios "
            "Theatrical and Disney Streaming/DSS campaigns provide the premium advertiser scale and "
            "cross-functional operating complexity behind that experience."
        )
    else:
        experience = (
            "Much of my career has been spent helping creative, marketing, media, analytics, and "
            "technology teams bring structure to complex theatrical and streaming campaign ecosystems. "
            f"At {position_company}, my primary focus was Disney Studios Theatrical and Disney "
            "Streaming/DSS work, supporting campaign operations across Pixar, Lucasfilm, Marvel, 20th "
            "Century Studios, Searchlight Pictures, Disney+, and franchise/IP priorities. That work "
            "required close coordination across internal teams and external partners, with clear "
            "workflows, milestones, quality standards, and consistent execution at scale."
        )

    if _campaignos_is_relevant(context) and campaignos_summary:
        transformation = (
            f"The systems mindset I developed at {position_shorthand} also led me to build "
            f"CampaignOS. As {campaignos.get('role')}, I "
            f"{campaignos_summary[0].lower() + campaignos_summary[1:]} The project grew from a "
            "practical question I have encountered repeatedly: how can teams reduce manual effort "
            "and operational risk while improving visibility and decision-making? That mix of "
            "strategy, systems thinking, and hands-on execution is where I do my best work."
        )
    else:
        workflow = _achievement(career_data, "workflow_governance")
        transformation = (
            f"I have also focused on improving the systems behind the work. {_as_first_person(workflow)} "
            "That experience has shaped a practical approach to improving operations, "
            "with clear ownership, useful standards, and room for creative teams to do their best work."
        )

    if is_google_youtube_role(parsed_job):
        closing = (
            "What appeals to me about this opportunity is the chance to help Google translate "
            "YouTube Brand Auction and AI-powered campaign priorities into clear activation "
            "strategies, seller enablement, feedback loops, and measurable execution. I would "
            "welcome the chance to learn more about the role's priorities and discuss how my "
            "platform experience and operational approach could contribute."
        )
    elif _is_creative_product_operations_role(parsed_job):
        closing = (
            "What appeals to me about this opportunity is the chance to help creative and product "
            f"development teams at {company} turn entertainment IP and franchise priorities into "
            "clear, scalable operating rhythms. I would welcome the chance to learn more about the "
            "team's priorities and discuss how I could contribute."
        )
    else:
        closing = (
            f"What appeals to me about this opportunity is the chance to bring that experience into "
            f"{company} within a complex entertainment organization. I would welcome the chance "
            "to learn more about the team's priorities and discuss how I could contribute."
        )

    content = "\n\n".join(
        ["Hello,", opening, experience, transformation, closing, "Best,\n\nTrisha Lynch"]
    )
    _validate_cover_letter_repetition(content)
    return content


def _signed_content(*paragraphs: str) -> str:
    content = "\n\n".join(("Hello,", *paragraphs, "Best,\n\nTrisha Lynch"))
    _validate_cover_letter_repetition(content)
    return content


def _bandsintown_cover_letter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title") or "content strategy opportunity"
    position = _position(career_data, "OMG23")
    position_company, _position_shorthand = _employer_names(position)

    opening = (
        f"The {role} role at {company} caught my attention because it sits at the intersection of music, "
        "audience connection, and the kind of clear, human storytelling I keep returning to in my "
        "own work. The opportunity to move between artists, industry partners, and fans is especially "
        "compelling because each audience needs a distinct voice, but all of them can tell when the "
        "writing understands their world."
    )
    experience = (
        f"My background is unusual in a way that feels relevant here. At {position_company}, I led "
        "large-scale entertainment marketing work across creative, media, analytics, technology, and "
        "operations. That experience taught me how to find the human idea inside a busy campaign "
        "ecosystem, shape it for different audiences, and build enough structure around the work to "
        "keep quality high across many formats and deadlines. Music has remained a recurring creative "
        "language and point of community throughout that work."
    )
    proof = (
        "I have also built editorial projects from scratch. As creator and managing editor of "
        "Multiverse, I developed an internal publication around creativity, culture, music, and "
        "innovation, built a contributor framework, and reached an audience of 400+ employees. More "
        "recently, through my Substack, I have been writing about creativity, technology, AI, music, "
        "grief, and life after corporate leadership in a voice that is personal without losing structure. "
        "Those projects have strengthened my ability to write with voice, edit with care, and turn "
        "creative ideas into repeatable content systems without sanding away what makes them human."
    )
    closing = (
        f"I would value the chance to bring that mix of editorial judgment, music and audience "
        f"awareness, and operational discipline to {company}. The role feels like a place where "
        "creative instinct and the systems behind strong content are equally useful, which is exactly "
        "the balance I would value discussing."
    )
    return _signed_content(opening, experience, proof, closing)


def _disney_cover_letter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "Disney"
    role = parsed_job.get("job_title") or "strategy and operations opportunity"
    position = _position(career_data, "OMG23")
    position_company, position_shorthand = _employer_names(position)
    campaignos = _project(career_data, "CampaignOS")

    opening = (
        f"The {role} role at {company} caught my attention because it connects product and technology strategy "
        "with the operating rhythms that let a large entertainment enterprise make clear decisions "
        "and execute at scale. I understand the Disney ecosystem through hands-on campaign "
        "work, but what draws me to this role is forward-looking: helping product, engineering, data, "
        "and business partners turn shared priorities into useful OKRs, decisions, and momentum."
    )
    experience = (
        f"At {position_company}, my primary focus was Disney Studios Theatrical and Disney "
        "Streaming/DSS. I supported theatrical and streaming film campaign operations across Pixar, "
        "Lucasfilm, Marvel, 20th Century Studios, Searchlight Pictures, Disney+, and franchise/IP "
        "priorities. Working across creative, marketing, media, analytics, technology, and external "
        "partners taught me how enterprise entertainment decisions travel through a system, where "
        "dependencies surface, and how much executive clarity matters when many teams must move together."
    )
    proof = (
        f"That systems perspective also led me, after {position_shorthand}, to build CampaignOS. As "
        f"{campaignos.get('role') or 'Founder and Product Lead'}, I designed an AI-powered operations "
        "platform around workflow governance, quality assurance, validation, and operational visibility. "
        "The work required the same discipline this role calls for: translating broad goals into a "
        "practical operating model, defining useful signals, and making information easier for leaders "
        "and delivery teams to act on."
    )
    closing = (
        f"I would welcome a conversation about how {company} is shaping the operating system around "
        "its product and technology priorities. I would bring deep entertainment context, a practical "
        "approach to strategy operations, and respect for the scale and coordination the work requires."
    )
    return _signed_content(opening, experience, proof, closing)


def _google_cover_letter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "Google"
    role = parsed_job.get("job_title") or "GTM operations opportunity"
    position = _position(career_data, "OMG23")
    position_company, _position_shorthand = _employer_names(position)

    opening = (
        f"The {role} role at {company} caught my attention because it brings YouTube product activation, GTM "
        "operations, seller enablement, and large advertiser execution into one operating challenge. "
        "The interesting work is not simply introducing a product priority. It is creating the feedback "
        "loops, activation guidance, and measurement clarity that help sellers and advertisers use it "
        "well at scale."
    )
    experience = (
        f"At {position_company}, I translated Google and YouTube "
        "platform capabilities into campaign activation, measurement readiness, and operational "
        "workflows for large entertainment advertisers. Disney Studios Theatrical and Disney "
        "Streaming/DSS provided the scale behind that work, requiring alignment across brand goals, "
        "media strategy, analytics, technology, platform requirements, and senior stakeholders."
    )
    proof = (
        "CampaignOS is a current proof point for how I approach product and operational ambiguity. "
        "I designed the AI-powered platform to standardize workflow governance, automate quality "
        "assurance, and improve validation and reporting. Building it has sharpened my ability to "
        "turn recurring user needs into structured systems, identify useful signals, and create "
        "feedback that supports better product and execution decisions."
    )
    closing = (
        f"I would welcome the chance to learn how the {company} team is approaching YouTube Brand "
        "Auction activation and seller readiness. I would bring an advertiser-grounded perspective, "
        "product fluency, and a grounded approach to clear adoption and measurable learning."
        " I am comfortable moving between data, stakeholder context, and execution detail, especially "
        "when a product's success depends on many groups understanding the same priority clearly. "
        "The useful measure is whether that shared understanding changes adoption and execution."
    )
    return _signed_content(opening, experience, proof, closing)


def _paramount_cover_letter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "Paramount"
    role = parsed_job.get("job_title") or "marketing operations opportunity"
    position = _position(career_data, "OMG23")
    position_company, _position_shorthand = _employer_names(position)

    opening = (
        f"The {role} role at {company} caught my attention because marketing operations is the connective layer "
        "between strategy and creative production. In a high-volume entertainment environment, the "
        "real opportunity is to give teams clearer intake, capacity, priorities, and visibility so "
        "creative work can move with fewer avoidable handoffs and better decisions. That is practical, "
        "people-centered systems work, and it is where I have spent much of my career. I am drawn to "
        "the practical question of what teams need to see sooner so the next decision becomes easier."
    )
    experience = (
        f"At {position_company}, I helped creative management, marketing, media, analytics, technology, "
        "and operations partners coordinate Disney Studios Theatrical and Disney Streaming/DSS campaigns. There, "
        "I built workflows, milestones, quality practices, partner coordination, and execution standards "
        "for a demanding slate of theatrical releases, streaming launches, and franchise/IP priorities."
    )
    proof = (
        "I also built CampaignOS to address the systems behind recurring delivery challenges. The "
        "platform uses AI-enabled validation, workflow governance, dashboards, and operational reporting "
        "to reduce manual effort and improve visibility. That experience has reinforced my belief that "
        "useful enablement starts with the work itself: understanding creative capacity, clarifying "
        "ownership, and designing tools teams can actually use."
    )
    closing = (
        f"I would welcome the chance to learn how {company} is evolving its marketing operations model "
        "and where this role can create the most leverage for creative and business partners. I would "
        "bring entertainment scale, clear operational judgment, and a builder's approach to making the "
        "work easier to see and manage. The goal is not more process; it is better flow, clearer "
        "choices, and stronger creative delivery."
    )
    return _signed_content(opening, experience, proof, closing)


def _uta_cover_letter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "UTA"
    role = parsed_job.get("job_title") or "transformation opportunity"
    position = _position(career_data, "OMG23")
    position_company, _position_shorthand = _employer_names(position)

    opening = (
        f"The {role} role at {company} caught my attention because it asks for more than an internal process "
        "operator. It calls for someone who can understand a stakeholder's problem, form a clear "
        "hypothesis, shape an operating model, and communicate a recommendation that people can act "
        "on. That combination of advisory thinking and practical execution fits how I have worked "
        "across media, marketing, advertising, and technology."
    )
    experience = (
        f"At {position_company}, I aligned senior stakeholders, cross-functional teams, and external "
        "partners around complex entertainment marketing work. "
        "I learned to move between executive context and delivery detail: clarify the decision, map "
        "dependencies, surface risk, and translate competing priorities into workflows and standards. "
        "That work required client-facing communication, sound judgment, and recommendations grounded "
        "in the realities of teams responsible for execution."
    )
    proof = (
        "Building CampaignOS extended that transformation work into a product. I took a recurring "
        "organizational problem, developed a point of view about its root causes, and designed an "
        "AI-powered operating system for governance, validation, quality, and reporting. The process "
        "has strengthened the same muscles useful in advisory work: structured discovery, hypothesis-driven "
        "problem solving, stakeholder empathy, and turning strategy into an implementable model."
    )
    closing = (
        f"I would welcome the chance to discuss how {company} approaches transformation across its "
        "clients and business. I would bring an operator's fluency in the media ecosystem, an advisory "
        "mindset, and the discipline to carry a recommendation through to measurable execution. I am "
        "at my best when the answer must be both strategically sound and workable for the people "
        "responsible for delivering it."
    )
    return _signed_content(opening, experience, proof, closing)


def _people_operations_cover_letter_content(context: Dict[str, Any]) -> str:
    """Translate verified operations evidence without relabeling it as HR experience."""
    parsed_job = context["parsed_job"]
    company = str(parsed_job.get("company") or "the organization")
    role = str(parsed_job.get("job_title") or "People Operations role")
    opening = (
        f"What interests me about the {role} role at {company} is the opportunity to improve "
        "how people experience the way an organization works. Much of my career has focused on "
        "listening to teams, noticing where ownership or communication is breaking down, and "
        "building practical structures that help people work together more effectively. The posting's "
        "focus on cross-functional programs, usable systems, clear reporting, and team effectiveness "
        "makes that connection especially relevant."
    )
    experience = (
        f"During my time at {OMG23_DISPLAY_NAME}, I led cross-functional teams and partnered across "
        "marketing, technology, analytics, creative, media, and operations. The business context was "
        "entertainment marketing, but the day-to-day questions were human ones: Do people understand "
        "what is expected? Is ownership clear? Can teams make decisions and navigate change without "
        "adding unnecessary friction? I introduced workflows, responsibilities, quality standards, "
        "and communication practices that made handoffs more dependable and gave teams a shared way "
        "to work through demanding priorities."
    )
    transfer = (
        "I bring a practical understanding of how change is adopted: listen to the people closest "
        "to the work, find the recurring friction, document expectations clearly, and build only enough "
        "structure to help teams use the change in their daily work. I have learned that consistency "
        "comes from trust and clarity, not from adding process for its own sake."
    )
    closing = (
        f"I would bring {company} a thoughtful, people-centered operating approach, grounded in team "
        "leadership, cross-functional partnership, and practical implementation. I would be glad to "
        "help the People team turn business priorities into programs and ways of working that teams "
        "can understand, adopt, and sustain."
    )
    return _signed_content(opening, experience, transfer, closing)


def _fieldai_cover_letter_content(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "FieldAI"
    role = parsed_job.get("job_title") or "operations systems opportunity"

    opening = (
        f"The {role} role at {company} caught my attention because matrix operations becomes consequential when "
        "a fast-moving organization needs to scale without losing clarity. The challenge is to create "
        "shared cadences, capacity visibility, and decision paths that help teams move faster, not to "
        "layer corporate process onto them. That tension between speed and operating discipline is one "
        "I know well."
    )
    experience = (
        "I have designed operating practices across marketing, creative, analytics, technology, and "
        "delivery functions, coordinating teams of more than 60 people when the work required it. My work has included capacity and "
        "workflow planning, governance, quality systems, dashboards, partner coordination, and executive "
        "visibility. Much of that experience was built in entertainment around an organizational "
        "problem: making ownership, dependencies, risk, and progress visible across "
        "a matrix without slowing down the people doing the work."
    )
    proof = (
        "CampaignOS is the clearest expression of my systems approach. I designed and developed the "
        "AI-powered operations platform to standardize workflows, automate quality assurance, reduce "
        "operational risk, and improve reporting. Building it required product thinking, schema design, "
        "validation frameworks, and a pragmatic view of where automation helps versus where human "
        "judgment still matters."
    )
    closing = (
        f"I would welcome the chance to learn where {company} sees the greatest friction across its "
        "matrix today. I would bring hands-on systems thinking, comfort with ambiguity, and a practical "
        "approach to organizational efficiency that connects operating cadences, data, automation, and "
        "accountable execution. I also understand that systems earn trust through use. The measures, "
        "dashboards, and routines have to help technical and business teams make faster decisions, "
        "not merely document activity."
    )
    return _signed_content(opening, experience, proof, closing)


def _crunchyroll_cover_letter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "Crunchyroll"
    role = parsed_job.get("job_title") or "streaming strategy opportunity"
    position = _position(career_data, "OMG23")
    position_company, _position_shorthand = _employer_names(position)

    opening = (
        f"The {role} role at {company} caught my attention because it connects streaming, fandom, franchise/IP, "
        "and enterprise strategy. The meaningful challenge is turning the energy around content "
        "and audience communities into clear priorities that creative and marketing teams can execute. "
        "That balance matters in fandom businesses: the operating model needs rigor, but it also needs "
        "to stay close to why the audience cares."
    )
    experience = (
        f"At {position_company}, I led entertainment campaign work across Disney Studios Theatrical "
        "and Disney Streaming/DSS, supporting theatrical releases, streaming launches, and franchise/IP "
        "priorities. I worked across creative, media, analytics, technology, and external partners to "
        "translate business goals into milestones, quality standards, measurement readiness, and reliable "
        "execution. That experience taught me how strategy becomes useful across a content ecosystem "
        "with different brands, audiences, release patterns, and stakeholder needs."
    )
    proof = (
        "CampaignOS grew from the same instinct to make complicated work easier to navigate. I designed "
        "the AI-powered platform around workflow governance, quality assurance, validation, and reporting, "
        "creating a clearer system for teams to make decisions and execute consistently. The project "
        "reflects how I approach enterprise strategy: understand the human and operational context, then "
        "build structure that helps the organization move."
    )
    closing = (
        f"I would welcome the chance to learn how {company} is approaching its next set of enterprise "
        "priorities. I would bring streaming and entertainment context, respect for fandom, and a "
        "practical ability to connect strategy with the systems and people responsible for execution."
        " I value doing that work with focus, curiosity, and care."
    )
    return _signed_content(opening, experience, proof, closing)


def _dynamic_cover_letter_content(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    effective = context.get("effective_voice_profile", context.get("profile", {}))
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title") or "senior operations opportunity"
    role_family = str(effective.get("role_family") or "generic_senior_operator")
    angles = effective.get("cover_letter_angle", [])
    angle = str(angles[-1] if angles else "connect the role's stated priorities with clear execution").rstrip(".")

    opening = (
        f"For the {role} role at {company}, I would start with the operating need behind the description: "
        f"{angle}. My most relevant experience is helping people with different priorities reach clear "
        "decisions, understand ownership, and keep useful momentum without losing the purpose behind the work."
    )

    editorial_relevant = _editorial_evidence_relevant(parsed_job)
    if role_family in {"editorial_content_strategy", "community_growth"} and editorial_relevant:
        experience = (
            "My experience combines large-scale entertainment marketing with editorial and community "
            "work. I created and managed Multiverse, an internal publication focused on creativity, "
            "culture, innovation, music, and employee storytelling, and built a contributor framework "
            "that reached 400+ employees. Through my Substack, I continue to develop a personal voice "
            "across creativity, technology, AI, music, grief, and life after corporate leadership."
        )
    elif role_family in {"product_strategy_ops", "gtm_product_activation"}:
        experience = (
            "At OMG23 / OMD Entertainment, Omnicom Media Group, I worked across business priorities, "
            "platform activation, analytics, technology, measurement, and delivery for large entertainment "
            "campaigns. I learned to translate broad goals into practical plans, surface dependencies, "
            "create feedback loops, and give senior stakeholders enough visibility to make sound decisions. "
            "That experience is directly relevant when adoption depends on many functions moving together."
        )
    else:
        experience = (
            "At OMG23 / OMD Entertainment, Omnicom Media Group, I built workflows, governance practices, "
            "quality standards, and executive visibility across creative, marketing, media, analytics, technology, "
            "and operations. The systems supported cross-functional teams of more than 60 people and gave them "
            "visibility for demanding entertainment work. Across functions, the recurring operating challenge "
            "was to create clarity and consistency without slowing the team down."
        )

    selected_ids = {str(card.get("id")) for card in context.get("selected_evidence_cards", [])}
    evidence_stories = []
    for card in context.get("selected_evidence_cards", []):
        proof_points = [
            str(value).strip()
            for value in card.get("proof_points") or []
            if str(value).strip()
        ]
        if proof_points:
            evidence_stories.append(_as_first_person(proof_points[0]))
        if len(evidence_stories) == 2:
            break
    if role_family in {"editorial_content_strategy", "community_growth"} and editorial_relevant:
        proof = (
            "Those editorial projects strengthened more than my writing. They required content planning, "
            "audience judgment, contributor management, repeatable workflows, and care for tone across different "
            "formats. They also reinforced a principle I bring to operational work: systems should make good "
            "creative decisions easier without flattening the human voice that gives the work meaning."
        )
    elif "campaignos" in selected_ids:
        proof = (
            "CampaignOS is a current proof point for that approach. I designed and developed the AI-powered "
            "operations platform to standardize workflow governance, automate quality assurance, reduce risk, "
            "and improve reporting. Building it required product thinking, schema design, validation frameworks, "
            "and practical judgment about where automation can help. That work strengthened my ability to turn "
            "an operating problem into a usable product with clear validation and review controls."
        )
    elif evidence_stories:
        proof = " ".join(evidence_stories)
    else:
        proof = (
            "I would bring governance practices, quality standards, clearer handoffs, and executive "
            "visibility for teams working under real delivery pressure. My approach is to make decisions "
            "and ownership clearer while building only the amount of process a team can trust and use."
        )

    closing = (
        f"I would welcome the opportunity to discuss the {role} role at {company} and how my "
        "systems-minded, practical approach could help the team do its best work."
    )
    return _signed_content(opening, experience, proof, closing)


def _cover_letter_content(context: Dict[str, Any]) -> str:
    profile_key = context.get("profile_key", "default")
    role_family = context.get("role_family")
    builders = {
        "disney": _disney_cover_letter_content,
        "google_youtube": _google_cover_letter_content,
        "paramount": _paramount_cover_letter_content,
        "uta": _uta_cover_letter_content,
        "fieldai": _fieldai_cover_letter_content,
        "bandsintown": _bandsintown_cover_letter_content,
        "crunchyroll": _crunchyroll_cover_letter_content,
    }
    if not context.get("material_editing_plan"):
        context = dict(context)
        context["material_editing_plan"] = material_editing_plan(context["parsed_job"], context.get("root"))
    builder: Callable[[Dict[str, Any]], str]
    interpreted_archetype = str(
        (context.get("role_interpretation") or {}).get("primary_archetype") or ""
    )
    # A confirmed people-operations lens is more specific than company defaults;
    # otherwise known company voices outrank generic technical archetypes.
    if context.get("role_lens", {}).get("primary") == "people_operations":
        builder = _people_operations_cover_letter_content
    elif profile_key in builders:
        builder = builders[profile_key]
    elif interpreted_archetype in TECHNICAL_ARCHETYPES:
        builder = _interpretation_aware_technical_cover_letter_content
    else:
        role_category = context["material_editing_plan"].get("role_category")
        if role_category in {"chief_of_staff_business_operations", "product_ai_operations"}:
            builder = _role_sensitive_cover_letter_content
        elif role_family == "music_content_strategy":
            builder = _bandsintown_cover_letter_content
        elif _is_creative_product_operations_role(context["parsed_job"]):
            builder = _default_cover_letter_content
        elif _is_technical_operations_role(context["parsed_job"]):
            builder = _technical_operations_cover_letter_content
        else:
            effective = context.get("effective_voice_profile", {})
            has_job_context = any(
                parsed_value
                for parsed_value in (
                    context["parsed_job"].get("company"),
                    context["parsed_job"].get("job_title"),
                    str(context["parsed_job"].get("raw_text") or "").strip(),
                )
            )
            builder = (
                _default_cover_letter_content
                if effective.get("company_category") == "gaming_fandom"
                else _dynamic_cover_letter_content
                if effective.get("source") == "dynamic_inference" and has_job_context
                else _default_cover_letter_content
            )
    content = replace_personal_project_paragraphs(
        builder(context), _professional_evidence_paragraph(context)
    )
    content = normalize_applicant_employer_names(content)
    parsed = context.get("parsed_job") or {}
    content, advocacy_review = rewrite_public_advocacy(
        content,
        company=str(parsed.get("company") or "the organization"),
        role=str(parsed.get("job_title") or "the role"),
        transparency_requested=bool(context.get("public_transparency_requested")),
    )
    context["public_advocacy_review"] = advocacy_review
    validate_public_advocacy(
        content,
        "cover letter",
        transparency_requested=bool(context.get("public_transparency_requested")),
    )
    validate_applicant_evidence(content, "cover letter")
    return content


def generate_cover_letter(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    package_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate and save a concise TXT cover letter with safe DOCX when available."""
    context = load_generation_context(job_path, project_root, package_context)
    result = save_material(
        context,
        "Cover_Letter",
        _cover_letter_content(context),
        minimum_words=250,
        maximum_words=400,
        repair_content=repair_cover_letter_content,
        repair_attempts=3,
    )
    markdown_path = Path(result["output_path"])
    markdown = markdown_path.read_text(encoding="utf-8")
    plain_text = re.sub(r"^#{1,6}\s+", "", markdown, flags=re.MULTILINE)
    plain_text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain_text)
    plain_text = plain_text.replace("**", "")
    text_path = markdown_path.with_suffix(".txt")
    text_path.write_text(plain_text, encoding="utf-8")
    result["txt_output_path"] = str(text_path)
    try:
        docx_path = _export_cover_letter_docx(context, plain_text, markdown_path)
    except Exception as error:
        # DOCX is a user-facing convenience; Markdown and TXT remain usable if it fails.
        result["docx_error"] = f"DOCX missing / unsupported: {error}"
    else:
        result["docx_output_path"] = str(docx_path)
    return result


def _export_cover_letter_docx(
    context: Dict[str, Any], plain_text: str, markdown_path: Path
) -> Path:
    """Export a restrained, application-ready DOCX using explicit business-letter tokens."""
    document = Document()
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = RGBColor(0x20, 0x27, 0x2D)
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    normal.paragraph_format.line_spacing = 1.10

    for block in re.split(r"\n\s*\n", plain_text.strip()):
        paragraph = document.add_paragraph()
        lines = block.splitlines()
        for index, line in enumerate(lines):
            if index:
                paragraph.add_run().add_break()
            paragraph.add_run(line)
        paragraph.paragraph_format.keep_together = True

    docx_path = markdown_path.with_suffix(".docx")
    document.save(docx_path)
    parsed_job = context.get("parsed_job") or {}
    role = str(parsed_job.get("job_title") or "Role")
    company = str(parsed_job.get("company") or "Company")
    clean_docx_metadata(
        docx_path,
        title=f"Trisha Lynch - {role} Cover Letter",
        subject=f"{role} at {company}",
    )
    return docx_path
