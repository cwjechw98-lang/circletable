import React, { useRef, useEffect, useMemo } from 'react'
import { MASCOT_DEFS, getMascotVisualMode } from './mascotData.js'
import { buildSprite, getPalette } from './spriteData.js'

const GRID = 16     // sprite resolution
const SCALE = 4     // each pixel = 4x4 CSS pixels
const SIZE = GRID * SCALE  // 64px canvas

// Animation offsets per emotion (dx, dy pairs for frame cycling)
const ANIM_FRAMES = {
  neutral:  [[0, 0], [0, -1]],
  happy:    [[0, -2], [0, 0], [0, -2], [1, -1]],
  excited:  [[0, -3], [0, 0], [0, -3], [-1, 0]],
  laughing: [[-1, 0], [1, 0], [-1, 0], [1, 0]],
  nervous:  [[-1, 0], [1, 0], [-1, 0], [0, 0]],
  angry:    [[0, 0], [0, -1], [0, 0], [0, 1]],
  thinking: [[0, 0], [0, -1], [0, -2], [0, -1]],
  speaking: [[0, 0], [0, -1], [0, 0], [0, 1]],
}

/**
 * Canvas-based 8-bit pixel sprite renderer with emotion animations.
 *
 * Props:
 *   mascot   — mascot type key (e.g. 'owl', 'robot')
 *   emotion  — current emotion state
 *   size     — display size in px (default 64)
 */
export default function PixelSprite({ mascot = 'wizard', emotion = 'neutral', size = SIZE }) {
  const visualMode = getMascotVisualMode(mascot)
  const canvasRef = useRef(null)
  const frameRef = useRef(0)
  const rafRef = useRef(null)
  const lastTickRef = useRef(0)

  const sprite = useMemo(() => buildSprite(mascot, emotion), [mascot, emotion])
  const palette = useMemo(() => getPalette(mascot), [mascot])
  const frames = ANIM_FRAMES[emotion] || ANIM_FRAMES.neutral
  const scale = size / GRID

  if (visualMode === 'emoji') {
    const emoji = MASCOT_DEFS[mascot]?.emoji || MASCOT_DEFS.wizard.emoji
    return (
      <div
        className="pixel-sprite-emoji"
        style={{
          width: size,
          height: size,
          fontSize: Math.round(size * 0.8),
        }}
        aria-hidden="true"
      >
        {emoji}
      </div>
    )
  }

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    ctx.imageSmoothingEnabled = false

    function drawFrame(offset) {
      const [dx, dy] = offset
      ctx.clearRect(0, 0, size, size)

      for (let row = 0; row < GRID; row++) {
        const line = sprite[row] || ''
        for (let col = 0; col < GRID; col++) {
          const ch = line[col]
          if (!ch || ch === '.') continue

          const color = palette[ch]
          if (!color) continue

          ctx.fillStyle = color
          const px = Math.round((col + dx * 0.5) * scale)
          const py = Math.round((row + dy * 0.5) * scale)
          ctx.fillRect(px, py, Math.ceil(scale), Math.ceil(scale))
        }
      }
    }

    let running = true
    const fps = emotion === 'neutral' ? 2 : emotion === 'speaking' ? 6 : 4
    const interval = 1000 / fps

    function tick(now) {
      if (!running) return
      if (now - lastTickRef.current >= interval) {
        lastTickRef.current = now
        const frame = frames[frameRef.current % frames.length]
        drawFrame(frame)
        frameRef.current++
      }
      rafRef.current = requestAnimationFrame(tick)
    }

    // Draw initial frame immediately
    drawFrame(frames[0])
    frameRef.current = 1
    lastTickRef.current = performance.now()
    rafRef.current = requestAnimationFrame(tick)

    return () => {
      running = false
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [sprite, palette, emotion, frames, size, scale])

  // Reset frame counter when emotion changes
  useEffect(() => {
    frameRef.current = 0
  }, [emotion])

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      className="pixel-sprite-canvas"
      style={{
        width: size,
        height: size,
        imageRendering: 'pixelated',
      }}
    />
  )
}

/**
 * Tiny inline sprite for chat avatars (24px).
 */
export function MiniSprite({ mascot = 'wizard', emotion = 'neutral' }) {
  return <PixelSprite mascot={mascot} emotion={emotion} size={24} />
}
