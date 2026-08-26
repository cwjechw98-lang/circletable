import React, { useEffect, useState } from 'react'

const STORAGE_KEY = 'circletable-onboarding-done'

// Шаги с selector подсвечивают реальный элемент (спотлайт),
// без selector показывается центрированная карточка.
const STEPS = [
  {
    emoji: '⚔',
    title: 'Добро пожаловать за Круглый стол!',
    text: 'Это мультиагентная дискуссия: несколько ИИ-моделей обсуждают вашу тему за круглым столом, а Хрономант следит за регламентом, темпом и качеством аргументов.',
  },
  {
    selector: '.control-panel',
    place: 'right',
    emoji: '🪑',
    title: 'Комната: тема и участники',
    text: 'Здесь формулируется тема и собирается состав из инвентаря персонажей или пресетов команд. Запуск, пауза и досрочное завершение — кнопками над темой.',
  },
  {
    selector: '.chat-panel',
    place: 'left',
    emoji: '💬',
    title: 'Живой чат и итоги',
    text: 'Реплики, реакции-перебивания и обзоры Хрономанта после каждого раунда. По завершении доступны отчёт, проверка фактов, экспорт ⬇ JSONL и препринт 📄.',
  },
  {
    selector: '.header-help-btn',
    place: 'bottom',
    emoji: '💡',
    title: 'Подсказки всегда рядом',
    text: 'Наводите курсор на элементы интерфейса — у большинства есть всплывающая подсказка. Этот тур можно вызвать снова кнопкой «?» в шапке.',
  },
]

function rectOf(el) {
  const r = el.getBoundingClientRect()
  return { top: r.top, left: r.left, width: r.width, height: r.height, bottom: r.bottom }
}

export default function OnboardingTour({ open, onClose }) {
  const [step, setStep] = useState(0)
  const [anchor, setAnchor] = useState(null)

  useEffect(() => {
    if (!open) return undefined
    const target = STEPS[step]?.selector ? document.querySelector(STEPS[step].selector) : null
    if (!target) {
      setAnchor(null)
      return undefined
    }
    const measure = () => {
      const rect = rectOf(target)
      if (rect.width < 2 && rect.height < 2) {
        setAnchor(null)
        return
      }
      setAnchor(rect)
    }
    try {
      target.scrollIntoView({ block: 'center' })
    } catch {
      // старые окружения без опций — просто измеряем как есть
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [step, open])

  if (!open) return null

  const current = STEPS[step]
  const last = step === STEPS.length - 1
  const floating = Boolean(anchor)

  function finish() {
    try {
      window.localStorage.setItem(STORAGE_KEY, '1')
    } catch {
      // приватный режим — просто закрываем до следующей сессии
    }
    setStep(0)
    onClose?.()
  }

  function goNext() {
    if (last) finish()
    else setStep((value) => value + 1)
  }

  const card = (
    <div className={`onboarding-card${floating ? ' is-floating' : ''}`} style={floating ? floatingStyle() : undefined}>
      <div className="onboarding-emoji" aria-hidden="true">{current.emoji}</div>
      <h3 className="onboarding-title">{current.title}</h3>
      <p className="onboarding-text">{current.text}</p>
      <div className="onboarding-dots" aria-hidden="true">
        {STEPS.map((item, index) => (
          <span
            key={item.title}
            className={`onboarding-dot${index === step ? ' is-active' : ''}${index < step ? ' is-done' : ''}`}
          />
        ))}
      </div>
      <div className="onboarding-actions">
        <button type="button" className="pixel-btn ghost" onClick={finish}>
          Пропустить
        </button>
        {step > 0 && (
          <button type="button" className="pixel-btn ghost" onClick={() => setStep((value) => value - 1)}>
            Назад
          </button>
        )}
        <button type="button" className="pixel-btn" onClick={goNext}>
          {last ? 'Понятно, за стол!' : 'Далее'}
        </button>
      </div>
      <span className="onboarding-counter">{step + 1} / {STEPS.length}</span>
    </div>
  )

  function floatingStyle() {
    const vw = window.innerWidth
    const vh = window.innerHeight
    const width = Math.min(340, vw - 24)
    const left = Math.max(12, Math.min(anchor.left + anchor.width / 2 - width / 2, vw - width - 12))
    const below = anchor.bottom + 12
    const style = { position: 'fixed', left, width }
    if (below + 240 < vh) {
      style.top = below
    } else {
      style.bottom = Math.max(12, vh - anchor.top + 12)
    }
    return style
  }

  if (!floating) {
    return (
      <div className="onboarding-overlay" role="dialog" aria-modal="true" aria-label="Знакомство с интерфейсом">
        {card}
      </div>
    )
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="Знакомство с интерфейсом">
      <div
        className="onboarding-spotlight"
        style={{
          top: anchor.top - 6,
          left: anchor.left - 6,
          width: anchor.width + 12,
          height: anchor.height + 12,
        }}
      />
      {card}
    </div>
  )
}

export { STORAGE_KEY }
