import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LabDrawer from './LabDrawer.jsx'

vi.mock('./PixelSprite.jsx', () => ({
  default: ({ size = 36 }) => <div data-testid="pixel-sprite" style={{ width: size, height: size }} />,
}))

const DOSSIERS = [
  {
    id: 'char_1',
    name: 'Логос',
    role: 'logician',
    specialty: 'strategy',
    provider: 'ollama',
    model: 'test-model',
    emoji: '🧠',
    mascot: 'sage',
    stats: { insight: 60, focus: 55, depth: 50, cooperation: 45, showmanship: 40 },
    hasMemory: true,
    reviewMentions: 2,
    career: { sessionsCount: 1, messagesCount: 2, roundsSpoken: 2 },
  },
]

const DOSSIER = {
  ...DOSSIERS[0],
  summary: 'Сухой аналитик',
  statsTotals: { insight: 4, focus: 1, depth: 2, cooperation: 2, showmanship: 0 },
  startValues: { insight: 56, focus: 54, depth: 48, cooperation: 43, showmanship: 40 },
  evolution: [
    { roundNumber: 1, values: { insight: 59, focus: 55, depth: 50, cooperation: 43, showmanship: 40 } },
    { roundNumber: 2, values: { insight: 60, focus: 55, depth: 50, cooperation: 45, showmanship: 40 } },
  ],
  achievements: [
    { roundNumber: 1, title: 'Аналитик раунда', reason: 'Разложил проблему по полочкам.' },
  ],
  notes: [
    { roundNumber: 1, text: 'Логос усилил показатель «Инсайт».' },
  ],
}

function mockFetch() {
  vi.stubGlobal('fetch', vi.fn((url) => {
    if (String(url).endsWith('/api/lab/profiles')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ dossiers: DOSSIERS }) })
    }
    if (String(url) === '/api/lab/profiles/char_1') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(DOSSIER) })
    }
    return Promise.resolve({ ok: false })
  }))
}

describe('LabDrawer', () => {
  beforeEach(() => {
    mockFetch()
  })

  it('renders nothing when closed', () => {
    const { container } = render(<LabDrawer open={false} onClose={() => {}} />)
    expect(container.querySelector('.drawer-lab')).toBeNull()
  })

  it('loads and lists character dossiers when opened', async () => {
    render(<LabDrawer open onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('Логос')).toBeTruthy())
    expect(screen.getByText(/Сессий: 1/)).toBeTruthy()
  })

  it('opens a dossier with evolution, achievements and notes', async () => {
    const user = userEvent.setup()
    render(<LabDrawer open onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('Логос')).toBeTruthy())

    await user.click(screen.getByText('Логос'))

    await waitFor(() => expect(screen.getByText('Показатели')).toBeTruthy())
    expect(screen.getByText(/Аналитик раунда/)).toBeTruthy()
    expect(screen.getByText('← Ко всем персонажам')).toBeTruthy()
    expect(screen.getByText('Логос усилил показатель «Инсайт».')).toBeTruthy()
  })
})
