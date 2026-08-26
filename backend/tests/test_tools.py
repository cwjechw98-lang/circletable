from __future__ import annotations

import asyncio

from tools import calculate_handler, execute_agent_tool, get_tool_definitions, search_external_snippets, web_search_handler, SearchSnippet


class TestAgentTools:
    def test_get_tool_definitions_filters_available_tools(self):
        tools = get_tool_definitions(["calculate"])
        assert list(tools.keys()) == ["calculate"]
        assert tools["calculate"]["parameters"]["expression"] == "str"

    def test_calculate_handler_evaluates_safe_math(self):
        result = asyncio.run(calculate_handler({"expression": "sqrt(16) + 2 * 3"}, {}))
        assert result.ok is True
        assert result.result == "10"

    def test_calculate_handler_rejects_unsafe_expression(self):
        result = asyncio.run(calculate_handler({"expression": "__import__('os').system('echo bad')"}, {}))
        assert result.ok is False
        assert "Недопустимое" in result.error or "not defined" in result.error

    def test_execute_unknown_tool_returns_error_payload(self):
        result = asyncio.run(execute_agent_tool("missing_tool", {}, {}))
        assert result["ok"] is False
        assert result["tool"] == "missing_tool"

    def test_web_search_handler_blocks_when_internet_is_off(self):
        result = asyncio.run(web_search_handler({"query": "latest ai regulation"}, {"internet_mode": "off"}))
        assert result.ok is False
        assert "интернет отключён" in result.error.lower()

    def test_search_external_snippets_prefers_science_sources(self, monkeypatch):
        async def fake_science(_client, query):
            return [SearchSnippet("science", "PubMed", f"{query} study", "Journal, 2026")]

        async def fake_web(_client, _query):
            return [SearchSnippet("web", "DuckDuckGo", "fallback", "fallback")]

        monkeypatch.setattr("tools._science_search_snippets", fake_science)
        monkeypatch.setattr("tools._general_web_search_snippets", fake_web)

        snippets, meta = asyncio.run(search_external_snippets(
            "clinical study on glucose control",
            {"internet_mode": "auto", "topic": "medical research"},
        ))
        assert meta["source"] == "science"
        assert meta["scienceFirst"] is True
        assert snippets[0].source_label == "PubMed"
