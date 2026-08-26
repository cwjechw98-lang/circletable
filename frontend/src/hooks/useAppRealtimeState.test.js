import { renderHook, act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import useAppRealtimeState from './useAppRealtimeState.js'

const sendSpy = vi.fn()
let capturedHandler = null

vi.mock('./useWebSocket.js', () => ({
  useWebSocket: (onMessage) => {
    capturedHandler = onMessage
    return { send: sendSpy }
  },
}))

function createInitPayload(overrides = {}) {
  return {
    type: 'init',
    providers: { openai: ['gpt-4'] },
    rooms: [{ id: 'room-1', name: 'Alpha' }],
    currentRoomId: 'room-1',
    customSpecialtyGroups: [{ id: 'spec-1', label: 'Ops' }],
    roomSnapshot: {
      room: { id: 'room-1', name: 'Alpha', lastTopic: 'Seed topic' },
      participants: {
        active: [{ id: 'agent-1', provider: 'openai', model: 'gpt-4' }],
        benched: [],
      },
      inventory: [{ id: 'profile-1' }],
      teamPresets: [{ id: 'preset-1' }],
      plannedEvents: [{ id: 'event-1' }],
      session: { id: 'session-1', status: 'paused', topic: 'Debate topic' },
      messages: [{ id: 'msg-1', type: 'status', content: 'ready' }],
      pinnedMessages: [{ id: 'pin-1' }],
      observerReviews: [{ id: 'review-1', roundNumber: 1 }],
      report: { markdown: '# Report' },
      factCheck: { status: 'completed' },
    },
    sessionState: {
      state: 'paused',
      session: { id: 'session-1', status: 'paused', topic: 'Debate topic' },
    },
    ...overrides,
  }
}

describe('useAppRealtimeState', () => {
  beforeEach(() => {
    sendSpy.mockReset()
    capturedHandler = null
  })

  it('hydrates room and session state from init payload', () => {
    const onProvidersLoaded = vi.fn()
    const { result } = renderHook(() => useAppRealtimeState({ onProvidersLoaded }))

    act(() => {
      capturedHandler(createInitPayload())
    })

    expect(onProvidersLoaded).toHaveBeenCalledTimes(1)
    expect(result.current.state.room.providers).toEqual({ openai: ['gpt-4'] })
    expect(result.current.state.room.rooms).toEqual([{ id: 'room-1', name: 'Alpha' }])
    expect(result.current.state.room.currentRoomId).toBe('room-1')
    expect(result.current.state.room.room).toMatchObject({ id: 'room-1', name: 'Alpha' })
    expect(result.current.state.session.session).toMatchObject({ id: 'session-1', status: 'paused' })
    expect(result.current.state.session.topic).toBe('Debate topic')
    expect(result.current.state.session.topicDraft).toBe('Debate topic')
    expect(result.current.state.room.teamPresets).toEqual([{ id: 'preset-1' }])
    expect(result.current.state.room.customSpecialtyGroups).toEqual([{ id: 'spec-1', label: 'Ops' }])
    expect(result.current.state.derived.activeParticipants).toHaveLength(1)
  })

  it('updates room snapshot on room_loaded and clears session data on reset', () => {
    const { result } = renderHook(() => useAppRealtimeState({}))

    act(() => {
      capturedHandler(createInitPayload())
      capturedHandler({
        type: 'room_loaded',
        room: { id: 'room-1', name: 'Beta', lastTopic: 'Fresh topic' },
        session: { id: 'session-2', status: 'running', topic: 'Fresh topic' },
        messages: [{ id: 'msg-2', type: 'status', content: 'updated' }],
      })
    })

    expect(result.current.state.room.room).toMatchObject({ name: 'Beta' })
    expect(result.current.state.session.session).toMatchObject({ id: 'session-2', status: 'running' })
    expect(result.current.state.session.topic).toBe('Fresh topic')

    act(() => {
      capturedHandler({ type: 'reset' })
    })

    expect(result.current.state.session.session).toBeNull()
    expect(result.current.state.session.sessionState).toBe('idle')
    expect(result.current.state.session.messages).toEqual([])
    expect(result.current.state.session.report).toBeNull()
    expect(result.current.state.session.factCheck).toBeNull()
  })

  it('handles planned events, report, fact check, and pin toggles', () => {
    const { result } = renderHook(() => useAppRealtimeState({}))

    act(() => {
      capturedHandler(createInitPayload())
      capturedHandler({ type: 'planned_events_updated', roomId: 'room-1', plannedEvents: [{ id: 'event-2' }] })
      capturedHandler({ type: 'report_completed', session_id: 'session-1', report: { markdown: '# Final' } })
      capturedHandler({ type: 'fact_check_completed', session_id: 'session-1', factCheck: { status: 'completed', claims: [] } })
      capturedHandler({
        type: 'message_pin_toggled',
        messages: [{ id: 'msg-3', type: 'status', content: 'pinned' }],
        pinnedMessages: [{ id: 'pin-2' }],
      })
    })

    expect(result.current.state.room.plannedEvents).toEqual([{ id: 'event-2' }])
    expect(result.current.state.session.report).toEqual({ markdown: '# Final' })
    expect(result.current.state.session.reportProgress).toBe(100)
    expect(result.current.state.session.factCheck).toEqual({ status: 'completed', claims: [] })
    expect(result.current.state.session.messages).toEqual([{ id: 'msg-3', type: 'status', content: 'pinned' }])
    expect(result.current.state.session.pinnedMessages).toEqual([{ id: 'pin-2' }])
  })

  it('fires transport callbacks for close and providers refresh', () => {
    const onSocketClosed = vi.fn()
    const onProvidersLoaded = vi.fn()
    const { result } = renderHook(() => useAppRealtimeState({ onSocketClosed, onProvidersLoaded }))

    act(() => {
      capturedHandler({ type: '_ws_open' })
    })
    expect(result.current.state.connection.connected).toBe(true)

    act(() => {
      capturedHandler({ type: 'providers', providers: { anthropic: ['claude'] } })
    })
    expect(onProvidersLoaded).toHaveBeenCalledTimes(1)
    expect(result.current.state.room.providers).toEqual({ anthropic: ['claude'] })

    act(() => {
      capturedHandler({ type: '_ws_close' })
    })
    expect(onSocketClosed).toHaveBeenCalledTimes(1)
    expect(result.current.state.connection.connected).toBe(false)
  })
})
