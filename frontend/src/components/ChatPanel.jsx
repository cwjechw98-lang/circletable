import React, { useEffect, useRef, useState } from 'react'
import { getRoleLabel } from '../constants/roles.js'
import { getSpecialtyLabel } from '../constants/specialties.js'

export default function ChatPanel({ messages }) {
  const endRef = useRef(null)
  const [autoScroll, setAutoScroll] = useState(true)

  useEffect(() => {
    if (autoScroll) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [autoScroll, messages.length])

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <span>Ход беседы</span>
        <button
          type="button"
          className={`chat-scroll-toggle${autoScroll ? ' is-active' : ''}`}
          onClick={() => setAutoScroll((value) => !value)}
          aria-pressed={autoScroll}
          title="Если выключить, новые сообщения не будут уводить чат вниз во время чтения."
        >
          {autoScroll ? 'Автопрокрутка: вкл' : 'Автопрокрутка: выкл'}
        </button>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            {'>'} Сообщения появятся после запуска беседы.<br />
            {'>'} Выберите участников и тему ниже.
          </div>
        )}

        {messages.map((msg, i) => {
          if (msg.type === 'status') {
            return <div key={msg.id || i} className="chat-status">// {msg.content}</div>
          }

          if (msg.type === 'round') {
            return (
              <div key={msg.id || i} className="chat-round-badge">
                ═══ Раунд {msg.round} ═══
              </div>
            )
          }

          if (msg.type === 'user_question') {
            return (
              <div key={msg.id || i} className="chat-user-question">
                <div className="chat-msg-head">
                  <span className="chat-msg-emoji">📝</span>
                  <span className="chat-msg-name">Вы</span>
                  <span className="chat-msg-role">[Вопрос в комнату]</span>
                  {msg.round && <span className="chat-msg-round">Раунд {msg.round}</span>}
                </div>
                <div className="chat-msg-body">{msg.content}</div>
              </div>
            )
          }

          if (msg.type === 'observer_note') {
            return (
              <div key={msg.id || i} className="chat-observer-note">
                <div className="chat-msg-head">
                  <span className="chat-msg-emoji">⏳</span>
                  <span className="chat-msg-name">Хрономант</span>
                  <span className="chat-msg-role">[Наблюдатель стола]</span>
                  {msg.round && <span className="chat-msg-round">Раунд {msg.round}</span>}
                </div>
                <div className="chat-msg-body">{msg.content}</div>
              </div>
            )
          }

          return (
            <div key={msg.id || i} className={`chat-msg${msg.streaming ? ' is-streaming' : ''}`}>
              <div className="chat-msg-head">
                <span className="chat-msg-emoji">{msg.emoji}</span>
                <span className="chat-msg-name">{msg.name}</span>
                <span className="chat-msg-role">
                  [{getRoleLabel(msg.role)} · {getSpecialtyLabel(msg.specialty)}]
                </span>
                {msg.round && (
                  <span className="chat-msg-round">Раунд {msg.round}</span>
                )}
              </div>
              <div className="chat-msg-body">{msg.content}</div>
            </div>
          )
        })}

        <div ref={endRef} />
      </div>
    </div>
  )
}
