from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from knowledge.lightrag_adapter import PROFILE_GRAPH_ROOT, query_graph
from providers import get_provider
from tools import execute_agent_tool, get_tool_definitions


# ────────────────────────────────────────────
#  Emotion detection (hybrid: keyword + LLM)
# ────────────────────────────────────────────

# Weighted keyword lists: (keyword, weight)
_EMOTION_KW: dict[str, list[tuple[str, int]]] = {
    "happy": [
        ("agree", 1), ("great", 1), ("excellent", 2), ("love", 2), ("amazing", 2),
        ("wonderful", 2), ("yes", 1), ("absolutely", 2), ("perfect", 2), ("nice", 1),
        ("good", 1), ("brilliant", 2), ("fantastic", 2), ("pleased", 1), ("glad", 1),
        ("delighted", 2), ("superb", 2), ("bravo", 2), ("благодар", 2),
        ("соглас", 1), ("отлично", 2), ("прекрасно", 2), ("люблю", 2),
        ("замечательно", 2), ("да", 1), ("идеально", 2), ("хорошо", 1),
        ("здорово", 2), ("молодец", 2), ("верно", 1), ("точно", 1),
        ("именно", 1), ("браво", 2), ("превосходно", 2), ("чудесно", 2),
    ],
    "excited": [
        ("idea", 2), ("imagine", 2), ("what if", 2), ("revolutionary", 3),
        ("breakthrough", 3), ("eureka", 3), ("exciting", 2), ("propose", 1),
        ("suggest", 1), ("discover", 2), ("unlock", 2), ("potential", 1),
        ("transform", 2), ("game-changer", 3), ("paradigm", 2), ("vision", 2),
        ("идея", 2), ("представь", 2), ("революц", 3), ("прорыв", 3),
        ("эврика", 3), ("предлагаю", 1), ("потенциал", 1), ("трансформ", 2),
        ("открыт", 2), ("возможност", 2), ("перспектив", 2), ("вдохнов", 2),
        ("амбициозн", 2), ("масштаб", 2),
    ],
    "laughing": [
        ("haha", 3), ("funny", 2), ("lol", 3), ("amusing", 2), ("hilarious", 3),
        ("joke", 2), ("laugh", 2), ("humor", 2), ("comedy", 2), ("witty", 2),
        ("ironic", 2), ("sarcas", 2), ("absurd", 2),
        ("ха-ха", 3), ("смешно", 2), ("шутка", 2), ("сме", 1), ("забавно", 2),
        ("ирони", 2), ("комич", 2), ("абсурд", 2), ("анекдот", 2),
        ("юмор", 2), ("хехе", 3), ("ахах", 3), ("лол", 3),
    ],
    "nervous": [
        ("worry", 2), ("risk", 2), ("danger", 2), ("careful", 1), ("afraid", 2),
        ("uncertain", 2), ("however", 1), ("concern", 2), ("caveat", 2),
        ("warning", 2), ("caution", 2), ("fragile", 2), ("volatile", 2),
        ("трев", 2), ("риск", 2), ("опас", 2), ("осторож", 2), ("боюсь", 2),
        ("неувер", 2), ("однако", 1), ("но", 1), ("сомне", 2), ("колеб", 2),
        ("тревож", 2), ("хрупк", 2), ("уязвим", 2), ("предупрежд", 2),
        ("проблем", 1), ("слож", 1),
    ],
    "angry": [
        ("wrong", 2), ("terrible", 2), ("never", 1), ("ridiculous", 3),
        ("nonsense", 3), ("disagree", 2), ("no way", 3), ("absurd", 2),
        ("unacceptable", 3), ("outrageous", 3), ("foolish", 2), ("failure", 2),
        ("catastroph", 3), ("incompetent", 3),
        ("неверно", 2), ("ужасно", 2), ("никогда", 1), ("нелепо", 3),
        ("чушь", 3), ("не соглас", 2), ("ни за что", 3), ("бред", 3),
        ("провал", 2), ("недопустим", 3), ("возмутител", 3), ("глупо", 2),
        ("безответствен", 3), ("катастроф", 3),
    ],
}

VALID_EMOTIONS = {"happy", "excited", "laughing", "nervous", "angry", "neutral"}


def detect_emotion(text: str) -> str:
    """Fast keyword-based emotion detection."""
    emotion, _ = detect_emotion_scored(text)
    return emotion


def detect_emotion_scored(text: str) -> tuple[str, float]:
    """Keyword-based emotion detection with confidence score (0.0-1.0)."""
    low = text.lower()
    scores: dict[str, int] = {}
    for emotion, keywords in _EMOTION_KW.items():
        scores[emotion] = sum(weight for kw, weight in keywords if kw in low)
    total = sum(scores.values())
    best = max(scores, key=scores.get)
    if total == 0:
        return "neutral", 0.0
    confidence = scores[best] / max(total, 1)
    return best, round(confidence, 2)


async def detect_emotion_llm(
    text: str,
    provider_name: str,
    model: str,
    timeout: float = 8.0,
) -> str | None:
    """LLM-based emotion classification. Returns None on failure."""
    try:
        provider = get_provider(provider_name)
        if not provider.is_available():
            return None

        messages = [
            {
                "role": "system",
                "content": (
                    "Classify the dominant emotion of the text into exactly one of: "
                    "happy, excited, laughing, nervous, angry, neutral. "
                    "Reply with only the single emotion word, nothing else."
                ),
            },
            {"role": "user", "content": text[:500]},
        ]

        result = await asyncio.wait_for(
            provider.stream_chat(model, messages, on_token=None),
            timeout=timeout,
        )

        emotion = result.strip().lower().split()[0] if result.strip() else None
        return emotion if emotion in VALID_EMOTIONS else None
    except Exception:
        return None


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
    specialty_label: str = ""
    emoji: str = "🧙"
    mascot: str = "wizard"  # mascot sprite id


class Agent:
    def __init__(self, cfg: AgentConfig):
        self.id = cfg.id
        self.profile_id = cfg.profile_id or cfg.id
        self.name = cfg.name
        self.role = cfg.role
        self.specialty = cfg.specialty
        self.specialty_label = cfg.specialty_label
        self.provider_name = cfg.provider
        self.model = cfg.model
        self.emoji = cfg.emoji
        self.mascot = cfg.mascot
        self._provider = get_provider(cfg.provider)
        self.last_tool_call: dict | None = None

    # ── prompt ──

    def _system_prompt(self, rag_context: str | None = None, memory_context: str | None = None) -> str:
        role_desc = ROLE_DESCRIPTIONS.get(self.role, f"You are a {self.role}.")
        specialty_desc = SPECIALTY_DESCRIPTIONS.get(
            self.specialty,
            (
                f"You bring the professional lens of {self.specialty_label or self.specialty.replace('-', ' ')}. "
                "Use that domain expertise explicitly when judging trade-offs and evidence."
            ),
        )
        prompt = (
            f"You are {self.name}, participating in an AI round-table discussion.\n"
            f"Debate style: {role_desc}\n"
            f"Professional lens: {specialty_desc}\n\n"
        )
        if memory_context:
            prompt += (
                "=== Твои прошлые рассуждения по схожим темам ===\n"
                f"{memory_context}\n"
                "===\n"
                "Можешь развивать прежние идеи или пересматривать позицию. "
                "Если уместно, естественно вспоминай прошлые совместные обсуждения с текущими участниками.\n\n"
            )
        if rag_context:
            prompt += (
                "=== Предметный контекст (из загруженных документов) ===\n"
                f"{rag_context}\n"
                "===\n"
                "Используй эти факты для обоснования аргументов. "
                "Не цитируй дословно — перефразируй.\n\n"
            )
        prompt += (
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
        return prompt

    def _build_rag_query(self, ctx: dict) -> str:
        topic = ctx.get("topic", "").strip()
        history = ctx.get("history", [])
        recent = " ".join(
            (message.get("content") or "").strip()[:200]
            for message in history[-3:]
            if (message.get("content") or "").strip()
        )
        parts = [part for part in [topic, recent] if part]
        return ". ".join(parts).strip()

    def _build_memory_query(self, ctx: dict) -> str:
        topic = (ctx.get("topic") or "").strip()
        active_names = [
            item.get("name")
            for item in ctx.get("active_participants", [])
            if item.get("name") and item.get("name") != self.name
        ][:5]
        recent = " ".join(
            (message.get("content") or "").strip()[:160]
            for message in ctx.get("history", [])[-3:]
            if (message.get("content") or "").strip()
        )
        base = f"Моё мнение: {topic}" if topic else ""
        social = f"Совместные обсуждения с: {', '.join(active_names)}" if active_names else ""
        observer = ""
        if ctx.get("observer_provider") and ctx.get("observer_model"):
            observer = f"Наблюдатель: {ctx['observer_provider']}/{ctx['observer_model']}"
        return ". ".join(part for part in [base, social, observer, recent] if part).strip()

    def _truncate_rag_context(self, rag_context: str, limit: int = 8000) -> str:
        text = (rag_context or "").strip()
        if len(text) <= limit:
            return text

        clipped = text[:limit].rstrip()
        sentence_end = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
        if sentence_end >= int(limit * 0.6):
            return clipped[:sentence_end + 1].rstrip()

        line_break = clipped.rfind("\n")
        if line_break >= int(limit * 0.6):
            return clipped[:line_break].rstrip()

        whitespace = clipped.rfind(" ")
        if whitespace >= int(limit * 0.6):
            return clipped[:whitespace].rstrip()

        return clipped

    def _build_messages(self, ctx: dict) -> list[dict]:
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
        graph_id = ctx.get("graph_id")
        memory_graph_id = ctx.get("memory_graph_id")
        tool_result = ctx.get("tool_result")

        rag_context_supplied = "rag_context" in ctx
        rag_context = (ctx.get("rag_context") or "").strip()
        if not rag_context_supplied and graph_id:
            try:
                rag_query = self._build_rag_query(ctx)
                if rag_query:
                    rag_context = query_graph(graph_id, rag_query, mode="hybrid", top_k=20)
            except Exception:
                rag_context = ""
        rag_context = self._truncate_rag_context(rag_context, limit=8000) if rag_context else ""

        memory_context_supplied = "memory_context" in ctx
        memory_context = (ctx.get("memory_context") or "").strip()
        if not memory_context_supplied and memory_graph_id:
            try:
                memory_query = self._build_memory_query(ctx)
                if memory_query:
                    memory_context = query_graph(
                        memory_graph_id,
                        memory_query,
                        mode="hybrid",
                        top_k=10,
                        root_dir=PROFILE_GRAPH_ROOT,
                    )
            except Exception:
                memory_context = ""
        memory_context = self._truncate_rag_context(memory_context, limit=4000) if memory_context else ""

        msgs: list[dict] = [{
            "role": "system",
            "content": self._system_prompt(
                rag_context=rag_context,
                memory_context=memory_context,
            ),
        }]

        context_chunks: list[str] = [f'Тема обсуждения: "{topic}"']
        if room_summary:
            context_chunks.append(f"Краткая память комнаты:\n{room_summary}")
        if session_chronicle:
            context_chunks.append(f"Хроника текущей сессии:\n{session_chronicle}")
        if self._should_force_russian(topic, history):
            context_chunks.append("Отвечай строго на русском языке, без англоязычных вставок.")
        if participants:
            roster = ", ".join(
                f"{item.get('name') or 'Безымянный'} ({str(item.get('role') or 'participant').replace('-', ' ')} / {(item.get('specialtyLabel') or str(item.get('specialty') or 'generalist').replace('-', ' '))})"
                for item in participants
            )
            context_chunks.append(f"Текущий состав стола: {roster}")
        if pinned_highlights:
            highlight_lines = [
                f"- {item.get('name') or item.get('agent_name') or 'Участник'}: {item.get('content', '')}"
                for item in pinned_highlights[:4]
            ]
            context_chunks.append("Сильные зацепки, которые пользователь закрепил:\n" + "\n".join(highlight_lines))
        if tool_result:
            tool_status = "успешно" if tool_result.get("ok", True) else f"с ошибкой: {tool_result.get('error', '')}"
            context_chunks.append(
                "Результат инструмента "
                f"{tool_result.get('tool')} для запроса \"{tool_result.get('query')}\": {tool_status}\n"
                f"{tool_result.get('result') or tool_result.get('error') or 'Нет результата.'}"
            )
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
        if author_type == "system_event" or message.get("type") == "system_event":
            return f"⚡ СОБЫТИЕ: {message['content']}"

        if author_type == "user":
            return f"Пользователь: {message['content']}"

        if author_type == "observer":
            return f"Хрономант: {message['content']}"

        role = message.get("role", "participant").replace("-", " ")
        specialty = message.get("specialtyLabel") or message.get("specialty", "generalist").replace("-", " ")
        return f"{message['agent_name']} [{role} | {specialty}]: {message['content']}"

    def _should_force_russian(self, topic: str, history: list[dict]) -> bool:
        joined = " ".join([topic] + [item.get("content", "") for item in history[-8:]])
        cyrillic = sum(1 for char in joined if "а" <= char.lower() <= "я" or char.lower() == "ё")
        latin = sum(1 for char in joined if "a" <= char.lower() <= "z")
        return cyrillic > max(12, latin)

    # ── generation ──

    async def generate(self, ctx: dict, on_token=None) -> str:
        self.last_tool_call = None
        tools = self._enabled_tools(ctx)
        if tools:
            decision_messages = self._build_tool_decision_messages(ctx, tools)
            decision = await self._provider.stream_chat(self.model, decision_messages, None)
            tool_call = self._parse_tool_call(decision, tools)
            if tool_call:
                tool_result = await execute_agent_tool(tool_call["tool"], tool_call["arguments"], ctx)
                self.last_tool_call = tool_result
                messages = self._build_messages({**ctx, "tool_result": tool_result})
                final_text = await self._provider.stream_chat(self.model, messages, None)
                direct = self._sanitize_final_tool_answer(final_text, tools, tool_result)
                if on_token:
                    for chunk in self._stream_chunks(direct):
                        await on_token(chunk)
                return direct

            direct = self._parse_direct_answer(decision)
            if on_token:
                for chunk in self._stream_chunks(direct):
                    await on_token(chunk)
            return direct

        messages = self._build_messages(ctx)
        return await self._provider.stream_chat(self.model, messages, on_token)

    def _enabled_tools(self, ctx: dict) -> dict[str, dict]:
        names: list[str] = ["calculate"]
        if ctx.get("graph_id"):
            names.append("search_knowledge")
        internet_mode = str(
            ctx.get("internet_mode")
            or ctx.get("internetMode")
            or (ctx.get("tools") or {}).get("internet_mode")
            or (ctx.get("tools") or {}).get("internetMode")
            or ""
        ).strip().lower()
        if internet_mode in {"auto", "on"}:
            names.append("web_search")
        return get_tool_definitions(names)

    def _build_tool_decision_messages(self, ctx: dict, tools: dict[str, dict]) -> list[dict]:
        messages = self._build_messages(ctx)
        tool_lines = [
            f"- {name}: {spec['description']}; parameters={json.dumps(spec['parameters'], ensure_ascii=False)}"
            for name, spec in tools.items()
        ]
        tool_prompt = (
            "Перед ответом реши, нужен ли один инструмент. Доступные инструменты:\n"
            + "\n".join(tool_lines)
            + "\n\nЕсли инструмент нужен, ответь только JSON без markdown:\n"
            '{"action":"use_tool","tool":"search_knowledge","query":"точный запрос"}\n'
            "Для calculate используй поле expression или query.\n"
            "Если инструмент не нужен, дай обычную финальную реплику без JSON.\n"
            "Максимум один tool call."
        )
        messages[0] = {**messages[0], "content": f"{messages[0]['content']}\n\n{tool_prompt}"}
        return messages

    def _parse_tool_call(self, text: str, tools: dict[str, dict]) -> dict | None:
        payload = self._extract_json_object(text)
        if not payload or payload.get("action") != "use_tool":
            return None
        tool_name = payload.get("tool")
        if tool_name not in tools:
            return None
        arguments = payload.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        if payload.get("query") is not None:
            arguments["query"] = payload.get("query")
        if payload.get("expression") is not None:
            arguments["expression"] = payload.get("expression")
        return {"tool": tool_name, "arguments": arguments}

    def _parse_direct_answer(self, text: str) -> str:
        payload = self._extract_json_object(text)
        if payload and payload.get("action") == "answer" and payload.get("content"):
            return str(payload["content"]).strip()
        return (text or "").strip()

    def _sanitize_final_tool_answer(self, text: str, tools: dict[str, dict], tool_result: dict) -> str:
        if self._parse_tool_call(text, tools):
            fallback = str(tool_result.get("result") or tool_result.get("error") or "").strip()
            return fallback or "Инструмент сработал, но финальная реплика модели не пришла."
        direct = self._parse_direct_answer(text)
        return direct or "Инструмент сработал, но финальная реплика модели не пришла."

    def _extract_json_object(self, text: str) -> dict | None:
        stripped = (text or "").strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
        if fenced:
            stripped = fenced.group(1)
        elif not stripped.startswith("{"):
            match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
            if not match:
                return None
            stripped = match.group(0)
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _stream_chunks(self, text: str, size: int = 24):
        for index in range(0, len(text), size):
            yield text[index:index + size]
