import React, { useEffect, useRef, useState } from 'react'
import { MiniSprite } from './PixelSprite.jsx'
import MarkdownReport from './MarkdownReport.jsx'
import { getRoleLabel } from '../constants/roles.js'
import { getSpecialtyLabel } from '../constants/specialties.js'

const FACT_CHECK_LABELS = {
  confirmed: 'Подтверждено',
  unverified: 'Не подтверждено',
  contradicted: 'Опровергнуто',
  disputed: 'Спорно',
  insufficient_evidence: 'Недостаточно данных',
}

function formatScopeLabel(factCheck) {
  if (!factCheck) return ''
  if (factCheck.scope === 'round' && factCheck.targetRound) {
    return `Проверен раунд ${factCheck.targetRound}`
  }
  return 'Проверена вся сессия'
}

function formatSeconds(value) {
  const seconds = Number(value)
  if (!Number.isFinite(seconds) || seconds <= 0) return ''
  return `${seconds.toFixed(1)}с`
}

export default function ChatPanel({
  messages,
  pinnedMessages = [],
  onTogglePin,
  session,
  sessionState,
  report,
  reportGenerating,
  reportProgress = 0,
  reportError,
  onGenerateReport,
  onDownloadReport,
  factCheck,
  factCheckError,
}) {
  const endRef = useRef(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const canGenerateReport = Boolean(session?.id) && ['completed', 'stopped'].includes(sessionState || session?.status)
  const hasReport = Boolean(report?.markdown)
  const hasFactCheck = Boolean(factCheck)
  const factCheckCounts = factCheck?.counts || {}
  const factCheckClaims = Array.isArray(factCheck?.claims) ? factCheck.claims : []
  const factCheckDeltas = Array.isArray(factCheck?.modelDeltas) ? factCheck.modelDeltas : []
  const factCheckStatusText = factCheck?.status === 'running'
    ? `Идёт проверка фактов… ${Math.max(5, Number(factCheck?.progress) || 0)}%`
    : factCheck?.status === 'queued'
      ? 'Проверка фактов поставлена в очередь.'
      : factCheck?.summary
  const shouldShowAnalytics = canGenerateReport || hasReport || reportGenerating || reportError || hasFactCheck || factCheckError

  useEffect(() => {
    if (autoScroll) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [autoScroll, messages.length])

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <span>Ход беседы</span>
        <button
          type="button"
          className={`chat-scroll-toggle${autoScroll ? ' is-active' : ''}`}
          onClick={() => setAutoScroll((value) => !value)}
          aria-pressed={autoScroll}
          data-hint="Если выключить, новые сообщения не будут уводить чат вниз во время чтения."
        >
          {autoScroll ? 'Автопрокрутка: вкл' : 'Автопрокрутка: выкл'}
        </button>
      </div>

      <div className="chat-messages">
        {pinnedMessages.length > 0 && (
          <div className="chat-pins">
            <div className="chat-pins-title">Зацепки</div>
            {pinnedMessages.slice(-4).map((msg, index) => (
              <button
                key={msg.id || `pin-${index}`}
                type="button"
                className="chat-pin-chip"
                onClick={() => onTogglePin?.(msg.id)}
                data-hint="Снять закрепление с сильной мысли."
              >
                📌 {(msg.name || msg.agent_name || 'Участник')}: {msg.content}
              </button>
            ))}
          </div>
        )}

        {shouldShowAnalytics && (
          <div className="chat-report-card">
            <div className="chat-report-header-row">
              <div>
                <div className="chat-report-kicker">Аналитика</div>
                <div className="chat-report-title">Итоговый отчёт по сессии</div>
                <div className="chat-report-meta">
                  {report?.generatedAt
                    ? `Обновлён: ${report.generatedAt}${report.provider ? ` · ${report.provider}/${report.model || '—'}` : ''}`
                    : 'После завершения сессии можно собрать аналитический отчёт.'}
                </div>
              </div>
              <div className="chat-report-actions">
                {canGenerateReport && (
                  <button
                    type="button"
                    className="chat-report-btn"
                    onClick={onGenerateReport}
                    disabled={reportGenerating}
                    data-hint="Собрать итоговый Markdown-отчёт по завершённой или остановленной сессии: выводы, аргументы, риски и рекомендации."
                  >
                    {reportGenerating ? 'Собираем...' : hasReport ? 'Пересобрать отчёт' : 'Сгенерировать отчёт'}
                  </button>
                )}
                {hasReport && (
                  <button
                    type="button"
                    className="chat-report-btn ghost"
                    onClick={onDownloadReport}
                    data-hint="Скачать готовый аналитический отчёт как .md-файл, чтобы открыть его в редакторе или добавить в документацию."
                  >
                    Скачать .md
                  </button>
                )}
              </div>
            </div>

            {reportGenerating && (
              <div className="chat-report-status">
                Хрономант собирает аналитический отчёт… {Math.max(5, reportProgress)}%
              </div>
            )}

            {reportError && (
              <div className="chat-report-error">
                {reportError}
              </div>
            )}

            {(hasFactCheck || factCheckError) && (
              <div className="chat-fact-check-card">
                <div className="chat-fact-check-head">
                  <div>
                    <div className="chat-report-kicker">Фактчекинг</div>
                    <div className="chat-fact-check-title">Надёжность утверждений</div>
                    <div className="chat-fact-check-meta">
                      {formatScopeLabel(factCheck)}
                      {factCheck?.internetMode ? ` · Интернет: ${factCheck.internetMode.toUpperCase()}` : ''}
                      {factCheck?.externalSourcesUsed === false ? ' · Без внешних источников' : ''}
                    </div>
                  </div>
                  {factCheck?.status && (
                    <span className={`chat-fact-check-status is-${factCheck.status}`}>
                      {factCheck.status === 'completed'
                        ? 'Готово'
                        : factCheck.status === 'failed'
                          ? 'Ошибка'
                          : 'В работе'}
                    </span>
                  )}
                </div>

                {factCheckStatusText && (
                  <div className="chat-report-status">
                    {factCheckStatusText}
                  </div>
                )}

                {factCheckError && (
                  <div className="chat-report-error">
                    {factCheckError}
                  </div>
                )}

                {Object.keys(factCheckCounts).length > 0 && (
                  <div className="chat-fact-check-counts">
                    {Object.entries(FACT_CHECK_LABELS).map(([key, label]) => (
                      <div key={key} className={`chat-fact-check-chip is-${key}`}>
                        <span>{label}</span>
                        <strong>{factCheckCounts[key] || 0}</strong>
                      </div>
                    ))}
                  </div>
                )}

                {factCheckClaims.length > 0 && (
                  <details className="chat-fact-check-details">
                    <summary>Проверенные тезисы</summary>
                    <div className="chat-fact-check-claims">
                      {factCheckClaims.slice(0, 6).map((claim) => (
                        <div key={claim.id || `${claim.messageId}-${claim.claimText}`} className={`chat-fact-check-claim is-${claim.verdict}`}>
                          <div className="chat-fact-check-claim-head">
                            <span>{claim.agentName || 'Агент'}</span>
                            <b>{FACT_CHECK_LABELS[claim.verdict] || claim.verdict}</b>
                          </div>
                          <div className="chat-fact-check-claim-text">{claim.claimText}</div>
                          {claim.evidence && (
                            <div className="chat-fact-check-claim-evidence">
                              {claim.sourceLabel ? `${claim.sourceLabel}: ` : ''}{claim.evidence}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {factCheckDeltas.length > 0 && (
                  <details className="chat-fact-check-details">
                    <summary>Как изменился рейтинг моделей</summary>
                    <div className="chat-fact-check-deltas">
                      {factCheckDeltas.map((delta) => (
                        <div key={`${delta.provider}-${delta.model}`} className="chat-fact-check-delta">
                          <div className="chat-fact-check-delta-head">
                            <strong>{delta.provider}/{delta.model}</strong>
                            <span>{delta.previousScore.toFixed(1)} → {delta.nextScore.toFixed(1)}</span>
                          </div>
                          <div className="chat-fact-check-delta-meta">
                            Проверено: {delta.checkedClaimsBefore} → {delta.checkedClaimsAfter}
                          </div>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}

            {hasReport && (
              <MarkdownReport markdown={report.markdown} />
            )}
          </div>
        )}

        {messages.length === 0 && (
          <div className="empty-state">
            {'>'} Сообщения появятся после запуска беседы.<br />
            {'>'} Выберите участников и тему ниже.
          </div>
        )}

        {messages.map((msg, i) => {
          const responseTimeLabel = msg.type === 'agent_message' ? formatSeconds(msg.responseSeconds) : ''
          const interTurnGapLabel = msg.type === 'agent_message' ? formatSeconds(msg.interTurnGapSeconds) : ''

          if (msg.type === 'status') {
            return <div key={msg.id || i} className="chat-status">// {msg.content}</div>
          }

          if (msg.type === 'round') {
            return (
              <div key={msg.id || i} className="chat-round-badge">
                ═══ Раунд {msg.round} ═══
              </div>
            )
          }

          if (msg.type === 'user_question') {
            return (
              <div key={msg.id || i} className="chat-user-question">
                <div className="chat-msg-head">
                  <span className="chat-msg-emoji">📝</span>
                  <span className="chat-msg-name">Вы</span>
                  <span className="chat-msg-role">[Вопрос в комнату]</span>
                  {msg.round && <span className="chat-msg-round">Раунд {msg.round}</span>}
                </div>
                <div className="chat-msg-body">{msg.content}</div>
              </div>
            )
          }

          if (msg.type === 'system_event') {
            return (
              <div key={msg.id || i} className="chat-system-event">
                <div className="chat-msg-head">
                  <span className="chat-msg-emoji">⚡</span>
                  <span className="chat-msg-name">Событие</span>
                  <span className="chat-msg-role">[Вброс в раунд]</span>
                  {msg.round && <span className="chat-msg-round">Раунд {msg.round}</span>}
                </div>
                <div className="chat-msg-body">{msg.content}</div>
              </div>
            )
          }

          if (msg.type === 'observer_note') {
            return (
              <div key={msg.id || i} className="chat-observer-note">
                <div className="chat-msg-head">
                  <span className="chat-msg-emoji">⏳</span>
                  <span className="chat-msg-name">Хрономант</span>
                  <span className="chat-msg-role">[Наблюдатель стола]</span>
                  {msg.round && <span className="chat-msg-round">Раунд {msg.round}</span>}
                </div>
                <div className="chat-msg-body">{msg.content}</div>
              </div>
            )
          }

          return (
            <div key={msg.id || i} className={`chat-msg${msg.streaming ? ' is-streaming' : ''}`}>
              <div className="chat-msg-head">
                <span className="chat-msg-avatar">
                  {msg.mascot
                    ? <MiniSprite mascot={msg.mascot} emotion={msg.emotion || 'neutral'} />
                    : <span className="chat-msg-emoji">{msg.emoji}</span>
                  }
                </span>
                <span className="chat-msg-name">{msg.name}</span>
                <span className="chat-msg-role">
                  [{getRoleLabel(msg.role)} · {getSpecialtyLabel(msg.specialty, msg.specialtyLabel)}]
                </span>
                {msg.round && (
                  <span className="chat-msg-round">Раунд {msg.round}</span>
                )}
                {responseTimeLabel && (
                  <span className="chat-msg-latency">⏱ {responseTimeLabel}</span>
                )}
                {interTurnGapLabel && (
                  <span className="chat-msg-gap">⌁ {interTurnGapLabel}</span>
                )}
                {onTogglePin && (
                  <button
                    type="button"
                    className={`chat-pin-toggle${msg.pinned ? ' is-pinned' : ''}`}
                    onClick={() => onTogglePin(msg.id)}
                    data-hint={msg.pinned ? 'Снять закрепление с этой мысли.' : 'Закрепить сильную мысль как зацепку для Хрономанта.'}
                  >
                    {msg.pinned ? '📌' : '⊹'}
                  </button>
                )}
              </div>
              {Array.isArray(msg.toolCalls) && msg.toolCalls.length > 0 && (
                <div className="chat-tool-stack">
                  {msg.toolCalls.map((toolCall, toolIndex) => (
                    <details key={`${msg.id || i}-tool-${toolIndex}`} className="chat-tool-call">
                      <summary data-hint="Это служебный блок: агент сначала вызвал инструмент, получил результат, затем сформировал финальную реплику. Раскройте, чтобы увидеть вход и ответ инструмента.">
                        🔧 {msg.name || msg.agent_name || 'Агент'} использовал {toolCall.tool}: "{toolCall.query}"
                      </summary>
                      <div className="chat-tool-result">
                        {toolCall.ok === false
                          ? `Ошибка: ${toolCall.error || 'инструмент не вернул результат'}`
                          : toolCall.result || 'Инструмент не вернул текстовый результат.'}
                      </div>
                    </details>
                  ))}
                </div>
              )}
              <div className="chat-msg-body">{msg.content}</div>
            </div>
          )
        })}

        <div ref={endRef} />
      </div>
    </div>
  )
}
