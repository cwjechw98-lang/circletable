import React from 'react'
import { useTypewriter } from '../hooks/useTypewriter.js'

/**
 * Dynamic speech bubble with typewriter effect.
 * Positioned above/beside the mascot based on table position.
 */
export default function SpeechBubble({ text, isThinking, position }) {
  const { displayed, done } = useTypewriter(text, 28)

  // Position bubble to avoid going off-screen
  // If agent is on top half → show below, else above
  const isTop = position.y < 40
  const isLeft = position.x < 40
  const isRight = position.x > 60

  const style = {
    position: 'absolute',
    zIndex: 100,
  }

  if (isTop) {
    style.top = '5rem'
  } else {
    style.bottom = '5.5rem'
  }

  if (isLeft) {
    style.left = '-0.5rem'
  } else if (isRight) {
    style.right = '-0.5rem'
  } else {
    style.left = '50%'
    style.transform = 'translateX(-50%)'
  }

  const placementClass = isTop ? 'bubble-below' : 'bubble-above'
  const alignClass = isLeft ? 'bubble-left' : isRight ? 'bubble-right' : 'bubble-center'

  if (isThinking && !text) {
    return (
      <div className={`speech-bubble is-thinking ${placementClass} ${alignClass}`} style={style}>
        <span className="thinking-dots">
          <span>●</span>
          <span>●</span>
          <span>●</span>
        </span>
      </div>
    )
  }

  if (!text) return null

  // Truncate for bubble display
  const maxLen = 150
  const truncated = displayed.length > maxLen
    ? '…' + displayed.slice(-maxLen)
    : displayed

  return (
    <div className={`speech-bubble ${placementClass} ${alignClass}`} style={style}>
      <span>{truncated}</span>
      {!done && <span className="typewriter-cursor" />}
    </div>
  )
}
