import React from 'react'

export default function PlannedEventsPanel({
  plannedEvents = [],
  eventsOpen,
  eventRound,
  eventDescription,
  canCreateEvent,
  onToggleOpen,
  onEventRoundChange,
  onEventDescriptionChange,
  onCreateEvent,
  onDeleteEvent,
}) {
  return (
    <div className="events-panel">
      <button
        className="pixel-btn ghost events-toggle"
        onClick={onToggleOpen}
        data-hint="Запланировать событие — инъекцию текста, которая будет добавлена в контекст агентов на нужном раунде."
      >
        {eventsOpen ? '▾ Запланированные события' : '▸ Запланированные события'}
        {plannedEvents.length > 0 && <span className="events-badge">{plannedEvents.length}</span>}
      </button>
      {eventsOpen && (
        <div className="events-body">
          <div className="event-create-row">
            <input
              className="mini-input event-round-input"
              type="number"
              min="1"
              value={eventRound}
              onChange={(event) => onEventRoundChange?.(event.target.value)}
              placeholder="Раунд"
              data-hint="Номер раунда, на котором будет внедрено событие."
            />
            <input
              className="mini-input"
              value={eventDescription}
              onChange={(event) => onEventDescriptionChange?.(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && onCreateEvent?.()}
              placeholder="Описание события или новый факт"
              data-hint="Текст события: новость, поворот сюжета, новый факт. Будет добавлен в контекст агентов в указанном раунде."
            />
            <button
              className="pixel-btn add"
              onClick={onCreateEvent}
              disabled={!canCreateEvent}
              data-hint="Добавить запланированное событие."
            >
              +
            </button>
          </div>
          <div className="event-list">
            {plannedEvents.length === 0 && (
              <div className="preset-empty">Нет запланированных событий.</div>
            )}
            {plannedEvents.map((plannedEvent) => (
              <div key={plannedEvent.id} className={`event-card${plannedEvent.injected ? ' is-injected' : ''}`}>
                <div className="event-card-round">Раунд {plannedEvent.targetRound}</div>
                <div className="event-card-desc">{plannedEvent.description}</div>
                {plannedEvent.injected && <div className="event-card-tag">внедрено</div>}
                {!plannedEvent.injected && (
                  <button
                    className="pixel-btn danger event-delete"
                    onClick={() => onDeleteEvent?.(plannedEvent.id)}
                    data-hint="Удалить событие."
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
