import React from 'react'
import PixelSprite from '../PixelSprite.jsx'
import { resolveMascot } from '../Mascot.jsx'
import { getRoleLabel } from '../../constants/roles.js'
import { getSpecialtyLabel } from '../../constants/specialties.js'

export default function TeamPresetsPanel({
  teamPresets = [],
  presetName,
  presetPanelOpen,
  presetPreviewId,
  editable,
  canSavePreset,
  onPresetNameChange,
  onToggleOpen,
  onTogglePreview,
  onSavePreset,
  onApplyPreset,
  onDeletePreset,
}) {
  return (
    <div className={`preset-panel ${presetPanelOpen ? 'is-open' : 'is-collapsed'}`}>
      <button
        type="button"
        className="preset-panel-toggle"
        onClick={onToggleOpen}
        aria-expanded={presetPanelOpen}
        data-hint="Сохранённые составы позволяют быстро вернуть готовую команду. Панель можно свернуть, чтобы освободить место."
      >
        <span>{presetPanelOpen ? '▾' : '▸'} Сохранённые составы</span>
        <span className="preset-count-chip">{teamPresets.length ? `${teamPresets.length} шт.` : 'пусто'}</span>
      </button>

      {presetPanelOpen && (
        <div className="preset-panel-body">
          <div className="preset-panel-head">
            <div className="preset-panel-sub">Сохраняют текущих участников за столом как готовую команду.</div>
          </div>
          <div className="preset-create-row">
            <input
              className="mini-input"
              value={presetName}
              onChange={(event) => onPresetNameChange?.(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && canSavePreset && onSavePreset?.()}
              placeholder="Имя состава"
            />
            <button
              className="pixel-btn ghost"
              onClick={onSavePreset}
              disabled={!canSavePreset}
              data-hint="Сохранить текущий состав стола как готовую команду."
            >
              Сохранить состав
            </button>
          </div>
          <div className="preset-list">
            {teamPresets.length === 0 && (
              <div className="preset-empty">Пока нет сохранённых составов. Соберите команду и сохраните её здесь.</div>
            )}
            {teamPresets.map((preset) => {
              const previewOpen = presetPreviewId === preset.id
              return (
                <div key={preset.id} className="preset-card-stack">
                  <div className="preset-card">
                    <div className="preset-card-main">
                      <div className="preset-card-name">{preset.name}</div>
                      <div className="preset-card-meta">
                        {preset.participants?.map((participant) => participant.name).filter(Boolean).slice(0, 4).join(' • ') || 'Состав без имён'}
                        {(preset.participants?.length || 0) > 4 ? ` • ещё ${(preset.participants?.length || 0) - 4}` : ''}
                      </div>
                    </div>
                    <div className="preset-card-actions">
                      <button
                        className="pixel-btn ghost"
                        onClick={() => onTogglePreview?.(preset.id)}
                        data-hint="Показать, кто именно входит в этот сохранённый состав."
                      >
                        {previewOpen ? 'Скрыть' : 'Состав'}
                      </button>
                      <button
                        className="pixel-btn ghost"
                        onClick={() => onApplyPreset?.(preset.id)}
                        disabled={!editable}
                        data-hint="Применить этот состав к текущей комнате."
                      >
                        Применить
                      </button>
                      <button
                        className="pixel-btn danger"
                        onClick={() => onDeletePreset?.(preset.id)}
                        data-hint="Удалить сохранённый состав."
                      >
                        Удалить
                      </button>
                    </div>
                  </div>

                  {previewOpen && (
                    <div className="preset-preview-grid">
                      {(preset.participants || []).map((participant, index) => {
                        const mascot = resolveMascot(participant)
                        return (
                          <div key={`${preset.id}-${participant.name || index}`} className="preset-preview-card">
                            <div className="preset-preview-avatar">
                              <PixelSprite mascot={mascot} emotion="neutral" size={28} />
                            </div>
                            <div className="preset-preview-main">
                              <div className="preset-preview-name">{participant.name || `Герой ${index + 1}`}</div>
                              <div className="preset-preview-meta">
                                {getRoleLabel(participant.role)} · {getSpecialtyLabel(participant.specialty, participant.specialtyLabel)}
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
