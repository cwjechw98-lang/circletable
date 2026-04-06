import React, { useMemo } from 'react'
import Mascot from './Mascot.jsx'
import SpeechBubble from './SpeechBubble.jsx'

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
  const positions = useMemo(
    () => agents.map((_, i) => agentPosition(i, agents.length)),
    [agents.length],
  )

  return (
    <div className="round-table-container">
      <div className="table-circle">
        {/* Central table */}
        <div className="table-surface">
          <div className="table-label">Тема</div>
          <div className="table-topic">
            {topic || 'Тема появится после запуска'}
          </div>
        </div>

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
