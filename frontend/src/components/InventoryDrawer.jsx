import React, { useEffect, useState } from 'react'
import { getRoleLabel } from '../constants/roles.js'
import { getSpecialtyLabel } from '../constants/specialties.js'
import PixelSprite from './PixelSprite.jsx'
import { resolveMascot } from './Mascot.jsx'

const TABS = [
  { value: 'active', label: 'За столом' },
  { value: 'benched', label: 'Скамейка' },
  { value: 'inventory', label: 'Все персонажи' },
]

const STAT_LABELS = {
  insight: 'Инсайт',
  focus: 'Фокус',
  depth: 'Глубина',
  cooperation: 'Кооперация',
  showmanship: 'Сценичность',
}

function StatBar({ label, value = 0 }) {
  return (
    <div className="stat-row">
      <span>{label}</span>
      <div className="stat-track">
        <div className="stat-fill" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
      <span>{value}</span>
    </div>
  )
}

function CharacterCard({ entity, actions = [], selectable, selected, onToggleSelect }) {
  const stats = entity.stats || {}
  const hasMemory = Boolean(entity.hasMemory || entity.memoryGraphId)
  const mascot = resolveMascot(entity)
  const strongTopics = Array.isArray(entity.strengths) ? entity.strengths.slice(0, 3) : []
  return (
    <div className="character-card">
      <div className="character-card-top">
        <div className="character-avatar">
          <PixelSprite mascot={mascot} emotion="neutral" size={36} />
        </div>
        <div className="character-meta">
          <div className="character-name-row">
            <div className="character-name">{entity.name}</div>
            {hasMemory && (
              <span
                className="character-memory-badge"
                title="У профиля есть содержательная память между сессиями."
                data-hint="Память профиля: этот персонаж сохранял прошлые ответы в личный граф и может использовать их в следующих обсуждениях."
                aria-label="У профиля есть память между сессиями"
              >
                🧠
              </span>
            )}
          </div>
          <div className="character-role">
            {getRoleLabel(entity.role)} · {getSpecialtyLabel(entity.specialty, entity.specialtyLabel)}
          </div>
        </div>
        {selectable && (
          <label className="character-check">
            <input type="checkbox" checked={selected} onChange={onToggleSelect} />
          </label>
        )}
      </div>

      <div className="character-summary">{entity.summary || entity.lastNote || 'Характеристики появятся после первой полной сессии.'}</div>

      <div className="character-insight-stack">
        {strongTopics.length > 0 && (
          <div className="character-insight-line">
            <strong>Сильные темы:</strong> {strongTopics.join(' · ')}
          </div>
        )}
        {entity.summary && (
          <div className="character-insight-line">
            <strong>Обычно привносит:</strong> {entity.summary}
          </div>
        )}
        {entity.lastNote && (
          <div className="character-insight-line">
            <strong>Ролевой след:</strong> {entity.lastNote}
          </div>
        )}
      </div>

      <div className="stat-grid">
        {Object.entries(STAT_LABELS).map(([key, label]) => (
          <StatBar key={key} label={label} value={stats[key] || 0} />
        ))}
      </div>

      <div className="character-note">
        <strong>Последняя заметка:</strong> {entity.lastNote || 'Пока без заметок.'}
      </div>

      {entity.strengths?.length > 0 && (
        <div className="character-tag-row">
          <span>Сильные темы:</span>
          {entity.strengths.map((item) => <em key={item}>{item}</em>)}
        </div>
      )}

      {entity.weaknesses?.length > 0 && (
        <div className="character-tag-row weak">
          <span>Слабые темы:</span>
          {entity.weaknesses.map((item) => <em key={item}>{item}</em>)}
        </div>
      )}

      {actions.length > 0 && (
        <div className="character-actions">
          {actions.map((action) => (
            <button
              key={action.label}
              className={`pixel-btn ${action.variant || 'ghost'}`}
              onClick={action.onClick}
              data-hint={action.hint}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function InventoryDrawer({
  open,
  activeParticipants,
  benchedParticipants,
  inventory,
  onClose,
  onAddFromInventory,
  onBenchParticipant,
  onRestoreParticipant,
  onSaveParticipant,
  onDeleteProfile,
}) {
  const [tab, setTab] = useState('active')
  const [selectedIds, setSelectedIds] = useState(new Set())

  useEffect(() => {
    if (!open) {
      setSelectedIds(new Set())
    }
  }, [open])

  const selectedCount = selectedIds.size
  if (!open) {
    return null
  }

  function toggleInventory(profileId) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(profileId)) {
        next.delete(profileId)
      } else {
        next.add(profileId)
      }
      return next
    })
  }

  function bulkAdd() {
    if (selectedIds.size === 0) return
    onAddFromInventory(Array.from(selectedIds))
    setSelectedIds(new Set())
  }

  const activeCards = activeParticipants.map((participant) => ({
    entity: participant,
    actions: [
      {
        label: participant.isSavedProfile ? 'Обновить профиль' : 'Сохранить как профиль',
        onClick: () => onSaveParticipant(participant),
      },
      {
        label: 'На скамейку',
        variant: 'ghost',
        onClick: () => onBenchParticipant(participant.id),
      },
      ...(participant.isSavedProfile
        ? [{
            label: 'Удалить профиль',
            variant: 'danger',
            onClick: () => onDeleteProfile(participant.profileId),
          }]
        : []),
    ],
  }))

  const benchCards = benchedParticipants.map((participant) => ({
    entity: participant,
    actions: [
      {
        label: participant.isSavedProfile ? 'Обновить профиль' : 'Сохранить как профиль',
        onClick: () => onSaveParticipant(participant),
      },
      {
        label: 'Вернуть',
        onClick: () => onRestoreParticipant(participant.id),
      },
      ...(participant.isSavedProfile
        ? [{
            label: 'Удалить профиль',
            variant: 'danger',
            onClick: () => onDeleteProfile(participant.profileId),
          }]
        : []),
    ],
  }))

  return (
    <div className="drawer-shell" onClick={onClose}>
      <aside className="drawer drawer-right" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <div className="drawer-kicker">Инвентарь</div>
            <div className="drawer-title">Персонажи и состав стола</div>
          </div>
          <button className="drawer-close" onClick={onClose}>×</button>
        </div>

        <div className="drawer-tabs">
          {TABS.map((item) => (
            <button
              key={item.value}
              className={`drawer-tab${tab === item.value ? ' is-active' : ''}`}
              onClick={() => setTab(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {tab === 'inventory' && (
          <div className="inventory-bulk-bar">
            <div>Выбрано персонажей: {selectedCount}</div>
            <button className="pixel-btn add" onClick={bulkAdd} disabled={selectedCount === 0}>
              Добавить за стол
            </button>
          </div>
        )}

        <div className="drawer-content">
          {tab === 'active' && activeCards.length === 0 && (
            <div className="drawer-empty">За столом пока никого нет.</div>
          )}
          {tab === 'active' && activeCards.map(({ entity, actions }) => (
            <CharacterCard key={entity.id} entity={entity} actions={actions} />
          ))}

          {tab === 'benched' && benchCards.length === 0 && (
            <div className="drawer-empty">Скамейка пока пуста.</div>
          )}
          {tab === 'benched' && benchCards.map(({ entity, actions }) => (
            <CharacterCard key={entity.id} entity={entity} actions={actions} />
          ))}

          {tab === 'inventory' && inventory.length === 0 && (
            <div className="drawer-empty">Сохранённых персонажей пока нет.</div>
          )}
          {tab === 'inventory' && inventory.map((profile) => (
            <CharacterCard
              key={profile.id}
              entity={profile}
              selectable
              selected={selectedIds.has(profile.id)}
              onToggleSelect={() => toggleInventory(profile.id)}
              actions={[
                {
                  label: 'За стол',
                  onClick: () => onAddFromInventory([profile.id]),
                  hint: 'Вернуть сохранённого персонажа из инвентаря за текущий круглый стол.',
                },
                {
                  label: 'Удалить из инвентаря',
                  variant: 'danger',
                  onClick: () => onDeleteProfile(profile.id),
                  hint: 'Удалить сохранённый профиль персонажа и его привязанные данные из инвентаря.',
                },
              ]}
            />
          ))}
        </div>
      </aside>
    </div>
  )
}
