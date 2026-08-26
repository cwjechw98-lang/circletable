from __future__ import annotations

import ast
import asyncio
import base64
import html
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from knowledge.lightrag_adapter import query_graph


@dataclass
class ToolResult:
    tool: str
    query: str
    result: str
    ok: bool = True
    error: str = ""

    def as_payload(self) -> dict:
        return {
            "tool": self.tool,
            "query": self.query,
            "result": self.result,
            "ok": self.ok,
            "error": self.error,
        }


@dataclass
class SearchSnippet:
    source_type: str
    source_label: str
    title: str
    snippet: str
    url: str = ""

    def as_line(self) -> str:
        source = f"[{self.source_label}] " if self.source_label else ""
        fallback = self.url or "Без ссылки"
        text = self.snippet or fallback
        return f"- {source}{self.title or 'Без названия'}: {text}".strip()


SCIENCE_KEYWORDS = (
    "science", "scientific", "research", "study", "paper", "journal", "trial",
    "medical", "medicine", "clinical", "biology", "biological", "biotech",
    "genetics", "genomic", "protein", "molecule", "chemical", "chemistry",
    "disease", "treatment", "therapy", "drug", "pharma", "patient",
    "наук", "исследован", "статья", "журнал", "медицин", "клиничес",
    "биолог", "биотех", "генет", "геном", "белок", "молекул", "хим",
    "болезн", "лечение", "терап", "препарат", "фарма", "пациент",
)


def _truncate_text(text: str, limit: int = 240) -> str:
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit].rstrip()}…"


def _render_snippets(snippets: list[SearchSnippet], limit: int = 4000) -> str:
    lines: list[str] = []
    total = 0
    for snippet in snippets:
        line = snippet.as_line()
        total += len(line)
        if total > limit and lines:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _normalize_internet_mode(ctx: dict | None) -> str:
    ctx = ctx or {}
    raw_mode = str(
        ctx.get("internet_mode")
        or ctx.get("internetMode")
        or (ctx.get("tools") or {}).get("internet_mode")
        or (ctx.get("tools") or {}).get("internetMode")
        or ""
    ).strip().lower()
    if raw_mode in {"off", "auto", "on"}:
        return raw_mode

    settings = ctx.get("tools") or {}
    legacy_available = {str(name) for name in (settings.get("available_tools") or settings.get("availableTools") or [])}
    tools_enabled = bool(settings.get("tools_enabled", settings.get("toolsEnabled", settings.get("enabled", False))))
    if tools_enabled and "web_search" in legacy_available:
        return "auto"
    return "off"


def _prefer_science_sources(query: str, ctx: dict | None = None) -> bool:
    haystack = " ".join([
        str(query or ""),
        str((ctx or {}).get("topic") or ""),
    ]).lower()
    return any(keyword in haystack for keyword in SCIENCE_KEYWORDS)


async def _search_pubmed_snippets(client: httpx.AsyncClient, query: str) -> list[SearchSnippet]:
    search_response = await client.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db": "pubmed", "retmode": "json", "retmax": 3, "term": query},
    )
    search_response.raise_for_status()
    search_payload = search_response.json()
    ids = ((search_payload.get("esearchresult") or {}).get("idlist") or [])[:3]
    if not ids:
        return []

    summary_response = await client.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "pubmed", "retmode": "json", "id": ",".join(ids)},
    )
    summary_response.raise_for_status()
    summary_payload = summary_response.json().get("result") or {}

    snippets: list[SearchSnippet] = []
    for item_id in ids:
        item = summary_payload.get(item_id) or {}
        title = _truncate_text(str(item.get("title") or "").strip(), 160)
        source = str(item.get("fulljournalname") or item.get("source") or "PubMed").strip()
        pubdate = str(item.get("pubdate") or "").strip()
        excerpt = ", ".join(part for part in [source, pubdate] if part) or "PubMed"
        if title:
            snippets.append(SearchSnippet("science", "PubMed", title, excerpt))
    return snippets


async def _search_europe_pmc_snippets(client: httpx.AsyncClient, query: str) -> list[SearchSnippet]:
    response = await client.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": query, "format": "json", "pageSize": 3},
    )
    response.raise_for_status()
    payload = response.json()
    results = ((payload.get("resultList") or {}).get("result") or [])[:3]
    snippets: list[SearchSnippet] = []
    for item in results:
        title = _truncate_text(str(item.get("title") or "").strip(), 160)
        journal = str(item.get("journalTitle") or item.get("source") or "Europe PMC").strip()
        year = str(item.get("pubYear") or "").strip()
        authors = _truncate_text(str(item.get("authorString") or "").strip(), 140)
        excerpt = ", ".join(part for part in [journal, year, authors] if part)
        if title:
            snippets.append(SearchSnippet("science", "Europe PMC", title, excerpt, item.get("doi") or ""))
    return snippets


async def _search_crossref_snippets(client: httpx.AsyncClient, query: str) -> list[SearchSnippet]:
    response = await client.get(
        "https://api.crossref.org/works",
        params={"query.bibliographic": query, "rows": 3},
        headers={"User-Agent": "CircleTable/1.0 (research mode)"},
    )
    response.raise_for_status()
    items = ((response.json().get("message") or {}).get("items") or [])[:3]
    snippets: list[SearchSnippet] = []
    for item in items:
        title_value = ((item.get("title") or [""]) or [""])[0]
        container = ((item.get("container-title") or [""]) or [""])[0]
        year_parts = (
            (item.get("published-print") or {}).get("date-parts")
            or (item.get("published-online") or {}).get("date-parts")
            or []
        )
        year = ""
        if year_parts and year_parts[0]:
            year = str(year_parts[0][0])
        authors = []
        for author in (item.get("author") or [])[:3]:
            family = str(author.get("family") or "").strip()
            given = str(author.get("given") or "").strip()
            full = " ".join(part for part in [given, family] if part)
            if full:
                authors.append(full)
        excerpt = ", ".join(part for part in [container, year, "; ".join(authors)] if part)
        title = _truncate_text(title_value, 160)
        if title:
            snippets.append(SearchSnippet("science", "Crossref", title, excerpt, item.get("URL") or ""))
    return snippets


async def _search_clinical_trials_snippets(client: httpx.AsyncClient, query: str) -> list[SearchSnippet]:
    response = await client.get(
        "https://clinicaltrials.gov/api/query/study_fields",
        params={
            "expr": query,
            "fields": "BriefTitle,Condition,OverallStatus,NCTId,Phase",
            "min_rnk": 1,
            "max_rnk": 3,
            "fmt": "json",
        },
    )
    response.raise_for_status()
    studies = (((response.json().get("StudyFieldsResponse") or {}).get("StudyFields")) or [])[:3]
    snippets: list[SearchSnippet] = []
    for item in studies:
        title = _truncate_text(" ".join(item.get("BriefTitle") or []), 160)
        condition = _truncate_text(", ".join(item.get("Condition") or []), 120)
        status = " ".join(item.get("OverallStatus") or [])
        phase = " ".join(item.get("Phase") or [])
        nct_id = " ".join(item.get("NCTId") or [])
        excerpt = ", ".join(part for part in [condition, status, phase, nct_id] if part)
        if title:
            snippets.append(SearchSnippet("science", "ClinicalTrials", title, excerpt, nct_id))
    return snippets


async def _science_search_snippets(client: httpx.AsyncClient, query: str) -> list[SearchSnippet]:
    snippets: list[SearchSnippet] = []
    for search_fn in (
        _search_pubmed_snippets,
        _search_europe_pmc_snippets,
        _search_crossref_snippets,
        _search_clinical_trials_snippets,
    ):
        try:
            snippets.extend(await search_fn(client, query))
        except Exception:
            continue
        if len(snippets) >= 5:
            break
    return snippets[:5]


async def _general_web_search_snippets(client: httpx.AsyncClient, query: str) -> list[SearchSnippet]:
    searxng_url = (os.getenv("SEARXNG_URL") or "").strip().rstrip("/")
    if searxng_url:
        response = await client.get(
            f"{searxng_url}/search",
            params={"q": query, "format": "json", "language": "ru-RU"},
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("results", [])[:5]
        snippets = [
            SearchSnippet(
                "web",
                "SearXNG",
                _truncate_text(str(item.get("title") or "Без названия"), 140),
                _truncate_text(str(item.get("content") or item.get("url") or ""), 220),
                str(item.get("url") or ""),
            )
            for item in items
            if item.get("title") or item.get("content") or item.get("url")
        ]
        if snippets:
            return snippets

    response = await client.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1, "skip_disambig": 1},
    )
    response.raise_for_status()
    payload = response.json()
    snippets: list[SearchSnippet] = []
    abstract = (payload.get("AbstractText") or "").strip()
    if abstract:
        snippets.append(SearchSnippet("web", "DuckDuckGo", query, _truncate_text(abstract, 220)))
    for topic in payload.get("RelatedTopics", [])[:5]:
        if "Text" in topic:
            snippets.append(SearchSnippet("web", "DuckDuckGo", query, _truncate_text(topic["Text"], 220)))
        for nested in topic.get("Topics", [])[:3]:
            if "Text" in nested:
                snippets.append(SearchSnippet("web", "DuckDuckGo", query, _truncate_text(nested["Text"], 220)))
    if snippets:
        return snippets[:5]

    response = await client.get(
        "https://www.bing.com/search",
        params={"q": query, "setlang": "ru"},
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    return _parse_bing_results(response.text)


async def search_external_snippets(query: str, ctx: dict | None = None) -> tuple[list[SearchSnippet], dict[str, Any]]:
    query = str(query or "").strip()
    if not query:
        return [], {"internetMode": _normalize_internet_mode(ctx), "scienceFirst": False, "source": "empty"}

    internet_mode = _normalize_internet_mode(ctx)
    if internet_mode == "off":
        return [], {"internetMode": internet_mode, "scienceFirst": False, "source": "blocked"}

    science_first = _prefer_science_sources(query, ctx)
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        if science_first:
            science_snippets = await _science_search_snippets(client, query)
            if science_snippets:
                return science_snippets, {"internetMode": internet_mode, "scienceFirst": True, "source": "science"}

        web_snippets = await _general_web_search_snippets(client, query)
        if web_snippets:
            return web_snippets, {"internetMode": internet_mode, "scienceFirst": science_first, "source": "web"}

        if science_first:
            science_snippets = await _science_search_snippets(client, query)
            if science_snippets:
                return science_snippets, {"internetMode": internet_mode, "scienceFirst": True, "source": "science"}

    return [], {"internetMode": internet_mode, "scienceFirst": science_first, "source": "none"}


async def search_knowledge_handler(arguments: dict, ctx: dict) -> ToolResult:
    query = str(arguments.get("query") or "").strip()
    graph_id = ctx.get("graph_id")
    if not query:
        return ToolResult("search_knowledge", query, "", ok=False, error="Пустой запрос к графу знаний.")
    if not graph_id:
        return ToolResult("search_knowledge", query, "", ok=False, error="У комнаты нет подключённого графа знаний.")

    try:
        result = await asyncio.to_thread(query_graph, graph_id, query, "hybrid", 12)
    except Exception as exc:
        return ToolResult("search_knowledge", query, "", ok=False, error=str(exc))
    return ToolResult("search_knowledge", query, (result or "").strip()[:4000])


async def web_search_handler(arguments: dict, ctx: dict) -> ToolResult:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return ToolResult("web_search", query, "", ok=False, error="Пустой поисковый запрос.")
    try:
        snippets, meta = await search_external_snippets(query, ctx)
    except Exception as exc:
        return ToolResult("web_search", query, "", ok=False, error=str(exc))
    if meta.get("internetMode") == "off":
        return ToolResult("web_search", query, "", ok=False, error="В этой комнате интернет отключён.")
    rendered = _render_snippets(snippets)
    if rendered:
        return ToolResult("web_search", query, rendered[:4000])
    return ToolResult("web_search", query, "Поиск не дал краткого ответа.", ok=False, error="Ничего не найдено.")


def _strip_html(value: str) -> str:
    return html.unescape(re.sub(r"<.*?>", "", value, flags=re.DOTALL)).strip()


def _decode_bing_url(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    query = parse_qs(parsed.query)
    encoded = (query.get("u") or [""])[0]
    if encoded.startswith("a1"):
        payload = encoded[2:]
        payload += "=" * (-len(payload) % 4)
        try:
            return base64.urlsafe_b64decode(payload).decode("utf-8", errors="replace")
        except Exception:
            pass
    return unquote(url)


def _parse_bing_results(markup: str) -> list[SearchSnippet]:
    results: list[SearchSnippet] = []
    for match in re.finditer(r'<li class="b_algo".*?</li>', markup, flags=re.DOTALL):
        block = match.group(0)
        title_match = re.search(r'<h2.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.DOTALL)
        if not title_match:
            continue
        snippet_match = re.search(r"<p>(.*?)</p>", block, flags=re.DOTALL)
        title = _strip_html(title_match.group(2))
        url = _decode_bing_url(title_match.group(1))
        snippet = _strip_html(snippet_match.group(1)) if snippet_match else ""
        if title:
            results.append(SearchSnippet("web", "Bing", title, snippet or url, url))
        if len(results) >= 5:
            break
    return results


_ALLOWED_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}
_ALLOWED_UNARY_OPS = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}
_ALLOWED_FUNCS = {
    "abs": abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
}
_ALLOWED_CONSTS = {"pi": math.pi, "e": math.e}


def _eval_math_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_math_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _ALLOWED_CONSTS:
        return _ALLOWED_CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BIN_OPS:
        left = _eval_math_node(node.left)
        right = _eval_math_node(node.right)
        return _ALLOWED_BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPS:
        return _ALLOWED_UNARY_OPS[type(node.op)](_eval_math_node(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        args = [_eval_math_node(arg) for arg in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise ValueError("Недопустимое математическое выражение.")


async def calculate_handler(arguments: dict, _ctx: dict) -> ToolResult:
    expression = str(arguments.get("expression") or arguments.get("query") or "").strip()
    if not expression:
        return ToolResult("calculate", expression, "", ok=False, error="Пустое выражение.")
    try:
        tree = ast.parse(expression, mode="eval")
        value = _eval_math_node(tree)
    except Exception as exc:
        return ToolResult("calculate", expression, "", ok=False, error=str(exc))
    return ToolResult("calculate", expression, f"{value:g}")


ToolHandler = Callable[[dict, dict], Any]

AGENT_TOOLS: dict[str, dict[str, Any]] = {
    "search_knowledge": {
        "description": "Поиск фактов в загруженных документах комнаты",
        "parameters": {"query": "str"},
        "handler": search_knowledge_handler,
    },
    "web_search": {
        "description": "Поиск в интернете через SearXNG или DuckDuckGo Instant Answer",
        "parameters": {"query": "str"},
        "handler": web_search_handler,
    },
    "calculate": {
        "description": "Безопасное вычисление математического выражения",
        "parameters": {"expression": "str"},
        "handler": calculate_handler,
    },
}


def get_tool_definitions(names: list[str] | None = None) -> dict[str, dict[str, Any]]:
    allowed = set(names or AGENT_TOOLS.keys())
    return {
        name: {
            "description": spec["description"],
            "parameters": spec["parameters"],
        }
        for name, spec in AGENT_TOOLS.items()
        if name in allowed
    }


async def execute_agent_tool(tool_name: str, arguments: dict, ctx: dict) -> dict:
    spec = AGENT_TOOLS.get(tool_name)
    if not spec:
        return ToolResult(tool_name, "", "", ok=False, error="Неизвестный инструмент.").as_payload()
    result = await spec["handler"](arguments, ctx)
    return result.as_payload()
