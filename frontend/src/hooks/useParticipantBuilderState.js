import { useEffect, useMemo, useState } from 'react'
import { MASCOT_DEFS } from '../components/Mascot.jsx'
import { mergeSpecialtyGroups } from '../constants/specialties.js'
import { getModelOptions, isEmbeddingModel, pickPreferredModel } from '../constants/models.js'

export default function useParticipantBuilderState({
  providers,
  customSpecialtyGroups = [],
  onCreateParticipant,
}) {
  const [newName, setNewName] = useState('')
  const [newRole, setNewRole] = useState('critic')
  const [newSpecialty, setNewSpecialty] = useState('digital-generalist')
  const [newProvider, setNewProvider] = useState('ollama')
  const [newModel, setNewModel] = useState('')
  const [newMascot, setNewMascot] = useState('wizard')
  const [saveToInventory, setSaveToInventory] = useState(true)

  const specialtyGroups = useMemo(
    () => mergeSpecialtyGroups(customSpecialtyGroups),
    [customSpecialtyGroups],
  )

  const availableProviders = useMemo(
    () => Object.entries(providers).filter(([, value]) => value.available).map(([key]) => key),
    [providers],
  )

  const providerModels = useMemo(
    () => getModelOptions(newProvider, providers),
    [newProvider, providers],
  )

  useEffect(() => {
    if (availableProviders.length > 0 && !availableProviders.includes(newProvider)) {
      setNewProvider(availableProviders[0])
    }
  }, [availableProviders, newProvider])

  useEffect(() => {
    const values = new Set(specialtyGroups.flatMap((group) => group.options.map((option) => option.value)))
    if (!values.has(newSpecialty)) {
      setNewSpecialty('digital-generalist')
    }
  }, [newSpecialty, specialtyGroups])

  useEffect(() => {
    if (providerModels.length === 0) {
      return
    }

    if (!newModel || !providerModels.includes(newModel) || isEmbeddingModel(newModel)) {
      setNewModel(pickPreferredModel(newProvider, providerModels))
    }
  }, [newModel, newProvider, providerModels])

  function createParticipant() {
    const trimmed = newName.trim()
    if (!trimmed) return
    const chosenModel = newModel || pickPreferredModel(newProvider, providers)
    onCreateParticipant?.({
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
      const chosenModel = draft.model || newModel || pickPreferredModel(draftProvider, providers)
      onCreateParticipant?.({
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

  return {
    participantBuilderProps: {
      name: newName,
      role: newRole,
      specialty: newSpecialty,
      provider: newProvider,
      model: newModel,
      mascot: newMascot,
      saveToInventory,
      specialtyGroups,
      availableProviders,
      providerModels,
      onNameChange: setNewName,
      onRoleChange: setNewRole,
      onSpecialtyChange: setNewSpecialty,
      onProviderChange: setNewProvider,
      onModelChange: setNewModel,
      onMascotChange: setNewMascot,
      onSaveToInventoryChange: setSaveToInventory,
      onCreateParticipant: createParticipant,
    },
    selectedProvider: newProvider,
    selectedModel: newModel,
    availableProviders,
    specialtyGroups,
    setSelectedSpecialty: setNewSpecialty,
    createAssistantParticipants,
  }
}
