import React, { useCallback, useEffect, useRef, useState } from 'react'
import RoundTable from './components/RoundTable.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import ControlPanel from './components/ControlPanel.jsx'
import RoundAnnounce from './components/RoundAnnounce.jsx'
import RoomsDrawer from './components/RoomsDrawer.jsx'
import InventoryDrawer from './components/InventoryDrawer.jsx'
import TimedHintLayer from './components/TimedHintLayer.jsx'
import { useWebSocket } from './hooks/useWebSocket.js'

async function apiJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Ошибка запроса: ${response.status}`)
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
const SLOW_THINKING_MS = 10000

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

export default function App() {
  const [connected, setConnected] = useState(false)
  const [shuttingDown, setShuttingDown] = useState(false)
  const [providers, setProviders] = useState({})
  const [rooms, setRooms] = useState([])
  const [currentRoomId, setCurrentRoomId] = useState(null)
  const [room, setRoom] = useState(null)
  const [participants, setParticipants] = useState({ active: [], benched: [] })
  const [inventory, setInventory] = useState([])
  const [teamPresets, setTeamPresets] = useState([])
  const [messages, setMessages] = useState([])
  const [pinnedMessages, setPinnedMessages] = useState([])
  const [observerReviews, setObserverReviews] = useState([])
  const [session, setSession] = useState(null)
  const [sessionState, setSessionState] = useState('idle')
  const [topic, setTopic] = useState('')
  const [refreshingProviders, setRefreshingProviders] = useState(false)
  const [roomsOpen, setRoomsOpen] = useState(false)
  const [inventoryOpen, setInventoryOpen] = useState(false)
  const [observerBusy, setObserverBusy] = useState(false)
  const [observerSuggestion, setObserverSuggestion] = useState(null)
  const [theme, setTheme] = useState(readTheme)
  const [uiFontScale, setUiFontScale] = useState(readUiFontScale)
  const [fontPanelOpen, setFontPanelOpen] = useState(false)
  const [chatPanelWidth, setChatPanelWidth] = useState(readChatPanelWidth)
  const [chatResizeActive, setChatResizeActive] = useState(false)
  const [responseMetrics, setResponseMetrics] = useState({})
  const [slowThinkingSet, setSlowThinkingSet] = useState(new Set())

  const [thinkingSet, setThinkingSet] = useState(new Set())
  const [speakingSet, setSpeakingSet] = useState(new Set())
  const [streamTexts, setStreamTexts] = useState({})
  const [emotions, setEmotions] = useState({})
  const [announce, setAnnounce] = useState(null)

  const processedEventsRef = useRef(new Set())
  const chatResizeRef = useRef(null)
  const responseTimingRef = useRef({})
  const activeParticipantsRef = useRef([])

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

  const applyRoomSnapshot = useCallback((payload) => {
    if (payload.rooms) {
      setRooms(payload.rooms)
    }
    if (payload.currentRoomId !== undefined) {
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
    if (payload.session !== undefined) {
      setSession(payload.session)
      if (payload.session?.status) {
        setSessionState(payload.session.status)
      } else if (!payload.session) {
        setSessionState('idle')
      }
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

    const nextTopic = payload.session?.topic || payload.room?.lastTopic || ''
    if (nextTopic) {
      setTopic(nextTopic)
    }
  }, [])

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
        setShuttingDown(false)
        setRefreshingProviders(false)
        break

      case 'init':
        resetResponseMetrics()
        setRefreshingProviders(false)
        setProviders(data.providers || {})
        setRooms(data.rooms || [])
        setCurrentRoomId(data.currentRoomId || null)
        if (data.roomSnapshot) {
          applyRoomSnapshot(data.roomSnapshot)
        }
        if (data.sessionState) {
          setSessionState(data.sessionState.state || data.sessionState.session?.status || 'idle')
          setSession(data.sessionState.session || null)
        }
        break

      case 'providers':
        setRefreshingProviders(false)
        setProviders(data.providers || {})
        break

      case 'room_loaded':
        resetResponseMetrics()
        applyRoomSnapshot(data)
        break

      case 'session_state':
        setSessionState(data.state || data.session?.status || 'idle')
        if (data.session) {
          setSession(data.session)
        }
        break

      case 'pause_requested':
        setSessionState('pause_requested')
        break

      case 'paused':
        setSessionState('paused')
        break

      case 'resumed':
        setSessionState('running')
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

      case 'session_final_summary':
        if (data.summary) {
          setObserverSuggestion({
            recommendation: 'complete',
            summary: data.summary,
            suggestedRoundsLeft: 0,
          })
        }
        break

      case 'reset':
        resetResponseMetrics()
        setSession(null)
        setSessionState('idle')
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
        setShuttingDown(true)
        setMessages((prev) => [...prev, {
          id: data.event_id || `shutdown-${Date.now()}`,
          type: 'status',
          content: data.message || 'Сеанс сохраняется и приложение завершает работу.',
        }])
        break

      default:
        break
    }
  }, [applyRoomSnapshot, finishResponseWatch, resetResponseMetrics, startResponseWatch])

  const { send } = useWebSocket(handleWsMessage)

  const activeParticipants = participants.active || []
  const benchedParticipants = participants.benched || []
  const latestObserverReview = observerReviews[0] || null
  const headerMode = normalizeMode(room?.observerMode)

  useEffect(() => {
    activeParticipantsRef.current = activeParticipants
  }, [activeParticipants])

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
            models: {
              [signature]: emptyMetric,
            },
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
            models: {
              ...existing.models,
              [signature]: normalizedEntry,
            },
            trendText: buildModelChangeText(
              previousEntry,
              existing.currentLabel,
              normalizedEntry,
              label,
            ),
          }
        }
      })

      return changed ? next : current
    })
  }, [activeParticipants])

  function handleThemeChange(nextTheme) {
    setTheme(nextTheme)
    localStorage.setItem('circletable-theme', nextTheme)
  }

  async function handleCreateRoom(name) {
    try {
      await apiJson('/api/rooms', {
        method: 'POST',
        body: JSON.stringify({ name }),
      })
    } catch (error) {
      console.error(error)
    }
  }

  async function handleRenameRoom(roomId, name) {
    try {
      await apiJson(`/api/rooms/${roomId}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      })
    } catch (error) {
      console.error(error)
    }
  }

  async function handleDeleteRoom(roomId) {
    try {
      await apiJson(`/api/rooms/${roomId}`, { method: 'DELETE' })
    } catch (error) {
      console.error(error)
    }
  }

  async function handleSaveParticipant(participant) {
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
        await apiJson(`/api/characters/${participant.profileId}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        })
      } else {
        await apiJson('/api/characters', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
      }
    } catch (error) {
      console.error(error)
    }
  }

  async function handleDeleteProfile(profileId) {
    try {
      await apiJson(`/api/characters/${profileId}`, { method: 'DELETE' })
    } catch (error) {
      console.error(error)
    }
  }

  async function handleShutdownApp() {
    if (shuttingDown) {
      return
    }

    setShuttingDown(true)
    try {
      await apiJson('/api/system/shutdown', { method: 'POST' })
    } catch (error) {
      console.error(error)
      setShuttingDown(false)
    }
  }

  function handleStartSession() {
    send({
      type: 'start_session',
      roomId: currentRoomId,
      topic,
      observerMode: room?.observerMode || 'suggest',
    })
  }

  function handleCreateParticipant(participant, saveToInventory) {
    send({
      type: 'create_and_add_participant',
      roomId: currentRoomId,
      participant,
      saveToInventory,
    })
  }

  function handleAddFromInventory(profileIds) {
    profileIds.forEach((profileId) => {
      send({
        type: 'add_participant_from_inventory',
        roomId: currentRoomId,
        profileId,
      })
    })
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
    chatResizeRef.current = {
      startX: event.clientX,
      startWidth: chatPanelWidth,
    }
    setChatResizeActive(true)
    document.body.classList.add('is-resizing-chat')
    event.preventDefault()
  }

  function resetChatPanelWidth() {
    const next = clampChatPanelWidth(400)
    setChatPanelWidth(next)
    localStorage.setItem(CHAT_PANEL_WIDTH_KEY, String(next))
  }

  async function handleCreateTeamPreset(name) {
    try {
      await apiJson('/api/team-presets', {
        method: 'POST',
        body: JSON.stringify({
          roomId: currentRoomId,
          name,
          participants: activeParticipants,
        }),
      })
    } catch (error) {
      console.error(error)
    }
  }

  async function handleDeleteTeamPreset(presetId) {
    try {
      await apiJson(`/api/team-presets/${presetId}`, {
        method: 'DELETE',
      })
    } catch (error) {
      console.error(error)
    }
  }

  async function handleApplyTeamPreset(presetId) {
    try {
      const snapshot = await apiJson(`/api/team-presets/${presetId}/apply`, {
        method: 'POST',
        body: JSON.stringify({ roomId: currentRoomId }),
      })
      applyRoomSnapshot(snapshot)
    } catch (error) {
      console.error(error)
    }
  }

  async function handleToggleMessagePin(messageId) {
    if (!session?.id || !currentRoomId) return
    try {
      await apiJson(`/api/messages/${messageId}/pin`, {
        method: 'POST',
        body: JSON.stringify({
          roomId: currentRoomId,
          sessionId: session.id,
        }),
      })
    } catch (error) {
      console.error(error)
    }
  }

  useEffect(() => {
    localStorage.setItem(CHAT_PANEL_WIDTH_KEY, String(chatPanelWidth))
  }, [chatPanelWidth])

  useEffect(() => () => {
    Object.values(responseTimingRef.current).forEach((entry) => {
      if (entry?.slowTimer) {
        window.clearTimeout(entry.slowTimer)
      }
    })
  }, [])

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
      className="app"
      data-theme={theme}
      style={{
        '--ui-font-scale': uiFontScale,
        '--chat-panel-width': `${chatPanelWidth}px`,
      }}
    >
      <TimedHintLayer />
      {announce && (
        <RoundAnnounce
          round={announce.round}
          onDone={() => setAnnounce(null)}
        />
      )}

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
        onLoadRoom={(roomId) => send({ type: 'load_room', roomId })}
        onSessionSnapshot={applyRoomSnapshot}
        onCreateRoom={handleCreateRoom}
        onRenameRoom={handleRenameRoom}
        onDeleteRoom={handleDeleteRoom}
        onForkSession={async (sessionId) => {
          try {
            const snapshot = await apiJson(`/api/sessions/${sessionId}/fork`, { method: 'POST' })
            applyRoomSnapshot(snapshot)
          } catch (error) {
            console.error(error)
          }
        }}
      />

      <InventoryDrawer
        open={inventoryOpen}
        activeParticipants={activeParticipants}
        benchedParticipants={benchedParticipants}
        inventory={inventory}
        onClose={() => setInventoryOpen(false)}
        onAddFromInventory={handleAddFromInventory}
        onBenchParticipant={(participantId) => send({ type: 'bench_participant', participantId })}
        onRestoreParticipant={(participantId) => send({ type: 'restore_participant', participantId })}
        onSaveParticipant={handleSaveParticipant}
        onDeleteProfile={handleDeleteProfile}
      />

      <header className="app-header">
        <div>
          <div className="header-title">⚔ Круглый стол ИИ ⚔</div>
          <div className="header-subtitle">
            {room?.name || 'Комната не выбрана'} · {headerMode}
          </div>
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
          topic={topic}
          activeParticipants={activeParticipants}
          connected={connected}
          refreshingProviders={refreshingProviders}
          latestObserverSuggestion={observerSuggestion}
          latestObserverReview={latestObserverReview}
          observerBusy={observerBusy}
          teamPresets={teamPresets}
          onTopicChange={setTopic}
          onStartSession={handleStartSession}
          onPauseSession={() => send({ type: 'pause_session' })}
          onResumeSession={() => send({ type: 'resume_session', roomId: currentRoomId })}
          onStopSession={() => send({ type: 'stop_session' })}
          onRequestWrap={() => send({ type: 'request_wrap' })}
          onRequestFinal={() => send({ type: 'request_final_round' })}
          onOpenRooms={() => setRoomsOpen(true)}
          onOpenInventory={() => setInventoryOpen(true)}
          onRefreshProviders={() => {
            setRefreshingProviders(true)
            send({ type: 'get_providers' })
          }}
          onObserverModeChange={(observerMode) => {
            setRoom((prev) => prev ? { ...prev, observerMode } : prev)
            send({ type: 'observer_mode_changed', roomId: currentRoomId, observerMode })
          }}
          onDensityModeChange={async (densityMode) => {
            try {
              const snapshot = await apiJson(`/api/rooms/${currentRoomId}`, {
                method: 'PATCH',
                body: JSON.stringify({ densityMode }),
              })
              applyRoomSnapshot(snapshot)
            } catch (error) {
              console.error(error)
            }
          }}
          onCreateParticipant={handleCreateParticipant}
          onSubmitQuestion={(content) => send({ type: 'submit_user_question', content })}
          onCreateTeamPreset={handleCreateTeamPreset}
          onApplyTeamPreset={handleApplyTeamPreset}
          onDeleteTeamPreset={handleDeleteTeamPreset}
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

      <ChatPanel messages={messages} pinnedMessages={pinnedMessages} onTogglePin={handleToggleMessagePin} />
    </div>
  )
}
