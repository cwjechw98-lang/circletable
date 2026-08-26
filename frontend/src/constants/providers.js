// Библиотека пресетов провайдеров — зеркалирует PROVIDER_PRESETS в backend/http_api/routes_custom_providers.py
export const PROVIDER_PRESETS = [
  { id: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', hint: 'Ключ platform.deepseek.com' },
  { id: 'openrouter', label: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1', hint: 'Сотни моделей одним ключом' },
  { id: 'groq', label: 'Groq', baseUrl: 'https://api.groq.com/openai/v1', hint: 'Очень быстрый инференс' },
  { id: 'mistral', label: 'Mistral', baseUrl: 'https://api.mistral.ai/v1', hint: 'Ключ console.mistral.ai' },
  { id: 'together', label: 'Together AI', baseUrl: 'https://api.together.xyz/v1', hint: 'Open-source модели в облаке' },
  { id: 'xai', label: 'xAI (Grok)', baseUrl: 'https://api.x.ai/v1', hint: 'Модели Grok' },
  { id: 'gemini-openai', label: 'Google Gemini (OpenAI-совместимый)', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai', hint: 'Ключ Google AI Studio' },
  { id: 'fireworks', label: 'Fireworks AI', baseUrl: 'https://api.fireworks.ai/inference/v1', hint: 'Быстрый хостинг open-source' },
  { id: 'lmstudio-local', label: 'LM Studio (локально)', baseUrl: 'http://localhost:1234/v1', hint: 'Локальный сервер без ключа' },
]

export const STATIC_PROVIDER_LABELS = {
  ollama: 'Ollama (локальные и :cloud)',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
}
