import { useCallback, useEffect, useRef, useState } from 'react'
import { useWebSocket } from './useWebSocket.js'

const SLOW_THINKING_MS = 10000

function buildAgentModelSignature(agent) {
  return `${agent?.provider || 'unknown'}::${agent?.model || 'unknown'}`
}

function buildAgentModelLabel(agent) {
  return `${agent?.provider || '—'}/${agent?.model || '—'}`
}

function createResponseMetricEntry(label = '') {
  return {
    label,
    avgSeconds: 0,
    sampleCount: 0,
    slowCount: 0,
    latestSeconds: 0,
  }
}

function buildModelChangeText(previousEntry, previousLabel, nextEntry, nextLabel) {
  if (!previousLabel || previousLabel === nextLabel) {
    return ''
  }

  if (previousEntry?.sampleCount >= 2 && nextEntry?.sampleCount >= 2) {
    const diff = nextEntry.avgSeconds - previousEntry.avgSeconds
    if (diff <= -1.2) {
      return `После смены модели отвечает быстрее на ${Math.abs(diff).toFixed(1)}с.`
    }
    if (diff >= 1.2) {
      return `После смены модели отвечает медленнее на ${diff.toFixed(1)}с.`
    }
    return 'После смены модели темп почти не изменился.'
  }

  return `Смена модели: ${previousLabel} → ${nextLabel}. Хрономант копит новый темп.`
}

export default function useAppRealtimeState({
  onSocketClosed,
  onProvidersLoaded,
  onShutdownRequested,
}) {
  const [connected, setConnected] = useState(false)
  const [providers, setProviders] = useState({})
  const [rooms, setRooms] = useState([])
  const [currentRoomId, setCurrentRoomId] = useState(null)
  const [room, setRoom] = useState(null)
  const [participants, setParticipants] = useState({ active: [], benched: [] })
  const [inventory, setInventory] = useState([])
  const [teamPresets, setTeamPresets] = useState([])
  const [customSpecialtyGroups, setCustomSpecialtyGroups] = useState([])
  const [plannedEvents, setPlannedEvents] = useState([])
  const [messages, setMessages] = useState([])
  const [pinnedMessages, setPinnedMessages] = useState([])
  const [observerReviews, setObserverReviews] = useState([])
  const [report, setReport] = useState(null)
  const [reportGenerating, setReportGenerating] = useState(false)
  const [reportProgress, setReportProgress] = useState(0)
  const [reportError, setReportError] = useState('')
  const [factCheck, setFactCheck] = useState(null)
  const [factCheckError, setFactCheckError] = useState('')
  const [session, setSession] = useState(null)
  const [sessionState, setSessionState] = useState('idle')
  const [topic, setTopic] = useState('')
  const [topicDraft, setTopicDraft] = useState('')
  const [topicDirty, setTopicDirty] = useState(false)
  const [topicFocusActive, setTopicFocusActive] = useState(false)
  const [observerBusy, setObserverBusy] = useState(false)
  const [observerSuggestion, setObserverSuggestion] = useState(null)
  const [responseMetrics, setResponseMetrics] = useState({})
  const [slowThinkingSet, setSlowThinkingSet] = useState(new Set())
  const [thinkingSet, setThinkingSet] = useState(new Set())
  const [speakingSet, setSpeakingSet] = useState(new Set())
  const [streamTexts, setStreamTexts] = useState({})
  const [emotions, setEmotions] = useState({})
  const [announce, setAnnounce] = useState(null)
  const [backgroundJobs, setBackgroundJobs] = useState([])

  const processedEventsRef = useRef(new Set())
  const responseTimingRef = useRef({})
  const activeParticipantsRef = useRef([])

  // Фоновые задачи (переиндексация памяти, графы знаний): до 6 последних,
  // активные видны в шапке постоянно, завершённые гаснут сами через 6с.
  function upsertBackgroundJob(job) {
    setBackgroundJobs((prev) => {
      const rest = prev.filter((item) => item.id !== job.id)
      return [{ ...job, at: Date.now() }, ...rest].slice(0, 6)
    })
    if (!job.active) {
      window.setTimeout(() => {
        setBackgroundJobs((prev) => prev.filter((item) => item.id !== job.id))
      }, 6000)
    }
  }
  const currentRoomIdRef = useRef(null)
  const currentSessionIdRef = useRef(null)

  const clearResponseWatch = useCallback((agentId, clearVisual = true) => {
    const current = responseTimingRef.current[agentId]
    if (current?.slowTimer) {
      window.clearTimeout(current.slowTimer)
    }
    delete responseTimingRef.current[agentId]
    if (clearVisual) {
      setSlowThinkingSet((prev) => {
        if (!prev.has(agentId)) return prev
        const next = new Set(prev)
        next.delete(agentId)
        return next
      })
    }
  }, [])

  const startResponseWatch = useCallback((agentId) => {
    clearResponseWatch(agentId, false)
    const agent = activeParticipantsRef.current.find((item) => item.id === agentId)
    const startedAt = Date.now()
    const slowTimer = window.setTimeout(() => {
      setSlowThinkingSet((prev) => {
        if (prev.has(agentId)) return prev
        return new Set([...prev, agentId])
      })
    }, SLOW_THINKING_MS)

    responseTimingRef.current[agentId] = {
      startedAt,
      recorded: false,
      slowTimer,
      signature: buildAgentModelSignature(agent),
      label: buildAgentModelLabel(agent),
    }
  }, [clearResponseWatch])

  const finishResponseWatch = useCallback((agentId) => {
    const current = responseTimingRef.current[agentId]
    if (!current || current.recorded) {
      clearResponseWatch(agentId)
      return
    }

    current.recorded = true
    const elapsedSeconds = Math.max(0.1, (Date.now() - current.startedAt) / 1000)

    setResponseMetrics((prev) => {
      const signature = current.signature || 'unknown::unknown'
      const label = current.label || '—/—'
      const existing = prev[agentId] || {
        currentSignature: signature,
        currentLabel: label,
        currentModelMetric: createResponseMetricEntry(label),
        models: {},
        trendText: '',
      }
      const existingEntry = existing.models[signature] || createResponseMetricEntry(label)
      const sampleCount = existingEntry.sampleCount + 1
      const avgSeconds = ((existingEntry.avgSeconds * existingEntry.sampleCount) + elapsedSeconds) / sampleCount
      const updatedEntry = {
        ...existingEntry,
        label,
        avgSeconds,
        sampleCount,
        slowCount: existingEntry.slowCount + (elapsedSeconds >= SLOW_THINKING_MS / 1000 ? 1 : 0),
        latestSeconds: elapsedSeconds,
      }
      const currentSignature = existing.currentSignature || signature

      return {
        ...prev,
        [agentId]: {
          ...existing,
          currentSignature,
          currentLabel: currentSignature === signature ? label : existing.currentLabel,
          currentModelMetric: currentSignature === signature
            ? updatedEntry
            : existing.currentModelMetric || updatedEntry,
          models: {
            ...existing.models,
            [signature]: updatedEntry,
          },
        },
      }
    })

    clearResponseWatch(agentId)
  }, [clearResponseWatch])

  const resetResponseMetrics = useCallback(() => {
    Object.values(responseTimingRef.current).forEach((entry) => {
      if (entry?.slowTimer) {
        window.clearTimeout(entry.slowTimer)
      }
    })
    responseTimingRef.current = {}
    setResponseMetrics({})
    setSlowThinkingSet(new Set())
  }, [])

  const syncTopicState = useCallback((nextTopic) => {
    const normalized = nextTopic || ''
    setTopic(normalized)
    setTopicDraft(normalized)
    setTopicDirty(false)
    setTopicFocusActive(false)
  }, [])

  const applyRoomSnapshot = useCallback((payload) => {
    if (payload.rooms) {
      setRooms(payload.rooms)
    }
    if (payload.currentRoomId !== undefined) {
      currentRoomIdRef.current = payload.currentRoomId
      setCurrentRoomId(payload.currentRoomId)
    }
    if (payload.room !== undefined) {
      setRoom(payload.room)
    }
    if (payload.participants) {
      setParticipants(payload.participants)
    }
    if (payload.inventory) {
      setInventory(payload.inventory)
    }
    if (payload.teamPresets) {
      setTeamPresets(payload.teamPresets)
    }
    if (payload.customSpecialtyGroups) {
      setCustomSpecialtyGroups(payload.customSpecialtyGroups)
    }
    if (payload.plannedEvents) {
      setPlannedEvents(payload.plannedEvents)
    } else if (payload.session === null) {
      setPlannedEvents([])
    }
    if (payload.session !== undefined) {
      setSession(payload.session)
      if (payload.session?.status) {
        setSessionState(payload.session.status)
        setObserverBusy(payload.session.status === 'observer_review')
      } else if (!payload.session) {
        setSessionState('idle')
        setObserverBusy(false)
      }
    }
    if (payload.report !== undefined) {
      setReport(payload.report)
      if (payload.report) {
        setReportError('')
        setReportGenerating(false)
        setReportProgress(100)
      } else {
        setReportGenerating(false)
        setReportProgress(0)
        setReportError('')
      }
    } else if (payload.session === null) {
      setReport(null)
      setReportGenerating(false)
      setReportProgress(0)
      setReportError('')
    }
    if (payload.factCheck !== undefined) {
      setFactCheck(payload.factCheck)
      if (payload.factCheck) {
        setFactCheckError('')
      }
    } else if (payload.session === null) {
      setFactCheck(null)
      setFactCheckError('')
    }
    if (payload.messages) {
      setMessages(payload.messages)
    }
    if (payload.pinnedMessages) {
      setPinnedMessages(payload.pinnedMessages)
    }
    if (payload.observerReviews) {
      setObserverReviews(payload.observerReviews)
      if (payload.observerReviews.length === 0) {
        setObserverSuggestion(null)
      }
    }

    if (payload.session !== undefined || payload.room !== undefined) {
      const nextTopic = payload.session?.topic || payload.room?.lastTopic || ''
      syncTopicState(nextTopic)
    }
  }, [syncTopicState])

  const handleWsMessage = useCallback((data) => {
    if (data.event_id) {
      if (processedEventsRef.current.has(data.event_id)) {
        return
      }
      processedEventsRef.current.add(data.event_id)
      if (processedEventsRef.current.size > 800) {
        processedEventsRef.current = new Set(Array.from(processedEventsRef.current).slice(-400))
      }
    }

    switch (data.type) {
      case '_ws_open':
        setConnected(true)
        break

      case '_ws_close':
        setConnected(false)
        onSocketClosed?.()
        break

      case 'init':
        resetResponseMetrics()
        onProvidersLoaded?.()
        setProviders(data.providers || {})
        setRooms(data.rooms || [])
        currentRoomIdRef.current = data.currentRoomId || null
        setCurrentRoomId(data.currentRoomId || null)
        setCustomSpecialtyGroups(data.customSpecialtyGroups || [])
        if (data.roomSnapshot) {
          applyRoomSnapshot(data.roomSnapshot)
        }
        if (data.sessionState) {
          setSessionState(data.sessionState.state || data.sessionState.session?.status || 'idle')
          setSession(data.sessionState.session || null)
        }
        break

      case 'providers':
        onProvidersLoaded?.()
        setProviders(data.providers || {})
        break

      case 'room_loaded':
        resetResponseMetrics()
        applyRoomSnapshot(data)
        break

      case 'session_state':
        setSessionState(data.state || data.session?.status || 'idle')
        setObserverBusy((data.state || data.session?.status || 'idle') === 'observer_review')
        if (data.session) {
          setSession(data.session)
        }
        break

      case 'pause_requested':
        setSessionState('pause_requested')
        setObserverBusy(false)
        break

      case 'paused':
        setSessionState('paused')
        setObserverBusy(false)
        break

      case 'resumed':
        setSessionState('running')
        setObserverBusy(false)
        break

      case 'countdown':
        setAnnounce({ round: data.round, seconds: data.seconds })
        break

      case 'round_start':
        setMessages((prev) => [...prev, {
          id: data.event_id || `round-${data.round}`,
          type: 'round',
          round: data.round,
        }])
        break

      case 'agent_thinking':
        startResponseWatch(data.agent_id)
        setThinkingSet((prev) => new Set([...prev, data.agent_id]))
        setSpeakingSet((prev) => {
          const next = new Set(prev)
          next.delete(data.agent_id)
          return next
        })
        setStreamTexts((prev) => ({ ...prev, [data.agent_id]: '' }))
        setEmotions((prev) => ({ ...prev, [data.agent_id]: 'thinking' }))
        break

      case 'agent_token':
        finishResponseWatch(data.agent_id)
        setSpeakingSet((prev) => new Set([...prev, data.agent_id]))
        setThinkingSet((prev) => {
          const next = new Set(prev)
          next.delete(data.agent_id)
          return next
        })
        setStreamTexts((prev) => ({
          ...prev,
          [data.agent_id]: `${prev[data.agent_id] || ''}${data.token}`,
        }))
        break

      case 'agent_message':
      case 'status':
      case 'user_question':
      case 'system_event':
      case 'observer_note':
        if (data.agent_id) {
          finishResponseWatch(data.agent_id)
          setSpeakingSet((prev) => {
            const next = new Set(prev)
            next.delete(data.agent_id)
            return next
          })
          setThinkingSet((prev) => {
            const next = new Set(prev)
            next.delete(data.agent_id)
            return next
          })
          setStreamTexts((prev) => {
            const next = { ...prev }
            delete next[data.agent_id]
            return next
          })
        }
        if (data.emotion && data.agent_id) {
          setEmotions((prev) => ({ ...prev, [data.agent_id]: data.emotion }))
        }
        setMessages((prev) => [...prev, data])
        break

      case 'observer_review_started':
        setObserverBusy(true)
        break

      case 'observer_review_completed':
        setObserverBusy(false)
        if (data.review) {
          setObserverReviews((prev) => [{ roundNumber: data.round, ...data.review }, ...prev].slice(0, 12))
        }
        break

      case 'observer_suggestion':
        setObserverSuggestion(data)
        break

      case 'participant_stats_updated':
        if (data.inventory) {
          setInventory(data.inventory)
        }
        if (data.participants) {
          setParticipants(data.participants)
        }
        break

      case 'team_presets_updated':
        if (data.teamPresets) {
          setTeamPresets(data.teamPresets)
        }
        break

      case 'custom_specialties_updated':
        setCustomSpecialtyGroups(data.customSpecialtyGroups || [])
        break

      case 'planned_events_updated':
        if (!data.roomId || data.roomId === currentRoomIdRef.current) {
          setPlannedEvents(data.plannedEvents || [])
        }
        break

      case 'event_injected':
        if (data.plannedEvents) {
          setPlannedEvents(data.plannedEvents)
        }
        break

      case 'participant_roster_changed':
        if (data.participants) {
          setParticipants(data.participants)
        }
        if (data.inventory) {
          setInventory(data.inventory)
        }
        break

      case 'message_pin_toggled':
        if (data.messages) {
          setMessages(data.messages)
        }
        if (data.pinnedMessages) {
          setPinnedMessages(data.pinnedMessages)
        }
        break

      case 'session_completed':
        setSessionState(data.status || 'completed')
        setObserverBusy(false)
        break

      case 'report_generating':
        if (data.session_id && currentSessionIdRef.current && data.session_id !== currentSessionIdRef.current) {
          break
        }
        setReportGenerating(true)
        setReportProgress(Number(data.progress) || 0)
        setReportError('')
        break

      case 'report_completed':
        if (data.session_id && currentSessionIdRef.current && data.session_id !== currentSessionIdRef.current) {
          break
        }
        setReportGenerating(false)
        setReport((prev) => (
          data.report
            || (data.text
              ? {
                  ...(prev || {}),
                  markdown: data.text,
                  generatedAt: data.generatedAt || prev?.generatedAt,
                  provider: data.provider || prev?.provider,
                  model: data.model || prev?.model,
                }
              : prev)
        ))
        setReportProgress(100)
        break

      case 'report_error':
      case 'report_failed':
        if (data.session_id && currentSessionIdRef.current && data.session_id !== currentSessionIdRef.current) {
          break
        }
        setReportGenerating(false)
        setReportProgress(0)
        setReportError(data.message || 'Не удалось создать отчёт.')
        break

      case 'fact_check_updated':
        if (data.session_id && currentSessionIdRef.current && data.session_id !== currentSessionIdRef.current) {
          break
        }
        setFactCheck(data.factCheck || null)
        setFactCheckError('')
        break

      case 'fact_check_completed':
        if (data.session_id && currentSessionIdRef.current && data.session_id !== currentSessionIdRef.current) {
          break
        }
        setFactCheck(data.factCheck || null)
        setFactCheckError('')
        break

      case 'fact_check_error':
        if (data.session_id && currentSessionIdRef.current && data.session_id !== currentSessionIdRef.current) {
          break
        }
        setFactCheck(data.factCheck || null)
        setFactCheckError(data.message || 'Не удалось завершить проверку фактов.')
        break

      case 'session_final_summary':
        if (data.summary) {
          setObserverSuggestion({
            recommendation: 'complete',
            summary: data.summary,
            suggestedRoundsLeft: 0,
          })
        }
        break

      case 'memory_reindex_progress': {
        const done = data.status === 'done'
        const failed = data.status === 'error'
        upsertBackgroundJob({
          id: `reindex:${data.profileId}`,
          kind: 'memory',
          label: 'Пересборка памяти',
          detail: done
            ? `готово · ${data.processed ?? 0} записей`
            : failed
              ? `ошибка: ${data.error || 'неизвестно'}`
              : `${data.processed ?? 0}/${data.total ?? '?'} записей`,
          status: data.status,
          active: !done && !failed,
        })
        break
      }

      case 'knowledge_graph_started':
      case 'knowledge_graph_updated':
      case 'knowledge_graph_status': {
        if (!data.roomId && !data.graphId) break
        upsertBackgroundJob({
          id: `kg:${data.roomId || data.graphId}`,
          kind: 'kg',
          label: 'Граф знаний',
          detail: data.status === 'building' ? 'строится…' : (data.status || 'обновлён'),
          status: data.status || 'ready',
          active: data.status === 'building',
        })
        break
      }

      case 'knowledge_graph_deleted': {
        upsertBackgroundJob({
          id: `kg:${data.roomId || data.graphId || '*'}`,
          kind: 'kg',
          label: 'Граф знаний',
          detail: 'удалён',
          status: 'deleted',
          active: false,
        })
        break
      }

      case 'reset':
        resetResponseMetrics()
        setSession(null)
        setSessionState('idle')
        setObserverBusy(false)
        setReport(null)
        setReportGenerating(false)
        setReportProgress(0)
        setReportError('')
        setFactCheck(null)
        setFactCheckError('')
        setMessages([])
        setThinkingSet(new Set())
        setSpeakingSet(new Set())
        setStreamTexts({})
        setEmotions({})
        setObserverReviews([])
        setObserverSuggestion(null)
        break

      case 'error':
        setMessages((prev) => [...prev, {
          id: data.event_id || `error-${Date.now()}`,
          type: 'status',
          content: data.message || 'Произошла ошибка.',
        }])
        break

      case 'app_shutdown_requested':
        onShutdownRequested?.()
        setMessages((prev) => [...prev, {
          id: data.event_id || `shutdown-${Date.now()}`,
          type: 'status',
          content: data.message || 'Сеанс сохраняется и приложение завершает работу.',
        }])
        break

      default:
        break
    }
  }, [applyRoomSnapshot, finishResponseWatch, onProvidersLoaded, onSocketClosed, resetResponseMetrics, startResponseWatch])

  const { send: sendMsg } = useWebSocket(handleWsMessage)

  const activeParticipants = participants.active || []
  const benchedParticipants = participants.benched || []
  const latestObserverReview = observerReviews[0] || null
  const effectiveSessionState = session?.status || sessionState
  const topicEditable = !session || ['completed', 'stopped', 'idle'].includes(effectiveSessionState) || effectiveSessionState === 'paused'

  useEffect(() => {
    activeParticipantsRef.current = activeParticipants
  }, [activeParticipants])

  useEffect(() => {
    currentRoomIdRef.current = currentRoomId
  }, [currentRoomId])

  useEffect(() => {
    currentSessionIdRef.current = session?.id || null
  }, [session?.id])

  useEffect(() => {
    if (effectiveSessionState !== 'observer_review') {
      setObserverBusy(false)
    }
  }, [effectiveSessionState])

  useEffect(() => {
    if (!topicEditable) {
      setTopicFocusActive(false)
      setTopicDirty(false)
      setTopicDraft(topic)
    }
  }, [topicEditable, topic])

  useEffect(() => {
    if (activeParticipants.length === 0) {
      return
    }

    setResponseMetrics((current) => {
      let changed = false
      const next = { ...current }

      activeParticipants.forEach((agent) => {
        const signature = buildAgentModelSignature(agent)
        const label = buildAgentModelLabel(agent)
        const existing = current[agent.id]

        if (!existing) {
          changed = true
          const emptyMetric = createResponseMetricEntry(label)
          next[agent.id] = {
            currentSignature: signature,
            currentLabel: label,
            currentModelMetric: emptyMetric,
            models: { [signature]: emptyMetric },
            trendText: '',
          }
          return
        }

        const nextEntry = existing.models[signature] || createResponseMetricEntry(label)
        const normalizedEntry = { ...nextEntry, label }

        if (
          existing.currentSignature !== signature
          || existing.currentLabel !== label
          || !existing.currentModelMetric
          || existing.currentModelMetric.label !== normalizedEntry.label
        ) {
          changed = true
          const previousEntry = existing.models[existing.currentSignature]
          next[agent.id] = {
            ...existing,
            currentSignature: signature,
            currentLabel: label,
            currentModelMetric: normalizedEntry,
            models: { ...existing.models, [signature]: normalizedEntry },
            trendText: buildModelChangeText(previousEntry, existing.currentLabel, normalizedEntry, label),
          }
        }
      })

      return changed ? next : current
    })
  }, [activeParticipants])

  useEffect(() => () => {
    Object.values(responseTimingRef.current).forEach((entry) => {
      if (entry?.slowTimer) window.clearTimeout(entry.slowTimer)
    })
  }, [])

  return {
    state: {
      connection: {
        connected,
      },
      room: {
        providers,
        rooms,
        currentRoomId,
        room,
        participants,
        inventory,
        teamPresets,
        customSpecialtyGroups,
        plannedEvents,
      },
      session: {
        messages,
        pinnedMessages,
        observerReviews,
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
        backgroundJobs,
      },
      derived: {
        activeParticipants,
        benchedParticipants,
        latestObserverReview,
        effectiveSessionState,
        topicEditable,
      },
    },
    actions: {
      applyRoomSnapshot,
      setRoom,
      setCustomSpecialtyGroups,
      setObserverBusy,
      setAnnounce,
      topic: {
        syncTopicState,
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
  }
}
