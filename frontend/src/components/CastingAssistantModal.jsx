import React, { useEffect, useMemo, useState } from 'react'
import { MASCOT_DEFS, MASCOT_LABELS } from './Mascot.jsx'
import { ROLE_OPTIONS, getRoleLabel } from '../constants/roles.js'
import { SPECIALTY_GROUPS, getSpecialtyLabel } from '../constants/specialties.js'

const ROLE_VALUES = new Set(ROLE_OPTIONS.map((role) => role.value))
const SPECIALTY_VALUES = new Set(
  SPECIALTY_GROUPS.flatMap((group) => group.options.map((specialty) => specialty.value)),
)
const MASCOT_VALUES = new Set(Object.keys(MASCOT_DEFS))
const EMBEDDING_MARKERS = ['embed', 'embedding', 'nomic-embed', 'text-embedding', 'bge', 'e5']

function isEmbeddingModel(model) {
  const lower = (model || '').toLowerCase()
  return EMBEDDING_MARKERS.some((marker) => lower.includes(marker))
}

function usableModels(providers, providerName) {
  const models = providers?.[providerName]?.models || []
  const filtered = models.filter((model) => !isEmbeddingModel(model))
  return filtered.length > 0 ? filtered : models
}

function renderSpecialtyOptions() {
  return SPECIALTY_GROUPS.map((group) => (
    <optgroup key={group.label} label={group.label}>
      {group.options.map((specialty) => (
        <option key={specialty.value} value={specialty.value}>
          {specialty.label}
        </option>
      ))}
    </optgroup>
  ))
}

function formatMascotLabel(mascot) {
  const label = MASCOT_LABELS[mascot] || mascot
  return label ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : mascot
}

function buildParticipantLine(participant) {
  const roleLabel = getRoleLabel(participant?.role) || participant?.role || 'Участник'
  const specialtyLabel = getSpecialtyLabel(participant?.specialty) || participant?.specialty || 'Без профиля'
  return `${participant?.name || 'Безымянный'} — ${roleLabel}, ${specialtyLabel}`
}

function normalizeDraft(draft, index, fallbackProvider = 'ollama', fallbackModel = '') {
  const mascot = MASCOT_VALUES.has(draft?.mascot) ? draft.mascot : 'wizard'
  const role = ROLE_VALUES.has(draft?.role) ? draft.role : 'analyst'
  const specialty = SPECIALTY_VALUES.has(draft?.specialty) ? draft.specialty : 'digital-generalist'

  return {
    id: draft?.id || `draft-${Date.now()}-${index}`,
    name: String(draft?.name || `Герой ${index + 1}`).trim(),
    role,
    specialty,
    provider: draft?.provider || fallbackProvider,
    model: draft?.model || fallbackModel,
    mascot,
    emoji: MASCOT_DEFS[mascot]?.emoji || draft?.emoji || '🧙',
    summary: draft?.summary || '',
    lastNote: draft?.lastNote || 'Предложен кастинг-помощником под текущую задачу.',
  }
}

export default function CastingAssistantModal({
  open,
  mode = 'full',
  topic,
  provider,
  model,
  providers,
  disabled,
  roomSummary,
  sessionChronicle,
  latestRoundSummary,
  activeParticipants,
  assistantProvider,
  assistantModel,
  missingExpertHint,
  onAssistantChange,
  onClose,
  onAccept,
}) {
  const [count, setCount] = useState(4)
  const [drafts, setDrafts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [contextCollapsed, setContextCollapsed] = useState(false)

  const trimmedTopic = topic.trim()
  const gapFill = mode === 'gap_fill'
  const canGenerate = !loading && trimmedTopic.length > 0 && !disabled
  const canAccept = drafts.length > 0 && !loading
  const availableProviders = useMemo(
    () => Object.entries(providers || {})
      .filter(([, value]) => value.available)
      .map(([key]) => key),
    [providers],
  )
  const assistantModels = useMemo(
    () => usableModels(providers, assistantProvider),
    [assistantProvider, providers],
  )
  const rosterPreview = useMemo(
    () => (activeParticipants || []).slice(0, 4).map(buildParticipantLine),
    [activeParticipants],
  )
  const activeCount = (activeParticipants || []).length
  const hasContext = Boolean(
    roomSummary?.trim()
    || sessionChronicle?.trim()
    || latestRoundSummary?.trim()
    || activeCount > 0,
  )

  useEffect(() => {
    if (!open) {
      setLoading(false)
      setError('')
      setMessage('')
      setDrafts([])
      setContextCollapsed(false)
      return
    }

    if (drafts.length === 0) {
      setCount(gapFill ? 2 : 4)
    }
  }, [drafts.length, gapFill, open])

  const roleOptions = useMemo(() => ROLE_OPTIONS, [])
  const mascotOptions = useMemo(() => Object.keys(MASCOT_DEFS), [])

  useEffect(() => {
    if (!open) return
    if (availableProviders.length > 0 && !availableProviders.includes(assistantProvider)) {
      onAssistantChange({
        provider: availableProviders.includes(provider) ? provider : availableProviders[0],
        model: assistantModel,
      })
    }
  }, [assistantModel, assistantProvider, availableProviders, onAssistantChange, open, provider])

  useEffect(() => {
    if (!open || assistantModels.length === 0) return
    if (!assistantModel || !assistantModels.includes(assistantModel)) {
      const preferred = assistantModels.includes(model) ? model : assistantModels[0]
      onAssistantChange({
        provider: assistantProvider,
        model: preferred,
      })
    }
  }, [assistantModel, assistantModels, assistantProvider, model, onAssistantChange, open])

  function modelOptionsFor(providerName) {
    return usableModels(providers, providerName)
  }

  function updateDraftProvider(index, nextProvider) {
    const models = modelOptionsFor(nextProvider)
    updateDraft(index, {
      provider: nextProvider,
      model: models[0] || '',
    })
  }

  async function generateDrafts() {
    if (!trimmedTopic) {
      setError('Сначала введите тему или вопрос.')
      return
    }

    setLoading(true)
    setError('')
    setMessage(gapFill
      ? 'Помощник сверяет тему, хронику и ищет недостающий голос...'
      : 'Помощник читает тему и собирает состав...')

    try {
      const response = await fetch('/api/casting/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: trimmedTopic,
          count,
          mode,
          provider: assistantProvider,
          model: assistantModel,
          roomSummary,
          sessionChronicle,
          latestRoundSummary,
          missingExpertHint,
          activeParticipants: (activeParticipants || []).map((participant) => ({
            name: participant.name,
            role: participant.role,
            specialty: participant.specialty,
            provider: participant.provider,
            model: participant.model,
          })),
        }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data?.detail || 'Не удалось собрать состав.')
      }
      const nextDrafts = (data.characters || []).map((draft, index) => normalizeDraft({
        ...draft,
        provider: draft.provider || assistantProvider,
        model: draft.model || assistantModel,
      }, index, assistantProvider, assistantModel))
      setDrafts(nextDrafts)
      setContextCollapsed(true)
      setMessage(data.message || 'Черновик состава готов.')
    } catch (err) {
      setError(err.message || 'Помощник не смог ответить.')
      setMessage('')
    } finally {
      setLoading(false)
    }
  }

  function updateDraft(index, patch) {
    setDrafts((current) => current.map((draft, draftIndex) => {
      if (draftIndex !== index) return draft
      const merged = { ...draft, ...patch }
      if (patch.mascot) {
        merged.emoji = MASCOT_DEFS[patch.mascot]?.emoji || merged.emoji
      }
      return normalizeDraft(merged, draftIndex)
    }))
  }

  function removeDraft(index) {
    setDrafts((current) => current.filter((_, draftIndex) => draftIndex !== index))
  }

  function acceptDrafts() {
    onAccept(drafts.map((draft, index) => normalizeDraft(draft, index, assistantProvider, assistantModel)))
    onClose()
  }

  if (!open) {
    return null
  }

  return (
    <div className="assistant-modal-shell" role="dialog" aria-modal="true" aria-label="Кастинг-помощник">
      <div className="assistant-modal">
        <div className="assistant-modal-header">
          <div>
            <div className="drawer-kicker">Кастинг-помощник</div>
            <div className="assistant-title">
              {gapFill ? 'Найти недостающих героев' : 'Подобрать героев под задачу'}
            </div>
          </div>
          <button className="drawer-close" onClick={onClose} aria-label="Закрыть">×</button>
        </div>

        <div className="assistant-topic-card">
          <div className="assistant-topic-label">Текущая тема</div>
          <div className="assistant-topic-text">
            {trimmedTopic || 'Тема пока не введена.'}
          </div>
        </div>

        {hasContext && (
          <div className="assistant-context-card">
            <div className="assistant-context-head">
              <div className="assistant-topic-label">Что ещё видит помощник</div>
              <button
                type="button"
                className="assistant-context-toggle"
                onClick={() => setContextCollapsed((value) => !value)}
              >
                {contextCollapsed ? 'Развернуть' : 'Свернуть'}
              </button>
            </div>
            {!contextCollapsed ? (
              <div className="assistant-context-list">
                {latestRoundSummary?.trim() && (
                  <div className="assistant-context-line">
                    <strong>Свежий раунд:</strong> {latestRoundSummary.trim()}
                  </div>
                )}
                {sessionChronicle?.trim() && (
                  <div className="assistant-context-line">
                    <strong>Хроника сессии:</strong> {sessionChronicle.trim()}
                  </div>
                )}
                {roomSummary?.trim() && (
                  <div className="assistant-context-line">
                    <strong>Память комнаты:</strong> {roomSummary.trim()}
                  </div>
                )}
                {rosterPreview.length > 0 && (
                  <div className="assistant-context-line">
                    <strong>Текущий состав:</strong> {rosterPreview.join(' • ')}
                    {activeCount > rosterPreview.length && ` • ещё ${activeCount - rosterPreview.length}`}
                  </div>
                )}
              </div>
            ) : (
              <div className="assistant-context-collapsed">
                Тема, свежий раунд, хроника и текущий состав свернуты, чтобы освободить место для вариантов.
              </div>
            )}
          </div>
        )}

        {gapFill && missingExpertHint && (
          <div className="assistant-gap-hint">
            Подсказка Хрономанта: {missingExpertHint}
          </div>
        )}

        <div className="assistant-controls">
          <label className="assistant-count">
            Количество персонажей
            <select
              className="mini-select"
              value={count}
              onChange={(event) => setCount(Number(event.target.value))}
              disabled={loading}
            >
              {[2, 3, 4, 5, 6, 7, 8].map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>

          <label className="assistant-count">
            Модель помощника
            <select
              className="mini-select"
              value={assistantProvider}
              onChange={(event) => onAssistantChange({
                provider: event.target.value,
                model: modelOptionsFor(event.target.value)[0] || '',
              })}
              disabled={loading}
            >
              {availableProviders.map((providerName) => (
                <option key={providerName} value={providerName}>{providerName}</option>
              ))}
            </select>
          </label>

          <select
            className="mini-select assistant-model-select"
            value={assistantModel}
            onChange={(event) => onAssistantChange({
              provider: assistantProvider,
              model: event.target.value,
            })}
            disabled={loading || assistantModels.length === 0}
            data-hint="Эта модель придумывает состав персонажей."
          >
            {assistantModels.map((modelName) => (
              <option key={modelName} value={modelName}>{modelName}</option>
            ))}
          </select>

          <button
            className="pixel-btn start"
            onClick={generateDrafts}
            disabled={!canGenerate}
          >
            {loading ? 'Думает...' : gapFill ? 'Найти недостающих' : 'Создать варианты'}
          </button>
        </div>

        {disabled && (
          <div className="assistant-warning">
            Менять состав можно до старта или во время паузы.
          </div>
        )}

        {message && <div className="assistant-message">{message}</div>}
        {error && <div className="assistant-error">{error}</div>}
        {!error && (
          <div className="assistant-brain-note">
            {gapFill
              ? 'Выбранная здесь модель становится общим мозгом помощника для следующих подборов. В этом режиме помощник ищет не абстрактно сильных, а именно недостающих героев под текущий стол.'
              : 'Выбранная здесь модель становится общим мозгом помощника для следующих подборов. Помощник подбирает не просто “красивых” героев, а недостающие голоса под тему, текущий состав и свежий ход беседы.'}
          </div>
        )}

        <div className="assistant-draft-list">
          {drafts.length === 0 && (
            <div className="drawer-empty">
              {gapFill
                ? 'Нажмите «Найти недостающих», и помощник предложит тех, кого сейчас не хватает за столом.'
                : 'Нажмите «Создать варианты», и помощник предложит готовую команду для круглого стола.'}
            </div>
          )}

          {drafts.map((draft, index) => (
            <div key={draft.id} className="assistant-draft-card">
              <div className="assistant-draft-avatar">
                {MASCOT_DEFS[draft.mascot]?.emoji || draft.emoji || '🧙'}
              </div>

              <div className="assistant-draft-fields">
                <input
                  className="mini-input"
                  value={draft.name}
                  onChange={(event) => updateDraft(index, { name: event.target.value })}
                  placeholder="Имя"
                />

                <select
                  className="mini-select"
                  value={draft.role}
                  onChange={(event) => updateDraft(index, { role: event.target.value })}
                >
                  {roleOptions.map((role) => (
                    <option key={role.value} value={role.value}>{role.label}</option>
                  ))}
                </select>

                <select
                  className="mini-select"
                  value={draft.specialty}
                  onChange={(event) => updateDraft(index, { specialty: event.target.value })}
                >
                  {renderSpecialtyOptions()}
                </select>

                <select
                  className="mini-select"
                  value={draft.mascot}
                  onChange={(event) => updateDraft(index, { mascot: event.target.value })}
                >
                  {mascotOptions.map((mascot) => (
                    <option key={mascot} value={mascot}>
                      {MASCOT_DEFS[mascot].emoji} {formatMascotLabel(mascot)}
                    </option>
                  ))}
                </select>

                <select
                  className="mini-select"
                  value={draft.provider}
                  onChange={(event) => updateDraftProvider(index, event.target.value)}
                  data-hint="Провайдер этого персонажа."
                >
                  {availableProviders.map((providerName) => (
                    <option key={providerName} value={providerName}>{providerName}</option>
                  ))}
                </select>

                <select
                  className="mini-select"
                  value={draft.model}
                  onChange={(event) => updateDraft(index, { model: event.target.value })}
                  data-hint="Модель этого персонажа."
                >
                  {modelOptionsFor(draft.provider).map((modelName) => (
                    <option key={modelName} value={modelName}>{modelName}</option>
                  ))}
                </select>

                <textarea
                  className="assistant-textarea"
                  value={draft.summary}
                  onChange={(event) => updateDraft(index, { summary: event.target.value })}
                  placeholder="Зачем этот персонаж нужен в обсуждении"
                />

                <div className="assistant-draft-meta">
                  {getRoleLabel(draft.role)} · {getSpecialtyLabel(draft.specialty)} · {draft.provider}/{draft.model || 'модель не выбрана'}
                </div>
              </div>

              <button className="pixel-btn danger" onClick={() => removeDraft(index)}>
                Удалить
              </button>
            </div>
          ))}
        </div>

        <div className="assistant-actions">
          <button className="pixel-btn ghost" onClick={onClose}>Отмена</button>
          <button className="pixel-btn add" onClick={acceptDrafts} disabled={!canAccept}>
            Добавить за стол
          </button>
        </div>
      </div>
    </div>
  )
}
