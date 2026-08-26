"""Кастомный OpenAI-совместимый провайдер.

Используется для пресетов (DeepSeek, OpenRouter, Groq, Mistral, Together,
xAI, Gemini OpenAI-compat и т.д.) и любых пользовательских endpoint'ов,
совместимых с /chat/completions и /models.
"""
from __future__ import annotations

import json

import httpx


class CustomOpenAIProvider:
    def __init__(self, provider_id: str, name: str, base_url: str, api_key: str = ""):
        self.provider_id = provider_id
        self.name = name or provider_id
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""

    def public_payload(self) -> dict:
        """Данные для UI без полного ключа."""
        masked = f"...{self.api_key[-4:]}" if len(self.api_key) > 4 else ("***" if self.api_key else "")
        return {
            "id": self.provider_id,
            "name": self.name,
            "baseUrl": self.base_url,
            "keyHint": masked,
        }

    def is_available(self) -> bool:
        return bool(self.base_url)

    async def list_models(self) -> list[str]:
        if not self.base_url:
            return []
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/models", headers=headers)
                resp.raise_for_status()
                payload = resp.json()
        except Exception:
            return []
        items = payload.get("data", payload) if isinstance(payload, dict) else payload
        models: list[str] = []
        for item in items or []:
            model_id = item.get("id") if isinstance(item, dict) else item
            if model_id:
                models.append(str(model_id))
        return sorted(models)

    async def stream_chat(self, model: str, messages: list[dict], on_token) -> str:
        if not self.base_url:
            raise RuntimeError(f"Провайдер {self.name}: не задан base_url")

        body = {
            "model": model,
            "stream": True,
            "max_tokens": 400,
            "messages": messages,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        full_text = ""
        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", json=body, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices", [])
                    if choices:
                        token = choices[0].get("delta", {}).get("content")
                        if token:
                            full_text += token
                            if on_token:
                                await on_token(token)
        return full_text
