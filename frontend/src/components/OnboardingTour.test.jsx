import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import OnboardingTour, { STORAGE_KEY } from './OnboardingTour.jsx'

describe('OnboardingTour', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<OnboardingTour open={false} onClose={() => {}} />)
    expect(container.querySelector('.onboarding-overlay')).toBeNull()
  })

  it('walks steps forward and stores the done flag on finish', () => {
    const onClose = vi.fn()
    render(<OnboardingTour open onClose={onClose} />)

    expect(screen.getByText(/Добро пожаловать/)).toBeTruthy()
    fireEvent.click(screen.getByText('Далее'))
    expect(screen.getByText(/Комната: тема и участники/)).toBeTruthy()

    fireEvent.click(screen.getByText('Далее'))
    fireEvent.click(screen.getByText('Далее'))
    expect(screen.getByText('Понятно, за стол!')).toBeTruthy()

    fireEvent.click(screen.getByText('Понятно, за стол!'))
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('1')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('skip button finishes immediately from any step', () => {
    const onClose = vi.fn()
    render(<OnboardingTour open onClose={onClose} />)
    fireEvent.click(screen.getByText('Пропустить'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
