import os
import json
import httpx

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-haiku-3-5-20241022",
]


class AnthropicProvider:
    def is_available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    async def list_models(self) -> list[str]:
        return DEFAULT_MODELS if self.is_available() else []

    async def stream_chat(self, model: str, messages: list[dict], on_token) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        # Anthropic separates system from messages
        system_text = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system_text += m["content"] + "\n"
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})

        body = {
            "model": model,
            "max_tokens": 400,
            "stream": True,
            "messages": chat_messages,
        }
        if system_text.strip():
            body["system"] = system_text.strip()

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        full_text = ""
        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream("POST", API_URL, json=body, headers=headers) as resp:
                resp.raise_for_status()
                current_event = None
                async for line in resp.aiter_lines():
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        if current_event == "content_block_delta":
                            token = data.get("delta", {}).get("text", "")
                            if token:
                                full_text += token
                                if on_token:
                                    await on_token(token)
                    elif not line.strip():
                        current_event = None

        return full_text
