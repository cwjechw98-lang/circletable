import React, { useEffect, useMemo, useRef, useState } from 'react'
import Mascot, { resolveMascot } from './Mascot.jsx'
import { MiniSprite } from './PixelSprite.jsx'
import SpeechBubble from './SpeechBubble.jsx'
import { getRoleLabel } from '../constants/roles.js'
import { getSpecialtyLabel } from '../constants/specialties.js'

function agentPosition(index, total) {
  const angle = (index * 2 * Math.PI) / Math.max(total, 1) - Math.PI / 2
  const radiusX = total >= 7 ? 35 : total >= 5 ? 37 : 40
  const radiusY = total >= 7 ? 30 : total >= 5 ? 33 : 36
  return {
    x: 50 + radiusX * Math.cos(angle),
    y: 50 + radiusY * Math.sin(angle),
  }
}

const SEAT_OFFSETS_KEY = 'circletable-seat-offsets-v2'
const SCENE_SCALE_KEY = 'circletable-scene-scale-v1'

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function readSeatOffsets() {
  try {
    return JSON.parse(localStorage.getItem(SEAT_OFFSETS_KEY) || '{}')
  } catch {
    return {}
  }
}

function readSceneScale() {
  try {
    const value = Number(localStorage.getItem(SCENE_SCALE_KEY) || '1')
    return Number.isFinite(value) ? clamp(value, 0.85, 2) : 1
  } catch {
    return 1
  }
}

function formatResponsePace(metric) {
  if (!metric?.sampleCount) {
    return 'Ещё не измерялся'
  }

  if (metric.avgSeconds >= 12) return 'Очень вдумчивый'
  if (metric.avgSeconds >= 8) return 'Медленный и основательный'
  if (metric.avgSeconds >= 4.5) return 'Размеренный'
  return 'Шустрый'
}

export default function RoundTable({
  agents,
  topic,
  densityMode = 'normal',
  thinkingSet,
  speakingSet,
  streamTexts,
  emotions,
  responseMetrics,
  slowThinkingSet,
  uiFontScale,
  fontPanelOpen,
  onToggleFontPanel,
  onFontScaleChange,
  onFontScaleReset,
  fontScaleMin,
  fontScaleMax,
}) {
  const [infoAgent, setInfoAgent] = useState(null)
  const [seatOffsets, setSeatOffsets] = useState(readSeatOffsets)
  const [sceneScale, setSceneScale] = useState(readSceneScale)
  const [zoomOpen, setZoomOpen] = useState(false)
  const [sceneBounds, setSceneBounds] = useState({ width: 1, height: 1 })

  const dragRef = useRef(null)
  const sceneRef = useRef(null)

  const basePositions = useMemo(
    () => agents.map((_, i) => agentPosition(i, agents.length)),
    [agents.length],
  )

  const positions = useMemo(
    () => agents.map((agent, index) => {
      const base = basePositions[index]
      const offset = seatOffsets[agent.id] || { x: 0, y: 0 }
      return {
        x: clamp(base.x + Number(offset.x || 0), 2, 98),
        y: clamp(base.y + Number(offset.y || 0), 2, 98),
      }
    }),
    [agents, basePositions, seatOffsets],
  )

  const statRows = infoAgent ? [
    ['Инсайт', infoAgent.stats?.insight],
    ['Фокус', infoAgent.stats?.focus],
    ['Глубина', infoAgent.stats?.depth],
    ['Кооперация', infoAgent.stats?.cooperation],
    ['Сцена', infoAgent.stats?.showmanship],
  ] : []
  const infoAgentMetricState = infoAgent ? responseMetrics?.[infoAgent.id] : null
  const infoAgentMetric = infoAgentMetricState?.currentModelMetric || null
  const infoAgentMascot = infoAgent ? resolveMascot(infoAgent) : null
  const infoAgentEmotion = infoAgent ? emotions[infoAgent.id] || 'neutral' : 'neutral'
  const infoAgentStrengths = Array.isArray(infoAgent?.strengths) ? infoAgent.strengths.slice(0, 3) : []

  useEffect(() => {
    localStorage.setItem(SEAT_OFFSETS_KEY, JSON.stringify(seatOffsets))
  }, [seatOffsets])

  useEffect(() => {
    localStorage.setItem(SCENE_SCALE_KEY, String(sceneScale))
  }, [sceneScale])

  useEffect(() => {
    const scene = sceneRef.current
    if (!scene) return undefined

    const updateBounds = () => {
      setSceneBounds({
        width: scene.clientWidth || 1,
        height: scene.clientHeight || 1,
      })
    }

    updateBounds()

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateBounds)
      return () => window.removeEventListener('resize', updateBounds)
    }

    const observer = new ResizeObserver(updateBounds)
    observer.observe(scene)

    return () => observer.disconnect()
  }, [])

  function startDrag(event, agent, basePosition) {
    if (event.button !== 0) return
    const scene = event.currentTarget.closest('.table-scene')
    if (!scene) return
    const rect = scene.getBoundingClientRect()
    dragRef.current = {
      agentId: agent.id,
      basePosition,
      rect,
      pointerId: event.pointerId,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function moveDrag(event) {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const x = ((event.clientX - drag.rect.left) / drag.rect.width) * 100
    const y = ((event.clientY - drag.rect.top) / drag.rect.height) * 100
    setSeatOffsets((current) => ({
      ...current,
      [drag.agentId]: {
        x: clamp(x, 2, 98) - drag.basePosition.x,
        y: clamp(y, 2, 98) - drag.basePosition.y,
      },
    }))
  }

  function endDrag(event) {
    const drag = dragRef.current
    if (drag?.pointerId === event.pointerId) {
      dragRef.current = null
    }
  }

  function resetSeat(agentId) {
    setSeatOffsets((current) => {
      const next = { ...current }
      delete next[agentId]
      return next
    })
  }

  return (
    <div className="round-table-container">
      <div className={`scene-zoom-widget${zoomOpen ? ' is-open' : ''}`}>
        <button
          type="button"
          className="scene-zoom-toggle"
          onClick={() => setZoomOpen((prev) => !prev)}
          data-hint="Лупа сцены: увеличить или уменьшить стол, героев и линии."
          aria-expanded={zoomOpen}
        >
          🔎
        </button>

        <div className="scene-zoom-panel">
          <div className="scene-zoom-title">Масштаб сцены</div>
          <input
            className="scene-zoom-range"
            type="range"
            min="0.85"
            max="2"
            step="0.01"
            value={sceneScale}
            onChange={(event) => setSceneScale(Number(event.target.value))}
          />
          <div className="scene-zoom-meta">
            <span>{Math.round(sceneScale * 100)}%</span>
            <button type="button" className="scene-zoom-reset" onClick={() => setSceneScale(1)}>
              Сброс
            </button>
          </div>
        </div>
      </div>

      <div className={`ui-font-widget${fontPanelOpen ? ' is-open' : ''}`}>
        <button
          type="button"
          className="ui-font-toggle"
          onClick={onToggleFontPanel}
          data-hint="Настроить размер текста в интерфейсе и чате."
          aria-expanded={fontPanelOpen}
        >
          Аа
        </button>
        <div className="ui-font-panel">
          <div className="ui-font-title">Размер текста</div>
          <input
            className="ui-font-range"
            type="range"
            min={fontScaleMin}
            max={fontScaleMax}
            step="0.01"
            value={uiFontScale}
            onChange={(event) => onFontScaleChange(event.target.value)}
          />
          <div className="ui-font-meta">
            <span>{Math.round(uiFontScale * 100)}%</span>
            <button type="button" className="ui-font-reset" onClick={onFontScaleReset}>
              Сброс
            </button>
          </div>
        </div>
      </div>

      <div className="table-scene" ref={sceneRef} style={{ transform: `scale(${sceneScale})` }}>
        <div className="table-surface">
          <div className="table-label">Тема</div>
          <div className="table-topic-mask">
            <div className="table-topic-crawl">
              <span>{topic || 'Тема появится после запуска'}</span>
              <span>{topic || 'Тема появится после запуска'}</span>
            </div>
          </div>
        </div>

        {infoAgent && (
          <div className="table-agent-card">
            <div className="table-agent-card-head">
              <span className="table-agent-card-avatar">
                {infoAgentMascot
                  ? <MiniSprite mascot={infoAgentMascot} emotion={infoAgentEmotion} />
                  : infoAgent.emoji}
              </span>
              <strong>{infoAgent.name}</strong>
            </div>
            <div className="table-agent-card-line">
              {getRoleLabel(infoAgent.role)} · {getSpecialtyLabel(infoAgent.specialty, infoAgent.specialtyLabel)}
            </div>
            <div className="table-agent-card-line">
              {infoAgent.provider}/{infoAgent.model}
            </div>
            <div className="table-agent-response-line">
              <span className={`table-agent-response-badge${infoAgentMetric?.avgSeconds >= 8 ? ' is-slow' : ''}`}>
                {infoAgentMetric?.avgSeconds >= 8 ? '⏳' : '⚡'} {formatResponsePace(infoAgentMetric)}
              </span>
              {infoAgentMetric?.sampleCount
                ? `Среднее: ${infoAgentMetric.avgSeconds.toFixed(1)}с · долгих ответов: ${infoAgentMetric.slowCount}`
                : 'После первых реплик здесь появится темп ответа героя.'}
            </div>
            {infoAgentMetricState?.trendText && (
              <div className="table-agent-response-note">{infoAgentMetricState.trendText}</div>
            )}
            <div className="table-agent-stats">
              {statRows.map(([label, value]) => (
                <div key={label} className="table-agent-stat">
                  <span>{label}</span>
                  <b>{Number.isFinite(Number(value)) ? Number(value) : 50}</b>
                </div>
              ))}
            </div>
            <div className="table-agent-card-note">
              {infoAgent.lastNote || infoAgent.summary || 'Хрономант ещё не оставил заметку по этому герою.'}
            </div>
            {(infoAgent.summary || infoAgent.lastNote || infoAgentStrengths.length > 0) && (
              <div className="table-agent-memory">
                {infoAgentStrengths.length > 0 && (
                  <div className="table-agent-memory-line">
                    <strong>Сильные темы:</strong> {infoAgentStrengths.join(' · ')}
                  </div>
                )}
                {infoAgent.summary && (
                  <div className="table-agent-memory-line">
                    <strong>Обычно привносит:</strong> {infoAgent.summary}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {agents.map((agent, index) => {
          const pos = positions[index]
          const dx = ((pos.x - 50) / 100) * sceneBounds.width
          const dy = ((pos.y - 50) / 100) * sceneBounds.height
          const len = Math.sqrt(dx * dx + dy * dy)
          const angle = Math.atan2(dy, dx) * (180 / Math.PI)

          return (
            <div
              key={`${agent.id}-line`}
              className="connector-line"
              style={{
                width: `${len}px`,
                transform: `rotate(${angle}deg)`,
              }}
            />
          )
        })}

        {agents.map((agent, index) => {
          const pos = positions[index]
          const isThinking = thinkingSet.has(agent.id)
          const isSpeaking = speakingSet.has(agent.id)
          const emotion = emotions[agent.id] || 'neutral'
          const streamText = streamTexts[agent.id] || ''
          const responseMetricState = responseMetrics?.[agent.id]
          const responseMetric = responseMetricState?.currentModelMetric || null
          const isSlowThinking = slowThinkingSet?.has(agent.id)

          return (
            <div
              key={agent.id}
              className="agent-seat"
              style={{
                left: `${pos.x}%`,
                top: `${pos.y}%`,
              }}
            >
              <SpeechBubble
                text={streamText}
                isThinking={isThinking}
                isSpeaking={isSpeaking}
                position={pos}
                densityMode={densityMode}
              />

              <div
                className="seat-drag-handle"
                onPointerDown={(event) => startDrag(event, agent, basePositions[index])}
                onPointerMove={moveDrag}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
                onDoubleClick={() => resetSeat(agent.id)}
                data-hint="Перетащить героя по всей сцене. Двойной клик — вернуть на автопозицию."
              >
                <Mascot
                  agent={agent}
                  emotion={emotion}
                  isThinking={isThinking}
                  isSpeaking={isSpeaking}
                  responseMetric={responseMetric}
                  isSlowThinking={isSlowThinking}
                />
              </div>

              <button
                type="button"
                className="agent-info-btn"
                onMouseEnter={() => setInfoAgent(agent)}
                onMouseLeave={() => setInfoAgent(null)}
                onFocus={() => setInfoAgent(agent)}
                onBlur={() => setInfoAgent(null)}
                aria-label={`Карточка персонажа ${agent.name}`}
                aria-expanded={infoAgent?.id === agent.id}
                data-hint="Показать карточку персонажа"
              >
                i
              </button>
            </div>
          )
        })}

        {agents.length === 0 && (
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, 7rem)',
              textAlign: 'center',
            }}
          >
            <div className="empty-state">
              Добавьте хотя бы двух участников
              <br />
              и запустите обсуждение
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
