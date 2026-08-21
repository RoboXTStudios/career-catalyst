"""Generate grounded cover letters from Career Catalyst data and job analysis."""

import re
from html import unescape
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

try:
    from .docx_quality import sanitize_docx
    from .candidate_output import (
        candidate_cover_letter,
        cover_letter_evidence_decision,
        cover_letter_evidence_selection,
    )
    from .career_claims import (
        PublicCareerClaimError,
        is_ai_transformation_role,
        leadership_claim,
        public_omg23_name,
        validate_public_career_claims,
    )
    from .company_voice import company_voice_context
    from .evidence_engine import evidence_generation_context, load_evidence_cards, load_writing_voice_profile, select_evidence_cards
    from .evidence_tailoring import (
        candidate_project_reference_violations,
        cover_letter_project_paragraph,
        project_kind,
        project_title,
        public_artifact_selection,
    )
    from .filename_utils import build_upload_filename, company_display_name
    from .resume_foundation import (
        CandidateLanguageError,
        candidate_language_violations,
        load_resume_foundation,
        validate_candidate_language,
    )
    from .parse_job import parse_job_description
    from .package_context import validate_material_context
    from .role_context import (
        google_claim_violations,
        is_google_youtube_role,
    )
    from .role_editing import (
        material_editing_plan,
        remaining_banned_voice_phrases,
        rewrite_banned_voice_phrases,
    )
    from .score_match import score_job_match
    from .text_cleanup import (
        cleanup_repeated_words,
        missing_subject_prose_fragments,
        normalize_candidate_text,
    )
    from .role_intent import build_role_intent
except ImportError:
    from docx_quality import sanitize_docx
    from candidate_output import (
        candidate_cover_letter,
        cover_letter_evidence_decision,
        cover_letter_evidence_selection,
    )
    from career_claims import (
        PublicCareerClaimError,
        is_ai_transformation_role,
        leadership_claim,
        public_omg23_name,
        validate_public_career_claims,
    )
    from company_voice import company_voice_context
    from evidence_engine import evidence_generation_context, load_evidence_cards, load_writing_voice_profile, select_evidence_cards
    from evidence_tailoring import (
        candidate_project_reference_violations,
        cover_letter_project_paragraph,
        project_kind,
        project_title,
        public_artifact_selection,
    )
    from filename_utils import build_upload_filename, company_display_name
    from resume_foundation import (
        CandidateLanguageError,
        candidate_language_violations,
        load_resume_foundation,
        validate_candidate_language,
    )
    from parse_job import parse_job_description
    from package_context import validate_material_context
    from role_context import google_claim_violations, is_google_youtube_role
    from role_editing import (
        material_editing_plan,
        remaining_banned_voice_phrases,
        rewrite_banned_voice_phrases,
    )
    from score_match import score_job_match
    from text_cleanup import cleanup_repeated_words, missing_subject_prose_fragments, normalize_candidate_text
    from role_intent import build_role_intent


PathInput = Union[str, Path]


class ApplicationMaterialError(Exception):
    """Raised when an application material cannot be generated safely."""


def load_generation_context(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
    role_intent: Optional[Dict[str, Any]] = None,
    parsed_job_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load career data, parsed job details, and the match report."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    resolved_job_path = Path(job_path)
    if not resolved_job_path.is_absolute():
        resolved_job_path = root / resolved_job_path

    career_data = load_resume_foundation(root)
    parsed_job = dict(
        parsed_job_override
        if parsed_job_override is not None
        else parse_job_description(resolved_job_path)
    )
    for field in ("job_title", "company", "role"):
        if field in parsed_job and parsed_job[field] is not None:
            parsed_job[field] = unescape(str(parsed_job[field]))
    voice_context = company_voice_context(
        parsed_job,
        career_data["config"].get("company_voice_profiles", {}),
    )
    parsed_job = dict(parsed_job)
    parsed_job["company_legal_name"] = parsed_job.get("company")
    parsed_job["company"] = company_display_name(parsed_job.get("company"))
    evidence_cards = load_evidence_cards(root)
    writing_voice = load_writing_voice_profile(root)
    selected_evidence = select_evidence_cards(parsed_job, evidence_cards)
    # An explicit non-empty tracker selection is the provenance boundary. An
    # empty legacy pool retains the established system-recommended behavior.
    evidence_scope_enforced = bool(associated_evidence_projects)
    associated_evidence_projects = associated_evidence_projects or []
    shared_role_intent = role_intent or build_role_intent(parsed_job, root)
    editing_plan = material_editing_plan(parsed_job, root, shared_role_intent)
    context = {
        "root": root,
        "career_data": career_data,
        "voice": career_data["config"].get("voice", {}),
        "writing_voice": writing_voice,
        "evidence_cards": evidence_cards,
        "selected_evidence_cards": selected_evidence,
        "associated_evidence_projects": associated_evidence_projects,
        "evidence_scope_enforced": evidence_scope_enforced,
        "associated_evidence_context": evidence_generation_context(associated_evidence_projects),
        "material_editing_plan": editing_plan,
        "role_intent": shared_role_intent,
        "parsed_job": parsed_job,
        "match_report": score_job_match(job_path, root, associated_evidence_projects),
        **voice_context,
    }
    context["cover_letter_evidence_selection"] = cover_letter_evidence_decision(
        context, limit=2
    )
    return context


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
    raw_violations = candidate_language_violations(content)
    if raw_violations:
        raise ApplicationMaterialError(
            "Generated material violates the Golden Master candidate-language policy: "
            + ", ".join(raw_violations)
        )
    employer = str(context.get("parsed_job", {}).get("company") or "")
    content = normalize_candidate_text(content, employer=employer)
    artifact_type = {
        "Cover_Letter": "cover_letter",
        "Application_Note": "application_note",
        "Recruiter_Message": "recruiter_message",
        "Hiring_Manager_Message": "hiring_manager_message",
    }.get(suffix, suffix.lower())
    provenance_violations = candidate_project_reference_violations(
        content, context, artifact_type
    )
    if provenance_violations:
        raise ApplicationMaterialError(
            f"Generated {suffix} references unselected Evidence/project(s): "
            + ", ".join(provenance_violations)
            + ". Select the project for this artifact or record an allowed fallback."
        )
    content = cleanup_repeated_words(content, employer=employer)
    rewrite_notes: list[dict[str, str]] = []
    content, initial_rewrites = rewrite_banned_voice_phrases(content)
    rewrite_notes.extend(initial_rewrites)
    word_count = _word_count(content)
    attempts = 0
    while not minimum_words <= word_count <= maximum_words and repair_content and attempts < repair_attempts:
        content = cleanup_repeated_words(
            repair_content(content, context), employer=employer
        )
        content = normalize_candidate_text(content, employer=employer)
        content, attempt_rewrites = rewrite_banned_voice_phrases(content)
        rewrite_notes.extend(attempt_rewrites)
        word_count = _word_count(content)
        attempts += 1
    content = normalize_candidate_text(content, employer=employer)
    provenance_violations = candidate_project_reference_violations(
        content, context, artifact_type
    )
    if provenance_violations:
        raise ApplicationMaterialError(
            f"Generated {suffix} references unselected Evidence/project(s): "
            + ", ".join(provenance_violations)
            + ". Select the project for this artifact or record an allowed fallback."
        )
    if "—" in content:
        raise ApplicationMaterialError("Generated application materials must not contain em dashes.")
    if "placeholder" in content.lower():
        raise ApplicationMaterialError("Generated application materials must not contain placeholder text.")
    if suffix in {"Cover_Letter", "Application_Note"}:
        fragments = missing_subject_prose_fragments(content)
        if fragments:
            raise ApplicationMaterialError(
                f"Generated {suffix} contains prose without an explicit subject: {fragments[0]}"
            )

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
    try:
        validate_candidate_language(content, context=f"Generated {suffix}")
        validate_public_career_claims(content)
    except (CandidateLanguageError, PublicCareerClaimError) as error:
        raise ApplicationMaterialError(str(error)) from error

    if not minimum_words <= word_count <= maximum_words:
        raise ApplicationMaterialError(
            f"Generated {suffix} must be {minimum_words}-{maximum_words} words; got {word_count}."
        )

    validate_material_context(content, context["parsed_job"], suffix)

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
    }


def _cover_letter_value_sentences(context: Dict[str, Any]) -> List[str]:
    parsed_job = context.get("parsed_job", {})
    company = str(parsed_job.get("company") or "the team")
    role_family = str(context.get("role_family") or "business_operations")
    intent_family = str(
        (context.get("role_intent") or {}).get("package_role_family") or ""
    )
    if intent_family == "strategy_gtm_operations":
        return [
            "I would apply that discipline to planning cadence, workflow quality, executive reporting, and the handoffs that connect teams.",
            "My goal is to make progress visible while keeping recommendations close to verified operating experience.",
            "I value practical systems that improve decisions without adding process that teams cannot sustain.",
        ]
    if intent_family == "music_partnerships_label_relations":
        return [
            "I would bring careful preparation, clear communication, and consistent follow-through to partner coordination.",
            "I value release readiness that respects creative voice and the specialized relationship knowledge already on the team.",
            "My approach is organized, collaborative, and attentive to the details that make shared delivery dependable.",
        ]
    if intent_family == "experiential_live_event_production":
        return [
            "I would bring structured planning, visible timelines, clear ownership, and steady coordination to activation work.",
            "I value practical support that helps creative and production partners stay aligned as delivery details change.",
            "My approach keeps the operating foundation clear while respecting the specialized expertise of the event team.",
        ]
    if intent_family:
        return [
            "I would apply that discipline to the role's stated priorities, with clear decisions, visible dependencies, and practical follow-through.",
            "I value operating systems that improve quality and momentum without adding process teams cannot sustain.",
            "My approach is grounded in direct experience, clear communication, and respect for the people closest to the work.",
            "I would begin by learning how the team coordinates priorities today, where decisions lose context, and which operating improvements would make delivery clearer without disrupting what already works.",
            "That approach keeps recommendations practical, proportionate, and accountable to the people responsible for execution.",
        ]
    role_sentence = {
        "creative_marketing_ops": "I know how much strong creative work depends on clear intake, thoughtful prioritization, and practical systems that help teams protect quality under pressure.",
        "business_operations": "My best work has been making complex operations easier to see and run, with clear ownership, useful decision rhythms, and systems people can actually maintain.",
        "product_strategy_ops": "I am comfortable translating product and business priorities into roadmaps, decisions, feedback loops, and operating rhythms that keep cross-functional work moving.",
        "product_marketing": "I connect audience insight and product value with clear positioning, messaging, launch readiness, enablement, and adoption across cross-functional teams.",
        "ai_operations_systems": "I build AI-enabled workflows with a practical bias: reduce repetitive work, surface risks earlier, and leave important judgment with the people closest to the work.",
    }.get(
        role_family,
        "I bring a practical operating style: listen closely, clarify the real constraint, and build enough structure for people to move with confidence.",
    )
    return [
        role_sentence,
        f"That is the perspective I would bring to {company}, along with calm stakeholder leadership and a habit of turning recurring friction into a clearer, more dependable way of working.",
        "The through line in my experience is building operating conditions that help people make sound decisions, protect quality, and deliver dependable work.",
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
    existing = re.sub(r"\s+", " ", str(content or "")).strip().lower()
    for sentence in _cover_letter_value_sentences(context):
        normalized = re.sub(r"\s+", " ", sentence).strip().lower()
        if normalized and normalized in existing:
            continue
        additions.append(sentence)
        if _word_count(content + "\n\n" + " ".join(additions)) >= target:
            break
    if not additions:
        return content
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
    role_family = str(
        (context.get("role_intent") or {}).get("package_role_family")
        or (context.get("role_intelligence") or {}).get("role_family")
        or ""
    )
    minimum = 300 if role_family in {
        "strategy_gtm_operations", "music_partnerships_label_relations"
    } else 250
    if count < minimum:
        return _expand_cover_letter(content, context, target=minimum + 10)
    if count > 400:
        return _trim_cover_letter(content)
    return content


def _remove_repeated_dynamic_closing(content: str, context: Dict[str, Any]) -> str:
    """Remove the generic operating-style paragraph from dynamic letters only."""
    role_family = str(
        (context.get("role_intent") or {}).get("package_role_family")
        or (context.get("role_intelligence") or {}).get("role_family")
        or ""
    )
    if role_family not in {
        "strategy_gtm_operations",
        "music_partnerships_label_relations",
        "experiential_live_event_production",
        "product_strategy_ops",
        "product_marketing",
        "product_operations",
        "gtm_product_activation",
        "ai_operations_systems",
    }:
        return content
    generic_markers = (
        "i bring a practical operating style:",
        "the through line in my experience is building operating conditions",
    )
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", str(content or "").strip())
        if paragraph.strip()
    ]
    return "\n\n".join(
        paragraph
        for paragraph in paragraphs
        if not any(marker in paragraph.lower() for marker in generic_markers)
    )


def _ground_cover_letter_in_selected_evidence(
    content: str, context: Dict[str, Any]
) -> str:
    """Keep the established narrative while making selected proof explicit."""
    decision = context.get("cover_letter_evidence_selection") or {}
    projects = list(decision.get("used_projects") or [])
    existing_text = str(content or "").lower()

    def already_allocated(project: Dict[str, Any]) -> bool:
        aliases = {
            str(project.get("id") or "").strip().lower(),
            project_title(project).strip().lower(),
        }
        if project_kind(project) == "podcast":
            aliases.add("just for us")
        if project_kind(project) == "career_catalyst":
            aliases.add("career catalyst")
        return any(alias and alias in existing_text for alias in aliases)

    evidence_paragraphs = [
        paragraph
        for project in projects
        if not already_allocated(project)
        and (paragraph := cover_letter_project_paragraph(project, context["parsed_job"]))
    ]
    if not evidence_paragraphs:
        return content

    paragraphs = [
        part.strip() for part in re.split(r"\n\s*\n", str(content or "").strip()) if part.strip()
    ]
    greeting = paragraphs.pop(0) if paragraphs and _word_count(paragraphs[0]) <= 5 else ""
    signoff: List[str] = []
    while paragraphs and (
        re.match(r"^(?:Sincerely|Best|Warmly|Thank you)\b", paragraphs[-1], re.I)
        or _word_count(paragraphs[-1]) <= 4
    ):
        signoff.insert(0, paragraphs.pop())

    evidence_titles = [project_title(project).lower() for project in projects]
    narrative = [
        paragraph
        for paragraph in paragraphs
        if not any(title and title in paragraph.lower() for title in evidence_titles)
    ]
    opening_context = narrative[:2]
    role_family = str(
        (context.get("role_intent") or {}).get("package_role_family")
        or (context.get("role_intelligence") or {}).get("role_family")
        or ""
    )
    # Dynamic role letters carry additional role-specific transfer paragraphs;
    # established archetype letters retain their concise historical shape.
    remaining_narrative = (
        narrative[2:]
        if role_family in {
            "strategy_gtm_operations",
            "music_partnerships_label_relations",
            "experiential_live_event_production",
        }
        else []
    )
    grounded = [
        value
        for value in (
            greeting,
            *opening_context,
            *evidence_paragraphs,
            *remaining_narrative,
            *signoff,
        )
        if value
    ]
    return "\n\n".join(grounded)


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
    full_name = str(position.get("company") or "OMG23 / OMD Entertainment, Omnicom Media Group")
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
        f"At {public_omg23_name(context.get('career_data', {}))}, I progressed to Group Director. I "
        f"{leadership_claim(context.get('career_data', {}))}. Supporting Disney theatrical and streaming campaigns required turning business "
        "requirements into executable plans, coordinating internal teams and external partners, managing "
        "dependencies, and giving senior stakeholders clear visibility into milestones, risks, and decisions. "
        "The pace was fast, but the processes still had to be practical enough for teams to trust and use."
    )
    fit = (
        f"As a supporting proof point, I also built CampaignOS around {platform_focus}: intake, validation, "
        "QA standards, risk flags, and reporting readiness. It reflects the same practical habit I bring "
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
        f"without slowing teams down.{adjacency}"
    )
    return _signed_content(opening, experience, fit, closing)


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
            f"For the {role} role at {company}, I would lead with senior team operating support. "
            f"{framing or 'I help senior teams turn broad priorities into clear plans, ownership, communication rhythms, and follow-through'} "
            "The role reads like one where planning rhythms, ownership clarity, stakeholder alignment, risk surfacing, and consistent follow-through matter more than adding process for its own sake."
        )
        experience = (
            f"At {public_omg23_name(context.get('career_data', {}))}, I progressed to Group Director. I "
            f"{leadership_claim(context.get('career_data', {}))}. "
            "Supporting Disney Studios Theatrical and Disney Streaming/DSS work required executive visibility, "
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
            f"For the {role} role at {company}, I would connect the product need to usable operating systems: "
            "clear workflows, thoughtful schemas, feedback loops, and automation that leaves room for human judgment."
        )
        experience = (
            "CampaignOS is the most relevant proof point for that work. I designed and developed an AI-powered "
            "operations platform around schema-driven workflows, validation frameworks, workflow governance, QA, "
            "risk flags, and operational reporting. The work required product judgment: translating recurring "
            "business needs into tools that make execution easier to understand and maintain."
        )
        proof = (
            "My Disney and OMG23 background gives that product work its operating context. I led cross-functional "
            "entertainment campaign teams through complex handoffs, stakeholder needs, measurement readiness, "
            "quality standards, dependencies, and delivery routines where tools only mattered if teams could use them."
        )
        closing = (
            f"I would welcome the chance to learn how {company} is shaping this product work and where the team "
            f"needs stronger {preferred or 'AI workflows, product judgment, workflow governance, and usable tools'}. "
            "I would bring both builder range and the enterprise operations experience to keep the solution grounded."
        )
        return _signed_content(opening, experience, proof, closing)

    return ""


def _evidence_project(context: Dict[str, Any], project_id: str) -> Dict[str, Any]:
    projects = context["career_data"]["data"].get("evidence_projects", {}).get(
        "evidence_projects", []
    )
    return next((item for item in projects if item.get("id") == project_id), {})


def _ai_transformation_cover_letter_content(context: Dict[str, Any]) -> str:
    """Ground AI-transformation positioning in adoption and operating evidence."""
    parsed_job = context["parsed_job"]
    company = str(parsed_job.get("company") or "the organization")
    role = str(parsed_job.get("job_title") or "AI transformation role")
    career_data = context["career_data"]
    catalyst = _project(career_data, "Career Catalyst")
    campaignos = _project(career_data, "CampaignOS")
    airtable = _evidence_project(context, "operational_workflow_design_airtable_implementation")
    teams = _evidence_project(
        context, "enterprise_collaboration_platform_adoption_stakeholder_enablement"
    )

    opening = (
        f"The {role} role at {company} fits work I am already doing: transforming Marketing "
        "operations and building AI-enabled operating systems that move from a clear hypothesis "
        "through working workflows, governance, adoption, and iteration. I would bring business "
        "context and hands-on building judgment while partnering closely with technical specialists "
        "on production architecture and scale."
    )
    catalyst_proof = (
        f"Career Catalyst is the clearest current example. As {catalyst.get('role') or 'Creator and Product Lead'}, "
        "I designed, built, and actively use a role-aware platform for opportunity intake, evidence "
        "management, fit analysis, material generation, status tracking, recovery controls, and "
        "quality governance. I turn recurring user problems into structured requirements, schemas, "
        "validation rules, and tested workflows, then refine the system through real use."
    )
    enterprise_proof = (
        f"At {public_omg23_name(career_data)}, I progressed through five roles to Group Director. I "
        f"{leadership_claim(career_data)}. That scale required more than process design. "
        + (
            "I coordinated an Airtable implementation that created a shared source of truth, with "
            "linked workflows, naming standards, permissions, QA, training, and adoption support. "
            if airtable else ""
        )
        + (
            "I also supported Microsoft Teams adoption through recurring office hours and a peer "
            "champion network."
            if teams else ""
        )
    )
    adoption_proof = (
        "I also served on the cross-functional task force that operationalized the Disney+ launch, "
        "connecting governance, taxonomies, validation, QA, measurement readiness, training, and "
        "change management under a fixed timeline. That experience taught me to define the outcome, "
        "map work and data flows, prototype the right intervention, and build the feedback channels "
        "that make a new way of working stick."
    )
    closing = (
        f"I would welcome the opportunity to bring that combination of Marketing operations depth, "
        f"AI workflow building, and adoption leadership to {company}. "
        f"{campaignos.get('name') or 'CampaignOS'} remains a working prototype and a useful supporting "
        "example, while Career Catalyst demonstrates the active operating system I build and improve today."
    )
    return _signed_content(opening, catalyst_proof, enterprise_proof, adoption_proof, closing)


def _campaignos_is_relevant(context: Dict[str, Any]) -> bool:
    associated = context.get("associated_evidence_projects")
    if associated is not None and not any(
        str(project.get("id") or project.get("name") or project.get("title") or "").lower()
        == "campaignos"
        for project in associated
    ):
        return False

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
            f"The {role} role at {company} stood out because it brings {job_focus} together "
            "across a large advertiser ecosystem."
        )
    elif role:
        opening_sentence = (
            f"The {role} role at {company} stood out because it brings {job_focus} together "
            "in a global entertainment organization."
        )
    else:
        opening_sentence = (
            f"This opportunity at {company} stood out because it brings {job_focus} together "
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
            "I bring long-term hands-on experience with Google advertising products, including "
            "YouTube, dating back to the early 2000s. Across agency and entertainment roles, I have "
            "translated Google and YouTube platform capabilities into campaign execution, "
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


def _dynamic_greeting(context: Dict[str, Any]) -> str:
    return str(
        (context.get("role_intent") or {}).get("cover_letter", {}).get("greeting")
        or "Dear Hiring Team,"
    )


def _replace_greeting(content: str, context: Dict[str, Any]) -> str:
    greeting = _dynamic_greeting(context)
    paragraphs = str(content or "").split("\n\n")
    if paragraphs:
        paragraphs[0] = greeting
    return "\n\n".join(paragraphs)


def _marketing_integration_cover_letter_content(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    company = str(parsed_job.get("company") or "the organization")
    role = str(parsed_job.get("job_title") or "marketing operations role")
    career_data = context["career_data"]
    opening = (
        f"The {role} role at {company} calls for more than process ownership. It requires someone "
        "who can connect brands, shared services, platforms, vendors, and resource decisions through "
        "an operating model people can use. My experience is strongest where fragmented marketing "
        "work needs clearer intake, standards, visibility, and sustained adoption."
    )
    airtable = (
        "At OMG23 / OMD Entertainment, Omnicom Media Group, I coordinated an Airtable implementation that created a "
        "shared source of truth across linked workflows. The work included naming conventions, "
        "permissions, automations, quality checks, documentation, training, and adoption support. "
        "It required translating different team needs into one maintainable structure while keeping "
        "ownership and handoffs clear."
    )
    enterprise = (
        f"That implementation sat within broader enterprise operating work. I {leadership_claim(career_data)}. "
        "Across Ad Operations, Creative Management, and Marketing Science and Analytics, I built "
        "workflow governance, delivery standards, vendor coordination, and reporting visibility for "
        "high-volume entertainment portfolios. I also worked with tools including Box and Trello, "
        "using each platform as part of an operating system rather than treating technology as the solution by itself."
    )
    closing = (
        f"For {company}, I would bring a practical integration approach: map the current work, define "
        "intake and prioritization, clarify shared-service ownership, rationalize vendors and repositories, "
        "then pair implementation with training, feedback, and measurable adoption. The result should be "
        "better portfolio visibility, more dependable throughput, and faster time to market without flattening individual brand needs."
    )
    return "\n\n".join((_dynamic_greeting(context), opening, airtable, enterprise, closing, "Best,\n\nTrisha Lynch"))


def _general_role_intent_cover_letter_content(context: Dict[str, Any]) -> str:
    return candidate_cover_letter(context)


def _bandsintown_cover_letter_content(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title") or "content strategy opportunity"
    position = _position(career_data, "OMG23")
    position_company, _position_shorthand = _employer_names(position)

    opening = (
        f"The {role} role at {company} stood out because it sits at the intersection of music, "
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
        "innovation, built a contributor framework, and reached an audience of 400+ employees. Through "
        "RoboXT Studios, I have continued developing creative, photography, editorial, and web-publishing "
        "systems in a voice that is personal without losing structure. "
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
        f"The {role} role at {company} stood out because it connects product and technology strategy "
        "with the operating rhythms that let a large entertainment enterprise make clear decisions "
        "and execute at scale. I understand the Disney ecosystem through years of hands-on campaign "
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
        f"The {role} role at {company} stood out because it brings YouTube product activation, GTM "
        "operations, seller enablement, and large advertiser execution into one operating challenge. "
        "The interesting work is not simply introducing a product priority. It is creating the feedback "
        "loops, activation guidance, and measurement clarity that help sellers and advertisers use it "
        "well at scale."
    )
    experience = (
        "I bring long-term hands-on experience with Google advertising products, including YouTube, "
        f"dating back to the early 2000s. At {position_company}, I translated Google and YouTube "
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
        "product fluency, and a practical operating style focused on clear adoption and measurable learning."
        " I am comfortable moving between data, stakeholder context, and execution detail, especially "
        "when a product's success depends on many groups understanding the same priority clearly."
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
        f"The {role} role at {company} stood out because marketing operations is the connective layer "
        "between strategy and creative production. In a high-volume entertainment environment, the "
        "real opportunity is to give teams clearer intake, capacity, priorities, and visibility so "
        "creative work can move with fewer avoidable handoffs and better decisions. That is practical, "
        "people-centered systems work, and it is where I have spent much of my career."
    )
    experience = (
        f"At {position_company}, I progressed to Group Director. I {leadership_claim(career_data)}. "
        "My primary work supported Disney Studios Theatrical and Disney Streaming/DSS campaigns, where "
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
        f"The {role} role at {company} stood out because it asks for more than an internal process "
        "operator. It calls for someone who can understand a stakeholder's problem, form a clear "
        "hypothesis, shape an operating model, and communicate a recommendation that people can act "
        "on. That combination of advisory thinking and practical execution fits how I have worked "
        "across media, marketing, advertising, and technology."
    )
    experience = (
        f"At {position_company}, I progressed to Group Director while aligning senior stakeholders, "
        "cross-functional teams, and external partners around complex entertainment marketing work. "
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


def _fieldai_cover_letter_content(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "FieldAI"
    role = parsed_job.get("job_title") or "operations systems opportunity"

    opening = (
        f"The {role} role at {company} stood out because matrix operations becomes consequential when "
        "a fast-moving organization needs to scale without losing clarity. The challenge is to create "
        "shared cadences, capacity visibility, and decision paths that help teams move faster, not to "
        "layer corporate process onto them. That tension between speed and operating discipline is one "
        "I know well."
    )
    experience = (
        f"I {leadership_claim(context.get('career_data', {}))} and designed operating practices across marketing, "
        "creative, analytics, technology, and delivery functions. My work has included capacity and "
        "workflow planning, governance, quality systems, dashboards, partner coordination, and executive "
        "visibility. Although much of that experience was built in entertainment, the transferable "
        "problem is organizational: making ownership, dependencies, risk, and progress visible across "
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
        "matrix today. I would bring a hands-on systems perspective, comfort with ambiguity, and a practical "
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
        f"The {role} role at {company} stood out because it connects streaming, fandom, franchise/IP, "
        "and enterprise strategy. What caught my attention is the need to turn the energy around content "
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
            "that reached 400+ employees. Through RoboXT Studios, I continue to develop creative, "
            "photography, editorial, and web-publishing systems with an independent builder perspective."
        )
    elif role_family in {"product_strategy_ops", "gtm_product_activation", "product_marketing"}:
        experience = (
            f"At {public_omg23_name(context.get('career_data', {}))}, I worked across business priorities, "
            "platform activation, analytics, technology, measurement, and delivery for large entertainment "
            "campaigns. I learned to translate broad goals into practical plans, surface dependencies, "
            "create feedback loops, and give senior stakeholders enough visibility to make sound decisions. "
            "That experience is directly relevant when adoption depends on many functions moving together."
        )
    else:
        experience = (
            f"At {public_omg23_name(context.get('career_data', {}))}, I progressed to Group Director. I "
            f"{leadership_claim(context.get('career_data', {}))}. I built workflows, governance practices, quality standards, and executive "
            "visibility for demanding entertainment work. The industry context was specific, but the operating "
            "challenge was broadly transferable: create clarity and consistency without slowing the team down."
        )

    selected_ids = {str(card.get("id")) for card in context.get("selected_evidence_cards", [])}
    associated_context = str(context.get("associated_evidence_context") or "")
    if role_family in {"editorial_content_strategy", "community_growth"} and editorial_relevant:
        proof = (
            "Those editorial projects strengthened more than my writing. They required content planning, "
            "audience judgment, contributor management, repeatable workflows, and care for tone across different "
            "formats. They also reinforced a principle I bring to operational work: systems should make good "
            "creative decisions easier without flattening the human voice that gives the work meaning."
        )
    elif associated_context:
        title = str((context.get("associated_evidence_projects") or [{}])[0].get("title") or "associated project evidence")
        proof = (
            f"For this role, I would also draw on verified project evidence such as {title}. "
            "That record captures the underlying problem, the actions I took, and the stored results, "
            "so I would use it as grounded support for relevant accomplishments without adding unsupported metrics or claims."
        )
    elif "career_catalyst" in selected_ids:
        proof = (
            "Career Catalyst is a relevant builder proof point for this work. I built the role-aware system "
            "to translate structured requirements and career evidence into ingestion, validation, scoring, "
            "recovery, and quality-governance workflows. I use it as evidence of iterative product operations "
            "and practical AI-system design, without claiming scale or results beyond the working system."
        )
    elif "roboxt_studios" in selected_ids:
        proof = (
            "RoboXT Studios is a relevant independent-building proof point. I am developing the creative and "
            "operating systems behind photography, editorial work, web publishing, and thoughtful AI-assisted "
            "production. I describe it as an early-stage practice, not as a launched agency or scaled studio."
        )
    elif "campaignos" in selected_ids:
        proof = (
            "CampaignOS is a current proof point for that approach. I designed and developed the AI-powered "
            "operations platform to standardize workflow governance, automate quality assurance, reduce risk, "
            "and improve reporting. Building it required product thinking, schema design, validation frameworks, "
            "and practical judgment about where automation can help. I describe it as a working builder project, "
            "not as proof of a larger enterprise product than the evidence supports."
        )
    else:
        proof = (
            "The evidence I would bring is more operational than flashy: governance practices, quality standards, "
            "clearer handoffs, and executive visibility for teams working under real delivery pressure. That work "
            "has taught me to keep claims close to the facts, name tradeoffs early, and build only the amount of "
            "process a team can trust and use."
        )

    closing = (
        f"I would welcome the chance to learn how {company} is defining success for this role and where the "
        "team sees the greatest opportunity for leverage. I would bring steady senior judgment, a practical "
        "builder mindset when it is relevant, and an approach grounded in the role's actual priorities rather than assumptions about the company."
    )
    return _signed_content(opening, experience, proof, closing)


def _cover_letter_content(context: Dict[str, Any]) -> str:
    if context.get("career_data"):
        role_intent = context.get("role_intent") or build_role_intent(
            context["parsed_job"], context.get("root")
        )
        context = {**context, "role_intent": role_intent}
        archetype = str(role_intent.get("primary_archetype") or "general_operations")
        if archetype == "ai_transformation":
            return _replace_greeting(
                _ai_transformation_cover_letter_content(context), context
            )
        if archetype == "marketing_operations_integration":
            return _marketing_integration_cover_letter_content(context)
        return _general_role_intent_cover_letter_content(context)

    # Preserve legacy direct-builder callers that provide only voice context.
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
    role_category = context["material_editing_plan"].get("role_category")
    if is_ai_transformation_role(context["parsed_job"]):
        return _ai_transformation_cover_letter_content(context)
    if role_category in {"chief_of_staff_business_operations", "product_ai_operations"}:
        return _role_sensitive_cover_letter_content(context)
    if role_family == "music_content_strategy":
        return _bandsintown_cover_letter_content(context)
    if profile_key in builders:
        return builders[profile_key](context)
    if _is_creative_product_operations_role(context["parsed_job"]):
        return _default_cover_letter_content(context)
    if _is_technical_operations_role(context["parsed_job"]):
        return _technical_operations_cover_letter_content(context)
    effective = context.get("effective_voice_profile", {})
    if effective.get("company_category") == "gaming_fandom":
        return _default_cover_letter_content(context)
    has_job_context = any(
        parsed_value
        for parsed_value in (
            context["parsed_job"].get("company"),
            context["parsed_job"].get("job_title"),
            str(context["parsed_job"].get("raw_text") or "").strip(),
        )
    )
    builder = (
        _dynamic_cover_letter_content
        if effective.get("source") == "dynamic_inference" and has_job_context
        else _default_cover_letter_content
    )
    return builder(context)


def generate_cover_letter(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    associated_evidence_projects: Optional[List[Dict[str, Any]]] = None,
    role_intent: Optional[Dict[str, Any]] = None,
    parsed_job_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate and save a concise TXT cover letter with safe DOCX when available."""
    context = load_generation_context(
        job_path,
        project_root,
        associated_evidence_projects,
        role_intent,
        parsed_job_override=parsed_job_override,
    )
    grounded_content = _ground_cover_letter_in_selected_evidence(
        _cover_letter_content(context), context
    )
    grounded_content = _remove_repeated_dynamic_closing(grounded_content, context)
    role_family = str(
        (context.get("role_intent") or {}).get("package_role_family")
        or (context.get("role_intelligence") or {}).get("role_family")
        or ""
    )
    minimum_words, maximum_words = (
        (300, 400)
        if role_family in {"strategy_gtm_operations", "music_partnerships_label_relations"}
        else (250, 325)
    )
    result = save_material(
        context,
        "Cover_Letter",
        grounded_content,
        minimum_words=minimum_words,
        maximum_words=maximum_words,
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
        result["docx_hygiene"] = sanitize_docx(docx_path)
    result["role_intent"] = context.get("role_intent") or {}
    result["associated_evidence_project_titles"] = [
        str(project.get("title")) for project in (associated_evidence_projects or [])
    ]
    decision = context.get("cover_letter_evidence_selection") or cover_letter_evidence_decision(
        context, limit=2
    )
    result["cover_letter_projects_used"] = [
        project_title(project) for project in decision.get("used_projects") or []
    ]
    result["evidence_selection"] = public_artifact_selection(decision)
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
    return docx_path
