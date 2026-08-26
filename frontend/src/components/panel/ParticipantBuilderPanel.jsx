import React from 'react'
import { MASCOT_DEFS, MASCOT_LABELS } from '../Mascot.jsx'
import { ROLE_OPTIONS } from '../../constants/roles.js'

function renderSpecialtyOptions(groups) {
  return groups.map((group) => (
    <optgroup key={group.label} label={group.label}>
      {group.options.map((specialty) => (
        <option key={specialty.value} value={specialty.value}>
          {specialty.label}
        </option>
      ))}
    </optgroup>
  ))
}

function formatMascotLabel(mascot) {
  const label = MASCOT_LABELS[mascot] || mascot
  return label ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : mascot
}

export default function ParticipantBuilderPanel({
  name,
  role,
  specialty,
  provider,
  model,
  mascot,
  saveToInventory,
  specialtyGroups,
  availableProviders,
  providerModels,
  onNameChange,
  onRoleChange,
  onSpecialtyChange,
  onProviderChange,
  onModelChange,
  onMascotChange,
  onSaveToInventoryChange,
  onCreateParticipant,
}) {
  return (
    <>
      <div className="builder-title">Создать персонажа</div>

      <div className="builder-grid">
        <input
          className="mini-input"
          placeholder="Имя героя"
          value={name}
          onChange={(event) => onNameChange?.(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && onCreateParticipant?.()}
        />
        <select className="mini-select" value={role} onChange={(event) => onRoleChange?.(event.target.value)}>
          {ROLE_OPTIONS.map((roleOption) => (
            <option key={roleOption.value} value={roleOption.value}>{roleOption.label}</option>
          ))}
        </select>
        <select className="mini-select specialty-select" value={specialty} onChange={(event) => onSpecialtyChange?.(event.target.value)}>
          {renderSpecialtyOptions(specialtyGroups)}
        </select>
        <select className="mini-select" value={provider} onChange={(event) => onProviderChange?.(event.target.value)}>
          {availableProviders.map((providerOption) => (
            <option key={providerOption} value={providerOption}>{providerOption}</option>
          ))}
        </select>
        <select className="mini-select" value={model} onChange={(event) => onModelChange?.(event.target.value)}>
          {providerModels.map((modelOption) => (
            <option key={modelOption} value={modelOption}>{modelOption}</option>
          ))}
        </select>
        <select className="mini-select" value={mascot} onChange={(event) => onMascotChange?.(event.target.value)}>
          {Object.keys(MASCOT_DEFS).map((mascotOption) => (
            <option key={mascotOption} value={mascotOption}>
              {MASCOT_DEFS[mascotOption].emoji} {formatMascotLabel(mascotOption)}
            </option>
          ))}
        </select>
      </div>

      <div className="builder-action-row">
        <label className="builder-check">
          <input
            type="checkbox"
            checked={saveToInventory}
            onChange={(event) => onSaveToInventoryChange?.(event.target.checked)}
          />
          Сразу сохранить в инвентарь
        </label>

        <button className="pixel-btn add" onClick={onCreateParticipant} data-hint="Создать персонажа с выбранными ролью, профилем и моделью.">+ Посадить за стол</button>
      </div>
    </>
  )
}
