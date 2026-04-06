import React, { useState } from 'react'

export default function RoomsDrawer({
  open,
  rooms,
  currentRoomId,
  onClose,
  onLoadRoom,
  onCreateRoom,
  onRenameRoom,
  onDeleteRoom,
}) {
  const [newRoomName, setNewRoomName] = useState('')

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
                  <button className="pixel-btn ghost" onClick={() => requestRename(room)}>
                    Переименовать
                  </button>
                  <button className="pixel-btn danger" onClick={() => requestDelete(room)}>
                    Удалить
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </aside>
    </div>
  )
}
