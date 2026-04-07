import React, { useEffect, useMemo, useState } from 'react'
import CastingAssistantModal from './CastingAssistantModal.jsx'
import { MASCOT_DEFS, MASCOT_LABELS } from './Mascot.jsx'
import { ROLE_OPTIONS } from '../constants/roles.js'
import { SPECIALTY_GROUPS } from '../constants/specialties.js'

const OBSERVER_MODE_OPTIONS = [
  { value: 'manual', label: 'Бесконечный режим' },
  { value: 'suggest', label: 'С подсказками' },
  { value: 'auto', label: 'Автофинал' },
]

const DENSITY_MODE_OPTIONS = [
  { value: 'calm', label: 'Спокойный' },
  { value: 'normal', label: 'Обычный' },
  { value: 'stage', label: 'Сценический' },
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
const ASSISTANT_MODEL_KEY = 'circletable-casting-assistant-model'

function readStoredAssistantConfig() {
  try {
    return JSON.parse(localStorage.getItem(ASSISTANT_MODEL_KEY) || '{}')
  } catch {
    return {}
  }
}

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

function formatMascotLabel(mascot) {
  const label = MASCOT_LABELS[mascot] || mascot
  return label ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : mascot
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
  teamPresets = [],
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
  onDensityModeChange,
  onCreateParticipant,
  onSubmitQuestion,
  onCreateTeamPreset,
  onApplyTeamPreset,
  onDeleteTeamPreset,
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
  const [assistantMode, setAssistantMode] = useState('full')
  const [deferredGapFillOpen, setDeferredGapFillOpen] = useState(false)
  const [assistantSettings, setAssistantSettings] = useState(() => readStoredAssistantConfig())
  const [presetName, setPresetName] = useState('')

  const effectiveSessionState = sessionState === 'running' && session?.status && session.status !== 'running'
    ? session.status
    : sessionState
  const activeSession = Boolean(session) && !['completed', 'stopped', 'idle'].includes(effectiveSessionState)
  const paused = effectiveSessionState === 'paused'
  const pausePending = effectiveSessionState === 'pause_requested'
  const running = activeSession && !paused && !pausePending
  const editable = !activeSession || paused
  const visibleSessionStatus = effectiveSessionState
  const displayTopic = session?.topic || topic
  const densityMode = room?.densityMode || 'normal'

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

  useEffect(() => {
    if (availableProviders.length === 0) {
      return
    }

    setAssistantSettings((current) => {
      const fallbackProvider = availableProviders.includes(newProvider) ? newProvider : availableProviders[0]
      const providerName = current.provider && availableProviders.includes(current.provider)
        ? current.provider
        : fallbackProvider
      const models = providers[providerName]?.models || []
      const preferredModel = pickPreferredModel(providerName, models)
      const modelName = current.model && models.includes(current.model) && !isEmbeddingModel(current.model)
        ? current.model
        : preferredModel

      if (providerName === current.provider && modelName === current.model) {
        return current
      }

      return {
        provider: providerName,
        model: modelName,
      }
    })
  }, [availableProviders, newProvider, providers])

  useEffect(() => {
    if (!assistantSettings.provider) {
      return
    }
    localStorage.setItem(ASSISTANT_MODEL_KEY, JSON.stringify(assistantSettings))
  }, [assistantSettings])

  const latestRoundSummary = latestObserverSuggestion?.summary
    || latestObserverReview?.summary
    || latestObserverReview?.roundSummary
    || latestObserverReview?.chronicleAfter
    || ''
  const observerProgress = latestObserverSuggestion?.progress || latestObserverReview?.progress || {}
  const finalReason = latestObserverReview?.finalReason || ''
  const missingExpertHint = latestObserverSuggestion?.missingExpertHint || latestObserverReview?.missingExpertHint || ''
  const suggestionRound = latestObserverReview?.roundNumber || 0
  const recruitAdviceVisible = Boolean(missingExpertHint) && suggestionRound >= 1 && room?.observerMode !== 'manual'

  useEffect(() => {
    if (deferredGapFillOpen && paused) {
      setAssistantMode('gap_fill')
      setAssistantOpen(true)
      setDeferredGapFillOpen(false)
    }
  }, [deferredGapFillOpen, paused])

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
    drafts.forEach((draft) => {
      const draftProvider = draft.provider || newProvider
      const chosenModel = draft.model || newModel || pickPreferredModel(draftProvider, providers[draftProvider]?.models || [])
      onCreateParticipant({
        name: draft.name,
        role: draft.role,
        specialty: draft.specialty,
        provider: draftProvider,
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

  function createTeamPreset() {
    const fallbackName = `Состав ${teamPresets.length + 1}`
    onCreateTeamPreset(presetName.trim() || fallbackName)
    setPresetName('')
  }

  function openGapFillAssistant() {
    setAssistantMode('gap_fill')
    setAssistantOpen(true)
  }

  function handleRecruitAdviceAction() {
    if (!activeSession || paused) {
      openGapFillAssistant()
      return
    }
    setDeferredGapFillOpen(true)
    onPauseSession?.()
  }

  return (
    <div className="control-panel">
      <div className="session-toolbar">
        <button className="pixel-btn ghost" onClick={onOpenRooms} data-hint="Открыть список комнат и сохранённых обсуждений.">Комнаты</button>
        <button className="pixel-btn ghost" onClick={onOpenInventory} data-hint="Открыть инвентарь персонажей, скамейку и состав стола.">Инвентарь</button>

        <div className="toolbar-select">
          <span>Режим:</span>
          <select
            value={room?.observerMode || 'suggest'}
            onChange={(event) => onObserverModeChange(event.target.value)}
            data-hint="Бесконечный — без автофинала. С подсказками — Хрономант предлагает. Автофинал — Хрономант сам ведёт к финалу."
          >
            {OBSERVER_MODE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>

        <div className="toolbar-select">
          <span>Плотность:</span>
          <select
            value={densityMode}
            onChange={(event) => onDensityModeChange?.(event.target.value)}
            data-hint="Спокойный — медленнее и размереннее. Сценический — короче и бодрее."
          >
            {DENSITY_MODE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>

        <button
          className="pixel-btn sync"
          onClick={onRefreshProviders}
          disabled={!connected || refreshingProviders}
          data-hint="Заново получить список доступных моделей."
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
        {editable ? (
          <input
            className="pixel-input"
            value={topic}
            onChange={(event) => onTopicChange(event.target.value)}
            placeholder="Введите тему или новый вопрос для комнаты"
            disabled={!editable}
          />
        ) : (
          <div className="topic-marquee-shell" data-hint="Текущая тема этой сессии. Во время активного раунда строка прокручивается автоматически.">
            <div className="topic-marquee-track">
              <span>{displayTopic || 'Тема сессии ещё не задана.'}</span>
              <span aria-hidden="true">{displayTopic || 'Тема сессии ещё не задана.'}</span>
            </div>
          </div>
        )}

        <button
          className="pixel-btn helper"
          onClick={() => {
            setAssistantMode('full')
            setAssistantOpen(true)
          }}
          disabled={!editable || !topic.trim()}
          data-hint="Помощник предложит состав персонажей под тему и контекст беседы. Его модель меняется внутри этого окна."
        >
          Помощь
        </button>

        <button
          className="pixel-btn ghost"
          onClick={() => {
            setAssistantMode('gap_fill')
            setAssistantOpen(true)
          }}
          disabled={!editable || !topic.trim()}
          data-hint="Помощник посмотрит на тему, хронику и состав стола и предложит именно недостающего эксперта."
        >
          Кого не хватает?
        </button>

        {!activeSession && (
          <button
            className="pixel-btn start"
            onClick={onStartSession}
            disabled={!connected || activeParticipants.length < 2 || !topic.trim()}
            data-hint="Начать новую сессию обсуждения с текущей темой и составом."
          >
            ▶ Запустить сессию
          </button>
        )}

        {running && (
          <>
            <button className="pixel-btn ghost" onClick={onPauseSession} data-hint="Поставить сессию на паузу после текущего говорящего.">⏸ Пауза</button>
            <button className="pixel-btn ghost" onClick={onRequestWrap} data-hint="Мягко попросить участников двигаться к выводу в ближайшие раунды.">Закругляться</button>
            <button className="pixel-btn stop" onClick={onRequestFinal} data-hint="Объявить следующий раунд финальным: участники подведут итог вместо новых веток.">Финальный раунд</button>
            <button className="pixel-btn danger" onClick={onStopSession} data-hint="Остановить сессию на ближайшей безопасной точке. Лог должен остаться в комнате.">■ Остановить</button>
          </>
        )}

        {pausePending && (
          <>
            <div className="pause-hint">Пауза будет поставлена после текущего говорящего.</div>
            <button className="pixel-btn danger" onClick={onStopSession} data-hint="Остановить сессию на ближайшей безопасной точке.">■ Остановить</button>
          </>
        )}

        {paused && (
          <>
            <button className="pixel-btn start" onClick={onResumeSession} data-hint="Продолжить эту же сессию с текущим составом.">▶ Продолжить</button>
            <button className="pixel-btn ghost" onClick={onRequestWrap} data-hint="Мягко попросить участников двигаться к выводу в ближайшие раунды.">Закругляться</button>
            <button className="pixel-btn stop" onClick={onRequestFinal} data-hint="Объявить следующий раунд финальным: участники подведут итог вместо новых веток.">Финальный раунд</button>
            <button className="pixel-btn danger" onClick={onStopSession} data-hint="Остановить сессию на ближайшей безопасной точке.">■ Остановить</button>
          </>
        )}
      </div>

      {(latestObserverSuggestion || latestObserverReview) && (
        <div className="observer-banner">
          <div className="observer-banner-title">Хрономант</div>
          <div className="observer-banner-body">
            {latestObserverSuggestion?.summary || latestObserverReview?.tableComment || latestObserverReview?.roundSummary}
          </div>
          <div className="observer-progress-grid">
            {[
              ['Новизна', observerProgress.novelty ?? 50],
              ['Фокус', observerProgress.focus ?? 50],
              ['Сходимость', observerProgress.convergence ?? 50],
            ].map(([label, value]) => (
              <div key={label} className="observer-progress-card">
                <div className="observer-progress-head">
                  <span>{label}</span>
                  <b>{value}%</b>
                </div>
                <div className="observer-progress-track">
                  <div className="observer-progress-fill" style={{ width: `${value}%` }} />
                </div>
              </div>
            ))}
          </div>
          {finalReason && (
            <div className="observer-banner-note">
              Причина финала: {finalReason}
            </div>
          )}
          {missingExpertHint && (
            <div className="observer-banner-note is-accent">
              Кого не хватает: {missingExpertHint}
            </div>
          )}
          {recruitAdviceVisible && (
            <div className="observer-recruit-card">
              <div className="observer-recruit-text">
                Хрономант советует добрать эксперта, но решение остаётся за тобой.
              </div>
              <button
                className="pixel-btn ghost"
                onClick={handleRecruitAdviceAction}
                disabled={pausePending}
                data-hint="Открыть точечный добор недостающего героя. Во время живого раунда сначала поставим стол на паузу."
              >
                {paused || !activeSession ? 'Подобрать героя' : pausePending ? 'Ждём паузу...' : 'Пауза и добор'}
              </button>
            </div>
          )}
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
          <button className="pixel-btn add" onClick={submitQuestion} data-hint="Добавить ваш вопрос в контекст следующего раунда.">Отправить вопрос</button>
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
                  {MASCOT_DEFS[mascot].emoji} {formatMascotLabel(mascot)}
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

          <button className="pixel-btn add" onClick={createParticipant} data-hint="Создать персонажа с выбранными ролью, профилем и моделью.">+ Посадить за стол</button>

          <div className="preset-panel">
            <div className="preset-panel-head">
              <div className="preset-panel-title">Сохранённые составы</div>
              <div className="preset-panel-sub">Сохраняют текущих участников за столом как готовую команду.</div>
            </div>

            <div className="preset-create-row">
              <input
                className="mini-input"
                value={presetName}
                onChange={(event) => setPresetName(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && activeParticipants.length > 0 && createTeamPreset()}
                placeholder="Имя состава"
              />
              <button
                className="pixel-btn ghost"
                onClick={createTeamPreset}
                disabled={activeParticipants.length === 0}
                data-hint="Сохранить текущий состав стола как готовую команду."
              >
                Сохранить состав
              </button>
            </div>

            <div className="preset-list">
              {teamPresets.length === 0 && (
                <div className="preset-empty">Пока нет сохранённых составов. Соберите команду и сохраните её здесь.</div>
              )}

              {teamPresets.map((preset) => (
                <div key={preset.id} className="preset-card">
                  <div className="preset-card-main">
                    <div className="preset-card-name">{preset.name}</div>
                    <div className="preset-card-meta">
                      {preset.participants?.map((participant) => participant.name).filter(Boolean).slice(0, 4).join(' • ')
                        || 'Состав без имён'}
                      {(preset.participants?.length || 0) > 4 ? ` • ещё ${(preset.participants?.length || 0) - 4}` : ''}
                    </div>
                  </div>
                  <div className="preset-card-actions">
                    <button
                      className="pixel-btn ghost"
                      onClick={() => onApplyTeamPreset?.(preset.id)}
                      disabled={!editable}
                      data-hint="Применить этот состав к текущей комнате."
                    >
                      Применить
                    </button>
                    <button
                      className="pixel-btn danger"
                      onClick={() => onDeleteTeamPreset?.(preset.id)}
                      data-hint="Удалить сохранённый состав."
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <CastingAssistantModal
        open={assistantOpen}
        mode={assistantMode}
        topic={topic}
        provider={newProvider}
        model={newModel || pickPreferredModel(newProvider, providers[newProvider]?.models || [])}
        providers={providers}
        disabled={!editable}
        roomSummary={room?.summary || ''}
        sessionChronicle={session?.chronicle || ''}
        latestRoundSummary={latestRoundSummary}
        activeParticipants={activeParticipants}
        assistantProvider={assistantSettings.provider || newProvider}
        assistantModel={assistantSettings.model || newModel || pickPreferredModel(newProvider, providers[newProvider]?.models || [])}
        missingExpertHint={missingExpertHint}
        onAssistantChange={setAssistantSettings}
        onClose={() => setAssistantOpen(false)}
        onAccept={createAssistantParticipants}
      />
    </div>
  )
}
