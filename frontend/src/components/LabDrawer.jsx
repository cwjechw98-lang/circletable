import React, { useEffect, useRef, useState } from 'react'
import { getRoleLabel } from '../constants/roles.js'
import { getSpecialtyLabel } from '../constants/specialties.js'
import PixelSprite from './PixelSprite.jsx'
import { resolveMascot } from './Mascot.jsx'
import Sparkline from './Sparkline.jsx'

const STAT_LABELS = {
  insight: 'Инсайт',
  focus: 'Фокус',
  depth: 'Глубина',
  cooperation: 'Кооперация',
  showmanship: 'Сценичность',
}

const STAT_KEYS = Object.keys(STAT_LABELS)

function formatSigned(value) {
  if (value > 0) return `+${value}`
  return String(value)
}

function StatEvolution({ statKey, dossier }) {
  const current = Number(dossier.stats?.[statKey] ?? 0)
  const total = Number(dossier.statsTotals?.[statKey] ?? 0)
  const startValue = dossier.startValues?.[statKey]
  const series = (dossier.evolution || []).map((entry) => entry.values?.[statKey])
  const sparkValues = series.length > 1
    ? [Number.isFinite(startValue) ? startValue : current - total, ...series]
    : []
  const toneClass = total > 0 ? ' is-up' : total < 0 ? ' is-down' : ''
  return (
    <div className={`dossier-stat${toneClass}`}>
      <div className="dossier-stat-head">
        <span className="dossier-stat-label">{STAT_LABELS[statKey]}</span>
        <span className="dossier-stat-total" title="Суммарный прирост показателя за все оценённые раунды.">
          {formatSigned(total)}
        </span>
      </div>
      <div className="dossier-stat-body">
        <div className="stat-track">
          <div className="stat-fill" style={{ width: `${Math.max(0, Math.min(100, current))}%` }} />
        </div>
        <span className="dossier-stat-value">{current}</span>
        <Sparkline values={sparkValues} />
      </div>
    </div>
  )
}

function LabCard({ dossier, onOpen }) {
  const mascot = resolveMascot(dossier)
  const career = dossier.career || {}
  return (
    <button className="lab-card" onClick={() => onOpen(dossier.id)}>
      <span className="lab-card-avatar">
        <PixelSprite mascot={mascot} emotion="neutral" size={36} />
      </span>
      <span className="lab-card-body">
        <span className="lab-card-name-row">
          <span className="lab-card-name">{dossier.name}</span>
          {dossier.hasMemory && <span className="character-memory-badge" title="У профиля есть память между сессиями.">🧠</span>}
        </span>
        <span className="lab-card-role">
          {getRoleLabel(dossier.role)} · {getSpecialtyLabel(dossier.specialty, dossier.specialtyLabel)}
        </span>
        <span className="lab-card-career">
          Сессий: {career.sessionsCount || 0} · Реплик: {career.messagesCount || 0} · Оценок: {dossier.reviewMentions || 0}
        </span>
      </span>
      <span className="lab-card-open" aria-hidden="true">▸</span>
    </button>
  )
}

function DossierView({ dossier, memory, confirmForget, forgetting, reindexing, onBack, onAskForget, onCancelForget, onForget, onReindex }) {
  const mascot = resolveMascot(dossier)
  const career = dossier.career || {}
  return (
    <div className="dossier">
      <button className="pixel-btn ghost dossier-back" onClick={onBack}>
        ← Ко всем персонажам
      </button>

      <div className="dossier-head">
        <div className="dossier-avatar">
          <PixelSprite mascot={mascot} emotion="neutral" size={56} />
        </div>
        <div className="dossier-identity">
          <div className="dossier-name-row">
            <span className="dossier-name">{dossier.name}</span>
            {dossier.hasMemory && <span className="character-memory-badge" title="У профиля есть память между сессиями.">🧠</span>}
          </div>
          <div className="dossier-sub">
            {getRoleLabel(dossier.role)} · {getSpecialtyLabel(dossier.specialty, dossier.specialtyLabel)}
          </div>
          <div className="dossier-model">{dossier.provider} / {dossier.model}</div>
        </div>
      </div>

      {dossier.summary && <div className="dossier-summary">{dossier.summary}</div>}

      <div className="dossier-section-title">Показатели</div>
      <div className="dossier-stats">
        {STAT_KEYS.map((statKey) => (
          <StatEvolution key={statKey} statKey={statKey} dossier={dossier} />
        ))}
      </div>

      <div className="dossier-section-title">Карьера</div>
      <div className="dossier-career">
        <div className="dossier-career-cell"><span>{career.sessionsCount || 0}</span>сессий</div>
        <div className="dossier-career-cell"><span>{career.roundsSpoken || 0}</span>раундов</div>
        <div className="dossier-career-cell"><span>{career.messagesCount || 0}</span>реплик</div>
        <div className="dossier-career-cell"><span>{dossier.reviewMentions || 0}</span>оценок Хрономанта</div>
      </div>

      <div className="dossier-section-title">Память</div>
      {!memory && <div className="dossier-empty">Загружаем память...</div>}
      {memory && !memory.hasMemory && (
        <div className="dossier-empty">
          Памяти пока нет — она появится после раундов с Хрономантом и будет помогать персонажу в следующих сессиях.
        </div>
      )}
      {memory && memory.hasMemory && (
        <div className="dossier-memory">
          <div className="dossier-memory-stats">
            <span className="dossier-memory-count">Сущностей: {memory.entityCount}</span>
            <span className="dossier-memory-count">Связей: {memory.factCount}</span>
            {memory.entityCount === 0 && (memory.entries || []).length > 0 && (
              <span className="dossier-memory-count">Сырых записей: {memory.entries.length}</span>
            )}
            {!confirmForget ? (
              <>
                <button
                  className="pixel-btn ghost dossier-reindex"
                  onClick={onReindex}
                  disabled={reindexing}
                  data-hint="Заново извлечь сущности и связи из уже накопленных записей памяти (нужно, если память писалась со сломанной экстракцией)."
                >
                  {reindexing ? '♻️ Пересобираем...' : '♻️ Пересобрать'}
                </button>
                <button
                  className="pixel-btn danger dossier-forget"
                  onClick={onAskForget}
                  data-hint="Полностью стереть профильный граф памяти: персонаж забудет все прошлые сессии."
                >
                  🧹 Забыть всё
                </button>
              </>
            ) : (
              <span className="dossier-forget-confirm">
                Стереть всю память?
                <button className="pixel-btn danger" onClick={onForget} disabled={forgetting}>
                  {forgetting ? 'Стираем...' : 'Да, забыть'}
                </button>
                <button className="pixel-btn ghost" onClick={onCancelForget}>Отмена</button>
              </span>
            )}
          </div>
          {(memory.entities || []).length > 0 && (
            <div className="dossier-memory-entities">
              {memory.entities.slice(0, 24).map((entity) => (
                <span
                  key={entity.name}
                  className="dossier-memory-entity"
                  title={`${entity.type}${entity.summary ? `: ${entity.summary}` : ''}`}
                >
                  {entity.name}
                </span>
              ))}
              {memory.entityCount > 24 && (
                <span className="dossier-memory-more">+{memory.entityCount - 24}…</span>
              )}
            </div>
          )}
          {(memory.facts || []).length > 0 && (
            <ul className="dossier-notes">
              {memory.facts.slice(0, 6).map((fact, index) => (
                <li key={`fact-${index}`}>{fact.fact}</li>
              ))}
            </ul>
          )}
          {memory.entityCount === 0 && (memory.entries || []).length > 0 && (
            <>
              <div className="dossier-memory-note-title">
                Что персонаж запомнил дословно (граф ещё не структурирован):
              </div>
              <ul className="dossier-notes">
                {memory.entries.slice(0, 6).map((entry, index) => (
                  <li key={`entry-${index}`}>{entry}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <div className="dossier-section-title">Ачивки</div>
      {(dossier.achievements || []).length === 0 ? (
        <div className="dossier-empty">Награды появятся после раундов с Хрономантом.</div>
      ) : (
        <ul className="dossier-achievements">
          {dossier.achievements.map((item, index) => (
            <li key={`${item.roundNumber}-${index}`}>
              <span className="dossier-achievement-round">Раунд {item.roundNumber}</span>
              <span className="dossier-achievement-body">
                <strong>⚑ {item.title}</strong>
                {item.reason && <em>{item.reason}</em>}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="dossier-section-title">Заметки Хрономанта</div>
      {(dossier.notes || []).length === 0 ? (
        <div className="dossier-empty">Персональных заметок пока нет.</div>
      ) : (
        <ul className="dossier-notes">
          {dossier.notes.slice().reverse().map((note, index) => (
            <li key={`${note.roundNumber}-${index}`}>{note.text}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function LabDrawer({ open, onClose }) {
  const [dossiers, setDossiers] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [memory, setMemory] = useState(null)
  const [confirmForget, setConfirmForget] = useState(false)
  const [forgetting, setForgetting] = useState(false)
  const [loadingList, setLoadingList] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const pollActiveRef = useRef(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoadingList(true)
    setError('')
    fetch('/api/lab/profiles')
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('Не удалось загрузить лабораторию'))))
      .then((data) => {
        if (!cancelled) setDossiers(data.dossiers || [])
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  useEffect(() => {
    if (!open || !selectedId) {
      setDetail(null)
      return
    }
    let cancelled = false
    setLoadingDetail(true)
    fetch(`/api/lab/profiles/${selectedId}`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('Не удалось загрузить досье'))))
      .then((data) => {
        if (!cancelled) setDetail(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, selectedId])

  useEffect(() => {
    if (!open || !selectedId) {
      setMemory(null)
      setConfirmForget(false)
      return
    }
    pollActiveRef.current = false
    let cancelled = false
    fetch(`/api/lab/profiles/${selectedId}/memory`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('Не удалось загрузить память'))))
      .then((data) => {
        if (!cancelled) setMemory(data)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [open, selectedId])

  async function forgetMemory() {
    if (!selectedId) return
    setForgetting(true)
    setError('')
    try {
      const response = await fetch(`/api/lab/profiles/${selectedId}/memory`, { method: 'DELETE' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Не удалось сбросить память')
      setMemory((current) => (
        current
          ? { ...current, hasMemory: false, entities: [], facts: [], entityCount: 0, factCount: 0 }
          : current
      ))
      setDetail((current) => (
        current ? { ...current, hasMemory: false, memoryGraphId: null } : current
      ))
      setDossiers((current) => current.map((item) => (
        item.id === selectedId ? { ...item, hasMemory: false } : item
      )))
      setConfirmForget(false)
      setNotice(data.clearedGraph
        ? 'Память персонажа полностью стёрта.'
        : 'У персонажа уже не было памяти.')
    } catch (err) {
      setError(err.message || 'Ошибка сброса памяти.')
    } finally {
      setForgetting(false)
    }
  }

  async function reindexMemory() {
    if (!selectedId || reindexing) return
    setReindexing(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`/api/lab/profiles/${selectedId}/memory/reindex`, { method: 'POST' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Не удалось запустить пересборку памяти')
      pollActiveRef.current = true
      setNotice(`Пересборка запущена: записей к обработке — ${data.total}. Это может занять пару минут.`)
      const deadline = Date.now() + 15 * 60 * 1000
      while (Date.now() < deadline && pollActiveRef.current) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        if (!pollActiveRef.current) return
        const statusResponse = await fetch(`/api/lab/profiles/${selectedId}/memory/reindex-status`)
        const status = await statusResponse.json()
        if (status.status === 'running') {
          setNotice(`Пересобираем память: ${status.processed}/${status.total}...`)
          continue
        }
        if (status.status === 'done') {
          const memResponse = await fetch(`/api/lab/profiles/${selectedId}/memory`)
          if (memResponse.ok) setMemory(await memResponse.json())
          setDetail((current) => (
            current ? { ...current, hasMemory: true } : current
          ))
          setDossiers((current) => current.map((item) => (
            item.id === selectedId ? { ...item, hasMemory: true } : item
          )))
          setNotice(`Память пересобрана: обработано ${status.processed} записей.`)
          break
        }
        setError(status.error || 'Пересборка памяти не удалась.')
        break
      }
    } catch (err) {
      setError(err.message || 'Ошибка пересборки памяти.')
    } finally {
      setReindexing(false)
    }
  }

  if (!open) return null

  return (
    <div className="drawer-shell" onClick={onClose}>
      <aside className="drawer drawer-right drawer-lab" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <div className="drawer-kicker">Лаборатория</div>
            <div className="drawer-title">Досье персонажей</div>
          </div>
          <button className="drawer-close" onClick={onClose}>×</button>
        </div>

        <div className="drawer-content lab-content">
          {error && <div className="drawer-empty lab-error">{error}</div>}
          {notice && !error && <div className="drawer-empty lab-notice">{notice}</div>}

          {!detail && loadingList && <div className="drawer-empty">Собираем досье...</div>}
          {!detail && !loadingList && !error && dossiers.length === 0 && (
            <div className="drawer-empty">Сохранённых персонажей пока нет.</div>
          )}

          {!detail && !loadingList && dossiers.length > 0 && (
            <div className="lab-grid">
              {dossiers.map((dossier) => (
                <LabCard key={dossier.id} dossier={dossier} onOpen={setSelectedId} />
              ))}
            </div>
          )}

          {detail && loadingDetail && <div className="drawer-empty">Открываем досье...</div>}
          {detail && !loadingDetail && (
            <DossierView
              dossier={detail}
              memory={memory}
              confirmForget={confirmForget}
              forgetting={forgetting}
              onBack={() => setSelectedId(null)}
              reindexing={reindexing}
              onAskForget={() => setConfirmForget(true)}
              onCancelForget={() => setConfirmForget(false)}
              onForget={forgetMemory}
              onReindex={reindexMemory}
            />
          )}
        </div>
      </aside>
    </div>
  )
}
