import React from 'react'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPanel from './ChatPanel.jsx'

describe('ChatPanel', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('renders response and inter-turn timing for agent messages', () => {
    render(
      <ChatPanel
        messages={[{
          id: 'msg-1',
          type: 'agent_message',
          name: 'Кот',
          emoji: '🐈',
          role: 'critic',
          specialty: 'lawyer',
          content: 'Сначала надо проверить спрос.',
          round: 3,
          responseSeconds: 2.4,
          interTurnGapSeconds: 0.6,
        }]}
        pinnedMessages={[]}
        onTogglePin={undefined}
        session={null}
        sessionState="idle"
        report={null}
        reportGenerating={false}
        reportProgress={0}
        reportError=""
        onGenerateReport={() => {}}
        onDownloadReport={() => {}}
        factCheck={null}
        factCheckError=""
      />,
    )

    expect(screen.getByText('⏱ 2.4с')).toBeTruthy()
    expect(screen.getByText('⌁ 0.6с')).toBeTruthy()
  })
})
