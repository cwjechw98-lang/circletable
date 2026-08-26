import { useEffect, useState } from 'react'

export default function useBuilderState({
  teamPresets = [],
  activeParticipantsCount = 0,
  editable = false,
  plannedEvents = [],
  sessionLastRoundNumber = 0,
  customSpecialtyGroups = [],
  onCreateTeamPreset,
  onApplyTeamPreset,
  onDeleteTeamPreset,
  onCreateCustomSpecialty,
  onUpdateCustomSpecialty,
  onDeleteCustomSpecialty,
  onCreatePlannedEvent,
  onDeletePlannedEvent,
}) {
  const [presetName, setPresetName] = useState('')
  const [presetPanelOpen, setPresetPanelOpen] = useState(teamPresets.length === 0)
  const [presetPreviewId, setPresetPreviewId] = useState('')
  const [eventsOpen, setEventsOpen] = useState(false)
  const [eventRound, setEventRound] = useState('1')
  const [eventDescription, setEventDescription] = useState('')

  useEffect(() => {
    const nextRound = Number(sessionLastRoundNumber || 0) + 1
    setEventRound(String(Math.max(1, nextRound)))
  }, [sessionLastRoundNumber])

  useEffect(() => {
    if (teamPresets.length === 0) {
      setPresetPanelOpen(true)
      setPresetPreviewId('')
    }
  }, [teamPresets.length])

  function createTeamPreset() {
    const fallbackName = `Состав ${teamPresets.length + 1}`
    onCreateTeamPreset?.(presetName.trim() || fallbackName)
    setPresetName('')
  }

  function togglePresetPreview(presetId) {
    setPresetPreviewId((current) => (current === presetId ? '' : presetId))
  }

  function createPlannedEvent() {
    const description = eventDescription.trim()
    const targetRound = Number(eventRound)
    if (!description || !Number.isFinite(targetRound) || targetRound < 1) {
      return
    }
    onCreatePlannedEvent?.({
      targetRound: Math.floor(targetRound),
      description,
    })
    setEventDescription('')
  }

  return {
    presetsProps: {
      teamPresets,
      presetName,
      presetPanelOpen,
      presetPreviewId,
      editable,
      canSavePreset: activeParticipantsCount > 0,
      onPresetNameChange: setPresetName,
      onToggleOpen: () => setPresetPanelOpen((value) => !value),
      onTogglePreview: togglePresetPreview,
      onSavePreset: createTeamPreset,
      onApplyPreset: onApplyTeamPreset,
      onDeletePreset: onDeleteTeamPreset,
    },
    eventsProps: {
      plannedEvents,
      eventsOpen,
      eventRound,
      eventDescription,
      canCreateEvent: Boolean(eventDescription.trim()),
      onToggleOpen: () => setEventsOpen((value) => !value),
      onEventRoundChange: setEventRound,
      onEventDescriptionChange: setEventDescription,
      onCreateEvent: createPlannedEvent,
      onDeleteEvent: onDeletePlannedEvent,
    },
    customSpecialtiesProps: {
      customSpecialtyGroups,
      onCreateCustomSpecialty,
      onUpdateCustomSpecialty,
      onDeleteCustomSpecialty,
    },
  }
}
