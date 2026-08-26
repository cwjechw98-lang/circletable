import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import useAppCommands from './useAppCommands.js'

function createArgs(overrides = {}) {
  return {
    apiJson: vi.fn(),
    currentRoomId: 'room-1',
    room: { observerMode: 'suggest' },
    report: { markdown: '# Report' },
    session: { id: 'session-1' },
    topic: 'Current topic',
    topicDraft: 'Draft topic',
    activeParticipants: [{ id: 'agent-1' }],
    topicEditable: true,
    topicFocusMode: 'glass',
    sendMsg: vi.fn(),
    applyRoomSnapshot: vi.fn(),
    setRoom: vi.fn(),
    setCustomSpecialtyGroups: vi.fn(),
    setObserverBusy: vi.fn(),
    setTopic: vi.fn(),
    setTopicDraft: vi.fn(),
    setTopicDirty: vi.fn(),
    setTopicFocusActive: vi.fn(),
    setReport: vi.fn(),
    setReportGenerating: vi.fn(),
    setReportProgress: vi.fn(),
    setReportError: vi.fn(),
    setFactCheck: vi.fn(),
    setFactCheckError: vi.fn(),
    ...overrides,
  }
}

describe('useAppCommands', () => {
  it('updates topic editing state via setters', () => {
    const args = createArgs()
    const { result } = renderHook(() => useAppCommands(args))

    act(() => {
      result.current.handleTopicDraftChange('Next topic')
      result.current.handleBeginTopicEditing()
      result.current.handleCancelTopicEdit()
      result.current.handleConfirmTopicEdit()
    })

    expect(args.setTopicDraft).toHaveBeenCalledWith('Next topic')
    expect(args.setTopicDirty).toHaveBeenCalledWith(true)
    expect(args.setTopicFocusActive).toHaveBeenCalledWith(true)
    expect(args.setTopicDraft).toHaveBeenCalledWith('Current topic')
    expect(args.setTopic).toHaveBeenCalledWith('Draft topic')
    expect(args.setTopicFocusActive).toHaveBeenLastCalledWith(false)
  })

  it('sends exact websocket envelopes for session and participant actions', () => {
    const args = createArgs()
    const { result } = renderHook(() => useAppCommands(args))

    act(() => {
      result.current.handleStartSession()
      result.current.handlePauseSession()
      result.current.handleResumeSession()
      result.current.handleSubmitQuestion('Why?')
      result.current.handleCreateParticipant({ id: 'agent-2' }, true)
      result.current.handleAddFromInventory(['profile-1'])
      result.current.handleBenchParticipant('agent-1')
      result.current.handleRestoreParticipant('agent-1')
    })

    expect(args.setObserverBusy).toHaveBeenCalledWith(false)
    expect(args.sendMsg).toHaveBeenCalledWith({
      type: 'start_session',
      roomId: 'room-1',
      topic: 'Current topic',
      observerMode: 'suggest',
    })
    expect(args.sendMsg).toHaveBeenCalledWith({ type: 'pause_session' })
    expect(args.sendMsg).toHaveBeenCalledWith({ type: 'resume_session', roomId: 'room-1' })
    expect(args.sendMsg).toHaveBeenCalledWith({ type: 'submit_user_question', content: 'Why?' })
    expect(args.sendMsg).toHaveBeenCalledWith({
      type: 'create_and_add_participant',
      roomId: 'room-1',
      participant: { id: 'agent-2' },
      saveToInventory: true,
    })
    expect(args.sendMsg).toHaveBeenCalledWith({
      type: 'add_participant_from_inventory',
      roomId: 'room-1',
      profileId: 'profile-1',
    })
    expect(args.sendMsg).toHaveBeenCalledWith({ type: 'bench_participant', participantId: 'agent-1' })
    expect(args.sendMsg).toHaveBeenCalledWith({ type: 'restore_participant', participantId: 'agent-1' })
  })

  it('applies snapshots for preset and internet mode actions', async () => {
    const snapshot = { room: { id: 'room-1', name: 'Room' } }
    const args = createArgs({
      apiJson: vi.fn()
        .mockResolvedValueOnce(snapshot)
        .mockResolvedValueOnce(snapshot),
    })
    const { result } = renderHook(() => useAppCommands(args))

    await act(async () => {
      await result.current.handleApplyTeamPreset('preset-1')
      await result.current.handleInternetModeChange('auto')
    })

    expect(args.apiJson).toHaveBeenNthCalledWith(1, '/api/team-presets/preset-1/apply', {
      method: 'POST',
      body: JSON.stringify({ roomId: 'room-1' }),
    })
    expect(args.apiJson).toHaveBeenNthCalledWith(2, '/api/rooms/room-1', {
      method: 'PATCH',
      body: JSON.stringify({ internetMode: 'auto' }),
    })
    expect(args.applyRoomSnapshot).toHaveBeenCalledTimes(2)
    expect(args.applyRoomSnapshot).toHaveBeenCalledWith(snapshot)
  })

  it('manages report generation state on success and failure', async () => {
    const okArgs = createArgs({
      apiJson: vi.fn().mockResolvedValue({ report: { markdown: '# Done' } }),
    })
    const { result: successResult } = renderHook(() => useAppCommands(okArgs))

    await act(async () => {
      await successResult.current.handleGenerateReport()
    })

    expect(okArgs.setReportGenerating).toHaveBeenCalledWith(true)
    expect(okArgs.setReportProgress).toHaveBeenCalledWith(5)
    expect(okArgs.setReportError).toHaveBeenCalledWith('')
    expect(okArgs.setReport).toHaveBeenCalledWith({ markdown: '# Done' })

    const badArgs = createArgs({
      apiJson: vi.fn().mockRejectedValue(new Error('boom')),
    })
    const { result: failureResult } = renderHook(() => useAppCommands(badArgs))

    await act(async () => {
      await failureResult.current.handleGenerateReport()
    })

    expect(badArgs.setReportGenerating).toHaveBeenCalledWith(false)
    expect(badArgs.setReportProgress).toHaveBeenCalledWith(0)
    expect(badArgs.setReportError).toHaveBeenCalledWith('boom')
  })

  it('manages fact check state on success and failure', async () => {
    const okArgs = createArgs({
      apiJson: vi.fn().mockResolvedValue({ factCheck: { status: 'completed' } }),
    })
    const { result: successResult } = renderHook(() => useAppCommands(okArgs))

    await act(async () => {
      await successResult.current.handleRunFactCheck('round')
    })

    expect(okArgs.setFactCheckError).toHaveBeenCalledWith('')
    expect(okArgs.setFactCheck).toHaveBeenCalledWith({ status: 'completed' })

    const badArgs = createArgs({
      apiJson: vi.fn().mockRejectedValue(new Error('fact failed')),
    })
    const { result: failureResult } = renderHook(() => useAppCommands(badArgs))

    await act(async () => {
      await failureResult.current.handleRunFactCheck('session')
    })

    expect(badArgs.setFactCheckError).toHaveBeenCalledWith('fact failed')
  })
})
