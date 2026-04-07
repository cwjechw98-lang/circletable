import React, { useEffect, useRef, useState } from 'react'
import { useTypewriter } from '../hooks/useTypewriter.js'

/**
 * Dynamic speech bubble with staged appearance and graceful exit.
 */
const DENSITY_CONFIG = {
  calm: { lingerMs: 1700, exitMs: 360, speed: 30 },
  normal: { lingerMs: 1400, exitMs: 320, speed: 24 },
  stage: { lingerMs: 950, exitMs: 220, speed: 18 },
}

export default function SpeechBubble({ text, isThinking, isSpeaking, position, densityMode = 'normal' }) {
  const [storedText, setStoredText] = useState('')
  const [phase, setPhase] = useState('hidden')
  const [pendingClose, setPendingClose] = useState(false)
  const lingerTimerRef = useRef(0)
  const exitTimerRef = useRef(0)
  const density = DENSITY_CONFIG[densityMode] || DENSITY_CONFIG.normal

  useEffect(() => {
    if (text) {
      setStoredText(text)
    }
  }, [text])

  const { displayed, done } = useTypewriter(storedText, density.speed)
  const hasLiveText = Boolean(text)
  const hasStoredText = Boolean(storedText)

  useEffect(() => {
    clearTimeout(lingerTimerRef.current)
    clearTimeout(exitTimerRef.current)

    if (isThinking && !hasLiveText) {
      setStoredText('')
      setPendingClose(false)
      setPhase('thinking')
      return undefined
    }

    if (hasLiveText) {
      setPendingClose(false)
      setPhase('typing')
      return undefined
    }

    if (hasStoredText && !isThinking && !isSpeaking) {
      setPendingClose(true)
      return undefined
    }

    if (!hasStoredText) {
      setPendingClose(false)
      setPhase('hidden')
    }

    return undefined
  }, [hasLiveText, hasStoredText, isSpeaking, isThinking])

  useEffect(() => {
    if (!pendingClose || !hasStoredText || !done) {
      return undefined
    }

    setPhase('linger')
    lingerTimerRef.current = window.setTimeout(() => {
      setPhase('exiting')
      exitTimerRef.current = window.setTimeout(() => {
        setStoredText('')
        setPendingClose(false)
        setPhase('hidden')
      }, density.exitMs)
    }, density.lingerMs)

    return () => {
      clearTimeout(lingerTimerRef.current)
      clearTimeout(exitTimerRef.current)
    }
  }, [density.exitMs, density.lingerMs, done, hasStoredText, pendingClose])

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

  if (phase === 'thinking') {
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

  if (phase === 'hidden' || !storedText) return null

  // Truncate for bubble display
  const maxLen = 150
  const truncated = displayed.length > maxLen
    ? '…' + displayed.slice(-maxLen)
    : displayed

  const phaseClass = phase === 'exiting' ? 'is-exiting' : phase === 'linger' ? 'is-lingering' : ''

  return (
    <div className={`speech-bubble ${placementClass} ${alignClass} ${phaseClass}`.trim()} style={style}>
      <span>{truncated}</span>
      {(phase === 'typing' || !done) && <span className="typewriter-cursor" />}
    </div>
  )
}
