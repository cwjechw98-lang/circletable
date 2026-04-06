import React, { useEffect, useMemo, useState } from 'react'
import CastingAssistantModal from './CastingAssistantModal.jsx'
import { MASCOT_DEFS } from './Mascot.jsx'
import { ROLE_OPTIONS } from '../constants/roles.js'
import { SPECIALTY_GROUPS } from '../constants/specialties.js'

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
  const [assistantOpen, setAssistantOpen] = useState(false)

  const effectiveSessionState = sessionState === 'running' && session?.status && session.status !== 'running'
    ? session.status
    : sessionState
  const activeSession = Boolean(session) && !['completed', 'stopped', 'idle'].includes(effectiveSessionState)
  const paused = effectiveSessionState === 'paused'
  const pausePending = effectiveSessionState === 'pause_requested'
  const running = activeSession && !paused && !pausePending
  const editable = !activeSession || paused
  const visibleSessionStatus = effectiveSessionState

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

  function createAssistantParticipants(drafts) {
    const chosenModel = newModel || pickPreferredModel(newProvider, providers[newProvider]?.models || [])
    drafts.forEach((draft) => {
      onCreateParticipant({
        name: draft.name,
        role: draft.role,
        specialty: draft.specialty,
        provider: newProvider,
        model: chosenModel,
        mascot: draft.mascot,
        emoji: MASCOT_DEFS[draft.mascot]?.emoji || draft.emoji || '🧙',
        stats: draft.stats || {
          insight: 50,
          focus: 50,
          depth: 50,
          cooperation: 50,
          showmanship: 50,
        },
        strengths: draft.strengths || [],
        weaknesses: draft.weaknesses || [],
        summary: draft.summary || '',
        lastNote: draft.lastNote || 'Предложен кастинг-помощником под текущую задачу.',
      }, saveToInventory)
    })
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
        <button className="pixel-btn ghost" onClick={onOpenRooms} title="Открыть список комнат и сохранённых обсуждений.">Комнаты</button>
        <button className="pixel-btn ghost" onClick={onOpenInventory} title="Открыть инвентарь персонажей, скамейку и состав стола.">Инвентарь</button>

        <div className="toolbar-select">
          <span>Режим:</span>
          <select
            value={room?.observerMode || 'suggest'}
            onChange={(event) => onObserverModeChange(event.target.value)}
            title="Бесконечный — без автофинала. С подсказками — Хрономант предлагает. Автофинал — Хрономант сам ведёт к финалу."
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
          title="Заново получить список доступных моделей."
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

        <button
          className="pixel-btn helper"
          onClick={() => setAssistantOpen(true)}
          disabled={!editable || !topic.trim()}
          title="Помощник предложит состав персонажей под текущую тему."
        >
          Помощь
        </button>

        {!activeSession && (
          <button
            className="pixel-btn start"
            onClick={onStartSession}
            disabled={!connected || activeParticipants.length < 2 || !topic.trim()}
            title="Начать новую сессию обсуждения с текущей темой и составом."
          >
            ▶ Запустить сессию
          </button>
        )}

        {running && (
          <>
            <button className="pixel-btn ghost" onClick={onPauseSession} title="Поставить сессию на паузу после текущего говорящего.">⏸ Пауза</button>
            <button className="pixel-btn ghost" onClick={onRequestWrap} title="Мягко попросить участников двигаться к выводу в ближайшие раунды.">Закругляться</button>
            <button className="pixel-btn stop" onClick={onRequestFinal} title="Объявить следующий раунд финальным: участники подведут итог вместо новых веток.">Финальный раунд</button>
            <button className="pixel-btn danger" onClick={onStopSession} title="Остановить сессию на ближайшей безопасной точке. Лог должен остаться в комнате.">■ Остановить</button>
          </>
        )}

        {pausePending && (
          <>
            <div className="pause-hint">Пауза будет поставлена после текущего говорящего.</div>
            <button className="pixel-btn danger" onClick={onStopSession} title="Остановить сессию на ближайшей безопасной точке.">■ Остановить</button>
          </>
        )}

        {paused && (
          <>
            <button className="pixel-btn start" onClick={onResumeSession} title="Продолжить эту же сессию с текущим составом.">▶ Продолжить</button>
            <button className="pixel-btn ghost" onClick={onRequestWrap} title="Мягко попросить участников двигаться к выводу в ближайшие раунды.">Закругляться</button>
            <button className="pixel-btn stop" onClick={onRequestFinal} title="Объявить следующий раунд финальным: участники подведут итог вместо новых веток.">Финальный раунд</button>
            <button className="pixel-btn danger" onClick={onStopSession} title="Остановить сессию на ближайшей безопасной точке.">■ Остановить</button>
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
          <button className="pixel-btn add" onClick={submitQuestion} title="Добавить ваш вопрос в контекст следующего раунда.">Отправить вопрос</button>
        </div>
      )}

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

          <button className="pixel-btn add" onClick={createParticipant} title="Создать персонажа с выбранными ролью, профилем и моделью.">+ Посадить за стол</button>
        </div>
      )}

      <CastingAssistantModal
        open={assistantOpen}
        topic={topic}
        provider={newProvider}
        model={newModel || pickPreferredModel(newProvider, providers[newProvider]?.models || [])}
        disabled={!editable}
        onClose={() => setAssistantOpen(false)}
        onAccept={createAssistantParticipants}
      />
    </div>
  )
}
