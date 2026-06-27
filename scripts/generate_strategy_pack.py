"""Generate a grounded Standout Strategy Pack for a local job description."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from .generate_cover_letter import (
        _achievement,
        _campaignos_is_relevant,
        _entertainment_scope,
        _is_creative_product_operations_role,
        _join_human,
        _position,
        _project,
        _slug,
        _word_count,
        load_generation_context,
    )
    from .text_cleanup import cleanup_repeated_words
except ImportError:
    from generate_cover_letter import (
        _achievement,
        _campaignos_is_relevant,
        _entertainment_scope,
        _is_creative_product_operations_role,
        _join_human,
        _position,
        _project,
        _slug,
        _word_count,
        load_generation_context,
    )
    from text_cleanup import cleanup_repeated_words


PathInput = Union[str, Path]
PACK_BANNED_PHRASES = (
    "As an insider",
    "I know your team",
    "I spoke with",
    "guaranteed",
    "perfect fit",
)


class StrategyPackError(Exception):
    """Raised when a strategy pack cannot be generated safely."""


def _job_functions(parsed_job: Dict[str, Any]) -> List[str]:
    raw_text = str(parsed_job.get("raw_text", "")).lower()
    candidates = (
        "executive leadership",
        "business operations",
        "creative operations",
        "product development",
        "licensing",
        "franchise teams",
        "external partners",
        "content",
        "marketing",
        "product",
        "finance",
        "regional teams",
    )
    return [function for function in candidates if function in raw_text]


def _organization_context(parsed_job: Dict[str, Any]) -> str:
    keywords = {str(keyword).lower() for keyword in parsed_job.get("keywords", [])}
    if {"streaming entertainment", "fandom", "global teams"}.issubset(keywords):
        return "a global streaming entertainment and fandom organization"
    if {"streaming entertainment", "fandom"}.issubset(keywords):
        return "a streaming entertainment and fandom organization"
    if "streaming entertainment" in keywords:
        return "a streaming entertainment organization"
    if "fandom" in keywords:
        return "a fandom-focused organization"
    return "a complex organization"


def _as_third_person(statement: str) -> str:
    text = statement.strip()
    if not text or text.startswith("She "):
        return text
    return "She " + text[0].lower() + text[1:]


def _role_opportunity_brief(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "the organization"
    role = parsed_job.get("job_title") or "this role"
    functions = _job_functions(parsed_job)
    function_text = _join_human(functions) if functions else "multiple business functions"
    organization_context = _organization_context(parsed_job)

    if _is_creative_product_operations_role(parsed_job):
        return (
            f"Based on the job description, the {role} role sits at the intersection of global "
            "creative operations, product development operations, licensing, and cross-functional "
            f"execution. {company} is asking this leader to translate entertainment IP and franchise "
            "priorities into clear concept-to-production workflows, milestones, style guides, creative "
            "assets, and product development tools. The operational problem is not simply managing a "
            "calendar. It is creating enough shared structure for creative teams, product partners, "
            "licensees, gaming studios, retail marketing, and external agencies to deliver consistent "
            "work on time, on budget, and in line with brand standards.\n\n"
            "The role matters because licensed merchandise moves through many internal and external "
            "handoffs before it reaches market. Clear ownership, quality standards, decision paths, "
            "and operating rhythms can reduce avoidable friction while protecting creative quality "
            "and franchise consistency. The job description points to team leadership, stakeholder "
            "influence, deadline and resource management, vendor coordination, and the full creative "
            "and product development lifecycle. A thoughtful first move would be to learn how work "
            "currently moves from franchise priority to brief, concept, approval, production, and "
            "launch before recommending changes."
        )

    return (
        f"Based on the job description, the {role} role appears to sit between enterprise strategy "
        f"and day-to-day execution. {company} is asking this leader to translate company priorities "
        "into operational plans, milestones, and decision-ready communication while coordinating "
        f"across {function_text}. The operational problem is not simply producing strategy. It is "
        "creating enough shared structure that many functions can understand dependencies, make "
        "decisions, and keep work moving.\n\n"
        f"The role likely matters because the job description presents {organization_context} that "
        "needs a reliable way to connect "
        "strategic programs with practical ownership, timelines, operating rhythms, and measurable "
        "outcomes. The cross-functional complexity is significant because the role must coordinate "
        "functions with different responsibilities while giving leaders concise visibility into risks "
        "and tradeoffs. "
        "The job description points specifically to operational planning, process improvement, "
        "stakeholder alignment, change management, executive communication, and coordination across "
        "markets and functions. Together, those themes suggest a role responsible for making strategy "
        "executable without adding unnecessary friction. A thoughtful first move would be to learn "
        "how decisions and work currently flow before recommending changes."
    )


def _why_trisha(context: Dict[str, Any]) -> str:
    career_data = context["career_data"]
    position = _position(career_data, "OMG23")
    position_company = position.get("company") or "OMG23 / OMD Entertainment"
    entertainment_scope = _entertainment_scope(career_data)
    leadership = _achievement(career_data, "cross_functional_leadership")
    disney_plus = _achievement(career_data, "disney_plus_launch_support")
    workflow = _achievement(career_data, "workflow_governance")
    campaignos = _project(career_data, "CampaignOS")

    value = (
        "Trisha brings more than 20 years of enterprise entertainment marketing and business "
        "operations experience, with a career built around helping complex teams move from strategy "
        f"to consistent execution. At {position_company}, she progressed from Campaign Manager to "
        f"Group Director. {_as_third_person(leadership)} {_as_third_person(disney_plus)} "
        f"{_as_third_person(entertainment_scope)}\n\n"
        f"Her relevance is broader than any one function. {_as_third_person(workflow)} She has worked across marketing, "
        "creative, media, analytics, engineering, technology, operations, quality assurance, and "
        "external partners. That experience gives her a practical view of where handoffs, milestones, "
        "decision paths, and operating standards can help or hinder the work. She understands that "
        "creative and product organizations need clarity and accountability, but not process for its "
        "own sake."
    )
    if _campaignos_is_relevant(context) and campaignos:
        value += (
            "\n\nCampaignOS adds a current proof point for her systems thinking. As Founder & Product "
            "Lead, she designed an AI-powered operations platform for workflow governance, quality "
            "assurance, validation, and operational reporting. That work connects her entertainment "
            "operations background with thoughtful AI application and shows how she turns recurring "
            "operational problems into usable systems."
        )
    return value


def _thirty_sixty_ninety_plan(context: Dict[str, Any]) -> str:
    if _is_creative_product_operations_role(context["parsed_job"]):
        return """#### First 30 Days: Listen, Map, and Understand

- Meet creative, product development, licensing, franchise, retail marketing, studio, and external partner leads to understand priorities and working expectations.
- Review active product categories, creative assets, style guides, milestone plans, approval paths, and quality standards.
- Map the concept-to-production lifecycle, including ownership, handoffs, vendor coordination, dependencies, and escalation points.
- Listen for recurring friction without assuming every issue requires a new process or tool.
- Confirm how leaders define creative quality, franchise consistency, speed, and successful market delivery.

#### Days 31-60: Prioritize, Align, and Improve

- Separate isolated delivery issues from recurring workflow, milestone, approval, or decision-path problems.
- Align internal and external stakeholders on a short list of high-impact improvements with clear ownership and realistic scope.
- Clarify communication loops for creative reviews, product decisions, risks, dependencies, and launch readiness.
- Test lightweight templates or workflow improvements with the teams closest to the work, then adjust based on what is useful.
- Identify where stronger standards, QA, or visibility can improve consistency without limiting creative judgment.

#### Days 61-90: Operationalize, Scale, and Measure

- Turn useful early improvements into repeatable operating rhythms that teams, licensees, studios, and agencies can sustain.
- Establish practical governance for ownership, approvals, escalation, quality, and cross-functional follow-through.
- Improve visibility into milestones, dependencies, resources, and risks while keeping reporting focused on decisions and action.
- Define success measures with stakeholders across creative quality, delivery reliability, partner experience, and market readiness.
- Prepare a longer-term roadmap for scalable global creative and product development operations."""

    return """#### First 30 Days: Listen, Map, and Understand

- Meet key partners across executive leadership, business operations, content, marketing, product, finance, and regional teams to understand priorities and working expectations.
- Review active strategic initiatives, existing planning cadences, and the ways risks, dependencies, and decisions are currently communicated.
- Map how work moves from company priority to plan, owner, decision, and follow-through, including where ownership and accountability are documented or need clarification.
- Listen for recurring friction and operational pain points without treating every complaint as a process problem.
- Confirm what leaders and teams need from the role before proposing changes.

#### Days 31-60: Prioritize, Align, and Improve

- Synthesize the patterns from the first month and separate isolated issues from recurring workflow or decision-path problems.
- Align stakeholders on a short list of high-impact improvements, with clear ownership and realistic scope.
- Clarify communication loops for decisions, risks, dependencies, and progress so teams know what information belongs where.
- Document any consequential process gaps and identify early wins that reduce friction without creating new bureaucracy.
- Test one or two lightweight improvements with the teams closest to the work, then adjust based on what is useful.

#### Days 61-90: Operationalize, Scale, and Measure

- Turn useful early improvements into repeatable practices, templates, or operating rhythms that teams can sustain.
- Establish appropriate governance for ownership, escalation, decision-making, and cross-functional follow-through.
- Improve visibility into progress, dependencies, and risks while keeping reporting focused on decisions and action.
- Define practical success measures with stakeholders rather than imposing metrics before the work is understood.
- Prepare a longer-term roadmap that distinguishes immediate operating needs from broader organizational improvements."""


def _strategic_pov_note(context: Dict[str, Any]) -> str:
    campaignos_relevant = _campaignos_is_relevant(context)
    campaignos_text = ""
    if campaignos_relevant:
        campaignos_text = (
            " CampaignOS grew from this same belief: recurring operational problems can often be "
            "made easier through clearer workflows, validation, quality assurance, and useful reporting."
        )

    return (
        "#### How I Think About This Role\n\n"
        "I do not see strategy and operations as separate disciplines. Strategy becomes useful when "
        "people can translate it into decisions, ownership, sequencing, and consistent execution. "
        "Operations should make that translation easier. It should help teams see what matters, where "
        "work is blocked, and how their decisions connect to a larger priority.\n\n"
        "That is especially important in creative organizations. Creative and marketing teams need "
        "clarity, not unnecessary bureaucracy. The goal is not to standardize every judgment call. It "
        "is to create enough shared structure that teams can move quickly without losing quality, "
        "context, or accountability. Good operating systems reduce avoidable friction and protect the "
        "time people need for creative and strategic thinking.\n\n"
        "I think about AI in the same practical way. It can be valuable when applied thoughtfully to "
        "workflow, quality assurance, documentation, validation, and repeatable reporting. It should "
        "support better decisions and cleaner execution, not become a layer of novelty that teams have "
        f"to work around.{campaignos_text}\n\n"
        "The best operators help teams move faster without losing the quality of the work. They listen "
        "before designing solutions, make decision paths visible, and know when a lightweight practice "
        "is more useful than a large process. In this role, I would focus on connecting strategic "
        "priorities to practical operating rhythms while preserving the judgment, momentum, and "
        "collaboration that creative organizations need."
    )


def _interview_talking_points(context: Dict[str, Any]) -> List[Tuple[str, str]]:
    campaignos_point = (
        "CampaignOS shows how I approach recurring operational problems: map the workflow, build "
        "validation and quality into the process, and improve visibility without adding noise."
    )
    return [
        (
            "Connecting entertainment IP to execution",
            "I can discuss how franchise and creative priorities become practical workflows, milestones, owners, quality standards, and operating rhythms.",
        ),
        (
            "Building clarity without slowing creative work",
            "I know how much structure creative and marketing teams need to move quickly without turning process into a burden.",
        ),
        (
            "Leading through cross-functional complexity",
            "I led teams of 60+ across creative management, marketing operations, media, analytics, technology, and campaign operations, with internal and external partners to align.",
        ),
        (
            "Turning recurring friction into systems",
            "I introduced scalable workflows, governance practices, and execution standards across marketing, technology, analytics, and creative teams.",
        ),
        (
            "Applying AI without making it gimmicky",
            campaignos_point,
        ),
        (
            "Understanding entertainment marketing scale",
            "My primary experience includes Disney Studios Theatrical and Disney Streaming/DSS campaign operations across Pixar, Lucasfilm, Marvel, 20th Century Studios, Searchlight Pictures, Disney+, and franchise/IP priorities.",
        ),
        (
            "Creating visibility for better decisions",
            "My operational systems work emphasizes quality assurance, validation, and reporting that help teams see risks, dependencies, and next actions more clearly.",
        ),
    ]


def _smart_questions(context: Dict[str, Any]) -> List[str]:
    if _is_creative_product_operations_role(context["parsed_job"]):
        return [
            "Where does the current concept-to-production process create the most friction for creative, product development, and licensing teams?",
            "How are franchise priorities, style guides, and brand standards translated into clear direction for internal teams and external partners today?",
            "Which milestones or approval points most often affect speed, quality, or market readiness?",
            "How does the team balance global consistency with the needs of individual product categories, licensees, studios, and markets?",
            "Which operating rhythms are working well today, and where do teams still lack useful visibility into ownership, dependencies, or risk?",
            "What would you want this leader to understand before recommending workflow or governance changes in the first 30 days?",
            "By the end of 90 days, what evidence would tell you this person is improving creative quality, partner alignment, and delivery reliability?",
        ]

    return [
        "Which strategic priorities most need clearer operating plans today, and what has made them difficult to move forward?",
        "Where does this role have the most responsibility for shaping strategy versus driving cross-functional execution?",
        "Which functions or stakeholder groups will require the strongest alignment from this person in the first six months?",
        "How are major decisions, dependencies, and tradeoffs surfaced today, and where does that process tend to slow down?",
        "What would you want the person in this role to understand before recommending changes in the first 30 days?",
        "Which current planning or communication rhythms are working well, and where is there still avoidable friction?",
        "By the end of 90 days, what specific evidence would tell you this person is creating better clarity and momentum?",
    ]


def _render_strategy_pack(context: Dict[str, Any]) -> str:
    parsed_job = context["parsed_job"]
    company = parsed_job.get("company") or "Company"
    role = parsed_job.get("job_title") or "Role"
    talking_points = "\n".join(
        f"- **{title}:** {detail}" for title, detail in _interview_talking_points(context)
    )
    questions = "\n".join(f"- {question}" for question in _smart_questions(context))

    return "\n\n".join(
        [
            "# Trisha Lynch | Strategy Pack",
            f"## {company} | {role}",
            "### Role Opportunity Brief\n\n" + _role_opportunity_brief(context),
            "### Why Trisha\n\n" + _why_trisha(context),
            "### 30/60/90-Day Plan\n\n" + _thirty_sixty_ninety_plan(context),
            "### Strategic POV Note\n\n" + _strategic_pov_note(context),
            "### Interview Talking Points\n\n" + talking_points,
            "### Smart Questions to Ask\n\n" + questions,
        ]
    )


def _validate_strategy_pack(context: Dict[str, Any], content: str) -> None:
    if "—" in content:
        raise StrategyPackError("Strategy packs must not contain em dashes.")
    if "placeholder" in content.lower():
        raise StrategyPackError("Strategy packs must not contain placeholder text.")

    lowered = content.lower()
    banned = list(PACK_BANNED_PHRASES) + list(context.get("voice", {}).get("avoid", []))
    for phrase in banned:
        if str(phrase).lower() in lowered:
            raise StrategyPackError(f"Strategy pack contains banned phrase: {phrase}")

    section_limits = (
        ("Role Opportunity Brief", _role_opportunity_brief(context), 150, 250),
        ("Why Trisha", _why_trisha(context), 150, 250),
        ("Strategic POV Note", _strategic_pov_note(context), 200, 350),
    )
    for section_name, section_text, minimum, maximum in section_limits:
        count = _word_count(section_text)
        if not minimum <= count <= maximum:
            raise StrategyPackError(
                f"{section_name} must be {minimum}-{maximum} words; got {count}."
            )


def generate_strategy_pack(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Generate and save a Markdown Standout Strategy Pack."""
    context = load_generation_context(job_path, project_root)
    content = cleanup_repeated_words(_render_strategy_pack(context))
    _validate_strategy_pack(context, content)

    parsed_job = context["parsed_job"]
    company_slug = _slug(parsed_job.get("company"), "Company")
    role_slug = _slug(parsed_job.get("job_title"), "Role")
    output_path = (
        context["root"]
        / "exports"
        / "strategy_packs"
        / f"Trisha_Lynch_{company_slug}_{role_slug}_Strategy_Pack.md"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content.rstrip() + "\n", encoding="utf-8")

    return {
        "job_title": parsed_job.get("job_title"),
        "company": parsed_job.get("company"),
        "match_score": context["match_report"].get("match_score"),
        "match_band": context["match_report"].get("match_band"),
        "output_path": str(output_path),
    }
