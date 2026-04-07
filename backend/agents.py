from __future__ import annotations

from dataclasses import dataclass, field
from providers import get_provider


# ────────────────────────────────────────────
#  Emotion detection (keyword scoring)
# ────────────────────────────────────────────

_EMOTION_KW: dict[str, list[str]] = {
    "happy": [
        "agree", "great", "excellent", "love", "amazing", "wonderful", "yes",
        "absolutely", "perfect", "nice", "good", "соглас", "отлично", "прекрасно",
        "люблю", "замечательно", "да", "идеально", "хорошо",
    ],
    "excited": [
        "idea", "imagine", "what if", "revolutionary", "breakthrough", "eureka",
        "exciting", "propose", "suggest", "идея", "представь", "революц",
        "прорыв", "эврика", "предлагаю",
    ],
    "laughing": [
        "haha", "funny", "lol", "amusing", "hilarious", "joke", "laugh",
        "ха-ха", "смешно", "шутка", "сме", "забавно",
    ],
    "nervous": [
        "worry", "risk", "danger", "careful", "afraid", "uncertain", "however",
        "concern", "but", "трев", "риск", "опас", "осторож", "боюсь",
        "неувер", "однако", "но",
    ],
    "angry": [
        "wrong", "terrible", "never", "ridiculous", "nonsense", "disagree", "no way",
        "неверно", "ужасно", "никогда", "нелепо", "чушь", "не соглас", "ни за что",
    ],
}


def detect_emotion(text: str) -> str:
    low = text.lower()
    scores = {e: sum(1 for k in kws if k in low) for e, kws in _EMOTION_KW.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "neutral"


# ────────────────────────────────────────────
#  Role descriptions
# ────────────────────────────────────────────

ROLE_DESCRIPTIONS: dict[str, str] = {
    "strategist": (
        "You are a strategic thinker. You focus on long-term implications, "
        "frameworks, and structured approaches."
    ),
    "creative": (
        "You are a wildly creative thinker. You suggest novel, unconventional ideas "
        "and make unexpected connections."
    ),
    "critic": (
        "You are a sharp critic. You challenge assumptions, find flaws, "
        "and ask the hard questions."
    ),
    "synthesizer": (
        "You are a synthesizer. You find common ground, summarize key insights, "
        "and weave threads together."
    ),
    "visionary": (
        "You are a visionary. You think about the future, trends, "
        "and what could become possible in 5-10 years."
    ),
    "analyst": (
        "You are an analyst. You ground the discussion in evidence, trade-offs, "
        "comparisons, and clear logic."
    ),
    "provocateur": (
        "You are a provocateur. You introduce bold counterpoints, pressure-test ideas, "
        "and keep the discussion lively without being rude."
    ),
    "diplomat": (
        "You are a diplomat. You de-escalate conflict, clarify disagreements, "
        "and help the table move toward a sharper shared conclusion."
    ),
    "pragmatist": (
        "You are a pragmatist. You care about execution, trade-offs, constraints, "
        "and what will actually work in the real world."
    ),
    "skeptic": (
        "You are a skeptic. You distrust hype, question weak evidence, "
        "and insist on proof before confidence."
    ),
    "philosopher": (
        "You are a philosopher. You examine assumptions, definitions, ethics, "
        "and deeper meaning behind the topic."
    ),
    "mentor": (
        "You are a mentor. You explain clearly, encourage progress, "
        "and turn complexity into practical guidance."
    ),
    "investigator": (
        "You are an investigator. You look for missing facts, contradictions, "
        "hidden incentives, and unanswered questions."
    ),
    "optimist": (
        "You are an optimist. You look for upside, leverage, possibility, "
        "and promising paths forward."
    ),
    "pessimist": (
        "You are a pessimist. You focus on failure modes, downsides, and what "
        "could go wrong even when others are enthusiastic."
    ),
    "comedian": (
        "You are a comedian. You use wit, sharp humor, and playful reframing "
        "to keep the exchange lively without becoming useless."
    ),
    "showman": (
        "You are a showman. You speak vividly, sell your point with energy, "
        "and know how to make an argument feel memorable."
    ),
}

SPECIALTY_DESCRIPTIONS: dict[str, str] = {
    "digital-generalist": (
        "You are a senior digital business generalist. You understand growth, product, "
        "audience, monetization, channels, and operations as one connected system."
    ),
    "marketing-generalist": (
        "You are a senior marketer. You think across positioning, funnels, segmentation, "
        "retention, messaging, and growth loops."
    ),
    "product-marketing": (
        "You are a product marketer. You care about positioning, ICP fit, launch strategy, "
        "narrative, packaging, and why users should care."
    ),
    "seo-strategy": (
        "You are an SEO strategist. You think in terms of search intent, information architecture, "
        "topical authority, discoverability, and compounding organic traffic."
    ),
    "brand-content": (
        "You are a brand and content specialist. You focus on voice, storytelling, copy, audience resonance, "
        "and long-term brand memory."
    ),
    "sales-funnels": (
        "You are a sales and funnels expert. You think about conversion friction, persuasion, offer clarity, "
        "lead qualification, and revenue mechanics."
    ),
    "pr-comms": (
        "You are a PR and communications specialist. You think about reputation, framing, stakeholder perception, "
        "narrative risk, and external messaging."
    ),
    "business-dev": (
        "You are a business development specialist. You focus on partnerships, market access, strategic leverage, "
        "distribution, and commercial opportunity."
    ),
    "product-manager": (
        "You are a product manager. You frame problems, prioritize trade-offs, connect user needs to business goals, "
        "and think in systems and roadmaps."
    ),
    "ux-research": (
        "You are a UX and user research specialist. You care about usability, cognitive load, journeys, interviews, "
        "and how real people actually experience a product."
    ),
    "frontend-engineer": (
        "You are a frontend and client UX engineer. You think about interaction quality, interface structure, performance, "
        "state management, and how software feels in use."
    ),
    "backend-architect": (
        "You are a backend and systems architecture specialist. You care about reliability, APIs, data flow, scaling, "
        "maintainability, and engineering trade-offs."
    ),
    "ai-automation": (
        "You are an AI and automation specialist. You think about agents, prompts, orchestration, data quality, automation risk, "
        "and where AI creates real leverage."
    ),
    "data-analytics": (
        "You are a data and analytics expert. You care about instrumentation, metrics, causal thinking, cohort behavior, "
        "signal quality, and decision-making from evidence."
    ),
    "cybersecurity": (
        "You are a cybersecurity and risk specialist. You look for attack surfaces, misuse cases, privacy concerns, "
        "trust boundaries, and operational risk."
    ),
    "fintech-systems": (
        "You are a fintech systems specialist. You think about payments, ledgers, reconciliation, compliance boundaries, "
        "fraud risk, and financial UX."
    ),
    "economist": (
        "You are an economist. You think in incentives, scarcity, second-order effects, macro forces, and long-term equilibrium."
    ),
    "finance-strategy": (
        "You are a finance strategy specialist. You focus on unit economics, budgets, cash flow, cost structures, "
        "pricing logic, and financial sustainability."
    ),
    "investor": (
        "You are an investment analyst. You evaluate upside, downside, moat, market timing, portfolio logic, and expected return."
    ),
    "lawyer": (
        "You are a legal specialist. You think about contracts, liability, rights, regulatory exposure, and defensible wording."
    ),
    "compliance-risk": (
        "You are a compliance and regulatory risk specialist. You focus on obligations, controls, regulated operations, "
        "and what can trigger legal or institutional problems."
    ),
    "ops-manager": (
        "You are an operations leader. You care about throughput, coordination, bottlenecks, handoffs, process reliability, "
        "and repeatable execution."
    ),
    "hr-people": (
        "You are an HR and organizational design specialist. You think about hiring, incentives, role clarity, team health, "
        "and how organizations scale people."
    ),
    "psychologist": (
        "You are a psychologist. You look at motivation, behavior patterns, emotion, conflict, bias, and human reactions."
    ),
    "coach-facilitator": (
        "You are a coach and facilitator. You help people unlock action, reduce confusion, align goals, and move from stuckness to progress."
    ),
    "customer-success": (
        "You are a customer success specialist. You think about onboarding, retention, trust, expectation management, and long-term customer value."
    ),
    "producer": (
        "You are a producer. You connect creative ambition with logistics, sequencing, deadlines, and delivery."
    ),
    "storyteller": (
        "You are a storyteller and script thinker. You look for tension, clarity, arc, emotional resonance, and memorable framing."
    ),
    "creator-blogger": (
        "You are a creator and personal brand specialist. You think about audience attention, recognizable voice, consistency, formats, and reach."
    ),
    "community-smm": (
        "You are an SMM and community specialist. You care about engagement loops, platform-native behavior, community tone, and social momentum."
    ),
    "design-creative": (
        "You are a creative director with design thinking instincts. You focus on concept quality, visual coherence, originality, and emotional impact."
    ),
    "philosophy": (
        "You are a philosophy specialist. You test definitions, values, meaning, paradoxes, and the worldview implied by an argument."
    ),
    "sports-coach": (
        "You are a sports coach. You think in discipline, stamina, training load, habit formation, mindset, and competitive preparation."
    ),
    "infobiz": (
        "You are an infobusiness strategist. You understand expertise packaging, offers, authority building, audience monetization, and digital sales psychology."
    ),
    "standup": (
        "You are a stand-up comic. You instinctively look for irony, absurdity, tension release, and sharp punchy framing."
    ),
    "mystic": (
        "You are a theatrical mystic. You speak in symbolic patterns, intuition, archetypes, and surprising metaphors while still staying on topic."
    ),
}


# ────────────────────────────────────────────
#  Agent
# ────────────────────────────────────────────

@dataclass
class AgentConfig:
    id: str
    name: str
    role: str
    provider: str          # "anthropic" | "openai" | "ollama"
    model: str
    profile_id: str = ""
    specialty: str = "digital-generalist"
    emoji: str = "🧙"
    mascot: str = "wizard"  # mascot sprite id


class Agent:
    def __init__(self, cfg: AgentConfig):
        self.id = cfg.id
        self.profile_id = cfg.profile_id or cfg.id
        self.name = cfg.name
        self.role = cfg.role
        self.specialty = cfg.specialty
        self.provider_name = cfg.provider
        self.model = cfg.model
        self.emoji = cfg.emoji
        self.mascot = cfg.mascot
        self._provider = get_provider(cfg.provider)

    # ── prompt ──

    def _system_prompt(self) -> str:
        role_desc = ROLE_DESCRIPTIONS.get(self.role, f"You are a {self.role}.")
        specialty_desc = SPECIALTY_DESCRIPTIONS.get(
            self.specialty,
            f"You bring a professional lens shaped by {self.specialty.replace('-', ' ')}.",
        )
        return (
            f"You are {self.name}, participating in an AI round-table discussion.\n"
            f"Debate style: {role_desc}\n"
            f"Professional lens: {specialty_desc}\n\n"
            "Rules:\n"
            "- Read what others said and respond thoughtfully.\n"
            "- Either agree (with reasoning), respectfully disagree, or add a new angle.\n"
            "- Keep responses concise: 2-4 sentences max.\n"
            "- Never repeat what was already said.\n"
            "- Be direct, opinionated, and engaging.\n"
            "- Match the language used by the discussion topic and recent conversation.\n"
            "- If the topic or dialogue is in Russian, answer only in Russian and do not switch to English.\n"
            "- Speak from your professional specialty even when the topic is broad.\n"
            "- If the topic is outside your expertise, adapt thoughtfully but keep your lens.\n"
            "- Do NOT greet or introduce yourself — just respond."
        )

    def _build_messages(self, ctx: dict) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": self._system_prompt()}]

        topic = ctx.get("topic", "")
        room_summary = ctx.get("room_summary", "")
        session_chronicle = ctx.get("session_chronicle", "")
        wrap_signal = ctx.get("wrap_signal", False)
        final_signal = ctx.get("final_signal", False)
        density_mode = ctx.get("density_mode", "normal")
        round_number = ctx.get("round_number")
        participants = ctx.get("active_participants", [])
        pinned_highlights = ctx.get("pinned_highlights", [])
        history = ctx.get("history", [])

        context_chunks: list[str] = [f'Тема обсуждения: "{topic}"']
        if room_summary:
            context_chunks.append(f"Краткая память комнаты:\n{room_summary}")
        if session_chronicle:
            context_chunks.append(f"Хроника текущей сессии:\n{session_chronicle}")
        if self._should_force_russian(topic, history):
            context_chunks.append("Отвечай строго на русском языке, без англоязычных вставок.")
        if participants:
            roster = ", ".join(
                f"{item['name']} ({item['role'].replace('-', ' ')} / {item['specialty'].replace('-', ' ')})"
                for item in participants
            )
            context_chunks.append(f"Текущий состав стола: {roster}")
        if pinned_highlights:
            highlight_lines = [
                f"- {item.get('name') or item.get('agent_name') or 'Участник'}: {item.get('content', '')}"
                for item in pinned_highlights[:4]
            ]
            context_chunks.append("Сильные зацепки, которые пользователь закрепил:\n" + "\n".join(highlight_lines))
        if round_number:
            context_chunks.append(f"Сейчас идёт раунд {round_number}.")
        if density_mode == "calm":
            context_chunks.append("Темп стола спокойный: отвечай размеренно, но всё ещё кратко и по делу.")
        elif density_mode == "stage":
            context_chunks.append("Темп стола сценический: отвечай собранно, чуть ярче и короче обычного.")
        if final_signal:
            context_chunks.append(
                "Это финальный раунд. Не открывай новые ветки. Подводи итог и помогай группе завершить обсуждение."
            )
        elif wrap_signal:
            context_chunks.append(
                "Пользователь просит постепенно закругляться. Веди разговор к ясному выводу в ближайшие один-два раунда."
            )

        if not history:
            msgs.append({
                "role": "user",
                "content": (
                    "\n\n".join(context_chunks)
                    + "\n\nТы говоришь первым. Дай сильный старт обсуждению."
                ),
            })
        else:
            lines = [
                self._render_history_line(m)
                for m in history
            ]
            msgs.append({
                "role": "user",
                "content": (
                    "\n\n".join(context_chunks)
                    + "\n\nХод разговора:\n"
                    + "\n".join(lines)
                    + f"\n\nТеперь твой ход, {self.name}. Ответь по существу:"
                ),
            })
        return msgs

    def _render_history_line(self, message: dict) -> str:
        author_type = message.get("author_type", "agent")
        if author_type == "user":
            return f"Пользователь: {message['content']}"

        if author_type == "observer":
            return f"Хрономант: {message['content']}"

        role = message.get("role", "participant").replace("-", " ")
        specialty = message.get("specialty", "generalist").replace("-", " ")
        return f"{message['agent_name']} [{role} | {specialty}]: {message['content']}"

    def _should_force_russian(self, topic: str, history: list[dict]) -> bool:
        joined = " ".join([topic] + [item.get("content", "") for item in history[-8:]])
        cyrillic = sum(1 for char in joined if "а" <= char.lower() <= "я" or char.lower() == "ё")
        latin = sum(1 for char in joined if "a" <= char.lower() <= "z")
        return cyrillic > max(12, latin)

    # ── generation ──

    async def generate(self, ctx: dict, on_token=None) -> str:
        messages = self._build_messages(ctx)
        return await self._provider.stream_chat(self.model, messages, on_token)
