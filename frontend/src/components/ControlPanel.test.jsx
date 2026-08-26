import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ControlPanel from './ControlPanel.jsx'

vi.mock('./CastingAssistantModal.jsx', () => ({
  default: () => <div data-testid="casting-assistant" />,
}))

vi.mock('./panel/CustomSpecialtiesPanel.jsx', () => ({
  default: () => <div data-testid="custom-specialties-panel" />,
}))

vi.mock('./panel/DocumentsPanel.jsx', () => ({
  default: () => <div data-testid="documents-panel" />,
}))

vi.mock('./panel/PlannedEventsPanel.jsx', () => ({
  default: () => <div data-testid="planned-events-panel" />,
}))

vi.mock('./panel/ParticipantBuilderPanel.jsx', () => ({
  default: () => <div data-testid="participant-builder-panel" />,
}))

vi.mock('./panel/TeamPresetsPanel.jsx', () => ({
  default: () => <div data-testid="team-presets-panel" />,
}))

vi.mock('../hooks/useBuilderState.js', () => ({
  default: () => ({
    presetsProps: {},
    eventsProps: {},
    customSpecialtiesProps: {},
  }),
}))

vi.mock('../hooks/useParticipantBuilderState.js', () => ({
  default: () => ({
    participantBuilderProps: {},
    selectedProvider: 'ollama',
    selectedModel: 'test-model',
    availableProviders: [],
    setSelectedSpecialty: vi.fn(),
    createAssistantParticipants: vi.fn(),
  }),
}))

function createProps(overrides = {}) {
  return {
    providers: {},
    room: { id: 'room-1', name: 'Комната', observerMode: 'suggest', densityMode: 'normal' },
    session: { id: 'session-1', status: 'paused', topic: 'Тема', lastRoundNumber: 2, chronicle: '' },
    sessionState: 'paused',
    committedTopic: 'Тема',
    draftTopic: 'Тема',
    topicDirty: false,
    topicFocusMode: 'off',
    topicFocusActive: false,
    activeParticipants: [
      { id: 'p-cat', profileId: 'prof-cat', name: 'Кот' },
      { id: 'p-fox', profileId: 'prof-fox', name: 'Лиса' },
    ],
    connected: true,
    refreshingProviders: false,
    latestObserverSuggestion: null,
    latestObserverReview: {
      roundNumber: 2,
      summary: 'Раунд собрал варианты решения.',
      progress: {
        novelty: 52,
        focus: 61,
        convergence: 58,
        decisionProgress: {
          stage: 'converge',
          readiness: 64,
          blocker: 'Не хватает коммерческого угла.',
          nextAction: 'add_expert',
        },
      },
      rosterAdvice: {},
    },
    observerBusy: false,
    teamPresets: [],
    customSpecialtyGroups: [],
    plannedEvents: [],
    currentRoomId: 'room-1',
    onTopicDraftChange: vi.fn(),
    onBeginTopicEditing: vi.fn(),
    onConfirmTopic: vi.fn(),
    onCancelTopic: vi.fn(),
    onStartSession: vi.fn(),
    onPauseSession: vi.fn(),
    onResumeSession: vi.fn(),
    onStopSession: vi.fn(),
    onRequestWrap: vi.fn(),
    onRequestFinal: vi.fn(),
    onOpenRooms: vi.fn(),
    onOpenInventory: vi.fn(),
    onRefreshProviders: vi.fn(),
    onObserverModeChange: vi.fn(),
    onDensityModeChange: vi.fn(),
    onCreateParticipant: vi.fn(),
    onBenchParticipant: vi.fn(),
    onSubmitQuestion: vi.fn(),
    onCreateTeamPreset: vi.fn(),
    onApplyTeamPreset: vi.fn(),
    onDeleteTeamPreset: vi.fn(),
    onCreateCustomSpecialty: vi.fn(),
    onUpdateCustomSpecialty: vi.fn(),
    onDeleteCustomSpecialty: vi.fn(),
    onInternetModeChange: vi.fn(),
    onRunFactCheck: vi.fn(),
    factCheck: null,
    onCreatePlannedEvent: vi.fn(),
    onUpdatePlannedEvent: vi.fn(),
    onDeletePlannedEvent: vi.fn(),
    ...overrides,
  }
}

function withRosterAdvice(overrides = {}) {
  return {
    roundNumber: 2,
    summary: 'Раунд собрал варианты решения.',
    progress: {
      novelty: 52,
      focus: 41,
      convergence: 48,
      decisionProgress: {
        stage: 'challenge',
        readiness: 45,
        blocker: 'Разговор расползается.',
        nextAction: 'bench_participant',
      },
    },
    rosterAdvice: {
      missingExpertHint: 'Практик по продажам и воронкам.',
      excessParticipant: {
        participantId: 'p-cat',
        profileId: 'prof-cat',
        name: 'Кот',
        reason: 'Уводит разговор в сторону.',
        confidence: 72,
      },
      balanceNote: 'Нужна фокусировка состава.',
      gapStatus: 'conflicted',
    },
    ...overrides,
  }
}

describe('ControlPanel observer banner', () => {
  it('shows decision readiness, stage and next action', () => {
    render(<ControlPanel {...createProps()} />)

    expect(screen.getByText('Прогресс решения')).toBeTruthy()
    expect(screen.getByText('64%')).toBeTruthy()
    expect(screen.getByText('Стадия: Сведение вариантов')).toBeTruthy()
    expect(screen.getByText('Следующий ход: Добрать эксперта')).toBeTruthy()
    expect(screen.getByText('Блокер: Не хватает коммерческого угла.')).toBeTruthy()
  })

  it('shows missing expert and focus-disrupting participant cards', () => {
    render(<ControlPanel {...createProps({ latestObserverReview: withRosterAdvice() })} />)

    expect(screen.getByText('Кого не хватает')).toBeTruthy()
    expect(screen.getByText('Практик по продажам и воронкам.')).toBeTruthy()
    expect(screen.getByText('Кто мешает фокусу сейчас')).toBeTruthy()
    expect(screen.getByText(/Кот/)).toBeTruthy()
    expect(screen.getByText(/Уводит разговор в сторону/)).toBeTruthy()
  })

  it('pauses before benching during running session and benches directly on pause', async () => {
    const user = userEvent.setup()
    const onPauseSession = vi.fn()
    const onBenchParticipant = vi.fn()
    const { unmount } = render(
      <ControlPanel
        {...createProps({
          session: { id: 'session-1', status: 'running', topic: 'Тема' },
          sessionState: 'running',
          latestObserverReview: withRosterAdvice(),
          onPauseSession,
          onBenchParticipant,
        })}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Пауза и скамейка' }))

    expect(onPauseSession).toHaveBeenCalledTimes(1)
    expect(onBenchParticipant).not.toHaveBeenCalled()

    unmount()
    render(
      <ControlPanel
        {...createProps({
          latestObserverReview: withRosterAdvice(),
          onPauseSession,
          onBenchParticipant,
        })}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'На скамейку' }))

    expect(onBenchParticipant).toHaveBeenCalledWith('p-cat')
  })
})
