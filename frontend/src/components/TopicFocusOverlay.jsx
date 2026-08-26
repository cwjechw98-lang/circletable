import React, { useEffect, useRef } from 'react'
import './topicFocus.css'

export default function TopicFocusOverlay({
  active,
  mode = 'glass',
  value,
  dirty,
  onChange,
  onConfirm,
  onCancel,
}) {
  const inputRef = useRef(null)

  useEffect(() => {
    if (!active) return
    const handle = window.requestAnimationFrame(() => {
      inputRef.current?.focus()
      inputRef.current?.setSelectionRange?.(value.length, value.length)
    })
    return () => window.cancelAnimationFrame(handle)
  }, [active, value.length])

  if (!active || mode === 'off') {
    return null
  }

  return (
    <div className={`topic-focus-overlay is-${mode}`} role="dialog" aria-modal="true" aria-label="Формулировка темы">
      <div className="topic-focus-backdrop" onClick={onCancel} />
      {mode === 'mist' && (
        <>
          <div className="topic-focus-mist mist-a" />
          <div className="topic-focus-mist mist-b" />
          <div className="topic-focus-mist mist-c" />
        </>
      )}

      <div className="topic-focus-panel">
        <div className="topic-focus-eyebrow">Режим фокуса</div>
        <div className="topic-focus-title">Сформулируй вопрос для стола</div>
        <div className="topic-focus-sub">
          Подтверди тему, и только после этого кастинг-помощник и старт сессии начнут работать с новым вопросом.
        </div>

        <div className="topic-focus-input-shell">
          <input
            ref={inputRef}
            className="topic-focus-input"
            value={value}
            onChange={(event) => onChange?.(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && dirty) {
                event.preventDefault()
                onConfirm?.()
              }
              if (event.key === 'Escape') {
                event.preventDefault()
                onCancel?.()
              }
            }}
            placeholder="Например: летали ли на самом деле на Луну?"
          />
        </div>

        <div className="topic-focus-actions">
          <button className="pixel-btn ghost" onClick={onCancel}>
            Отмена
          </button>
          <button className="pixel-btn start" onClick={onConfirm} disabled={!dirty}>
            ✓ Подтвердить
          </button>
        </div>

        <div className="topic-focus-tip">Enter подтверждает тему · Esc возвращает предыдущую версию</div>
      </div>
    </div>
  )
}
