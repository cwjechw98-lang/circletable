import React, { useEffect, useRef, useState } from 'react'

const SHOW_DELAY_MS = 420
const TABLE_SHOW_DELAY_MS = 950
const HIDE_AFTER_MS = 3000
const EDGE_PADDING = 18
const VERTICAL_GAP = 14

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function findHintTarget(node) {
  if (!(node instanceof Element)) return null
  return node.closest('[data-hint]')
}

function buildHintState(element, pointerPosition = null) {
  if (!element) return null
  const text = element.getAttribute('data-hint')
  if (!text) return null
  const rect = element.getBoundingClientRect()
  const isTableHint = Boolean(element.closest('.round-table-container'))
  if (isTableHint) {
    const x = pointerPosition?.x ?? rect.left + rect.width / 2
    const y = pointerPosition?.y ?? rect.bottom
    return {
      text,
      x: clamp(x, EDGE_PADDING, window.innerWidth - EDGE_PADDING),
      y: clamp(y + VERTICAL_GAP, EDGE_PADDING, window.innerHeight - EDGE_PADDING),
      placement: 'bottom',
    }
  }
  const showBelow = rect.top < 84
  return {
    text,
    x: clamp(rect.left + rect.width / 2, EDGE_PADDING, window.innerWidth - EDGE_PADDING),
    y: showBelow ? rect.bottom + VERTICAL_GAP : rect.top - VERTICAL_GAP,
    placement: showBelow ? 'bottom' : 'top',
  }
}

export default function TimedHintLayer() {
  const [hint, setHint] = useState(null)
  const [hintPosition, setHintPosition] = useState(null)
  const hintRef = useRef(null)
  const tooltipRef = useRef(null)
  const activeTargetRef = useRef(null)
  const pointerPositionRef = useRef(null)
  const showTimerRef = useRef(null)
  const hideTimerRef = useRef(null)

  useEffect(() => {
    function clearTimers() {
      window.clearTimeout(showTimerRef.current)
      window.clearTimeout(hideTimerRef.current)
      showTimerRef.current = null
      hideTimerRef.current = null
    }

    function hideHint(resetTarget = false) {
      clearTimers()
      hintRef.current = null
      setHint(null)
      setHintPosition(null)
      if (resetTarget) {
        activeTargetRef.current = null
        pointerPositionRef.current = null
      }
    }

    function showHintFor(target) {
      const nextHint = buildHintState(target, pointerPositionRef.current)
      if (!nextHint) return
      hintRef.current = nextHint
      setHint(nextHint)
      hideTimerRef.current = window.setTimeout(() => {
        hintRef.current = null
        setHint(null)
      }, HIDE_AFTER_MS)
    }

    function scheduleHint(target, immediate = false, pointerPosition = null) {
      if (!target || target === activeTargetRef.current) return
      activeTargetRef.current = target
      pointerPositionRef.current = pointerPosition
      clearTimers()
      const delay = immediate
        ? 120
        : target.closest('.round-table-container')
          ? TABLE_SHOW_DELAY_MS
          : SHOW_DELAY_MS
      showTimerRef.current = window.setTimeout(
        () => showHintFor(target),
        delay,
      )
    }

    function handlePointerOver(event) {
      scheduleHint(
        findHintTarget(event.target),
        false,
        { x: event.clientX, y: event.clientY },
      )
    }

    function handlePointerOut(event) {
      const current = activeTargetRef.current
      if (!current) return
      if (findHintTarget(event.relatedTarget) === current) return
      hideHint(true)
    }

    function handleFocusIn(event) {
      scheduleHint(findHintTarget(event.target), true)
    }

    function handleFocusOut(event) {
      const current = activeTargetRef.current
      if (!current) return
      if (findHintTarget(event.relatedTarget) === current) return
      hideHint(true)
    }

    function syncPosition() {
      if (!activeTargetRef.current || !hintRef.current) return
      const nextHint = buildHintState(activeTargetRef.current, pointerPositionRef.current)
      if (nextHint) {
        hintRef.current = nextHint
        setHint(nextHint)
      }
    }

    document.addEventListener('pointerover', handlePointerOver, true)
    document.addEventListener('pointerout', handlePointerOut, true)
    document.addEventListener('focusin', handleFocusIn, true)
    document.addEventListener('focusout', handleFocusOut, true)
    window.addEventListener('scroll', syncPosition, true)
    window.addEventListener('resize', syncPosition)

    return () => {
      clearTimers()
      document.removeEventListener('pointerover', handlePointerOver, true)
      document.removeEventListener('pointerout', handlePointerOut, true)
      document.removeEventListener('focusin', handleFocusIn, true)
      document.removeEventListener('focusout', handleFocusOut, true)
      window.removeEventListener('scroll', syncPosition, true)
      window.removeEventListener('resize', syncPosition)
    }
  }, [])

  useEffect(() => {
    if (!hint) {
      setHintPosition(null)
      return undefined
    }

    const frame = window.requestAnimationFrame(() => {
      const tooltip = tooltipRef.current
      if (!tooltip) {
        setHintPosition({ left: hint.x, top: hint.y })
        return
      }

      const rect = tooltip.getBoundingClientRect()
      const halfWidth = rect.width / 2
      const nextLeft = clamp(
        hint.x,
        EDGE_PADDING + halfWidth,
        window.innerWidth - EDGE_PADDING - halfWidth,
      )

      const nextTop = hint.placement === 'bottom'
        ? clamp(
            hint.y,
            EDGE_PADDING,
            window.innerHeight - EDGE_PADDING - rect.height,
          )
        : clamp(
            hint.y,
            EDGE_PADDING + rect.height,
            window.innerHeight - EDGE_PADDING,
          )

      setHintPosition({
        left: nextLeft,
        top: nextTop,
      })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [hint])

  if (!hint) return null

  return (
    <div
      ref={tooltipRef}
      className={`timed-hint-layer timed-hint-layer--${hint.placement}`}
      style={{
        left: `${(hintPosition?.left ?? hint.x)}px`,
        top: `${(hintPosition?.top ?? hint.y)}px`,
      }}
      role="tooltip"
      aria-live="polite"
    >
      {hint.text}
    </div>
  )
}
