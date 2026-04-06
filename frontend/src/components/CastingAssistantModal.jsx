import React, { useEffect, useMemo, useState } from 'react'
import { MASCOT_DEFS } from './Mascot.jsx'
import { ROLE_OPTIONS, getRoleLabel } from '../constants/roles.js'
import { SPECIALTY_GROUPS, getSpecialtyLabel } from '../constants/specialties.js'

const MASCOT_LABELS = {
  owl: 'Сова',
  robot: 'Робот',
  cat: 'Кот',
  llama: 'Лама',
  dragon: 'Дракон',
  wizard: 'Маг',
  ghost: 'Призрак',
  crystal: 'Кристалл',
  fox: 'Лис',
  panda: 'Панда',
}

const ROLE_VALUES = new Set(ROLE_OPTIONS.map((role) => role.value))
const SPECIALTY_VALUES = new Set(
  SPECIALTY_GROUPS.flatMap((group) => group.options.map((specialty) => specialty.value)),
)
const MASCOT_VALUES = new Set(Object.keys(MASCOT_DEFS))

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

function normalizeDraft(draft, index) {
  const mascot = MASCOT_VALUES.has(draft?.mascot) ? draft.mascot : 'wizard'
  const role = ROLE_VALUES.has(draft?.role) ? draft.role : 'analyst'
  const specialty = SPECIALTY_VALUES.has(draft?.specialty) ? draft.specialty : 'digital-generalist'

  return {
    id: draft?.id || `draft-${Date.now()}-${index}`,
    name: String(draft?.name || `Герой ${index + 1}`).trim(),
    role,
    specialty,
    mascot,
    emoji: MASCOT_DEFS[mascot]?.emoji || draft?.emoji || '🧙',
    summary: draft?.summary || '',
    lastNote: draft?.lastNote || 'Предложен кастинг-помощником под текущую задачу.',
  }
}

export default function CastingAssistantModal({
  open,
  topic,
  provider,
  model,
  disabled,
  onClose,
  onAccept,
}) {
  const [count, setCount] = useState(4)
  const [drafts, setDrafts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const trimmedTopic = topic.trim()
  const canGenerate = !loading && trimmedTopic.length > 0 && !disabled
  const canAccept = drafts.length > 0 && !loading
  const providerLabel = provider && model ? `${provider}/${model}` : 'автовыбор'

  useEffect(() => {
    if (!open) {
      setLoading(false)
      setError('')
      setMessage('')
      setDrafts([])
      return
    }

    if (drafts.length === 0) {
      setCount(4)
    }
  }, [drafts.length, open])

  const roleOptions = useMemo(() => ROLE_OPTIONS, [])
  const mascotOptions = useMemo(() => Object.keys(MASCOT_DEFS), [])

  async function generateDrafts() {
    if (!trimmedTopic) {
      setError('Сначала введите тему или вопрос.')
      return
    }

    setLoading(true)
    setError('')
    setMessage('Помощник читает тему и собирает состав...')

    try {
      const response = await fetch('/api/casting/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: trimmedTopic,
          count,
          provider,
          model,
        }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data?.detail || 'Не удалось собрать состав.')
      }
      const nextDrafts = (data.characters || []).map(normalizeDraft)
      setDrafts(nextDrafts)
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
    onAccept(drafts.map((draft, index) => normalizeDraft(draft, index)))
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
            <div className="assistant-title">Подобрать героев под задачу</div>
          </div>
          <button className="drawer-close" onClick={onClose} aria-label="Закрыть">×</button>
        </div>

        <div className="assistant-topic-card">
          <div className="assistant-topic-label">Текущая тема</div>
          <div className="assistant-topic-text">
            {trimmedTopic || 'Тема пока не введена.'}
          </div>
        </div>

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

          <div className="assistant-model-note">
            Помощник: {providerLabel}
          </div>

          <button
            className="pixel-btn start"
            onClick={generateDrafts}
            disabled={!canGenerate}
          >
            {loading ? 'Думает...' : 'Создать варианты'}
          </button>
        </div>

        {disabled && (
          <div className="assistant-warning">
            Менять состав можно до старта или во время паузы.
          </div>
        )}

        {message && <div className="assistant-message">{message}</div>}
        {error && <div className="assistant-error">{error}</div>}

        <div className="assistant-draft-list">
          {drafts.length === 0 && (
            <div className="drawer-empty">
              Нажмите «Создать варианты», и помощник предложит готовую команду для круглого стола.
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
                      {MASCOT_DEFS[mascot].emoji} {MASCOT_LABELS[mascot] || mascot}
                    </option>
                  ))}
                </select>

                <textarea
                  className="assistant-textarea"
                  value={draft.summary}
                  onChange={(event) => updateDraft(index, { summary: event.target.value })}
                  placeholder="Зачем этот персонаж нужен в обсуждении"
                />

                <div className="assistant-draft-meta">
                  {getRoleLabel(draft.role)} · {getSpecialtyLabel(draft.specialty)}
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
