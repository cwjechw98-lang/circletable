import React, { useEffect, useState } from 'react'

async function apiJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Ошибка запроса: ${response.status}`)
  }
  return response.json()
}

export default function RoomsDrawer({
  open,
  rooms,
  currentRoomId,
  onClose,
  onLoadRoom,
  onSessionSnapshot,
  onCreateRoom,
  onRenameRoom,
  onDeleteRoom,
  onForkSession,
}) {
  const [newRoomName, setNewRoomName] = useState('')
  const [expandedRoomId, setExpandedRoomId] = useState(null)
  const [sessionQuery, setSessionQuery] = useState('')
  const [sessionsByRoom, setSessionsByRoom] = useState({})
  const [loadingRoomId, setLoadingRoomId] = useState(null)

  useEffect(() => {
    if (!open || !expandedRoomId) {
      return
    }
    const handle = window.setTimeout(() => {
      loadSessions(expandedRoomId, sessionQuery)
    }, 180)
    return () => window.clearTimeout(handle)
  }, [expandedRoomId, open, sessionQuery])

  if (!open) {
    return null
  }

  function handleCreate() {
    const trimmed = newRoomName.trim()
    if (!trimmed) return
    onCreateRoom(trimmed)
    setNewRoomName('')
  }

  function requestRename(room) {
    const nextName = window.prompt('Новое имя комнаты', room.name)
    if (nextName && nextName.trim() && nextName.trim() !== room.name) {
      onRenameRoom(room.id, nextName.trim())
    }
  }

  function requestDelete(room) {
    if (window.confirm(`Удалить комнату «${room.name}»?`)) {
      onDeleteRoom(room.id)
    }
  }

  async function loadSessions(roomId, query = '') {
    setLoadingRoomId(roomId)
    try {
      const params = new URLSearchParams()
      if (query.trim()) {
        params.set('query', query.trim())
      }
      const suffix = params.toString() ? `?${params}` : ''
      const data = await apiJson(`/api/rooms/${roomId}/sessions${suffix}`)
      setSessionsByRoom((current) => ({ ...current, [roomId]: data.sessions || [] }))
    } catch (error) {
      console.error(error)
    } finally {
      setLoadingRoomId(null)
    }
  }

  async function toggleSessions(roomId) {
    const nextRoomId = expandedRoomId === roomId ? null : roomId
    setExpandedRoomId(nextRoomId)
    setSessionQuery('')
    if (nextRoomId) {
      await loadSessions(nextRoomId)
    }
  }

  async function openSession(sessionId) {
    try {
      const snapshot = await apiJson(`/api/sessions/${sessionId}/open`, { method: 'POST' })
      onSessionSnapshot(snapshot)
    } catch (error) {
      console.error(error)
    }
  }

  async function continueSession(sessionId) {
    try {
      const snapshot = await apiJson(`/api/sessions/${sessionId}/continue`, { method: 'POST' })
      onSessionSnapshot(snapshot)
      onClose()
    } catch (error) {
      console.error(error)
      window.alert('Не удалось продолжить сессию. Возможно, уже идёт другой диалог.')
    }
  }

  async function renameSession(session) {
    const currentTitle = session.title || session.topic || 'Диалог'
    const nextTitle = window.prompt('Новое имя диалога', currentTitle)
    if (!nextTitle || !nextTitle.trim()) {
      return
    }
    try {
      const snapshot = await apiJson(`/api/sessions/${session.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ title: nextTitle.trim() }),
      })
      onSessionSnapshot(snapshot)
      if (expandedRoomId) {
        await loadSessions(expandedRoomId, sessionQuery)
      }
    } catch (error) {
      console.error(error)
    }
  }

  async function deleteSession(session) {
    const title = session.title || session.topic || 'диалог'
    if (!window.confirm(`Удалить диалог «${title}»?`)) {
      return
    }
    try {
      await apiJson(`/api/sessions/${session.id}`, { method: 'DELETE' })
      if (expandedRoomId) {
        await loadSessions(expandedRoomId, sessionQuery)
      }
    } catch (error) {
      console.error(error)
      window.alert('Не удалось удалить диалог. Возможно, он сейчас выполняется.')
    }
  }

  function exportSession(sessionId) {
    window.location.href = `/api/sessions/${sessionId}/export.md`
  }

  return (
    <div className="drawer-shell" onClick={onClose}>
      <aside className="drawer drawer-left" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <div className="drawer-kicker">Комнаты</div>
            <div className="drawer-title">Список переговорных</div>
          </div>
          <button className="drawer-close" onClick={onClose}>×</button>
        </div>

        <div className="drawer-create-row">
          <input
            className="drawer-input"
            value={newRoomName}
            onChange={(event) => setNewRoomName(event.target.value)}
            placeholder="Имя новой комнаты"
            onKeyDown={(event) => event.key === 'Enter' && handleCreate()}
          />
          <button className="pixel-btn add" onClick={handleCreate}>+ Создать</button>
        </div>

        <div className="room-list">
          {rooms.length === 0 && (
            <div className="drawer-empty">Комнат пока нет. Создайте первую и соберите состав.</div>
          )}

          {rooms.map((room) => {
            const latest = room.latestSession
            const isCurrent = room.id === currentRoomId
            return (
              <div key={room.id} className={`room-card${isCurrent ? ' is-current' : ''}`}>
                <div className="room-card-top">
                  <div>
                    <div className="room-card-name">{room.name}</div>
                    <div className="room-card-meta">
                      {latest?.topic || room.lastTopic || 'Пока без темы'}
                    </div>
                  </div>
                  {isCurrent && <span className="room-badge">Открыта</span>}
                </div>

                <div className="room-card-stats">
                  <span>За столом: {room.activeCount}</span>
                  <span>Скамейка: {room.benchedCount}</span>
                  <span>Режим: {room.observerMode === 'manual' ? 'Бесконечный' : room.observerMode === 'auto' ? 'Автофинал' : 'С подсказками'}</span>
                </div>

                {room.summary && (
                  <div className="room-card-summary">{room.summary}</div>
                )}

                <div className="room-card-actions">
                  <button className="pixel-btn ghost" onClick={() => onLoadRoom(room.id)}>
                    {isCurrent ? 'Обновить' : 'Открыть'}
                  </button>
                  <button className="pixel-btn ghost" onClick={() => toggleSessions(room.id)}>
                    {expandedRoomId === room.id ? 'Скрыть диалоги' : 'Диалоги'}
                  </button>
                  <button className="pixel-btn ghost" onClick={() => requestRename(room)}>
                    Переименовать
                  </button>
                  <button className="pixel-btn danger" onClick={() => requestDelete(room)}>
                    Удалить
                  </button>
                </div>

                {expandedRoomId === room.id && (
                  <div className="session-archive">
                    <input
                      className="drawer-input"
                      value={sessionQuery}
                      onChange={(event) => setSessionQuery(event.target.value)}
                      placeholder="Поиск по диалогам"
                    />

                    {loadingRoomId === room.id && (
                      <div className="drawer-empty">Загружаю диалоги...</div>
                    )}

                    {(sessionsByRoom[room.id] || []).length === 0 && loadingRoomId !== room.id && (
                      <div className="drawer-empty">В этой комнате пока нет сохранённых диалогов.</div>
                    )}

                    {(sessionsByRoom[room.id] || []).map((session) => (
                      <div key={session.id} className="session-card">
                        <div className="session-card-top">
                          <div>
                            <div className="session-card-title">
                              {session.title || `Диалог от ${new Date(session.createdAt).toLocaleString('ru-RU')}`}
                            </div>
                            <div className="session-card-topic">{session.topic}</div>
                          </div>
                          <span className="room-badge">
                            {session.status === 'completed'
                              ? 'Завершена'
                              : session.status === 'stopped'
                                ? 'Остановлена'
                                : session.status === 'paused'
                                  ? 'Пауза'
                                  : 'Активна'}
                          </span>
                        </div>

                        <div className="room-card-stats">
                          <span>Раундов: {session.lastRoundNumber}</span>
                          <span>Сообщений: {session.messageCount}</span>
                          <span>{new Date(session.updatedAt).toLocaleString('ru-RU')}</span>
                        </div>

                        {session.preview && (
                          <div className="session-preview">{session.preview}</div>
                        )}

                        <div className="room-card-actions">
                          <button className="pixel-btn ghost" onClick={() => openSession(session.id)}>Читать</button>
                          <button className="pixel-btn start" onClick={() => continueSession(session.id)}>Продолжить</button>
                          <button className="pixel-btn ghost" onClick={() => onForkSession?.(session.id)}>От финала</button>
                          <button className="pixel-btn ghost" onClick={() => renameSession(session)}>Переименовать</button>
                          <button className="pixel-btn ghost" onClick={() => exportSession(session.id)}>Экспорт .md</button>
                          <button className="pixel-btn danger" onClick={() => deleteSession(session)}>Удалить</button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </aside>
    </div>
  )
}
