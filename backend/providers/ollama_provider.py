import json
import httpx

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_CLOUD_MODEL_HINTS = ["gemma4:31b-cloud"]


class OllamaProvider:
    def is_available(self) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=2)
            return True
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{OLLAMA_BASE}/api/tags")
                resp.raise_for_status()
                models = resp.json().get("models", [])
                names = [m["name"] for m in models]
                for model_name in OLLAMA_CLOUD_MODEL_HINTS:
                    if model_name in names:
                        continue
                    try:
                        show_resp = await client.post(f"{OLLAMA_BASE}/api/show", json={"model": model_name})
                        if show_resp.status_code < 400:
                            names.append(model_name)
                    except Exception:
                        continue
                return names
        except Exception:
            return []

    async def stream_chat(self, model: str, messages: list[dict], on_token) -> str:
        full_text = ""
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE}/api/chat",
                json={"model": model, "messages": messages, "stream": True},
            ) as resp:
                resp.raise_for_status()
                async for raw_line in resp.aiter_lines():
                    if not raw_line.strip():
                        continue
                    try:
                        data = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("done"):
                        break
                    token = data.get("message", {}).get("content", "")
                    if token:
                        full_text += token
                        if on_token:
                            await on_token(token)
        return full_text
