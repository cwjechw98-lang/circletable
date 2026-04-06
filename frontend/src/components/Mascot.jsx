import React, { useMemo } from 'react'
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

export default function Mascot({ agent, emotion = 'neutral', isThinking, isSpeaking }) {
  const def = MASCOT_DEFS[agent.mascot] || MASCOT_DEFS.wizard
  const displayEmoji = agent.emoji || def.emoji

  // Determine CSS class for animation
  let animClass = ''
  if (isThinking && !isSpeaking) animClass = 'thinking'
  else if (isSpeaking) animClass = 'speaking'
  else if (emotion && emotion !== 'neutral') animClass = emotion

  const particles = EMOTION_PARTICLES[emotion] || []

  const borderStyle = {
    borderColor: isSpeaking ? 'var(--green)' : isThinking ? 'var(--cyan)' : def.color,
  }

  return (
    <div className="mascot-wrapper">
      <div className={`mascot ${animClass}`} style={borderStyle}>
        <span role="img" aria-label={MASCOT_LABELS[agent.mascot] || agent.mascot}>
          {displayEmoji}
        </span>

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

      <div className="agent-specialty-label">
        {getSpecialtyLabel(agent.specialty)}
      </div>

      <div className="agent-model-label">
        {agent.provider}/{agent.model.length > 18 ? agent.model.slice(0, 18) + '…' : agent.model}
      </div>
    </div>
  )
}

export { MASCOT_DEFS }
