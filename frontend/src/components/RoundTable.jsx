import React, { useMemo, useState } from 'react'
import Mascot from './Mascot.jsx'
import SpeechBubble from './SpeechBubble.jsx'
import { getRoleLabel } from '../constants/roles.js'
import { getSpecialtyLabel } from '../constants/specialties.js'

/**
 * Circular table with agents distributed evenly around it.
 * Uses absolute positioning with CSS transitions for smooth re-seating.
 */

function agentPosition(index, total) {
  const angle = (index * 2 * Math.PI) / Math.max(total, 1) - Math.PI / 2
  const radius = 42 // % from centre
  return {
    x: 50 + radius * Math.cos(angle),
    y: 50 + radius * Math.sin(angle),
  }
}

export default function RoundTable({
  agents,
  topic,
  thinkingSet,
  speakingSet,
  streamTexts,
  emotions,
}) {
  const [infoAgent, setInfoAgent] = useState(null)
  const positions = useMemo(
    () => agents.map((_, i) => agentPosition(i, agents.length)),
    [agents.length],
  )
  const statRows = infoAgent ? [
    ['Инсайт', infoAgent.stats?.insight],
    ['Фокус', infoAgent.stats?.focus],
    ['Глубина', infoAgent.stats?.depth],
    ['Кооперация', infoAgent.stats?.cooperation],
    ['Сцена', infoAgent.stats?.showmanship],
  ] : []

  return (
    <div className="round-table-container">
      <div className="table-circle">
        {/* Central table */}
        <div className="table-surface">
          <div className="table-label">Тема</div>
          <div className="table-topic-mask">
            <div className="table-topic-crawl">
              <span>{topic || 'Тема появится после запуска'}</span>
              <span>{topic || 'Тема появится после запуска'}</span>
            </div>
          </div>
        </div>

        {infoAgent && (
          <div className="table-agent-card">
            <div className="table-agent-card-head">
              <span>{infoAgent.emoji}</span>
              <strong>{infoAgent.name}</strong>
            </div>
            <div className="table-agent-card-line">
              {getRoleLabel(infoAgent.role)} · {getSpecialtyLabel(infoAgent.specialty)}
            </div>
            <div className="table-agent-card-line">
              {infoAgent.provider}/{infoAgent.model}
            </div>
            <div className="table-agent-stats">
              {statRows.map(([label, value]) => (
                <div key={label} className="table-agent-stat">
                  <span>{label}</span>
                  <b>{Number.isFinite(Number(value)) ? Number(value) : 50}</b>
                </div>
              ))}
            </div>
            <div className="table-agent-card-note">
              {infoAgent.lastNote || infoAgent.summary || 'Хрономант ещё не оставил заметку по этому герою.'}
            </div>
          </div>
        )}

        {/* Connector lines from centre to each agent */}
        {agents.map((agent, i) => {
          const pos = positions[i]
          const dx = pos.x - 50
          const dy = pos.y - 50
          const len = Math.sqrt(dx * dx + dy * dy)
          const angle = Math.atan2(dy, dx) * (180 / Math.PI)
          return (
            <div
              key={agent.id + '-line'}
              className="connector-line"
              style={{
                width: `${len}%`,
                transform: `rotate(${angle}deg)`,
              }}
            />
          )
        })}

        {/* Agent seats */}
        {agents.map((agent, i) => {
          const pos = positions[i]
          const isThinking = thinkingSet.has(agent.id)
          const isSpeaking = speakingSet.has(agent.id)
          const emotion = emotions[agent.id] || 'neutral'
          const streamText = streamTexts[agent.id] || ''

          return (
            <div
              key={agent.id}
              className="agent-seat"
              style={{
                left: `${pos.x}%`,
                top: `${pos.y}%`,
              }}
            >
              {/* Speech bubble */}
              {(isThinking || isSpeaking) && (
                <SpeechBubble
                  text={streamText}
                  isThinking={isThinking}
                  position={pos}
                />
              )}

              {/* Mascot character */}
              <Mascot
                agent={agent}
                emotion={emotion}
                isThinking={isThinking}
                isSpeaking={isSpeaking}
              />
              <button
                type="button"
                className="agent-info-btn"
                onMouseEnter={() => setInfoAgent(agent)}
                onMouseLeave={() => setInfoAgent(null)}
                onFocus={() => setInfoAgent(agent)}
                onBlur={() => setInfoAgent(null)}
                aria-label={`Карточка персонажа ${agent.name}`}
                aria-expanded={infoAgent?.id === agent.id}
                title="Показать карточку персонажа"
              >
                i
              </button>
            </div>
          )
        })}

        {/* Empty state */}
        {agents.length === 0 && (
          <div
            style={{
              position: 'absolute',
              top: '50%', left: '50%',
              transform: 'translate(-50%, 80px)',
              textAlign: 'center',
            }}
          >
            <div className="empty-state">
              Добавьте хотя бы двух участников<br />и запустите обсуждение
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
