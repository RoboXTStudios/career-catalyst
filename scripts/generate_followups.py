"""Generate grounded follow-up and networking materials for submitted applications."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .application_tracker import follow_up_action_state, get_record_status, load_application_tracker, update_prospect
    from .dynamic_role_intelligence import get_effective_voice_profile
    from .filename_utils import build_upload_filename, company_display_name
    from .generate_cover_letter import load_generation_context
    from .generate_dashboard import generate_dashboard
    from .load_data import load_all_yaml
    from .package_generator import PackageGenerationError, resolve_job_reference
    from .package_context import validate_material_context
    from .role_context import is_google_youtube_role
except ImportError:
    from application_tracker import follow_up_action_state, get_record_status, load_application_tracker, update_prospect
    from dynamic_role_intelligence import get_effective_voice_profile
    from filename_utils import build_upload_filename, company_display_name
    from generate_cover_letter import load_generation_context
    from generate_dashboard import generate_dashboard
    from load_data import load_all_yaml
    from package_generator import PackageGenerationError, resolve_job_reference
    from package_context import validate_material_context
    from role_context import is_google_youtube_role


PathInput = Union[str, Path]
FOLLOWUP_ELIGIBLE_STATUSES = (
    "Applied",
    "Under Consideration",
    "Interviewing",
)
POST_APPLICATION_STATUSES = FOLLOWUP_ELIGIBLE_STATUSES
MESSAGE_LIMITS = {
    "recruiter_followup": (70, 120),
    "hiring_manager_followup": (100, 160),
    "warm_contact_message": (70, 130),
    "referral_ask": (80, 140),
}
BANNED_PHRASES = (
    "just checking in",
    "perfect fit",
    "top of your inbox",
    "desperate",
)
GOOGLE_RELATIONSHIP_TERMS = ("cousin", "family", "internal referral")


class FollowupGenerationError(Exception):
    """Raised when a follow-up package cannot be generated safely."""


@dataclass(frozen=True)
class RoleAngle:
    outreach_angle: str
    operational_challenge: str
    experience: str
    core_value: str
    who_to_look_for: tuple[str, ...]
    what_to_avoid: tuple[str, ...]


def _clean(value: Any) -> str:
    return str(value or "").strip().replace("—", "-").replace("–", "-")


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*\b", text))


def _achievement_statement(
    career_data: Dict[str, Any], achievement_id: str, fallback: str
) -> str:
    achievements = (
        career_data.get("data", {})
        .get("achievements", {})
        .get("achievements", [])
    )
    statement = next(
        (
            _clean(item.get("statement"))
            for item in achievements
            if item.get("id") == achievement_id
        ),
        "",
    )
    statement = statement or fallback
    if statement.startswith("I "):
        return statement
    return f"I {statement[0].lower()}{statement[1:]}"


def _intelligent_role_angle(
    effective_profile: Dict[str, Any], career_data: Dict[str, Any]
) -> RoleAngle:
    role_family = str(effective_profile.get("role_family") or "generic_senior_operator")
    family_copy = {
        "music_content_strategy": (
            "music, audience connection, editorial voice, and content systems",
            "writing with a distinct voice for different music audiences while building a reliable content operation",
            "multiverse_editorial",
            "I connect editorial judgment and music-aware storytelling with the systems needed to sustain quality at scale.",
        ),
        "editorial_content_strategy": (
            "editorial judgment, audience clarity, voice, and repeatable content systems",
            "turning a clear editorial point of view into content workflows, standards, and consistent delivery",
            "multiverse_editorial",
            "I combine writing and editorial judgment with practical content operations and cross-functional delivery.",
        ),
        "transformation_advisory": (
            "transformation advisory, stakeholder recommendations, operating models, and implementation",
            "moving from a sound hypothesis to an operating model stakeholders can understand, adopt, and sustain",
            "workflow_governance",
            "I pair structured problem solving with the stakeholder judgment and operating discipline needed to make transformation practical.",
        ),
        "product_strategy_ops": (
            "product and technology priorities, roadmaps, OKRs, and executive operating rhythms",
            "aligning product, technology, data, and business partners around decisions, dependencies, and measurable priorities",
            "workflow_governance",
            "I translate broad product and business priorities into clear operating systems and accountable execution.",
        ),
        "gtm_product_activation": (
            "GTM activation, seller enablement, adoption, feedback loops, and measurable learning",
            "turning product priorities into activation plans, enablement, useful feedback loops, and clear measures of adoption",
            "google_youtube_platform_familiarity",
            "I connect product priorities, activation realities, stakeholder enablement, and disciplined feedback loops.",
        ),
        "ai_operations_systems": (
            "matrix operations, capacity visibility, dashboards, automation, and organizational clarity",
            "creating shared cadences, decision paths, and accountable workflows across a fast-moving matrix",
            "campaignos_ai_operations",
            "I make matrixed work more visible and manageable through clear cadences, useful signals, and thoughtful automation.",
        ),
        "streaming_strategy": (
            "streaming, content and franchise/IP priorities, audience context, and executable strategy",
            "turning content and audience priorities into clear decisions, operating rhythms, and cross-functional execution",
            "enterprise_campaign_delivery",
            "I connect entertainment and audience context with the systems teams need to execute strategy reliably.",
        ),
        "community_growth": (
            "community understanding, audience trust, content, measurement, and sustainable growth",
            "building repeatable community programs without losing the human voice and audience insight behind them",
            "multiverse_editorial",
            "I combine community-minded communication with the planning, measurement, and operating discipline needed to sustain growth.",
        ),
        "business_operations": (
            "ownership, capacity planning, decision cadence, and cross-functional delivery",
            "creating capacity visibility, clear ownership, and useful operating rhythms across business functions",
            "cross_functional_leadership",
            "I help complex teams create the operating clarity needed to move from priorities to execution.",
        ),
        "creative_marketing_ops": (
            "creative and marketing priorities, workflow, quality, capacity, and dependable delivery",
            "creating workflow visibility and cross-team alignment without adding process for its own sake",
            "cross_functional_leadership",
            "I bring operational structure to creative and marketing work while protecting the momentum teams need to execute.",
        ),
        "generic_senior_operator": (
            "strategic clarity, stakeholder alignment, scalable systems, and reliable execution",
            "turning complex priorities into clear ownership, useful operating rhythms, and dependable cross-functional execution",
            "cross_functional_leadership",
            "I help complex teams create the clarity and systems needed to move from strategy to execution.",
        ),
    }
    outreach, challenge, achievement_id, core = family_copy.get(
        role_family, family_copy["generic_senior_operator"]
    )
    fallback_experience = (
        "I led 10 direct reports, provided strategic and operational leadership across an integrated 64-person organization, and built clearer workflows and execution standards."
    )
    experience = _achievement_statement(
        career_data, achievement_id, fallback_experience
    )
    leader_title = {
        "music_content_strategy": "content, editorial, or artist marketing leader",
        "editorial_content_strategy": "content or editorial leader",
        "transformation_advisory": "transformation or advisory leader",
        "product_strategy_ops": "product strategy or operations leader",
        "gtm_product_activation": "GTM or product activation leader",
        "ai_operations_systems": "business, product, or organizational operations leader",
        "streaming_strategy": "streaming, content strategy, or operations leader",
        "community_growth": "community, audience, or growth leader",
        "business_operations": "business operations leader",
        "creative_marketing_ops": "creative or marketing operations leader",
        "generic_senior_operator": "hiring manager or relevant team lead",
    }.get(role_family, "hiring manager or relevant team lead")
    return RoleAngle(
        outreach_angle=outreach,
        operational_challenge=challenge,
        experience=experience,
        core_value=core,
        who_to_look_for=(
            "recruiter or talent acquisition partner supporting the function",
            leader_title,
            "relevant cross-functional operations leader",
            "former partner or professional contact who knows Trisha's work",
        ),
        what_to_avoid=(
            "Repeating the full application story.",
            "Claiming knowledge of people or priorities beyond the posted role.",
            "Contacting several people with identical notes.",
        ),
    )


def _role_angle(
    parsed_job: Dict[str, Any],
    career_data: Dict[str, Any],
    effective_profile: Optional[Dict[str, Any]] = None,
) -> RoleAngle:
    if effective_profile:
        return _intelligent_role_angle(effective_profile, career_data)
    company = _clean(parsed_job.get("company")).lower()
    role = _clean(parsed_job.get("job_title")).lower()
    combined = f"{company} {role}"

    if is_google_youtube_role(parsed_job):
        return RoleAngle(
            outreach_angle=(
                "YouTube product activation, GTM operations, seller enablement, and the "
                "large advertiser ecosystem"
            ),
            operational_challenge=(
                "turning YouTube ad product priorities into clear activation plans, seller "
                "enablement, and useful product feedback loops"
            ),
            experience=_achievement_statement(
                career_data,
                "google_youtube_platform_familiarity",
                "I bring long-term hands-on experience with Google advertising products, including YouTube.",
            ),
            core_value=(
                "I connect product priorities, GTM operations, advertiser realities, and "
                "disciplined feedback loops."
            ),
            who_to_look_for=(
                "recruiter or talent acquisition partner supporting YouTube business roles",
                "hiring manager for YouTube Brand Auction strategy and operations",
                "GTM operations or product activation leader",
                "seller enablement leader",
                "relevant former professional contact who knows Trisha's work",
            ),
            what_to_avoid=(
                "Implying employment at Google, inside access, or a prearranged introduction.",
                "Overstating product ownership instead of describing hands-on platform activation.",
                "Sending the same note to several people on the team at once.",
            ),
        )

    if "playstation" in combined or "sony interactive entertainment" in combined:
        return RoleAngle(
            outreach_angle=(
                "creative and product operations, entertainment IP, and cross-functional "
                "creative execution"
            ),
            operational_challenge=(
                "building workflows, milestones, and operating rhythms that keep global creative "
                "and product development moving around entertainment IP"
            ),
            experience=_achievement_statement(
                career_data,
                "cross_functional_leadership",
                "I led 10 direct reports and provided strategic and operational leadership across an integrated 64-person organization.",
            ),
            core_value=(
                "I bring operational structure to creative and product work while protecting the "
                "clarity and momentum teams need to execute."
            ),
            who_to_look_for=(
                "recruiter or talent acquisition partner for creative and product roles",
                "hiring manager overseeing global creative or product development operations",
                "creative operations leader",
                "product operations leader",
                "relevant former partner or professional contact",
            ),
            what_to_avoid=(
                "Treating the outreach as a second cover letter.",
                "Claiming knowledge of team priorities beyond the posted role.",
                "Leading with broad enthusiasm instead of an operational point of view.",
            ),
        )

    if "paramount" in combined:
        return RoleAngle(
            outreach_angle=(
                "marketing and creative operations, AI enablement, dashboards, and capacity planning"
            ),
            operational_challenge=(
                "creating workflow visibility, useful capacity signals, and cross-team alignment "
                "without adding process for its own sake"
            ),
            experience=_achievement_statement(
                career_data,
                "campaignos_ai_operations",
                "I designed an AI-powered operations system for workflow governance, quality assurance, and operational visibility.",
            ),
            core_value=(
                "I turn complex marketing operations into practical systems, dashboards, and "
                "cadences that help teams make better decisions."
            ),
            who_to_look_for=(
                "recruiter or talent acquisition partner for marketing roles",
                "hiring manager for marketing operations",
                "marketing operations leader",
                "creative operations or capacity planning leader",
                "relevant former partner or professional contact",
            ),
            what_to_avoid=(
                "Presenting AI as the answer before understanding the workflow.",
                "Repeating the full application story.",
                "Overloading the note with tools or process terminology.",
            ),
        )

    if "united talent agency" in combined or "uta" in combined:
        return RoleAngle(
            outreach_angle=(
                "transformation advisory, media, marketing, and technology fluency, operating "
                "models, and strategy translated into execution"
            ),
            operational_challenge=(
                "moving from a sound transformation hypothesis to an operating model that clients "
                "and stakeholders can understand, adopt, and sustain"
            ),
            experience=_achievement_statement(
                career_data,
                "workflow_governance",
                "I introduced scalable workflows and execution standards across marketing and technology teams.",
            ),
            core_value=(
                "I pair hypothesis-driven problem solving with the stakeholder judgment and "
                "operating discipline needed to make transformation practical."
            ),
            who_to_look_for=(
                "recruiter or talent acquisition partner for transformation roles",
                "hiring manager for transformation advisory",
                "operating model or enterprise transformation leader",
                "media, marketing, or technology practice leader",
                "relevant former client, partner, or professional contact",
            ),
            what_to_avoid=(
                "Implying a consulting relationship or client connection that has not been established.",
                "Using abstract transformation language without an execution point.",
                "Asking a weak connection for an immediate endorsement.",
            ),
        )

    if "disney" in combined:
        return RoleAngle(
            outreach_angle=(
                "product and technology strategy operations, OKRs, and executive operating rhythms"
            ),
            operational_challenge=(
                "aligning product, engineering, and data partners around priorities, OKRs, decision "
                "cadences, and clear executive visibility"
            ),
            experience=_achievement_statement(
                career_data,
                "omg23_advancement",
                "I led campaign operations across Disney Studios Theatrical and Disney Streaming/DSS.",
            ),
            core_value=(
                "I bring Disney ecosystem familiarity together with practical strategy operations, "
                "cross-functional governance, and executive-ready clarity."
            ),
            who_to_look_for=(
                "recruiter or talent acquisition partner for product and technology roles",
                "hiring manager for product and technology strategy operations",
                "product operations leader",
                "engineering or data operations leader",
                "relevant former Disney partner or professional contact",
            ),
            what_to_avoid=(
                "Relying on Disney ecosystem familiarity as the whole value story.",
                "Suggesting direct knowledge of the current product or engineering team.",
                "Listing every Disney brand instead of focusing on operating relevance.",
            ),
        )

    if "fieldai" in combined or "field ai" in combined:
        return RoleAngle(
            outreach_angle=(
                "matrix operations, organizational efficiency, capacity planning, and AI workflow systems"
            ),
            operational_challenge=(
                "creating shared operating cadences, capacity visibility, and accountable workflows "
                "across a fast-moving matrix organization"
            ),
            experience=_achievement_statement(
                career_data,
                "campaignos_ai_operations",
                "I designed AI-enabled workflow governance, quality assurance, and operational reporting systems.",
            ),
            core_value=(
                "I make matrixed work more visible and manageable through clear cadences, useful "
                "capacity signals, dashboards, and thoughtful automation."
            ),
            who_to_look_for=(
                "recruiter or talent acquisition partner for operations leadership",
                "hiring manager for matrix operations and organizational efficiency",
                "business or product operations leader",
                "organizational effectiveness leader",
                "relevant former partner or professional contact",
            ),
            what_to_avoid=(
                "Framing automation as a substitute for organizational judgment.",
                "Making assumptions about reporting lines or current capacity constraints.",
                "Sending a long inventory of systems and tools.",
            ),
        )

    return RoleAngle(
        outreach_angle="cross-functional operations, workflow clarity, and strategy translated into execution",
        operational_challenge=(
            "turning complex priorities into clear ownership, useful operating rhythms, and "
            "reliable cross-functional execution"
        ),
        experience=_achievement_statement(
            career_data,
            "cross_functional_leadership",
            "I led 10 direct reports and provided strategic and operational leadership across an integrated 64-person organization.",
        ),
        core_value=(
            "I help complex teams create the operating clarity needed to move from strategy to execution."
        ),
        who_to_look_for=(
            "recruiter or talent acquisition partner",
            "hiring manager or team lead",
            "operations or product operations leader",
            "relevant former partner or professional contact",
        ),
        what_to_avoid=(
            "Repeating the full application story.",
            "Claiming knowledge of people or priorities beyond the posted role.",
            "Contacting several people with identical notes.",
        ),
    )


def _package_materials(root: Path, role: str, company: str) -> Dict[str, Path]:
    specs = (
        ("strategy_pack", "exports/strategy_packs", "Strategy Pack", "md"),
        ("cover_letter", "exports/messages", "Cover Letter", "md"),
        ("recruiter_message", "exports/messages", "Recruiter Message", "md"),
        ("hiring_manager_message", "exports/messages", "Hiring Manager Message", "md"),
        ("application_note", "exports/messages", "Application Note", "md"),
    )
    materials: Dict[str, Path] = {}
    for key, directory, export_type, extension in specs:
        filename = build_upload_filename(
            "Trisha Lynch", role, company, export_type, extension
        )
        path = root / directory / filename
        if path.is_file():
            # Loading the text here ensures generation is based on the package on disk, when present.
            path.read_text(encoding="utf-8")
            materials[key] = path
    return materials


def _role_action(role: str, post_application: bool) -> str:
    if post_application:
        return f"I recently applied for the {role} role"
    return f"I'm preparing an application for the {role} role"


def _recruiter_message(
    company: str, role: str, angle: RoleAngle, post_application: bool
) -> str:
    return "\n\n".join(
        (
            "Hello,",
            (
                f"{_role_action(role, post_application)} at {company}. The opportunity caught "
                f"my attention because it connects {angle.outreach_angle}. My background includes "
                "leading complex cross-functional operations and building clearer workflows and "
                "execution standards. If you support this search, I would be glad to share more "
                "context. If not, would you be able to point me toward the right recruiter or "
                "talent acquisition partner?"
            ),
            "Best,\n\nTrisha Lynch",
        )
    )


def _hiring_manager_message(
    company: str, role: str, angle: RoleAngle, post_application: bool
) -> str:
    return "\n\n".join(
        (
            "Hello,",
            (
                f"{_role_action(role, post_application)} at {company}. What stands out to me is "
                f"the operational challenge behind it: {angle.operational_challenge}. "
                f"{angle.experience} {angle.core_value} I would welcome the chance to learn how "
                "the team is thinking about its priorities and where this role can create the "
                "most useful leverage for the team right now."
            ),
            "Best,\n\nTrisha Lynch",
        )
    )


def _warm_contact_message(
    company: str, role: str, angle: RoleAngle, post_application: bool
) -> str:
    return "\n\n".join(
        (
            "Hi,",
            (
                f"{_role_action(role, post_application)} at {company}. Since we have worked "
                "together before, you have some context for how I approach cross-functional work "
                f"and operational problem solving. The role's focus on {angle.outreach_angle} "
                "felt closely aligned. If you have perspective on the team or know who would be "
                "the best person to contact, I would appreciate your guidance. No introduction is "
                "necessary; even a little direction would be helpful."
            ),
            "Warmly,\n\nTrisha Lynch",
        )
    )


def _referral_ask(
    company: str, role: str, angle: RoleAngle, post_application: bool
) -> str:
    return "\n\n".join(
        (
            "Hi,",
            (
                f"{_role_action(role, post_application)} at {company}. Because you know my work, "
                "I wanted to ask whether you would consider referring me or sharing my application "
                f"with the right person, only if you feel comfortable. The focus on "
                f"{angle.outreach_angle} connects closely with the kind of work I have led. There "
                "is no obligation at all. Your candid perspective on the role or the best path "
                "forward would be valuable either way."
            ),
            "Warmly,\n\nTrisha Lynch",
        )
    )


def _validate_message(
    key: str,
    text: str,
    parsed_job: Dict[str, Any],
    voice_avoid: tuple[str, ...],
) -> None:
    if "—" in text:
        raise FollowupGenerationError("Follow-up messages must not contain em dashes.")
    lowered = text.lower()
    for phrase in (*BANNED_PHRASES, *voice_avoid):
        if phrase.lower() in lowered:
            raise FollowupGenerationError(
                f"Generated follow-up contains banned phrase: {phrase}"
            )
    if is_google_youtube_role(parsed_job):
        for phrase in GOOGLE_RELATIONSHIP_TERMS:
            if phrase in lowered:
                raise FollowupGenerationError(
                    f"Google follow-up contains unsupported relationship language: {phrase}"
                )
    minimum, maximum = MESSAGE_LIMITS[key]
    count = _word_count(text)
    if not minimum <= count <= maximum:
        raise FollowupGenerationError(
            f"Generated {key} must be {minimum}-{maximum} words; got {count}."
        )


def _suggested_timing(
    application: Dict[str, Any], post_application: bool
) -> str:
    if not post_application:
        return (
            "Use one targeted networking note before applying, ideally after the role and likely "
            "team have been reviewed. If there is no reply, apply on schedule rather than waiting, "
            "and send one concise update after submission if the contact is relevant."
        )
    submitted = _clean(application.get("submitted_date"))
    application_reference = f"the {submitted} submission" if submitted else "submitting"
    return (
        f"Send the first targeted note 5 to 7 business days after {application_reference}. "
        "If there is no reply, send one concise follow-up 7 to 10 business days later. "
        "Pause after that unless there is a meaningful update or a response."
    )


def _strategy_content(
    application: Dict[str, Any],
    job_path: Optional[Path],
    angle: RoleAngle,
    messages: Dict[str, str],
    package_materials: Dict[str, Path],
    root: Path,
    post_application: bool,
) -> str:
    company = _clean(application.get("company"))
    role = _clean(application.get("role"))
    status = _clean(application.get("status"))
    submitted = _clean(application.get("submitted_date")) or "Not recorded"
    sources = []
    if job_path is not None:
        sources.append(
            str(job_path.relative_to(root))
            if job_path.is_relative_to(root)
            else str(job_path)
        )
    sources.extend(
        relative_path
        for relative_path in (
            "data/positions.yml",
            "data/achievements.yml",
            "data/projects.yml",
        )
        if (root / relative_path).is_file()
    )
    sources.extend(
        str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        for path in package_materials.values()
    )
    who = "\n".join(f"- {item}" for item in angle.who_to_look_for)
    avoid = "\n".join(f"- {item}" for item in angle.what_to_avoid)
    source_list = "\n".join(f"  - {source}" for source in sources)
    option_labels = {
        "recruiter_followup": "Recruiter Follow-Up",
        "hiring_manager_followup": "Hiring Manager Follow-Up",
        "warm_contact_message": "Warm Contact Message",
        "referral_ask": "Referral Ask",
    }
    options = "\n\n".join(
        f"#### {option_labels[key]}\n\n{text}" for key, text in messages.items()
    )
    outreach_mode = (
        "Post-application follow-up"
        if post_application
        else "Pre-application networking"
    )
    return (
        "# Follow-Up Strategy\n\n"
        f"## {company} | {role}\n\n"
        "### Current Status\n\n"
        f"- Status: {status}\n"
        f"- Outreach mode: {outreach_mode}\n"
        f"- Submitted: {submitted}\n"
        "- Grounding reviewed:\n"
        f"{source_list}\n\n"
        "### Best Outreach Angle\n\n"
        f"Lead with {angle.outreach_angle}. Keep the note focused on the operating "
        "challenge and the value Trisha can add, rather than restating the application.\n\n"
        "### Who To Look For\n\n"
        f"{who}\n\n"
        "### What To Avoid\n\n"
        f"{avoid}\n\n"
        "### Suggested Timing\n\n"
        f"{_suggested_timing(application, post_application)}\n\n"
        "### Core Value Point\n\n"
        f"{angle.core_value}\n\n"
        "### Message Options\n\n"
        f"{options}\n"
    )


def _write_output(
    root: Path,
    role: str,
    company: str,
    export_type: str,
    content: str,
) -> Path:
    output_directory = root / "exports" / "followups"
    output_directory.mkdir(parents=True, exist_ok=True)
    filename = build_upload_filename(
        "Trisha Lynch", role, company, export_type, "txt"
    )
    output_path = output_directory / filename
    output_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return output_path


def generate_followups(
    tracker_id: str,
    project_root: Optional[PathInput] = None,
    role_intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate five follow-up or pre-application networking files for one tracker role."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    try:
        applications = load_application_tracker(root)
        application = next(
            (item for item in applications if str(item.get("id")) == str(tracker_id)),
            None,
        )
        if application is None:
            raise FollowupGenerationError(f"Tracker entry not found: {tracker_id}")
        status = get_record_status(application)
        follow_up_action = follow_up_action_state(application)
        if not follow_up_action["eligible"]:
            raise FollowupGenerationError(
                f"Tracker entry '{tracker_id}' cannot generate follow-ups: "
                f"{follow_up_action['reason']}"
            )
        post_application = status in POST_APPLICATION_STATUSES
        job_path: Optional[Path] = None
        try:
            resolved = resolve_job_reference(tracker_id, root)
            job_path = Path(resolved["job_path"])
        except PackageGenerationError:
            job_path = None

        if job_path is not None:
            context = load_generation_context(job_path, root, role_intent=role_intent)
            parsed_job = context["parsed_job"]
            career_data = context["career_data"]
        else:
            career_data = load_all_yaml(root)
            parsed_job = {
                "company": application.get("company"),
                "job_title": application.get("role"),
                "raw_text": application.get("job_description", ""),
                "source_url": application.get("official_url", ""),
                "keywords": [],
            }
            context = {
                "career_data": career_data,
                "voice": career_data["config"].get("voice", {}),
                "parsed_job": parsed_job,
                "role_intent": role_intent,
            }
        raw_company = _clean(application.get("company") or parsed_job.get("company"))
        company = company_display_name(raw_company)
        role = _clean(application.get("role") or parsed_job.get("job_title"))
        effective_profile = get_effective_voice_profile(
            company_name=company,
            job_title=role,
            job_description=str(parsed_job.get("raw_text") or ""),
            source_url=str(
                parsed_job.get("source_url") or application.get("official_url") or ""
            ),
            existing_profiles=career_data["config"].get(
                "company_voice_profiles", {}
            ),
        )
        context["effective_voice_profile"] = effective_profile
        application = update_prospect(
            str(application["id"]),
            {
                "company_category": effective_profile["company_category"],
                "role_family": effective_profile["role_family"],
                "company_voice_profile": effective_profile["profile_name"],
                "company_voice_source": effective_profile["source"],
            },
            root,
        )
        angle = _role_angle(parsed_job, career_data, effective_profile)
        package_materials = _package_materials(root, role, raw_company)
        messages = {
            "recruiter_followup": _recruiter_message(
                company, role, angle, post_application
            ),
            "hiring_manager_followup": _hiring_manager_message(
                company, role, angle, post_application
            ),
            "warm_contact_message": _warm_contact_message(
                company, role, angle, post_application
            ),
            "referral_ask": _referral_ask(
                company, role, angle, post_application
            ),
        }
        voice_avoid = tuple(
            _clean(phrase)
            for phrase in context.get("voice", {}).get("avoid", [])
            if _clean(phrase)
        )
        for key, message in messages.items():
            _validate_message(key, message, parsed_job, voice_avoid)
            validate_material_context(message, parsed_job, key)

        output_specs = (
            ("recruiter_followup", "Recruiter Followup"),
            ("hiring_manager_followup", "Hiring Manager Followup"),
            ("warm_contact_message", "Warm Contact Message"),
            ("referral_ask", "Referral Ask"),
        )
        outputs = {
            key: str(_write_output(root, role, company, export_type, messages[key]))
            for key, export_type in output_specs
        }
        strategy = _strategy_content(
            application,
            job_path,
            angle,
            messages,
            package_materials,
            root,
            post_application,
        )
        if "—" in strategy:
            raise FollowupGenerationError("Follow-up strategy must not contain em dashes.")
        validate_material_context(strategy, parsed_job, "Followup_Strategy")
        outputs["followup_strategy"] = str(
            _write_output(root, role, company, "Followup Strategy", strategy)
        )
        dashboard = generate_dashboard(root)
    except FollowupGenerationError:
        raise
    except Exception as error:
        raise FollowupGenerationError(f"Could not generate follow-ups: {error}") from error

    return {
        "tracker_id": str(application.get("id") or tracker_id),
        "company": company,
        "role": role,
        "status": status,
        "job_path": str(job_path) if job_path is not None else None,
        "company_category": effective_profile["company_category"],
        "role_family": effective_profile["role_family"],
        "company_voice_profile": effective_profile["profile_name"],
        "company_voice_source": effective_profile["source"],
        "outreach_mode": (
            "post-application follow-up"
            if post_application
            else "pre-application networking"
        ),
        "source_materials": {key: str(path) for key, path in package_materials.items()},
        "outputs": outputs,
        "dashboard": dashboard.get("output_path"),
    }


def _expected_followup_paths(
    application: Dict[str, Any], root: Path
) -> Dict[str, Path]:
    company = _clean(application.get("company"))
    role = _clean(application.get("role"))
    specs = (
        ("recruiter_followup", "Recruiter Followup"),
        ("hiring_manager_followup", "Hiring Manager Followup"),
        ("warm_contact_message", "Warm Contact Message"),
        ("referral_ask", "Referral Ask"),
        ("followup_strategy", "Followup Strategy"),
    )
    return {
        key: root
        / "exports"
        / "followups"
        / build_upload_filename("Trisha Lynch", role, company, export_type, "txt")
        for key, export_type in specs
    }


def generate_missing_followups(
    project_root: Optional[PathInput] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Generate only eligible follow-ups and report every skipped tracker role."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    generated = []
    generated_roles = []
    skipped: Dict[str, str] = {}
    skipped_roles = []
    skipped_existing = []
    failed: Dict[str, str] = {}
    for application in load_application_tracker(root):
        tracker_id = str(application.get("id") or "")
        role_summary = {
            "id": tracker_id,
            "company": str(application.get("company") or "Unknown company"),
            "role": str(application.get("role") or "Unknown role"),
        }
        follow_up_action = follow_up_action_state(application)
        if not follow_up_action["eligible"]:
            reason = str(follow_up_action["reason"])
            skipped[tracker_id] = reason
            skipped_roles.append({**role_summary, "reason": reason})
            continue
        expected = _expected_followup_paths(application, root)
        if not force and all(path.is_file() for path in expected.values()):
            reason = "Follow-up materials already exist."
            skipped[tracker_id] = reason
            skipped_roles.append({**role_summary, "reason": reason})
            skipped_existing.append(tracker_id)
            continue
        try:
            generate_followups(tracker_id, root)
        except FollowupGenerationError as error:
            failed[tracker_id] = str(error)
        else:
            generated.append(tracker_id)
            generated_roles.append(role_summary)
    return {
        "generated": generated,
        "generated_roles": generated_roles,
        "skipped": skipped,
        "skipped_roles": skipped_roles,
        "skipped_existing": skipped_existing,
        "failed": failed,
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "skipped_existing_count": len(skipped_existing),
        "failed_count": len(failed),
    }
