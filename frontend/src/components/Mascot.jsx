import React from 'react'
import PixelSprite from './PixelSprite.jsx'
import {
  MASCOT_DEFS,
  MASCOT_LABELS,
  resolveMascot,
} from './mascotData.js'
import { getRoleLabel } from '../constants/roles.js'
import { getSpecialtyLabel } from '../constants/specialties.js'

/**
 * Pixel-art styled mascot with emotions.
 * Each mascot type has a distinct emoji + color theme.
 * Emotions add CSS animations + particle effects.
 */

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
  const mascot = resolveMascot(agent)
  const def = MASCOT_DEFS[mascot] || MASCOT_DEFS.wizard
  const spriteEmotion = isThinking && !isSpeaking
    ? 'thinking'
    : isSpeaking
      ? 'speaking'
      : emotion

  // Determine CSS class for animation
  let animClass = ''
  if (isThinking && !isSpeaking) animClass = 'thinking'
  else if (isSpeaking) animClass = 'speaking'
  else if (emotion && emotion !== 'neutral') animClass = emotion

  const particles = EMOTION_PARTICLES[emotion] || []
  const specialtyLabel = getSpecialtyLabel(agent.specialty, agent.specialtyLabel)
  const roleLabel = getRoleLabel(agent.role)
  const modelLabel = `${agent.provider}/${agent.model.length > 24 ? `${agent.model.slice(0, 24)}…` : agent.model}`
  const hoverLine = `${roleLabel} · ${specialtyLabel} · ${modelLabel}`

  const borderStyle = {
    borderColor: isSpeaking ? 'var(--green)' : isThinking ? 'var(--cyan)' : def.color,
  }

  return (
    <div className="mascot-wrapper">
      <div
        className={`mascot ${animClass}`}
        style={borderStyle}
        role="img"
        aria-label={`${MASCOT_LABELS[mascot] || mascot} — ${agent.name}`}
      >
        <PixelSprite
          mascot={mascot}
          emotion={spriteEmotion}
          size={64}
        />

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

export { MASCOT_DEFS, MASCOT_LABELS, resolveMascot } from './mascotData.js'
