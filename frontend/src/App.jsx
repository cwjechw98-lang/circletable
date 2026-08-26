import React, { useCallback, useEffect, useRef, useState } from 'react'
import RoundTable from './components/RoundTable.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import ControlPanel from './components/ControlPanel.jsx'
import RoundAnnounce from './components/RoundAnnounce.jsx'
import RoomsDrawer from './components/RoomsDrawer.jsx'
import InventoryDrawer from './components/InventoryDrawer.jsx'
import LabDrawer from './components/LabDrawer.jsx'
import ProvidersDrawer from './components/ProvidersDrawer.jsx'
import TimedHintLayer from './components/TimedHintLayer.jsx'
import TopicFocusOverlay from './components/TopicFocusOverlay.jsx'
import useAppCommands from './hooks/useAppCommands.js'
import useAppRealtimeState from './hooks/useAppRealtimeState.js'

async function apiJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    const text = await response.text()
    let message = text
    try {
      const parsed = JSON.parse(text)
      message = parsed?.detail || parsed?.message || text
    } catch {
      message = text
    }
    throw new Error(message || `Ошибка запроса: ${response.status}`)
  }

  if (response.status === 204) {
    return null
  }

  return response.json()
}

function normalizeMode(mode) {
  if (mode === 'manual') return 'Бесконечный'
  if (mode === 'auto') return 'Автофинал'
  return 'С подсказками'
}

const THEME_OPTIONS = [
  { value: 'classic', label: 'Аркада' },
  { value: 'matrix', label: 'Матрица' },
  { value: 'ember', label: 'Уголь' },
  { value: 'slate', label: 'Сталь' },
  { value: 'violet', label: 'Ночь' },
  { value: 'abyss', label: 'Бездна' },
  { value: 'aurora', label: 'Аврора' },
  { value: 'porcelain', label: 'Фарфор' },
  { value: 'sand', label: 'Песок' },
]

function readTheme() {
  try {
    return localStorage.getItem('circletable-theme') || 'classic'
  } catch {
    return 'classic'
  }
}

const UI_FONT_SCALE_KEY = 'circletable-ui-font-scale-v1'
const UI_FONT_SCALE_MIN = 0.9
const UI_FONT_SCALE_MAX = 1.6
const CHAT_PANEL_WIDTH_KEY = 'circletable-chat-panel-width-v1'
const CHAT_PANEL_MIN = 320
const CHAT_PANEL_MAX = 860
const TOPIC_FOCUS_MODE_KEY = 'circletable-topic-focus-mode-v1'
const TOPIC_FOCUS_OPTIONS = [
  { value: 'off', label: 'Off' },
  { value: 'dim', label: 'Dim' },
  { value: 'glass', label: 'Glass' },
  { value: 'mist', label: 'Mist' },
]

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function clampChatPanelWidth(value) {
  const viewportWidth = typeof window === 'undefined' ? 1600 : window.innerWidth
  const maxAllowed = clamp(Math.round(viewportWidth * 0.48), 360, CHAT_PANEL_MAX)
  return clamp(Number(value) || 0, CHAT_PANEL_MIN, maxAllowed)
}

function readUiFontScale() {
  try {
    const raw = Number(localStorage.getItem(UI_FONT_SCALE_KEY) || '1')
    return Number.isFinite(raw) ? clamp(raw, UI_FONT_SCALE_MIN, UI_FONT_SCALE_MAX) : 1
  } catch {
    return 1
  }
}

function readChatPanelWidth() {
  try {
    const raw = Number(localStorage.getItem(CHAT_PANEL_WIDTH_KEY) || '400')
    return Number.isFinite(raw) ? clampChatPanelWidth(raw) : 400
  } catch {
    return 400
  }
}

function readTopicFocusMode() {
  try {
    const saved = localStorage.getItem(TOPIC_FOCUS_MODE_KEY) || 'glass'
    return TOPIC_FOCUS_OPTIONS.some((option) => option.value === saved) ? saved : 'glass'
  } catch {
    return 'glass'
  }
}

export default function App() {
  const [shuttingDown, setShuttingDown] = useState(false)
  const [topicFocusMode, setTopicFocusMode] = useState(readTopicFocusMode)
  const [refreshingProviders, setRefreshingProviders] = useState(false)
  const [roomsOpen, setRoomsOpen] = useState(false)
  const [inventoryOpen, setInventoryOpen] = useState(false)
  const [labOpen, setLabOpen] = useState(false)
  const [providersOpen, setProvidersOpen] = useState(false)
  const [theme, setTheme] = useState(readTheme)
  const [uiFontScale, setUiFontScale] = useState(readUiFontScale)
  const [fontPanelOpen, setFontPanelOpen] = useState(false)
  const [chatPanelWidth, setChatPanelWidth] = useState(readChatPanelWidth)
  const [chatResizeActive, setChatResizeActive] = useState(false)
  const chatResizeRef = useRef(null)
  const {
    state: {
      connection: { connected },
      room: {
        providers,
        rooms,
        currentRoomId,
        room,
        inventory,
        teamPresets,
        customSpecialtyGroups,
        plannedEvents,
      },
      session: {
        messages,
        pinnedMessages,
        report,
        reportGenerating,
        reportProgress,
        reportError,
        factCheck,
        factCheckError,
        session,
        sessionState,
        topic,
        topicDraft,
        topicDirty,
        topicFocusActive,
        observerBusy,
        observerSuggestion,
        announce,
      },
      live: {
        responseMetrics,
        slowThinkingSet,
        thinkingSet,
        speakingSet,
        streamTexts,
        emotions,
      },
      derived: {
        activeParticipants,
        benchedParticipants,
        latestObserverReview,
        topicEditable,
      },
    },
    actions: {
      applyRoomSnapshot,
      setRoom,
      setObserverBusy,
      setAnnounce,
      setCustomSpecialtyGroups,
      topic: {
        setTopic,
        setTopicDraft,
        setTopicDirty,
        setTopicFocusActive,
      },
      report: {
        setReport,
        setReportGenerating,
        setReportProgress,
        setReportError,
      },
      factCheck: {
        setFactCheck,
        setFactCheckError,
      },
    },
    sendMsg,
  } = useAppRealtimeState({
    onSocketClosed: () => {
      setShuttingDown(false)
      setRefreshingProviders(false)
    },
    onProvidersLoaded: () => {
      setRefreshingProviders(false)
    },
    onShutdownRequested: () => {
      setShuttingDown(true)
    },
  })

  const headerMode = normalizeMode(room?.observerMode)
  const {
    handleTopicDraftChange,
    handleBeginTopicEditing,
    handleCancelTopicEdit,
    handleConfirmTopicEdit,
    handleCreateRoom,
    handleRenameRoom,
    handleDeleteRoom,
    handleSaveParticipant,
    handleDeleteProfile,
    handleLoadRoom,
    handleForkSession,
    handleStartSession,
    handlePauseSession,
    handleResumeSession,
    handleStopSession,
    handleRequestWrap,
    handleRequestFinal,
    handleCreateParticipant,
    handleAddFromInventory,
    handleBenchParticipant,
    handleRestoreParticipant,
    handleSubmitQuestion,
    handleCreateTeamPreset,
    handleDeleteTeamPreset,
    handleApplyTeamPreset,
    handleCreateCustomSpecialty,
    handleUpdateCustomSpecialty,
    handleDeleteCustomSpecialty,
    handleToggleMessagePin,
    handleInternetModeChange,
    handleObserverModeChange,
    handleDensityModeChange,
    handleGenerateReport,
    handleDownloadReport,
    handleRunFactCheck,
    handleCreatePlannedEvent,
    handleUpdatePlannedEvent,
    handleDeletePlannedEvent,
  } = useAppCommands({
    apiJson,
    currentRoomId,
    room,
    report,
    session,
    topic,
    topicDraft,
    activeParticipants,
    topicEditable,
    topicFocusMode,
    sendMsg,
    applyRoomSnapshot,
    setRoom,
    setCustomSpecialtyGroups,
    setObserverBusy,
    setTopic,
    setTopicDraft,
    setTopicDirty,
    setTopicFocusActive,
    setReport,
    setReportGenerating,
    setReportProgress,
    setReportError,
    setFactCheck,
    setFactCheckError,
  })

  useEffect(() => {
    localStorage.setItem(TOPIC_FOCUS_MODE_KEY, topicFocusMode)
  }, [topicFocusMode])

  function handleThemeChange(nextTheme) {
    setTheme(nextTheme)
    localStorage.setItem('circletable-theme', nextTheme)
  }

  function handleTopicFocusModeChange(nextMode) {
    setTopicFocusMode(nextMode)
    if (nextMode === 'off') {
      setTopicFocusActive(false)
    }
  }

  async function handleShutdownApp() {
    if (shuttingDown) return
    setShuttingDown(true)
    try {
      await apiJson('/api/system/shutdown', { method: 'POST' })
    } catch (error) {
      console.error(error)
      setShuttingDown(false)
    }
  }

  function handleFontScaleChange(nextScale) {
    const clamped = clamp(Number(nextScale), UI_FONT_SCALE_MIN, UI_FONT_SCALE_MAX)
    setUiFontScale(clamped)
    localStorage.setItem(UI_FONT_SCALE_KEY, String(clamped))
  }

  function handleFontScaleReset() {
    setUiFontScale(1)
    localStorage.setItem(UI_FONT_SCALE_KEY, '1')
  }

  const handleChatResizeMove = useCallback((event) => {
    const drag = chatResizeRef.current
    if (!drag) return
    const delta = drag.startX - event.clientX
    setChatPanelWidth(clampChatPanelWidth(drag.startWidth + delta))
  }, [])

  const stopChatResize = useCallback(() => {
    if (!chatResizeRef.current) return
    chatResizeRef.current = null
    setChatResizeActive(false)
    document.body.classList.remove('is-resizing-chat')
  }, [])

  function startChatResize(event) {
    if (event.button !== 0) return
    chatResizeRef.current = { startX: event.clientX, startWidth: chatPanelWidth }
    setChatResizeActive(true)
    document.body.classList.add('is-resizing-chat')
    event.preventDefault()
  }

  function resetChatPanelWidth() {
    const next = clampChatPanelWidth(400)
    setChatPanelWidth(next)
    localStorage.setItem(CHAT_PANEL_WIDTH_KEY, String(next))
  }

  useEffect(() => {
    localStorage.setItem(CHAT_PANEL_WIDTH_KEY, String(chatPanelWidth))
  }, [chatPanelWidth])

  useEffect(() => {
    function handleViewportResize() {
      setChatPanelWidth((current) => clampChatPanelWidth(current))
    }
    window.addEventListener('resize', handleViewportResize)
    window.addEventListener('pointermove', handleChatResizeMove)
    window.addEventListener('pointerup', stopChatResize)
    window.addEventListener('pointercancel', stopChatResize)
    return () => {
      window.removeEventListener('resize', handleViewportResize)
      window.removeEventListener('pointermove', handleChatResizeMove)
      window.removeEventListener('pointerup', stopChatResize)
      window.removeEventListener('pointercancel', stopChatResize)
      document.body.classList.remove('is-resizing-chat')
    }
  }, [handleChatResizeMove, stopChatResize])

  return (
    <div
      className={`app${topicFocusActive && topicFocusMode !== 'off' ? ' is-topic-focus-active' : ''}`}
      data-theme={theme}
      style={{ '--ui-font-scale': uiFontScale, '--chat-panel-width': `${chatPanelWidth}px` }}
    >
      <TimedHintLayer />
      {announce && <RoundAnnounce round={announce.round} onDone={() => setAnnounce(null)} />}
      <TopicFocusOverlay
        active={topicEditable && topicFocusActive && topicFocusMode !== 'off'}
        mode={topicFocusMode}
        value={topicDraft}
        dirty={topicDirty}
        onChange={handleTopicDraftChange}
        onConfirm={handleConfirmTopicEdit}
        onCancel={handleCancelTopicEdit}
      />

      {observerBusy && (
        <div className="observer-overlay">
          <div className="observer-overlay-card">
            <div className="observer-overlay-title">Хрономант оценивает ход беседы</div>
            <div className="observer-overlay-sub">Собирает хронику, ачивки и подсказки для следующего раунда.</div>
          </div>
        </div>
      )}

      <RoomsDrawer
        open={roomsOpen}
        rooms={rooms}
        currentRoomId={currentRoomId}
        onClose={() => setRoomsOpen(false)}
        onLoadRoom={handleLoadRoom}
        onSessionSnapshot={applyRoomSnapshot}
        onCreateRoom={handleCreateRoom}
        onRenameRoom={handleRenameRoom}
        onDeleteRoom={handleDeleteRoom}
        onForkSession={handleForkSession}
      />

      <InventoryDrawer
        open={inventoryOpen}
        activeParticipants={activeParticipants}
        benchedParticipants={benchedParticipants}
        inventory={inventory}
        onClose={() => setInventoryOpen(false)}
        onAddFromInventory={handleAddFromInventory}
        onBenchParticipant={handleBenchParticipant}
        onRestoreParticipant={handleRestoreParticipant}
        onSaveParticipant={handleSaveParticipant}
        onDeleteProfile={handleDeleteProfile}
      />

      <LabDrawer
        open={labOpen}
        onClose={() => setLabOpen(false)}
      />

      <ProvidersDrawer
        open={providersOpen}
        onClose={() => setProvidersOpen(false)}
        providers={providers}
        onRefreshProviders={() => sendMsg({ type: 'get_providers' })}
      />

      <header className="app-header">
        <div>
          <div className="header-title">⚔ Круглый стол ИИ ⚔</div>
          <div className="header-subtitle">{room?.name || 'Комната не выбрана'} · {headerMode}</div>
        </div>
        <div className="header-status">
          <label className="theme-switcher" data-hint="Переключить цветовую тему интерфейса.">
            <span>Палитра</span>
            <select value={theme} onChange={(event) => handleThemeChange(event.target.value)}>
              {THEME_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="theme-switcher" data-hint="Визуальный режим фокуса во время формулировки новой темы. Off — без эффектов, Glass и Mist — атмосферные варианты.">
            <span>Фокус</span>
            <select value={topicFocusMode} onChange={(event) => handleTopicFocusModeChange(event.target.value)}>
              {TOPIC_FOCUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <div className="header-status-indicator">
            <div className={`status-led${connected ? ' on' : ''}`} />
            {connected ? 'На связи' : 'Подключение...'}
          </div>
          <button
            className="pixel-btn danger header-exit-btn"
            onClick={handleShutdownApp}
            disabled={shuttingDown}
          >
            {shuttingDown ? 'Завершаем...' : 'Завершить сеанс'}
          </button>
        </div>
      </header>

      <div className="table-area">
        <RoundTable
          agents={activeParticipants}
          topic={session?.topic || topic}
          densityMode={room?.densityMode || 'normal'}
          thinkingSet={thinkingSet}
          speakingSet={speakingSet}
          streamTexts={streamTexts}
          emotions={emotions}
          responseMetrics={responseMetrics}
          slowThinkingSet={slowThinkingSet}
          uiFontScale={uiFontScale}
          fontPanelOpen={fontPanelOpen}
          onToggleFontPanel={() => setFontPanelOpen((value) => !value)}
          onFontScaleChange={handleFontScaleChange}
          onFontScaleReset={handleFontScaleReset}
          fontScaleMin={UI_FONT_SCALE_MIN}
          fontScaleMax={UI_FONT_SCALE_MAX}
        />

        <ControlPanel
          providers={providers}
          room={room}
          session={session}
          sessionState={sessionState}
          committedTopic={topic}
          draftTopic={topicDraft}
          topicDirty={topicDirty}
          topicFocusMode={topicFocusMode}
          topicFocusActive={topicFocusActive}
          activeParticipants={activeParticipants}
          connected={connected}
          refreshingProviders={refreshingProviders}
          latestObserverSuggestion={observerSuggestion}
          latestObserverReview={latestObserverReview}
          observerBusy={observerBusy}
          teamPresets={teamPresets}
          customSpecialtyGroups={customSpecialtyGroups}
          plannedEvents={plannedEvents}
          currentRoomId={currentRoomId}
          onTopicDraftChange={handleTopicDraftChange}
          onBeginTopicEditing={handleBeginTopicEditing}
          onConfirmTopic={handleConfirmTopicEdit}
          onCancelTopic={handleCancelTopicEdit}
          onStartSession={handleStartSession}
          onPauseSession={handlePauseSession}
          onResumeSession={handleResumeSession}
          onStopSession={handleStopSession}
          onRequestWrap={handleRequestWrap}
          onRequestFinal={handleRequestFinal}
          onOpenRooms={() => setRoomsOpen(true)}
          onOpenInventory={() => setInventoryOpen(true)}
          onOpenLab={() => setLabOpen(true)}
          onOpenProviders={() => {
            setProvidersOpen(true)
            if (!connected) return
            sendMsg({ type: 'get_providers' })
          }}
          onRefreshProviders={() => {
            setRefreshingProviders(true)
            sendMsg({ type: 'get_providers' })
          }}
          onObserverModeChange={handleObserverModeChange}
          onDensityModeChange={handleDensityModeChange}
          onCreateParticipant={handleCreateParticipant}
          onBenchParticipant={handleBenchParticipant}
          onSubmitQuestion={handleSubmitQuestion}
          onCreateTeamPreset={handleCreateTeamPreset}
          onApplyTeamPreset={handleApplyTeamPreset}
          onDeleteTeamPreset={handleDeleteTeamPreset}
          onCreateCustomSpecialty={handleCreateCustomSpecialty}
          onUpdateCustomSpecialty={handleUpdateCustomSpecialty}
          onDeleteCustomSpecialty={handleDeleteCustomSpecialty}
          onInternetModeChange={handleInternetModeChange}
          onRunFactCheck={handleRunFactCheck}
          factCheck={factCheck}
          onCreatePlannedEvent={handleCreatePlannedEvent}
          onUpdatePlannedEvent={handleUpdatePlannedEvent}
          onDeletePlannedEvent={handleDeletePlannedEvent}
        />
      </div>

      <div
        className={`chat-resizer${chatResizeActive ? ' is-active' : ''}`}
        onPointerDown={startChatResize}
        onDoubleClick={resetChatPanelWidth}
        data-hint="Потяните, чтобы изменить ширину журнала беседы. Двойной клик вернёт стандартный размер."
        role="separator"
        aria-orientation="vertical"
        aria-label="Изменить ширину журнала беседы"
      />
      <ChatPanel
        messages={messages}
        pinnedMessages={pinnedMessages}
        onTogglePin={handleToggleMessagePin}
        session={session}
        sessionState={sessionState}
        report={report}
        reportGenerating={reportGenerating}
        reportProgress={reportProgress}
        reportError={reportError}
        onGenerateReport={handleGenerateReport}
        onDownloadReport={handleDownloadReport}
        factCheck={factCheck}
        factCheckError={factCheckError}
      />
    </div>
  )
}
