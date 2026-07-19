"""Generate a grounded Standout Strategy Pack for a local job description."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from .employer_identity import OMG23_DISPLAY_NAME, normalize_applicant_employer_names
    from .filename_utils import build_upload_filename
    from .generate_cover_letter import (
        _achievement,
        _entertainment_scope,
        _is_creative_product_operations_role,
        _join_human,
        _position,
        _word_count,
        load_generation_context,
    )
    from .human_positioning import validate_applicant_evidence
    from .text_cleanup import cleanup_repeated_words
    from .role_context import google_claim_violations, is_google_youtube_role
    from .package_context import validate_material_context
    from .role_lens import enforce_role_lens_quality
except ImportError:
    from employer_identity import OMG23_DISPLAY_NAME, normalize_applicant_employer_names
    from filename_utils import build_upload_filename
    from generate_cover_letter import (
        _achievement,
        _entertainment_scope,
        _is_creative_product_operations_role,
        _join_human,
        _position,
        _word_count,
        load_generation_context,
    )
    from human_positioning import validate_applicant_evidence
    from text_cleanup import cleanup_repeated_words
    from role_context import google_claim_violations, is_google_youtube_role
    from package_context import validate_material_context
    from role_lens import enforce_role_lens_quality


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
    if is_google_youtube_role(parsed_job):
        return "a large advertiser and platform activation ecosystem"
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

    if context.get("role_lens", {}).get("primary") == "people_operations":
        return (
            f"Based on the posting, the {role} role is responsible for turning People strategy into "
            f"programs, systems, reporting, and daily operating practices that can scale with {company}. "
            "The work brings together cross-functional program leadership, continuous improvement, "
            "clear executive updates, team leadership, and practical implementation. Its success will "
            "depend on whether managers and teams understand the programs, trust the operating model, "
            "and can use it without unnecessary friction.\n\n"
            "The posting also includes requirements that should be treated distinctly. Cross-functional "
            "alignment, workflow design, stakeholder communication, implementation, and leading complex "
            "teams have strong parallels in Trisha's professional operations background. Direct People "
            "Operations tenure, employee-lifecycle ownership, People policy, organizational design, and "
            "People data expertise are not established by her evidence and should remain visible gaps. "
            "A thoughtful first move would be to listen to the People team and its partners, map how "
            "programs and decisions currently move, and identify where clearer ownership, communication, "
            "or standards would improve both business outcomes and the day-to-day experience of the work."
        )

    if is_google_youtube_role(parsed_job):
        return (
            f"Based on the job description, the {role} role sits between YouTube Brand Auction "
            "product priorities and go-to-market execution across a large advertiser ecosystem. "
            f"{company} is asking this leader to turn YouTube activation opportunities, including "
            "AI-powered campaign types, into regional strategies that sellers can understand and "
            "customers can adopt. The operational challenge is to align Product Go-To-Market, "
            "Americas Large Customer Sales, sector video leads, and YouTube partners around shared "
            "objectives without losing market nuance.\n\n"
            "The role matters because product activation depends on more than awareness. Sellers need "
            "clear value propositions, training, communications, and feedback channels, while senior "
            "stakeholders need visibility into adoption, revenue goals, product gaps, and market-level "
            "signals. The job description points to Brand Auction commercialization, seller enablement, "
            "cross-functional forums, operational excellence, product feedback loops, and alignment to "
            "business forecasts and objectives. A thoughtful first move would be to understand how "
            "activation priorities currently travel from product teams to sector leads and sellers, "
            "then identify where clearer ownership, feedback, or operating rhythms could improve "
            "execution."
        )

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

    if context.get("role_lens", {}).get("primary") == "people_operations":
        return (
            "Trisha's fit is grounded in transferable operations leadership, not a claim of traditional "
            "HR experience. At "
            f"{OMG23_DISPLAY_NAME}, she led cross-functional teams of 60+ across creative, marketing, "
            "media, analytics, technology, and operations. The work required listening across functions, "
            "clarifying responsibilities, improving communication, and helping teams use shared workflows "
            "and standards under demanding conditions.\n\n"
            "She also introduced scalable governance practices and execution standards across several "
            "functions. The meaningful result was not more process. It was clearer ownership, more "
            "dependable handoffs, and a common understanding of what good execution required. That maps "
            "well to the parts of People Operations centered on program implementation, change adoption, "
            "team effectiveness, and operational consistency. She would be transparent about the areas "
            "where her background is adjacent, including employee-lifecycle programs, People policy, "
            "organizational design, and People analytics. Her value is a practical, observant approach to "
            "building systems around how people actually work in a complex, fast-moving environment."
        )

    if is_google_youtube_role(context["parsed_job"]):
        google_familiarity = _achievement(
            career_data,
            "google_youtube_platform_familiarity",
        )
        value = (
            "Trisha is known for making complex marketing operations clearer and more executable "
            "across large entertainment advertisers. "
            f"{_as_third_person(google_familiarity)} Her background includes translating Google and "
            "YouTube platform capabilities into campaign execution, measurement readiness, and "
            "operational workflows, connecting brand objectives with practical activation at scale.\n\n"
            f"At {position_company}, she progressed from Campaign Manager to Group Director and led "
            "cross-functional teams of 60+ across creative management, marketing operations, media, "
            "analytics, technology, and campaign operations. Disney Studios Theatrical and Disney "
            "Streaming/DSS campaigns provide evidence of her ability to operate across premium "
            "advertiser complexity, align senior stakeholders, and turn platform capabilities into "
            "consistent execution. Her experience with workflow governance, measurement readiness, "
            "and operational standards maps directly to GTM operations, seller enablement, and product "
            "feedback loops. She works by learning how information and decisions move, then building "
            "the lightest useful structure around ownership, quality, and visibility."
        )
        return value

    value = (
        "Trisha is known for helping complex entertainment teams move from strategy to consistent "
        f"execution. At {position_company}, she progressed from Campaign Manager to Group Director. "
        f"{_as_third_person(leadership)} {_as_third_person(disney_plus)} "
        f"{_as_third_person(entertainment_scope)}\n\n"
        f"Her relevance is broader than any one function. {_as_third_person(workflow)} She has worked across marketing, "
        "creative, media, analytics, engineering, technology, operations, quality assurance, and "
        "external partners. That experience gives her a practical view of where handoffs, milestones, "
        "decision paths, and operating standards can help or hinder the work. She understands that "
        "creative and product organizations need clarity and accountability, but not process for its "
        "own sake. Her approach starts with observation: understand the handoffs, find the recurring "
        "friction, and build a practical operating rhythm that people can actually use. That combination "
        "of scale, curiosity, and execution discipline is the value she would bring to this role."
    )
    return value


def _thirty_sixty_ninety_plan(context: Dict[str, Any]) -> str:
    if context.get("role_lens", {}).get("primary") == "people_operations":
        return """#### First 30 Days: Listen, Map, and Understand

- Meet People leaders, People Operations specialists, managers, and key partner teams to understand priorities and working expectations.
- Review active People programs, reporting rhythms, service expectations, workflows, and the current paths for ownership and escalation.
- Map how business priorities become People programs, team actions, decisions, and executive updates.
- Listen for recurring friction in communication, handoffs, adoption, and day-to-day use without assuming every issue needs a new process.
- Confirm where direct HR expertise is essential and where transferable operating support can add value.

#### Days 31-60: Prioritize, Align, and Improve

- Separate isolated concerns from recurring ownership, communication, workflow, or implementation problems.
- Align stakeholders on a short list of practical improvements with clear owners, audiences, and measures.
- Test lightweight changes to documentation, handoffs, reporting, or team routines with the people closest to the work.
- Improve decision-ready updates for People leadership while keeping reporting useful to operating teams.
- Define how feedback from managers and teams will shape changes before they scale.

#### Days 61-90: Operationalize, Learn, and Scale

- Turn effective early improvements into repeatable practices teams can understand and sustain.
- Establish practical governance for ownership, escalation, service expectations, and cross-functional follow-through.
- Improve visibility into progress and friction without creating unnecessary administrative burden.
- Agree on measures that connect business outcomes with adoption and team experience.
- Prepare a longer-term roadmap that distinguishes operating improvements from work requiring specialized HR ownership."""
    if is_google_youtube_role(context["parsed_job"]):
        return """#### First 30 Days: Listen, Map, and Understand

- Meet partners across Product Go-To-Market, YouTube, Americas Large Customer Sales, sector video leads, measurement, and regional operations.
- Review Brand Auction activation priorities, AI-powered campaign types, seller materials, adoption goals, and existing business review rhythms.
- Map how product updates, market feedback, activation guidance, and customer signals move between product teams, sector leads, and sellers.
- Understand where large advertisers encounter friction across value proposition, campaign activation, measurement readiness, or adoption.
- Confirm how leaders define success across activation, revenue contribution, seller readiness, customer outcomes, and feedback quality.

#### Days 31-60: Prioritize, Align, and Improve

- Separate isolated market issues from recurring activation, communication, enablement, or product-feedback gaps.
- Align senior stakeholders on a focused set of activation priorities with clear owners, audiences, milestones, and measures.
- Strengthen seller enablement with concise guidance that connects YouTube capabilities to advertiser objectives and practical execution.
- Establish a useful feedback loop for product gaps, market signals, adoption barriers, and customer needs.
- Test lightweight improvements to activation forums, communications, or reporting with the teams closest to sellers and customers.

#### Days 61-90: Operationalize, Scale, and Measure

- Turn effective activation practices into repeatable GTM operating rhythms across sectors while preserving necessary market nuance.
- Improve visibility into adoption, risks, product updates, seller readiness, and feedback without adding unnecessary reporting.
- Formalize decision and escalation paths across product, sales, measurement, and regional stakeholders.
- Define practical measures for activation progress, enablement effectiveness, feedback quality, and advertiser adoption.
- Prepare a longer-term roadmap for scalable YouTube Brand Auction activation across AI-powered campaign types."""

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
    if context.get("role_lens", {}).get("primary") == "people_operations":
        return (
            "#### How I Think About This Role\n\n"
            "People Operations is most useful when business priorities and the lived experience of "
            "work are considered together. A program can be sound on paper and still fail if ownership "
            "is unclear, managers do not understand the decision, or teams cannot use the process in "
            "their daily work. The operating question is therefore not only whether a system is "
            "efficient. It is whether people understand it, trust it, and know what to do next.\n\n"
            "My perspective comes from operations rather than a traditional HR organization. I have "
            "listened across functions with different pressures and built workflows, responsibilities, "
            "standards, and communication practices around complex work. "
            "That background does not replace expertise in employee relations, People policy, HR "
            "systems, or organizational design. It does offer a grounded way to translate leadership "
            "priorities into practices teams can adopt without adding process for its own sake.\n\n"
            "I would begin by learning how work happens now. Where do managers lose context? Which "
            "handoffs create repeated confusion? What are teams doing outside the formal process to "
            "keep work moving? Those observations make it possible to distinguish a documentation "
            "problem from an ownership problem, a reporting problem from a decision problem, and a "
            "one-time issue from a pattern worth addressing.\n\n"
            "The goal is practical consistency with room for judgment. Clear expectations, useful "
            "feedback loops, and proportionate governance can make People programs easier to operate "
            "while respecting the people who use them. I would bring that balance to the role: support "
            "the business need, listen closely to the human context, and build enough structure for "
            "teams to move forward with confidence."
        )
    if is_google_youtube_role(context["parsed_job"]):
        return (
            "#### How I Think About This Role\n\n"
            "Product activation becomes real when platform priorities are translated into a clear "
            "customer value proposition, practical seller guidance, measurable campaign execution, "
            "and a feedback loop that product teams can use. GTM operations should connect those "
            "elements. It should help sellers understand what is changing, why it matters for large "
            "advertisers, and how to activate it without creating unnecessary process.\n\n"
            "My perspective comes from translating Google and YouTube advertising capabilities into "
            "campaign activation and measurement workflows. I have seen platform "
            "capabilities evolve while the practical operating questions remain consistent: Is the "
            "campaign ready to launch? Is measurement configured? Do teams understand the objective, "
            "dependencies, and value proposition? Can market feedback reach the right product and "
            "business partners in a form they can act on?\n\n"
            "For YouTube Brand Auction and AI-powered campaign types, strong activation requires "
            "alignment across product, sales, measurement, sector leads, and customers. The goal is "
            "not simply broad awareness. It is consistent adoption supported by useful enablement, "
            "clear operating rhythms, and decision-ready visibility into progress and friction. Large "
            "advertisers also need enough flexibility to connect platform capabilities to distinct "
            "brand objectives and market conditions.\n\n"
            "In my professional work, that discipline has meant creating shared campaign workflows, "
            "quality checks, measurement readiness practices, and reporting across creative, media, "
            "analytics, technology, and campaign operations. I would bring that same practical approach "
            "to activation strategy, seller enablement, stakeholder alignment, and product feedback loops."
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
        "I think about technology in the same practical way. It is valuable when it makes workflow, "
        "quality assurance, documentation, validation, or reporting easier to use. It should support "
        "better decisions and cleaner execution, not become a layer of novelty that teams have to work around.\n\n"
        "The best operators help teams move faster without losing the quality of the work. They listen "
        "before designing solutions, make decision paths visible, and know when a lightweight practice "
        "is more useful than a large process. In this role, I would focus on connecting strategic "
        "priorities to practical operating rhythms while preserving the judgment, momentum, and "
        "collaboration that creative organizations need."
    )


def _interview_talking_points(context: Dict[str, Any]) -> List[Tuple[str, str]]:
    if context.get("role_lens", {}).get("primary") == "people_operations":
        return [
            ("Transparent transferable fit", "My background is in operations rather than traditional HR, and I can be specific about where team leadership, change adoption, and workflow implementation transfer."),
            ("Listening for operational friction", "I start by understanding how teams actually work, where context disappears, and which points of friction recur."),
            ("Helping different functions work together", "I aligned teams with different priorities and working styles around shared responsibilities, decision paths, and dependable handoffs."),
            ("Ownership and communication clarity", "I introduced workflows, responsibilities, standards, and communication practices that made handoffs more dependable."),
            ("Adoption without bureaucracy", "I focus on the lightest useful structure and whether people understand, trust, and can sustain a change."),
            ("Knowing the evidence boundary", "I would not claim direct ownership of employee relations, People policy, HRIS, organizational design, or People analytics."),
        ]
    if is_google_youtube_role(context["parsed_job"]):
        return [
            (
                "Google and YouTube activation fluency",
                "I translate Google and YouTube advertising capabilities into practical campaign activation and measurement decisions for large advertisers.",
            ),
            (
                "Translating product priorities into execution",
                "I can discuss how platform capabilities become campaign workflows, measurement readiness, activation guidance, and repeatable operating practices.",
            ),
            (
                "Operating across large advertiser complexity",
                "Disney Studios Theatrical and Disney Streaming/DSS work gave me experience aligning premium brand objectives, media execution, measurement, technology, and operational delivery at scale.",
            ),
            (
                "Building useful GTM operating rhythms",
                "I focus on clear ownership, milestones, decision paths, stakeholder forums, and reporting that helps teams act rather than adding process for its own sake.",
            ),
            (
                "Strengthening seller enablement",
                "I understand that activation guidance must connect product value to customer objectives, execution realities, measurement, and market nuance.",
            ),
            (
                "Creating actionable product feedback loops",
                "My systems work emphasizes turning recurring friction, adoption barriers, and market signals into structured feedback that teams can prioritize.",
            ),
            (
                "Applying operational systems thinking",
                "At OMG23, I used workflow governance, validation, quality assurance, and reporting to improve consistency and visibility across campaign operations.",
            ),
        ]

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
            "Building practical operating systems",
            "My professional workflow work starts by mapping the handoffs, building quality into the process, and improving visibility without adding noise.",
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
    if context.get("role_lens", {}).get("primary") == "people_operations":
        return [
            "Where do managers and teams experience the most recurring friction in current People programs or processes?",
            "Which responsibilities require deep HR subject-matter ownership, and where would strong cross-functional operating leadership add the most value?",
            "How does feedback from managers, employees, and People Operations specialists shape program improvements today?",
            "Which reporting rhythms help People leadership make decisions, and where is context still difficult to see?",
            "What changes are teams being asked to adopt, and what has made adoption easier or harder?",
            "How does the team balance consistency with the needs of different functions and employee groups?",
            "By the end of 90 days, what evidence would show that this leader is improving both execution and the experience of the work?",
        ]
    if is_google_youtube_role(context["parsed_job"]):
        return [
            "Which YouTube Brand Auction products or AI-powered campaign types most need stronger activation across Americas Large Customer Sales today?",
            "Where does the current path from product priority to seller readiness create the most friction or loss of context?",
            "How do sector video leads, Product Go-To-Market, YouTube, and sales teams currently align activation strategies and resolve tradeoffs?",
            "What product feedback from large advertisers is most valuable, and how is it captured, prioritized, and returned to product teams?",
            "Which seller enablement formats are working well, and where do sellers still need clearer value propositions or activation guidance?",
            "How are adoption goals, revenue signals, customer outcomes, and market nuance balanced in business reviews and activation decisions?",
            "By the end of 90 days, what evidence would show that this person is improving activation, stakeholder alignment, and feedback quality?",
        ]

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
    try:
        validate_applicant_evidence(content, "strategy pack")
    except ValueError as exc:
        raise StrategyPackError(str(exc)) from exc
    if "—" in content:
        raise StrategyPackError("Strategy packs must not contain em dashes.")
    if "placeholder" in content.lower():
        raise StrategyPackError("Strategy packs must not contain placeholder text.")
    if is_google_youtube_role(context["parsed_job"]):
        violations = google_claim_violations(content)
        if violations:
            raise StrategyPackError(
                f"Strategy pack contains unsupported Google relationship claim: {violations[0]}"
            )

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
    package_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate and save a Markdown Standout Strategy Pack."""
    context = load_generation_context(job_path, project_root, package_context)
    content = normalize_applicant_employer_names(
        cleanup_repeated_words(_render_strategy_pack(context))
    )
    content, role_lens_quality = enforce_role_lens_quality(
        content, context.get("role_lens", {}), material_type="strategy_pack"
    )
    if not role_lens_quality["valid"]:
        raise StrategyPackError(
            f"Strategy pack does not match role lens: {role_lens_quality['violations'][0]['code']}"
        )
    _validate_strategy_pack(context, content)
    validate_material_context(content, context["parsed_job"], "Strategy_Pack")

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
        "Strategy_Pack",
        "txt",
    )
    output_path = (
        context["root"]
        / "exports"
        / "strategy_packs"
        / filename
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content.rstrip() + "\n", encoding="utf-8")

    return {
        "job_title": parsed_job.get("job_title"),
        "company": parsed_job.get("company"),
        "match_score": context["match_report"].get("match_score"),
        "match_band": context["match_report"].get("match_band"),
        "output_path": str(output_path),
        "role_lens": context.get("role_lens", {}),
        "requirement_map": context.get("requirement_map", []),
        "role_lens_quality": role_lens_quality,
    }
