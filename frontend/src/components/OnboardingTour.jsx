import React, { useState } from 'react'

const STORAGE_KEY = 'circletable-onboarding-done'

const STEPS = [
  {
    emoji: '⚔',
    title: 'Добро пожаловать за Круглый стол!',
    text: 'Это мультиагентная дискуссия: несколько ИИ-моделей обсуждают вашу тему за круглым столом, а Хрономант следит за регламентом, темпом и качеством аргументов.',
  },
  {
    emoji: '🪑',
    title: 'Комната: тема и участники',
    text: 'Слева выберите комнату, сформулируйте тему и соберите состав из инвентаря персонажей или пресетов команд. Запуск, пауза и досрочное завершение — кнопками над темой.',
  },
  {
    emoji: '💬',
    title: 'Живой чат и итоги',
    text: 'Справа идёт обсуждение: реплики, реакции-перебивания и обзоры Хрономанта после каждого раунда. По завершении доступны отчёт, проверка фактов, экспорт ⬇ JSONL и препринт 📄.',
  },
  {
    emoji: '💡',
    title: 'Всё подскажет значок ?',
    text: 'Наводите курсор на любые элементы интерфейса — у большинства есть всплывающая подсказка. Память профилей и пересборка знаний живут в «Лаборатории». Прогресс фоновых задач виден в шапке.',
  },
]

export default function OnboardingTour({ open, onClose }) {
  const [step, setStep] = useState(0)
  if (!open) return null
  const current = STEPS[step]
  const last = step === STEPS.length - 1

  function finish() {
    try {
      window.localStorage.setItem(STORAGE_KEY, '1')
    } catch {
      // приватный режим — просто закрываем до следующей сессии
    }
    setStep(0)
    onClose?.()
  }

  return (
    <div className="onboarding-overlay" role="dialog" aria-modal="true" aria-label="Знакомство с интерфейсом">
      <div className="onboarding-card">
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
          <button type="button" className="pixel-btn" onClick={() => (last ? finish() : setStep((value) => value + 1))}>
            {last ? 'Понятно, за стол!' : 'Далее'}
          </button>
        </div>
        <span className="onboarding-counter">{step + 1} / {STEPS.length}</span>
      </div>
    </div>
  )
}

export { STORAGE_KEY }
