import React, { useCallback, useRef, useState } from 'react'
import RoundTable from './components/RoundTable.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import ControlPanel from './components/ControlPanel.jsx'
import RoundAnnounce from './components/RoundAnnounce.jsx'
import RoomsDrawer from './components/RoomsDrawer.jsx'
import InventoryDrawer from './components/InventoryDrawer.jsx'
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

export default function App() {
  const [connected, setConnected] = useState(false)
  const [shuttingDown, setShuttingDown] = useState(false)
  const [providers, setProviders] = useState({})
  const [rooms, setRooms] = useState([])
  const [currentRoomId, setCurrentRoomId] = useState(null)
  const [room, setRoom] = useState(null)
  const [participants, setParticipants] = useState({ active: [], benched: [] })
  const [inventory, setInventory] = useState([])
  const [messages, setMessages] = useState([])
  const [observerReviews, setObserverReviews] = useState([])
  const [session, setSession] = useState(null)
  const [sessionState, setSessionState] = useState('idle')
  const [topic, setTopic] = useState('')
  const [refreshingProviders, setRefreshingProviders] = useState(false)
  const [roomsOpen, setRoomsOpen] = useState(false)
  const [inventoryOpen, setInventoryOpen] = useState(false)
  const [observerBusy, setObserverBusy] = useState(false)
  const [observerSuggestion, setObserverSuggestion] = useState(null)

  const [thinkingSet, setThinkingSet] = useState(new Set())
  const [speakingSet, setSpeakingSet] = useState(new Set())
  const [streamTexts, setStreamTexts] = useState({})
  const [emotions, setEmotions] = useState({})
  const [announce, setAnnounce] = useState(null)

  const processedEventsRef = useRef(new Set())

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

      case 'participant_roster_changed':
        if (data.participants) {
          setParticipants(data.participants)
        }
        if (data.inventory) {
          setInventory(data.inventory)
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
  }, [applyRoomSnapshot])

  const { send } = useWebSocket(handleWsMessage)

  const activeParticipants = participants.active || []
  const benchedParticipants = participants.benched || []
  const latestObserverReview = observerReviews[0] || null
  const headerMode = normalizeMode(room?.observerMode)

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

  return (
    <div className="app">
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
        onCreateRoom={handleCreateRoom}
        onRenameRoom={handleRenameRoom}
        onDeleteRoom={handleDeleteRoom}
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
          thinkingSet={thinkingSet}
          speakingSet={speakingSet}
          streamTexts={streamTexts}
          emotions={emotions}
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
          onCreateParticipant={handleCreateParticipant}
          onSubmitQuestion={(content) => send({ type: 'submit_user_question', content })}
        />
      </div>

      <ChatPanel messages={messages} />
    </div>
  )
}
