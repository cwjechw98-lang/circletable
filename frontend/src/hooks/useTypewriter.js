import { useState, useEffect, useRef } from 'react'

/**
 * Typewriter effect with a steady visual pace.
 * Incoming tokens may arrive in bursts, but the reveal stays smooth.
 */
export function useTypewriter(text, speed = 24) {
  const [displayed, setDisplayed] = useState('')
  const indexRef = useRef(0)
  const targetRef = useRef('')
  const tickRef = useRef(0)
  const rafRef = useRef(0)

  useEffect(() => {
    if (!text) {
      setDisplayed('')
      indexRef.current = 0
      targetRef.current = ''
      tickRef.current = 0
      cancelAnimationFrame(rafRef.current)
      return
    }

    if (!text.startsWith(targetRef.current)) {
      indexRef.current = 0
      setDisplayed('')
    }
    targetRef.current = text

    const tick = (now) => {
      if (!tickRef.current) {
        tickRef.current = now
      }

      const target = targetRef.current
      const elapsed = now - tickRef.current
      const charsToAdd = Math.floor(elapsed / Math.max(12, speed))

      if (indexRef.current < target.length) {
        if (charsToAdd > 0) {
          indexRef.current = Math.min(target.length, indexRef.current + charsToAdd)
          setDisplayed(target.slice(0, indexRef.current))
          tickRef.current = now
        }
        rafRef.current = requestAnimationFrame(tick)
        return
      }

      tickRef.current = now
      rafRef.current = requestAnimationFrame(tick)
    }

    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(rafRef.current)
    }
  }, [text, speed])

  return { displayed, done: displayed.length >= text.length }
}
