import React, { useEffect, useState } from 'react'
import CastingAssistantModal from './CastingAssistantModal.jsx'
import CustomSpecialtiesPanel from './panel/CustomSpecialtiesPanel.jsx'
import DocumentsPanel from './panel/DocumentsPanel.jsx'
import PlannedEventsPanel from './panel/PlannedEventsPanel.jsx'
import ParticipantBuilderPanel from './panel/ParticipantBuilderPanel.jsx'
import TeamPresetsPanel from './panel/TeamPresetsPanel.jsx'
import useBuilderState from '../hooks/useBuilderState.js'
import useParticipantBuilderState from '../hooks/useParticipantBuilderState.js'
import { getModelOptions, isEmbeddingModel, pickPreferredModel } from '../constants/models.js'

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

const INTERNET_MODE_OPTIONS = [
  { value: 'off', label: 'Off' },
  { value: 'auto', label: 'Auto' },
  { value: 'on', label: 'On' },
]

const DECISION_STAGE_LABELS = {
  explore: 'Исследование',
  challenge: 'Проверка гипотез',
  converge: 'Сведение вариантов',
  decide: 'Фиксация решения',
  stalled: 'Потеря фокуса',
}

const NEXT_ACTION_LABELS = {
  continue: 'Продолжить раунд',
  ask_user: 'Уточнить у пользователя',
  add_expert: 'Добрать эксперта',
  bench_participant: 'Разгрузить состав',
  fact_check: 'Проверить факты',
  final_round: 'Идти к финалу',
}

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

function clampPercent(value, fallback = 0) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return fallback
  }
  return Math.max(0, Math.min(100, Math.round(numeric)))
}

export default function ControlPanel({
  providers,
  room,
  session,
  sessionState,
  committedTopic,
  draftTopic,
  topicDirty,
  topicFocusMode,
  topicFocusActive,
  activeParticipants,
  connected,
  refreshingProviders,
  latestObserverSuggestion,
  latestObserverReview,
  observerBusy,
  teamPresets = [],
  customSpecialtyGroups = [],
  plannedEvents = [],
  currentRoomId,
  onTopicDraftChange,
  onBeginTopicEditing,
  onConfirmTopic,
  onCancelTopic,
  onStartSession,
  onPauseSession,
  onResumeSession,
  onStopSession,
  onRequestWrap,
  onRequestFinal,
  onOpenRooms,
  onOpenInventory,
  onOpenLab,
  onRefreshProviders,
  onObserverModeChange,
  onDensityModeChange,
  onCreateParticipant,
  onBenchParticipant,
  onSubmitQuestion,
  onCreateTeamPreset,
  onApplyTeamPreset,
  onDeleteTeamPreset,
  onCreateCustomSpecialty,
  onUpdateCustomSpecialty,
  onDeleteCustomSpecialty,
  onInternetModeChange,
  onRunFactCheck,
  factCheck,
  onCreatePlannedEvent,
  onUpdatePlannedEvent,
  onDeletePlannedEvent,
}) {
  const [question, setQuestion] = useState('')
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [assistantMode, setAssistantMode] = useState('full')
  const [deferredGapFillOpen, setDeferredGapFillOpen] = useState(false)
  const [deferredBenchParticipantId, setDeferredBenchParticipantId] = useState('')
  const [dismissedExcessAdviceKey, setDismissedExcessAdviceKey] = useState('')
  const [assistantSettings, setAssistantSettings] = useState(() => readStoredAssistantConfig())
  const [observerOpen, setObserverOpen] = useState(true)

  const effectiveSessionState = sessionState === 'running' && session?.status && session.status !== 'running'
    ? session.status
    : sessionState
  const activeSession = Boolean(session) && !['completed', 'stopped', 'idle'].includes(effectiveSessionState)
  const paused = effectiveSessionState === 'paused'
  const pausePending = effectiveSessionState === 'pause_requested'
  const running = activeSession && !paused && !pausePending
  const editable = !activeSession || paused
  const canChangeRoomSettings = editable
  const finished = ['completed', 'stopped'].includes(effectiveSessionState)
  const visibleSessionStatus = effectiveSessionState
  const displayTopic = session?.topic || committedTopic
  const densityMode = room?.densityMode || 'normal'
  const internetMode = room?.internetMode || room?.settings?.internet_mode || 'auto'
  const factCheckStatus = factCheck?.status || ''
  const factCheckBusy = ['queued', 'running'].includes(factCheckStatus)
  const canRunFactCheck = (paused || finished) && Boolean(session?.id)
  const hasCommittedTopic = Boolean((committedTopic || '').trim())
  const topicNeedsConfirmation = Boolean(topicDirty)
  const topicInputHint = topicFocusMode === 'off'
    ? 'Введите тему и подтвердите её галочкой, чтобы кастинг и старт работали именно с этим вопросом.'
    : 'Нажмите, чтобы открыть режим фокуса и сформулировать тему без отвлекающих панелей.'
  const topicDependentHint = topicNeedsConfirmation
    ? 'Сначала подтвердите новую тему: сейчас это ещё черновик.'
    : 'Работает с подтверждённой темой комнаты.'
  const {
    participantBuilderProps,
    selectedProvider,
    selectedModel,
    availableProviders,
    setSelectedSpecialty,
    createAssistantParticipants,
  } = useParticipantBuilderState({
    providers,
    customSpecialtyGroups,
    onCreateParticipant,
  })
  const { presetsProps, eventsProps, customSpecialtiesProps } = useBuilderState({
    teamPresets,
    activeParticipantsCount: activeParticipants.length,
    editable,
    plannedEvents,
    sessionLastRoundNumber: session?.lastRoundNumber,
    customSpecialtyGroups,
    onCreateTeamPreset,
    onApplyTeamPreset,
    onDeleteTeamPreset,
    onCreateCustomSpecialty,
    onUpdateCustomSpecialty,
    onDeleteCustomSpecialty,
    onCreatePlannedEvent,
    onDeletePlannedEvent,
  })

  useEffect(() => {
    if (availableProviders.length === 0) {
      return
    }

    setAssistantSettings((current) => {
      const fallbackProvider = availableProviders.includes(selectedProvider) ? selectedProvider : availableProviders[0]
      const providerName = current.provider && availableProviders.includes(current.provider)
        ? current.provider
        : fallbackProvider
      const models = getModelOptions(providerName, providers)
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
  }, [availableProviders, selectedProvider, providers])

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
  const observerSource = latestObserverSuggestion || latestObserverReview || {}
  const observerProgress = observerSource.progress || {}
  const decisionProgress = observerProgress.decisionProgress || observerSource.decisionProgress || {}
  const decisionReadiness = clampPercent(decisionProgress.readiness, 0)
  const decisionStageLabel = DECISION_STAGE_LABELS[decisionProgress.stage] || 'Стадия не ясна'
  const nextActionLabel = NEXT_ACTION_LABELS[decisionProgress.nextAction] || 'Продолжить наблюдение'
  const rosterAdvice = observerSource.rosterAdvice || {}
  const excessParticipant = rosterAdvice.excessParticipant && typeof rosterAdvice.excessParticipant === 'object'
    ? rosterAdvice.excessParticipant
    : null
  const finalReason = observerSource.finalReason || latestObserverReview?.finalReason || ''
  const missingExpertHint = latestObserverSuggestion?.missingExpertHint || rosterAdvice.missingExpertHint || ''
  const suggestionRound = latestObserverReview?.roundNumber || 0
  const recruitAdviceVisible = Boolean(missingExpertHint) && suggestionRound >= 1 && room?.observerMode !== 'manual'
  const excessAdviceKey = excessParticipant
    ? `${suggestionRound}:${excessParticipant.participantId || excessParticipant.profileId || excessParticipant.name || 'unknown'}:${excessParticipant.confidence || 0}`
    : ''

  function resolveExcessParticipantId() {
    if (!excessParticipant) {
      return ''
    }
    if (excessParticipant.participantId && activeParticipants.some((item) => item.id === excessParticipant.participantId)) {
      return excessParticipant.participantId
    }
    const byProfile = activeParticipants.find((item) => item.profileId === excessParticipant.profileId)
    if (byProfile) {
      return byProfile.id
    }
    const byName = activeParticipants.find((item) => item.name === excessParticipant.name)
    return byName?.id || ''
  }

  const excessParticipantId = resolveExcessParticipantId()
  const excessAdviceVisible = Boolean(excessParticipant && excessParticipantId)
    && excessAdviceKey !== dismissedExcessAdviceKey
    && room?.observerMode !== 'manual'

  useEffect(() => {
    if (deferredGapFillOpen && paused) {
      setAssistantMode('gap_fill')
      setAssistantOpen(true)
      setDeferredGapFillOpen(false)
    }
  }, [deferredGapFillOpen, paused])

  useEffect(() => {
    if (!deferredBenchParticipantId || !paused) {
      return
    }
    onBenchParticipant?.(deferredBenchParticipantId)
    setDismissedExcessAdviceKey(excessAdviceKey)
    setDeferredBenchParticipantId('')
  }, [deferredBenchParticipantId, paused, onBenchParticipant, excessAdviceKey])

  useEffect(() => {
    if (latestObserverSuggestion || latestObserverReview) {
      setObserverOpen(true)
    }
  }, [latestObserverSuggestion, latestObserverReview])

  function submitQuestion() {
    const trimmed = question.trim()
    if (!trimmed) return
    onSubmitQuestion(trimmed)
    setQuestion('')
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

  function handleExcessAdviceAction() {
    if (!excessParticipantId) {
      return
    }
    if (running) {
      setDeferredBenchParticipantId(excessParticipantId)
      onPauseSession?.()
      return
    }
    onBenchParticipant?.(excessParticipantId)
    setDismissedExcessAdviceKey(excessAdviceKey)
  }

  function dismissExcessAdvice() {
    setDismissedExcessAdviceKey(excessAdviceKey)
  }

  async function createSpecialtyFromObserverHint() {
    if (!missingExpertHint) return
    try {
      const specialty = await onCreateCustomSpecialty?.({
        sourceHint: missingExpertHint,
        groupLabel: 'Кастомные оптики',
        description: missingExpertHint,
      })
      if (specialty?.value) {
        setSelectedSpecialty(specialty.value)
      }
    } catch {
      // Ошибка будет видна в сетевом слое; основной сценарий подбора не блокируем.
    }
  }

  return (
    <div className="control-panel">
      <div className="session-toolbar">
        <button className="pixel-btn ghost" onClick={onOpenRooms} data-hint="Открыть список комнат и сохранённых обсуждений.">Комнаты</button>
        <button className="pixel-btn ghost" onClick={onOpenInventory} data-hint="Открыть инвентарь персонажей, скамейку и состав стола.">Инвентарь</button>
        <button className="pixel-btn ghost" onClick={onOpenLab} data-hint="Открыть лабораторию персонажей: досье с эволюцией показателей, ачивками и заметками Хрономанта.">Лаборатория</button>

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

      <div className="internet-settings-row">
          <div className="internet-settings-copy">
            <div className="internet-settings-title">Интернет</div>
            <div className="internet-settings-help">
              Off — память комнаты. Auto — по необходимости. On — внешний поиск разрешён.
            </div>
          </div>
        <label className="internet-settings-select" data-hint="Режим внешнего поиска для этой комнаты. Документы комнаты доступны автоматически и не зависят от этого переключателя.">
          <span>Режим</span>
          <select
            value={internetMode}
            disabled={!canChangeRoomSettings}
            onChange={(event) => onInternetModeChange?.(event.target.value)}
          >
            {INTERNET_MODE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>

      {editable && <DocumentsPanel roomId={currentRoomId} />}

      {editable && (
        <CustomSpecialtiesPanel
          {...customSpecialtiesProps}
        />
      )}

      <div className="topic-row">
        {editable ? (
          <div className={`topic-input-shell${topicNeedsConfirmation ? ' is-dirty' : ''}${topicFocusActive ? ' is-focus-active' : ''}`}>
            <input
              className={`pixel-input${topicFocusMode !== 'off' ? ' is-launcher' : ''}`}
              value={draftTopic}
              onChange={(event) => onTopicDraftChange?.(event.target.value)}
              onFocus={() => onBeginTopicEditing?.()}
              onClick={() => onBeginTopicEditing?.()}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && topicFocusMode === 'off') {
                  onConfirmTopic?.()
                }
                if (event.key === 'Escape' && topicFocusMode === 'off') {
                  onCancelTopic?.()
                }
              }}
              placeholder="Введите тему или новый вопрос для комнаты"
              disabled={!editable}
              readOnly={topicFocusMode !== 'off'}
              data-hint={topicInputHint}
            />
            {topicNeedsConfirmation && topicFocusMode === 'off' && (
              <div className="topic-confirm-actions">
                <button
                  className="pixel-btn add topic-confirm-btn"
                  onClick={onConfirmTopic}
                  data-hint="Подтвердить тему и сделать её активной для старта и кастинга."
                >
                  ✓
                </button>
                <button
                  className="pixel-btn ghost topic-confirm-btn"
                  onClick={onCancelTopic}
                  data-hint="Отменить черновик и вернуть последнюю подтверждённую тему."
                >
                  ×
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="topic-marquee-shell" data-hint="Текущая тема этой сессии. Во время активного раунда строка прокручивается автоматически.">
            <div className="topic-marquee-track">
              <span>{displayTopic || 'Тема сессии ещё не задана.'}</span>
              <span aria-hidden="true">{displayTopic || 'Тема сессии ещё не задана.'}</span>
            </div>
          </div>
        )}

        <button
          className="pixel-btn ghost"
          onClick={() => {
            setAssistantMode('gap_fill')
            setAssistantOpen(true)
          }}
          disabled={!editable || !hasCommittedTopic || topicNeedsConfirmation}
          data-hint={`Помощник посмотрит на тему, хронику и состав стола и предложит именно недостающего эксперта. ${topicDependentHint}`}
        >
          Кого не хватает?
        </button>

        {!activeSession && (
          <button
            className="pixel-btn start"
            onClick={onStartSession}
            disabled={!connected || activeParticipants.length < 2 || !hasCommittedTopic || topicNeedsConfirmation}
            data-hint={`Начать новую сессию обсуждения с текущей темой и составом. ${topicDependentHint}`}
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
            <button
              className="pixel-btn ghost"
              onClick={() => onRunFactCheck?.('round')}
              disabled={!canRunFactCheck || factCheckBusy}
              data-hint="Ручной фактчекинг текущего раунда. Проверяются только верифицируемые тезисы, а спорные интерпретации не штрафуются."
            >
              {factCheckBusy ? 'Проверяем...' : 'Проверить факты'}
            </button>
            <button className="pixel-btn danger" onClick={onStopSession} data-hint="Остановить сессию на ближайшей безопасной точке.">■ Остановить</button>
          </>
        )}

        {finished && (
          <button
            className="pixel-btn ghost"
            onClick={() => onRunFactCheck?.('session')}
            disabled={!canRunFactCheck || factCheckBusy}
            data-hint="Ручной фактчекинг всей завершённой сессии с накоплением надёжности задействованных моделей."
          >
            {factCheckBusy ? 'Проверяем...' : 'Проверить факты'}
          </button>
        )}
      </div>

      {(latestObserverSuggestion || latestObserverReview) && (
        <div className="observer-banner">
          <div className="observer-banner-head">
            <div>
              <div className="observer-banner-title">Хрономант</div>
              {!observerOpen && (
                <div className="observer-banner-compact">
                  {missingExpertHint ? `Кого не хватает: ${missingExpertHint}` : latestObserverSuggestion?.summary || latestObserverReview?.tableComment || latestObserverReview?.roundSummary}
                </div>
              )}
            </div>
            <button
              type="button"
              className="observer-collapse-btn"
              onClick={() => setObserverOpen((value) => !value)}
              data-hint={observerOpen ? 'Свернуть блок Хрономанта и освободить место для управления комнатой.' : 'Развернуть последнюю оценку Хрономанта.'}
            >
              {observerOpen ? 'Свернуть' : 'Развернуть'}
            </button>
          </div>
          {observerOpen && (
            <>
              <div className="observer-banner-body">
                {latestObserverSuggestion?.summary || latestObserverReview?.tableComment || latestObserverReview?.roundSummary}
              </div>
              <div className="observer-decision-card">
                <div className="observer-decision-head">
                  <span>Прогресс решения</span>
                  <b>{decisionReadiness}%</b>
                </div>
                <div className="observer-progress-track">
                  <div className="observer-progress-fill" style={{ width: `${decisionReadiness}%` }} />
                </div>
                <div className="observer-decision-meta">
                  <span>Стадия: {decisionStageLabel}</span>
                  <span>Следующий ход: {nextActionLabel}</span>
                </div>
                <div className="observer-decision-blocker">
                  Блокер: {decisionProgress.blocker || 'явного блокера нет'}
                </div>
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
              <div className="observer-roster-grid">
                {missingExpertHint && (
                  <div className="observer-roster-card is-accent">
                    <div className="observer-roster-title">Кого не хватает</div>
                    <div className="observer-roster-text">{missingExpertHint}</div>
                    {recruitAdviceVisible && (
                      <div className="observer-roster-actions">
                        <button
                          className="pixel-btn ghost"
                          onClick={handleRecruitAdviceAction}
                          disabled={pausePending}
                          data-hint="Открыть точечный добор недостающего героя. Во время живого раунда сначала поставим стол на паузу."
                        >
                          {paused || !activeSession ? 'Подобрать героя' : pausePending ? 'Ждём паузу...' : 'Пауза и добор'}
                        </button>
                        <button
                          className="pixel-btn add"
                          onClick={createSpecialtyFromObserverHint}
                          disabled={!editable || !missingExpertHint}
                          data-hint="Добавить подсказку Хрономанта как новую экспертизу, чтобы дальше выбирать её в профиле персонажа."
                        >
                          Сохранить как экспертизу
                        </button>
                      </div>
                    )}
                  </div>
                )}
                {excessAdviceVisible && (
                  <div className="observer-roster-card is-warning">
                    <div className="observer-roster-title">Кто мешает фокусу сейчас</div>
                    <div className="observer-roster-text">
                      <b>{excessParticipant.name}</b>: {excessParticipant.reason}
                      {excessParticipant.confidence ? ` · уверенность ${excessParticipant.confidence}%` : ''}
                    </div>
                    <div className="observer-roster-actions">
                      <button
                        className="pixel-btn ghost"
                        onClick={handleExcessAdviceAction}
                        disabled={pausePending || !excessParticipantId}
                        data-hint="Ручное решение: во время живого раунда сначала ставим паузу, затем отправляем участника на скамейку."
                      >
                        {running ? 'Пауза и скамейка' : pausePending ? 'Ждём паузу...' : 'На скамейку'}
                      </button>
                      <button
                        className="pixel-btn ghost"
                        onClick={dismissExcessAdvice}
                        data-hint="Скрыть эту подсказку только в интерфейсе. Состав не меняется."
                      >
                        Оставить
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </>
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
          <ParticipantBuilderPanel {...participantBuilderProps} />

          <TeamPresetsPanel {...presetsProps} />

          <PlannedEventsPanel {...eventsProps} />
        </div>
      )}

      <CastingAssistantModal
        open={assistantOpen}
        mode={assistantMode}
        topic={committedTopic}
        provider={selectedProvider}
        model={selectedModel || pickPreferredModel(selectedProvider, providers)}
        providers={providers}
        disabled={!editable}
        roomSummary={room?.summary || ''}
        sessionChronicle={session?.chronicle || ''}
        latestRoundSummary={latestRoundSummary}
        activeParticipants={activeParticipants}
        assistantProvider={assistantSettings.provider || selectedProvider}
        assistantModel={assistantSettings.model || selectedModel || pickPreferredModel(selectedProvider, providers)}
        missingExpertHint={missingExpertHint}
        customSpecialtyGroups={customSpecialtyGroups}
        onAssistantChange={setAssistantSettings}
        onClose={() => setAssistantOpen(false)}
        onAccept={createAssistantParticipants}
      />
    </div>
  )
}
