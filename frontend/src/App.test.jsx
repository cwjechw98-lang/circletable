import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import useAppRealtimeState from './hooks/useAppRealtimeState.js'
import useAppCommands from './hooks/useAppCommands.js'

vi.mock('./hooks/useAppRealtimeState.js', () => ({
  default: vi.fn(),
}))

vi.mock('./hooks/useAppCommands.js', () => ({
  default: vi.fn(),
}))

vi.mock('./components/RoundTable.jsx', () => ({
  default: () => <div data-testid="round-table" />,
}))

vi.mock('./components/ChatPanel.jsx', () => ({
  default: () => <div data-testid="chat-panel" />,
}))

vi.mock('./components/ControlPanel.jsx', () => ({
  default: () => <div data-testid="control-panel" />,
}))

vi.mock('./components/RoomsDrawer.jsx', () => ({
  default: () => <div data-testid="rooms-drawer" />,
}))

vi.mock('./components/InventoryDrawer.jsx', () => ({
  default: () => <div data-testid="inventory-drawer" />,
}))

vi.mock('./components/TimedHintLayer.jsx', () => ({
  default: () => <div data-testid="timed-hint-layer" />,
}))

vi.mock('./components/TopicFocusOverlay.jsx', () => ({
  default: () => <div data-testid="topic-focus-overlay" />,
}))

vi.mock('./components/RoundAnnounce.jsx', () => ({
  default: ({ round, onDone }) => (
    <button type="button" onClick={onDone}>
      announce {round}
    </button>
  ),
}))

function createRealtimeMock(overrides = {}) {
  const setAnnounce = vi.fn()

  return {
    value: {
      state: {
        connection: { connected: true },
        room: {
          providers: {},
          rooms: [],
          currentRoomId: 'room-1',
          room: { id: 'room-1', name: 'Alpha', observerMode: 'suggest', densityMode: 'normal' },
          inventory: [],
          teamPresets: [],
          customSpecialtyGroups: [],
          plannedEvents: [],
        },
        session: {
          messages: [],
          pinnedMessages: [],
          report: null,
          reportGenerating: false,
          reportProgress: 0,
          reportError: '',
          factCheck: null,
          factCheckError: '',
          session: null,
          sessionState: 'idle',
          topic: 'Topic',
          topicDraft: 'Topic',
          topicDirty: false,
          topicFocusActive: false,
          observerBusy: false,
          observerSuggestion: null,
          announce: { round: 3 },
        },
        live: {
          responseMetrics: {},
          slowThinkingSet: new Set(),
          thinkingSet: new Set(),
          speakingSet: new Set(),
          streamTexts: {},
          emotions: {},
        },
        derived: {
          activeParticipants: [],
          benchedParticipants: [],
          latestObserverReview: null,
          topicEditable: true,
        },
      },
      actions: {
        applyRoomSnapshot: vi.fn(),
        setRoom: vi.fn(),
        setObserverBusy: vi.fn(),
        setAnnounce,
        setCustomSpecialtyGroups: vi.fn(),
        topic: {
          setTopic: vi.fn(),
          setTopicDraft: vi.fn(),
          setTopicDirty: vi.fn(),
          setTopicFocusActive: vi.fn(),
        },
        report: {
          setReport: vi.fn(),
          setReportGenerating: vi.fn(),
          setReportProgress: vi.fn(),
          setReportError: vi.fn(),
        },
        factCheck: {
          setFactCheck: vi.fn(),
          setFactCheckError: vi.fn(),
        },
      },
      sendMsg: vi.fn(),
      ...overrides,
    },
    setAnnounce,
  }
}

function createCommandMock() {
  return {
    handleTopicDraftChange: vi.fn(),
    handleBeginTopicEditing: vi.fn(),
    handleCancelTopicEdit: vi.fn(),
    handleConfirmTopicEdit: vi.fn(),
    handleCreateRoom: vi.fn(),
    handleRenameRoom: vi.fn(),
    handleDeleteRoom: vi.fn(),
    handleSaveParticipant: vi.fn(),
    handleDeleteProfile: vi.fn(),
    handleLoadRoom: vi.fn(),
    handleForkSession: vi.fn(),
    handleStartSession: vi.fn(),
    handlePauseSession: vi.fn(),
    handleResumeSession: vi.fn(),
    handleStopSession: vi.fn(),
    handleRequestWrap: vi.fn(),
    handleRequestFinal: vi.fn(),
    handleCreateParticipant: vi.fn(),
    handleAddFromInventory: vi.fn(),
    handleBenchParticipant: vi.fn(),
    handleRestoreParticipant: vi.fn(),
    handleSubmitQuestion: vi.fn(),
    handleCreateTeamPreset: vi.fn(),
    handleDeleteTeamPreset: vi.fn(),
    handleApplyTeamPreset: vi.fn(),
    handleCreateCustomSpecialty: vi.fn(),
    handleUpdateCustomSpecialty: vi.fn(),
    handleDeleteCustomSpecialty: vi.fn(),
    handleToggleMessagePin: vi.fn(),
    handleInternetModeChange: vi.fn(),
    handleObserverModeChange: vi.fn(),
    handleDensityModeChange: vi.fn(),
    handleGenerateReport: vi.fn(),
    handleDownloadReport: vi.fn(),
    handleRunFactCheck: vi.fn(),
    handleCreatePlannedEvent: vi.fn(),
    handleUpdatePlannedEvent: vi.fn(),
    handleDeletePlannedEvent: vi.fn(),
  }
}

describe('App shell baseline', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('updates theme on the app shell and persists it', async () => {
    const user = userEvent.setup()
    const realtime = createRealtimeMock()
    vi.mocked(useAppRealtimeState).mockReturnValue(realtime.value)
    vi.mocked(useAppCommands).mockReturnValue(createCommandMock())

    const { container } = render(<App />)

    await user.selectOptions(screen.getByRole('combobox', { name: 'Палитра' }), 'matrix')

    expect(container.firstChild?.getAttribute('data-theme')).toBe('matrix')
    expect(localStorage.getItem('circletable-theme')).toBe('matrix')
  })

  it('updates topic focus mode and persists it', async () => {
    const user = userEvent.setup()
    const realtime = createRealtimeMock()
    vi.mocked(useAppRealtimeState).mockReturnValue(realtime.value)
    vi.mocked(useAppCommands).mockReturnValue(createCommandMock())

    render(<App />)

    await user.selectOptions(screen.getByRole('combobox', { name: 'Фокус' }), 'mist')

    expect(localStorage.getItem('circletable-topic-focus-mode-v1')).toBe('mist')
  })

  it('dismisses round announce through realtime action', async () => {
    const user = userEvent.setup()
    const realtime = createRealtimeMock()
    vi.mocked(useAppRealtimeState).mockReturnValue(realtime.value)
    vi.mocked(useAppCommands).mockReturnValue(createCommandMock())

    render(<App />)

    await user.click(screen.getByRole('button', { name: 'announce 3' }))

    expect(realtime.setAnnounce).toHaveBeenCalledWith(null)
  })
})
