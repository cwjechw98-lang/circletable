import React from 'react'
import { getRoleLabel } from '../constants/roles.js'
import { getSpecialtyLabel } from '../constants/specialties.js'

/**
 * Pixel-art styled mascot with emotions.
 * Each mascot type has a distinct emoji + color theme.
 * Emotions add CSS animations + particle effects.
 */

const MASCOT_DEFS = {
  owl:     { emoji: '🦉', color: '#aa44ff' },
  robot:   { emoji: '🤖', color: '#00ff66' },
  cat:     { emoji: '🐱', color: '#4488ff' },
  llama:   { emoji: '🦙', color: '#ff8833' },
  dragon:  { emoji: '🐲', color: '#ff3355' },
  wizard:  { emoji: '🧙', color: '#00f0f0' },
  ghost:   { emoji: '👻', color: '#e0e0e8' },
  crystal: { emoji: '💎', color: '#1abc9c' },
  fox:     { emoji: '🦊', color: '#e67e22' },
  panda:   { emoji: '🐼', color: '#95a5a6' },
  wolf:    { emoji: '🐺', color: '#7f8c8d' },
  tiger:   { emoji: '🐯', color: '#f39c12' },
  frog:    { emoji: '🐸', color: '#2ecc71' },
  octopus: { emoji: '🐙', color: '#9b59b6' },
  alien:   { emoji: '👽', color: '#7bed9f' },
  bat:     { emoji: '🦇', color: '#6c5ce7' },
  bee:     { emoji: '🐝', color: '#f1c40f' },
  eagle:   { emoji: '🦅', color: '#c6a56b' },
  unicorn: { emoji: '🦄', color: '#ff66cc' },
  raccoon: { emoji: '🦝', color: '#a1887f' },
}

const MASCOT_LABELS = {
  owl: 'сова',
  robot: 'робот',
  cat: 'кот',
  llama: 'лама',
  dragon: 'дракон',
  wizard: 'маг',
  ghost: 'призрак',
  crystal: 'кристалл',
  fox: 'лис',
  panda: 'панда',
  wolf: 'волк',
  tiger: 'тигр',
  frog: 'лягушка',
  octopus: 'осьминог',
  alien: 'пришелец',
  bat: 'летучая мышь',
  bee: 'пчела',
  eagle: 'орёл',
  unicorn: 'единорог',
  raccoon: 'енот',
}

const EMOTION_PARTICLES = {
  happy:    ['✨', '⭐'],
  excited:  ['💡', '🔥', '✨'],
  laughing: ['😄', '😂'],
  nervous:  ['💧', '😰'],
  angry:    ['💢', '😤'],
  neutral:  [],
  thinking: ['💭'],
}

export default function Mascot({ agent, emotion = 'neutral', isThinking, isSpeaking, responseMetric, isSlowThinking }) {
  const def = MASCOT_DEFS[agent.mascot] || MASCOT_DEFS.wizard
  const displayEmoji = agent.emoji || def.emoji

  // Determine CSS class for animation
  let animClass = ''
  if (isThinking && !isSpeaking) animClass = 'thinking'
  else if (isSpeaking) animClass = 'speaking'
  else if (emotion && emotion !== 'neutral') animClass = emotion

  const particles = EMOTION_PARTICLES[emotion] || []
  const specialtyLabel = getSpecialtyLabel(agent.specialty)
  const roleLabel = getRoleLabel(agent.role)
  const modelLabel = `${agent.provider}/${agent.model.length > 24 ? `${agent.model.slice(0, 24)}…` : agent.model}`
  const hoverLine = `${roleLabel} · ${specialtyLabel} · ${modelLabel}`

  const borderStyle = {
    borderColor: isSpeaking ? 'var(--green)' : isThinking ? 'var(--cyan)' : def.color,
  }

  return (
    <div className="mascot-wrapper">
      <div className={`mascot ${animClass}`} style={borderStyle}>
        <span role="img" aria-label={MASCOT_LABELS[agent.mascot] || agent.mascot}>
          {displayEmoji}
        </span>

        {isSlowThinking && (
          <div className="mascot-snooze" aria-hidden="true">
            <span>Z</span>
            <span>z</span>
            <span>z</span>
          </div>
        )}

        {responseMetric?.avgSeconds >= 8 && !isSlowThinking && (
          <div className="mascot-latency-chip" aria-hidden="true">
            ⏳
          </div>
        )}

        {/* Emotion particles */}
        {particles.length > 0 && emotion !== 'neutral' && (
          <div className="emotion-particles">
            {particles.map((p, i) => (
              <span
                key={`${emotion}-${i}`}
                className="particle"
                style={{
                  left: `${i * 20 - 10}px`,
                  animationDelay: `${i * 0.3}s`,
                }}
              >
                {p}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="agent-nametag" style={{ borderColor: def.color }}>
        {agent.name}
      </div>

      <div className="agent-hover-ticker" aria-hidden="true">
        <div className="agent-hover-ticker-track">
          <span>{hoverLine}</span>
          <span>{hoverLine}</span>
        </div>
      </div>
    </div>
  )
}

export { MASCOT_DEFS, MASCOT_LABELS }
