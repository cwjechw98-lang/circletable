import { useCallback } from 'react'

export default function useAppCommands({
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
  setPreprintGenerating,
}) {
  const handleTopicDraftChange = useCallback((nextTopic) => {
    setTopicDraft(nextTopic)
    setTopicDirty(nextTopic !== topic)
  }, [setTopicDraft, setTopicDirty, topic])

  const handleBeginTopicEditing = useCallback(() => {
    if (!topicEditable) return
    if (topicFocusMode === 'off') return
    setTopicFocusActive(true)
  }, [setTopicFocusActive, topicEditable, topicFocusMode])

  const handleCancelTopicEdit = useCallback(() => {
    setTopicDraft(topic)
    setTopicDirty(false)
    setTopicFocusActive(false)
  }, [setTopicDraft, setTopicDirty, setTopicFocusActive, topic])

  const handleConfirmTopicEdit = useCallback(() => {
    const normalized = topicDraft.trim()
    setTopic(normalized)
    setTopicDraft(normalized)
    setTopicDirty(false)
    setTopicFocusActive(false)
  }, [setTopic, setTopicDraft, setTopicDirty, setTopicFocusActive, topicDraft])

  const handleCreateRoom = useCallback(async (name) => {
    try {
      await apiJson('/api/rooms', { method: 'POST', body: JSON.stringify({ name }) })
    } catch (error) {
      console.error(error)
    }
  }, [apiJson])

  const handleRenameRoom = useCallback(async (roomId, name) => {
    try {
      await apiJson(`/api/rooms/${roomId}`, { method: 'PATCH', body: JSON.stringify({ name }) })
    } catch (error) {
      console.error(error)
    }
  }, [apiJson])

  const handleDeleteRoom = useCallback(async (roomId) => {
    try {
      await apiJson(`/api/rooms/${roomId}`, { method: 'DELETE' })
    } catch (error) {
      console.error(error)
    }
  }, [apiJson])

  const handleSaveParticipant = useCallback(async (participant) => {
    const payload = {
      name: participant.name,
      role: participant.role,
      specialty: participant.specialty,
      provider: participant.provider,
      model: participant.model,
      emoji: participant.emoji,
      mascot: participant.mascot,
      stats: participant.stats,
      strengths: participant.strengths || [],
      weaknesses: participant.weaknesses || [],
      summary: participant.summary || '',
      lastNote: participant.lastNote || '',
    }
    try {
      if (participant.isSavedProfile) {
        await apiJson(`/api/characters/${participant.profileId}`, { method: 'PATCH', body: JSON.stringify(payload) })
      } else {
        await apiJson('/api/characters', { method: 'POST', body: JSON.stringify(payload) })
      }
    } catch (error) {
      console.error(error)
    }
  }, [apiJson])

  const handleDeleteProfile = useCallback(async (profileId) => {
    try {
      await apiJson(`/api/characters/${profileId}`, { method: 'DELETE' })
    } catch (error) {
      console.error(error)
    }
  }, [apiJson])

  const handleLoadRoom = useCallback((roomId) => {
    sendMsg({ type: 'load_room', roomId })
  }, [sendMsg])

  const handleForkSession = useCallback(async (sessionId) => {
    try {
      const snapshot = await apiJson(`/api/sessions/${sessionId}/fork`, { method: 'POST' })
      applyRoomSnapshot(snapshot)
    } catch (error) {
      console.error(error)
    }
  }, [apiJson, applyRoomSnapshot])

  const handleStartSession = useCallback(() => {
    setObserverBusy(false)
    sendMsg({ type: 'start_session', roomId: currentRoomId, topic, observerMode: room?.observerMode || 'suggest' })
  }, [currentRoomId, room?.observerMode, sendMsg, setObserverBusy, topic])

  const handlePauseSession = useCallback(() => {
    sendMsg({ type: 'pause_session' })
  }, [sendMsg])

  const handleResumeSession = useCallback(() => {
    sendMsg({ type: 'resume_session', roomId: currentRoomId })
  }, [currentRoomId, sendMsg])

  const handleStopSession = useCallback(() => {
    sendMsg({ type: 'stop_session' })
  }, [sendMsg])

  const handleRequestWrap = useCallback(() => {
    sendMsg({ type: 'request_wrap' })
  }, [sendMsg])

  const handleRequestFinal = useCallback(() => {
    sendMsg({ type: 'request_final_round' })
  }, [sendMsg])

  const handleCreateParticipant = useCallback((participant, saveToInventory) => {
    sendMsg({ type: 'create_and_add_participant', roomId: currentRoomId, participant, saveToInventory })
  }, [currentRoomId, sendMsg])

  const handleAddFromInventory = useCallback((profileIds) => {
    profileIds.forEach((profileId) => {
      sendMsg({ type: 'add_participant_from_inventory', roomId: currentRoomId, profileId })
    })
  }, [currentRoomId, sendMsg])

  const handleBenchParticipant = useCallback((participantId) => {
    sendMsg({ type: 'bench_participant', participantId })
  }, [sendMsg])

  const handleRestoreParticipant = useCallback((participantId) => {
    sendMsg({ type: 'restore_participant', participantId })
  }, [sendMsg])

  const handleSubmitQuestion = useCallback((content) => {
    sendMsg({ type: 'submit_user_question', content })
  }, [sendMsg])

  const handleCreateTeamPreset = useCallback(async (name) => {
    try {
      await apiJson('/api/team-presets', {
        method: 'POST',
        body: JSON.stringify({ roomId: currentRoomId, name, participants: activeParticipants }),
      })
    } catch (error) {
      console.error(error)
    }
  }, [activeParticipants, apiJson, currentRoomId])

  const handleDeleteTeamPreset = useCallback(async (presetId) => {
    try {
      await apiJson(`/api/team-presets/${presetId}`, { method: 'DELETE' })
    } catch (error) {
      console.error(error)
    }
  }, [apiJson])

  const handleApplyTeamPreset = useCallback(async (presetId) => {
    try {
      const snapshot = await apiJson(`/api/team-presets/${presetId}/apply`, {
        method: 'POST',
        body: JSON.stringify({ roomId: currentRoomId }),
      })
      applyRoomSnapshot(snapshot)
    } catch (error) {
      console.error(error)
    }
  }, [apiJson, applyRoomSnapshot, currentRoomId])

  const handleCreateCustomSpecialty = useCallback(async (payload) => {
    const data = await apiJson('/api/specialties', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    setCustomSpecialtyGroups(data.customSpecialtyGroups || [])
    return data.specialty
  }, [apiJson, setCustomSpecialtyGroups])

  const handleUpdateCustomSpecialty = useCallback(async (specialtyId, changes) => {
    const data = await apiJson(`/api/specialties/${specialtyId}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    })
    setCustomSpecialtyGroups(data.customSpecialtyGroups || [])
    return data.specialty
  }, [apiJson, setCustomSpecialtyGroups])

  const handleDeleteCustomSpecialty = useCallback(async (specialtyId) => {
    const data = await apiJson(`/api/specialties/${specialtyId}`, { method: 'DELETE' })
    setCustomSpecialtyGroups(data.customSpecialtyGroups || [])
  }, [apiJson, setCustomSpecialtyGroups])

  const handleToggleMessagePin = useCallback(async (messageId) => {
    if (!session?.id || !currentRoomId) return
    try {
      await apiJson(`/api/messages/${messageId}/pin`, {
        method: 'POST',
        body: JSON.stringify({ roomId: currentRoomId, sessionId: session.id }),
      })
    } catch (error) {
      console.error(error)
    }
  }, [apiJson, currentRoomId, session?.id])

  const handleInternetModeChange = useCallback(async (internetMode) => {
    if (!currentRoomId) return
    try {
      const snapshot = await apiJson(`/api/rooms/${currentRoomId}`, {
        method: 'PATCH',
        body: JSON.stringify({ internetMode }),
      })
      applyRoomSnapshot(snapshot)
    } catch (error) {
      console.error(error)
    }
  }, [apiJson, applyRoomSnapshot, currentRoomId])

  const handleObserverModeChange = useCallback((observerMode) => {
    setRoom((prev) => (prev ? { ...prev, observerMode } : prev))
    sendMsg({ type: 'observer_mode_changed', roomId: currentRoomId, observerMode })
  }, [currentRoomId, sendMsg, setRoom])

  const handleDensityModeChange = useCallback(async (densityMode) => {
    try {
      const snapshot = await apiJson(`/api/rooms/${currentRoomId}`, {
        method: 'PATCH',
        body: JSON.stringify({ densityMode }),
      })
      applyRoomSnapshot(snapshot)
    } catch (error) {
      console.error(error)
    }
  }, [apiJson, applyRoomSnapshot, currentRoomId])

  const handleGenerateReport = useCallback(async () => {
    if (!session?.id) return
    try {
      setReportGenerating(true)
      setReportProgress(5)
      setReportError('')
      const data = await apiJson(`/api/sessions/${session.id}/report`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      if (data?.report) {
        setReport(data.report)
      }
    } catch (error) {
      setReportGenerating(false)
      setReportProgress(0)
      setReportError(error.message || 'Не удалось создать отчёт.')
    }
  }, [apiJson, session?.id, setReport, setReportError, setReportGenerating, setReportProgress])

  const handleDownloadReport = useCallback(() => {
    if (!report?.markdown || !session?.id) return
    const blob = new Blob([report.markdown], { type: 'text/markdown;charset=utf-8' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `circletable-${session.id}.md`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }, [report?.markdown, session?.id])

  const handleGeneratePreprint = useCallback(async () => {
    if (!session?.id) return
    setPreprintGenerating(true)
    try {
      const data = await apiJson(`/api/preprint/${session.id}`, { method: 'POST', body: JSON.stringify({}) })
      const markdown = data?.markdown
      if (markdown) {
        const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `preprint-${session.id}.md`
        document.body.appendChild(link)
        link.click()
        link.remove()
        window.URL.revokeObjectURL(url)
      }
    } catch (error) {
      console.error('Препринт не удался:', error)
    } finally {
      setPreprintGenerating(false)
    }
  }, [apiJson, session?.id])

  const handleRunFactCheck = useCallback(async (scope) => {
    if (!session?.id) return
    try {
      setFactCheckError('')
      const data = await apiJson(`/api/sessions/${session.id}/fact-check`, {
        method: 'POST',
        body: JSON.stringify({ scope }),
      })
      if (data?.factCheck) {
        setFactCheck(data.factCheck)
      }
    } catch (error) {
      setFactCheckError(error.message || 'Не удалось запустить проверку фактов.')
    }
  }, [apiJson, session?.id, setFactCheck, setFactCheckError])

  const handleCreatePlannedEvent = useCallback(async (event) => {
    if (!currentRoomId) return
    try {
      await apiJson(`/api/rooms/${currentRoomId}/events`, {
        method: 'POST',
        body: JSON.stringify({ ...event, sessionId: session?.id }),
      })
    } catch (error) {
      console.error(error)
    }
  }, [apiJson, currentRoomId, session?.id])

  const handleUpdatePlannedEvent = useCallback(async (eventId, changes) => {
    if (!currentRoomId) return
    try {
      await apiJson(`/api/rooms/${currentRoomId}/events/${eventId}`, {
        method: 'PATCH',
        body: JSON.stringify(changes),
      })
    } catch (error) {
      console.error(error)
    }
  }, [apiJson, currentRoomId])

  const handleDeletePlannedEvent = useCallback(async (eventId) => {
    if (!currentRoomId) return
    try {
      await apiJson(`/api/rooms/${currentRoomId}/events/${eventId}`, { method: 'DELETE' })
    } catch (error) {
      console.error(error)
    }
  }, [apiJson, currentRoomId])

  return {
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
    handleGeneratePreprint,
    handleRunFactCheck,
    handleCreatePlannedEvent,
    handleUpdatePlannedEvent,
    handleDeletePlannedEvent,
  }
}
