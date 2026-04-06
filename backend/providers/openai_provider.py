import os
import json
import httpx

API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "o4-mini",
]


class OpenAIProvider:
    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    async def list_models(self) -> list[str]:
        return DEFAULT_MODELS if self.is_available() else []

    async def stream_chat(self, model: str, messages: list[dict], on_token) -> str:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        body = {
            "model": model,
            "stream": True,
            "max_tokens": 400,
            "messages": messages,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        full_text = ""
        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream("POST", API_URL, json=body, headers=headers) as resp:
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
