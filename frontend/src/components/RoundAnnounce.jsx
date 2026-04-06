import React, { useState, useEffect } from 'react'

/**
 * Full-screen round announcement with countdown and a short title card.
 */
export default function RoundAnnounce({ round, onDone }) {
  const [count, setCount] = useState(3)
  const [phase, setPhase] = useState('counting') // 'counting' | 'title' | 'exit'

  useEffect(() => {
    if (phase === 'counting') {
      if (count > 0) {
        const t = setTimeout(() => setCount(c => c - 1), 1000)
        return () => clearTimeout(t)
      } else {
        setPhase('title')
      }
    }

    if (phase === 'title') {
      const t = setTimeout(() => setPhase('exit'), 1400)
      return () => clearTimeout(t)
    }

    if (phase === 'exit') {
      const t = setTimeout(() => onDone?.(), 350)
      return () => clearTimeout(t)
    }
  }, [count, phase, onDone])

  if (phase === 'exit') {
    return <div className="round-announce exit" />
  }

  return (
    <div className="round-announce">
      {phase === 'counting' && count > 0 && (
        <div className="countdown-num" key={count}>
          {count}
        </div>
      )}

      {phase === 'title' && (
        <>
          <div className="announce-text">⚔ Раунд {round} ⚔</div>
          <div className="announce-sub">Пусть спор начнётся</div>
        </>
      )}
    </div>
  )
}
