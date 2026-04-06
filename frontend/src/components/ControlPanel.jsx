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

const OBSERVER_MODE_OPTIONS = [
  { value: 'manual', label: 'Бесконечный режим' },
  { value: 'suggest', label: 'С подсказками' },
  { value: 'auto', label: 'Автофинал' },
]

const PREFERRED_MODELS = {
  anthropic: ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-latest', 'claude-haiku-3-5-20241022'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1-mini', 'o4-mini'],
  ollama: [
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

const EMBEDDING_MARKERS = ['embed', 'embedding', 'nomic-embed', 'text-embedding', 'bge', 'e5']

function getSessionStateLabel(state) {
  switch (state) {
    case 'running':
      return 'В процессе'
    case 'pause_requested':
      return 'Готовится пауза'
    case 'paused':
      return 'На паузе'
    case 'observer_review':
      return 'Хрономант оценивает'
    case 'finalizing':
      return 'Финализация'
    case 'completed':
      return 'Завершена'
    case 'stopped':
      return 'Остановлена'
    default:
      return 'Ожидание'
  }
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

function pickPreferredModel(providerName, models) {
  if (!models || models.length === 0) {
    return ''
  }

  const preferred = PREFERRED_MODELS[providerName] || []
  const exactMatch = preferred.find((model) => models.includes(model))
  if (exactMatch) {
    return exactMatch
  }

  const fallback = models.find((model) => {
    const lower = model.toLowerCase()
    return !EMBEDDING_MARKERS.some((marker) => lower.includes(marker))
  })

  return fallback || models[0]
}

function isEmbeddingModel(model) {
  const lower = (model || '').toLowerCase()
  return EMBEDDING_MARKERS.some((marker) => lower.includes(marker))
}

export default function ControlPanel({
  providers,
  room,
  session,
  sessionState,
  topic,
  activeParticipants,
  connected,
  refreshingProviders,
  latestObserverSuggestion,
  latestObserverReview,
  observerBusy,
  onTopicChange,
  onStartSession,
  onPauseSession,
  onResumeSession,
  onStopSession,
  onRequestWrap,
  onRequestFinal,
  onOpenRooms,
  onOpenInventory,
  onRefreshProviders,
  onObserverModeChange,
  onCreateParticipant,
  onSubmitQuestion,
}) {
  const [newName, setNewName] = useState('')
  const [newRole, setNewRole] = useState('critic')
  const [newSpecialty, setNewSpecialty] = useState('digital-generalist')
  const [newProvider, setNewProvider] = useState('ollama')
  const [newModel, setNewModel] = useState('')
  const [newMascot, setNewMascot] = useState('wizard')
  const [saveToInventory, setSaveToInventory] = useState(true)
  const [question, setQuestion] = useState('')

  const activeSession = Boolean(session) && !['completed', 'stopped'].includes(session?.status || '')
  const paused = sessionState === 'paused'
  const pausePending = sessionState === 'pause_requested'
  const running = activeSession && !paused && !pausePending
  const editable = !activeSession || paused
  const visibleSessionStatus = session?.status || sessionState

  const availableProviders = useMemo(
    () => Object.entries(providers).filter(([, value]) => value.available).map(([key]) => key),
    [providers],
  )

  useEffect(() => {
    if (availableProviders.length > 0 && !availableProviders.includes(newProvider)) {
      setNewProvider(availableProviders[0])
    }
  }, [availableProviders, newProvider])

  useEffect(() => {
    const models = providers[newProvider]?.models || []
    if (models.length === 0) {
      return
    }

    if (!newModel || !models.includes(newModel) || isEmbeddingModel(newModel)) {
      setNewModel(pickPreferredModel(newProvider, models))
    }
  }, [newProvider, newModel, providers])

  function createParticipant() {
    const trimmed = newName.trim()
    if (!trimmed) return
    const chosenModel = newModel || pickPreferredModel(newProvider, providers[newProvider]?.models || [])
    onCreateParticipant({
      name: trimmed,
      role: newRole,
      specialty: newSpecialty,
      provider: newProvider,
      model: chosenModel,
      mascot: newMascot,
      emoji: MASCOT_DEFS[newMascot]?.emoji || '🧙',
      stats: {
        insight: 50,
        focus: 50,
        depth: 50,
        cooperation: 50,
        showmanship: 50,
      },
      strengths: [],
      weaknesses: [],
      summary: '',
      lastNote: 'Новый герой ещё не прошёл ни одной полной сессии.',
    }, saveToInventory)
    setNewName('')
  }

  function submitQuestion() {
    const trimmed = question.trim()
    if (!trimmed) return
    onSubmitQuestion(trimmed)
    setQuestion('')
  }

  return (
    <div className="control-panel">
      <div className="session-toolbar">
        <button className="pixel-btn ghost" onClick={onOpenRooms}>Комнаты</button>
        <button className="pixel-btn ghost" onClick={onOpenInventory}>Инвентарь</button>

        <div className="toolbar-select">
          <span>Режим:</span>
          <select
            value={room?.observerMode || 'suggest'}
            onChange={(event) => onObserverModeChange(event.target.value)}
          >
            {OBSERVER_MODE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>

        <button
          className="pixel-btn sync"
          onClick={onRefreshProviders}
          disabled={!connected || refreshingProviders}
        >
          {refreshingProviders ? 'Обновление...' : '↻ Модели'}
        </button>

        <div className="toolbar-badges">
          <span className="toolbar-badge">{room?.name || 'Комната не выбрана'}</span>
          <span className={`toolbar-badge${observerBusy ? ' is-accent' : ''}`}>
            {observerBusy
              ? 'Хрономант думает'
              : visibleSessionStatus && visibleSessionStatus !== 'idle'
                ? `Статус: ${getSessionStateLabel(visibleSessionStatus)}`
                : 'Сессия не запущена'}
          </span>
        </div>
      </div>

      <div className="topic-row">
        <input
          className="pixel-input"
          value={topic}
          onChange={(event) => onTopicChange(event.target.value)}
          placeholder="Введите тему или новый вопрос для комнаты"
          disabled={!editable}
        />

        {!activeSession && (
          <button
            className="pixel-btn start"
            onClick={onStartSession}
            disabled={!connected || activeParticipants.length < 2 || !topic.trim()}
          >
            ▶ Запустить сессию
          </button>
        )}

        {running && (
          <>
            <button className="pixel-btn ghost" onClick={onPauseSession}>⏸ Пауза</button>
            <button className="pixel-btn ghost" onClick={onRequestWrap}>Закругляться</button>
            <button className="pixel-btn stop" onClick={onRequestFinal}>Финальный раунд</button>
            <button className="pixel-btn danger" onClick={onStopSession}>■ Завершить</button>
          </>
        )}

        {pausePending && (
          <>
            <div className="pause-hint">Пауза будет поставлена после текущего говорящего.</div>
            <button className="pixel-btn danger" onClick={onStopSession}>■ Завершить</button>
          </>
        )}

        {paused && (
          <>
            <button className="pixel-btn start" onClick={onResumeSession}>▶ Продолжить</button>
            <button className="pixel-btn ghost" onClick={onRequestWrap}>Закругляться</button>
            <button className="pixel-btn stop" onClick={onRequestFinal}>Финальный раунд</button>
            <button className="pixel-btn danger" onClick={onStopSession}>■ Завершить</button>
          </>
        )}
      </div>

      {(latestObserverSuggestion || latestObserverReview) && (
        <div className="observer-banner">
          <div className="observer-banner-title">Хрономант</div>
          <div className="observer-banner-body">
            {latestObserverSuggestion?.summary || latestObserverReview?.tableComment || latestObserverReview?.roundSummary}
          </div>
        </div>
      )}

      {paused && (
        <div className="question-row">
          <input
            className="pixel-input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Добавьте пользовательский вопрос в эту комнату"
            onKeyDown={(event) => event.key === 'Enter' && submitQuestion()}
          />
          <button className="pixel-btn add" onClick={submitQuestion}>Отправить вопрос</button>
        </div>
      )}

      <div className="active-roster">
        {activeParticipants.map((participant) => (
          <div key={participant.id} className="roster-chip">
            <span>{participant.emoji}</span>
            <strong>{participant.name}</strong>
            <small>{getRoleLabel(participant.role)} · {getSpecialtyLabel(participant.specialty)}</small>
          </div>
        ))}
      </div>

      {editable && (
        <div className="builder-panel">
          <div className="builder-title">Создать персонажа</div>

          <div className="builder-grid">
            <input
              className="mini-input"
              placeholder="Имя героя"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && createParticipant()}
            />

            <select className="mini-select" value={newRole} onChange={(event) => setNewRole(event.target.value)}>
              {ROLE_OPTIONS.map((role) => (
                <option key={role.value} value={role.value}>{role.label}</option>
              ))}
            </select>

            <select className="mini-select specialty-select" value={newSpecialty} onChange={(event) => setNewSpecialty(event.target.value)}>
              {renderSpecialtyOptions()}
            </select>

            <select className="mini-select" value={newProvider} onChange={(event) => setNewProvider(event.target.value)}>
              {availableProviders.map((provider) => (
                <option key={provider} value={provider}>{provider}</option>
              ))}
            </select>

            <select className="mini-select" value={newModel} onChange={(event) => setNewModel(event.target.value)}>
              {(providers[newProvider]?.models || []).map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>

            <select className="mini-select" value={newMascot} onChange={(event) => setNewMascot(event.target.value)}>
              {Object.keys(MASCOT_DEFS).map((mascot) => (
                <option key={mascot} value={mascot}>
                  {MASCOT_DEFS[mascot].emoji} {MASCOT_LABELS[mascot] || mascot}
                </option>
              ))}
            </select>
          </div>

          <label className="builder-check">
            <input
              type="checkbox"
              checked={saveToInventory}
              onChange={(event) => setSaveToInventory(event.target.checked)}
            />
            Сразу сохранить в инвентарь
          </label>

          <button className="pixel-btn add" onClick={createParticipant}>+ Посадить за стол</button>
        </div>
      )}
    </div>
  )
}
