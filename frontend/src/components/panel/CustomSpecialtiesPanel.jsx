import React from 'react'

export default function CustomSpecialtiesPanel({
  customSpecialtyGroups = [],
  onCreateCustomSpecialty,
  onUpdateCustomSpecialty,
  onDeleteCustomSpecialty,
}) {
  const [open, setOpen] = React.useState(false)
  const [label, setLabel] = React.useState('')
  const [groupLabel, setGroupLabel] = React.useState('Кастомные оптики')
  const [description, setDescription] = React.useState('')
  const [editingId, setEditingId] = React.useState('')
  const [editLabel, setEditLabel] = React.useState('')
  const [editGroupLabel, setEditGroupLabel] = React.useState('')
  const [editDescription, setEditDescription] = React.useState('')
  const [error, setError] = React.useState('')

  const customOptions = (customSpecialtyGroups || []).flatMap((group) => (
    (group.options || []).map((option) => ({
      ...option,
      groupLabel: option.groupLabel || group.label || 'Кастомные оптики',
    }))
  ))

  async function createSpecialty() {
    const nextLabel = label.trim()
    if (!nextLabel) {
      setError('Введите название экспертизы.')
      return
    }
    try {
      setError('')
      await onCreateCustomSpecialty?.({
        label: nextLabel,
        groupLabel: groupLabel.trim() || 'Кастомные оптики',
        description: description.trim(),
      })
      setLabel('')
      setDescription('')
    } catch (err) {
      setError(err.message || 'Не удалось создать экспертизу.')
    }
  }

  function startEdit(option) {
    setEditingId(option.id)
    setEditLabel(option.label || '')
    setEditGroupLabel(option.groupLabel || 'Кастомные оптики')
    setEditDescription(option.description || '')
    setError('')
  }

  async function saveEdit(optionId) {
    if (!editLabel.trim()) {
      setError('Название экспертизы не может быть пустым.')
      return
    }
    try {
      setError('')
      await onUpdateCustomSpecialty?.(optionId, {
        label: editLabel.trim(),
        groupLabel: editGroupLabel.trim() || 'Кастомные оптики',
        description: editDescription.trim(),
      })
      setEditingId('')
    } catch (err) {
      setError(err.message || 'Не удалось обновить экспертизу.')
    }
  }

  async function deleteSpecialty(optionId) {
    try {
      setError('')
      await onDeleteCustomSpecialty?.(optionId)
    } catch (err) {
      setError(err.message || 'Не удалось удалить экспертизу.')
    }
  }

  return (
    <div className={`expertise-panel ${open ? 'is-open' : 'is-collapsed'}`}>
      <button
        type="button"
        className="expertise-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        data-hint="Пользовательские экспертизы — узкие профессиональные направления, которых нет в базовом списке. Их можно выбрать при создании персонажа или использовать в кастинг-помощнике."
      >
        <span>{open ? '▾' : '▸'} Экспертизы</span>
        <span className="expertise-count-chip">{customOptions.length ? `${customOptions.length} кастомн.` : 'базовые'}</span>
      </button>

      {open && (
        <div className="expertise-body">
          <div className="preset-panel-sub">
            Роль за столом задаёт стиль поведения. Экспертиза задаёт область знания: биология, урбанистика, медицина, игровая экономика и любые редкие оптики.
          </div>

          <div className="expertise-create-grid">
            <input
              className="mini-input"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && createSpecialty()}
              placeholder="Например: эволюционный биолог"
              data-hint="Название будет видно в карточках, чате и промпте агента."
            />
            <input
              className="mini-input"
              value={groupLabel}
              onChange={(event) => setGroupLabel(event.target.value)}
              placeholder="Группа"
              data-hint="Группа в выпадающем списке. Можно оставить «Кастомные оптики»."
            />
            <button
              type="button"
              className="pixel-btn add"
              onClick={createSpecialty}
              data-hint="Добавить новую экспертизу в список профилей персонажа."
            >
              Добавить
            </button>
            <input
              className="mini-input expertise-description-input"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Короткое описание, необязательно"
              data-hint="Описание помогает помнить, зачем добавлена эта экспертиза."
            />
          </div>

          {error && <div className="documents-error">{error}</div>}

          <div className="expertise-list">
            {customOptions.length === 0 && (
              <div className="preset-empty">Кастомных экспертиз пока нет. Базовый список остаётся доступен.</div>
            )}
            {customOptions.map((option) => (
              <div key={option.id || option.value} className="expertise-card">
                {editingId === option.id ? (
                  <>
                    <input
                      className="mini-input"
                      value={editLabel}
                      onChange={(event) => setEditLabel(event.target.value)}
                      placeholder="Название"
                    />
                    <input
                      className="mini-input"
                      value={editGroupLabel}
                      onChange={(event) => setEditGroupLabel(event.target.value)}
                      placeholder="Группа"
                    />
                    <input
                      className="mini-input"
                      value={editDescription}
                      onChange={(event) => setEditDescription(event.target.value)}
                      placeholder="Описание"
                    />
                    <div className="expertise-card-actions">
                      <button className="pixel-btn add" onClick={() => saveEdit(option.id)}>Сохранить</button>
                      <button className="pixel-btn ghost" onClick={() => setEditingId('')}>Отмена</button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="expertise-card-main">
                      <div className="expertise-card-name">{option.label}</div>
                      <div className="expertise-card-meta">
                        {option.groupLabel}{option.description ? ` · ${option.description}` : ''}
                      </div>
                    </div>
                    <div className="expertise-card-actions">
                      <button
                        className="pixel-btn ghost"
                        onClick={() => startEdit(option)}
                        data-hint="Переименовать экспертизу или перенести её в другую группу."
                      >
                        Править
                      </button>
                      <button
                        className="pixel-btn danger"
                        onClick={() => deleteSpecialty(option.id)}
                        data-hint="Удалить экспертизу. Если она уже используется персонажем или составом, удаление будет заблокировано."
                      >
                        Удалить
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
