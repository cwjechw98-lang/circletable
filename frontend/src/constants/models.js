export const PREFERRED_MODELS = {
  anthropic: ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-latest', 'claude-haiku-3-5-20241022'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1-mini', 'o4-mini'],
  ollama: [
    'gemma4:31b-cloud',
    'gemini-3-flash-preview:cloud',
    'qwen3.5:cloud',
    'glm-5:cloud',
    'minimax-m2.5:cloud',
    'deepseek-r1',
    'deepseek-r1:8b',
    'qwen3:4b',
    'qwen3',
    'gemma3:4b',
    'gemma3',
    'llama3.2',
  ],
}

export const EMBEDDING_MARKERS = ['embed', 'embedding', 'nomic-embed', 'text-embedding', 'bge', 'e5']

export function isEmbeddingModel(model) {
  const lower = (model || '').toLowerCase()
  return EMBEDDING_MARKERS.some((marker) => lower.includes(marker))
}

export function getModelOptions(providerName, providers = {}) {
  const providerModels = providers?.[providerName]?.models || []
  const preferredModels = PREFERRED_MODELS[providerName] || []
  const merged = Array.from(new Set([...preferredModels, ...providerModels]))
  const usable = merged.filter((model) => !isEmbeddingModel(model))
  return usable.length > 0 ? usable : merged
}

export function pickPreferredModel(providerName, providersOrModels = {}) {
  const models = Array.isArray(providersOrModels)
    ? providersOrModels
    : getModelOptions(providerName, providersOrModels)
  if (!models || models.length === 0) {
    return ''
  }

  const preferred = PREFERRED_MODELS[providerName] || []
  const exactMatch = preferred.find((model) => models.includes(model))
  if (exactMatch) {
    return exactMatch
  }

  const fallback = models.find((model) => !isEmbeddingModel(model))
  return fallback || models[0]
}
