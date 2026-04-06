import { useState, useEffect, useRef } from 'react'

/**
 * Typewriter effect for streaming text.
 * When `text` grows (new tokens arrive), displayed text catches up at `speed` ms/char.
 * When `text` changes entirely (reset), starts fresh.
 */
export function useTypewriter(text, speed = 18) {
  const [displayed, setDisplayed] = useState('')
  const indexRef = useRef(0)
  const prevTextRef = useRef('')

  useEffect(() => {
    // Full reset
    if (!text) {
      setDisplayed('')
      indexRef.current = 0
      prevTextRef.current = ''
      return
    }

    // If text grew (streaming), keep catching up
    if (text.startsWith(prevTextRef.current)) {
      prevTextRef.current = text
    } else {
      // Entirely new text
      indexRef.current = 0
      prevTextRef.current = text
    }

    const timer = setInterval(() => {
      if (indexRef.current < text.length) {
        const remaining = text.length - indexRef.current
        const step = remaining > 36 ? 3 : remaining > 18 ? 2 : 1
        indexRef.current = Math.min(text.length, indexRef.current + step)
        setDisplayed(text.slice(0, indexRef.current))
      } else {
        clearInterval(timer)
      }
    }, speed)

    return () => clearInterval(timer)
  }, [text, speed])

  return { displayed, done: displayed.length >= text.length }
}
